"""Read the closed ordinary Teacher run without changing source data."""
import argparse, hashlib, json, os, subprocess, gzip
from pathlib import Path
import h5py
import numpy as np
p=argparse.ArgumentParser();p.add_argument('run',type=Path);p.add_argument('--output',required=True,type=Path);a=p.parse_args()
r=a.run.resolve();a.output.mkdir(parents=True,exist_ok=False)
def load(p):return json.loads(p.read_text())
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(8<<20),b''):h.update(b)
 return h.hexdigest()
def save(n,v):(a.output/n).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
proof=load(r/'process_exit.json');manifest=load(r/'run_manifest.json');startup=load(r/'startup_summary.json')
assert proof['exit_code']==0 and proof['process_exited']
assert all(not Path('/proc',str(pid)).exists() for pid in (proof['pid'],manifest['process_id']))
assert manifest['code_commit']==proof['runtime_commit']=='5c6b6422f9ba6fc16ac7b4374799c5ed7e426e47'
e=r/'episode_0000';result=load(e/'result.json');assert result['task_success'] is True and result['record_valid'] is True
assert result['record_integrity_valid'] is True and result['success_bc_eligible'] is True
assert result['post_retreat_window']['stable'] is True and result['post_retreat_window']['measured_duration_s']>=3
assert result['record_purpose']=='demonstration' and startup['version']=='Project_release_v1'
assert startup['asset_id']=='cuvette_xy_1000' and startup['record_mode']=='collect'
h=e/'dataset/episode_0000.h5';before=sha(h);datasets=[];seen=set()
with h5py.File(h) as f:
 assert f.attrs['record_purpose']=='demonstration' and bool(f.attrs['complete']) and f.attrs['publication_state']=='complete'
 assert f.attrs['episode_id']==result['episode_id'] and f.attrs['finalization_id']==result['finalization_id']
 metadata=json.loads(f['episode_metadata_json'].asstr()[()]);assert metadata['record_purpose']=='demonstration'
 def visit(name,obj):
  if not isinstance(obj,h5py.Dataset):return
  addr=h5py.h5o.get_info(obj.id).addr
  if addr in seen:return
  seen.add(addr)
  if not obj.shape:obj[()]
  else:
   # Bound each full-read slice; decode/check all stored chunks, not only batch samples.
   row_bytes=max(1,int(np.prod(obj.shape[1:]))*obj.dtype.itemsize);step=max(1,(32<<20)//row_bytes)
   for start in range(0,len(obj),step):obj[start:start+step]
  datasets.append(dict(path=name,shape=list(obj.shape),dtype=str(obj.dtype)))
 f.visititems(visit)
 attrs={k:(v.item() if isinstance(v,np.generic) else str(v)) for k,v in f.attrs.items()}
 assert f.attrs['record_purpose']==metadata['record_purpose']==result['record_purpose']
after=sha(h);assert before==after
movies=[]
for name in ('side_camera.mp4','wrist_camera.mp4','dual_view.mp4'):
 path=e/name
 if not path.exists():continue
 info=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration:stream=width,height,nb_frames,r_frame_rate','-of','json',str(path)],text=True))
 subprocess.run(['ffmpeg','-v','error','-i',str(path),'-f','null','-'],check=True,capture_output=True)
 movies.append(dict(path=str(path),bytes=path.stat().st_size,sha256=sha(path),probe=info,full_decode_passed=True))
assert len(movies)==3
streams=[]
for path in sorted(e.glob('*.jsonl.gz')):
 digest=hashlib.sha256();line_count=0;byte_count=0
 with gzip.open(path,'rb') as stream:
  for line in stream: digest.update(line);line_count+=1;byte_count+=len(line)
 streams.append(dict(path=str(path),compressed_bytes=path.stat().st_size,uncompressed_bytes=byte_count,lines=line_count,uncompressed_sha256=digest.hexdigest(),gzip_EOF_CRC_valid=True))
save('gzip_streams.json',streams)
save('summary.json',dict(schema='labsim.Internal_use_v1.ordinary_teacher_closed.v1',run=str(r),runtime_commit=proof['runtime_commit'],exit_code=0,launcher_and_native_PID_gone=True,ordinary_teacher_entry=True,acceptance_sequence_used=False,task_success=True,record_valid=True,record_integrity_valid=True,success_bc_eligible=True,record_purpose='demonstration',asset_id=startup['asset_id'],version=startup['version'],startup=startup,transitions=int(result['frames']),post_retreat_window=result['post_retreat_window'],physics_quality_flags=result['physics_quality_flags'],h5=dict(path=str(h),bytes=h.stat().st_size,sha256=before,all_unique_datasets_read=True,unique_dataset_count=len(datasets),hash_unchanged_after_read=True),movies=movies,gzip_streams=streams))
save('H5_datasets.json',datasets);save('H5_attrs.json',attrs)
for name in ('result.json','release_metadata.json','reset_audit.json','recording_configuration.json','project_scene_contract.json'):
 save(name,load(e/name))
for name in ('process_exit.json','run_manifest.json','startup_summary.json','launch_identity.json','application_shutdown.json'):
 save(name,load(r/name))
print(json.dumps(dict(task_success=True,transitions=result['frames'],H5_bytes=h.stat().st_size,unique_datasets=len(datasets),movies=len(movies)),indent=2))
