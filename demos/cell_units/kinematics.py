"""Continuous small-step Cartesian IK with explicit physical error thresholds."""

import numpy as np
from scipy.optimize import least_squares
from scipy.spatial.transform import Rotation


def solve_step(forward, current, position, rotation, lower, upper, max_step):
    """Solve within one legal joint increment; never accept an unchanged pose by tolerance alone."""
    lo, hi = np.maximum(lower, current - max_step), np.minimum(upper, current + max_step)

    def residual(q):
        point, matrix = forward(q)
        error = (rotation * Rotation.from_matrix(matrix).inv()).as_rotvec()
        return np.r_[np.asarray(point) - position, 0.1 * error]

    def jacobian(q):
        # Absolute differences remain resolvable when a joint is near zero;
        # relative differences can vanish in the native FK implementation.
        offsets = np.eye(len(q)) * 1e-5
        return np.column_stack([(residual(q + d) - residual(q - d)) / 2e-5 for d in offsets])

    result = least_squares(
        residual,
        np.clip(current, lo, hi),
        bounds=(lo, hi),
        method="dogbox",
        jac=jacobian,
        ftol=1e-10,
        xtol=1e-10,
        gtol=1e-10,
        max_nfev=40,
    )
    error = residual(result.x)
    diagnostics = dict(
        position_error_m=float(np.linalg.norm(error[:3])),
        rotation_error_rad=float(np.linalg.norm(error[3:]) / 0.1),
        max_joint_increment_rad=float(np.max(abs(result.x - current))),
    )
    ok = diagnostics["position_error_m"] < 1e-5 and diagnostics["rotation_error_rad"] < 1e-4
    return result.x, ok, diagnostics


def cartesian_path(
    kinematics,
    frame,
    start_position,
    start_rotation,
    end_position,
    end_rotation,
    start_joints,
    duration,
    *,
    lower,
    upper,
):
    """Precision path for small clearances, using the actual starting FK pose."""
    forward = lambda q: kinematics.compute_forward_kinematics(frame, q)
    start_position, matrix = forward(start_joints)
    first = Rotation.from_matrix(matrix)
    last = Rotation.from_quat(np.roll(end_rotation, -1))
    delta = (last * first.inv()).as_rotvec()
    path = [np.asarray(start_joints, dtype=float)]
    for fraction in np.linspace(0, 1, max(2, round(duration * 30)))[1:]:
        position = start_position + fraction * (end_position - start_position)
        rotation = Rotation.from_rotvec(delta * fraction) * first
        q, ok, detail = solve_step(
            forward, path[-1], position, rotation, lower, upper, np.full(7, 0.08)
        )
        if not ok:
            raise RuntimeError(f"Precision Cartesian path rejected: {detail}")
        path.append(q)
    return np.asarray(path)
