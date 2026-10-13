"""Extend the existing streaming HDF5/MP4 collector; no new data platform."""
import cv2
import numpy as np
from data_collectors.minimal_pick_collector import MinimalPickCollector


class MinimalPrecisionInsertionCollector(MinimalPickCollector):
    def begin_episode(self,index,initial_position):
        super().begin_episode(index,initial_position)
        self.file.attrs.update(schema_version='labsim.minimal_precision_insertion.v1',
            task='minimal_precision_insertion',physics_hz=self.cfg.physics.hz,
            physics_substeps=self.cfg.physics.hz//self.cfg.task.control_hz,
            observation_alignment='obs_t_before_action_t; next_state_after_physics_hz/control_hz_substeps')

    def cache_transition(self,state,action,next_state,result):
        for key,rgb in state['camera_data'].items():
            self._append(key,rgb.astype(np.uint8))
        fields=dict(agent_pose=state['joint_positions'][:8],actions=action.joint_positions[:8],
            next_agent_pose=next_state['joint_positions'][:8],joint_positions=state['joint_positions'],
            object_pose=np.r_[state['object_position'],state['object_orientation']],
            next_object_pose=np.r_[next_state['object_position'],next_state['object_orientation']],
            finger_contact_N=next_state['finger_contact_N'],timestamp=state['simulation_time'],
            next_timestamp=next_state['simulation_time'],target_tcp=state['target_tcp'],
            actual_tcp=state['tcp'],next_actual_tcp=next_state['tcp'],ik_residual_m=state['ik_residual_m'],
            xy_error_m=next_state['metrics']['xy_error_m'],tilt_rad=next_state['metrics']['tilt_rad'],
            depth_m=next_state['metrics']['depth_m'],overlap_m=next_state['metrics']['overlap_m'],
            grasp_slip_m=next_state['metrics']['slip_m'],module_contact_N=next_state['metrics']['module_contact_N'],
            done=result['status']!='RUNNING',reward=result['status']=='SUCCESS')
        for key,value in fields.items():
            self._append(key,np.asarray(value))
        if self.save_video:
            rgb=np.concatenate([np.transpose(x,(1,2,0)) for x in state['camera_data'].values()],axis=1)
            frame=cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR)
            if self.writer is None:
                self.writer=cv2.VideoWriter(str(self.video_dir/(self.name+'.mp4')),cv2.VideoWriter_fourcc(*'mp4v'),
                    self.cfg.task.control_hz,(frame.shape[1],frame.shape[0]))
                if not self.writer.isOpened():
                    raise RuntimeError('Video writer failed')
            for text,position in [(f"{state['simulation_time']:.1f}s {state['phase']} depth={fields['depth_m']*1000:.2f}mm",(4,15)),
                                  (f"X={fields['xy_error_m'][0]*1000:.3f}mm {result['status']}",(4,30))]:
                cv2.putText(frame,text,position,cv2.FONT_HERSHEY_SIMPLEX,.33,(0,0,0),3)
                cv2.putText(frame,text,position,cv2.FONT_HERSHEY_SIMPLEX,.33,(255,255,255),1)
            self.writer.write(frame)
        self.count+=1
