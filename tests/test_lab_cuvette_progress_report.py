"""Report acceptance: causal original endpoints, compact facts and local extrema."""
import gzip
import hashlib
import json
from pathlib import Path

import pytest

from demos.lab_cuvette_progress_v1.report import (
    PLOT_METRICS, REPORT_VERSION, STAGES, _pack_rows, _plot_rows, _state_row,
    generate_report,
)


def _payload(path):
    text = Path(path).read_text()
    return json.loads(text.split('<script type="application/json" id="data">', 1)[1].split('</script>', 1)[0])


def _metric(value, reason=None):
    return dict(value=value, available=value is not None, reason=reason)


def _state(t, lateral, *, effective=0., missing=False):
    return dict(t=t, current_stage='align', highest_ever_stage='transport',
        current_stage_continuous=.4, coverage_progress=4/9,
        stage_vector=[True, True, True, True, False, False, False, False, False],
        hold_state='gripper_held', attempt_id=1,
        stages={s: dict(user_status='active', user_status_reason='physical evidence',
                       effective_continuous=.4) for s in STAGES},
        metrics={'target_lateral_error_m': _metric(lateral),
                 'raw_axial_depth_m': _metric(.171),
                 'raw_depth_fraction': _metric(.171/.027),
                 'valid_insertion_progress': _metric(None if missing else effective,
                     'target_evidence_missing' if missing else None)},
        insertion_progress_applicable=None if missing else False,
        insertion_gate_details={'not_applicable_reasons': [] if missing else ['wrong_entrance_region'],
                                'unknown_reasons': ['target_evidence_missing'] if missing else []},
        image='large scene/image objects must not be embedded',
        evidence={'huge': list(range(100))})


def _case(tmp_path, count=7):
    case = tmp_path/'progress'
    case.mkdir()
    with gzip.open(case/'progress_v1.jsonl.gz', 'wt') as stream:
        for i in range(count):
            t = (i+1)/60
            state = _state(t, .000443 if i == 3 else .0001, missing=i == 4)
            stream.write(json.dumps(dict(t_obs=i/60, t_next=t, before=state, after=state))+'\n')
    events = [dict(event_id=1, name='align_confirmed', t=1/60,
                   candidate_start_t=0., confirmed_t=1/60, attempt_id=1, evidence={}),
              dict(event_id=2, name='stable_window_interrupted', t=5/60,
                   evidence={'reason': 'missing_evidence'})]
    (case/'progress_events.jsonl').write_text('\n'.join(map(json.dumps, events))+'\n')
    (case/'progress_config.resolved.json').write_text(json.dumps(
        dict(thresholds=dict(alignment_lateral_m=.0001, stable_duration_s=3.))))
    (case/'progress_summary.json').write_text(json.dumps(dict(
        progress_complete=False, original_result={'task_success':False},
        attempts=[dict(attempt_id=1)], milestones={}, metadata={},
        reset_snapshot=_state(0., .298), first_control_observation=None)))
    return case


def test_all_control_scalar_endpoints_are_packed_exactly_without_full_states(tmp_path):
    case = _case(tmp_path, count=3001)
    html = generate_report(case)
    data = _payload(html)
    assert data['report_version'] == REPORT_VERSION
    from demos.lab_cuvette_progress_v1.config import resolve_config
    assert data['report_version'] == resolve_config({})['visualization_version']
    assert len(data['rows']) == data['display_sampling']['cursor_rows'] == 3001
    assert len(data['plot_indices']) < 3001
    assert data['rows'][3][0] == 4/60
    assert data['rows'][3][11][PLOT_METRICS.index('target_lateral_error_m')] == .000443
    assert data['rows'][4][11][PLOT_METRICS.index('valid_insertion_progress')] is None
    assert 'target_evidence_missing' in data['strings']
    assert data['original_result']['task_success'] is False
    text = html.read_text()
    assert 'large scene/image objects must not be embedded' not in text
    assert 'huge' not in text and 'before' not in data and 'after' not in data
    assert 'window.LabSimProgressReport' in text
    assert "'released','retreated'" in text
    assert '实际样本时间' in text and '请求仿真时间' in text
    assert 'https://cdn' not in text and '<script src=' not in text


def test_old_raw_depth_never_becomes_effective_progress():
    row = _state_row(dict(t=1, metrics={'raw_depth_m': _metric(.171)},
                          stages={'insert': {'continuous':1.}}))
    assert row['metrics']['raw_axial_depth_m'] == .171
    assert row['metrics']['valid_insertion_progress'] is None
    assert row['missing']['valid_insertion_progress'] == 'metric_not_recorded'


def test_compact_reason_table_preserves_unknown_and_gate_semantics():
    rows = [_state_row(_state(i/60, .0002, missing=i == 1)) for i in range(3)]
    packed, strings = _pack_rows(rows)
    assert packed[0][8] is False and packed[1][8] is None
    assert strings[packed[0][15][0][0]] == 'wrong_entrance_region'
    assert strings[packed[1][15][1][0]] == 'target_evidence_missing'
    key = PLOT_METRICS.index('valid_insertion_progress')
    assert packed[1][11][key] is None
    assert any(i == key and strings[j] == 'target_evidence_missing' for i,j in packed[1][12])


def test_plot_reduction_preserves_submillimetre_extrema_and_unknown_breaks():
    rows = [_state_row(_state(i/60, .0001)) for i in range(10000)]
    rows[5555]['metrics']['target_lateral_error_m'] = .000443
    rows[2345]['metrics']['target_lateral_error_m'] = None
    reduced = _plot_rows(rows, [], limit=800)
    assert rows[5555] in reduced
    assert rows[2344] in reduced and rows[2345] in reduced and rows[2346] in reduced
    assert max(r['metrics']['target_lateral_error_m'] or 0 for r in reduced) == .000443


def test_video_copy_is_real_bytes_and_hash_and_no_source_mutation(tmp_path):
    case = _case(tmp_path)
    episode = tmp_path/'episode'
    episode.mkdir()
    source = episode/'side_camera.mp4'
    source.write_bytes(b'actual recorded bytes')
    timestamps = dict(nominal_fps=30, frame_simulation_times_s=[0., .03, .066])
    (episode/'video_timestamps.json').write_text(json.dumps(timestamps))
    data = _payload(generate_report(case, episode, copy_videos=True))
    assert data['timestamps'] == timestamps
    video = data['videos'][0]
    assert video['src'] == 'media/side_camera.mp4'
    assert video['original_sha256'] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert (case/video['src']).read_bytes() == source.read_bytes()
    with pytest.raises(FileExistsError):
        generate_report(case, episode, copy_videos=True)


def test_thresholds_units_and_key_controls_are_present(tmp_path):
    case = _case(tmp_path)
    html = generate_report(case)
    data = _payload(html)
    assert data['thresholds']['alignment_lateral_m'] == .0001
    text = html.read_text()
    for selector in ('zoomContact', 'zoomFull', 'zoomAround', 'zoomApply',
                     'zoomStart', 'zoomEnd', 'readouts', 'gates', 'eventCounts'):
        assert f'id="{selector}"' in text
    for unit in ("unit:'mm'", "unit:'°'", "unit:'N'", "unit:'s'", "unit:'0–1'"):
        assert unit in text
    assert 'Math.min(...all)' in text  # domain is evaluated from all original endpoints
    assert "R.filter(r=>r.t>=range[0]&&r.t<=range[1])" in text
