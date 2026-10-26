"""CPU time semantics of the phase-only teacher adapter; no simulated physics."""
import copy
import importlib.util
from pathlib import Path
import sys
from types import ModuleType

import numpy as np
import pytest
from scipy.spatial.transform import Rotation

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


@pytest.fixture
def fixture(monkeypatch):
    # controllers/__init__ eagerly imports Isaac. Only these two standalone
    # controller modules are loaded; the actual production parent is retained.
    package = ModuleType('controllers');package.__path__ = [str(ROOT / 'controllers')]
    monkeypatch.setitem(sys.modules, 'controllers', package)
    parent = load('controllers.lab_cuvette_env_v1_controller', ROOT / 'controllers/lab_cuvette_env_v1_controller.py')
    monkeypatch.setitem(sys.modules, 'controllers.lab_cuvette_env_v1_controller', parent)
    module = load('teacher_clock_cpu', ROOT / 'controllers/lab_cuvette_project_v1_1_controller.py')
    cfg = dict(env=dict(task_type='loading'), physics=dict(control_hz=60, dynamic_friction=.5, finger_dynamic_friction=.8),
        teacher_execution=dict(motion_time_scale=1.5), vessel=dict(mass_kg=.02, yaw_deg=90, outer_xy_m=[.01, .01]),
        robot=dict(finger_kp=2000), gripper=dict(contact_safety_factor=2), control=dict(timeout_s=160.))
    layout = dict(source_floor=[-.085, -.175, .743], target_floor=[.21237, -.1499, .887],
        instrument_rotation=np.eye(3), target_rim_z=.914, source_rim_z=.768, opening_direction_world=[-1., 0., 0.])
    hand, cup = Rotation.from_euler('xyz', [180, 0, -90], degrees=True), Rotation.from_euler('z', 90, degrees=True)
    debug = dict(actual_tcp_position_m=[-.085, -.175, 1.022], actual_tcp_quaternion_wxyz=parent.wxyz(hand),
        object_position_m=[-.085, -.175, .743], object_quaternion_wxyz=parent.wxyz(cup), finger_contact_N=[0., 0.],
        finger_joint_positions_m=[.0067, .0065], source_bottom_z_m=.743, tilt_deg=0., xy_error_target_m=[0., 0.],
        target_bottom_gap_m=.005, target_bottom_support_N=0., wall_contact_N=0.)
    def make(adapted=True, configuration=None):
        controller = (module.LabCuvetteProjectV11Teacher if adapted else parent.LabCuvetteTeacher)(
            copy.deepcopy(cfg if configuration is None else configuration), copy.deepcopy(layout))
        return controller
    return make, debug, parent, module, cfg


def act(controller, debug, t, episode='cpu'):
    return controller.act(dict(simulation_time=t, episode_id=episode, step_index=round(t * 60)), debug)


def enter(controller, debug, phase):
    act(controller, debug, 0.)
    controller._enter(phase, 0.)
    controller.anchor = np.array(debug['actual_tcp_position_m'])
    controller.initial_tcp = controller.anchor + [0., 0., .2]
    controller.lift = controller.anchor + [0., 0., .15]
    controller.source_initial = np.array(debug['object_position_m'])
    controller.transport_start = controller.anchor.copy()
    controller.transport_end = controller.anchor + [.25, .02, 0.]
    controller.open_target = controller.anchor.copy()
    controller.contact_target = controller.anchor.copy()
    controller.contact_opening = .011


@pytest.mark.parametrize('phase', ['APPROACH_SOURCE', 'EXTRACT', 'TRANSPORT', 'RETREAT'])
def test_only_fast_motion_phases_follow_parent_at_one_over_1_5_time(fixture, phase):
    make, debug, _, _, _ = fixture
    new, old = make(), make(False)
    enter(new, debug, phase);enter(old, debug, phase)
    original_cfg = copy.deepcopy(new.cfg)
    result = act(new, debug, 3.)
    reference = act(old, debug, 2.)
    np.testing.assert_allclose(result['values'], reference['values'], atol=1e-12)
    assert result['duration_s'] == reference['duration_s'] == 1 / 60
    assert result['metadata']['motion_time_scale'] == 1.5
    assert result['metadata']['physical_phase_elapsed_s'] == 3.
    assert result['metadata']['motion_phase_elapsed_s'] == 2.
    assert new.phase_start == 0.  # Temporary remapping never leaks outside act.
    assert new.cfg == original_cfg and new.hz == 60


@pytest.mark.parametrize('phase', ['RESET', 'GRASP', 'ALIGN', 'INSERT', 'SUPPORT_TRANSFER', 'OPEN', 'VERIFY', 'TRANSPORT_HOLD'])
def test_other_phase_clocks_effort_and_per_tick_commands_are_unscaled(fixture, phase):
    make, debug, _, _, _ = fixture
    new, old = make(), make(False)
    enter(new, debug, phase);enter(old, debug, phase)
    if phase in ('SUPPORT_TRANSFER', 'OPEN'):
        new.latch_opening = old.latch_opening = .010
    result, reference = act(new, debug, 2.), act(old, debug, 2.)
    np.testing.assert_allclose(result['values'], reference['values'], atol=1e-12)
    assert result['gripper_opening_m'] == reference['gripper_opening_m']
    assert result['gripper_effort_limit_N'] == reference['gripper_effort_limit_N']
    assert result['metadata']['motion_time_scale'] == 1
    assert result['metadata']['motion_phase_elapsed_s'] == 2.
    assert new._last_time == 2. and new.history[-1]['t'] == 2.


