"""Small native reset/purpose check; source H5 and labels are read-only."""
import argparse,json,hashlib
from pathlib import Path
import h5py
from demos.lab_cuvette_project_release_v1.dataset_index import build_index
p=argparse.ArgumentParser();p.add_argument('run',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args();r=a.run.resolve();o=a.output.resolve();o.mkdir(parents=True,exist_ok=False)
def load(p):return json.loads(p.read_text())
def save(n,v):(o/n).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
proof=load(r/'process_exit.json');m=load(r/'run_manifest.json');checks=load(r/'reset_checks.json')
assert proof['exit_code']==0 and proof['process_exited'] and m['episodes_completed']==2
assert all(not Path('/proc',str(pid)).exists() for pid in (proof['pid'],m['process_id']))
assert checks[1]['prior_episode_rejected'] is True and checks[1]['stale_probe_executed_ticks']==0
ids=[];rows=[]
for h in sorted(r.glob('episode_*/dataset/episode_*.h5')):
 with h5py.File(h) as f:
  result=load(h.parent.parent/'result.json');purpose=str(f.attrs['record_purpose']);identity=str(f.attrs['episode_id']);ids.append(identity)
  assert purpose=='lifecycle_diagnostic' and f.attrs['publication_state']=='complete'
  assert result['record_valid'] is True and result['task_success'] is False
  assert result['post_retreat_window']['status']=='unavailable' and result['stable_after_retreat'] is None
  rows.append(dict(episode_id=identity,purpose=purpose,frames=len(f['timestamp']),task_success=False,record_valid=True,post_retreat_window='unavailable',stable_after_retreat=None,source_sha256=hashlib.sha256(h.read_bytes()).hexdigest()))
assert len(ids)==len(set(ids))==2
index=build_index(r,r/'index/lifecycle.hdf5',purpose='lifecycle_diagnostic')
policy=build_index(r,r/'index/policy_evaluation.hdf5',purpose='policy_evaluation')
assert index['counts']['all_valid']==2 and policy['counts']['all_valid']==0
save('summary.json',dict(schema='labsim.Internal_use_v1.reset_closed.v1',runtime_commit=m['code_commit'],same_native_process=True,processes_exited=True,episodes=rows,unique_episode_ids=True,old_action_rejected_zero_steps=True,diagnostic_counts=index['counts'],formal_policy_counts=policy['counts']))
for name in ['run_manifest.json','process_exit.json','reset_checks.json','application_shutdown.json']:save(name,load(r/name))
save('lifecycle.index.json',index);save('policy_evaluation.index.json',policy)
print(json.dumps(dict(diagnostic=index['counts'],policy=policy['counts']),indent=2))
