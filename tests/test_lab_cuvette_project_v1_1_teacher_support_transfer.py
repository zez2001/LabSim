"""Teacher-only gated unload clock on CPU; not a physical support simulation."""
import copy
import importlib.util
from pathlib import Path

import numpy as np
import pytest
from scipy.spatial.transform import Rotation

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('teacher_support_cpu_helpers',
    ROOT / 'tests/test_lab_cuvette_project_v1_1_teacher_clock.py')
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)
fixture = helper.fixture


def support_teacher(fixture):
    make, debug, parent, _, cfg = fixture
    cfg = copy.deepcopy(cfg)
    cfg['control'].update(alignment_budget_m=.0001, tilt_budget_deg=.15, yaw_budget_deg=.2)
    cfg['demo_release'] = dict(unload_seconds=3., support_window_s=.5)
    controller = make(configuration=cfg)
    debug = copy.deepcopy(debug)
    debug.update(object_position_m=controller.floor.tolist(),
        actual_tcp_position_m=(controller.floor + [0, 0, .053]).tolist(),
        target_bottom_gap_m=0., target_bottom_support_N=.1962,
        native_target_overlap_m=0., yaw_error_deg=0., tilt_deg=0., xy_error_target_m=[0., 0.])
    helper.enter(controller, debug, 'SUPPORT_TRANSFER')
    controller.latch_opening = .01
    controller.contact_opening = .011
    return controller, debug, parent


def run_ticks(controller, debug, first, last):
    return [helper.act(controller, debug, tick/60) for tick in range(first, last+1)]


def test_uninterrupted_alignment_preserves_original_three_second_effort_and_opening_ramp(fixture):
    controller, debug, _ = support_teacher(fixture)
    for tick in range(1, 180):
        action = helper.act(controller, debug, tick/60)
        elapsed = tick/60
        assert action['gripper_effort_limit_N'] == pytest.approx(8. - 7.95*elapsed/3.)
        assert action['gripper_opening_m'] == pytest.approx(.01+.001*elapsed/3.)
        support = action['metadata']['support_transfer']
        assert support['unload_elapsed_s'] == pytest.approx(elapsed)
        assert support['physical_phase_elapsed_s'] == pytest.approx(elapsed)
        assert action['metadata']['motion_time_scale'] == 1.
        assert action['duration_s'] == 1/60
        assert controller.phase_start == 0.
    final = helper.act(controller, debug, 3.)
    assert controller.phase == 'OPEN'
    assert final['gripper_effort_limit_N'] == pytest.approx(.05)
    assert final['metadata']['teacher_phase'] == 'OPEN'
    transition = next(e for e in controller.events if e.get('target') == 'OPEN')
    assert transition['t'] == 3. and controller.phase_start == 3.


def test_outside_budget_pauses_unload_but_applies_existing_bounded_xy_and_orientation_feedback(fixture):
    controller, debug, parent = support_teacher(fixture)
    previous = run_ticks(controller, debug, 1, 60)[-1]
    debug['xy_error_target_m'] = [.000188, 0.]
    debug['object_position_m'] = (controller.floor + [.000188, 0., 0.]).tolist()
    debug['tilt_deg'] = .2
    debug['object_quaternion_wxyz'] = parent.wxyz(Rotation.from_euler('x', .2, degrees=True)
        * Rotation.from_euler('z', 90., degrees=True))
    before_target = controller.target.copy()
    before_rotation = controller.rotation_command
    action = helper.act(controller, debug, 61/60)
    assert np.linalg.norm(np.asarray(action['values'][:2])-before_target[:2]) == pytest.approx(.00002)
    assert np.rad2deg((controller.rotation_command*before_rotation.inv()).magnitude()) == pytest.approx(.1)
    assert action['values'][2] == before_target[2]  # No resumed descent.
    assert action['gripper_effort_limit_N'] == previous['gripper_effort_limit_N']
    assert action['gripper_opening_m'] == previous['gripper_opening_m']
    support = action['metadata']['support_transfer']
    assert support['unload_elapsed_s'] == pytest.approx(1.)
    assert support['unloading_paused'] is True
    assert support['alignment']['measured']['xy_m'] == pytest.approx(.000188)
    assert len(support['pause_reasons']) == 2
    for action in run_ticks(controller, debug, 62, 240):
        assert action['gripper_effort_limit_N'] == previous['gripper_effort_limit_N']
        assert action['gripper_opening_m'] == previous['gripper_opening_m']
    assert controller.phase == 'SUPPORT_TRANSFER' and not controller.finished


