"""Oracle expert recomputes source/target from each sampled scene; no seed branches."""
import numpy as np
from isaacsim.core.utils.types import ArticulationAction
from isaacsim.core.utils.rotations import euler_angles_to_quat

class LabCuvetteLoadingController:
 def __init__(self,cfg,robot,task):
  self.cfg,self.robot,self.task=cfg,robot,task;self.previous_target=np.array(cfg.robot.initial_tcp_m);self.anchor=self.previous_target.copy();self.last_phase='';self.yaw_anchor=0.;self.last_yaw=0.;self.align_offset=None
 def step(self,state):
  t=state['simulation_time'];cfg=self.cfg;task=self.task
  total=0.
  for phase,duration in cfg.control.phases_s.items():
   if t<total+duration:break
   total+=duration
  local=t-total;f=float(np.clip(local/duration,0,1));smooth=f*f*(3-2*f)
  if self.last_phase!=phase:
   self.anchor=self.previous_target.copy();self.yaw_anchor=self.last_yaw;self.last_phase=phase
   if phase=='ALIGN':self.align_offset=np.array(state['object_position'])-np.array(state['tcp'])
   task.events.append(dict(event='PHASE_CHANGE',phase=phase,time=t))
  source=task.scene['source'];target=task.scene['target'];grasp_z=source[2]+cfg.cuvette.grasp_above_bottom_m
  source_yaw=task.layout['rack_yaw_deg'];target_yaw=task.layout['instrument_yaw_deg']
  grip=0.;end_yaw=source_yaw
  if phase=='APPROACH_SOURCE':end=np.r_[source[:2],grasp_z];grip=.04
  elif phase=='GRASP':end=self.anchor;grip=.04*(1-smooth)
  elif phase=='EXTRACT':end=np.r_[source[:2],grasp_z+cfg.control.extract_clearance_m]
  elif phase=='TRANSPORT':end=np.r_[target[:2],cfg.control.transport_tcp_z_m];end_yaw=target_yaw
  elif phase=='ALIGN':
   # Privileged actual held-object offset, measured in this scene. Correct object
   # center (not robot-only TCP) before insertion; target geometry stays fixed.
   end=np.r_[target[:2],target[2]+cfg.holder.depth_m+cfg.control.insert_start_gap_m+cfg.cuvette.size_m[2]/2]-self.align_offset;end_yaw=target_yaw
  elif phase in ['INSERT','RELEASE']:
   offset=self.align_offset
   end=np.r_[target[:2],target[2]+cfg.control.released_bottom_gap_m+cfg.cuvette.size_m[2]/2]-offset;end_yaw=target_yaw
   if phase=='RELEASE':grip=.04*smooth
  else:
   end=self.anchor.copy()
   if phase=='RETREAT':end[2]+=cfg.control.retreat_m
   grip=.04;end_yaw=target_yaw
  target_tcp=self.anchor+smooth*(end-self.anchor) if phase not in ['GRASP','RELEASE','VERIFY'] else end
  yaw=self.yaw_anchor+smooth*(end_yaw-self.yaw_anchor)
  orientation=euler_angles_to_quat(np.array([np.pi,0.,np.radians(yaw)]))
  ik,valid=task.solver.compute_inverse_kinematics(target_tcp,orientation,position_tolerance=cfg.robot.ik_position_tolerance_m,orientation_tolerance=cfg.robot.ik_orientation_tolerance_rad)
  if not valid:task.status,task.reason='CONTROL_FAILURE','IK_unreachable_'+phase;return None
  q=state['joint_positions'].copy();q[np.asarray(ik.joint_indices,dtype=int)]=ik.joint_positions;q[7:]=grip
  # Bound commanded step as well as actual PhysX joint velocity.
  previous=task.last_action if task.last_action is not None else state['joint_positions']
  delta=np.array(cfg.robot.max_velocity)/cfg.physics.control_hz
  q=np.clip(q,previous-delta,previous+delta)
  self.previous_target=target_tcp;self.last_yaw=yaw;task.phase=phase;task.target_tcp=target_tcp;task.last_action=q.copy()
  return ArticulationAction(joint_positions=q)
