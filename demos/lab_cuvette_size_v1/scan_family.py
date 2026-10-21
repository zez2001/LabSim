"""Build and screen a retained cuvette family against unchanged original A.

Coarse width step0.2mm, then0.02mm around observed changes. Every evaluated
width is first retained as an independent registered USD, including failures.
Only geometry runs here; runtime/complete-task fields remain null.
"""
from __future__ import annotations
import argparse
import csv
import json
from pathlib import Path
import time
from demos.lab_cuvette_size_v1.build_assets import build, asset_id, write, sha, ROOT
from demos.lab_cuvette_size_v1.geometry_audit import load_geometry, evaluate, _plot

COARSE = [round(12.5 - .2 * i, 2) for i in range(16)] + [10.0]


def run(config, output, geometry_site):
    import numpy as np
    from omegaconf import OmegaConf
    cfg = OmegaConf.to_container(OmegaConf.load(config), resolve=True)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    registry = build(COARSE)
    results, shapes = {}, {}

    def measure(widths):
        nonlocal registry
        registry = build(widths)
        for width in sorted(set(widths), reverse=True):
            ident = asset_id(width)
            if ident in results:
                continue
            cc = json.loads(json.dumps(cfg))
            cc['source']['vessel'] = registry['assets'][ident]['asset_path']
            cc['source']['vessel_collision'] = cc['source']['vessel']
            cc['asset_id'] = ident
            g = load_geometry(cc, geometry_site)
            rows = []
            for yaw in (0, 90, 180, 270):
                result, shape = evaluate(g, yaw_deg=yaw)
                rows.append(result)
                if yaw == 0:
                    shapes[ident] = shape
            results[ident] = {'asset_id': ident, 'width_nominal_mm': width,
                'asset_sha256': registry['assets'][ident]['asset_sha256'],
                'actual_outer_dimensions_mm': g['cup'].extents * 1000,
                'entry_any_four_yaw_XY_domain_present': any(r['entry_positive_clearance_XY_domain_present'] for r in rows),
                'continuous_vertical_sweep_certificate_any_four_yaw': any(r['conservative_full_path_positive_XY_domain_present'] for r in rows),
                'orientations': rows, 'physics_validation': None,
                'full_task_success': None, 'released_stability': None}
            write(output / (ident + '.json'), results[ident])

    measure(COARSE)
    finer = set()
    ordered = sorted(results.values(), key=lambda r: r['width_nominal_mm'])
    for key in ('entry_any_four_yaw_XY_domain_present', 'continuous_vertical_sweep_certificate_any_four_yaw'):
        for a, b in zip(ordered, ordered[1:]):
            if a[key] != b[key]:
                finer.update(round(x, 2) for x in np.arange(a['width_nominal_mm'], b['width_nominal_mm'] + .001, .02))
    measure(finer)
    ordered = sorted(results.values(), key=lambda r: r['width_nominal_mm'], reverse=True)
    table = []
    for r in ordered:
        best = max(r['orientations'], key=lambda x: x['best_sweep_clearance_mm'] or -1)
        table.append({'asset_id': r['asset_id'], 'nominal_outer_width_mm': r['width_nominal_mm'],
            'actual_outer_X_mm': float(r['actual_outer_dimensions_mm'][0]),
            'actual_outer_Y_mm': float(r['actual_outer_dimensions_mm'][1]),
            'actual_height_mm': float(r['actual_outer_dimensions_mm'][2]),
            'entry_any_four_yaw_positive_domain': r['entry_any_four_yaw_XY_domain_present'],
            'conservative_continuous_vertical_path_certified': r['continuous_vertical_sweep_certificate_any_four_yaw'],
            'recommended_yaw_local_deg': best['yaw_deg'] if best['best_offset_mm'] else None,
            'best_X_offset_mm': best['best_offset_mm'][0] if best['best_offset_mm'] else None,
            'best_Y_offset_mm': best['best_offset_mm'][1] if best['best_offset_mm'] else None,
            'conservative_XY_clearance_lower_bound_mm': best['best_sweep_clearance_mm'],
            'sampled_support_COM_contained': best['support']['COM_XY_inside_sampled_support_hull'] if best['support'] else None,
            'physics_validation': 'NOT_RUN', 'complete_task_result': 'NOT_RUN',
            'boundary_note': 'Conservative sweep failure is inconclusive; entrance gate is a necessary exact polygonal test for the four stated upright yaws'})
    with (output / 'candidate_dimensions_and_geometry.csv').open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, list(table[0])); writer.writeheader(); writer.writerows(table)
    safe = [r['width_nominal_mm'] for r in ordered if r['continuous_vertical_sweep_certificate_any_four_yaw']]
    entry = [r['width_nominal_mm'] for r in ordered if r['entry_any_four_yaw_XY_domain_present']]
    rejected = [r['width_nominal_mm'] for r in ordered if not r['entry_any_four_yaw_XY_domain_present']]
    recommended = results['cuvette_xy_1000']
    cc = json.loads(json.dumps(cfg))
    cc['source']['vessel'] = registry['assets']['cuvette_xy_1000']['asset_path']
    cc['source']['vessel_collision'] = cc['source']['vessel']
    g = load_geometry(cc, geometry_site)
    fixed, fixed_shapes = evaluate(g, yaw_deg=0, offset_mm=[.65, .001])
    _plot(output / 'recommended_1000_original_A_path.png', fixed_shapes, fixed)
    _plot(output / 'control_1250_original_A_path.png', shapes['cuvette_xy_1250'], results['cuvette_xy_1250']['orientations'][0])
    summary = {'schema': 'labsim.Size_v1.family_geometry.v1',
        'source_control_asset': 'assets/lab_cuvette_loading/V0_demo04/vessel_125_mm.usda',
        'source_control_sha256': registry['assets']['cuvette_xy_1000']['source']['sha256'],
        'selected_original_seat': 'candidate_far_hinge',
        'original_instrument_path': str(g['instrument_path'].relative_to(ROOT)),
        'original_instrument_sha256': sha(g['instrument_path']),
        'original_seat_unmodified': True, 'registered_count': len(registry['assets']),
        'evaluated_count': len(results), 'coarse_step_mm': .2, 'fine_step_mm': .02,
        'search_width_range_mm': [min(r['width_nominal_mm'] for r in ordered), max(r['width_nominal_mm'] for r in ordered)],
        'upright_yaws_deg': [0, 90, 180, 270],
        'translation_search': 'Same full polygonal boundedXY configuration-space algorithm at every width/yaw; not centre-only',
        'largest_sampled_positive_continuous_sweep_certificate_mm': max(safe) if safe else None,
        'largest_sampled_positive_required_entrance_domain_mm': max(entry) if entry else None,
        'smallest_sampled_entrance_rejected_mm': min(rejected) if rejected else None,
        'recommended_initial_physics_candidate': {'asset_id': 'cuvette_xy_1000',
            'width_mm': 10.0, 'seat_local_target_offset_m': [.00065, .000001, 0],
            'bottom_above_original_seat_base_m': g['floor'],
            'candidate_insertion_depth_m': g['rim'] - g['floor'],
            'fixed_offset_geometry': fixed,
            'reason': 'Retains more width than9.5mm lower search endpoint with approximately0.35mm conservative lateral sweep margin, unlike near10.7mm zero-margin boundary; geometric support hull contains assumedCOM. Physics/complete task still required.'},
        'range_scope': 'Observed tested size hypotheses, not a real specimen inference. Positive conservative sweep means clearance of authored triangle surfaces. False conservative gate is inconclusive; four-yaw entrance rejects do not exclude arbitrary inclined6DOF paths.',
        'runtime_started': False, 'physics_validation': None,
        'full_task_success': None, 'real_calibrated': False,
        'wall_clock_s': time.monotonic() - started}
    write(output / 'family_summary.json', summary)
    write(output / 'asset_registry_snapshot.json', registry)
    (output / 'README.md').write_text(
        '# Size_v1：原A座固定的比色皿横向尺寸筛选\n\n'
        '原12.5mm源资产、整机和A座字节保持；所有候选先生成独立USD再评估，含不可通过和边界版本。'
        '统一XY仿射、Z67.5mm和底部基准不变；视觉与28块厚壁碰撞输入同步；20g继续是假设。'
        '固定总质量和均匀材料体分布模型下重新积分COM/惯量，数值密度随宽度变；不声称密度固定。\n\n'
        '入口判据使用原座28.5mm真实闭合孔域及器皿底上1mm实际实心截面，计算三角形对Minkowski禁区并集，'
        '检查每个直立方位的全部有界XY平移域。全深路径正证书使用实际视觉XY外轮廓的保守竖直扫掠，'
        '与原座承托面上0.1um以上所有实际三角面投影求配置空间；垂直壁退化线段也保留。'
        '这是输入三角表面安全下界，未读取PhysX烹饪形状。负的保守证书只表示未证明，不能写成全局不可能。'
        '未搜索任意倾斜6DoF路径。\n\n'
        '底面由原座中心向下射线得到约2mm，候选插入深度29−2=27mm，仍非实测操作深度。'
        '最低实际平底三角形内15×15采样下射线核查承托；COM位于命中点凸包仅证明静态几何候选，'
        '释放后稳定必须实际运行。推荐10.00mm、原座局部XY=(+0.650,+0.001)mm，'
        '保守连续竖直扫掠侧向余量约0.350mm。没有扩大座、删凸起或更改接触参数。\n\n'
        '候选表中的NOT_RUN/null是尚未物理验证，不能计作任务成败或采集配额。'
        '原座非封闭网格，故不虚构全局实体符号距离；孔域和投影分别保留其算法适用范围。\n', encoding='utf-8')
    print(json.dumps({'evaluated_count': len(results), 'largest_safe': max(safe), 'largest_entry': max(entry), 'recommended': 'cuvette_xy_1000', 'output': str(output)}))
    return summary


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config', required=True)
    p.add_argument('--output', required=True)
    p.add_argument('--geometry-site', required=True)
    a = p.parse_args()
    run(a.config, a.output, a.geometry_site)
