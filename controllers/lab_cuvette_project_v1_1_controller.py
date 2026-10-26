"""Phase-motion clock and source-constrained grasp teacher adapter.

Only four smooth motion phases are slowed. The original teacher, physics,
scorer, 60 Hz actions and physical contact timers are unchanged. GRASP holds
the existing EE orientation rather than correcting a vessel still in its rack.
"""
from __future__ import annotations

import copy
import math

from controllers.lab_cuvette_env_v1_controller import LabCuvetteTeacher, get


class LabCuvetteProjectV11Teacher(LabCuvetteTeacher):
    VERSION = 'Project_v1_1.teacher_phase_motion_clock.v2'
    SLOWED_PHASES = frozenset(('APPROACH_SOURCE', 'EXTRACT', 'TRANSPORT', 'RETREAT'))

    def __init__(self, cfg, layout):
        self.motion_time_scale = float(get(cfg, 'teacher_execution.motion_time_scale', 1.5))
        if not math.isfinite(self.motion_time_scale) or self.motion_time_scale < 1:
            raise ValueError('teacher_execution.motion_time_scale must be finite and at least 1')
        super().__init__(cfg, layout)

    def reset(self, public_obs=None, debug=None):
        super().reset(public_obs, debug)
        self._clock_last_actual = None
        self._clock_phase = self.phase
        self._phase_motion_elapsed = 0.
        self.controller_motion_clock_s = 0.
        self._clock_cached_action = None
        self._grasp_orientation_feedback_suppressed = False
        return self

    def _feedback(self, debug, desired_cup_xy=None, *, orientation=True):
        # Rotating a closed hand while the cup remains rack-constrained can
        # move its bottom about the grasp anchor. Reorient after extraction,
        # using the unchanged TRANSPORT/ALIGN feedback, not during GRASP.
        if self.phase == 'GRASP' and orientation:
            self._grasp_orientation_feedback_suppressed = True
            orientation = False
        return super()._feedback(debug, desired_cup_xy, orientation=orientation)

    def act(self, public_obs, debug):
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
        if physical_start is not None:
            self.phase_start = actual_t - motion_elapsed
        try:
            # Actual t drives history, contact-loss, quiet windows, latch times
            # and global watchdogs. Only u=t-phase_start sees the mapped clock.
            action = super().act(public_obs, debug)
        finally:
            if self.phase == source_phase and physical_start is not None:
                self.phase_start = physical_start
            # _enter uses actual t; preserve its new physical phase_start.
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
            grasp_orientation_feedback_suppressed=self._grasp_orientation_feedback_suppressed,
            grasp_orientation_feedback_policy='Hold existing EE orientation during GRASP while source-constrained; unchanged feedback after extraction')
        self._clock_cached_action = copy.deepcopy(action)
        return action
