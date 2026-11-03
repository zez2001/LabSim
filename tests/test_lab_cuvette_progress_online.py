"""CPU lifecycle fixtures: diagnostics must never change physics or task labels."""
import copy
from pathlib import Path
from types import SimpleNamespace

import pytest
from omegaconf import OmegaConf

from demos.lab_cuvette_progress_v1 import online
from tasks.lab_cuvette_loading_project_release import LabCuvetteProjectRelease
from tasks.lab_cuvette_loading_project_v1_1 import LabCuvetteProjectV11


class Writer:
    def __init__(self, calls, *, fail=None):
        self.calls, self.fail = calls, fail
        self.metadata, self.rows, self.transitions = {}, [], []
        self.status, self.summary, self.closed = 'recording', None, False

    def physical(self, row):
        self.calls.append('progress-physical')
        if self.fail == 'physical':
            raise OSError('injected progress disk failure')
        self.rows.append(copy.deepcopy(row))
        # Deliberately misbehaving observer: the scorer must still see raw data.
        row['object_position_m'][0] = 999.

    def transition(self, t_obs, t_next, **kwargs):
        self.calls.append('progress-transition')
        if self.fail == 'transition':
            raise OSError('injected progress transition failure')
        self.transitions.append(dict(t_obs=t_obs, t_next=t_next, **kwargs))

    def finalize(self, termination=None, original_result=None):
        self.calls.append('progress-finalize')
        if self.fail == 'finalize':
            raise OSError('injected progress finalize failure')
        self.status = termination.get('progress_status', 'complete')
        self.summary = dict(progress_status=self.status, original_result=copy.deepcopy(original_result))
        return copy.deepcopy(self.summary)

    def abort(self, error, termination=None, original_result=None):
        self.calls.append('progress-abort')
        self.status, self.summary = 'interrupted', dict(progress_status='interrupted')
        return self.summary

    def close(self):
        self.calls.append('progress-close')
        self.closed = True
        if self.fail == 'close':
            raise OSError('injected progress close failure')


def task_fixture(tmp_path, monkeypatch, *, flag=True, fail=None, episode='one'):
    tmp_path.mkdir(parents=True, exist_ok=True)
    calls = []
    task = LabCuvetteProjectRelease.__new__(LabCuvetteProjectRelease)
    task.base_cfg = task.cfg = OmegaConf.create(dict(version='Project_release_v1',
        progress=dict(enabled=flag), physics=dict(hz=240, control_hz=60)))
    task.episode_id, task.episode_dir, task.episode_index = episode, tmp_path, 0
    task._result, task._finalization_error, task._recording_sinks = None, None, {}
    task.ended, task._tick_trace = False, None
    writer = Writer(calls, fail=fail)

    def start(session, sample):
        calls.append('progress-start')
        session.writer = writer
    monkeypatch.setattr(online.OnlineProgressSession, '_start', start)

    def capture(step, t, phase='RESET'):
        calls.append('capture')
        return dict(t=t, physics_step=step, phase=phase,
                    object_position_m=[1., 2., 3.], command_q9=[0.] * 9, gripper_target_m=.04)
    recorder = SimpleNamespace(capture=capture, close=lambda: calls.append('recorder-close'))
    task.recorder = recorder
    return task, recorder, writer, calls


def state(t, step):
    return dict(simulation_time=t, step_index=step)


def test_disabled_release_keeps_original_step_and_recorder(tmp_path, monkeypatch):
    task, recorder, writer, calls = task_fixture(tmp_path, monkeypatch, flag=False)
    assert LabCuvetteProjectRelease.step is LabCuvetteProjectV11.step
    assert not hasattr(task, '_progress_session')
    row = recorder.capture(0, 0.)
    assert row['object_position_m'] == [1., 2., 3.]
    assert calls == ['capture'] and not writer.rows


def test_step_zero_and_initial_gravity_are_observed_without_mutating_scorer_input(tmp_path, monkeypatch):
    task, recorder, writer, calls = task_fixture(tmp_path, monkeypatch)
    for step in range(5):
        raw = recorder.capture(step, step / 240, 'RESET' if step == 0 else 'RESET_INITIALIZATION')
        assert raw['object_position_m'] == [1., 2., 3.]
    assert [r['physics_step'] for r in writer.rows] == list(range(5))
    assert calls[:3] == ['capture', 'progress-start', 'progress-physical']
    assert all(not row['_execution']['available'] for row in writer.rows)
    assert task._progress_session.physics_count == 5


