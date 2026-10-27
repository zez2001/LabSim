#!/usr/bin/env python3
"""Targeted closed-only lifecycle audit; never mutates native evidence."""
import csv
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from datetime import datetime, timezone

import h5py
import numpy as np

REPO = Path('/home/wujing/Desktop/vla/LabSim')
SRC = REPO / 'outputs/lab_cuvette_loading/Project_release_v1/termination_cases_01'
OUT = REPO / 'docs/lab_cuvette_loading/Project_release_v1/validation/termination_cases_01_closed'
FROZEN = Path('/tmp/labsim-release-termination-clean-20261027')
SOURCE_COMMIT = '73b1a9db9470f9706a3068a8ce24e7e09d8cfc65'
CONDITIONS = ['early_finish', 'no_progress', 'unreachable', 'service_timeout', 'user_interrupt']
EXPECTED_FRAMES = [180, 300, 60, 60, 60]
CHECK_FIELDS = ['task_success', 'record_valid', 'record_integrity_valid', 'failure_type',
                'failure_domain', 'termination_reason', 'eligible_for_success_bc',
                'eligible_for_failure_analysis']
checks = []
sources = {}


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda: f.read(1024 * 1024), b''):
            h.update(b)
    return h.hexdigest()


def remember(path):
    path = path.resolve()
    if str(path) not in sources:
        sources[str(path)] = dict(path=str(path), bytes=path.stat().st_size,
                                  sha256_before=sha(path))
    return path


def read(path):
    return json.loads(remember(path).read_text())


def plain(value):
    if isinstance(value, bytes):
        return value.decode()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    return value


def check(name, ok, **details):
    checks.append(dict(name=name, passed=bool(ok), **details))


def write(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


if OUT.exists():
    raise SystemExit('Refusing to overwrite audit output: ' + str(OUT))
OUT.mkdir(parents=True)
proof = read(SRC / 'process_exit.json')
manifest = read(SRC / 'run_manifest.json')
run_summary = read(SRC / 'summary.json')
resets = read(SRC / 'reset_checks.json')
shutdown = read(SRC / 'application_shutdown.json')
head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=FROZEN, text=True).strip()
check('runtime_source_commit', head == SOURCE_COMMIT and
      manifest.get('actual_execution_commit', manifest.get('code_commit')) == SOURCE_COMMIT,
      frozen_head=head, manifest_commit=manifest.get('actual_execution_commit', manifest.get('code_commit')))
pids = [1754493, 1754496]
check('processes_exited_before_audit', proof.get('process_exited') is True and
      proof.get('exit_code') == 0 and all(not Path(f'/proc/{pid}').exists() for pid in pids),
      pids=pids, exit_code=proof.get('exit_code'))
check('five_episodes_one_native_process', manifest.get('process_id') == 1754496 and
      manifest.get('episodes_completed') == 5 and len(run_summary) == 5,
      native_pid=manifest.get('process_id'))
