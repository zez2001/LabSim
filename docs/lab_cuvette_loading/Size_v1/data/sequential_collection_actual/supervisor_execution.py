from __future__ import annotations
import os
for k in ('OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS','NUMEXPR_NUM_THREADS'):
    os.environ[k]='2'
import datetime, fcntl, hashlib, json, shutil, subprocess, sys, time, traceback
from pathlib import Path
ROOT=Path('/home/wujing/Desktop/vla/LabSim')
sys.path.insert(0,str(ROOT))
from scripts.collect_lab_cuvette_size_v1_standard import statistics
from scripts.validate_lab_cuvette_size_v1_data import audit_episode, official_process_gate
C=ROOT/'outputs/lab_cuvette_loading/Size_v1/collection_standard'
F='f435d2a43aae5ba78f71bbc754b0ecaf401924e9b56db462606c0c5406fbd59b'
A='cuvette_xy_1000'
PYTHON=ROOT.parent/'labutopia-env/bin/python'
AUDIT=Path('/tmp/labsim-size-sequential-batch-audits-20261021')
AUDIT.mkdir(exist_ok=True)
EXPECTED_FLAGS={'NATIVE_FD_LINEAR_VELOCITY_DISAGREEMENT','NATIVE_TARGET_OVERLAP_UNAVAILABLE'}
START=datetime.datetime.now(datetime.timezone.utc).isoformat()
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def log(event,**kw):
    row=dict(time_utc=now(),event=event,**kw)
    print(json.dumps(row,ensure_ascii=False,allow_nan=False),flush=True)
    with (AUDIT/'events.jsonl').open('a') as f:f.write(json.dumps(row,ensure_ascii=False,allow_nan=False)+'\n')
def read(p):return json.loads(Path(p).read_text())
def require(test,msg):
    if not test: raise RuntimeError(msg)
def sha(p):
    h=hashlib.sha256()
    with open(p,'rb') as f:
        for chunk in iter(lambda:f.read(4*1024*1024),b''):h.update(chunk)
    return h.hexdigest()
def totals():
    d=statistics(C,F,A)
    return {k:v for k,v in d.items() if k!='episodes'}
def locks_free():
    for p in ('/tmp/labsim-Size_v1-collection-driver.lock','/tmp/labsim-V0_ext01-gpu.lock'):
        with open(p,'a') as f:
            fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
            fcntl.flock(f,fcntl.LOCK_UN)
