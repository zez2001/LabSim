"""Inspect an actual closed Env_v1 episode, without simulation or label edits."""
from __future__ import annotations
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
from fractions import Fraction
import h5py
import numpy as np
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from scripts.read_lab_cuvette_env_v1_data import inspect as normal_read


def plain(x):
    if isinstance(x,dict):return {str(k):plain(v) for k,v in x.items()}
    if isinstance(x,np.ndarray):return plain(x.tolist())
    if isinstance(x,(tuple,list)):return [plain(v) for v in x]
    if isinstance(x,(np.bool_,bool)):return bool(x)
    if isinstance(x,(np.integer,int)):return int(x)
    if isinstance(x,(np.floating,float)):return float(x) if np.isfinite(x) else None
    if isinstance(x,bytes):return x.decode()
    return x


def scan_links(group,prefix=''):
    bad=[]
    for key in group:
        name=prefix+'/'+key;link=group.get(key,getlink=True)
        if not isinstance(link,h5py.HardLink):bad.append(dict(path=name,type=type(link).__name__));continue
        obj=group[key]
        if isinstance(obj,h5py.Group):bad+=scan_links(obj,name)
        else:
            if obj.is_virtual:bad.append(dict(path=name,type='VDS'))
            if obj.external:bad.append(dict(path=name,type='external_storage'))
    return bad


def statistics(dataset):
    black=0;repeated=0;last=None;means=[];std=[];digests=[]
    for i in range(len(dataset)):
        image=dataset[i];digest=hashlib.sha256(image.tobytes()).hexdigest()
        repeated+=int(last==digest);last=digest;digests.append(digest)
        black+=int(image.max()<=1);means.append(float(image.mean()));std.append(float(image.std()))
    return dict(frames=len(dataset),black_frames=black,consecutive_identical_RGB_frames=repeated,
        unique_RGB_hashes=len(set(digests)),mean_intensity_range=[min(means),max(means)] if means else None,
        spatial_std_range=[min(std),max(std)] if std else None,
        repeat_note='Identical RGB can represent a static scene; sensor frame tokens checked independently.')


def pose_source_statistics(poses,camera):
    """Read recorded transform alternatives; never infer which pose rendered RGB."""
    result={}
    for source in ('USD','camera_API_USD','Fabric','physics_hand_times_mount'):
        rows=[p[camera].get('pose_sources',{}).get(source) for p in poses]
        available=[r for r in rows if r and r.get('available')]
        position=[r['position_delta_from_USD_m'] for r in available if r.get('position_delta_from_USD_m') is not None]
        angle=[r['rotation_delta_from_USD_deg'] for r in available if r.get('rotation_delta_from_USD_deg') is not None]
        result[source]=dict(records_with_field=sum(r is not None for r in rows),available_records=len(available),
            unavailable_records=sum(bool(r) and not r.get('available') for r in rows),
            max_position_difference_from_USD_m=max(position) if position else None,
            max_rotation_difference_from_USD_deg=max(angle) if angle else None,
            first_available_world_from_camera=available[0].get('world_from_camera') if available else None,
            last_available_world_from_camera=available[-1].get('world_from_camera') if available else None,
            unavailable_reasons=[dict(reason=r.get('reason'),error_type=r.get('error_type'),message=r.get('message')) for r in rows if r and not r.get('available')][:3])
    return dict(sources=result,rendered_pixel_pose_association='Not proven by transform agreement alone; inspect actual image projections and scene features.')


