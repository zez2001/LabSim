"""Deterministic, model-free probes through the real task and public executor.

The legacy replay keeps the original action prefix and changes only run IDs.
Instrumentation reads solver inputs/results and actual states; no object writes.
"""
from __future__ import annotations
import argparse,copy,fcntl,hashlib,json,os,time
from pathlib import Path
import numpy as np
from scipy.spatial.transform import Rotation
from omegaconf import OmegaConf
from demos.lab_cuvette_project_v1.runtime import ROOT,resolve_config
from demos.lab_cuvette_project_v1.run import ensure_audit


def safe(value):
    if isinstance(value,np.ndarray):return value.tolist()
    if isinstance(value,np.generic):return value.item()
    if isinstance(value,dict):return {k:safe(v) for k,v in value.items()}
    if isinstance(value,(tuple,list)):return [safe(v) for v in value]
    return value


def write(path,value):Path(path).write_text(json.dumps(safe(value),indent=2,allow_nan=False)+'\n')


def pose_error(fk,goal):
    p,R=fk
    return dict(position_m=np.asarray(p).tolist(),quaternion_wxyz=np.roll(Rotation.from_matrix(np.asarray(R)).as_quat(),1).tolist(),
        position_error_m=float(np.linalg.norm(np.asarray(p)-np.asarray(goal[:3]))),
        orientation_error_rad=float((Rotation.from_quat(np.roll(goal[3:],-1))*Rotation.from_matrix(np.asarray(R)).inv()).magnitude()))


