"""Real denominator, causality, provenance and read-only analysis behavior."""
import copy
import gzip
import hashlib
import json
from pathlib import Path

import pytest

from demos.lab_cuvette_policy_eval_v1.analysis import (PROGRESS_STAGES, STAGE_ORDER,
    analyze_manifest, analyze_trial, file_sha256, numeric_summary, summarize_group,
    wilson, write_results)


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def snapshot(t, *, applicable=False, unknown=None, progress=0., depth=.171, target_error=.3):
    def m(value):
        return dict(available=value is not None, value=value)
    stages = {name: dict(current_satisfied=None if name == unknown else False)
        for name in PROGRESS_STAGES}
    return dict(t=t, episode_id='episode-1', milestones=stages,
        valid_insertion_progress=progress, insertion_progress_applicable=applicable,
        raw_axial_depth_m=depth,
        insertion_gate_details=dict(gates={
            'entrance_region': dict(value=applicable),
            'current_attempt_route': dict(value=applicable)}),
        metrics={name: m(value) for name, value in dict(
            grasp_approach_position_error_m=.02-t*.001,
            target_lateral_error_m=target_error, target_tilt_rad=.1,
            target_yaw_error_rad=-.01, stable_duration_s=0.,
            gripper_object_clearance_m=.2).items()})


def episode(tmp_path, *, success=False, confirmed=(), unknown=None, applicable=False,
        terminated='ROBOT_ENVIRONMENT_COLLISION', control=2):
    p = tmp_path/'episode'
    p.mkdir()
    event_names = list(confirmed)
    events = [dict(event_id=i+1, name=name+'_confirmed', t=.05,
        candidate_start_t=.04, attempt_id=None, evidence={})
        for i, name in enumerate(event_names)]
    milestones = {name: dict(first_confirmed_t=.05 if name in confirmed else None,
        first_candidate_t=.04 if name in confirmed else None, ever_achieved=name in confirmed,
        current_satisfied=None if name == unknown else name in confirmed)
        for name in PROGRESS_STAGES}
    result = dict(episode_id='episode-1', task_success=success, complete=True,
        record_valid=True, geometry_valid=True, failure_domain='none' if success else 'safety',
        termination_reason=terminated, simulation_seconds=control*.1,
        actual_control_steps=control, observed_events={}, transport_success=False,
        scene_version='Project_release_v1', asset_id='cuvette_xy_1000',
        record_purpose='policy_evaluation')
    dump(p/'result.json', result)
    dump(p/'independent_score.json', copy.deepcopy(result))
    dump(p/'progress_summary.json', dict(episode_id='episode-1',
        progress_evaluator_version='Progress_v1_2.causal_physics.v1',
        output_integrity=dict(complete=True), progress_complete=success,
        milestones=milestones, event_count=len(events), events=events,
        retry_count=0, attempts=[]))
    dump(p/'progress_config.resolved.json', dict(geometry=dict(target_depth_m=.027)))
    dump(p/'reset_check.json', dict(passed=True))
    dump(p/'release_metadata.json', dict(actual_execution_commit='a'*40,
        frozen_scene_sha256='scene-unchanged'))
    dump(p/'episode_0000_complete.json', dict(episode_id='episode-1', complete=True))
    dump(p/'recording_closed_receipt.json', dict(streams={'physics': dict(closed=True)}))
    with (p/'progress_events.jsonl').open('w') as f:
        for event in events:
            f.write(json.dumps(dict(schema='labsim.lab_cuvette_loading.progress.v1.2', **event))+'\n')
    with gzip.open(p/'progress_v1.jsonl.gz', 'wt') as f:
        for i in range(control):
            before = snapshot(i*.1, unknown=unknown, applicable=applicable,
                progress=.5 if applicable else 0., depth=.0135 if applicable else .171)
            after = snapshot((i+1)*.1, unknown=unknown, applicable=applicable,
                progress=.5 if applicable else 0., depth=.0135 if applicable else .171)
            for s in (before, after):
                for name in confirmed:
                    s['milestones'][name]['current_satisfied'] = s['t'] >= .05
            f.write(json.dumps(dict(episode_id='episode-1', t_obs=i*.1,
                t_next=(i+1)*.1, before=before, after=after, events=events if i == 0 else []))+'\n')
    return p


def trial(p, **kw):
    return dict(trial_id='gpt01', group_id='gpt', purpose='formal', status='completed',
        episode_dir=str(p), **kw)


def test_wilson_small_sample_and_zero_denominator():
    assert wilson(0, 0)['rate'] is None
    assert wilson(0, 1)['upper'] == pytest.approx(.7934506856)
    assert wilson(1, 1)['lower'] == pytest.approx(.2065493144)
    assert wilson(0, 10)['upper'] == pytest.approx(.2775327999)
    with pytest.raises(ValueError):
        wilson(2, 1)


