"""Deterministic, full-pose free-space diagnostic plans; no simulator imports.

Only robot poses are accepted. Plans are not GPT policies and do not certify
collision-free reachability. The runner must reset between the three episodes,
use fresh observation/action identities and keep the existing runtime guards.
"""
from __future__ import annotations

import copy
import math

import numpy as np
from scipy.spatial.transform import Rotation

AMPLITUDES_M = (.001, .005, .020, .040)
POSITION_TOLERANCE_M = .00075
ORIENTATION_TOLERANCE_RAD = .002
LINEAR_SPEED_M_S = .015
ANGULAR_SPEED_RAD_S = .1
MAX_RETURN_TRANSLATION_M = .025
MAX_RETURN_ROTATION_RAD = .1


def _pose(value):
    p = np.asarray(value['position_m'], dtype=float)
    q = np.asarray(value['quaternion_wxyz'], dtype=float)
    if p.shape != (3,) or q.shape != (4,) or not np.isfinite(np.r_[p, q]).all():
        raise ValueError('Robot pose requires finite xyz and wxyz')
    norm = float(np.linalg.norm(q))
    if abs(norm - 1) > 1e-6:
        raise ValueError('Robot pose requires a unit wxyz quaternion')
    return dict(position_m=p.tolist(), quaternion_wxyz=(q / norm).tolist())


def _rotation(pose):
    return Rotation.from_quat(np.roll(pose['quaternion_wxyz'], -1))


def _hz(value):
    if not math.isfinite(float(value)) or int(value) != float(value) or int(value) < 1:
        raise ValueError('control_hz must be a positive integer')
    return int(value)


def _duration(distance_m, angle_rad, control_hz):
    seconds = max(.3, distance_m / LINEAR_SPEED_M_S, angle_rad / ANGULAR_SPEED_RAD_S)
    return math.ceil(seconds * control_hz - 1e-12) / control_hz


def anchor_pose_error(actual_pose, anchor_pose, *, position_tolerance_m=POSITION_TOLERANCE_M,
                      orientation_tolerance_rad=ORIENTATION_TOLERANCE_RAD):
    """Check both xyz and orientation; quaternion signs are physically equivalent."""
    actual, anchor = _pose(actual_pose), _pose(anchor_pose)
    if not np.isfinite([position_tolerance_m, orientation_tolerance_rad]).all() or min(
            position_tolerance_m, orientation_tolerance_rad) < 0:
        raise ValueError('Anchor tolerances must be finite and nonnegative')
    p_error = float(np.linalg.norm(np.asarray(actual['position_m']) - anchor['position_m']))
    r_error = float((_rotation(anchor) * _rotation(actual).inv()).magnitude())
    return dict(position_error_m=p_error, orientation_error_rad=r_error,
        position_tolerance_m=float(position_tolerance_m), orientation_tolerance_rad=float(orientation_tolerance_rad),
        reached=bool(p_error <= position_tolerance_m and r_error <= orientation_tolerance_rad))


def anchor_return_commands(current_pose, anchor_pose, *, control_hz=60):
    """Bounded absolute full-pose commands, using one fixed observed start.

    Recompute this path from a fresh robot observation for each return. Return
    segments leave margin below the facade's 40 mm / 0.15 rad per-action limits,
    including a 40 mm probe's possible tracking residual. The last command has
    the exact fixed anchor xyz+wxyz; orientation is never dropped.
    """
    start, anchor = _pose(current_pose), _pose(anchor_pose)
    hz = _hz(control_hz)
    p0, p1 = np.asarray(start['position_m']), np.asarray(anchor['position_m'])
    r0, r1 = _rotation(start), _rotation(anchor)
    dp = p1 - p0
    dr = (r1 * r0.inv()).as_rotvec()
    count = max(1, math.ceil(np.linalg.norm(dp) / MAX_RETURN_TRANSLATION_M - 1e-12),
        math.ceil(np.linalg.norm(dr) / MAX_RETURN_ROTATION_RAD - 1e-12))
    commands = []
    duration = _duration(float(np.linalg.norm(dp)) / count, float(np.linalg.norm(dr)) / count, hz)
    for index in range(count):
        fraction = (index + 1) / count
        position = (p0 + fraction * dp).tolist()
        quaternion = np.roll((Rotation.from_rotvec(fraction * dr) * r0).as_quat(), 1).tolist()
        if index == count - 1:
            position, quaternion = anchor['position_m'], anchor['quaternion_wxyz']
        commands.append(dict(tool='move_ee', arguments=dict(mode='ee_pose',
            values=position + quaternion, frame='world', duration_s=duration)))
    return commands


def _expected_endpoint(anchor, delta, frame):
    offset = np.asarray(delta) if frame == 'world' else _rotation(anchor).apply(delta)
    return dict(position_m=(np.asarray(anchor['position_m']) + offset).tolist(),
        quaternion_wxyz=list(anchor['quaternion_wxyz']))


