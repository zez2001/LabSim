"""Read-only computation of real extract01/grasp04 alignment evidence."""
import hashlib,json
from pathlib import Path
from datetime import datetime
import numpy as np,h5py
from scipy.spatial.transform import Rotation as R
from scipy.ndimage import uniform_filter1d
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parents[4]
BASE=ROOT/'outputs/lab_cuvette_loading/Env_v1'
OUT=ROOT/'docs/lab_cuvette_loading/Env_v1/data'
REF=15.266666666666667

def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(2**20),b''):h.update(chunk)
    return h.hexdigest()

def rotation(q):return R.from_quat(np.roll(q,-1,axis=-1))

def main():
    data={};sources=[]
    for name in ['grasp_hold_04','extract_transport_01']:
        path=BASE/name/'episode_0000'
        rows=[json.loads(s) for s in (path/'physics_records.jsonl').read_text().splitlines()]
        d=dict(rows=rows,events=json.loads((path/'teacher_events.json').read_text()),result=json.loads((path/'result.json').read_text()))
        for key,field in [('t','t'),('normal','finger_normal_force_on_cup_N'),('friction','finger_friction_force_on_cup_N'),('env','environment_net_force_N'),('bottom','source_bottom_z_m')]:d[key]=np.asarray([r[field] for r in rows])
        d['opening']=np.array([2*r['gripper_target_m'] for r in rows]);d['actualopening']=np.array([sum(r['finger_joint_positions_m']) for r in rows])
        for key,field in [('cupR','object_quaternion_wxyz'),('handR','actual_tcp_quaternion_wxyz'),('relR','cup_in_hand_quaternion_wxyz')]:d[key]=rotation(np.array([r[field] for r in rows]))
        d['fkR']=rotation(np.array([r['command_FK_TCP_pose']['quaternion_wxyz'] for r in rows]));data[name]=d
        for rel in ['physics_records.jsonl','teacher_events.json','result.json','dataset/episode_0000.h5']:
            p=path/rel;sources.append(dict(path=str(p.relative_to(ROOT)),bytes=p.stat().st_size,sha256=sha(p)))
    d=data['extract_transport_01'];rows=d['rows'];t=d['t'];ref=rows[int(np.argmin(abs(t-REF)))];ri=int(np.argmin(abs(t-REF)))
    for x in data.values():x['delta']={k:(x[k]*d[k][ri].inv()).as_rotvec()*180/np.pi for k in ['cupR','handR','relR','fkR']}
    windows=[]
    for name,x in data.items():
        for a,b in [(14.3,14.4166),(14.4333,14.5166),(14.6,15.2),(15.3,15.45),(15.5,15.7667)]:
            m=(x['t']>=a)&(x['t']<=b)
            windows.append(dict(run=name,start_s=a,end_s=b,sample_count=int(m.sum()),finger_normal_mean_world_N=x['normal'][m].mean(0).tolist(),finger_friction_mean_world_N=x['friction'][m].mean(0).tolist(),environment_mean_world_N=x['env'][m].mean(0).tolist(),gravity_world_N=[0.,0.,-.1962],contact_minus_weight_mean_world_N=((x['normal'][m]+x['friction'][m]).sum(1).mean(0)+x['env'][m].mean(0)-[0,0,.1962]).tolist()))
    onsets={str(v):{k:next((float(t[i]) for i in range(len(t)) if t[i]>=REF and np.linalg.norm(delta[i])>v),None) for k,delta in d['delta'].items()} for v in [.05,.1,.3,.5,1.]}
    with h5py.File(BASE/'extract_transport_01/episode_0000/dataset/episode_0000.h5','r') as f:
        index=[int(round(float(s)*240)) for s in f['next_timestamp'][:]]
        goals=[json.loads(v)['target_pose'] for v in f['action_conversion_json'][:]];gt=f['timestamp'][:]
        gr=rotation(np.array([v['quaternion_wxyz'] for v in goals]));g0=int(np.argmin(abs(gt-REF)));gd=(gr*gr[g0].inv()).as_rotvec()*180/np.pi
        fk=rotation(np.array([rows[i]['command_FK_TCP_pose']['quaternion_wxyz'] for i in index]));residual=(gr*fk.inv()).magnitude()*180/np.pi
    first=lambda test:next((r['t'] for r in rows if r['t']>REF and test(r)),None)
    supportlost=first(lambda r:np.linalg.norm(r['environment_net_force_N'])<1e-8)
    unchanged=all(a['object_position_m']==b['object_position_m'] and a['command_q9']==b['command_q9'] for a,b in zip(data['grasp_hold_04']['rows'],rows) if a['t']<=REF)
    result=dict(schema='labsim.Env_v1.extract01_observational_control_analysis.v1',created_at=datetime.now().astimezone().isoformat(timespec='seconds'),scope='Read-only actual JSONL/H5 analysis, no rerun or source modification.',causation_confirmed=False,sources=sources,analysis_source_sha256=sha(Path(__file__)),reference_time_s=REF,comparison_preextract_exact_pose_and_command_match=unchanged,event_timeline=dict(first_bilateral_freeze_s=14.416666666666666,latch_s=14.516666666666667,extract_transition_s=REF,source_support_first_observed_zero_s=supportlost,command_joints_first_change_s=first(lambda r:np.linalg.norm(np.array(r['command_q9'])[:7]-np.array(ref['command_q9'])[:7])>1e-9),bottom_first_lift_over_10um_s=first(lambda r:r['source_bottom_z_m']>ref['source_bottom_z_m']+1e-5),termination_s=rows[-1]['t']),command_discontinuity=dict(frozen_total_opening_m=.012333333333333203,latched_total_opening_m=.012818814175487496,opening_increase_m=.000485480842154293,also_present_in_static_success=True,sole_failure_cause_established=False),force_windows=windows,orientation_onsets_deg_threshold=onsets,final_delta_rotation_vectors_deg={k:v[-1].tolist() for k,v in d['delta'].items()},final_object_world_tilt_deg=rows[-1]['tilt_deg'],bottom_lift_from_preextract_reference_m=rows[-1]['source_bottom_z_m']-ref['source_bottom_z_m'],source_clearance_m=rows[-1]['source_clearance_m'],IK=dict(recorded_orientation_tolerance_rad=.003,recorded_orientation_tolerance_deg=float(np.rad2deg(.003)),post15_35_target_to_FK_residual_range_deg=[float(residual[gt>=15.35].min()),float(residual[gt>=15.35].max())],cache_flag_warning='Then-source unchanged_goal_cached was literal true; only actual joints/FK changes establish command changes.'),independent_failure_type=d['result']['failure_type'],grasp_origin_vs_anchor_metrics=d['result']['grasp_relative_pose'],interpretation=['Static success is source-supported, not suspended holding: downward finger tangential preload plus source force balance gravity.','After support loss, finger vertical force carries approximately mg on average; gross missing vertical force is not established.','At0.05deg from extraction reference, cup/relative angle crosses before FK/actualhand. Later hand counterrotation and relative drift are observed; causal amplification remains a hypothesis.','Opening discontinuity occurs in both runs and does not identify a unique failure cause.'],single_factor_checks=['Continuous freeze-to-latch opening without increasing effort or friction.','Small physical lift and supported-to-suspended hold; in-rack quiet alone does not verify load transfer.','Fixed latched TCP orientation versus instantaneous relative-orientation feedback under unchanged physics and acceptance.'],method=dict(force_frame='world xyz,N,on cup; engineAPI with physics_dt',gravity='mass0.02kg engineering assumption times9.81m/s2',rotation='log(R_t R_reference^-1),deg; relR in hand basis; TCP/hand fixed orientation gives same delta magnitude',onset='observed stated-threshold crossing,not exact causal onset',plot_smoothing='force display only centered50ms boxcar12physics samples,nearestedge extension; raw data untouched'))
    (OUT/'extract01_control_analysis.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    plt.rcParams.update({'font.size':9,'axes.spines.top':False,'axes.spines.right':False})
    fig,axs=plt.subplots(3,2,figsize=(13,9.2),sharex=True,constrained_layout=True);ax=axs.ravel();smooth=lambda v:uniform_filter1d(v,12,axis=0,mode='nearest')
    for name,x in data.items():
        static=name=='grasp_hold_04';style='--' if static else '-';alpha=.6 if static else 1
        for key,color,label in [('opening','#3168a6','command'),('actualopening','#b44a23','measured')]:ax[0].plot(x['t'],x[key]*1e3,style,color=color,alpha=alpha,label=label+(' static' if static else ' extract'))
        if static:
            ax[2].plot(x['t'],smooth(x['env'][:,2]),'--',color='#178f9d',alpha=.6,label='rack Z static');ax[2].plot(x['t'],smooth(x['friction'].sum(1)[:,2]),'--',color='#b44a23',alpha=.6,label='finger friction Z static')
            ax[3].plot(x['t'],(x['bottom']-ref['source_bottom_z_m'])*1e3,'--',color='#888',label='cup bottom static')
    ax[0].set(title='A  Opening command jumps wider at latch',ylabel='Total opening (mm)',ylim=(12.,18.4));ax[0].legend(fontsize=7,ncol=2,loc='upper right')
    for i,col in enumerate(['#3168a6','#b44a23']):
        ax[1].plot(t,smooth(d['normal'][:,i,0]),color=col,label=f'finger{i+1} normal X');ax[1].plot(t,smooth(d['friction'][:,i,2]),':',color=col,label=f'finger{i+1} friction Z')
    ax[1].set(title='B  Finger force components on vessel',ylabel='Force (N)');ax[1].legend(fontsize=7,ncol=2,loc='upper right')
    for values,col,label in [(d['env'][:,2],'#178f9d','rack/environment Z'),(d['friction'].sum(1)[:,2],'#b44a23','finger friction Z'),((d['normal']+d['friction']).sum(1)[:,2]+d['env'][:,2],'#444','all contact Z')]:ax[2].plot(t,smooth(values),color=col,label=label)
    ax[2].axhline(.1962,color='black',lw=.8,ls=':',label='assumed mg=0.1962N');ax[2].set(title='C  Static hold remains rack-supported',ylabel='Vertical force (N)');ax[2].legend(fontsize=6.7,ncol=2,loc='upper right')
    ax[3].plot(t,(d['bottom']-ref['source_bottom_z_m'])*1e3,color='#188341',label='cup bottom')
    for key,col,label in [('actual_tcp_position_m','#b44a23','actual TCP'),('command_FK_TCP_pose','#3168a6','command FK TCP')]:
        values=np.array([r[key][2] if key=='actual_tcp_position_m' else r[key]['position_m'][2] for r in rows]);v0=ref[key][2] if key=='actual_tcp_position_m' else ref[key]['position_m'][2];ax[3].plot(t,(values-v0)*1e3,color=col,label=label)
    ax[3].set(title='D  Physical lift after source support loss',ylabel='Vertical change (mm)',ylim=(-.15,4.7));ax[3].legend(fontsize=7,ncol=2)
    for key,col,label in [('cupR','#188341','cup'),('handR','#b44a23','actual hand/TCP'),('fkR','#3168a6','command FK')]:ax[4].plot(t,d['delta'][key][:,0],color=col,label=label)
    ax[4].plot(gt,gd[:,0],':',color='#333',label='teacher goal');ax[4].set(title='E  Later hand rotation opposes cup rotation',ylabel='World X rotation delta (deg)');ax[4].legend(fontsize=7,ncol=2)
    for key,col,label in [('cupR','#188341','cup'),('handR','#b44a23','hand/TCP'),('relR','#7b3d99','cup relative to hand')]:ax[5].plot(t,np.linalg.norm(d['delta'][key],axis=1),color=col,label=label)
    ax[5].plot(gt,residual,':',color='#444',label='goal-to-FK residual');ax[5].axhline(np.rad2deg(.003),ls='--',lw=.7,color='#888',label='IK tolerance0.003rad');ax[5].set(title='F  Relative drift exceeds measured IK residual',ylabel='Rotation magnitude (deg)');ax[5].legend(fontsize=6.7,ncol=2,loc='upper left')
    for panel in ax:
        panel.set_xlim(14.2,15.8);panel.grid(alpha=.15)
        for event,style in [(14.4166667,':'),(14.5166667,':'),(REF,'--'),(supportlost,'-.')]:panel.axvline(event,color='#777',lw=.7,ls=style)
    for panel in ax[-2:]:panel.set_xlabel('Simulation time (s)')
    fig.suptitle('Actual extract01 versus static grasp04   Observed alignment is not causal proof\nDotted: freeze14.4167 / latch14.5167   Dashed: extract15.2667   Dash-dot: rack support loss15.3542',fontsize=11)
    fig.savefig(OUT/'extract01_control_alignment.png',dpi=190);plt.close(fig)
    print(json.dumps(dict(json=str(OUT/'extract01_control_analysis.json'),figure=str(OUT/'extract01_control_alignment.png'),source_files=len(sources),unchanged=unchanged,bottom_lift_mm=result['bottom_lift_from_preextract_reference_m']*1000)))

if __name__=='__main__':main()
