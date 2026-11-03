"""CPU contracts for causal sidecars and read-only offline adapters.

Small synthetic files are test fixtures only, never demonstrations or evaluations.
The physics/state-machine scenario suite lives in test_lab_cuvette_progress_v1.
"""
from __future__ import annotations

import copy
import gzip
import json
from pathlib import Path

import h5py
import pytest

from demos.lab_cuvette_progress_v1.io import ProgressWriter, file_sha256, iter_json_rows
from demos.lab_cuvette_progress_v1 import offline
from demos.lab_cuvette_progress_v1.report import generate_report


class CausalProbe:
    """State-machine independent probe exposes the exact writer/adapter inputs."""
    VERSION = 'test_probe'

    def reset(self, metadata):
        self.events, self.samples = [], []
        self.last = None

    def update(self, sample):
        self.samples.append(copy.deepcopy(sample))
        events = copy.deepcopy(sample.get('new_events', []))
        self.events.extend(events)
        self.last = dict(t=sample['t'], physics_step=sample.get('physics_step'),
            current_stage=sample.get('stage', 'approach_grasp'), stage_vector=[False] * 9,
            stages={}, milestones={}, metrics={'raw_depth_m': dict(available='depth_m' in sample,
                value=sample.get('depth_m'), unit='m')}, hold_state=sample.get('hold_state', 'unknown'),
            stable_window={}, events=events)
        return self.last

    def finalize(self, termination):
        return dict(progress_complete=None, events=self.events, last_snapshot=self.last,
                    termination_domain=termination.get('termination_reason', 'unknown'))


def event(name, t):
    return dict(event_id=name, name=name, t=t, candidate_start_t=t, confirmed_t=t,
                attempt_id=None, evidence={})


def rows():
    return [dict(t=t, physics_step=i, depth_m=t / 100, new_events=[event(str(i), t)],
                 native_contact_events_count=int(t >= .5))
            for i, t in enumerate((0., .5, 1., 1.2, 1.4))]


def writer(path):
    return ProgressWriter(path, {}, {'episode_id': 'fixture-only'}, evaluator=CausalProbe())


def test_boundary_events_reset_partial_terminal_and_no_raw_scene(tmp_path):
    output = writer(tmp_path)
    data = rows()
    for row in data[:3]:
        output.physical(dict(row, unneeded_scene={'pixels': [123] * 100}))
    a = output.transition(0, 1)
    for row in data[3:]:
        output.physical(row)
    b = output.transition(1, 1.4, transition_metadata={'partial_terminal_control_interval': True, 'done': True})
    summary = output.finalize({'termination_reason': 'timeout'}, {'task_success': False})
    assert [e['t'] for e in a['events']] == [.5, 1.]
    assert [e['t'] for e in b['events']] == [1.2, 1.4]
    assert [e['t'] for e in summary['initial_events']] == [0.]
    assert a['before']['t'] == 0 and a['after']['t'] == b['before']['t'] == 1
    assert b['transition']['partial_terminal_control_interval'] is True
    assert summary['original_result'] == {'task_success': False}
    assert b['after']['metrics']['raw_depth_m']['value'] == pytest.approx(.014)
    assert 'unneeded_scene' not in gzip.decompress((tmp_path / 'progress_v1.jsonl.gz').read_bytes()).decode()
    assert len(list(iter_json_rows(tmp_path / 'progress_events.jsonl'))) == 5
    assert len(output._snapshots) == 1


def test_missing_boundary_never_uses_a_future_state(tmp_path):
    output = writer(tmp_path)
    output.physical({'t': 0})
    output.physical({'t': .6})
    output.physical({'t': 1})
    record = output.transition(.5, 1)
    assert record['before'] is None
    assert record['evidence_alignment']['before_available'] is False
    output.close()


