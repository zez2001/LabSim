import argparse,datetime,json,os,subprocess,time
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--checkout',type=Path,required=True);p.add_argument('--asset-root',type=Path,required=True);p.add_argument('--source-sha',required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--module',default='demos.lab_cuvette_project_release_v1.run');p.add_argument('--cli-command',choices=['demo','collect','eval','serve']);p.add_argument('native_args',nargs=argparse.REMAINDER);a=p.parse_args()
py='/home/wujing/Desktop/vla/labutopia-env/bin/python';root=a.checkout.resolve();out=a.output.resolve();assert not out.exists();assert not subprocess.check_output(['git','status','--porcelain'],cwd=root).strip();head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip();assert head==a.source_sha
out.parent.mkdir(parents=True,exist_ok=True);env=dict(os.environ);env.pop('CUBENCE_API_KEY',None);env.pop('HF_TOKEN',None);env.update(LABSIM_ASSET_ROOT=str(a.asset_root.resolve()),OMNI_KIT_ACCEPT_EULA='YES',PYTHONHASHSEED='0')
args=a.native_args[1:] if a.native_args[:1]==['--'] else a.native_args
cmd=([py,str(root/'scripts/labsim_cli.py'),a.cli_command,'--project-version','Project_release_v1','--output',str(out),*args] if a.cli_command else [py,'-m',a.module,'--output',str(out),*args]);start=time.perf_counter();utc=datetime.datetime.now(datetime.timezone.utc).isoformat();log=out.with_suffix('.native.log');statepath=out.with_suffix('.supervisor.json')
with log.open('x') as f:
 child=subprocess.Popen(cmd,cwd=root,env=env,stdout=f,stderr=subprocess.STDOUT);state=dict(started_utc=utc,run_directory=str(out),pid=child.pid,runtime_commit=head,checkout=str(root),command=cmd,status='running',credentials_in_child=False)
 while child.poll() is None:
  state['wall_seconds']=time.perf_counter()-start;statepath.write_text(json.dumps(state,indent=2)+'\n')
  if state['wall_seconds']>7200:child.terminate();state['parent_wall_timeout']=True
  time.sleep(5)
 code=child.wait()
state.update(process_exited=True,exit_code=code,wall_seconds=time.perf_counter()-start,status='closed',UTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),completion_evidence='Parent observed Popen.wait; native PID gone')
assert not Path('/proc',str(child.pid)).exists();statepath.write_text(json.dumps(state,indent=2)+'\n')
if out.is_dir():(out/'process_exit.json').write_text(json.dumps(state,indent=2)+'\n')
print(json.dumps(state,indent=2));raise SystemExit(code)
