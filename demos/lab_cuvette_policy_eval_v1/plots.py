"""Generate six static scientific figures from actual formal episode analysis.

No model calls, simulation, source-data edits or hand-entered result numbers.
English labels keep portable rendering independent of Chinese font packages.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import textwrap

from .analysis import STAGE_ORDER, file_sha256, finite, json_rows, metric, read_json


STAGE_LABELS = ('Approach', 'Grasp', 'Extract', 'Held XY 50 mm', 'Pre-insert',
    'Align', 'Insert', 'Support', 'Detach', 'Retreat', 'Stable 3 s')
COLORS = ('#1769aa', '#d76a1b', '#238363', '#8e4ea8')
FIGURE_NAMES = ('01_stage_rates.png', '02_episode_farthest_stage.png',
    '03_termination_types.png', '04_representative_progress.png',
    '05_applicable_target_metrics.png', '06_latency_and_wall_time.png')


def select_representatives(episodes, limit=4):
    """All started formal cases up to four; otherwise group medians and failures.

    Median rank is a transparent typical-case rule rather than best-case
    selection.  A success, if present, and a failure can be added without
    replacing the first representative of another group.
    """
    formal = [e for e in episodes if e.get('purpose') == 'formal' and e.get('started')]
    ordered = sorted(formal, key=lambda e: (e['group_id'], e['trial_id']))
    if len(ordered) <= limit:
        return ordered, 'all started formal episodes (at most four)'
    selected = []
    groups = sorted({e['group_id'] for e in ordered})
    for group in groups:
        cases = sorted((e for e in ordered if e['group_id'] == group),
            key=lambda e: (e.get('farthest_stage_rank', 0), e['trial_id']))
        if len(selected) < limit:
            selected.append(cases[(len(cases)-1)//2])
    for success in (True, False):
        for group in groups:
            if len(selected) >= limit:
                break
            cases = [e for e in ordered if e['group_id'] == group and e.get('task_success') is success and e not in selected]
            if cases:
                selected.append(cases[0])
    return selected, 'lower-median farthest-stage rank per group, then first success/failure cases if space permits'


def _curve(episode):
    p = Path(episode['progress_dir'])/'progress_v1.jsonl.gz'
    data = {k: [] for k in ('time', 'coverage', 'effective_insertion', 'xy_mm', 'tilt_deg', 'applicable_progress')}
    for row_index, row in enumerate(json_rows(p)):
        snapshots = [row.get('before'), row.get('after')] if row_index == 0 else [row.get('after')]
        for s in snapshots:
            if not isinstance(s, dict) or finite(s.get('t')) is None:
                continue
            gates = (s.get('insertion_gate_details') or {}).get('gates') or {}
            region = (gates.get('entrance_region') or {}).get('value') is True and (gates.get('current_attempt_route') or {}).get('value') is True
            applicable = s.get('insertion_progress_applicable') is True
            def value(v, scale=1.):
                return finite(v)*scale if finite(v) is not None else math.nan
            data['time'].append(float(s['t']))
            data['coverage'].append(value(s.get('coverage_progress')))
            data['effective_insertion'].append(value(s.get('valid_insertion_progress')))
            data['xy_mm'].append(value(metric(s, 'target_lateral_error_m'), 1000.) if region else math.nan)
            data['tilt_deg'].append(value(metric(s, 'target_tilt_rad'), 180./math.pi) if region else math.nan)
            data['applicable_progress'].append(value(s.get('valid_insertion_progress')) if applicable else math.nan)
    return data


def _wrap(text, width=24):
    return '\n'.join(textwrap.wrap(str(text).replace('_', ' '), width))


def plot_results(result_path, manifest_path, output):
    """Return a figure receipt; refuse empty formal datasets and overwrites."""
    result_path, manifest_path, output = map(Path, (result_path, manifest_path, output))
    result, manifest = read_json(result_path), read_json(manifest_path)
    if result.get('manifest_sha256') != file_sha256(manifest_path):
        raise ValueError('Trial manifest differs from the analyzed source manifest')
    formal = [e for e in result['episodes'] if e.get('purpose') == 'formal' and e.get('started')]
    if not formal:
        raise ValueError('No started formal episodes: do not draw nonexistent results')
    if output.exists():
        raise FileExistsError(output)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 9,
        'axes.titlesize': 11, 'axes.labelsize': 10, 'savefig.dpi': 160,
        'axes.spines.top': False, 'axes.spines.right': False})
    output.mkdir(parents=True)
    groups = sorted({e['group_id'] for e in formal})
    labels = {g.get('group_id'): g.get('label', g.get('group_id')) for g in manifest.get('groups', []) if isinstance(g, dict)}
    names = {g: str(labels.get(g, g)) for g in groups}
    color = {g: COLORS[i % len(COLORS)] for i, g in enumerate(groups)}
    selected, selection_rule = select_representatives(result['episodes'])
    curves = {e['trial_id']: _curve(e) for e in selected}
    receipts = []

    def save(fig, name, description):
        fig.savefig(output/name, bbox_inches='tight', facecolor='white')
        plt.close(fig)
        receipts.append(dict(path=name, sha256=file_sha256(output/name), description=description))

    fig, ax = plt.subplots(figsize=(12, 4.6))
    x, width = np.arange(len(STAGE_ORDER)), .75/len(groups)
    for index, group in enumerate(groups):
        stats = result['groups'][group]['stage_rates']
        rate = [stats[s]['achieved_per_started']['rate'] for s in STAGE_ORDER]
        lower = [r-stats[s]['achieved_per_started']['lower'] for r, s in zip(rate, STAGE_ORDER)]
        upper = [stats[s]['achieved_per_started']['upper']-r for r, s in zip(rate, STAGE_ORDER)]
        offset = x+(index-(len(groups)-1)/2)*width
        ax.bar(offset, rate, width=width, color=color[group], alpha=.85, label=names[group],
            yerr=[lower, upper], capsize=2, error_kw={'linewidth': .8})
        for xx, yy, stage in zip(offset, rate, STAGE_ORDER):
            s = stats[stage]
            ax.annotate(f"{s['achieved']}/{s['started_denominator']}\nU={s['unknown']}",
                (xx, yy), xytext=(0, 5), textcoords='offset points', ha='center', fontsize=6.5)
    ax.set(xticks=x, xticklabels=STAGE_LABELS, ylim=(0, 1.16), ylabel='Confirmed episodes / all started formal episodes',
        title='Stage confirmation rates with 95% Wilson intervals')
    ax.tick_params(axis='x', rotation=35)
    ax.legend(loc='upper right', fontsize=8)
    ax.grid(axis='y', alpha=.2)
    fig.text(.07, -.04, 'U = unknown evidence episodes. Confirmed / started is observed achievement coverage; known-only rates and counts remain in the result tables.', fontsize=8)
    fig.tight_layout()
    save(fig, FIGURE_NAMES[0], 'First physical confirmations, explicit started denominators and unknown counts; Wilson 95% intervals.')

    ordered = sorted(formal, key=lambda e: (e['group_id'], e['trial_id']))
    fig, ax = plt.subplots(figsize=(11, max(3.1, .38*len(ordered)+1.5)))
    y = np.arange(len(ordered))
    ranks = [e.get('farthest_stage_rank', 0) for e in ordered]
    ax.barh(y, ranks, color=[color[e['group_id']] for e in ordered], height=.62)
    ax.set(yticks=y, yticklabels=[e['trial_id'] for e in ordered], xlim=(0, len(STAGE_ORDER)+.8),
        xticks=range(len(STAGE_ORDER)+1), xticklabels=['None', *STAGE_LABELS],
        title='Farthest physically confirmed milestone in each started formal episode')
    ax.tick_params(axis='x', labelrotation=35)
    ax.invert_yaxis()
    for yy, rank, e in zip(y, ranks, ordered):
        ax.text(rank+.1, yy, 'success' if e.get('task_success') is True else 'incomplete', va='center', fontsize=8)
    ax.grid(axis='x', alpha=.2)
    fig.tight_layout()
    save(fig, FIGURE_NAMES[1], 'One row per actual started formal episode; held 50 mm translation and pre-insertion arrival remain separate.')

    terminations = sorted({e.get('termination_reason') or 'unknown' for e in formal})
    fig, ax = plt.subplots(figsize=(10, max(3.3, .45*len(terminations)+1.7)))
    y = np.arange(len(terminations))
    height = .75/len(groups)
    for index, group in enumerate(groups):
        counts = result['groups'][group]['termination_counts']
        yy = y+(index-(len(groups)-1)/2)*height
        values = [counts.get(t, 0) for t in terminations]
        ax.barh(yy, values, height=height, color=color[group], label=names[group])
        for yi, value in zip(yy, values):
            ax.text(value+.03, yi, str(value), va='center', fontsize=8)
    ax.set(yticks=y, yticklabels=[_wrap(t, 38) for t in terminations], xlabel='Actual started episodes',
        title='Original termination reasons (no failures removed)')
    ax.set_xlim(0, max(1, max(result['groups'][g]['started'] for g in groups))+.4)
    ax.xaxis.set_major_locator(plt.MaxNLocator(integer=True))
    ax.legend(fontsize=8)
    fig.tight_layout()
    save(fig, FIGURE_NAMES[2], 'Original termination reasons, including service failures and budget truncation, retain started denominators.')

    fig, axes = plt.subplots(len(selected), 1, figsize=(10, max(3.2, 2.65*len(selected))), squeeze=False)
    for ax, e in zip(axes[:, 0], selected):
        c = curves[e['trial_id']]
        ax.step(c['time'], c['coverage'], where='post', color=color[e['group_id']], label='Historical stage coverage (diagnostic)')
        ax.plot(c['time'], c['effective_insertion'], color='#903b3b', label='Valid insertion progress', linewidth=1.2)
        ax.set(ylim=(-.03, 1.05), xlabel='Simulation time (s)', ylabel='Dimensionless [0, 1]',
            title=f"{e['trial_id']} | {e['group_id']} | {e.get('termination_reason')}")
        ax.grid(alpha=.2)
        ax.legend(fontsize=7, loc='upper left')
        if not c['time']:
            ax.text(.5, .5, 'No completed control endpoints available',
                transform=ax.transAxes, ha='center', va='center', color='#666666')
    fig.tight_layout()
    save(fig, FIGURE_NAMES[3], 'Original control-endpoint Progress v1.2 curves; diagnostic stage coverage is separate from effective insertion.')

    fig, axes = plt.subplots(len(selected), 3, figsize=(12, max(3.1, 2.6*len(selected))), squeeze=False)
    for row, e in enumerate(selected):
        c = curves[e['trial_id']]
        for column, (key, unit, title) in enumerate((('xy_mm', 'mm', 'Target lateral error'),
                ('tilt_deg', 'deg', 'Target tilt'), ('applicable_progress', '1', 'Applicable insertion progress'))):
            ax = axes[row, column]
            present = any(math.isfinite(v) for v in c[key])
            if present:
                ax.plot(c['time'], c[key], color=color[e['group_id']], linewidth=1.1)
            else:
                if key == 'applicable_progress':
                    unavailable = 'N/A\nInsertion applicability not observed'
                elif e.get('continuous', {}).get('target_operation_region_sample_count', 0):
                    unavailable = 'N/A\nMeasurement unavailable in reached region'
                else:
                    unavailable = 'N/A\nTarget operation region not reached'
                ax.text(.5, .5, unavailable, transform=ax.transAxes, ha='center', va='center', color='#666666')
                ax.set_yticks([])
                # An empty Matplotlib axis defaults to 0..1, which would look
                # like a measured one-second episode. Keep the actual observed
                # simulation interval even when the metric itself is N/A.
                if c['time'] and c['time'][-1] > c['time'][0]:
                    ax.set_xlim(c['time'][0], c['time'][-1])
            ax.set(xlabel='Simulation time (s)', ylabel=unit,
                title=f"{e['trial_id']}: {title}")
            ax.grid(alpha=.18)
    fig.tight_layout()
    save(fig, FIGURE_NAMES[4], 'Target error uses entrance AND current-route gates; insertion curves require applicability. Missing regions are N/A, never zero millimetres.')

    fig, axes = plt.subplots(1, 3, figsize=(12, 4.3))
    xx = np.arange(len(ordered))
    resources = [('latency_per_call_s', 'Model latency (s / call)'),
        ('inference_seconds', 'Total inference (wall s / episode)'),
        ('wall_seconds', 'Episode elapsed wall time (s)')]
    for ax, (key, title) in zip(axes, resources):
        values = [e.get('resource', {}).get(key, {}).get('mean') if key == 'latency_per_call_s' else e.get('resource', {}).get(key) for e in ordered]
        for index, (e, v) in enumerate(zip(ordered, values)):
            if finite(v) is None:
                ax.text(index, .04, 'N/A', transform=ax.get_xaxis_transform(), ha='center', color='#666666')
            else:
                ax.bar(index, v, width=.6, color=color[e['group_id']])
                ax.annotate(f'{v:.2f}', (index, v), xytext=(0, 3), textcoords='offset points', ha='center', fontsize=7)
        ax.set(xticks=xx, xticklabels=[e['trial_id'] for e in ordered], title=title)
        ax.tick_params(axis='x', rotation=45)
        ax.grid(axis='y', alpha=.2)
        ax.set_ylim(bottom=0)
    fig.suptitle('Distinct wall-clock quantities; inference pauses simulation', fontsize=12)
    fig.tight_layout()
    save(fig, FIGURE_NAMES[5], 'Separate per-call latency, total inference wall time and whole-episode wall time. Missing telemetry remains N/A.')

    receipt = dict(schema='labsim.policy_eval.figures.v1', analysis_path=str(result_path.resolve()),
        analysis_sha256=file_sha256(result_path), manifest_path=str(manifest_path.resolve()),
        manifest_sha256=file_sha256(manifest_path), selection_rule=selection_rule,
        representatives=[dict(trial_id=e['trial_id'], episode_id=e.get('episode_id'),
            group_id=e['group_id'], task_success=e.get('task_success'), progress_dir=e['progress_dir']) for e in selected],
        started_formal_episode_count=len(formal), formal_group_counts={g: result['groups'][g]['started'] for g in groups},
        figures=receipts, original_data_modified=False)
    (output/'plots_manifest.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2)+'\n')
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('summary', type=Path)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    receipt = plot_results(args.summary, args.manifest, args.output)
    print(json.dumps(dict(figures=len(receipt['figures']), representatives=[e['trial_id'] for e in receipt['representatives']])))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
