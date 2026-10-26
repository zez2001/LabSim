"""Generic, robot-sensor-only contact hold; no task phase or object pose input.

The caller supplies the existing scheduled/ramped target. Before contact that
schedule is unchanged. Contact freezes an already applied command without
reopening; loss permits bounded slow closure toward the original logical goal.
This helper never changes gains, force caps, physics or task acceptance gates.
"""
from __future__ import annotations

import math


class GenericContactHold:
    def __init__(self, *, control_hz, mass_kg, dynamic_friction,
                 finger_dynamic_friction, finger_kp_N_per_m,
                 contact_safety_factor, maximum_compression_m,
                 contact_threshold_N, contact_persist_s,
                 contact_approach_speed_m_s, minimum_total_opening_m=.002):
        values = dict(control_hz=control_hz, mass_kg=mass_kg,
                      dynamic_friction=dynamic_friction,
                      finger_dynamic_friction=finger_dynamic_friction,
                      finger_kp_N_per_m=finger_kp_N_per_m,
                      contact_safety_factor=contact_safety_factor,
                      maximum_compression_m=maximum_compression_m,
                      contact_threshold_N=contact_threshold_N,
                      contact_persist_s=contact_persist_s,
                      contact_approach_speed_m_s=contact_approach_speed_m_s,
                      minimum_total_opening_m=minimum_total_opening_m)
        for name, value in values.items():
            if not math.isfinite(float(value)) or float(value) < 0:
                raise ValueError("Invalid contact-hold configuration: " + name)
            setattr(self, name, float(value))
        if min(self.control_hz, self.dynamic_friction, self.finger_dynamic_friction,
               self.finger_kp_N_per_m) <= 0:
            raise ValueError("Frequency, friction and drive stiffness must be positive")
        if self.minimum_total_opening_m > .08:
            raise ValueError("Minimum opening exceeds the public opening range")
        mu = math.sqrt(self.dynamic_friction * self.finger_dynamic_friction)
        self.weight_compression_per_finger_m = min(self.maximum_compression_m,
            self.mass_kg * 9.81 * self.contact_safety_factor /
            (2 * mu * self.finger_kp_N_per_m))
        self.reset()

    def reset(self):
        self.logical_requested_opening_m = None
        self.frozen_opening_m = None
        self.contact_since_s = None
        self.confirmed = False
        self.ever_confirmed = False
        self.recovering = False
        self.release_ramp_active = False
        self.last_t = None

    @staticmethod
    def _number(value, name):
        value = float(value)
        if not math.isfinite(value):
            raise ValueError("Nonfinite contact-hold input: " + name)
        return value

    def update(self, *, t, logical_requested_opening_m, ramped_opening_m,
               previous_applied_opening_m, measured_finger_positions_m,
               finger_contact_N):
        t = self._number(t, "t")
        logical = self._number(logical_requested_opening_m, "logical_requested_opening_m")
        ramped = self._number(ramped_opening_m, "ramped_opening_m")
        previous = self._number(previous_applied_opening_m, "previous_applied_opening_m")
        if any(value < 0 or value > .08 for value in (logical, ramped, previous)):
            raise ValueError("Contact-hold opening must be in0..0.08m")
        fingers = [self._number(value, "measured_finger_positions_m")
                   for value in measured_finger_positions_m]
        forces = [self._number(value, "finger_contact_N") for value in finger_contact_N]
        if len(fingers) != 2 or len(forces) != 2 or min(forces) < 0:
            raise ValueError("Expected two finite measured fingers and nonnegative forces")
        if self.last_t is not None and t < self.last_t - 1e-12:
            raise ValueError("Contact-hold time must not go backwards")
        dt = 1 / self.control_hz if self.last_t is None else max(0., t - self.last_t)
        widening = (self.logical_requested_opening_m is not None and
                    logical > self.logical_requested_opening_m + 1e-10)
        if widening:
            self.frozen_opening_m = None
            self.contact_since_s = None
            self.confirmed = False
            self.recovering = False
            self.release_ramp_active = True
        self.logical_requested_opening_m = logical
        bilateral = all(value > self.contact_threshold_N for value in forces)
        candidate = max(self.minimum_total_opening_m,
                        sum(fingers) - 2 * self.weight_compression_per_finger_m)
        confirmed_before = self.confirmed

        if self.release_ramp_active:
            # Keep the whole explicit opening ramp free from re-latching while
            # residual bilateral contact is still measured during release.
            applied = ramped
            decision = "explicit_opening_ramp"
            if ramped >= logical - 1e-10:
                self.release_ramp_active = False
        elif bilateral:
            if self.frozen_opening_m is None:
                # Key invariant: a transient measured contact width must not
                # widen a tighter command that has already been applied.
                self.frozen_opening_m = min(previous, candidate)
                self.contact_since_s = t
                self.confirmed = False
                decision = "first_bilateral_freeze"
            else:
                decision = "hold_contact_target"
            self.recovering = False
            if t - self.contact_since_s >= self.contact_persist_s - 1e-10:
                self.confirmed = True
                self.ever_confirmed = True
            applied = self.frozen_opening_m
        elif self.frozen_opening_m is not None or self.recovering:
            # Never jump to an old, already elapsed closure-ramp target after
            # a transient or established grasp loses contact.
            self.frozen_opening_m = None
            self.contact_since_s = None
            self.confirmed = False
            self.recovering = True
            applied = min(previous, max(logical,
                          previous - self.contact_approach_speed_m_s * dt))
            decision = "contact_loss_slow_close"
        else:
            applied = ramped
            decision = "original_ramp"

        self.last_t = t
        diagnostics = dict(
            schema="labsim.Project_v1_1.generic_contact_hold.v1", t=t,
            elapsed_control_time_s=dt, decision=decision,
            logical_requested_opening_m=logical, dispatched_ramped_opening_m=ramped,
            previous_applied_opening_m=previous, applied_opening_m=applied,
            measured_finger_positions_m=fingers, measured_total_opening_m=sum(fingers),
            finger_contact_N=forces, bilateral=bilateral,
            contact_threshold_N=self.contact_threshold_N,
            contact_persist_s=self.contact_persist_s,
            weight_compression_per_finger_m=self.weight_compression_per_finger_m,
            weight_based_candidate_opening_m=candidate,
            frozen_opening_m=self.frozen_opening_m,
            contact_since_s=self.contact_since_s, confirmed=self.confirmed,
            previously_confirmed=confirmed_before, ever_confirmed=self.ever_confirmed,
            contact_loss_recovery=self.recovering,
            explicit_opening_ramp_active=self.release_ramp_active,
            slow_close_speed_m_s=self.contact_approach_speed_m_s,
            observation_scope="logical/ramped/applied commands and robot finger sensors only",
            force_cap_modified=False, task_phase_or_object_pose_used=False)
        return applied, diagnostics
