"""Configured open-hand prealignment on CPU; no Isaac/contact simulation."""
import copy
import importlib.util
from pathlib import Path

import numpy as np
import pytest
from scipy.spatial.transform import Rotation

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('teacher_prealign_cpu_helpers',
    ROOT / 'tests/test_lab_cuvette_project_v1_1_teacher_clock.py')
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)
fixture = helper.fixture


def setup_approach(fixture, *, configuration=None):
    make, debug, parent, _, cfg = fixture
    cfg = copy.deepcopy(cfg if configuration is None else configuration)
    cfg['robot'].setdefault('gripper_yaw_deg', -90.)
    cfg['control'].setdefault('approach_s', 6.)
    ideal = Rotation.from_euler('xyz', [180., 0., cfg['robot']['gripper_yaw_deg']], degrees=True)
    start = Rotation.from_rotvec(np.deg2rad([.045, -.025, .015])) * ideal
    debug = copy.deepcopy(debug)
    debug['actual_tcp_quaternion_wxyz'] = parent.wxyz(start)
    controller = make(configuration=cfg)
    helper.enter(controller, debug, 'APPROACH_SOURCE')
    return controller, debug, start, ideal


def action_rotation(action):
    return Rotation.from_quat(np.roll(action['values'][3:7], -1))


def test_matches_configured_Rz_yaw_Rx_pi_and_preserves_reset_observed_start(fixture):
    controller, debug, start, ideal = setup_approach(fixture)
    np.testing.assert_allclose(controller.approach_orientation_goal.as_matrix(),
        (Rotation.from_euler('z', -90., degrees=True) * Rotation.from_euler('x', 180., degrees=True)).as_matrix(), atol=1e-15)
    np.testing.assert_allclose(controller._approach_orientation_start.as_matrix(), start.as_matrix(), atol=1e-15)
    # A later robot observation must not move the interpolation's reset anchor.
    debug['actual_tcp_quaternion_wxyz'] = [1., 0., 0., 0.]
    action = helper.act(controller, debug, 4.5)
    expected = Rotation.from_rotvec(.5 * (ideal * start.inv()).as_rotvec()) * start
    np.testing.assert_allclose(action_rotation(action).as_matrix(), expected.as_matrix(), atol=1e-15)
    metadata = action['metadata']
    assert metadata['approach_orientation_active'] is True
    assert metadata['approach_orientation_motion_progress'] == pytest.approx(.5)
    assert metadata['approach_orientation_smooth_fraction'] == pytest.approx(.5)
    assert metadata['approach_orientation_motion_duration_s'] == 6.
    assert metadata['approach_orientation_uses_object_truth'] is False
    assert 'robot.gripper_yaw_deg' in metadata['approach_orientation_source']


@pytest.mark.parametrize('physical_time,progress', [(1.5, 1/6), (4.5, .5), (9., 1.)])
def test_uses_existing_slowed_motion_clock_and_smooth_shortest_arc(fixture, physical_time, progress):
    controller, debug, start, ideal = setup_approach(fixture)
    configuration = copy.deepcopy(controller.cfg)
    action = helper.act(controller, debug, physical_time)
    fraction = progress**2 * (3 - 2*progress)
    expected_angle = (ideal * start.inv()).magnitude() * fraction
    assert (action_rotation(action) * start.inv()).magnitude() == pytest.approx(expected_angle, abs=1e-14)
    assert action['metadata']['motion_phase_elapsed_s'] == pytest.approx(physical_time / 1.5)
    assert action['duration_s'] == 1/60 and action['gripper_opening_m'] == .08
    assert action['gripper_effort_limit_N'] == 8.
    assert controller.cfg == configuration


def test_small_residual_is_continuous_and_goal_is_held_through_grasp_boundary(fixture):
    controller, debug, start, ideal = setup_approach(fixture)
    total = (ideal * start.inv()).magnitude()
    maximum_step = 1.5 * total / (6 * 1.5 * 60)
    previous = start
    times = []
    for tick in range(1, 633):
        time = tick/60
        action = helper.act(controller, debug, time)
        current = action_rotation(action)
        assert (current * previous.inv()).magnitude() <= maximum_step + 1e-13
        if time >= 9.:
            np.testing.assert_allclose(current.as_matrix(), ideal.as_matrix(), atol=1e-15)
        debug['actual_tcp_position_m'] = action['values'][:3]
        debug['actual_tcp_quaternion_wxyz'] = action['values'][3:7]
        if action['metadata']['motion_source_phase'] == 'GRASP':
            assert action['metadata']['approach_orientation_active'] is False
            times.append(time)
        previous = current
    assert controller.phase == 'GRASP' and times
    transition = next(e for e in controller.events if e.get('target') == 'GRASP')
    assert transition['t'] == pytest.approx(10.5)
    assert transition['motion_time_scale'] == 1.5


