"""Read saved diagnostics; independent source-mesh support/pose and HDF5 timing audit."""
from pathlib import Path
import json,csv
import numpy as np
import h5py
from scipy.spatial.transform import Rotation
from demos.lab_cuvette_external.geometry import ROOT,DOC,normalized,tri,write

def main():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    _,rows=normalized('TestTube_Baked.usd');vertices=tri(rows[0]).vertices
    root=ROOT/'outputs/lab_cuvette_loading/V0_ext01';allrows=[]
    for directory in sorted(root.iterdir()):
        resultfile=directory/'result.json'
        if not resultfile.exists():continue
        result=json.loads(resultfile.read_text());row=dict(directory=directory.name,status=result['status'],full_success=result.get('full_success',False),diagnostic_pass=result.get('diagnostic_pass'),held=result.get('subtask_held'),simulation_s=result.get('simulation_seconds'),wall_s=result.get('wall_seconds'))
        file=directory/'dataset/episode_0000.h5'
        if file.exists():
            with h5py.File(file) as f:
                n=len(f['actions']);t=f['timestamp'][:];nt=f['next_timestamp'][:];arrays=[]
                def visit(name,obj):
                    if isinstance(obj,h5py.Dataset) and obj.dtype.kind in 'fibu':arrays.append((name,obj.shape,bool(np.isfinite(obj[:]).all())))
                f.visititems(visit)
                row['h5']=dict(frames=n,actions=list(f['actions'].shape),robot_state=list(f['joint_positions'].shape),camera_1=list(f['camera_1_rgb'].shape),rgb_dtype=str(f['camera_1_rgb'].dtype),finite=all(a[2] for a in arrays),time_monotonic=bool(np.all(np.diff(t)>0)),dt_min=float(np.min(nt-t)),dt_max=float(np.max(nt-t)),transition_alignment=bool(np.allclose(nt[:-1],t[1:],atol=1e-9)),all_numeric_lengths_match=all(s[0]==n for _,s,_ in arrays),complete=bool(f.attrs.get('complete')),full_success_attr=bool(f.attrs.get('success')),actual_overlap_available=bool(f.attrs.get('overlap_measurement_available',False)),privileged_progress_columns=['actual_held'],learning_schema_unchanged='RGB CHW uint8 256; q8; action8; state9')
        datafile=directory/'physics_records.json'
        if datafile.exists():
            records=json.loads(datafile.read_text());q=np.array([x['orientation'] for x in records]);p=np.array([x['position'] for x in records]);rot=Rotation.from_quat(q[:,[1,2,3,0]]);tilt=np.degrees(np.arccos(np.clip(rot.apply(np.tile([0,0,1.],(len(q),1)))[:,2],-1,1)))
            lows=np.array([(vertices@R.T+pos).min(0)[2] for R,pos in zip(rot.as_matrix(),p)])
            times=np.array([x['time'] for x in records]);forces=np.array([x['finger_force_N'] for x in records]);startpos=json.loads((directory/'initial.json').read_text())['position'];lift=p[:,2]-startpos[2];active=(forces>.02).all(1)&(lift>=.040);longest=0.;begin=None
            for t,ok in zip(times,active):
                if ok:
                    if begin is None:begin=t
                    longest=max(longest,t-begin)
                else:begin=None
            clock=[abs(x['engine_elapsed']-x['time']) for x in records if 'engine_elapsed' in x]
            row['independent_actual_states']=dict(longest_bilateral_lift_hold_s=longest,hold_1s_pass=bool(longest>=1.-1e-6),max_origin_lift_m=float(lift.max()),max_xy_displacement_m=float(np.linalg.norm(p[:,:2]-np.array(startpos[:2]),axis=1).max()),final_tilt_deg=float(tilt[-1]),max_source_vertex_table_penetration_lower_bound_m=float(max(0,.740-lows.min())),final_actual_lowest_source_vertex_z_m=float(lows[-1]),engine_clock_max_error_s=max(clock) if clock else None,penetration_coverage='all source vertices vs horizontal table; vertex samples do NOT prove no mesh-mesh wall intersection; robot/dynamic distractor overlap not fully covered')
            phase_events=[];previous=None
            for r in records:
                if r['phase']!=previous:phase_events.append(dict(time=r['time'],event='PHASE_CHANGE',phase=r['phase']));previous=r['phase']
            row['phase_events']=phase_events
        allrows.append(row)
    write(DOC/'diagnostic_audit.json',dict(episodes=allrows,full_task_successes=0,eligible_complete_task_training_episodes=0,success_rate_not_estimated=True))
    for key in ['drop_final01','side_final01','grasp_table02','rack01']:
        path=root/key/'physics_records.json'
        if not path.exists():continue
        r=json.loads(path.read_text());times=np.array([x['time'] for x in r]);p=np.array([x['position'] for x in r]);f=np.array([x['finger_force_N'] for x in r]);fig,axs=plt.subplots(2,1,figsize=(9,6),sharex=True)
        axs[0].plot(times,p[:,2]*1000,label='Actual body origin Z');axs[0].set_ylabel('World Z mm');axs[0].legend();axs[0].grid(alpha=.2)
        axs[1].plot(times,f[:,0],label='Left finger');axs[1].plot(times,f[:,1],label='Right finger');axs[1].set_ylabel('Contact force N');axs[1].set_xlabel('Recorded simulation time s');axs[1].legend();axs[1].grid(alpha=.2)
        fig.suptitle(key+' source: actual saved PhysX states; not full loading');fig.tight_layout();fig.savefig(DOC/(key+'_trace.png'),dpi=160);plt.close(fig)
    print('DIAGNOSTIC_AUDIT',len(allrows),'records; full task successes0')

if __name__=='__main__':main()
