"""Bounded, causal attempt bookkeeping for Progress v1.2.

Only one fixed cup-in-hand reference is accepted per attempt.  The summaries
cover every physical sample in each declared interval, including samples whose
grasp-quality flag is false.  These are observed relative-motion statistics,
not an attribution of all motion to grasp failure.
"""
from __future__ import annotations

import copy
import math

from .geometry import number, rotation, rotation_distance, vector


INTERVALS = {
    'operation': 'reference_t <= sample_t <= operation_end_t; entire operation, including support handover',
    'before_first_target_support': 'reference_t <= sample_t < first support_transfer confirmation; if none, through operation_end_t',
    'support_transfer': 'first support_transfer confirmation <= sample_t <= operation_end_t',
}


def _empty_interval(name, sample_hz):
    return dict(interval_definition=INTERVALS[name], available=False,
        declared_start_t=None, declared_end_t=None, end_inclusive=True,
        sample_start_t=None, sample_end_t=None, sample_count=0,
        valid_sample_count=0, missing_sample_count=0,
        translation_valid_sample_count=0, translation_missing_sample_count=0,
        rotation_valid_sample_count=0, rotation_missing_sample_count=0,
        grasp_quality_false_sample_count=0, grasp_quality_unknown_sample_count=0,
        maximum_relative_translation_m=None, translation_peak_t=None,
        translation_peak_hold_state=None, translation_peak_grasp_quality=None,
        maximum_relative_rotation_rad=None, rotation_peak_t=None,
        rotation_peak_hold_state=None, rotation_peak_grasp_quality=None,
        nominal_sampling_frequency_hz=sample_hz,
        observed_sampling_frequency_hz=None,
        minimum_sample_interval_s=None, maximum_sample_interval_s=None,
        reference_t=None, reference_position_m=None, reference_quaternion_wxyz=None,
        sampling_scope='physical samples after fixed attempt reference; not control-rate maxima',
        sample_count_definition='completed physical rows observed in the declared interval',
        missing_sample_count_definition='observed rows lacking finite translation or rotation evidence; does not invent samples inside an evidence gap',
        quality_filter_applied=False,
        interpretation='relative cup-in-hand motion; support-handover motion is not automatically grasp failure')


def new_attempt_fields(sample_hz=None):
    """Fields to merge into the evaluator's ordinary attempt dictionary."""
    hz = number(sample_hz)
    if hz is not None and hz <= 0:
        hz = None
    return dict(operation_end_t=None, outcome_confirmed_t=None,
        outcome_reason=None, final_outcome_confirmed=False,
        stage_timing={}, relative_pose_reference=None,
        first_support_transfer_t=None,
        relative_motion_statistics={name: _empty_interval(name, hz) for name in INTERVALS},
        maximum_relative_translation_m=None, maximum_relative_rotation_rad=None,
        relative_motion_summary_semantics='entire operation from fixed reference through operation end; see named interval statistics')


def set_reference(attempt, t, position, quaternion):
    """Establish a reference once; a later call may not erase measured slip."""
    if attempt.get('relative_pose_reference') is not None:
        raise ValueError('Attempt relative reference is immutable; start a new attempt for a new reference')
    p, q = vector(position), vector(quaternion, 4)
    if p is None or rotation(q) is None:
        raise ValueError('Attempt reference requires finite position and a nonzero finite wxyz quaternion')
    reference = dict(t=float(t), position_m=p.tolist(), quaternion_wxyz=q.tolist(),
        frame='cup in actual hand frame', source='first valid bilateral-hold reference in this attempt')
    attempt['relative_pose_reference'] = reference
    for name, interval in attempt['relative_motion_statistics'].items():
        interval.update(reference_t=float(t), reference_position_m=p.tolist(),
            reference_quaternion_wxyz=q.tolist())
        if name != 'support_transfer':
            interval['declared_start_t'] = float(t)


def candidate_stage(attempt, name, t):
    """Keep the first candidate even if it is lost before confirmation."""
    stage = attempt.setdefault('stage_timing', {}).setdefault(name, dict(
        first_candidate_t=None, first_confirmed_t=None, last_confirmed_t=None,
        confirmation_count=0, duration_basis='first candidate to first confirmation',
        first_candidate_to_first_confirmation_s=None,
        attempt_start_to_first_confirmation_s=None))
    if stage['first_candidate_t'] is None:
        stage['first_candidate_t'] = float(t)
    return stage


def confirm_stage(attempt, name, t, candidate_t=None):
    """Record first candidate/confirmation without overwriting them on re-entry."""
    candidate = number(candidate_t)
    stage = candidate_stage(attempt, name, candidate if candidate is not None else t)
    if stage['first_confirmed_t'] is None:
        stage['first_confirmed_t'] = float(t)
        stage['first_candidate_to_first_confirmation_s'] = float(t)-stage['first_candidate_t']
        stage['attempt_start_to_first_confirmation_s'] = float(t)-float(attempt['start_t'])
    stage['last_confirmed_t'] = float(t)
    stage['confirmation_count'] += 1
    attempt.setdefault('completed_stages', {}).setdefault(name, float(t))


