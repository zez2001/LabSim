"""Independent physical-state adjudication for Env_v1 loading and diagnostics.

No teacher stage flag or controller success string is accepted as physical proof.
Unknown measurements stay unknown. Sensor/action completeness is additionally
checked by the collector; this class checks the physical state trace.
"""
from __future__ import annotations

from collections import deque

import numpy as np


NON_PHYSICAL = {
    'GEOMETRY_PRECHECK_BLOCKED', 'GEOMETRY_PREFLIGHT_BLOCKED', 'GEOMETRY_BLOCKED', 'GEOMETRY_BLOCKED_NOT_EXECUTED',
    'INITIALIZATION_INVALID', 'INIT_INVALID', 'SCENE_INVALID', 'MODEL_SERVICE_ERROR',
    'MODEL_ERROR', 'PROCESS_INTERRUPTED', 'PROCESS_ABORT', 'INPUT_CONTRACT_ERROR',
    'PHYSICS_INVALID',
}


def _plain(value):
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(v) for v in value]
    if isinstance(value, np.ndarray):
        return _plain(value.tolist())
    if isinstance(value, np.generic):
        return value.item()
    return value


def _mapping(cfg):
    try:
        from omegaconf import OmegaConf
        if OmegaConf.is_config(cfg):
            return OmegaConf.to_container(cfg, resolve=True)
    except ImportError:
        pass
    return dict(cfg)


def _get(cfg, path, default=None):
    value = cfg
    for part in path.split('.'):
        if not isinstance(value, dict) or part not in value:
            return default
        value = value[part]
    return value


def _known(value):
    try:
        return value is not None and np.isfinite(np.asarray(value, dtype=float)).all()
    except (TypeError, ValueError):
        return False


def _number(row, name):
    value = row.get(name)
    return float(value) if _known(value) and np.asarray(value).ndim == 0 else None


def _vector(row, name, count):
    value = row.get(name)
    return np.asarray(value, float) if _known(value) and np.asarray(value).shape == (count,) else None


