"""Public lifecycle guards; fake task measures stepping, never fabricates outcomes."""
import copy
from types import SimpleNamespace
import numpy as np
import pytest
from demos.lab_cuvette_project_v1.environment import ProjectEnvironment


class Task:
    def __init__(self, path):
        self.episode_dir = path
        self.episode_id = 'episode-1'
        self.control_steps, self.t, self.ended, self._result = 0, 0., False, None
        self.cfg = SimpleNamespace(physics=SimpleNamespace(control_hz=60),
            project=SimpleNamespace(backend_gripper_effort_N=8))
        self.commands = []
        self.observation = dict(episode_id=self.episode_id, observation_id='episode-1:0',
            TCPpose=dict(position_m=[0., 0., 1.], quaternion_wxyz=[1., 0., 0., 0.]),
            gripper_opening_m=.08, images={}, joint_positions=np.zeros(9))

    def get_observation(self):
        result = copy.deepcopy(self.observation)
        result['observation_id'] = f'{self.episode_id}:{self.control_steps}'
        return result

    def step(self, action):
        self.commands.append(copy.deepcopy(action))
        self.control_steps += 1
        self.t = self.control_steps / 60
        if action['type'] == 'ee_pose':
            self.observation['TCPpose']['position_m'] = action['values'][:3]
        self.observation['gripper_opening_m'] = action['gripper_opening_m']

    def finalize_episode(self, reason, failure_type):
        self.finalize_arguments = (reason, failure_type)
        self.ended = True
        self._result = dict(task_success=None, termination_reason=reason, failure_type=failure_type)


def action(**kwargs):
    return dict(action_id='first', episode_id='episode-1', observation_id='episode-1:0',
        type='ee_delta', values=[.02, 0, 0, 0, 0, 0], frame='world', duration_s=1., **kwargs)


def test_acknowledged_action_is_never_executed_twice(tmp_path):
    task = Task(tmp_path)
    env = ProjectEnvironment(task)
    first = env.execute(action())
    assert task.control_steps == 60
    assert env.execute(action()) == first
    assert task.control_steps == 60
    assert first['completed'] is True and first['executed_control_ticks'] == 60
    assert task.commands[-1]['values'][:3] == [.02, 0., 1.]


def test_stale_observation_and_reused_action_payload_refused(tmp_path):
    env = ProjectEnvironment(Task(tmp_path))
    env.execute(action())
    changed = action()
    changed['values'][0] = .01
    with pytest.raises(ValueError, match='different payload'):
        env.execute(changed)
    changed['action_id'] = 'second'
    with pytest.raises(ValueError, match='Stale'):
        env.execute(changed)


@pytest.mark.parametrize('change,match', [
    ({'values':[.05, 0, 0, 0, 0, 0], 'duration_s':3.}, 'per-action'),
    ({'duration_s':.1}, '0.02m/s'),
    ({'duration_s':.111}, 'whole control ticks'),
    ({'metadata':{'teacher_phase':'INSERT'}}, 'teacher phases'),
    ({'gripper_effort_limit_N':9.}, 'Gripper'),
])
def test_invalid_action_causes_no_physics_steps(tmp_path, change, match):
    task = Task(tmp_path)
    command = action()
    command.update(change)
    with pytest.raises(ValueError, match=match):
        ProjectEnvironment(task).execute(command)
    assert task.control_steps == 0


def test_opening_is_symmetric_ramp_not_pose_assignment(tmp_path):
    task = Task(tmp_path)
    command = action()
    command.update(values=[0.] * 6, gripper_opening_m=.02, gripper_effort_limit_N=2.)
    ProjectEnvironment(task).execute(command)
    assert task.commands[0]['gripper_opening_m'] > .02
    assert task.commands[-1]['gripper_opening_m'] == pytest.approx(.02)
    assert all(c['gripper_effort_limit_N'] == 2 for c in task.commands)


def test_partial_exception_reserves_action_id(tmp_path):
    task = Task(tmp_path)
    def fail(action):
        task.control_steps += 1
        raise RuntimeError('simulator disconnected')
    task.step = fail
    env = ProjectEnvironment(task)
    with pytest.raises(RuntimeError, match='disconnected'):
        env.execute(action())
    receipt = env.execute(action())
    assert receipt['completed'] is False
    assert receipt['error_type'] == 'RuntimeError'
    assert task.control_steps == 1


@pytest.mark.parametrize('failure_type', ['MODEL_SERVICE_ERROR', 'INPUT_CONTRACT_ERROR',
    'PROCESS_INTERRUPTED', 'PHYSICS_INVALID'])
def test_backend_failure_is_forwarded_before_independent_finalization(tmp_path, failure_type):
    task = Task(tmp_path)
    result = ProjectEnvironment(task).finish('provider_or_protocol_error', failure_type=failure_type)
    assert task.finalize_arguments == ('provider_or_protocol_error', failure_type)
    assert result['task_success'] is None


def test_backend_failure_never_rewrites_previously_scored_outcome(tmp_path):
    task = Task(tmp_path)
    task.ended = True
    task._result = dict(task_success=False, termination_reason='REAL_PHYSICAL_DROP')
    result = ProjectEnvironment(task).finish('provider_error', failure_type='MODEL_SERVICE_ERROR')
    assert result['termination_reason'] == 'REAL_PHYSICAL_DROP'
    assert result['task_success'] is False
    assert not hasattr(task, 'finalize_arguments')


def test_finish_cannot_submit_a_success_classification(tmp_path):
    task = Task(tmp_path)
    with pytest.raises(ValueError, match='nonphysical'):
        ProjectEnvironment(task).finish('done', failure_type='SUCCESS')
    assert not task.ended


@pytest.mark.parametrize('options', [{'mode':'random'}, {'subtask':'preinsert_diagnostic'}])
def test_reset_cannot_stamp_another_scene_or_subtask_as_standard_loading(tmp_path, options):
    task = Task(tmp_path)
    with pytest.raises(ValueError, match='only'):
        ProjectEnvironment(task).reset(options=options)
    assert task.control_steps == 0
