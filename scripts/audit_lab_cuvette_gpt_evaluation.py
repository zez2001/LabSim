#!/usr/bin/env python3
"""Audit only closed GPT attempts; never starts Isaac, a model, or opens HDF5.

Original physical labels remain unchanged. Derived control/IK causes, invalid
records and unknown outcomes are separate from valid task failures.
"""
from __future__ import annotations
import argparse
import csv
from datetime import datetime,timedelta
import gzip
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import time

ROOT=Path(__file__).resolve().parents[1]
EXPECTED_CODE='7a7cbb81c6fcede84b48d1e9b60f66c68dfac0f0'
EXPECTED_CONTROLLER='af2238443e8210b6b53243d297603c22ca4e8a654b415562a7c9dc8b726e2b85'
PUBLIC_KEYS={'episode_id','observation_id','step_index','simulation_time','simulation_time_s','joint_positions','joint_velocities',
    'TCPpose','tcp_pose','gripper_opening_m','gripper_effort_limit_N','task_language','source_slot_id','target_seat_id',
    'camera_meta','camera_calibration','finger_contact_forces_N','finger_contact_N','model_image_transforms'}
PRIVATE_KEYS={'object_position_m','object_quaternion_wxyz','renderer_debug','debug','phase','depth_m','xy_error_target_m',
    'target_floor','scorer','independent_score','record_valid','task_success','geometry_valid','Authorization','api_key','token'}


def read(path):return json.loads(Path(path).read_text())
def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1<<20),b''):h.update(block)
    return h.hexdigest()