selection_path = remember(FROZEN / 'utils/episode_selection.py')
spec = importlib.util.spec_from_file_location('frozen_episode_selection', selection_path)
selection = importlib.util.module_from_spec(spec)
spec.loader.exec_module(selection)
episodes = []
video_rows = []
for i, condition in enumerate(CONDITIONS):
    ep = SRC / f'episode_{i:04d}'
    result = read(ep / 'result.json')
    independent = read(ep / 'independent_score.json')
    collector = read(ep / 'episode_0000_result.json')
    marker = read(ep / 'episode_0000_complete.json')
    controlled = read(ep / 'controlled_termination.json')
    recording = read(ep / 'recording_closed_receipt.json')
    facade_reset = read(ep / 'facade_reset_audit.json')
    index_path = remember(ep / 'dataset/meta/episode.jsonl')
    index_rows = [json.loads(x) for x in index_path.read_text().splitlines() if x.strip()]
    check(condition + '.one_index_row', len(index_rows) == 1)
    index = index_rows[0]
    h5_path = remember(ep / 'dataset/episode_0000.h5')
    with h5py.File(h5_path, 'r') as f:
        attrs = {k: plain(v) for k, v in f.attrs.items()}
        attrs_task_success_raw = attrs.get('task_success')
        attrs['task_success'] = selection.episode_labels(attrs)['task_success']
        finals = [result.get('finalization_id'), collector.get('finalization_id'),
                  collector['labels'].get('finalization_id'), marker.get('finalization_id'),
                  index.get('finalization_id'), index['labels'].get('finalization_id'),
                  attrs.get('finalization_id')]
        check(condition + '.finalization_identity', len(set(finals)) == 1 and bool(finals[0]))
        check(condition + '.episode_identity', result['episode_id'] == independent['episode_id'] ==
              marker['episode_id'] == index['episode_id'] == attrs['episode_id'] ==
              controlled['terminal_status']['episode_id'] == facade_reset['episode_id'])
        check(condition + '.publication_complete', all(x.get('complete') is True and
              x.get('publication_state') == 'complete' for x in [result, attrs, collector['labels'], index['labels']]))
        comparisons = [independent, collector['result'], collector['labels'], index['labels'],
                       run_summary[i]['result'], attrs]
        mismatches = [{key: [result.get(key), obj.get(key)]} for obj in comparisons
                      for key in CHECK_FIELDS if result.get(key) != obj.get(key)]
        check(condition + '.final_labels_consistent', not mismatches, mismatches=mismatches)
        expected_task = False if i < 3 else None
        check(condition + '.expected_qualification', result['task_success'] is expected_task and
              result['record_valid'] is (i < 3) and result['record_integrity_valid'] is True)
        check(condition + '.explicit_fault_scope', controlled['condition'] == condition and
              controlled['controlled_fault_injection'] is (i >= 3) and
              controlled['real_model_service_failure'] is False and
              controlled['actual_user_keyboard_action'] is False)
        check(condition + '.no_false_retreat_window', result['retreat_observed'] is False and
              result['post_retreat_window']['status'] == 'unavailable' and
              result['stable_after_retreat'] is None and result['post_retreat_window']['stable'] is None)
        n = len(f['timestamp'])
        done = f['done'][:]
        obs = f['obs_step'][:]
        next_obs = f['next_obs_step'][:]
        times = f['timestamp'][:]
        next_times = f['next_timestamp'][:]
        terminal = f['terminal_observation']
        check(condition + '.frame_count', n == EXPECTED_FRAMES[i] == result['frames'] ==
              attrs['frames'] == index['length'] == controlled['control_steps_advanced'])
        check(condition + '.one_terminal_transition', int(done.sum()) == 1 and bool(done[-1]))
        check(condition + '.transition_chain', np.array_equal(obs, np.arange(n)) and
              np.array_equal(next_obs, np.arange(1, n + 1)) and
              np.allclose(next_times - times, 1 / 60, atol=1e-12, rtol=0) and
              np.array_equal(next_times[:-1], times[1:]))
        check(condition + '.terminal_successor', int(terminal.attrs['step_index']) == n and
              terminal.attrs['simulation_time'] == float(next_times[-1]) ==
              controlled['terminal_status']['simulation_time'] and
              np.array_equal(terminal['joint_positions'][:], f['next_joint_positions'][-1]))
        check(condition + '.finite_small_state_action_arrays', all(np.isfinite(f[k][:]).all()
              for k in ['actions', 'joint_positions', 'next_joint_positions', 'timestamp', 'next_timestamp']))
        receipts = controlled['action_receipts']
        check(condition + '.all_receipts_have_successors', all(r['successor_observation_available'] is True
              and r.get('actual_endpoint_valid') is True for r in receipts))
        check(condition + '.receipt_tick_total', sum(r['executed_control_ticks'] for r in receipts) == n)
        check(condition + '.repeated_finish_idempotent', controlled['repeated_finish_preserved_status'] is True)
        if i:
            check(condition + '.old_observation_zero_ticks', resets[i]['prior_episode_rejected'] is True
                  and resets[i]['stale_probe_executed_ticks'] == 0)
        check(condition + '.reset_cleared_receipts', facade_reset['receipt_count'] == 0 and
              facade_reset['payload_hash_count'] == 0 and
              facade_reset['observation_id'] == result['episode_id'] + ':0')
        if condition == 'unreachable':
            rejected = receipts[-1]
            check(condition + '.unreachable_no_state_advance', rejected['accepted'] is False and
                  rejected['status'] == 'REJECTED' and rejected['stop_reason'] == 'JOINT_PLAN_REJECTED' and
                  rejected['executed_control_ticks'] == rejected['executed_physics_steps'] == 0 and
                  rejected['simulation_time_before'] == rejected['simulation_time_after'] and
                  rejected['observation_id'] == rejected['observation_id_after'])
        filters = {name: dict(zip(['accepted', 'reason'], selection.episode_matches_filter(attrs, name)))
                   for name in ['success', 'failure', 'all_valid']}
        check(condition + '.filter_scope', filters['success']['accepted'] is False and
              filters['failure']['accepted'] is (i < 3) and filters['all_valid']['accepted'] is (i < 3))
        embedded_bytes = f['independent_score_json'][()]
        embedded = json.loads(embedded_bytes)
        check(condition + '.embedded_snapshot_hash', hashlib.sha256(embedded_bytes).hexdigest() ==
              attrs['independent_score_sha256'])
        # Legacy embedded score predates collector close. Final publication labels are authoritative.
        snapshot_differences = {k: dict(embedded=embedded.get(k), final=independent.get(k))
                                for k in set(embedded) | set(independent)
                                if embedded.get(k) != independent.get(k)}
        for channel in ['side_camera_rgb', 'wrist_camera_rgb']:
            check(condition + '.' + channel + '_shape', f[channel].shape == (n, 480, 640, 3))
        finalization = finals[0]
        episode_summary = dict(episode_index=i, condition=condition, episode_id=result['episode_id'],
            finalization_id=finalization, frames=n, executed_duration_s=float(next_times[-1] - times[0]),
            task_success=result['task_success'], record_valid=result['record_valid'],
            failure_type=result['failure_type'], failure_domain=result['failure_domain'],
            termination_reason=result['termination_reason'], filter_results=filters,
            h5_task_success_raw=attrs_task_success_raw,
            embedded_pre_close_score_differences=snapshot_differences,
            native_pair_success=result['native_pair_success'], real_calibrated=result['real_calibrated'],
            controlled_fault_injection=controlled['controlled_fault_injection'],
            qualification_scope='lifecycle diagnostics; not full-loading collection quota')
    check(condition + '.recording_writers_closed', all(s['closed'] is True and
          s['close_succeeded'] is True for s in recording['streams'].values()))
    for name in ['side_camera.mp4', 'wrist_camera.mp4', 'dual_view.mp4']:
        video = remember(ep / name)
        probe = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries',
                                'stream=width,height,avg_frame_rate,nb_frames,duration', '-of', 'json', str(video)],
                               capture_output=True, text=True)
        decode = subprocess.run(['ffmpeg', '-v', 'error', '-xerror', '-i', str(video), '-map', '0:v:0',
                                 '-f', 'framemd5', '-'], capture_output=True)
        records = [line for line in decode.stdout.splitlines() if line and not line.startswith(b'#')]
        metadata = json.loads(probe.stdout) if probe.returncode == 0 else {}
        stream = metadata.get('streams', [{}])[0]
        count = len(records)
        check(condition + '.' + name + '_decode_to_EOF', probe.returncode == decode.returncode == 0 and
              not decode.stderr and count > 0 and count == int(stream.get('nb_frames', -1)),
              decoded_frames=count, declared_frames=stream.get('nb_frames'))
        video_rows.append(dict(episode_index=i, condition=condition, name=name, decoded_frames=count,
            ffmpeg_exit_code=decode.returncode, decoder_stderr=decode.stderr.decode(),
            decoded_frame_hashes_sha256=hashlib.sha256(decode.stdout).hexdigest(), **stream))
    episodes.append(episode_summary)

