"""Optional existing RPent/pi0.5 runner on the bounded Project_v1 RPC.

Run in the already installed RPent Python. No models or Isaac are started by
importing this module. The legacy Codex planner is optional Harness support;
the separate gpt6 backend always uses the independent Cubence transport.
"""
from __future__ import annotations
import argparse
import math
import os
from pathlib import Path
import shutil
import sys


ROOT=Path(__file__).resolve().parents[2]


def prepare_arguments(argv):
    p=argparse.ArgumentParser(description=__doc__,epilog='Additional historical runner arguments are forwarded unchanged; use a new output directory.')
    p.add_argument('--backend',choices=('pi05','harness'),required=True)
    p.add_argument('--policy-config')
    p.add_argument('--subtask',default='loading')
    p.add_argument('--layout-mode',default='standard')
    p.add_argument('--codex-bin')
    p.add_argument('--env-endpoint')
    p.add_argument('--vla-endpoint')
    p.add_argument('--output')
    p.add_argument('--max-model-requests',type=int)
    p.add_argument('--max-actions',type=int)
    p.add_argument('--planner-timeout-s',type=int)
    args,_=p.parse_known_args(argv)
    if args.subtask!='loading' or args.layout_mode!='standard':
        raise ValueError('Project_v1 optional backends use the same standard/loading scene')
    result=list(argv)
    if not args.policy_config:
        result+=['--policy-config',str(ROOT/'config/lab_cuvette_loading/Project_v1/policies/pi05_libero.yaml')]
    if args.backend=='harness' and not args.codex_bin:
        codex=os.environ.get('LABSIM_CODEX_BIN') or shutil.which('codex')
        if not codex:raise ValueError('Optional Harness requires an existing Codex executable; set LABSIM_CODEX_BIN or --codex-bin')
        result+=['--codex-bin',codex]
    return result


def main(argv=None):
    argv=prepare_arguments(sys.argv[1:] if argv is None else argv)
    from policy_backends.lab_cuvette_env_v1 import policy_runner as legacy
    from policy_backends.lab_cuvette_env_v1.rpent_extension import LabSimToolkit
    from policy_backends.lab_cuvette_env_v1.policy_adapters import append_event
    import numpy as np

    class ProjectCompatibleToolkit(LabSimToolkit):
        """Keep the same real model primitive; cap generic tools to facade speed."""
        def __init__(self,*args,**kwargs):
            super().__init__(*args,**kwargs)
            spec,handler=self._tools['bounded_action']
            spec['description']='One generic bounded EE/joint action, executed by the same ProjectEnvironment. No task macro.'
            spec['input_schema']['properties']['values']['description']='EE world translation in metres and rotation vector in radians; per-axis <=0.5mm/0.004rad and norm speed <=0.02m/s/0.15rad/s. Joint delta radians.'
            self._tools['bounded_action']=(spec,handler)

        def bounded_action(self,kind,values,gripper_opening_m,duration_s=.05):
            raw=np.asarray(values,dtype=float)
            bounded=raw.copy()
            if kind=='ee_delta' and bounded.shape==(6,) and np.isfinite(bounded).all():
                duration=float(duration_s)
                translation=min(.0005,.02*duration/math.sqrt(3))
                rotation=min(.004,.15*duration/math.sqrt(3))
                bounded[:3]=np.clip(bounded[:3],-translation,translation)
                bounded[3:]=np.clip(bounded[3:],-rotation,rotation)
            append_event(self.output_dir/'project_transfer_limits.jsonl',dict(event='bounded_generic_transfer',raw_kind=kind,
                raw_values=raw,applied_values=bounded,duration_s=duration_s,teacher_used=False,object_truth_used=False))
            return super().bounded_action(kind,bounded.tolist(),gripper_opening_m,duration_s)

    legacy.LabSimToolkit=ProjectCompatibleToolkit
    return legacy.main(argv)


if __name__=='__main__':raise SystemExit(main())
