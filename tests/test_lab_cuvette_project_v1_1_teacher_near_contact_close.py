"""Near-contact teacher speed bounds on CPU; no physical contact is simulated."""
import copy
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('teacher_near_contact_cpu_helpers',
    ROOT / 'tests/test_lab_cuvette_project_v1_1_teacher_clock.py')
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)
fixture = helper.fixture


def closing_teacher(fixture, opening=.012, forces=(0., 0.), *, configuration=None):
    make, debug, _, _, _ = fixture
    teacher = make(configuration=configuration)
    helper.enter(teacher, debug, 'GRASP')
    teacher.last_grip_opening = opening
    debug['finger_contact_N'] = list(forces)
    return teacher, debug


@pytest.mark.parametrize('opening,expected_speed,limited', [(.0120001, .02, False),
    (.012, .002, True), (.011, .002, True)])
def test_nominal_width_plus_two_mm_gate_bounds_only_the_near_closing_step(
        fixture, opening, expected_speed, limited):
    teacher, debug = closing_teacher(fixture, opening)
    configuration = copy.deepcopy(teacher.cfg)
    result = helper.act(teacher, debug, 1 / 60)
    expected = opening - expected_speed / 60
    assert result['gripper_opening_m'] == pytest.approx(expected)
    assert teacher.last_grip_opening == result['gripper_opening_m']
    metadata = result['metadata']
    assert metadata['near_contact_slow_close_applied'] is limited
    assert metadata['near_contact_slow_close_zone'] is limited
    assert metadata['near_contact_nominal_outer_width_m'] == .01
    assert metadata['near_contact_close_threshold_m'] == .012
    assert metadata['near_contact_close_speed_m_s'] == .002
    assert metadata['near_contact_previous_opening_m'] == opening
    assert metadata['near_contact_parent_opening_m'] == pytest.approx(opening - .02 / 60)
    assert metadata['near_contact_dispatched_opening_m'] == expected
    assert result['gripper_effort_limit_N'] == 8.
    assert result['duration_s'] == 1 / 60
    assert metadata['teacher_controller_version'].endswith('.v3')
    assert teacher.cfg == configuration


@pytest.mark.parametrize('forces', [(0., 0.), (.07, 0.), (0., .07)])
def test_no_or_single_contact_slows_without_faking_bilateral_state(fixture, forces):
    teacher, debug = closing_teacher(fixture, forces=forces)
    result = helper.act(teacher, debug, 1 / 60)
    assert result['metadata']['near_contact_slow_close_applied'] is True
    assert result['metadata']['near_contact_bilateral_sensor_observed'] is False
    assert teacher._first_bilateral_seen is False
    assert teacher.contact_start is None and teacher._closure_freeze_opening is None
    assert teacher.latch_opening is None
    assert not any(e['event'] in ('contact_latched', 'first_bilateral_contact_stop_closure') for e in teacher.events)


def test_real_bilateral_contact_preserves_existing_freeze_and_latch(fixture):
    make, debug, _, _, _ = fixture
    new, old = make(), make(False)
    helper.enter(new, debug, 'GRASP');helper.enter(old, debug, 'GRASP')
    new.last_grip_opening = old.last_grip_opening = .011
    debug['finger_contact_N'] = [.7, 1.3]
    for tick in range(1, 10):
        actual = helper.act(new, debug, tick / 60)
        reference = helper.act(old, debug, tick / 60)
        assert actual['gripper_opening_m'] == reference['gripper_opening_m']
        assert actual['metadata']['near_contact_slow_close_zone'] is False
        assert actual['metadata']['near_contact_slow_close_applied'] is False
        assert actual['metadata']['near_contact_bilateral_sensor_observed'] is True
    assert new._first_bilateral_seen is True
    assert new.latch_opening == old.latch_opening and new.latch_time == old.latch_time
    assert [e['event'] for e in new.events] == [e['event'] for e in old.events]


