"""CPU checks of local IK against noncommuting multi-axis kinematics."""
import json

import numpy as np
import pytest
from scipy.spatial.transform import Rotation

from demos.lab_cuvette_project_v1_1.continuous_ik import solve


SEED = np.array([.2, -.4, .25, .3, -.2, .1, .5])
BASE_R = Rotation.from_euler('zyx', [.3, -.2, .4]).as_matrix()
BASE_P = np.array([.12, -.25, .41])


def serial_fk(q):
    """Seven rotated-offset links; the TCP has its own nonidentity frame."""
    r, p = BASE_R.copy(), BASE_P.copy()
    offsets = [(0, 0, .11), (.03, 0, .13), (.15, 0, .02),
               (.13, .02, 0), (0, 0, .09), (.04, 0, .08), (.02, .01, .07)]
    for axis, angle, offset in zip('zyxyxyz', q, offsets):
        r = r @ Rotation.from_euler(axis, angle).as_matrix()
        p = p + r @ np.asarray(offset)
    return p + r @ [.015, -.008, .095], r @ Rotation.from_euler('xyz', [.1, -.2, .3]).as_matrix()


def bounded_fk(q):
    """Exactly bounded translation plus noncommuting redundant orientation."""
    p = BASE_P + BASE_R @ q[:3]
    r = BASE_R @ Rotation.from_euler('zyx', [q[3], q[4], q[5] + q[6]]).as_matrix()
    return p, r


def assert_pose(result, fk, target):
    p, r = fk(result['q'])
    assert np.linalg.norm(p - target[0]) <= 2e-6
    assert (Rotation.from_matrix(target[1]) * Rotation.from_matrix(r).inv()).magnitude() <= 2e-5
    assert result['position_error_m'] == pytest.approx(np.linalg.norm(p - target[0]), abs=1e-12)


def test_reachable_serial_pose_with_world_base_and_tcp_rotation():
    target = serial_fk(SEED + [.018, -.027, .012, .023, .006, -.019, .013])
    original = SEED.copy()
    result = solve(serial_fk, SEED, *target, np.full(7, -2.), np.full(7, 2.), max_joint_step_rad=.08)
    assert result['success'] is True
    assert_pose(result, serial_fk, target)
    assert np.max(np.abs(result['q'] - original)) <= .08
    np.testing.assert_array_equal(SEED, original)


def test_repeated_small_pose_targets_preserve_continuous_branch():
    q = SEED.copy()
    for fraction in np.linspace(.1, 1, 10):
        target = serial_fk(SEED + fraction * np.array([.04, -.03, .02, .03, .01, -.02, .03]))
        result = solve(serial_fk, q, *target, np.full(7, -2.), np.full(7, 2.), max_joint_step_rad=.012)
        assert result['success'] is True
        assert np.max(np.abs(result['q'] - q)) <= .012
        assert_pose(result, serial_fk, target)
        q = result['q']


def test_local_joint_step_cannot_jump_to_remote_exact_pose():
    target_q = SEED.copy()
    target_q[0] += .1
    target = bounded_fk(target_q)
    result = solve(bounded_fk, SEED, *target, np.full(7, -2.), np.full(7, 2.), max_joint_step_rad=.01)
    assert result['success'] is False
    assert result['reason'] == 'LOCAL_BOUNDARY_UNREACHABLE'
    assert result['position_error_m'] >= .09 - 1e-10
    assert np.max(np.abs(result['q'] - SEED)) <= .01 + 1e-14


def test_physical_limit_intersects_local_bounds_without_postsolve_clipping():
    lo, hi = np.full(7, -2.), np.full(7, 2.)
    hi[0] = SEED[0] + .006
    target_q = SEED.copy()
    target_q[0] += .02
    result = solve(bounded_fk, SEED, *bounded_fk(target_q), lo, hi, max_joint_step_rad=.1)
    assert result['success'] is False
    assert result['reason'] == 'LOCAL_BOUNDARY_UNREACHABLE'
    assert result['q'][0] <= hi[0]
    assert result['position_error_m'] >= .014 - 1e-10


def test_zero_step_holds_pose_and_does_not_claim_other_pose_reached():
    target = serial_fk(SEED)
    good = solve(serial_fk, SEED, *target, SEED, SEED, max_joint_step_rad=0.)
    assert good['success'] and good['iterations'] == 0
    failed = solve(serial_fk, SEED, target[0] + [0, 0, .001], target[1], SEED, SEED, max_joint_step_rad=0.)
    assert failed['success'] is False and failed['reason'] == 'NO_LOCAL_JOINT_FREEDOM'
    np.testing.assert_array_equal(failed['q'], SEED)


def test_rotation_only_command_uses_full_noncommuting_so3_error():
    target_q = SEED.copy()
    target_q[3:6] += [.035, -.024, .019]
    target = bounded_fk(target_q)
    result = solve(bounded_fk, SEED, *target, np.full(7, -2.), np.full(7, 2.), max_joint_step_rad=.05)
    assert result['success']
    assert_pose(result, bounded_fk, target)
    np.testing.assert_allclose(bounded_fk(result['q'])[0], bounded_fk(SEED)[0], atol=2e-6)


def test_iteration_budget_does_not_masquerade_as_reached_target():
    result = solve(serial_fk, SEED, *serial_fk(SEED + .04), np.full(7, -2.), np.full(7, 2.),
                   max_joint_step_rad=.1, max_iterations=1)
    assert result['success'] is False
    assert result['reason'] == 'ITERATION_LIMIT' and result['iterations'] == 1


@pytest.mark.parametrize('change', [
    {'q_seed': [float('nan')] * 7}, {'max_joint_step_rad': -.1},
    {'target_rotation_matrix': np.zeros((3, 3))}, {'position_tolerance_m': 0},
    {'lower': [3.] * 7}, {'max_iterations': 0},
])
def test_invalid_input_is_explicit_and_never_returns_nonfinite_errors(change):
    target = bounded_fk(SEED)
    args = dict(fk=bounded_fk, q_seed=SEED, target_position=target[0], target_rotation_matrix=target[1],
                lower=np.full(7, -2.), upper=np.full(7, 2.), max_joint_step_rad=.1)
    args.update(change)
    result = solve(**args)
    assert result['success'] is False
    assert result['reason'] == 'INVALID_INPUT'
    json.dumps({k: v.tolist() if isinstance(v, np.ndarray) else v for k, v in result.items()}, allow_nan=False)


@pytest.mark.parametrize('broken', [
    lambda q: (np.full(3, np.nan), np.eye(3)),
    lambda q: (np.zeros(3), np.zeros((3, 3))),
    lambda q: (_ for _ in ()).throw(RuntimeError('FK unavailable')),
])
def test_invalid_fk_never_becomes_success_or_nan(broken):
    result = solve(broken, SEED, *bounded_fk(SEED), np.full(7, -2.), np.full(7, 2.), max_joint_step_rad=.1)
    assert result['success'] is False and result['reason'] == 'FK_EVALUATION_FAILED'
    assert result['position_error_m'] is None and result['orientation_error_rad'] is None
    assert np.isfinite(result['q']).all()


def test_seed_outside_physical_joint_limits_is_not_silently_projected():
    result = solve(bounded_fk, SEED, *bounded_fk(SEED), np.full(7, -2.), np.full(7, .1), max_joint_step_rad=.1)
    assert result['success'] is False and result['reason'] == 'SEED_OUTSIDE_JOINT_LIMITS'
    np.testing.assert_array_equal(result['q'], SEED)
