"""Read-only validation of the real original expert-regression launch command.

Loads only the existing CLI parser (SimulationApp lives inside main), resolves
assets/config/registry and checks output protection. Never starts Isaac/GPU.
"""
from __future__ import annotations
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import runpy
import shlex
import sys

ROOT=Path(__file__).resolve().parents[1]
PYTHON=ROOT.parent/'labutopia-env/bin/python'


def check(output):
    from omegaconf import OmegaConf
    pipeline=ROOT/'demos/minimal_pick/pipeline.py';cfg_path=ROOT/'config/minimal_pick.yaml'
    output=Path(output).resolve()
    if output.exists():raise FileExistsError('Regression output must be new: '+str(output))
    tree=ast.parse(pipeline.read_text())
    top_level_imports=[node for node in tree.body if isinstance(node,(ast.Import,ast.ImportFrom))]
    if any('isaacsim' in ast.unparse(node) for node in top_level_imports):
        raise RuntimeError('Parser no longer safe to load without starting Isaac')
    argv=['--config',str(cfg_path),'--headless','--episodes','1','--output',str(output)]
    namespace=runpy.run_path(str(pipeline),run_name='labsim_readonly_minimal_pick_parser')
    original_argv=sys.argv
    try:
        sys.argv=[str(pipeline),*argv]
        args=namespace['arguments']()
    finally:sys.argv=original_argv
    cfg=OmegaConf.load(cfg_path)
    checks=dict(parser_accepted_real_arguments=args.headless and args.episodes==1 and args.replay is None and args.checkpoint is None,
        expert_mode=cfg.mode=='collect',original_task=cfg.task_type=='minimal_pick',
        original_controller=cfg.controller_type=='minimal_pick',original_collector=cfg.collector.type=='minimal_pick',
        existing_python_executable=PYTHON.is_file() and os.access(PYTHON,os.X_OK),output_does_not_exist=not output.exists(),
        positive_timeout=cfg.task.timeout_seconds>0)
    for kind,name in [('task','minimal_pick'),('controller','minimal_pick'),('collector','minimal_pick')]:
        source=(ROOT/f'factories/{kind}_factory.py').read_text()
        parsed=ast.parse(source)
        calls=[n for n in ast.walk(parsed) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='register_'+kind]
        checks[kind+'_registered']=any(n.args and isinstance(n.args[0],ast.Constant) and n.args[0].value==name for n in calls)
    for path in ['assets/robots/Franka.usd','tasks/minimal_pick_task.py','controllers/minimal_pick_controller.py','data_collectors/minimal_pick_collector.py']:
        checks['exists:'+path]=(ROOT/path).is_file()
    if not all(checks.values()):raise RuntimeError('Regression command precheck failed: '+str(checks))
    command=['env','OMNI_KIT_ACCEPT_EULA=YES','flock','/tmp/labsim-V0_ext01-gpu.lock',str(PYTHON),str(pipeline),*argv]
    evidence_files=[pipeline,cfg_path,ROOT/'tasks/minimal_pick_task.py',ROOT/'controllers/minimal_pick_controller.py',ROOT/'data_collectors/minimal_pick_collector.py']
    return dict(schema='labsim.Env_v1.original_task_regression_command.v1',checks=checks,
        executable_command=shlex.join(command),working_directory=str(ROOT),argument_values={k:str(v) if isinstance(v,Path) else v for k,v in vars(args).items()},
        file_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in evidence_files},
        Isaac_started=False,GPU_started=False,physical_regression_executed=False,source_files_modified=False,
        note='This validates the existing real expert command and dependencies only. Prior minimal_pick raw-data reader regression is separate evidence; actual new physical regression awaits serialized GPU availability.')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True,help='Proposed NEW simulation output directory; never created by this checker')
    parser.add_argument('--output-json')
    args=parser.parse_args();result=check(args.output)
    text=json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n'
    if args.output_json:
        with Path(args.output_json).open('x',encoding='utf-8') as stream:stream.write(text)
    print(text,end='')

if __name__=='__main__':main()
