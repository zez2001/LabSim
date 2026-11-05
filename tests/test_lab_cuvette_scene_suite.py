"""Fixed scene selection and frame propagation without starting Isaac."""
import copy
import json
from pathlib import Path

import numpy as np
import pytest
import yaml
from omegaconf import OmegaConf

from demos.lab_cuvette_project_release_v1 import scene_suite as suite


def baseline():
    return yaml.safe_load(suite.STANDARD_CONFIG.read_text())


@pytest.mark.parametrize('scene_id', suite.SCENE_IDS)
def test_all_scene_definitions_are_hash_bound_and_repeatable(scene_id):
    first = suite.load_scene_definition(scene_id)
    assert first == suite.load_scene_definition(scene_id)
    assert first['fixed_source_slot_id'] == 'A1'
    assert first['fixed_target_seat_id'] == 'candidate_far_hinge'
    assert first['source_configuration_sha256'] == suite.hashlib.sha256(suite.STANDARD_CONFIG.read_bytes()).hexdigest()
    assert first['initialization_rules']['reset_repetitions'] == 3
    assert first['unchanged']['physics'] is True


def test_standard_preserves_every_existing_config_field_and_legacy_contract():
    from demos.lab_cuvette_project_release_v1.contract import scene_contract
    config = baseline()
    selected = suite.select_scene(config, purpose='collect')
    assert config == baseline()  # no mutation
    membership = selected.pop('scene_suite')
    assert selected == config
    assert membership['scene_id'] == 'standard'
    selected['scene_suite'] = membership
    assert scene_contract(config) == scene_contract(selected)


@pytest.mark.parametrize('scene_id', suite.SCENE_IDS[1:])
def test_fixed_random_changes_only_allowed_assembly_values(scene_id):
    config = baseline()
    selected = suite.select_scene(OmegaConf.create(config), scene_id)
    assert OmegaConf.is_config(selected)
    data = OmegaConf.to_container(selected, resolve=True)
    for key in ('source', 'asset_id', 'asset_selection', 'physics', 'cameras',
                'geometry', 'gripper', 'acceptance', 'demo_release', 'adapter', 'robot'):
        assert data[key] == config[key]
    assert data['rack']['selected_slot_id'] == 'A1'
    assert data['rack']['inner_m'] == .016
    assert data['scene']['instrument_count'] == 1
    assert data['scene_mode'] == data['env']['mode'] == 'standard'
    assert data['randomization'] == config['randomization']
    assert data['release']['record_purpose'] == 'policy_evaluation'
    assert data['scene_suite']['reset_sampling_enabled'] is False
    assert suite.select_scene(selected, scene_id) == selected  # no accumulating deltas


@pytest.mark.parametrize('scene_id', suite.SCENE_IDS)
def test_source_target_neighbor_and_collision_frames_follow_assembly(scene_id):
    from demos.lab_cuvette_size_v1.scene import layout
    cfg = suite.select_scene(OmegaConf.create(baseline()), scene_id)
    actual = layout(cfg)
    expected = suite.load_scene_definition(scene_id)['frames']
    assert np.allclose(actual['source_floor'], expected['source_floor_world_m'], atol=1e-12)
    assert np.allclose(actual['target_floor'], expected['target_loading_floor_world_m'], atol=1e-12)
    assert np.allclose(actual['seat_original_floor'], expected['original_seat_floor_world_m'], atol=1e-12)
    assert len(actual['slots']) == 36
    assert len(actual['boxes']) == 50
    for box in actual['boxes']:
        assert np.allclose(box['rotation'], actual['rack_rotation'])
    blue = actual['neighbors'][0]
    blue_slot = next(slot for slot in actual['slots'] if slot['id'] == 'F6')
    assert np.allclose(blue['position'], blue_slot['origin_world_m']+[0, 0, cfg.scene.initial_bottom_gap_m])
    assert actual['target_seat_id'] == 'candidate_far_hinge'
    offset = actual['target_floor']-actual['seat_original_floor']
    assert np.allclose(offset, actual['instrument_rotation']@cfg.geometry.target_loading_offset_local_m)


@pytest.mark.parametrize('purpose', ['demo', 'collect', 'train', 'validation'])
def test_random_rejects_non_evaluation_uses(purpose):
    with pytest.raises(ValueError, match='policy_evaluation only'):
        suite.select_scene(baseline(), 'random_001', purpose=purpose)


