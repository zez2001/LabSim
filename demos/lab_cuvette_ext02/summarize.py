"""Independent final scoring and CSV export of ALL ext02 support attempts."""
from pathlib import Path
import json,csv
import numpy as np
from omegaconf import OmegaConf
from demos.lab_cuvette_ext02.build import ROOT
from demos.lab_cuvette_ext02.support import measure
from demos.lab_cuvette_external.run import write

def summarize():
 base=ROOT/'outputs/lab_cuvette_loading/V0_ext02';doc=ROOT/'docs/lab_cuvette_loading/V0_ext02';doc.mkdir(exist_ok=True);cfg=OmegaConf.load(ROOT/'config/lab_cuvette_loading/V0_ext02.yaml');summaries=[]
 for path in sorted(base.rglob('result.json')):
  p=path.parent
  if not (p/'physics_records.json').exists() or not (p/'support.h5').exists():continue
  local_cfg=OmegaConf.load(p/'config.yaml')
  raw=json.load(open(path));rows=json.load(open(p/'physics_records.json'));score=measure(rows,local_cfg);geo=json.load(open(p/'geometry_audit.json')) if (p/'geometry_audit.json').exists() else None;runtime=json.load(open(p/'runtime.json'));native=runtime['physics_stats'];native_count=native['numConvexShapes']+native['numTriMeshShapes'];kind='cooking-query point-to-triangle'
  if (p/'native_triangle_probe.json').exists():
   probe=json.load(open(p/'native_triangle_probe.json'));kind='native source-face-centroid directional sampling (not full cooked mesh export)'
   if not probe['missing_samples']:geo=dict(observed_support_error_m=probe['observed_directional_surface_distance_m'])
  qualified=bool(score['static_pass'] and geo and geo['observed_support_error_m']<=local_cfg.acceptance.support_geometry_m and native_count>0)
  counts={};first_contact=None
  if (p/'native_contact_events.json').exists():
   events=json.load(open(p/'native_contact_events.json'))
   for e in events:
    if not e['points']:continue
    key=e['collider0']+' <-> '+e['collider1'];counts[key]=counts.get(key,0)+len(e['points'])
    if first_contact is None:first_contact=e
  for r in rows:
   if not np.isfinite(np.r_[r['position'],r['quaternion'],r['linear_velocity'],r['angular_velocity']]).all():raise ValueError('Nonfinite state')
  item=dict(run=str(p.relative_to(base)),scheme=raw['scheme'],**score,observed_query_support_error_m=geo['observed_support_error_m'] if geo else None,C_complete_native_export=False,native_convex_count=native['numConvexShapes'],native_trimesh_count=native['numTriMeshShapes'],support_qualified=qualified,status='PHYSICS_INVALID' if native_count==0 else 'GEOMETRY_OR_NATIVE_REPRESENTATION_GATE_BLOCKED',full_success=False,tabletop_executed=False,wall_seconds=raw['wall_seconds'],physics_steps=len(rows)-1,simulation_seconds=rows[-1]['t'],first_contact=first_contact,contact_shape_counts=counts,source_penetration_early_max_m=max(r['source_penetration_m'] for r in rows if r['t']<1.),initial_z_m=rows[0]['position'][2],initial_v_m_s=rows[0]['linear_velocity'])
  item.update(geometry_measurement=kind,physics_hz=local_cfg.physics.hz,solver_velocity_iterations_authored=local_cfg.physics.velocity_iterations)
  if qualified:item['status']='SUPPORT_OBSERVED_GATES_PASS'
  write(p/'independent_score.json',item);summaries.append(item)
  with (p/'states.csv').open('w') as fp:
   writer=csv.writer(fp);writer.writerow(['time_s','x_m','y_m','z_m','qw','qx','qy','qz','vx_m_s','vy_m_s','vz_m_s','wx_rad_s','wy_rad_s','wz_rad_s','source_penetration_m','source_gap_m','support_fx_N','support_fy_N','support_fz_N'])
   for r in rows:writer.writerow([r['t'],*r['position'],*r['quaternion'],*r['linear_velocity'],*r['angular_velocity'],r['source_penetration_m'],r['source_bottom_gap_m'],*r['support_force_vector_N']])
  import h5py
  with h5py.File(p/'support.h5','r') as f:
   assert len(f['t'])==len(rows) and np.allclose(np.diff(f['t'][:]),1/local_cfg.physics.hz)
   assert not f.attrs['full_success'] and not f.attrs['full_task_eligible']
 tables=[]
 for p in sorted(base.glob('table*/trial_*/result.json')):
  result=json.load(open(p));tables.append(dict(path=str(p.relative_to(base)),**result))
 write(base/'summary.json',dict(schema='labsim.V0_ext02.support_summary.v1',attempts=summaries,tabletop_results=tables,full_task_executed=False,tabletop_attempts=len(tables),tabletop_successes=sum(bool(t.get('diagnostic_success')) for t in tables),fixed_five_trials_executed=(base/'table_repeat05/results.json').exists(),stop_reason=None if any(s['support_qualified'] for s in summaries) else 'support gate remains blocked',full_task_training_index=[]))
 columns=['run','scheme','static_pass','source_penetration_m','position_drift_m','orientation_change_deg','max_linear_speed_m_s','max_angular_speed_rad_s','observed_query_support_error_m','native_convex_count','native_trimesh_count','support_qualified','wall_seconds']
 with (doc/'comparison.csv').open('w') as fp:
  writer=csv.DictWriter(fp,fieldnames=columns,extrasaction='ignore');writer.writeheader();writer.writerows(summaries)
 import matplotlib;matplotlib.use('Agg')
 import matplotlib.pyplot as plt
 selected=[s for s in summaries if s['run'] in ['final_repro01/control193','final_repro01/walls28_mm','support02/sdf_cpu']]
 fig,axs=plt.subplots(3,1,figsize=(10,9),sharex=True)
 for s in selected:
  rows=json.load(open(base/s['run']/'physics_records.json'));t=np.array([r['t'] for r in rows]);p=np.array([r['position'] for r in rows]);q=np.array([r['quaternion'] for r in rows],dtype=float);q/=np.linalg.norm(q,axis=1)[:,None];tilt=np.degrees(np.arccos(np.clip(1-2*(q[:,1]**2+q[:,2]**2),-1,1)))
  axs[0].plot(t,np.array([r['source_penetration_m'] for r in rows])*1000,label=s['scheme']);axs[1].plot(t,tilt,label=s['scheme']);axs[2].plot(t,[r['support_force_vector_N'][2] for r in rows],label=s['scheme'])
 axs[0].axhline(.05,color='black',ls='--',label='0.05 mm fixed gate');axs[0].set_ylabel('Source penetration (mm)');axs[1].set_ylabel('Tilt (deg)');axs[2].set_ylabel('Table support Fz (N)');axs[2].set_xlabel('Recorded simulation time (s)')
 for ax in axs:ax.grid(alpha=.2);ax.legend(fontsize=8)
 fig.suptitle('240 Hz CPU PhysX, 60 Hz recording; equal source / mass / material / initial pose');fig.tight_layout();fig.savefig(doc/'support_comparison.png',dpi=160)
 print('SUMMARIZED',len(summaries),'support runs; none authorises full task training')
if __name__=='__main__':summarize()
