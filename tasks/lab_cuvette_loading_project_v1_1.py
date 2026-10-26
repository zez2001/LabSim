"""Independent Project_v1_1 task with continuous FK-verified robot commands."""
from __future__ import annotations
import copy,hashlib,json,time
import numpy as np
from scipy.spatial.transform import Rotation
from tasks.lab_cuvette_loading_project_v1 import LabCuvetteProjectV1
from demos.lab_cuvette_project_v1_1.continuous_ik import solve


class LabCuvetteProjectV11(LabCuvetteProjectV1):
    def _reset(self,seed=None,options=None):
        observation,info=super()._reset(seed,options)
        from demos.lab_cuvette_project_v1_1.contract import scene_contract
        self.release_contract=scene_contract(self.base_cfg,self.geometry_audit)
        self._write(self.episode_dir/'project_scene_contract.json',self.release_contract)
        path=self.episode_dir/'release_metadata.json';metadata=json.loads(path.read_text())
        metadata.update(scene_version='Project_v1_1',frozen_scene_sha256=self.release_contract['frozen_scene_sha256'],
            control_config_sha256=self.release_contract['frozen_scene_sha256'],action_interface_version='Project_v1_1.actions.v1')
        self.collector.file.attrs.update(metadata);self._write(path,metadata)
        self._tick_trace=None;self._write(self.episode_dir/'executor_configuration.json',dict(self.cfg.executor))
        from demos.lab_cuvette_project_v1_1.gripper_hold import GenericContactHold
        self.contact_hold=GenericContactHold(control_hz=self.cfg.physics.control_hz,mass_kg=self.cfg.vessel.mass_kg,
            dynamic_friction=self.cfg.physics.dynamic_friction,finger_dynamic_friction=self.cfg.physics.finger_dynamic_friction,
            finger_kp_N_per_m=self.ctx['old'].robot.finger_kp,contact_safety_factor=self.cfg.gripper.contact_safety_factor,
            maximum_compression_m=self.cfg.gripper.maximum_compression_m,contact_threshold_N=self.cfg.gripper.contact_threshold_N,
            contact_persist_s=self.cfg.gripper.contact_persist_s,contact_approach_speed_m_s=self.cfg.gripper.get('contact_approach_speed_m_s',.002),
            minimum_total_opening_m=2*self.cfg.gripper.get('minimum_latched_finger_m',.001))
        self._write(self.episode_dir/'contact_hold_configuration.json',dict(self.contact_hold.__dict__))
        tracking=dict(self.cfg.get('robot_tracking',{}))
        self.tracking_compensator=None;self._tracking_sample_control_step=-1
        if tracking.get('enabled',False):
            from demos.lab_cuvette_project_v1_1.robot_tracking import RobotTrackingCompensator
            self.tracking_compensator=RobotTrackingCompensator(time_constant_s=tracking['time_constant_s'],
                max_position_bias_m=tracking['max_position_bias_m'],max_rotation_bias_rad=tracking['max_rotation_bias_rad'])
        self._write(self.episode_dir/'robot_tracking_configuration.json',tracking)
        return observation,info

    def forward(self,q):
        kin=self.solver.get_kinematics_solver()
        p,R=kin.compute_forward_kinematics(self.solver.get_end_effector_frame(),np.asarray(q,float))
        return np.asarray(p,float),np.asarray(R,float)

    def joint_bounds(self):
        return (np.asarray(self.robot.dof_properties['lower'][:7],float),np.asarray(self.robot.dof_properties['upper'][:7],float),np.asarray(self.ctx['old'].robot.max_velocity[:7],float))

    def local_solution(self,p,r,seed):
        lower,upper,speed=self.joint_bounds()
        return solve(self.forward,seed,p,r.as_matrix(),lower,upper,max_joint_step_rad=speed/float(self.cfg.physics.control_hz),
            position_tolerance_m=float(self.cfg.executor.ik_position_tolerance_m),orientation_tolerance_rad=float(self.cfg.executor.ik_orientation_tolerance_rad),max_iterations=int(self.cfg.executor.ik_iterations))

    def plan_cartesian(self,references):
        start=time.perf_counter();seed=self.qcmd[:7].copy();commands=[];worst_p=0.;worst_r=0.;max_delta=0.
        for index,(p,r) in enumerate(references):
            if self.tracking_compensator is not None:
                corrected=self.tracking_compensator.hold(nominal_position_m=p,nominal_rotation_matrix=r.as_matrix())
                solution=self.local_solution(corrected.command_position_m,Rotation.from_matrix(corrected.command_rotation_matrix),seed)
            else:solution=self.local_solution(p,r,seed)
            if not solution['success']:
                detail={k:v for k,v in solution.items() if k!='q'}
                return dict(success=False,q7=[],summary=dict(planned_ticks=len(commands),requested_ticks=len(references),wall_seconds=time.perf_counter()-start),
                    failure=dict(reference_tick=index,reason=solution['reason'],IK=detail,robot_state_only=True))
            q=np.asarray(solution['q']);max_delta=max(max_delta,float(np.max(abs(q-seed))));commands.append(q.copy());seed=q
            worst_p=max(worst_p,solution['position_error_m']);worst_r=max(worst_r,solution['orientation_error_rad'])
        return dict(success=True,q7=commands,summary=dict(planned_ticks=len(commands),requested_ticks=len(references),
            maximum_FK_position_error_m=worst_p,maximum_FK_orientation_error_rad=worst_r,maximum_joint_step_rad=max_delta,
            wall_seconds=time.perf_counter()-start,scope='Continuous kinematics only; not collision or dynamics certification',
            FK_goal_scope='nominal + frozen current robot tracking estimate' if self.tracking_compensator is not None else 'nominal',
            runtime_feedback_revalidation=True))

    def _convert_action(self,action):
        if action.get('episode_id')!=self.episode_id or action.get('observation_step')!=self.control_steps:raise ValueError('Stale low-level action')
        duration=float(action.get('duration_s',1/self.cfg.physics.control_hz))
        if abs(duration-1/self.cfg.physics.control_hz)>1e-6:raise ValueError('Use the facade for bounded multi-tick actions')
        kind=action.get('type');v=np.asarray(action.get('values',[]),float)
        if not np.isfinite(v).all():raise ValueError('Nonfinite command')
        opening=float(action.get('gripper_opening_m',self.grip));effort=float(action.get('gripper_effort_limit_N',self.effort))
        if not np.isfinite([opening,effort]).all() or not 0<=opening<=.08 or not 0<=effort<=8:raise ValueError('Invalid gripper command')
        seed=self.qcmd[:7].copy();reference=None;solution=None;tracking_diagnostics=None;effective_reference=None
        if kind in ('ee_pose','ee_delta'):
            if kind=='ee_pose':
                if v.shape!=(7,) or abs(np.linalg.norm(v[3:])-1)>1e-3:raise ValueError('Expected xyz+wxyz')
                p=v[:3];r=Rotation.from_quat(np.roll(v[3:],-1))
            else:
                if v.shape!=(6,):raise ValueError('Expected spatial delta6')
                p=np.asarray(self.debug['actual_tcp_position_m']);r=Rotation.from_quat(np.roll(self.debug['actual_tcp_quaternion_wxyz'],-1))
                if action.get('frame','world')=='world':p=p+v[:3];r=Rotation.from_rotvec(v[3:])*r
                elif action.get('frame')=='tcp':p=p+r.apply(v[:3]);r=r*Rotation.from_rotvec(v[3:])
                else:raise ValueError('Unknown frame')
            reference=dict(position_m=p.tolist(),quaternion_wxyz=np.roll(r.as_quat(),1).tolist())
            if self.tracking_compensator is not None:
                if self._tracking_sample_control_step!=self.control_steps:
                    command_p,command_R=self.forward(seed)
                    corrected=self.tracking_compensator.update(nominal_position_m=p,nominal_rotation_matrix=r.as_matrix(),
                        previous_command_position_m=command_p,previous_command_rotation_matrix=command_R,
                        actual_position_m=self.debug['actual_tcp_position_m'],
                        actual_rotation_matrix=Rotation.from_quat(np.roll(self.debug['actual_tcp_quaternion_wxyz'],-1)).as_matrix(),
                        dt_s=1/self.cfg.physics.control_hz)
                    self._tracking_sample_control_step=self.control_steps
                else:corrected=self.tracking_compensator.hold(nominal_position_m=p,nominal_rotation_matrix=r.as_matrix())
                p=corrected.command_position_m;r=Rotation.from_matrix(corrected.command_rotation_matrix)
                tracking_diagnostics=corrected.diagnostics
                effective_reference=dict(position_m=p.tolist(),quaternion_wxyz=np.roll(r.as_quat(),1).tolist())
            if '_executor_q7' in action and self.tracking_compensator is None:
                q7=np.asarray(action['_executor_q7'],float)
                fp,fR=self.forward(q7);pe=float(np.linalg.norm(fp-p));oe=float((r*Rotation.from_matrix(fR).inv()).magnitude())
                solution=dict(success=pe<=self.cfg.executor.ik_position_tolerance_m and oe<=self.cfg.executor.ik_orientation_tolerance_rad,
                    q=q7,position_error_m=pe,orientation_error_rad=oe,reason='PREFLIGHT_REVERIFIED')
            else:solution=self.local_solution(p,r,seed);q7=np.asarray(solution['q'],float)
            if not solution['success']:raise RuntimeError('CONTROL_OR_IK_FAILURE:'+solution['reason'])
        elif kind in ('joint_position','joint_velocity'):
            if v.shape not in ((7,),(9,)):raise ValueError('Expected joint vector7/9')
            if kind=='joint_velocity' and v.shape!=(7,):raise ValueError('Joint velocity requires7 arm values')
            if v.shape==(9,):
                if np.any(v[7:]<0) or np.any(v[7:]>.04) or abs(v[7]-v[8])>1e-7:raise ValueError('Joint9 fingers must be legal symmetric positions')
                if 'gripper_opening_m' in action and abs(sum(v[7:])-opening)>1e-7:raise ValueError('Joint9 opening contradicts explicit total opening')
                opening=float(sum(v[7:]))
            q7=v[:7] if kind=='joint_position' else self.robot.get_joint_positions()[:7]+v[:7]/self.cfg.physics.control_hz
        else:raise ValueError('Unknown low-level action')
        lo,hi,speed=self.joint_bounds()
        if q7.shape!=(7,) or not np.isfinite(q7).all() or np.any(q7<lo) or np.any(q7>hi) or np.any(abs(q7-seed)>speed/self.cfg.physics.control_hz+1e-9):raise RuntimeError('JOINT_CONTINUITY_OR_LIMIT_FAILURE')
        logical=float(action.get('raw_model_action',{}).get('gripper_opening_m',opening))
        opening,grip_diagnostics=self.contact_hold.update(t=self.t,logical_requested_opening_m=logical,
            ramped_opening_m=opening,previous_applied_opening_m=self.grip,
            measured_finger_positions_m=self.debug['finger_joint_positions_m'],finger_contact_N=self.debug['finger_contact_N'])
        # Prevent the inherited instantaneous latch from recomputing a wider
        # target from the contact-deformed measured opening. It may still clear
        # this compatibility latch during an explicit release; the generic
        # sensor-only helper above owns its independent continuous-contact state.
        self._policy_latch=opening
        q=np.r_[q7,[opening/2]*2]
        # Seed is always an executed command; no raw unexecuted branch is retained.
        self._ik_seed=q7.copy();self._ik_goal=None;self._ik_solution=None
        conversion=dict(input_type=kind,control_hz=int(self.cfg.physics.control_hz),physics_hz=int(self.cfg.physics.hz),duration_s=duration,ticks=1,
            target_pose=reference,raw_values=v.tolist(),executed_q=q.tolist(),effort_limit_N=effort,truth_used_by_environment=False,
            IK=None if solution is None else {k:copy.deepcopy(v) for k,v in solution.items() if k!='q'},
            generic_contact_hold=grip_diagnostics,
            robot_tracking=tracking_diagnostics,effective_IK_goal_TCP=effective_reference,
            FK_validation_scope='effective IK goal; actual tracking guard compares the unchanged nominal reference',
            no_post_IK_joint_clipping=True,seed_semantics='previous applied command',gripper_semantics='persistent applied symmetric opening target; explicit changes only')
        self._tick_trace=dict(t_before=self.t,control_tick_before=self.control_steps,action=copy.deepcopy(action),seed_q7=seed.tolist(),command_q9=q.tolist(),reference_TCP=reference,IK=conversion['IK'],generic_contact_hold=grip_diagnostics,robot_tracking=tracking_diagnostics,effective_IK_goal_TCP=effective_reference)
        return q,opening,effort,1,conversion

    def hold_actual_joints(self):
        from isaacsim.core.utils.types import ArticulationAction
        self.qcmd=self.robot.get_joint_positions().copy();self.qcmd[7:]=self.grip/2
        self.ac.apply_action(ArticulationAction(joint_positions=self.qcmd))
        self._ik_seed=self.qcmd[:7].copy()

    def step(self,action):
        before_q=self.robot.get_joint_positions().copy();before_p=np.asarray(self.debug['actual_tcp_position_m']);before_t=self.t
        self._tick_trace=None
        try:
            result=super().step(action)
            trace=self._tick_trace
            if trace and trace['reference_TCP']:
                actual_p=np.asarray(self.debug['actual_tcp_position_m']);actual_r=Rotation.from_quat(np.roll(self.debug['actual_tcp_quaternion_wxyz'],-1))
                target=trace['reference_TCP'];pe=float(np.linalg.norm(actual_p-target['position_m']));oe=float((Rotation.from_quat(np.roll(target['quaternion_wxyz'],-1))*actual_r.inv()).magnitude())
                dt=self.t-before_t;actual_q=self.robot.get_joint_positions().copy();speed=float(np.linalg.norm(actual_p-before_p)/dt)
                fdq=abs(actual_q[:7]-before_q[:7])/dt;lo,hi,jv=self.joint_bounds();stop=None
                if not np.isfinite(np.r_[actual_q,actual_p,fdq]).all():stop='NONFINITE_ACTUAL_STATE'
                elif pe>self.cfg.executor.maximum_position_tracking_error_m or oe>np.deg2rad(self.cfg.executor.maximum_orientation_tracking_error_deg):stop='EXECUTOR_TRACKING_ERROR'
                elif speed>self.cfg.executor.maximum_actual_TCP_speed_m_s:stop='EXECUTOR_ACTUAL_SPEED_LIMIT'
                elif np.any(fdq>jv*self.cfg.executor.maximum_actual_joint_speed_factor):stop='EXECUTOR_ACTUAL_JOINT_SPEED_LIMIT'
                elif np.any(actual_q[:7]<lo-.001) or np.any(actual_q[:7]>hi+.001):stop='EXECUTOR_ACTUAL_JOINT_LIMIT'
                trace.update(t_after=self.t,actual_TCP=dict(position_m=actual_p.tolist(),quaternion_wxyz=self.debug['actual_tcp_quaternion_wxyz']),
                    actual_q9=actual_q.tolist(),actual_joint_velocities=self.robot.get_joint_velocities().tolist(),FD_joint_speed_rad_s=fdq.tolist(),
                    position_tracking_error_m=pe,orientation_tracking_error_rad=oe,actual_TCP_speed_m_s=speed,
                    gripper_applied_target_m=float(self.grip),gripper_actual_opening_m=float(sum(self.debug['finger_joint_positions_m'])),effort_limit_N=float(self.effort),finger_contact_N=self.debug['finger_contact_N'],
                    forbidden_robot_environment_contact=self.debug.get('forbidden_robot_environment_contact'),runtime_stop=stop)
                # Separate joint tracking from the kinematic/native TCP frame
                # agreement. This uses only robot state, never object truth.
                fk_actual_p,fk_actual_R=self.forward(actual_q[:7])
                trace['actual_joint_FK_TCP']=dict(position_m=fk_actual_p.tolist(),quaternion_wxyz=np.roll(Rotation.from_matrix(fk_actual_R).as_quat(),1).tolist())
                trace['FK_vs_native_TCP_position_error_m']=float(np.linalg.norm(fk_actual_p-actual_p))
                if stop and not self.ended:
                    self.hold_actual_joints();self.finalize_episode(stop,'SIMULATION_FAILURE' if stop=='NONFINITE_ACTUAL_STATE' else 'EXECUTOR_FAILURE')
                    result=(self.get_observation(),0.,True,False,self._public_info())
            return result
        finally:
            if self._tick_trace is not None:
                from data_collectors.lab_cuvette_env_v1_collector import json_safe
                with (self.episode_dir/'execution_trace.jsonl').open('a') as f:f.write(json.dumps(json_safe(self._tick_trace),allow_nan=False)+'\n')
