"""Pure CPU state-machine checks with recorded contact-onset values."""
import json

import pytest

from demos.lab_cuvette_project_v1_1.gripper_hold import GenericContactHold


def helper(**overrides):
    values = dict(control_hz=60, mass_kg=.02, dynamic_friction=.5,
                  finger_dynamic_friction=.8, finger_kp_N_per_m=2000,
                  contact_safety_factor=2, maximum_compression_m=.0003,
                  contact_threshold_N=.03, contact_persist_s=.1,
                  contact_approach_speed_m_s=.002)
    values.update(overrides)
    return GenericContactHold(**values)


def update(hold, t=0., **overrides):
    values = dict(t=t, logical_requested_opening_m=.009, ramped_opening_m=.009,
                  previous_applied_opening_m=.009394443937804961,
                  measured_finger_positions_m=[.005385360214859247, .005385363008826971],
                  finger_contact_N=[.9883206486701965, 1.767882227897644])
    values.update(overrides)
    return hold.update(**values)


def test_recorded_first_contact_cannot_reopen_the_tighter_applied_command():
    applied, evidence = update(helper())
    assert evidence['weight_compression_per_finger_m'] == pytest.approx(.000155109719231259)
    assert evidence['weight_based_candidate_opening_m'] == pytest.approx(.0104605037852237)
    assert applied == .009394443937804961
    assert evidence['decision'] == 'first_bilateral_freeze'
    assert evidence['confirmed'] is False
    assert evidence['task_phase_or_object_pose_used'] is False
    assert evidence['force_cap_modified'] is False
    json.dumps(evidence, allow_nan=False)


def test_first_contact_uses_weight_candidate_if_it_is_narrower_than_previous():
    applied, evidence = update(helper(), previous_applied_opening_m=.011,
                               measured_finger_positions_m=[.00545, .00545])
    assert applied == evidence['weight_based_candidate_opening_m']
    assert applied < .011 and applied > .009


def test_original_three_second_schedule_is_unchanged_before_contact():
    hold = helper()
    previous = .08
    for tick in range(1, 181):
        ramped = .08 + (.009 - .08) * tick / 180
        applied, evidence = update(hold, (tick - 1) / 60,
            ramped_opening_m=ramped, previous_applied_opening_m=previous,
            finger_contact_N=[0., 0.])
        assert applied == ramped
        assert evidence['decision'] == 'original_ramp'
        previous = applied
    assert previous == pytest.approx(.009)


def test_contact_confirmation_requires_continuous_existing_persistence_window():
    hold = helper()
    target, _ = update(hold, 1.)
    for tick in range(1, 6):
        applied, evidence = update(hold, 1. + tick / 60,
            previous_applied_opening_m=target, measured_finger_positions_m=[.0052, .0052])
        assert applied == target
        assert evidence['confirmed'] is False
    applied, evidence = update(hold, 1.1, previous_applied_opening_m=target)
    assert applied == target and evidence['confirmed'] is True


def test_loss_before_confirmation_ignores_elapsed_ramp_and_closes_only_slowly():
    hold = helper()
    previous, _ = update(hold, 0.)
    for tick in range(1, 5):
        applied, evidence = update(hold, tick / 60, previous_applied_opening_m=previous,
            ramped_opening_m=.009, finger_contact_N=[0., .2])
        assert applied == pytest.approx(previous - .002 / 60)
        assert applied > .009
        assert evidence['confirmed'] is False
        assert evidence['contact_since_s'] is None
        previous = applied


def test_contact_loss_after_confirmation_also_recovers_without_instant_jump():
    hold = helper()
    previous, _ = update(hold, 0.)
    _, confirmed = update(hold, .1, previous_applied_opening_m=previous)
    assert confirmed['confirmed']
    applied, evidence = update(hold, .1 + 1 / 60,
        previous_applied_opening_m=previous, finger_contact_N=[0., 0.])
    assert applied == pytest.approx(previous - .002 / 60)
    assert evidence['previously_confirmed'] and evidence['ever_confirmed']
    assert not evidence['confirmed']


