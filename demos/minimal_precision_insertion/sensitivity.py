"""Sequential, one-factor diagnostics around the observed 120 Hz anomaly."""
import argparse
import csv
import json
from pathlib import Path
import subprocess
import sys
import time
from omegaconf import OmegaConf

ROOT=Path(__file__).resolve().parents[2]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--reference',type=Path,required=True,help='Same held-body state used by matched_initial.py')
    args=p.parse_args();args.output=args.output.resolve();args.output.mkdir(parents=True,exist_ok=False)
    (args.output/'configs').mkdir()
    cases=[('contact_25um',{'physics.contact_offset_m':.000025}),
           ('contact_100um',{'physics.contact_offset_m':.0001}),
           ('position_iterations_64',{'physics.position_iterations':64}),
           ('analytic_cylinder',{'geometry.collision':'analytic_cylinder'})]
    rows=[];timing=[];codes=[]
    for name,changes in cases:
        cfg=OmegaConf.load(ROOT/'config/minimal_precision_insertion.yaml')
        for key,value in changes.items():OmegaConf.update(cfg,key,value)
        config=args.output/'configs'/(name+'.yaml');OmegaConf.save(cfg,config)
        command=[sys.executable,str(ROOT/'demos/minimal_precision_insertion/matched_initial.py'),
            '--reference',str(args.reference.resolve()),
            '--config',str(config),'--headless','--offsets','0,0.35,0.4','--repeats','1',
            '--physics-hz','120','--output',str(args.output/name)]
        begin=time.monotonic()
        with (args.output/(name+'.log')).open('w') as log:
            code=subprocess.run(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT).returncode
        gates=list((args.output/name).rglob('geometry_gate_result.json'))
        excluded=(name=='analytic_cylinder' and code!=0 and bool(gates)
            and all(json.loads(g.read_text()).get('operation_started') is False for g in gates))
        if excluded:
            (args.output/name/'GEOMETRY_EXCLUSION.json').write_text(json.dumps(dict(
                excluded_from_precision_comparison=True,
                reason='Runtime boundary differs from declared cylinder; insertion was not started.',
                geometry_gate_files=[str(g) for g in gates]),indent=2)+'\n')
        codes.append(0 if excluded else code)
        timing.append(dict(case=name,changes=changes,process_wall_seconds=time.monotonic()-begin,
            exit=code,geometry_excluded=excluded))
        summary=args.output/name/'summary.json'
        if summary.exists():
            for result in json.loads(summary.read_text()):
                pre=result['actual_precontact']
                rows.append(dict(case=name,physics_hz=120,nominal_offset_mm=result['nominal_offset_mm'],
                    repeat=result['repeat'],status=result['status'],reason=result['reason'],
                    actual_precontact_x_mm=pre['xy_error_m'][0]*1000 if pre else None,
                    actual_precontact_y_mm=pre['xy_error_m'][1]*1000 if pre else None,
                    max_depth_mm=result['max_depth_mm'],max_overlap_mm=result['max_overlap_mm'],
                    contact_offset_m=cfg.physics.contact_offset_m,rest_offset_m=0.,
                    position_iterations=cfg.physics.position_iterations,collision=cfg.geometry.collision,
                    result_file=str(Path(result['output'])/(result['episode']+'_result.json'))))
        print('SENSITIVITY_CONFIGURATION_FINISHED',name,code,flush=True)
    (args.output/'condition_results.json').write_text(json.dumps(rows,indent=2)+'\n')
    (args.output/'process_timing.json').write_text(json.dumps(timing,indent=2)+'\n')
    if rows:
        with (args.output/'condition_results.csv').open('w') as f:
            writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    return 0 if all(code==0 for code in codes) else 1


if __name__=='__main__':
    sys.exit(main())
