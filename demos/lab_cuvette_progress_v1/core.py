"""Causal, strategy-independent Progress evaluator for the cuvette loading task.

Every duration uses completed physical-sample time. Snapshots never change after
they have been returned, and no future sample can confirm a past online label.
This evaluator is diagnostic: it neither changes reward nor adjudicates the
original task_success/record_valid/BC fields.
"""
from __future__ import annotations

from collections import deque
import copy
import math

import numpy as np

from .config import EVALUATOR_VERSION, SCHEMA_VERSION, plain, resolve_config
from .geometry import measured_geometry, number, rotation, rotation_distance, vector

STAGES = ('approach_grasp', 'grasp', 'extract', 'transport', 'align', 'insert',
          'support_transfer', 'release_retreat', 'stable_complete')
MILESTONES = STAGES + ('released', 'retreated')


def conjunction(*values):
    """Three-valued conjunction: absent evidence is never False or zero."""
    if any(v is False for v in values):
        return False
    return None if any(v is None for v in values) else True


def compare(value, threshold, *, minimum=False, absolute=False):
    if value is None or threshold is None:
        return None
    if absolute:
        value = abs(value)
    return bool(value >= threshold if minimum else value <= threshold)


def boolean(value):
    return bool(value) if isinstance(value, (bool, np.bool_)) else None


def quality(error, scale):
    return float(np.clip(1.-error/scale, 0., 1.)) if error is not None and scale and scale > 0 else None


