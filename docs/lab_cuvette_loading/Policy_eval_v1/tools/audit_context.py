"""Verify frozen scene correspondence and locate actual safety contact evidence."""
from __future__ import annotations
import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(4<<20),b''):h.update(block)
    return h.hexdigest()


def load(path):return json.loads(Path(path).read_text())


def differences(a,b,path=''):
    if isinstance(a,dict) and isinstance(b,dict):
        rows=[]
        for key in sorted(a.keys()|b.keys()):
            if key not in a or key not in b:rows.append(dict(path=path+'/'+key,before=a.get(key),after=b.get(key)))
            else:rows.extend(differences(a[key],b[key],path+'/'+key))
        return rows
    return [] if a==b else [dict(path=path,before=a,after=b)]


def audit(run_root,teacher):
    teacher_path=teacher/'project_scene_contract.json'
    baseline=load(teacher_path)
    allowed={'/frozen_scene_sha256','/physical_and_execution_baseline/frozen_scene_sha256',
        '/physical_and_execution_baseline/config/experiment/truth_teacher',
        '/physical_and_execution_baseline/config/release/record_mode'}
    rows=[]
    for run in sorted(run_root.glob('formal_*')):
        if not run.is_dir():continue
        proof=load(run/'supervisor.json')
        if proof['status']!='closed' or not all(c.get('native_pid_gone') for c in proof['children']):
            raise ValueError('Only closed trials: '+str(run))
        episode=run/'environment/episode_0000'
        contract_path=episode/'project_scene_contract.json';contract=load(contract_path)
        delta=differences(baseline,contract)
        unexpected=[r for r in delta if r['path'] not in allowed]
        source=episode/'native_contact_events.jsonl.gz';before=sha(source)
        forbidden=[];total=0
        with gzip.open(source,'rt') as stream:
            for line in stream:
                event=json.loads(line);total+=1
                if not event.get('forbidden_robot_environment'):continue
                vectors=[p.get('force_raw_N') for p in event.get('points',[])]
                norms=[math.sqrt(sum(float(v)**2 for v in x)) for x in vectors
                       if isinstance(x,list) and len(x)==3]
                forbidden.append(dict(t=event['t'],physics_step=event['physics_step'],
                    colliders=event.get('colliders'),event_type=event.get('type'),
                    possible_duplicate_same_step=event.get('possible_duplicate_same_step'),
                    maximum_single_point_raw_force_norm_N=max(norms,default=None),
                    points=event.get('points',[])))
        if sha(source)!=before:raise RuntimeError('Source changed during audit')
        result=load(episode/'result.json')
        rows.append(dict(trial_id=run.name.removeprefix('formal_'),episode_id=result['episode_id'],
            scene_fingerprint=contract['frozen_scene_sha256'],
            teacher_contract_differences=delta,unexpected_contract_differences=unexpected,
            physical_configuration_matches_teacher=not unexpected,
            termination_reason=result['termination_reason'],failure_type=result['failure_type'],
            terminal_simulation_time_s=result['simulation_seconds'],
            forbidden_contact_event_count=len(forbidden),first_forbidden=forbidden[0] if forbidden else None,
            last_forbidden=forbidden[-1] if forbidden else None,
            source=dict(path=str(source.resolve()),sha256=before,total_native_events=total),
            raw_contact_interpretation='Recorded callback impulse divided by current physics_dt. Single-point raw vector convention; not signed force on the cuvette. No summation across duplicate events or contact points.',
            report_scope='Instrument contact localization from recorded collider paths; not a new collision tolerance or scorer.'))
    fingerprints={r['scene_fingerprint'] for r in rows}
    return dict(schema='labsim.Policy_eval_v1.context_audit.v1',
        passed=bool(rows) and len(fingerprints)==1 and all(r['physical_configuration_matches_teacher'] for r in rows),
        teacher_reference=dict(path=str(teacher.resolve()),contract_sha256=sha(teacher_path),
            existing_complete_teacher_success=load(teacher/'result.json')['task_success']),
        common_evaluation_scene_fingerprint=next(iter(fingerprints)) if len(fingerprints)==1 else None,
        episodes=rows,source_records_modified=False,protocol_or_scorer_changed=False)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run-root',type=Path,required=True)
    p.add_argument('--teacher',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists():raise FileExistsError(a.output)
    value=audit(a.run_root,a.teacher)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open('x') as f:json.dump(value,f,ensure_ascii=False,indent=2,allow_nan=False);f.write('\n')
    print(json.dumps(dict(passed=value['passed'],episodes=len(value['episodes']),output=str(a.output))))
    raise SystemExit(0 if value['passed'] else 1)
