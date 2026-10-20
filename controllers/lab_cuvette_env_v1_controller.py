"""Truth-declared teacher issuing bounded robot actions, never moving the vessel.

The environment owns stepping and the independent scorer owns task outcomes.
This controller reports completion/stop suggestions, not successful labels.
"""
from __future__ import annotations
from collections import deque
import numpy as np
from scipy.spatial.transform import Rotation


def get(config, path, default=None):
    value = config
    for key in path.split('.'):
        try:
            value = value[key]
        except (KeyError,TypeError):
            return default
    return value


def rotation(quaternion_wxyz):
    q=np.asarray(quaternion_wxyz,float)
    return Rotation.from_quat(np.r_[q[1:],q[0]])


def wxyz(r):
    q=r.as_quat()
    return np.r_[q[3],q[:3]]


def smooth(a,b,fraction):
    u=np.clip(float(fraction),0.,1.)
    return np.asarray(a)+(np.asarray(b)-a)*(u*u*(3.-2.*u))


class LabCuvetteTeacher:
    def __init__(self,cfg,layout):
        self.cfg,self.layout=cfg,layout
        self.hz=float(get(cfg,'physics.control_hz',60))
        self.task_type=str(get(cfg,'env.task_type','loading'))
        if self.task_type not in ('loading','preinsert_diagnostic','grasp_hold','extract_transport'):
            raise ValueError('Unsupported teacher task_type: '+self.task_type)
        self.source=np.asarray(layout['source_floor'],float)
        self.floor=np.asarray(layout['target_floor'],float)
        self.instrument_rotation=np.asarray(layout['instrument_rotation'],float)
        self.rim=float(layout['target_rim_z'])
        self.desired_cup_rotation=Rotation.from_euler('z',float(get(cfg,'control.target_vessel_yaw_deg',get(cfg,'vessel.yaw_deg',90))),degrees=True)
        self.reset()

    def reset(self,public_obs=None,debug=None):
        self.phase='RESET';self.status='RUNNING';self.finished=False
        self.events=[];self.history=deque(maxlen=max(1000,int(self.hz*8)))
        self.target=None;self.rotation_command=None;self.phase_start=None
        self.contact_start=None;self.latch_time=None;self.latch_opening=None
        self._closure_freeze_opening=None;self._first_bilateral_seen=False
        self.contact_opening=None;self.grasp_reference=None
        self.anchor=None;self.lift=None;self.transport_start=None;self.transport_end=None
        self.contact_target=None;self.open_target=None;self.clear_start=None
        self.ready_start=None;self.last_grip_opening=.08;self.total_feedback_m=np.zeros(2)
        self._last_time=None;self._episode_id=None;self._loss_start=None;self._bottom_wait_start=None
        return self

    def _time(self,obs,debug):
        for obj in (obs,debug):
            for key in ('simulation_time','simulation_time_s','sim_time_s','timestamp','t'):
                if key in obj:return float(obj[key])
        raise KeyError('Teacher needs the observation simulation timestamp')

    def _enter(self,phase,t,**data):
        self.events.append(dict(t=t,event='teacher_phase_transition',source=self.phase,target=phase,**data))
        self.phase,self.phase_start=phase,t
        self.ready_start=None;self.clear_start=None

    def _finish(self,status,t):
        self.status,self.finished=status,True
        self.events.append(dict(t=t,event='teacher_stop_suggestion',status=status,phase=self.phase,
                                independent_task_result_not_assigned=True))

    def _relative(self,debug):
        tcp=np.asarray(debug['actual_tcp_position_m'],float)
        hand=rotation(debug['actual_tcp_quaternion_wxyz'])
        cup=np.asarray(debug['object_position_m'],float)
        cup_rotation=rotation(debug['object_quaternion_wxyz'])
        return hand.inv().apply(cup-tcp),hand.inv()*cup_rotation

    def _feedback(self,debug,desired_cup_xy=None,*,orientation=True):
        # Actual relative rotation includes passive slip; correcting only XY
        # would leave a tilted vessel approaching the narrow original seat.
        if orientation:
            _,relative_rotation=self._relative(debug)
            desired_hand=self.desired_cup_rotation*relative_rotation.inv()
            delta=(desired_hand*self.rotation_command.inv()).as_rotvec()
            cap=np.deg2rad(float(get(self.cfg,'control.orientation_step_limit_deg',.1)))
            norm=np.linalg.norm(delta)
            if norm>cap:delta*=cap/norm
            self.rotation_command=Rotation.from_rotvec(delta)*self.rotation_command
        if desired_cup_xy is not None:
            error=np.asarray(debug['object_position_m'],float)[:2]-np.asarray(desired_cup_xy,float)
            correction=-float(get(self.cfg,'control.truth_xy_gain',.15))*error
            cap=float(get(self.cfg,'control.truth_xy_step_limit_m',.00002))
            norm=np.linalg.norm(correction)
            if norm>cap:correction*=cap/norm
            self.target[:2]+=correction
            self.total_feedback_m+=correction

    def _quiet(self,t,seconds):
        window=[x for x in self.history if x['t']>=t-seconds-1e-8]
        if not window or window[-1]['t']-window[0]['t']<seconds-1.1/self.hz:return False
        p=np.array([x['position'] for x in window]);q=[x['quaternion'] for x in window]
        drift=np.max(np.linalg.norm(p-p[0],axis=1))
        turns=[(rotation(v)*rotation(q[0]).inv()).magnitude() for v in q]
        return bool(drift<=float(get(self.cfg,'demo_release.position_drift_m',.0002))
                    and max(turns)<=np.deg2rad(float(get(self.cfg,'demo_release.orientation_change_deg',1.))))

    def _supported(self,debug):
        force=debug.get('target_bottom_support_N');gap=debug.get('target_bottom_gap_m')
        if force is None or gap is None:return False
        overlap=debug.get('native_target_overlap_m')
        return bool(np.isfinite([force,gap]).all() and force>=float(get(self.cfg,'demo_release.min_support_N',.1))
            and abs(gap)<=float(get(self.cfg,'demo_release.bottom_distance_m',.00005))
            and float(debug['tilt_deg'])<=float(get(self.cfg,'demo_release.max_tilt_deg',1.))
            and (overlap is None or overlap<=float(get(self.cfg,'demo_release.penetration_m',.00005))))

    def _latch(self,debug,t):
        fingers=np.asarray(debug['finger_joint_positions_m'],float)
        mass=float(get(self.cfg,'vessel.mass_kg',.02))
        mu=np.sqrt(float(get(self.cfg,'physics.dynamic_friction',.5))*float(get(self.cfg,'physics.finger_dynamic_friction',.8)))
        kp=float(get(self.cfg,'robot.finger_kp',2000.))
        compression=mass*9.81/(2*max(mu,1e-6))*float(get(self.cfg,'gripper.contact_safety_factor',2.))/kp
        compression=float(np.clip(compression,0.,float(get(self.cfg,'gripper.maximum_compression_m',.0003))))
        half=max(float(np.mean(fingers))-compression,float(get(self.cfg,'gripper.minimum_latched_finger_m',.001)))
        candidate_opening=2*half
        policy=str(get(self.cfg,'gripper.latch_transition_policy','measured_weight_based'))
        if policy=='preserve_first_contact_command' and self._closure_freeze_opening is not None:
            # The persistence window already held this command. Recomputing
            # from later finger positions can reopen the gripper at latch.
            # Keep that existing target; do not add further closure or effort.
            self.latch_opening=float(self._closure_freeze_opening)
        elif policy=='measured_weight_based':self.latch_opening=candidate_opening
        else:raise ValueError('Unknown/unavailable gripper latch transition policy: '+policy)
        self.contact_opening=float(np.sum(fingers));self.latch_time=t
        p,q=self._relative(debug);self.grasp_reference=(p.copy(),q)
        self.events.append(dict(t=t,event='contact_latched',measured_finger_m=fingers.tolist(),
            commanded_total_opening_m=self.latch_opening,per_finger_compression_m=compression,
            latch_transition_policy=policy,weight_based_candidate_opening_m=candidate_opening,
            effective_measured_minus_command_per_finger_m=(fingers-self.latch_opening/2).tolist(),
            compression_semantics='Joint target difference, not measured material penetration; first-contact command may predate measured finger response',
            effort_limit_N=8.,friction_assumption=mu,mass_kg=mass,finger_kp_N_per_m=kp,
            truth_pose_used=True))

    def _jam(self,t,debug):
        window_s=float(get(self.cfg,'control.jam_detection.window_s',.3))
        window=[x for x in self.history if x['t']>=t-window_s-1e-8]
        if len(window)<2 or window[-1]['t']-window[0]['t']<window_s-1.1/self.hz:return None
        first,last=window[0],window[-1]
        down=first['target_z']-last['target_z'];actual=first['bottom']-last['bottom']
        if down>=float(get(self.cfg,'control.jam_detection.command_down_min_m',.00015)) and actual<=float(get(self.cfg,'control.jam_detection.vessel_down_max_m',.000025)):
            return 'COMMANDED_DESCENT_WITHOUT_VESSEL_DESCENT'
        force=[x['wall_force'] for x in window if x['wall_force'] is not None]
        if len(force)==len(window) and min(force)>.5 and force[-1]-force[0]>.2:
            return 'SUSTAINED_RISING_WALL_FORCE_BEFORE_BOTTOM'
        return None

    def act(self,public_obs,debug):
        debug=dict(debug)
        if 'object_quaternion_wxyz' not in debug and 'quaternion_wxyz' in debug:
            debug['object_quaternion_wxyz']=debug['quaternion_wxyz']
        t=self._time(public_obs,debug)
        episode_id=public_obs.get('episode_id',debug.get('episode_id'))
        if self._episode_id is None:self._episode_id=episode_id
        if episode_id!=self._episode_id:raise ValueError('Reset teacher before changing episode')
        if self._last_time is not None and t<self._last_time-1e-9:raise ValueError('Teacher time moved backwards; reset required')
        self._last_time=t
        if self.target is None:
            self.target=np.asarray(debug['actual_tcp_position_m'],float).copy()
            self.initial_tcp=self.target.copy()
            self.rotation_command=rotation(debug['actual_tcp_quaternion_wxyz'])
            self.phase_start=t
        u=t-self.phase_start
        position=np.asarray(debug['object_position_m'],float)
        forces=np.asarray(debug['finger_contact_N'],float)
        bottom=float(debug['source_bottom_z_m'])
        self.history.append(dict(t=t,position=position.copy(),quaternion=np.asarray(debug['object_quaternion_wxyz']).copy(),
            bottom=bottom,target_z=self.target[2],wall_force=debug.get('wall_contact_N')))
        opening=self.latch_opening if self.latch_opening is not None else .08
        effort=8.
        if not self.finished and self.latch_opening is not None and self.phase in ('EXTRACT','TRANSPORT','TRANSPORT_HOLD','ALIGN','INSERT','GATE_RETRACT','DIAGNOSTIC_HOLD'):
            relative,_=self._relative(debug)
            slip=float(np.linalg.norm(relative-self.grasp_reference[0]))
            if slip>float(get(self.cfg,'control.max_grasp_relative_drift_m',.0015)):
                self._finish('GRASP_SLIP',t)
            if np.all(forces<.005):
                if self._loss_start is None:self._loss_start=t
                if t-self._loss_start>.3:self._finish('BILATERAL_CONTACT_LOST',t)
            else:self._loss_start=None
        if not self.finished:
            if self.phase=='RESET':
                opening=.08
                if u>=4.:
                    if not self._quiet(t,3.) or float(debug['tilt_deg'])>1. or abs(bottom-self.source[2])>.00005:
                        self._finish('INITIAL_SUPPORT_INVALID',t)
                    else:
                        self.source_initial=position.copy();self.anchor=position+[0,0,float(get(self.cfg,'robot.grasp_above_bottom_m',.053))]
                        self.lift=self.anchor+[0,0,float(get(self.cfg,'control.transport_bottom_z_m',.975))-bottom]
                        self._enter('APPROACH_SOURCE',t)
            elif self.phase=='APPROACH_SOURCE':
                duration=float(get(self.cfg,'control.approach_s',6.));opening=.08
                self.target=smooth(self.initial_tcp,self.anchor,u/duration)
                if u>=duration+1.:
                    if np.linalg.norm(np.asarray(debug['actual_tcp_position_m'])-self.anchor)>.002:self._finish('CONTROL_OR_IK_FAILURE',t)
                    else:self._enter('GRASP',t)
            elif self.phase=='GRASP':
                self.target=self.anchor.copy()
                if self.latch_opening is None:
                    bilateral=bool(np.all(forces>float(get(self.cfg,'gripper.contact_threshold_N',.02))))
                    if bilateral:
                        if self.contact_start is None:
                            self.contact_start=t
                            self._first_bilateral_seen=True
                            mass=float(get(self.cfg,'vessel.mass_kg',.02));mu=np.sqrt(float(get(self.cfg,'physics.dynamic_friction',.5))*float(get(self.cfg,'physics.finger_dynamic_friction',.8)))
                            compression=min(float(get(self.cfg,'gripper.maximum_compression_m',.0003)),mass*9.81*float(get(self.cfg,'gripper.contact_safety_factor',2.))/(2*mu*float(get(self.cfg,'robot.finger_kp',2000.))))
                            self._closure_freeze_opening=max(.002,min(self.last_grip_opening,float(np.sum(debug['finger_joint_positions_m']))-2*compression))
                            self.events.append(dict(t=t,event='first_bilateral_contact_stop_closure',
                                actual_finger_positions_m=list(debug['finger_joint_positions_m']),
                                previous_total_opening_command_m=self.last_grip_opening,
                                frozen_total_opening_m=self._closure_freeze_opening,per_finger_compression_m=compression,normal_load_basis='mg/(2*mu)*safety/finger_kp; no wider than previous command'))
                        # Freeze on the very first bilateral sample, before the
                        # persistence timer. Continuing the original time ramp
                        # during this window would add millimetres of compression.
                        opening=self._closure_freeze_opening
                        if t-self.contact_start>=float(get(self.cfg,'gripper.contact_persist_s',.1)):
                            self._latch(debug,t);opening=self.latch_opening
                    else:
                        if self.contact_start is not None:
                            self.events.append(dict(t=t,event='bilateral_contact_lost_resume_bounded_closure',
                                resume_from_total_opening_m=self.last_grip_opening))
                        self.contact_start=None;self._closure_freeze_opening=None
                        speed=float(get(self.cfg,'gripper.contact_approach_speed_m_s',.002) if self._first_bilateral_seen
                                    else get(self.cfg,'gripper.close_speed_m_s',.02))
                        opening=max(.002,self.last_grip_opening-speed/self.hz)
                    if u>float(get(self.cfg,'gripper.grasp_timeout_s',8.)) and self.latch_opening is None:self._finish('GRASP_FAILED',t)
                else:
                    opening=self.latch_opening
                    self._feedback(debug)
                    if self.task_type=='grasp_hold':
                        if t-self.latch_time>=3.:self._finish('GRASP_HOLD_COMPLETE',t)
                    elif t-self.latch_time>=.75:self._enter('EXTRACT',t)
            elif self.phase=='EXTRACT':
                duration=float(get(self.cfg,'control.extract_s',6.))
                self.target=smooth(self.anchor,self.lift,u/duration)
                self._feedback(debug,self.source_initial[:2],orientation=bool(get(self.cfg,'control.extract_orientation_feedback',True)))
                if u>=duration+1.:
                    if bottom<=float(self.layout['source_rim_z'])+.01 or not np.all(forces>.02):self._finish('EXTRACTION_FAILED',t)
                    else:
                        self.transport_start=self.target.copy();rel,_=self._relative(debug)
                        tcp_offset=self.rotation_command.apply(rel)
                        self.transport_end=np.r_[self.floor[:2]-tcp_offset[:2],self.lift[2]]
                        self._enter('TRANSPORT',t)
            elif self.phase=='TRANSPORT':
                duration=float(get(self.cfg,'control.transport_s',16.));waypoint=self.transport_start.copy();waypoint[1]=self.transport_end[1]
                if u<duration:
                    self.target=smooth(self.transport_start,waypoint,u/(duration/2)) if u<duration/2 else smooth(waypoint,self.transport_end,(u-duration/2)/(duration/2))
                self._feedback(debug,self.floor[:2] if u>=duration else None)
                if u>=duration+1.:
                    if np.linalg.norm(position[:2]-self.floor[:2])>.003:self._finish('HELD_POSE_DEVIATION_AFTER_TRANSPORT',t)
                    elif self.task_type=='extract_transport' or float(get(self.cfg,'control.transport_hold_before_align_s',0.))>0:
                        self._enter('TRANSPORT_HOLD',t)
                    else:self._enter('ALIGN',t)
            elif self.phase=='TRANSPORT_HOLD':
                # Holding is a fixed robot target, not continued XY centering.
                # Wait for the declared stationary window; never relax the
                # independent scorer's position/orientation criteria.
                seconds=float(get(self.cfg,'control.transport_hold_before_align_s',3.))
                if seconds<=0:seconds=3.
                if u>=seconds and self._quiet(t,seconds):
                    if self.task_type=='extract_transport':self._finish('EXTRACT_TRANSPORT_COMPLETE',t)
                    else:self._enter('ALIGN',t)
                elif u>float(get(self.cfg,'control.transport_hold_timeout_s',10.)):
                    self._finish('HELD_TRANSPORT_NOT_STABLE',t)
            elif self.phase=='ALIGN':
                self._feedback(debug,self.floor[:2])
                diagnostic=self.task_type=='preinsert_diagnostic'
                xy_budget=float(get(self.cfg,'control.diagnostic_alignment_budget_m',.0001) if diagnostic else get(self.cfg,'control.alignment_budget_m',.000015))
                tilt_budget=float(get(self.cfg,'control.diagnostic_tilt_budget_deg',.5) if diagnostic else get(self.cfg,'control.tilt_budget_deg',.02))
                aligned=np.max(np.abs(np.asarray(debug['xy_error_target_m'])))<=xy_budget and float(debug['tilt_deg'])<=tilt_budget
                if u>=2.5 and aligned:
                    if diagnostic:
                        stop=self.rim+float(get(self.cfg,'control.diagnostic_safe_bottom_above_rim_m',.001))
                        if bottom<=stop+.00002:
                            self.contact_target=self.target.copy();self._enter('GATE_RETRACT',t)
                        else:
                            speed=float(get(self.cfg,'control.diagnostic_near_speed_m_s',.0005) if bottom-stop<.003 else get(self.cfg,'control.diagnostic_approach_speed_m_s',.002))
                            self.target[2]-=min(speed/self.hz,max(0.,bottom-stop)*.2)
                    else:self._enter('INSERT',t)
                if u>80.:self._finish('ALIGNMENT_TIMEOUT',t)
            elif self.phase=='GATE_RETRACT':
                self.target=smooth(self.contact_target,self.contact_target+[0,0,.01],u/2.)
                self._feedback(debug,self.floor[:2])
                if u>=2.5:self._enter('DIAGNOSTIC_HOLD',t)
            elif self.phase=='DIAGNOSTIC_HOLD':
                self.target=self.contact_target+[0,0,.01];self._feedback(debug,self.floor[:2])
                if u>=1.:self._finish('PREINSERT_DIAGNOSTIC_COMPLETE',t)
            elif self.phase=='INSERT':
                self._feedback(debug,self.floor[:2]);jam=self._jam(t,debug)
                if jam:
                    self.contact_target=self.target.copy();self.events.append(dict(t=t,event='jam_stop_downward_target',reason=jam));self._enter('JAM_RETRACT',t)
                elif self._supported(debug):
                    self.contact_target=self.target.copy();self._enter('SUPPORT_TRANSFER',t)
                else:
                    gap=debug.get('target_bottom_gap_m')
                    if gap is None:self._finish('BOTTOM_MEASUREMENT_UNAVAILABLE',t)
                    elif gap<=float(get(self.cfg,'demo_release.bottom_distance_m',.00005)):
                        # Geometry reached the base: do not keep driving down
                        # while waiting for a missing/insufficient force signal.
                        if self._bottom_wait_start is None:self._bottom_wait_start=t
                        if t-self._bottom_wait_start>=1.:
                            self._finish('BOTTOM_SUPPORT_MEASUREMENT_UNAVAILABLE' if debug.get('target_bottom_support_N') is None else 'BOTTOM_SUPPORT_NOT_ESTABLISHED',t)
                    else:
                        self._bottom_wait_start=None
                        speed=float(get(self.cfg,'control.final_speed_m_s',.0002) if gap<.001 else get(self.cfg,'control.insert_speed_m_s',.001))
                        self.target[2]-=min(speed/self.hz,max(0.,gap)*.2)

                    if u>35.:self.contact_target=self.target.copy();self._enter('JAM_RETRACT',t)
            elif self.phase=='JAM_RETRACT':
                self.target=smooth(self.contact_target,self.contact_target+[0,0,.01],u/2.)
                if u>=2.5:self._finish('INSERT_BLOCKED',t)
            elif self.phase=='SUPPORT_TRANSFER':
                duration=float(get(self.cfg,'demo_release.unload_seconds',3.));fraction=min(1.,u/duration)
                effort=8.-7.95*fraction
                opening=self.latch_opening+(self.contact_opening-self.latch_opening)*fraction
                force=debug.get('target_bottom_support_N')
                if force is not None and force>.02*9.81+.05:
                    self.target[2]+=min(.00001,max(0.,self.contact_target[2]+.001-self.target[2]),(force-.02*9.81)*.000002)
                if u>=duration and self._supported(debug) and self._quiet(t,float(get(self.cfg,'demo_release.support_window_s',.5))):
                    self.open_target=self.target.copy();self._enter('OPEN',t)
                if u>10.:self._finish('SUPPORT_TRANSFER_FAILED',t)
            elif self.phase=='OPEN':
                self.target=self.open_target.copy();effort=.5
                opening=self.contact_opening+(.08-self.contact_opening)*min(1.,u/float(get(self.cfg,'demo_release.open_seconds',3.)))
                clear=np.all(forces<.01) and np.all(np.asarray(debug['finger_joint_positions_m'])>.025) and self._supported(debug)
                if clear:
                    if self.clear_start is None:self.clear_start=t
                    if t-self.clear_start>=float(get(self.cfg,'demo_release.clear_seconds',.5)):self._enter('RETREAT',t)
                else:self.clear_start=None
                if u>7.:self._finish('RELEASE_FAILED',t)
            elif self.phase=='RETREAT':
                opening=.08;raised=self.open_target+[0,0,float(get(self.cfg,'control.retreat_lift_m',.06))]
                outward=np.asarray(self.layout.get('opening_direction_world',[-1.,0.,0.]),float)*.12
                withdrawn=raised+outward
                self.target=smooth(self.open_target,raised,u/2.) if u<2 else smooth(raised,withdrawn,(u-2)/3.)
                if u>=5.5:self._enter('VERIFY',t)
            elif self.phase=='VERIFY':
                opening=.08
                if u>=float(get(self.cfg,'demo_release.observe_s',3.))+.1:
                    self._finish('CONTROLLER_WORKFLOW_COMPLETE' if self._quiet(t,3.) and self._supported(debug) and np.all(forces<.01) else 'UNSTABLE_AFTER_RELEASE',t)
        if not self.finished and t>float(get(self.cfg,'control.timeout_s',160.)):
            self._finish('TIMEOUT',t)
        self.last_grip_opening=float(opening)
        relative_position,relative_rotation=self._relative(debug)
        relative_position_drift=None if self.grasp_reference is None else float(np.linalg.norm(relative_position-self.grasp_reference[0]))
        relative_rotation_drift=None if self.grasp_reference is None else float(np.rad2deg((relative_rotation*self.grasp_reference[1].inv()).magnitude()))
        return dict(type='ee_pose',values=np.r_[self.target,wxyz(self.rotation_command)].tolist(),
            gripper_opening_m=float(np.clip(opening,.002,.08)),gripper_effort_limit_N=float(effort),
            episode_id=episode_id,observation_step=public_obs.get('step_index',public_obs.get('observation_step')),
            duration_s=1./self.hz,metadata=dict(teacher_phase=self.phase,teacher_status=self.status,
                teacher_finished=self.finished,truth_pose_used=True,gripper_control='contact_latched_bounded' if self.latch_opening is not None else 'closing_until_bilateral_contact',
                latched_total_opening_m=self.latch_opening,closure_frozen_at_first_bilateral_m=self._closure_freeze_opening,relative_position_in_TCP_m=relative_position.tolist(),
                relative_quaternion_in_TCP_wxyz=wxyz(relative_rotation).tolist(),relative_grasp_position_drift_m=relative_position_drift,
                relative_grasp_rotation_drift_deg=relative_rotation_drift,actual_result_owned_by_independent_scorer=True))