def _observe_interval(interval, t, translation, angle, hold_state, grasp_quality):
    previous = interval['sample_end_t']
    if previous is not None and t <= previous:
        raise ValueError('Attempt drift statistics require strictly increasing physical sample times')
    if interval['sample_start_t'] is None:
        interval['sample_start_t'] = t
    interval['sample_end_t'] = t
    interval['sample_count'] += 1
    pair_valid = translation is not None and angle is not None
    interval['valid_sample_count' if pair_valid else 'missing_sample_count'] += 1
    interval['translation_valid_sample_count' if translation is not None else 'translation_missing_sample_count'] += 1
    interval['rotation_valid_sample_count' if angle is not None else 'rotation_missing_sample_count'] += 1
    interval['available'] = interval['available'] or pair_valid
    if grasp_quality is False:
        interval['grasp_quality_false_sample_count'] += 1
    elif grasp_quality is None:
        interval['grasp_quality_unknown_sample_count'] += 1
    for value, maximum_key, peak_prefix in (
            (translation, 'maximum_relative_translation_m', 'translation'),
            (angle, 'maximum_relative_rotation_rad', 'rotation')):
        if value is not None and (interval[maximum_key] is None or value > interval[maximum_key]):
            interval[maximum_key] = value
            interval[peak_prefix+'_peak_t'] = t
            interval[peak_prefix+'_peak_hold_state'] = hold_state
            interval[peak_prefix+'_peak_grasp_quality'] = grasp_quality
    if previous is not None:
        dt = t-previous
        old = interval['minimum_sample_interval_s']
        interval['minimum_sample_interval_s'] = dt if old is None else min(old, dt)
        old = interval['maximum_sample_interval_s']
        interval['maximum_sample_interval_s'] = dt if old is None else max(old, dt)
        duration = t-interval['sample_start_t']
        interval['observed_sampling_frequency_hz'] = (interval['sample_count']-1)/duration if duration > 0 else None


def observe_drift(attempt, t, position, quaternion, hold_state,
                  first_support_transfer_t=None, grasp_quality=None):
    """Accumulate one completed physical sample without filtering bad grasps."""
    reference = attempt.get('relative_pose_reference')
    if reference is None:
        return
    t = float(t)
    if t < reference['t']-1e-9:
        raise ValueError('Cannot collect attempt drift before its fixed reference')
    if attempt.get('operation_end_t') is not None and t > attempt['operation_end_t']+1e-9:
        raise ValueError('Cannot append drift samples after operation ended')
    support_t = number(first_support_transfer_t)
    if support_t is not None and attempt.get('first_support_transfer_t') is None:
        attempt['first_support_transfer_t'] = support_t
        before = attempt['relative_motion_statistics']['before_first_target_support']
        before.update(declared_end_t=support_t, end_inclusive=False)
        attempt['relative_motion_statistics']['support_transfer']['declared_start_t'] = support_t
    support_t = attempt.get('first_support_transfer_t')
    p, q = vector(position), vector(quaternion, 4)
    ref_p = vector(reference['position_m'])
    translation = float(math.sqrt(float(((p-ref_p)**2).sum()))) if p is not None else None
    angle = rotation_distance(q, reference['quaternion_wxyz']) if rotation(q) is not None else None
    names = ['operation', 'support_transfer' if support_t is not None and t >= support_t else 'before_first_target_support']
    for name in names:
        _observe_interval(attempt['relative_motion_statistics'][name], t,
            translation, angle, hold_state, grasp_quality)
    # Backwards-compatible names now have an explicitly declared v1.2 whole-
    # operation scope.  The old pre-transfer values remain in their own scope.
    whole = attempt['relative_motion_statistics']['operation']
    attempt['maximum_relative_translation_m'] = whole['maximum_relative_translation_m']
    attempt['maximum_relative_rotation_rad'] = whole['maximum_relative_rotation_rad']


def end_operation_statistics(attempt, t):
    """Close declared statistical intervals without changing final outcome."""
    t = float(t)
    old = attempt.get('operation_end_t')
    if old is not None and abs(old-t) > 1e-9:
        raise ValueError('An attempt operation interval can only end once')
    attempt['operation_end_t'] = t
    for name, interval in attempt['relative_motion_statistics'].items():
        if name == 'before_first_target_support' and attempt.get('first_support_transfer_t') is not None:
            continue
        if name == 'support_transfer' and attempt.get('first_support_transfer_t') is None:
            # No support interval occurred; do not invent one from episode end.
            continue
        interval['declared_end_t'] = t


def attempt_event_evidence(attempt, **extra):
    """Immutable complete lifecycle receipt for event-only reconstruction."""
    return dict(extra, attempt=copy.deepcopy(attempt))