def test_outside_target_raw_depth_does_not_count_as_effective_insertion(tmp_path):
    p = episode(tmp_path)
    before = {str(f.relative_to(p)): file_sha256(f) for f in p.rglob('*') if f.is_file()}
    result = analyze_trial(trial(p), tmp_path)
    assert result['analysis_evidence_valid'] is True
    assert result['continuous']['maximum']['valid_insertion_progress']['value'] == 0.
    assert result['continuous']['maximum']['valid_insertion_depth_m']['value'] is None
    assert result['continuous']['target_error_status'] == 'not_reached'
    assert result['continuous']['minimum']['target_lateral_error_m']['value'] is None
    assert result['stage_results']['insert']['reached'] is False
    assert result['task_evaluable'] is True  # actual safety failure is task evidence
    assert result['scan']['endpoint_count'] == 3  # shared boundary is not counted twice
    assert before == {str(f.relative_to(p)): file_sha256(f) for f in p.rglob('*') if f.is_file()}


def test_target_error_is_only_measured_at_applicable_endpoints(tmp_path):
    p = episode(tmp_path, applicable=True)
    result = analyze_trial(trial(p), tmp_path)
    assert result['continuous']['valid_insertion_depth_status'] == 'observed'
    assert result['continuous']['maximum']['valid_insertion_depth_m']['value'] == .0135
    assert result['continuous']['target_operation_region_sample_count'] == 3
    assert result['continuous']['target_error_within_episode']['target_yaw_error_rad']['mean'] == .01


def test_unknown_evidence_not_assigned_failure_and_confirmation_has_time(tmp_path):
    p = episode(tmp_path, confirmed=('approach_grasp',), unknown='insert')
    result = analyze_trial(trial(p), tmp_path)
    assert result['stage_results']['insert']['reached'] is None
    assert result['stage_results']['insert']['status'] == 'unknown'
    assert result['stage_results']['approach_grasp']['first_confirmed_t'] == .05
    assert result['stage_results']['approach_grasp']['candidate_to_confirmation_wait_s'] == pytest.approx(.01)
    group = summarize_group([result], 'gpt')
    assert group['stage_rates']['insert']['unknown'] == 1
    assert group['stage_rates']['insert']['known_denominator'] == 0
    assert group['stage_rates']['insert']['achieved_per_known']['rate'] is None


def test_full_event_stream_includes_finalize_not_in_control_rows(tmp_path):
    p = episode(tmp_path, confirmed=('stable_complete',))
    rows = list()
    with gzip.open(p/'progress_v1.jsonl.gz', 'rt') as f:
        for line in f:
            row = json.loads(line)
            row['events'] = []
            rows.append(row)
    with gzip.open(p/'progress_v1.jsonl.gz', 'wt') as f:
        for row in rows:
            f.write(json.dumps(row)+'\n')
    events = [json.loads(line) for line in (p/'progress_events.jsonl').read_text().splitlines()]
    events[0]['emission'] = 'finalize'
    (p/'progress_events.jsonl').write_text('\n'.join(json.dumps(e) for e in events)+'\n')
    result = analyze_trial(trial(p), tmp_path)
    assert result['stage_results']['stable_complete']['reached'] is True
    assert result['finalize_events_outside_control_records'] == [1]
    assert result['event_ids_outside_control_records'] == [1]


def test_missing_evidence_interval_does_not_prove_nonachievement(tmp_path):
    p = episode(tmp_path)
    summary = json.loads((p/'progress_summary.json').read_text())
    summary['evidence_gap_count'] = 1
    dump(p/'progress_summary.json', summary)
    result = analyze_trial(trial(p), tmp_path)
    assert result['stage_results']['insert']['reached'] is None
    assert result['stage_results']['insert']['episode_evidence_gap_count'] == 1


def test_progress_hash_and_actual_before_after_adjacency_are_verified(tmp_path):
    p = episode(tmp_path)
    rows_path = p/'progress_v1.jsonl.gz'
    summary = json.loads((p/'progress_summary.json').read_text())
    summary['output_integrity']['files'] = {rows_path.name: dict(sha256=file_sha256(rows_path))}
    dump(p/'progress_summary.json', summary)
    with gzip.open(rows_path, 'rt') as f:
        rows = [json.loads(line) for line in f]
    rows[1]['before']['valid_insertion_progress'] = .99
    with gzip.open(rows_path, 'wt') as f:
        for row in rows:
            f.write(json.dumps(row)+'\n')
    result = analyze_trial(trial(p), tmp_path)
    assert 'nonadjacent_progress_endpoint_states' in result['integrity_errors']
    assert 'progress_recorded_sha256_mismatch:progress_v1.jsonl.gz' in result['integrity_errors']