class ProgressEvaluator:
    """One independent instance per environment, episode and source trace.

    Input is the original flat ``PhysicsRecorder.capture`` row. Optional
    ``_execution`` only supplies action-intent evidence for contact-stall
    diagnosis. Teacher phase, waypoints and task-success strings are ignored.
    ``events`` is the full sparse event log; snapshot ``events`` is its delta.
    """

    def __init__(self, config_dict):
        self.config = resolve_config(config_dict)
        self.geometry = self.config['geometry']
        self.thresholds = self.config['thresholds']
        self.normalization = self.config['normalization']
        self.reset({})

    def reset(self, episode_metadata_dict=None):
        self.metadata = copy.deepcopy(plain(episode_metadata_dict or {}))
        self.events = []
        self.attempts = []
        self.failure_observations = []
        self._observation_keys = set()
        self._since = {name: None for name in MILESTONES}
        self._milestones = {name: dict(ever_achieved=False, current_satisfied=None,
            first_candidate_t=None, first_confirmed_t=None,
            evidence_version=EVALUATOR_VERSION) for name in MILESTONES}
        self._active_attempt = None
        self._attempt_counter = 0
        self._grasp_reference = None
        self._bilateral_since = None
        self._contact_since = None
        self._loaded_pose_seen = False
        self._loss_since = None
        self._support_committed = False
        self._stable_start = None
        self._stable_position = None
        self._stable_quaternion = None
        self._stable_max_position = 0.
        self._stable_max_rotation = 0.
        self._stable_confirmed_t = None
        self._initial_position = None
        self._initial_bottom = None
        self._last_row = None
        self._last_t = None
        self._last_snapshot = None
        self._sample_count = 0
        self._gap_count = 0
        self._unknown_counts = {}
        self._jam_window = deque()
        self._jam_active = False
        self._finalized = None
        self._finalizing = False
        return self

    @property
    def last_snapshot(self):
        return copy.deepcopy(self._last_snapshot)

    def _event(self, name, t, *, candidate_start_t=None, evidence=None):
        event = dict(event_id=len(self.events)+1, name=name, t=float(t),
            candidate_start_t=float(candidate_start_t) if candidate_start_t is not None else None,
            confirmed_t=float(t), attempt_id=self._active_attempt['attempt_id'] if self._active_attempt else None,
            evidence=plain(evidence or {}))
        self.events.append(event)
        return event

    def _observe(self, name, fact, t, hold_s=0., evidence=None):
        milestone = self._milestones[name]
        old = milestone['current_satisfied']
        if fact is True:
            if self._since[name] is None:
                self._since[name] = t
                if milestone['first_candidate_t'] is None:
                    milestone['first_candidate_t'] = t
                self._event(name+'_candidate', t, candidate_start_t=t, evidence=evidence)
            satisfied = bool(t-self._since[name]+1e-9 >= hold_s)
            if satisfied and old is not True:
                self._event(name+'_confirmed', t, candidate_start_t=self._since[name], evidence=evidence)
                if not milestone['ever_achieved']:
                    milestone.update(ever_achieved=True, first_confirmed_t=t)
                if self._active_attempt and name in STAGES:
                    self._active_attempt['completed_stages'][name] = t
            milestone['current_satisfied'] = satisfied
        else:
            if old is True:
                self._event(name+'_condition_lost', t, candidate_start_t=self._since[name],
                    evidence=dict(reason='missing_evidence' if fact is None else 'physical_condition_false'))
            milestone['current_satisfied'] = fact
            self._since[name] = None
        return milestone['current_satisfied']

    def _new_attempt(self, t):
        self._attempt_counter += 1
        attempt = dict(attempt_id=self._attempt_counter, start_t=t, end_t=None,
            outcome='incomplete', ended_by=None, completed_stages={},
            previous_attempt_id=self.attempts[-1]['attempt_id'] if self.attempts else None,
            recovered_from_attempt_id=self.attempts[-1]['attempt_id'] if self.attempts and self.attempts[-1]['outcome'] == 'failure' else None,
            next_attempt_id=None, maximum_relative_translation_m=None,
            maximum_relative_rotation_rad=None, source_clear_confirmed=False,
            held_transport_confirmed=False, preinsert_region_reached=False)
        if self.attempts:
            self.attempts[-1]['next_attempt_id'] = attempt['attempt_id']
        self.attempts.append(attempt)
        self._active_attempt = attempt
        self._support_committed = False
        self._loaded_pose_seen = False
        self._event('attempt_started', t)

    def _end_attempt(self, t, outcome, reason):
        if self._active_attempt is None:
            return
        self._active_attempt.update(end_t=t, outcome=outcome, ended_by=reason)
        self._event('attempt_ended', t, evidence=dict(outcome=outcome, reason=reason))
        self._active_attempt = None
        self._grasp_reference = None
        self._loss_since = None
        self._bilateral_since = None

    def _failure(self, code, t, evidence):
        # Repeated physical samples of one continuous incident are one fact.
        key = (code, self._attempt_counter)
        if key not in self._observation_keys:
            observation = dict(code=code, t=t, attempt_id=self._attempt_counter or None,
                               evidence=plain(evidence), attribution='observed_physical_fact')
            self.failure_observations.append(observation)
            self._observation_keys.add(key)
            self._event('failure_observation', t, evidence=observation)

    def _metric(self, value, unit, source, reason=None):
        return dict(available=value is not None, value=plain(value), unit=unit,
                    source=source, reason=reason if value is None else None)

    def _stable(self, t, row, conditions, gap):
        valid = conjunction(*conditions.values())
        position = vector(row.get('object_position_m', row.get('position')))
        quaternion = vector(row.get('object_quaternion_wxyz', row.get('quaternion_wxyz')), 4)
        pose_known = position is not None and rotation(quaternion) is not None
        valid = conjunction(valid, True if pose_known else None)
        interrupted = None
        if gap:
            interrupted = 'evidence_sampling_gap'
        elif valid is not True:
            interrupted = 'missing_evidence' if valid is None else 'stable_prerequisite_lost'
        elif self._stable_start is not None:
            drift = float(np.linalg.norm(position-self._stable_position))
            angle = rotation_distance(quaternion, self._stable_quaternion)
            self._stable_max_position = max(self._stable_max_position, drift)
            self._stable_max_rotation = max(self._stable_max_rotation, angle)
            if (self._stable_max_position > self.thresholds['stable_position_drift_m'] or
                    self._stable_max_rotation > self.thresholds['stable_orientation_change_rad']):
                interrupted = 'actual_pose_drift_exceeded'
                self._failure('POST_RELEASE_UNSTABLE', t, dict(position_drift_m=drift,
                    orientation_change_rad=angle, candidate_start_t=self._stable_start))
        if interrupted and self._stable_start is not None:
            self._event('stable_window_interrupted', t, candidate_start_t=self._stable_start,
                evidence=dict(reason=interrupted, position_drift_m=self._stable_max_position,
                              orientation_change_rad=self._stable_max_rotation))
            self._stable_start = None
            self._stable_position = self._stable_quaternion = None
            self._stable_max_position = self._stable_max_rotation = 0.
            self._stable_confirmed_t = None
            self._since['stable_complete'] = None
            self._observe('stable_complete', None if valid is None else False, t)
        if valid is True:
            if self._stable_start is None:
                self._stable_start = t
                self._stable_position = position.copy()
                self._stable_quaternion = quaternion.copy()
            duration = t-self._stable_start
            complete = self._observe('stable_complete', True, t,
                hold_s=self.thresholds['stable_duration_s'], evidence=conditions)
            if complete and self._stable_confirmed_t is None:
                self._stable_confirmed_t = t
                # A legally released attempt can finish after its grip ended.
                if self.attempts and self.attempts[-1]['ended_by'] == 'legal_target_support_release':
                    self.attempts[-1].update(outcome='success', stable_complete_t=t)
        else:
            duration = 0.
            complete = self._observe('stable_complete', valid, t)
        return dict(available=valid is not None, conditions=conditions, current_satisfied=complete,
            candidate_start_t=self._stable_start, confirmed_t=self._stable_confirmed_t,
            continuous_duration_s=float(duration), required_duration_s=self.thresholds['stable_duration_s'],
            position_drift_m=self._stable_max_position if self._stable_start is not None else None,
            orientation_change_rad=self._stable_max_rotation if self._stable_start is not None else None)

    def _stall(self, row, t, depth, inserted):
        """An actual downward request + contact + little motion is required."""
        execution = row.get('_execution') or {}
        intent = bool(execution.get('available') is True and execution.get('raw_action') is not None)
        command = number(row.get('commanded_bottom_z_m'))
        wall = number(row.get('wall_contact_N'))
        item = dict(t=t, depth=depth, command=command, wall=wall, intent=intent)
        self._jam_window.append(item)
        window = self.thresholds['stall_window_s']
        while len(self._jam_window) > 1 and self._jam_window[1]['t'] <= t-window:
            self._jam_window.popleft()
        first = self._jam_window[0]
        depth_change = None
        contact_stall = None
        if t-first['t']+1e-9 >= window and depth is not None and first['depth'] is not None:
            depth_change = depth-first['depth']
            request_known = all(v['intent'] and v['command'] is not None for v in self._jam_window)
            if request_known:
                commanded_down = first['command']-command
                contact_stall = bool(commanded_down >= self.thresholds['stall_command_down_min_m']
                    and depth_change <= self.thresholds['stall_actual_down_max_m']
                    and wall is not None and wall > self.thresholds['bilateral_force_N'] and inserted is not True)
                if contact_stall and not self._jam_active:
                    self._failure('CONTACT_STALL_OBSERVED', t, dict(commanded_down_m=commanded_down,
                        actual_depth_increase_m=depth_change, wall_contact_N=wall,
                        interval_start_t=first['t'], execution_evidence=True))
        self._jam_active = contact_stall is True
        return depth_change, contact_stall

    def update(self, sample_dict):
        if self._finalized is not None:
            raise RuntimeError('ProgressEvaluator has finalized; reset before another episode')
        row = dict(sample_dict)
        t = number(row.get('t', row.get('simulation_time')))
        if t is None:
            raise ValueError('Progress sample requires finite simulation time t in seconds')
        if self._last_t is not None and t <= self._last_t:
            raise ValueError('Progress sample times must strictly increase within one episode')
        event_start = len(self.events)
        gap = self._last_t is not None and t-self._last_t > self.thresholds['maximum_evidence_gap_s']+1e-9
        if gap:
            self._gap_count += 1
            self._event('evidence_gap', t, evidence=dict(previous_t=self._last_t,
                elapsed_s=t-self._last_t, declared_maximum_gap_s=self.thresholds['maximum_evidence_gap_s']))
            self._bilateral_since = None
            self._contact_since = None
            self._loss_since = None
            self._since = {name: None for name in MILESTONES}
            self._jam_window.clear()
        geom = measured_geometry(row, self.geometry)
        p, r, bottom = geom['position'], geom['rotation'], geom['bottom']
        if self._initial_position is None and p is not None:
            self._initial_position = p.copy()
        if self._initial_bottom is None and bottom is not None:
            self._initial_bottom = bottom
        thresholds = self.thresholds
        forces = vector(row.get('finger_contact_N', row.get('finger_contact_N2')), 2)
        fingers = vector(row.get('finger_joint_positions_m', row.get('finger_joint_positions_m2')), 2)
        bilateral = bool(np.all(forces >= thresholds['bilateral_force_N'])) if forces is not None else None
        if bilateral is True:
            if self._contact_since is None:
                self._contact_since = t
        else:
            self._contact_since = None
        detached = conjunction(bool(np.all(forces < thresholds['bilateral_force_N'])) if forces is not None else None,
            bool(np.all(fingers >= thresholds['finger_open_min_m'])) if fingers is not None else None)
        reasonable_gripper = bool(np.all(fingers >= 0.) and np.all(fingers < thresholds['finger_open_min_m'])) if fingers is not None else None
        relative_p = vector(row.get('cup_in_hand_position_m'))
        relative_q = vector(row.get('cup_in_hand_quaternion_wxyz'), 4)
        relative_known = relative_p is not None and rotation(relative_q) is not None
        pose_known = p is not None and r is not None
        grasp_candidate = conjunction(bilateral, reasonable_gripper, True if relative_known and pose_known else None)
        if grasp_candidate is True:
            if self._bilateral_since is None:
                self._bilateral_since = t
                if self._active_attempt is None:
                    self._new_attempt(t)
            if t-self._bilateral_since+1e-9 >= thresholds['bilateral_hold_s'] and self._grasp_reference is None:
                self._grasp_reference = dict(position=relative_p.copy(), quaternion=relative_q.copy(), t=t)
        else:
            self._bilateral_since = None
        slip = angle = None
        if self._grasp_reference is not None and relative_known:
            slip = float(np.linalg.norm(relative_p-self._grasp_reference['position']))
            angle = rotation_distance(relative_q, self._grasp_reference['quaternion'])
            if self._active_attempt and not self._loaded_pose_seen:
                old = self._active_attempt['maximum_relative_translation_m']
                self._active_attempt['maximum_relative_translation_m'] = max(old or 0., slip)
                old = self._active_attempt['maximum_relative_rotation_rad']
                self._active_attempt['maximum_relative_rotation_rad'] = max(old or 0., angle)
        grip_quality = conjunction(compare(slip, thresholds['grasp_translation_m']), compare(angle, thresholds['grasp_rotation_rad']))
        held = conjunction(grasp_candidate, self._grasp_reference is not None, grip_quality)
        # Candidate time is contact onset; confirmation time is causal .1s later.
        grasp_fact = conjunction(grasp_candidate, grip_quality) if self._grasp_reference is not None else grasp_candidate
        grasp_current = self._observe('grasp', grasp_fact, t,
            hold_s=thresholds['bilateral_hold_s'], evidence=dict(bilateral_contact=bilateral,
                reasonable_gripper=reasonable_gripper, relative_pose_available=relative_known))
        if grasp_current is True and held is not True:
            self._milestones['grasp']['current_satisfied'] = held
        approach = conjunction(compare(geom['approach_distance'], thresholds['approach_position_m']),
            compare(geom['approach_orientation'], thresholds['approach_orientation_rad']))
        # Contact establishing a valid grasp is also physical reach evidence,
        # even if an older trace lacks the optional TCP pose channel.
        if held is True:
            approach = True
        self._observe('approach_grasp', approach, t, evidence=dict(distance_m=geom['approach_distance'], orientation_error_rad=geom['approach_orientation']))
        source_rim = number(self.geometry.get('source_rim_world_z_m'))
        clearance = bottom-source_rim if bottom is not None and source_rim is not None else number(row.get('source_clearance_m'))
        source_clear = compare(clearance, thresholds['source_clearance_m'], minimum=True)
        source_gap = number(row.get('source_bottom_gap_m'))
        source_inside = boolean(row.get('source_reference_inside'))
        source_supported = conjunction(source_inside, compare(source_gap, thresholds['support_gap_m'], absolute=True))
        extract = conjunction(source_clear, held)
        self._observe('extract', extract, t, evidence=dict(bottom_envelope_clearance_m=clearance, held=held))
        if extract is True and self._active_attempt:
            self._active_attempt['source_clear_confirmed'] = True
        displacement = float(np.linalg.norm(p[:2]-self._initial_position[:2])) if p is not None and self._initial_position is not None else None
        route_extracted = bool(self._active_attempt and self._active_attempt['source_clear_confirmed'])
        if conjunction(held, route_extracted, compare(displacement, thresholds['held_transport_displacement_m'], minimum=True)) is True and self._active_attempt:
            if not self._active_attempt['held_transport_confirmed']:
                self._event('held_transport_observed', t, evidence=dict(horizontal_displacement_m=displacement, source_clear_verified=True))
            self._active_attempt['held_transport_confirmed'] = True
        transported = bool(self._active_attempt and self._active_attempt['held_transport_confirmed'])
        preinsert_near = compare(geom['preinsert_distance'], thresholds['preinsert_region_radius_m'])
        transport = conjunction(held, route_extracted, transported, preinsert_near)
        self._observe('transport', transport, t, evidence=dict(preinsert_distance_m=geom['preinsert_distance'], held_transport_verified=transported))
        if transport is True and self._active_attempt:
            self._active_attempt['preinsert_region_reached'] = True
        near_lineage = bool(self._active_attempt and self._active_attempt['preinsert_region_reached']) or self._support_committed
        aligned = conjunction(compare(geom['lateral'], thresholds['alignment_lateral_m']),
            compare(geom['tilt'], thresholds['alignment_tilt_rad'], absolute=True),
            compare(geom['yaw'], thresholds['alignment_yaw_rad'], absolute=True))
        align = conjunction(aligned, near_lineage, True if (held is True or self._support_committed) else held)
        self._observe('align', align, t, evidence=dict(lateral_error_m=geom['lateral'], tilt_rad=geom['tilt'], yaw_error_rad=geom['yaw'], symmetry_order=self.geometry['allowed_yaw_symmetry_order']))
        contains = boolean(row.get('target_region_contains_object'))
        if contains is None and geom['lateral'] is not None and number(self.geometry.get('target_inner_m')) is not None:
            if geom['lateral'] > self.geometry['target_inner_m']:
                contains = False
        depth = geom['depth']
        requested = number(self.geometry.get('target_depth_m'))
        depth_done = compare(depth, requested-thresholds['overlap_m'] if requested is not None else None, minimum=True)
        effective_insertion = conjunction(contains, aligned, near_lineage,
            compare(depth, 0., minimum=True), True if (held is True or self._support_committed) else held)
        insert = conjunction(effective_insertion, depth_done)
        self._observe('insert', insert, t, evidence=dict(raw_depth_m=depth, target_depth_m=requested,
            target_contains=contains, aligned=aligned, lineage_verified=near_lineage))
        support_force = number(row.get('target_bottom_support_N'))
        support_gap = number(row.get('target_bottom_gap_m'))
        if conjunction(depth_done, aligned, near_lineage,
                compare(support_gap, thresholds['support_gap_m'], absolute=True)) is True:
            self._loaded_pose_seen = True
        # Mirrors Size_v1 support-window checks: actual classified bottom force,
        # bottom gap, containment, retained depth and sampled input overlap.
        overlap = number(row.get('input_geometry_overlap_observed_m'))
        support_contact = conjunction(compare(support_force, thresholds['support_min_N'], minimum=True),
            compare(support_gap, thresholds['support_gap_m'], absolute=True))
        # Acquisition uses the original scorer's aligned loaded candidate.
        # Once transferred, continuous support uses its actual post-release
        # upright gate (1deg here), not the controller alignment budget.
        support_posture = compare(geom['tilt'], thresholds['upright_after_release_rad'], absolute=True) if self._support_committed else aligned
        support = conjunction(support_contact, contains, depth_done, support_posture, near_lineage,
            compare(overlap, thresholds['overlap_m']))
        self._observe('support_transfer', support, t, hold_s=thresholds['support_hold_s'], evidence=dict(
            bottom_support_N=support_force, bottom_gap_m=support_gap, target_contains=contains,
            observed_input_overlap_m=overlap, scope='classified physical bottom support and qualified input-material geometry, not cooked geometry'))
        if support is True:
            self._support_committed = True
        if held is not True and self._active_attempt and bilateral is False:
            if support is True:
                self._loss_since = None
            elif support is None or source_supported is None:
                self._loss_since = None
            else:
                if self._loss_since is None:
                    self._loss_since = t
                if t-self._loss_since+1e-9 >= thresholds['grasp_loss_hold_s']:
                    if source_supported is True:
                        self._end_attempt(t, 'interrupted', 'released_on_source_support')
                    else:
                        self._failure('GRASP_LOST_DURING_TRANSPORT' if route_extracted else 'GRASP_LOST', t,
                            dict(bilateral_contact=False, target_support=False, source_support=False,
                                 actual_relative_translation_m=slip, physical_duration_s=t-self._loss_since))
                        self._end_attempt(t, 'failure', 'unsupported_grasp_loss')
        else:
            self._loss_since = None
        released = self._observe('released', conjunction(detached, support), t,
            hold_s=thresholds['release_hold_s'], evidence=dict(both_fingers_open_and_detached=detached, target_supported=support))
        if released is True and self._active_attempt:
            self._end_attempt(t, 'incomplete', 'legal_target_support_release')
        clearance_gripper = number(row.get('gripper_object_clearance_m'))
        retreated = self._observe('retreated', conjunction(released,
            compare(clearance_gripper, thresholds['retreat_clearance_m'], minimum=True)), t,
            evidence=dict(minimum_gripper_input_geometry_clearance_m=clearance_gripper,
                          required_clearance_m=thresholds['retreat_clearance_m']))
        self._observe('release_retreat', conjunction(released, retreated), t,
            evidence=dict(released=released, retreated=retreated))
        stable_conditions = dict(correct_target_supported=support, released=released, retreated=retreated,
            no_finger_contact=bool(np.all(forces < thresholds['bilateral_force_N'])) if forces is not None else None,
            upright=compare(geom['tilt'], thresholds['upright_after_release_rad'], absolute=True),
            retained_loading_depth=depth_done, observed_input_overlap_within_limit=compare(overlap, thresholds['overlap_m']))
        stable_window = self._stable(t, row, stable_conditions, gap)
        depth_change, stall = self._stall(row, t, depth, insert)
        if support is True:
            hold_state = 'target_supported'
        elif held is True:
            hold_state = 'gripper_held'
        elif source_supported is True:
            hold_state = 'source_supported'
        elif any(value is None for value in (support, held, source_supported)):
            hold_state = 'unknown'
        else:
            hold_state = 'unsupported_or_lost'
        if released is True and retreated is True:
            current_stage = 'stable_complete'
        elif support is True:
            current_stage = 'release_retreat'
        elif insert is True:
            current_stage = 'support_transfer'
        elif align is True:
            current_stage = 'insert'
        elif near_lineage:
            current_stage = 'align'
        elif held is True and route_extracted:
            current_stage = 'transport'
        elif held is True:
            current_stage = 'extract'
        elif self._active_attempt or approach is True:
            current_stage = 'grasp'
        else:
            current_stage = 'approach_grasp'
        metrics = {}
        def metric(key, value, unit, source, reason='missing_required_physical_evidence'):
            metrics[key] = self._metric(value, unit, source, reason)
            if value is None:
                self._unknown_counts[key] = self._unknown_counts.get(key, 0)+1
        metric('grasp_approach_position_error_m', geom['approach_distance'], 'm', 'actual TCP to transformed configured body grip point')
        metric('grasp_approach_orientation_error_rad', geom['approach_orientation'], 'rad', 'actual TCP versus static configured grasp orientation')
        metric('gripper_opening_m', float(fingers.sum()) if fingers is not None else None, 'm', 'sum actual finger joints; not commanded target')
        metric('finger_contact_N', forces, 'N', 'PhysicsRecorder cup-on-finger force tensor')
        metric('bilateral_contact', bilateral, 'bool', 'both actual contact forces >= original scorer .01N')
        metric('bilateral_contact_duration_s', t-self._contact_since if self._contact_since is not None else (0. if bilateral is False else None), 's', 'continuous physical-sample time independent of optional relative-pose availability')
        metric('grasp_relative_translation_m', slip, 'm', 'current cup-in-hand translation versus this attempt reference')
        metric('grasp_relative_rotation_rad', angle, 'rad', 'quaternion geodesic versus this attempt reference')
        metric('grasp_quality_current', grip_quality, 'bool', 'original scorer relative-motion limits')
        metric('grasp_off_source_verified', route_extracted if self._active_attempt else False, 'bool', 'attempt-specific bilateral held extraction evidence')
        metric('source_bottom_envelope_clearance_m', clearance, 'm', geom['bottom_source'])
        metric('source_supported', source_supported, 'bool', 'source reference occupancy and measured bottom gap; geometric support candidate, not force attribution')
        metric('preinsert_distance_m', geom['preinsert_distance'], 'm', 'actual body-bottom reference to fixed loading-axis preinsert reference')
        metric('held_transport_displacement_m', displacement, 'm', 'actual body XY displacement from initial physical sample; only meaningful with held/source-clear gates')
        metric('target_lateral_error_m', geom['lateral'], 'm', 'actual pose relative to offset loading frame')
        metric('target_tilt_rad', geom['tilt'], 'rad', 'actual vessel +Z relative to target +Z')
        metric('target_yaw_error_rad', geom['yaw'], 'rad', 'full frame yaw; symmetry order '+str(self.geometry['allowed_yaw_symmetry_order']))
        metric('correct_target_contains', contains, 'bool', 'actual selected-seat input-material query; rectangle alone cannot prove containment')
        metric('raw_depth_m', depth, 'm', 'capture actual bottom-envelope depth, else declared body-bottom datum projected on loading axis')
        metric('target_depth_m', requested, 'm', 'resolved task.geometry.target_depth_m')
        metric('depth_ratio', float(np.clip(depth/requested, 0., 1.)) if depth is not None and requested and requested > 0 else None, '1', 'clip(raw_depth / configured target_depth, 0, 1)')
        metric('effective_insertion', effective_insertion, 'bool', 'correct target + aligned + nonnegative depth + same-attempt held transport evidence')
        metric('target_bottom_support_N', support_force, 'N', 'classified upward bottom contacts on selected seat; not whole-seat Fz')
        metric('target_bottom_gap_m', support_gap, 'm', 'actual transformed vessel envelope relative to target floor')
        metric('input_geometry_overlap_observed_m', overlap, 'm', 'qualified sampled input-material observation; cooked overlap remains unknown')
        metric('both_fingers_open_and_detached', detached, 'bool', 'both actual finger openings and both forces')
        metric('gripper_object_clearance_m', clearance_gripper, 'm', 'actual three-link input-geometry AABB lower-bound clearance')
        metric('tcp_object_distance_m', geom['tcp_distance'], 'm', 'auxiliary actual TCP-to-body-origin distance; does not confirm retreat')
        metric('stable_duration_s', stable_window['continuous_duration_s'] if stable_window['available'] else None, 's', 'continuous supported, released, retreated physical stability')
        metric('stable_position_drift_m', stable_window['position_drift_m'], 'm', 'actual pose change since current stable candidate start')
        metric('stable_orientation_change_rad', stable_window['orientation_change_rad'], 'rad', 'actual quaternion change since current stable candidate start')
        metric('insertion_depth_change_window_m', depth_change, 'm', 'causal .3s physical-time window; no jam attribution without executed request and contact')
        metric('contact_stall_observed', stall, 'bool', 'executed downward request + limited actual depth increase + actual wall contact', 'executed_action_or_window_evidence_unavailable')
        metric('native_linear_velocity_m_s', vector(row.get('linear_velocity_native_m_s', row.get('native_linear_velocity_m_s'))), 'm/s', 'native diagnostic only')
        fd = None
        if self._last_row is not None and p is not None:
            old_p = vector(self._last_row.get('object_position_m', self._last_row.get('position')))
            if old_p is not None:
                fd = (p-old_p)/(t-self._last_t)
        metric('pose_difference_linear_velocity_m_s', fd, 'm/s', 'actual body-origin finite difference, distinct from native/COM velocity')
        norms = self.normalization
        continuous = dict(
            approach_grasp=quality(geom['approach_distance'], norms['approach_distance_scale_m']),
            grasp=quality(slip, thresholds['grasp_translation_m']),
            extract=float(np.clip((clearance+norms['extraction_depth_scale_m'])/(norms['extraction_depth_scale_m']+thresholds['source_clearance_m']), 0., 1.)) if clearance is not None and norms['extraction_depth_scale_m'] is not None else None,
            transport=quality(geom['preinsert_distance'], norms['preinsert_distance_scale_m']),
            align=min(quality(geom['lateral'], norms['alignment_lateral_scale_m']),
                      quality(abs(geom['tilt']), norms['alignment_tilt_scale_rad']),
                      quality(abs(geom['yaw']), norms['alignment_yaw_scale_rad'])) if all(geom[k] is not None for k in ('lateral', 'tilt', 'yaw')) else None,
            insert=metrics['depth_ratio']['value'],
            support_transfer=float(np.clip(support_force/thresholds['support_min_N'], 0., 1.)) if support_force is not None else None,
            release_retreat=float(np.clip(clearance_gripper/thresholds['retreat_clearance_m'], 0., 1.)) if released is True and clearance_gripper is not None else (0. if released is False else None),
            stable_complete=float(np.clip(stable_window['continuous_duration_s']/thresholds['stable_duration_s'], 0., 1.)) if stable_window['available'] else None)
        stages = {}
        for name in STAGES:
            milestone = self._milestones[name]
            fact = milestone['current_satisfied']
            status = 'current_satisfied' if fact is True else 'evidence_missing' if fact is None else 'in_progress' if (self._since[name] is not None or current_stage == name) else 'regressed' if milestone['ever_achieved'] else 'not_started'
            stages[name] = dict(milestone, status=status, continuous=continuous[name])
        highest = max((i for i, name in enumerate(STAGES) if self._milestones[name]['ever_achieved']), default=-1)
        snapshot = dict(progress_schema_version=SCHEMA_VERSION, progress_evaluator_version=EVALUATOR_VERSION,
            config_hash=self.config['config_hash'], episode_id=self.metadata.get('episode_id'),
            t=t, physics_step=row.get('physics_step'), sample_index=self._sample_count,
            current_stage=current_stage, current_stage_continuous=continuous[current_stage],
            stage_vector=[stages[name]['current_satisfied'] for name in STAGES], stage_order=list(STAGES),
            stages=stages, milestones=copy.deepcopy(self._milestones), metrics=metrics,
            hold_state=hold_state, hold_evidence=dict(source_supported=source_supported, gripper_held=held, target_supported=support),
            attempt_id=self._active_attempt['attempt_id'] if self._active_attempt else None,
            highest_ever_stage=STAGES[highest] if highest >= 0 else None,
            coverage_progress=sum(int(self._milestones[name]['ever_achieved']) for name in STAGES)/len(STAGES),
            coverage_progress_definition='fixed equal weight historical stage coverage; not current physical success or reward',
            stable_window=stable_window, events=copy.deepcopy(self.events[event_start:]),
            evidence=dict(sampling_gap=gap, phase_used_as_success_evidence=False,
                          raw_fields_present=sorted(key for key in ('object_position_m', 'object_quaternion_wxyz', 'finger_contact_N', 'cup_in_hand_position_m', 'target_region_contains_object', 'input_geometry_overlap_observed_m', 'gripper_object_clearance_m') if row.get(key) is not None)))
        self._last_snapshot = plain(snapshot)
        self._last_row = {key: plain(row[key]) for key in ('object_position_m', 'position') if key in row}
        self._last_t = t
        self._sample_count += 1
        return copy.deepcopy(self._last_snapshot)

    @staticmethod
    def _termination_domain(termination):
        explicit = termination.get('termination_domain')
        if explicit:
            return explicit
        text = (str(termination.get('termination_reason', ''))+' '+str(termination.get('failure_type', ''))).upper()
        # A service deadline is a service interruption, distinct from the
        # environment's task time limit. Keep the original reason alongside it.
        for words, domain in [(['SERVICE', 'MODEL_ERROR', 'PROVIDER'], 'service_interruption'),
            (['SAFETY', 'COLLISION', 'GEOMETRY_VIOLATION'], 'safety_stop'), (['TIMEOUT', 'TIME_LIMIT'], 'timeout'),
            (['INTERRUPT', 'PROCESS_ABORT', 'RESET_', 'ENVIRONMENT_CLOSED'], 'interruption'),
            (['EXECUTOR', 'TRACKING_ERROR', 'CONTROL_OR_IK'], 'executor_failure'), (['SIMULATION', 'NONFINITE'], 'simulation_failure'),
            (['RECORDING', 'WRITER'], 'recording_failure')]:
            if any(word in text for word in words):
                return domain
        return 'normal_end'

    def _unfinished(self):
        if self._last_snapshot is None:
            return dict(code='GRASP_NOT_ESTABLISHED', stage='grasp', requirement='physical grasp evidence', available=False)
        snapshot = self._last_snapshot
        if snapshot['stages']['stable_complete']['current_satisfied'] is True:
            return None
        milestone = self._milestones
        held = snapshot['hold_evidence']['gripper_held']
        supported = snapshot['hold_evidence']['target_supported']
        # finalize closes the active grip before calling this method. The last
        # causal snapshot identifies its attempt without borrowing another
        # attempt's historical milestones or relying on that cleared pointer.
        attempt = next((a for a in reversed(self.attempts)
            if a['attempt_id'] == snapshot['attempt_id']), None)
        released_attempt = (self.attempts[-1] if self.attempts and
            self.attempts[-1]['ended_by'] == 'legal_target_support_release' else None)
        # This is an unfulfilled current requirement, never a failure fact.
        # A legal release on the source needs a fresh grasp. A legal release on
        # the target proceeds through support/release/retreat/stability gates.
        if supported is not True and held is not True and released_attempt is None:
            code, stage, requirement = 'GRASP_NOT_ESTABLISHED', 'grasp', 'verify or re-establish a measured bilateral grasp'
        elif supported is not True and held is True and (attempt is None or not attempt['source_clear_confirmed'] or
                snapshot['stages']['extract']['current_satisfied'] is not True):
            code, stage, requirement = 'EXTRACTION_NOT_COMPLETED', 'extract', 'clear source rim with the complete tilted vessel envelope while held'
        elif supported is not True and held is True and (not attempt['held_transport_confirmed'] or not attempt['preinsert_region_reached']):
            code, stage, requirement = 'TRANSPORT_NOT_COMPLETED', 'transport', 'reach fixed preinsert region with same-attempt held-object evidence'
        elif supported is not True and held is True and snapshot['stages']['align']['current_satisfied'] is not True:
            code, stage, requirement = 'ALIGNMENT_NOT_COMPLETED', 'align', 'satisfy measured loading-frame lateral, tilt and full-yaw gates'
        elif supported is not True and held is True and snapshot['stages']['insert']['current_satisfied'] is not True:
            code, stage, requirement = 'INSERTION_NOT_COMPLETED', 'insert', 'reach requested depth with valid target, posture and route evidence'
        elif supported is not True:
            code, stage, requirement = 'SUPPORT_TRANSFER_NOT_COMPLETED', 'support_transfer', 'establish correct-target classified bottom support'
        elif milestone['released']['current_satisfied'] is not True:
            code, stage, requirement = 'RELEASE_NOT_COMPLETED', 'release_retreat', 'open both actual fingers and lose both contacts under legal support'
        elif milestone['retreated']['current_satisfied'] is not True:
            code, stage, requirement = 'RETREAT_NOT_COMPLETED', 'release_retreat', 'reach actual gripper geometry clearance requirement'
        else:
            code, stage, requirement = 'STABILITY_WINDOW_NOT_COMPLETED', 'stable_complete', 'complete a continuous causally observed stable window'
        return dict(code=code, stage=stage, requirement=requirement,
                    available=milestone[stage]['current_satisfied'] is not None)

    def finalize(self, termination_dict=None):
        if self._finalized is not None:
            return copy.deepcopy(self._finalized)
        termination = plain(termination_dict or {})
        domain = self._termination_domain(termination)
        if self._active_attempt is not None:
            self._end_attempt(self._last_t if self._last_t is not None else 0.,
                'interrupted' if domain not in {'normal_end', 'timeout'} else 'incomplete',
                'episode_terminated:'+domain)
        stages = copy.deepcopy(self._last_snapshot['stages']) if self._last_snapshot else {
            name: dict(self._milestones[name], status='not_reached', continuous=None) for name in STAGES}
        for name, stage in stages.items():
            if stage['first_candidate_t'] is None:
                stage['terminal_status'] = 'not_reached'
            elif stage['current_satisfied'] is True:
                stage['terminal_status'] = 'current_satisfied'
            elif stage['ever_achieved']:
                stage['terminal_status'] = 'previously_achieved_currently_unmet'
            else:
                stage['terminal_status'] = 'interrupted' if domain not in {'normal_end', 'timeout'} else 'incomplete'
        unfinished = self._unfinished()
        complete = self._milestones['stable_complete']['current_satisfied']
        if complete is None and self._last_snapshot and unfinished and unfinished['available']:
            complete = False
        self._finalized = plain(dict(progress_schema_version=SCHEMA_VERSION,
            progress_evaluator_version=EVALUATOR_VERSION, config_hash=self.config['config_hash'],
            episode_id=self.metadata.get('episode_id'), progress_complete=complete,
            termination_domain=domain, termination=termination, unfinished_requirement=unfinished,
            failure_observation=self.failure_observations,
            stages=stages, milestones=copy.deepcopy(self._milestones), attempts=copy.deepcopy(self.attempts),
            retry_count=max(0, len(self.attempts)-1), events=copy.deepcopy(self.events),
            event_count=len(self.events), physical_sample_count=self._sample_count,
            evidence_gap_count=self._gap_count, unknown_metric_sample_counts=self._unknown_counts,
            input_evidence=copy.deepcopy(self.metadata), last_snapshot=copy.deepcopy(self._last_snapshot),
            original_scoring_unchanged=True, reward_unchanged=True,
            current_and_historical_status_separate=True))
        return copy.deepcopy(self._finalized)
