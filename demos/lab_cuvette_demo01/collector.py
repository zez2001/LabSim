"""Reuse existing aligned writer with an isolated workflow eligibility contract."""
from data_collectors.lab_cuvette_loading_collector import LabCuvetteLoadingCollector
class DemoCollector(LabCuvetteLoadingCollector):
    def cache_transition(self,state,action,next_state,result):
        super().cache_transition(state,action,next_state,result)
        self.count-=1
        for key in ['linear_velocity','angular_velocity','usd_linear_velocity','usd_angular_velocity_deg_s','fd_com_velocity','fd_angular_velocity','support_force_vector_N','source_bottom_z_m','source_penetration_m','finger_force_vectors_on_cup_N','finger_friction_on_cup_N']:
            self._append('diagnostic/'+key,next_state[key])
        self.count+=1