for item in sources.values():
    item['sha256_after'] = sha(Path(item['path']))
    item['unchanged'] = item['sha256_before'] == item['sha256_after']
check('all_audited_sources_unchanged', all(x['unchanged'] for x in sources.values()))
summary = dict(schema='labsim.Project_release_v1.termination_cases_closed_audit.v1',
    audited_at_utc=datetime.now(timezone.utc).isoformat(), source_root=str(SRC),
    source_commit=SOURCE_COMMIT, source_process_proof=proof, source_native_pid=manifest['process_id'],
    audit_mode='closed-only CPU, targeted metadata/state/transition and MP4 full-decode audit',
    all_checks_passed=all(x['passed'] for x in checks), check_count=len(checks),
    failed_checks=[x for x in checks if not x['passed']],
    episode_count=5, videos_decoded_to_EOF=len(video_rows),
    generic_filter_counts={name: sum(ep['filter_results'][name]['accepted'] for ep in episodes)
                           for name in ['success', 'failure', 'all_valid']},
    qualified_full_task_success_count=0, full_task_failure_collection_quota_added=0,
    episodes=episodes,
    scope_notes=[
      'All five are explicitly bounded lifecycle diagnostics, not complete-loading demonstrations or natural failure-rate measurements.',
      'service_timeout/user_interrupt are explicit finish-domain injections, not a real model outage or physical user keyboard action.',
      'The last two are safely finalized complete records with valid integrity, but record_valid=false/task_success=null excludes them from failure/all_valid task filters.',
      'The first three pass generic failure/all_valid qualification; keep the entire diagnostic cohort outside full-loading data quotas and BC success datasets.',
      'The embedded independent_score_json is the legacy pre-collector-close snapshot; its hash binds those exact bytes. Final H5 attributes, qualification/task_result and external labels include the final integrity decision.',
      'This audit does not read all H5 camera pixels, reconstruct physics/contact traces, or assert effective cooked-collision validity.',
      'SDK cleanup calls returned successfully and process exited zero; absence of SDK warnings is not claimed.'
    ])
