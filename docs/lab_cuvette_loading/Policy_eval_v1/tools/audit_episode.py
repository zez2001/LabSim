#!/usr/bin/env python3
"""Read-only closure audit for successful or unsuccessful policy episodes.

Uses the release's authoritative final qualifications and Progress v1.2 event
replay. A normal task failure is not a failed integrity audit. No source record,
label, video, or H5 file is modified.
"""
from __future__ import annotations
import argparse
import collections
import gzip
import hashlib
import json
from pathlib import Path
import sys
import time


def sha(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(4 << 20), b''):
            value.update(block)
    return value.hexdigest()


def load(path):
    return json.loads(Path(path).read_text())


def same(value, expected):
    if hasattr(value, 'item'):
        value = value.item()
    if isinstance(value, bytes):
        value = value.decode()
    return value == expected


def environment_status(result, reset_check, physical_nonfinite_rows=0):
    """Describe physical validity independently of task and service outcomes."""
    reasons = []
    if result.get('geometry_valid') is not True:
        reasons.append('geometry_not_valid')
    if reset_check.get('passed') is not True:
        reasons.append('reset_not_valid')
    if physical_nonfinite_rows:
        reasons.append('nonfinite_recorded_physical_state')
    if result.get('failure_domain') == 'simulation':
        reasons.append('simulation_failure')
    # An ordinary policy/budget/safety failure remains an observed task outcome.
    return dict(environment_valid=not reasons, reasons=reasons,
                scope='geometry, reset, finite physical state and explicit simulation-domain failures; independent of task_success')


def check_time_alignment(t0, t1, intervals, obs_step, next_step):
    import numpy as np
    if len(t0) != len(t1) or len(t0) != len(intervals):
        return False
    return bool(np.isfinite(t0).all() and np.isfinite(t1).all() and
        np.all(t1 > t0) and np.allclose(t0[1:], t1[:-1], rtol=0, atol=1e-8) and
        np.allclose(t1-t0, intervals, rtol=0, atol=1e-8) and
        np.array_equal(obs_step[1:], next_step[:-1]) and np.all(next_step == obs_step+1))


def decode_video(path):
    import cv2
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise ValueError('Video cannot be opened: ' + str(path))
    expected = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = float(cap.get(cv2.CAP_PROP_FPS))
    width, height = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    count = 0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if frame is None or not frame.size:
                raise ValueError('Empty decoded video frame')
            count += 1
    finally:
        cap.release()
    if count != expected or count < 1 or fps <= 0:
        raise ValueError('Incomplete video decode: ' + str(path))
    return dict(path=str(path), frames_decoded=count, expected_frames=expected,
                fps=fps, resolution_wh=[width, height], complete_decode=True)


