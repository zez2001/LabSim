"""Release transaction fixtures only; these are not physical run evidence."""
import copy
import json
from pathlib import Path

import h5py
import numpy as np
import pytest

from data_collectors.lab_cuvette_project_release_collector import LabCuvetteProjectReleaseCollector
from utils.episode_selection import episode_matches_filter


def collector(tmp_path):
    return LabCuvetteProjectReleaseCollector(dict(version='Project_release_v1',
        physics=dict(hz=240, control_hz=60)), tmp_path, save_video=False)


def transition(c, tick=0):
    def state(step):
        return dict(episode_id=c.episode_id, joint_positions=np.arange(9) * .001,
            simulation_time=step / 60, step_index=step, phase='FIXTURE',
            camera_data={key: np.full((3, 4, 4), 100 + step, np.uint8) for key in c.CAMERAS})
    c.cache_transition(state(tick), dict(episode_id=c.episode_id, command_q=np.arange(9) * .001,
        gripper_target_m=.005, gripper_effort_limit_N=8), state(tick + 1), dict(terminated=False))


def score(c, success=True):
    return dict(episode_id=c.episode_id, record_valid=True, task_success=success,
        geometry_valid=True, physics_trustworthy=True, failure_domain='none' if success else 'task',
        failure_type='NONE' if success else 'TASK_INCOMPLETE', termination_reason='FIXTURE_END',
        task_type='loading', success_bc_eligible=success,
        task_result=dict(success=success, status='success' if success else 'failure'))


def test_finish_idempotent_and_cannot_relabel(tmp_path):
    c = collector(tmp_path)
    c.begin_episode(0, episode_id='new-0')
    transition(c)
    evidence = score(c)
    first = c.finish_episode({}, evidence)
    index = (tmp_path / 'dataset/meta/episode.jsonl').read_bytes()
    assert c.finish_episode({}, evidence) == first
    assert (tmp_path / 'dataset/meta/episode.jsonl').read_bytes() == index
    assert c.episode_count == 1
    with pytest.raises(ValueError, match='relabelled'):
        c.finish_episode({}, dict(evidence, task_success=False))
    with h5py.File(c.path) as f:
        assert f.attrs['publication_state'] == 'complete'
        assert f.attrs['complete'] and f.attrs['record_valid']
        assert json.loads(f['task_properties'].asstr()[()])['labels'] == first
        assert episode_matches_filter(f.attrs, 'success') == (True, 'accepted')


def test_close_only_incomplete_never_indexes(tmp_path):
    c = collector(tmp_path)
    c.begin_episode(0, episode_id='incomplete')
    transition(c)
    c.close()
    with h5py.File(c.path) as f:
        assert not f.attrs['complete']
        assert not episode_matches_filter(f.attrs, 'all_valid')[0]
    assert not (tmp_path / 'dataset/meta/episode.jsonl').exists()


def test_partial_stream_write_never_qualifies(tmp_path):
    c = collector(tmp_path)
    c.begin_episode(0, episode_id='partial-write')
    transition(c)
    c.file['side_camera_rgb'].resize(2, axis=0)  # controlled failed next-frame write fixture
    labels = c.finish_episode({}, score(c))
    assert not labels['record_valid'] and not labels['eligible_for_success_bc']
    assert 'incomplete_stream:side_camera_rgb' in labels['record_integrity_errors'] or 'incomplete_stream:camera_1_rgb' in labels['record_integrity_errors']


