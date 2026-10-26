#!/usr/bin/env python3
"""Read-only CPU inventory of optional deployed RPent/pi0.5 dependencies.

Does not import torch, start a service, download a model, run inference, or touch
GPU. Full checkpoint hashing is opt-in because the local weights are7.47GB.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time


ROOT=Path(__file__).resolve().parents[1]


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(8<<20),b''):h.update(block)
    return h.hexdigest()


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--rpent-root',type=Path,default=os.environ.get('RPENT_REPO_ROOT',ROOT.parent/'rpent'))
    p.add_argument('--policy-python',type=Path,default=os.environ.get('LABSIM_POLICY_PYTHON'))
    p.add_argument('--checkpoint',type=Path,default=os.environ.get('LABSIM_PI05_CHECKPOINT'))
    p.add_argument('--hash-weights',action='store_true')
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args(argv)
    if args.output.exists():p.error('Preserve prior evidence: output already exists')
    root=args.rpent_root.expanduser().resolve();python=(args.policy_python or root/'.venv/bin/python').expanduser().resolve()
    checkpoint=(args.checkpoint or root/'checkpoints/RLinf-Pi05-LIBERO-130-fullshot-SFT').expanduser().resolve()
    result=dict(schema='labsim.Project_v1.optional_policy_inventory.v1',observed_unix_s=time.time(),rpent_root=str(root),policy_python=str(python),
        checkpoint=str(checkpoint),cpu_only=True,models_started=False,inference_executed=False,gpu_touched=False,
        checkpoint_is_labsim_finetuned=False,transfer_dynamics_calibrated=False)
    if (root/'.git').exists():
        proc=subprocess.run(['git','-C',str(root),'rev-parse','HEAD'],capture_output=True,text=True,timeout=10)
        result['rpent_commit']=proc.stdout.strip() if proc.returncode==0 else None
    result['runtime_exists']=python.is_file()
    if python.is_file():
        program="""import importlib.metadata as m,json,sys
out={'python':sys.version,'packages':{}}
for name in ['rpent-openpi','rpent-rlinf','torch','openai-codex']:
 try:out['packages'][name]=m.version(name)
 except m.PackageNotFoundError:out['packages'][name]=None
print(json.dumps(out))
"""
        proc=subprocess.run([str(python),'-c',program],capture_output=True,text=True,timeout=30)
        result['runtime']=json.loads(proc.stdout) if proc.returncode==0 else {'inspection_failed':True,'exit_code':proc.returncode}
    rows=[]
    for rel in ('model.safetensors','metadata.pt','physical-intelligence/libero/norm_stats.json'):
        path=checkpoint/rel;row=dict(file=rel,exists=path.is_file(),bytes=path.stat().st_size if path.is_file() else None,
            sha256=sha(path) if path.is_file() and (args.hash_weights or rel!='model.safetensors') else None)
        if path.is_file() and row['sha256'] is None:row['hash_status']='not rehashed; use --hash-weights'
        rows.append(row)
    result['checkpoint_files']=rows
    result['services']={}
    for port in (8097,8098):
        with socket.socket() as sock:
            sock.settimeout(.2);opened=sock.connect_ex(('127.0.0.1',port))==0
        result['services'][str(port)]=dict(tcp_listening=opened,service_identity_verified=False,
            note='TCP reachability alone is not model/environment identity or task validation')
    history=ROOT/'docs/lab_cuvette_loading/Env_v1/policy_evidence/real_three_chain_01.json'
    evidence=json.loads(history.read_text())
    result['historical_evidence']=dict(file=str(history.relative_to(ROOT)),sha256=sha(history),scope=evidence['scope'],
        full_loading_attempts=evidence['full_loading_attempts'],attempts=[{k:a.get(k) for k in ('attempt','backend','episode_id','actual_executed_policy_actions','actual_control_steps','simulation_duration_s','actual_vla_predict_requests','task_success','termination_reason')} for a in evidence['attempts']])
    result['new_project_optional_backend_physics_run']=False
    result['new_project_rpc_status']='CPU transport contract only until an actual Isaac RPC run is separately recorded'
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
    return 0


if __name__=='__main__':raise SystemExit(main())
