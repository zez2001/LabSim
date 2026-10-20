"""CPU semantic regression checks, explicitly not model or Isaac evidence."""
import numpy as np
import unittest
try:
    import pytest
except ImportError as exc:
    raise unittest.SkipTest("This pytest suite runs in the deployed RPent .venv; Isaac Python has no pytest and is not modified") from exc
from scipy.spatial.transform import Rotation

from policy_backends.lab_cuvette_env_v1.policy_adapters import (
    LiberoTransferContract, Pi05LiberoAdapter, policy_observation, sensor_meta,
)


def adapter():
    # No model stub: instantiate only the pure conversion part, not infer().
    value = Pi05LiberoAdapter.__new__(Pi05LiberoAdapter)
    value.contract = LiberoTransferContract()
    value.base_position = np.array([-.3, 0, .74])
    value.base_rotation = Rotation.from_euler('z', 90, degrees=True)
    value.reset()
    return value


def observation():
    return {'episode_id': 'actual-episode-identity', 'step_index': 17,
            'simulation_time': 17 / 60, 'task_language': 'load the cuvette',
            'images': {'side_camera': np.zeros((8, 8, 3), np.uint8),
                       'wrist_camera': np.zeros((6, 6, 3), np.uint8)},
            'joint_positions': np.r_[np.zeros(7), .02, .02],
            'joint_velocities': np.zeros(9),
            'TCPpose': {'position_m': [-.3, .2, .84],
                        'quaternion_wxyz': [.7071067811865476, 0, 0, .7071067811865476]},
            'debug': {'object_pose': [999, 999, 999]},
            'teacher_internal': 'must never reach visual policy'}


def test_truth_is_absent_by_allowlist():
    result = policy_observation(observation())
    assert 'debug' not in result and 'teacher_internal' not in result
    assert 'images' in result and 'TCPpose' in result


def test_camera_sensor_metadata_does_not_leak_renderer_or_depth_debug():
    meta = {'name': 'wrist_camera', 'intrinsic_matrix_native': np.eye(3).tolist(),
            'renderer_debug': {'distance_to_image_plane': {'center_m': .33}},
            'configuration': {'debug_render_diagnostics': True},
            'last_image_read': {'observation_simulation_time_s': .5, 'hidden_depth': 999},
            'optical_conventions': {'quaternion': 'wxyz', 'debug': 999},
            'unannounced_sensor': 'not declared'}
    result = sensor_meta(meta)
    assert set(result) == {'name', 'intrinsic_matrix_native', 'last_image_read', 'optical_conventions'}
    assert result['last_image_read'] == {'observation_simulation_time_s': .5}
    assert result['optical_conventions'] == {'quaternion': 'wxyz'}
    obs = observation()
    obs['camera_meta'] = {'wrist_camera': meta, 'debug_camera': meta}
    assert policy_observation(obs)['camera_meta'] == {'wrist_camera': result}


def test_libero_state_uses_base_frame_quaternion_and_signed_fingers():
    encoded = adapter().encode_observation(observation())
    np.testing.assert_allclose(encoded['states'][:3], [.2, 0, .1], atol=1e-7)
    np.testing.assert_allclose(encoded['states'][3:6], [0, 0, 0], atol=1e-7)
    np.testing.assert_allclose(encoded['states'][6:], [.02, -.02], atol=1e-7)
    assert encoded['states'].shape == (8,)
    assert encoded['main_images'].shape != encoded['wrist_images'].shape


def test_seven_model_numbers_become_pose_delta_not_joint_positions():
    action = adapter().convert_action([1, 0, 0, 0, 0, 1, -1], observation())
    assert action['type'] == 'ee_delta' and action['frame'] == 'world'
    np.testing.assert_allclose(action['values'], [0, .002, 0, 0, 0, .02], atol=1e-12)
    assert action['gripper_opening_m'] == pytest.approx(.056)
    assert action['duration_s'] == pytest.approx(.05)
    assert action['observation_step'] == 17
    assert action['raw_model_action'] == [1, 0, 0, 0, 0, 1, -1]


def test_gripper_is_bounded_stateful_opening_not_dimension_reinterpretation():
    value = adapter()
    for _ in range(20):
        opened = value.convert_action(np.r_[np.zeros(6), -1], observation())
    assert opened['gripper_opening_m'] == pytest.approx(.08)
    for _ in range(20):
        closed = value.convert_action(np.r_[np.zeros(6), 1], observation())
    assert closed['gripper_opening_m'] == pytest.approx(0)


@pytest.mark.parametrize('bad', [[0] * 8, [float('nan')] * 7, [float('inf')] * 7])
def test_invalid_model_actions_rejected(bad):
    with pytest.raises(ValueError):
        adapter().convert_action(bad, observation())


def test_camera_replication_metadata_rejected():
    obs = observation()
    obs['camera_meta'] = {'wrist_camera': {'synthetic_duplicate': True}}
    with pytest.raises(ValueError, match='duplicated'):
        adapter().encode_observation(obs)


def test_noninteger_control_policy_ratio_rejected():
    with pytest.raises(ValueError, match='integer'):
        LiberoTransferContract(policy_action_hz=23)


def test_astra_direct_toolkit_cannot_expose_vla_or_expert(tmp_path):
    pytest.importorskip('rpent')
    from policy_backends.lab_cuvette_env_v1.rpent_extension import LabSimToolkit
    toolkit = LabSimToolkit(None, output_dir=tmp_path / 'direct', mode='direct')
    assert {spec['name'] for spec in toolkit.get_tools_spec()} == {'observe', 'bounded_action', 'finish'}
    assert toolkit._task_success is None
    assert not list((tmp_path / 'direct' / 'frozen_empty_memory').iterdir())
    assert toolkit.memory._memory_access == 'read_only'
    with pytest.raises(ValueError, match='forbids'):
        LabSimToolkit(None, output_dir=tmp_path / 'invalid', mode='direct', vla_adapter=object())


def test_spent_harness_action_budget_refuses_before_sensor_or_model_access(tmp_path):
    pytest.importorskip('rpent')
    from policy_backends.lab_cuvette_env_v1.rpent_extension import LabSimToolkit
    toolkit = LabSimToolkit(None, output_dir=tmp_path / 'harness', mode='harness',
                            vla_adapter=object(), maximum_action_calls=1)
    toolkit._action_calls = 1
    with pytest.raises(RuntimeError, match='budget reached'):
        toolkit.vla_primitive('observe and move', maximum_actions=1)
