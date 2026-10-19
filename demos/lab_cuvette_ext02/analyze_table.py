"""Independent post-hoc physical tabletop adjudication; never writes labels back."""
import argparse,json,csv
from pathlib import Path
import numpy as np
from omegaconf import OmegaConf
from demos.lab_cuvette_ext02.build import ROOT
from demos.lab_cuvette_ext02.support import measure
from demos.lab_cuvette_external.run import write

def analyze(folder):
    p=Path(folder);rows=json.load(open(p/'physics_records.json'));raw=json.load(open(p/'result.json'));cfg=OmegaConf.load(p/'config.yaml');cfg.acceptance.setdefault('upright_after_release_deg',1.);cfg.acceptance.setdefault('actual_retreat_clearance_m',.040)
    time=np.array([r['t'] for r in rows]);pos=np.array([r['position'] for r in rows]);vel=np.array([r['linear_velocity'] for r in rows]);ang=np.array([r['angular_velocity'] for r in rows]);q=np.array([r['quaternion'] for r in rows]);q/=np.linalg.norm(q,axis=1)[:,None];tilt=np.degrees(np.arccos(np.clip(1-2*(q[:,1]**2+q[:,2]**2),-1,1)));f=np.array([r['finger_force_N'] for r in rows]);force=np.array([r['support_force_vector_N'] for r in rows]);tcp=np.array([r['actual_tcp'] for r in rows]);bottom=np.array([r['source_bottom_z_m'] for r in rows]);events=json.load(open(p/'events.json'));opened=next((e for e in events if e.get('next')=='OPEN'),None);retreated=any(e.get('next')=='RETREAT' for e in events)
    initial=measure([r for r in rows if r['t']<=5.+1e-8],cfg);t0=pos[np.flatnonzero(time<=5)[-1]];lift=pos[:,2]-t0[2];valid=(lift>=cfg.acceptance.lift_m)&np.all(f>.02,axis=1);best=0.;start=None
    for t,ok in zip(time,valid):
        if ok:
            if start is None:start=t
            best=max(best,t-start)
        else:start=None
    before=None;release_ok=False
    if opened:
        ids=(time>=opened['t']-.5-1e-8)&(time<=opened['t']+1e-8);before=dict(start_s=float(time[ids][0]),end_s=float(time[ids][-1]),max_speed_m_s=float(np.linalg.norm(vel[ids],axis=1).max()),max_angular_speed_rad_s=float(np.linalg.norm(ang[ids],axis=1).max()),min_support_force_N=float(force[ids,2].min()),max_bottom_distance_m=float(np.abs(bottom[ids]-.74).max()))
        release_ok=bool(before['max_speed_m_s']<=cfg.acceptance.linear_speed_m_s and before['max_angular_speed_rad_s']<=cfg.acceptance.angular_speed_rad_s and before['min_support_force_N']>=cfg.acceptance.release_support_force_N and before['max_bottom_distance_m']<=cfg.acceptance.release_bottom_gap_m)
    final=measure(rows,cfg);clearance=float(tcp[-1,2]-(pos[-1,2]+.0674999952));stable=bool(opened and retreated and final['static_pass'] and tilt[-1]<=cfg.acceptance.upright_after_release_deg and clearance>=cfg.acceptance.actual_retreat_clearance_m and np.all(f[-1]<.01))
    transport=[r for r in rows if r['phase']=='TRANSPORT'];transport_ok=bool(transport and np.linalg.norm(np.array(transport[-1]['position'])[:2]-t0[:2]-[.03,.02])<=.003 and np.all(np.array(transport[-1]['finger_force_N'])>.02))
    flags=dict(support_valid=bool(initial['static_pass']),grasp_success=bool(best>=1.),hold_success=bool(best>=1.),transport_success=transport_ok,pre_release_supported_and_quiet=release_ok,released_stable=stable);success=bool(all(flags.values()))
    result=dict(schema='labsim.V0_ext02.independent_tabletop.v1',diagnostic_success=success,full_success=False,full_task_executed=False,flags=flags,controller_diagnostic_success=raw['diagnostic_success'],controller_agrees=success==raw['diagnostic_success'],actual_hold_s=best,max_lift_m=float(lift.max()),final_tilt_deg=float(tilt[-1]),actual_retreat_clearance_m=clearance,pre_release=before,final_window=final,simulation_seconds=raw['simulation_seconds'],wall_seconds=raw['wall_seconds'])
    if success:status='DIAGNOSTIC_SUCCESS'
    elif final['source_penetration_m']>cfg.acceptance.steady_source_penetration_m:status='PHYSICS_INVALID'
    elif not transport_ok:status='GRASP_SLIP'
    elif opened:status='UNSTABLE_AFTER_RELEASE'
    elif np.any(force[-int(cfg.physics.hz):,2]>=cfg.acceptance.release_support_force_N):status='PRE_RELEASE_UNSTABLE'
    else:status='PLACEMENT_SUPPORT_NOT_ESTABLISHED'
    result.update(independent_status=status,controller_status=raw['status'],OPEN_executed=bool(opened),RETREAT_executed=retreated,steady_velocity_thresholds_source='engineering assumptions declared in ext02 config, not measured hardware specifications')
    write(p/'independent_tabletop_score.json',result)
    with (p/'tabletop_states.csv').open('w') as fp:
        w=csv.writer(fp);w.writerow(['time_s','phase','x_m','y_m','z_m','source_bottom_m','tilt_deg','speed_m_s','angular_speed_rad_s','left_N','right_N','support_z_N'])
        for i,r in enumerate(rows):w.writerow([time[i],r['phase'],*pos[i],bottom[i],tilt[i],np.linalg.norm(vel[i]),np.linalg.norm(ang[i]),*f[i],force[i,2]])
    import h5py
    with h5py.File(p/'dataset/episode_0000.h5','r') as h:
        n=len(h['timestamp']);assert len(h['actions'])==n and len(h['next_timestamp'])==n
        assert np.allclose(h['next_timestamp'][:]-h['timestamp'][:],1/60)
        assert h['actions'].shape[1]==8 and h['joint_positions'].shape[1]==9
        assert not h.attrs['success'] and not h.attrs['full_task_eligible']
        assert all(k not in h for k in ['privileged/depth_m','privileged/overlap_m'])
        result['h5_alignment_verified']=True;write(p/'independent_tabletop_score.json',result)
    print(p,'INDEPENDENT',success,flags,flush=True)
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('folders',nargs='+',type=Path);a=p.parse_args()
    for folder in a.folders:analyze(folder)
