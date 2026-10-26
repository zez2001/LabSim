"""Execute the actual task methods against CPU robot/FK stubs.

The class AST is used to replace only its Isaac-dependent parent/import chain.
Task method bodies remain the production source; numerical FK/drive stubs do
not represent physical validation. No H5, simulator, GPU or provider is needed.
"""
import ast
import copy
import json
from pathlib import Path
import sys
import time
from types import ModuleType, SimpleNamespace

import numpy as np
from omegaconf import OmegaConf
import pytest
from scipy.spatial.transform import Rotation

from demos.lab_cuvette_project_v1_1.robot_tracking import RobotTrackingCompensator

ROOT = Path(__file__).resolve().parents[1]


class MemoryPath:
    """An in-memory path prevents the real task's trace/reset writes reaching disk."""
    def __init__(self, name='', files=None):
        self.name, self.files = name, {} if files is None else files

    def __truediv__(self, name):
        return MemoryPath(self.name + '/' + name, self.files)

    def read_text(self):
        return self.files[self.name]

    def write_text(self, value):
        self.files[self.name] = value

    def open(self, *args):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def write(self, value):
        self.files[self.name] = self.files.get(self.name, '') + value


def json_safe(value):
    if isinstance(value, np.ndarray):
        return json_safe(value.tolist())
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, np.generic):
        return value.item()
    return value


class CPUParent:
    @staticmethod
    def _write(path, value):
        path.write_text(json.dumps(json_safe(value)))

    def _reset(self, seed=None, options=None):
        self.reset_count += 1
        self.episode_id = 'CPU_RESET_' + str(self.reset_count)
        self.episode_dir = self.memory_root / self.episode_id
        (self.episode_dir / 'release_metadata.json').write_text('{}')
        self.control_steps, self.steps, self.t = 0, 4, 1 / 60
        self.qcmd = np.array([.0004, 0, 0, 0, 0, 0, 0, .005, .005])
        self.debug['actual_tcp_position_m'] = [0., 0., 0.]
        self.debug['actual_tcp_quaternion_wxyz'] = [1., 0., 0., 0.]
        self.actual_q = np.zeros(9)
        return dict(cpu_stub=True), dict(cpu_stub=True)

    def step(self, action):
        # A failed conversion must happen before this fictional physical step.
        q, opening, effort, _, conversion = self._convert_action(action)
        self.qcmd = q.copy()
        self.grip, self.effort = opening, effort
        self.applied_count += 1
        self.t += 1 / 60
        self.steps += 4
        self.control_steps += 1
        self.actual_q[:3] = self.after_position
        self.debug['actual_tcp_position_m'] = self.after_position.tolist()
        return ({}, 0., False, False, {})


def module(**values):
    result = ModuleType('tracking_cpu_stub')
    result.__dict__.update(values)
    return result


