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


@pytest.mark.parametrize('scene_id', ['standard', 'random_007'])
def test_context_hook_preserves_standard_light_and_sets_explicit_random_only(tmp_path, monkeypatch, scene_id):
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
        return dict(available=True, path=path, position_m=list(position), quaternion_wxyz=validation._yaw_quaternion(yaw))
    monkeypatch.setattr(validation, '_usd_pose', pose)
    task = SimpleNamespace(cfg=cfg, episode_dir=tmp_path)
    ctx = dict(stage=SimpleNamespace(GetPrimAtPath=lambda _: False), fixtures=fixtures,
        validation_runtime_kind='offline_usd_composition', robot_joint_state_source='configuration_mock',
        robot=SimpleNamespace(get_joint_positions=lambda: np.asarray(cfg.robot.initial_joint_positions)))
    receipt = validation.configure_context(task, ctx)
    assert receipt['passed']
    assert (tmp_path/'authored_scene_validation.json').is_file()
    assert len(sets) == (0 if scene_id == 'standard' else 2)
    assert intensity.Get() == cfg.scene_suite.actual_parameters.lighting.intensity
    assert receipt['runtime_kind'] == 'offline_usd_composition'
    assert receipt['robot_initial_joint_check']['native_articulation_verified'] is False


@pytest.mark.parametrize('count', [0, 1, 2, True, 11, 3.5])
def test_reset_count_is_checked_before_runtime_import_or_creation(tmp_path, count):
    with pytest.raises(ValueError, match='3..10'):
        validation.validate_resets(None, {}, tmp_path, {}, count=count)
    assert not (tmp_path/'reset_validation').exists()
