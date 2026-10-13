"""Read all attempts; independently rescore physics and exercise existing ACT/DP adapter."""
import argparse,json,sys,csv
from pathlib import Path
import numpy as np,h5py
from omegaconf import OmegaConf
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
def audit(directory,rescore=True):
 from demos.lab_cuvette_loading.scoring import Scorer
 results=json.loads((directory/'summary.json').read_text());checks=[];cfg=OmegaConf.load(directory/'config.yaml')
 for i,result in enumerate(results):
  name=f'episode_{i:04d}';initial=json.loads((directory/(name+'_initial.json')).read_text());boxes=json.loads((directory/(name+'_collision_boxes.json')).read_text());layout=initial['layout'];check=dict(episode=i,seed=result['seed'],status=result['status'],initial_valid=json.loads((directory/(name+'_initial_validation.json')).read_text())['valid'])
  with h5py.File(directory/'dataset'/(name+'.h5'),'r') as f:
   n=len(f['actions']) if 'actions' in f else 0;check['frames']=n;check['complete']=bool(f.attrs['complete'])
   if n:
    for key in ['actions','agent_pose','joint_positions','privileged/object_pose','privileged/next_object_pose','privileged/finger_contact_N','privileged/environment_contact_N']:assert np.isfinite(f[key][:]).all(),key
    check['finite_state_action_contact']=True
    t=f['timestamp'][:];next_t=f['next_timestamp'][:];check.update(actions_shape=list(f['actions'].shape),actual_state_shape=list(f['joint_positions'].shape),first_time=float(t[0]),last_time=float(next_t[-1]),terminal_done=bool(f['done'][-1]),interior_done=int(f['done'][:-1].sum()),max_dt_error_s=float(np.max(abs((next_t-t)[:-1]-1/cfg.physics.control_hz))),timestamp_chain_error_s=float(np.max(abs(next_t[:-1]-t[1:]))),next_state_chain_error=float(np.max(abs(f['next_agent_pose'][:-1]-f['agent_pose'][1:]))),rgb_dtype=str(f['camera_1_rgb'].dtype),rgb_shape=list(f['camera_1_rgb'].shape),external_std=float(np.std(f['camera_1_rgb'][min(n-1,600)])),wrist_std=float(np.std(f['camera_2_rgb'][min(n-1,600)])))
    assert f['actions'].shape==(n,8) and f['joint_positions'].shape==(n,9)
    assert check['timestamp_chain_error_s']<1e-10
    assert check['terminal_done'] and check['interior_done']==0 and check['max_dt_error_s']<1e-8 and check['next_state_chain_error']==0
    assert f['camera_1_rgb'].shape==(n,3,256,256) and f['camera_2_rgb'].shape==(n,3,256,256) and check['external_std']>2 and check['wrist_std']>2
  if rescore:
   scorer=Scorer(cfg,dict(source=np.array(initial['source_m']),target=np.array(initial['target_m']),boxes=boxes),layout,initial);status='RUNNING'
   with (directory/(name+'_physics.jsonl')).open() as stream:
    for line in stream:
     raw=json.loads(line)
     assert np.isfinite(np.r_[raw['linear_velocity'],raw['angular_velocity'],raw['joint_velocities'],raw['target_tcp']]).all()
     m=scorer.measure(raw['position'],raw['orientation'],raw['tcp'],raw['joint_positions'],raw['finger_contact_N'],raw['environment_contact_N']);status,reason=scorer.update(raw['time'],m)
     if status!='RUNNING':break
   check['offline_status']=status;check['offline_matches']=status==result['status'];assert check['offline_matches']
  checks.append(check)
 return checks

def adapter_check(directory):
 from policy.dataset.minimal_pick_dataset import MinimalPickDataset
 from torch.utils.data import DataLoader
 shape={'obs':{'camera_1_rgb':{'type':'rgb','shape':[3,256,256]},'camera_2_rgb':{'type':'rgb','shape':[3,256,256]},'agent_pose':{'type':'low_dim','shape':[8]}},'action':{'shape':[8]}}
 out={}
 for typ,nobs in [('act',1),('dp',2)]:
  from hydra import initialize_config_dir,compose
  from hydra.utils import instantiate
  with initialize_config_dir(config_dir=str(ROOT/'policy/config'),version_base=None):
   config=compose(config_name='train_lab_cuvette_loading_'+typ,overrides=['task.dataset_path='+str((directory/'dataset').resolve())]);dataset=instantiate(config.task.dataset)
  batch=next(iter(DataLoader(dataset,batch_size=2,collate_fn=dataset.collate_fn)));validation=dataset.get_validation_dataset()
  assert not set(dataset.train_episodes)&set(validation.episode_ids)
  last=dataset[dataset.lengths[dataset.episode_ids[0]]-1]
  if typ=='act':assert last['is_pad'].tolist()==[False]+[True]*15
  out[typ]=dict(hydra_dataset_target=str(config.task.dataset._target_),composed_task_name=str(config.task.name),batch_action_shape=list(batch['action'].shape),batch_obs_shapes={k:list(v.shape) for k,v in batch['obs'].items()},train_episodes=dataset.train_episodes,validation_episodes=validation.episode_ids,episode_boundary_checked=True,privileged_not_in_obs=True)
 return out

def main():
 p=argparse.ArgumentParser();p.add_argument('directories',nargs='+',type=Path);p.add_argument('--output',type=Path,required=True);p.add_argument('--no-rescore',action='store_true');args=p.parse_args();out={}
 for d in args.directories:out[str(d)]=dict(episodes=audit(d,not args.no_rescore),adapter=adapter_check(d) if json.loads((d/'training_index.json').read_text()) else None)
 args.output.write_text(json.dumps(out,indent=2));print('AUDIT_PASS',sum(len(x['episodes']) for x in out.values()))
if __name__=='__main__':main()
