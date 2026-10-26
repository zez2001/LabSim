"""Current geometry proof bound only to actual release assets and implementation.

The unchanged Size_v1 geometric algorithms are reused. Historical raw attachment
files unrelated to the loaded asset chain are not implicit runtime dependencies.
"""
from pathlib import Path
import argparse
import hashlib
import json
from demos.lab_cuvette_env_v1 import geometry_audit as common
from demos.lab_cuvette_size_v1.geometry_audit import audit as size_audit
from demos.lab_cuvette_project_v1.runtime import asset_root_from_config, logical_path, portable_config

ROOT = Path(__file__).resolve().parents[2]


def binding(cfg, dependency_paths=None):
    value = common.plain(cfg)
    files = set(common.paths_for_config(value).values())
    files.update(Path(__file__).parent.glob('*.py'))
    for name in ('demos/lab_cuvette_env_v1', 'demos/lab_cuvette_size_v1'):
        files.update((ROOT / name).glob('*.py'))
    files.update(ROOT / p for p in ('tasks/lab_cuvette_loading_env_v1.py',
        'tasks/lab_cuvette_loading_project_v1.py', 'controllers/lab_cuvette_env_v1_controller.py',
        'demos/lab_cuvette_demo04/scene.py', 'demos/lab_cuvette_demo03/scene.py',
        'demos/lab_cuvette_external/geometry.py', 'demos/lab_cuvette_external/feasibility.py'))
    if dependency_paths is None:
        from pxr import Usd
        for path in tuple(files):
            if path.suffix in ('.usd', '.usda', '.usdc'):
                stage = Usd.Stage.Open(str(path), Usd.Stage.LoadAll)
                if not stage:
                    raise RuntimeError('Cannot load current asset: ' + str(path))
                files.update(Path(layer.realPath).resolve() for layer in stage.GetUsedLayers() if layer.realPath)
    else:
        files.update((asset_root_from_config(value) / p if str(p).startswith('assets/') else common.resolve(p))
                     for p in dependency_paths)
    contract = portable_config({key: value[key] for key in common.CONTRACT_KEYS if key in value}, value)
    body = dict(schema='labsim.Project_v1.geometry_binding.v1', contract=contract,
                files={logical_path(p, value): common.sha(p) for p in sorted(files)})
    return dict(body, fingerprint=hashlib.sha256(common.canonical(body)).hexdigest())


def ensure_current_audit(cfg, cache_directory, *, geometry_site=None):
    bound = binding(cfg)
    directory = Path(cache_directory)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / bound['fingerprint']
    path = target / 'geometry_audit.json'
    if path.exists():
        result = json.loads(path.read_text())
    else:
        result = size_audit(cfg, target, geometry_site=geometry_site, bound=bound)
    common.write(directory / 'latest.json', dict(audit_relative_path=str(path.relative_to(directory)),
                                               fingerprint=bound['fingerprint']))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--geometry-site')
    args = parser.parse_args()
    from omegaconf import OmegaConf
    result = ensure_current_audit(OmegaConf.load(args.config), args.output, geometry_site=args.geometry_site)
    print(json.dumps(dict(geometry_valid=result['geometry_valid'], fingerprint=result['binding']['fingerprint'])))