def test_unknown_selection_and_legacy_sampler_rejected():
    with pytest.raises(ValueError, match='Unknown scene'):
        suite.load_scene_definition('random_011')
    with pytest.raises(ValueError, match='Unknown scene suite'):
        suite.suite_scene_ids('random11')
    config = baseline()
    config['randomization']['enabled'] = True
    with pytest.raises(ValueError, match='on-reset'):
        suite.select_scene(config, 'random_001')
    assert suite.suite_scene_ids() == suite.SCENE_IDS[1:]


def test_fixed_environment_cannot_change_scene_between_resets():
    first = suite.select_scene(baseline(), 'random_001')
    with pytest.raises(ValueError, match='fresh environment'):
        suite.select_scene(first, 'random_002')


def test_execution_indices_do_not_change_scene_or_standard_contract_identity():
    from demos.lab_cuvette_project_release_v1.contract import scene_contract
    first = suite.select_scene(baseline(), 'random_003')
    second = copy.deepcopy(first)
    first['scene_execution'] = dict(suite_run_id='run_a', scene_repetition_index=0, suite_episode_index=2)
    second['scene_execution'] = dict(suite_run_id='run_b', scene_repetition_index=8, suite_episode_index=92)
    assert suite.scene_manifest(first, 'random_003') == suite.scene_manifest(second, 'random_003')
    assert scene_contract(first) == scene_contract(second)
    standard = suite.select_scene(baseline())
    standard['scene_execution'] = first['scene_execution']
    assert scene_contract(standard) == scene_contract(baseline())


def test_damaged_definition_rejected_before_application(tmp_path):
    (tmp_path/'scenes').mkdir()
    data = suite.load_scene_definition('random_001')
    data['actual_parameters']['rack']['origin_m'][0] += .001
    (tmp_path/'scenes/random_001.json').write_text(json.dumps(data))
    with pytest.raises(ValueError, match='hash mismatch'):
        suite.load_scene_definition('random_001', directory=tmp_path)


def test_rehashed_definition_requires_explicit_suite_registration(tmp_path):
    (tmp_path/'scenes').mkdir()
    registry = suite.load_suite()
    (tmp_path/'suite.json').write_text(json.dumps(registry))
    data = suite.load_scene_definition('random_001')
    data['actual_parameters']['rack']['origin_m'][0] += .001
    data['definition_sha256'] = suite.canonical_sha({key: value for key, value in data.items() if key != 'definition_sha256'})
    (tmp_path/'scenes/random_001.json').write_text(json.dumps(data))
    with pytest.raises(ValueError, match='registered suite membership'):
        suite.load_scene_definition('random_001', directory=tmp_path)


def test_rotation_commands_follow_source_and_target_frames():
    cfg = suite.select_scene(baseline(), 'random_006')
    selected = suite.load_scene_definition('random_006')
    angle = selected['declared_delta']['instrument_yaw_deg']
    assert cfg['control']['target_vessel_yaw_deg'] == 90.+angle
    assert cfg['vessel']['yaw_deg'] == 90.
    assert np.allclose(cfg['control']['retreat_lateral_m'],
        suite._rotate_xy(baseline()['control']['retreat_lateral_m'], angle))
    rack = suite.select_scene(baseline(), 'random_005')
    source_angle = suite.load_scene_definition('random_005')['declared_delta']['rack_yaw_deg']
    assert rack['vessel']['yaw_deg'] == 90.+source_angle
    assert rack['control']['target_vessel_yaw_deg'] == 90.


def test_dependency_sidecar_includes_indirect_robot_builder_and_asset_chain():
    receipt = suite.dependency_snapshot(baseline(), geometry_audit={'binding': {'files': {'assets/example.usda': 'a'*64}}})
    assert receipt['dependencies']['config/lab_cuvette_loading/V0.yaml']['status'] == 'present'
    assert receipt['dependencies']['demos/lab_cuvette_demo04/run.py']['status'] == 'present'
    assert receipt['loaded_geometry_dependency_sha256']['assets/example.usda'] == 'a'*64
    assert receipt['dependency_fingerprint'] == suite.canonical_sha({key: value for key, value in receipt.items() if key != 'dependency_fingerprint'})


def test_manifest_binds_light_and_layout_separately_from_historical_contract():
    low = suite.scene_manifest(baseline(), 'random_007')
    high = suite.scene_manifest(baseline(), 'random_008')
    assert low['scene_suite_fingerprint'] != high['scene_suite_fingerprint']
    assert 900. <= low['definition']['actual_parameters']['lighting']['intensity'] <= 950.
    assert 1050. <= high['definition']['actual_parameters']['lighting']['intensity'] <= 1100.