def video(path,output):
    probe=subprocess.run(['ffprobe','-v','error','-count_frames','-select_streams','v:0','-show_streams','-of','json',str(path)],capture_output=True,text=True)
    if probe.returncode:return dict(path=str(path),present=True,ffprobe_error=probe.stderr)
    stream=json.loads(probe.stdout)['streams'][0];count=int(stream.get('nb_read_frames',stream.get('nb_frames',0)))
    fps=float(Fraction(stream['avg_frame_rate']))
    result=dict(path=str(path.resolve()),present=True,frames=count,fps=fps,resolution_wh=[stream['width'],stream['height']],
        duration_s=float(stream.get('duration',count/fps)),last_frame_nominal_time_s=(count-1)/fps)
    decode=subprocess.run(['ffmpeg','-v','error','-i',str(path),'-f','null','-'],capture_output=True,text=True)
    result.update(full_CPU_decode_exit_code=decode.returncode,decode_error=decode.stderr[-2000:])
    for index,label in [(0,'first'),(max(0,count//2),'middle'),(max(0,count-1),'last')]:
        dest=output/(path.stem+'_'+label+'.png')
        run=subprocess.run(['ffmpeg','-v','error','-i',str(path),'-vf',f'select=eq(n\\,{index})','-frames:v','1',str(dest)],capture_output=True,text=True)
        if run.returncode:result.setdefault('sample_errors',[]).append(run.stderr[-500:])
    return result


def inspect_episode(episode,output):
    episode=Path(episode).resolve();output=Path(output).resolve()
    source=episode/'dataset/episode_0000.h5'
    if not source.is_file():raise FileNotFoundError(source)
    output.mkdir(parents=True,exist_ok=False)
    result=dict(schema='labsim.Env_v1.actual_episode_inspection.v1',source_episode=str(episode),
        no_simulation_started=True,raw_labels_modified=False,training_executed=False)
    cfg=json.loads((episode/'result.json').read_text()) if (episode/'result.json').exists() else {}
    score=json.loads((episode/'independent_score.json').read_text()) if (episode/'independent_score.json').exists() else {}
    first_physics=None;last_physics=None;count_physics=0;monotonic=True;last_t=None
    for line in (episode/'physics_records.jsonl').open():
        row=json.loads(line);count_physics+=1
        if first_physics is None:first_physics=row
        if last_t is not None and row['t']<=last_t:monotonic=False
        last_t=row['t'];last_physics=row
    origin=first_physics.get('engine_time',0)-first_physics['t']
    result['physics']=dict(samples=count_physics,initial_t=first_physics['t'],final_t=last_physics['t'],
        initial_engine_time=first_physics.get('engine_time'),final_engine_time=last_physics.get('engine_time'),
        engine_minus_episode_time_origin_s=origin,strictly_monotonic=monotonic)
    with h5py.File(source) as h:
        n=len(h['actions']);result['transitions']=n
        labels={k:plain(h.attrs.get(k)) for k in ('episode_id','scene_version','task_type','complete','record_valid','task_success',
            'failure_type','termination_reason','eligible_for_success_bc','eligible_for_failure_analysis','real_calibrated')}
        result['H5_labels']=labels;result['independent_score_labels']={k:score.get(k) for k in labels}
        compare=('record_valid','task_success','failure_type','termination_reason','eligible_for_success_bc','eligible_for_failure_analysis')
        result['label_consistency']={k:labels[k]==score.get(k) for k in compare}
        result['labels_do_not_count_diagnostics_as_loading']=not(labels.get('task_type')!='loading' and (labels.get('eligible_for_success_bc') or labels.get('eligible_for_failure_analysis')))
        result['external_data_dependencies']=scan_links(h)
        result['self_contained_HDF5']=not result['external_data_dependencies']
        before,after=h['timestamp'][:],h['next_timestamp'][:]
        result['time_alignment']=dict(first_obs_t=float(before[0]) if n else None,last_next_t=float(after[-1]) if n else None,
            intervals_range_s=[float(np.min(after-before)),float(np.max(after-before))] if n else None,
            strictly_monotonic_before=bool(np.all(np.diff(before)>0)),successor_time_matches_next_observation=bool(np.allclose(after[:-1],before[1:],atol=1e-9,rtol=0)))
        result['action_state_checks']=dict(executed_9d_maps_exactly_to_legacy8=bool(np.array_equal(h['control_auxiliary/command_q'][:,:8].astype(np.float32),h['actions'][:])),
            actual_9d_maps_exactly_to_legacy8=bool(np.array_equal(h['joint_positions'][:,:8].astype(np.float32),h['agent_pose'][:])),
            measured_successor_maps_exactly_to_legacy8=bool(np.array_equal(h['next_joint_positions'][:,:8].astype(np.float32),h['next_agent_pose'][:])),
            next_state_matches_following_observation=bool(np.array_equal(h['next_joint_positions'][:-1],h['joint_positions'][1:])),
            all_control_auxiliary_available=bool(h['control_auxiliary/available'][:].all()),all_done_terminal=bool(h['done'][-1]) if n else None)
        result['cameras']={key:statistics(h[key]) for key in ('side_camera_rgb','wrist_camera_rgb')}
        poses=[json.loads(v) for v in h['camera_pose_json'].asstr()[:]]
        for camera in ('side_camera','wrist_camera'):
            timestamps=np.array([p[camera]['sensor_rendering_time_s'] for p in poses],float)
            tokens=[json.dumps(p[camera]['sensor_rendering_frame'],sort_keys=True) for p in poses]
            dataset_times=h['camera_timestamp/'+camera+'_rgb'][:]
            result['cameras'][camera+'_rgb'].update(sensor_unique_frame_tokens=len(set(tokens)),sensor_uninitialized_frame0_count=sum(p[camera]['sensor_rendering_frame']==0 for p in poses),
                consecutive_repeated_sensor_tokens=sum(a==b for a,b in zip(tokens[:-1],tokens[1:])),sensor_times_first_last=timestamps[[0,-1]].tolist(),
                sensor_time_minus_obs_range_s=[float(np.min(timestamps-before)),float(np.max(timestamps-before))],
                sensor_time_minus_engine_epoch_obs_range_s=[float(np.min(timestamps-origin-before)),float(np.max(timestamps-origin-before))],
                camera_timestamp_dataset_vs_actual_sensor_max_abs_s=float(np.max(np.abs(dataset_times-timestamps))))
            result['cameras'][camera+'_rgb']['pose_source_diagnostics']=pose_source_statistics(poses,camera)
        samples=sorted(set((0,n//2,n-1))) if n else []
        panel=Image.new('RGB',(512,max(1,len(samples))*282),'white');draw=ImageDraw.Draw(panel)
        for y,index in enumerate(samples):
            draw.text((5,y*282+4),f'obs_step={index}, episode_t={before[index]:.6f}s; side | wrist',fill='black')
            for x,camera in enumerate(('side_camera_rgb','wrist_camera_rgb')):
                panel.paste(Image.fromarray(np.transpose(h[camera][index],(1,2,0))),(x*256,y*282+25))
        panel.save(output/'H5_RGB_samples.png')
    initial=json.loads((episode/'cameras.json').read_text());final=json.loads((episode/'final_camera_meta.json').read_text())
    result['camera_mounts']={}
    for camera in ('side_camera','wrist_camera'):
        a,b=initial[camera],final[camera]
        result['camera_mounts'][camera]=dict(physical_parent=a['physical_parent'],resolution_wh=a['resolution_wh'],
            initial_world_pose_position_m=a['world_pose_position_m'],final_world_pose_position_m=b['world_pose_position_m'],
            initial_local_pose_position_m=a['local_pose_position_m'],final_local_pose_position_m=b['local_pose_position_m'],
            world_position_change_m=float(np.linalg.norm(np.asarray(b['world_pose_position_m'])-a['world_pose_position_m'])),
            local_mount_unchanged=bool(np.allclose(b['local_pose_position_m'],a['local_pose_position_m'],atol=1e-8,rtol=0)
                and np.allclose(b['local_pose_quaternion_wxyz'],a['local_pose_quaternion_wxyz'],atol=1e-8,rtol=0)),
            initial_sensor_frame=a['sensor_rendering_frame'],final_sensor_frame=b['sensor_rendering_frame'],
            initial_render_binding=a.get('render_binding'),final_render_binding=b.get('render_binding'),
            authored_mount_position_difference_from_config_m_initial=a.get('authored_mount_position_difference_from_config_m'),
            authored_mount_position_difference_from_config_m_final=b.get('authored_mount_position_difference_from_config_m'))
    result['videos']={}
    for relative in ('side_camera.mp4','wrist_camera.mp4','dual_view.mp4','video/episode_0000.mp4'):
        path=episode/relative
        result['videos'][relative]=video(path,output) if path.exists() else dict(present=False)
    result['normal_reader']={}
    for policy,nobs in (('act',1),('dp',3)):
        try:
            data=normal_read(source,'all_valid',policy,16,nobs)
            result['normal_reader'][policy]=data
        except Exception as exc:result['normal_reader'][policy]=dict(error_type=type(exc).__name__,message=str(exc))
    lifecycle=episode/'camera_lifecycle.json'
    if lifecycle.exists():result['camera_lifecycle']=json.loads(lifecycle.read_text())
    result['audit_scope']='Actualclosedrecord readability/action/timestamps/media consistency. Itdoesnotturnpreview/diagnostic into full loading result; image visibility requires human review.'
    with (output/'inspection.json').open('x') as stream:json.dump(plain(result),stream,ensure_ascii=False,indent=2,allow_nan=False);stream.write('\n')
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('episode');parser.add_argument('--output',required=True)
    args=parser.parse_args();result=inspect_episode(args.episode,args.output)
    print(json.dumps(dict(output=str(Path(args.output).resolve()),transitions=result['transitions'],labels=result['H5_labels'],
        action_state_checks=result['action_state_checks'],label_consistency=result['label_consistency'],self_contained_HDF5=result['self_contained_HDF5']),ensure_ascii=False,indent=2))

if __name__=='__main__':main()