write('summary.json', summary)
write('checks.json', checks)
write('videos.json', video_rows)
write('source_manifest.json', list(sources.values()))
with (OUT / 'episodes.csv').open('w', newline='') as f:
    fields=['episode_index','condition','episode_id','frames','executed_duration_s','task_success',
            'record_valid','failure_type','failure_domain','termination_reason','controlled_fault_injection']
    writer=csv.DictWriter(f, fieldnames=fields); writer.writeheader()
    for ep in episodes: writer.writerow({k:ep[k] for k in fields})
shutil.copyfile(__file__, OUT / 'audit.py')
(OUT / 'README.md').write_text('''# Closed termination lifecycle checks\n\nThe five cases ran in one native Isaac process using source `73b1a9d`. Both native and supervisor processes exited with code 0 before this read-only CPU audit. `summary.json`, `checks.json`, `episodes.csv`, and `videos.json` contain the targeted checks and exact qualifications.\n\n`early_finish`, `no_progress`, and `unreachable` are valid task-failure lifecycle records. `service_timeout` and `user_interrupt` are explicit injected termination domains: their task outcome is unknown, and their records are excluded by the normal task failure/all-valid filters. They do not prove a real service outage or actual user key event. No case completed the loading task, and this diagnostic cohort adds no trajectories to the complete-task collection quota.\n\nAll 15 MP4 streams were decoded to EOF. H5 checks cover final labels, transactional identity, state/action time alignment, terminal successor, and image shapes; the audit does not reread every H5 image pixel or all physical traces. The legacy embedded independent score is a pre-close snapshot, while final publication fields include collector integrity; its SHA binds the embedded bytes, not the separately rewritten final independent-score file.\n\nSource evidence was hashed before and after the audit and never modified. Run `audit.py` with the native Python only after choosing a new output directory, because it refuses to overwrite this audit.\n''')
write('evidence_manifest.json', [dict(path=str(p.relative_to(OUT)), bytes=p.stat().st_size, sha256=sha(p))
                                  for p in sorted(OUT.iterdir()) if p.is_file()])
print(json.dumps(dict(output=str(OUT), all_checks_passed=summary['all_checks_passed'],
      check_count=len(checks), failed_checks=summary['failed_checks'],
      generic_filter_counts=summary['generic_filter_counts'], summary_sha256=sha(OUT/'summary.json')),
      ensure_ascii=False))
sys.exit(0 if summary['all_checks_passed'] else 1)
