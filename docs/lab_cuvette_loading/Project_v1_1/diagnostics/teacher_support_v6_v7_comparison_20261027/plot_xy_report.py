"""Wide single-panel companion; original three-panel figure stays immutable."""
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
D=R/'docs/lab_cuvette_loading/Project_v1_1/diagnostics';specs=[dict(label='v6: TASK_INCOMPLETE',color='#c26b25',summary=D/'teacher_baseline_close_01_support_gate_audit/summary.json',csv=D/'teacher_baseline_close_01_support_gate_audit/baseline_support_release_control_boundaries.csv'),dict(label='v7: SUCCESS',color='#12649a',summary=D/'teacher_support_align_01_support_portability_audit/summary.json',csv=D/'teacher_support_align_01_support_portability_audit/support_release_physics_control_boundaries.csv')];sources=[];series=[]
for s in specs:
 j=json.loads(s['summary'].read_text());v=j['runs'][0] if 'runs' in j else j;ph=v.get('teacher_phase_transition_times_s') or v['phase_times_s'];t0=ph['SUPPORT_TRANSFER'];points=[]
 for row in csv.DictReader(s['csv'].open()):
  t=float(row['t'])-t0
  if t>=-1e-9 and t<=5.15:points.append((t,float(row['xy_error_norm_m'])*1e6))
 a=np.asarray(points);assert len(a)>0 and np.all(np.diff(a[:,0])>0);e=v.get('first_qualifying_samples',{}).get('correct_target_supported');event=None if e is None else dict(relative_t_s=e['t']-t0,actual_t_s=e['t'],xy_um=e['xy_error_norm_m']*1e6);series.append(dict(spec=s,data=a,support_start_t_s=t0,actual_OPEN_t_s=ph['OPEN'],relative_OPEN_t_s=ph['OPEN']-t0,event=event))
 for p in (s['summary'],s['csv']):sources.append(dict(path=str(p.relative_to(R)),bytes=p.stat().st_size,SHA256=sha(p)))
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':14,'axes.labelsize':14,'xtick.labelsize':14,'ytick.labelsize':14,'legend.fontsize':14,'axes.spines.top':False,'axes.spines.right':False,'savefig.facecolor':'white'})
fig,ax=plt.subplots(figsize=(8,3));fig.subplots_adjust(left=.12,right=.99,bottom=.22,top=.76)
for s in series:
 ax.plot(s['data'][:,0],s['data'][:,1],lw=1.55,color=s['spec']['color']);ax.axvline(s['relative_OPEN_t_s'],color=s['spec']['color'],ls='--',lw=1.25)
 short=s['spec']['label'].split(':')[0];ax.text(s['relative_OPEN_t_s'],1.035,f"{short} OPEN +{s['relative_OPEN_t_s']:.3f} s",transform=ax.get_xaxis_transform(),ha='center',va='bottom',fontsize=14,color=s['spec']['color'],clip_on=False)
 if s['event']:
  e=s['event'];ax.scatter([e['relative_t_s']],[e['xy_um']],s=65,marker='D',facecolor=s['spec']['color'],edgecolor='white',linewidth=.8,zorder=5)
ax.axhline(100,color='#333333',ls=':',lw=1.2);ax.text(.06,104,'100 µm gate',ha='left',va='bottom',fontsize=14,color='#333333',bbox=dict(facecolor='white',edgecolor='none',alpha=.9,pad=1))
ax.set_xlim(0,5.15);ax.set_ylim(bottom=0);ax.grid(axis='y',color='#e8e8e8',lw=.7);ax.set_xlabel('Actual time since each SUPPORT start (s)');ax.set_ylabel('Actual XY error (µm)')
handles=[Line2D([0],[0],color=s['spec']['color'],lw=1.8,label=s['spec']['label']) for s in series]+[Line2D([0],[0],marker='D',color='#12649a',lw=0,markersize=6,label='Support event (v7)')];fig.legend(handles=handles,loc='upper left',bbox_to_anchor=(.065,.995),ncol=3,frameon=False,handlelength=1.5,columnspacing=.9,borderaxespad=0)
png=O/'teacher_v6_v7_XY_report.png';assert not png.exists();fig.savefig(png,dpi=200);plt.close(fig)
out=dict(schema='labsim.Project_v1_1.report_XY_companion_figure.v1',analysis_date_local='2026-10-27',sources=sources,original_three_panel_companion=dict(path=str((Path(__file__).resolve().parent/'teacher_v6_v7_support_gate_comparison.png').relative_to(R)),SHA256=sha(Path(__file__).resolve().parent/'teacher_v6_v7_support_gate_comparison.png')),figure=dict(path=png.name,SHA256=sha(png),bytes=png.stat().st_size,width_px=1600,height_px=600,minimum_authored_font_pt=14),series=[dict(label=s['spec']['label'],original_support_start_t_s=s['support_start_t_s'],actual_OPEN_t_s=s['actual_OPEN_t_s'],relative_OPEN_t_s=s['relative_OPEN_t_s'],independent_correct_target_supported=s['event'],native_control_boundary_sample_count=len(s['data'])) for s in series],semantics='Same closed CSV samples as immutable three-panel figure, independent original timestamps minus each SUPPORT start; no interpolation/resampling/paired duration assumption. Support diamond is exact original independent240Hz event, not a teacher-phase success label.',plot_range_relative_s=[0,5.15],original_XY_gate_m=.0001,tilt_and_floor_support_retained_in_three_panel_CSV_and_summary=True,script=dict(path=str(Path(__file__).relative_to(R)),SHA256=sha(Path(__file__))),reproduction_command='/home/wujing/Desktop/vla/labutopia-env/bin/python docs/lab_cuvette_loading/Project_v1_1/diagnostics/teacher_support_v6_v7_comparison_20261027/plot_xy_report.py --repo-root /home/wujing/Desktop/vla/LabSim --output-dir /tmp/labsim-support-XY-report-reproduction',visual_QA_completed=False,original_three_panel_image_or_manifests_modified=False,GPU_used=False,API_calls=0)
(O/'XY_report_figure_receipt.json').open('x').write(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(json.dumps(out['figure']))