def test_close_finalize_idempotent_reset_isolated_and_repeated_output_rejected(tmp_path):
    output = writer(tmp_path / 'first')
    output.physical({'t': 0, 'new_events': [event('reset', 0)]})
    summary = output.finalize({}, {'task_success': False})
    assert output.finalize({}, {'task_success': False}) == summary
    assert output.close() == summary
    assert output.close() == summary
    with pytest.raises(RuntimeError, match='closed'):
        output.physical({'t': 1})
    with pytest.raises(FileExistsError):
        writer(tmp_path / 'first')
    next_episode = writer(tmp_path / 'second')
    next_episode.physical({'t': 0})
    assert next_episode.close()['events'] == []
    assert next_episode.summary['output_integrity']['status'] == 'interrupted'


def test_write_exception_preserves_original_result_and_records_interruption(tmp_path):
    output = writer(tmp_path)
    output.physical({'t': 0})
    output.physical({'t': 1})
    output._gzip.close()
    with pytest.raises(ValueError):
        output.transition(0, 1)
    summary = output.abort(RuntimeError('disk-full probe'), original_result={'task_success': True})
    assert summary['original_result']['task_success'] is True
    assert summary['output_integrity']['status'] == 'interrupted'
    assert {e['operation'] for e in summary['output_integrity']['errors']} == {'transition', 'abort'}
    assert json.loads((tmp_path / 'progress_summary.json').read_text()) == summary
    assert output.close() == summary


def test_future_physics_and_overlap_rejected(tmp_path):
    output = writer(tmp_path)
    output.physical({'t': 0})
    with pytest.raises(ValueError, match='future'):
        output.transition(0, 1)
    output.physical({'t': 1})
    output.transition(0, 1)
    with pytest.raises(ValueError, match='Overlapping'):
        output.transition(0, 1)
    output.close()


def make_episode(path, *, physics=True, complete=True):
    path.mkdir()
    (path / 'dataset').mkdir()
    data = rows()
    h5 = path / 'dataset' / 'episode_0000.h5'
    with h5py.File(h5, 'w') as h:
        h.attrs.update(episode_id='fixture-only', complete=complete,
            publication_state='complete' if complete else 'recording', task_success=False,
            termination_reason='fixture_timeout', configuration_json=json.dumps({'version': 'fixture'}))
        h['timestamp'] = [0., 1.]
        h['next_timestamp'] = [1., 1.4]
        h['done'] = [False, True]
        h['partial_terminal_control_interval'] = [False, True]
        for key, values in [('privileged/state_json', [data[0], data[2]]),
                            ('privileged/next_state_json', [data[2], data[4]]),
                            ('actions_raw_json', [{'type': 'ee_pose', 'values': [1, 2, 3]}, {'type': 'hold'}]),
                            ('action_conversion_json', [{}, {}]), ('task_events_json', [[], []])]:
            h.create_dataset(key, data=[json.dumps(v) for v in values], dtype=h5py.string_dtype())
    if physics:
        with gzip.open(path / 'physics_records.jsonl.gz', 'wt') as stream:
            stream.write(''.join(json.dumps(r) + '\n' for r in data))
        with gzip.open(path / 'native_contact_events.jsonl.gz', 'wt') as stream:
            stream.write(json.dumps(dict(t=.5, possible_duplicate_same_step=True)) + '\n')
    return h5


@pytest.fixture
def probe_adapter(monkeypatch):
    from demos.lab_cuvette_progress_v1 import config
    captured = []

    def factory(path, resolved, metadata):
        result = ProgressWriter(path, resolved, metadata, evaluator=CausalProbe())
        captured.append(result)
        return result

    monkeypatch.setattr(offline, 'ProgressWriter', factory)
    monkeypatch.setattr(config, 'resolve_config', lambda *args, **kwargs: {})
    return captured