def _angle_deg(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    scale = np.linalg.norm(a) * np.linalg.norm(b)
    if scale <= 0 or not np.isfinite(scale):
        return None
    return float(np.degrees(2 * np.arccos(np.clip(abs(np.dot(a, b)) / scale, 0, 1))))


def _rotate_vector(quaternion_wxyz, vector):
    quaternion = np.asarray(quaternion_wxyz, float)
    quaternion /= np.linalg.norm(quaternion)
    w, v = quaternion[0], quaternion[1:]
    vector = np.asarray(vector, float)
    return (w*w-np.dot(v, v))*vector + 2*v*np.dot(v, vector) + 2*w*np.cross(v, vector)


class CuvetteLoadingEnvV1Scorer:
    """One instance per reset; all durations use actual end-of-physics-step t."""

    def __init__(self, cfg, layout, geometry_audit):
        self.cfg, self.layout = _mapping(cfg), _plain(layout)
        self.geometry_audit = dict(geometry_audit or {})
        self.rows, self.events, self.warnings = [], {}, set()
        self.invalid_reasons = set()
        self.initial = None
        self.grasp_reference = None
        self.last_grasp_reference = None
        self.grasp_attempts = []
        self._grasp_release_since = None
        self._grasp_supported = False
        self.near_bottom_z = None
        self._grasp_since = None
        self._open_since = None
        self._jam_window = deque()
        self.max_relative_position_drift_m = 0.0
        self.max_relative_orientation_drift_deg = 0.0
        self.max_grasp_anchor_drift_m = 0.0
        self.max_grasp_anchor_axial_drift_m = 0.0
        self.max_grasp_anchor_transverse_drift_m = 0.0
        self._automatic_failure = None
        self.tolerance_m = float(_get(self.cfg, 'acceptance.steady_source_penetration_m', .00005))

    def _event(self, name, row, **evidence):
        if name not in self.events:
            self.events[name] = dict(t=float(row['t']),
                physics_step=int(row.get('physics_step', len(self.rows) - 1)), **_plain(evidence))

    def _bottom(self, row):
        # source_bottom_z_m is accepted only as the declared actual world-space
        # vessel minimum, never as a fixed source-frame baseline or TCP height.
        return _number(row, 'object_bottom_world_z_m') if row.get('object_bottom_world_z_m') is not None else _number(row, 'source_bottom_z_m')

    def update(self, row):
        row = _plain(dict(row))
        t = _number(row, 't')
        position = _vector(row, 'object_position_m', 3)
        quaternion = _vector(row, 'object_quaternion_wxyz', 4)
        if t is None or position is None or quaternion is None or np.linalg.norm(quaternion) < .5:
            self.invalid_reasons.add('missing_or_nonfinite_required_physical_state')
            self._automatic_failure = 'PHYSICS_INVALID'
            return dict(terminate=True, termination_reason='NONFINITE_OR_MISSING_PHYSICAL_STATE', failure_type='PHYSICS_INVALID')
        if self.rows and t <= self.rows[-1]['t']:
            self.invalid_reasons.add('nonmonotonic_physics_time')
        self.rows.append(row)
        if self.initial is None:
            self.initial = row
        if len(self.rows) > 1:
            previous = _vector(self.rows[-2], 'object_position_m', 3)
            if previous is not None and np.linalg.norm(position - previous) > float(_get(self.cfg, 'demo_release.max_actual_pose_step_m', .003)):
                self._automatic_failure = 'PHYSICS_INVALID'
                self.invalid_reasons.add('actual_object_pose_jump_above_declared_limit')
        for key in ('native_linear_velocity_m_s', 'native_angular_velocity_rad_s',
                    'native_angular_velocity_deg_s', 'usd_linear_velocity_m_s',
                    'usd_angular_velocity_deg_s', 'linear_velocity_native_m_s',
                    'angular_velocity_native_rad_s', 'linear_velocity_USD_m_s',
                    'angular_velocity_USD_deg_s'):
            if row.get(key) is not None and not _known(row[key]):
                self.invalid_reasons.add('nonfinite_' + key)
                self._automatic_failure = 'PHYSICS_INVALID'
        native = _vector(row, 'native_linear_velocity_m_s', 3)
        fd = _vector(row, 'fd_linear_velocity_m_s', 3)
        if native is None:
            native = _vector(row, 'linear_velocity_native_m_s', 3)
        if fd is None:
            fd = _vector(row, 'fd_com_velocity_m_s', 3)
        if native is not None and fd is not None and np.linalg.norm(native-fd) > .05:
            self.warnings.add('NATIVE_FD_LINEAR_VELOCITY_DISAGREEMENT')
        bottom = self._bottom(row)
        table = float(_get(self.cfg, 'scene.table_top_m', self.layout.get('table_top_m', .74)))
        if bottom is not None and bottom < table - .01:
            self._automatic_failure = 'DROPPED'
        source_pen = _number(row, 'source_rack_penetration_m')
        if source_pen is not None and source_pen > self.tolerance_m:
            self.warnings.add('SOURCE_RACK_GEOMETRY_PENETRATION')
        native_pen = _number(row, 'native_target_overlap_m')
        if native_pen is None:
            self.warnings.add('NATIVE_TARGET_OVERLAP_UNAVAILABLE')
        elif native_pen > self.tolerance_m:
            self._automatic_failure = 'PHYSICS_INVALID'
            self.invalid_reasons.add('measured_native_target_overlap_above_declared_limit')
        forces = _vector(row, 'finger_contact_N', 2)
        fingers = _vector(row, 'finger_joint_positions_m', 2)
        if forces is None:
            forces = _vector(row, 'finger_contact_N2', 2)
        if fingers is None:
            fingers = _vector(row, 'finger_joint_positions_m2', 2)
        bilateral = forces is not None and bool(np.all(forces >= .01))
        if bilateral:
            if self._grasp_since is None:
                self._grasp_since = t
            if t - self._grasp_since >= .1:
                self._event('bilateral_grasp_observed', row, actual_force_N=forces)
                relative_q = _vector(row, 'cup_in_hand_quaternion_wxyz', 4)
                if self.grasp_reference is None and _vector(row, 'cup_in_hand_position_m', 3) is not None and relative_q is not None and np.linalg.norm(relative_q) > 1e-9:
                    self.grasp_reference = row
                    self.max_relative_position_drift_m = 0.0
                    self.max_relative_orientation_drift_deg = 0.0
                    self.max_grasp_anchor_drift_m = 0.0
                    self.max_grasp_anchor_axial_drift_m = 0.0
                    self.max_grasp_anchor_transverse_drift_m = 0.0
                    self._grasp_supported = False
        else:
            self._grasp_since = None
        if self.grasp_reference is not None and bilateral and not self._grasp_supported:
            relative = _vector(row, 'cup_in_hand_position_m', 3)
            reference = _vector(self.grasp_reference, 'cup_in_hand_position_m', 3)
            orientation = _vector(row, 'cup_in_hand_quaternion_wxyz', 4)
            qref = _vector(self.grasp_reference, 'cup_in_hand_quaternion_wxyz', 4)
            if relative is not None and reference is not None:
                self.max_relative_position_drift_m = max(self.max_relative_position_drift_m, float(np.linalg.norm(relative-reference)))
            if orientation is not None and qref is not None:
                measured_angle = _angle_deg(orientation, qref)
                if measured_angle is not None:
                    self.max_relative_orientation_drift_deg = max(self.max_relative_orientation_drift_deg, measured_angle)
                else:
                    self.warnings.add('CUP_IN_HAND_QUATERNION_UNAVAILABLE')
            if relative is not None and reference is not None and orientation is not None and qref is not None and np.linalg.norm(orientation) > 0 and np.linalg.norm(qref) > 0:
                height = float(_get(self.cfg, 'robot.grasp_above_bottom_m', .053))
                anchor = relative + _rotate_vector(orientation, [0, 0, height])
                anchor0 = reference + _rotate_vector(qref, [0, 0, height])
                displacement = anchor-anchor0
                axis0 = _rotate_vector(qref, [0, 0, 1])
                axial = float(np.dot(displacement, axis0))
                self.max_grasp_anchor_drift_m = max(self.max_grasp_anchor_drift_m, float(np.linalg.norm(displacement)))
                self.max_grasp_anchor_axial_drift_m = max(self.max_grasp_anchor_axial_drift_m, abs(axial))
                self.max_grasp_anchor_transverse_drift_m = max(self.max_grasp_anchor_transverse_drift_m, float(np.linalg.norm(displacement-axial*axis0)))
        source_rim = self.layout.get('source_rim_z', self.layout.get('source_rim_z_m'))
        initial_bottom = self._bottom(self.initial)
        if 'bilateral_grasp_observed' in self.events and bilateral and bottom is not None and initial_bottom is not None and bottom >= initial_bottom + .001:
            self._event('actual_lift_started', row, actual_lift_m=bottom-initial_bottom)
        if source_rim is not None and bottom is not None and bilateral and 'bilateral_grasp_observed' in self.events and bottom >= float(source_rim) + .002:
            self._event('source_slot_cleared', row, actual_bottom_world_z_m=bottom, source_rim_world_z_m=source_rim)
        initial_position = _vector(self.initial, 'object_position_m', 3)
        if 'source_slot_cleared' in self.events and bilateral and np.linalg.norm(position[:2]-initial_position[:2]) >= .05:
            self._event('held_transport_observed', row, horizontal_displacement_m=float(np.linalg.norm(position[:2]-initial_position[:2])))
        xy = row.get('xy_error_target_m')
        xy_error = (float(np.linalg.norm(np.asarray(xy, float))) if _known(xy) else None)
        depth, tilt = _number(row, 'depth_m'), _number(row, 'tilt_deg')
        yaw_error = _number(row, 'yaw_error_deg')
        if 'held_transport_observed' in self.events and bilateral and xy_error is not None and depth is not None and bottom is not None:
            safe_gap = float(_get(self.cfg, 'control.diagnostic_safe_bottom_above_rim_m', .001))
            budget = float(_get(self.cfg, 'control.diagnostic_alignment_budget_m', .0001))
            if xy_error <= budget and -safe_gap-.002 <= depth <= -.0005:
                self._event('safe_preinsert_observed', row, actual_depth_m=depth, actual_xy_error_m=xy_error)
                self.near_bottom_z = bottom if self.near_bottom_z is None else min(self.near_bottom_z, bottom)
        if 'safe_preinsert_observed' in self.events and bilateral and bottom is not None and self.near_bottom_z is not None and bottom - self.near_bottom_z >= .008:
            self._event('diagnostic_up_retract_observed', row, actual_upward_motion_m=bottom-self.near_bottom_z)
        requested_depth = float(_get(self.cfg, 'geometry.target_depth_m',
            _get(self.cfg, 'geometry.depth_m', self.layout.get('target_depth_m', .027))))
        bottom_gap = _number(row, 'target_bottom_gap_m')
        support = _number(row, 'target_bottom_support_N')
        target_inside = row.get('target_region_contains_object')
        aligned = (xy_error is not None and xy_error <= float(_get(self.cfg, 'control.alignment_budget_m', .000015))
            and tilt is not None and abs(tilt) <= float(_get(self.cfg, 'control.tilt_budget_deg', .02))
            and yaw_error is not None and abs(yaw_error) <= float(_get(self.cfg, 'control.yaw_budget_deg', .1)))
        at_bottom_pose = (depth is not None and depth >= requested_depth - self.tolerance_m
            and bottom_gap is not None and abs(bottom_gap) <= float(_get(self.cfg, 'demo_release.bottom_distance_m', .00005)))
        at_bottom = at_bottom_pose and support is not None and support >= float(_get(self.cfg, 'demo_release.min_support_N', .1))
        if 'held_transport_observed' in self.events and aligned and at_bottom_pose:
            self._event('loaded_pose_candidate', row, actual_depth_m=depth,
                        measured_bottom_support_N=support, target_region_contains_object=target_inside)
            self._grasp_supported = True
        if 'held_transport_observed' in self.events and aligned and at_bottom:
            self._event('loaded_supported_candidate', row, actual_depth_m=depth,
                classified_bottom_support_N=support, target_region_contains_object=target_inside)
            if target_inside is True:
                self._event('correct_target_supported', row)
        open_min = float(_get(self.cfg, 'scorer.finger_joint_open_min_m', float(_get(self.cfg, 'vessel.outer_xy_m', [.0125])[0]) / 2 + .001))
        detached = (forces is not None and fingers is not None and np.all(forces < .01) and np.all(fingers >= open_min))
        # Explicit physical opening/loss of both contacts ends one grasp attempt.
        # A later measured bilateral regrasp creates a fresh bounded reference;
        # prior attempts remain recorded rather than permanently vetoing retries.
        if detached and self.grasp_reference is not None:
            if self._grasp_release_since is None:
                self._grasp_release_since = t
            if t-self._grasp_release_since >= .2:
                self.grasp_attempts.append(dict(start_t=self.grasp_reference['t'], end_t=t,
                    maximum_position_drift_m=self.max_relative_position_drift_m,
                    maximum_orientation_drift_deg=self.max_relative_orientation_drift_deg,
                    maximum_configured_grasp_anchor_drift_m=self.max_grasp_anchor_drift_m,
                    ended_by='measured_fingers_open_and_both_contacts_lost'))
                self.last_grasp_reference = self.grasp_reference
                self.grasp_reference = None
                self._grasp_release_since = None
        else:
            self._grasp_release_since = None
        if 'loaded_pose_candidate' in self.events and detached:
            if self._open_since is None:
                self._open_since = t
            if t - self._open_since >= .05:
                self._event('both_fingers_open_and_detached', row, actual_joint_positions_m=fingers, actual_force_N=forces)
        else:
            self._open_since = None
        clearance = _number(row, 'gripper_object_clearance_m')
        if 'both_fingers_open_and_detached' in self.events and clearance is not None and clearance >= float(_get(self.cfg, 'acceptance.actual_retreat_clearance_m', .04)):
            self._event('actual_gripper_retreat', row, minimum_gripper_object_clearance_m=clearance)
        self._update_jam(row)
        failure = self._automatic_failure
        return dict(terminate=failure is not None, termination_reason=failure,
                    failure_type=failure, observed_events=list(self.events))

    def _update_jam(self, row):
        t = float(row['t'])
        self._jam_window.append(row)
        duration = float(_get(self.cfg, 'control.jam_detection.window_s', .3))
        while self._jam_window and t - self._jam_window[0]['t'] > duration + .02:
            self._jam_window.popleft()
        if len(self._jam_window) < 2 or t - self._jam_window[0]['t'] < duration:
            return
        first = self._jam_window[0]
        commanded = _number(row, 'commanded_bottom_z_m')
        old_commanded = _number(first, 'commanded_bottom_z_m')
        actual, old_actual = self._bottom(row), self._bottom(first)
        if all(v is not None for v in (commanded, old_commanded, actual, old_actual)):
            down_command = old_commanded-commanded
            down_actual = old_actual-actual
            if down_command >= float(_get(self.cfg, 'control.jam_detection.command_down_min_m', .00015)) and down_actual <= float(_get(self.cfg, 'control.jam_detection.vessel_down_max_m', .000025)):
                wall = _number(row, 'wall_contact_N')
                if wall is not None and wall > .01:
                    self._event('actual_contact_stall_observed', row,
                        commanded_down_m=down_command, measured_down_m=down_actual, classified_wall_contact_N=wall)
                    self.warnings.add('CONTACT_STALL_DETECTED')
                    # The environment/controller may retract and legally retry;
                    # observing a jam is not an irrevocable task-failure label.

    def _window(self, rows, required_s, *, supported=False):
        if len(rows) < 2:
            return dict(status='incomplete', stable=None, required_duration_s=required_s,
                        measured_duration_s=0.0 if rows else None, sample_count=len(rows))
        duration = float(rows[-1]['t']-rows[0]['t'])
        positions = np.asarray([r['object_position_m'] for r in rows], float)
        drift = float(np.linalg.norm(positions-positions[0], axis=1).max())
        angles = [_angle_deg(r['object_quaternion_wxyz'], rows[0]['object_quaternion_wxyz']) for r in rows]
        orientation = max(a for a in angles if a is not None)
        complete = duration + 1e-8 >= required_s
        stable = bool(drift <= float(_get(self.cfg, 'demo_release.position_drift_m', .0002))
                      and orientation <= float(_get(self.cfg, 'demo_release.orientation_change_deg', 1)))
        criteria = dict(position_stable=stable, target_support=None, target_contains=None,
                        native_overlap_within_limit=None, no_finger_contact=None)
        if supported:
            support = [_number(r, 'target_bottom_support_N') for r in rows]
            gaps = [_number(r, 'target_bottom_gap_m') for r in rows]
            overlap = [_number(r, 'native_target_overlap_m') for r in rows]
            forces = [_vector(r, 'finger_contact_N', 2) if r.get('finger_contact_N') is not None else _vector(r, 'finger_contact_N2', 2) for r in rows]
            criteria['target_support'] = (all(v >= float(_get(self.cfg, 'demo_release.min_support_N', .1)) for v in support)
                and all(abs(v) <= float(_get(self.cfg, 'demo_release.bottom_distance_m', .00005)) for v in gaps)) if all(v is not None for v in support+gaps) else None
            contains = [r.get('target_region_contains_object') for r in rows]
            criteria['target_contains'] = all(v is True for v in contains) if all(v is not None for v in contains) else None
            criteria['native_overlap_within_limit'] = all(v <= self.tolerance_m for v in overlap) if all(v is not None for v in overlap) else None
            criteria['no_finger_contact'] = all(np.all(v < .01) for v in forces) if all(v is not None for v in forces) else None
            tilts = [_number(r, 'tilt_deg') for r in rows]
            depths = [_number(r, 'depth_m') for r in rows]
            requested = float(_get(self.cfg, 'geometry.target_depth_m',
                _get(self.cfg, 'geometry.depth_m', self.layout.get('target_depth_m', .027))))
            criteria['upright'] = all(abs(v) <= float(_get(self.cfg, 'acceptance.upright_after_release_deg', 1)) for v in tilts) if all(v is not None for v in tilts) else None
            criteria['retained_loading_depth'] = all(v >= requested-self.tolerance_m for v in depths) if all(v is not None for v in depths) else None
            if any(v is False for v in criteria.values()):
                stable = False
            elif any(v is None for v in criteria.values()):
                stable = None
        return dict(status='complete' if complete else 'incomplete',
                    stable=stable if complete else None, required_duration_s=required_s,
                    measured_duration_s=duration, sample_count=len(rows),
                    position_drift_m=drift, orientation_change_deg=orientation,
                    criteria=criteria, start_t=float(rows[0]['t']), end_t=float(rows[-1]['t']))

    @staticmethod
    def _tail(rows, duration):
        if not rows:
            return rows
        cutoff = rows[-1]['t'] - duration
        before = [i for i, row in enumerate(rows) if row['t'] <= cutoff + 1e-10]
        return rows[before[-1]:] if before else rows

    def _grasp_segments(self):
        definitions = (
            ('static_grasp', 'bilateral_grasp_observed', 'actual_lift_started'),
            ('extraction', 'actual_lift_started', 'source_slot_cleared'),
            ('transport', 'source_slot_cleared', 'safe_preinsert_observed'))
        result = {}
        for name, first, last in definitions:
            if first not in self.events or last not in self.events:
                result[name] = dict(status='unavailable', reference_position_drift_m=None,
                                    reference_orientation_drift_deg=None)
                continue
            rows = [r for r in self.rows if self.events[first]['t'] <= r['t'] <= self.events[last]['t']]
            pairs = [(r, _vector(r, 'cup_in_hand_position_m', 3),
                      _vector(r, 'cup_in_hand_quaternion_wxyz', 4)) for r in rows]
            known = [(r, p, q) for r, p, q in pairs if p is not None and q is not None and np.linalg.norm(q) > 0]
            if not known:
                result[name] = dict(status='unavailable', reference_position_drift_m=None,
                                    reference_orientation_drift_deg=None)
                continue
            p0, q0 = known[0][1:]
            result[name] = dict(status='measured', start_t=known[0][0]['t'], end_t=known[-1][0]['t'],
                sample_count=len(known), reference_position_drift_m=max(float(np.linalg.norm(p-p0)) for _, p, _ in known),
                reference_orientation_drift_deg=max(_angle_deg(q, q0) for _, _, q in known),
                boundary_definition='Independent observed physical lift/source-clear/near-target events; teacher phase ignored')
        return result

    def _held_window(self, rows, duration):
        window_rows = self._tail(rows, duration)
        window = self._window(window_rows, duration)
        forces = [_vector(r, 'finger_contact_N', 2) if r.get('finger_contact_N') is not None else _vector(r, 'finger_contact_N2', 2) for r in window_rows]
        bilateral = (all(np.all(force >= .01) for force in forces)
                     if window_rows and all(force is not None for force in forces) else None)
        window.setdefault('criteria', {})['bilateral_contact_during_hold'] = bilateral
        if window['status'] == 'complete':
            if bilateral is False:
                window['stable'] = False
            elif bilateral is None and window['stable'] is not False:
                window['stable'] = None
        return window, window_rows

    def finalize(self, episode_id, task_type, termination_reason=None, failure_type=None):
        task_type = str(task_type)
        is_loading = task_type == 'loading'
        failure_type = str(failure_type or self._automatic_failure or 'NONE').upper()
        termination_reason = str(termination_reason or self._automatic_failure or 'EPISODE_ENDED')
        record_valid = bool(len(self.rows) >= 2 and not self.invalid_reasons and failure_type not in NON_PHYSICAL)
        if self.rows:
            end = float(self.rows[-1]['t'])
            terminal = self._window(self._tail(self.rows, 3.0), 3.0)
        else:
            terminal = dict(status='unavailable', stable=None, sample_count=0)
        retreat = self.events.get('actual_gripper_retreat')
        if retreat is None:
            post_retreat = dict(status='unavailable', stable=None, sample_count=0,
                                reason='actual_gripper_retreat_not_observed')
        else:
            observe_s = float(_get(self.cfg, 'demo_release.observe_s', 3))
            post_retreat = self._window(self._tail(
                [r for r in self.rows if r['t'] >= retreat['t']], observe_s), observe_s, supported=True)
        grip_pos_limit = float(_get(self.cfg, 'gripper.max_relative_position_drift_m', .0002))
        grip_angle_limit = float(_get(self.cfg, 'gripper.max_relative_orientation_drift_deg', 1))
        relative_measured = self.grasp_reference is not None or self.last_grasp_reference is not None
        grasp_stable = bool('bilateral_grasp_observed' in self.events and relative_measured
            and self.max_relative_position_drift_m <= grip_pos_limit
            and self.max_relative_orientation_drift_deg <= grip_angle_limit)
        required = ('bilateral_grasp_observed', 'source_slot_cleared',
            'held_transport_observed', 'correct_target_supported',
            'both_fingers_open_and_detached', 'actual_gripper_retreat')
        loading_sequence = all(k in self.events for k in required)
        loading_candidate_sequence = all(k in self.events for k in (
            'bilateral_grasp_observed', 'source_slot_cleared', 'held_transport_observed',
            'loaded_pose_candidate', 'both_fingers_open_and_detached', 'actual_gripper_retreat'))
        geometry_valid = self.geometry_audit.get('geometry_valid')
        if isinstance(geometry_valid, np.bool_):
            geometry_valid = bool(geometry_valid)
        if not isinstance(geometry_valid, bool):
            geometry_valid = None
        if is_loading:
            if not loading_candidate_sequence or not grasp_stable or post_retreat['status'] != 'complete' or post_retreat['stable'] is False:
                task_success = False
            elif geometry_valid is False:
                task_success = False
            elif geometry_valid is None or post_retreat['stable'] is None:
                task_success = None
            else:
                task_success = bool(record_valid and loading_sequence and post_retreat['stable'])
            diagnostic_window = dict(status='not_applicable', stable=None)
        elif task_type == 'grasp_hold':
            grasp = self.events.get('bilateral_grasp_observed')
            if grasp is None:
                diagnostic_window = dict(status='unavailable', stable=None,
                    reason='actual_bilateral_grasp_not_observed')
            else:
                duration = float(_get(self.cfg, 'scorer.subtask_hold_s', 3))
                diagnostic_window, hold_rows = self._held_window(
                    [r for r in self.rows if r['t'] >= grasp['t']], duration)
                occupancy = [r.get('source_reference_inside') for r in hold_rows]
                in_rack = (all(v is True for v in occupancy)
                           if hold_rows and all(isinstance(v, bool) for v in occupancy) else None)
                diagnostic_window.setdefault('criteria', {})['source_rack_occupancy'] = in_rack
                if diagnostic_window['status'] == 'complete':
                    if in_rack is False:
                        diagnostic_window['stable'] = False
                    elif in_rack is None and diagnostic_window['stable'] is not False:
                        diagnostic_window['stable'] = None
            if not grasp_stable or diagnostic_window['status'] != 'complete' or diagnostic_window['stable'] is False or grasp is None:
                task_success = False
            elif diagnostic_window['stable'] is None:
                task_success = None
            else:
                task_success = bool(record_valid and diagnostic_window['stable'])
        elif task_type == 'extract_transport':
            transport = self.events.get('held_transport_observed')
            if transport is None:
                diagnostic_window = dict(status='unavailable', stable=None,
                    reason='actual_source_clear_and_held_transport_not_observed')
            else:
                duration = float(_get(self.cfg, 'scorer.subtask_hold_s', 3))
                diagnostic_window, hold_rows = self._held_window(
                    [r for r in self.rows if r['t'] >= transport['t']], duration)
                xy_errors = [r.get('xy_error_target_m') for r in hold_rows]
                near_target = (all(np.linalg.norm(np.asarray(value, float)) <= float(_get(self.cfg, 'scorer.transport_target_xy_budget_m', .003)) for value in xy_errors)
                    if hold_rows and all(_known(value) for value in xy_errors) else None)
                diagnostic_window.setdefault('criteria', {})['transport_above_target_xy'] = near_target
                bottoms = [self._bottom(r) for r in hold_rows]
                rim = self.layout.get('target_rim_z')
                above_rim = (all(v >= float(rim)+.0005 for v in bottoms)
                    if rim is not None and hold_rows and all(v is not None for v in bottoms) else None)
                diagnostic_window['criteria']['above_target_rim'] = above_rim
                if diagnostic_window['status'] == 'complete':
                    if near_target is False or above_rim is False:
                        diagnostic_window['stable'] = False
                    elif (near_target is None or above_rim is None) and diagnostic_window['stable'] is not False:
                        diagnostic_window['stable'] = None
            if not grasp_stable or diagnostic_window['status'] != 'complete' or diagnostic_window['stable'] is False or transport is None or 'source_slot_cleared' not in self.events:
                task_success = False
            elif diagnostic_window['stable'] is None:
                task_success = None
            else:
                task_success = bool(record_valid and diagnostic_window['stable'])
        elif task_type == 'preinsert_diagnostic':
            up = self.events.get('diagnostic_up_retract_observed')
            if up is None:
                diagnostic_window = dict(status='unavailable', stable=None,
                    reason='physical_diagnostic_up_retract_not_observed')
            else:
                hold_s = float(_get(self.cfg, 'acceptance.hold_s', 1))
                diagnostic_window, _ = self._held_window(
                    [r for r in self.rows if r['t'] >= up['t']], hold_s)
            task_success = bool(record_valid and grasp_stable
                and all(k in self.events for k in ('source_slot_cleared',
                    'held_transport_observed', 'safe_preinsert_observed',
                    'diagnostic_up_retract_observed')) and diagnostic_window['stable'] is True)
        else:
            diagnostic_window = dict(status='unavailable', stable=None, reason='unknown_task_type')
            task_success, record_valid, failure_type = None, False, 'INPUT_CONTRACT_ERROR'
        if failure_type in NON_PHYSICAL:
            task_success = None
        if failure_type == 'NONE' and task_success is False:
            if 'actual_contact_stall_observed' in self.events:
                failure_type = 'BLOCKED'
            elif relative_measured and not grasp_stable:
                failure_type = 'GRASP_SLIP'
            elif loading_sequence and post_retreat['stable'] is False:
                failure_type = 'UNSTABLE_AFTER_RELEASE'
            else:
                failure_type = 'TASK_INCOMPLETE'
        stable_after = post_retreat['stable'] if post_retreat['status'] == 'complete' else None
        full_success = task_success if is_loading else None
        score = dict(schema='labsim.Env_v1.independent_physical.v1', episode_id=str(episode_id),
            task_type=task_type, geometry_valid=geometry_valid, task_success=task_success,
            workflow_success=full_success, full_success=full_success,
            native_pair_success=full_success if is_loading and geometry_valid is True else None,
            record_valid=record_valid, record_valid_scope='physics-state trace; collector additionally verifies action/sensor/time integrity',
            failure_type=failure_type, termination_reason=termination_reason,
            eligible_for_success_bc=bool(record_valid and task_success is True and is_loading and geometry_valid is True),
            eligible_for_failure_analysis=bool(record_valid and task_success is False and is_loading and failure_type not in NON_PHYSICAL),
            real_calibrated=bool(_get(self.cfg, 'calibrated', False)),
            source_slot_cleared='source_slot_cleared' in self.events,
            grasp_success=grasp_stable,
            transport_success=bool(grasp_stable and 'held_transport_observed' in self.events),
            loading_sequence_observed=loading_sequence,
            loading_candidate_sequence_observed=loading_candidate_sequence,
            release_observed='both_fingers_open_and_detached' in self.events,
            retreat_observed=retreat is not None,
            stable_after_retreat=stable_after,
            post_retreat_window=post_retreat, terminal_window=terminal,
            diagnostic_hold_window=diagnostic_window,
            grasp_relative_pose=dict(reference_available=relative_measured,
                maximum_position_drift_m=self.max_relative_position_drift_m if relative_measured else None,
                maximum_orientation_drift_deg=self.max_relative_orientation_drift_deg if relative_measured else None,
                maximum_configured_grasp_anchor_drift_m=self.max_grasp_anchor_drift_m if relative_measured else None,
                maximum_configured_grasp_anchor_axial_drift_m=self.max_grasp_anchor_axial_drift_m if relative_measured else None,
                maximum_configured_grasp_anchor_transverse_drift_m=self.max_grasp_anchor_transverse_drift_m if relative_measured else None,
                configured_grasp_anchor_height_m=float(_get(self.cfg, 'robot.grasp_above_bottom_m', .053)),
                position_reference='Vessel bottom-frame origin in hand frame; includes rotation lever-arm motion, not isolated axial slip.',
                anchor_reference='Configured body point[0,0,grasp_height] in hand frame, not measured contact pressure centre. Anchor metrics are analysis only; existing acceptance gates unchanged.',
                position_limit_m=grip_pos_limit, orientation_limit_deg=grip_angle_limit),
            measured_grasp_segments=self._grasp_segments(),
            grasp_attempts=self.grasp_attempts,
            retry_count=max(0, len(self.grasp_attempts) + int(self.grasp_reference is not None) - 1),
            physics_quality_flags=sorted(self.warnings), invalid_state_reasons=sorted(self.invalid_reasons),
            observed_events=self.events, physical_sample_count=len(self.rows),
            simulation_duration_s=float(self.rows[-1]['t']-self.rows[0]['t']) if len(self.rows) >= 2 else None,
            stage_labels_used_as_success_proof=False,
            geometry_audit_fingerprint=self.geometry_audit.get('binding', {}).get('fingerprint'))
        return _plain(score)


LabCuvetteEnvV1Scorer = CuvetteLoadingEnvV1Scorer
