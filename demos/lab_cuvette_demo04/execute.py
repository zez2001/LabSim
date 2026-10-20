"""Sequential single-process driver preserving start, exit, timing and full log."""
from pathlib import Path
import argparse,datetime,json,subprocess,time
ROOT=Path(__file__).resolve().parents[2]
def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('arguments',nargs=argparse.REMAINDER);a=p.parse_args();dest=a.output.resolve();dest.mkdir(parents=True,exist_ok=False)
    extra=a.arguments[1:] if a.arguments and a.arguments[0]=='--' else a.arguments
    cmd=['bash',str(ROOT/'demos/lab_cuvette_demo04/run.sh'),*extra,'--output',str(dest/'run')];start=time.monotonic();utc=datetime.datetime.now(datetime.timezone.utc).isoformat()
    (dest/'request.json').write_text(json.dumps(dict(command=cmd,started_at_utc=utc,sequential=True),indent=2)+'\n')
    with (dest/'process.log').open('xb') as f:code=subprocess.run(cmd,cwd=ROOT,stdout=f,stderr=subprocess.STDOUT).returncode
    result=dict(command=cmd,started_at_utc=utc,finished_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),observed_process_exit_code=code,process_wall_seconds=time.monotonic()-start,wall_scope='full child startup through output and shutdown',parallel_isaac=False)
    (dest/'driver_result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
    raise SystemExit(code if code>=0 else 128-code)
if __name__=='__main__':main()
