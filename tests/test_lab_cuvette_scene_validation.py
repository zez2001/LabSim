"""Reset measurement semantics without importing Isaac or creating a stage."""
import copy
import json
import math
import sys
from types import SimpleNamespace

import numpy as np

import pytest
import yaml

from demos.lab_cuvette_project_release_v1 import scene_validation as validation
from demos.lab_cuvette_project_release_v1.scene_suite import STANDARD_CONFIG


def config():
    return yaml.safe_load(STANDARD_CONFIG.read_text())


def state(time, *, dx=0., quaternion=None):
    return dict(t=time, object_position_m=[-.085+dx, -.175, .743],
        object_quaternion_wxyz=quaternion or [1., 0., 0., 0.],
        source_bottom_gap_m=0., source_rack_penetration_m=0., tilt_deg=0.,
        environment_net_force_N=[0., 0., .1962],
        linear_velocity_native_m_s=[0., 0., 0.], angular_velocity_native_rad_s=[0., 0., 0.],
        fd_com_velocity_m_s=[0., 0., 0.], fd_angular_velocity_rad_s=[0., 0., 0.],
        forbidden_robot_environment_contact=False)


def rows():
    return [state(index/60.) for index in range(241)]


def test_authored_pose_comparison_uses_units_and_quaternion_sign():
    expected = dict(position_m=[.1, .2, .3], quaternion_wxyz=[1., 0., 0., 0.])
    actual = dict(position_m=[.1, .2, .3], quaternion_wxyz=[-1., 0., 0., 0.])
    assert validation.compare_pose(expected, actual)['passed']
    actual['position_m'][0] += 1.1e-6
    result = validation.compare_pose(expected, actual)
    assert not result['passed']
    assert result['errors'] == ['position_mismatch']
    assert result['position_tolerance_m'] == 1.e-6


def test_authored_pose_angle_tolerance_is_not_stability_tolerance():
    angle = math.radians(2.e-5)/2
    expected = dict(quaternion_wxyz=[1., 0., 0., 0.])
    result = validation.compare_pose(expected,
        dict(quaternion_wxyz=[math.cos(angle), 0., 0., math.sin(angle)]))
    assert not result['passed']
    assert result['orientation_tolerance_deg'] == 1.e-5


def test_missing_and_nonfinite_pose_fail_closed():
    assert not validation.compare_pose(dict(position_m=[0., 0., 0.]), {})['passed']
    assert not validation.compare_pose(dict(position_m=[0., 0., 0.]), dict(position_m=[0., float('nan'), 0.]))['passed']
    assert validation.quaternion_angle_deg([0., 0., 0., 0.], [1., 0., 0., 0.]) is None
    assert validation.quaternion_angle_deg([1., 0., 0., 0.], [None, 0., 0., 0.]) is None


def test_settled_window_requires_full_duration_and_real_support():
    result = validation.validate_settled_state(rows(), config())
    assert result['passed']
    assert result['source_net_vertical_force_N'] == .1962
    assert result['checks']['full_three_second_window']
    short = validation.validate_settled_state(rows()[-20:], config())
    assert not short['passed']
    assert short['checks']['full_three_second_window'] is False


@pytest.mark.parametrize('field,value,failed_check', [
    ('source_rack_penetration_m', .000051, 'source_penetration_valid'),
    ('source_bottom_gap_m', .000051, 'source_bottom_supported'),
    ('tilt_deg', 1.01, 'upright'),
    ('environment_net_force_N', [0., 0., .099], 'supported'),
    ('linear_velocity_native_m_s', [None, 0., 0.], 'native_velocities_finite'),
    ('forbidden_robot_environment_contact', True, 'no_robot_environment_contact'),
])
def test_existing_engineering_gates_are_not_relaxed(field, value, failed_check):
    values = rows()
    values[-1][field] = value
    result = validation.validate_settled_state(values, config())
    assert not result['passed']
    assert result['checks'][failed_check] is False