def _episode(pose_id, frame, reset_pose, anchor, control_hz):
    anchor_rule = dict(kind='return_anchor', pose=copy.deepcopy(anchor),
        position_tolerance_m=POSITION_TOLERANCE_M, orientation_tolerance_rad=ORIENTATION_TOLERANCE_RAD,
        failed_anchor_action='stop_or_mark_probe_unavailable; never silently use xyz-only arrival')
    probes = []
    current = copy.deepcopy(anchor)
    # Entry and each subsequent return are computed from the measured pose by
    # the runner. These nominal calculations only estimate simulation duration.
    nominal_duration = sum(c['arguments']['duration_s'] for c in
        anchor_return_commands(reset_pose, anchor, control_hz=control_hz))
    for amplitude in AMPLITUDES_M:
        for axis, axis_name in enumerate(('X', 'Y', 'Z')):
            for sign in (1, -1):
                delta = np.zeros(3)
                delta[axis] = sign * amplitude
                duration = _duration(amplitude, 0., control_hz)
                endpoint = _expected_endpoint(anchor, delta, frame)
                probes.append(dict(probe_id=f'{pose_id}_{frame}_{axis_name}_{"plus" if sign > 0 else "minus"}_{amplitude*1000:g}mm',
                    axis=axis_name, sign=sign, amplitude_m=amplitude, frame=frame,
                    return_before=copy.deepcopy(anchor_rule),
                    action=dict(tool='move_ee', arguments=dict(mode='ee_delta', values=delta.tolist() + [0., 0., 0.],
                        frame=frame, duration_s=duration)),
                    delta_start_semantics='one actual observation captured after full-pose return; fixed throughout action',
                    expected_endpoint_if_exact_anchor=endpoint,
                    record_actual_start_and_anchor_residual=True))
                nominal_duration += sum(c['arguments']['duration_s'] for c in
                    anchor_return_commands(current, anchor, control_hz=control_hz)) + duration
                current = endpoint
    epilogue = [copy.deepcopy(anchor_rule),
        dict(kind='tool', tool='wait', arguments=dict(duration_s=1.)),
        dict(kind='tool', tool='gripper', arguments=dict(opening_m=.06, effort_limit_N=5., duration_s=1.)),
        dict(kind='tool', tool='gripper', arguments=dict(opening_m=.08, effort_limit_N=5., duration_s=1.)),
        copy.deepcopy(anchor_rule),
        dict(kind='tool', role='absolute_anchor_hold', tool='move_ee', arguments=dict(mode='ee_pose',
            values=anchor['position_m'] + anchor['quaternion_wxyz'], frame='world', duration_s=3.))]
    nominal_duration += sum(c['arguments']['duration_s'] for c in
        anchor_return_commands(current, anchor, control_hz=control_hz))
    nominal_duration += 1. + 1. + 1. + _duration(0., 0., control_hz) + 3.
    return dict(episode_id=f'{pose_id}_{frame}', pose_id=pose_id, probe_frame=frame,
        reset_before_episode=True, expected_reset_pose=copy.deepcopy(reset_pose), anchor_pose=copy.deepcopy(anchor),
        enter_anchor=copy.deepcopy(anchor_rule), probes=probes, epilogue=epilogue,
        estimated_nominal_simulation_seconds=nominal_duration,
        estimate_excludes_retries_and_reset_settling=True)


def build_free_space_plan(pose0, pose1, *, control_hz=60, episode_timeout_s=170.):
    """Return three independent episodes, each with 24 signed translation probes.

    Both supplied anchor poses are explicit immutable design values. A runner
    may derive pose1 once from the initial robot pose, then must preserve that
    same xyz+wxyz in all episodes and save it. Do not derive a new anchor from
    each action's drifted orientation or join these groups into one episode.
    """
    p0, p1 = _pose(pose0), _pose(pose1)
    hz = _hz(control_hz)
    if not math.isfinite(float(episode_timeout_s)) or episode_timeout_s <= 0:
        raise ValueError('episode_timeout_s must be positive and finite')
    episodes = [_episode('pose0', 'world', p0, p0, hz), _episode('pose1', 'world', p0, p1, hz),
        _episode('pose1', 'tcp', p0, p1, hz)]
    if any(e['estimated_nominal_simulation_seconds'] >= episode_timeout_s for e in episodes):
        raise ValueError('Nominal diagnostic episode exceeds timeout; do not merge or truncate groups')
    return dict(schema='labsim.Project_v1_1.fixed_pose_free_space_plan.v1', control_hz=hz,
        diagnostic_not_GPT_run=True, object_truth_used=False, model_calls=0,
        existing_runtime_guards_required=True, runtime_deadline_is_runner_responsibility=True,
        episode_timeout_s=float(episode_timeout_s),
        delta_reference='actual observed start, fixed for one action; expected endpoint also recorded relative to immutable anchor',
        position_tolerance_m=POSITION_TOLERANCE_M, orientation_tolerance_rad=ORIENTATION_TOLERANCE_RAD,
        episodes=episodes)
