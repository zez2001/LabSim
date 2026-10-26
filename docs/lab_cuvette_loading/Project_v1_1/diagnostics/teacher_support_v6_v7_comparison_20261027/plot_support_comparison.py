"""Plot closed v6/v7 records without resampling or label changes."""
from pathlib import Path
import argparse,csv,hashlib,json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

ap=argparse.ArgumentParser();ap.add_argument('--repo-root',type=Path,default=Path.cwd());ap.add_argument('--output-dir',type=Path,default=Path(__file__).resolve().parent);args=ap.parse_args();R=args.repo_root.resolve();O=args.output_dir.resolve();O.mkdir(parents=True,exist_ok=True)
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(4<<20),b''):h.update(b)
 return h.hexdigest()
D=R/'docs/lab_cuvette_loading/Project_v1_1/diagnostics'
specs=[dict(label='v6: TASK_INCOMPLETE',color='#c26b25',summary=D/'teacher_baseline_close_01_support_gate_audit/summary.json',csv=D/'teacher_baseline_close_01_support_gate_audit/baseline_support_release_control_boundaries.csv'),dict(label='v7: SUCCESS',color='#12649a',summary=D/'teacher_support_align_01_support_portability_audit/summary.json',csv=D/'teacher_support_align_01_support_portability_audit/support_release_physics_control_boundaries.csv')]
sources=[];series=[]
for s in specs:
 j=json.loads(s['summary'].read_text());v=j['runs'][0] if 'runs' in j else j;t0=(v.get('teacher_phase_transition_times_s') or v['phase_times_s'])['SUPPORT_TRANSFER'];op=(v.get('teacher_phase_transition_times_s') or v['phase_times_s'])['OPEN'];rows=list(csv.DictReader(s['csv'].open()));points=[]
 for row in rows:
  t=float(row['t'])-t0
  if t>=-1e-9 and t<=5.15:points.append((t,float(row['xy_error_norm_m'])*1e6,float(row['tilt_deg']),float(row['target_bottom_support_N'])))
 a=np.asarray(points);assert a.shape[0]>0 and np.all(np.diff(a[:,0])>0)
 event=(v.get('first_qualifying_samples') or {}).get('correct_target_supported');e=None if event is None else dict(relative_t_s=event['t']-t0,xy_um=event['xy_error_norm_m']*1e6,tilt_deg=event['tilt_deg'],support_N=event['target_bottom_support_N'])
 series.append(dict(spec=s,data=a,support_start_t_s=t0,OPEN_t_s=op,relative_OPEN_t_s=op-t0,correct_supported=e,original_task_success=v.get('original_task_success',v.get('original_result',{}).get('task_success'))))
 for p in (s['summary'],s['csv']):sources.append(dict(path=str(p.relative_to(R)),SHA256=sha(p),bytes=p.stat().st_size))
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':9,'axes.titlesize':10,'axes.labelsize':9,'legend.fontsize':8.5,'axes.spines.top':False,'axes.spines.right':False,'savefig.facecolor':'white'})
fig,axes=plt.subplots(3,1,figsize=(7.0,6.4),sharex=True);fig.subplots_adjust(left=.12,right=.985,bottom=.08,top=.855,hspace=.13)
panels=[(1,'Actual XY error (µm)',100.,'Original gate: 100 µm'),(2,'Actual tilt (°)',.15,'Original gate: 0.15°'),(3,'Classified floor support (N)',.1,'Original gate: 0.1 N')]
for ax,(col,label,gate,gate_label) in zip(axes,panels):
 for s in series:
  a=s['data'];c=s['spec']['color'];ax.plot(a[:,0],a[:,col],lw=1.15,color=c,label=s['spec']['label']);ax.axvline(s['relative_OPEN_t_s'],color=c,ls='--',lw=.9,alpha=.9)
  if s['correct_supported'] is not None:
   e=s['correct_supported'];value=e[['','xy_um','tilt_deg','support_N'][col]];ax.scatter([e['relative_t_s']],[value],s=27,marker='D',facecolor=c,edgecolor='white',linewidth=.7,zorder=5)
 ax.axhline(gate,color='#333333',ls=':',lw=1.,zorder=0);ax.set_ylabel(label);ax.grid(axis='y',color='#e7e7e7',lw=.6);ax.set_xlim(0,5.15);ax.set_ylim(bottom=0);ax.text(5.1,gate,gate_label,ha='right',va='bottom',fontsize=8,color='#333333',bbox=dict(facecolor='white',edgecolor='none',alpha=.85,pad=1.5))
