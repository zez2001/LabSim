import copy,itertools,json,shutil,tempfile,time
from pathlib import Path
from types import SimpleNamespace
import h5py,numpy as np
from omegaconf import OmegaConf
from demos.lab_cuvette_progress_v1.online import OnlineProgressSession
from demos.lab_cuvette_progress_v1.offline import analyze_episode,compare_progress
from demos.lab_cuvette_project_release_v1.recording import iter_jsonl
from demos.lab_cuvette_size_v1.scene import layout
root=Path.cwd()
source=root/'outputs/lab_cuvette_loading/Project_release_v1/same_process_collect_01/episode_0000'
package=Path(tempfile.mkdtemp(prefix='labsim-progress-full-online-replay-'))
online=package/'cpu_online_replay';online.mkdir();(online/'dataset').mkdir()
for name in ('config.yaml','physics_capture_meta.json','result.json','independent_score.json'):
 shutil.copy(source/name,online/name)
for stem in ('physics_records.jsonl','native_contact_events.jsonl'):
 p=source/stem;p=p if p.exists() else p.with_suffix(p.suffix+'.gz');(online/p.name).symlink_to(p)
h5_path=next((source/'dataset').glob('episode_*.h5'));(online/'dataset'/h5_path.name).symlink_to(h5_path)
cfg=OmegaConf.load(source/'config.yaml');cfg.progress={'enabled':True,'configuration':{}}
registry=json.loads((root/'assets/lab_cuvette_loading/Size_v1/registry.json').read_text())
bounds=np.asarray(registry['assets'][cfg.asset_id]['actual_body_bounds_m'])
result=json.loads((source/'result.json').read_text())
task=SimpleNamespace(cfg=cfg,base_cfg=cfg,episode_dir=online,episode_id=result['episode_id'],_result=result,_tick_trace=None,
 collector=SimpleNamespace(path=online/'dataset'/h5_path.name))
session=OnlineProgressSession(task,SimpleNamespace(layout=layout(cfg),vertices=bounds))
session.metadata['verification_kind']='CPU replay of real recorded raw data and recorded H5 commands; not a new simulation'
rows=iter(iter_jsonl(source/'physics_records.jsonl'));pending=next(rows,None);started=time.perf_counter()
with h5py.File(h5_path,'r') as h:
 for i,(before,after) in enumerate(zip(h['timestamp'],h['next_timestamp'])):
  action=json.loads(h['actions_raw_json'][i]);task._tick_trace=dict(action=action)
  while pending is not None and pending['t']<=float(after)+1e-8:
   if pending['t']<=float(before):task._tick_trace=None
   else:task._tick_trace=dict(action=action)
   session.physical(pending);pending=next(rows,None)
  session.transition({'simulation_time':float(before),'step_index':int(h['obs_step'][i])},{'raw_output':action},
   {'simulation_time':float(after),'step_index':int(h['next_obs_step'][i])},{'reward':float(h['reward'][i]),'terminated':bool(h['done'][i]),'truncated':False})
  if i%1500==0: print('ONLINE_REPLAY',i,session.physics_count,'seconds',round(time.perf_counter()-started,2),flush=True)
 while pending is not None:
  task._tick_trace=None;session.physical(pending);pending=next(rows,None)
summary=session.finalize({'termination_reason':result['termination_reason'],'failure_type':result['failure_type']},result)
assert not session.errors,session.errors
assert session.writer.status=='complete'
print('ONLINE_COMPLETE',package,summary['recording'],flush=True)
replay=analyze_episode(online,package/'offline_replay',make_report=False)
print('OFFLINE_COMPLETE',flush=True)
comparison=compare_progress(online,package/'offline_replay',package/'comparison.json')
print('COMPARE',json.dumps(comparison,ensure_ascii=False),flush=True)
