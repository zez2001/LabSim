"""Ten bounded, explicitly non-task reset/recording resource probes on existing RPC."""
import json,pathlib,subprocess,os,time,urllib.request,datetime,hashlib
BASE=pathlib.Path("/home/wujing/Desktop/vla/LabSim/outputs/lab_cuvette_loading/Project_release_v1")
OUT=BASE/"reset_resource_probe_01";OUT.mkdir(exist_ok=False)
S=json.loads((BASE/"pi05_standard_01_sequence_state.json").read_text());assert S["phase"]=="policy_closed_services_idle_for_root_diagnostics"
P=json.loads((BASE/"pi05_standard_01_env.supervisor.json").read_text());wrapper=int(P["pid"])
children=pathlib.Path(f"/proc/{wrapper}/task/{wrapper}/children").read_text().split();assert len(children)==1
native=int(children[0]);opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
def call(method,kwargs=None):
 req=urllib.request.Request("http://127.0.0.1:8097/call",data=json.dumps(dict(method=method,args=[],kwargs=kwargs or {},session_id=None)).encode(),headers={"Content-Type":"application/json"})
 with opener.open(req,timeout=180) as f:d=json.load(f)
 if not d["ok"]:raise RuntimeError(str(d))
 return d["result"]
def attempt(method,kwargs):
 try:return dict(accepted=True,result=call(method,kwargs))
 except Exception as e:return dict(accepted=False,error=str(e))
def resources(event,index):
 vals={}
 for l in pathlib.Path(f"/proc/{native}/status").read_text().splitlines():
  if l.startswith(("VmRSS:","VmHWM:")):
   k,v,_=l.split();vals[k[:-1]+"_bytes"]=int(v)*1024
 vals["file_descriptors"]=len(list(pathlib.Path(f"/proc/{native}/fd").iterdir()))
 result=subprocess.run(["nvidia-smi","--query-compute-apps=pid,used_gpu_memory","--format=csv,noheader,nounits"],capture_output=True,text=True,timeout=10)
 vals["VRAM_MiB"]=sum(float(l.split(",")[1]) for l in result.stdout.splitlines() if l.split(",")[0].strip()==str(native))
 return dict(event=event,index=index,pid=native,**vals)
def public_summary(o):
 return {k:o.get(k) for k in ("episode_id","observation_id","step_index","simulation_time","joint_positions","TCPpose")}
rows=[];snapshots=[resources("before_reset_probes",-1)];old=None;start=time.perf_counter()
try:
 for i in range(10):
  obs,info=call("env.reset",dict(seed=0,options=dict(mode="standard",policy_id="release_short_reset_resource_probe")))
  snapshots.append(resources("after_reset",i));record=dict(index=i,kind="short_interface_resource_diagnostic",not_complete_task_evaluation=True,initial_observation=public_summary(obs))
  if old:
   before=call("project.status");stale=attempt("project.execute",dict(action=old));after=call("project.status")
   assert stale["accepted"] is False and before==after
   record["old_episode_rejected_without_step"]=True
  action=dict(action_id=obs["episode_id"]+":reset_probe:0",episode_id=obs["episode_id"],observation_id=obs["observation_id"],type="ee_delta",frame="world",values=[0.]*6,duration_s=.05)
  receipt=call("project.execute",dict(action=action));before=call("project.status");repeat=call("project.execute",dict(action=action));after=call("project.status")
  assert receipt==repeat and before==after
  final=call("project.finish",dict(reason="SHORT_RESET_RESOURCE_DIAGNOSTIC_END"));again=call("project.finish",dict(reason="DUPLICATE_MUST_NOT_RELABEL"));assert final==again
  assert final["task_success"] is False
  record.update(receipt=receipt,final_status=final,duplicate_action_zero_extra_steps=True,duplicate_finish_unchanged=True)
  rows.append(record);old=action;snapshots.append(resources("after_finish",i))
  (OUT/"resource_probe.json").write_text(json.dumps(dict(schema="labsim.release.short_reset_resource_probe.v1",native_PID=native,wrapper_PID=wrapper,source_runtime=P["runtime_commit"],episodes=rows,resource_samples=snapshots,scope="Ten 0.05s zero-delta physical episodes after real pi05 evaluation; diagnostics, not model inference or complete-task failures",model_calls=0,all_same_native_process=True,wall_seconds=time.perf_counter()-start),indent=2)+"\n")
  print("RESET_RESOURCE_PROBE",i,final["episode_id"],snapshots[-1],flush=True)
 call("shutdown");(OUT/"shutdown_requested.json").write_text(json.dumps(dict(endpoint="http://127.0.0.1:8097",method="shutdown",after_ten_closed_diagnostics=True,wall_seconds=time.perf_counter()-start))+"\n")
except BaseException as e:
 (OUT/"probe_failure.json").write_text(json.dumps(dict(type=type(e).__name__,error=str(e),closed_episodes=len(rows)),indent=2)+"\n");raise
