"""Phase-motion clock and source-constrained grasp teacher adapter.

Only four smooth motion phases are slowed. Physics, scorer, 60 Hz actions and
physical contact timers are unchanged. An open-hand approach aligns to the
configured orientation; GRASP holds it with optional near-contact slow closure.
EXTRACT keeps the nominal lateral lift axis. Support transfer retains bounded
pose feedback and pauses only its unloading schedule outside the scorer budget.
"""
from __future__ import annotations

import copy
import math

import numpy as np
from scipy.spatial.transform import Rotation

from controllers.lab_cuvette_env_v1_controller import LabCuvetteTeacher, get, wxyz


class LabCuvetteProjectV11Teacher(LabCuvetteTeacher):
    VERSION = 'Project_v1_1.teacher_phase_motion_clock.v7'
    SLOWED_PHASES = frozenset(('APPROACH_SOURCE', 'EXTRACT', 'TRANSPORT', 'RETREAT'))
    NEAR_CONTACT_MARGIN_M = .002

    def __init__(self, cfg, layout):
        self.motion_time_scale = float(get(cfg, 'teacher_execution.motion_time_scale', 1.5))
        if not math.isfinite(self.motion_time_scale) or self.motion_time_scale < 1:
            raise ValueError('teacher_execution.motion_time_scale must be finite and at least 1')
        try:
            dimensions = tuple(float(v) for v in get(cfg, 'vessel.outer_xy_m'))
        except (TypeError, ValueError):
            raise ValueError('vessel.outer_xy_m must contain two finite positive nominal dimensions') from None
        if len(dimensions) != 2 or any(not math.isfinite(v) or v <= 0 for v in dimensions):
            raise ValueError('vessel.outer_xy_m must contain two finite positive nominal dimensions')
        self.nominal_vessel_outer_width_m = max(dimensions)
        self.near_contact_close_threshold_m = self.nominal_vessel_outer_width_m + self.NEAR_CONTACT_MARGIN_M
        self.near_contact_close_speed_m_s = float(get(cfg, 'gripper.contact_approach_speed_m_s', .002))
        if not math.isfinite(self.near_contact_close_speed_m_s) or self.near_contact_close_speed_m_s <= 0:
            raise ValueError('gripper.contact_approach_speed_m_s must be finite and positive')
        self.near_contact_slow_close_enabled = get(cfg, 'teacher_execution.near_contact_slow_close_enabled', True)
        if not isinstance(self.near_contact_slow_close_enabled, bool):
            raise ValueError('teacher_execution.near_contact_slow_close_enabled must be boolean')
        try:
            yaw = float(get(cfg, 'robot.gripper_yaw_deg', -90.))
            self.approach_orientation_duration_s = float(get(cfg, 'control.approach_s', 6.))
        except (TypeError, ValueError):
            raise ValueError('Approach yaw and duration must be finite numbers') from None
        if not math.isfinite(yaw) or not math.isfinite(self.approach_orientation_duration_s) or self.approach_orientation_duration_s <= 0:
            raise ValueError('Approach yaw must be finite and duration must be positive')
        # Same extrinsic XYZ convention as make_scene/plan_arm: Rz(yaw) Rx(pi).
        # This target is a static robot configuration, never a measured cup pose.
        self.approach_orientation_goal = Rotation.from_euler('xyz', [math.pi, 0., math.radians(yaw)])
        super().__init__(cfg, layout)

    def reset(self, public_obs=None, debug=None):
        super().reset(public_obs, debug)
        self._clock_last_actual = None
        self._clock_phase = self.phase
        self._phase_motion_elapsed = 0.
        self.controller_motion_clock_s = 0.
        self._clock_cached_action = None
        self._grasp_orientation_feedback_suppressed = False
        self._extract_lateral_feedback_suppressed = False
        self._approach_orientation_start = None
        self._approach_orientation_progress = 0.
        self._approach_orientation_fraction = 0.
        self._support_physical_start = None
        self._support_last_actual = None
        self._support_previous_aligned = None
        self._support_unload_elapsed_s = 0.
        self._support_gate_context = None
        return self

    def _feedback(self, debug, desired_cup_xy=None, *, orientation=True):
        # Rotating a closed hand while the cup remains rack-constrained can
        # move its bottom about the grasp anchor. Reorient after extraction,
        # using the unchanged TRANSPORT/ALIGN feedback, not during GRASP.
        if self.phase == 'GRASP' and orientation:
            self._grasp_orientation_feedback_suppressed = True
            orientation = False
        if self.phase == 'EXTRACT' and desired_cup_xy is not None:
            # A source-supported bottom can pivot about the fingers. Chasing
            # that bottom with lateral hand corrections during a nominally
            # vertical lift changes the load transfer. Keep the existing lift
            # axis; resume the parent's XY feedback during TRANSPORT/ALIGN.
            # This is a teacher-only A/B, not an established physical fix.
            self._extract_lateral_feedback_suppressed = True
            desired_cup_xy = None
        return super()._feedback(debug, desired_cup_xy, orientation=orientation)

    def _support_alignment(self, debug):
        """Same actual-state alignment quantities and norms as the scorer.

        This is explicitly private truth-teacher control. Missing/nonfinite
        measurements pause unloading rather than silently counting as aligned.
        The independent scorer still owns every task-success label.
        """
        budgets = dict(xy_m=float(get(self.cfg, 'control.alignment_budget_m', .000015)),
            tilt_deg=float(get(self.cfg, 'control.tilt_budget_deg', .02)),
            yaw_deg=float(get(self.cfg, 'control.yaw_budget_deg', .1)))
        reasons = []
        try:
            xy = np.asarray(debug.get('xy_error_target_m'), dtype=float)
            xy_error = float(np.linalg.norm(xy)) if xy.shape == (2,) and np.isfinite(xy).all() else None
        except (TypeError, ValueError):
            xy_error = None
        measured = dict(xy_m=xy_error)
        for name, key in (('tilt_deg', 'tilt_deg'), ('yaw_deg', 'yaw_error_deg')):
            try:
                value = float(debug[key])
                measured[name] = abs(value) if math.isfinite(value) else None
            except (KeyError, TypeError, ValueError):
                measured[name] = None
        for name, value in measured.items():
            if value is None:
                reasons.append(name + '_unavailable_or_nonfinite')
            elif value > budgets[name]:
                reasons.append(name + '_outside_original_alignment_budget')
        return dict(aligned=not reasons, measured=measured, budgets=budgets, reasons=reasons,
            xy_norm='Euclidean, matching independent scorer', truth_pose_used=True)

    def _supported(self, debug):
        # Only the SUPPORT_TRANSFER -> OPEN transition gains this gate.
        # INSERT/OPEN/VERIFY retain the historical physical support predicate.
        if self.phase == 'SUPPORT_TRANSFER' and self._support_gate_context is not None:
            context = self._support_gate_context
            if (not context['alignment']['aligned'] or context['unloading_paused']
                    or context['physical_watchdog_expired']):
                # Short-circuit unavailable tilt before the historical helper
                # attempts float(debug['tilt_deg']). Alignment fails closed.
                return False
        return super()._supported(debug)

    def act(self, public_obs, debug):
        debug = dict(debug)
        if 'object_quaternion_wxyz' not in debug and 'quaternion_wxyz' in debug:
            debug['object_quaternion_wxyz'] = debug['quaternion_wxyz']
        actual_t = super()._time(public_obs, debug)
        if not math.isfinite(actual_t):
            raise ValueError('Teacher observation time must be finite')
        episode_id = public_obs.get('episode_id', debug.get('episode_id'))
        if self._episode_id is not None and episode_id != self._episode_id:
            raise ValueError('Reset teacher before changing episode')
        if self._clock_last_actual is not None and actual_t < self._clock_last_actual:
            raise ValueError('Teacher time moved backwards; reset required')
        if self._clock_last_actual is not None and abs(actual_t - self._clock_last_actual) <= 1e-12:
            # A repeated observation is not another physical control tick;
            # avoid consuming feedback/closure gains a second time as well.
            return copy.deepcopy(self._clock_cached_action)
        source_phase = self.phase
        scale = self.motion_time_scale if source_phase in self.SLOWED_PHASES else 1.
        dt = 0. if self._clock_last_actual is None else actual_t - self._clock_last_actual
        physical_start = self.phase_start
        physical_elapsed = 0. if physical_start is None else actual_t - physical_start
        if self._clock_phase != source_phase:
            # Supports an explicit private phase entry between observations;
            # ordinary transitions are accounted for after the previous act.
            self._phase_motion_elapsed = max(0., physical_elapsed / scale)
        else:
            self._phase_motion_elapsed += dt / scale
        self.controller_motion_clock_s += dt / scale
        motion_elapsed = self._phase_motion_elapsed
        event_start = len(self.events)
        self._grasp_orientation_feedback_suppressed = False
        self._extract_lateral_feedback_suppressed = False
        previous_opening = self.last_grip_opening
        unlatched_before = self.latch_opening is None
        bilateral = all(float(v) > float(get(self.cfg, 'gripper.contact_threshold_N', .02))
            for v in debug['finger_contact_N'])
        prealign_active = bool(source_phase == 'APPROACH_SOURCE' and not self.finished
            and previous_opening >= .08 - 1e-10
            and all(float(v) <= float(get(self.cfg, 'gripper.contact_threshold_N', .02))
                    for v in debug['finger_contact_N'])
            and self._approach_orientation_start is not None)
        if prealign_active:
            progress = min(1., max(0., motion_elapsed / self.approach_orientation_duration_s))
            fraction = progress * progress * (3. - 2. * progress)
            delta = self.approach_orientation_goal * self._approach_orientation_start.inv()
            self.rotation_command = Rotation.from_rotvec(fraction * delta.as_rotvec()) * self._approach_orientation_start
            self._approach_orientation_progress = progress
            self._approach_orientation_fraction = fraction
        support_context = None
        parent_elapsed = motion_elapsed
        if source_phase == 'SUPPORT_TRANSFER' and not self.finished:
            alignment = self._support_alignment(debug)
            if self._support_physical_start != physical_start:
                # Also handles explicit private phase entry between samples.
                self._support_physical_start = physical_start
                self._support_last_actual = actual_t if physical_start is None else physical_start
                self._support_previous_aligned = alignment['aligned']
                self._support_unload_elapsed_s = 0.
            support_dt = max(0., actual_t - self._support_last_actual)
            advancing = bool(alignment['aligned'] and self._support_previous_aligned)
            if advancing:
                duration = float(get(self.cfg, 'demo_release.unload_seconds', 3.))
                self._support_unload_elapsed_s = min(duration, self._support_unload_elapsed_s + support_dt)
            self._support_last_actual = actual_t
            self._support_previous_aligned = alignment['aligned']
            support_context = dict(alignment=alignment, unloading_paused=not advancing,
                pause_reasons=alignment['reasons'] if not alignment['aligned'] else
                    ([] if advancing else ['awaiting_consecutive_aligned_observations']),
                unload_elapsed_s=self._support_unload_elapsed_s,
                unload_duration_s=float(get(self.cfg, 'demo_release.unload_seconds', 3.)),
                physical_phase_elapsed_s=physical_elapsed,
                physical_watchdog_s=10., physical_watchdog_expired=physical_elapsed > 10.,
                feedback_source='Private actual object pose; existing bounded parent XY and orientation feedback',
                truth_pose_used=True, independent_success_label_assigned=False)
            self._support_gate_context = support_context
            # Keep correcting alignment while paused. The parent retains its
            # exact unloading/force-relief equations; only its local ramp u is
            # mapped. Contact history, quiet windows and t remain physical.
            self._feedback(debug, self.floor[:2])
            parent_elapsed = self._support_unload_elapsed_s
        if physical_start is not None:
            self.phase_start = actual_t - parent_elapsed
        try:
            # Actual t drives history, contact-loss, quiet windows, latch times
            # and global watchdogs. Only u=t-phase_start sees the mapped clock.
            action = super().act(public_obs, debug)
        finally:
            if self.phase == source_phase and physical_start is not None:
                self.phase_start = physical_start
            # _enter uses actual t; preserve its new physical phase_start.
            self._support_gate_context = None
        if support_context is not None and support_context['physical_watchdog_expired'] and not self.finished:
            # Parent u is the monotone ramp clock, so retain its original
            # strict >10 s watchdog explicitly on real phase elapsed time.
            self._finish('SUPPORT_TRANSFER_FAILED', actual_t)
            action['metadata'].update(teacher_status=self.status, teacher_finished=True)
        if source_phase != 'SUPPORT_TRANSFER' and self.phase == 'SUPPORT_TRANSFER':
            self._support_physical_start = self.phase_start
            self._support_last_actual = actual_t
            self._support_previous_aligned = self._support_alignment(debug)['aligned']
            self._support_unload_elapsed_s = 0.
        if self._approach_orientation_start is None and self.rotation_command is not None:
            # The parent initializes this from the original reset/first-act
            # robot TCP observation. Capture once; later observations do not
            # move the interpolation start or accumulate an orientation error.
            self._approach_orientation_start = Rotation.from_quat(self.rotation_command.as_quat())
        parent_opening = float(action['gripper_opening_m'])
        slow_zone = bool(self.near_contact_slow_close_enabled and source_phase == 'GRASP' and unlatched_before and not bilateral
            and previous_opening <= self.near_contact_close_threshold_m
            and parent_opening < previous_opening and not self.finished)
        if slow_zone:
            action['gripper_opening_m'] = max(parent_opening,
                previous_opening - self.near_contact_close_speed_m_s / self.hz)
            # Preserve first-contact/latch logic; only bound this closing step.
            # In particular, a single finger contact never marks bilateral.
            self.last_grip_opening = float(action['gripper_opening_m'])
        if self.phase != source_phase:
            self._phase_motion_elapsed = 0.
        self._clock_phase = self.phase
        self._clock_last_actual = actual_t
        for event in self.events[event_start:]:
            event.update(controller_time_s=self.controller_motion_clock_s,
                controller_motion_clock_s=self.controller_motion_clock_s,
                actual_simulation_time_s=actual_t, motion_source_phase=source_phase,
                motion_time_scale=scale)
        action['metadata'].update(teacher_controller_version=self.VERSION, truth_teacher=True,
            actual_simulation_time_s=actual_t, controller_time_s=self.controller_motion_clock_s,
            controller_motion_clock_s=self.controller_motion_clock_s,
            motion_source_phase=source_phase, physical_phase_elapsed_s=physical_elapsed,
            motion_phase_elapsed_s=motion_elapsed, motion_time_scale=scale,
            physical_control_hz=self.hz, physical_watchdogs_unscaled=True,
            support_transfer_control_active=support_context is not None,
            support_transfer=support_context,
            approach_orientation_active=prealign_active,
            approach_orientation_source='Original reset/first-act robot TCP orientation -> static robot.gripper_yaw_deg; no object truth',
            approach_orientation_start_quaternion_wxyz=wxyz(self._approach_orientation_start).tolist(),
            approach_orientation_goal_quaternion_wxyz=wxyz(self.approach_orientation_goal).tolist(),
            approach_orientation_motion_progress=self._approach_orientation_progress,
            approach_orientation_smooth_fraction=self._approach_orientation_fraction,
            approach_orientation_motion_duration_s=self.approach_orientation_duration_s,
            approach_orientation_uses_object_truth=False,
            grasp_orientation_feedback_suppressed=self._grasp_orientation_feedback_suppressed,
            grasp_orientation_feedback_policy='Hold existing EE orientation during GRASP while source-constrained; unchanged feedback after extraction',
            extract_lateral_feedback_suppressed=self._extract_lateral_feedback_suppressed,
            extract_lateral_feedback_policy='Fixed nominal XY during EXTRACT; parent XY feedback resumes in TRANSPORT and ALIGN',
            near_contact_slow_close_zone=slow_zone,
            near_contact_slow_close_enabled=self.near_contact_slow_close_enabled,
            near_contact_slow_close_applied=float(action['gripper_opening_m']) > parent_opening,
            near_contact_nominal_outer_width_m=self.nominal_vessel_outer_width_m,
            near_contact_close_threshold_m=self.near_contact_close_threshold_m,
            near_contact_close_speed_m_s=self.near_contact_close_speed_m_s,
            near_contact_previous_opening_m=previous_opening,
            near_contact_parent_opening_m=parent_opening,
            near_contact_dispatched_opening_m=float(action['gripper_opening_m']),
            near_contact_bilateral_sensor_observed=bilateral)
        self._clock_cached_action = copy.deepcopy(action)
        return action
