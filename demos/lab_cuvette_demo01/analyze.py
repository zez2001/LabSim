"""Independent saved-state score and synchronized force/velocity audit, no label rewriting."""
from pathlib import Path
import argparse,json,csv
import numpy as np
from scipy.spatial.transform import Rotation
from omegaconf import OmegaConf
from demos.lab_cuvette_external.run import write

def analyze(folder):
    p=Path(folder);rows=json.loads((p/'physics_records.json').read_text());raw=json.loads((p/'result.json').read_text());cfg=OmegaConf.load(p/'config.yaml');s=cfg.demo_release;hz=cfg.physics.hz
    t=np.array([r['t'] for r in rows]);pos=np.array([r['position'] for r in rows]);q=np.array([r['quaternion'] for r in rows]);q/=np.linalg.norm(q,axis=1)[:,None];rot=Rotation.from_quat(q[:,[1,2,3,0]]);com=np.array([r['com_world_m'] for r in rows]).reshape(-1,3);native=np.array([r['linear_velocity'] for r in rows]);omega=np.array([r['angular_velocity'] for r in rows]);fd=np.zeros_like(com);fd[1:]=np.diff(com,axis=0)*hz;wa=np.zeros_like(com);wa[1:]=(rot[1:]*rot[:-1].inv()).as_rotvec()*hz
    force=np.array([r['support_force_vector_N'] for r in rows]);fm=np.array([r['finger_force_vectors_on_cup_N'] for r in rows]);ff=np.array([r['finger_friction_on_cup_N'] for r in rows]);grips=np.array([r['joints'][7:] for r in rows]);tcp=np.array([r['actual_tcp'] for r in rows]);pen=np.array([r['source_penetration_m'] for r in rows]);gap=np.array([r['target_bottom_signed_gap_m'] for r in rows]);tilt=np.array([r['tilt_deg'] for r in rows]);fingers=np.array([r['finger_force_N'] for r in rows]);ph=np.array([r['phase'] for r in rows]);events=json.loads((p/'events.json').read_text());full=cfg.mode=='workflow'
    def window(ids):
        ix=np.flatnonzero(ids)
        if not len(ix):return dict(available=False)
        return dict(available=True,duration_s=float(t[ix[-1]]-t[ix[0]]),position_drift_m=float(np.linalg.norm(pos[ix]-pos[ix[0]],axis=1).max()),rotation_change_deg=float(np.degrees(2*np.arccos(np.clip(abs(q[ix]@q[ix[0]]),0,1))).max()),max_tilt_deg=float(tilt[ix].max()),max_penetration_m=float(pen[ix].max()),max_abs_target_bottom_gap_m=float(abs(gap[ix]).max()),min_support_Fz_N=float(force[ix,2].min()),max_native_speed_m_s=float(np.linalg.norm(native[ix],axis=1).max()),max_fd_com_speed_m_s=float(np.linalg.norm(fd[ix],axis=1).max()),max_native_angular_rad_s=float(np.linalg.norm(omega[ix],axis=1).max()),max_fd_angular_rad_s=float(np.linalg.norm(wa[ix],axis=1).max()))
    def quiet(w,secs):return bool(w.get('available') and w['duration_s']>=secs-1e-6 and w['position_drift_m']<=s.position_drift_m and w['rotation_change_deg']<=s.orientation_change_deg and w['max_penetration_m']<=s.penetration_m and w['max_tilt_deg']<=s.max_tilt_deg)
    reset_end=t[np.flatnonzero(ph=='RESET')[-1]];initial=window((t>=reset_end-3-1e-8)&(t<=reset_end+1e-8));p0=pos[np.flatnonzero(ph=='RESET')[-1]]
    opened=next((e for e in events if e.get('next')=='OPEN'),None);retreat=next((e for e in events if e.get('next')=='RETREAT'),None);verify=next((e for e in events if e.get('next')=='VERIFY'),None)
    pre=window((t>=opened['t']-s.support_window_s-1e-8)&(t<=opened['t']+1e-8)) if opened else dict(available=False)
    final=window(t>=t[-1]-s.observe_s-1e-8);depth=np.array([r['depth_m'] for r in rows]);clearance=float(tcp[-1,2]-(pos[-1,2]+.0674999952));initial_source_z=cfg.fixtures.source_base_z_m+cfg.fixtures.base_m if full else cfg.scene.table_top_m
    flags=dict(initial_support=quiet(initial,3),physical_grasp=bool(np.any(np.all(fingers>.02,axis=1)&(pos[:,2]-p0[2]>.04))),extracted=bool(np.any((np.array([r['source_bottom_z_m'] for r in rows])>initial_source_z+cfg.fixtures.depth_m+.010)&np.all(fingers>.02,axis=1))),transported=bool(np.linalg.norm(pos[-1,:2]-p0[:2])>=(.12 if full else .025)),target_loaded=bool(np.isfinite(depth[-1]) and depth[-1]>=.018 and abs(gap[-1])<=s.bottom_distance_m and np.max(np.abs(rows[-1]['xy_error_m']))<=cfg.fixtures.inner_m/2-.007425),support_handoff_before_open=bool(opened and quiet(pre,s.support_window_s) and pre['min_support_Fz_N']>=s.min_support_N and pre['max_abs_target_bottom_gap_m']<=s.bottom_distance_m),actual_open_and_detached=bool(retreat and np.all(grips[-1]>.025) and np.all(fingers[-1]<.01)),actual_retreat=bool(verify and clearance>=.04),stable_after_retreat=bool(verify and t[-1]-verify['t']>=s.observe_s and quiet(final,s.observe_s) and final['min_support_Fz_N']>=s.min_support_N),no_observed_source_penetration_over_tolerance=bool(pen.max()<=s.penetration_m))
    native_events=json.loads((p/'native_contact_events.json').read_text());external_robot=[e for e in native_events if not any(x.startswith('/World/Cuvette') for x in e['colliders']) and e['points']];cup_inst=[e for e in native_events if any(x.startswith('/World/Cuvette') for x in e['colliders']) and any(x.startswith('/World/Instrument') for x in e['colliders']) and e['points']]
    flags['no_unintended_instrument_contact']=not(external_robot or cup_inst)
    quality=[]
    if pen.max()>s.penetration_m:quality.append('SOURCE_GEOMETRY_PENETRATION_EXCEEDS_50UM')
    if np.linalg.norm(native[-int(3*hz):]-fd[-int(3*hz):],axis=1).max()>.001:quality.append('NATIVE_VS_POSE_VELOCITY_MISMATCH_RETAINED')
    if external_robot or cup_inst:quality.append('UNINTENDED_INSTRUMENT_OR_FIXTURE_CONTACT')
    quality.extend(['ROBOT_AND_VESSEL_DYNAMICS_NOT_REAL_CALIBRATED','GEOMETRY_CHECKS_SAMPLED_NOT_GLOBAL_NATIVE_SHAPE_PROOF'])
    ok=all(flags.values());result=dict(schema='labsim.V0_demo01.independent.v1',workflow_success=bool(ok and full),tabletop_release_success=bool(ok and not full),native_pair_success=False,full_success=False,full_task_eligible=False,flags=flags,controller_status=raw['status'],controller_success=bool(raw['workflow_success'] or raw.get('tabletop_release_success')),controller_agrees=bool(ok==bool(raw['workflow_success'] or raw.get('tabletop_release_success'))),physics_quality_flags=quality,initial_window=initial,pre_open_window=pre,final_window=final,peak_source_penetration_m=float(pen.max()),peak_source_penetration_time_s=float(t[pen.argmax()]),actual_retreat_clearance_m=clearance,final_depth_m=float(depth[-1]),final_xy_error_m=rows[-1]['xy_error_m'],simulation_seconds=raw['simulation_seconds'],wall_seconds=raw['wall_seconds'],actual_phases=list(dict.fromkeys(ph)),OPEN_executed=opened is not None,RETREAT_executed=retreat is not None,unintended_robot_contact_events=len(external_robot),direct_cup_instrument_contact_events=len(cup_inst))
    audit={}
    for phase in ['RESET','INSERT','SUPPORT_TRANSFER','OPEN','VERIFY']:
        ids=ph==phase
        if not ids.any():continue
        net=force[ids]+fm[ids].sum(1)+ff[ids].sum(1)+[0,0,-.1962]
        u=np.array([r['usd_angular_velocity_deg_s'] for r in rows])[ids]
        audit[phase]=dict(count=int(ids.sum()),native_linear_rms_m_s=float(np.sqrt(np.mean(native[ids]**2)*3)),fd_com_linear_rms_m_s=float(np.sqrt(np.mean(fd[ids]**2)*3)),native_angular_rms_rad_s=float(np.sqrt(np.mean(omega[ids]**2)*3)),fd_angular_rms_rad_s=float(np.sqrt(np.mean(wa[ids]**2)*3)),usd_angular_raw_rms_deg_s=float(np.sqrt(np.nanmean(u*u)*3)),mean_support_vector_N=force[ids].mean(0),mean_finger_normal_sum_N=fm[ids].sum(1).mean(0),mean_finger_friction_sum_N=ff[ids].sum(1).mean(0),mean_contact_plus_gravity_vector_N=net.mean(0),mean_environment_normal_norm_sum_N=float(np.mean([rows[i]['environment_normal_sum_norms_N'] for i in np.flatnonzero(ids)])))
    # Canonical event records: one report side per collider pair and physics step.
    keys=[(e['step'],tuple(sorted(e['colliders'])),e['type']) for e in native_events];dups=len(keys)-len(set(keys))
    write(p/'force_velocity_audit.json',dict(api={'native_linear':'SingleRigidPrim -> tensor RigidBodyView.get_velocities, world COM m/s','native_angular':'same tensor, world rad/s; USD fallback converts degrees to radians','usd_linear':'UsdPhysics.RigidBodyAPI.GetVelocityAttr raw world m/s, read after same physics step; may be stale under Fabric','usd_angular':'GetAngularVelocityAttr raw world deg/s, not tensor rad/s','fd_linear':'world COM positions from same-step source origin+rotated localCOM, backward difference dt','fd_angular':'R_current R_previous^-1 rotation vector /dt, world rad/s','force':'cup-side RigidContactView normal matrix plus get_friction_data; dt=1/physics_hz; no double-side force addition'},phase_summary=audit,duplicate_pair_step_type_reports=dups,duplicate_limitation='types can legitimately differ; records not summed into force query; native event vectors retain reported side convention',assumed_weight_N=.1962,source='20g assumption, not measured'))
    import h5py
    with h5py.File(p/'dataset/episode_0000.h5','r') as h:
        n=len(h['timestamp']);assert n==len(h['actions']) and h['actions'].shape[1]==8 and h['joint_positions'].shape[1]==9
        assert np.allclose(h['next_timestamp'][:]-h['timestamp'][:],1/cfg.physics.control_hz);assert not h.attrs['full_task_eligible'] and not h.attrs['success'];result['h5_alignment_verified']=True
    write(p/'independent_score.json',result)
    with (p/'states.csv').open('w') as fp:
        w=csv.writer(fp);w.writerow(['time_s','phase','x_m','y_m','z_m','bottom_gap_m','tilt_deg','depth_m','penetration_m','support_Fz_N','left_normal_N','right_normal_N','native_speed_m_s','fd_COM_speed_m_s','native_angular_rad_s','fd_angular_rad_s'])
        for i,r in enumerate(rows):w.writerow([t[i],ph[i],*pos[i],gap[i],tilt[i],depth[i],pen[i],force[i,2],*fingers[i],np.linalg.norm(native[i]),np.linalg.norm(fd[i]),np.linalg.norm(omega[i]),np.linalg.norm(wa[i])])
    print(p,'INDEPENDENT',ok,flags,flush=True);return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('folders',type=Path,nargs='+');a=p.parse_args()
    for d in a.folders:analyze(d)