def test_formal_started_denominator_keeps_service_failure_and_not_unstarted(tmp_path):
    p = episode(tmp_path, success=True)
    good = analyze_trial(trial(p), tmp_path)
    service = copy.deepcopy(good)
    service.update(trial_id='gpt02', task_success=False, task_evaluable=False,
        failure_domain='service', exclusion_reason='API_TIMEOUT', termination_reason='API_TIMEOUT')
    planned = analyze_trial(dict(trial_id='gpt03', group_id='gpt', purpose='formal', status='unstarted',
        unstarted_reason='remaining API budget'), tmp_path)
    history = copy.deepcopy(good)
    history.update(trial_id='old', purpose='historical')
    diagnostic = copy.deepcopy(service)
    diagnostic.update(trial_id='probe', purpose='diagnostic')
    group = summarize_group([good, service, planned, history, diagnostic], 'gpt')
    assert (group['planned'], group['started'], group['unstarted'], group['success']) == (3, 2, 1, 1)
    assert group['end_to_end_success']['rate'] == .5
    assert group['evaluable_task_success']['rate'] == 1.
    assert group['exclusions'] == [dict(trial_id='gpt02', task_evaluable=False, reason='API_TIMEOUT')]


def test_budget_censor_does_not_change_valid_task_denominator(tmp_path):
    p = episode(tmp_path, terminated='COST_BUDGET_EXHAUSTED')
    result = analyze_trial(trial(p), tmp_path)
    assert result['censored'] is True
    assert result['task_evaluable'] is True
    group = summarize_group([result], 'gpt')
    assert group['task_evaluable'] == 1
    assert group['censored'] == 1
    assert group['end_to_end_success']['rate'] == 0


def test_external_closure_failure_remains_visible_without_relabeling_task(tmp_path):
    p = episode(tmp_path, success=True)
    closure = tmp_path/'closure.json'
    dump(closure, dict(episode_id='episode-1', passed=False, source_hashes_unchanged=False))
    result = analyze_trial(trial(p, closure_receipt_path=str(closure)), tmp_path)
    assert result['task_success'] is True
    assert result['analysis_evidence_valid'] is False
    assert 'independent_episode_closure_verifier_failed' in result['integrity_errors']
    assert 'independent_episode_source_hashes_changed' in result['integrity_errors']


def test_episode_weighting_and_missing_times_are_not_frame_weighted_or_zero():
    e = dict(group_id='pi05', purpose='formal', planned=True, started=True,
        task_success=False, environment_valid=True, task_evaluable=True,
        continuous=dict(target_error_within_episode=dict(target_lateral_error_m=dict(mean=.001))),
        stage_results={name: {} for name in STAGE_ORDER})
    second = copy.deepcopy(e)
    second['continuous']['target_error_within_episode']['target_lateral_error_m']['mean'] = .003
    group = summarize_group([e, second], 'pi05')
    assert group['episode_equal_weighted']['episode_mean_target_lateral_error_m']['mean'] == .002
    assert group['stage_rates']['insert']['first_confirmed_time_s']['n'] == 0
    assert group['stage_rates']['insert']['first_confirmed_time_s']['mean'] is None
    assert group['episode_equal_weighted']['success_completion_time_s']['n'] == 0


def test_manifest_does_not_duplicate_formal_episode_and_writes_portable_tables(tmp_path):
    p = episode(tmp_path)
    manifest = tmp_path/'trials.json'
    dump(manifest, dict(protocol_id='fixed', trials=[trial(p)]))
    result = analyze_manifest(manifest)
    assert result['manifest_sha256'] == file_sha256(manifest)
    output = tmp_path/'result'
    write_results(result, output)
    assert (output/'summary.json').is_file()
    import csv
    with (output/'episodes.csv').open(encoding='utf-8-sig') as f:
        csv_result = next(csv.DictReader(f))
    assert csv_result['target_error_status'] == 'not_reached'
    assert csv_result['maximum_applicable_insertion_depth_m'] == ''
    assert csv_result['target_xy_mean_m'] == ''
    assert (output/'stage_rates.csv').read_text(encoding='utf-8-sig').splitlines()[0].startswith('group_id,stage,')
    with pytest.raises(FileExistsError):
        write_results(result, output)
    duplicate = trial(p)
    duplicate['trial_id'] = 'gpt02'
    dump(manifest, dict(trials=[trial(p), duplicate]))
    with pytest.raises(ValueError, match='actual episode'):
        analyze_manifest(manifest)


