"""State-based jam diagnostics; command motion alone never establishes insertion."""
import numpy as np

def jam_reason(rows,cfg):
    if not rows:return None
    t=float(rows[-1]['t']);w=[r for r in rows if r['t']>=t-float(cfg['window_s'])-1e-9]
    if len(w)<2 or w[-1]['t']-w[0]['t']<float(cfg['window_s'])-1e-6:return None
    a,b=w[0],w[-1]
    if b.get('target_bottom_signed_gap_m',np.inf)<=.00005:return None
    command_down=float(a['target_tcp'][2]-b['target_tcp'][2]);actual_down=float(a['source_bottom_z_m']-b['source_bottom_z_m'])
    if command_down>=float(cfg['command_down_min_m']) and actual_down<=float(cfg['vessel_down_max_m']):return 'DOWNWARD_COMMAND_WITHOUT_VESSEL_PROGRESS'
    slip=np.linalg.norm(np.asarray(b['cup_in_hand_position_m'])-a['cup_in_hand_position_m'])
    if slip>float(cfg['relative_slip_m']):return 'VESSEL_SLIPPED_RELATIVE_TO_HAND'
    forces=np.array([np.linalg.norm(r['target_support_force_vector_N']) for r in w])
    if np.min(forces[-max(2,len(forces)//2):])>float(cfg['wall_force_N']) and forces[-1]-forces[0]>float(cfg['force_rise_N']):return 'SUSTAINED_RISING_NATIVE_SEAT_FORCE_BEFORE_BOTTOM'
    return None
