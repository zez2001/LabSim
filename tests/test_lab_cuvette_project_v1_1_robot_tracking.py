"""Pure numerical observer tests; toy plants are not Isaac/real calibration."""
import json

import numpy as np
import pytest
from scipy.spatial.transform import Rotation

from demos.lab_cuvette_project_v1_1.robot_tracking import RobotTrackingCompensator


def sample(observer, *, nominal_p=None, nominal_r=None, command_p=None, command_r=None,
           actual_p=None, actual_r=None, dt=1 / 60):
    return observer.update(nominal_position_m=np.zeros(3) if nominal_p is None else nominal_p,
        nominal_rotation_matrix=np.eye(3) if nominal_r is None else nominal_r,
        previous_command_position_m=np.zeros(3) if command_p is None else command_p,
        previous_command_rotation_matrix=np.eye(3) if command_r is None else command_r,
        actual_position_m=np.zeros(3) if actual_p is None else actual_p,
        actual_rotation_matrix=np.eye(3) if actual_r is None else actual_r, dt_s=dt)


def test_fixed_disturbance_toy_plant_converges_in_position_and_world_rotation():
    observer = RobotTrackingCompensator()
    nominal_p = np.array([.4, -.2, .7])
    nominal_r = Rotation.from_euler("xyz", [.4, -.2, .3]).as_matrix()
    disturbance_p = np.array([.0003, -.0002, .0001])
    disturbance_r = np.array([.0004, -.0003, .0002])
    command_p, command_r = nominal_p.copy(), nominal_r.copy()
    for _ in range(150):
        actual_p = command_p - disturbance_p
        actual_r = Rotation.from_rotvec(-disturbance_r).as_matrix() @ command_r
        result = sample(observer, nominal_p=nominal_p, nominal_r=nominal_r,
            command_p=command_p, command_r=command_r, actual_p=actual_p, actual_r=actual_r)
        command_p, command_r = result.command_position_m, result.command_rotation_matrix
    np.testing.assert_allclose(command_p - disturbance_p, nominal_p, atol=1e-12)
    remaining = Rotation.from_matrix((Rotation.from_rotvec(-disturbance_r).as_matrix() @ command_r) @ nominal_r.T)
    assert remaining.magnitude() < 1e-12
    assert result.diagnostics["uses_object_truth"] is False
    assert result.diagnostics["real_calibrated"] is False
    json.dumps(result.diagnostics, allow_nan=False)


def ramp_plant(compensated):
    observer = RobotTrackingCompensator()
    actual, previous = np.zeros(3), np.zeros(3)
    errors, biases = [], []
    for tick in range(480):
        nominal = np.array([tick / 60 * .005, 0., 0.])
        result = sample(observer, nominal_p=nominal, command_p=previous, actual_p=actual)
        command = result.command_position_m if compensated else nominal
        # Simple first-order joint-drive surrogate with constant load error.
        actual += .3 * (command - np.array([.0002, 0., 0.]) - actual)
        previous = command.copy()
        errors.append(float(np.linalg.norm(actual - nominal)))
        biases.append(result.diagnostics["position_bias_norm_m"])
    return np.asarray(errors), np.asarray(biases)


def test_dynamic_lag_ramp_toy_plant_reduces_steady_error_without_exceeding_bound():
    uncorrected, _ = ramp_plant(False)
    corrected, biases = ramp_plant(True)
    assert np.mean(corrected[-100:]) < np.mean(uncorrected[-100:]) * .05
    assert np.max(biases) <= .001 + 1e-15


def test_lowpass_reduces_noise_and_uses_norm_rather_than_per_axis_limits():
    observer = RobotTrackingCompensator(alpha=.2)
    rng = np.random.default_rng(824)
    inputs, outputs = [], []
    for _ in range(2000):
        noise = rng.normal(0, .00002, 3)
        result = sample(observer, actual_p=-noise)
        inputs.append(noise)
        outputs.append(result.diagnostics["applied_position_bias_m"])
    assert np.std(outputs[100:]) < np.std(inputs[100:]) * .45
    bounded = sample(RobotTrackingCompensator(alpha=1), actual_p=-np.ones(3) * .01,
        actual_r=Rotation.from_rotvec([-.02, -.02, -.02]).as_matrix())
    assert np.linalg.norm(bounded.command_position_m) == pytest.approx(.001)
    assert Rotation.from_matrix(bounded.command_rotation_matrix).magnitude() == pytest.approx(.002)
    assert bounded.diagnostics["position_saturated"] is True
    assert bounded.diagnostics["rotation_saturated"] is True
    np.testing.assert_allclose(bounded.diagnostics["raw_position_error_m"], np.ones(3) * .01)


def test_large_transient_does_not_leave_an_unbounded_hidden_filter_tail():
    observer = RobotTrackingCompensator(alpha=.2)
    first = sample(observer, actual_p=[-1., 0., 0.])
    assert first.diagnostics["filtered_position_error_before_bound_m"] == [.2, 0., 0.]
    second = sample(observer)
    assert second.diagnostics["applied_position_bias_m"] == pytest.approx([.0008, 0., 0.])
    assert second.diagnostics["position_saturated"] is False


