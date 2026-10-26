"""CPU full-pose diagnostic planning; no physics or model inference starts."""
import copy
import json

import numpy as np
import pytest
from scipy.spatial.transform import Rotation

from demos.lab_cuvette_project_v1_1.free_space_plan import (
    anchor_pose_error, anchor_return_commands, build_free_space_plan,
)


def pose(position=(.4, .1, .9), euler=(.2, -.3, .4)):
    return dict(position_m=list(position), quaternion_wxyz=np.roll(Rotation.from_euler('xyz', euler).as_quat(), 1).tolist())


def test_three_independent_groups_have_all_signed_axes_and_fixed_full_pose():
    p0, p1 = pose(), pose((.4, .1, .93), (.2, -.3, .5))
    before = copy.deepcopy((p0, p1))
    plan = build_free_space_plan(p0, p1)
    assert [e['episode_id'] for e in plan['episodes']] == ['pose0_world', 'pose1_world', 'pose1_tcp']
    for episode in plan['episodes']:
        assert episode['reset_before_episode'] is True
        assert len(episode['probes']) == 24
        expected = {(axis, sign, amplitude) for axis in ('X', 'Y', 'Z')
            for sign in (-1, 1) for amplitude in (.001, .005, .02, .04)}
        actual = {(p['axis'], p['sign'], p['amplitude_m']) for p in episode['probes']}
        assert actual == expected
        for probe in episode['probes']:
            assert probe['return_before']['pose'] == episode['anchor_pose']
            assert probe['expected_endpoint_if_exact_anchor']['quaternion_wxyz'] == episode['anchor_pose']['quaternion_wxyz']
            assert probe['record_actual_start_and_anchor_residual'] is True
        assert episode['estimated_nominal_simulation_seconds'] < 75
    assert plan['object_truth_used'] is False and plan['diagnostic_not_GPT_run'] is True
    assert (p0, p1) == before
    json.dumps(plan, allow_nan=False)


def test_xyz_arrival_does_not_hide_quaternion_drift_and_q_sign_is_equivalent():
    anchor = pose()
    drifted = copy.deepcopy(anchor)
    r = Rotation.from_quat(np.roll(anchor['quaternion_wxyz'], -1))
    drifted['quaternion_wxyz'] = np.roll((Rotation.from_rotvec([0, 0, .01]) * r).as_quat(), 1).tolist()
    error = anchor_pose_error(drifted, anchor)
    assert error['position_error_m'] == 0
    assert error['orientation_error_rad'] == pytest.approx(.01)
    assert error['reached'] is False
    same = dict(position_m=anchor['position_m'], quaternion_wxyz=(-np.asarray(anchor['quaternion_wxyz'])).tolist())
    assert anchor_pose_error(same, anchor)['reached'] is True


def test_return_from_40mm_plus_residual_is_segmented_and_restores_fixed_quaternion():
    current, anchor = pose((.4408, .1, .9), (.2, -.3, .45)), pose()
    commands = anchor_return_commands(current, anchor)
    assert len(commands) == 2
    previous = current
    for command in commands:
        args = command['arguments']
        assert args['mode'] == 'ee_pose' and args['frame'] == 'world'
        target = dict(position_m=args['values'][:3], quaternion_wxyz=args['values'][3:])
        error = anchor_pose_error(previous, target)
        assert error['position_error_m'] <= .025 + 1e-12
        assert error['orientation_error_rad'] <= .1 + 1e-12
        assert error['position_error_m'] / args['duration_s'] <= .015 + 1e-12
        assert error['orientation_error_rad'] / args['duration_s'] <= .1 + 1e-12
        assert 0 < args['duration_s'] <= 3.
        assert args['duration_s'] * 60 == pytest.approx(round(args['duration_s'] * 60))
        previous = target
    assert previous == anchor


def test_orientation_only_return_is_not_skipped_or_accumulated():
    anchor = pose(euler=(0, 0, 0))
    current = pose(euler=(0, 0, .21))
    commands = anchor_return_commands(current, anchor)
    assert len(commands) == 3
    assert commands[-1]['arguments']['values'] == anchor['position_m'] + anchor['quaternion_wxyz']
    # Repeating the return from the same observed start yields identical
    # absolute targets rather than another relative orientation increment.
    assert anchor_return_commands(current, anchor) == commands


def test_tcp_delta_expected_endpoint_uses_fixed_anchor_rotation():
    p0 = pose(euler=(0, 0, 0))
    p1 = pose(euler=(0, 0, np.pi / 2))
    plan = build_free_space_plan(p0, p1)
    world, tcp = plan['episodes'][1:]
    w, t = world['probes'][0], tcp['probes'][0]
    assert w['action']['arguments']['values'] == t['action']['arguments']['values']
    assert w['action']['arguments']['frame'] == 'world'
    assert t['action']['arguments']['frame'] == 'tcp'
    np.testing.assert_allclose(np.asarray(w['expected_endpoint_if_exact_anchor']['position_m']) - p1['position_m'], [.001, 0, 0], atol=1e-14)
    np.testing.assert_allclose(np.asarray(t['expected_endpoint_if_exact_anchor']['position_m']) - p1['position_m'], [0, .001, 0], atol=1e-14)


def test_each_episode_has_wait_close_open_and_absolute_three_second_hold():
    for episode in build_free_space_plan(pose(), pose((.4, .1, .93)))['episodes']:
        epilogue = episode['epilogue']
        assert [e.get('tool', e['kind']) for e in epilogue] == ['return_anchor', 'wait', 'gripper', 'gripper', 'return_anchor', 'move_ee']
        assert epilogue[1]['arguments']['duration_s'] == 1
        assert epilogue[2]['arguments']['opening_m'] == .06
        assert epilogue[3]['arguments']['opening_m'] == .08
        hold = epilogue[-1]
        assert hold['arguments']['duration_s'] == 3
        assert hold['arguments']['values'] == episode['anchor_pose']['position_m'] + episode['anchor_pose']['quaternion_wxyz']
        assert hold['arguments']['mode'] == 'ee_pose'


@pytest.mark.parametrize('value', [0, -1, 1.5, float('nan')])
def test_invalid_control_frequency_is_rejected(value):
    with pytest.raises(ValueError):
        build_free_space_plan(pose(), pose(), control_hz=value)


def test_invalid_pose_and_insufficient_budget_are_rejected():
    bad = pose()
    bad['quaternion_wxyz'] = [0, 0, 0, 0]
    with pytest.raises(ValueError, match='unit'):
        build_free_space_plan(pose(), bad)
    with pytest.raises(ValueError, match='timeout'):
        build_free_space_plan(pose(), pose(), episode_timeout_s=20)
    bad = pose()
    bad['position_m'][0] = float('nan')
    with pytest.raises(ValueError, match='finite'):
        anchor_return_commands(bad, pose())