@pytest.fixture
def task_factory(monkeypatch):
    source = ROOT / 'tasks/lab_cuvette_loading_project_v1_1.py'
    tree = ast.parse(source.read_text())
    node = next(item for item in tree.body if isinstance(item, ast.ClassDef))
    node.bases = [ast.Name(id='CPUParent', ctx=ast.Load())]
    namespace = dict(CPUParent=CPUParent, np=np, Rotation=Rotation, copy=copy, time=time, json=json)
    exec(compile(ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[])), str(source), 'exec'), namespace)
    task_class = namespace['LabCuvetteProjectV11']
    monkeypatch.setitem(sys.modules, 'demos.lab_cuvette_project_v1_1.contract',
        module(scene_contract=lambda *args: dict(frozen_scene_sha256='a' * 64)))
    monkeypatch.setitem(sys.modules, 'data_collectors.lab_cuvette_env_v1_collector', module(json_safe=json_safe))

    def make_task(enabled=True, seed_x=.0004, alpha=1):
        task = task_class()
        task.cfg = OmegaConf.create(dict(physics=dict(control_hz=60, hz=240, dynamic_friction=.5,
            finger_dynamic_friction=.8), vessel=dict(mass_kg=.02),
            executor=dict(maximum_position_tracking_error_m=.005, maximum_orientation_tracking_error_deg=2.,
                maximum_actual_TCP_speed_m_s=.05, maximum_actual_joint_speed_factor=1.25,
                ik_position_tolerance_m=2e-6, ik_orientation_tolerance_rad=2e-5),
            gripper=dict(contact_safety_factor=2., maximum_compression_m=.0003,
                contact_threshold_N=.03, contact_persist_s=.1, contact_approach_speed_m_s=.002,
                minimum_latched_finger_m=.001),
            robot_tracking=dict(enabled=enabled, time_constant_s=.1, max_position_bias_m=.001,
                max_rotation_bias_rad=.002, version='Project_v1_1.robot_tracking.v1')))
        task.base_cfg = task.cfg
        task.geometry_audit = {}
        task.memory_root = MemoryPath()
        task.episode_dir = task.memory_root / 'initial'
        task.collector = SimpleNamespace(file=SimpleNamespace(attrs={}))
        task.ctx = dict(old=SimpleNamespace(robot=SimpleNamespace(finger_kp=2000)))
        task.reset_count = 0
        task.episode_id = 'CPU_INITIAL'
        task.control_steps, task.steps, task.t = 0, 4, 1 / 60
        task.qcmd = np.array([seed_x, 0, 0, 0, 0, 0, 0, .005, .005])
        task.grip, task.effort = .01, 5.
        task.debug = dict(actual_tcp_position_m=[0., 0., 0.], actual_tcp_quaternion_wxyz=[1., 0., 0., 0.],
            finger_joint_positions_m=[.005, .005], finger_contact_N=[0., 0.])
        task.tracking_compensator = RobotTrackingCompensator(alpha=alpha) if enabled else None
        task._tracking_sample_control_step = -1
        task.forward = lambda q: (np.asarray(q[:3]).copy(), Rotation.from_rotvec(q[3:6]).as_matrix())
        task.solution_requests = []
        def solution(p, r, seed):
            task.solution_requests.append(dict(position=np.asarray(p).copy(), rotation=r.as_matrix(), seed=np.asarray(seed).copy()))
            return dict(success=True, q=np.r_[p, r.as_rotvec(), 0.], position_error_m=0.,
                orientation_error_rad=0., reason='CPU_STUB')
        task.local_solution = solution
        task.joint_bounds = lambda: (-np.ones(7) * 10, np.ones(7) * 10, np.ones(7) * 100)
        task.contact_hold = SimpleNamespace(update=lambda **kw: (kw['ramped_opening_m'], {}))
        task._tick_trace = None
        task.actual_q = np.zeros(9)
        task.after_position = np.zeros(3)
        task.ended, task.applied_count, task.hold_count = False, 0, 0
        task.robot = SimpleNamespace(get_joint_positions=lambda: task.actual_q.copy(),
            get_joint_velocities=lambda: np.zeros(9))
        task.hold_actual_joints = lambda: setattr(task, 'hold_count', task.hold_count + 1)
        def finalize(reason, failure_type):
            task.ended = True
            task._result = dict(termination_reason=reason, failure_type=failure_type)
        task.finalize_episode = finalize
        task.get_observation = lambda: {}
        task._public_info = lambda: {}
        return task
    return make_task


def action(task, **updates):
    result = dict(episode_id=task.episode_id, observation_step=task.control_steps, type='ee_pose',
        values=[.01, 0, 0, 1, 0, 0, 0], duration_s=1 / 60, _executor_q7=[9.] * 7)
    result.update(updates)
    return result


def test_effective_ik_goal_changes_but_nominal_trace_is_preserved_and_frozen_q7_is_ignored(task_factory):
    task = task_factory()
    q, _, _, _, conversion = task._convert_action(action(task))
    assert q[0] == pytest.approx(.0104)
    assert conversion['target_pose']['position_m'] == [.01, 0., 0.]
    assert conversion['effective_IK_goal_TCP']['position_m'] == pytest.approx([.0104, 0., 0.])
    assert conversion['robot_tracking']['raw_position_error_m'] == pytest.approx([.0004, 0., 0.])
    assert len(task.solution_requests) == 1
    np.testing.assert_array_equal(task.solution_requests[0]['seed'], task.qcmd[:7])
    assert task._tick_trace['reference_TCP']['position_m'] == [.01, 0., 0.]
    assert conversion['truth_used_by_environment'] is False


def test_one_sample_per_control_boundary_then_new_applied_command_actual_pair_is_used(task_factory):
    task = task_factory()
    first_q, *_, first = task._convert_action(action(task))
    second = task._convert_action(action(task, values=[.02, 0, 0, 1, 0, 0, 0]))[-1]
    assert first['robot_tracking']['sample_count'] == second['robot_tracking']['sample_count'] == 1
    assert second['robot_tracking']['estimate_held'] is True
    assert second['effective_IK_goal_TCP']['position_m'][0] == pytest.approx(.0204)
    task.qcmd = first_q.copy()  # Fictional apply; a new sampled physical boundary follows.
    task.control_steps += 1
    task.t += 1 / 60
    task.debug['actual_tcp_position_m'] = (first_q[:3] - [.0002, 0, 0]).tolist()
    third = task._convert_action(action(task))[-1]
    assert third['robot_tracking']['sample_count'] == 2
    assert third['robot_tracking']['raw_position_error_m'] == pytest.approx([.0002, 0, 0])