def validate_batch(record,expected_phase,expected_count,expected_depth=None):
    b=read(record);run=Path(b['run_directory']);proof=read(run/'process_exit.json')
    require(b.get('official_collection_run') is True,'not official driver')
    for d in (b,proof):
        require(d.get('process_exited') is True and d.get('exit_code')==0 and not isinstance(d.get('exit_code'),bool) and d.get('interrupted') is False,'actual child process nonzero/unknown/interrupted')
        require(Path(d['run_directory']).resolve()==run.resolve(),'process run mismatch')
    require(b['phase']==expected_phase,'unexpected phase')
    require(b['requested_episodes']==expected_count,'unexpected episode count')
    require(b['frozen_scene_sha256']==F,'driver frozen scene changed')
    require(sha(b['config_path'])==b['config_sha256'],'config hash no longer matches actual launch')
    phase_id=run.name.rsplit('_',1)[0]
    phase=read(C/(phase_id+'_result.json'))
    require(phase['phase']==expected_phase and phase['status'] in ('maximum_processes_reached','target_reached') and not phase['prelaunch_or_driver_stops'],'phase abnormal result')
    require(phase['randomization_enabled'] is False and phase['labels_modified'] is False,'phase changed scene/labels')
    archives=b['archive_results'];require(len(archives)==expected_count and all(x['archived'] is True for x in archives),'archive count or status failed')
    eps=sorted(run.glob('episode_*/dataset/episode_0000.h5'))
    require(len(eps)==expected_count,'episode actual count differs requested')
    verified_archives=[]
    for ar in archives:
        m=read(ar['manifest']);require(m['state']=='complete_original_bytes_recoverable_from_verified_gzip','archive not complete')
        require(m['HDF5_labels_videos_modified'] is False,'archive changed HDF5/media')
        require(m['closed_episode_evidence']['process_exit_evidence']['sha256']==sha(run/'process_exit.json'),'archive process evidence hash mismatch')
        require(len(m['files'])==2,'archive missing physics/contact logs')
        for item in m['files']:
            require(item['decompressed_bytes_equal_original'] is True and item['original_sha256']==item['decompressed_sha256'],'archive decompressed bytes mismatch')
            p=Path(item['archive_path']);require(p.is_file() and p.stat().st_size==item['archive_bytes'] and sha(p)==item['archive_sha256'],'actual gzip missing/mismatched')
            require(not Path(item['original_path']).exists() and item['raw_removed'] is True,'raw archive state inconsistent')
        verified_archives.append(dict(manifest=ar['manifest'],manifest_sha256=sha(ar['manifest']),verified_gzip_files=2))
    rows=[]
    for source in eps:
        row=official_process_gate(audit_episode(source,F),C)
        require(not row['admission_errors'],str(source)+' production admission errors '+str(row['admission_errors']))
        result=read(source.parents[1]/'result.json')
        require(result.get('complete') is True and result.get('record_valid') is True and result.get('geometry_valid') is True,'physical validity false')
        require(not result.get('invalid_state_reasons'),'unexpected invalid state')
        require(set(result.get('physics_quality_flags',[]))==EXPECTED_FLAGS,'new/unexpected physics quality flags '+str(result.get('physics_quality_flags')))
        require(result.get('native_pair_success') is not True and result.get('real_calibrated') is False,'native calibration status incorrectly changed')
        require(row['labels'].get('asset_id')==A and row['labels'].get('frozen_scene_sha256')==F,'frozen asset mismatch')
        if expected_phase=='success':
            require(row['success'] is True and row['failure'] is False and row['labels']['condition_group']=='natural','natural batch contains non-success')
            for k in ('task_success','workflow_success','full_success','source_slot_cleared','grasp_success','transport_success','loading_sequence_observed','release_observed','retreat_observed','stable_after_retreat'):
                require(result.get(k) is True,'physical success step failed '+k)
            w=result['post_retreat_window'];require(w['status']=='complete' and w['stable'] is True and w['measured_duration_s']>=3,'post retreat 3 sec missing')
        else:
            require(row['failure'] is True and row['success'] is False,'controlled record not valid actual task failure')
            require(row['labels']['condition_group']=='deterministic_action_deviation','wrong failure group')
            event=row['controlled_deviation_event_evidence'];require(event and event['qualified'] is True and not event['errors'],'actual controlled event failed')
            require(abs(event['configuration_spec']['stop_insertion_at_depth_m']-expected_depth)<1e-12,'unexpected controlled depth rotation')
            require(abs(event['actual_event']['actual_depth_m']-expected_depth)<=.0001,'actual stop overshoot unexpectedly exceeds 0.1 mm')
        row['actual_result_key_fields']={k:result.get(k) for k in ('complete','record_valid','task_success','failure_type','termination_reason','source_slot_cleared','grasp_success','transport_success','loading_sequence_observed','release_observed','retreat_observed','stable_after_retreat','post_retreat_window','physics_quality_flags')}
        rows.append(row)
    out=dict(schema='labsim.Size_v1.sequential_batch_gate.cpu_audit.v1',source_driver=str(record),driver_sha256=sha(record),actual_child_exit=proof,phase_parent_status=phase['status'],expected_phase=expected_phase,expected_count=expected_count,expected_depth_m=expected_depth,frozen_scene_sha256=F,archive_validation=verified_archives,episodes=rows,all_checks_passed=True,source_labels_or_data_modified=False,finished_utc=now())
    outpath=AUDIT/(run.name+'.json')
    with outpath.open('x') as f:json.dump(out,f,indent=2,ensure_ascii=False,allow_nan=False)
    log('BATCH_STRICTLY_VALIDATED',run=run.name,proof_child_exit_code=proof['exit_code'],count=expected_count,depth_m=expected_depth,audit=str(outpath),totals=totals())
    return out

def wait_existing():
    name='success_20261021T050557Z_1940849e_00'
    rec=C/'driver_records'/('batch_'+name+'.json')
    phase=C/(name.rsplit('_',1)[0]+'_result.json')
    last=None;tick=0
    while not (rec.is_file() and phase.is_file()):
        done=[]
        for e in sorted((C/'runs'/name).glob('episode_*/result.json')):
            try:
                d=read(e)
                if d.get('complete') is True:done.append(dict(episode=e.parent.name,valid=d.get('record_valid'),success=d.get('task_success'),reason=d.get('termination_reason')))
            except (OSError,ValueError):pass
        marker=json.dumps(done,sort_keys=True)
        if marker!=last or tick%10==0:
            log('WAIT_CURRENT_BATCH_METADATA',run=name,closed_result_sidecars=done,process_exit_available=(C/'runs'/name/'process_exit.json').is_file(),free_GiB=round(shutil.disk_usage(C).free/2**30,2))
            last=marker
        time.sleep(30);tick+=1
    validate_batch(rec,'success',5)
    t=totals();require(t['success']==15 and t['failure']==1 and t['natural_failure']==0 and t['archived_not_counted']==0,'unexpected existing batch totals')
    return name

