"""Generate reproducible CSV/JSON and scientific plots from actual trial records."""
import argparse
from collections import Counter,defaultdict
import csv
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

COLORS={'SUCCESS':'#287a54','BLOCKED':'#bf6b16','PHYSICS_INVALID':'#b83838','GRASP_SLIP':'#8c5bb3',
        'DROPPED':'#677080','UNSTABLE_AFTER_RELEASE':'#d6788c','TIMEOUT':'#417baf','CONTROL_OR_IK_FAILURE':'#333333'}
STATUS=list(COLORS)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directories',type=Path,nargs='+');parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=False)
    trials=[]
    for directory in args.directories:
        for path in sorted(directory.rglob('episode_*_result.json')):
            result=json.loads(path.read_text());result['result_file']=str(path.resolve())
            trials.append(result)
    fields=['physics_hz','nominal_offset_mm','repeat','status','reason','actual_precontact_x_mm','actual_precontact_y_mm',
            'actual_precontact_tilt_deg','actual_preentry_x_mm','actual_preentry_y_mm',
            'initial_x_mm','initial_y_mm','initial_tilt_deg','max_depth_mm','final_depth_mm','max_overlap_mm',
            'max_grasp_slip_mm','continuous_hold_seconds','simulation_seconds','engine_simulation_seconds','execution_wall_seconds','setup_wall_seconds','result_file']
    rows=[]
    for t in trials:
        pre=t.get('actual_precontact');entry=t.get('actual_preentry');init=t['initial_state']
        row={k:t.get(k) for k in fields}
        row.update(actual_precontact_x_mm=pre['xy_error_m'][0]*1000 if pre else None,
            actual_precontact_y_mm=pre['xy_error_m'][1]*1000 if pre else None,
            actual_precontact_tilt_deg=np.degrees(pre['tilt_rad']) if pre else None,
            actual_preentry_x_mm=entry['xy_error_m'][0]*1000 if entry else None,
            actual_preentry_y_mm=entry['xy_error_m'][1]*1000 if entry else None,
            initial_x_mm=init['xy_error_m'][0]*1000,initial_y_mm=init['xy_error_m'][1]*1000,
            initial_tilt_deg=np.degrees(init['tilt_rad']),final_depth_mm=t['final_state']['depth_m']*1000)
        rows.append(row)
    with (args.output/'trials.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
    # Full contact arrays remain in the immutable episode records. The portable
    # summary uses exactly the same measured scalar values as the CSV.
    (args.output/'trials.json').write_text(json.dumps(rows,indent=2)+'\n')
    groups=defaultdict(list)
    for r in rows:
        groups[(r['physics_hz'],r['nominal_offset_mm'])].append(r)
    summaries=[]
    for (hz,offset),values in sorted(groups.items()):
        counts=Counter(v['status'] for v in values)
        summaries.append(dict(physics_hz=hz,nominal_offset_mm=offset,repeats=len(values),outcomes=dict(counts),
            preentry_x_range_mm=[min(v['actual_preentry_x_mm'] for v in values),max(v['actual_preentry_x_mm'] for v in values)]
                if all(v['actual_preentry_x_mm'] is not None for v in values) else None,
            max_depth_range_mm=[min(v['max_depth_mm'] for v in values),max(v['max_depth_mm'] for v in values)],
            max_overlap_range_mm=[min(v['max_overlap_mm'] for v in values),max(v['max_overlap_mm'] for v in values)],
            precontact_x_range_mm=[min(v['actual_precontact_x_mm'] for v in values),max(v['actual_precontact_x_mm'] for v in values)]
                if all(v['actual_precontact_x_mm'] is not None for v in values) else None))
    changes=[]
    for hz in sorted({r['physics_hz'] for r in rows}):
        series=[s for s in summaries if s['physics_hz']==hz]
        for a,b in zip(series,series[1:]):
            if a['outcomes']!=b['outcomes']:
                changes.append(dict(physics_hz=hz,nominal_interval_mm=[a['nominal_offset_mm'],b['nominal_offset_mm']],
                    left=a['outcomes'],right=b['outcomes'],
                    measured_precontact_x_interval_mm=[a['precontact_x_range_mm'],b['precontact_x_range_mm']],
                    note='Observed adjacent outcome transition, not a geometric threshold or a probability estimate.'))
    (args.output/'condition_summary.json').write_text(json.dumps(summaries,indent=2)+'\n')
    with (args.output/'condition_summary.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=list(summaries[0]));w.writeheader();w.writerows(summaries)
    (args.output/'boundary_intervals.json').write_text(json.dumps(changes,indent=2)+'\n')
    plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False,'figure.dpi':150})
    frequencies=sorted({r['physics_hz'] for r in rows})
    fig,axes=plt.subplots(len(frequencies),1,figsize=(7,2.4*len(frequencies)),squeeze=False,sharex=True)
    for ax,hz in zip(axes[:,0],frequencies):
        for status in STATUS:
            values=[r for r in rows if r['physics_hz']==hz and r['status']==status and r['actual_precontact_x_mm'] is not None]
            if values:
                ax.scatter([r['actual_precontact_x_mm'] for r in values],[STATUS.index(status)+.045*(r['repeat']-1) for r in values],
                           color=COLORS[status],s=30,label=status)
        ax.set_yticks(range(len(STATUS)),STATUS,fontsize=8)
        ax.set_ylim(-.5,max([STATUS.index(r['status']) for r in rows if r['physics_hz']==hz])+ .5)
        ax.axvline(.3,color='#777777',linestyle=':',label='Nominal single-side clearance 0.3 mm')
        ax.set_title(f'Physical insertion outcomes at {hz} Hz (control 60 Hz)')
        ax.grid(axis='x',alpha=.2)
    axes[-1,0].set_xlabel('Measured X offset immediately before first sensed module contact (mm)')
    fig.text(.02,.005,'Repeated fixed initializations; symbols are runs, not estimated success probabilities.',fontsize=8)
    fig.tight_layout(rect=[0,.035,1,1]);fig.savefig(args.output/'actual_offset_outcome.png');plt.close(fig)
    fig,ax=plt.subplots(figsize=(7,4))
    for hz,marker in zip(frequencies,['o','s','^']):
        values=sorted([r for r in rows if r['physics_hz']==hz],key=lambda r:(r['nominal_offset_mm'],r['repeat']))
        ax.scatter([r['nominal_offset_mm'] for r in values],[r['max_depth_mm'] for r in values],label=f'{hz} Hz',marker=marker,s=35,alpha=.7)
    invalid=[r for r in rows if r['status']=='PHYSICS_INVALID']
    if invalid:
        ax.scatter([r['nominal_offset_mm'] for r in invalid],[r['max_depth_mm'] for r in invalid],
            facecolors='none',edgecolors=COLORS['PHYSICS_INVALID'],s=110,label='Invalid penetration; depth is not success')
    ax.axhline(18,color='#555555',linestyle=':',label='Depth requirement 18 mm')
    ax.set(xlabel='Nominal X offset (mm)',ylabel='Maximum measured insertion depth (mm)',title='Insertion depth versus injected offset')
    ax.legend();ax.grid(alpha=.2);fig.tight_layout();fig.savefig(args.output/'offset_depth.png');plt.close(fig)
    fig,ax=plt.subplots(figsize=(7,4))
    for hz,marker in zip(frequencies,['o','s','^']):
        values=[r for r in rows if r['physics_hz']==hz and r['actual_preentry_x_mm'] is not None]
        ax.scatter([r['nominal_offset_mm'] for r in values],[r['actual_preentry_x_mm'] for r in values],label=f'{hz} Hz before entry/contact',marker=marker,s=35)
    ax.plot([0,.8],[0,.8],color='#777777',linestyle=':',label='Injected = measured')
    ax.set(xlabel='Nominal X offset (mm)',ylabel='Measured X offset before entry/contact (mm)',title='Injected and actual offsets')
    ax.legend();ax.grid(alpha=.2);fig.tight_layout();fig.savefig(args.output/'injected_actual_offset.png');plt.close(fig)
    # Authored dimensions only: this schematic supplements, and does not replace,
    # the runtime collision screenshot, cooking snapshot and PhysX ray probes.
    fig,(ax,detail)=plt.subplots(1,2,figsize=(8,3.8),gridspec_kw={'width_ratios':[1.2,1]})
    from matplotlib.patches import Rectangle,Circle
    ax.add_patch(Rectangle((-9,0),3.7,20,color='#9da5ad'))
    ax.add_patch(Rectangle((5.3,0),3.7,20,color='#9da5ad'))
    ax.add_patch(Rectangle((-9,-4),18,4,color='#657482'))
    ax.add_patch(Rectangle((-5,0),10,50,color='#3c83b5',alpha=.8))
    ax.annotate('20 mm straight hole',xy=(5.3,10),xytext=(11,18),fontsize=9,
        arrowprops={'arrowstyle':'->','color':'#333333'})
    ax.text(-8,52,'Tube diameter 10 mm\nLength 50 mm; mass 0.02 kg',fontsize=9)
    ax.set(xlim=(-12,30),ylim=(-6,64),xlabel='X (mm)',ylabel='Z above hole floor (mm)',title='Authored synthetic section')
    ax.set_aspect('equal');ax.grid(alpha=.15)
    for radius,n,color,label in [(5,96,'#3c83b5','Tube: 96 sectors'),(5.3,128,'#657482','Hole wall: 128 segments')]:
        a=np.arange(n+1)*2*np.pi/n
        detail.plot(radius*np.cos(a),radius*np.sin(a),color=color,label=label)
        detail.add_patch(Circle((0,0),radius,fill=False,linestyle=':',edgecolor=color,alpha=.5))
    detail.annotate('0.3 mm nominal clearance',xy=(5.15,0),xytext=(1.5,3),fontsize=9,
        arrowprops={'arrowstyle':'->','color':'#333333'})
    detail.set(xlim=(-6,6),ylim=(-6,6),xlabel='X (mm)',ylabel='Y (mm)',title='Ideal circles and polygon outlines')
    detail.set_aspect('equal');detail.legend(fontsize=8,loc='lower center');detail.grid(alpha=.15)
    fig.tight_layout();fig.savefig(args.output/'asset_geometry.png');plt.close(fig)
    print(json.dumps(dict(trials=len(trials),conditions=len(summaries),outcomes=dict(Counter(r['status'] for r in rows)),transitions=changes),indent=2))


if __name__=='__main__':
    main()