@pytest.mark.parametrize('stage', ['index', 'marker', 'h5_final_commit'])
def test_new_finalization_failure_preserves_previous_completed_episode(tmp_path, monkeypatch, stage):
    c = collector(tmp_path)
    c.begin_episode(0, episode_id='old-success')
    transition(c)
    c.finish_episode({}, score(c))
    previous = c.path.read_bytes()
    previous_index = (tmp_path / 'dataset/meta/episode.jsonl').read_bytes()
    c.begin_episode(1, episode_id='new-fails')
    transition(c)
    if stage == 'index':
        monkeypatch.setattr(c, '_publish_index', lambda row: (_ for _ in ()).throw(OSError('injected index failure')))
    elif stage == 'marker':
        from data_collectors import lab_cuvette_project_release_collector as module
        real = module.atomic_text
        def failing_marker(path, text):
            if str(path).endswith('_complete.json'):
                raise OSError('injected marker failure')
            return real(path, text)
        monkeypatch.setattr(module, 'atomic_text', failing_marker)
    else:
        real = h5py.File
        triggered = False
        def fail_one_commit(path, mode='r', *args, **kwargs):
            nonlocal triggered
            if Path(path) == c.path and mode == 'r+' and not triggered:
                triggered = True
                raise OSError('injected final H5 commit failure')
            return real(path, mode, *args, **kwargs)
        monkeypatch.setattr(h5py, 'File', fail_one_commit)
    with pytest.raises(OSError, match='injected'):
        c.finish_episode({}, score(c))
    assert (tmp_path / 'dataset/episode_0000.h5').read_bytes() == previous
    assert (tmp_path / 'dataset/meta/episode.jsonl').read_bytes() == previous_index
    with h5py.File(c.path) as f:
        assert not f.attrs['complete'] and f.attrs['publication_state'] == 'failed'
        assert not episode_matches_filter(f.attrs, 'all_valid')[0]
    assert not (tmp_path / 'episode_0001_complete.json').exists()
    with pytest.raises(RuntimeError, match='No open publishable'):
        c.finish_episode({}, score(c))


def test_reuse_three_episodes_clears_integrity_and_classifies_filters(tmp_path):
    c = collector(tmp_path)
    for index, success in enumerate((True, False, True)):
        c.begin_episode(index, episode_id=f'fixture-{index}')
        assert c.count == 0 and c._integrity_errors == [] and c._last_time is None
        transition(c)
        c.finish_episode({}, score(c, success))
    index = [json.loads(line) for line in (tmp_path / 'dataset/meta/episode.jsonl').read_text().splitlines()]
    assert [row['episode_id'] for row in index] == ['fixture-0', 'fixture-1', 'fixture-2']
    assert [row['labels']['task_success'] for row in index] == [True, False, True]
    for name, wanted in [('success', 2), ('failure', 1), ('all_valid', 3)]:
        assert sum(episode_matches_filter(h5py.File(path).attrs, name)[0]
                   for path in (tmp_path / 'dataset').glob('episode_*.h5')) == wanted


def test_pending_publication_rejected_even_if_complete_flag_true():
    attrs = dict(complete=True, publication_state='finalizing', record_valid=True,
                 task_success=True, eligible_for_success_bc=True)
    assert episode_matches_filter(attrs, 'success') == (False, 'publication_not_complete')


def test_legacy_files_keep_prior_filter_semantics():
    assert episode_matches_filter(dict(complete=True, record_valid=True,
        task_success=True, eligible_for_success_bc=True), 'success') == (True, 'accepted')