def traced_task_class():
    from tasks.lab_cuvette_loading_project_v1 import LabCuvetteProjectV1
    class TracedTask(LabCuvetteProjectV1):
        def _convert_action(self,action):
            original_solver=self.solver;kin=original_solver.get_kinematics_solver();calls=[]
            class Kin:
                def __getattr__(self,name):return getattr(kin,name)
                def compute_inverse_kinematics(self,*args,**kwargs):
                    before=time.perf_counter();result=kin.compute_inverse_kinematics(*args,**kwargs)
                    calls.append(dict(frame=args[0],target_position_m=args[1],target_quaternion_wxyz=args[2],warm_start=copy.deepcopy(kwargs.get('warm_start')),raw_solution=np.asarray(result[0]).copy(),valid=bool(result[1]),wall_seconds=time.perf_counter()-before))
                    return result
            class Solver:
                def get_kinematics_solver(self):return Kin()
                def __getattr__(self,name):return getattr(original_solver,name)
            row=dict(control_tick_before=self.control_steps,t_before=self.t,outer_action=getattr(self,'trace_outer',None),
                low_level_input=copy.deepcopy(action),seed_before=np.asarray(self._ik_seed).copy(),previous_command_q9=self.qcmd.copy(),
                actual_joints_before=self.robot.get_joint_positions().copy(),actual_TCP_before=dict(position_m=self.debug['actual_tcp_position_m'],quaternion_wxyz=self.debug['actual_tcp_quaternion_wxyz']))
            self.solver=Solver()
            try:
                result=super()._convert_action(action);q,opening,effort,ticks,conversion=result
                row.update(command_q9=q,opening_m=opening,effort_limit_N=effort,conversion=conversion)
                target=conversion.get('target_pose')
                if target:
                    goal=np.r_[target['position_m'],target['quaternion_wxyz']]
                    row['command_FK']=pose_error(kin.compute_forward_kinematics(original_solver.get_end_effector_frame(),q[:7]),goal)
                    for call in calls:
                        call['raw_solution_FK']=pose_error(kin.compute_forward_kinematics(call['frame'],call['raw_solution']),goal)
                        call['raw_delta_from_previous_command_rad']=np.asarray(call['raw_solution'])-self.qcmd[:7]
                return result
            except Exception as error:
                row.update(conversion_error_type=type(error).__name__,conversion_error=str(error));raise
            finally:
                self.solver=original_solver;row['IK_calls']=calls;self.trace_last=row
        def step(self,action):
            self.trace_last=None
            try:return super().step(action)
            finally:
                row=self.trace_last
                if row is not None:
                    row.update(t_after=self.t,physics_steps=self.steps,actual_joints_after=self.robot.get_joint_positions().copy(),
                        actual_joint_velocities=self.robot.get_joint_velocities().copy(),actual_TCP_after=dict(position_m=self.debug['actual_tcp_position_m'],quaternion_wxyz=self.debug['actual_tcp_quaternion_wxyz']),
                        measured_gripper_opening_m=float(np.sum(self.debug['finger_joint_positions_m'])),
                        actual_finger_contact_N=self.debug['finger_contact_N'],forbidden_robot_environment_contact=self.debug.get('forbidden_robot_environment_contact'),
                        ended=self.ended,termination_reason=(self._result or {}).get('termination_reason'))
                    with (self.episode_dir/'execution_trace.jsonl').open('a') as f:f.write(json.dumps(safe(row),allow_nan=False)+'\n')
    return TracedTask


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mode',choices=['legacy-replay'],default='legacy-replay')
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--headless',action='store_true')
    p.add_argument('--attempts',nargs='+',type=int,default=[1,2])
    args=p.parse_args(argv);out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    cfg=resolve_config(OmegaConf.load(ROOT/'config/lab_cuvette_loading/Project_v1/standard.yaml'))
    cfg.experiment.condition_group='control_diagnostic';cfg.env.execution_purpose='eval'
    OmegaConf.save(cfg,out/'launch_config.yaml');audit=ensure_audit(cfg,out);write(out/'geometry_audit.json',audit)
    if audit.get('geometry_valid') is not True:raise RuntimeError('Geometry audit failed')
    lock=open('/tmp/labsim-V0_ext01-gpu.lock','a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    os.environ['OMNI_KIT_ACCEPT_EULA']='YES'
    from isaacsim import SimulationApp
    app=SimulationApp(dict(headless=args.headless,width=1280,height=720,extra_args=['--/app/extensions/fsWatcherEnabled=false','--/app/hydraEngine/waitIdle=true','--/app/updateOrder/checkForHydraRenderComplete=1000']))
    task=None;results=[];started=time.perf_counter()
    try:
        Task=traced_task_class();task=Task(cfg,app,out,geometry_audit=audit)
        from demos.lab_cuvette_project_v1.environment import ProjectEnvironment
        from policy.backends.cubence_tools import GenericRobotTools
        limits=json.loads((ROOT/'config/lab_cuvette_loading/Project_v1/policies/cubence_gpt6.json').read_text())['action_limits']
        facade=ProjectEnvironment(task)
        for attempt in args.attempts:
            facade.reset(0,dict(mode='standard',teacher=False,policy_id='deterministic_original_GPT_prefix',demonstrator_id='LegacyPrefixReplay'))
            tools=GenericRobotTools(facade,limits);tools.observe()
            source=ROOT/'outputs/lab_cuvette_loading/Project_v1/gpt_formal5_01'/f'attempt_{attempt:04d}'/'episode_0000/gpt_control/policy_trace.jsonl'
            events=[json.loads(line) for line in source.read_text().splitlines()];records=[]
            write(task.episode_dir/'replay_source.json',dict(original_attempt=attempt,source_path=str(source.relative_to(ROOT)),sha256=hashlib.sha256(source.read_bytes()).hexdigest(),original_actions_unchanged_except_episode_observation_ID=True,no_model_calls=True,diagnostic_not_task_demonstration=True))
            for index,event in enumerate(events):
                call=event.get('tool_call')
                if call is None:
                    calls=event.get('model_tool_calls',[])
                    if len(calls)!=1:raise ValueError('Original replay event lacks one recorded tool call')
                    call=calls[0]
                arguments=copy.deepcopy(call['arguments'])
                if isinstance(arguments,str):arguments=json.loads(arguments)
                obs=tools.observe()
                arguments.update(episode_id=obs['episode_id'],observation_id=obs['observation_id'])
                task.trace_outer=dict(source_decision=index,tool_name=call['name'],arguments=arguments,fixed_start_TCP=obs['TCPpose'])
                before=time.perf_counter()
                try:receipt=tools.execute(call['name'],arguments);record=dict(index=index,receipt=receipt)
                except Exception as error:
                    receipt=tools.execution_receipt(arguments);record=dict(index=index,receipt=receipt,error_type=type(error).__name__,error=str(error))
                record['wall_seconds']=time.perf_counter()-before;records.append(record)
                print('DIAGNOSTIC_ACTION',attempt,index,json.dumps(safe(record)),flush=True)
                if task.ended or 'error' in record:break
            if not task.ended:task.finalize_episode('DETERMINISTIC_PREFIX_REPLAY_END','PHYSICS_INVALID' if any('error' in x for x in records) else 'POLICY_BUDGET')
            result=dict(attempt=attempt,episode_id=task.episode_id,episode_directory=task.episode_dir.name,actions=records,independent_result=task._result)
            results.append(result);write(out/'diagnostic_summary.json',results)
        write(out/'run_manifest.json',dict(mode=args.mode,wall_seconds=time.perf_counter()-started,model_calls=0,source_commit=__import__('subprocess').check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),diagnostic_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),baseline_interface='Unmodified Project_v1 ProjectEnvironment and GenericRobotTools; read-only IK instrumentation'))
    except BaseException as error:
        import traceback,sys
        detail=traceback.format_exc();write(out/'runner_failure.json',dict(type=type(error).__name__,error=str(error),traceback=detail))
        print(detail,file=sys.stderr,flush=True)
        raise
    finally:
        if task is not None:task.close()
        from omni.kit.app import get_app
        get_app().post_quit(0);app.close();lock.close()
    return 0

if __name__=='__main__':raise SystemExit(main())