def test_offline_online_same_inputs_same_events_and_partial_control_records(tmp_path, probe_adapter):
    h5 = make_episode(tmp_path / 'episode')
    before_hash = file_sha256(h5)
    result = offline.analyze_episode(h5, tmp_path / 'offline', make_report=False)
    online = writer(tmp_path / 'online')
    for row in rows()[:3]:
        online.physical(row)
    online.transition(0, 1)
    for row in rows()[3:]:
        online.physical(row)
    online.transition(1, 1.4, transition_metadata={'partial_terminal_control_interval': True})
    online_summary = online.finalize()
    a = list(iter_json_rows(tmp_path / 'offline' / 'progress_v1.jsonl.gz'))
    b = list(iter_json_rows(tmp_path / 'online' / 'progress_v1.jsonl.gz'))
    assert [[r[k] for k in ('before', 'after', 'events')] for r in a] == [[r[k] for k in ('before', 'after', 'events')] for r in b]
    assert result['events'] == online_summary['events']
    assert a[1]['transition']['partial_terminal_control_interval'] is True
    assert file_sha256(h5) == before_hash
    assert result['metadata']['source_trajectory']['h5_sha256'] == before_hash
    contacts = result['metadata']['input_evidence']['contacts']
    assert contacts['events'] == contacts['possible_duplicate_same_step'] == 1
    assert contacts['matches_recorder_cumulative_count'] is True
    execution = [sample.get('_execution') for sample in probe_adapter[0].evaluator.samples]
    assert execution[0] is None
    assert execution[2]['raw_action']['type'] == 'ee_pose'
    assert execution[3]['raw_action']['type'] == 'hold'


def test_h5_only_marks_evidence_scope_and_missing_channels_unknown(tmp_path, probe_adapter):
    h5 = make_episode(tmp_path / 'episode', physics=False)
    result = offline.analyze_episode(h5, tmp_path / 'out', make_report=False)
    assert result['metadata']['input_evidence']['mode'] == 'control_frequency_only'
    assert result['metadata']['input_evidence']['contacts']['available'] is False
    assert result['recording']['physics_samples'] == 3
    assert probe_adapter[0].evaluator.samples[1]['_evidence']['missing_between_samples'] is True


def test_original_episode_output_and_active_source_are_protected(tmp_path, probe_adapter):
    h5 = make_episode(tmp_path / 'episode')
    with pytest.raises(ValueError, match='outside'):
        offline.analyze_episode(h5, tmp_path / 'episode' / 'progress')
    active = make_episode(tmp_path / 'active', complete=False)
    with pytest.raises(RuntimeError, match='closed'):
        offline.analyze_episode(active, tmp_path / 'rejected')
    assert not (tmp_path / 'rejected').exists()


@pytest.mark.parametrize('mode', ['external', 'copy', 'legacy_root'])
def test_index_members_external_copy_and_legacy_root(tmp_path, probe_adapter, mode):
    h5 = make_episode(tmp_path / 'episode')
    index_path = tmp_path / 'index.h5'
    with h5py.File(index_path, 'w') as index, h5py.File(h5, 'r') as original:
        index.attrs.update(complete=True, membership_json=json.dumps([
            dict(episode_id='fixture-only', included=True, source=str(h5), source_h5_sha256=file_sha256(h5)),
            dict(episode_id='excluded-fixture', included=False, exclusion_reason='purpose_mismatch')]))
        if mode == 'external':
            index['member'] = h5py.ExternalLink(str(h5), '/')
        elif mode == 'copy':
            member = index.create_group('member')
            member.attrs.update(dict(original.attrs))
            for name in original:
                original.copy(name, member)
        else:
            index.attrs.update(dict(original.attrs))
            for name in original:
                original.copy(name, index)
    original_hash, index_hash = file_sha256(h5), file_sha256(index_path)
    result = offline.analyze_index(index_path, tmp_path / 'batch', make_report=False)
    assert len(result['episodes']) == len(result['excluded']) == 1
    assert result['excluded'][0]['exclusion_reason'] == 'purpose_mismatch'
    assert file_sha256(h5) == original_hash and file_sha256(index_path) == index_hash