def test_native_fd_disagreement_is_retained_without_loosening_motion_gate():
    values = rows()
    values[-1]['linear_velocity_native_m_s'] = [.2, .1, 0.]
    original = copy.deepcopy(values)
    result = validation.validate_settled_state(values, config())
    assert result['passed']
    assert result['velocity_channel_differences']['linear']['warning']
    assert result['velocity_channel_differences']['linear']['gating'] is False
    assert values == original
    moving = rows()
    moving[-1]['object_position_m'][0] += .000201
    assert not validation.validate_settled_state(moving, config())['passed']


def test_repeatability_compares_resets_not_just_within_reset_stability():
    records = [dict(settled=state(4., dx=index*.00005)) for index in range(3)]
    assert validation.repeatability(records)['passed']
    records[-1]['settled']['object_position_m'][0] += .0002
    assert not validation.repeatability(records)['passed']
    assert not validation.repeatability([dict(settled=state(4.)), {}])['passed']


def test_closure_requires_matching_marker_h5_and_result(tmp_path):
    import h5py
    dataset = tmp_path/'dataset'
    dataset.mkdir()
    (tmp_path/'result.json').write_text('{}')
    (dataset/'episode_complete.json').write_text(json.dumps(dict(
        episode_id='identity_a', h5='episode.h5', finalization_id='closure_a')))
    with h5py.File(dataset/'episode.h5', 'w') as source:
        source.attrs.update(complete=True, publication_state='complete',
            episode_id='identity_a', finalization_id='closure_a')
    assert validation.closure_status(tmp_path, 'identity_a')['closed']
    assert not validation.closure_status(tmp_path, 'identity_b')['closed']
    with h5py.File(dataset/'episode.h5', 'r+') as source:
        source.attrs['publication_state'] = 'prepared'
    assert not validation.closure_status(tmp_path, 'identity_a')['closed']
    with h5py.File(dataset/'episode.h5', 'r+') as source:
        source.attrs['publication_state'] = 'complete'
    (tmp_path/'result.json').unlink()
    assert not validation.closure_status(tmp_path, 'identity_a')['closed']


