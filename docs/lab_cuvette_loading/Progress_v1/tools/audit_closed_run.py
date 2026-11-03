"""Read-only acceptance receipt for a genuinely closed Progress Teacher run."""
from __future__ import annotations
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import time


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(4*1024*1024), b''):
            digest.update(block)
    return digest.hexdigest()


def load(path):
    return json.loads(Path(path).read_text())


def audit(run, output):
    import cv2
    import h5py
    import numpy as np
    run, output = Path(run).resolve(), Path(output).resolve()
    if output.exists():
        raise FileExistsError(output)
    proof = load(run/'process_exit.json')
    assert proof['process_exited'] is True and proof['exit_code'] == 0
    assert not Path('/proc', str(proof['pid'])).exists()
    manifest_path = run/'run_manifest.json'
    if manifest_path.exists():
        manifest = load(manifest_path)
        for key in ('process_id', 'pid'):
            if manifest.get(key):
                assert not Path('/proc', str(manifest[key])).exists()
    episode = run/'episode_0000'
    result = load(episode/'result.json')
    marker = load(episode/'episode_0000_complete.json')
    published = load(episode/'episode_0000_result.json')
    progress = load(episode/'progress_summary.json')
    assert result['task_success'] is True and result['record_valid'] is True
    assert result['success_bc_eligible'] is True and result['complete'] is True
    assert result['publication_state'] == 'complete'
    assert result['finalization_id'] == marker['finalization_id'] == published['finalization_id']
    assert result['progress_status'] == 'complete'
    assert progress['progress_complete'] is True
    assert progress['output_integrity']['complete'] is True
    assert progress['output_integrity']['errors'] == []
    path = episode/'dataset/episode_0000.h5'
    before = sha(path)
    with h5py.File(path, 'r') as source:
        assert source.attrs['complete'] and source.attrs['publication_state'] == 'complete'
        assert source.attrs['task_success'] and source.attrs['record_valid'] and source.attrs['success_bc_eligible']
        assert source.attrs['finalization_id'] == result['finalization_id']
        assert source.attrs['episode_id'] == progress['metadata']['episode_id'] == result['episode_id']
        assert source.attrs['scene_version'] == 'Project_release_v1'
        assert source.attrs['asset_id'] == 'cuvette_xy_1000'
        assert source.attrs['record_purpose'] == 'demonstration'
        n = len(source['actions'])
        t0, t1 = source['timestamp'][:], source['next_timestamp'][:]
        assert np.all(t1>t0) and np.allclose(t0[1:],t1[:-1],atol=1e-8)
        assert np.allclose(t1-t0, source['control_interval_s'][:],atol=1e-8)
        assert progress['recording']['control_transitions'] == n
        assert source['actions'].shape[1:] == (8,)
        assert source['control_auxiliary/command_q'].shape == (n,9)
        metadata = json.loads(source['episode_metadata_json'].asstr()[()])
        attrs = {k:str(source.attrs[k]) for k in source.attrs}
        # Exercise every distinct HDF5 dataset, preserving camera alias hardlinks.
        seen, datasets, read_bytes = set(), [], 0
        def read_all(name, item):
            nonlocal read_bytes
            if not isinstance(item, h5py.Dataset):
                return
            identity = h5py.h5o.get_info(item.id).addr
            if identity in seen:
                return
            seen.add(identity)
            if not item.shape:
                value=item[()]
                read_bytes += getattr(value,'nbytes',0)
            else:
                for start in range(0,len(item),32):
                    value=item[start:start+32]
                    read_bytes += getattr(value,'nbytes',0)
            datasets.append(dict(name=name,shape=list(item.shape),dtype=str(item.dtype)))
        source.visititems(read_all)
        aliases = {cam:source[cam].id == source[alias].id for cam,alias in
            [('camera_1_rgb','side_camera_rgb'),('camera_2_rgb','wrist_camera_rgb')]}
        assert all(aliases.values())
        h5_receipt=dict(path=str(path),bytes=path.stat().st_size,sha256=before,attributes=attrs,
            episode_metadata=metadata,transitions=n,first_t_obs_s=float(t0[0]),last_t_next_s=float(t1[-1]),
            datasets=datasets,all_unique_datasets_read=True,read_array_bytes=read_bytes,image_hardlink_aliases=aliases)
    assert sha(path) == before
    logs = {}
    for name in ['physics_records.jsonl.gz','native_contact_events.jsonl.gz','progress_v1.jsonl.gz']:
        p=episode/name
        count=0
        with gzip.open(p,'rt') as stream:
            for line in stream:
                if line.strip():
                    json.loads(line);count+=1
        logs[name]=dict(rows=count,bytes=p.stat().st_size,sha256=sha(p),gzip_crc_and_json_valid=True)
    assert logs['physics_records.jsonl.gz']['rows']==progress['recording']['physics_samples']
    assert logs['progress_v1.jsonl.gz']['rows']==h5_receipt['transitions']
    videos={}
    for name in ['side_camera.mp4','wrist_camera.mp4','dual_view.mp4']:
        p=episode/name;cap=cv2.VideoCapture(str(p));assert cap.isOpened()
        expected=int(cap.get(cv2.CAP_PROP_FRAME_COUNT));fps=cap.get(cv2.CAP_PROP_FPS);count=0
        while True:
            ok,frame=cap.read()
            if not ok:break
            assert frame is not None and frame.size
            count+=1
        cap.release();assert count==expected and count>0
        videos[name]=dict(path=str(p),bytes=p.stat().st_size,sha256=sha(p),frames_decoded=count,fps=fps,complete_decode=True)
    value=dict(schema='labsim.Progress_v1.closed_teacher_acceptance.v1',run=str(run),
        runtime_commit=proof['runtime_commit'],process_exit=proof,original_final_result=result,
        completion_marker=marker,h5=h5_receipt,logs=logs,videos=videos,
        progress=dict(complete=progress['progress_complete'],integrity=progress['output_integrity'],
            recording=progress['recording'],milestones=progress['milestones']),
        original_h5_hash_unchanged_by_audit=True,
        full_shutdown_observed=True,paid_policy_calls=False,scene_randomization=False)
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(output=str(output),task_success=True,progress_complete=True,transitions=h5_receipt['transitions'],h5_sha256=before),indent=2))
    return value

if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('run',type=Path);p.add_argument('--output',required=True,type=Path);a=p.parse_args();audit(a.run,a.output)