def test_resume_requires_consecutive_alignment_then_continues_without_force_reincrease(fixture):
    controller, debug, _ = support_teacher(fixture)
    run_ticks(controller, debug, 1, 60)
    debug['yaw_error_deg'] = .201
    paused = run_ticks(controller, debug, 61, 180)[-1]
    debug['yaw_error_deg'] = 0.
    first = helper.act(controller, debug, 181/60)
    assert first['metadata']['support_transfer']['pause_reasons'] == ['awaiting_consecutive_aligned_observations']
    assert first['gripper_effort_limit_N'] == paused['gripper_effort_limit_N']
    prior_effort, prior_opening = first['gripper_effort_limit_N'], first['gripper_opening_m']
    for tick in range(182, 305):
        action = helper.act(controller, debug, tick/60)
        assert action['gripper_effort_limit_N'] <= prior_effort + 1e-12
        assert action['gripper_opening_m'] >= prior_opening - 1e-12
        prior_effort, prior_opening = action['gripper_effort_limit_N'], action['gripper_opening_m']
        if controller.phase == 'OPEN':
            break
    assert controller.phase == 'OPEN'
    assert controller.phase_start > 5.
    assert action['metadata']['support_transfer']['unload_elapsed_s'] == 3.


@pytest.mark.parametrize('override,expected_reason', [
    ({'xy_error_target_m': [.00008, .00008]}, 'xy_m_outside_original_alignment_budget'),
    ({'tilt_deg': -.150001}, 'tilt_deg_outside_original_alignment_budget'),
    ({'yaw_error_deg': -.200001}, 'yaw_deg_outside_original_alignment_budget'),
    ({'tilt_deg': None}, 'tilt_deg_unavailable_or_nonfinite'),
    ({'tilt_deg': float('nan')}, 'tilt_deg_unavailable_or_nonfinite'),
    ({'yaw_error_deg': None}, 'yaw_deg_unavailable_or_nonfinite'),
    ({'yaw_error_deg': float('nan')}, 'yaw_deg_unavailable_or_nonfinite'),
    ({'xy_error_target_m': [float('nan'), 0.]}, 'xy_m_unavailable_or_nonfinite'),
    ({'xy_error_target_m': [0., 0., 0.]}, 'xy_m_unavailable_or_nonfinite'),
])
def test_exact_scorer_norm_absolute_angles_and_unknowns_gate_unloading(fixture, override, expected_reason):
    controller, debug, _ = support_teacher(fixture)
    debug.update(override)
    action = helper.act(controller, debug, 1/60)
    support = action['metadata']['support_transfer']
    assert expected_reason in support['pause_reasons']
    assert support['unload_elapsed_s'] == 0.
    assert action['gripper_effort_limit_N'] == 8.
    assert action['gripper_opening_m'] == .01
    assert controller.phase == 'SUPPORT_TRANSFER'


