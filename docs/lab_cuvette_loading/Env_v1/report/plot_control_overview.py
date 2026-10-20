"""Compact control evidence from closed HDF5 only; no physics JSONL scan."""
from pathlib import Path
import json,hashlib
import numpy as np,h5py
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parents[4];BASE=ROOT/'outputs/lab_cuvette_loading/Env_v1';OUT=ROOT/'docs/lab_cuvette_loading/Env_v1/data'
RUNS=[('extract_transport_01','feedback01 false','#c17b26'),('extract_fixed_orientation_01','fixed01 false','#86519d'),('extract_continuous_latch_01','latch01 hold false','#346da4'),('preinsert_continuous_latch_01','preinsert diagnostic true','#168153')]
def main():
    fig,axes=plt.subplots(3,1,figsize=(7.8,5.5),sharex=True,constrained_layout=True)
    plt.rcParams.update({'font.size':12,'axes.spines.top':False,'axes.spines.right':False})
    inset=axes[2].inset_axes([.51,.28,.25,.65]);records=[]
    for name,label,color in RUNS:
        p=BASE/name/'episode_0000';score=json.loads((p/'result.json').read_text());h5=p/'dataset/episode_0000.h5'
        with h5py.File(h5,'r') as f:
            if not f.attrs.get('complete'):raise ValueError('Not closed: '+name)
            rows=[json.loads(x) for x in f['privileged/state_json'][:]]
            rows.append(json.loads(f['privileged/next_state_json'][-1]))
            times=np.array([x['t'] for x in rows]);bottom=np.array([x['source_bottom_z_m'] for x in rows]);grip=np.r_[np.array(f['control_auxiliary/gripper_target_m'][:]),f['control_auxiliary/gripper_target_m'][-1]]*2000
            t0=score['observed_events']['bilateral_grasp_observed']['t'];index=int(np.argmin(abs(times-t0)))
            relative=np.array([x['cup_in_hand_position_m'] for x in rows]);drift=np.linalg.norm(relative-relative[index],axis=1)*1e6;drift[times<t0]=np.nan
            settled=bottom[int(np.argmin(abs(times-4.0)))];lift=(bottom-settled)*1000
            axes[0].plot(times,lift,color=color,lw=1.7,label=label)
            axes[1].plot(times,np.where(drift>.1,drift,np.nan),color=color,lw=1.7)
            axes[2].plot(times,grip,color=color,lw=1.7);inset.plot(times,grip,color=color,lw=1.8)
            records.append(dict(run=name,source_h5=str(h5.relative_to(ROOT)),closed=True,transitions=len(f['actions']),plot_samples=len(rows),task_success=score['task_success'],task_type=score['task_type'],full_success=score['full_success'],source_slot_cleared=score['source_slot_cleared'],transport_success=score['transport_success'],terminal_bottom_lift_mm=float(lift[-1]),plot60Hz_max_relative_origin_drift_um=float(np.nanmax(drift)),score240Hz_max_relative_origin_drift_um=score['grasp_relative_pose']['maximum_position_drift_m']*1e6,gripper_total_opening_min_after_latch_mm=float(np.min(grip[times>=t0])),gripper_total_opening_max_after_latch_mm=float(np.max(grip[times>=t0]))))
    axes[0].set_ylabel('Bottom lift\n(mm)',fontsize=12);axes[0].set_ylim(-5,245);axes[0].set_yticks([0,100,200]);axes[0].legend(fontsize=11,ncol=2,loc='upper right')
    axes[1].set_ylabel('Relative drift\n(µm log)',fontsize=12);axes[1].set_yscale('log');axes[1].set_ylim(.8,2500);axes[1].set_yticks([1,10,100,1000]);axes[1].set_yticklabels(['1','10','100','1000']);axes[1].axhline(200,color='#555',lw=.8,ls=':')
    axes[2].set_ylabel('Grip opening\n(mm)',fontsize=12);axes[2].set_ylim(12.05,13.25);axes[2].set_yticks([12.33,12.82,13.15]);axes[2].set_xlabel('Simulation time (s)',fontsize=12)
    inset.set_xlim(14.35,14.65);inset.set_ylim(12.2,12.97);inset.set_xticks([14.4,14.6]);inset.set_yticks([12.33,12.82]);inset.tick_params(labelsize=11);inset.set_title('Latch transition',fontsize=11);inset.grid(alpha=.15)
    for axis in axes:
        axis.set_xlim(14.2,84);axis.tick_params(labelsize=11);axis.grid(alpha=.15)
    fig.suptitle('Actual control trials  Full native loading remains incomplete',fontsize=12.5)
    fig.savefig(OUT/'control_results_compact.png',dpi=210);plt.close(fig)
    evidence=dict(schema='labsim.Env_v1.compact_control_plot.v1',sources='Closed HDF5 privileged/state_json plus last actual successor; full physicsJSONL not loaded',plot_scope='60Hz samples; scoring maxima independently computed at240Hz and retained separately',relative_reference='Nearest recorded bilateral-grasp event control observation; samples before grasp unavailable, zeros not invented',axis_note='Relative drift uses log axis; values <=0.1um omitted from log display. Grip panel shows postcontact12.05..13.25mm; inset shows original opening jump.',independent_score_not_modified=True,full_loading_success=False,records=records,analysis_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (OUT/'control_results_compact.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(figure=str(OUT/'control_results_compact.png'),runs=len(records),no_simulation=True)))
if __name__=='__main__':main()