def test_recontact_restarts_confirmation_and_cannot_reopen_recovered_command():
    hold = helper()
    previous, _ = update(hold, 0.)
    previous, _ = update(hold, .05, previous_applied_opening_m=previous, finger_contact_N=[0., 0.])
    applied, evidence = update(hold, .1, previous_applied_opening_m=previous,
                              measured_finger_positions_m=[.006, .006])
    assert applied == previous
    assert evidence['contact_since_s'] == .1 and not evidence['confirmed']
    _, evidence = update(hold, .19, previous_applied_opening_m=applied)
    assert not evidence['confirmed']
    _, evidence = update(hold, .2, previous_applied_opening_m=applied)
    assert evidence['confirmed']


def test_slow_closure_stops_at_original_logical_goal_without_overshoot():
    hold = helper()
    previous, _ = update(hold, 0., previous_applied_opening_m=.00901)
    applied, _ = update(hold, 1 / 60, previous_applied_opening_m=previous,
                        finger_contact_N=[0., 0.])
    assert applied == .009
    for tick in range(2, 10):
        applied, _ = update(hold, tick / 60, previous_applied_opening_m=applied,
                            finger_contact_N=[0., 0.])
        assert applied == .009


def test_explicit_widening_releases_and_does_not_relatch_during_opening_ramp():
    hold = helper()
    previous, _ = update(hold, 0.)
    _, _ = update(hold, .1, previous_applied_opening_m=previous)
    for tick, ramped in enumerate((.010, .020, .040, .080), start=1):
        applied, evidence = update(hold, .1 + tick / 60,
            logical_requested_opening_m=.080, ramped_opening_m=ramped,
            previous_applied_opening_m=previous)
        assert applied == ramped
        assert evidence['decision'] == 'explicit_opening_ramp'
        assert evidence['frozen_opening_m'] is None and not evidence['confirmed']
        previous = applied


def test_same_logical_move_wait_preserves_target_despite_changed_measured_width():
    hold = helper()
    previous, _ = update(hold, 0.)
    for tick in range(1, 30):
        applied, evidence = update(hold, tick / 60,
            ramped_opening_m=previous, previous_applied_opening_m=previous,
            measured_finger_positions_m=[.0051, .0051])
        assert applied == previous
        assert evidence['logical_requested_opening_m'] == .009


def test_exact_threshold_and_single_finger_do_not_trigger_first_latch():
    for forces in ([.03, .03], [.02, 1.], [1., 0.]):
        applied, evidence = update(helper(), finger_contact_N=forces)
        assert applied == .009
        assert not evidence['bilateral'] and evidence['frozen_opening_m'] is None


def test_repeated_time_does_not_add_recovery_closure_and_backward_time_rejects():
    hold = helper()
    previous, _ = update(hold, 1.)
    previous, _ = update(hold, 1.1, previous_applied_opening_m=previous, finger_contact_N=[0., 0.])
    applied, _ = update(hold, 1.1, previous_applied_opening_m=previous, finger_contact_N=[0., 0.])
    assert applied == previous
    with pytest.raises(ValueError, match='backwards'):
        update(hold, 1.)


def test_reset_removes_contact_memory_for_the_next_episode():
    hold = helper()
    update(hold, 50.)
    update(hold, 50.1)
    hold.reset()
    applied, evidence = update(hold, 0., ramped_opening_m=.08,
                               previous_applied_opening_m=.08, finger_contact_N=[0., 0.])
    assert applied == .08 and not evidence['ever_confirmed']


@pytest.mark.parametrize('inputs', [dict(finger_contact_N=[float('nan'), 1.]),
    dict(measured_finger_positions_m=[float('inf'), .005]),
    dict(logical_requested_opening_m=-.001), dict(finger_contact_N=[1.]),
    dict(ramped_opening_m=.09)])
def test_invalid_sensor_or_command_input_rejects_without_advancing_helper(inputs):
    hold = helper()
    with pytest.raises(ValueError):
        update(hold, **inputs)
    assert hold.last_t is None and hold.frozen_opening_m is None