def test_same_inclusive_alignment_boundaries_and_original_config_thresholds(fixture):
    controller, debug, _ = support_teacher(fixture)
    debug.update(xy_error_target_m=[.0001, 0.], tilt_deg=-.15, yaw_error_deg=-.2)
    result = controller._support_alignment(debug)
    assert result['aligned'] is True
    assert result['budgets'] == {'xy_m': .0001, 'tilt_deg': .15, 'yaw_deg': .2}
    from omegaconf import OmegaConf
    cfg = OmegaConf.load(ROOT / 'config/lab_cuvette_loading/Project_v1_1/standard.yaml')
    assert list(result['budgets'].values()) == [cfg.control.alignment_budget_m,
        cfg.control.tilt_budget_deg, cfg.control.yaw_budget_deg]


@pytest.mark.parametrize('missing_gate', ['alignment', 'support', 'quiet', 'unload_complete'])
def test_open_requires_every_gate_in_same_observation_even_with_elapsed_unload(fixture, missing_gate):
    controller, debug, _ = support_teacher(fixture)
    helper.act(controller, debug, 1/60)
    controller._support_unload_elapsed_s = 3. if missing_gate != 'unload_complete' else 2.
    if missing_gate == 'alignment':
        debug['xy_error_target_m'] = [.000101, 0.]
    if missing_gate == 'support':
        debug['target_bottom_support_N'] = 0.
    controller._quiet = lambda t, seconds: missing_gate != 'quiet'
    helper.act(controller, debug, 2/60)
    assert controller.phase == 'SUPPORT_TRANSFER'
    if missing_gate == 'unload_complete':
        assert controller._support_unload_elapsed_s < 3.


def test_watchdog_is_real_ten_seconds_even_if_paused_or_alignment_returns_late(fixture):
    controller, debug, _ = support_teacher(fixture)
    debug['xy_error_target_m'] = [.000188, 0.]
    run_ticks(controller, debug, 1, 600)
    assert not controller.finished and controller.phase == 'SUPPORT_TRANSFER'
    assert controller._support_unload_elapsed_s == 0.
    # Even a completed ramp and a late valid support sample cannot escape via OPEN.
    controller._support_unload_elapsed_s = 3.
    controller._quiet = lambda t, seconds: True
    debug['xy_error_target_m'] = [0., 0.]
    final = helper.act(controller, debug, 10.01)
    assert controller.finished and controller.status == 'SUPPORT_TRANSFER_FAILED'
    assert controller.phase == 'SUPPORT_TRANSFER'
    assert final['metadata']['teacher_finished'] is True
    assert final['metadata']['teacher_status'] == 'SUPPORT_TRANSFER_FAILED'
    assert final['metadata']['support_transfer']['physical_watchdog_expired'] is True
    assert controller.events[-1]['t'] == 10.01
    assert not any(e.get('target') == 'OPEN' for e in controller.events)


def test_repeat_and_reset_do_not_double_feedback_or_reuse_unload_progress(fixture):
    controller, debug, _ = support_teacher(fixture)
    action = helper.act(controller, debug, .5)
    target = controller.target.copy()
    again = helper.act(controller, debug, .5)
    assert again == action
    np.testing.assert_array_equal(controller.target, target)
    assert controller._support_unload_elapsed_s == .5
    controller.reset()
    assert controller._support_unload_elapsed_s == 0.
    assert controller._support_last_actual is None and controller._support_previous_aligned is None
    assert controller._support_physical_start is None and controller._support_gate_context is None


def test_parent_supported_remains_unchanged_outside_support_and_after_context_cleanup(fixture):
    controller, debug, _ = support_teacher(fixture)
    debug['xy_error_target_m'] = [.001, 0.]
    assert controller._supported(debug) is True  # No private active context.
    action = helper.act(controller, debug, .5)
    assert action['metadata']['support_transfer']['alignment']['aligned'] is False
    assert controller._support_gate_context is None
    for phase in ('INSERT', 'OPEN', 'VERIFY'):
        controller.phase = phase
        assert controller._supported(debug) is True


