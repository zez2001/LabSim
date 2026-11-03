"""Attempt intervals and lifecycle replay; all fixtures are CPU synthetic data."""
import copy
import math

import pytest

from demos.lab_cuvette_progress_v1.attempts import (
    attempt_event_evidence, candidate_stage, confirm_stage,
    end_operation_statistics, new_attempt_fields, observe_drift, set_reference)
from demos.lab_cuvette_progress_v1.replay import replay_attempts, verify_replay


def attempt(aid=1, previous=None):
    return dict(attempt_id=aid, start_t=0., end_t=None, outcome='incomplete',
        ended_by=None, completed_stages={}, previous_attempt_id=previous,
        recovered_from_attempt_id=None, next_attempt_id=None,
        **new_attempt_fields(240.))


def test_fixed_reference_whole_operation_includes_quality_false_handover_motion():
    value = attempt()
    set_reference(value, 1., [0., 0., 0.], [1., 0., 0., 0.])
    observe_drift(value, 1., [0., 0., 0.], [1., 0., 0., 0.], 'gripper_held', grasp_quality=True)
    observe_drift(value, 1.+1/240, [.00001, 0., 0.], [1., 0., 0., 0.], 'gripper_held', grasp_quality=True)
    t = 1.+2/240
    q = [math.cos(.033322/2), 0., 0., math.sin(.033322/2)]
    observe_drift(value, t, [.001651, 0., 0.], q, 'target_supported',
        first_support_transfer_t=t, grasp_quality=False)
    end_operation_statistics(value, t)
    stats = value['relative_motion_statistics']
    assert value['maximum_relative_translation_m'] == pytest.approx(.001651)
    assert value['maximum_relative_rotation_rad'] == pytest.approx(.033322)
    assert stats['before_first_target_support']['maximum_relative_translation_m'] == pytest.approx(.00001)
    assert stats['support_transfer']['sample_count'] == 1
    assert stats['operation']['sample_count'] == 3
    assert stats['operation']['grasp_quality_false_sample_count'] == 1
    assert stats['operation']['translation_peak_t'] == t
    assert stats['operation']['translation_peak_hold_state'] == 'target_supported'
    assert stats['operation']['translation_peak_grasp_quality'] is False
    assert stats['operation']['observed_sampling_frequency_hz'] == pytest.approx(240.)
    assert stats['before_first_target_support']['end_inclusive'] is False
    assert stats['before_first_target_support']['declared_end_t'] == t
    assert all(stats[key]['quality_filter_applied'] is False for key in stats)


def test_missing_samples_counted_and_no_reference_reset_can_hide_motion():
    value = attempt()
    set_reference(value, .1, [0., 0., 0.], [1., 0., 0., 0.])
    observe_drift(value, .1, None, None, 'unknown', grasp_quality=None)
    observe_drift(value, .2, [.002, 0., 0.], None, 'gripper_held', grasp_quality=False)
    end_operation_statistics(value, .2)
    whole = value['relative_motion_statistics']['operation']
    assert whole['sample_count'] == 2
    assert whole['valid_sample_count'] == 0
    assert whole['missing_sample_count'] == 2
    assert whole['translation_valid_sample_count'] == 1
    assert whole['rotation_missing_sample_count'] == 2
    assert whole['maximum_relative_translation_m'] == pytest.approx(.002)
    assert whole['maximum_relative_rotation_rad'] is None
    assert whole['grasp_quality_false_sample_count'] == 1
    assert whole['grasp_quality_unknown_sample_count'] == 1
    assert whole['available'] is False
    assert value['relative_motion_statistics']['support_transfer']['declared_start_t'] is None
    with pytest.raises(ValueError, match='immutable'):
        set_reference(value, .2, [.002, 0., 0.], [1., 0., 0., 0.])
    with pytest.raises(ValueError, match='after operation'):
        observe_drift(value, .3, [.002, 0., 0.], None, 'gripper_held')


def test_first_stage_candidate_and_confirmation_preserved_with_reconfirm_count():
    value = attempt()
    candidate_stage(value, 'align', 10.)
    confirm_stage(value, 'align', 11., 10.5)
    confirm_stage(value, 'align', 20., 19.)
    assert value['completed_stages']['align'] == 11.
    assert value['stage_timing']['align'] == dict(first_candidate_t=10.,
        first_confirmed_t=11., last_confirmed_t=20., confirmation_count=2,
        duration_basis='first candidate to first confirmation',
        first_candidate_to_first_confirmation_s=1.,
        attempt_start_to_first_confirmation_s=11.)


def event(index, name, t, value):
    return dict(event_id=index, name=name, t=t, attempt_id=value['attempt_id'],
        evidence=attempt_event_evidence(value))


def test_event_only_replay_keeps_operation_end_separate_from_final_outcome():
    value = attempt()
    events = [event(1, 'attempt_started', 0., value)]
    value.update(end_t=1., operation_end_t=1., ended_by='legal_target_support_release')
    events.append(event(2, 'attempt_ended', 1., value))
    assert events[-1]['evidence']['attempt']['outcome'] == 'incomplete'
    value.update(outcome='success', outcome_confirmed_t=4., outcome_reason='stable_window_confirmed', final_outcome_confirmed=True)
    events.append(event(3, 'attempt_outcome_updated', 4., value))
    replay = verify_replay(events, dict(attempts=[value], retry_count=0))
    assert replay['passed'] is True
    assert replay['attempts'][0]['operation_end_t'] == 1.
    assert replay['attempts'][0]['outcome_confirmed_t'] == 4.
    assert events[1]['evidence']['attempt']['outcome'] == 'incomplete'


