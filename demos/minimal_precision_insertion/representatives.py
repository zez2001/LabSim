"""Extract measured dynamics, native video frames and an explicitly partial clip."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import cv2
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('group',type=Path);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    selected={'success':0,'blocked':18,'physics_invalid':15}
    manifest={}
    for name,episode in selected.items():
        source=args.group/'video'/f'episode_{episode:04d}.mp4'
        dest=args.output/(name+'.mp4');shutil.copy2(source,dest)
        cap=cv2.VideoCapture(str(source))
        last=int(cap.get(cv2.CAP_PROP_FRAME_COUNT))-1
        time=last/cap.get(cv2.CAP_PROP_FPS)
        cap.set(cv2.CAP_PROP_POS_FRAMES,last)
        ok,frame=cap.read()
        if not ok:raise RuntimeError('Native video frame unavailable: '+str(source))
        cv2.imwrite(str(args.output/(name+'.png')),frame)
        manifest[name]=dict(source=str(source.resolve()),episode=episode,frame_time_s=time,
            frames=int(cap.get(cv2.CAP_PROP_FRAME_COUNT)),fps=cap.get(cv2.CAP_PROP_FPS),
            outcome=json.loads((args.group/f'episode_{episode:04d}_result.json').read_text())['status'])
        cap.release()
    source=args.group/'video/episode_0015.mp4'
    subprocess.run(['ffmpeg','-nostdin','-loglevel','error','-i',str(source),'-ss','3.9','-t','19.1',
        '-c:v','libx264','-crf','18','-pix_fmt','yuv420p',str(args.output/'passive_alignment_partial.mp4')],check=True)
    manifest['passive_alignment_partial']=dict(source=str(source.resolve()),source_interval_s=[3.9,23.0],
        outcome='PARTIAL_ONLY; complete episode PHYSICS_INVALID',
        note='Observed contact-induced alignment and insertion before release; not a success demonstration.')
    records=[json.loads(line) for line in (args.group/'episode_0015_physics.jsonl').open()]
    t=np.array([r['time'] for r in records])
    fig,axes=plt.subplots(4,1,figsize=(7,7),sharex=True)
    axes[0].plot(t,[r['xy_error_m'][0]*1000 for r in records],label='Measured bottom-axis X')
    axes[0].axhline(.3,color='#555555',linestyle=':',label='Nominal single-side clearance')
    axes[0].set_ylabel('X offset (mm)');axes[0].legend(fontsize=8)
    axes[1].plot(t,[r['depth_m']*1000 for r in records]);axes[1].axhline(18,color='#555555',linestyle=':')
    axes[1].set_ylabel('Depth (mm)')
    axes[2].plot(t,[r['wall_overlap_m']*1000 for r in records],label='Finite wall overlap')
    axes[2].plot(t,[r['base_overlap_m']*1000 for r in records],label='Base overlap')
    axes[2].axhline(.05,color='#b83838',linestyle=':',label='Fixed 0.05 mm tolerance')
    axes[2].set_ylabel('Overlap (mm)');axes[2].legend(fontsize=8)
    axes[3].plot(t,[r['module_contact_N'] for r in records]);axes[3].set_ylabel('Module contact (N)')
    for ax in axes:
        ax.axvline(25,color='#777777',linestyle='--');ax.grid(alpha=.2)
    axes[3].set_xlabel('Actual simulation time (s); dashed vertical line begins release')
    axes[0].set_title('120 Hz, nominal 0.35 mm\nPassive alignment followed by invalid penetration')
    fig.tight_layout();fig.savefig(args.output/'passive_then_invalid_dynamics.png',dpi=160);plt.close(fig)
    first1=next(r for r in records if r['depth_m']>=.001)
    first18=next(r for r in records if r['depth_m']>=.018)
    def measured(r):
        return {k:r[k] for k in ('time','depth_m','xy_error_m','tilt_rad','wall_overlap_m','base_overlap_m','slip_m')}
    manifest['measured_alignment']=dict(first_1mm=measured(first1),first_18mm=measured(first18),
        maximum_wall_overlap_mm=max(r['wall_overlap_m'] for r in records)*1000,
        final=measured(records[-1]))
    (args.output/'media_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print('REPRESENTATIVES_SAVED',args.output)


if __name__=='__main__':
    main()
