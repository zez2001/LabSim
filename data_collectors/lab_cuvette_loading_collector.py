"""Existing stream writer; learning fields separate from privileged task truth."""
import cv2
import numpy as np
from data_collectors.minimal_pick_collector import MinimalPickCollector

class LabCuvetteLoadingCollector(MinimalPickCollector):
 def begin_episode(self,index,initial_position):
  super().begin_episode(index,initial_position)
  self.file.attrs.update(schema_version='labsim.lab_cuvette_loading.V0',task='lab_cuvette_loading',physics_hz=self.cfg.physics.hz,control_hz=self.cfg.physics.control_hz,action_semantics='absolute_7_arm_rad_and_symmetric_finger_metre',observation_alignment='obs_before_action; next_state_after_explicit_substeps',rgb=f'CHW RGB uint8 256x256 {self.cfg.physics.control_hz}Hz',robot_state_dimension=9,action_dimension=8,privileged_fields='privileged/* not default policy inputs')
 def cache_transition(self,state,action,next_state,result):
  for key,rgb in state['camera_data'].items():self._append(key,rgb)
  m=next_state['metrics']
  fields=dict(agent_pose=state['joint_positions'][:8].astype(np.float32),actions=action.joint_positions[:8].astype(np.float32),next_agent_pose=next_state['joint_positions'][:8].astype(np.float32),joint_positions=state['joint_positions'].astype(np.float32),timestamp=np.float64(state['simulation_time']),next_timestamp=np.float64(next_state['simulation_time']),done=np.bool_(result['status']!='RUNNING'),reward=np.float32(result['full_success']))
  for k,v in fields.items():self._append(k,v)
  truth=dict(object_pose=np.r_[state['object_position'],state['object_orientation']],next_object_pose=np.r_[next_state['object_position'],next_state['object_orientation']],actual_tcp=state['tcp'],next_actual_tcp=next_state['tcp'],target_tcp=state.get('target_tcp',state['tcp']),depth_m=m['depth_m'],xy_error_m=m['xy_error_m'],tilt_rad=m['tilt_rad'],yaw_error_rad=m['yaw_error_rad'],overlap_m=m['overlap_m'],finger_contact_N=m['finger_contact_N'],environment_contact_N=m['environment_contact_N'],progress=np.array(list(result['stage_progress'].values()),dtype=bool))
  for k,v in truth.items():self._append('privileged/'+k,np.asarray(v))
  self._append('phase_code',np.int32(list(self.cfg.control.phases_s).index(state['phase']) if state['phase'] in self.cfg.control.phases_s else -1))
  if self.save_video:
   depth_label=f"{m['depth_m']*1000:.2f}mm" if np.linalg.norm(m['xy_error_m'])<.015 else 'outside target'
   # Both frame and annotation use post-action state to avoid the prior demo's
   # pre-image/post-result label discrepancy. H5 learning observation remains pre.
   rgb=np.concatenate([np.transpose(x,(1,2,0)) for x in next_state['camera_data'].values()],axis=1);frame=cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR)
   if self.writer is None:
    self.writer=cv2.VideoWriter(str(self.video_dir/(self.name+'.mp4')),cv2.VideoWriter_fourcc(*'mp4v'),self.cfg.physics.control_hz,(frame.shape[1],frame.shape[0]))
    if not self.writer.isOpened():raise RuntimeError('video writer failed')
   for text,pt in [(f"t={next_state['simulation_time']:.2f} {state['phase']} {result['status']}",(4,15)),(f"depth={depth_label} overlap={m['overlap_m']*1000:.3f}mm seed={result['seed']}",(4,30))]:
    cv2.putText(frame,text,pt,cv2.FONT_HERSHEY_SIMPLEX,.34,(0,0,0),3);cv2.putText(frame,text,pt,cv2.FONT_HERSHEY_SIMPLEX,.34,(255,255,255),1)
   self.writer.write(frame)
  self.count+=1