def test_previous_episode_execution_trace_does_not_leak_into_reset(tmp_path, monkeypatch):
    task, recorder, writer, _ = task_fixture(tmp_path, monkeypatch)
    task._tick_trace = dict(action=dict(episode_id='old', values=[1.]))
    recorder.capture(0, 0.)
    recorder.capture(1, 1 / 240, 'RESET_INITIALIZATION')
    task._tick_trace = dict(action=dict(episode_id='one', values=[2.]))
    recorder.capture(5, 5 / 240, 'POLICY')
    assert [r['_execution']['available'] for r in writer.rows] == [False, False, True]
    assert writer.rows[-1]['_execution']['raw_action']['values'] == [2.]


def test_cache_hook_preserves_original_return_and_only_records_accepted_transition(tmp_path, monkeypatch):
    task, recorder, writer, calls = task_fixture(tmp_path, monkeypatch)
    recorder.capture(4, 4 / 240)
    recorder.capture(8, 8 / 240)
    accepted = object()
    def cache(before, command, after, flags):
        calls.append('cache')
        if command.get('reject'):
            raise ValueError('original collector rejection')
        return accepted
    task.collector = SimpleNamespace(cache_transition=cache)
    flags = dict(terminated=True, truncated=False, reward=0.)
    command = dict(raw_output=dict(action_id='action-one'))
    assert task.collector.cache_transition(state(4 / 240, 0), command, state(8 / 240, 1), flags) is accepted
    record = writer.transitions[0]
    assert record['t_obs'] == 4 / 240 and record['t_next'] == 8 / 240
    assert record['transition_metadata']['terminated']
    assert record['transition_metadata']['original_reward'] == 0.
    assert calls[-2:] == ['cache', 'progress-transition']
    with pytest.raises(ValueError, match='original collector'):
        task.collector.cache_transition(state(8 / 240, 1), dict(reject=True), state(12 / 240, 2), {})
    assert len(writer.transitions) == 1


def test_original_capture_exception_is_not_hidden_or_relabelled(tmp_path, monkeypatch):
    task, _, writer, _ = task_fixture(tmp_path, monkeypatch)
    def failed_capture(*args):
        raise RuntimeError('original physics capture failed')
    task.recorder = SimpleNamespace(capture=failed_capture)
    with pytest.raises(RuntimeError, match='original physics'):
        task.recorder.capture(0, 0.)
    assert not writer.rows and task._progress_session.physics_count == 0


@pytest.mark.parametrize('failure', ['physical', 'transition', 'finalize', 'close'])
def test_sidecar_failure_preserves_original_success_reward_and_eligibility(tmp_path, monkeypatch, failure):
    task, recorder, writer, calls = task_fixture(tmp_path, monkeypatch, fail=failure)
    original = dict(task_success=True, record_valid=True, success_bc_eligible=True, reward=1.)
    recorder.capture(0, 0.)
    recorder.capture(4, 4 / 240)
    task.collector = SimpleNamespace(cache_transition=lambda *args: 'original-cached')
    assert task.collector.cache_transition(state(0., 0), {}, state(4 / 240, 1), {}) == 'original-cached'
    task._result = copy.deepcopy(original)
    assert online.finish(task, dict(termination_reason='COMPLETE')) == 'partial'
    assert {k: task._result[k] for k in original} == original
    assert task._result['progress_status'] == 'partial' and writer.closed
    assert (tmp_path / 'progress_failure.json').exists()
    assert online.finish(task, dict(termination_reason='MUST_NOT_RELABEL')) == 'partial'
    assert calls.count('progress-close') == 1


