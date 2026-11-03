"""Independently recompute v1.2 attempt drift from original physical rows.

This audit deliberately does not import the evaluator, its statistics helper,
or its geometry implementation.  It reads the declared reference/operation
receipts, verifies the reference against the original physical sample, then
calculates distances with numpy and quaternion angles using a dot product.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path

import numpy as np


TRANSLATION_TOLERANCE_M = 1e-12
ROTATION_TOLERANCE_RAD = 1e-7  # trace/arccos versus independent dot/arccos rounding near zero
TIME_TOLERANCE_S = 1e-9


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            value.update(block)
    return value.hexdigest()


def finite_vector(value, n):
    try:
        result = np.asarray(value, dtype=float)
        return result if result.shape == (n,) and np.isfinite(result).all() else None
    except (TypeError, ValueError):
        return None


def angle(a, b):
    if a is None or b is None or np.linalg.norm(a) < 1e-9 or np.linalg.norm(b) < 1e-9:
        return None
    cosine = float(np.clip(abs(np.dot(a/np.linalg.norm(a), b/np.linalg.norm(b))), 0., 1.))
    return 2.*math.acos(cosine)


def _new():
    return dict(sample_count=0, valid_sample_count=0, missing_sample_count=0,
        translation_valid_sample_count=0, translation_missing_sample_count=0,
        rotation_valid_sample_count=0, rotation_missing_sample_count=0,
        maximum_relative_translation_m=None, maximum_relative_rotation_rad=None,
        translation_peak_t=None, rotation_peak_t=None,
        sample_start_t=None, sample_end_t=None,
        minimum_sample_interval_s=None, maximum_sample_interval_s=None,
        observed_sampling_frequency_hz=None, peak_physical_evidence={})


def _consume(stats, row, displacement, rotation):
    t = float(row['t'])
    previous = stats['sample_end_t']
    if stats['sample_start_t'] is None:
        stats['sample_start_t'] = t
    stats['sample_end_t'] = t
    stats['sample_count'] += 1
    stats['valid_sample_count' if displacement is not None and rotation is not None else 'missing_sample_count'] += 1
    stats['translation_valid_sample_count' if displacement is not None else 'translation_missing_sample_count'] += 1
    stats['rotation_valid_sample_count' if rotation is not None else 'rotation_missing_sample_count'] += 1
    for value, key, prefix in ((displacement, 'maximum_relative_translation_m', 'translation'),
            (rotation, 'maximum_relative_rotation_rad', 'rotation')):
        if value is not None and (stats[key] is None or value > stats[key]):
            stats[key], stats[prefix+'_peak_t'] = value, t
            stats['peak_physical_evidence'][prefix] = {key: row.get(key) for key in (
                't', 'physics_step', 'cup_in_hand_position_m', 'cup_in_hand_quaternion_wxyz',
                'finger_contact_N', 'finger_joint_positions_m', 'target_bottom_support_N',
                'target_bottom_gap_m', 'source_reference_inside', 'target_region_contains_object',
                'depth_m', 'tilt_deg', 'yaw_error_deg', 'input_geometry_overlap_observed_m')}
    if previous is not None:
        dt = t-previous
        stats['minimum_sample_interval_s'] = min(stats['minimum_sample_interval_s'] or dt, dt)
        stats['maximum_sample_interval_s'] = max(stats['maximum_sample_interval_s'] or dt, dt)
        stats['observed_sampling_frequency_hz'] = (stats['sample_count']-1)/(t-stats['sample_start_t'])


def _same(a, b, tolerance):
    return a is None and b is None or a is not None and b is not None and abs(a-b) <= tolerance


def audit(episode, progress_directory, output):
    episode, progress_directory, output = map(Path, (episode, progress_directory, output))
    if output.exists():
        raise FileExistsError(output)
    physics = episode/'physics_records.jsonl.gz'
    event_path, summary_path = progress_directory/'progress_events.jsonl', progress_directory/'progress_summary.json'
    control_path = progress_directory/'progress_v1.jsonl.gz'
    input_paths = [physics, event_path, summary_path]+([control_path] if control_path.is_file() else [])
    source_hashes = {str(path): digest(path) for path in input_paths}
    events = [json.loads(line) for line in event_path.read_text().splitlines() if line.strip()]
    summary = json.loads(summary_path.read_text())
    rows = []
    with gzip.open(physics, 'rt') as stream:
        for line in stream:
            if line.strip():
                rows.append(json.loads(line))
    control_times = set()
    if control_path.is_file():
        with gzip.open(control_path, 'rt') as stream:
            for line in stream:
                if not line.strip():
                    continue
                transition = json.loads(line)
                for endpoint in ('before', 'after'):
                    snapshot = transition.get(endpoint) or {}
                    if snapshot.get('t') is not None:
                        control_times.add(round(float(snapshot['t']), 9))
    checks = []
    for attempt in summary.get('attempts', []):
        aid = attempt['attempt_id']
        reference = attempt.get('relative_pose_reference')
        if reference is None:
            checks.append(dict(attempt_id=aid, available=False, reason='reference_not_established',
                passed=not any(s['sample_count'] for s in attempt.get('relative_motion_statistics', {}).values())))
            continue
        lifecycle_end = next((event for event in events if event.get('attempt_id') == aid and event['name'] in {'attempt_ended', 'attempt_operation_ended'}), None)
        if lifecycle_end is None:
            checks.append(dict(attempt_id=aid, available=False, reason='operation_end_event_missing', passed=False))
            continue
        start, end = float(reference['t']), float(lifecycle_end['t'])
        support_t = next((float(event['t']) for event in events if event.get('attempt_id') == aid and event['name'] == 'support_transfer_confirmed'), None)
        original_reference = next((row for row in rows if abs(float(row['t'])-start) <= TIME_TOLERANCE_S), None)
        if original_reference is None:
            checks.append(dict(attempt_id=aid, available=False, reason='reference_row_missing_from_physics', passed=False))
            continue
        p0 = finite_vector(original_reference.get('cup_in_hand_position_m'), 3)
        q0 = finite_vector(original_reference.get('cup_in_hand_quaternion_wxyz'), 4)
        stored_p, stored_q = finite_vector(reference['position_m'], 3), finite_vector(reference['quaternion_wxyz'], 4)
        ref_matches = bool(p0 is not None and q0 is not None and stored_p is not None and stored_q is not None
            and np.allclose(p0, stored_p, rtol=0., atol=TRANSLATION_TOLERANCE_M)
            and angle(q0, stored_q) <= ROTATION_TOLERANCE_RAD)
        measured = {name: _new() for name in ('operation', 'before_first_target_support', 'support_transfer')}
        control_measured = {name: _new() for name in measured}
        for row in rows:
            t = float(row['t'])
            if t < start-TIME_TOLERANCE_S or t > end+TIME_TOLERANCE_S:
                continue
            p = finite_vector(row.get('cup_in_hand_position_m'), 3)
            q = finite_vector(row.get('cup_in_hand_quaternion_wxyz'), 4)
            displacement = float(np.linalg.norm(p-p0)) if p is not None and p0 is not None else None
            distance = angle(q, q0)
            names = ['operation', 'support_transfer' if support_t is not None and t >= support_t else 'before_first_target_support']
            for name in names:
                _consume(measured[name], row, displacement, distance)
                if round(t, 9) in control_times:
                    _consume(control_measured[name], row, displacement, distance)
        intervals = {}
        for name, recalculated in measured.items():
            declared = attempt.get('relative_motion_statistics', {}).get(name, {})
            comparisons = {}
            for key in ('sample_count', 'valid_sample_count', 'missing_sample_count', 'translation_valid_sample_count',
                    'translation_missing_sample_count', 'rotation_valid_sample_count', 'rotation_missing_sample_count'):
                comparisons[key] = recalculated[key] == declared.get(key)
            for key in ('maximum_relative_translation_m',):
                comparisons[key] = _same(recalculated[key], declared.get(key), TRANSLATION_TOLERANCE_M)
            for key in ('maximum_relative_rotation_rad',):
                comparisons[key] = _same(recalculated[key], declared.get(key), ROTATION_TOLERANCE_RAD)
            for key in ('sample_start_t', 'sample_end_t', 'translation_peak_t', 'rotation_peak_t'):
                comparisons[key] = _same(recalculated[key], declared.get(key), TIME_TOLERANCE_S)
            # Near-zero angle plateaus can select different equivalent peak
            # times under trace/dot rounding; a genuine peak must still match.
            if recalculated['maximum_relative_rotation_rad'] is not None and recalculated['maximum_relative_rotation_rad'] < ROTATION_TOLERANCE_RAD:
                comparisons['rotation_peak_t'] = True
            intervals[name] = dict(recalculated=recalculated, declared=declared,
                comparisons=comparisons, passed=all(comparisons.values()))
        timing = {}
        for stage, recorded in attempt.get('stage_timing', {}).items():
            confirmations = [event for event in events if event.get('attempt_id') == aid and event['name'] == stage+'_confirmed']
            candidates = [event for event in events if event.get('attempt_id') == aid and event['name'] == stage+'_candidate']
            if not confirmations:
                timing[stage] = dict(passed=recorded.get('first_confirmed_t') is None,
                    first_candidate_t=candidates[0]['t'] if candidates else None)
                continue
            expected = dict(first_candidate_t=candidates[0]['t'] if candidates else confirmations[0].get('candidate_start_t'),
                first_confirmed_t=confirmations[0]['t'], last_confirmed_t=confirmations[-1]['t'], confirmation_count=len(confirmations))
            timing[stage] = dict(recalculated=expected, declared=recorded,
                passed=all(recorded.get(key) == value for key, value in expected.items()))
        checks.append(dict(attempt_id=aid, available=True, reference_t=start,
            reference_matches_original_physics=ref_matches, operation_end_event_t=end,
            first_support_transfer_event_t=support_t, intervals=intervals, stage_timing=timing,
            control_endpoint_recalculation=control_measured,
            cadence_interpretation='Both rates use the identical fixed reference and operation intervals. Control endpoint times come from the sidecar, but values are recomputed from original physical rows. A physical-rate observed maximum may exceed a control-rate observed maximum.',
            passed=ref_matches and all(value['passed'] for value in intervals.values()) and all(value['passed'] for value in timing.values())))
    unchanged = all(digest(Path(path)) == sha for path, sha in source_hashes.items())
    result = dict(schema='labsim.Progress_v1.2.independent_attempt_audit.v1',
        episode_id=summary.get('episode_id'), physics_source=str(physics), progress_directory=str(progress_directory),
        source_sha256=source_hashes, source_files_unchanged=unchanged,
        method='Original physical rows, Euclidean translation and independently normalized quaternion dot-product angle; intervals from operation-end and first support-confirmation events.',
        tolerance=dict(translation_m=TRANSLATION_TOLERANCE_M, rotation_rad=ROTATION_TOLERANCE_RAD, time_s=TIME_TOLERANCE_S),
        quality_filter_applied=False, hold_state_verification_scope='Peak hold-state labels are preserved declared evaluator labels; original raw physical evidence at each independently located peak is included for verification.',
        physical_sample_count=len(rows), attempts=checks,
        passed=unchanged and all(item['passed'] for item in checks))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('episode', type=Path)
    parser.add_argument('progress_directory', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(argv)
    result = audit(args.episode, args.progress_directory, args.output)
    print(json.dumps(dict(output=str(args.output), passed=result['passed'], attempts=len(result['attempts']))))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
