"""Reproducible sequential V0 checks, frozen random seeds, collection and replays."""
import argparse,sys,json,subprocess,time,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def main():
 p=argparse.ArgumentParser();p.add_argument('--root-output',type=Path,default=ROOT/'outputs/lab_cuvette_loading');p.add_argument('--suffix',default='V0');args=p.parse_args();out=args.root_output.resolve();out.mkdir(exist_ok=True);state=[];seeds=json.loads((ROOT/'config/lab_cuvette_loading/seeds.json').read_text());py=str(ROOT.parent/'labutopia-env/bin/python')
 def execute(name,command):
  start=time.monotonic();print('SUITE_BEGIN',name,flush=True)
  with (out/(name+'.log')).open('x') as log:r=subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,env={**os.environ,'OMNI_KIT_ACCEPT_EULA':'YES'})
  state.append(dict(stage=name,returncode=r.returncode,wall_seconds=time.monotonic()-start));(out/('suite_'+args.suffix+'.json')).write_text(json.dumps(state,indent=2));print('SUITE_END',name,r.returncode,flush=True)
  if r.returncode:raise RuntimeError(name+' process failed; artifacts retained')
 def run(name,extra):execute(name,['bash',str(ROOT/'demos/lab_cuvette_loading/run.sh'),'--headless','--output',str(out/name)]+extra)
 for mode in ['appearance','layout']:
  run(mode+'_check_'+args.suffix,['--mode',mode,'--seeds',str(seeds[mode+'_check'][0])])
 # Test outcomes never select replacement seeds or alter V0 parameters.
 run('random_test_'+args.suffix,['--mode','random','--seeds',','.join(map(str,seeds['test']))])
 run('collection_'+args.suffix,['--mode','random','--seeds',','.join(map(str,seeds['collection']))])
 for mode,original in [('standard','standard_demo_V0'),('random','random_test_'+args.suffix)]:
  source=out/original;results=json.loads((source/'summary.json').read_text());success=next((i for i,r in enumerate(results) if r['full_success']),None)
  if success is None:state.append(dict(stage=mode+'_replay',status='NOT_RUN_NO_SUCCESS'));continue
  n=f'episode_{success:04d}';run(mode+'_replay_'+args.suffix,['--config',str(source/'config.yaml'),'--replay',str(source/'dataset'/(n+'.h5')),'--replay-initial',str(source/(n+'_initial.json'))])
 for mode in ['static_geometry','command_response']:
  execute('synthetic_'+mode+'_'+args.suffix,[py,str(ROOT/'demos/lab_cuvette_loading/real_compare.py'),'--headless','--record',str(ROOT/'config/lab_cuvette_loading/synthetic_import_fixture.json'),'--mode',mode,'--output',str(out/('synthetic_'+mode+'_'+args.suffix))])
 execute('data_audit_'+args.suffix,[py,str(ROOT/'demos/lab_cuvette_loading/audit.py'),*[str(out/name) for name in ['standard10_verified_V0','appearance_check_'+args.suffix,'layout_check_'+args.suffix,'random_test_'+args.suffix,'collection_'+args.suffix,'standard_replay_'+args.suffix,'random_replay_'+args.suffix]],'--output',str(out/('all_audit_'+args.suffix+'.json'))])
 print('SUITE_FINISHED',flush=True)
if __name__=='__main__':main()
