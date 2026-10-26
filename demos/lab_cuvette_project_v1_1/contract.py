"""Release fingerprint and dataset admission, separate from historical Size_v1."""
from __future__ import annotations
import hashlib
import json
import subprocess
import copy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def scene_contract(cfg, geometry_audit=None):
    if isinstance(cfg, dict):
        data = copy.deepcopy(cfg)
    else:
        from omegaconf import OmegaConf
        data = OmegaConf.to_container(cfg, resolve=True)
    if data['scene_mode'] != 'standard' or data['env']['mode'] != 'standard':
        raise ValueError('Project_v1 collect/train/eval baseline is standard; random requires an explicit future release')
    randomization = data.get('randomization', {})
    if any(value is True for key, value in randomization.items() if key.endswith('enabled')):
        raise ValueError('Scene randomization must be disabled')
    data['env'].pop('shapely_site', None)
    data['env'].pop('geometry_audit_cache', None)
    data['env'].pop('execution_purpose', None)
    data['experiment'].pop('condition_group', None)
    data['experiment'].pop('deviation', None)
    from demos.lab_cuvette_project_v1.runtime import portable_config
    data = portable_config(data, data)
    code = {}
    names = ['tasks/lab_cuvette_loading_project_v1.py', 'tasks/lab_cuvette_loading_env_v1.py',
             'controllers/lab_cuvette_env_v1_controller.py', 'data_collectors/lab_cuvette_env_v1_collector.py',
             'tasks/lab_cuvette_loading_env_v1_scorer.py', 'demos/lab_cuvette_size_v1/scorer.py',
             'demos/lab_cuvette_env_v1/physics_capture.py', 'demos/lab_cuvette_size_v1/runtime_geometry.py']
    names += ['demos/lab_cuvette_project_v1_1/'+name for name in ('environment.py','continuous_ik.py','contract.py','scorer.py')]
    names += ['tasks/lab_cuvette_loading_project_v1_1.py','data_collectors/lab_cuvette_project_v1_1_collector.py']
    names += ['demos/lab_cuvette_project_v1_1/gripper_hold.py','demos/lab_cuvette_project_v1_1/robot_tracking.py']
    for name in sorted(set(names)):
        code[name] = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
    assets = {name: sha for name, sha in (geometry_audit or {}).get('binding', {}).get('files', {}).items()
              if name.startswith('assets/')}
    body = dict(schema='labsim.Project_v1_1.scene_contract.v1', config=data, dependencies=code, assets=assets,
                acceptance_version='Project_v1_1.independent.v1')
    return dict(body, frozen_scene_sha256=hashlib.sha256(canonical(body)).hexdigest())


def code_version():
    return subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
