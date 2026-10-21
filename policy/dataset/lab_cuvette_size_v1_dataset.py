"""Normal ACT/DP dataset with a strict fixed-scene Size_v1 admission guard.

The existing episode reader performs image/action slicing and whole-episode
splits. No format conversion, relabeling, optimizer or environment is added.
"""
from pathlib import Path

import h5py
from omegaconf import OmegaConf

from demos.lab_cuvette_size_v1.frozen_scene import load_frozen, validate_frozen_scene
from policy.dataset.minimal_pick_dataset import MinimalPickDataset


class LabCuvetteSizeV1Dataset(MinimalPickDataset):
    def __init__(self, *args, frozen_scene_path, scene_config_path, repository_root=".",
                 scene_mode="standard", scene_randomization_enabled=False,
                 automatic_validation_mode="standard", training_rng_seed=42,
                 split_group_keys=None, **kwargs):
        if scene_mode != "standard" or scene_randomization_enabled is not False or automatic_validation_mode != "standard":
            raise ValueError("Size_v1 training and automatic validation must use the fixed standard scene")
        if split_group_keys:
            raise ValueError("Fixed-scene Size_v1 splits by complete episode, not by its single shared scene condition")
        self.frozen_scene_manifest = load_frozen(frozen_scene_path)
        cfg = OmegaConf.load(scene_config_path)
        self.scene_admission = validate_frozen_scene(cfg, self.frozen_scene_manifest,
                                                    repository_root, purpose="train")
        self.training_rng_seed = int(training_rng_seed)
        super().__init__(*args, split_group_keys=[], **kwargs)
        expected = self.frozen_scene_manifest["frozen_scene_sha256"]
        with h5py.File(self.path, "r") as source:
            for episode, group_path in self.group_paths.items():
                attrs = source[group_path].attrs
                if attrs.get("scene_mode") != "standard" or attrs.get("frozen_scene_sha256") != expected:
                    raise ValueError("Episode is not a member of the frozen standard scene: " + episode)
                if attrs.get("condition_group") not in {"natural", "deterministic_action_deviation"}:
                    raise ValueError("Unknown failure/control group in " + episode)
                if attrs.get("task_type") != "loading":
                    raise ValueError("A diagnostic subtask cannot enter the full-loading dataset: " + episode)
        if set(self.train_episodes) & set(self.val_episodes):
            raise AssertionError("One complete episode crossed the train/validation split")
        self.split_scope = "complete episode; identical frozen standard scene in train and validation"
