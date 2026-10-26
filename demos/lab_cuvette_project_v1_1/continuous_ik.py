"""Local, FK-verified IK with explicit joint-step bounds; no simulator imports.

The caller supplies the true world-frame TCP FK, including the robot base and
TCP offset.  This solver searches only the intersection of physical limits and
``q_seed +/- max_joint_step_rad``.  It never clips a returned solution into a
different joint configuration and then calls that configuration successful.

This is a local pose solver, not collision avoidance or a dynamics guarantee.
The caller must preflight the whole Cartesian path and check actual tracking.
"""
from __future__ import annotations

import numpy as np
from scipy.optimize import least_squares
from scipy.spatial.transform import Rotation


class _InvalidFK(ValueError):
    pass


def _rotation_matrix(value):
    matrix = np.asarray(value, dtype=float)
    if (matrix.shape != (3, 3) or not np.isfinite(matrix).all()
            or not np.allclose(matrix.T @ matrix, np.eye(3), atol=1e-6, rtol=0)
            or abs(np.linalg.det(matrix) - 1.0) > 1e-6):
        raise ValueError('Expected a finite proper rotation matrix')
    return matrix


def solve(fk, q_seed, target_position, target_rotation_matrix, lower, upper, *,
          max_joint_step_rad, position_tolerance_m=2e-6,
          orientation_tolerance_rad=2e-5, max_iterations=35):
    """Solve one local 7-joint TCP pose and independently verify its final FK.

    ``fk(q)`` returns ``(world_position_m, world_rotation_matrix)`` for the same
    TCP as the target. ``max_joint_step_rad`` is a scalar or a seven-vector;
    zero fixes a joint. The seed must already satisfy the physical limits.

    ``iterations`` counts the bounded optimizer's residual evaluations, capped
    by ``max_iterations``. Central finite-difference Jacobian probes require
    extra FK calls, reported separately as ``fk_evaluations``. Convergence of
    the optimizer alone is insufficient: both declared pose tolerances and all
    joint bounds must pass an additional FK evaluation. Failed results are
    diagnostics only and must not be applied as a successful command.

    The return value contains no NaN/Inf; unavailable pose errors are ``None``.
    No state, files, environment variables, or external services are modified.
    """
    result = dict(q=None, success=False, position_error_m=None,
                  orientation_error_rad=None, iterations=0,
                  fk_evaluations=0, reason='INVALID_INPUT')
    try:
        seed = np.asarray(q_seed, dtype=float)
        lo = np.asarray(lower, dtype=float)
        hi = np.asarray(upper, dtype=float)
        target_p = np.asarray(target_position, dtype=float)
        target_r = _rotation_matrix(target_rotation_matrix)
        step = np.asarray(max_joint_step_rad, dtype=float)
        if step.ndim == 0:
            step = np.full(7, float(step))
        if (not callable(fk) or seed.shape != (7,) or lo.shape != (7,)
                or hi.shape != (7,) or step.shape != (7,)
                or target_p.shape != (3,)
                or not all(np.isfinite(x).all() for x in (seed, lo, hi, step, target_p))
                or np.any(lo > hi) or np.any(step < 0)
                or not np.isfinite(position_tolerance_m) or position_tolerance_m <= 0
                or not np.isfinite(orientation_tolerance_rad) or orientation_tolerance_rad <= 0
                or isinstance(max_iterations, bool) or int(max_iterations) != max_iterations
                or max_iterations < 1):
            return result
        result['q'] = seed.copy()
        if np.any(seed < lo) or np.any(seed > hi):
            result['reason'] = 'SEED_OUTSIDE_JOINT_LIMITS'
            return result
    except (TypeError, ValueError, OverflowError):
        return result

    local_lo = np.maximum(lo, seed - step)
    local_hi = np.minimum(hi, seed + step)
    # scipy requires strict variable bounds. A joint with no representable
    # search interval stays exactly at its already-valid seed value.
    active = np.flatnonzero(local_hi - local_lo > 1e-14)
    best_q = seed.copy()
    best_errors = None
    best_cost = float('inf')

    def pose_errors(q):
        nonlocal best_q, best_errors, best_cost
        result['fk_evaluations'] += 1
        try:
            p, r = fk(q.copy())
            p = np.asarray(p, dtype=float)
            r = _rotation_matrix(r)
            if p.shape != (3,) or not np.isfinite(p).all():
                raise ValueError('Invalid FK position')
            translation = p - target_p
            # Spatial rotation error; both rotations are expressed in world.
            angle_vector = Rotation.from_matrix(target_r @ r.T).as_rotvec()
            pe = float(np.linalg.norm(translation))
            oe = float(np.linalg.norm(angle_vector))
            residual = np.r_[translation / position_tolerance_m,
                             angle_vector / orientation_tolerance_rad]
            if not np.isfinite(residual).all():
                raise ValueError('Nonfinite FK residual')
        except Exception as error:
            raise _InvalidFK('FK evaluation failed') from error
        cost = float(residual @ residual)
        if np.isfinite(cost) and cost < best_cost:
            best_q, best_errors, best_cost = q.copy(), (pe, oe), cost
        return residual, pe, oe

    def finish(q, pe, oe, *, success, reason, iterations=0):
        result.update(q=q.copy(), success=bool(success), position_error_m=float(pe),
                      orientation_error_rad=float(oe), iterations=int(iterations), reason=reason)
        return result

    try:
        _, pe, oe = pose_errors(seed)
        if pe <= position_tolerance_m and oe <= orientation_tolerance_rad:
            return finish(seed, pe, oe, success=True, reason='TARGET_REACHED')
        if not len(active):
            return finish(seed, pe, oe, success=False, reason='NO_LOCAL_JOINT_FREEDOM')

        def unpack(values):
            q = seed.copy()
            q[active] = values
            return q

        def residual(values):
            return pose_errors(unpack(values))[0]

        optimized = least_squares(residual, seed[active], jac='3-point',
            bounds=(local_lo[active], local_hi[active]), method='dogbox',
            ftol=1e-12, xtol=1e-12, gtol=1e-10, max_nfev=int(max_iterations))
        q = unpack(optimized.x)
        _, pe, oe = pose_errors(q)
        # No projection/clipping is allowed here: verify the exact output.
        bounded = bool(np.all(q >= local_lo) and np.all(q <= local_hi))
        if bounded and pe <= position_tolerance_m and oe <= orientation_tolerance_rad:
            return finish(q, pe, oe, success=True, reason='TARGET_REACHED', iterations=optimized.nfev)
        if not bounded:
            reason = 'OPTIMIZER_OUTSIDE_LOCAL_BOUNDS'
        elif optimized.status == 0:
            reason = 'ITERATION_LIMIT'
        elif np.any((q[active] - local_lo[active] < 1e-8)
                    | (local_hi[active] - q[active] < 1e-8)):
            reason = 'LOCAL_BOUNDARY_UNREACHABLE'
        else:
            reason = 'LOCAL_POSE_NOT_REACHED'
        return finish(q, pe, oe, success=False, reason=reason, iterations=optimized.nfev)
    except _InvalidFK:
        result.update(q=best_q.copy(), reason='FK_EVALUATION_FAILED')
        if best_errors is not None:
            result.update(position_error_m=best_errors[0], orientation_error_rad=best_errors[1])
        return result
    except (ValueError, FloatingPointError, OverflowError):
        result.update(q=best_q.copy(), reason='LOCAL_OPTIMIZER_FAILED')
        if best_errors is not None:
            result.update(position_error_m=best_errors[0], orientation_error_rad=best_errors[1])
        return result
