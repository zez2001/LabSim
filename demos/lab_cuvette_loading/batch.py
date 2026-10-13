"""Sequential fresh-process episodes isolate Isaac renderer lifecycle; no GPU overlap."""
import json,subprocess,shutil,os,time,datetime
from pathlib import Path
from omegaconf import OmegaConf
ROOT=Path(__file__).resolve().parents[2]
def link(src,dst):
 dst.parent.mkdir(parents=True,exist_ok=True)
 try:os.link(src,dst)
 except OSError:shutil.copy2(src,dst)
def run_batch(args):
 from data_collectors.lab_cuvette_loading_collector import LabCuvetteLoadingCollector
 output=(args.output or ROOT/'outputs/lab_cuvette_loading'/datetime.datetime.now().strftime('%Y%m%d_%H%M%S')).resolve();output.mkdir(parents=True,exist_ok=False);cfg=OmegaConf.load(args.config);OmegaConf.save(cfg,output/'config.yaml');seeds=[int(s) for s in args.seeds.split(',')];seeds=seeds*args.episodes if args.mode=='standard' else seeds;results=[];recorder=LabCuvetteLoadingCollector(cfg,output,False);started=time.monotonic()
 for index,seed in enumerate(seeds):
  child=output/f'attempt_{index:04d}';command=['bash',str(ROOT/'demos/lab_cuvette_loading/run.sh'),'--config',str(args.config),'--mode',args.mode,'--seeds',str(seed),'--output',str(child)]
  for flag in ['headless','no_video','debug_material','scene_only']:
   if getattr(args,flag):command.append('--'+flag.replace('_','-'))
  print('BEGIN',index,seed,flush=True)
  with (output/f'attempt_{index:04d}.log').open('w') as log:process=subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
  name=f'episode_{index:04d}';summary=child/'summary.json'
  if summary.exists():
   r=json.loads(summary.read_text())[0];r.update(episode=index,process_exit=process.returncode,original_data=r['data'],data=str(output/'dataset'/(name+'.h5')))
   link(child/'dataset/episode_0000.h5',output/'dataset'/(name+'.h5'))
   for f in child.glob('episode_0000*'):
    dest=output/(f.name.replace('episode_0000',name))
    if f.name.endswith('_result.json'):dest.write_text(json.dumps(r,indent=2))
    else:link(f,dest)
   video=child/'video/episode_0000.mp4'
   if video.exists():link(video,output/'video'/(name+'.mp4'))
   if index==0:
    for filename in ['version.json']:
     shutil.copy2(child/filename,output/filename)
    shutil.copytree(child/'assets',output/'assets',copy_function=link);shutil.copytree(child/'source_snapshot',output/'source_snapshot',copy_function=link)
  else:r=dict(episode=index,seed=seed,mode=args.mode,status='ENVIRONMENT_FAILURE',reason='incomplete_process',process_exit=process.returncode,full_success=False,data=None,attempt_directory=str(child))
  results.append(r);(output/'summary.json').write_text(json.dumps(results,indent=2));print('RESULT',index,seed,r['status'],flush=True)
  # Preserve every attempted seed, including environment or initialization failure.
  (output/'failure_index.json').write_text(json.dumps([r for r in results if not r['full_success']],indent=2));(output/'training_index.json').write_text(json.dumps([dict(episode=r['episode'],data=r['data'],seed=r['seed'],mode=r['mode'],version=cfg.version) for r in results if r['full_success']],indent=2))
  with (output/'dataset/meta/episode.jsonl').open('a') as meta:meta.write(json.dumps(dict(episode_index=index,length=r.get('frames',0),tasks=[cfg.task.instruction],task_properties=r))+'\n')
 recorder.merge();recorder.close();(output/'batch_runtime.json').write_text(json.dumps(dict(wall_seconds=time.monotonic()-started,sequential=True,fresh_process_each_episode=True,requested_seeds=seeds),indent=2));print('OUTPUT',output,flush=True);return 0
