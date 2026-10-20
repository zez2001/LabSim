"""CPU-only observational comparison of retained extraction trials."""
import json,hashlib
from pathlib import Path
from datetime import datetime
import numpy as np
from scipy.spatial.transform import Rotation as R
from scipy.ndimage import uniform_filter1d
from omegaconf import OmegaConf
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parents[4];BASE=ROOT/'outputs/lab_cuvette_loading/Env_v1';OUT=ROOT/'docs/lab_cuvette_loading/Env_v1/data'
NAMES=['extract_transport_01','extract_fixed_orientation_01']
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def rotation(q):return R.from_quat(np.roll(q,-1,axis=-1))
def leaves(a,b,path=''):
    if isinstance(a,dict) and isinstance(b,dict):
        for k in set(a)|set(b):yield from leaves(a.get(k),b.get(k),path+'/'+str(k))
    elif isinstance(a,list) and isinstance(b,list) and len(a)==len(b):
        for i,(v,w) in enumerate(zip(a,b)):yield from leaves(v,w,path+'/'+str(i))
    elif a!=b:yield path,a,b
def main():
    data={};sources=[]
    for n in NAMES:
        p=BASE/n/'episode_0000';r=[json.loads(s) for s in (p/'physics_records.jsonl').read_text().splitlines()]
        e=json.loads((p/'teacher_events.json').read_text());score=json.loads((p/'result.json').read_text());cfg=OmegaConf.to_container(OmegaConf.load(p/'config.yaml'),resolve=True)
        start=next(x['t'] for x in e if x.get('target')=='EXTRACT');index=next(i for i,x in enumerate(r) if abs(x['t']-start)<1e-8)
        d=dict(rows=r,events=e,score=score,cfg=cfg,start=start,index=index,t=np.array([x['t'] for x in r]))
        for k,f in [('cupR','object_quaternion_wxyz'),('handR','actual_tcp_quaternion_wxyz'),('relR','cup_in_hand_quaternion_wxyz')]:
            rotations=rotation(np.array([x[f] for x in r]));d[k]=(rotations*rotations[index].inv()).magnitude()*180/np.pi
        d['normal']=np.array([x['finger_normal_force_on_cup_N'] for x in r]);d['friction']=np.array([x['finger_friction_force_on_cup_N'] for x in r]);d['env']=np.array([x['environment_net_force_N'] for x in r]);
        positions=np.array([x['cup_in_hand_position_m'] for x in r]);d['relative_mm']=np.linalg.norm(positions-positions[index],axis=1)*1e3
        rq=rotation(np.array([x['cup_in_hand_quaternion_wxyz'] for x in r]));anchors=positions+rq.apply([0,0,.053]);d['anchor_mm']=np.linalg.norm(anchors-anchors[index],axis=1)*1e3
        d['bottom_mm']=(np.array([x['source_bottom_z_m'] for x in r])-r[index]['source_bottom_z_m'])*1e3;data[n]=d
        for rel in ['physics_records.jsonl','result.json','teacher_events.json','config.yaml']:
            f=p/rel;sources.append(dict(path=str(f.relative_to(ROOT)),sha256=sha(f),bytes=f.stat().st_size))
    A,B=(data[n] for n in NAMES);cut=min(A['start'],B['start']);pairs=[(a,b) for a,b in zip(A['rows'],B['rows']) if a['t']<=cut+1e-9]
    diffs={};excluded=['engine_time']
    for a,b in pairs:
        for k in set(a)|set(b):
            if k in excluded or k.startswith('camera'):continue
            if a.get(k)==b.get(k):continue
            item=diffs.setdefault(k,dict(samples_differ=0,first_t_s=a['t'],max_numeric_absolute_difference=0.,numeric_leaf_paths=[]));item['samples_differ']+=1
            for path,x,y in leaves(a.get(k),b.get(k)):
                if isinstance(x,(float,int)) and isinstance(y,(float,int)):
                    delta=abs(x-y)
                    if delta>item['max_numeric_absolute_difference']:item['max_numeric_absolute_difference']=delta
                    if path not in item['numeric_leaf_paths']:item['numeric_leaf_paths'].append(path)
    physical_keys=['object_position_m','object_quaternion_wxyz','source_bottom_z_m','actual_tcp_position_m','actual_tcp_quaternion_wxyz','joints9','joint_velocities9','linear_velocity_native_m_s','angular_velocity_native_rad_s','command_q9','command_FK_hand_pose','command_FK_TCP_pose','environment_net_force_N']
    exact={k:all(a.get(k)==b.get(k) for a,b in pairs) for k in physical_keys}
    config_equal={k:A['cfg'].get(k)==B['cfg'].get(k) for k in ['physics','vessel','robot','source','rack','adapter','scene','gripper']}
    summaries=[]
    for name,d in data.items():
        w=(d['t']>=d['start']);score=d['score'];last=d['rows'][-1]
        summaries.append(dict(run=name,extract_start_s=d['start'],termination_s=score['simulation_seconds'],failure_type=score['failure_type'],task_success=score['task_success'],source_slot_cleared=score['source_slot_cleared'],transport_success=score['transport_success'],actual_lift_from_extract_start_m=float(d['bottom_mm'][-1]/1000),source_clearance_m=last['source_clearance_m'],final_tilt_deg=last['tilt_deg'],final_delta_world_cup_rotation_deg=float(d['cupR'][-1]),final_delta_hand_rotation_deg=float(d['handR'][-1]),final_delta_relative_rotation_deg=float(d['relR'][-1]),score_grasp_relative_pose=score['grasp_relative_pose'],maximum_finger_normal_N=np.linalg.norm(d['normal'][w],axis=2).max(0).tolist(),mean_finger_normal_world_N=d['normal'][w].mean(0).tolist(),mean_finger_friction_world_N=d['friction'][w].mean(0).tolist(),mean_environment_force_world_N=d['env'][w].mean(0).tolist(),drop_label_observed=score['failure_type']=='DROPPED',retreat_observed=score['retreat_observed']))
    renderer=OUT/'extract_fixed01_inspection/renderer_USD_sync_audit.json'
    if renderer.exists():sources.append(dict(path=str(renderer.relative_to(ROOT)),sha256=sha(renderer),bytes=renderer.stat().st_size))
    result=dict(schema='labsim.Env_v1.extract_fixed01_control_comparison.v1',created_at=datetime.now().astimezone().isoformat(timespec='seconds'),sources=sources,analysis_source_sha256=sha(Path(__file__)),raw_inputs_modified=False,physics_started_by_analysis=False,causal_unique_cause_established=False,prefix=dict(end_time_s=cut,samples=len(pairs),excluded_fields=excluded,physical_state_and_command_exact_by_field=exact,all_selected_physical_state_and_command_exact=all(exact.values()),all_recorded_nonclock_fields_exact=not diffs,contact_rounding_differences=diffs,interpretation='Stored kinematics, velocities, actual command/FK and environment force match exactly before EXTRACT. Finger aggregate/detail forces differ only by observed float roundoff, not a newly chosen acceptance threshold.'),physical_config_equal=config_equal,changed_control_factor='Disable active orientation feedback only during EXTRACT; later-phase feedback retained.',independent_renderer_change='Official zero_delay rendering settings also changed; prefix evidence supports unchanged observed pre-EXTRACT motion. This is not byte-identical all contact data or a global renderer-independence proof.',runs=summaries,conclusion='Both trials fail GRASP_SLIP before clearing the source. Removing EXTRACT active rotation feedback alone does not solve extraction; it cannot be the sole necessary cause. The shared freeze-to-latch opening discontinuity remains a separate, testable factor.',limits=['Two deterministic matched-prefix trials are not a success-probability estimate.','The post-EXTRACT contact response differs by intended motion feedback and outcome; force differences do not by themselves identify a unique mechanism.','Native original-seat loading remains geometry-blocked.','Fixed01 render-state association is separately checked by dataset audit, not a claim of real optical calibration.'])
    (OUT/'extract_fixed01_control_comparison.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    plt.rcParams.update({'font.size':9,'axes.spines.top':False,'axes.spines.right':False})
    fig,axs=plt.subplots(3,2,figsize=(12.8,9),sharex=True,constrained_layout=True);ax=axs.ravel();sm=lambda x:uniform_filter1d(x,12,axis=0,mode='nearest')
    for name,d in data.items():
        ls='-' if name==NAMES[0] else '--';suffix='feedback' if name==NAMES[0] else 'fixed';t=d['t']
        ax[0].plot(t,d['bottom_mm'],ls,color='#188341',label='cup '+suffix)
        q=np.array([r['actual_tcp_position_m'][2] for r in d['rows']]);ax[0].plot(t,(q-q[d['index']])*1e3,ls,color='#b44a23',label='TCP '+suffix)
        ax[1].plot(t,d['relative_mm'],ls,color='#7030a0',label='bottom origin '+suffix);ax[1].plot(t,d['anchor_mm'],ls,color='#3168a6',label='53mm anchor '+suffix)
        ax[2].plot(t,d['cupR'],ls,color='#188341',label='cup '+suffix);ax[2].plot(t,d['handR'],ls,color='#b44a23',label='hand '+suffix)
        ax[3].plot(t,sm(d['env'][:,2]),ls,color='#178f9d',label='rack Z '+suffix);ax[3].plot(t,sm(d['friction'].sum(1)[:,2]),ls,color='#b44a23',label='finger friction Z '+suffix)
        for i,color in enumerate(['#3168a6','#b44a23']):ax[4].plot(t,sm(np.linalg.norm(d['normal'][:,i],axis=1)),ls,color=color,label=f'finger{i+1} '+suffix)
        ax[5].plot(t,np.array([2*r['gripper_target_m'] for r in d['rows']])*1e3,ls,color='#3168a6',label='command '+suffix);ax[5].plot(t,np.array([sum(r['finger_joint_positions_m']) for r in d['rows']])*1e3,ls,color='#b44a23',label='actual '+suffix)
    settings=[('A  Both stop before clearing source','Vertical change (mm)',(-.05,4.7)),('B  Body origin versus grasp-height anchor','Relative displacement (mm)',(-.03,1.8)),('C  Fixed hand does not prevent cup rotation','Rotation from EXTRACT start (deg)',(-.03,2.1)),('D  Physical load transfer','Force (N)',(-.4,.6)),('E  Finger normal load magnitude','Force (N)',(.20,.42)),('F  Both retain same latch opening jump','Total opening (mm)',(12.7,13.2))]
    for panel,(title,label,ylim) in zip(ax,settings):
        panel.set(title=title,ylabel=label,ylim=ylim,xlim=(15.24,15.8));panel.grid(alpha=.15);panel.axvline(cut,color='#888',lw=.7,ls=':');panel.legend(fontsize=7,ncol=2)
    ax[3].axhline(.1962,color='#333',ls=':',lw=.8)
    for panel in ax[-2:]:panel.set_xlabel('Simulation time (s)')
    fig.suptitle('Actual extraction comparison  Solid: feedback01  Dashed: fixed01\nMatched state and command prefix; contact-force float differences retained; no unique causal claim',fontsize=11)
    fig.savefig(OUT/'extract_fixed01_control_comparison.png',dpi=180);plt.close(fig)
    print(json.dumps(dict(prefix_exact=all(exact.values()),contact_difference_keys=list(diffs),configs_equal=config_equal,runs=[(r['run'],r['actual_lift_from_extract_start_m'],r['failure_type']) for r in summaries])))
if __name__=='__main__':main()
