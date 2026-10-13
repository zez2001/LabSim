"""Sequential standard/random oracle collection and physical action replay."""
import argparse,json,sys,time,subprocess,hashlib,csv,datetime,shutil
from pathlib import Path
import numpy as np
from omegaconf import OmegaConf
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
def write(path,x):path.write_text(json.dumps(x,ensure_ascii=False,indent=2,default=lambda v:v.tolist() if hasattr(v,'tolist') else str(v))+'\n')
def parser():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',type=Path,default=ROOT/'config/lab_cuvette_loading/V0.yaml');p.add_argument('--output',type=Path);p.add_argument('--headless',action='store_true');p.add_argument('--mode',choices=['standard','random','appearance','layout'],default='standard');p.add_argument('--seeds',default='0');p.add_argument('--episodes',type=int,default=1);p.add_argument('--no-video',action='store_true');p.add_argument('--debug-material',action='store_true');p.add_argument('--keep-open',action='store_true');p.add_argument('--replay',type=Path);p.add_argument('--replay-initial',type=Path);p.add_argument('--scene-only',action='store_true');return p

def run(args,app):
 from demos.lab_cuvette_loading.model import export_assets,sample_layout
 from tasks.lab_cuvette_loading_task import LabCuvetteLoadingTask
 from controllers.lab_cuvette_loading_controller import LabCuvetteLoadingController
 from data_collectors.lab_cuvette_loading_collector import LabCuvetteLoadingCollector
 from isaacsim.core.utils.types import ArticulationAction
 import h5py
 cfg=OmegaConf.load(args.config);output=(args.output or ROOT/'outputs/lab_cuvette_loading'/datetime.datetime.now().strftime('%Y%m%d_%H%M%S')).resolve();output.mkdir(parents=True,exist_ok=False);OmegaConf.save(cfg,output/'config.yaml')
 assets=output/'assets';manifest=export_assets(assets,cfg);write(output/'version.json',dict(branch=subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip(),commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),git_status=subprocess.check_output(['git','status','--short'],cwd=ROOT,text=True),source_sha256={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in [*Path(__file__).parent.glob('*.py'),ROOT/'tasks/lab_cuvette_loading_task.py',ROOT/'controllers/lab_cuvette_loading_controller.py',ROOT/'data_collectors/lab_cuvette_loading_collector.py']}))
 snapshot=output/'source_snapshot';snapshot.mkdir()
 for f in [*Path(__file__).parent.glob('*.py'),ROOT/'tasks/lab_cuvette_loading_task.py',ROOT/'controllers/lab_cuvette_loading_controller.py',ROOT/'data_collectors/lab_cuvette_loading_collector.py']:
  dest=snapshot/f.relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(f,dest)
 recorder=LabCuvetteLoadingCollector(cfg,output,save_video=not args.no_video);results=[];seeds=[int(x) for x in args.seeds.split(',')];seeds=seeds if args.mode!='standard' else seeds*args.episodes
 replay_actions=None;restored=None
 if args.replay:
  if not args.replay_initial:raise ValueError('Replay requires original actual initial state and sampled layout')
  restored=json.loads(args.replay_initial.read_text())
  with h5py.File(args.replay,'r') as f:
   if f.attrs['action_dimension']!=8 or f.attrs['robot_state_dimension']!=9:raise ValueError('wrong embodiment/action dimensions')
   replay_actions=f['actions'][:];replay_phase=f['phase_code'][:]
  seeds=[restored['layout']['seed']]
 try:
  for index,seed in enumerate(seeds):
   started=time.monotonic();layout=restored['layout'] if restored else sample_layout(cfg,args.mode,seed);task=LabCuvetteLoadingTask(cfg,layout,assets,manifest,args.debug_material);task.initialize(restored)
   write(output/f'episode_{index:04d}_initial.json',task.initial);write(output/f'episode_{index:04d}_initial_validation.json',task.initial_validation);write(output/f'episode_{index:04d}_effective.json',task.effective());write(output/f'episode_{index:04d}_geometry_probe.json',task.geometry_probe());write(output/f'episode_{index:04d}_collision_boxes.json',task.scene['boxes'])
   if hasattr(task,'restore_validation'):write(output/'restore_validation.json',task.restore_validation)
   task.save_views(output,f'episode_{index:04d}_initial');task.save_views(output,f'episode_{index:04d}_collision',collision=True)
   task.stage.Flatten().Export(str(output/f'episode_{index:04d}_scene.usda'))
   if args.scene_only:
    task.status,task.reason='SCENE_ONLY','not_a_task_result';results.append(task.result());break
   recorder.begin_episode(index,np.array(task.initial['objects']['target']['position']));recorder.file.attrs.update(seed=seed,mode=layout['mode'],scene_version=cfg.version,target_object_id=cfg.cuvette.target_id,source_slot_id=task.initial['source_slot_id'],target_slot_id=cfg.holder.target_id)
   controller=LabCuvetteLoadingController(cfg,task.robot,task);state=task.observation();execution=time.monotonic()
   while task.status=='RUNNING' and app.is_running():
    if replay_actions is None:action=controller.step(state)
    else:
     j=min(task.frame,len(replay_actions)-1);a=replay_actions[j];action=ArticulationAction(joint_positions=np.r_[a[:7],a[7],a[7]]);task.last_action=action.joint_positions;task.phase=list(cfg.control.phases_s)[max(0,int(replay_phase[j]))]
    if action is None:break
    state['phase']=task.phase;state['target_tcp']=task.target_tcp.copy();task.advance(action);next_state=task.observation();result=task.result();recorder.cache_transition(state,action,next_state,result);state=next_state
    if task.frame%180==0:print('STATE',index,seed,task.phase,round(task.elapsed,3),round(task.metrics['depth_m']*1000,3),task.scorer.progress,flush=True)
    if time.monotonic()-execution>600:task.status,task.reason='TIMEOUT','wall_clock_watchdog';recorder.file['done'][-1]=True
   if task.status=='RUNNING':task.status,task.reason='CONTROL_FAILURE','application_or_controller_stopped'
   if recorder.count and task.status!='RUNNING':recorder.file['done'][-1]=True
   result=task.result();result.update(execution_wall_seconds=time.monotonic()-execution,setup_wall_seconds=execution-started,wall_clock_seconds=time.monotonic()-started,gpu_memory_MiB=int(subprocess.check_output(['nvidia-smi','--query-gpu=memory.used','--format=csv,noheader,nounits'],text=True).strip().splitlines()[0]),replay=bool(args.replay),data=str(output/'dataset'/f'episode_{index:04d}.h5'))
   task.save_views(output,f'episode_{index:04d}_final')
   recorder.finish_episode(result);write(output/f'episode_{index:04d}_events.json',task.events)
   with (output/f'episode_{index:04d}_physics.jsonl').open('w') as f:
    for item in task.physics_records:f.write(json.dumps(item)+'\n')
   results.append(result);write(output/'summary.json',results);print(result['status'],index,seed,result['reason'],'depth',result['max_depth_mm'],'overlap',result['max_overlap_mm'],flush=True)
   task.close()
  if not args.scene_only:
   merged,count=recorder.merge();write(output/'training_index.json',[dict(episode=i,data=r['data'],seed=r['seed'],mode=r['mode'],version=cfg.version) for i,r in enumerate(results) if r['full_success']]);write(output/'failure_index.json',[dict(episode=i,data=r['data'],seed=r['seed'],status=r['status'],reason=r['reason']) for i,r in enumerate(results) if not r['full_success']])
  write(output/'summary.json',results)
  if args.keep_open:
   while app.is_running():task.world.render()
 finally:recorder.close()
 print('OUTPUT',output,flush=True);return 0

def main():
 args=parser().parse_args()
 from isaacsim import SimulationApp
 app=SimulationApp(dict(headless=args.headless,width=1280,height=720,extra_args=['--/app/extensions/fsWatcherEnabled=false']))
 code=1
 try:
  code=run(args,app);return code
 except BaseException:
  import traceback;traceback.print_exc();sys.stderr.flush();raise
 finally:
  from omni.kit.app import get_app
  get_app().post_quit(code);app.close()
if __name__=='__main__':sys.exit(main())
