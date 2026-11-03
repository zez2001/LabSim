"""Recompute a transferred evidence package without source-machine H5 access.

Run from package root with an existing compatible Python + NumPy environment:
  PYTHONPATH=code python code/docs/lab_cuvette_loading/Policy_eval_v1/tools/reanalyse_portable.py \
    --package-root . --output /absolute/path/to/NEW_RECOMPUTATION

The original scorer, stage labels and source evidence remain byte-identical.
Only a NEW working summary's compressed-file identity is rebound to a verified
lossless transfer representation. This is Progress/result recomputation, not a
fresh H5 structural audit or a rerun of the physical scorer from raw physics.
"""
from __future__ import annotations

import argparse
import copy
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from demos.lab_cuvette_policy_eval_v1.analysis import (analyze_manifest, file_sha256,
    read_json, write_results)


def inside(root, base, value):
    path = (base/value).resolve()
    if not path.is_relative_to(root):
        raise ValueError('Portable evidence path escapes package: '+str(value))
    if not path.exists():
        raise FileNotFoundError(path)
    return path


def decoded_sha256(path):
    value = hashlib.sha256()
    with gzip.open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(4 << 20), b''):
            value.update(block)
    return value.hexdigest()


def reanalyse(package_root, output):
    package_root, output = Path(package_root).resolve(), Path(output).resolve()
    if output.exists():
        raise FileExistsError(output)
    manifest_path = package_root/'results/portable_trials.json'
    manifest = read_json(manifest_path)
    if manifest.get('derived_evidence_only') is not True:
        raise ValueError('An explicitly derived portable manifest is required')
    binding = read_json(package_root/'results/source_binding.json')
    if file_sha256(manifest_path) != binding['derived_manifest_sha256']:
        raise ValueError('Derived portable manifest identity differs')
    verified_files = []
    for item in binding['portable_files']:
        path = inside(package_root, package_root, item['package_path'])
        actual = file_sha256(path)
        if actual != item['sha256']:
            raise ValueError('Portable source hash mismatch: '+item['package_path'])
        verified_files.append(dict(path=item['package_path'], sha256=actual))
    cases, representation_changes = [], []
    for trial in manifest['trials']:
        if not trial.get('started'):
            continue
        progress = inside(package_root, manifest_path.parent, trial['progress_dir'])
        receipt = read_json(progress/'portable_media_receipt.json')
        summary_path = progress/'progress_summary.json'
        if file_sha256(summary_path) != receipt['source_summary_sha256']:
            raise ValueError('Original Progress summary identity differs: '+trial['trial_id'])
        summary = read_json(summary_path)
        sidecars = {entry['path']: entry for entry in receipt['sidecars']}
        for name, entry in sidecars.items():
            if Path(name).name != name:
                raise ValueError('Sidecar receipt must name a direct file')
            if file_sha256(progress/name) != entry['sha256']:
                raise ValueError('Sidecar stored identity differs: '+trial['trial_id']+':'+name)
        for name, recorded in (summary.get('output_integrity', {}).get('files') or {}).items():
            if Path(name).name != name:
                raise ValueError('Unsafe Progress file identity')
            actual = file_sha256(progress/name)
            if actual == recorded.get('sha256'):
                continue
            entry = sidecars.get(name) or {}
            if (name != 'progress_v1.jsonl.gz' or entry.get('unchanged_copy') is not False or
                    entry.get('decoded_bytes_identical') is not True or
                    entry.get('source_sha256') != recorded.get('sha256') or
                    entry.get('sha256') != actual or
                    decoded_sha256(progress/name) != entry.get('decoded_jsonl_sha256')):
                raise ValueError('No valid lossless representation proof: '+trial['trial_id']+':'+name)
            representation_changes.append(dict(trial_id=trial['trial_id'], file=name,
                original_stored_sha256=recorded['sha256'], transfer_stored_sha256=actual,
                decoded_jsonl_sha256=entry['decoded_jsonl_sha256'],
                original_summary_sha256=file_sha256(summary_path),
                scope='new working-copy storage identity only; original stage/scoring values unchanged'))
        cases.append((trial, progress, summary))
    output.mkdir(parents=True, exist_ok=False)
    working_manifest = copy.deepcopy(manifest)
    changes_by_case = {change['trial_id']: change for change in representation_changes}
    for trial in working_manifest['trials']:
        if not trial.get('started'):
            continue
        tid = trial['trial_id']
        _, source, summary = next(item for item in cases if item[0]['trial_id'] == tid)
        work = output/'derived_evidence'/tid
        work.mkdir(parents=True)
        for name in ('progress_v1.jsonl.gz', 'progress_events.jsonl', 'progress_config.resolved.json'):
            shutil.copy2(source/name, work/name)
        altered = copy.deepcopy(summary)
        if tid in changes_by_case:
            recorded = altered['output_integrity']['files']['progress_v1.jsonl.gz']
            recorded.update(sha256=file_sha256(work/'progress_v1.jsonl.gz'),
                bytes=(work/'progress_v1.jsonl.gz').stat().st_size)
        (work/'progress_summary.json').write_text(json.dumps(altered, ensure_ascii=False, indent=2)+'\n')
        original_facts, new_facts = copy.deepcopy(summary), copy.deepcopy(altered)
        for facts in (original_facts, new_facts):
            record = facts['output_integrity']['files'].get('progress_v1.jsonl.gz', {})
            for storage_key in ('sha256', 'bytes'):
                record.pop(storage_key, None)
        if original_facts != new_facts:
            raise AssertionError('A non-storage-identity summary field changed')
        trial['progress_dir'] = str(work)
        for name in ('episode_dir', 'cost_summary_path', 'closure_receipt_path'):
            trial[name] = str(inside(package_root, manifest_path.parent, trial[name]))
        trial['episode_directory'] = trial['episode_dir']
    working_path = output/'derived_trials.json'
    working_path.write_text(json.dumps(working_manifest, ensure_ascii=False, indent=2)+'\n')
    result = analyze_manifest(working_path)
    canonical_path = package_root/'results/analysis/summary.json'
    canonical = read_json(canonical_path)
    checks = dict(groups_equal=result['groups'] == canonical['groups'])
    fields = ('task_success', 'record_complete', 'record_valid', 'environment_valid', 'task_evaluable',
        'censored', 'censor_reason', 'simulation_seconds', 'control_steps', 'termination_reason',
        'failure_type', 'stage_results', 'continuous', 'drift_intervals', 'attempts', 'retry_count',
        'event_count', 'resource', 'farthest_stage', 'farthest_stage_rank')
    reference = {e['trial_id']: e for e in canonical['episodes']}
    for field in fields:
        checks['episode_'+field+'_equal'] = all(e.get(field) == reference[e['trial_id']].get(field)
            for e in result['episodes'] if e['started'])
    checks['all_started_analysis_evidence_valid'] = all(e['analysis_evidence_valid'] for e in result['episodes'] if e['started'])
    write_results(result, output/'analysis')
    receipt = dict(schema='labsim.Policy_eval_v1.portable_reanalysis.v1', passed=all(checks.values()),
        tool_sha256=file_sha256(Path(__file__).resolve()),
        checks=checks, portable_manifest_sha256=file_sha256(manifest_path),
        canonical_analysis_sha256=file_sha256(canonical_path), verified_portable_files=verified_files,
        representation_changes=representation_changes, original_data_modified=False,
        source_h5_opened=False, physical_scorer_rerun=False,
        scope='recomputes reported group and episode metrics from original result labels and complete lossless Progress sidecars; raw H5/physics/cooked geometry revalidation requires the engineering source records')
    (output/'portable_reanalysis_receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2)+'\n')
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package-root', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(argv)
    receipt = reanalyse(args.package_root, args.output)
    print(json.dumps(dict(passed=receipt['passed'], source_h5_opened=False,
        representation_changes=len(receipt['representation_changes']))))
    return 0 if receipt['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