def test_prealignment_ignores_vessel_truth_pose_and_does_not_change_translation(fixture):
    first, debug, _, _ = setup_approach(fixture)
    second, other, _, _ = setup_approach(fixture)
    other['object_quaternion_wxyz'] = [1., 0., 0., 0.]
    other['object_position_m'] = [.7, -.3, 1.2]
    a, b = helper.act(first, debug, 4.5), helper.act(second, other, 4.5)
    np.testing.assert_array_equal(a['values'], b['values'])
    assert a['gripper_opening_m'] == b['gripper_opening_m']
    assert a['gripper_effort_limit_N'] == b['gripper_effort_limit_N']


@pytest.mark.parametrize('phase', ['RESET', 'GRASP', 'EXTRACT', 'TRANSPORT_HOLD', 'SUPPORT_TRANSFER', 'OPEN', 'VERIFY'])
def test_no_new_orientation_schedule_runs_outside_approach(fixture, phase):
    controller, debug, start, _ = setup_approach(fixture)
    controller._enter(phase, 0.)
    if phase in ('SUPPORT_TRANSFER', 'OPEN'):
        controller.latch_opening = .01
    controller.cfg['control']['extract_orientation_feedback'] = False
    action = helper.act(controller, debug, .1)
    if phase != 'SUPPORT_TRANSFER':
        np.testing.assert_allclose(action_rotation(action).as_matrix(), start.as_matrix(), atol=1e-15)
    else:
        # v7 adds the parent's separate support-alignment feedback, not the
        # configured open-hand approach interpolation. Its bound is tested in
        # the support-transfer contract.
        assert action['metadata']['support_transfer_control_active'] is True
    assert action['metadata']['approach_orientation_active'] is False


@pytest.mark.parametrize('opening,forces', [(.01, [0., 0.]), (.08, [.04, 0.]), (.08, [0., .04])])
def test_requires_open_command_and_no_existing_contact_threshold_crossing(fixture, opening, forces):
    controller, debug, start, _ = setup_approach(fixture)
    controller.last_grip_opening = opening
    debug['finger_contact_N'] = forces
    action = helper.act(controller, debug, .1)
    np.testing.assert_allclose(action_rotation(action).as_matrix(), start.as_matrix(), atol=1e-15)
    assert action['metadata']['approach_orientation_active'] is False


def test_repeat_observation_and_reset_neither_accumulate_nor_reuse_old_anchor(fixture):
    controller, debug, start, _ = setup_approach(fixture)
    first = helper.act(controller, debug, 4.5)
    again = helper.act(controller, debug, 4.5)
    assert again == first
    np.testing.assert_allclose(controller._approach_orientation_start.as_matrix(), start.as_matrix(), atol=1e-15)
    controller.reset()
    assert controller._approach_orientation_start is None
    assert controller._approach_orientation_progress == 0.
    assert controller._approach_orientation_fraction == 0.
    new_start = Rotation.from_euler('xyz', [179.97, .01, -90.02], degrees=True)
    debug['actual_tcp_quaternion_wxyz'] = np.roll(new_start.as_quat(), 1).tolist()
    helper.act(controller, debug, 0., episode='another')
    np.testing.assert_allclose(controller._approach_orientation_start.as_matrix(), new_start.as_matrix(), atol=1e-15)


def test_static_yaw_and_existing_approach_duration_are_configurable(fixture):
    _, _, _, _, cfg = fixture
    cfg = copy.deepcopy(cfg);cfg['robot']['gripper_yaw_deg'] = -80.;cfg['control']['approach_s'] = 2.
    controller, debug, _, ideal = setup_approach(fixture, configuration=cfg)
    action = helper.act(controller, debug, 3.)
    np.testing.assert_allclose(action_rotation(action).as_matrix(), ideal.as_matrix(), atol=1e-15)
    assert action['metadata']['approach_orientation_motion_progress'] == 1.


def test_an_already_ideal_reset_orientation_is_unchanged(fixture):
    make, debug, parent, _, _ = fixture
    controller = make()
    ideal = Rotation.from_euler('xyz', [180., 0., -90.], degrees=True)
    debug['actual_tcp_quaternion_wxyz'] = parent.wxyz(ideal)
    helper.enter(controller, debug, 'APPROACH_SOURCE')
    for time in (.1, 4.5, 9.):
        action = helper.act(controller, debug, time)
        np.testing.assert_allclose(action_rotation(action).as_matrix(), ideal.as_matrix(), atol=1e-15)


@pytest.mark.parametrize('field,value', [('gripper_yaw_deg', float('nan')), ('gripper_yaw_deg', None),
    ('approach_s', 0.), ('approach_s', float('inf'))])
def test_invalid_alignment_configuration_is_rejected(fixture, field, value):
    make, _, _, _, cfg = fixture
    cfg = copy.deepcopy(cfg);cfg['robot' if field == 'gripper_yaw_deg' else 'control'][field] = value
    with pytest.raises(ValueError, match='Approach yaw'):
        make(configuration=cfg)
