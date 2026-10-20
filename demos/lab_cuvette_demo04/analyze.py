"""Independent saved-state scoring for nominal native-seat diagnostics.

A preinsert episode cannot qualify as a complete native loading demonstration.
Unknown native penetration and unavailable post-release observations stay null.
"""
from pathlib import Path
import json,hashlib
import numpy as np
from scipy.spatial.transform import Rotation
from demos.lab_cuvette_demo04.scene import layout
from omegaconf import OmegaConf

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def window(rows,start,end):
    w=[x for x in rows if start-1e-9<=x['t']<=end+1e-9]
    if not w:return dict(available=False)
    p=np.array([r['position'] for r in w]);q=np.array([r['quaternion'] for r in w]);q/=np.linalg.norm(q,axis=1)[:,None]
    return dict(available=True,start_s=w[0]['t'],end_s=w[-1]['t'],duration_s=w[-1]['t']-w[0]['t'],samples=len(w),position_drift_m=float(np.linalg.norm(p-p[0],axis=1).max()),orientation_change_deg=float(np.degrees(2*np.arccos(np.clip(abs(q@q[0]),0,1))).max()),max_observed_rack_table_penetration_m=max(r['source_penetration_m'] for r in w))

def analyze(episode,contract):
    ep=Path(episode).resolve();rows=json.loads((ep/'physics_records.json').read_text());events=json.loads((ep/'events.json').read_text());raw=json.loads((ep/'result.json').read_text());cfg=OmegaConf.load(ep/'config.yaml');d=layout(cfg);t=float(rows[-1]['t']);phases=list(dict.fromkeys(r['phase'] for r in rows));end=rows[-1]
    source=[r for r in rows if r['phase']=='RESET' and r['t']>=1]
    grasp=[r for r in rows if r['phase']=='GRASP']
    transported=[r for r in rows if r['phase'] in ['TRANSPORT','ALIGN','GATE_RETRACT','DIAGNOSTIC_HOLD']]
    gate_events=[e for e in events if e.get('event')=='known_geometry_gate_stop_before_native_tabs']
    checks=dict(scene_population_and_orientation=contract.get('scene_correspondence',{}).get('accepted') is True and contract.get('instrument_count')==1,
        source_initial_support=bool(source and all(r['independent_geometry']['source_supported_inside_designated_slot'] for r in source[-int(cfg.physics.hz):])),
        actual_bilateral_grasp=bool(grasp and min(grasp[-1]['finger_force_N'])>.02),
        actual_source_extraction=bool(transported and max(r['independent_geometry']['source_clearance_m'] for r in transported)>.01),
        actual_transport_to_target_region=bool(transported and min(np.linalg.norm(r['xy_error_m']) for r in transported)<.003),
        controlled_stop_above_obstructed_seat=bool(gate_events and gate_events[-1]['source_bottom_z_m']>=d['target_rim_z']+.0009),
        actual_upward_diagnostic_retraction=bool(gate_events and end['source_bottom_z_m']-gate_events[-1]['source_bottom_z_m']>=.008),
        finite_native_state=bool(all(np.isfinite(np.r_[r['position'],r['quaternion'],r['linear_velocity'],r['angular_velocity']]).all() for r in rows)),
        no_forbidden_robot_environment_contact=not any(r['independent_geometry']['forbidden_robot_environment_contact'] for r in rows),
        continuous_explicit_substeps=bool(len(rows)==raw['frames']*(cfg.physics.hz//cfg.physics.control_hz)+1 and np.allclose(np.diff([r['t'] for r in rows]),1/cfg.physics.hz,atol=1e-10,rtol=0)))
    blocked=not contract.get('geometry_audit',{}).get('accepted',False)
    # Retained original tabs have positive material-intersection witnesses;
    # this run intentionally does not execute the obstructed insertion or release.
    qualified=False
    return dict(schema='labsim.V0_demo04.independent.v1',scene_version='V0_demo04',scene_mode='native_nominal',data_scope='lab_cuvette_loading_V0_demo04_native_nominal',source_episode=str(ep),source_slot_id=d['source_slot_id'],target_seat_id=d['target_seat_id'],asset_manifest_sha256=contract['asset_manifest_sha256'],scene_correspondence_accepted=checks['scene_population_and_orientation'],geometry_gate_passed=not blocked,geometry_gate_basis='retained original source-mesh intersection witnesses; not nominal gap threshold',workflow_success=False,native_pair_success=False,real_calibrated=False,data_eligible=False,diagnostic_read_eligible=raw['frames']>0,diagnostic_subtask_completed=bool(all(checks.values()) and raw['status']=='GEOMETRY_BLOCKED_PREINSERT'),status=raw['status'],checks=checks,phases_executed=phases,trajectory_end_time_s=t,simulation_seconds=t,record_count=len(rows),frames=raw['frames'],physics_records_sha256=sha(ep/'physics_records.json'),events_sha256=sha(ep/'events.json'),post_retreat_window=dict(available=False,reason='No full-task release and RETREAT/VERIFY completed'),stable_after_retreat=None,terminal_window=window(rows,max(0,t-3),t),native_seat_penetration_m=None,native_seat_penetration_available=False,physics_quality_flags=['USER_NOMINAL_DIMENSIONS_NOT_REAL_CALIBRATED','ORIGINAL_SEAT_MATERIAL_INTERFERENCE_CONFIRMED','NATIVE_COOKED_GEOMETRY_AND_SEAT_PENETRATION_NOT_FULLY_MEASURED','NO_NATIVE_INSERTION_OR_RELEASE_EXECUTED'],classification='preinsert diagnostic; never full loading success')