def test_extreme_finite_residual_keeps_direction_and_overflow_is_rejected():
    observer = RobotTrackingCompensator(alpha=1)
    result = sample(observer, actual_p=[-1e300, -1e300, 0])
    np.testing.assert_allclose(result.command_position_m, [.001 / np.sqrt(2), .001 / np.sqrt(2), 0])
    before = result.diagnostics["applied_position_bias_m"]
    with pytest.raises(ValueError, match="residual overflow"):
        sample(observer, command_p=[1.7e308, 0, 0], actual_p=[-1.7e308, 0, 0])
    held = observer.hold(nominal_position_m=[0, 0, 0], nominal_rotation_matrix=np.eye(3))
    assert held.diagnostics["applied_position_bias_m"] == before
    assert held.diagnostics["sample_count"] == 1


def test_world_frame_rotation_composition_and_rigid_frame_equivariance():
    arguments = dict(nominal_p=np.array([.1, .2, .3]), nominal_r=Rotation.from_euler("x", .7).as_matrix(),
        command_p=np.array([.3, .2, .1]), command_r=Rotation.from_euler("xyz", [.2, -.1, .4]).as_matrix())
    arguments["actual_p"] = arguments["command_p"] - [.0002, -.0003, .0001]
    arguments["actual_r"] = Rotation.from_rotvec([-.0003, .0005, -.0002]).as_matrix() @ arguments["command_r"]
    result = sample(RobotTrackingCompensator(alpha=1), **arguments)
    bias_r = Rotation.from_rotvec(result.diagnostics["applied_rotation_bias_world_rad"]).as_matrix()
    np.testing.assert_allclose(result.command_rotation_matrix, bias_r @ arguments["nominal_r"], atol=1e-14)
    world = Rotation.from_euler("xyz", [-.4, .8, .3]).as_matrix()
    translation = np.array([1., -2., .5])
    changed = {name: world @ value + translation if name.endswith("_p") else world @ value
        for name, value in arguments.items()}
    transformed = sample(RobotTrackingCompensator(alpha=1), **changed)
    np.testing.assert_allclose(transformed.command_position_m, world @ result.command_position_m + translation, atol=1e-14)
    np.testing.assert_allclose(transformed.command_rotation_matrix, world @ result.command_rotation_matrix, atol=1e-14)


def test_time_constant_filter_depends_on_elapsed_time_not_sample_count():
    estimates = []
    for hz in (60, 120, 240):
        observer = RobotTrackingCompensator(time_constant_s=.1)
        for _ in range(hz // 2):
            result = sample(observer, actual_p=[-.0005, 0, 0], dt=1 / hz)
        estimates.append(result.diagnostics["applied_position_bias_m"])
    np.testing.assert_allclose(estimates, np.tile(estimates[0], (3, 1)), atol=1e-15)


def test_hold_does_not_reuse_observation_and_reset_clears_all_state():
    observer = RobotTrackingCompensator(alpha=.2)
    first = sample(observer, actual_p=[-.0005, 0, 0])
    for _ in range(10):
        held = observer.hold(nominal_position_m=[.1, .2, .3], nominal_rotation_matrix=np.eye(3))
        assert held.diagnostics["sample_count"] == 1
        assert held.diagnostics["raw_position_error_m"] is None
        assert held.diagnostics["applied_position_bias_m"] == first.diagnostics["applied_position_bias_m"]
    held.command_position_m[:] = 9  # Returned arrays must not alias observer state.
    observer.reset()
    reset = observer.hold(nominal_position_m=[.1, .2, .3], nominal_rotation_matrix=np.eye(3))
    np.testing.assert_array_equal(reset.command_position_m, [.1, .2, .3])
    assert reset.diagnostics["sample_count"] == 0


@pytest.mark.parametrize("field,bad", [("actual_p", [np.nan, 0, 0]), ("command_p", [0, 0]),
    ("nominal_r", np.zeros((3, 3))), ("actual_r", np.diag([1., 1., -1.])),
    ("dt", 0), ("dt", float("inf"))])
def test_invalid_inputs_fail_before_observer_mutation(field, bad):
    observer = RobotTrackingCompensator()
    sample(observer, actual_p=[-.0005, 0, 0])
    before = observer.hold(nominal_position_m=[0, 0, 0], nominal_rotation_matrix=np.eye(3)).diagnostics
    with pytest.raises(ValueError):
        sample(observer, **{field: bad})
    after = observer.hold(nominal_position_m=[0, 0, 0], nominal_rotation_matrix=np.eye(3)).diagnostics
    assert after == before


@pytest.mark.parametrize("kwargs", [dict(alpha=0), dict(alpha=1.1), dict(alpha=float("nan")),
    dict(time_constant_s=0), dict(max_position_bias_m=-1), dict(max_rotation_bias_rad=float("inf")),
    dict(max_position_bias_m=.002), dict(max_rotation_bias_rad=.003)])
def test_invalid_observer_configuration_is_rejected(kwargs):
    with pytest.raises(ValueError):
        RobotTrackingCompensator(**kwargs)
