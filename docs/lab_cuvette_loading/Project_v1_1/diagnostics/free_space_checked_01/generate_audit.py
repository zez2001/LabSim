"""Reproduce this closed-run CPU audit. Reads JSON/JSONL only; no H5 or simulator."""
from __future__ import annotations
import argparse
import csv
import datetime
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from scipy.spatial.transform import Rotation

ROOT = Path(__file__).resolve().parents[5]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rotation(pose):
    return Rotation.from_quat(np.roll(pose['quaternion_wxyz'], -1))


def stats(values):
    a = np.asarray(values, float)
    return dict(count=len(a), minimum=float(a.min()), maximum=float(a.max()), mean=float(a.mean()),
        rms=float(np.sqrt(np.mean(a * a))), p95=float(np.percentile(a, 95)))


def write_json(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def read_episode(directory, declared):
    names = ['probe_actions.json', 'execution_trace.jsonl', 'initial_debug.json', 'result.json',
        'release_metadata.json', 'project_scene_contract.json', 'robot_tracking_configuration.json', 'executor_configuration.json']
    hashes = {str((directory / name).relative_to(ROOT)): sha(directory / name) for name in names}
    actions = json.loads((directory / 'probe_actions.json').read_text())
    rows = [json.loads(line) for line in (directory / 'execution_trace.jsonl').open()]
    initial = json.loads((directory / 'initial_debug.json').read_text())
    result = json.loads((directory / 'result.json').read_text())
    metadata = json.loads((directory / 'release_metadata.json').read_text())
    assert result['complete'] is True
    previous_p = np.array(initial['actual_tcp_position_m'])
    previous_r = Rotation.from_quat(np.roll(initial['actual_tcp_quaternion_wxyz'], -1))
    previous_q = np.array(initial['joints9'])
    previous_t = initial['simulation_time']
    for row in rows:
        dt = row['t_after'] - row['t_before']
        assert dt > 0 and abs(row['t_before'] - previous_t) < 1e-7
        actual_p, actual_q = np.array(row['actual_TCP']['position_m']), np.array(row['actual_q9'])
        actual_r = rotation(row['actual_TCP'])
        fd = (actual_q[:7] - previous_q[:7]) / dt
        speed = float(np.linalg.norm(actual_p - previous_p) / dt)
        row['_audit'] = dict(FD_joint=fd, native_joint=np.array(row['actual_joint_velocities'])[:7],
            TCP_FD_speed=speed, TCP_FD_angular_speed=float((actual_r * previous_r.inv()).magnitude() / dt),
            recorded_TCP_FD_difference=abs(speed - row['actual_TCP_speed_m_s']),
            recorded_joint_FD_difference=float(np.max(abs(abs(fd) - np.array(row['FD_joint_speed_rad_s'])))),
            FK_native_orientation_error=float((rotation(row['actual_joint_FK_TCP']) * actual_r.inv()).magnitude()))
        previous_p, previous_r, previous_q, previous_t = actual_p, actual_r, actual_q, row['t_after']
    probes, paths = [], []
    for action in actions:
        if 'probe_definition' not in action:
            continue
        definition, receipt = action['probe_definition'], action['receipt']
        selected = [r for r in rows if r['action'].get('_executor_action_id') == receipt['execution_action_id']]
        assert len(selected) == receipt['executed_control_ticks']
        start, end, target = action['start_TCP'], action['actual_endpoint_TCP'], receipt['requested_target_TCP']
        p0, p1, goal = (np.array(p['position_m']) for p in (start, end, target))
        requested_delta = np.array(action['arguments']['values'][:3])
        expected_goal = p0 + (requested_delta if definition['frame'] == 'world' else rotation(start).apply(requested_delta))
        direction = (goal - p0) / np.linalg.norm(goal - p0)
        points = np.vstack([p0] + [np.array(r['actual_TCP']['position_m']) for r in selected])
        progress = (points - p0) @ direction
        lateral = np.linalg.norm(points - p0 - progress[:, None] * direction, axis=1)
        endpoint = float(np.linalg.norm(p1 - goal))
        path_error = max(r['position_tracking_error_m'] for r in selected)
        record = dict(group=declared['group'], episode_directory=directory.name, probe_id=definition['probe_id'],
            axis=definition['axis'], sign=definition['sign'], frame=definition['frame'], amplitude_m=definition['amplitude_m'],
            requested_signed_displacement_mm=definition['sign'] * definition['amplitude_m'] * 1000,
            actual_signed_displacement_mm=float((p1 - p0) @ direction) * definition['sign'] * 1000,
            start_time_s=receipt['simulation_time_before'], end_time_s=receipt['simulation_time_after'], control_samples=len(selected),
            anchor_position_error_m=definition['anchor_start_check']['position_error_m'],
            anchor_orientation_error_rad=definition['anchor_start_check']['orientation_error_rad'],
            anchor_reached=definition['anchor_start_check']['reached'], accepted=receipt['accepted'], target_reached=receipt['target_reached'],
            actual_net_displacement_m=float(np.linalg.norm(p1 - p0)),
            target_reconstruction_error_m=float(np.linalg.norm(expected_goal - goal)),
            endpoint_error_to_actual_start_target_m=endpoint,
            endpoint_orientation_error_rad=float((rotation(target) * rotation(end).inv()).magnitude()),
            endpoint_error_to_fixed_anchor_ideal_m=float(np.linalg.norm(p1 - np.array(definition['expected_endpoint_if_exact_anchor']['position_m']))),
            actual_path_length_m=float(np.linalg.norm(np.diff(points, axis=0), axis=1).sum()),
            maximum_lateral_path_deviation_m=float(lateral.max()), maximum_path_tracking_error_m=path_error,
            maximum_path_orientation_error_rad=max(r['orientation_tracking_error_rad'] for r in selected),
            maximum_actual_TCP_FD_speed_m_s=max(r['_audit']['TCP_FD_speed'] for r in selected),
            maximum_native_arm_joint_speed_rad_s=max(float(np.max(abs(r['_audit']['native_joint']))) for r in selected),
            maximum_FD_arm_joint_speed_rad_s=max(float(np.max(abs(r['_audit']['FD_joint']))) for r in selected),
            endpoint_receipt_consistent=abs(endpoint - receipt['final_position_error_m']) < 1e-12,
            path_receipt_consistent=abs(path_error - receipt['maximum_position_tracking_error_m']) < 1e-12)
        probes.append(record)
        paths.append(dict(axis=record['axis'], points=points))
    assert len(probes) == 24 and len({p['probe_id'] for p in probes}) == 24
    last = actions[-1]
    assert last['arguments']['mode'] == 'ee_pose' and last['arguments']['duration_s'] == 3
    hold_rows = [r for r in rows if r['action'].get('_executor_action_id') == last['receipt']['execution_action_id']]
    start_p, start_r = np.array(last['start_TCP']['position_m']), rotation(last['start_TCP'])
    hold_p = np.vstack([start_p] + [r['actual_TCP']['position_m'] for r in hold_rows])
    hold_q = np.array([r['actual_q9'] for r in hold_rows])
    hold_native = np.array([r['actual_joint_velocities'][:7] for r in hold_rows])
    hold_fd = np.array([r['_audit']['FD_joint'] for r in hold_rows])
    native = np.array([r['_audit']['native_joint'] for r in rows])
    fd = np.array([r['_audit']['FD_joint'] for r in rows])
    tracking = [r['robot_tracking'] for r in rows if r.get('robot_tracking')]
    anchor_checks = declared['anchor_checks']
    audit = dict(group=declared['group'], episode_directory=directory.name, metadata=metadata,
        diagnostic_passed=declared['full_diagnostic_passed'], declared_failure=declared['failure'], signed_probes_completed=len(probes),
        simulation_duration_s=result['simulation_duration_s'], control_samples=len(rows), action_records=len(actions),
        task_success=result['task_success'], record_valid=result['record_valid'], physics_trustworthy=result['physics_trustworthy'],
        failure_domain=result['failure_domain'], termination_reason=result['termination_reason'],
        post_retreat_window=result['post_retreat_window'], physics_quality_flags=result['physics_quality_flags'],
        runtime_stop_count=sum(r.get('runtime_stop') is not None for r in rows),
        forbidden_contact_count=sum(bool(r.get('forbidden_robot_environment_contact')) for r in rows),
        all_anchor_checks_reached=all(c['reached'] for c in anchor_checks),
        anchor_position_error_m=stats([c['position_error_m'] for c in anchor_checks]),
        anchor_orientation_error_rad=stats([c['orientation_error_rad'] for c in anchor_checks]),
        endpoint_error_m=stats([p['endpoint_error_to_actual_start_target_m'] for p in probes]),
        endpoint_orientation_error_rad=stats([p['endpoint_orientation_error_rad'] for p in probes]),
        maximum_path_tracking_error_m=max(p['maximum_path_tracking_error_m'] for p in probes),
        maximum_lateral_path_deviation_m=max(p['maximum_lateral_path_deviation_m'] for p in probes),
        maximum_path_orientation_error_rad=max(p['maximum_path_orientation_error_rad'] for p in probes),
        maximum_actual_TCP_FD_speed_m_s=max(r['_audit']['TCP_FD_speed'] for r in rows),
        maximum_actual_TCP_FD_angular_speed_rad_s=max(r['_audit']['TCP_FD_angular_speed'] for r in rows),
        maximum_native_arm_joint_speed_rad_s=float(np.max(abs(native))), maximum_FD_arm_joint_speed_rad_s=float(np.max(abs(fd))),
        maximum_native_minus_FD_arm_speed_rad_s=float(np.max(abs(native - fd))),
        per_joint_native_minus_FD_RMS_rad_s=np.sqrt(np.mean((native - fd)**2, axis=0)).tolist(),
        maximum_recorded_TCP_FD_disagreement_m_s=max(r['_audit']['recorded_TCP_FD_difference'] for r in rows),
        maximum_recorded_joint_FD_disagreement_rad_s=max(r['_audit']['recorded_joint_FD_difference'] for r in rows),
        maximum_FK_native_position_error_m=max(r['FK_vs_native_TCP_position_error_m'] for r in rows),
        maximum_FK_native_orientation_error_rad=max(r['_audit']['FK_native_orientation_error'] for r in rows),
        tracking=dict(sample_count_last=tracking[-1]['sample_count'], actual_updates=sum(t['observation_used'] for t in tracking),
            maximum_position_bias_m=max(t['position_bias_norm_m'] for t in tracking),
            maximum_rotation_bias_rad=max(t['rotation_bias_norm_rad'] for t in tracking),
            position_saturation_count=sum(t['position_saturated'] is True for t in tracking),
            rotation_saturation_count=sum(t['rotation_saturated'] is True for t in tracking)),
        robot_absolute_hold=dict(start_t=last['receipt']['simulation_time_before'], duration_s=last['receipt']['executed_duration_s'],
            control_samples=len(hold_rows), maximum_position_drift_m=float(np.linalg.norm(hold_p - start_p, axis=1).max()),
            maximum_orientation_drift_rad=max(float((rotation(r['actual_TCP']) * start_r.inv()).magnitude()) for r in hold_rows),
            maximum_native_arm_joint_speed_rad_s=float(np.max(abs(hold_native))),
            maximum_FD_arm_joint_speed_rad_s=float(np.max(abs(hold_fd))),
            unique_recorded_arm_q7_rows=len(np.unique(hold_q[:, :7], axis=0)),
            unique_recorded_native_arm_velocity_rows=len(np.unique(hold_native, axis=0)),
            native_arm_velocity_range_per_joint_rad_s=np.ptp(hold_native, axis=0).tolist()),
        initial_robot=dict(joints9=initial['joints9'], TCP=dict(position_m=initial['actual_tcp_position_m'],
            quaternion_wxyz=initial['actual_tcp_quaternion_wxyz'])), source_hashes=hashes)
    audit['all_receipts_consistent'] = all(p['endpoint_receipt_consistent'] and p['path_receipt_consistent'] for p in probes)
    assert all(sha(ROOT / name) == digest for name, digest in hashes.items())
    payload = dict(paths=paths, anchor=probes and declared['actions'][next(i for i, a in enumerate(declared['actions']) if 'probe_definition' in a)]['probe_definition']['return_before']['pose'],
        anchor_checks=anchor_checks, hold_times=np.array([r['t_after'] for r in hold_rows]) - last['receipt']['simulation_time_before'],
        hold_native_peak=np.max(abs(hold_native), axis=1), hold_FD_peak=np.max(abs(hold_fd), axis=1),
        hold_position_drift=np.linalg.norm(hold_p[1:] - start_p, axis=1))
    return audit, probes, payload


def figures(out, audits, probes, payloads):
    plt.rcParams.update({'font.size': 10, 'axes.grid': True, 'grid.alpha': .22})
    colors = ['#0072B2', '#D55E00', '#009E73']
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), constrained_layout=True)
    for audit, color, payload in zip(audits, colors, payloads):
        selected = [p for p in probes if p['group'] == audit['group']]
        axes[0, 0].scatter([p['requested_signed_displacement_mm'] for p in selected], [p['actual_signed_displacement_mm'] for p in selected], color=color, label=audit['group'], s=22, alpha=.7)
        for axis, field, factor in [(axes[0, 1], 'endpoint_error_to_actual_start_target_m', 1e6), (axes[1, 0], 'maximum_path_tracking_error_m', 1e3)]:
            axis.scatter([p['amplitude_m'] * 1000 for p in selected], [p[field] * factor for p in selected], color=color, s=25, alpha=.7)
        axes[1, 1].plot(np.arange(1, len(payload['anchor_checks']) + 1), [c['orientation_error_rad'] * 1000 for c in payload['anchor_checks']], '.-', color=color, label=audit['group'], markersize=4)
    axes[0, 0].plot([-40, 40], [-40, 40], '--', color='.4', linewidth=1)
    axes[0, 0].set(xlabel='Requested signed displacement (mm)', ylabel='Actual projected displacement (mm)', title='72 signed probes; 3 independent resets')
    axes[0, 0].legend()
    axes[0, 1].set(xlabel='Nominal amplitude (mm)', ylabel='Endpoint error (µm)', title='Error to target from the actual observed start')
    axes[1, 0].set(xlabel='Nominal amplitude (mm)', ylabel='Maximum control-boundary error (mm)', title='Transient path error is larger than endpoint error')
    axes[1, 1].set(xlabel='Full-pose anchor return index', ylabel='Orientation error to fixed anchor (mrad)', title='Fixed quaternion, including epilogue returns')
    fig.savefig(out / 'probe_metrics.png', dpi=160)
    plt.close(fig)
    fig, axes = plt.subplots(3, 2, figsize=(12, 9), constrained_layout=True)
    for index, (audit, payload, color) in enumerate(zip(audits, payloads, colors)):
        axes[index, 0].plot(payload['hold_times'], payload['hold_native_peak'], color=color, label='Native instantaneous arm velocity')
        axes[index, 0].plot(payload['hold_times'], payload['hold_FD_peak'], '--', color='.15', label='Interval FD arm velocity')
        axes[index, 0].set(title=audit['group'] + ': 3 s absolute hold', ylabel='Peak |joint speed| (rad/s)', xlabel='Hold time (s)')
        axes[index, 0].legend(fontsize=8)
        axes[index, 1].plot(np.r_[0., payload['hold_times']], np.r_[0., payload['hold_position_drift'] * 1e6], color=color)
        axes[index, 1].set(title='Recorded TCP position drift; not exact physical zero', ylabel='Drift from hold start (µm)', xlabel='Hold time (s)')
    fig.savefig(out / 'hold_velocity_discrepancy.png', dpi=160)
    plt.close(fig)
    fig = plt.figure(figsize=(15, 6))
    axis_colors = dict(X='#D55E00', Y='#009E73', Z='#0072B2')
    for index, (audit, payload) in enumerate(zip(audits, payloads)):
        axis = fig.add_subplot(1, 3, index + 1, projection='3d')
        anchor_p = np.array(payload['anchor']['position_m'])
        anchor_r = rotation(payload['anchor'])
        for path in payload['paths']:
            points = path['points'] - anchor_p
            if audit['group'].endswith('_tcp'):
                points = anchor_r.inv().apply(points)
            points *= 1000
            axis.plot(points[:, 0], points[:, 1], points[:, 2], color=axis_colors[path['axis']], alpha=.7, linewidth=.8)
        axis.set(title=audit['group'] + ': 24 actual probe paths', xlabel='X (mm)', ylabel='Y (mm)', zlabel='Z (mm)')
        axis.set_box_aspect((1, 1, 1));axis.set_xlim(-42, 42);axis.set_ylim(-42, 42);axis.set_zlim(-42, 42)
    fig.subplots_adjust(left=.01, right=.97, bottom=.15, top=.88, wspace=.03)
    fig.text(.5, .035, 'Individual probe paths overlaid; TCP group shown in its fixed anchor frame', ha='center')
    fig.savefig(out / 'actual_probe_paths.png', dpi=160)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, default=ROOT / 'outputs/lab_cuvette_loading/Project_v1_1/free_space_checked_01')
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parent)
    args = parser.parse_args()
    proof = json.loads((args.run / 'process_exit.json').read_text())
    assert proof['process_exited'] is True and proof['exit_code'] == 0
    declared = json.loads((args.run / 'diagnostic_summary.json').read_text())
    assert len(declared) == 3
    args.output.mkdir(parents=True, exist_ok=True)
    outputs = ['audit.json', 'probe_results.csv', 'group_results.csv', 'README.md', 'probe_metrics.png', 'hold_velocity_discrepancy.png', 'actual_probe_paths.png']
    assert not any((args.output / name).exists() for name in outputs), 'Use a new output directory; historical audit is immutable'
    audits, probes, payloads = [], [], []
    for index, group in enumerate(declared):
        audit, records, payload = read_episode(args.run / f'episode_{index:04d}', group)
        audits.append(audit);probes.extend(records);payloads.append(payload)
    assert len(probes) == len({p['probe_id'] for p in probes}) == 72
    assert len({a['metadata']['frozen_scene_sha256'] for a in audits}) == 1
    proof['run_directory'] = str(args.run.relative_to(ROOT))
    whole = dict(schema='labsim.Project_v1_1.free_space_checked.closed_audit.v1',
        audit_UTC=datetime.datetime.now(datetime.timezone.utc).isoformat(), source_run=str(args.run.relative_to(ROOT)),
        actual_process_evidence=proof, process_exit_sha256=sha(args.run / 'process_exit.json'),
        PID_absent_observed_at_audit=not Path('/proc/' + str(proof['pid'])).exists(),
        audit_scope=dict(JSON_and_JSONL_only=True, HDF5_opened=False, source_labels_modified=False,
            raw_files_compressed=False, simulator_or_model_started=False, source_hashes_unchanged_during_read=True),
        groups=audits, total_signed_probes=len(probes), all_diagnostic_groups_passed=all(a['diagnostic_passed'] for a in audits),
        all_endpoints_target_reached=all(p['target_reached'] for p in probes),
        all_receipts_consistent=all(a['all_receipts_consistent'] for a in audits),
        all_delta_frame_targets_consistent=all(p['target_reconstruction_error_m'] < 1e-12 for p in probes),
        identical_actual_reset_robot_states=all(a['initial_robot'] == audits[0]['initial_robot'] for a in audits),
        observed_measurement_issue='Nonzero native arm velocities coexist with identical recorded arm q7/TCP in ep0 hold and submicrometre pose changes with much smaller FD speeds in ep1/ep2. Native and interval FD signals are retained independently. Mechanism remains unknown.',
        limits=['Diagnostic pass is not full loading success; all raw task_success labels remain false.',
            'Endpoint error does not bound transient path error or physics-substep extrema.',
            'Zero recorded hold drift is not an exact physical zero-motion claim, particularly with the native/FD discrepancy.',
            'Native joint velocity is an instantaneous articulation API sample; FD is the interval average. Native TCP velocity is not supplied by execution_trace.',
            'This is one configuration, three reset groups, not real calibration or broad-scene success probability.'])
    external = ROOT / 'docs/lab_cuvette_loading/Project_v1_1/diagnostics/free_space_checked_01_closed_read_archive.json'
    if external.is_file():
        independent = json.loads(external.read_text())
        whole['separate_HDF5_audit'] = dict(path=str(external.relative_to(ROOT)), sha256=sha(external),
            performed_by='separate release audit agent; not this JSONL analysis',
            all_full_reads_and_time_receipt_audits_passed=independent['all_full_H5_reads_and_labels_time_receipt_audits_passed'],
            total_control_transitions=independent['total_control_transitions'],
            all_protected_original_hashes_unchanged=independent['all_protected_original_hashes_unchanged'])
    write_json(args.output / 'audit.json', whole)
    with (args.output / 'probe_results.csv').open('x', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(probes[0]));writer.writeheader();writer.writerows(probes)
    group_records = [dict(group=a['group'], signed_probes=a['signed_probes_completed'], diagnostic_passed=a['diagnostic_passed'],
        simulation_duration_s=a['simulation_duration_s'], maximum_anchor_position_error_um=a['anchor_position_error_m']['maximum'] * 1e6,
        maximum_anchor_orientation_error_mrad=a['anchor_orientation_error_rad']['maximum'] * 1e3,
        maximum_endpoint_error_um=a['endpoint_error_m']['maximum'] * 1e6, maximum_path_error_mm=a['maximum_path_tracking_error_m'] * 1e3,
        maximum_lateral_path_error_mm=a['maximum_lateral_path_deviation_m'] * 1e3,
        hold_position_drift_um=a['robot_absolute_hold']['maximum_position_drift_m'] * 1e6,
        hold_native_peak_rad_s=a['robot_absolute_hold']['maximum_native_arm_joint_speed_rad_s'],
        hold_FD_peak_rad_s=a['robot_absolute_hold']['maximum_FD_arm_joint_speed_rad_s'],
        runtime_stop_count=a['runtime_stop_count'], forbidden_contact_count=a['forbidden_contact_count']) for a in audits]
    with (args.output / 'group_results.csv').open('x', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(group_records[0]));writer.writeheader();writer.writerows(group_records)
    figures(args.output, audits, probes, payloads)
    readme = ['# free_space_checked_01：闭合记录的独立 CPU 审计', '',
        '本次三组完整诊断均完成，每组 24 个 signed probe，共 72 个。原进程 exit 0，process_exit.json 记录 session 40474 / PID 4003768，审计时 `/proc/4003768` 已不存在。此审计只读取 JSON/JSONL，未读取 H5、改写标签或压缩原始记录。', '',
        '原始任务结果均为 `task_success=false / CONTROL_DIAGNOSTIC_COMPLETE / budget`；诊断通过不代表完成器皿装载。`post_retreat_window` 保持 unavailable，稳定结果为 null。', '']
    for g in group_records:
        readme.append(f"- **{g['group']}**：24/24，仿真 {g['simulation_duration_s']:.6f} s；完整回锚最大 {g['maximum_anchor_position_error_um']:.2f} µm / {g['maximum_anchor_orientation_error_mrad']:.4f} mrad；终点最大误差 {g['maximum_endpoint_error_um']:.2f} µm；路径最大跟踪误差 {g['maximum_path_error_mm']:.5f} mm，横向偏离 {g['maximum_lateral_path_error_mm']:.5f} mm。")
    readme += ['', '## 结果边界与测量问题', '',
        '每次平移均从实际观测的固定起点执行，并先恢复固定完整 xyz+wxyz。CSV 分别保存目标相对实际起点的误差、相对理想固定 anchor 的误差、实际净位移、路径长度和控制边界误差；不能把名义幅度当成实际位移，也不能用终点误差代替全程误差。', '',
        '三秒绝对 hold 中，ep0 记录的 TCP 与臂关节 q7 不变，ep1/ep2 的 TCP 最大变化分别为 0.649 / 0.134 µm；三组原生关节速度峰值仍约 0.0245–0.0256 rad/s，明显大于差分速度。两种信号分开保存，未删除或替换。本审计没有确定缓存、休眠或求解器内部机制。记录不变或微小变化不能作为精确物理零运动或真实标定精度的证明。', '',
        '路径最大值仅覆盖控制边界，不是物理子步的严格上界。本文结论限于本配置下的机器人自由空间重复探针；没有验证器皿接触装载，也不能推导 Isaac Sim 的真实微米精度。', '',
        '## 文件与复现', '',
        '- `audit.json`：闭合证据、三组统计、源 SHA256、代码/资产/场景元数据、独立速度与测量限制。',
        '- `probe_results.csv`：72 个实际探针的逐条结果（字段名注明单位）。',
        '- `group_results.csv`：三组的摘要。',
        '- `probe_metrics.png`：实际位移、终点误差、全程误差与完整回锚姿态。',
        '- `actual_probe_paths.png`：各组实际路径叠加；tcp 组投影到固定 anchor 的 TCP 坐标系。',
        '- `hold_velocity_discrepancy.png`：三秒 hold 的原生/差分关节速度与记录的 TCP 漂移。',
        '- `generate_audit.py`：纯 CPU 复现程序；保留原审计，重跑时必须指定新的输出目录。', '',
        '三集实际 reset 的机器人 q9 与 TCP 记录完全一致，场景 fingerprint 一致。另一个审计流程已实际完成三 H5 全读与回执时间链检查；参见 [独立 H5/归档审计](../free_space_checked_01_closed_read_archive.json)。该验证由另一审计代理完成，本文没有打开 H5。', '',
        '```bash', '"$LABSIM_PYTHON" docs/lab_cuvette_loading/Project_v1_1/diagnostics/free_space_checked_01/generate_audit.py \\',
        '  --output outputs/lab_cuvette_loading/Project_v1_1/free_space_checked_01_audit_new', '```', '',
        '此前 `free_space_checked_01_preliminary.json` 是父进程尚在运行时的 ep0 快照，原样保留；本目录为完整闭合后的新增分析。', '']
    with (args.output / 'README.md').open('x', encoding='utf-8') as stream:
        stream.write('\n'.join(readme))
    print(json.dumps(group_records, ensure_ascii=False))


if __name__ == '__main__':
    main()
