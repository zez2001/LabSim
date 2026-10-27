"""Root-authorized one-shot conditional release pi05 acceptance; no credentials/API.

Wait for the actual three-episode same-process predecessor, then start exactly
one environment and one unchanged local checkpoint. Preserve both services
idle after policy finalization for root's additional diagnostics.
"""
from __future__ import annotations
import datetime, fcntl, hashlib, json, os, socket, subprocess, sys, time, urllib.request
from pathlib import Path

REPO=Path('/home/wujing/Desktop/vla/LabSim')
CHECKOUT=Path('/tmp/labsim-project-v1-1-clean-20261027')
ASSETS=Path('/tmp/labsim-release-v1-assets-20261027/bb880f098180c291f6f65995f969d48047207067')
SHA='122c4c03586abdfa7e3117c13e62f8d46f786b04'
OUT=REPO/'outputs/lab_cuvette_loading/Project_release_v1'
GATE=OUT/'same_process_collect_01'
ENV_OUT=OUT/'pi05_standard_01_env'
MODEL_OUT=OUT/'pi05_standard_01_model'
POLICY_OUT=OUT/'pi05_standard_01_policy'
STATE=OUT/'pi05_standard_01_sequence_state.json'
CANCEL=Path('/tmp/labsim-release-pi05-condition-20261027.cancel')
PY='/home/wujing/Desktop/vla/rpent/.venv/bin/python'
ISAAC='/home/wujing/Desktop/vla/labutopia-env/bin/python'
NATIVE_SUP=Path('/tmp/labsim_release_native_supervisor_20261027.py')
CHECKPOINT=Path('/home/wujing/Desktop/vla/rpent/checkpoints/RLinf-Pi05-LIBERO-130-fullshot-SFT')
LEDGER=REPO/'outputs/lab_cuvette_loading/Project_v1/cubence_budget.json'
state=dict(schema='labsim.Project_release_v1.pi05_conditional_supervisor.v1',
    authorized_by_root=True, scheduler_pid=os.getpid(), phase='waiting_for_closed_three_episode_gate',
    expected_commit=SHA, checkpoint_is_labsim_finetuned=False, paid_API_calls=0,
    model_started=False, environment_started=False, policy_started=False,
    waiting_physics='paused outside explicit actions', requested_simulation_s=20,
    requested_model_calls=80, requested_actions=400, services_retained_after_policy=True)

def utc():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def write(path,value):
    path=Path(path);tmp=path.with_name('.'+path.name+'.tmp')
    tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n');os.replace(tmp,path)
def update(**kw):
    state.update(kw,updated_utc=utc());write(STATE,state)
def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(8<<20),b''):h.update(b)
    return h.hexdigest()
def alive(pid):return Path('/proc',str(int(pid))).exists()
def load(path):return json.loads(Path(path).read_text())
def rpc(endpoint,method,*,args=(),kwargs=None,timeout=5):
    data=json.dumps(dict(method=method,args=list(args),kwargs=kwargs or {},session_id=None)).encode()
    req=urllib.request.Request(endpoint+'/call',data=data,headers={'Content-Type':'application/json'})
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(req,timeout=timeout) as f:value=json.loads(f.read())
    if value.get('ok') is not True:raise RuntimeError(str(value.get('error','RPC failed')))
    return value['result']
def reachable(port):
    with socket.socket() as s:s.settimeout(.2);return s.connect_ex(('127.0.0.1',port))==0
def wait_ready(endpoint,child,meta_method,timeout_s):
    deadline=time.monotonic()+timeout_s;last='not_ready'
    while time.monotonic()<deadline:
        if child.poll() is not None:raise RuntimeError('service exited before ready: '+str(child.returncode))
        try:
            health=rpc(endpoint,'healthz');meta=rpc(endpoint,meta_method)
            return dict(health=health,metadata=meta,observed_utc=utc())
        except Exception as e:last=str(e)
        time.sleep(2)
    raise RuntimeError('service readiness timeout: '+last)