def mock_context(tmp_path, monkeypatch, scene_id='standard'):
    from omegaconf import OmegaConf
    from demos.lab_cuvette_project_release_v1.scene_suite import select_scene
    from demos.lab_cuvette_size_v1.scene import layout
    cfg = select_scene(OmegaConf.create(config()), scene_id)
    fixtures = layout(cfg)
    sets = []
    class Attr:
        def __init__(self, value):
            self.value = value
        def Get(self):
            return self.value
        def Set(self, value):
            sets.append(value)
            self.value = value
    intensity, exposure = Attr(1000.), Attr(0.)
    light = SimpleNamespace(GetIntensityAttr=lambda: intensity, GetExposureAttr=lambda: exposure)
    class Prim:
        def __init__(self, path):
            self.path = path
        def IsActive(self):
            return True
        def HasAPI(self, _):
            return '/Collision/' in self.path
        def IsA(self, _):
            return '/Visual/' in self.path
        def GetPath(self):
            return self.path
    colliders = [Prim('/World/'+name+'/Collision/'+str(index)) for name, number in
        [('SourceRack', 50), ('Instrument', 8), ('Cuvette', 28), ('Franka', 11), ('NeighborCuvette_F6', 28)]
        for index in range(number)]
    colliders += [Prim('/World/'+name+'/Visual/'+str(index)) for name, number in
        [('SourceRack', 50), ('Instrument', 8), ('Cuvette', 1), ('NeighborCuvette_F6', 1)] for index in range(number)]
    fake = SimpleNamespace(
        Usd=SimpleNamespace(PrimRange=SimpleNamespace(Stage=lambda *_: colliders), TraverseInstanceProxies=lambda: None),
        UsdGeom=SimpleNamespace(GetStageMetersPerUnit=lambda _: 1., Mesh=object(), Cube=object()),
        UsdPhysics=SimpleNamespace(CollisionAPI=object()),
        UsdLux=SimpleNamespace(DomeLight=SimpleNamespace(Get=lambda *_: light)))
    monkeypatch.setitem(sys.modules, 'pxr', fake)
    pose_offsets = {}
    def pose(_, path):
        if path == '/World/SourceRack':
            position, yaw = cfg.rack.origin_m, cfg.rack.yaw_deg
        elif path == '/World/Instrument':
            position, yaw = cfg.scene.instrument_xyz_m, cfg.scene.instrument_yaw_deg
        elif path == '/World/Franka':
            position, yaw = cfg.robot.base_m, 0.
        elif path == '/World/Cuvette':
            position, yaw = fixtures['source_floor']+[0, 0, cfg.scene.initial_bottom_gap_m], cfg.vessel.yaw_deg
        elif '/Slots/' in path:
            position, yaw = fixtures['source_floor'], cfg.rack.yaw_deg
        elif '/Frames/' in path:
            position = fixtures['seat_original_floor']-fixtures['instrument_rotation']@np.array([0, 0, .002])
            yaw = cfg.scene.instrument_yaw_deg
        else:
            position, yaw = fixtures['neighbors'][0]['position'], cfg.vessel.yaw_deg
        position = np.asarray(position)+np.asarray(pose_offsets.get(path, [0., 0., 0.]))
        return dict(available=True, path=path, position_m=list(position), quaternion_wxyz=validation._yaw_quaternion(yaw))
    monkeypatch.setattr(validation, '_usd_pose', pose)
    task = SimpleNamespace(cfg=cfg, episode_dir=tmp_path)
    ctx = dict(stage=SimpleNamespace(GetPrimAtPath=lambda _: False), fixtures=fixtures,
        validation_runtime_kind='offline_usd_composition', robot_joint_state_source='configuration_mock',
        robot=SimpleNamespace(get_joint_positions=lambda: np.asarray(cfg.robot.initial_joint_positions)))
    return task, ctx, pose_offsets, sets, intensity


@pytest.mark.parametrize('scene_id', ['standard', 'random_007'])
def test_context_hook_preserves_standard_light_and_sets_explicit_random_only(tmp_path, monkeypatch, scene_id):
    task, ctx, _, sets, intensity = mock_context(tmp_path, monkeypatch, scene_id)
    receipt = validation.configure_context(task, ctx)
    assert receipt['passed']
    assert (tmp_path/'authored_scene_validation.json').is_file()
    assert len(sets) == (0 if scene_id == 'standard' else 2)
    assert intensity.Get() == task.cfg.scene_suite.actual_parameters.lighting.intensity
    assert receipt['runtime_kind'] == 'offline_usd_composition'
    assert receipt['robot_initial_joint_check']['native_articulation_verified'] is False


def native_snapshot(task, ctx):
    ctx.pop('validation_runtime_kind')
    ctx.pop('robot_joint_state_source')
    ctx['scene_authoring_snapshot'] = validation.capture_scene_authoring(ctx['stage'], task.cfg, ctx['fixtures'])
    return copy.deepcopy(ctx['scene_authoring_snapshot'])


def test_native_authoring_uses_pre_reset_snapshot_and_retains_natural_fall(tmp_path, monkeypatch):
    task, ctx, offsets, sets, _ = mock_context(tmp_path, monkeypatch)
    before = native_snapshot(task, ctx)
    for path in ('/World/Cuvette', '/World/NeighborCuvette_F6'):
        offsets[path] = [0., 0., -.000170286]
    receipt = validation.configure_context(task, ctx)
    assert receipt['passed']
    assert receipt['scene_authoring_snapshot'] == before
    assert ctx['scene_authoring_snapshot'] == before
    assert sets == []
    assert receipt['authored_pose_timing'] == 'before_first_world_reset'
    for name in ('cuvette', 'neighbor_0'):
        assert receipt['comparisons'][name]['passed']
        assert receipt['dynamic_builder_pose_changes'][name]['vertical_delta_m'] == pytest.approx(-.000170286)
        assert receipt['post_builder_actual'][name]['position_m'][2] == pytest.approx(
            receipt['authored_actual'][name]['position_m'][2]-.000170286)
    assert all(row['passed'] for row in receipt['static_post_builder_comparisons'].values())


