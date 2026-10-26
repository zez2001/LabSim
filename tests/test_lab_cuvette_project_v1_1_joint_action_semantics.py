"""Real facade/task/collector methods with explicitly nonphysical CPU stubs.

The FK exposes one redundant coordinate so that matching TCP position cannot
silently stand in for preserving an absolute joint-space policy command.
"""
import ast
import copy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from scipy.spatial.transform import Rotation

from demos.lab_cuvette_project_v1_1.environment import ProjectEnvironment
from policy.backends.action_adapters import act_dp_joint_action

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('joint_action_cpu_helpers',
    ROOT / 'tests/test_lab_cuvette_project_v1_1_tracking_integration.py')
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)
task_factory = helper.task_factory


@pytest.fixture
def public_task_factory(task_factory, monkeypatch):
    def ideal_drive(task, action):
        q, opening, effort, _, conversion = task._convert_action(action)
        task.low_actions.append(copy.deepcopy(action))
        task.conversions.append(copy.deepcopy(conversion))
        task.qcmd, task.actual_q = q.copy(), q.copy()
        task.grip, task.effort = opening, effort
        task.applied_count += 1
        task.control_steps += 1
        task.steps += 4
        task.t += 1 / 60
        p, matrix = task.forward(q[:7])
        if task.imposed_actual_position is not None:
            p = np.asarray(task.imposed_actual_position)
            task.actual_q[:3] = p
        task.debug['actual_tcp_position_m'] = p.tolist()
        task.debug['actual_tcp_quaternion_wxyz'] = np.roll(Rotation.from_matrix(matrix).as_quat(), 1).tolist()
        return {}, 0., False, False, {}
    monkeypatch.setattr(helper.CPUParent, 'step', ideal_drive)

    def make_task(enabled=True):
        task = task_factory(enabled=enabled)
        task.low_actions, task.conversions = [], []
        task._result = None
        task.imposed_actual_position = None
        task.get_observation = lambda: dict(episode_id=task.episode_id,
            observation_id=f'{task.episode_id}:{task.control_steps}',
            TCPpose=dict(position_m=list(task.debug['actual_tcp_position_m']),
                quaternion_wxyz=list(task.debug['actual_tcp_quaternion_wxyz'])),
            joint_positions=task.actual_q.copy(), gripper_opening_m=task.grip, images={})
        return task
    return make_task


def joint_request(task, *, kind='joint_position', duration=1 / 60):
    q = np.array([.0001, 0., 0., 0., 0., 0., .001])
    action = act_dp_joint_action(np.r_[q, .005], task.get_observation(),
        action_id='cpu_joint', duration_s=duration, gripper_effort_limit_N=6.)
    action['type'] = kind
    if kind == 'joint_velocity':
        action['values'] = (q / duration).tolist()
    return action, q


@pytest.mark.parametrize('kind', ['joint_position', 'joint_velocity'])
@pytest.mark.parametrize('ticks', [1, 4])
@pytest.mark.parametrize('enabled', [True, False])
def test_public_joint_plan_preserves_all_seven_targets_and_skips_cartesian_feedback(
        public_task_factory, kind, ticks, enabled):
    task = public_task_factory(enabled)
    request, target = joint_request(task, kind=kind, duration=ticks / 60)
    result = ProjectEnvironment(task).execute(request)
    assert result['accepted'] and result['target_reached']
    assert result['executed_control_ticks'] == ticks
    np.testing.assert_array_equal(task.qcmd[:7], target)
    assert task.qcmd[6] == .001  # Explicit redundant-coordinate preservation.
    assert task.solution_requests == []  # A joint policy must not become IK.
    if enabled:
        assert task.tracking_compensator._samples == 0
    for i, (low, conversion) in enumerate(zip(task.low_actions, task.conversions)):
        expected = target * (i + 1) / ticks
        np.testing.assert_allclose(conversion['executed_q'][:7], expected, atol=1e-18)
        assert low['type'] == conversion['input_type'] == 'ee_pose'
        assert low['raw_model_action'] == request
        assert conversion['origin_type'] == kind
        assert conversion['compensation_applied'] is False
        assert conversion['joint_target_preserved'] is True
        assert conversion['robot_tracking'] is None
        assert conversion['target_pose'] is not None
        assert conversion['IK']['reason'] == 'PREFLIGHT_REVERIFIED'
        assert conversion['effort_limit_N'] == 6.
        assert conversion['generic_contact_hold'] == {}
    trace = json.loads((task.episode_dir / 'execution_trace.jsonl').read_text().splitlines()[-1])
    assert trace['reference_TCP']['position_m'] == pytest.approx(target[:3])
    assert trace['origin_type'] == kind and trace['joint_target_preserved'] is True
    assert trace['compensation_applied'] is False and trace['runtime_stop'] is None