def gate():
    if not (GATE/'process_exit.json').is_file():return None
    proof=load(GATE/'process_exit.json')
    if proof.get('process_exited') is not True:return None
    if proof.get('exit_code')!=0:raise RuntimeError('predecessor process did not exit0')
    manifest=load(GATE/'run_manifest.json');summary=load(GATE/'summary.json')
    assert proof['runtime_commit']==manifest['code_commit']==SHA,'predecessor source mismatch'
    assert not alive(proof['pid']) and not alive(manifest['process_id']),'predecessor PID still exists'
    assert manifest['sequence']==['teacher','early_finish','teacher']
    assert manifest['all_episodes_same_process'] is True and manifest['episodes_completed']==3
    assert len(summary)==3 and [r['condition'] for r in summary]==manifest['sequence']
    assert [r['result']['task_success'] for r in summary]==[True,False,True],'teacher/failure sequence did not pass'
    ids=[r['episode_id'] for r in summary];assert len(set(ids))==3
    closure=[]
    for i,r in enumerate(summary):
        episode=GATE/f'episode_{i:04d}'
        result=load(episode/'result.json');marker=load(episode/'episode_0000_complete.json')
        collector=load(episode/'episode_0000_result.json');rows=[json.loads(x) for x in (episode/'dataset/meta/episode.jsonl').read_text().splitlines()]
        assert result['episode_id']==marker['episode_id']==r['episode_id']
        assert result['complete'] is True and result['publication_state']=='complete'
        assert result['record_integrity_valid'] is True and result['task_success']==r['result']['task_success']
        assert len(rows)==1 and rows[0]['episode_id']==r['episode_id']
        assert rows[0]['finalization_id']==marker['finalization_id']==collector['finalization_id']
        assert collector['labels']['complete'] is True and collector['labels']['task_success']==result['task_success']
        streams=load(episode/'recording_closed_receipt.json')
        assert all(v['closed'] is True and v['close_succeeded'] is True for v in streams['streams'].values())
        closure.append(dict(episode_id=r['episode_id'],task_success=result['task_success'],finalization_id=marker['finalization_id']))
    return dict(process_proof=proof,manifest=manifest,episode_closure=closure,
        H5_opened=False,source_files=[dict(path=str(GATE/n),sha256=digest(GATE/n)) for n in ['process_exit.json','run_manifest.json','summary.json']])

