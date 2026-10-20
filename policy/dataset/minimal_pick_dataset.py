"""ACT/DP adapter with episode or explicit scene-condition group splits."""
import copy
import json
from pathlib import Path
import h5py
import numpy as np
import torch
from policy.dataset.base_dataset import BaseImageDataset
from policy.model.common.normalizer import LinearNormalizer, SingleFieldLinearNormalizer
from policy.common.normalize_util import get_image_range_normalizer


from utils.episode_selection import (LEGACY_ABSOLUTE_ACTION_SEMANTICS,
    NON_PHYSICAL_FAILURES, episode_labels, episode_matches_filter)


class MinimalPickDataset(BaseImageDataset):
    def __init__(self, shape_meta, dataset_path, horizon=16, n_obs_steps=1,
                 val_ratio=0.1, seed=42, policy_type="act",
                 sample_filter="success", include_labels=None, split_group_keys=None):
        # Optional direct HDF5 episode attributes, never inferred from filenames
        # or manufactured condition IDs. None/[] preserves the legacy split.
        if isinstance(split_group_keys, (str, bytes)):
            raise ValueError("split_group_keys must be a sequence of HDF5 attribute names")
        self.split_group_keys = tuple(split_group_keys or ())
        if any(not isinstance(key, str) or not key for key in self.split_group_keys) or len(set(self.split_group_keys)) != len(self.split_group_keys):
            raise ValueError("split_group_keys requires unique, nonempty HDF5 attribute names")
        if sample_filter not in ("success", "failure", "all_valid"):
            raise ValueError("sample_filter must be success, failure or all_valid")
        self.sample_filter = sample_filter
        self.include_labels = sample_filter != "success" if include_labels is None else bool(include_labels)
        self.path = Path(dataset_path)
        if self.path.is_dir():
            self.path = self.path / "episode_data.hdf5"
        self.horizon, self.n_obs_steps, self.policy_type = horizon, n_obs_steps, policy_type
        if policy_type not in ("act", "dp") or (policy_type == "act" and n_obs_steps != 1):
            raise ValueError("ACT requires one observation; policy_type must be act or dp")
        if horizon < n_obs_steps or not 0 <= val_ratio < 1:
            raise ValueError("Invalid horizon or validation ratio")
        self.camera_names = [k for k, v in shape_meta["obs"].items() if v["type"] == "rgb"]
        self.group_paths, self.episode_metadata, self.excluded_episodes = {}, {}, {}
        self.episode_group_values = {}
        with h5py.File(self.path, "r") as f:
            if "actions" in f and "agent_pose" in f:
                candidates = [(str(f.attrs.get("episode_id", self.path.stem)), "/")]
            else:
                candidates = [(name, name) for name in sorted(f) if isinstance(f[name], h5py.Group)
                              and "actions" in f[name] and "agent_pose" in f[name]]
            episodes = []
            self.lengths = {}
            for name, group_path in candidates:
                group = f[group_path]
                metadata = episode_labels(group.attrs)
                accepted, reason = episode_matches_filter(group.attrs, sample_filter)
                if not accepted:
                    self.excluded_episodes[name] = reason
                    continue
                if group["actions"].shape != group["agent_pose"].shape or group["actions"].shape[1:] != (8,):
                    raise ValueError(f"Invalid action/state shape in {name}")
                semantics = str(group.attrs.get("action_semantics", ""))
                if semantics and semantics not in LEGACY_ABSOLUTE_ACTION_SEMANTICS:
                    raise ValueError(f"Unsupported 8D action semantics in {name}: {semantics}")
                self.lengths[name] = len(group["actions"])
                if not self.lengths[name]:
                    self.excluded_episodes[name] = "no_transitions"
                    continue
                for camera in self.camera_names:
                    if camera not in group or group[camera].shape != (self.lengths[name], *shape_meta["obs"][camera]["shape"]):
                        raise ValueError(f"Invalid RGB shape for {camera} in {name}")
                episodes.append(name)
                self.group_paths[name] = group_path
                self.episode_metadata[name] = metadata
                if self.split_group_keys:
                    values = {}
                    for key in self.split_group_keys:
                        if key not in group.attrs:
                            raise ValueError(f"Missing split_group_keys attribute {key!r} in episode {name}; no fallback to episode split")
                        value = group.attrs[key]
                        if isinstance(value, np.ndarray) and value.shape == ():
                            value = value.item()
                        if isinstance(value, np.generic):
                            value = value.item()
                        if isinstance(value, bytes):
                            value = value.decode("utf-8")
                        unknown = isinstance(value, str) and value.strip().lower() in {"", "unknown", "unavailable", "null", "none"}
                        if not isinstance(value, (str, bool, int, float)) or (isinstance(value, float) and not np.isfinite(value)) or unknown:
                            raise ValueError(f"Split group attribute {key!r} must be a known finite scalar in episode {name}")
                        values[key] = value
                    self.episode_group_values[name] = values
        if not episodes:
            suffix = "complete successful episodes" if sample_filter == "success" else f"eligible {sample_filter} episodes"
            raise ValueError(f"Dataset contains no {suffix}")
        self.train_group_values, self.val_group_values = [], []
        if self.split_group_keys:
            groups = {}
            for episode in episodes:
                group = tuple(self.episode_group_values[episode][key] for key in self.split_group_keys)
                groups.setdefault(group, []).append(episode)
            # Renaming/reordering episodes must not move an existing condition
            # across the split when the set of conditions is unchanged.
            identities = sorted(groups, key=lambda values: json.dumps(values, allow_nan=False))
            if val_ratio and len(identities) < 2:
                raise ValueError("Scene-condition split requires at least two distinct groups for nonzero val_ratio; use val_ratio=0 for reading only")
            order = np.random.default_rng(seed).permutation(len(identities)).tolist()
            shuffled = [identities[index] for index in order]
            # val_ratio applies to distinct conditions, not episode counts;
            # unequal group sizes can produce a different episode fraction.
            n_val = min(len(identities) - 1, max(1, round(len(identities) * val_ratio))) if val_ratio else 0
            train_groups, val_groups = shuffled[n_val:], shuffled[:n_val]
            self.train_episodes = [e for group in train_groups for e in groups[group]]
            self.val_episodes = [e for group in val_groups for e in groups[group]]
            self.train_group_values = [dict(zip(self.split_group_keys, group)) for group in train_groups]
            self.val_group_values = [dict(zip(self.split_group_keys, group)) for group in val_groups]
        else:
            shuffled = np.random.default_rng(seed).permutation(episodes).tolist()
            n_val = min(len(episodes) - 1, max(1, round(len(episodes) * val_ratio))) if val_ratio else 0
            self.train_episodes, self.val_episodes = shuffled[n_val:], shuffled[:n_val]
        self._set_episodes(self.train_episodes)

    def _set_episodes(self, episodes):
        self.episode_ids = episodes
        self.sequences = [(episode, t) for episode in episodes for t in range(self.lengths[episode])]

    def get_validation_dataset(self):
        validation = copy.copy(self)
        validation._set_episodes(self.val_episodes)
        return validation

    def __len__(self):
        return len(self.sequences)

    def get_all_actions(self):
        with h5py.File(self.path, "r") as f:
            return torch.from_numpy(np.concatenate([f[self.group_paths[e]]["actions"][:] for e in self.train_episodes]))

    def get_normalizer(self, **kwargs):
        normalizer = LinearNormalizer()
        normalizer["action"] = SingleFieldLinearNormalizer.create_fit(self.get_all_actions().numpy())
        with h5py.File(self.path, "r") as f:
            poses = np.concatenate([f[self.group_paths[e]]["agent_pose"][:] for e in self.train_episodes])
        normalizer["agent_pose"] = SingleFieldLinearNormalizer.create_fit(poses)
        for key in self.camera_names:
            normalizer[key] = get_image_range_normalizer()
        return normalizer

    def __getitem__(self, index):
        episode, t = self.sequences[index]
        size = self.lengths[episode]
        with h5py.File(self.path, "r") as f:
            group = f[getattr(self, "group_paths", {}).get(episode, episode)]
            if self.policy_type == "act":
                obs_indices = [t]
                action_indices = np.arange(t, t + self.horizon)
            else:
                start = t - self.n_obs_steps + 1
                obs_indices = np.clip(np.arange(start, t + 1), 0, size - 1).tolist()
                action_indices = np.arange(start, start + self.horizon)
            # Fetch each RGB frame separately: avoids materializing a whole video and
            # supports repeated boundary indices, which h5py fancy indexing disallows.
            obs = {key: torch.from_numpy(np.stack([group[key][i] for i in obs_indices])).float() / 255.
                   for key in self.camera_names}
            obs["agent_pose"] = torch.from_numpy(np.stack([group["agent_pose"][i] for i in obs_indices])).float()
            actions = np.stack([group["actions"][int(i)] for i in np.clip(action_indices, 0, size - 1)])
        if self.policy_type == "act":
            obs = {k: v[0] for k, v in obs.items()}
        sample = dict(obs=obs, action=torch.from_numpy(actions).float())
        if self.policy_type == "act":
            sample["is_pad"] = torch.from_numpy((action_indices < 0) | (action_indices >= size))
        if getattr(self, "include_labels", False):
            metadata = self.episode_metadata[episode]
            sample["labels"] = dict(episode_id=episode, task_success=bool(metadata["task_success"]),
                                    record_valid=bool(metadata["record_valid"]),
                                    failure_type=metadata["failure_type"],
                                    termination_reason=metadata["termination_reason"])
        return sample

    @staticmethod
    def collate_fn(batch):
        return torch.utils.data.default_collate(batch)
