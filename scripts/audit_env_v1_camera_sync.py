"""Read-only actual renderer/recorded-USD camera-pose age audit, without Isaac."""
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
import h5py,numpy as np
from scipy.spatial.transform import Rotation


def file_hash(path):
    value=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):value.update(block)
    return value.hexdigest()


def pose_errors(renderer,usd):
    return float(np.linalg.norm(renderer[:3,3]-usd[:3,3])),float(np.rad2deg(Rotation.from_matrix(renderer[:3,:3]@usd[:3,:3].T).magnitude()))


def audit_episode(episode,*,include_series=False):
    episode=Path(episode).resolve();source=episode/'dataset/episode_0000.h5'
    first=json.loads(next((episode/'physics_records.jsonl').open()));origin=first['engine_time']-first['t']
    with h5py.File(source) as h:
        poses=[json.loads(value) for value in h['camera_pose_json'].asstr()[:]]
        times=h['timestamp'][:];phases=h['phase'].asstr()[:];episode_id=str(h.attrs['episode_id'])
    cameras={}
    for name in ('side_camera','wrist_camera'):
        rows=[];previous=None;physical=[];actual_settings=[]
        for index,(pair,t,phase) in enumerate(zip(poses,times,phases)):
            meta=pair[name];raw=meta['renderer_debug']['CameraParams']['raw']
            # Exact row-vector world-to-camera matrix supplied by renderer.
            W=np.linalg.inv(np.asarray(raw['cameraViewTransform'],float).reshape(4,4).T)
            U=np.asarray(meta['world_from_camera_usd'],float)
            position,angle=pose_errors(W,U)
            previous_position,previous_angle=pose_errors(W,previous) if previous is not None else (None,None)
            mount=meta.get('pose_sources',{}).get('physics_hand_times_mount',{})
            if mount.get('available'):physical.append(pose_errors(U,np.asarray(mount['world_from_camera']))[0])
            settings=meta.get('render_binding',{}).get('settings',{})
            selected={k:settings.get(k) for k in ('/app/hydraEngine/waitIdle','/app/updateOrder/checkForHydraRenderComplete')}
            if selected not in actual_settings:actual_settings.append(selected)
            rows.append(dict(observation_index=index,episode_t_s=float(t),phase=str(phase),
                position_residual_m=position,rotation_residual_deg=angle,
                renderer_position_vs_previous_USD_m=previous_position,renderer_rotation_vs_previous_USD_deg=previous_angle,
                sensor_rendering_time_s=meta['sensor_rendering_time_s'],
                sensor_minus_engine_origin_minus_obs_s=float(meta['sensor_rendering_time_s']-origin-t)))
            previous=U
        distance=np.asarray([r['position_residual_m'] for r in rows]);angles=np.asarray([r['rotation_residual_deg'] for r in rows])
        prior=np.asarray([r['renderer_position_vs_previous_USD_m'] for r in rows[1:]])
        summary=dict(samples=len(rows),first=rows[0],last=rows[-1],worst_position=rows[int(distance.argmax())],worst_rotation=rows[int(angles.argmax())],
            position_residual_m=dict(min=float(distance.min()),median=float(np.median(distance)),p95=float(np.percentile(distance,95)),maximum=float(distance.max())),
            rotation_residual_deg=dict(median=float(np.median(angles)),p95=float(np.percentile(angles,95)),maximum=float(angles.max())),
            same_observation_matches_current_USD_within_1e_8_m=int((distance<1e-8).sum()),
            previous_control_USD_correspondence=dict(samples=len(prior),within_1e_8_m=int((prior<1e-8).sum()),median_position_residual_m=float(np.median(prior)) if len(prior) else None),
            direct_USD_vs_physical_hand_times_mount_max_position_m=max(physical) if physical else None,
            actual_zero_delay_settings_observed=actual_settings)
        if include_series:summary['scalar_observation_series']=rows
        cameras[name]=summary
    return dict(schema='labsim.Env_v1.actual_camera_sync_audit.v2',source_episode=str(episode),episode_id=episode_id,
        source_HDF5=str(source),source_HDF5_sha256=file_hash(source),
        value_paths=dict(renderer='camera_pose_json[i][camera].renderer_debug.CameraParams.raw.cameraViewTransform',
            USD='camera_pose_json[i][camera].world_from_camera_usd',observation_time='timestamp[i]',
            actual_settings='camera_pose_json[i][camera].render_binding.settings'),
        calculation=dict(renderer='Gf row world-to-camera 16values reshape4x4, transpose then invert -> column world-from-camera',
            position='Euclidean world-translation difference in metres',rotation='angle(R_renderer * R_USD.T) in degrees',engine_time_origin_s=origin),
        cameras=cameras,raw_data_modified=False,Isaac_started=False,
        scope='Actual renderer-to-USD observation association; not physical precision, collision penetration or real optical calibration. Near-previous-pose equality does not alone establish exact RGB exposure latency. record_valid does not certify zero latency.')


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('episode');parser.add_argument('--output',required=True)
    parser.add_argument('--include-series',action='store_true');parser.add_argument('--reference',help='Earlier audit JSON for summary comparison')
    args=parser.parse_args();destination=Path(args.output)
    if destination.exists():raise FileExistsError(destination)
    result=audit_episode(args.episode,include_series=args.include_series)
    if args.reference:
        reference=json.loads(Path(args.reference).read_text());result['comparison']={}
        for name,current in result['cameras'].items():
            old=reference['cameras'][name]
            result['comparison'][name]=dict(reference_max_position_residual_m=old['position_residual_m']['maximum'],
                current_max_position_residual_m=current['position_residual_m']['maximum'],
                reference_last_position_residual_m=old['last']['position_residual_m'],
                current_last_position_residual_m=current['last']['position_residual_m'],
                reference_source=str(Path(args.reference)),
                caveat='Compare observed sensor association. Different control trials do not isolate dynamics or establish physics convergence.')
    destination.parent.mkdir(parents=True,exist_ok=True)
    with destination.open('x') as stream:json.dump(result,stream,ensure_ascii=False,indent=2,allow_nan=False);stream.write('\n')
    print(json.dumps({name:{key:value[key] for key in ('samples','position_residual_m','rotation_residual_deg','same_observation_matches_current_USD_within_1e_8_m','previous_control_USD_correspondence','actual_zero_delay_settings_observed')} for name,value in result['cameras'].items()},indent=2))

if __name__=='__main__':main()