def test_retry_relation_reconstructed_and_no_duplicate_events_needed_for_finalize():
    first = attempt()
    events = [event(1, 'attempt_started', 0., first)]
    first.update(end_t=1., operation_end_t=1., outcome='failure', ended_by='unsupported_grasp_loss')
    events.append(event(2, 'attempt_ended', 1., first))
    second = attempt(2, previous=1)
    second.update(start_t=2., recovered_from_attempt_id=1)
    events.append(event(3, 'attempt_started', 2., second))
    second.update(end_t=3., operation_end_t=3., outcome='interrupted', ended_by='episode_terminated:interruption')
    events.append(event(4, 'attempt_ended', 3., second))
    first['next_attempt_id'] = 2
    replay = verify_replay(events, dict(attempts=[first, second], retry_count=1))
    assert replay['passed'] is True
    assert replay['attempts'][1]['recovered_from_attempt_id'] == 1
    assert replay['attempt_count'] == 2
    assert replay_attempts(copy.deepcopy(events)) == replay_attempts(events)


def test_legacy_events_missing_receipts_are_explicitly_incomplete():
    result = replay_attempts([dict(event_id=1, name='attempt_started', t=0., attempt_id=1, evidence={})])
    assert result['complete'] is False
    assert result['warnings'][0]['reason'] == 'attempt_receipt_missing'


def test_duplicate_id_or_backwards_event_clock_is_rejected():
    value = attempt()
    with pytest.raises(ValueError, match='IDs'):
        replay_attempts([event(1, 'attempt_started', 0., value), event(1, 'attempt_ended', 1., value)])
    with pytest.raises(ValueError, match='times'):
        replay_attempts([event(1, 'attempt_started', 1., value), event(2, 'attempt_ended', 0., value)])


def test_post_outcome_stage_reconfirmation_increment_is_replayed():
    value = attempt()
    events = [event(1, 'attempt_started', 0., value)]
    value.update(end_t=1., operation_end_t=1., ended_by='legal_target_support_release')
    confirm_stage(value, 'stable_complete', 4., 1.)
    value.update(outcome='success', outcome_confirmed_t=4., final_outcome_confirmed=True)
    events.append(event(2, 'attempt_outcome_updated', 4., value))
    events.append(dict(event_id=3, name='stable_complete_candidate', t=5., attempt_id=1, evidence={}))
    events.append(dict(event_id=4, name='stable_complete_confirmed', t=8., candidate_start_t=5., attempt_id=1, evidence={}))
    confirm_stage(value, 'stable_complete', 8., 5.)
    result = verify_replay(events, dict(attempts=[value], retry_count=0))
    assert result['passed'] is True
    assert result['attempts'][0]['stage_timing']['stable_complete']['first_confirmed_t'] == 4.
    assert result['attempts'][0]['stage_timing']['stable_complete']['last_confirmed_t'] == 8.
    assert result['attempts'][0]['stage_timing']['stable_complete']['confirmation_count'] == 2


@pytest.mark.parametrize('termination,expected', [
    ('TIMEOUT', 'incomplete'), ('USER_INTERRUPTED', 'interrupted'), ('SERVICE_TIMEOUT', 'interrupted')])
def test_actual_evaluator_termination_event_replay(termination, expected):
    # Reuse the shared synthetic physical-state fixture used by the evaluator
    # contract suite; it is not a saved experimental episode.
    from test_lab_cuvette_progress_core import Trace, evaluate
    evaluator, _ = evaluate(Trace().held_route().rows)
    summary = evaluator.finalize(dict(termination_reason=termination))
    assert summary['attempts'][0]['outcome'] == expected
    assert verify_replay(evaluator.events, summary)['passed'] is True
    before = copy.deepcopy(evaluator.events)
    assert evaluator.finalize(dict(termination_reason='OTHER')) == summary
    assert evaluator.events == before


def test_actual_evaluator_retry_and_recovery_replay():
    from test_lab_cuvette_progress_core import Trace, evaluate
    trace = Trace().held_route().add((.15, 0., .15), held=False, n=7)
    trace.add((0., 0., .00002), held=False, n=2).success()
    evaluator, _ = evaluate(trace.rows)
    summary = evaluator.finalize()
    result = verify_replay(evaluator.events, summary)
    assert result['passed'] is True
    assert result['retry_count'] == 1
    assert [value['outcome'] for value in result['attempts']] == ['failure', 'success']


def test_actual_evaluator_post_success_instability_and_recovery_replay():
    from test_lab_cuvette_progress_core import Trace, evaluate
    trace = Trace().success()
    # Move while still legally supported, outside the 0.2mm stable-drift gate
    # but within the post-release valid target envelope, then allow a fresh
    # complete 3s physical stability window at the new pose.
    trace.add((.3003, 0., .12), held=False, support=.2, clearance=.05, n=65)
    evaluator, snapshots = evaluate(trace.rows)
    summary = evaluator.finalize()
    updates = [event for event in evaluator.events if event['name'] == 'attempt_outcome_updated']
    assert any(event['evidence']['outcome'] == 'success' for event in updates)
    assert any(event['evidence'].get('provisional') is True for event in updates)
    assert updates[-1]['evidence']['outcome'] == 'success'
    assert summary['attempts'][0]['operation_end_t'] < summary['attempts'][0]['outcome_confirmed_t']
    assert verify_replay(evaluator.events, summary)['passed'] is True