@pytest.mark.parametrize('name,path', [('cuvette', '/World/Cuvette'), ('rack', '/World/SourceRack')])
def test_native_pre_reset_snapshot_keeps_one_micrometre_tolerance(tmp_path, monkeypatch, name, path):
    task, ctx, offsets, _, _ = mock_context(tmp_path, monkeypatch)
    offsets[path] = [1.1e-6, 0., 0.]
    native_snapshot(task, ctx)
    with pytest.raises(validation.SceneInitializationError):
        validation.configure_context(task, ctx)
    receipt = json.loads((tmp_path/'authored_scene_validation.json').read_text())
    assert receipt['comparisons'][name]['errors'] == ['position_mismatch']
    assert receipt['comparisons'][name]['position_tolerance_m'] == 1.e-6


def test_native_pre_reset_snapshot_keeps_orientation_tolerance(tmp_path, monkeypatch):
    task, ctx, _, _, _ = mock_context(tmp_path, monkeypatch)
    native_snapshot(task, ctx)
    ctx['scene_authoring_snapshot']['poses']['cuvette']['quaternion_wxyz'] = validation._yaw_quaternion(90.00002)
    with pytest.raises(validation.SceneInitializationError):
        validation.configure_context(task, ctx)
    receipt = json.loads((tmp_path/'authored_scene_validation.json').read_text())
    assert receipt['comparisons']['cuvette']['errors'] == ['orientation_mismatch']
    assert receipt['comparisons']['cuvette']['orientation_tolerance_deg'] == 1.e-5


@pytest.mark.parametrize('channel', ['snapshot', 'post_builder'])
def test_native_nonfinite_pose_fails_closed(tmp_path, monkeypatch, channel):
    task, ctx, offsets, _, _ = mock_context(tmp_path, monkeypatch)
    native_snapshot(task, ctx)
    if channel == 'snapshot':
        ctx['scene_authoring_snapshot']['poses']['cuvette']['position_m'][0] = float('nan')
    else:
        offsets['/World/Cuvette'] = [float('nan'), 0., 0.]
    with pytest.raises(validation.SceneInitializationError):
        validation.configure_context(task, ctx)
    receipt = json.loads((tmp_path/'authored_scene_validation.json').read_text())
    assert receipt['passed'] is False
    if channel == 'snapshot':
        assert receipt['comparisons']['cuvette']['errors'] == ['position_missing_or_nonfinite']
    else:
        assert receipt['component_checks']['dynamic_post_builder_poses_finite'] is False


@pytest.mark.parametrize('name,path', [
    ('rack', '/World/SourceRack'), ('instrument', '/World/Instrument'),
    ('robot', '/World/Franka'), ('source_slot', '/World/SourceRack/Slots/A1'),
    ('target_seat', '/World/Instrument/Frames/candidate_far_hinge')])
def test_native_static_roots_must_remain_fixed_during_builder(tmp_path, monkeypatch, name, path):
    task, ctx, offsets, _, _ = mock_context(tmp_path, monkeypatch)
    native_snapshot(task, ctx)
    offsets[path] = [1.1e-6, 0., 0.]
    with pytest.raises(validation.SceneInitializationError):
        validation.configure_context(task, ctx)
    receipt = json.loads((tmp_path/'authored_scene_validation.json').read_text())
    assert receipt['comparisons'][name]['passed']
    assert receipt['static_post_builder_comparisons'][name]['errors'] == ['position_mismatch']


