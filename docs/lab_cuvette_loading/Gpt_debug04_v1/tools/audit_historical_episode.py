"""Read-only closure audit for a legacy Project_v1_1 historical episode.

Historical files predate transactional completion markers and explicit data
purposes. Missing later-schema fields stay unavailable; they are not invented.
Original completed-H5 attributes, final qualifications, process receipts, raw
streams and full video decoding establish the available closure evidence.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from demos.lab_cuvette_progress_v1.io import file_sha256, json_safe


def load(path):
    return json.loads(Path(path).read_text())


def audit(episode, output):
    import h5py
    import numpy as np
    episode, output = Path(episode).resolve(), Path(output).resolve()
    if output.exists():
        raise FileExistsError(output)
    source_paths = sorted(p for p in episode.rglob('*') if p.is_file())
    source_paths += [episode.parent/n for n in ('process_exit.json', 'run_manifest.json', 'summary.json') if (episode.parent/n).is_file()]
    before = {str(p): dict(sha256=file_sha256(p), bytes=p.stat().st_size) for p in source_paths}
    checks = []
    def check(condition, name):
        checks.append(dict(check=name, passed=bool(condition)))
    spec = importlib.util.spec_from_file_location('existing_policy_audit', ROOT/'docs/lab_cuvette_loading/Policy_eval_v1/tools/audit_episode.py')
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    result, independent = load(episode/'result.json'), load(episode/'independent_score.json')
    metadata = load(episode/'release_metadata.json')
    process, run = load(episode.parent/'process_exit.json'), load(episode.parent/'run_manifest.json')
    reset = load(episode/'reset_check.json')
    episode_id = result['episode_id']
    check(process.get('process_exited') is True and process.get('exit_code') == 0, 'historical_native_Popen_wait_exit_zero')
    check(result.get('complete') is True and result.get('record_integrity_valid') is True, 'original_final_result_complete_and_record_integrity_valid')
    check(run.get('episodes_completed') == 1, 'historical_run_completed_one_episode')
    check(result['episode_id'] == independent['episode_id'], 'original_result_and_independent_identity_match')
    h5_path = episode/'dataset/episode_0000.h5'
    with h5py.File(h5_path, 'r') as f:
        for k in ('episode_id', 'complete', 'record_valid', 'record_integrity_valid', 'task_success',
                'failure_type', 'termination_reason', 'failure_domain', 'scene_version', 'asset_id', 'success_bc_eligible'):
            check(helper.same(f.attrs.get(k), result.get(k)), 'H5_original_final_label:'+k)
        score_text = f['independent_score_json'].asstr()[()]
        check(json.loads(score_text) == independent, 'original_H5_score_semantics_match_independent_JSON')
        if 'independent_score_sha256' in f.attrs:
            check(helper.same(f.attrs['independent_score_sha256'], hashlib.sha256(score_text.encode()).hexdigest()), 'original_H5_score_serialized_text_hash')
        qualifications = json.loads(f['qualification_json'].asstr()[()])
        check(all(helper.same(result.get(k), v) for k, v in qualifications.items() if k != 'schema'), 'final_qualification_values_match_result')
        original_metadata = json.loads(f['episode_metadata_json'].asstr()[()])
        n = len(f['actions'])
        t0, t1 = f['timestamp'][:], f['next_timestamp'][:]
        check(helper.check_time_alignment(t0, t1, f['control_interval_s'][:], f['obs_step'][:], f['next_obs_step'][:]), 'obs_action_successor_time_and_step_adjacency')
        check(np.allclose(f['next_joint_positions'][:-1], f['joint_positions'][1:], rtol=0, atol=1e-8), 'actual_joint_successor_state_adjacency')
        check(all(v == episode_id for v in f['episode_id'].asstr()[:]), 'every_transition_has_original_episode_identity')
        check(n == result['actual_control_steps'] == result['frames'], 'H5_control_count_matches_original_result')
        check(bool(f['done'][-1]), 'last_transition_done')
        check(f['actions'].shape == (n, 8) and f['control_auxiliary/command_q'].shape == (n, 9), 'original_action_and_command_shapes')
        for name in ('actions', 'joint_positions', 'next_joint_positions', 'agent_pose', 'next_agent_pose', 'control_auxiliary/command_q'):
            check(np.isfinite(f[name][:]).all(), 'finite_robot_action_state:'+name)
        check(abs(float(f['terminal_observation'].attrs['simulation_time'])-float(t1[-1])) < 1e-8, 'terminal_observation_matches_last_successor_time')
        check(np.allclose(f['terminal_observation/joint_positions'][:], f['next_joint_positions'][-1], rtol=0, atol=1e-8), 'terminal_robot_state_matches_last_successor')
        runtime = str(f.attrs['actual_execution_commit'])
        check(runtime == process['runtime_commit'] == metadata['actual_execution_commit'], 'runtime_commit_matches_original_H5_process_and_release_metadata')
        seen, datasets = set(), []
        def visit(name, obj):
            if not isinstance(obj, h5py.Dataset):
                return
            address = h5py.h5o.get_info(obj.id).addr
            if address in seen:
                return
            seen.add(address)
            if not obj.shape:
                obj[()]
            else:
                for start in range(0, len(obj), 32):
                    obj[start:start+32]
            datasets.append(dict(name=name, shape=list(obj.shape), dtype=str(obj.dtype)))
        f.visititems(visit)
        aliases = {name: f[name].id == f[alias].id for name, alias in
            [('camera_1_rgb', 'side_camera_rgb'), ('camera_2_rgb', 'wrist_camera_rgb')]}
        check(all(aliases.values()), 'camera_aliases_are_original_H5_hardlinks')
        h5 = dict(path=str(h5_path), sha256=file_sha256(h5_path), bytes=h5_path.stat().st_size,
            transitions=n, t_obs_first_s=float(t0[0]), t_next_last_s=float(t1[-1]),
            all_unique_datasets_read=True, datasets=datasets, original_episode_metadata=original_metadata,
            original_qualifications=qualifications, image_hardlink_aliases=aliases,
            record_purpose=f.attrs.get('record_purpose'), publication_state=f.attrs.get('publication_state'))
    streams, nonfinite = {}, 0
    for stem in ('physics_records', 'native_contact_events'):
        path = next((episode/name for name in (stem+'.jsonl.gz', stem+'.jsonl') if (episode/name).is_file()), None)
        if path is None:
            streams[stem] = dict(available=False)
            check(False, 'historical_stream_present:'+stem)
            continue
        opener = gzip.open if path.suffix == '.gz' else open
        rows, first, last, monotonic, uncompressed = 0, None, None, True, hashlib.sha256()
        with opener(path, 'rb') as f:
            for line in f:
                uncompressed.update(line)
                if not line.strip():
                    continue
                row = json.loads(line)
                if stem == 'physics_records':
                    t = float(row['t'])
                    monotonic = monotonic and (last is None or t > last)
                    first, last = t if first is None else first, t
                    if any(row.get(k) is None or not np.isfinite(np.asarray(row[k], float)).all()
                           for k in ('object_position_m', 'object_quaternion_wxyz', 'joints9')):
                        nonfinite += 1
                rows += 1
        streams[stem] = dict(path=str(path), rows=rows, first_t=first, last_t=last,
            sha256=file_sha256(path), decoded_sha256=uncompressed.hexdigest(),
            gzip_crc_and_json_valid=True, strictly_increasing_physics_time=monotonic)
    check(streams['physics_records']['rows'] == result['physical_sample_count'], 'physical_count_matches_original_result')
    check(streams['physics_records']['strictly_increasing_physics_time'], 'physics_time_strictly_increasing')
    check(nonfinite == 0, 'finite_original_physical_pose_and_joints')
    check(abs(streams['physics_records']['last_t']-result['simulation_seconds']) < 1e-8, 'physical_final_time_matches_original_result')
    videos = []
    for name in ('side_camera.mp4', 'wrist_camera.mp4', 'dual_view.mp4'):
        path = episode/name
        value = helper.decode_video(path)
        value.update(sha256=file_sha256(path), bytes=path.stat().st_size)
        videos.append(value)
    check(all(v['complete_decode'] for v in videos), 'all_three_original_full_videos_decode')
    after = {str(p): dict(sha256=file_sha256(p), bytes=p.stat().st_size) for p in source_paths}
    check(before == after, 'all_historical_source_hashes_unchanged')
    errors = [c['check'] for c in checks if not c['passed']]
    receipt = dict(schema='labsim.Gpt_debug04_v1.historical_closed_audit.v1', passed=not errors,
        episode_id=episode_id, source_episode=str(episode), checks=checks, errors=errors,
        environment=helper.environment_status(result, reset, nonfinite),
        original_task_success=result['task_success'], original_record_valid=result['record_valid'],
        original_result=result, original_release_metadata=metadata, original_process_receipt=process,
        h5=h5, streams=streams, videos=videos, source_files=before, source_hashes_unchanged=before == after,
        record_schema_notes=dict(version='Project_v1_1 legacy completed record',
            later_transactional_completion_marker='unavailable; not required by this historical schema',
            record_purpose='unknown in original record; new analysis purpose is explicitly historical',
            current_pid_absent=not Path('/proc', str(process['pid'])).exists(),
            current_pid_scope='current PID presence is diagnostic and cannot establish historical process identity after PID reuse'),
        source_mutation_policy='read-only; original H5/result/score/reward/qualifications/videos preserved')
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x') as f:
        json.dump(json_safe(receipt), f, ensure_ascii=False, indent=2, allow_nan=False)
        f.write('\n')
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('episode', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(argv)
    result = audit(args.episode, args.output)
    print(json.dumps(dict(passed=result['passed'], errors=result['errors'], episode_id=result['episode_id'])))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