axes[-1].axhline(.1962,color='#777777',ls='-.',lw=.8,zorder=0);axes[-1].text(.04,.1962,'Weight reference: 0.1962 N',ha='left',va='bottom',fontsize=8,color='#666666',bbox=dict(facecolor='white',edgecolor='none',alpha=.85,pad=1.5))
handles=[Line2D([0],[0],color=s['spec']['color'],lw=1.5,label=s['spec']['label']) for s in series]+[Line2D([0],[0],color='#555555',ls='--',lw=.9,label='Actual OPEN (each run)'),Line2D([0],[0],marker='D',color='#12649a',lw=0,markersize=5,label='correct_target_supported (v7)')]
fig.legend(handles=handles,loc='upper left',bbox_to_anchor=(.12,.952),frameon=False,ncol=2,borderaxespad=0,columnspacing=1.5)
for s in series:axes[0].text(s['relative_OPEN_t_s']+.045,.38 if s['spec']['label'].startswith('v6') else .58,s['spec']['label'].split(':')[0]+' OPEN\n'+f"{s['relative_OPEN_t_s']:.3f} s",transform=axes[0].get_xaxis_transform(),fontsize=8,color=s['spec']['color'],va='center',bbox=dict(facecolor='white',edgecolor='none',alpha=.8,pad=1.5))
axes[-1].set_xlabel('Actual simulation time since each SUPPORT_TRANSFER start (s)')
fig.suptitle('Closed teacher v6 / v7: alignment and physical support',x=.12,y=.99,ha='left',fontsize=12,fontweight='bold')
png=O/'teacher_v6_v7_support_gate_comparison.png';assert not png.exists();fig.savefig(png,dpi=220);plt.close(fig)
metadata=dict(schema='labsim.Project_v1_1.closed_v6_v7_support_figure.v1',analysis_date_local='2026-10-27',sources=sources,plotted_records=[dict(label=s['spec']['label'],support_start_t_s=s['support_start_t_s'],OPEN_t_s=s['OPEN_t_s'],relative_OPEN_t_s=s['relative_OPEN_t_s'],plotted_native_control_boundary_samples=len(s['data']),correct_target_supported_original_physical_sample=s['correct_supported'],original_task_success=s['original_task_success']) for s in series],alignment='Subtract each run original SUPPORT_TRANSFER transition only; each curve retains own recorded timestamps. No resampling, time warping, common-duration assumption or paired-sample inference.',correct_event_marker='Original independently derived physical sample, may lie between plotted control-boundary samples; teacher phase is only an axis origin, not success proof.',original_gates_preserved=dict(XY_m=.0001,tilt_deg=.15,classified_floor_support_N=.1,weight_reference_N=.1962),plot_range_relative_s=[0,5.15],figure=dict(path=png.name,SHA256=sha(png),bytes=png.stat().st_size),script=dict(path=str(Path(__file__).relative_to(R)),SHA256=sha(Path(__file__))),reproduction_command='/home/wujing/Desktop/vla/labutopia-env/bin/python docs/lab_cuvette_loading/Project_v1_1/diagnostics/teacher_support_v6_v7_comparison_20261027/plot_support_comparison.py --repo-root /home/wujing/Desktop/vla/LabSim --output-dir /tmp/labsim-support-comparison-reproduction',GPU_used=False,API_calls=0,original_data_labels_or_runtime_modified=False,visual_QA_completed=False)
(O/'figure_source_manifest.json').open('x').write(json.dumps(metadata,ensure_ascii=False,indent=2)+'\n');print(json.dumps(metadata['figure']))