@pytest.mark.parametrize('mode', ['relative-links', 'copy'])
def test_multi_episode_index_reads_normal_act_dp_and_preserves_labels(tmp_path, mode):
    from demos.lab_cuvette_project_release_v1.dataset_index import build_index
    from scripts.read_lab_cuvette_env_v1_data import inspect
    root = tmp_path / 'run'
    for index, success in enumerate((True, False, True)):
        c = collector(root / f'episode_{index:04d}')
        c.begin_episode(0, episode_id=f'sim-fixture-{index}')
        transition(c)
        transition(c, 1)
        c.finish_episode({}, score(c, success))
    (root / 'run_manifest.json').write_text(json.dumps(dict(process_id=999999999)))
    result = build_index(root, root / 'index/episode_data.hdf5', mode=mode)
    assert result['counts'] == dict(success=2, failure=1, all_valid=3, incomplete=0)
    with h5py.File(root / 'index/episode_data.hdf5') as index:
        for group in index.values():
            assert group['side_camera_rgb'].id == group['camera_1_rgb'].id
            assert group['wrist_camera_rgb'].id == group['camera_2_rgb'].id
    for sample_filter, count in [('success', 2), ('failure', 1), ('all_valid', 3)]:
        for policy, observations in [('act', 1), ('dp', 3)]:
            read = inspect(root / 'index/episode_data.hdf5', sample_filter, policy, 16, observations)
            assert len(read['episodes']) == count
            assert all(row['exact_executed_actions'] and row['exact_saved_RGB'] for row in read['checks'])
    if mode == 'relative-links':
        import shutil
        moved = tmp_path / 'moved'
        shutil.copytree(root, moved)
        assert len(inspect(moved / 'index/episode_data.hdf5', 'all_valid')['episodes']) == 3


def test_release_facade_reset_clears_all_receipt_and_requested_command_state(tmp_path):
    from types import SimpleNamespace
    from demos.lab_cuvette_project_release_v1.environment import ProjectEnvironment
    class Task:
        episode_id = 'old'
        episode_dir = tmp_path
        cfg = SimpleNamespace(physics=SimpleNamespace(control_hz=60))
        def reset(self, seed, options):
            self.episode_id = 'fresh'
            self.grip, self.effort = .08, 8.
        def get_observation(self):
            return dict(episode_id=self.episode_id, observation_id='fresh:0', images={})
        def _write(self, path, value):
            path.write_text(json.dumps(value))
    env = ProjectEnvironment(Task())
    env._receipts['old-action'] = {'accepted': True}
    env._payload_hashes['old-action'] = 'old-hash'
    env.requested_opening, env.requested_effort = .009, .05
    obs = env.reset(seed=0)
    assert obs['episode_id'] == 'fresh'
    assert env.receipt('old-action') is None
    assert env._receipts == {} and env._payload_hashes == {}
    assert env.requested_opening == .08 and env.requested_effort == 8.


def test_release_cleanup_continues_past_an_owner_error(tmp_path):
    from tasks.lab_cuvette_loading_project_release import LabCuvetteProjectRelease
    calls = []
    class Owner:
        def __init__(self, name, fail=False):
            self.name, self.fail = name, fail
        def close(self):
            calls.append(self.name)
            if self.fail:
                raise OSError('injected owner close error')
    class Writer:
        def release(self):
            calls.append('video')
    class World:
        def stop(self):
            calls.append('world-stop')
        def clear(self):
            calls.append('world-clear')
    task = LabCuvetteProjectRelease.__new__(LabCuvetteProjectRelease)
    task._video_writers = {'side': Writer()}
    task.collector, task.recorder, task.rig = Owner('collector', True), Owner('recorder'), Owner('rig')
    task.ctx, task.episode_dir = {'world': World()}, tmp_path
    task._cleanup_episode()
    assert calls == ['video', 'collector', 'recorder', 'rig', 'world-stop', 'world-clear']
    assert task.ctx is None and task.collector is None and task.recorder is None and task.rig is None
    assert task._cleanup_errors[0]['resource'] == 'collector'


def test_standard_reset_rejects_slot_override_before_mutating_episode():
    from types import SimpleNamespace
    from tasks.lab_cuvette_loading_project_release import LabCuvetteProjectRelease
    task = LabCuvetteProjectRelease.__new__(LabCuvetteProjectRelease)
    task.base_cfg = SimpleNamespace(rack=SimpleNamespace(selected_slot_id='A1'))
    task._finalization_error = {'type': 'old-failure'}
    with pytest.raises(ValueError, match='frozen source slot'):
        task.reset(seed=0, options={'mode': 'standard', 'source_slot_id': 'F6'})
    assert task._finalization_error == {'type': 'old-failure'}
