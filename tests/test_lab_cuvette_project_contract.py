"""Portable fingerprints retain physical values and ignore only runtime locations."""
import copy
from pathlib import Path
import yaml
import pytest
from demos.lab_cuvette_project_v1.contract import scene_contract
from demos.lab_cuvette_project_v1.runtime import portable_config

ROOT = Path(__file__).resolve().parents[1]


def config_at(root):
    cfg = yaml.safe_load((ROOT / 'config/lab_cuvette_loading/Project_v1/standard.yaml').read_text())
    for key in ('asset_directory', 'derived_directory', 'asset_registry', 'source.instrument',
                'source.vessel', 'source.vessel_collision', 'robot.usd_path'):
        parts = key.split('.')
        parent = cfg
        for part in parts[:-1]:
            parent = parent[part]
        parent[parts[-1]] = str(root / parent[parts[-1]])
    cfg['env']['shapely_site'] = str(root / 'isolated_geometry')
    return cfg


def test_scene_fingerprint_independent_of_checkout_and_asset_cache_locations(tmp_path):
    first = scene_contract(config_at(tmp_path / 'machine_a'))
    second = scene_contract(config_at(tmp_path / 'machine_b'))
    assert first['frozen_scene_sha256'] == second['frozen_scene_sha256']
    assert first['config']['source']['vessel'].startswith('assets/')


def test_physics_or_actual_asset_hash_changes_fingerprint(tmp_path):
    cfg = config_at(tmp_path)
    baseline = scene_contract(cfg, {'binding': {'files': {'assets/example.usda': 'a' * 64}}})
    other = scene_contract(cfg, {'binding': {'files': {'assets/example.usda': 'b' * 64}}})
    assert baseline['frozen_scene_sha256'] != other['frozen_scene_sha256']
    cfg['physics']['hz'] = 480
    assert scene_contract(cfg)['frozen_scene_sha256'] != baseline['frozen_scene_sha256']


def test_controlled_action_deviation_is_not_a_scene_change(tmp_path):
    cfg = config_at(tmp_path)
    baseline = scene_contract(cfg)
    cfg['experiment']['condition_group'] = 'deterministic_action_deviation'
    cfg['experiment']['deviation'] = dict(stage='INSERT', value=.005, unit='m')
    assert scene_contract(cfg)['frozen_scene_sha256'] == baseline['frozen_scene_sha256']


def test_randomization_cannot_silently_enter_standard_training(tmp_path):
    cfg = config_at(tmp_path)
    cfg['randomization']['layout_randomization_enabled'] = True
    with pytest.raises(ValueError, match='randomization'):
        scene_contract(cfg)
