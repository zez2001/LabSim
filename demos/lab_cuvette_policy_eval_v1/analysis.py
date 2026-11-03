"""Recompute policy evaluation tables from immutable original episode evidence.

Example: python -m demos.lab_cuvette_policy_eval_v1.analysis trials.json --output NEW_DIR

Only explicitly formal trials contribute to formal group statistics.  Started
trials with service or recording failures remain in the end-to-end denominator.
No function changes source H5 files, scorer labels, Progress, or input manifests.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
from pathlib import Path
import statistics
import subprocess
import sys
from collections import Counter

from . import SCHEMA


STAGE_ORDER = ('approach_grasp', 'grasp', 'extract', 'held_transport_50mm',
    'transport', 'align', 'insert', 'support_transfer', 'released', 'retreated',
    'stable_complete')
PROGRESS_STAGES = tuple(s for s in STAGE_ORDER if s != 'held_transport_50mm')
PURPOSES = {'formal', 'diagnostic', 'historical'}
RESOURCE_FIELDS = ('model_calls', 'returned_actions', 'executed_actions',
    'inference_seconds', 'service_wait_seconds', 'retry_count', 'wall_seconds',
    'input_tokens', 'output_tokens', 'cost_usd', 'action_rejections',
    'action_clipped', 'action_execution_errors')


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def finite(value):
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else None


def tri(value):
    return value if isinstance(value, bool) else None


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def json_rows(path):
    opener = gzip.open if str(path).endswith('.gz') else open
    with opener(path, 'rt', encoding='utf-8') as stream:
        for line in stream:
            if line.strip():
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ValueError('Expected an object in ' + str(path))
                yield value


def metric(snapshot, name):
    value = (snapshot.get('metrics') or {}).get(name)
    return value.get('value') if isinstance(value, dict) and value.get('available') is True else None


def numeric_summary(values):
    """Each member is already one scalar per episode, never a pooled frame."""
    values = [x for value in values if (x := finite(value)) is not None]
    if not values:
        return dict(n=0, mean=None, median=None, minimum=None, maximum=None, population_sd=None)
    return dict(n=len(values), mean=statistics.fmean(values), median=statistics.median(values),
        minimum=min(values), maximum=max(values), population_sd=statistics.pstdev(values))


def wilson(successes, total, z=1.959963984540054):
    """Two-sided 95% Wilson score interval; no interval for a zero denominator."""
    if not isinstance(successes, int) or not isinstance(total, int) or not 0 <= successes <= total:
        raise ValueError('Wilson requires integer 0 <= successes <= total')
    if total == 0:
        return dict(successes=successes, denominator=0, rate=None, lower=None, upper=None,
            confidence=0.95, method='Wilson score')
    p, z2 = successes / total, z * z
    denominator = 1 + z2 / total
    centre = (p + z2 / (2 * total)) / denominator
    radius = z * math.sqrt(p * (1 - p) / total + z2 / (4 * total * total)) / denominator
    return dict(successes=successes, denominator=total, rate=p,
        lower=max(0., centre-radius), upper=min(1., centre+radius),
        confidence=0.95, method='Wilson score')


def _path(base, value):
    if value is None:
        return None
    p = Path(value)
    return p.resolve() if p.is_absolute() else (base / p).resolve()


def _first_number(*values):
    return next((v for value in values if (v := finite(value)) is not None), None)


def _update_extreme(target, name, value, t, *, minimum=False):
    value = finite(value)
    if value is not None and (target[name]['value'] is None or
            (value < target[name]['value'] if minimum else value > target[name]['value'])):
        target[name].update(value=value, t=t)


def _empty_extreme(unit):
    return dict(value=None, t=None, unit=unit)


def _scan_progress(path, summary, events):
    counts = {name: Counter() for name in PROGRESS_STAGES}
    maximum = dict(valid_insertion_progress=_empty_extreme('1'),
        valid_insertion_depth_m=_empty_extreme('m'),
        stable_duration_s=_empty_extreme('s'),
        post_release_stable_duration_s=_empty_extreme('s'),
        post_release_clearance_m=_empty_extreme('m'))
    minimum = dict(grasp_approach_position_error_m=_empty_extreme('m'),
        target_lateral_error_m=_empty_extreme('m'), target_tilt_rad=_empty_extreme('rad'),
        target_yaw_error_rad=_empty_extreme('rad'), post_release_clearance_m=_empty_extreme('m'))
    post_release_clearance_final = _empty_extreme('m')
    region_values = {name: [] for name in ('target_lateral_error_m', 'target_tilt_rad', 'target_yaw_error_rad')}
    milestones = summary.get('milestones') or summary.get('stages') or {}
    release_t = finite((milestones.get('released') or {}).get('first_confirmed_t'))
    endpoint_count = transition_count = region_count = applicable_count = post_release_count = 0
    last_t = last_next = None
    previous_after = None
    errors, transition_event_ids, identities = [], set(), set()
    first_t = None

    def snapshot(s):
        nonlocal endpoint_count, region_count, applicable_count, post_release_count, last_t, first_t
        if not isinstance(s, dict):
            for name in counts:
                counts[name]['unknown'] += 1
            return
        t = finite(s.get('t'))
        if t is None:
            errors.append('nonfinite_or_missing_endpoint_time')
        elif last_t is not None and t <= last_t:
            errors.append('nonincreasing_unique_endpoint_time')
        last_t = t
        if first_t is None:
            first_t = t
        endpoint_count += 1
        if s.get('episode_id'):
            identities.add(s['episode_id'])
        for name in counts:
            fact = (s.get('milestones', {}).get(name) or s.get('stages', {}).get(name) or {}).get('current_satisfied')
            counts[name]['true' if fact is True else 'false' if fact is False else 'unknown'] += 1
        _update_extreme(minimum, 'grasp_approach_position_error_m', metric(s, 'grasp_approach_position_error_m'), t, minimum=True)
        _update_extreme(maximum, 'valid_insertion_progress', s.get('valid_insertion_progress', metric(s, 'valid_insertion_progress')), t)
        applicable = s.get('insertion_progress_applicable', metric(s, 'insertion_progress_applicable')) is True
        if applicable:
            applicable_count += 1
            # Use the actual raw depth at a causally applicable endpoint.  A
            # 171 mm raw projection outside the target is deliberately absent.
            _update_extreme(maximum, 'valid_insertion_depth_m', s.get('raw_axial_depth_m', metric(s, 'raw_axial_depth_m')), t)
        gates = (s.get('insertion_gate_details') or {}).get('gates') or {}
        in_region = (gates.get('entrance_region') or {}).get('value') is True and (gates.get('current_attempt_route') or {}).get('value') is True
        if in_region:
            region_count += 1
            for name in region_values:
                value = finite(metric(s, name))
                if value is not None:
                    value = abs(value)
                    region_values[name].append(value)
                    _update_extreme(minimum, name, value, t, minimum=True)
        if release_t is not None and t is not None and t >= release_t:
            post_release_count += 1
            clearance = metric(s, 'gripper_object_clearance_m')
            _update_extreme(maximum, 'post_release_clearance_m', clearance, t)
            _update_extreme(minimum, 'post_release_clearance_m', clearance, t, minimum=True)
            post_release_clearance_final.update(value=finite(clearance), t=t)
            # The core's pre-release zero remains unchanged in raw evidence.
            # Evaluation statistics apply only after actual physical release;
            # never reaching release is N/A, not an observed zero-second hold.
            _update_extreme(maximum, 'post_release_stable_duration_s', metric(s, 'stable_duration_s'), t)
            _update_extreme(maximum, 'stable_duration_s', metric(s, 'stable_duration_s'), t)

    if path and path.exists():
        for row in json_rows(path):
            if row.get('episode_id'):
                identities.add(row['episode_id'])
            a, b = finite(row.get('t_obs')), finite(row.get('t_next'))
            if a is None or b is None or b < a:
                errors.append('invalid_transition_time')
            if last_next is not None and (a is None or abs(a-last_next) > 1e-8):
                errors.append('nonadjacent_transition_times')
            if transition_count and previous_after != row.get('before'):
                errors.append('nonadjacent_progress_endpoint_states')
            if transition_count == 0:
                snapshot(row.get('before'))
            snapshot(row.get('after'))
            for event in row.get('events') or []:
                if isinstance(event.get('event_id'), int):
                    transition_event_ids.add(event['event_id'])
            last_next = b
            previous_after = row.get('after')
            transition_count += 1
    event_ids = {event['event_id'] for event in events if isinstance(event.get('event_id'), int)}
    return dict(endpoint_count=endpoint_count, transition_count=transition_count,
        first_observation_t=first_t, last_observation_t=last_t, evidence_counts={k: dict(v) for k, v in counts.items()},
        maximum=maximum, minimum=minimum, target_operation_region_sample_count=region_count,
        post_release_clearance_final=post_release_clearance_final,
        post_release_sample_count=post_release_count,
        target_operation_region_definition='entrance_region AND current_attempt_route gates are both true at this actual control endpoint',
        target_error_within_episode={k: numeric_summary(v) for k, v in region_values.items()},
        insertion_applicable_sample_count=applicable_count,
        identities=sorted(identities), integrity_errors=sorted(set(errors)),
        event_ids_in_control_records=len(transition_event_ids),
        event_ids_outside_control_records=sorted(event_ids-transition_event_ids),
        events_missing_from_full_stream=sorted(transition_event_ids-event_ids),
        cadence='first before endpoint followed by every after endpoint; no duplicate transition boundary weighting')


def _stage_results(summary, events, scan, original):
    stages = {}
    facts = summary.get('milestones') or summary.get('stages') or {}
    stream_complete = (summary.get('output_integrity') or {}).get('complete') is True
    for name in PROGRESS_STAGES:
        source = facts.get(name) or {}
        confirmed = [e for e in events if e.get('name') == name+'_confirmed' and finite(e.get('t')) is not None]
        first = min((float(e['t']) for e in confirmed), default=None)
        candidate = finite(source.get('first_candidate_t'))
        covered = scan['evidence_counts'][name]
        n = sum(covered.values())
        known = covered.get('true', 0) + covered.get('false', 0)
        # Achievement comes from the whole append-only stream, including
        # finalize events.  A missing stream cannot prove non-achievement.
        if first is not None:
            reached, status = True, 'achieved'
        elif stream_complete and not summary.get('evidence_gap_count') and n > 0 and known == n:
            reached, status = False, 'not_reached'
        else:
            reached, status = None, 'unknown'
        stages[name] = dict(reached=reached, status=status, first_confirmed_t=first,
            first_candidate_t=candidate,
            candidate_to_confirmation_wait_s=first-candidate if first is not None and candidate is not None else None,
            confirmation_count=len(confirmed), summary_first_confirmed_t=finite(source.get('first_confirmed_t')),
            source='complete progress_events.jsonl confirmations; coverage from original Progress endpoints',
            evidence_known_samples=known, evidence_total_samples=n,
            evidence_coverage=known/n if n else None,
            unknown_samples=covered.get('unknown', 0),
            episode_evidence_gap_count=summary.get('evidence_gap_count'))
    # Held transport over 50 mm is an independent scorer event, not transport
    # (which confirms arrival at the fixed pre-insertion region).
    event = (original.get('observed_events') or {}).get('held_transport_observed')
    t = finite(event.get('t')) if isinstance(event, dict) else None
    known = isinstance(original.get('transport_success'), bool)
    stages['held_transport_50mm'] = dict(reached=True if t is not None else False if known else None,
        status='achieved' if t is not None else 'not_reached' if known else 'unknown',
        first_confirmed_t=t, first_candidate_t=None, candidate_to_confirmation_wait_s=None,
        source='original independent scorer observed_events.held_transport_observed',
        evidence_coverage=1. if known else None, evidence_known_samples=None,
        evidence_total_samples=None, unknown_samples=None)
    return {name: stages[name] for name in STAGE_ORDER}


def analyze_trial(trial, base):
    """Analyze one immutable trial; malformed/missing evidence stays explicit."""
    base = Path(base)
    purpose = trial.get('purpose')
    if purpose not in PURPOSES:
        raise ValueError('Unknown purpose: ' + str(purpose))
    status = trial.get('status', 'planned')
    started = status in {'started', 'completed', 'interrupted', 'failed'} or trial.get('started') is True
    output = dict(schema=SCHEMA, trial_id=trial['trial_id'], group_id=trial['group_id'],
        purpose=purpose, planned=True, started=started, trial_status=status,
        paired_trial_id=trial.get('paired_trial_id'), unstarted_reason=trial.get('unstarted_reason'),
        environment_valid=tri(trial.get('environment_valid')), task_evaluable=tri(trial.get('task_evaluable')),
        exclusion_reason=trial.get('exclusion_reason'), censored=tri(trial.get('censored')),
        censor_reason=trial.get('censor_reason'), task_success=None, record_complete=None,
        record_valid=None, episode_id=None, stage_results={}, source_files=[],
        integrity_errors=[], policy_identity=trial.get('policy_identity'),
        resource={key: None for key in RESOURCE_FIELDS})
    if not started:
        return output
    episode = _path(base, trial.get('episode_dir'))
    progress = _path(base, trial.get('progress_dir')) or episode
    if episode is None:
        output['integrity_errors'].append('started_trial_missing_episode_directory')
        return output
    output['episode_dir'], output['progress_dir'] = str(episode), str(progress)
    sources = output['source_files']

    def load(path, *, required=False):
        if path and path.exists():
            sources.append(dict(path=str(path.resolve()), size_bytes=path.stat().st_size, sha256=file_sha256(path)))
            try:
                return read_json(path)
            except (ValueError, OSError) as exc:
                output['integrity_errors'].append('unreadable_json:'+path.name+':'+str(exc))
        elif required:
            output['integrity_errors'].append('missing:'+str(path))
        return {}

    original = load(episode/'result.json', required=True)
    independent = load(episode/'independent_score.json')
    summary = load(progress/'progress_summary.json', required=True)
    resolved = load(progress/'progress_config.resolved.json')
    metadata = load(episode/'release_metadata.json')
    reset = load(episode/'reset_check.json')
    closed = load(episode/'recording_closed_receipt.json')
    costs = load(_path(base, trial.get('cost_summary_path')))
    closure = load(_path(base, trial.get('closure_receipt_path')))
    marker_paths = sorted(episode.glob('episode_*_complete.json'))
    markers = [load(p) for p in marker_paths]
    # Hash H5 bytes without opening a writer or interpreting/changing labels.
    # Video decode, H5 structural checks, and native process exit are performed
    # by the independent per-run closure verifier, whose receipt is bound here.
    h5_paths = sorted((episode/'dataset').glob('*.h5'))
    for p in h5_paths:
        sources.append(dict(path=str(p.resolve()), size_bytes=p.stat().st_size,
            sha256=file_sha256(p), kind='original_h5_read_only'))
    events_path, rows_path = progress/'progress_events.jsonl', progress/'progress_v1.jsonl.gz'
    events = []
    if events_path.exists():
        sources.append(dict(path=str(events_path.resolve()), size_bytes=events_path.stat().st_size, sha256=file_sha256(events_path)))
        try:
            events = list(json_rows(events_path))
        except (ValueError, OSError) as exc:
            output['integrity_errors'].append('unreadable_event_stream:'+str(exc))
    else:
        output['integrity_errors'].append('missing:progress_events.jsonl')
    if rows_path.exists():
        sources.append(dict(path=str(rows_path.resolve()), size_bytes=rows_path.stat().st_size, sha256=file_sha256(rows_path)))
    else:
        output['integrity_errors'].append('missing:progress_v1.jsonl.gz')
    try:
        scan = _scan_progress(rows_path, summary, events)
    except (ValueError, OSError, EOFError) as exc:
        output['integrity_errors'].append('unreadable_control_sidecar:'+str(exc))
        scan = _scan_progress(None, summary, events)
    output['integrity_errors'] += scan['integrity_errors']
    identities = set(scan['identities'])
    for document in (original, independent, summary, closure, *markers):
        if document.get('episode_id'):
            identities.add(document['episode_id'])
    if len(identities) != 1:
        output['integrity_errors'].append('episode_identity_missing_or_mismatch')
    output['episode_id'] = original.get('episode_id') or summary.get('episode_id')
    output['episode_identities'] = sorted(identities)
    output['task_success'] = tri(original.get('task_success'))
    output['record_valid'] = tri(original.get('record_valid'))
    output['record_complete'] = tri(original.get('complete'))
    if output['environment_valid'] is None:
        if reset.get('passed') is False or original.get('geometry_valid') is False:
            output['environment_valid'] = False
        elif reset.get('passed') is True and original.get('geometry_valid') is True:
            output['environment_valid'] = True
        output['environment_valid_source'] = 'original reset_check.passed and result.geometry_valid; unknown without both'
    else:
        output['environment_valid_source'] = 'explicit trial manifest assertion; see evidence references'
    if output['task_evaluable'] is None and output['environment_valid'] is True and original.get('record_valid') is True:
        domain = str(original.get('failure_domain') or '').lower()
        output['task_evaluable'] = domain not in {'service', 'environment', 'recording', 'interface', 'system'}
        output['task_evaluable_source'] = 'original validity and failure domain; task safety failures are retained'
    elif output['task_evaluable'] is not None:
        output['task_evaluable_source'] = 'explicit trial manifest assertion; see exclusion reason and evidence'
    termination = original.get('termination_reason') or (summary.get('termination') or {}).get('termination_reason')
    output.update(termination_reason=termination, failure_type=original.get('failure_type'),
        failure_domain=original.get('failure_domain'), record_purpose=original.get('record_purpose'),
        simulation_seconds=_first_number(original.get('simulation_seconds'), original.get('simulation_duration_s'), scan['last_observation_t']),
        control_steps=_first_number(original.get('actual_control_steps'), scan['transition_count']),
        progress_complete=tri(summary.get('progress_complete')),
        progress_record_complete=tri((summary.get('output_integrity') or {}).get('complete')),
        progress_evaluator_version=summary.get('progress_evaluator_version'),
        progress_config_sha256=summary.get('config_hash'),
        scene_version=original.get('scene_version') or metadata.get('scene_version'),
        asset_id=original.get('asset_id') or metadata.get('asset_id'),
        frozen_scene_sha256=metadata.get('frozen_scene_sha256'),
        actual_execution_commit=metadata.get('actual_execution_commit') or metadata.get('code_commit'),
        environment_seed=original.get('seed', trial.get('environment_seed')),
        policy_seed=trial.get('policy_seed'), policy_seed_supported=trial.get('policy_seed_supported'),
        original_qualifications={k: original.get(k) for k in ('task_success', 'record_valid', 'success_bc_eligible', 'trajectory_analysis_eligible', 'physics_trustworthy', 'physics_quality_flags')})
    if output['censored'] is None:
        reason_upper = str(termination or '').upper()
        output['censored'] = any(word in reason_upper for word in ('BUDGET', 'TIMEOUT', 'TIME_LIMIT', 'CALL_LIMIT', 'MAX_STEPS'))
        output['censor_reason'] = termination if output['censored'] else None
    if summary.get('progress_evaluator_version') != 'Progress_v1_2.causal_physics.v1':
        output['integrity_errors'].append('progress_version_is_not_v1_2')
    if purpose == 'formal' and original.get('record_purpose') != 'policy_evaluation':
        output['integrity_errors'].append('formal_trial_record_purpose_is_not_policy_evaluation')
    if summary.get('event_count') != len(events):
        output['integrity_errors'].append('event_count_mismatch')
    known_hashes = {s['path']: s['sha256'] for s in sources}
    for name, recorded in ((summary.get('output_integrity') or {}).get('files') or {}).items():
        actual_path = (progress/name).resolve()
        if not actual_path.is_relative_to(progress.resolve()):
            output['integrity_errors'].append('unsafe_progress_integrity_path:'+name)
            continue
        if not actual_path.exists():
            output['integrity_errors'].append('missing_progress_integrity_file:'+name)
        elif recorded.get('sha256') and (known_hashes.get(str(actual_path)) or file_sha256(actual_path)) != recorded['sha256']:
            output['integrity_errors'].append('progress_recorded_sha256_mismatch:'+name)
    if summary.get('events') is not None:
        # The writer adds wrapper schema and emission='finalize' when flushing
        # post-control lifecycle events.  Those transport annotations are not
        # part of the evaluator's original embedded event object.
        ignore = {'schema', 'emission'}
        embedded = [{k: v for k, v in event.items() if k not in ignore} for event in events]
        if embedded != [{k: v for k, v in event.items() if k not in ignore} for event in summary['events']]:
            output['integrity_errors'].append('summary_event_stream_mismatch')
    if scan['events_missing_from_full_stream']:
        output['integrity_errors'].append('control_events_missing_from_append_only_stream')
    if original.get('actual_control_steps') is not None and int(original['actual_control_steps']) != scan['transition_count']:
        output['integrity_errors'].append('control_count_mismatch')
    try:
        from demos.lab_cuvette_progress_v1.replay import verify_replay
        replay = verify_replay(events, summary)
        output['event_replay'] = {k: v for k, v in replay.items() if k != 'attempts'}
        if not replay['passed']:
            output['integrity_errors'].append('attempt_event_replay_mismatch')
    except (ValueError, KeyError) as exc:
        output['integrity_errors'].append('invalid_event_lifecycle:'+str(exc))
    output['stage_results'] = _stage_results(summary, events, scan, original)
    for name in PROGRESS_STAGES:
        stage = output['stage_results'][name]
        if stage['first_confirmed_t'] != stage['summary_first_confirmed_t']:
            output['integrity_errors'].append('stage_event_summary_timing_mismatch:'+name)
    achieved = [name for name in STAGE_ORDER if output['stage_results'][name]['reached'] is True]
    output['farthest_stage'] = achieved[-1] if achieved else None
    output['farthest_stage_rank'] = max((STAGE_ORDER.index(name)+1 for name in achieved), default=0)
    output['continuous'] = dict(minimum=scan['minimum'], maximum=scan['maximum'],
        post_release_clearance_final=scan['post_release_clearance_final'],
        post_release_sample_count=scan['post_release_sample_count'],
        post_release_stable_duration_status='observed_after_release' if scan['post_release_sample_count'] else 'not_applicable',
        post_release_stable_duration_definition='maximum original stable_duration_s among actual control endpoints at or after the first physically confirmed released event; stable_duration_s is a compatibility alias of post_release_stable_duration_s; raw pre-release zeros are excluded',
        target_operation_region_sample_count=scan['target_operation_region_sample_count'],
        target_operation_region_definition=scan['target_operation_region_definition'],
        target_error_within_episode=scan['target_error_within_episode'],
        target_error_status='observed' if scan['target_operation_region_sample_count'] else 'not_reached',
        valid_insertion_depth_status='observed' if scan['insertion_applicable_sample_count'] else 'not_applicable',
        insertion_applicable_sample_count=scan['insertion_applicable_sample_count'],
        sampling_scope='actual control endpoints; attempt drift below uses original physical-rate statistics')
    output['drift_intervals'] = {interval: [dict(attempt_id=a.get('attempt_id'), **a['relative_motion_statistics'][interval])
        for a in summary.get('attempts', []) if interval in (a.get('relative_motion_statistics') or {})]
        for interval in ('operation', 'before_first_target_support', 'support_transfer')}
    output['attempt_count'], output['retry_count'] = len(summary.get('attempts', [])), summary.get('retry_count')
    output['attempts'] = summary.get('attempts', [])
    output['event_count'] = len(events)
    output['event_ids_outside_control_records'] = scan['event_ids_outside_control_records']
    output['finalize_event_ids'] = [e['event_id'] for e in events if e.get('emission') == 'finalize']
    output['finalize_events_outside_control_records'] = sorted(set(output['finalize_event_ids']) & set(scan['event_ids_outside_control_records']))
    output['post_retreat_window'] = original.get('post_retreat_window')
    output['terminal_window'] = original.get('terminal_window')
    output['scan'] = {k: scan[k] for k in ('endpoint_count', 'transition_count', 'first_observation_t', 'last_observation_t', 'cadence')}
    output['resource'].update({key: finite(costs.get(key)) for key in RESOURCE_FIELDS})
    output['resource']['wall_seconds'] = _first_number(costs.get('wall_seconds'), original.get('wall_seconds'))
    output['resource']['latency_per_call_s'] = numeric_summary(costs.get('latencies_s') or [])
    output['resource']['action_execution_duration_s'] = numeric_summary(costs.get('action_execution_durations_s') or [])
    output['resource']['measurement_scope'] = costs.get('measurement_scope', 'unknown for fields without a supplied cost summary')
    output['source_closure_receipt'] = closure
    if closure.get('passed') is False:
        output['integrity_errors'].append('independent_episode_closure_verifier_failed')
    if closure.get('source_hashes_unchanged') is False:
        output['integrity_errors'].append('independent_episode_source_hashes_changed')
    output['h5_files'] = [s for s in sources if s.get('kind') == 'original_h5_read_only']
    output['completion_markers'] = markers
    output['recording_stream_close'] = {k: v.get('closed') for k, v in (closed.get('streams') or {}).items()}
    if any(value is not True for value in output['recording_stream_close'].values()):
        output['integrity_errors'].append('recording_stream_not_closed')
    output['resolved_target_depth_m'] = (resolved.get('geometry') or {}).get('target_depth_m')
    output['integrity_errors'] = sorted(set(output['integrity_errors']))
    output['analysis_evidence_valid'] = not output['integrity_errors']
    return output


def summarize_group(episodes, group_id):
    formal = [e for e in episodes if e['group_id'] == group_id and e['purpose'] == 'formal']
    started = [e for e in formal if e['started']]
    valid = [e for e in started if e.get('task_evaluable') is True]
    success = sum(e.get('task_success') is True for e in started)
    rates = {}
    for name in STAGE_ORDER:
        states = [(e.get('stage_results') or {}).get(name, {}) for e in started]
        achieved = sum(s.get('reached') is True for s in states)
        known = sum(isinstance(s.get('reached'), bool) for s in states)
        coverage = [s.get('evidence_coverage') for s in states]
        rates[name] = dict(achieved=achieved, started_denominator=len(started),
            known_denominator=known, unknown=len(started)-known,
            achieved_per_started=wilson(achieved, len(started)),
            achieved_per_known=wilson(achieved, known),
            mean_episode_evidence_coverage=numeric_summary(coverage),
            first_confirmed_time_s=numeric_summary(s.get('first_confirmed_t') for s in states),
            candidate_to_confirmation_wait_s=numeric_summary(s.get('candidate_to_confirmation_wait_s') for s in states))
    scalar = {
        'simulation_seconds': [e.get('simulation_seconds') for e in started],
        'control_steps': [e.get('control_steps') for e in started],
        'success_completion_time_s': [e.get('simulation_seconds') for e in started if e.get('task_success') is True],
        'attempt_count': [e.get('attempt_count') for e in started],
        'retry_count': [e.get('retry_count') for e in started],
    }
    for name in ('grasp_approach_position_error_m', 'target_lateral_error_m', 'target_tilt_rad', 'target_yaw_error_rad'):
        scalar['episode_minimum_'+name] = [(e.get('continuous') or {}).get('minimum', {}).get(name, {}).get('value') for e in started]
    for name in ('valid_insertion_progress', 'valid_insertion_depth_m', 'post_release_clearance_m', 'stable_duration_s', 'post_release_stable_duration_s'):
        scalar['episode_maximum_'+name] = [(e.get('continuous') or {}).get('maximum', {}).get(name, {}).get('value') for e in started]
    for name in RESOURCE_FIELDS:
        scalar[name] = [e.get('resource', {}).get(name) for e in started]
    scalar['latency_episode_mean_s'] = [e.get('resource', {}).get('latency_per_call_s', {}).get('mean') for e in started]
    for name in ('target_lateral_error_m', 'target_tilt_rad', 'target_yaw_error_rad'):
        scalar['episode_mean_'+name] = [(e.get('continuous') or {}).get('target_error_within_episode', {}).get(name, {}).get('mean') for e in started]
    for interval in ('operation', 'before_first_target_support', 'support_transfer'):
        for name in ('maximum_relative_translation_m', 'maximum_relative_rotation_rad'):
            scalar['episode_maximum_drift_'+interval+'_'+name] = [max((v for a in e.get('drift_intervals', {}).get(interval, [])
                if (v := finite(a.get(name))) is not None), default=None) for e in started]
    return dict(schema=SCHEMA, group_id=group_id, planned=len(formal), started=len(started),
        unstarted=len(formal)-len(started),
        environment_valid=sum(e.get('environment_valid') is True for e in started),
        environment_invalid=sum(e.get('environment_valid') is False for e in started),
        environment_unknown=sum(e.get('environment_valid') is None for e in started),
        record_complete=sum(e.get('record_complete') is True for e in started),
        analysis_evidence_valid=sum(e.get('analysis_evidence_valid') is True for e in started),
        task_evaluable=len(valid), task_evaluable_unknown=sum(e.get('task_evaluable') is None for e in started),
        success=success, end_to_end_success=wilson(success, len(started)),
        evaluable_task_success=wilson(sum(e.get('task_success') is True for e in valid), len(valid)),
        censored=sum(e.get('censored') is True for e in started),
        termination_counts=dict(Counter(e.get('termination_reason') or 'unknown' for e in started)),
        failure_domain_counts=dict(Counter(e.get('failure_domain') or 'unknown' for e in started)),
        unstarted_reason_counts=dict(Counter(e.get('unstarted_reason') or 'unspecified' for e in formal if not e['started'])),
        exclusions=[dict(trial_id=e['trial_id'], task_evaluable=e.get('task_evaluable'), reason=e.get('exclusion_reason') or e.get('failure_domain') or 'unknown') for e in started if e.get('task_evaluable') is not True],
        stage_rates=rates, episode_equal_weighted={k: numeric_summary(v) for k, v in scalar.items()},
        resource_totals={k: dict(sum=sum(v for e in started if (v := finite(e.get('resource', {}).get(k))) is not None) if any(finite(e.get('resource', {}).get(k)) is not None for e in started) else None,
            known_episode_count=sum(finite(e.get('resource', {}).get(k)) is not None for e in started), started_episode_count=len(started)) for k in RESOURCE_FIELDS},
        scope='fixed standard scene repetitions; conditional performance of frozen end-to-end schemes, not general scene success probability',
        aggregation='one scalar per episode then equal-weighted across episodes; no pooled frame-level errors')


def analyze_manifest(path):
    path = Path(path).resolve()
    manifest = read_json(path)
    trials = manifest.get('trials')
    if not isinstance(trials, list):
        raise ValueError('Manifest requires a trials list')
    ids = [t['trial_id'] for t in trials]
    if len(ids) != len(set(ids)):
        raise ValueError('trial_id values must be globally unique')
    episodes = [analyze_trial(trial, path.parent) for trial in trials]
    episode_ids = [e['episode_id'] for e in episodes if e['purpose'] == 'formal' and e.get('episode_id')]
    if len(episode_ids) != len(set(episode_ids)):
        raise ValueError('One actual episode cannot fill multiple formal trials')
    groups = sorted({e['group_id'] for e in episodes})
    source = Path(__file__).resolve()
    git = subprocess.run(['git', '-C', str(source.parents[2]), 'rev-parse', 'HEAD'],
        capture_output=True, text=True, check=False)
    dirty = subprocess.run(['git', '-C', str(source.parents[2]), 'status', '--porcelain', '--',
        'demos/lab_cuvette_policy_eval_v1'], capture_output=True, text=True, check=False)
    return dict(schema=SCHEMA, manifest_path=str(path), manifest_sha256=file_sha256(path),
        protocol_id=manifest.get('protocol_id'), protocol_sha256=manifest.get('protocol_sha256'),
        episodes=episodes, groups={group: summarize_group(episodes, group) for group in groups},
        historical_and_diagnostic_trial_ids=[e['trial_id'] for e in episodes if e['purpose'] != 'formal'],
        analysis_implementation=dict(path=str(source), sha256=file_sha256(source),
            code_commit=git.stdout.strip() if git.returncode == 0 else None,
            implementation_worktree_dirty=bool(dirty.stdout.strip()) if dirty.returncode == 0 else None,
            python=sys.version.split()[0]),
        original_sources_modified=False)


def write_results(result, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    for name, value in (('summary.json', result), ('episodes.json', result['episodes']), ('groups.json', result['groups'])):
        (output/name).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n')
    fields = ['trial_id', 'group_id', 'purpose', 'trial_status', 'started', 'episode_id', 'environment_valid',
        'record_complete', 'record_valid', 'task_evaluable', 'task_success', 'censored', 'censor_reason',
        'termination_reason', 'failure_domain', 'failure_type', 'simulation_seconds', 'control_steps',
        'farthest_stage', 'attempt_count', 'retry_count', 'event_count', 'analysis_evidence_valid', 'unstarted_reason']
    metrics = ['nearest_grasp_distance_m', 'target_error_status', 'target_xy_mean_m', 'target_tilt_mean_rad',
        'maximum_valid_insertion_progress', 'maximum_applicable_insertion_depth_m',
        'post_release_clearance_final_m', 'maximum_continuous_stable_duration_s',
        'maximum_post_release_stable_duration_s', 'post_release_stable_duration_status']
    for interval in ('operation', 'before_first_target_support', 'support_transfer'):
        metrics += ['maximum_drift_'+interval+'_m', 'maximum_drift_'+interval+'_rad']
    metrics += ['resource_'+k for k in RESOURCE_FIELDS]
    for stage in STAGE_ORDER:
        metrics += [stage+'_reached', stage+'_first_confirmed_t', stage+'_evidence_coverage']
    fields += metrics

    def csv_row(e):
        row = dict(e)
        c = e.get('continuous') or {}
        row.update(nearest_grasp_distance_m=c.get('minimum', {}).get('grasp_approach_position_error_m', {}).get('value'),
            target_error_status=c.get('target_error_status'),
            target_xy_mean_m=c.get('target_error_within_episode', {}).get('target_lateral_error_m', {}).get('mean'),
            target_tilt_mean_rad=c.get('target_error_within_episode', {}).get('target_tilt_rad', {}).get('mean'),
            maximum_valid_insertion_progress=c.get('maximum', {}).get('valid_insertion_progress', {}).get('value'),
            maximum_applicable_insertion_depth_m=c.get('maximum', {}).get('valid_insertion_depth_m', {}).get('value'),
            post_release_clearance_final_m=c.get('post_release_clearance_final', {}).get('value'),
            maximum_continuous_stable_duration_s=c.get('maximum', {}).get('stable_duration_s', {}).get('value'),
            maximum_post_release_stable_duration_s=c.get('maximum', {}).get('post_release_stable_duration_s', {}).get('value'),
            post_release_stable_duration_status=c.get('post_release_stable_duration_status'))
        for interval in ('operation', 'before_first_target_support', 'support_transfer'):
            attempts = e.get('drift_intervals', {}).get(interval, [])
            for name, suffix in (('maximum_relative_translation_m', 'm'), ('maximum_relative_rotation_rad', 'rad')):
                row['maximum_drift_'+interval+'_'+suffix] = max((v for a in attempts if (v := finite(a.get(name))) is not None), default=None)
        row.update({'resource_'+k: e.get('resource', {}).get(k) for k in RESOURCE_FIELDS})
        for stage in STAGE_ORDER:
            state = e.get('stage_results', {}).get(stage, {})
            row.update({stage+'_reached': state.get('reached'), stage+'_first_confirmed_t': state.get('first_confirmed_t'),
                stage+'_evidence_coverage': state.get('evidence_coverage')})
        return row

    with (output/'episodes.csv').open('w', newline='', encoding='utf-8-sig') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(csv_row(e) for e in result['episodes'])
    with (output/'stage_rates.csv').open('w', newline='', encoding='utf-8-sig') as stream:
        fields = ('group_id', 'stage', 'achieved', 'started_denominator', 'known_denominator', 'unknown', 'rate_per_started', 'wilson95_lower', 'wilson95_upper', 'rate_per_known', 'evidence_coverage_mean', 'time_mean_s', 'time_n')
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for group, summary in result['groups'].items():
            for stage, s in summary['stage_rates'].items():
                writer.writerow(dict(group_id=group, stage=stage, achieved=s['achieved'],
                    started_denominator=s['started_denominator'], known_denominator=s['known_denominator'], unknown=s['unknown'],
                    rate_per_started=s['achieved_per_started']['rate'], wilson95_lower=s['achieved_per_started']['lower'],
                    wilson95_upper=s['achieved_per_started']['upper'], rate_per_known=s['achieved_per_known']['rate'],
                    evidence_coverage_mean=s['mean_episode_evidence_coverage']['mean'],
                    time_mean_s=s['first_confirmed_time_s']['mean'], time_n=s['first_confirmed_time_s']['n']))
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists():
        raise FileExistsError(args.output)
    result = analyze_manifest(args.manifest)
    write_results(result, args.output)
    print(json.dumps({k: {n: g[n] for n in ('planned', 'started', 'success', 'task_evaluable', 'unstarted')}
        for k, g in result['groups'].items()}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
