"""Existing learning transition writer, separate diagnostic flags and video."""
import cv2,numpy as np
from demos.lab_cuvette_external.collector import ExternalCollector

class DiagnosticCollector(ExternalCollector):
    def cache_transition(self,state,action,next_state,result):
        video=self.save_video;self.save_video=False
        try:super().cache_transition(state,action,next_state,result)
        finally:self.save_video=video
        # Parent increments count; append at this SAME transition row.
        self.count-=1
        for key in ['source_penetration_m','source_bottom_gap_m','linear_velocity','angular_velocity','support_force_vector_N','cup_in_hand_position_m','cup_in_hand_quaternion']:
            self._append('diagnostic/'+key,next_state[key])
        self.count+=1
        if video:
            rgb=np.concatenate([np.transpose(v,(1,2,0)) for v in next_state['camera_data'].values()],axis=1);frame=cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR)
            if self.writer is None:self.writer=cv2.VideoWriter(str(self.video_dir/(self.name+'.mp4')),cv2.VideoWriter_fourcc(*'mp4v'),60,(512,256))
            for text,y in [(f"EXT02 TABLE diagnostic t={next_state['simulation_time']:.2f} {state['phase']}",14),('Full instrument loading: NOT EXECUTED',29)]:
                cv2.putText(frame,text,(3,y),cv2.FONT_HERSHEY_SIMPLEX,.31,(0,0,0),3);cv2.putText(frame,text,(3,y),cv2.FONT_HERSHEY_SIMPLEX,.31,(255,255,255),1)
            self.writer.write(frame)
