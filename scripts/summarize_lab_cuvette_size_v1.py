"""Read-only Size_v1 geometry/runtime/collection summary into a NEW directory.

No simulation, raw-label edits, asset changes or synthetic missing values. The
20+20 qualification counts require an explicit existing collection-audit JSON;
without it they remain unknown, while observed independent outcomes are listed.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys

REPOSITORY = Path(__file__).resolve().parents[1]
DEFAULT_GEOMETRY = REPOSITORY / 'docs/lab_cuvette_loading/Size_v1/geometry/family_20261021_02'
DEFAULT_ROOT = REPOSITORY / 'outputs/lab_cuvette_loading/Size_v1'
NON_TASK = frozenset(('GEOMETRY_PREFLIGHT_BLOCKED', 'GEOMETRY_PRECHECK_BLOCKED',
    'PREFLIGHT_BLOCKED', 'INPUT_CONTRACT_ERROR', 'GEOMETRY_BLOCKED',
    'GEOMETRY_BLOCKED_NOT_EXECUTED', 'GEOMETRY_BLOCKED_PREINSERT',
    'INVALID_INITIAL_STATE', 'INITIALIZATION_INVALID', 'INIT_INVALID',
    'MODEL_SERVICE_UNAVAILABLE', 'MODEL_SERVICE_ERROR', 'MODEL_ERROR',
    'PROCESS_ABORT', 'PROCESS_ABORTED', 'PROCESS_INTERRUPTED', 'INTERRUPTED',
    'UNADJUDICATED', 'PHYSICS_INVALID'))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_json(path, errors):
    if not Path(path).is_file():
        return None
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        errors.append({'path': str(path), 'error': type(exc).__name__ + ': ' + str(exc)})
        return None


def known_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    return None


def _first(*values):
    return next((v for v in values if v is not None), None)


def read_config(path, errors):
    if not Path(path).is_file():
        return {}
    try:
        import yaml
        value = yaml.safe_load(Path(path).read_text(encoding='utf-8'))
        return value if isinstance(value, dict) else {}
    except (ImportError, OSError, ValueError) as exc:
        errors.append({'path': str(path), 'error': type(exc).__name__ + ': ' + str(exc)})
        return {}


def read_closed_h5_metadata(episode, errors):
    """Only called after a complete canonical result is present, not live files."""
    paths = sorted((episode / 'dataset').glob('episode_*.h5'))
    if not paths:
        return {}, None
    try:
        import h5py
        import numpy as np
        with h5py.File(paths[0], 'r') as stream:
            attrs = {}
            for key, value in stream.attrs.items():
                if np.ndim(value):
                    continue
                if isinstance(value, bytes):
                    value = value.decode('utf-8')
                elif isinstance(value, np.generic):
                    value = value.item()
                attrs[str(key)] = value
            attrs['observed_actions_length'] = len(stream['actions']) if 'actions' in stream else None
        return attrs, str(paths[0])
    except (ImportError, OSError, ValueError) as exc:
        errors.append({'path': str(paths[0]), 'error': type(exc).__name__ + ': ' + str(exc)})
        return {}, str(paths[0])


def _result_document(value):
    if isinstance(value, dict) and isinstance(value.get('result'), dict):
        combined = dict(value['result'])
        combined.update(value.get('labels', {}))
        return combined
    return value if isinstance(value, dict) else {}


def scan_runs(root, errors):
    root = Path(root).resolve()
    rows, seen_ids = [], {}
    episodes = sorted({p.parent for p in root.rglob('config.yaml')
                       if p.parent.name.startswith('episode_')})
    episodes = sorted(set(episodes) | {p.parent for p in root.rglob('result.json')
                                     if p.parent.name.startswith('episode_')})
    for episode in episodes:
        cfg = read_config(episode / 'config.yaml', errors)
        options = read_json(episode / 'options.json', errors) or {}
        result_path = episode / 'result.json'
        result = _result_document(read_json(result_path, errors))
        if not result:
            alternatives = sorted(episode.glob('episode_*_result.json'))
            if alternatives:
                result_path = alternatives[0]
                result = _result_document(read_json(result_path, errors))
        complete = known_bool(result.get('complete'))
        metadata, h5_path = read_closed_h5_metadata(episode, errors) if complete is True else ({}, None)
        identifier = _first(result.get('episode_id'), metadata.get('episode_id'))
        config_asset = _first(cfg.get('asset_id'), cfg.get('vessel', {}).get('asset_id'))
        source = cfg.get('source', {}).get('vessel')
        asset = _first(result.get('asset_id'), metadata.get('asset_id'), config_asset,
                       Path(source).stem if source else None)
        task = _first(result.get('task_type'), metadata.get('task_type'),
                      cfg.get('env', {}).get('task_type'), options.get('subtask'))
        policy = _first(result.get('policy_id'), options.get('policy_id'))
        failure = result.get('failure_type')
        reason = result.get('termination_reason')
        exclusions = []
        if not result:
            exclusions.append('unclosed_or_no_independent_result')
        if complete is not True:
            exclusions.append('complete_record_not_confirmed')
        if task != 'loading':
            exclusions.append('not_full_loading_task')
        if isinstance(policy, str) and ('preview' in policy.lower() or 'interface' in policy.lower()):
            exclusions.append('preview_or_interface_diagnostic')
        if str(failure).upper() in NON_TASK or str(reason).upper() in NON_TASK:
            exclusions.append('precheck_initialization_service_interruption_or_physics_invalid')
        steps = result.get('actual_control_steps')
        if steps is not None and steps <= 0:
            exclusions.append('no_task_actions')
        if known_bool(result.get('record_valid')) is not True:
            exclusions.append('record_valid_not_confirmed')
        outcome = known_bool(result.get('task_success'))
        if outcome is None:
            exclusions.append('task_outcome_unknown')
        discrepancies = []
        for field in ('task_success', 'record_valid', 'task_type', 'failure_type', 'termination_reason'):
            if field in result and field in metadata:
                left, right = result[field], metadata[field]
                if field in ('task_success', 'record_valid'):
                    left, right = known_bool(left), known_bool(right)
                if left != right:
                    discrepancies.append(field)
        if discrepancies:
            exclusions.append('result_H5_label_disagreement')
        relative = str(episode.relative_to(root))
        run_name = relative.split('/')[0]
        duplicate = seen_ids.get(identifier) if identifier else None
        if duplicate:
            exclusions.append('duplicate_episode_id')
        elif identifier:
            seen_ids[identifier] = relative
        phases = None
        if metadata.get('phase_names_json'):
            try:
                phases = json.loads(metadata['phase_names_json'])
            except (TypeError, ValueError):
                pass
        role = _first(cfg.get('experiment', {}).get('run_role'), cfg.get('collection', {}).get('run_role'))
        rows.append({'run_name': run_name, 'episode_directory': relative,
            'episode_id': identifier, 'asset_id': asset,
            'closed_status': 'COMPLETE_RECORD' if complete is True else 'UNCLOSED_OR_UNKNOWN',
            'complete': complete, 'task_type': task,
            'record_valid': known_bool(result.get('record_valid')), 'task_success': outcome,
            'workflow_success': known_bool(result.get('workflow_success')),
            'failure_type': failure, 'termination_reason': reason,
            'condition_group': _first(metadata.get('condition_group'), cfg.get('experiment', {}).get('condition_group')),
            'scene_version': _first(metadata.get('scene_version'), result.get('scene_version'), cfg.get('version')),
            'mode': cfg.get('env', {}).get('mode'), 'run_role': role,
            'scene_randomization_enabled': cfg.get('env', {}).get('scene_randomization_enabled'),
            'frozen_scene_sha256': metadata.get('frozen_scene_sha256'),
            'controller_version': _first(metadata.get('controller_version'), cfg.get('experiment', {}).get('controller_version')),
            'control_config_sha256': metadata.get('control_config_sha256'),
            'code_commit': metadata.get('code_commit'), 'policy_id': policy,
            'actual_control_steps': steps, 'actual_physics_steps': result.get('actual_physics_steps'),
            'simulation_seconds': _first(result.get('simulation_seconds'), result.get('simulation_duration_s')),
            'wall_seconds': result.get('wall_seconds'),
            'release_observed': known_bool(result.get('release_observed')),
            'retreat_observed': known_bool(result.get('retreat_observed')),
            'stable_after_retreat': known_bool(result.get('stable_after_retreat')),
            'source_slot_cleared': known_bool(result.get('source_slot_cleared')),
            'grasp_success': known_bool(result.get('grasp_success')),
            'transport_success': known_bool(result.get('transport_success')),
            'phase_names': phases, 'physics_quality_flags': result.get('physics_quality_flags'),
            'post_retreat_window': result.get('post_retreat_window'),
            'terminal_window': result.get('terminal_window'),
            'qualification_exclusions': exclusions, 'result_H5_label_disagreements': discrepancies,
            'duplicate_of': duplicate,
            'qualified_success': None, 'qualified_failure': None,
            'qualification_evidence': 'unavailable_until_explicit_collection_audit',
            'result_path': str(result_path) if result else None,
            'result_sha256': sha(result_path) if result else None,
            'H5_path': h5_path,
            'side_video': str(episode / 'side_camera.mp4') if (episode / 'side_camera.mp4').is_file() else None,
            'wrist_video': str(episode / 'wrist_camera.mp4') if (episode / 'wrist_camera.mp4').is_file() else None})
    # Summary files are evidence links, not additional episodes or duplicate quotas.
    summaries = [{'path': str(p), 'sha256': sha(p)} for p in sorted(root.rglob('summary.json'))]
    return rows, summaries


def launch_only_attempts(root, rows, errors):
    """Report launches with no episode separately; do not call them task failures."""
    root = Path(root).resolve()
    result = []
    episode_paths = [(root / r['episode_directory']).resolve() for r in rows]
    for path in sorted(root.rglob('launch_config.yaml')):
        launch = path.parent
        if any(p.is_relative_to(launch) for p in episode_paths):
            continue
        cfg = read_config(path, errors)
        result.append({'launch_directory': str(launch.relative_to(root)),
            'asset_id': _first(cfg.get('asset_id'), cfg.get('vessel', {}).get('asset_id')),
            'status': 'NO_EPISODE_RECORD_AVAILABLE', 'task_success': None,
            'actual_physics_steps': None, 'failure_type': None,
            'counts_as_task_failure': False,
            'launch_config_path': str(path), 'launch_config_sha256': sha(path)})
    return result


def attach_collection_audit(rows, audit_path, errors):
    if audit_path is None:
        return None
    audit = read_json(audit_path, errors)
    if not audit:
        return None
    if audit.get('schema') != 'labsim.Size_v1.collection_audit.v1':
        raise ValueError('Expected existing Size_v1 collection-audit schema')
    by_id = {r['labels'].get('episode_id'): r for r in audit.get('episodes', [])
             if isinstance(r.get('labels'), dict) and r['labels'].get('episode_id')}
    for row in rows:
        entry = by_id.get(row['episode_id'])
        if entry is None:
            continue
        errors_found = list(row['qualification_exclusions'])
        if entry.get('admission_errors'):
            errors_found.append('collection_audit_admission_errors')
        if row.get('frozen_scene_sha256') != audit.get('frozen_scene_sha256'):
            errors_found.append('frozen_scene_not_matched')
        row['qualified_success'] = bool(entry.get('success') is True and not errors_found)
        row['qualified_failure'] = bool(entry.get('failure') is True and not errors_found)
        row['qualification_exclusions'] = sorted(set(errors_found))
        row['qualification_evidence'] = str(Path(audit_path).resolve())
    return {'path': str(Path(audit_path).resolve()), 'sha256': sha(audit_path),
        'frozen_scene_sha256': audit.get('frozen_scene_sha256'),
        'original_audit_qualified_success_count': audit.get('qualified_success_count'),
        'original_audit_qualified_failure_count': audit.get('qualified_failure_count'),
        'reader_validation': audit.get('reader_validation')}


def candidate_table(geometry, rows):
    table = []
    for path in sorted(Path(geometry).glob('cuvette_xy_*.json')):
        candidate = json.loads(path.read_text())
        if 'orientations' not in candidate:
            continue
        ori = candidate['orientations']
        best = max(ori, key=lambda r: r.get('best_sweep_clearance_mm') or -1)
        runs = [r for r in rows if r['asset_id'] == candidate['asset_id'] and not r['duplicate_of']]
        physical = [r for r in runs if r.get('actual_physics_steps') is not None and r['actual_physics_steps'] > 0]
        loading = [r for r in runs if r['task_type'] == 'loading'
                   and not any(x in r['qualification_exclusions'] for x in
                       ('preview_or_interface_diagnostic', 'precheck_initialization_service_interruption_or_physics_invalid', 'no_task_actions'))]
        observed = [r['task_success'] for r in loading if r['task_success'] is not None]
        success_n, failure_n = observed.count(True), observed.count(False)
        if not observed:
            task_result = None
        else:
            task_result = 'SUCCESS_AND_FAILURE_OBSERVED' if success_n and failure_n else 'SUCCESS_OBSERVED' if success_n else 'FAILURE_OBSERVED'
        certificate = candidate['continuous_vertical_sweep_certificate_any_four_yaw']
        support = best.get('support')
        table.append({'asset_id': candidate['asset_id'], 'nominal_outer_width_mm': candidate['width_nominal_mm'],
            'actual_outer_dimensions_mm': candidate['actual_outer_dimensions_mm'],
            'entry_required_slice_four_yaw_XY_domain_present': candidate['entry_any_four_yaw_XY_domain_present'],
            'full_path_feasible': True if certificate else None,
            'conservative_full_path_certificate_present': certificate,
            'full_path_status': 'POSITIVE_CONSERVATIVE_CERTIFICATE' if certificate else 'NOT_CERTIFIED',
            'conservative_XY_clearance_lower_bound_mm': best.get('best_sweep_clearance_mm'),
            'best_yaw_local_deg': best['yaw_deg'] if best.get('best_offset_mm') else None,
            'best_seat_local_offset_mm': best.get('best_offset_mm'),
            'support_geometry_COM_in_sampled_hull': support.get('COM_XY_inside_sampled_support_hull') if support else None,
            'support_geometry_margin_mm': support.get('COM_to_sampled_support_hull_boundary_mm') if support else None,
            'physical_execution_observed': True if physical else None,
            'physics_validation': 'ACTUAL_PHYSICS_RECORDED_REVIEW_QUALITY_FLAGS' if physical else None,
            'complete_task_result': task_result,
            'actual_started_episode_count': len(runs), 'closed_episode_count': sum(r['complete'] is True for r in runs),
            'observed_loading_success_count': success_n, 'observed_loading_failure_count': failure_n,
            'observed_loading_unknown_count': sum(r['task_success'] is None for r in loading),
            'actual_run_directories': [r['episode_directory'] for r in runs],
            'physics_quality_flags': sorted({f for r in runs for f in (r.get('physics_quality_flags') or [])}),
            'physical_stability_after_release_observed': True if any(r['stable_after_retreat'] is True for r in runs) else None,
            'geometry_note': '10.70mm is the largest sampled positive conservative certificate, not a universal size limit;10.72–11.00mm remains unclassified for full path; entry rejects apply only to the four stated upright yaws'})
    return sorted(table, key=lambda r: r['nominal_outer_width_mm'], reverse=True)


def write_csv(path, rows, fallback_fields):
    fields = list(rows[0]) if rows else list(fallback_fields)
    with Path(path).open('x', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: json.dumps(v, ensure_ascii=False, separators=(',', ':'))
                if isinstance(v, (dict, list)) else v for k, v in row.items()})


def summarize(root, geometry, output, *, collection_audit=None, verification_prefixes=()):
    root, geometry, output = Path(root).resolve(), Path(geometry).resolve(), Path(output).resolve()
    if not root.is_dir() or not geometry.is_dir():
        raise FileNotFoundError('Output root and geometry evidence directory must exist')
    if output.exists():
        raise FileExistsError('Refusing to overwrite an existing summary directory')
    errors = []
    rows, summaries = scan_runs(root, errors)
    launch_only = launch_only_attempts(root, rows, errors)
    audit = attach_collection_audit(rows, collection_audit, errors)
    candidates = candidate_table(geometry, rows)
    verification = [r for r in rows if r['mode'] == 'standard' and
        (r['run_role'] == 'standard_validation' or any(r['run_name'].startswith(p) for p in verification_prefixes))]
    successes = [r for r in rows if r['qualified_success'] is True]
    failures = [r for r in rows if r['qualified_failure'] is True]
    quota = {'status': 'CHECKED_AGAINST_EXPLICIT_COLLECTION_AUDIT' if audit else 'QUALIFICATION_UNAVAILABLE_NO_COLLECTION_AUDIT',
        'qualified_success_count': len(successes) if audit else None,
        'qualified_failure_count': len(failures) if audit else None,
        'success_target': 20, 'failure_target': 20,
        'success_missing': max(0, 20 - len(successes)) if audit else None,
        'failure_missing': max(0, 20 - len(failures)) if audit else None,
        'unqualified_or_unknown_episode_count': len(rows) - len(successes) - len(failures),
        'qualification_unknown_count': sum(r['qualified_success'] is None for r in rows),
        'condition_groups': {name: {'qualified_success': sum(r['condition_group'] == name for r in successes) if audit else None,
            'qualified_failure': sum(r['condition_group'] == name for r in failures) if audit else None}
            for name in ('natural', 'deterministic_action_deviation')},
        'qualification_evidence': audit, 'raw_labels_modified': False}
    standard5 = {'requested_count': 5, 'selection': {'explicit_run_prefixes': list(verification_prefixes),
            'config_role': 'experiment.run_role or collection.run_role=standard_validation'},
        'selected_episode_count': len(verification),
        'closed_record_count': sum(r['complete'] is True for r in verification),
        'independently_scored_success_count': sum(r['task_success'] is True for r in verification),
        'independently_scored_failure_count': sum(r['task_success'] is False for r in verification),
        'outcome_unknown_count': sum(r['task_success'] is None for r in verification),
        'qualified_success_count': sum(r['qualified_success'] is True for r in verification) if audit else None,
        'status': 'NOT_SELECTED_OR_NOT_STARTED' if not verification else 'AT_LEAST_FIVE_CLOSED' if sum(r['complete'] is True for r in verification) >= 5 else 'INCOMPLETE',
        'all_five_successful': True if len(verification) >= 5 and all(r['task_success'] is True and r['complete'] is True for r in verification) else False if any(r['task_success'] is False for r in verification) else None,
        'episodes': [r['episode_directory'] for r in verification]}
    summary = {'schema': 'labsim.Size_v1.combined_results.v1', 'root': str(root),
        'geometry_directory': str(geometry), 'geometry_summary_sha256': sha(geometry / 'family_summary.json'),
        'original_seat': 'candidate_far_hinge; unchanged original geometry and settings',
        'geometry_boundary_scope': '10.70mm is the maximum sampled positive conservative full-path certificate.10.72–11.00mm full path is unknown/not certified, not universally impossible.11.02mm and larger tested widths fail the required entrance slice at the four stated upright yaws; no arbitrary6DOF claim.',
        'raw_label_and_asset_edits': False, 'run_count': len(rows), 'run_read_errors': errors,
        'launch_attempts_without_episode': launch_only,
        'run_summary_files_not_double_counted': summaries,
        'candidate_count': len(candidates), 'standard5': standard5,
        'collection20_success20_failure': quota, 'random10_required': False,
        'candidates': candidates, 'runs': rows}
    output.mkdir(parents=True, exist_ok=False)
    (output / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    write_csv(output / 'candidate_results.csv', candidates, ('asset_id',))
    write_csv(output / 'actual_runs.csv', rows, ('run_name', 'episode_id', 'task_success'))
    write_csv(output / 'launch_only_attempts.csv', launch_only, ('launch_directory', 'task_success', 'status'))
    write_csv(output / 'standard5_runs.csv', verification, ('run_name', 'episode_id', 'task_success'))
    write_csv(output / 'collection_status.csv', [quota], ('status',))
    text = ['# Size_v1 当前尺寸与实际运行结果\n',
        '仅读取已有文件；未完成或未知结果保留null，CSV空单元格表示未知。此脚本不运行仿真、不改变资产或标签。\n',
        '候选表字段：asset_id、实际外尺寸、入口四方位全XY域、全路径正证书、保守侧向余量、静态承托、实际物理记录、完整任务结果。\n',
        summary['geometry_boundary_scope'] + '\n',
        '入口可行不等于全深可行，几何正证书不等于PhysX烹饪形状核验、释放稳定或任务成功。\n',
        f"已发现{len(rows)}条episode目录，{sum(r['complete'] is True for r in rows)}条具备完成记录。summary.json重复汇总不另计episode。\n",
        '5次standard验证只纳入显式run前缀或standard_validation角色；开发preview、预插入和短预算接口记录不凑入验收。\n',
        '20+20配额必须指定既有validate_lab_cuvette_size_v1_data.py输出的collection_audit；未提供时资格计数保持null。自然失败和确定性动作偏差分组。\n',
        '本轮不要求random10。冻结场景、读取验证与真实物理结论仍以原始episode及collection audit为依据。\n']
    (output / 'README.md').write_text('\n'.join(text), encoding='utf-8')
    return summary


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, default=DEFAULT_ROOT, help='Existing outputs tree; arbitrary new output root supported')
    p.add_argument('--geometry', type=Path, default=DEFAULT_GEOMETRY)
    p.add_argument('--output', type=Path, required=True, help='Must be a NEW directory')
    p.add_argument('--collection-audit', type=Path)
    p.add_argument('--verification-run-prefix', action='append', default=[])
    a = p.parse_args(argv)
    result = summarize(a.root, a.geometry, a.output, collection_audit=a.collection_audit,
        verification_prefixes=a.verification_run_prefix)
    print(json.dumps({'output': str(a.output), 'candidate_count': result['candidate_count'],
        'run_count': result['run_count'], 'standard5': result['standard5']['status'],
        'collection': result['collection20_success20_failure']['status']}, ensure_ascii=False))
    return result


if __name__ == '__main__':
    main()
