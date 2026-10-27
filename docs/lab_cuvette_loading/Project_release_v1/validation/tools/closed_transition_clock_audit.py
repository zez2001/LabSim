"""Closed-only scalar clock/transition audit, never changes H5 or labels."""
import argparse,hashlib,json,pathlib,time
import h5py,numpy as np
p=argparse.ArgumentParser();p.add_argument("run",type=pathlib.Path);p.add_argument("--output",required=True,type=pathlib.Path);a=p.parse_args()
r=a.run.resolve();proof=json.loads((r/"process_exit.json").read_text());manifest=json.loads((r/"run_manifest.json").read_text())
assert proof["process_exited"] is True and proof["exit_code"]==0
assert not pathlib.Path("/proc",str(proof["pid"])).exists()
assert not pathlib.Path("/proc",str(manifest["process_id"])).exists()
assert not a.output.exists()
def stats(x):
 x=np.asarray(x,float);good=x[np.isfinite(x)]
 return dict(count=int(x.size),nonfinite=int(x.size-good.size),minimum_s=float(good.min()) if good.size else None,maximum_s=float(good.max()) if good.size else None,median_s=float(np.median(good)) if good.size else None)
rows=[]
for h in sorted(r.glob("episode_*/dataset/*.h5")):
 init=json.loads((h.parent.parent/"initialization_timing.json").read_text());origin=float(init["engine_clock_origin_s"])
 with h5py.File(h,"r") as f:
  assert bool(f.attrs["complete"])
  t=f["timestamp"][:];nt=f["next_timestamp"][:];s=f["obs_step"][:];ns=f["next_obs_step"][:];interval=f["control_interval_s"][:]
  cameras={}
  for name in ("side_camera_rgb","wrist_camera_rgb"):
   ct=f["camera_timestamp/"+name][:];cameras[name]=dict(sensor_engine_minus_origin_minus_obs=stats(ct-origin-t),sensor_time_monotonic=bool(np.all(np.diff(ct)>=0)))
  rows.append(dict(episode=h.parent.parent.name,H5_source=str(h),source_size_bytes=h.stat().st_size,engine_clock_origin_s=origin,transitions=len(t),obs_time_monotonic=bool(np.all(np.diff(t)>0)),successor_steps=np.unique(ns-s).tolist(),successor_time_delta=stats(nt-t),interval_minus_time_delta=stats(interval-(nt-t)),next_state_equals_next_row_time=bool(np.allclose(nt[:-1],t[1:],rtol=0,atol=1e-9)),cameras=cameras))
result=dict(schema="labsim.release.closed_transition_clock_audit.v1",source_run=str(r),runtime_commit=manifest["code_commit"],launcher_and_native_PID_gone=True,scope="Full scalar timestamp arrays and declared engine origin; no pixel-pose synchronization certification, no source rewrite",episodes=rows)
a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2)+"\n");print(json.dumps(result,indent=2))