def test_irregular_physical_intervals_do_not_retroactively_unload_a_paused_interval(fixture):
    controller, debug, _ = support_teacher(fixture)
    helper.act(controller, debug, .1)
    debug['yaw_error_deg'] = .3
    helper.act(controller, debug, .23)
    debug['yaw_error_deg'] = 0.
    helper.act(controller, debug, .61)
    resumed = helper.act(controller, debug, .68)
    assert resumed['metadata']['support_transfer']['unload_elapsed_s'] == pytest.approx(.17)
    assert resumed['gripper_effort_limit_N'] == pytest.approx(8.-7.95*.17/3.)


def test_completed_unload_still_requires_two_aligned_samples_after_an_alignment_pause(fixture):
    controller, debug, _ = support_teacher(fixture)
    debug['yaw_error_deg'] = .3
    helper.act(controller, debug, .1)
    controller._support_unload_elapsed_s = 3.
    controller._quiet = lambda t, seconds: True
    debug['yaw_error_deg'] = 0.
    first = helper.act(controller, debug, .2)
    assert first['metadata']['support_transfer']['unloading_paused'] is True
    assert controller.phase == 'SUPPORT_TRANSFER'
    helper.act(controller, debug, .3)
    assert controller.phase == 'OPEN' and controller.phase_start == .3


def test_support_entry_starts_zero_ramp_and_does_not_include_previous_insert_time(fixture):
    controller, debug, _ = support_teacher(fixture)
    controller._enter('INSERT', 0.)
    controller.grasp_reference = controller._relative(debug)
    debug['finger_contact_N'] = [1., 1.]
    helper.act(controller, debug, 2.)
    assert controller.phase == 'SUPPORT_TRANSFER' and controller.phase_start == 2.
    assert controller._support_unload_elapsed_s == 0.
    following = helper.act(controller, debug, 2.+1/60)
    assert following['metadata']['support_transfer']['unload_elapsed_s'] == pytest.approx(1/60)
    assert following['metadata']['support_transfer']['physical_phase_elapsed_s'] == pytest.approx(1/60)


def test_support_quiet_window_and_global_timeout_use_physical_observation_time(fixture):
    controller, debug, _ = support_teacher(fixture)
    controller.cfg['control']['timeout_s'] = .7
    seen = []
    controller._quiet = lambda t, seconds: seen.append((t, seconds)) or True
    controller._support_unload_elapsed_s = 3.
    # Initialize support phase mapping without opening yet.
    debug['target_bottom_support_N'] = 0.
    helper.act(controller, debug, .6)
    debug['target_bottom_support_N'] = .1962
    controller._support_unload_elapsed_s = 3.
    helper.act(controller, debug, .71)
    assert seen == [(.71, .5)]
    assert controller.finished and controller.status == 'TIMEOUT'
    assert controller.events[-1]['t'] == .71


def test_parent_quaternion_alias_is_normalized_before_support_feedback(fixture):
    controller, debug, _ = support_teacher(fixture)
    debug['quaternion_wxyz'] = debug.pop('object_quaternion_wxyz')
    action = helper.act(controller, debug, 1/60)
    assert action['metadata']['support_transfer_control_active'] is True
    assert action['metadata']['support_transfer']['alignment']['aligned'] is True


@pytest.mark.parametrize('kind', ['missing', 'none', 'nan'])
def test_missing_tilt_fails_closed_before_the_historical_support_helper_reads_it(fixture, kind):
    controller, debug, _ = support_teacher(fixture)
    helper.act(controller, debug, .1)
    controller._support_unload_elapsed_s = 3.  # Parent now evaluates its OPEN support predicate.
    if kind == 'missing':
        del debug['tilt_deg']
    else:
        debug['tilt_deg'] = None if kind == 'none' else float('nan')
    action = helper.act(controller, debug, .2)
    assert action['metadata']['support_transfer']['alignment']['aligned'] is False
    assert 'tilt_deg_unavailable_or_nonfinite' in action['metadata']['support_transfer']['pause_reasons']
    assert controller.phase == 'SUPPORT_TRANSFER' and controller._support_unload_elapsed_s == 3.
