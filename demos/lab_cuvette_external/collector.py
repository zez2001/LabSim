"""Reuse V0 HDF5 transitions; make unavailable mesh scoring explicit in new video."""
import cv2
import numpy as np
from data_collectors.lab_cuvette_loading_collector import LabCuvetteLoadingCollector

class ExternalCollector(LabCuvetteLoadingCollector):
    def cache_transition(self,state,action,next_state,result):
        video=self.save_video;self.save_video=False
        self._append('privileged/overlap_measurement_available',np.bool_(False))
        try:super().cache_transition(state,action,next_state,result)
        finally:self.save_video=video
        if not video:return
        rgb=np.concatenate([np.transpose(x,(1,2,0)) for x in next_state['camera_data'].values()],axis=1)
        frame=cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR)
        if self.writer is None:
            self.writer=cv2.VideoWriter(str(self.video_dir/(self.name+'.mp4')),cv2.VideoWriter_fourcc(*'mp4v'),self.cfg.physics.control_hz,(frame.shape[1],frame.shape[0]))
            if not self.writer.isOpened():raise RuntimeError('External diagnostic video writer failed')
        lines=[f"EXT01 diagnostic t={next_state['simulation_time']:.2f} {state['phase']}",'Full loading BLOCKED; mesh overlap NOT measured']
        for text,y in zip(lines,[14,28]):
            cv2.putText(frame,text,(3,y),cv2.FONT_HERSHEY_SIMPLEX,.31,(0,0,0),3);cv2.putText(frame,text,(3,y),cv2.FONT_HERSHEY_SIMPLEX,.31,(255,255,255),1)
        self.writer.write(frame)
