"""ACT/DP adapter: commanded actions, episode-level splits, bounded action chunks."""
import copy
from pathlib import Path
import h5py
import numpy as np
import torch
from policy.dataset.base_dataset import BaseImageDataset
from policy.model.common.normalizer import LinearNormalizer, SingleFieldLinearNormalizer
from policy.common.normalize_util import get_image_range_normalizer


class MinimalPickDataset(BaseImageDataset):
    def __init__(self, shape_meta, dataset_path, horizon=16, n_obs_steps=1,
                 val_ratio=0.1, seed=42, policy_type="act"):
        self.path = Path(dataset_path)
        if self.path.is_dir():
            self.path = self.path / "episode_data.hdf5"
        self.horizon, self.n_obs_steps, self.policy_type = horizon, n_obs_steps, policy_type
        if policy_type not in ("act", "dp") or (policy_type == "act" and n_obs_steps != 1):
            raise ValueError("ACT requires one observation; policy_type must be act or dp")
        if horizon < n_obs_steps or not 0 <= val_ratio < 1:
            raise ValueError("Invalid horizon or validation ratio")
        self.camera_names = [k for k, v in shape_meta["obs"].items() if v["type"] == "rgb"]
        with h5py.File(self.path, "r") as f:
            episodes = sorted(k for k in f if isinstance(f[k], h5py.Group) and
                              f[k].attrs.get("complete", False) and f[k].attrs.get("success", False))
            self.lengths = {k: len(f[k]["actions"]) for k in episodes}
            for name in episodes:
                group = f[name]
                if group["actions"].shape != group["agent_pose"].shape or group["actions"].shape[1] != 8:
                    raise ValueError(f"Invalid action/state shape in {name}")
                for camera in self.camera_names:
                    if group[camera].shape != (self.lengths[name], *shape_meta["obs"][camera]["shape"]):
                        raise ValueError(f"Invalid RGB shape for {camera} in {name}")
        if not episodes:
            raise ValueError("Dataset contains no complete successful episodes")
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
            return torch.from_numpy(np.concatenate([f[e]["actions"][:] for e in self.train_episodes]))

    def get_normalizer(self, **kwargs):
        normalizer = LinearNormalizer()
        normalizer["action"] = SingleFieldLinearNormalizer.create_fit(self.get_all_actions().numpy())
        with h5py.File(self.path, "r") as f:
            poses = np.concatenate([f[e]["agent_pose"][:] for e in self.train_episodes])
        normalizer["agent_pose"] = SingleFieldLinearNormalizer.create_fit(poses)
        for key in self.camera_names:
            normalizer[key] = get_image_range_normalizer()
        return normalizer

    def __getitem__(self, index):
        episode, t = self.sequences[index]
        size = self.lengths[episode]
        with h5py.File(self.path, "r") as f:
            group = f[episode]
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
        return sample

    @staticmethod
    def collate_fn(batch):
        return torch.utils.data.default_collate(batch)
