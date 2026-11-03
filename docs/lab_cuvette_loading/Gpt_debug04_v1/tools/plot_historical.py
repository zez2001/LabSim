"""Three source-backed CPU plots for one historical or closed formal episode."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from demos.lab_cuvette_policy_eval_v1.analysis import file_sha256, finite, json_rows, metric


def plot(progress, metrics_path, quant_path, output, *, scope='historical'):
    progress, metrics_path, quant_path, output = map(Path, (progress, metrics_path, quant_path, output))
    if output.exists():
        raise FileExistsError(output)
    episodes = json.loads(metrics_path.read_text())
    selected = [row for row in episodes if row.get('started') and row.get('purpose')==scope]
    if len(selected) != 1:
        raise ValueError('Exactly one started '+scope+' episode is required')
    episode = selected[0]
    quant = json.loads(quant_path.read_text())
    if episode['episode_id'] != quant['episode_id']:
        raise ValueError('Episode identities differ')
    config = json.loads((progress/'progress_config.resolved.json').read_text())
    keys = ('t', 'coverage', 'transport', 'align', 'valid_insert', 'drift_mm', 'rotation_deg', 'xy_mm', 'tilt_deg', 'yaw_deg')
    data = {k: [] for k in keys}
    def number(value, scale=1.):
        return finite(value)*scale if finite(value) is not None else math.nan
    for index, row in enumerate(json_rows(progress/'progress_v1.jsonl.gz')):
        for s in ([row['before'], row['after']] if index == 0 else [row['after']]):
            data['t'].append(float(s['t']))
            data['coverage'].append(number(s.get('coverage_progress')))
            data['transport'].append(number(s['stages']['transport'].get('effective_continuous')))
            data['align'].append(number(s['stages']['align'].get('effective_continuous')))
            data['valid_insert'].append(number(s.get('valid_insertion_progress')))
            data['drift_mm'].append(number(metric(s, 'grasp_relative_translation_m'), 1000.))
            data['rotation_deg'].append(number(metric(s, 'grasp_relative_rotation_rad'), 180./math.pi))
            gates = s['insertion_gate_details']['gates']
            region = gates['entrance_region']['value'] is True and gates['current_attempt_route']['value'] is True
            for key, name, scale in [('xy_mm','target_lateral_error_m',1000.), ('tilt_deg','target_tilt_rad',180./math.pi), ('yaw_deg','target_yaw_error_rad',180./math.pi)]:
                v = number(metric(s, name), scale)
                data[key].append(abs(v) if region else math.nan)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.titlesize':11,
        'axes.labelsize':10,'axes.spines.top':False,'axes.spines.right':False,'savefig.dpi':170})
    output.mkdir(parents=True, exist_ok=False)
    files = []
    def save(fig, name, description):
        fig.savefig(output/name,bbox_inches='tight',facecolor='white')
        plt.close(fig)
        files.append(dict(path=name,sha256=file_sha256(output/name),description=description))
    stages = ['approach_grasp','grasp','extract','held_transport_50mm','transport','align','insert','support_transfer','released','retreated','stable_complete']
    labels = ['Approach','Grasp','Extract','Held XY 50 mm','Fixed pre-insert','Align','Valid insertion','Target support','Detach','Retreat','Stable 3 s']
    fig, ax = plt.subplots(figsize=(9.2,4.8))
    for i, name in enumerate(stages):
        stage = episode['stage_results'][name]
        t = stage.get('first_confirmed_t')
        if finite(t) is not None:
            ax.hlines(i,0,t,color='#c5d5e1',linewidth=2)
            ax.plot(t,i,'o',color='#1769aa')
            ax.annotate(f'{t:.4f} s',(t,i),xytext=(6,0),textcoords='offset points',va='center',fontsize=8)
        else:
            ax.text(3,i,'not reached' if stage.get('reached') is False else 'unknown evidence',va='center',color='#777777',fontsize=8)
    ax.set(yticks=range(len(stages)),yticklabels=labels,xlim=(0,quant['simulation_seconds']),
        xlabel='Simulation time of first physical confirmation (s)',
        title=('Historical gpt_debug_04' if scope=='historical' else 'Restored debug04: authorized formal trial 01')+': first achieved milestones')
    ax.set_ylim(len(stages)-.5,-.5);ax.grid(axis='x',alpha=.2)
    fig.tight_layout()
    save(fig,f'01_{scope}_first_times.png','First confirmations from the full event stream; unachieved stages have no invented zero-second timestamp.')

    fig,axes=plt.subplots(3,1,figsize=(8.8,7.7),sharex=True)
    for key,label,color in [('coverage','Historical stage coverage','#1769aa'),('transport','Effective transport','#228563'),
            ('align','Effective alignment','#cd7b26'),('valid_insert','Valid insertion progress','#9b3447')]:
        axes[0].plot(data['t'],data[key],label=label,color=color,linewidth=1.1)
    axes[0].set(ylabel='Dimensionless [0, 1]',ylim=(-.03,1.05),title='Progress v1.2 diagnostics, not cumulative reward')
    axes[0].legend(fontsize=8,ncol=2,loc='upper left')
    axes[1].plot(data['t'],data['drift_mm'],color='#1769aa',linewidth=1.)
    axes[1].set(ylabel='Relative translation (mm)',title='Actual cup-in-hand motion; fixed reference per attempt')
    axes[2].plot(data['t'],data['rotation_deg'],color='#228563',linewidth=1.)
    axes[2].set(ylabel='Relative rotation (deg)',xlabel='Simulation time (s)')
    quality=quant['observed_control_times']['first_grasp_quality_false_t']
    loss=quant['observed_control_times']['first_actual_grasp_loss_observed_t']
    for ax in axes:
        if quality is not None:ax.axvline(quality,color='#cd7b26',linestyle='--',linewidth=.9)
        if loss is not None:ax.axvline(loss,color='#9b3447',linestyle=':',linewidth=1.)
        ax.grid(alpha=.2);ax.set_xlim(0,quant['simulation_seconds'])
    warning='N/A' if quality is None else f'{quality:.3f} s'
    lost='N/A' if loss is None else f'{loss:.4f} s'
    axes[1].text(.02,.94,f'First false quality (control): {warning}\nConfirmed unsupported loss (observed control): {lost}',
        transform=axes[1].transAxes,va='top',fontsize=8)
    axes[2].text(.02,.94,'Curves: unique control endpoints; 240 Hz physical maxima are in the evidence table.\nReference resets across attempts are not object teleportation.',transform=axes[2].transAxes,va='top',fontsize=7.5)
    fig.tight_layout()
    save(fig,f'02_{scope}_progress_drift.png','Actual control-endpoint effective Progress and relative drift; per-attempt references and different warning/loss times are explicit.')

    fig,axes=plt.subplots(3,1,figsize=(8.8,7.2),sharex=True)
    params=config['thresholds']
    specifications=[('xy_mm','Lateral error (mm)',params['alignment_lateral_m']*1000.),
        ('tilt_deg','Tilt (deg)',params['alignment_tilt_rad']*180./math.pi),
        ('yaw_deg','Absolute yaw error (deg)',params['alignment_yaw_rad']*180./math.pi)]
    for ax,(key,label,threshold) in zip(axes,specifications):
        ax.plot(data['t'],data[key],color='#1769aa',linewidth=1.1,label='Actual applicable endpoints')
        ax.axhline(threshold,color='#9b3447',linestyle='--',linewidth=.9,label=f'Original alignment limit {threshold:g}')
        ax.set_ylabel(label);ax.grid(alpha=.2);ax.legend(fontsize=8,loc='upper left')
        ax.set_xlim(0,quant['simulation_seconds'])
        if not any(math.isfinite(value) for value in data[key]):
            ax.text(.5,.45,'N/A: target operation region not reached',ha='center',va='center',transform=ax.transAxes,color='#666666')
    axes[0].set_title('Target errors only where entrance-region AND attempt-route gates hold')
    axes[2].set_xlabel('Simulation time (s)')
    fig.text(.11,-.015,'Outside the applicable region: no measured target-error curve. Valid insertion depth and post-release stability are N/A.',fontsize=8)
    fig.tight_layout()
    save(fig,f'03_{scope}_applicable_errors.png','Only applicable target-region endpoints are plotted; original limits unchanged; component minima are not a synthetic common pose.')
    receipt=dict(schema='labsim.Gpt_debug04_v1.'+scope+'_figures.v1',historical_only=scope=='historical',
        episode_id=episode['episode_id'],control_endpoint_count=len(data['t']),
        progress_source_sha256=file_sha256(progress/'progress_v1.jsonl.gz'),
        quantification_sha256=file_sha256(quant_path),metric_source_sha256=file_sha256(metrics_path),
        tool_sha256=file_sha256(Path(__file__)),original_data_modified=False,figures=files)
    (output/'plots_manifest.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    return receipt


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--progress',required=True,type=Path);p.add_argument('--metrics',required=True,type=Path)
    p.add_argument('--quantification',required=True,type=Path);p.add_argument('--output',required=True,type=Path)
    p.add_argument('--scope',choices=('historical','formal'),default='historical')
    a=p.parse_args(argv);r=plot(a.progress,a.metrics,a.quantification,a.output,scope=a.scope)
    print(json.dumps(dict(figures=len(r['figures']),endpoints=r['control_endpoint_count'])))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