def test_missing_started_record_stays_in_main_denominator(tmp_path):
    result = analyze_trial(trial(tmp_path/'missing', environment_valid=False, task_evaluable=False), tmp_path)
    assert result['task_success'] is None
    assert result['analysis_evidence_valid'] is False
    group = summarize_group([result], 'gpt')
    assert group['started'] == 1
    assert group['end_to_end_success']['rate'] == 0.


@pytest.mark.parametrize('case,episode_dir,expected', [
    ('teacher_online_01/episode_0000', 'teacher_online_01/episode_0000', ('stable_complete', 174, 7539)),
    ('historical_pi05_final_01', '../Project_release_v1/pi05_standard_01_env/episode_0000', (None, 0, 1021)),
    ('historical_held_incomplete_final_01', '../Project_v1_1/gpt_debug_08/episode_0000', ('held_transport_50mm', 9, 3906)),
])
def test_actual_historical_progress12_read_only_protocol(case, episode_dir, expected):
    """Real source fixtures are optional; they are method checks, never formal trials."""
    root = Path(__file__).resolve().parents[1]
    base = root/'outputs/lab_cuvette_loading/Progress_v1_2'
    if not (base/case/'progress_summary.json').exists():
        pytest.skip('local immutable historical experiment is not shipped in the code repository')
    p = (base/episode_dir).resolve()
    original_hash = file_sha256(p/'result.json')
    progress_hash = file_sha256(base/case/'progress_summary.json')
    row = trial(p, progress_dir=str(base/case))
    row['purpose'] = 'historical'
    result = analyze_trial(row, root)
    assert result['analysis_evidence_valid'], result['integrity_errors']
    assert result['farthest_stage'] == expected[0]
    assert result['event_count'] == expected[1]
    assert result['scan']['transition_count'] == expected[2]
    assert file_sha256(p/'result.json') == original_hash
    assert file_sha256(base/case/'progress_summary.json') == progress_hash
    assert summarize_group([result], 'gpt')['started'] == 0
    if 'pi05' in case:
        assert result['continuous']['maximum']['valid_insertion_progress']['value'] == 0.
        assert result['continuous']['maximum']['valid_insertion_depth_m']['value'] is None
        assert result['continuous']['target_error_status'] == 'not_reached'
    if 'held' in case:
        assert result['stage_results']['held_transport_50mm']['reached'] is True
        assert result['stage_results']['transport']['reached'] is False
        assert result['post_retreat_window']['status'] == 'unavailable'


def test_nonfinite_values_are_unknown_not_json_nan():
    assert numeric_summary([float('nan'), float('inf'), None, 3])['n'] == 1
    assert numeric_summary([])['mean'] is None


def test_plots_require_actual_formal_members_and_preserve_source(tmp_path):
    pytest.importorskip('matplotlib')
    from demos.lab_cuvette_policy_eval_v1.plots import FIGURE_NAMES, plot_results
    p = episode(tmp_path)
    manifest = tmp_path/'trials.json'
    dump(manifest, dict(protocol_id='test-fixture-only', trials=[trial(p)]))
    result = analyze_manifest(manifest)
    source = tmp_path/'analysis.json'
    dump(source, result)
    original_hash = file_sha256(source)
    receipt = plot_results(source, manifest, tmp_path/'figures')
    assert len(receipt['figures']) == 6
    assert {f['path'] for f in receipt['figures']} == set(FIGURE_NAMES)
    for f in receipt['figures']:
        path = tmp_path/'figures'/f['path']
        assert path.read_bytes().startswith(b'\x89PNG\r\n\x1a\n')
        assert path.stat().st_size > 5000
        assert file_sha256(path) == f['sha256']
    assert receipt['representatives'][0]['trial_id'] == 'gpt01'
    assert original_hash == file_sha256(source)
    with pytest.raises(FileExistsError):
        plot_results(source, manifest, tmp_path/'figures')
    result['episodes'][0]['purpose'] = 'diagnostic'
    dump(source, result)
    with pytest.raises(ValueError, match='No started formal'):
        plot_results(source, manifest, tmp_path/'nonexistent')
    assert not (tmp_path/'nonexistent').exists()


def test_representative_selection_keeps_both_groups_and_is_not_best_case_only():
    from demos.lab_cuvette_policy_eval_v1.plots import select_representatives
    cases = [dict(trial_id=f'{g}{i}', group_id=g, purpose='formal', started=True,
        farthest_stage_rank=i, task_success=i == 5) for g in ('gpt', 'pi05') for i in range(6)]
    representatives, rule = select_representatives(cases)
    assert len(representatives) <= 4
    assert {e['group_id'] for e in representatives} == {'gpt', 'pi05'}
    assert [e['trial_id'] for e in representatives[:2]] == ['gpt2', 'pi052']
    assert 'median' in rule