@pytest.mark.parametrize('kind', ['ee_delta', 'ee_pose'])
def test_public_ee_still_uses_robot_feedback_and_nominal_reference(public_task_factory, kind):
    task = public_task_factory()
    request, _ = joint_request(task)
    request['type'] = kind
    request['frame'] = 'world'
    request['values'] = [.0001, 0., 0., 0., 0., 0.] if kind == 'ee_delta' else [.0001, 0., 0., 1., 0., 0., 0.]
    result = ProjectEnvironment(task).execute(request)
    assert result['target_reached'] is True
    assert task.qcmd[0] == pytest.approx(.0005)
    conversion = task.conversions[0]
    assert conversion['origin_type'] == kind
    assert conversion['compensation_applied'] is True
    assert conversion['joint_target_preserved'] is False
    assert conversion['robot_tracking']['sample_count'] == 1
    assert conversion['target_pose']['position_m'][0] == .0001
    assert conversion['effective_IK_goal_TCP']['position_m'][0] == pytest.approx(.0005)


def test_public_joint_preserves_existing_generic_contact_hold_and_effort(public_task_factory):
    task = public_task_factory()
    calls = []
    def held_gripper(**values):
        calls.append(values)
        return .009, {'cpu_contact_latched': True}
    task.contact_hold.update = held_gripper
    request, target = joint_request(task)
    ProjectEnvironment(task).execute(request)
    assert len(calls) == 1
    assert calls[0]['logical_requested_opening_m'] == .01
    np.testing.assert_array_equal(task.qcmd[:7], target)
    np.testing.assert_allclose(task.qcmd[7:], [.0045, .0045])
    assert task.effort == 6.
    assert task.conversions[0]['generic_contact_hold']['cpu_contact_latched'] is True


def test_public_joint9_keeps_symmetric_finger_mapping(public_task_factory):
    task = public_task_factory()
    request, target = joint_request(task)
    request['values'] = np.r_[target, .005, .005].tolist()
    result = ProjectEnvironment(task).execute(request)
    assert result['accepted'] is True
    np.testing.assert_array_equal(task.qcmd, np.r_[target, .005, .005])
    assert task.low_actions[0]['raw_model_action']['values'] == request['values']


def test_preserved_joint_fk_mismatch_stops_before_any_physical_step(public_task_factory):
    task = public_task_factory()
    low = dict(episode_id=task.episode_id, observation_step=task.control_steps,
        type='ee_pose', values=[.0001, 0., 0., 1., 0., 0., 0.], duration_s=1 / 60,
        raw_model_action={'type': 'joint_position'}, _executor_q7=[.002, 0., 0., 0., 0., 0., .001])
    with pytest.raises(RuntimeError, match='CONTROL_OR_IK_FAILURE'):
        task.step(low)
    assert task.applied_count == task.control_steps == 0
    assert task.tracking_compensator._samples == 0


