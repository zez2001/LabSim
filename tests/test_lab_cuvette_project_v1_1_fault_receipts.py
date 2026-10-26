"""CPU fault injection for measured receipts; no Isaac or physical claims."""
from __future__ import annotations

import copy
import json
from types import SimpleNamespace

import numpy as np
import pytest

from demos.lab_cuvette_project_v1_1.environment import ProjectEnvironment


class FaultTask:
    """Keep robot state separate from the public render/observation cache."""

    def __init__(self, path):
        self.episode_dir = path
        self.episode_id = "faults"
        self.control_steps = 0
        self.steps = 4
        self.t = 1 / 60
        self.ended = False
        self._result = None
        self.grip = .0101
        self.effort = 5.
        self.qcmd = np.zeros(9)
        self.cfg = SimpleNamespace(physics=SimpleNamespace(control_hz=60))
        self.actual_q = np.zeros(9)
        self.robot = SimpleNamespace(get_joint_positions=lambda: self.actual_q.copy())
        self.pose = dict(position_m=[0., 0., 1.], quaternion_wxyz=[1., 0., 0., 0.])
        self.commands = []
        self.reject_cartesian = False
        self.invalid_endpoint_quaternion = None
        self.observation_reads = 0
        self.partial_cache_failure = False
        self.task_end = None
        self.held = False

    def get_observation(self):
        self.observation_reads += 1
        pose = copy.deepcopy(self.pose)
        # The input observation is valid; fault only the endpoint snapshot.
        if self.invalid_endpoint_quaternion is not None and self.observation_reads > 1:
            pose["quaternion_wxyz"] = list(self.invalid_endpoint_quaternion)
        return dict(episode_id=self.episode_id,
                    observation_id=f"faults:{self.control_steps}",
                    TCPpose=pose, gripper_opening_m=.0107,
                    joint_positions=np.zeros(9), images={})

    def joint_bounds(self):
        return -np.ones(7), np.ones(7), np.ones(7)

    def forward(self, q):
        # A simple exact FK stand-in, independent of the public pose cache.
        q = np.asarray(q)
        return np.array([q[0], q[1], 1. + q[2]]), np.eye(3)

    def plan_cartesian(self, references):
        commands = []
        for p, _ in references:
            q = np.zeros(7)
            q[:3] = np.asarray(p) - [0., 0., 1.]
            commands.append(q)
        return dict(success=not self.reject_cartesian, q7=commands,
                    summary=dict(planned_ticks=0 if self.reject_cartesian else len(commands)),
                    failure=dict(reason="INJECTED_REJECTION"))

    def step(self, action):
        self.commands.append(copy.deepcopy(action))
        if self.partial_cache_failure:
            # Physics advances by two substeps, then rendering/recording fails
            # before the public cache and complete-control counter are updated.
            self.steps += 2
            self.t += 1 / 120
            self.actual_q[:3] = [.003, .004, .002]
            raise RuntimeError("injected render failure after partial physics")
        self.steps += 4
        self.t += 1 / 60
        self.control_steps += 1
        self.actual_q[:7] = action["_executor_q7"]
        self.pose = dict(position_m=list(action["values"][:3]),
                         quaternion_wxyz=list(action["values"][3:]))
        self.grip = action["gripper_opening_m"]
        if self.task_end:
            self.ended = True
            self._result = dict(termination_reason=self.task_end, failure_type=self.task_end,
                                failure_domain="task", task_success=False)

    def hold_actual_joints(self):
        self.held = True

    def finalize_episode(self, reason, failure_type):
        self.ended = True
        self._result = dict(termination_reason=reason, failure_type=failure_type,
                            failure_domain="executor")


def action(**overrides):
    value = dict(action_id="one", episode_id="faults", observation_id="faults:0",
                 type="ee_delta", values=[.005, 0., 0., 0., 0., 0.],
                 frame="world", duration_s=1.)
    value.update(overrides)
    return value


def assert_no_advance(task, before):
    assert (task.control_steps, task.steps, task.t) == before
    assert task.commands == []


def test_joint_plan_rejection_is_not_a_safety_stop_and_keeps_observation(tmp_path):
    task = FaultTask(tmp_path)
    before = (task.control_steps, task.steps, task.t)
    env = ProjectEnvironment(task)
    request = action(type="joint_position", values=[2., 0., 0., 0., 0., 0., 0.], frame="joint")
    result = env.execute(request)
    assert result["stop_reason"] == "JOINT_PLAN_REJECTED"
    assert result["accepted"] is False
    assert result["safety_stopped"] is False
    assert result["stop_domain"] == "none"
    assert result["partial_execution"] is False
    assert result["executed_control_ticks"] == 0
    assert result["executed_physics_steps"] == 0
    assert result["executed_duration_s"] == 0.
    assert result["observation_id_after"] == "faults:0"
    assert_no_advance(task, before)
    assert env.receipt("one") == result
    assert env.execute(request) == result
    assert_no_advance(task, before)


