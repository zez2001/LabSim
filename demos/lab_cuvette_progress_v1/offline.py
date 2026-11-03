"""Read-only adapters for closed lab_cuvette_loading episodes and HDF5 indexes."""
from __future__ import annotations

import copy
import json
import math
import os
from pathlib import Path
import subprocess
import time

from .io import (ProgressWriter, atomic_json, file_sha256, iter_json_rows,
                 json_safe, object_sha256)


def _json(value, default=None):
    if value is None:
        return default
    if isinstance(value, bytes):
        value = value.decode('utf-8')
    return json.loads(str(value))


def _load(path, default=None):
    return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else default


def _dataset_json(group, key, index=None, default=None):
    if key not in group:
        return default
    return _json(group[key][() if index is None else index], default)


def _scalar(group, key, index, default=None):
    if key not in group:
        return default
    return json_safe(group[key][index])


def _find_log(episode, stem):
    if episode is None:
        return None
    return next((episode / name for name in (stem + '.jsonl', stem + '.jsonl.gz', stem + '.json')
                 if (episode / name).is_file()), None)


def _closed(group, episode):
    complete = group.attrs.get('complete', False)
    state = str(group.attrs.get('publication_state', 'complete' if complete else 'unknown'))
    if not complete or state != 'complete':
        raise RuntimeError('Offline Progress requires a closed, completely published HDF5 episode')
    if episode is not None:
        manifest = _load(episode.parent / 'run_manifest.json', {})
        pid = manifest.get('process_id')
        if pid:
            try:
                os.kill(int(pid), 0)
            except ProcessLookupError:
                pass
            else:
                raise RuntimeError(f'Source writer process {pid} still exists; close it before offline analysis')


def _safe_output(output, source_h5, episode=None):
    output = Path(output).resolve()
    source_h5 = Path(source_h5).resolve()
    if output == source_h5 or (episode is not None and
            (output == episode or episode in output.parents)):
        raise ValueError('Offline output must be outside the original episode directory')
    if output in source_h5.parents:
        raise ValueError('Offline output must not contain the source trajectory')
    if output.exists() and any(output.iterdir()):
        raise FileExistsError('Offline output must be a new or empty directory: ' + str(output))
    return output