@pytest.mark.parametrize('fault', ['missing', 'wrong_timing', 'wrong_scene', 'missing_pose', 'wrong_path'])
def test_native_context_without_valid_pre_reset_snapshot_fails_closed(tmp_path, monkeypatch, fault):
    task, ctx, _, _, _ = mock_context(tmp_path, monkeypatch)
    native_snapshot(task, ctx)
    snapshot = ctx['scene_authoring_snapshot']
    if fault == 'missing':
        del ctx['scene_authoring_snapshot']
    elif fault == 'wrong_timing':
        snapshot['timing'] = 'after_builder_reset'
    elif fault == 'wrong_scene':
        snapshot['scene_id'] = 'random_007'
    elif fault == 'missing_pose':
        del snapshot['poses']['neighbor_0']
    else:
        snapshot['poses']['cuvette']['path'] = '/World/OtherCuvette'
    with pytest.raises(validation.SceneInitializationError, match='pre-reset'):
        validation.configure_context(task, ctx)
    receipt = json.loads((tmp_path/'authored_scene_validation.json').read_text())
    assert receipt['passed'] is False
    assert receipt['errors'] == ['pre_reset_authoring_snapshot_missing_or_invalid']
    assert receipt['post_builder_actual']['cuvette']['available']


@pytest.mark.parametrize('suite', [False, True])
def test_builder_passes_read_only_observer_only_for_suite(tmp_path, monkeypatch, suite):
    from omegaconf import OmegaConf
    from demos.lab_cuvette_env_v1 import scene
    from demos.lab_cuvette_project_release_v1.scene_suite import select_scene
    cfg = OmegaConf.create(config())
    if suite:
        cfg = select_scene(cfg, 'standard')
    calls = []
    stage = object()
    snapshot = dict(pre_reset='read-only-observation')
    def capture(actual_stage, actual_cfg, fixtures):
        assert actual_stage is stage
        assert actual_cfg is cfg
        calls.append('observe_before_reset')
        return snapshot
    def make_scene(args, app, output, actual_cfg):
        assert actual_cfg is cfg
        if suite:
            args.scene_authoring_observer(stage)
        else:
            assert not hasattr(args, 'scene_authoring_observer')
        calls.append('unchanged_builder_reset')
        return dict(stage=stage)
    monkeypatch.setattr(validation, 'capture_scene_authoring', capture)
    monkeypatch.setitem(sys.modules, 'demos.lab_cuvette_demo04.run', SimpleNamespace(make_scene=make_scene))
    context = scene.build_context(cfg, None, tmp_path)
    assert calls == (['observe_before_reset', 'unchanged_builder_reset'] if suite else ['unchanged_builder_reset'])
    assert ('scene_authoring_snapshot' in context) is suite
    if suite:
        assert context['scene_authoring_snapshot'] is snapshot


def test_observer_is_before_first_builder_reset_without_changing_reset_calls():
    import ast
    from pathlib import Path
    source = Path('demos/lab_cuvette_demo04/run.py').read_text()
    function = next(node for node in ast.parse(source).body if isinstance(node, ast.FunctionDef) and node.name == 'make_scene')
    calls = [node for node in ast.walk(function) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)]
    observer = [node for node in calls if node.func.attr == 'scene_authoring_observer']
    resets = [node for node in calls if isinstance(node.func.value, ast.Name) and
        node.func.value.id == 'world' and node.func.attr == 'reset']
    assert len(observer) == 1
    assert len(resets) == 2  # first reset plus the unchanged range(2) reset loop
    assert observer[0].lineno < min(node.lineno for node in resets)


@pytest.mark.parametrize('count', [0, 1, 2, True, 11, 3.5])
def test_reset_count_is_checked_before_runtime_import_or_creation(tmp_path, count):
    with pytest.raises(ValueError, match='3..10'):
        validation.validate_resets(None, {}, tmp_path, {}, count=count)
    assert not (tmp_path/'reset_validation').exists()
