"""Bounded robot-state-only tracking aid, independent of Isaac and task code.

The paired observation is the previous applied joint command's FK pose and the
current measured robot TCP pose, both in the same world frame and at one sample
boundary. Their difference estimates drive lag/load; no object pose is accepted.
This is a numerical control aid, not a calibration result or a physical model.
It changes neither drive gains nor material/contact settings and is not enabled
by importing this module. The Project_v1_1 release configuration explicitly
enables it; the task records nominal and corrected targets independently.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np
from scipy.spatial.transform import Rotation


def _vector(value, name):
    value = np.asarray(value, dtype=float)
    if value.shape != (3,) or not np.isfinite(value).all():
        raise ValueError(name + " must be a finite three-vector")
    return value.copy()


def _rotation(value, name):
    value = np.asarray(value, dtype=float)
    if value.shape != (3, 3) or not np.isfinite(value).all():
        raise ValueError(name + " must be a finite 3×3 rotation matrix")
    if not np.allclose(value.T @ value, np.eye(3), atol=1e-7, rtol=0) or not math.isclose(
            float(np.linalg.det(value)), 1., abs_tol=1e-7, rel_tol=0):
        raise ValueError(name + " must be a proper orthonormal rotation matrix")
    return value.copy()


def _bounded(vector, maximum):
    scale = float(np.max(np.abs(vector)))
    if scale == 0:
        return vector.copy(), False
    normalized = vector / scale
    scaled_norm = float(np.linalg.norm(normalized))
    saturated = scale > maximum / scaled_norm
    return (normalized * (maximum / scaled_norm) if saturated else vector.copy()), saturated


@dataclass(frozen=True)
class TrackingCompensation:
    command_position_m: np.ndarray
    command_rotation_matrix: np.ndarray
    diagnostics: dict


class RobotTrackingCompensator:
    """First-order observer with norm bounds; no explicit integral/PI term.

    ``alpha=None`` uses ``1-exp(-dt/time_constant_s)``. An explicit alpha in
    (0,1] selects a fixed per-sample coefficient instead. The bounded filtered
    state is reused, so a large transient cannot hide an unbounded filter tail.
    Rotation residuals/biases are world-frame rotation vectors, in radians.
    """

    def __init__(self, *, time_constant_s=.1, alpha=None,
                 max_position_bias_m=.001, max_rotation_bias_rad=.002):
        for name, value in (("time_constant_s", time_constant_s),
                            ("max_position_bias_m", max_position_bias_m),
                            ("max_rotation_bias_rad", max_rotation_bias_rad)):
            if not math.isfinite(float(value)) or float(value) <= 0:
                raise ValueError(name + " must be positive and finite")
        if alpha is not None and (not math.isfinite(float(alpha)) or not 0 < float(alpha) <= 1):
            raise ValueError("alpha must be in (0,1]")
        if float(max_position_bias_m) > .001 or float(max_rotation_bias_rad) > .002:
            raise ValueError("Tracking aid limits may not exceed 1 mm and 2 mrad")
        self.time_constant_s = float(time_constant_s)
        self.alpha = None if alpha is None else float(alpha)
        self.max_position_bias_m = float(max_position_bias_m)
        self.max_rotation_bias_rad = float(max_rotation_bias_rad)
        self.reset()

    def reset(self):
        """Clear the estimate between episodes or after a changed command frame."""
        self._position_bias = np.zeros(3)
        self._rotation_bias = np.zeros(3)
        self._samples = 0

    def _result(self, nominal_position, nominal_rotation, **diagnostics):
        diagnostics.update(schema="labsim.Project_v1_1.robot_tracking.v1",
            sample_count=self._samples, frame="world", uses_object_truth=False,
            numerical_control_aid=True, real_calibrated=False,
            filter_mode="fixed_alpha" if self.alpha is not None else "time_constant",
            time_constant_s=self.time_constant_s if self.alpha is None else None,
            max_position_bias_m=self.max_position_bias_m,
            max_rotation_bias_rad=self.max_rotation_bias_rad,
            applied_position_bias_m=self._position_bias.tolist(),
            applied_rotation_bias_world_rad=self._rotation_bias.tolist(),
            position_bias_norm_m=float(np.linalg.norm(self._position_bias)),
            rotation_bias_norm_rad=float(np.linalg.norm(self._rotation_bias)))
        return TrackingCompensation(
            command_position_m=nominal_position + self._position_bias,
            command_rotation_matrix=Rotation.from_rotvec(self._rotation_bias).as_matrix() @ nominal_rotation,
            diagnostics=diagnostics)

    def update(self, *, nominal_position_m, nominal_rotation_matrix,
               previous_command_position_m, previous_command_rotation_matrix,
               actual_position_m, actual_rotation_matrix, dt_s):
        """Use one newly paired robot sample, then compensate the nominal pose.

        ``previous_command_*`` must describe the actually applied, rate-limited
        joint command's FK, including any previous compensation. It must not be
        an unexecuted raw IK result or the next nominal Cartesian target.
        ``actual_*`` must be sampled after that command's physical interval.
        All validation happens before the observer state changes.
        """
        nominal_p = _vector(nominal_position_m, "nominal_position_m")
        nominal_r = _rotation(nominal_rotation_matrix, "nominal_rotation_matrix")
        command_p = _vector(previous_command_position_m, "previous_command_position_m")
        command_r = _rotation(previous_command_rotation_matrix, "previous_command_rotation_matrix")
        actual_p = _vector(actual_position_m, "actual_position_m")
        actual_r = _rotation(actual_rotation_matrix, "actual_rotation_matrix")
        dt = float(dt_s)
        if not math.isfinite(dt) or dt <= 0:
            raise ValueError("dt_s must be positive and finite")
        coefficient = self.alpha if self.alpha is not None else -math.expm1(-dt / self.time_constant_s)
        with np.errstate(over="ignore", invalid="ignore"):
            raw_p = command_p - actual_p
        if not np.isfinite(raw_p).all():
            raise ValueError("Position residual overflow; no tracking estimate was updated")
        raw_r = Rotation.from_matrix(command_r @ actual_r.T).as_rotvec()
        filtered_p = self._position_bias + coefficient * (raw_p - self._position_bias)
        filtered_r = self._rotation_bias + coefficient * (raw_r - self._rotation_bias)
        self._position_bias, p_saturated = _bounded(filtered_p, self.max_position_bias_m)
        self._rotation_bias, r_saturated = _bounded(filtered_r, self.max_rotation_bias_rad)
        self._samples += 1
        return self._result(nominal_p, nominal_r, observation_used=True, estimate_held=False,
            dt_s=dt, filter_alpha=coefficient,
            raw_position_error_m=raw_p.tolist(), raw_rotation_error_world_rad=raw_r.tolist(),
            filtered_position_error_before_bound_m=filtered_p.tolist(),
            filtered_rotation_error_before_bound_world_rad=filtered_r.tolist(),
            position_saturated=p_saturated, rotation_saturated=r_saturated)

    def hold(self, *, nominal_position_m, nominal_rotation_matrix):
        """Reuse the estimate without reusing an observation as a new sample.

        This only computes a Cartesian target. It does not hold a simulated
        object, freeze a robot, advance time, or make a safety decision.
        """
        nominal_p = _vector(nominal_position_m, "nominal_position_m")
        nominal_r = _rotation(nominal_rotation_matrix, "nominal_rotation_matrix")
        return self._result(nominal_p, nominal_r, observation_used=False, estimate_held=True,
            dt_s=None, filter_alpha=None, raw_position_error_m=None, raw_rotation_error_world_rad=None,
            filtered_position_error_before_bound_m=None, filtered_rotation_error_before_bound_world_rad=None,
            position_saturated=None, rotation_saturated=None)
