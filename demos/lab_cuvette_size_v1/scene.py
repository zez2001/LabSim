"""Keep the original assembly intact; move only the commanded loading axis."""
import numpy as np

def layout(cfg):
    from demos.lab_cuvette_demo04.scene import layout as original
    result=original(cfg)
    offset=np.asarray(cfg.geometry.target_loading_offset_local_m,float)
    result['seat_original_floor']=result['target_floor'].copy()
    result['target_loading_offset_local_m']=offset.copy()
    result['target_floor']=result['target_floor']+result['instrument_rotation']@offset
    result['target_depth_m']=float(cfg.geometry.target_depth_m)
    result['target_rim_z']=float(result['target_floor'][2]+result['target_depth_m'])
    return result