@pytest.mark.parametrize('index', range(1, 11))
def test_seed_reconstructs_effective_candidate_and_raw_draws(index):
    rack, instrument, ryaw, iyaw, light, family, generation = suite.candidate_parameters(index)
    definition = suite.load_scene_definition(f'random_{index:03d}')
    assert definition['source_seed'] == generation['seed'] == 31000+index
    assert generation['raw_draws']
    assert generation['raw_draws'] == definition['generation']['raw_draws']
    assert rack == definition['declared_delta']['rack_translation_m'][:2]
    assert instrument == definition['declared_delta']['instrument_translation_m'][:2]
    assert ryaw == definition['declared_delta']['rack_yaw_deg']
    assert iyaw == definition['declared_delta']['instrument_yaw_deg']
    assert light == definition['actual_parameters']['lighting']['intensity']
    assert family == definition['change_family']


def test_definition_generation_refuses_existing_directory(tmp_path):
    with pytest.raises(FileExistsError):
        suite.generate_definitions(tmp_path)


@pytest.mark.parametrize('path,value', [
    ('vessel.mass_kg', .021),
    ('vessel.outer_xy_m', [.009, .009]),
    ('vessel.inertia_body_kg_m2', [[1., 0., 0.], [0., 1., 0.], [0., 0., 1.]]),
    ('physics.hz', 480),
    ('physics.dynamic_friction', .6),
    ('cameras.side_camera.focal_length_cm', 2.),
    ('cameras.wrist_camera.localeye_m', [.1, 0., .04]),
    ('acceptance.position_drift_m', .001),
    ('demo_release.penetration_m', .001),
    ('rack.selected_slot_id', 'A2'),
    ('rack.inner_m', .017),
    ('adapter.selected_target_seat_id', 'candidate_near_hinge'),
    ('robot.initial_joint_positions', [0.]*9),
    ('robot.tcp_local_m', [0., 0., .09]),
    ('robot.finger_kp', 9000.),
    ('teacher_execution.motion_time_scale', 1.),
    ('executor.ik_position_tolerance_m', .001),
    ('control.final_speed_m_s', .002),
    ('env.action_max_translation_m', .2),
    ('scene.instrument_xyz_m', [.5, .3, .74]),
    ('randomization.rack_translation_half_range_m', .1),
])
def test_fixed_protocol_rejects_hidden_physical_camera_score_or_control_changes(path, value):
    config = OmegaConf.create(baseline())
    OmegaConf.update(config, path, value)
    with pytest.raises(ValueError, match='protocol changed'):
        suite.select_scene(config, 'random_003')


def test_fixed_protocol_accepts_resolved_asset_roots_and_execution_metadata(tmp_path):
    config = baseline()
    root = tmp_path/'assets'/'portable_assets'
    for key in ('asset_directory', 'derived_directory', 'asset_registry'):
        config[key] = str(root/config[key])
    for key in ('instrument', 'vessel', 'vessel_collision'):
        config['source'][key] = str(root/config['source'][key])
    config['robot']['usd_path'] = str(root/config['robot']['usd_path'])
    config['asset_selection'].update(registry_sha256='c'*64, asset_sha256='d'*64,
        verified_registry_provenance={'portable_release': True})
    config['vessel'].update(mass_source='Retained engineering assumption; provenance annotation')
    config['env'].update(shapely_site=str(tmp_path/'geometry'), geometry_audit_cache='outputs/new_cache',
        seed=42, execution_purpose='eval')
    config['release'].update(record_mode='eval', record_purpose='policy_evaluation')
    config['scene_execution'] = dict(suite_run_id='new_run', scene_repetition_index=4, suite_episode_index=8)
    selected = suite.select_scene(config, 'random_006')
    assert suite.select_scene(selected, 'random_006') == selected
    assert selected['vessel']['mass_kg'] == .02
    assert selected['scene_execution'] == config['scene_execution']
    assert selected['asset_selection']['registry_sha256'] == 'c'*64


def test_frozen_standard_file_hash_is_a_protocol_gate(monkeypatch, tmp_path):
    changed = tmp_path/'standard.yaml'
    changed.write_bytes(suite.STANDARD_CONFIG.read_bytes()+b'\n# changed\n')
    monkeypatch.setattr(suite, 'STANDARD_CONFIG', changed)
    with pytest.raises(ValueError, match='frozen standard source changed'):
        suite.select_scene(baseline(), 'standard')
