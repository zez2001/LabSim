"""Offline record/clock validation and independent geometric rescoring (no Isaac)."""
import argparse
from collections import deque
import json
from pathlib import Path
import sys
import h5py
import numpy as np
from omegaconf import OmegaConf
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from demos.minimal_precision_insertion.geometry import cylinder_mesh,overlap_metrics


def audit_episode(result_path):
    result=json.loads(result_path.read_text());group=result_path.parent
    episode=result_path.stem.replace('_result','')
    cfg=OmegaConf.load(group/'config.yaml')
    hz=cfg.physics.hz;dt=1./hz
    geom=json.loads((group/(episode+'_collision_snapshot.json')).read_text())
    if 'vertices' in geom:
        raw=np.array(geom['vertices']);raw_edges=np.array(geom['edges'])
        vertices,index=np.unique(np.round(raw,12),axis=0,return_inverse=True)
        edges=np.unique(np.sort(index[raw_edges],axis=1),axis=0)
    else:
        vertices,faces=cylinder_mesh(.005,.05,cfg.geometry.tube_segments)
        edges=np.unique(np.sort(np.concatenate([faces[:,[0,1]],faces[:,[1,2]],faces[:,[2,0]]]),axis=1),axis=0)
    initial=json.loads((group/(episode+'_initial.json')).read_text())
    hole=np.array(initial['hole_center_m'])
    times=[];maximum=0.;first_bad=None;stable_start=None;stable_anchor=None
    max_stable=0.;depths=deque();stall=False;slip=False;dropped=False
    with h5py.File(group/'dataset'/(episode+'.h5'),'r') as f:
        n=len(f['actions']);errors=[]
        if not f.attrs.get('complete',False):
            errors.append('recording_incomplete')
        for key in ('camera_1_rgb','camera_2_rgb','agent_pose','next_agent_pose','object_pose','next_object_pose','timestamp','next_timestamp','done'):
            if len(f[key])!=n:
                errors.append('length_'+key)
        t=f['timestamp'][:];tn=f['next_timestamp'][:]
        if n>1 and not np.allclose(t[1:],tn[:-1],atol=1e-9,rtol=0):
            errors.append('transition_time_alignment')
        if n>1 and not np.allclose(tn[:-1]-t[:-1],1/60,atol=1e-9,rtol=0):
            errors.append('control_period')
        if n>1 and not np.array_equal(f['object_pose'][1:],f['next_object_pose'][:-1]):
            errors.append('observation_successor_alignment')
        if not bool(f['done'][-1]):
            errors.append('terminal_done_missing')
        for key in ('actions','joint_positions','object_pose','next_object_pose'):
            if not np.isfinite(f[key][:]).all():errors.append('nonfinite_'+key)
        for key in ('camera_1_rgb','camera_2_rgb'):
            if f[key].shape[1:]!=(3,256,256) or f[key].dtype!=np.uint8:
                errors.append('rgb_schema_'+key)
            elif any(np.ptp(f[key][i])==0 for i in (0,n//2,n-1)):
                errors.append('blank_sampled_rgb_'+key)
        q=f['joint_positions'][:];qnext=f['next_agent_pose'][:];tcp=f['next_actual_tcp'][:]
        for line in (group/(episode+'_physics.jsonl')).open():
            p=json.loads(line);time=p['time'];times.append(time)
            m=overlap_metrics(np.array(p['position']),p['orientation'],vertices,edges,hole,cfg.task.floor_z,cfg.geometry.hole_segments)
            bound=m['overlap_m']+(3e-6 if cfg.geometry.collision=='analytic_cylinder' and m['lowest_depth_m']>=0 else 0.)
            maximum=max(maximum,bound)
            if bound>cfg.task.penetration_tolerance_m and first_bad is None:
                first_bad=dict(time=time,wall_mm=m['wall_overlap_m']*1000,base_mm=m['base_overlap_m']*1000)
            depths.append((time,m['depth_m']))
            while depths[0][0]<time-2.:
                depths.popleft()
            if (2.<time<24. and m['depth_m']<.018 and p['module_contact_N']>.01
                and time-depths[0][0]>1.98 and np.ptp([x[1] for x in depths])<.0001):
                stall=True
            slip=slip or (time<25. and p['slip_m']>.008)
            dropped=dropped or p['position'][2]<.735
            if time+1e-9>=30.:
                frame=min(np.searchsorted(tn,time-1e-9),n-1)
                joints=np.array(p.get('joint_positions',q[frame]))
                opened=np.all(joints[7:]>.035)
                valid=(.018<=m['depth_m']<=.020+cfg.task.penetration_tolerance_m and opened
                    and np.array(p['tcp'])[2]-(cfg.task.floor_z+.020)>.035
                    and np.all(np.array(p['finger_contact_N'])<.01)
                    and m['containment_error_m']<=cfg.task.penetration_tolerance_m
                    and bound<=cfg.task.penetration_tolerance_m)
                if stable_anchor is None:
                    stable_anchor=(np.array(p['position']),np.array(p['orientation']))
                angle=2*np.arccos(np.clip(abs(np.dot(stable_anchor[1],p['orientation'])),0,1))
                valid=valid and np.linalg.norm(np.array(p['position'])-stable_anchor[0])<.0001 and angle<np.radians(.5)
                if valid:
                    if stable_start is None:
                        stable_start=time
                    max_stable=max(max_stable,time-stable_start)
                else:
                    stable_start=None
        if len(times)>1 and not np.allclose(np.diff(times),dt,atol=1e-9,rtol=0):
            errors.append('physics_period')
        if not np.isclose(result['engine_simulation_seconds'],result['simulation_seconds'],atol=1e-5,rtol=0):
            errors.append('engine_clock')
        if not np.isclose(times[-1],tn[-1],atol=1e-9,rtol=0):
            errors.append('physics_control_last_time')
        ikmax=float(np.max(f['ik_residual_m'][:])*1000)
    if first_bad is not None:
        independent='PHYSICS_INVALID'
    elif dropped:
        independent='DROPPED'
    elif slip:
        independent='GRASP_SLIP'
    elif 'diagnostic' in result and n==180 and np.isclose(times[-1],3.,atol=1e-9) and result['diagnostic']['max_environment_contact_N']==0.:
        independent='DIAGNOSTIC_COMPLETE'
    elif max_stable+1e-9>=1.:
        independent='SUCCESS'
    elif stall:
        independent='BLOCKED'
    elif result['status']=='CONTROL_OR_IK_FAILURE':
        independent='CONTROL_OR_IK_FAILURE'
    elif times[-1]>=32.-1e-9:
        independent='UNSTABLE_AFTER_RELEASE'
    else:
        independent='TIMEOUT'
    return dict(file=str(result_path),online=result['status'],independent=independent,
        match=result['status']==independent,errors=errors,frames=n,physics_steps=len(times),
        independent_max_overlap_mm=maximum*1000,first_invalid=first_bad,
        stable_seconds=max_stable,max_ik_residual_mm=ikmax,
        limitation='Uses saved actual poses and cooked convexes plus authored static wall polygons; not a complete wall cooking audit.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    reports=[]
    for path in sorted(args.directory.rglob('episode_*_result.json')):
        reports.append(audit_episode(path))
        print(path.parent.name,path.name,reports[-1]['independent'],reports[-1]['errors'],flush=True)
    args.output.write_text(json.dumps(reports,indent=2)+'\n')
    return 0 if reports and all(x['match'] and not x['errors'] for x in reports) else 1


if __name__=='__main__':
    sys.exit(main())