def test_repeated_observation_and_next_tick_use_the_limited_previous_command(fixture):
    teacher, debug = closing_teacher(fixture)
    first = helper.act(teacher, debug, 1 / 60)
    length = len(teacher.history)
    repeated = helper.act(teacher, debug, 1 / 60)
    assert repeated == first
    assert len(teacher.history) == length
    assert teacher.last_grip_opening == first['gripper_opening_m']
    following = helper.act(teacher, debug, 2 / 60)
    assert following['metadata']['near_contact_previous_opening_m'] == first['gripper_opening_m']
    assert following['gripper_opening_m'] == pytest.approx(.012 - 2 * .002 / 60)


def test_a_slower_parent_request_is_never_accelerated(fixture):
    _, _, _, _, cfg = fixture
    cfg = copy.deepcopy(cfg)
    cfg['gripper']['close_speed_m_s'] = .001
    teacher, debug = closing_teacher(fixture, configuration=cfg)
    result = helper.act(teacher, debug, 1 / 60)
    assert result['gripper_opening_m'] == pytest.approx(.012 - .001 / 60)
    assert result['metadata']['near_contact_slow_close_applied'] is False


def test_gate_uses_configured_asset_width_and_existing_slow_speed(fixture):
    _, _, _, _, cfg = fixture
    cfg = copy.deepcopy(cfg)
    cfg['vessel']['outer_xy_m'] = [.0125, .011]
    cfg['gripper']['contact_approach_speed_m_s'] = .0015
    teacher, debug = closing_teacher(fixture, opening=.014, configuration=cfg)
    result = helper.act(teacher, debug, 1 / 60)
    assert result['metadata']['near_contact_close_threshold_m'] == .0145
    assert result['gripper_opening_m'] == pytest.approx(.014 - .0015 / 60)


@pytest.mark.parametrize('phase', ['EXTRACT', 'TRANSPORT', 'ALIGN', 'INSERT', 'SUPPORT_TRANSFER', 'OPEN', 'RETREAT', 'VERIFY'])
def test_other_phases_never_apply_near_contact_closure_cap(fixture, phase):
    make, debug, _, _, _ = fixture
    teacher = make()
    helper.enter(teacher, debug, phase)
    teacher.last_grip_opening = .012
    teacher.latch_opening = .01
    teacher.latch_time = 0.
    teacher.grasp_reference = teacher._relative(debug)
    debug['finger_contact_N'] = [1., 1.]
    result = helper.act(teacher, debug, 1 / 60)
    assert result['metadata']['near_contact_slow_close_zone'] is False
    assert result['metadata']['near_contact_slow_close_applied'] is False


def test_reset_clears_closure_cache_and_grasp_feedback_suppression(fixture):
    teacher, debug = closing_teacher(fixture)
    helper.act(teacher, debug, 1 / 60)
    teacher.reset()
    assert teacher.last_grip_opening == .08
    assert teacher._clock_cached_action is None
    assert teacher._first_bilateral_seen is False
    assert teacher._grasp_orientation_feedback_suppressed is False


@pytest.mark.parametrize('dimensions', [None, .01, '.01', [], [.01], [.01, 0.], [.01, float('nan')]])
def test_missing_or_invalid_nominal_dimensions_are_not_silently_guessed(fixture, dimensions):
    make, _, _, _, cfg = fixture
    cfg = copy.deepcopy(cfg);cfg['vessel']['outer_xy_m'] = dimensions
    with pytest.raises(ValueError, match='vessel.outer_xy_m'):
        make(configuration=cfg)


@pytest.mark.parametrize('speed', [0., -1., float('nan'), float('inf')])
def test_invalid_existing_slow_speed_is_rejected(fixture, speed):
    make, _, _, _, cfg = fixture
    cfg = copy.deepcopy(cfg);cfg['gripper']['contact_approach_speed_m_s'] = speed
    with pytest.raises(ValueError, match='gripper.contact_approach_speed_m_s'):
        make(configuration=cfg)
