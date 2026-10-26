"""JSON/JSONL-only comparison of the two final fixed prefixes; no simulator/H5."""
import csv
import datetime
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from omegaconf import OmegaConf
from scipy.spatial.transform import Rotation

ROOT = Path(__file__).resolve().parents[5]
OUT = Path(__file__).resolve().parent
RUN = ROOT / 'outputs/lab_cuvette_loading/Project_v1_1/fixed_replay_02'
OLD = OUT.parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def safe(value):
    if isinstance(value, dict):
        return {key: safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, np.ndarray)):
        return [safe(item) for item in value]
    return value.item() if isinstance(value, np.generic) else value


def main():
    assert not (OUT / 'audit.json').exists(), 'Retain previous audits; use a separate copy/output for reruns'
    historical = [OLD / name for name in ('legacy_reproduction.json', 'legacy_reproduction.csv',
        'fixed_reproduction/summary.json', 'fixed_reproduction/action_comparison.csv', 'fixed_reproduction/fixed_process_exit.json')]
    history_hashes = {str(p.relative_to(ROOT)): sha(p) for p in historical}
    legacy = json.loads(historical[0].read_text())
    first = json.loads(historical[2].read_text())
    comparisons = {(int(r['sequence']), int(r['action_index'])): r for r in csv.DictReader(historical[3].open())}
    proof = json.loads((RUN / 'process_exit.json').read_text())
    assert proof['process_exited'] is True and proof['exit_code'] == 0
    declared = json.loads((RUN / 'diagnostic_summary.json').read_text())
    assert len(declared) == 2
    rows, episodes, plots = [], [], []
    source_hashes = {str((RUN / n).relative_to(ROOT)): sha(RUN / n) for n in ('process_exit.json', 'diagnostic_summary.json')}
    for sequence, group in enumerate(declared, 1):
        directory = RUN / f'episode_{sequence - 1:04d}'
        names = ['execution_trace.jsonl', 'probe_actions.json', 'initial_debug.json', 'result.json',
            'release_metadata.json', 'project_scene_contract.json', 'robot_tracking_configuration.json', 'config.yaml', 'replay_source.json']
        source_hashes.update({str((directory / name).relative_to(ROOT)): sha(directory / name) for name in names})
        traces = [json.loads(line) for line in (directory / 'execution_trace.jsonl').open()]
        actions = json.loads((directory / 'probe_actions.json').read_text())
        metadata = json.loads((directory / 'release_metadata.json').read_text())
        contract = json.loads((directory / 'project_scene_contract.json').read_text())
        expected = legacy['episodes'][sequence - 1]['source_action_sequence']
        assert len(actions) == len(expected)
        for index, action in enumerate(actions):
            arguments = {k: v for k, v in action['arguments'].items() if k not in ('episode_id', 'observation_id', 'action_id')}
            assert arguments == expected[index]['requested_arguments'] and action['tool'] == expected[index]['tool']
            receipt = action['receipt']
            selected = [r for r in traces if r['action'].get('_executor_action_id') == receipt['execution_action_id']]
            assert len(selected) == receipt['executed_control_ticks']
            start = np.array(action['start_TCP']['position_m'])
            end = np.array(action['actual_endpoint_TCP']['position_m'])
            goal = np.array(receipt['requested_target_TCP']['position_m'])
            points = np.vstack([start] + [r['actual_TCP']['position_m'] for r in selected])
            old = comparisons[(sequence, index)]
            row = dict(sequence=sequence, original_formal_attempt_zero_based=group['original_attempt'], action_index=index,
                tool=action['tool'], requested_duration_s=arguments['duration_s'],
                requested_translation_norm_mm=float(np.linalg.norm(arguments.get('values', [0, 0, 0])[:3])) * 1000,
                legacy_net_displacement_mm=float(old['legacy_endpoint_displacement_mm']),
                legacy_endpoint_error_mm=float(old['legacy_final_position_error_mm']),
                legacy_executed_ticks=int(old['legacy_executed_control_ticks']),
                legacy_executed_duration_s=float(old['legacy_executed_duration_s']),
                first_fix01_net_displacement_mm=float(old['fixed_endpoint_displacement_mm']),
                first_fix01_endpoint_error_mm=float(old['fixed_final_position_error_mm']),
                first_fix01_maximum_path_error_mm=float(old['fixed_maximum_tracking_error_mm']), first_fix01_process_exit_code=139,
                final_fix02_net_displacement_mm=float(np.linalg.norm(end - start)) * 1000,
                final_fix02_endpoint_error_mm=float(np.linalg.norm(end - goal)) * 1000,
                final_fix02_path_length_mm=float(np.linalg.norm(np.diff(points, axis=0), axis=1).sum()) * 1000,
                final_fix02_maximum_path_error_mm=max(r['position_tracking_error_m'] for r in selected) * 1000,
                final_fix02_maximum_TCP_FD_speed_m_s=max(r['actual_TCP_speed_m_s'] for r in selected),
                final_fix02_executed_ticks=len(selected),
                final_fix02_executed_duration_s=receipt['simulation_time_after'] - receipt['simulation_time_before'],
                final_fix02_target_reached=receipt['target_reached'], final_fix02_stop_reason=receipt['stop_reason'],
                final_fix02_process_exit_code=0, original_prefix_arguments_preserved=True,
                endpoint_receipt_consistent=bool(abs(np.linalg.norm(end - goal) - receipt['final_position_error_m']) < 1e-12))
            rows.append(row)
            if index == 2:
                plots.append(dict(sequence=sequence,
                    time=np.array([r['t_after'] for r in selected]) - receipt['simulation_time_before'],
                    error=np.array([r['position_tracking_error_m'] for r in selected]) * 1000))
        cfg = OmegaConf.to_container(OmegaConf.load(directory / 'config.yaml'), resolve=True)
        cfg01 = OmegaConf.to_container(OmegaConf.load(ROOT / f'outputs/lab_cuvette_loading/Project_v1_1/fixed_replay_01/episode_{sequence - 1:04d}/config.yaml'), resolve=True)
        equal = {key: cfg[key] == cfg01[key] for key in ('physics', 'vessel', 'rack', 'scene', 'adapter')}
        assert all(equal.values()) and first['episodes'][sequence - 1]['assets'] == contract['assets']
        episodes.append(dict(sequence=sequence, actions_executed=len(actions), all_target_reached=all(a['receipt']['target_reached'] for a in actions),
            simulation_duration_s=group['result']['simulation_duration_s'], task_success=group['result']['task_success'],
            record_valid=group['result']['record_valid'], termination_reason=group['result']['termination_reason'], metadata=metadata,
            physical_config_equal_to_first_fix01=equal, asset_hashes_equal_to_first_fix01=True,
            tracking_config=json.loads((directory / 'robot_tracking_configuration.json').read_text()),
            runtime_stop_count=sum(r.get('runtime_stop') is not None for r in traces),
            forbidden_contact_count=sum(bool(r.get('forbidden_robot_environment_contact')) for r in traces),
            maximum_per_tick_joint_command_delta_rad=max(float(np.max(abs(np.array(r['command_q9'][:7]) - np.array(r['seed_q7'])))) for r in traces),
            maximum_tracking_bias_m=max(r['robot_tracking']['position_bias_norm_m'] for r in traces),
            maximum_tracking_rotation_bias_rad=max(r['robot_tracking']['rotation_bias_norm_rad'] for r in traces),
            third_action=next(r for r in rows if r['sequence'] == sequence and r['action_index'] == 2)))
    assert all(sha(ROOT / path) == digest for path, digest in {**history_hashes, **source_hashes}.items())
    proof['run_directory'] = str(RUN.relative_to(ROOT))
    audit = dict(schema='labsim.Project_v1_1.final_fixed_prefix_02.audit.v1', audit_UTC=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        source_run=str(RUN.relative_to(ROOT)), process_evidence=proof, PID_absent_observed=not Path('/proc/' + str(proof['pid'])).exists(),
        historical_source_SHA256_unchanged=history_hashes, source_SHA256_unchanged=source_hashes, all_original_prefix_parameters_equal=True,
        all_seven_action_targets_reached=all(r['final_fix02_target_reached'] for r in rows), model_calls=0, HDF5_opened=False, labels_modified=False,
        full_loading_success_claimed=False, episodes=episodes,
        scope='Each end error is relative to its own actual observed start and fixed target. Prior tracking errors can change the next actual start.',
        attribution_limit='Final pipeline includes continuous IK, wrapper fixes, bounded robot feedback and shutdown changes; not a one-factor causal experiment.',
        preserved_history='Legacy03 real executor failures and fixed01 exit139 remain unchanged; final fixed02 is a separate clean exit0 run.',
        limitations=['Legacy sequence2 third action stopped after1.9s/114ticks; final executes full2s/120ticks.',
            'Final third-action path peaks remain about0.25–0.37mm; endpoint improvement is not a whole-path precision guarantee.',
            'Two deterministic robot motion prefixes, not GPT task performance, fine contact loading or real calibration.'])
    (OUT / 'audit.json').write_text(json.dumps(safe(audit), ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    with (OUT / 'action_comparison.csv').open('x', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8), constrained_layout=True)
    x, width = np.arange(2), .24
    thirds = [e['third_action'] for e in episodes]
    for offset, key, label, color in [(-1, 'legacy_endpoint_error_mm', 'Legacy03', '#D55E00'),
        (0, 'first_fix01_endpoint_error_mm', 'First fix01 (exit139)', '#999999'),
        (1, 'final_fix02_endpoint_error_mm', 'Final fix02 (exit0)', '#0072B2')]:
        values = [r[key] * 1000 for r in thirds]
        bars = axes[0].bar(x + offset * width, values, width, label=label, color=color)
        for bar, value in zip(bars, values):
            axes[0].text(bar.get_x() + bar.get_width()/2, value * 1.12, f'{value:.2f}', ha='center', fontsize=8)
    axes[0].set_yscale('log');axes[0].set_ylim(.5, 1e6)
    axes[0].set_xticks(x, ['Sequence1 / original formal02', 'Sequence2 / original formal03'])
    axes[0].set_ylabel('Third-action endpoint error (µm; log scale)')
    axes[0].set_title('Same requested prefixes; clean final process exit');axes[0].legend(fontsize=8)
    for data, color in zip(plots, ['#0072B2', '#009E73']):
        axes[1].plot(data['time'], data['error'], color=color, label=f"Sequence{data['sequence']}")
    axes[1].set(xlabel='Third-action elapsed simulation time (s)', ylabel='Actual-to-nominal tracking error (mm)',
        title='Final fix02: transient path error remains')
    axes[1].legend();axes[1].grid(alpha=.25);fig.savefig(OUT / 'comparison.png', dpi=160);plt.close(fig)
    lines = ['# final_fixed_prefix_02：完整原动作前缀回归', '',
        '本次进程真实 exit0，supervisor 记录 Popen.wait 返回；审计时 PID 11479 已不存在。两条原动作前缀完整执行 4 / 3 个动作，7 个目标全部到达。未调用模型，不是 GPT 演示或完整装载成功。', '',
        '第三动作仍分别为 world [0,40,0] mm 和 [0,35,-19] mm，各2秒。相对每次实际起点的原目标计算：', '']
    for episode in episodes:
        r = episode['third_action']
        lines.append(f"- 序列{episode['sequence']}：旧执行器净位移 {r['legacy_net_displacement_mm']:.3f} mm、终点误差 {r['legacy_endpoint_error_mm']:.3f} mm；首次修复误差 {r['first_fix01_endpoint_error_mm']*1000:.2f} µm（历史进程 exit139）；本次净位移 {r['final_fix02_net_displacement_mm']:.6f} mm、终点误差 {r['final_fix02_endpoint_error_mm']*1000:.3f} µm，最大瞬态跟踪误差 {r['final_fix02_maximum_path_error_mm']:.5f} mm。")
    lines += ['', '原请求参数逐项一致；原序列2的第三动作在1.9秒终止，本次执行完整2秒。相同请求参数不代表此前跟踪后的实际起点相同。', '',
        '与首次修复相比，physics/vessel/rack/scene/adapter 配置及资产哈希一致；控制、工具封装和退出流程已有变化，不能把全部差异单独归因于补偿。终点改善不代表全程精度，也不等于原座装载或真实标定成功。', '',
        '旧 fixed_replay_01 的 exit139、旧 legacy_replay_03 的执行器失败以及全部原始标签、资产和记录原样保留。未读取或修改 H5。', '',
        '`audit.json`：闭合证据、配置/资产保护、源SHA及解释边界；`action_comparison.csv`：全部7动作的三版本对照；`comparison.png`：终点改善与剩余瞬态误差。', '',
        '物理复现使用新目录且与其他仿真顺序运行：', '', '```bash',
        '"$LABSIM_PYTHON" -m demos.lab_cuvette_project_v1_1.run --backend diagnostic \\',
        '  --probe fixed-replay --attempts 1 2 --headless \\',
        '  --output outputs/lab_cuvette_loading/Project_v1_1/fixed_prefix_new', '```', '',
        '旧分析参见 `../legacy_reproduction.md`、`../fixed_reproduction/README.md`。本目录为新增闭合对照，不覆盖它们。', '']
    (OUT / 'README.md').write_text('\n'.join(lines))
    manifest = dict(files=[dict(path=p.name, bytes=p.stat().st_size, sha256=sha(p)) for p in sorted(OUT.iterdir()) if p.is_file()])
    (OUT / 'artifact_manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps(safe(dict(output=str(OUT.relative_to(ROOT)), third_actions=thirds)), ensure_ascii=False))


if __name__ == '__main__':
    main()
