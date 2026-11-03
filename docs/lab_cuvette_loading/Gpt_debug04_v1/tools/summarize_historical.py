"""Export source-backed historical Progress metrics, without changing labels."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from demos.lab_cuvette_policy_eval_v1.analysis import file_sha256, finite, json_rows, metric


def summarize(progress, episode_metrics, output):
    progress, episode_metrics, output = map(Path, (progress, episode_metrics, output))
    if output.exists():
        raise FileExistsError(output)
    summary = json.loads((progress/'progress_summary.json').read_text())
    config = json.loads((progress/'progress_config.resolved.json').read_text())
    episode = json.loads(episode_metrics.read_text())[0]
    peaks = {stage: dict(maximum_effective_continuous=None, maximum_effective_t=None,
        last_effective_continuous=None, known_control_endpoints=0, unknown_control_endpoints=0,
        maximum_legacy_raw_continuous=None, legacy_raw_semantics='diagnostic only; not effective task progress')
        for stage in summary['stages']}
    times = dict(first_target_operation_region_t=None, last_target_operation_region_t=None,
        first_grasp_quality_false_t=None, first_actual_grasp_loss_observed_t=None)
    for index, row in enumerate(json_rows(progress/'progress_v1.jsonl.gz')):
        for snapshot in ([row.get('before'), row.get('after')] if index == 0 else [row.get('after')]):
            if not snapshot:
                continue
            t = finite(snapshot.get('t'))
            for stage, record in peaks.items():
                state = snapshot.get('stages', {}).get(stage, {})
                value = finite(state.get('effective_continuous'))
                record['last_effective_continuous'] = value
                record['known_control_endpoints' if value is not None else 'unknown_control_endpoints'] += 1
                if value is not None and (record['maximum_effective_continuous'] is None or value > record['maximum_effective_continuous']):
                    record['maximum_effective_continuous'], record['maximum_effective_t'] = value, t
                legacy = finite(state.get('continuous'))
                if legacy is not None:
                    record['maximum_legacy_raw_continuous'] = max(record['maximum_legacy_raw_continuous'] or 0., legacy)
            gates = snapshot.get('insertion_gate_details', {}).get('gates', {})
            if (gates.get('entrance_region') or {}).get('value') is True and (gates.get('current_attempt_route') or {}).get('value') is True:
                if times['first_target_operation_region_t'] is None:
                    times['first_target_operation_region_t'] = t
                times['last_target_operation_region_t'] = t
            if metric(snapshot, 'grasp_quality_current') is False and times['first_grasp_quality_false_t'] is None:
                times['first_grasp_quality_false_t'] = t
            if snapshot.get('actual_grasp_loss_observed') is True and times['first_actual_grasp_loss_observed_t'] is None:
                times['first_actual_grasp_loss_observed_t'] = t
    stage_rows = []
    for stage, milestone in summary['milestones'].items():
        observed = episode['stage_results'].get(stage, {})
        stage_rows.append(dict(stage=stage, ever_confirmed=milestone.get('ever_achieved'),
            first_candidate_t=milestone.get('first_candidate_t'), first_confirmed_t=milestone.get('first_confirmed_t'),
            last_confirmed_t=milestone.get('last_confirmed_t'), confirmation_count=milestone.get('confirmation_count'),
            known_evidence_coverage=observed.get('evidence_coverage'),
            **peaks.get(stage, dict(maximum_effective_continuous=None, maximum_effective_t=None,
                last_effective_continuous=None, known_control_endpoints=0, unknown_control_endpoints=None,
                maximum_legacy_raw_continuous=None, legacy_raw_semantics='physical milestone; no stage continuous field'))))
    value = dict(schema='labsim.Gpt_debug04_v1.historical_quantification.v1',
        episode_id=summary['episode_id'], analysis_scope='one historical source episode; not a new model or simulation trial; no formal evaluation denominator',
        original_result=episode['original_qualifications'], original_termination_reason=episode['termination_reason'],
        source_episode=episode['episode_dir'], source_runtime_commit=episode['actual_execution_commit'],
        progress_analysis_commit=summary['metadata'].get('progress_code_commit'),
        progress_analysis_worktree_clean=summary['metadata'].get('analysis_worktree_clean'),
        progress_analysis_code_files=summary['metadata'].get('analysis_code_files'),
        original_scene_version=episode['scene_version'], original_asset_id=episode['asset_id'],
        simulation_seconds=episode['simulation_seconds'], control_steps=episode['control_steps'],
        physical_samples=summary['recording']['physics_samples'], complete_event_count=summary['recording']['event_count'],
        phase_evidence=stage_rows, continuous=episode['continuous'], observed_control_times=times,
        physical_drift_intervals=episode['drift_intervals'], attempts=episode['attempts'],
        progress_attempt_count=episode['attempt_count'], progress_retry_count=episode['retry_count'],
        original_retry_count=json.loads((Path(episode['episode_dir'])/'result.json').read_text()).get('retry_count'),
        progress_unfinished_requirement=summary['unfinished_requirement'],
        progress_failures=summary['failure_observation'], progress_termination_domain=summary['termination_domain'],
        original_post_retreat_window=episode['post_retreat_window'], original_terminal_window=episode['terminal_window'],
        recording_integrity=summary['output_integrity'], event_replay=episode['event_replay'],
        unavailable_metric_physics_sample_counts=summary['unknown_metric_sample_counts'],
        sources={str(p.resolve()):file_sha256(p) for p in
            (progress/'progress_summary.json', progress/'progress_events.jsonl', progress/'progress_v1.jsonl.gz',
             progress/'progress_config.resolved.json', episode_metrics)},
        original_source_mutated=False, original_labels_mutated=False,
        limits='actual input material and recorded state evidence; effective cooked geometry and real calibration are unverified; stage timing at physics rate, continuous extrema at actual unique control endpoints')
    output.mkdir(parents=True, exist_ok=False)
    (output/'historical_quantification.json').write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n')
    with (output/'stages.csv').open('w', newline='', encoding='utf-8-sig') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(stage_rows[0]))
        writer.writeheader()
        writer.writerows(stage_rows)
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('progress', type=Path)
    parser.add_argument('--episode-metrics', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(argv)
    value = summarize(args.progress, args.episode_metrics, args.output)
    print(json.dumps(dict(episode_id=value['episode_id'], control_steps=value['control_steps'],
        events=value['complete_event_count'], attempts=value['progress_attempt_count'])))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