def _identity(source_h5, group, episode, container_hash=None):
    keys = ('episode_id', 'scene_version', 'asset_id', 'asset_sha256', 'asset_version',
            'code_commit', 'actual_execution_commit', 'record_purpose', 'task_success',
            'task_success_known', 'failure_type', 'termination_reason', 'record_valid',
            'physics_trustworthy', 'success_bc_eligible', 'record_integrity_valid',
            'publication_state', 'complete')
    attrs = {key: json_safe(group.attrs[key]) for key in keys if key in group.attrs}
    metadata = _dataset_json(group, 'episode_metadata_json', default={}) or {}
    metadata.update(attrs)
    if episode is not None:
        # These exact measured references bind online and offline initialization.
        metadata.update(_load(episode / 'progress_input_metadata.json', {}) or {})
        metadata['physics_capture_meta'] = _load(episode / 'physics_capture_meta.json', {})
    metadata['source_trajectory'] = dict(h5=str(source_h5), h5_group=group.name,
        h5_sha256=container_hash or file_sha256(source_h5),
        episode_directory=str(episode) if episode is not None else None,
        original_labels=attrs, mutation_policy='read-only; original HDF5, labels and reward untouched')
    try:
        metadata['progress_code_commit'] = subprocess.check_output(
            ['git', 'rev-parse', 'HEAD'], cwd=Path(__file__).parents[2], text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        metadata['progress_code_commit'] = 'unknown'
    return metadata


def _configuration(group, episode, config_path):
    import yaml
    if config_path is not None:
        path = Path(config_path).resolve()
        return yaml.safe_load(path.read_text()), dict(path=str(path), sha256=file_sha256(path))
    if episode is not None and (episode / 'config.yaml').is_file():
        path = episode / 'config.yaml'
        return yaml.safe_load(path.read_text()), dict(path=str(path), sha256=file_sha256(path))
    if 'configuration_json' in group.attrs:
        cfg = _json(group.attrs['configuration_json'])
        return cfg, dict(source='HDF5 configuration_json', sha256=object_sha256(cfg))
    raise ValueError('Task configuration missing; pass --config with the actual episode configuration')


def audit_contacts(path):
    """Audit callbacks as independent provenance; tensor forces are never added again."""
    if path is None:
        return dict(available=False, reason='native contact callback log absent',
                    force_fusion='none; never infer zero contact from a missing callback log')
    count = duplicate = forbidden = 0
    first = last = None
    for row in iter_json_rows(path):
        t = float(row.get('t', row.get('time', 0.)))
        first = t if first is None else min(first, t)
        last = t if last is None else max(last, t)
        count += 1
        duplicate += int(row.get('possible_duplicate_same_step', False))
        forbidden += int(row.get('forbidden_robot_environment', False))
    return dict(available=True, path=str(path), sha256=file_sha256(path), events=count,
        possible_duplicate_same_step=duplicate, forbidden_callback_events=forbidden,
        first_t=first, last_t=last,
        evidence_scope='Sparse raw native PhysX callbacks, not a regularly sampled no-contact channel',
        force_fusion='audit only; callback impulse/force never summed with tensor normal/friction channels')


def execution_for_transition(group, index, before, after):
    """Only actual recorded commands qualify insertion requests; phase names never do."""
    raw = _dataset_json(group, 'actions_raw_json', index, {}) or {}
    conversion = _dataset_json(group, 'action_conversion_json', index, {}) or {}
    q = _scalar(group, 'control_auxiliary/command_q', index)
    available = bool(raw or conversion or q is not None)
    return dict(available=available, t_obs=before, t_next=after, raw_action=raw,
        conversion=conversion, command_q9=q,
        gripper_target_m=_scalar(group, 'control_auxiliary/gripper_target_m', index),
        source='recorded HDF5 action/conversion/control_auxiliary, not teacher phase')


def _h5_row(group, index, *, after=False):
    field = 'privileged/next_state_json' if after else 'privileged/state_json'
    row = _dataset_json(group, field, index, {}) or {}
    # Historical debug dictionaries may wrap the actual recorder row.
    for key in ('physics', 'physics_record', 'raw_physics'):
        if isinstance(row.get(key), dict):
            row = row[key]
            break
    row = copy.deepcopy(row)
    row['t'] = float(group['next_timestamp' if after else 'timestamp'][index])
    row['simulation_time'] = row['t']
    row['_evidence'] = dict(scope='control_frequency_only', source=field,
        missing_between_samples=True, confirmation='first observed control sample; no high-frequency claim')
    return row


def _transition_metadata(group, index):
    return dict(source='HDF5', source_transition_index=index,
        obs_step=_scalar(group, 'obs_step', index), next_obs_step=_scalar(group, 'next_obs_step', index),
        partial_terminal_control_interval=bool(_scalar(group, 'partial_terminal_control_interval', index, False)),
        done=bool(_scalar(group, 'done', index, False)),
        control_interval_s=_scalar(group, 'control_interval_s', index),
        original_task_events=_dataset_json(group, 'task_events_json', index, []))


def _analyze_group(source_h5, group, output, *, episode=None, config_path=None,
                   make_report=True, container_hash=None, membership=None):
    from .config import resolve_config

    _closed(group, episode)
    output = _safe_output(output, source_h5, episode)
    if 'timestamp' not in group or 'next_timestamp' not in group:
        raise ValueError('HDF5 episode has no aligned timestamp/next_timestamp transitions')
    if len(group['timestamp']) != len(group['next_timestamp']):
        raise ValueError('HDF5 transition time channels have unequal lengths')
    metadata = _identity(source_h5, group, episode, container_hash)
    if membership:
        metadata['source_trajectory']['index_membership'] = membership
    task_cfg, config_origin = _configuration(group, episode, config_path)
    metadata['task_config_origin'] = config_origin
    count = len(group['timestamp'])
    if not count:
        raise ValueError('HDF5 episode contains no transitions')
    physics_path = _find_log(episode, 'physics_records')
    contacts = audit_contacts(_find_log(episode, 'native_contact_events'))
    metadata['input_evidence'] = dict(mode='physics_rate' if physics_path else 'control_frequency_only',
        contacts=contacts, h5_transitions=count, privileged_channels=dict(
            before='privileged/state_json' in group, after='privileged/next_state_json' in group),
        missing_evidence=[] if physics_path else ['high-frequency physics samples', 'reset initial physical sample'],
        temporal_scope='physics timestamps' if physics_path else 'HDF5 observed endpoints only; transients can be missed')
    if not physics_path:
        hz = group.attrs.get('control_hz', task_cfg.get('physics', {}).get('control_hz'))
        metadata['sample_interval_s'] = 1. / float(hz) if hz else float(group['next_timestamp'][0] - group['timestamp'][0])
    rows = iter(iter_json_rows(physics_path)) if physics_path else iter([_h5_row(group, 0)])
    first = next(rows, None)
    if first is None:
        raise ValueError('Physics log contains no samples')
    overrides = task_cfg.get('progress', {}).get('configuration', {})
    config = resolve_config(task_cfg, metadata, first, overrides=overrides)
    writer = ProgressWriter(output, config, metadata)
    start = time.perf_counter()
    times = dict(first_t=None, last_t=None, min_dt_s=None, max_dt_s=None, samples=0,
                 expected_native_callback_count=None)

    def feed(row, execution=None):
        row = copy.deepcopy(row)
        # An absent execution envelope stays unknown, including reset initialization.
        if execution is not None:
            row['_execution'] = execution
        else:
            row.pop('_execution', None)
        t = float(row.get('t', row.get('simulation_time')))
        if times['last_t'] is not None:
            dt = t - times['last_t']
            if dt <= 0:
                raise ValueError('Offline physics samples must have increasing timestamps')
            times['min_dt_s'] = dt if times['min_dt_s'] is None else min(times['min_dt_s'], dt)
            times['max_dt_s'] = dt if times['max_dt_s'] is None else max(times['max_dt_s'], dt)
        times['first_t'] = t if times['first_t'] is None else times['first_t']
        times['last_t'], times['samples'] = t, times['samples'] + 1
        if row.get('native_contact_events_count') is not None:
            times['expected_native_callback_count'] = int(row['native_contact_events_count'])
        return writer.physical(row)

    original = dict(result=_load(episode / 'result.json', {}) if episode else {},
        independent_score=_load(episode / 'independent_score.json', {}) if episode else
            _dataset_json(group, 'independent_score_json', default={}),
        h5_original_labels=metadata['source_trajectory']['original_labels'])
    termination = {key: group.attrs[key] for key in ('termination_reason', 'failure_type', 'failure_domain')
                   if key in group.attrs}
    termination.update(original_result=original)
    try:
        feed(first)
        pending = next(rows, None) if physics_path else None
        last_end = None
        alignment = dict(exact_before=0, exact_after=0, discontinuous_intervals=0)
        for index in range(count):
            before, after = float(group['timestamp'][index]), float(group['next_timestamp'][index])
            if not math.isfinite(before + after) or after < before:
                raise ValueError(f'Invalid HDF5 execution interval at {index}')
            if last_end is not None and abs(before - last_end) > 1e-8:
                alignment['discontinuous_intervals'] += 1
            execution = execution_for_transition(group, index, before, after)
            if physics_path:
                while pending is not None and float(pending.get('t', pending.get('simulation_time'))) <= after + 1e-8:
                    t = float(pending.get('t', pending.get('simulation_time')))
                    feed(pending, execution if before < t <= after else None)
                    pending = next(rows, None)
            else:
                if before > times['last_t'] + 1e-8:
                    feed(_h5_row(group, index))
                if after > times['last_t'] + 1e-8:
                    feed(_h5_row(group, index, after=True), execution)
            record = writer.transition(before, after, transition_metadata=_transition_metadata(group, index))
            alignment['exact_before'] += int(record['before'] is not None)
            alignment['exact_after'] += int(record['after'] is not None)
            last_end = after
        # Real post-control / terminal samples stay separately attributable, never shifted back.
        while pending is not None:
            feed(pending)
            pending = next(rows, None)
        metadata['input_evidence']['sampling'] = times
        metadata['input_evidence']['h5_alignment'] = alignment
        if physics_path:
            metadata['input_evidence']['physics'] = dict(path=str(physics_path), sha256=file_sha256(physics_path),
                bytes=physics_path.stat().st_size)
        expected = times['expected_native_callback_count']
        contacts['matches_recorder_cumulative_count'] = (expected == contacts['events']) if contacts.get('available') and expected is not None else None
        metadata['input_evidence']['processing_wall_seconds_before_finalize'] = time.perf_counter() - start
        # Bind final evidence metadata after streaming, without changing evaluator initialization.
        writer.metadata.update(metadata)
        summary = writer.finalize(json_safe(termination), original)
    except BaseException as exc:
        writer.metadata.update(metadata)
        writer.abort(exc, json_safe(termination), original)
        raise
    if file_sha256(source_h5) != metadata['source_trajectory']['h5_sha256']:
        raise RuntimeError('Source HDF5 changed during offline analysis')
    if make_report:
        from .report import generate_report
        generate_report(output, episode)
    return summary


def analyze_episode(source, output, *, config_path=None, make_report=True):
    import h5py

    source = Path(source).resolve()
    if source.is_dir():
        episode = source
        candidates = sorted((source / 'dataset').glob('episode_*.h5'))
        if len(candidates) != 1:
            raise ValueError('Episode must contain exactly one dataset/episode_*.h5')
        source_h5 = candidates[0]
    else:
        source_h5 = source
        episode = source.parent.parent if source.parent.name == 'dataset' else None
    with h5py.File(source_h5, 'r') as group:
        return _analyze_group(source_h5, group, output, episode=episode,
                              config_path=config_path, make_report=make_report)


def analyze_index(index_path, output, *, config_path=None, make_report=True):
    """Process explicit index members, preserving exclusion and qualification labels."""
    import h5py

    index_path, output = Path(index_path).resolve(), Path(output).resolve()
    if output.exists() and any(output.iterdir()):
        raise FileExistsError('Batch output already exists: ' + str(output))
    if output == index_path.parent or output in index_path.parents:
        raise ValueError('Batch output must not contain the source index')
    index_hash = file_sha256(index_path)
    results, excluded = [], []
    output.mkdir(parents=True, exist_ok=True)
    with h5py.File(index_path, 'r') as index:
        if not index.attrs.get('complete', False):
            raise RuntimeError('Source index is not completely published')
        membership = _json(index.attrs.get('membership_json'), []) or []
        by_id = {row.get('episode_id'): row for row in membership}
        excluded.extend(row for row in membership if not row.get('included', True))
        groups = [('/', index)] if 'timestamp' in index else [(name, index[name]) for name in index
            if isinstance(index[name], h5py.Group) and 'timestamp' in index[name]]
        for number, (name, group) in enumerate(groups):
            episode_id = str(group.attrs.get('episode_id', name))
            member = by_id.get(episode_id)
            if member is not None and not member.get('included', True):
                continue
            actual_h5 = Path(group.file.filename).resolve()
            episode = actual_h5.parent.parent if actual_h5.parent.name == 'dataset' else None
            if member and member.get('source'):
                original_h5 = (index_path.parent / member['source']).resolve()
                if original_h5.is_file():
                    if member.get('source_h5_sha256') and file_sha256(original_h5) != member['source_h5_sha256']:
                        raise ValueError('Index member source HDF5 hash mismatch: ' + episode_id)
                    if original_h5.parent.name == 'dataset':
                        episode = original_h5.parent.parent
            destination = output / f'{number:04d}_{Path(name).name or "episode"}'
            try:
                summary = _analyze_group(actual_h5, group, destination, episode=episode,
                    config_path=config_path, make_report=make_report,
                    container_hash=index_hash if actual_h5 == index_path else None, membership=member)
            except RuntimeError as exc:
                if 'closed' in str(exc) or 'published' in str(exc) or 'still exists' in str(exc):
                    excluded.append(dict(episode_id=episode_id, included=False, exclusion_reason=str(exc)))
                    continue
                raise
            results.append(dict(episode_id=episode_id, h5_group=name, output=str(destination),
                progress_complete=summary.get('progress_complete'), output_status=summary['output_integrity']['status']))
    if file_sha256(index_path) != index_hash:
        raise RuntimeError('Source index changed during offline analysis')
    result = dict(schema='labsim.lab_cuvette_loading.progress.batch.v1', index=str(index_path),
        index_sha256=index_hash, episodes=results, excluded=excluded,
        original_hdf5_and_labels_unchanged=True)
    atomic_json(output / 'progress_batch_summary.json', result)
    return result


def compare_progress(online_directory, offline_directory, output=None):
    """Compare causal diagnostics; metadata, execution envelopes and timings are provenance.

    Floating point values are compared exactly: both paths call the same core
    with the same raw samples and resolved geometry, so tolerances could hide
    an actual sampling/boundary discrepancy.
    """
    online, offline = Path(online_directory).resolve(), Path(offline_directory).resolve()
    left = json.loads((online / 'progress_summary.json').read_text())
    right = json.loads((offline / 'progress_summary.json').read_text())
    differences, checked = [], 0

    def first_difference(a, b, path):
        if type(a) is not type(b):
            return dict(path=path, online=a, offline=b)
        if isinstance(a, dict):
            for key in sorted(set(a) | set(b)):
                if key not in a or key not in b:
                    return dict(path=path + '.' + key, online=a.get(key), offline=b.get(key), missing_key=True)
                found = first_difference(a[key], b[key], path + '.' + key)
                if found:
                    return found
        elif isinstance(a, list):
            if len(a) != len(b):
                return dict(path=path + '.length', online=len(a), offline=len(b))
            for i, (x, y) in enumerate(zip(a, b)):
                found = first_difference(x, y, f'{path}[{i}]')
                if found:
                    return found
        elif a != b:
            return dict(path=path, online=a, offline=b)
        return None

    import itertools
    for i, (a, b) in enumerate(itertools.zip_longest(
            iter_json_rows(online / 'progress_v1.jsonl.gz'),
            iter_json_rows(offline / 'progress_v1.jsonl.gz'))):
        if a is None or b is None:
            differences.append(dict(path=f'transition[{i}]', online_present=a is not None, offline_present=b is not None))
            break
        checked += 1
        for key in ('t_obs', 't_next', 'before', 'after', 'events'):
            found = first_difference(a.get(key), b.get(key), f'transition[{i}].{key}')
            if found:
                differences.append(dict(found, t_obs=a['t_obs'], t_next=a['t_next']))
                break
        if differences:
            break
    final_keys = ('progress_complete', 'unfinished_requirement', 'failure_observation',
                  'attempts', 'stages', 'milestones', 'events', 'last_snapshot',
                  'reset_snapshot', 'first_control_observation', 'initial_events',
                  'unassigned_terminal_events')
    for key in final_keys:
        found = first_difference(left.get(key), right.get(key), 'summary.' + key)
        if found:
            differences.append(found)
            break
    config_equal = left.get('config_sha256') == right.get('config_sha256')
    samples_equal = left.get('recording', {}).get('physics_samples') == right.get('recording', {}).get('physics_samples')
    result = dict(schema='labsim.lab_cuvette_loading.progress.consistency.v1',
        online_directory=str(online), offline_directory=str(offline),
        equal=not differences and config_equal and samples_equal,
        causal_labels_equal=not differences, resolved_config_equal=config_equal,
        physics_sample_count_equal=samples_equal, transitions_compared=checked,
        differences=differences,
        comparison='Exact causal snapshots, interval events, milestones and attempts; excludes metadata and performance',
        online_summary_sha256=file_sha256(online / 'progress_summary.json'),
        offline_summary_sha256=file_sha256(offline / 'progress_summary.json'))
    if output is not None:
        output = Path(output).resolve()
        if output.exists():
            raise FileExistsError(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        atomic_json(output, result)
    return result
