"""Draw readable report figures from the saved, verified control-time trace."""
from pathlib import Path
import argparse
import hashlib
import json

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--trajectory', type=Path)
    parser.add_argument('--episode-label', default='dev_03')
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    source = args.trajectory or root/'data_audit/dev_03_trajectory/trajectory.npz'
    phases = json.loads((source.parent/'phase_events.json').read_text())
    times = {e['next']: e['t'] for e in phases}
    args.output.mkdir(parents=True, exist_ok=False)
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    with np.load(source, allow_pickle=False) as data:
        t = data['next_timestamp_s']
        xy = data['xy_error_after_m']*1000
        depth = data['target_depth_after_m']*1000
        base = data['target_base_force_after_N'][:, 2]
        fingers = data['finger_friction_vectors_after_N'].sum(axis=1)[:, 2]
        joints = data['robot_joint_positions_after'][:, 7:]*1000
    font_file = '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'
    font_manager.fontManager.addfont(font_file)
    family = font_manager.FontProperties(fname=font_file).get_name()
    plt.rcParams.update({'font.family':family, 'font.size':11,
                         'axes.unicode_minus':False, 'savefig.dpi':180})
    fig, axes = plt.subplots(2, 1, figsize=(7, 5.5), sharex=True,
                             constrained_layout=True)
    mask = t >= times['ALIGN']
    axes[0].plot(t[mask], xy[mask, 0], label='实际 X 偏差')
    axes[0].plot(t[mask], xy[mask, 1], label='实际 Y 偏差')
    for sign in [-1, 1]:
        axes[0].axhline(sign*.575, color='gray', ls=':', lw=1)
    axes[0].set_ylabel('偏差 mm')
    axes[0].set_title(f'同一次 {args.episode_label} 的实际偏差与装载深度', fontsize=13)
    axes[0].legend(loc='lower right', fontsize=10)
    axes[1].plot(t[mask], depth[mask], label='源网格底部相对座口深度')
    axes[1].axhline(26.9, color='green', ls=':', label='26.9 mm 验收门槛')
    axes[1].set_ylabel('插入深度 mm')
    axes[1].set_xlabel('仿真时间 s')
    axes[1].legend(loc='lower right', fontsize=9)
    for ax in axes:
        ax.grid(alpha=.2)
        for key in ['INSERT', 'OPEN', 'VERIFY']:
            ax.axvline(times[key], color='gray', ls='--', alpha=.6, lw=.8)
    fig.savefig(args.output/'alignment_depth.png')
    plt.close(fig)

    fig, axes = plt.subplots(2, 1, figsize=(7, 5.6), sharex=True,
                             constrained_layout=True)
    mask = (t >= times['SUPPORT_TRANSFER']-1) & (t <= times['RETREAT']+.6)
    axes[0].plot(t[mask], base[mask], label='目标底座净竖直力')
    axes[0].plot(t[mask], fingers[mask], label='双指摩擦合力竖直分量')
    axes[0].axhline(.1962, color='gray', ls=':', label='20 g 假设重量')
    axes[0].set_ylabel('力 N')
    axes[0].set_title('实际支撑交接与双指松开', fontsize=13)
    axes[0].legend(loc='lower right', fontsize=9)
    axes[1].plot(t[mask], joints[mask, 0], label='左指实际关节位置')
    axes[1].plot(t[mask], joints[mask, 1], ls='--', label='右指实际关节位置')
    axes[1].set_ylabel('单指开度 mm')
    axes[1].set_xlabel('仿真时间 s')
    axes[1].legend(loc='upper left', fontsize=9)
    for ax in axes:
        ax.grid(alpha=.2)
        for key in ['SUPPORT_TRANSFER', 'OPEN', 'RETREAT']:
            ax.axvline(times[key], color='gray', ls='--', alpha=.6, lw=.8)
    fig.savefig(args.output/'support_open.png')
    plt.close(fig)
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before
    manifest = dict(source=str(source), source_sha256=before,
                    source_unchanged=True, method='direct saved arrays, no interpolation',
                    unavailable='NaN retained, not replaced with zero',
                    scope='simulation observation, not real calibration or precision',
                    files={p.name:hashlib.sha256(p.read_bytes()).hexdigest()
                           for p in args.output.glob('*.png')})
    (args.output/'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n')


if __name__ == '__main__':
    main()
