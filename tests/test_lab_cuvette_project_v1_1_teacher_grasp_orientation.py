"""Actual teacher code, CPU observations only; not an Isaac contact simulation."""
import importlib.util
from pathlib import Path

import numpy as np
import pytest
from scipy.spatial.transform import Rotation

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('teacher_grasp_cpu_helpers',
    ROOT / 'tests/test_lab_cuvette_project_v1_1_teacher_clock.py')
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)
fixture = helper.fixture


def latched_controller(fixture, *, adapted=True):
    make, debug, parent, _, _ = fixture
    controller = make(adapted)
    helper.enter(controller, debug, 'GRASP')
    controller.latch_opening = .009666666666666539
    controller.latch_time = .1
    controller.grasp_reference = controller._relative(debug)
    debug['finger_contact_N'] = [1., 1.]
    debug['object_quaternion_wxyz'] = parent.wxyz(Rotation.from_euler('y', .265, degrees=True)
        * Rotation.from_euler('z', 90., degrees=True))
    return controller, debug, parent


def test_grasp_latched_truth_tilt_does_not_reorient_closed_hand_and_declares_suppression(fixture):
    controller, debug, _ = latched_controller(fixture)
    start = controller.rotation_command.as_matrix().copy()
    position = controller.anchor.copy()
    for tick in range(1, 31):
        action = helper.act(controller, debug, .1 + tick / 60)
        np.testing.assert_allclose(controller.rotation_command.as_matrix(), start, atol=1e-15)
        np.testing.assert_array_equal(action['values'][:3], position)
        assert action['gripper_opening_m'] == controller.latch_opening
        assert action['gripper_effort_limit_N'] == 8.
        assert action['duration_s'] == 1 / 60
        assert action['metadata']['grasp_orientation_feedback_suppressed'] is True
        assert action['metadata']['teacher_controller_version'].endswith('.v2')
        assert action['metadata']['truth_teacher'] is True
        assert action['metadata']['physical_watchdogs_unscaled'] is True
    assert controller.phase == 'GRASP'


def test_original_parent_still_reorients_for_same_grasp_observation(fixture):
    controller, debug, _ = latched_controller(fixture, adapted=False)
    start = controller.rotation_command
    helper.act(controller, debug, .2)
    assert (controller.rotation_command * start.inv()).magnitude() == pytest.approx(np.deg2rad(.1))


@pytest.mark.parametrize('phase', ['EXTRACT', 'TRANSPORT', 'ALIGN', 'INSERT', 'GATE_RETRACT'])
@pytest.mark.parametrize('orientation', [True, False])
def test_non_grasp_feedback_is_identical_to_original_parent_including_xy(fixture, phase, orientation):
    make, debug, parent, _, _ = fixture
    new, old = make(), make(False)
    helper.enter(new, debug, phase)
    helper.enter(old, debug, phase)
    debug['object_quaternion_wxyz'] = parent.wxyz(Rotation.from_euler('x', .4, degrees=True)
        * Rotation.from_euler('z', 90., degrees=True))
    old._feedback(debug, [.01, .02], orientation=orientation)
    new._feedback(debug, [.01, .02], orientation=orientation)
    np.testing.assert_allclose(new.rotation_command.as_matrix(), old.rotation_command.as_matrix(), atol=1e-15)
    np.testing.assert_array_equal(new.target, old.target)
    np.testing.assert_array_equal(new.total_feedback_m, old.total_feedback_m)
    assert new._grasp_orientation_feedback_suppressed is False


def test_grasp_suppresses_orientation_without_suppressing_explicit_xy_feedback(fixture):
    controller, debug, _ = latched_controller(fixture)
    start_rotation = controller.rotation_command.as_matrix().copy()
    start_target = controller.target.copy()
    controller._feedback(debug, [.01, .02])
    np.testing.assert_array_equal(controller.rotation_command.as_matrix(), start_rotation)
    assert np.linalg.norm(controller.target[:2] - start_target[:2]) > 0.
    assert controller._grasp_orientation_feedback_suppressed is True


def test_grasp_to_extract_keeps_physical_hold_timer_and_clears_suppression_on_next_phase(fixture):
    controller, debug, _ = latched_controller(fixture)
    controller.cfg['control']['extract_orientation_feedback'] = False
    helper.act(controller, debug, .849)
    assert controller.phase == 'GRASP'
    transition = helper.act(controller, debug, .85)
    assert controller.phase == 'EXTRACT'
    assert controller.phase_start == .85
    assert transition['metadata']['grasp_orientation_feedback_suppressed'] is True
    assert controller.events[-1]['t'] == .85
    orientation = controller.rotation_command.as_matrix().copy()
    following = helper.act(controller, debug, .85 + 1 / 60)
    np.testing.assert_array_equal(controller.rotation_command.as_matrix(), orientation)
    assert following['metadata']['grasp_orientation_feedback_suppressed'] is False


def test_repeat_observation_and_reset_preserve_suppression_and_clock_contract(fixture):
    controller, debug, _ = latched_controller(fixture)
    first = helper.act(controller, debug, .2)
    again = helper.act(controller, debug, .2)
    assert first == again
    assert first['metadata']['grasp_orientation_feedback_suppressed'] is True
    controller.reset()
    assert controller._grasp_orientation_feedback_suppressed is False
    assert controller.phase == 'RESET' and controller._clock_cached_action is None


def test_before_latch_does_not_claim_suppression_of_a_feedback_call_that_never_occurred(fixture):
    make, debug, _, _, _ = fixture
    controller = make()
    helper.enter(controller, debug, 'GRASP')
    action = helper.act(controller, debug, .2)
    assert controller.latch_opening is None
    assert action['metadata']['grasp_orientation_feedback_suppressed'] is False