@pytest.mark.parametrize('actual,expected_stop', [(.0001, None), (.0052, 'EXECUTOR_TRACKING_ERROR')])
def test_public_joint_nominal_fk_reference_still_drives_actual_tracking_guard(
        public_task_factory, actual, expected_stop):
    task = public_task_factory()
    # Hold actual position fixed to isolate nominal tracking from speed checks.
    task.actual_q[0] = actual
    task.debug['actual_tcp_position_m'][0] = actual
    task.imposed_actual_position = [actual, 0., 0.]
    request, _ = joint_request(task)
    result = ProjectEnvironment(task).execute(request)
    trace = json.loads((task.episode_dir / 'execution_trace.jsonl').read_text())
    assert trace['reference_TCP']['position_m'][0] == pytest.approx(.0001)
    assert trace['runtime_stop'] == expected_stop
    assert trace['position_tracking_error_m'] == pytest.approx(abs(actual - .0001))
    assert task.hold_count == bool(expected_stop)
    assert result['safety_stopped'] == bool(expected_stop)


def test_public_joint_still_enforces_actual_tcp_speed_guard(public_task_factory):
    task = public_task_factory()
    request, _ = joint_request(task)
    request['values'][0] = .001  # Ideal CPU drive moves 1 mm in one 60 Hz tick.
    result = ProjectEnvironment(task).execute(request)
    trace = json.loads((task.episode_dir / 'execution_trace.jsonl').read_text())
    assert trace['reference_TCP'] is not None
    assert trace['runtime_stop'] == 'EXECUTOR_ACTUAL_SPEED_LIMIT'
    assert trace['position_tracking_error_m'] == pytest.approx(0.)
    assert trace['actual_TCP_speed_m_s'] == pytest.approx(.06)
    assert result['safety_stopped'] is True


def test_actual_collector_method_keeps_raw_public_action_and_applied_joint9_distinct(public_task_factory):
    task = public_task_factory()
    request, target = joint_request(task)
    ProjectEnvironment(task).execute(request)
    source = ROOT / 'data_collectors/lab_cuvette_env_v1_collector.py'
    tree = ast.parse(source.read_text())
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef))
    method = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == 'cache_transition')
    namespace = dict(np=np, json_text=lambda v: json.dumps(helper.json_safe(v), allow_nan=False))
    exec(compile(ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[])), str(source), 'exec'), namespace)
    cameras = ('side_camera_rgb', 'wrist_camera_rgb')
    fields = {}
    recorder = SimpleNamespace(file={k: object() for k in ('camera_1_rgb', 'camera_2_rgb')},
        episode_id=task.episode_id, cfg=task.cfg, CAMERAS=cameras, _integrity_errors=[],
        _last_time=None, _camera_black_counts={k: 0 for k in cameras}, _phases=[], count=0,
        _append=lambda k, v: fields.__setitem__(k, v), _append_text=lambda k, v: fields.__setitem__(k, v), save_video=False)
    before = dict(episode_id=task.episode_id, joint_positions=np.zeros(9), simulation_time=0.,
        step_index=0, camera_data={k: np.ones((3, 2, 2), np.uint8) for k in cameras}, phase='CPU')
    after = dict(before, joint_positions=task.actual_q.copy(), simulation_time=1 / 60, step_index=1)
    command = dict(episode_id=task.episode_id, command_q=task.qcmd.copy(), raw_output=request,
        conversion=task.conversions[0], gripper_effort_limit_N=task.effort, gripper_target_m=task.grip / 2)
    namespace['cache_transition'](recorder, before, command, after, {})
    assert recorder._integrity_errors == []
    assert json.loads(fields['actions_raw_json']) == request
    assert json.loads(fields['action_conversion_json'])['origin_type'] == 'joint_position'
    np.testing.assert_array_equal(fields['control_auxiliary/command_q'], task.qcmd)
    np.testing.assert_allclose(fields['actions'][:7], target, rtol=1e-7)
    assert fields['actions'].shape == (8,) and fields['control_auxiliary/command_q'].shape == (9,)
    assert fields['control_auxiliary/gripper_effort_limit_N'].tolist() == [6., 6.]
    assert fields['control_auxiliary/available']