def execute_one(phase,expected_count,logpath,expected_depth=None):
    # Wait only for prior CLI lock release after its finalized metadata, never run two Isaac processes.
    for _ in range(30):
        try:locks_free();break
        except BlockingIOError:time.sleep(1)
    else:raise RuntimeError('previous driver/GPU lock still held after finalized run')
    require(shutil.disk_usage(C).free>=20*2**30,'less than 20GiB free; conservative stop before batch')
    previous=set((C/'driver_records').glob('batch_*.json'))
    cmd=[str(PYTHON),'scripts/collect_lab_cuvette_size_v1_standard.py','--phase',phase,'--collection',str(C),'--allow-after-verified-five','--max-processes','1','--episodes-per-process','5','--headless']
    log('LAUNCH_ONE_EXISTING_CLI',phase=phase,expected_count=expected_count,expected_depth_m=expected_depth,argv=cmd,stdout=str(logpath),free_GiB=round(shutil.disk_usage(C).free/2**30,2))
    with Path(logpath).open('x') as f:
        p=subprocess.Popen(cmd,cwd=ROOT,stdout=f,stderr=subprocess.STDOUT)
        log('DRIVER_PARENT_STARTED',pid=p.pid)
        last=None;tick=0
        while p.poll() is None:
            new=[x for x in (C/'runs').glob(phase+'_*') if C/'driver_records'/('batch_'+x.name+'.json') not in previous]
            latest=max(new,key=lambda x:x.stat().st_mtime) if new else None
            closed=[]
            if latest:
                for q in sorted(latest.glob('episode_*/result.json')):
                    try:
                        d=read(q)
                        if d.get('complete') is True:closed.append(dict(episode=q.parent.name,valid=d.get('record_valid'),success=d.get('task_success'),reason=d.get('termination_reason')))
                    except (OSError,ValueError):pass
            marker=json.dumps(closed,sort_keys=True)
            if marker!=last or tick%10==0:
                log('DRIVER_PROGRESS_CLOSED_METADATA_ONLY',phase=phase,run=latest.name if latest else None,closed_result_sidecars=closed,free_GiB=round(shutil.disk_usage(C).free/2**30,2))
                last=marker
            time.sleep(30);tick+=1
        code=p.wait()
    log('DRIVER_PARENT_WAIT_RETURNED',phase=phase,exit_code=code,stdout=str(logpath))
    require(code in (0,2),'unexpected collector parent exit '+str(code))
    added=set((C/'driver_records').glob('batch_*.json'))-previous
    require(len(added)==1,'expected exactly one new closed batch')
    record=added.pop()
    validate_batch(record,phase,expected_count,expected_depth)
    phase_status=read(C/(read(record)['run_directory'].split('/')[-1].rsplit('_',1)[0]+'_result.json'))['status']
    require((code==0)==(phase_status=='target_reached'),'parent return code and phase status disagree')
    return record

def main():
    # Exclusive supervisor ownership prevents accidental duplicate external orchestration.
    own=open('/tmp/labsim-Size_v1-audit-supervisor.lock','a')
    fcntl.flock(own,fcntl.LOCK_EX|fcntl.LOCK_NB)
    log('SUPERVISOR_START',started_utc=START,source_config_or_assets_modified=False,plan='existing natural batch -> last natural5 -> four controlled batches 5/5/5/4 at5/10/18/1mm')
    wait_existing()
    execute_one('success',5,Path('/tmp/labsim-size-success-batch03-driver.log'))
    t=totals();require(t['success']==20 and t['failure']==1 and t['natural_failure']==0 and t['archived_not_counted']==0,'natural target totals not 20/1')
    for i,(depth,n) in enumerate(((.005,5),(.010,5),(.018,5),(.001,4)),1):
        execute_one('controlled_failure',n,Path(f'/tmp/labsim-size-controlled-remaining19-batch{i:02d}-driver.log'),depth)
        t=totals();require(t['success']==20 and t['failure']==1+sum(v for _,v in ((.005,5),(.010,5),(.018,5),(.001,4))[:i]) and t['natural_failure']==0 and t['archived_not_counted']==0,'unexpected counts after controlled batch')
    t=totals();require(t['success']==20 and t['failure']==20 and t['controlled_failure']==20 and t['nonzero_exit_processes']==0 and t['interrupted_processes']==0,'final 20/20 actual target not satisfied')
    log('ALL_SEQUENTIAL_COLLECTION_FINISHED_AND_VERIFIED',totals=t,final_indexes_not_generated=True)
    own.close()
if __name__=='__main__':
    try:main()
    except BaseException as e:
        log('STOP_NO_FURTHER_LAUNCH',exception_type=type(e).__name__,exception=str(e),traceback=traceback.format_exc());raise
