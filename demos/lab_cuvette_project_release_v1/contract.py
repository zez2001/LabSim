"""Version the publication behavior without editing the physical v1.1 contract."""
import hashlib
import copy
from pathlib import Path

from demos.lab_cuvette_project_v1_1.contract import canonical, scene_contract as previous_contract

ROOT = Path(__file__).resolve().parents[2]


def scene_contract(cfg, geometry_audit=None):
    # Record intent belongs to dataset membership, not the physical scene.
    # Historical contract code/configuration remain unchanged.
    if isinstance(cfg, dict):
        scene_cfg = copy.deepcopy(cfg)
    else:
        from omegaconf import OmegaConf
        scene_cfg = OmegaConf.to_container(cfg, resolve=True)
    scene_cfg.get('release', {}).pop('record_purpose', None)
    baseline = previous_contract(scene_cfg, geometry_audit)
    names = (
        'tasks/lab_cuvette_loading_project_release.py',
        'data_collectors/lab_cuvette_project_release_collector.py',
        'demos/lab_cuvette_project_release_v1/environment.py',
        'demos/lab_cuvette_project_release_v1/contract.py',
        'demos/lab_cuvette_project_release_v1/recording.py',
        'demos/lab_cuvette_project_release_v1/shutdown.py',
        'utils/episode_selection.py',
    )
    body = dict(schema='labsim.Project_release_v1.scene_contract.v1',
        physical_and_execution_baseline=baseline,
        acceptance_version='Project_v1_1.independent.v1',
        lifecycle_version='Project_release_v1.transactional_lifecycle.v1',
        publication_dependencies={name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                                  for name in names})
    return dict(body, frozen_scene_sha256=hashlib.sha256(canonical(body)).hexdigest())