@pytest.mark.parametrize("quaternion", [[0., 0., 0., 0.],
                                         [float("nan"), 0., 0., 0.],
                                         [float("inf"), 0., 0., 0.]])
def test_invalid_endpoint_quaternion_closes_queryable_strict_json_receipt(tmp_path, quaternion):
    task = FaultTask(tmp_path)
    task.reject_cartesian = True
    task.invalid_endpoint_quaternion = quaternion
    before = (task.control_steps, task.steps, task.t)
    env = ProjectEnvironment(task)
    request = action()
    result = env.execute(request)
    assert result["actual_endpoint_valid"] is False
    assert result["final_position_error_m"] is None
    assert result["final_orientation_error_rad"] is None
    assert result["target_reached"] is False
    assert result["execution_finished"] is True
    assert env.receipt("one") == result
    assert env.execute(request) == result
    # Nonfinite measurements must not leave an unpersistable/in-flight receipt.
    json.dumps(result, allow_nan=False)
    lines = (tmp_path / "action_receipts.jsonl").read_text().splitlines()
    assert len(lines) == 1
    json.loads(lines[0], parse_constant=lambda value: pytest.fail("nonfinite JSON: " + value))
    assert_no_advance(task, before)


def test_partial_physics_uses_fresh_robot_fk_without_claiming_a_cached_successor(tmp_path):
    task = FaultTask(tmp_path)
    task.partial_cache_failure = True
    env = ProjectEnvironment(task)
    request = action()
    result = env.execute(request)
    assert result["accepted"] is True
    assert result["partial_execution"] is True
    assert result["safety_stopped"] is True
    assert result["executed_control_ticks"] == 0
    assert result["executed_physics_steps"] == 2
    assert result["executed_duration_s"] == pytest.approx(1 / 120)
    assert result["incomplete_control_interval"] is True
    assert result["actual_endpoint_valid"] is True
    assert result["actual_endpoint_TCP"]["position_m"] == pytest.approx([.003, .004, 1.002])
    assert task.pose["position_m"] == [0., 0., 1.]
    assert result["final_position_error_m"] == pytest.approx(np.linalg.norm([-.002, .004, .002]))
    assert result["successor_observation_available"] is False
    assert result["observation_id_after"] is None
    assert result["tracking_error_coverage_complete"] is False
    assert result["target_reached"] is False
    assert task.held and task.ended
    assert env.receipt("one") == result
    assert env.execute(request) == result
    assert len(task.commands) == 1


@pytest.mark.parametrize("fingers", [[.004, .004], [.004, .006]])
def test_contradictory_9d_fingers_are_rejected_before_any_physics(tmp_path, fingers):
    task = FaultTask(tmp_path)
    before = (task.control_steps, task.steps, task.t)
    env = ProjectEnvironment(task)
    request = action(type="joint_position", values=[0.] * 7 + fingers,
                     frame="joint", gripper_opening_m=.010)
    # Both approved API choices are safe: reject every 9D action, or accept
    # consistent symmetric 9D only. A validation error and an explicit rejection
    # receipt are distinct allowed representations of zero-execution refusal.
    try:
        result = env.execute(request)
    except ValueError:
        pass
    else:
        assert result["accepted"] is False
        assert result["executed_control_ticks"] == 0
        assert result["executed_physics_steps"] == 0
        assert result["executed_duration_s"] == 0.
        assert result["partial_execution"] is False
        assert result["safety_stopped"] is False
    assert_no_advance(task, before)


def test_grasp_slip_task_end_does_not_become_a_safety_stop(tmp_path):
    task = FaultTask(tmp_path)
    task.task_end = "GRASP_SLIP"
    result = ProjectEnvironment(task).execute(action())
    assert result["stop_reason"] == "GRASP_SLIP"
    assert result["stop_domain"] == "task"
    assert result["safety_stopped"] is False
    assert result["partial_execution"] is True
    assert result["executed_control_ticks"] == 1
    assert result["executed_physics_steps"] == 4
    assert result["executed_duration_s"] == pytest.approx(1 / 60)
    assert task._result["failure_type"] == "GRASP_SLIP"
    assert task._result["task_success"] is False
