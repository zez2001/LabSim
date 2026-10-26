"""Read a real recorded Project_v1 episode/index through the normal ACT/DP reader."""
import json
from pathlib import Path
import h5py
import numpy as np
import torch
from torch.utils.data import DataLoader
from policy.dataset.lab_cuvette_project_v1_dataset import LabCuvetteProjectV1Dataset
from utils.episode_selection import episode_matches_filter


def recorded_image_shape(path, sample_filter):
    """Infer recorded policy RGB shape; native capture calibration is separate."""
    images, derivations = set(), []
    with h5py.File(path, 'r') as source:
        candidates = [('/', source)] if 'actions' in source and 'agent_pose' in source else [
            (name, source[name]) for name in sorted(source)
            if isinstance(source[name], h5py.Group) and 'actions' in source[name] and 'agent_pose' in source[name]]
        for name, group in candidates:
            if not episode_matches_filter(group.attrs, sample_filter)[0]:
                continue
            shapes = []
            for camera in ('side_camera_rgb', 'wrist_camera_rgb'):
                if camera not in group:
                    raise ValueError('Missing recorded RGB camera: ' + name + '/' + camera)
                dataset = group[camera]
                if dataset.dtype != np.dtype('uint8') or dataset.ndim != 4 or dataset.shape[1] != 3 \
                        or min(dataset.shape[2:]) < 1 or dataset.shape[0] != len(group['actions']):
                    raise ValueError('Recorded RGB must be aligned N×3×H×W uint8: ' + name + '/' + camera)
                shapes.append(tuple(dataset.shape[1:]))
            if shapes[0] != shapes[1]:
                raise ValueError('Side and wrist RGB shapes differ in episode: ' + name)
            images.add(shapes[0])
            if 'public_sample_schema' in group.attrs:
                derivations.append(dict(episode_id=str(group.attrs.get('episode_id', name)),
                    schema=str(group.attrs['public_sample_schema']),
                    source_hdf5_sha256=str(group.attrs.get('public_sample_source_sha256', 'unknown')),
                    temporal_subsampling=bool(group.attrs.get('public_sample_temporal_subsampling', False)),
                    original_capture_camera_metadata_retained=bool(group.attrs.get('public_sample_original_camera_metadata_retained', False)),
                    recorded_policy_RGB_shape=list(shapes[0]),
                    note='Stored policy RGB may be a spatial derivative; original capture calibration retains its source resolution.'))
    if not images:
        raise ValueError('No eligible episodes from which to infer recorded image shape')
    if len(images) != 1:
        raise ValueError('Selected episodes have mixed policy RGB shapes; select a consistent derivative/index')
    return list(next(iter(images))), derivations


def read_check(path, *, sample_filter='success', policies=('act', 'dp')):
    path = Path(path)
    if path.is_dir():
        candidates = [path / 'episode_data.hdf5', path / 'dataset/episode_0000.h5']
        path = next((p for p in candidates if p.is_file()), candidates[0])
    image_shape, derivations = recorded_image_shape(path, sample_filter)
    shape = dict(obs={
        'side_camera_rgb': dict(shape=image_shape, type='rgb'),
        'wrist_camera_rgb': dict(shape=image_shape, type='rgb'),
        'agent_pose': dict(shape=[8], type='low_dim')}, action=dict(shape=[8]))
    results = []
    for policy in policies:
        dataset = LabCuvetteProjectV1Dataset(shape_meta=shape, dataset_path=path,
            horizon=16, n_obs_steps=1 if policy == 'act' else 3, policy_type=policy,
            sample_filter=sample_filter, val_ratio=0)
        batch = next(iter(DataLoader(dataset, batch_size=min(3, len(dataset)), num_workers=0)))
        def describe(value):
            if isinstance(value, dict):
                return {key: describe(item) for key, item in value.items()}
            if torch.is_tensor(value):
                return dict(shape=list(value.shape), dtype=str(value.dtype), finite=bool(torch.isfinite(value).all()))
            if isinstance(value, (list, tuple)):
                return [describe(item) for item in value]
            return value
        with h5py.File(path, 'r') as source:
            checks = []
            for episode, group_path in dataset.group_paths.items():
                group = source[group_path]
                dt = group['next_timestamp'][:] - group['timestamp'][:]
                checks.append(dict(episode_id=episode, transitions=len(dt),
                    observation_action_time_aligned=bool(np.allclose(dt, 1 / 60, atol=1e-6)),
                    action_shape=list(group['actions'].shape),
                    executed_command_shape=list(group['control_auxiliary/command_q'].shape),
                    source_slot_id=str(group.attrs['source_slot_id']), target_seat_id=str(group.attrs['target_seat_id']),
                    asset_id=str(group.attrs['asset_id']), record_valid=bool(group.attrs['record_valid']),
                    task_success=bool(group.attrs['task_success']), condition_group=str(group.attrs['condition_group'])))
        results.append(dict(policy_type=policy, episodes=list(dataset.group_paths), scene_fingerprint=dataset.scene_fingerprint,
            batch=describe(batch), episode_checks=checks, training_or_optimizer_executed=False))
    return dict(schema='labsim.Project_v1.reader_check.v1', path=str(path),
        recorded_policy_image_shape=image_shape, public_sample_derivations=derivations,
        sample_filter=sample_filter, reader_validation=results, source_labels_modified=False)