def test_report_keeps_real_video_references_and_causal_unknowns(tmp_path):
    output = writer(tmp_path / 'progress')
    output.physical({'t': 0})
    output.physical({'t': 1})
    output.transition(0, 1)
    output.finalize()
    episode = tmp_path / 'episode'
    episode.mkdir()
    (episode / 'side_camera.mp4').write_bytes(b'original-media-reference-only')
    (episode / 'video_timestamps.json').write_text(json.dumps(dict(nominal_fps=30, frame_simulation_times_s=[0., 1.])))
    report = generate_report(tmp_path / 'progress', episode)
    text = report.read_text()
    assert '../episode/side_camera.mp4' in text
    assert 'frame_simulation_times_s' in text
    assert '<svg' not in text  # SVG is created by embedded self-contained JS.
    assert 'unknown' in text and 'first_control_observation' in text
    assert not (tmp_path / 'progress' / 'media').exists()


def test_prefix_transitions_are_immutable_when_future_samples_are_appended(tmp_path):
    def run(path, future):
        output = writer(path)
        for row in rows()[:3]:
            output.physical(row)
        initial = output.transition(0, 1)
        if future:
            for row in rows()[3:]:
                output.physical(row)
            output.transition(1, 1.4)
        output.finalize()
        return initial, list(iter_json_rows(path / 'progress_v1.jsonl.gz'))[0]

    a, saved_a = run(tmp_path / 'short', False)
    b, saved_b = run(tmp_path / 'long', True)
    assert a == b == saved_a == saved_b


def test_finalization_events_are_sparse_lifecycle_emissions_without_rewriting_intervals(tmp_path):
    class FinalizingProbe(CausalProbe):
        def finalize(self, termination):
            self.events.append(event('attempt_ended', 1.))
            return super().finalize(termination)

    output = ProgressWriter(tmp_path, {}, evaluator=FinalizingProbe())
    output.physical({'t': 0})
    output.physical({'t': 1})
    record = output.transition(0, 1)
    summary = output.finalize()
    assert record['events'] == []
    assert list(iter_json_rows(tmp_path / 'progress_v1.jsonl.gz'))[0]['events'] == []
    sparse = list(iter_json_rows(tmp_path / 'progress_events.jsonl'))
    assert sparse[0]['name'] == 'attempt_ended' and sparse[0]['emission'] == 'finalize'
    assert summary['unassigned_terminal_events'][0]['name'] == 'attempt_ended'
    assert summary['recording']['event_count'] == 1


def test_compare_detects_first_causal_difference_but_ignores_control_provenance(tmp_path):
    for label in ('online', 'offline'):
        output = writer(tmp_path / label)
        output.physical({'t': 0})
        output.physical({'t': 1})
        output.transition(0, 1, transition_metadata={'source': label})
        output.finalize()
    result = offline.compare_progress(tmp_path / 'online', tmp_path / 'offline')
    assert result['equal'] is True and result['transitions_compared'] == 1
    path = tmp_path / 'offline' / 'progress_v1.jsonl.gz'
    records = list(iter_json_rows(path))
    records[0]['after']['current_stage'] = 'changed'
    with gzip.open(path, 'wt') as stream:
        stream.write(json.dumps(records[0]) + '\n')
    result = offline.compare_progress(tmp_path / 'online', tmp_path / 'offline', tmp_path / 'comparison.json')
    assert result['equal'] is False
    assert result['differences'][0]['path'] == 'transition[0].after.current_stage'


def test_report_display_reduction_retains_spikes_unknown_edges_and_events():
    from demos.lab_cuvette_progress_v1.report import PLOT_METRICS, _plot_rows
    data = [dict(t=i / 100., stage='grasp', hold_state='gripper_held', vector=[False] * 9,
        metrics={key: .1 for key in PLOT_METRICS}) for i in range(10000)]
    data[4321]['metrics']['raw_depth_m'] = 99.
    data[5678]['metrics']['raw_depth_m'] = None
    result = _plot_rows(data, [event('boundary', 12.34)])
    assert len(result) <= 2000
    assert data[4321] in result and data[5678] in result
    assert data[1233] in result and data[1234] in result