def test_planning_reads_frozen_estimate_without_consuming_observation_or_advancing_state(task_factory):
    task = task_factory()
    task._convert_action(action(task))
    before_count = task.tracking_compensator._samples
    before_boundary = task._tracking_sample_control_step
    before_clock = (task.t, task.steps, task.control_steps)
    plan = task.plan_cartesian([(np.array([p, 0., 0.]), Rotation.identity()) for p in (.02, .03, .04)])
    assert plan['success'] is True
    assert [q[0] for q in plan['q7']] == pytest.approx([.0204, .0304, .0404])
    assert task.tracking_compensator._samples == before_count
    assert task._tracking_sample_control_step == before_boundary
    assert (task.t, task.steps, task.control_steps) == before_clock


@pytest.mark.parametrize('bias,actual,expected_stop', [(.001, .0151, 'EXECUTOR_TRACKING_ERROR'),
    (-.001, .0149, None)])
def test_runtime_guard_uses_unchanged_nominal_for_both_false_negative_and_false_positive_cases(
        task_factory, bias, actual, expected_stop):
    task = task_factory(seed_x=actual + bias)
    task.debug['actual_tcp_position_m'] = [actual, 0., 0.]
    task.actual_q[0] = actual
    task.after_position = np.array([actual, 0., 0.])  # Isolate tracking from actual-speed guard.
    task.step(action(task))
    trace = json.loads((task.episode_dir / 'execution_trace.jsonl').read_text())
    assert trace['runtime_stop'] == expected_stop
    assert trace['position_tracking_error_m'] == pytest.approx(abs(actual - .01))
    assert trace['effective_IK_goal_TCP']['position_m'][0] == pytest.approx(.01 + bias)
    assert task.hold_count == (1 if expected_stop else 0)


def test_reset_creates_fresh_observer_and_records_explicit_configuration(task_factory):
    task = task_factory()
    task._convert_action(action(task))
    previous = task.tracking_compensator
    task._reset()
    assert task.tracking_compensator is not previous
    assert task.tracking_compensator._samples == 0
    assert task._tracking_sample_control_step == -1
    metadata = json.loads((task.episode_dir / 'release_metadata.json').read_text())
    assert metadata['scene_version'] == 'Project_v1_1'
    saved = json.loads((task.episode_dir / 'robot_tracking_configuration.json').read_text())
    assert saved['enabled'] is True and saved['max_position_bias_m'] == .001
    first = task._convert_action(action(task))[-1]
    assert first['robot_tracking']['sample_count'] == 1


def test_disabling_tracking_restores_frozen_plan_verification_and_reset_removes_old_estimate(task_factory):
    task = task_factory()
    task._convert_action(action(task))
    task.cfg.robot_tracking.enabled = False
    task._reset()
    assert task.tracking_compensator is None
    task.local_solution = lambda *args: pytest.fail('Disabled tracking must verify the supplied frozen plan')
    q7 = [.01, 0., 0., 0., 0., 0., 0.]
    q, _, _, _, conversion = task._convert_action(action(task, _executor_q7=q7))
    np.testing.assert_array_equal(q[:7], q7)
    assert conversion['IK']['reason'] == 'PREFLIGHT_REVERIFIED'
    assert conversion['robot_tracking'] is None and conversion['effective_IK_goal_TCP'] is None
    assert json.loads((task.episode_dir / 'robot_tracking_configuration.json').read_text())['enabled'] is False


def test_ik_failure_occurs_before_any_physical_apply_or_counter_advance(task_factory):
    task = task_factory()
    task.local_solution = lambda p, r, seed: dict(success=False, q=seed, reason='CPU_IK_REJECTION')
    before = (task.t, task.steps, task.control_steps, task.qcmd.copy())
    with pytest.raises(RuntimeError, match='CONTROL_OR_IK_FAILURE:CPU_IK_REJECTION'):
        task.step(action(task))
    assert (task.t, task.steps, task.control_steps) == before[:3]
    np.testing.assert_array_equal(task.qcmd, before[3])
    assert task.applied_count == 0


def test_plan_rejection_does_not_update_observer_or_execute_a_partial_prefix(task_factory):
    task = task_factory()
    task.local_solution = lambda p, r, seed: dict(success=False, q=seed, reason='CPU_IK_REJECTION')
    before = (task.t, task.steps, task.control_steps)
    plan = task.plan_cartesian([(np.array([.01, 0., 0.]), Rotation.identity())])
    assert plan['success'] is False and plan['q7'] == []
    assert plan['failure']['reference_tick'] == 0
    assert task.tracking_compensator._samples == 0
    assert (task.t, task.steps, task.control_steps) == before
    assert task.applied_count == 0