def test_release_closes_progress_before_publication_and_finalize_is_idempotent(tmp_path, monkeypatch):
    task, recorder, writer, calls = task_fixture(tmp_path, monkeypatch)
    recorder.capture(0, 0.)
    original = dict(task_success=True, record_valid=True, success_bc_eligible=True)
    def parent_finalize(self, *args):
        calls.append('original-scorer-and-video-finalize')
        self._result = copy.deepcopy(original)
        self.ended = True
        return copy.deepcopy(self._result)
    monkeypatch.setattr(LabCuvetteProjectV11, 'finalize_episode', parent_finalize)
    task.collector = SimpleNamespace(cache_transition=lambda *args: None,
        prepared_labels=lambda **kwargs: dict(complete=True, publication_state='complete'),
        record_purpose='demonstration', commit_publication=lambda: calls.append('commit'))
    result = task.finalize_episode('CONTROLLER_WORKFLOW_COMPLETE')
    assert result['progress_status'] == 'complete'
    assert all(result[key] == value for key, value in original.items())
    assert calls.index('original-scorer-and-video-finalize') < calls.index('recorder-close')
    assert calls.index('recorder-close') < calls.index('progress-finalize')
    assert calls.index('progress-close') < calls.index('commit')
    before = list(calls)
    assert task.finalize_episode('DUPLICATE') == result and calls == before


def test_cleanup_aborts_unfinished_sidecar_and_new_recorder_starts_new_session(tmp_path, monkeypatch):
    task, recorder, writer, calls = task_fixture(tmp_path, monkeypatch)
    recorder.capture(0, 0.)
    first = task._progress_session
    task.collector, task.rig, task.ctx, task._video_writers = None, None, None, {}
    task._cleanup_episode()
    assert writer.closed and first.finalized
    assert first.summary['progress_status'] == 'interrupted'
    assert calls.index('recorder-close') < calls.index('progress-finalize')
    task.episode_id, task.episode_dir = 'two', tmp_path / 'two'
    task.episode_dir.mkdir()
    task.recorder = recorder
    assert task._progress_session is not first
    assert task._progress_session.physics_count == 0 and not task._progress_session.errors


def test_multiple_environment_hooks_are_isolated(tmp_path, monkeypatch):
    one, first_recorder, _, _ = task_fixture(tmp_path / 'one', monkeypatch, episode='one')
    first_recorder.capture(0, 0.)
    first = one._progress_session
    two, second_recorder, _, _ = task_fixture(tmp_path / 'two', monkeypatch, episode='two')
    second_recorder.capture(0, 0.)
    first_recorder.capture(1, 1 / 240)
    assert one._progress_session is first and two._progress_session is not first
    assert first.physics_count == 2 and two._progress_session.physics_count == 1
    assert first.metadata['episode_id'] == 'one'
    assert two._progress_session.metadata['episode_id'] == 'two'


def test_progress_configuration_does_not_change_physical_scene_contract():
    from demos.lab_cuvette_project_release_v1.contract import scene_contract
    root = Path(__file__).resolve().parents[1]
    cfg = OmegaConf.load(root / 'config/lab_cuvette_loading/Project_release_v1/standard.yaml')
    previous = scene_contract(cfg)
    cfg.progress = dict(enabled=True, configuration=dict(normalization=dict(example=123.)))
    assert scene_contract(cfg) == previous


def test_normal_launchers_expose_opt_in_progress_switch():
    from demos.lab_cuvette_project_release_v1.launch import parser as launch_parser
    from demos.lab_cuvette_project_release_v1.run import parser as sequence_parser
    for factory in (launch_parser, sequence_parser):
        assert not factory().parse_args(['--output', '/tmp/parse-only']).progress
        assert factory().parse_args(['--output', '/tmp/parse-only', '--progress']).progress


def test_unexpected_diagnostic_finish_error_cannot_escape_original_cleanup(tmp_path, monkeypatch):
    task, recorder, writer, calls = task_fixture(tmp_path, monkeypatch)
    recorder.capture(0, 0.)
    task._result = dict(task_success=True, record_valid=True, success_bc_eligible=True)
    def unexpected(*args, **kwargs):
        raise RuntimeError('unexpected diagnostic integration error')
    monkeypatch.setattr(online, 'finish', unexpected)
    task.collector, task.rig, task.ctx, task._video_writers = None, None, None, {}
    task._cleanup_episode()
    assert task._result['task_success'] and task._result['record_valid']
    assert task._result['success_bc_eligible'] and task._result['progress_status'] == 'partial'
    assert task.recorder is None and 'recorder-close' in calls and writer.closed