def canonical(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def lines(path):
    path=Path(path)
    if not path.exists():path=path.with_suffix(path.suffix+'.gz')
    opener=gzip.open if path.suffix=='.gz' else open
    with opener(path,'rt') as f:
        for line in f:
            if line.strip():yield json.loads(line)
def safe_path(root,relative):
    path=(root/relative).resolve();path.relative_to(root.resolve())
    if not path.is_file():raise ValueError('Missing evidence: '+str(path))
    return path
def private_paths(value,path=''):
    found=[]
    if isinstance(value,dict):
        for key,item in value.items():
            where=path+'/'+key
            if key in PRIVATE_KEYS:found.append(where)
            found+=private_paths(item,where)
    elif isinstance(value,list):
        for index,item in enumerate(value):found+=private_paths(item,path+'/'+str(index))
    return found
def close(a,b,tol=1e-8):return a is not None and b is not None and abs(float(a)-float(b))<=tol
def action_args(row):
    if row.get('tool_call'):return row['tool_call'].get('arguments',{}),row['tool_call'].get('name')
    calls=row.get('model_tool_calls',[])
    if len(calls)==1:
        args=calls[0].get('arguments',{})
        return (json.loads(args) if isinstance(args,str) else args),calls[0].get('name')
    return {},None


def audit_artifacts(control,trace):
    from PIL import Image
    rows=[];errors=[];references=[]
    for event in trace:
        artifact=event.get('observation_artifacts')
        if artifact is None:
            errors.append('Missing observation artifacts for decision '+str(event.get('decision_index')));continue
        mp=safe_path(control,artifact['manifest_path']);manifest=read(mp)
        if sha(mp)!=artifact['manifest_sha256']:errors.append('Manifest SHA mismatch: '+str(mp))
        if manifest['request_label']!=event.get('request_label'):errors.append('Manifest/trace request label mismatch')
        public=artifact['public_observation'];pp=safe_path(control,public['path']);state=read(pp)
        if manifest['public_observation']!=public or manifest['images']!=artifact['images']:errors.append('Manifest/trace artifact metadata mismatch')
        if sha(pp)!=public['sha256']:errors.append('Public JSON SHA mismatch')
        if set(state)-PUBLIC_KEYS or private_paths(state):errors.append('Unexpected private observation fields')
        for key in ('episode_id','observation_id'):
            if state.get(key)!=event.get(key):errors.append('Observation/trace identity mismatch: '+key)
        if not close(state.get('simulation_time',state.get('simulation_time_s')),event.get('simulation_time_s')):
            errors.append('Observation/trace simulation time mismatch')
        expected_label=f"policy:{state['episode_id']}:{state.get('step_index',state['observation_id'])}:decision{manifest['decision_index']}"
        if manifest['request_label']!=expected_label:errors.append('Request label does not bind observation/decision')
        if len(artifact['images'])!=2:errors.append('Image count differs from two')
        images=[]
        for image in artifact['images']:
            ip=safe_path(control,image['path']);digest=sha(ip)
            declared=state['model_image_transforms'][image['camera_name']]
            if digest!=image['sha256'] or digest!=declared['transmitted_jpeg_sha256']:errors.append('JPEG SHA mismatch')
            if ip.stat().st_size!=image['bytes'] or ip.stat().st_size!=declared['transmitted_bytes']:errors.append('JPEG byte count mismatch')
            native_k=state['camera_meta'][image['camera_name']]['intrinsic_matrix_native']
            transform=declared['transmitted_pixel_from_native_pixel'];reported_k=declared['intrinsic_matrix_transmitted']
            predicted_k=[[sum(transform[i][k]*native_k[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
            if any(not close(predicted_k[i][j],reported_k[i][j]) for i in range(3) for j in range(3)):errors.append('Resized image calibration metadata mismatch')
            with Image.open(ip) as pixels:
                if pixels.format!='JPEG' or list(pixels.size)!=image['resolution_wh']:errors.append('JPEG format/resolution mismatch')
            images.append(dict(camera_name=image['camera_name'],path=str(ip.relative_to(ROOT)),sha256=digest,bytes=ip.stat().st_size,
                resolution_wh=image['resolution_wh']))
            references.append(ip)
        expected={'manifest.json','public_observation.json','side_camera.jpg','wrist_camera.jpg'}
        if {p.name for p in mp.parent.iterdir()}!=expected:errors.append('Unexpected or missing observation files')
        references.extend([mp,pp])
        rows.append(dict(decision_index=manifest['decision_index'],request_label=manifest['request_label'],
            observation_id=state['observation_id'],public_json_sha256=sha(pp),images=images,verified=True))
    return dict(decisions=len(rows),jpeg_files=sum(len(x['images']) for x in rows),all_passed=not errors,errors=errors,decisions_audit=rows,
        scope='Exact transmitted JPEG and public JSON file/hash/identity audit; native RGB hashes cannot be reconstructed from lossy JPEG or resized policy H5.'),references


def physics_audit(episode,score):
    previous=None;count=0;step_errors=0;clock_errors=0;engine_delta_max=0.;first=None;last=None
    for row in lines(episode/'physics_records.jsonl'):
        count+=1;t=float(row['simulation_time']);step=int(row['physics_step']);engine=float(row['engine_time'])
        if first is None:first=dict(t=t,step=step,engine_time=engine)
        if previous:
            if step!=previous['step']+1 or not close(t-previous['t'],1/240):step_errors+=1
            residual=abs((engine-previous['engine_time'])-(t-previous['t']));engine_delta_max=max(engine_delta_max,residual)
            if residual>1e-5:clock_errors+=1
        previous=last=dict(t=t,step=step,engine_time=engine)
    return dict(rows=count,first=first,last=last,physics_step_or_dt_errors=step_errors,engine_clock_increment_errors=clock_errors,
        maximum_abs_engine_minus_recorded_dt_s=engine_delta_max,engine_dt_comparison_tolerance_s=1e-5,
        row_count_matches_recorded_physics=bool(count==score['actual_physics_steps']+1),
        final_simulation_time_matches_result=close(last['t'],score['simulation_seconds']),
        scope='All physics JSONL rows, including reset; engine-clock versus recorded-step increments plus action-receipt timing. No HDF5 was opened.')


def audit_run(run,ledger,*,formal):
    proof=read(run/'process_exit.json')
    if proof.get('process_exited') is not True or (formal and proof.get('status')!='CLOSED'):raise ValueError('Attempt not closed: '+str(run))
    episode=run/'episode_0000';control=episode/'gpt_control'
    result=read(episode/'result.json');independent=read(episode/'independent_score.json');summary=read(control/'summary.json');controller=read(control/'controller.json')
    trace=list(lines(control/'policy_trace.jsonl'));receipts=list(lines(episode/'action_receipts.jsonl')) if (episode/'action_receipts.jsonl').exists() else []
    canonical_controller=canonical(controller);hz=int(read(run/'run_manifest.json')['control_hz']);errors=[]
    if formal and summary['controller_sha256']!=canonical_controller:errors.append('Provider summary/controller canonical hash mismatch')
    native={r['action_id']:r for r in receipts};timing=[];pause=[]
    for event in trace:
        args,name=action_args(event);model_id=args.get('action_id')
        execution_id='gpt:'+hashlib.sha256(json.dumps([args.get('episode_id'),model_id],ensure_ascii=False,separators=(',',':')).encode()).hexdigest() if model_id else None
        if formal and model_id:
            returned=event.get('receipt',{}).get('execution_action_id')
            if returned is not None and returned!=execution_id:errors.append('Namespaced execution ID mismatch')
        r=native.get(execution_id)
        if r is None and not formal:r=native.get(model_id)
        if r:
            dt=float(r['simulation_time_after'])-float(r['simulation_time_before']);from_ticks=r['executed_control_ticks']/hz
            measured=event.get('receipt',{}).get('executed_duration_s')
            mismatch=measured is not None and not close(measured,dt)
            if not close(dt,from_ticks):errors.append('Native action time/tick mismatch')
            if formal and mismatch:errors.append('Formal provider actual-duration mismatch')
            paused=close(event.get('simulation_time_s'),r['simulation_time_before'])
            if not paused:errors.append('Simulation advanced between decision and action receipt')
            pause.append(paused)
            timing.append(dict(model_action_id=model_id,execution_action_id=r['action_id'],tool=name,requested_duration_s=args.get('duration_s'),
                reported_executed_duration_s=measured,measured_executed_duration_s=dt,executed_control_ticks=r['executed_control_ticks'],
                historical_duration_field_mismatch=mismatch,completed=r.get('completed'),terminated=r.get('terminated'),
                underlying_error_type=r.get('error_type'),underlying_error=r.get('error')))
        elif name in ('observe','finish') or event.get('receipt',{}).get('status')=='REJECTED':
            index=trace.index(event);after=trace[index+1]['simulation_time_s'] if index+1<len(trace) else result['simulation_seconds']
            unchanged=close(event.get('simulation_time_s'),after);pause.append(unchanged)
            if not unchanged:errors.append('Read-only/rejected action advanced recorded simulation time')
    for receipt in receipts:
        if receipt['episode_id']!=result['episode_id']:errors.append('Cross-episode native receipt')
    actual_ticks=sum(r['executed_control_ticks'] for r in receipts)
    if actual_ticks!=result['actual_control_steps']:errors.append('Native executed tick sum differs from actual control steps')
    if len(native)!=len(receipts):errors.append('Duplicate native execution IDs')
    model_rows=[r for r in ledger['attempts'] if r.get('label','').startswith('policy:'+result['episode_id'])]
    accepted_wrong=[e for e in trace if e.get('event')=='decision' and e.get('returned_model')!='gpt-6-astra']
    if accepted_wrong:errors.append('Accepted decision without matching model identity')
    if any(r.get('requested_model')!='gpt-6-astra' for r in model_rows):errors.append('Requested model substitution')
    if formal:
        artifacts,refs=audit_artifacts(control,trace);errors+=artifacts['errors']
    elif (control/'observations').is_dir():artifacts,refs=audit_artifacts(control,trace)
    else:artifacts,refs=dict(status='not_recorded_by_historical_backend',decisions=0,jpeg_files=0,all_passed=None),[]
    phys=physics_audit(episode,result)
    if phys['physics_step_or_dt_errors'] or phys['engine_clock_increment_errors'] or not phys['row_count_matches_recorded_physics'] or not phys['final_simulation_time_matches_result']:
        errors.append('Physics log clock/coverage audit failed')
    if summary['api_decisions']!=sum(1 for e in trace if e.get('request_id') and any(r['request_id']==e['request_id'] and r.get('status')=='OK' for r in model_rows)):
        errors.append('Successful API response count differs from joined trace/ledger')
    known_control=[r['error'] for r in receipts if 'CONTROL_OR_IK_FAILURE' in str(r.get('error',''))]
    if known_control:derived='KNOWN_CONTROL_OR_IK_FAILURE'
    elif result['termination_reason']=='ROBOT_ENVIRONMENT_COLLISION':derived='ROBOT_ENVIRONMENT_COLLISION_SAFETY_STOP'
    elif result.get('failure_type')=='GRASP_SLIP':derived='VALID_TASK_FAILURE_GRASP_SLIP' if result.get('record_valid') is True else 'GRASP_SLIP_INVALID_RECORD'
    elif result['termination_reason']=='LOCAL_CONTEXT_TOKEN_BOUND_EXCEEDED':derived='LOCAL_INPUT_CONTEXT_GUARD'
    else:derived=result['termination_reason']
    for key in ('task_success','failure_type','termination_reason','source_slot_cleared','release_observed','retreat_observed','stable_after_retreat'):
        if result.get(key)!=independent.get(key):errors.append('Collector/independent semantic mismatch: '+key)
    if not result.get('retreat_observed') and (result['post_retreat_window']['status']!='unavailable' or result['stable_after_retreat'] is not None):
        errors.append('Pre-retreat failure mislabeled post-retreat stability')
    row=dict(name=str(run.relative_to(ROOT)),episode_id=result['episode_id'],formal=formal,code_commit=proof['code_commit'],
        canonical_controller_sha256=canonical_controller,controller_document_bytes_sha256=sha(control/'controller.json'),
        source_hash_supervisor_field=proof.get('controller_sha256'),provider_implementation_sha256=controller.get('implementation_sha256'),
        images=controller['provider_config']['images'],scene_fingerprint=read(run/'run_manifest.json')['project_scene_fingerprint'],
        exit_code=proof['exit_code'],process_exited=proof['process_exited'],api_decisions=summary['api_decisions'],network_attempts=len(model_rows),
        executed_action_receipts=sum(r['executed_control_ticks']>0 for r in receipts),completed_action_receipts=sum(r.get('completed') is True for r in receipts),
        rejected_tool_decisions=sum(e.get('receipt',{}).get('status')=='REJECTED' for e in trace),provider_episode_wall_seconds=summary['wall_seconds'],
        simulation_seconds=result['simulation_seconds'],action_simulation_seconds=sum(x['measured_executed_duration_s'] for x in timing),
        actual_control_steps=result['actual_control_steps'],wall_seconds=proof['wall_seconds'],
        record_valid=result['record_valid'],task_success=result['task_success'],failure_type_raw=result['failure_type'],termination_reason_raw=result['termination_reason'],
        derived_failure_cause=derived,underlying_control_or_ik_errors=known_control,
        source_slot_cleared=result['source_slot_cleared'],grasp_success=result['grasp_success'],transport_success=result['transport_success'],
        release_observed=result['release_observed'],retreat_observed=result['retreat_observed'],stable_after_retreat=result['stable_after_retreat'],
        eligible_for_success_bc=result.get('eligible_for_success_bc'),eligible_for_failure_analysis=result.get('eligible_for_failure_analysis'),
        post_retreat_window=result['post_retreat_window'],terminal_window=result['terminal_window'],observed_events=result['observed_events'],
        physics_quality_flags=result['physics_quality_flags'],invalid_state_reasons=result['invalid_state_reasons'],
        artifacts=artifacts,timing=timing,simulation_pause_checks=dict(checked_intervals=len(pause),all_observed_unchanged=all(pause)),
        physics_log_audit=phys,audit_errors=errors,audit_passed=not errors)
    return row,refs


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--state',type=Path,default=ROOT/'outputs/lab_cuvette_loading/Project_v1/gpt_validation_sequence_state_03.json')
    p.add_argument('--output',type=Path,default=ROOT/'docs/lab_cuvette_loading/Project_v1/evaluation/gpt_formal5_01')
    args=p.parse_args(argv);state=read(args.state)
    if state.get('finished') is not True:raise SystemExit('Sequence is not finished; no final audit or active HDF5 access performed')
    base=ROOT/'outputs/lab_cuvette_loading/Project_v1';ledger=read(base/'cubence_budget.json')
    if any(x.get('status')=='RESERVED' for x in ledger['attempts']):raise SystemExit('Budget contains an active request; wait for closure')
    formal=[];refs={}
    for index in range(5):
        run=base/'gpt_formal5_01'/f'attempt_{index:04d}';row,images=audit_run(run,ledger,formal=True);formal.append(row);refs[index]=images
    debug=[audit_run(base/name,ledger,formal=False)[0] for name in ('gpt_pilot_01','gpt_pilot_02','gpt_pilot_03')]
    errors=[]
    if {r['canonical_controller_sha256'] for r in formal}!={EXPECTED_CONTROLLER}:errors.append('Formal controller identity differs')
    if {r['code_commit'] for r in formal}!={EXPECTED_CODE}:errors.append('Formal execution commit differs')
    if len({r['scene_fingerprint'] for r in formal})!=1:errors.append('Formal scene fingerprints differ')
    source_hashes={}
    for name in ('cubence.py','cubence_tools.py'):
        raw=subprocess.check_output(['git','show',EXPECTED_CODE+':policy/backends/'+name],cwd=ROOT)
        source_hashes[name]=hashlib.sha256(raw).hexdigest()
    if any(r['provider_implementation_sha256']!=source_hashes for r in formal):errors.append('Committed provider implementation hashes differ')
    process_windows=[]
    for index in range(5):
        proof=read(base/'gpt_formal5_01'/f'attempt_{index:04d}'/'process_exit.json')
        start=datetime.fromisoformat(proof['started_utc']);end=start+timedelta(seconds=proof['wall_seconds'])
        process_windows.append(dict(attempt=index,started_utc=start.isoformat(),exited_utc_from_wait_duration=end.isoformat(),gap_after_previous_exit_s=None if index==0 else (start-previous_end).total_seconds()))
        if index and start<previous_end:errors.append('Formal process wall intervals overlap')
        previous_end=end
    outcomes={'true':sum(r['task_success'] is True for r in formal),'false':sum(r['task_success'] is False for r in formal),'null':sum(r['task_success'] is None for r in formal)}
    summary=dict(schema='labsim.Project_v1.gpt_formal5_audit.v1',generated_unix_s=time.time(),finished_state_sha256=sha(args.state),
        execution_commit=EXPECTED_CODE,canonical_controller_sha256=EXPECTED_CONTROLLER,committed_provider_source_sha256=source_hashes,
        process_proof_scope='Supervisor process wait/exit evidence and closed result files; all5 were actual sequential attempts, not successful workflows.',
        protocol=state['formal_protocol'],formal_attempts=5,closed_processes=sum(r['process_exited'] for r in formal),sequential_process_windows=process_windows,
        task_outcome_counts=outcomes,valid_records=sum(r['record_valid'] is True for r in formal),
        qualified_complete_successes=sum(r['record_valid'] is True and r['task_success'] is True for r in formal),
        valid_task_failures=sum(r['record_valid'] is True and r['task_success'] is False for r in formal),
        invalid_or_unknown_outcomes=sum(r['record_valid'] is not True or r['task_success'] is None for r in formal),
        success_rate_among_valid_task_outcomes=(sum(r['record_valid'] is True and r['task_success'] is True for r in formal)/sum(r['record_valid'] is True and r['task_success'] is not None for r in formal)) if any(r['record_valid'] is True and r['task_success'] is not None for r in formal) else None,
        actual_api_decisions=sum(r['api_decisions'] for r in formal),all_decision_image_json_audits_passed=all(r['artifacts']['all_passed'] for r in formal),
        all_formal_audits_passed=not errors and all(r['audit_passed'] for r in formal),audit_errors=errors,
        formal_results=formal,debug_pilots_separate=True,labels_rewritten=False,hdf5_opened_by_this_script=False,
        source_hash_field_note='Supervisor process_exit.controller_sha256 is tools.py source SHA; canonical_controller_sha256 hashes the entire controller document canonically.')
    out=args.output;out.mkdir(parents=True,exist_ok=True)
    for index in range(5):
        if (out/f'attempt_{index:04d}').exists():raise ValueError('Evidence destination exists; preserve existing audit')
    if any((out/name).exists() for name in ('formal5_summary.json','formal5_results.csv','debug_pilots_summary.json','evidence_manifest.json')):
        raise ValueError('Final audit already exists')
    copied=[]
    def copy(source,destination):
        destination.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,destination)
        if sha(source)!=sha(destination):raise RuntimeError('Evidence copy SHA mismatch')
        copied.append(dict(source=str(source.relative_to(ROOT)),destination=str(destination.relative_to(out)),sha256=sha(source),bytes=source.stat().st_size))
    for index in range(5):
        run=base/'gpt_formal5_01'/f'attempt_{index:04d}';destination=out/f'attempt_{index:04d}'
        for rel in ('process_exit.json','run_manifest.json','episode_0000/result.json','episode_0000/independent_score.json','episode_0000/action_receipts.jsonl',
            'episode_0000/release_metadata.json','episode_0000/initialization_timing.json','episode_0000/reset_check.json',
            'episode_0000/gpt_control/controller.json','episode_0000/gpt_control/summary.json','episode_0000/gpt_control/policy_trace.jsonl'):
            source=run/rel
            if source.is_file():copy(source,destination/rel)
        if index==3:
            for source in refs[index]:copy(source,destination/source.relative_to(run))
    copy(args.state,out/'sequence_process_evidence.json')
    def write(name,value):
        with (out/name).open('x') as f:f.write(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    write('formal5_summary.json',summary);write('debug_pilots_summary.json',dict(schema='labsim.Project_v1.gpt_debug_pilots.v1',formal=False,pilots=debug))
    write('evidence_manifest.json',dict(schema='labsim.Project_v1.gpt_small_evidence.v1',files=copied,
        exact_model_input_images_included_for='attempt_0003 only',hdf5_and_raw_physics_logs_included=False,
        note='Original absolute paths in copied JSON are provenance, not promises of packaged files. Other attempts images were audited at source but are not copied.'))
    fields=('name','episode_id','api_decisions','network_attempts','simulation_seconds','actual_control_steps','wall_seconds','record_valid','task_success',
        'failure_type_raw','termination_reason_raw','derived_failure_cause','source_slot_cleared','grasp_success','transport_success','release_observed','retreat_observed','stable_after_retreat','audit_passed')
    with (out/'formal5_results.csv').open('x',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
        for row in formal:writer.writerow({key:('null' if row.get(key) is None else row.get(key)) for key in fields})
    with (out/'README.md').open('x') as f:
        f.write('GPT formal5 closed-attempt evidence\n\nRead formal5_summary.json and formal5_results.csv first. Original labels remain unchanged; null outcomes remain null. Known underlying CONTROL_OR_IK_FAILURE is separate from the wrapper PHYSICS_INVALID label.\n\nAttempt0003 includes the exact JPEG/public JSON inputs under its original gpt_control/observations path. Other attempts include small original logs and source hash audits. HDF5, raw physics logs and most other images are excluded. Absolute paths retained in raw JSON describe original provenance; they are not package-local files. Debug pilots and probe/budget summaries are separate from the formal five.\n')
    print(json.dumps({k:summary[k] for k in ('formal_attempts','task_outcome_counts','valid_records','valid_task_failures','actual_api_decisions','all_formal_audits_passed','audit_errors')},indent=2))
    return 0 if summary['all_formal_audits_passed'] else 2


if __name__=='__main__':raise SystemExit(main())