def test_reset_to_approach_to_grasp_preserves_physical_event_times_and_continuous_clock(fixture):
    make, debug, _, _, _ = fixture
    controller = make();observed = copy.deepcopy(debug)
    for tick in range(871):  # Through physical14.5s = RESET4 + APPROACH7*1.5.
        result = act(controller, observed, tick / 60)
        observed['actual_tcp_position_m'] = result['values'][:3]
    transitions = [event for event in controller.events if event['event'] == 'teacher_phase_transition']
    assert [(e['source'], e['target']) for e in transitions] == [('RESET', 'APPROACH_SOURCE'), ('APPROACH_SOURCE', 'GRASP')]
    assert transitions[0]['t'] == pytest.approx(4.)
    assert transitions[0]['controller_time_s'] == pytest.approx(4.)
    assert transitions[1]['t'] == pytest.approx(14.5)
    assert transitions[1]['controller_time_s'] == pytest.approx(11.)
    assert controller.phase_start == pytest.approx(14.5)
    assert controller.phase == 'GRASP'
    action = act(controller, observed, 14.5 + 1 / 60)
    assert action['metadata']['motion_phase_elapsed_s'] == pytest.approx(1 / 60)
    assert action['metadata']['physical_watchdogs_unscaled'] is True
    assert action['metadata']['truth_teacher'] is True


def test_contact_loss_watchdog_stays_point_three_physical_seconds_inside_slow_phase(fixture):
    make, debug, _, _, _ = fixture
    controller = make();enter(controller, debug, 'EXTRACT')
    controller.latch_opening = .01
    controller.grasp_reference = controller._relative(debug)
    act(controller, debug, .01)
    act(controller, debug, .32)
    assert controller.finished and controller.status == 'BILATERAL_CONTACT_LOST'
    event = next(e for e in controller.events if e.get('status') == 'BILATERAL_CONTACT_LOST')
    assert event['t'] == .32
    assert event['controller_time_s'] == pytest.approx(.32 / 1.5)


def test_global_timeout_remains_physical_in_a_slow_phase(fixture):
    make, debug, _, _, _ = fixture
    controller = make();enter(controller, debug, 'TRANSPORT')
    controller.cfg['control']['timeout_s'] = 1.
    act(controller, debug, 1.1)
    assert controller.finished and controller.status == 'TIMEOUT'
    assert controller.events[-1]['t'] == 1.1


def test_verify_keeps_physical_three_second_stability_window(fixture):
    make, debug, _, _, _ = fixture
    controller = make();enter(controller, debug, 'VERIFY')
    observed = dict(debug, target_bottom_support_N=.1962, target_bottom_gap_m=0.)
    for tick in range(1, 186):
        act(controller, observed, tick / 60)
    assert not controller.finished
    act(controller, observed, 3.1)
    assert controller.finished and controller.status == 'CONTROLLER_WORKFLOW_COMPLETE'
    assert controller.events[-1]['t'] == 3.1
    assert controller.events[-1]['controller_time_s'] == pytest.approx(3.1)


def test_insert_per_control_tick_speed_is_not_rescaled(fixture):
    make, debug, _, _, _ = fixture
    controller = make();enter(controller, debug, 'INSERT')
    previous_z = controller.target[2]
    for tick in range(1, 11):
        action = act(controller, debug, tick / 60)
        assert previous_z - action['values'][2] == pytest.approx(.001 / 60)
        assert action['duration_s'] == 1 / 60
        previous_z = action['values'][2]


def test_repeated_time_does_not_advance_clock_or_apply_feedback_closure_twice(fixture):
    make, debug, _, _, _ = fixture
    controller = make();enter(controller, debug, 'GRASP')
    first = act(controller, debug, 1.)
    count, clock, opening = len(controller.history), controller.controller_motion_clock_s, controller.last_grip_opening
    second = act(controller, debug, 1.)
    assert first == second and len(controller.history) == count
    assert controller.controller_motion_clock_s == clock and controller.last_grip_opening == opening
    with pytest.raises(ValueError, match='backwards'):
        act(controller, debug, .9)
    with pytest.raises(ValueError, match='backwards'):
        act(controller, debug, 1. - 1e-10)
    with pytest.raises(ValueError, match='changing episode'):
        act(controller, debug, 1.1, episode='another')
    controller.reset()
    assert controller.controller_motion_clock_s == 0 and controller._clock_last_actual is None
    assert controller.events == [] and controller.phase == 'RESET'
    result = act(controller, debug, .0166666667, episode='another')
    assert result['metadata']['controller_time_s'] == 0


def test_scale_one_preserves_original_teacher_actions_on_distinct_observations(fixture):
    make, debug, _, _, cfg = fixture
    cfg = copy.deepcopy(cfg);cfg['teacher_execution']['motion_time_scale'] = 1.
    new, old = make(configuration=cfg), make(False, configuration=cfg)
    for phase in ('APPROACH_SOURCE', 'EXTRACT', 'TRANSPORT', 'RETREAT', 'INSERT'):
        new.reset();old.reset();enter(new, debug, phase);enter(old, debug, phase)
        for time in (.1, .2, .3):
            actual, expected = act(new, debug, time), act(old, debug, time)
            for key in ('values', 'gripper_opening_m', 'gripper_effort_limit_N', 'duration_s', 'episode_id', 'observation_step'):
                np.testing.assert_allclose(actual[key], expected[key], atol=1e-12) if key not in ('episode_id',) else None
            assert actual['metadata']['teacher_phase'] == expected['metadata']['teacher_phase']


@pytest.mark.parametrize('scale', [0, .9, float('nan'), float('inf')])
def test_invalid_or_faster_scale_rejected_without_editing_parent(fixture, scale):
    make, _, _, _, cfg = fixture
    cfg = copy.deepcopy(cfg);cfg['teacher_execution']['motion_time_scale'] = scale
    with pytest.raises(ValueError):
        make(configuration=cfg)