def audit(episode, *, expected_purpose=None):
    import h5py
    import numpy as np
    root = Path(__file__).resolve().parents[4]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from demos.lab_cuvette_progress_v1.replay import verify_replay
    episode = Path(episode).resolve()
    run = episode.parent
    errors, checks = [], []
    def check(condition, description):
        checks.append(dict(check=description, passed=bool(condition)))
        if not condition:
            errors.append(description)
    source_paths = sorted(p for p in episode.rglob('*') if p.is_file())
    source_paths += [run/name for name in ('process_exit.json', 'run_manifest.json',
        'launch_identity.json', 'application_shutdown.json') if (run/name).is_file()]
    before = {str(path): sha(path) for path in source_paths}
    result = load(episode/'result.json')
    independent = load(episode/'independent_score.json')
    marker_path = next(episode.glob('episode_*_complete.json'))
    marker = load(marker_path)
    published_path = episode/marker['result']
    published = load(published_path)
    summary = load(episode/'progress_summary.json')
    process = load(run/'process_exit.json')
    manifest = load(run/'run_manifest.json')
    shutdown = load(run/'application_shutdown.json')
    check(process.get('process_exited') is True and process.get('exit_code') == 0,
          'parent_observed_native_process_exit_zero')
    pids = {int(row['pid']) for row in process.get('children', []) if row.get('pid')}
    pids.update(int(d[k]) for d in (process, manifest) for k in ('pid', 'process_id') if d.get(k))
    check(bool(pids) and all(not Path('/proc', str(pid)).exists() for pid in pids),
          'all_recorded_native_and_launcher_PIDs_absent_now')
    check(all(row.get('process_exited') is True and row.get('native_pid_gone') is True
              for row in process.get('children', [])), 'all_supervised_children_closed')
    check(shutdown.get('application_close_returned') is True and not shutdown.get('errors'),
          'application_full_shutdown_closed_writers')
    episode_id, finalization = result['episode_id'], result['finalization_id']
    check(independent == published['result'], 'raw_independent_score_matches_immutable_published_projection')
    check(all(same(result.get(key), value) for key, value in published['labels'].items()),
          'authoritative_final_labels_match_published_labels')
    check(all(value == episode_id for value in (independent.get('episode_id'), marker.get('episode_id'),
        summary.get('episode_id'), summary.get('metadata', {}).get('episode_id'))), 'all_episode_identities_match')
    check(finalization == marker.get('finalization_id') == published.get('finalization_id') ==
        published['labels'].get('finalization_id'), 'finalization_identity_matches')
    check(result.get('complete') is True and result.get('publication_state') == 'complete',
          'authoritative_episode_publication_complete')
    purpose = result.get('record_purpose')
    check(purpose == marker.get('record_purpose') == published.get('record_purpose') == manifest.get('record_purpose'),
          'explicit_record_purpose_matches')
    if expected_purpose is not None:
        check(purpose == expected_purpose, 'record_purpose_matches_requested_audit_scope')
    check(result.get('progress_status') == 'complete' and
        summary.get('output_integrity', {}).get('complete') is True and
        summary.get('output_integrity', {}).get('errors') == [], 'progress_recording_integrity_complete')
    for relative, descriptor in summary.get('output_integrity', {}).get('files', {}).items():
        path = episode/relative
        check(path.is_file() and path.stat().st_size == descriptor['bytes'] and sha(path) == descriptor['sha256'],
              'progress_integrity_hash:' + relative)

    h5_path = episode/'dataset'/marker['h5']
    with h5py.File(h5_path, 'r') as source:
        attrs = source.attrs
        for key in ('episode_id', 'finalization_id', 'task_success', 'record_valid', 'complete',
                    'record_integrity_valid', 'publication_state', 'record_purpose', 'asset_id', 'scene_version',
                    'success_bc_eligible', 'termination_reason', 'failure_type', 'failure_domain'):
            check(key in attrs and same(attrs[key], result.get(key)), 'H5_final_attribute:' + key)
        h5_score_text = source['independent_score_json'].asstr()[()]
        check(same(attrs.get('independent_score_sha256'), hashlib.sha256(h5_score_text.encode()).hexdigest()),
              'H5_independent_score_serialized_value_hash')
        check(json.loads(h5_score_text) == independent,
              'H5_raw_independent_score_unchanged')
        qualifications = json.loads(source['qualification_json'].asstr()[()])
        check(all(same(result.get(key), value) for key, value in qualifications.items() if key != 'schema'),
              'H5_final_qualification_values_match')
        metadata = json.loads(source['episode_metadata_json'].asstr()[()])
        check(metadata.get('record_purpose') == purpose, 'H5_metadata_purpose')
        check(metadata.get('actual_execution_commit') == process.get('runtime_commit') == manifest.get('code_commit'),
              'runtime_commit_matches_H5_metadata_and_run')
        n = len(source['actions'])
        t0, t1 = source['timestamp'][:], source['next_timestamp'][:]
        check(check_time_alignment(t0, t1, source['control_interval_s'][:], source['obs_step'][:], source['next_obs_step'][:]),
              'observation_action_successor_time_and_step_adjacency')
        check(source['actions'].shape == (n, 8) and source['control_auxiliary/command_q'].shape == (n, 9),
              'actual_command_shapes_8D_compatibility_and_9D_execution')
        for name in ('actions', 'joint_positions', 'next_joint_positions', 'agent_pose',
                     'next_agent_pose', 'control_auxiliary/command_q'):
            check(np.isfinite(source[name][:]).all(), 'finite_robot_action_state:' + name)
        check(np.allclose(source['next_joint_positions'][:-1], source['joint_positions'][1:], rtol=0, atol=1e-8),
              'actual_joint_successor_state_adjacency')
        check(all(x == episode_id for x in source['episode_id'].asstr()[:]), 'all_H5_transition_episode_identities_match')
        check(len(source['actions_raw_json']) == n and len(source['action_conversion_json']) == n,
              'raw_action_and_conversion_counts_match')
        for name in ('actions_raw_json', 'action_conversion_json'):
            for item in source[name].asstr()[:]:
                json.loads(item)
        if n:
            check(abs(float(source['terminal_observation'].attrs['simulation_time'])-float(t1[-1])) < 1e-8,
                  'terminal_observation_time_matches_final_successor')
            check(np.allclose(source['terminal_observation/joint_positions'][:], source['next_joint_positions'][-1], rtol=0, atol=1e-8),
                  'terminal_robot_state_matches_final_successor')
        seen, dataset_specs, read_bytes = set(), [], 0
        def read_dataset(name, item):
            nonlocal read_bytes
            if not isinstance(item, h5py.Dataset):
                return
            address = h5py.h5o.get_info(item.id).addr
            if address in seen:
                return
            seen.add(address)
            if not item.shape:
                value = item[()]
                read_bytes += getattr(value, 'nbytes', 0)
            else:
                for start in range(0, len(item), 32):
                    value = item[start:start+32]
                    read_bytes += getattr(value, 'nbytes', 0)
            dataset_specs.append(dict(name=name, shape=list(item.shape), dtype=str(item.dtype)))
        source.visititems(read_dataset)
        aliases = {cam: source[cam].id == source[alias].id for cam, alias in
                   [('camera_1_rgb', 'side_camera_rgb'), ('camera_2_rgb', 'wrist_camera_rgb')]}
        check(all(aliases.values()), 'camera_aliases_are_original_H5_hardlinks')
        h5 = dict(path=str(h5_path), sha256=sha(h5_path), bytes=h5_path.stat().st_size,
                  transitions=n, first_t_obs_s=float(t0[0]) if n else None,
                  last_t_next_s=float(t1[-1]) if n else None, metadata=metadata,
                  all_unique_datasets_read=True, read_array_bytes=read_bytes,
                  datasets=dataset_specs, image_hardlink_aliases=aliases)

    logs = {}
    nonfinite_rows = 0
    for name in ('physics_records.jsonl.gz', 'native_contact_events.jsonl.gz', 'progress_v1.jsonl.gz'):
        path = episode/name
        rows, byte_count, unpacked_hash, last_t = 0, 0, hashlib.sha256(), None
        with gzip.open(path, 'rb') as stream:
            for raw_line in stream:
                byte_count += len(raw_line)
                unpacked_hash.update(raw_line)
                if not raw_line.strip():
                    continue
                row = json.loads(raw_line)
                if name == 'physics_records.jsonl.gz':
                    t = float(row['t'])
                    check(last_t is None or t >= last_t-1e-9, 'physics_time_monotonic:' + str(rows))
                    last_t = t
                    critical = [row.get(key) for key in ('object_position_m', 'object_quaternion_wxyz', 'joints9')]
                    if any(value is None or not np.isfinite(np.asarray(value, float)).all() for value in critical):
                        nonfinite_rows += 1
                if name == 'progress_v1.jsonl.gz':
                    check(row.get('episode_id') == episode_id and row.get('transition_index') == rows,
                          'progress_transition_identity:' + str(rows))
                    check(rows < n and abs(float(row['t_obs'])-float(t0[rows])) < 1e-8 and
                          abs(float(row['t_next'])-float(t1[rows])) < 1e-8,
                          'progress_H5_time_alignment:' + str(rows))
                rows += 1
        logs[name] = dict(rows=rows, sha256=sha(path), stored_bytes=path.stat().st_size,
                          uncompressed_bytes=byte_count, uncompressed_sha256=unpacked_hash.hexdigest(),
                          gzip_crc_and_json_valid=True)
    check(logs['physics_records.jsonl.gz']['rows'] == summary['recording']['physics_samples'], 'physics_log_count_matches_Progress')
    check(logs['progress_v1.jsonl.gz']['rows'] == n == summary['recording']['control_transitions'],
          'H5_and_Progress_transition_counts_match')
    closed = load(episode/'recording_closed_receipt.json')
    for item in closed['streams'].values():
        actual = logs[item['path']]
        check(item['closed'] and item['close_succeeded'] and item['line_count'] == actual['rows'] and
              item['uncompressed_sha256'] == actual['uncompressed_sha256'], 'original_stream_close_hash:' + item['path'])
    events = [json.loads(line) for line in (episode/'progress_events.jsonl').read_text().splitlines() if line.strip()]
    replay = verify_replay(events, summary)
    check(replay['passed'], 'full_append_only_events_replay_matches_attempts_and_retries')
    check(len(events) == summary['recording']['event_count'] == summary['event_count'], 'complete_event_stream_count_matches')
    video_clock = load(episode/'video_timestamps.json')
    video_times = np.asarray(video_clock['frame_simulation_times_s'], float)
    check(np.isfinite(video_times).all() and np.all(np.diff(video_times) > 0), 'actual_video_sample_times_finite_and_monotonic')
    videos = {}
    for name in ('side_camera.mp4', 'wrist_camera.mp4', 'dual_view.mp4'):
        videos[name] = decode_video(episode/name)
        videos[name]['sha256'] = sha(episode/name)
        check(videos[name]['frames_decoded'] == len(video_times), 'video_decoded_frames_match_actual_clock:' + name)
    if n:
        check(abs(float(video_clock['terminal_simulation_time_s'])-float(t1[-1])) < 1e-8,
              'video_terminal_clock_matches_final_successor')
    validity = environment_status(result, load(episode/'reset_check.json'), nonfinite_rows)
    after = {path: sha(path) for path in before}
    unchanged = before == after
    check(unchanged, 'all_source_record_hashes_unchanged_by_audit')
    return dict(schema='labsim.Policy_eval_v1.closed_episode_audit.v1', episode=str(episode),
        episode_id=episode_id, passed=not errors, errors=errors, check_count=len(checks),
        checks_failed=[item for item in checks if not item['passed']],
        runtime_commit=process.get('runtime_commit'), task_success=result['task_success'],
        environment_valid=validity['environment_valid'], environment_validity=validity,
        record_complete=not errors, record_valid=result['record_valid'], record_purpose=purpose,
        qualification_semantics='Integrity acceptance is independent of task success; preserve authoritative record_valid/BC labels',
        termination_reason=result['termination_reason'], failure_domain=result.get('failure_domain'),
        original_final_result=result, original_completion_marker=marker,
        physical_scorer_projection_pending_collector=True,
        process=dict(process_exited=process['process_exited'], exit_code=process['exit_code'],
                     checked_native_PIDs=sorted(pids), native_PIDs_absent=True,
                     evidence_path=str(run/'process_exit.json'), wall_seconds=process.get('wall_seconds')),
        h5=h5, logs=logs, videos=videos,
        progress=dict(recording_complete=summary['output_integrity']['complete'],
            task_progress_complete=summary['progress_complete'], output_integrity=summary['output_integrity'],
            recording=summary['recording'], events_replay=replay, complete_stream_events=len(events),
            event_names=dict(collections.Counter(row.get('name') for row in events)),
            finalize_events_included='Consumed every line of progress_events.jsonl, including unassigned/finalize outcomes if emitted; no event required when no attempt exists'),
        source_hashes_unchanged=unchanged, source_files=[dict(path=path, sha256=value) for path, value in before.items()])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('episode', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--expected-purpose', choices=('policy_evaluation', 'lifecycle_diagnostic', 'demonstration', 'resource_probe'))
    args = parser.parse_args(argv)
    episode, output = args.episode.resolve(), args.output.resolve()
    if output.exists():
        parser.error('Output already exists: ' + str(output))
    if output.is_relative_to(episode):
        parser.error('Audit output must be outside the source episode')
    started = time.perf_counter()
    try:
        value = audit(episode, expected_purpose=args.expected_purpose)
    except Exception as error:
        value = dict(schema='labsim.Policy_eval_v1.closed_episode_audit.v1', episode=str(episode),
                     passed=False, record_complete=False, environment_valid=None,
                     errors=[type(error).__name__ + ': ' + str(error)])
    value['audit_wall_seconds'] = time.perf_counter()-started
    value['audit_tool_sha256'] = sha(__file__)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({key: value.get(key) for key in
        ('passed', 'episode_id', 'task_success', 'environment_valid', 'record_complete', 'errors')}, ensure_ascii=False))
    return 0 if value['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
