"""FK-preflighted, measured-control executor; preserves the Project_v1 API.

No object state is used. A planning rejection leaves physics paused. completed
means the interval has ended, not that its target was reached; see explicit flags.
"""
from __future__ import annotations
import copy,hashlib,json,time
import numpy as np
from scipy.spatial.transform import Rotation
from demos.lab_cuvette_project_v1.environment import ProjectEnvironment as Previous,_jsonable


class ProjectEnvironment(Previous):
    def reset(self,*args,**kwargs):
        result=super().reset(*args,**kwargs)
        self.requested_opening=float(self.task.grip)
        self.requested_effort=float(self.task.effort)
        return result

    def receipt(self,action_id):
        value=super().receipt(action_id)
        return None if value is None else {k:v for k,v in value.items() if not k.startswith('_')}

    def finish(self,reason='POLICY_FINISH_REQUEST',*,failure_type=None):
        allowed={None,'MODEL_SERVICE_ERROR','INPUT_CONTRACT_ERROR','PROCESS_INTERRUPTED',
                 'PHYSICS_INVALID','EXECUTOR_FAILURE','SIMULATION_FAILURE','SAFETY_FAILURE'}
        if failure_type not in allowed:raise ValueError('Unsupported backend failure classification')
        if not self.task.ended:self.task.finalize_episode(str(reason),failure_type)
        return self.status()

    def execute(self,action):
        if not isinstance(action,dict):raise ValueError('Explicit action envelope required')
        action=_jsonable(action);aid=str(action.get('action_id',''))
        if not aid or len(aid)>128:raise ValueError('action_id must contain1..128 characters')
        digest=hashlib.sha256(json.dumps(action,sort_keys=True,allow_nan=False).encode()).hexdigest()
        if aid in self._receipts:
            if self._payload_hashes[aid]!=digest:raise ValueError('action_id reused with different payload')
            return self.receipt(aid)
        if self.task.ended:raise ValueError('Episode ended; reset before actions')
        obs=self.task.get_observation()
        if action.get('episode_id')!=obs['episode_id'] or action.get('observation_id')!=obs['observation_id']:raise ValueError('Stale episode_id or observation_id')
        if action.get('metadata'):raise ValueError('Public policies cannot select private phases')
        hz=float(self.task.cfg.physics.control_hz);duration=float(action.get('duration_s',1/hz))
        if not np.isfinite(duration):raise ValueError('Nonfinite duration')
        ticks=round(duration*hz)
        if ticks<1 or duration>3 or abs(ticks/hz-duration)>1e-6:raise ValueError('duration must be whole control ticks up to3seconds')
        kind=action.get('type');v=np.asarray(action.get('values',[]),float)
        if not np.isfinite(v).all():raise ValueError('Nonfinite action values')
        p0=np.asarray(obs['TCPpose']['position_m'],float);r0=Rotation.from_quat(np.roll(obs['TCPpose']['quaternion_wxyz'],-1))
        q0=np.asarray(obs['joint_positions'],float)[:7];p1=p0.copy();r1=r0
        if kind=='ee_delta':
            if v.shape!=(6,):raise ValueError('ee_delta requires6 values')
            if action.get('frame','world')=='world':p1=p0+v[:3];r1=Rotation.from_rotvec(v[3:])*r0
            elif action.get('frame')=='tcp':p1=p0+r0.apply(v[:3]);r1=r0*Rotation.from_rotvec(v[3:])
            else:raise ValueError('Unknown frame')
        elif kind=='ee_pose':
            if v.shape!=(7,) or abs(np.linalg.norm(v[3:])-1)>1e-3:raise ValueError('ee_pose requires world xyz + unit wxyz')
            if action.get('frame','world')!='world':raise ValueError('Absolute EE pose requires world')
            p1=v[:3];r1=Rotation.from_quat(np.roll(v[3:],-1))
        elif kind in ('joint_position','joint_velocity'):
            if v.shape not in ((7,),(9,)) or kind=='joint_velocity' and v.shape!=(7,):raise ValueError('Invalid joint action shape')
        else:raise ValueError('Unknown typed action')
        dr=(r1*r0.inv()).as_rotvec()
        if kind.startswith('ee_') and (np.linalg.norm(p1-p0)>.04+1e-9 or np.linalg.norm(p1-p0)/duration>.02+1e-9 or np.linalg.norm(dr)>.15+1e-9 or np.linalg.norm(dr)/duration>.15+1e-9):raise ValueError('EE distance/rotation/speed exceeds public limit')
        opening=float(action.get('gripper_opening_m',getattr(self,'requested_opening',self.task.grip)))
        if kind=='joint_position' and v.shape==(9,):
            if np.any(v[7:]<0) or np.any(v[7:]>.04) or abs(v[7]-v[8])>1e-7:raise ValueError('Joint9 fingers must be legal symmetric positions')
            if 'gripper_opening_m' in action and abs(sum(v[7:])-opening)>1e-7:raise ValueError('Joint9 fingers contradict total opening')
            opening=float(sum(v[7:]))
        effort=float(action.get('gripper_effort_limit_N',getattr(self,'requested_effort',self.task.effort)))
        if not np.isfinite([opening,effort]).all() or not 0<=opening<=.08 or not 0<=effort<=8:raise ValueError('Invalid gripper command')
        changing_opening=abs(opening-getattr(self,'requested_opening',self.task.grip))>1e-10
        start_opening=float(self.task.grip) # actual APPLIED target, never deformed measured opening
        receipt=dict(action_id=aid,episode_id=obs['episode_id'],observation_id=obs['observation_id'],
            accepted=False,execution_finished=False,target_reached=False,safety_stopped=False,completed=False,
            completed_semantics='Execution interval ended; target_reached independently measures actual endpoint.',
            requested_duration_s=duration,executed_duration_s=0.,executed_control_ticks=0,partial_execution=False,
            simulation_time_before=float(self.task.t),requested_start_TCP=copy.deepcopy(obs['TCPpose']),
            requested_target_TCP=dict(position_m=p1.tolist(),quaternion_wxyz=np.roll(r1.as_quat(),1).tolist()),
            maximum_position_tracking_error_m=0.,maximum_orientation_tracking_error_rad=0.,stop_reason=None)
        receipt.update(control_steps_before=int(self.task.control_steps),physics_steps_before=int(getattr(self.task,'steps',0)))
        self._payload_hashes[aid]=digest;self._receipts[aid]=receipt
        wall=time.perf_counter();references=[];plan=[]
        try:
            if kind.startswith('ee_'):
                for i in range(ticks):
                    fraction=(i+1)/ticks;references.append((p0+(p1-p0)*fraction,Rotation.from_rotvec(dr*fraction)*r0))
                planned=self.task.plan_cartesian(references)
                receipt['plan']=planned['summary']
                if not planned['success']:
                    receipt.update(stop_reason='CONTROL_PLAN_REJECTED',status='REJECTED',planning_failure=planned['failure'])
                    return self._finish_receipt(receipt,obs,wall,ticks,p1,r1)
                plan=planned['q7']
            else:
                q1=v[:7] if kind=='joint_position' else q0+v*duration
                lower,upper,speed=self.task.joint_bounds()
                if np.any(q1<lower) or np.any(q1>upper) or np.any(abs(q1-q0)/duration>speed):
                    receipt.update(stop_reason='JOINT_PLAN_REJECTED',status='REJECTED')
                    return self._finish_receipt(receipt,obs,wall,ticks,p1,r1)
                plan=[q0+(q1-q0)*(i+1)/ticks for i in range(ticks)]
                previous=self.task.qcmd[:7]
                for q in plan:
                    if np.any(abs(q-previous)>speed/hz+1e-9):
                        receipt.update(stop_reason='JOINT_PLAN_REJECTED',status='REJECTED')
                        return self._finish_receipt(receipt,obs,wall,ticks,p1,r1)
                    previous=q
                p1,R=self.task.forward(plan[-1]);r1=Rotation.from_matrix(R)
                receipt['requested_target_TCP']=dict(position_m=p1.tolist(),quaternion_wxyz=np.roll(r1.as_quat(),1).tolist())
                references=[(np.asarray(self.task.forward(q)[0]),Rotation.from_matrix(self.task.forward(q)[1])) for q in plan]
            receipt.update(accepted=True,status='EXECUTING');self.requested_opening=opening;self.requested_effort=effort
            for i,(q,(p,r)) in enumerate(zip(plan,references)):
                if self.task.ended:break
                low=dict(episode_id=obs['episode_id'],observation_step=self.task.control_steps,type='ee_pose',
                    values=np.r_[p,np.roll(r.as_quat(),1)].tolist(),frame='world',duration_s=1/hz,
                    gripper_opening_m=start_opening+(opening-start_opening)*(i+1)/ticks if changing_opening else float(self.task.grip),
                    gripper_effort_limit_N=effort,raw_model_action=copy.deepcopy(action),_executor_q7=np.asarray(q).tolist(),
                    _executor_action_id=aid,_executor_interval_tick=i,_executor_fixed_start=receipt['requested_start_TCP'],
                    _executor_fixed_target=receipt['requested_target_TCP'])
                self.task.step(low)
                receipt['executed_control_ticks']=int(self.task.control_steps)-receipt['control_steps_before']
                now=self.task.get_observation();actual_p=np.asarray(now['TCPpose']['position_m']);actual_r=Rotation.from_quat(np.roll(now['TCPpose']['quaternion_wxyz'],-1))
                pe=float(np.linalg.norm(actual_p-p));oe=float((r*actual_r.inv()).magnitude())
                receipt['maximum_position_tracking_error_m']=max(pe,receipt['maximum_position_tracking_error_m'])
                receipt['maximum_orientation_tracking_error_rad']=max(oe,receipt['maximum_orientation_tracking_error_rad'])
            if self.task.ended:receipt['stop_reason']=(self.task._result or {}).get('termination_reason','ENVIRONMENT_TERMINATED')
            else:receipt['stop_reason']='INTERVAL_FINISHED'
        except Exception as error:
            receipt.update(stop_reason='EXECUTOR_EXCEPTION',executor_error_type=type(error).__name__,executor_error=str(error))
            receipt['exception_state_snapshot']=True
            try:self.task.hold_actual_joints()
            except Exception as hold_error:receipt['hold_error_type']=type(hold_error).__name__
            if not self.task.ended:self.task.finalize_episode('EXECUTOR_EXCEPTION','EXECUTOR_FAILURE')
        finally:
            if not receipt.get('execution_finished'):self._finish_receipt(receipt,obs,wall,ticks,p1,r1)
        return self.receipt(aid)

    def _finish_receipt(self,receipt,obs,wall,ticks,p1,r1):
        after=self.task.get_observation();endpoint=copy.deepcopy(after['TCPpose'])
        endpoint_valid=True;successor_available=not receipt.get('exception_state_snapshot',False)
        if not successor_available:
            # A render/recording exception may leave the public observation
            # cache at the preceding control tick although physics advanced.
            # Read robot-only FK without advancing; never label stale RGB as a
            # synchronized successor that the caller may execute against.
            try:
                p,R=self.task.forward(self.task.robot.get_joint_positions()[:7])
                endpoint=dict(position_m=np.asarray(p).tolist(),quaternion_wxyz=np.roll(Rotation.from_matrix(R).as_quat(),1).tolist())
            except Exception:endpoint=None;endpoint_valid=False
        if endpoint_valid:
            try:
                p=np.asarray(endpoint['position_m'],float);q=np.asarray(endpoint['quaternion_wxyz'],float)
                if p.shape!=(3,) or q.shape!=(4,) or not np.isfinite(np.r_[p,q]).all() or abs(np.linalg.norm(q)-1)>1e-3:raise ValueError('Invalid actual TCP')
                r=Rotation.from_quat(np.roll(q,-1))
            except (ValueError,TypeError,KeyError):endpoint_valid=False
        if not endpoint_valid:endpoint=None;successor_available=False
        pe=float(np.linalg.norm(p-p1)) if endpoint_valid else None
        oe=float((r1*r.inv()).magnitude()) if endpoint_valid else None
        n=int(self.task.control_steps)-receipt['control_steps_before']
        receipt['executed_control_ticks']=n
        physics_steps=int(getattr(self.task,'steps',0))-receipt['physics_steps_before']
        elapsed=float(self.task.t)-receipt['simulation_time_before']
        partial_control=abs(elapsed-n/float(self.task.cfg.physics.control_hz))>1e-7
        reason=receipt.get('stop_reason')
        result=self.task._result or {}
        domain=result.get('failure_domain')
        if domain is None:
            domain='executor' if reason not in ('CONTROL_PLAN_REJECTED','JOINT_PLAN_REJECTED') and reason and (reason.startswith('EXECUTOR') or reason.startswith('JOINT_')) else 'none'
        safe=domain in ('safety','executor','simulation')
        receipt.update(status='REJECTED' if not receipt['accepted'] else ('STOPPED' if safe or n<ticks or partial_control else 'FINISHED'),
            execution_finished=True,completed=True,target_reached=bool(endpoint_valid and receipt['accepted'] and n==ticks and pe<=.001 and oe<=np.deg2rad(.5) and not safe),
            safety_stopped=safe,partial_execution=bool(elapsed>0 and (n<ticks or partial_control)),executed_duration_s=elapsed,
            executed_physics_steps=physics_steps,incomplete_control_interval=partial_control,
            simulation_time_after=float(self.task.t),observation_id_after=after['observation_id'] if successor_available else None,
            successor_observation_available=successor_available,actual_endpoint_valid=endpoint_valid,actual_endpoint_TCP=endpoint,
            TCPpose=endpoint,final_position_error_m=pe,final_orientation_error_rad=oe,
            tracking_error_coverage_complete=not receipt.get('exception_state_snapshot',False),
            tracking_error_sampling='completed control boundaries; not a physics-substep maximum',
            target_reached_scope='TCP pose only; not a claim of grasp, gripper opening, or task success',
            requested_gripper_opening_m=getattr(self,'requested_opening',None),applied_gripper_opening_m=float(self.task.grip),
            requested_effort_limit_N=getattr(self,'requested_effort',None),applied_effort_limit_N=float(self.task.effort),
            stop_domain=domain,
            endpoint_tolerances=dict(position_m=.001,orientation_rad=float(np.deg2rad(.5))),wall_seconds=time.perf_counter()-wall,
            terminated=bool(self.task.ended),gripper_opening_m=float(after['gripper_opening_m']))
        path=self.task.episode_dir/'action_receipts.jsonl'
        # This method can be called once from return and again by finally; write once.
        if not receipt.get('_persisted'):
            with path.open('a') as f:f.write(json.dumps(receipt,allow_nan=False)+'\n')
            receipt['_persisted']=True
        return copy.deepcopy({k:v for k,v in receipt.items() if not k.startswith('_')})