if STATE.exists():raise RuntimeError('one-shot scheduler state already exists; refuse duplicate automatic run')
ledger_before=digest(LEDGER);update(started_utc=utc(),cubence_ledger_sha256_before=ledger_before)
try:
    while True:
        if CANCEL.exists():update(phase='cancelled_before_GPU_start');raise SystemExit(0)
        ready=gate()
        if ready is not None:break
        time.sleep(10)
    update(phase='closed_gate_passed',predecessor_gate=ready)
    assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=CHECKOUT,text=True).strip()==SHA
    assert not subprocess.check_output(['git','status','--porcelain'],cwd=CHECKOUT).strip()
    assert all(not p.exists() for p in (ENV_OUT,MODEL_OUT,POLICY_OUT)),'evaluation output already exists'
    assert not reachable(8097) and not reachable(8098),'existing RPC service; do not replace it'
    with open('/tmp/labsim-V0_ext01-gpu.lock','a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    assert digest(CHECKPOINT/'model.safetensors')=='4d9089c941793f170b625c2ed0ac7a3aa09b6f103e52dbbc82e67301529d6683'
    assert digest(CHECKPOINT/'physical-intelligence/libero/norm_stats.json')=='dae37d79a22108af83df9189c6710a3ec8e077d65b28e34bdf1da724e5ae30f1'
    env=dict(os.environ)
    for key in ('CUBENCE_API_KEY','OPENAI_API_KEY','HF_TOKEN','HUGGING_FACE_HUB_TOKEN','HUGGINGFACEHUB_API_TOKEN','CODEX_API_KEY'):
        env.pop(key,None)
    env.update(LABSIM_ASSET_ROOT=str(ASSETS),OMNI_KIT_ACCEPT_EULA='YES',PYTHONHASHSEED='0',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',TOKENIZERS_PARALLELISM='false')
    env_command=[sys.executable,str(NATIVE_SUP),'--checkout',str(CHECKOUT),'--asset-root',str(ASSETS),'--source-sha',SHA,'--output',str(ENV_OUT),'--cli-command','serve','--','--headless','--record-mode','eval','--port','8097']
    envlog=(OUT/'pi05_standard_01_env_supervisor.log').open('x')
    environment=subprocess.Popen(env_command,cwd=CHECKOUT,env=env,stdout=envlog,stderr=subprocess.STDOUT)
    update(phase='starting_release_RPC',environment_started=True,environment_supervisor_pid=environment.pid,environment_command=env_command)
    env_ready=wait_ready('http://127.0.0.1:8097',environment,'env.get_env_meta',300)
    assert env_ready['metadata']['version']=='Project_release_v1'
    model_command=[PY,'-m','policy_backends.lab_cuvette_env_v1.pi05_server','--model-path',str(CHECKPOINT),'--output',str(MODEL_OUT),'--host','127.0.0.1','--port','8098','--seed','0']
    model_log=(OUT/'pi05_standard_01_model.native.log').open('x');model_started=time.perf_counter()
    model=subprocess.Popen(model_command,cwd=CHECKOUT,env=env,stdout=model_log,stderr=subprocess.STDOUT)
    update(phase='starting_real_pi05_checkpoint',environment_ready=env_ready,model_started=True,model_pid=model.pid,model_command=model_command)
    model_ready=wait_ready('http://127.0.0.1:8098',model,'vla.get_metadata',300)
    assert model_ready['metadata']['weights_sha256']=='4d9089c941793f170b625c2ed0ac7a3aa09b6f103e52dbbc82e67301529d6683'
    assert model_ready['metadata']['norm_stats_sha256']=='dae37d79a22108af83df9189c6710a3ec8e077d65b28e34bdf1da724e5ae30f1'
    policy_command=[PY,'-m','policy.backends.rpent_compat','--backend','pi05','--env-endpoint','http://127.0.0.1:8097','--vla-endpoint','http://127.0.0.1:8098','--output',str(POLICY_OUT),'--max-simulation-s','20','--max-model-requests','80','--max-actions','400','--seed','0']
    policy_log=(OUT/'pi05_standard_01_policy.native.log').open('x');policy_started=time.perf_counter()
    policy=subprocess.Popen(policy_command,cwd=CHECKOUT,env=env,stdout=policy_log,stderr=subprocess.STDOUT)
    update(phase='real_pi05_policy_running',model_ready=model_ready,policy_started=True,policy_pid=policy.pid,policy_command=policy_command)
    while policy.poll() is None:
        update(phase='real_pi05_policy_running',policy_wall_seconds=time.perf_counter()-policy_started)
        time.sleep(5)
    code=policy.wait();assert not alive(policy.pid)
    policyproof=dict(schema='labsim.Project_release_v1.pi05_policy_process.v1',pid=policy.pid,process_exited=True,exit_code=code,runtime_commit=SHA,command=policy_command,wall_seconds=time.perf_counter()-policy_started,completion_evidence='parent Popen.wait returned; actual policy PID absent',credentials_in_child=False,UTC=utc())
    write(POLICY_OUT/'process_exit.json',policyproof)
    result=load(POLICY_OUT/'result.json')
    ledger_after=digest(LEDGER)
    update(phase='policy_closed_services_idle_for_root_diagnostics',policy_process_proof=policyproof,policy_result=result,
        model_service_running=model.poll() is None,environment_service_running=environment.poll() is None,
        cubence_ledger_sha256_after_policy=ledger_after,cubence_ledger_unchanged=ledger_after==ledger_before,
        services_note='No shutdown requested by scheduler; root may perform short public RPC diagnostics. Physics idle/paused.')
    # Root owns explicit shutdown after its additional diagnostics. Do not close
    # the paused environment or model implicitly when this policy ends.
    model_proved=False;env_proved=False
    while not (model_proved and env_proved):
        if not model_proved and model.poll() is not None:
            mcode=model.wait();assert not alive(model.pid)
            proof=dict(schema='labsim.Project_release_v1.pi05_model_process.v1',pid=model.pid,process_exited=True,exit_code=mcode,runtime_commit=SHA,command=model_command,wall_seconds=time.perf_counter()-model_started,completion_evidence='parent Popen.wait returned; actual model PID absent',credentials_in_child=False,UTC=utc())
            write(MODEL_OUT/'process_exit.json',proof);state['model_process_proof']=proof;model_proved=True
        if not env_proved and environment.poll() is not None:
            ecode=environment.wait();assert not alive(environment.pid)
            state['environment_supervisor_exit_code']=ecode;state['environment_supervisor_PID_gone']=True;env_proved=True
        if not (model_proved and env_proved):
            update(model_service_running=not model_proved,environment_service_running=not env_proved)
            time.sleep(5)
    update(phase='all_processes_closed_after_root_diagnostics',finished_utc=utc())
except BaseException as error:
    if isinstance(error,SystemExit):raise
    import traceback
    update(phase='blocked_or_failed_no_automatic_retry',error_type=type(error).__name__,error=str(error),traceback=traceback.format_exc(),automatic_retry=False)
    raise
