"""Normal ACT/Diffusion reads with honest success/failure/all_valid selection.

No simulation, optimization, label edits or temporary HDF5 indexes are used.
Run from the repository root with its existing Python environment.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import h5py
import numpy as np
from policy.dataset.minimal_pick_dataset import MinimalPickDataset


def describe(path):
    with h5py.File(path, "r") as f:
        group = f if "actions" in f else next(f[k] for k in sorted(f)
            if isinstance(f[k], h5py.Group) and "actions" in f[k])
        cameras = [k for k in ("side_camera_rgb", "wrist_camera_rgb") if k in group]
        if len(cameras) != 2:
            cameras = [k for k in ("camera_1_rgb", "camera_2_rgb") if k in group]
        if len(cameras) != 2:
            raise ValueError("Expected two separately recorded declared camera datasets")
        meta = dict(obs={k: dict(type="rgb", shape=list(group[k].shape[1:])) for k in cameras},
                    action=dict(shape=[8]))
        meta["obs"]["agent_pose"] = dict(type="low_dim", shape=[8])
        return meta


def inspect(dataset_path, sample_filter="success", policy_type="act", horizon=16, n_obs_steps=1):
    path = Path(dataset_path)
    if path.is_dir():
        path = path / "episode_data.hdf5"
    meta = describe(path)
    dataset = MinimalPickDataset(meta, path, horizon=horizon, n_obs_steps=n_obs_steps,
        val_ratio=0, policy_type=policy_type, sample_filter=sample_filter, include_labels=True)
    indices = sorted(set((0, len(dataset)//2, len(dataset)-1)))
    samples = [dataset[i] for i in indices]
    batch = dataset.collate_fn(samples)
    checks = []
    with h5py.File(path, "r") as f:
        for index, sample in zip(indices, samples):
            episode, t = dataset.sequences[index]
            group = f[dataset.group_paths[episode]]
            size = len(group["actions"])
            start = t if policy_type == "act" else t - n_obs_steps + 1
            action_indices = np.clip(np.arange(start, start+horizon), 0, size-1)
            expected_actions = np.stack([group["actions"][int(i)] for i in action_indices])
            if not np.array_equal(sample["action"].numpy(), expected_actions):
                raise AssertionError("Action alignment/padding differs from saved executed command")
            obs_indices = [t] if policy_type == "act" else np.clip(np.arange(start, t+1), 0, size-1)
            for camera in dataset.camera_names:
                expected = np.stack([group[camera][int(i)] for i in obs_indices])
                actual = np.rint(sample["obs"][camera].numpy()*255).astype(np.uint8)
                if policy_type == "act":
                    expected = expected[0]
                if not np.array_equal(actual, expected):
                    raise AssertionError("Saved RGB differs from reader batch")
            checks.append(dict(episode_id=episode, transition=t, raw_task_success=dataset.episode_metadata[episode]["task_success"],
                               exact_executed_actions=True, exact_saved_RGB=True))
    return dict(schema="labsim.Env_v1.normal_dataset_read.v1", source=str(path.resolve()),
        sample_filter=sample_filter, policy_type=policy_type, episodes=dataset.episode_ids,
        episode_labels=dataset.episode_metadata, excluded_episodes=dataset.excluded_episodes,
        transitions=len(dataset), selected_indices=indices, checks=checks,
        batch_shapes={**{f"obs/{k}":list(v.shape) for k,v in batch["obs"].items()}, "action":list(batch["action"].shape)},
        source_labels_unchanged=True, temporary_or_fake_indexes_created=False,
        optimizer_or_training_executed=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset")
    parser.add_argument("--sample-filter", choices=("success", "failure", "all_valid"), default="success")
    parser.add_argument("--policy-type", choices=("act", "dp"), default="act")
    parser.add_argument("--horizon", type=int, default=16)
    parser.add_argument("--n-obs-steps", type=int, default=1)
    parser.add_argument("--output-json")
    args = parser.parse_args()
    result = inspect(args.dataset, args.sample_filter, args.policy_type, args.horizon, args.n_obs_steps)
    text = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if args.output_json:
        destination = Path(args.output_json)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("x", encoding="utf-8") as stream:
            stream.write(text)
    print(text, end="")

if __name__ == "__main__":
    main()
