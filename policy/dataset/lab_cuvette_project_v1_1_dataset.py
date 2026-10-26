"""Normal ACT/DP reader for the independent Project_v1_1 qualification schema."""
from pathlib import Path
import json

import h5py

from policy.dataset.minimal_pick_dataset import MinimalPickDataset
from utils.episode_selection import _optional_bool


class LabCuvetteProjectV11Dataset(MinimalPickDataset):
    def __init__(self, *args, scene_mode="standard", scene_randomization_enabled=False,
                 automatic_validation_mode="standard", scene_contract_path=None, **kwargs):
        if scene_mode != "standard" or scene_randomization_enabled is not False or automatic_validation_mode != "standard":
            raise ValueError("Project_v1_1 requires fixed standard training and validation")
        if kwargs.pop("split_group_keys", None):
            raise ValueError("Split the fixed scene by complete episode")
        super().__init__(*args, split_group_keys=[], **kwargs)
        expected = json.loads(Path(scene_contract_path).read_text())["frozen_scene_sha256"] if scene_contract_path else None
        fingerprints = set()
        with h5py.File(self.path, "r") as source:
            for episode, group_path in self.group_paths.items():
                attrs = source[group_path].attrs
                if attrs.get("scene_version") != "Project_v1_1" or attrs.get("scene_mode") != "standard":
                    raise ValueError("Not a Project_v1_1 fixed standard episode: " + episode)
                if attrs.get("task_type") != "loading":
                    raise ValueError("Diagnostic subtasks cannot enter the full-loading dataset: " + episode)
                if attrs.get("condition_group") not in ("natural", "deterministic_action_deviation"):
                    raise ValueError("Unknown condition group: " + episode)
                if attrs.get("qualification_schema") != "labsim.Project_v1_1.qualifications.v1":
                    raise ValueError("Missing Project_v1_1 qualifications: " + episode)
                for field in ("record_integrity_valid", "physics_trustworthy"):
                    if _optional_bool(attrs.get(field)) is not True:
                        raise ValueError("Not qualified for normal training reader: " + field + ": " + episode)
                if attrs.get("failure_domain") not in ("none", "task", "safety", "budget"):
                    raise ValueError("Execution/service/simulation diagnostics are not task training data: " + episode)
                if self.sample_filter == "success" and _optional_bool(attrs.get("success_bc_eligible")) is not True:
                    raise ValueError("Not success BC eligible: " + episode)
                fingerprint = str(attrs.get("frozen_scene_sha256", ""))
                if len(fingerprint) != 64 or expected and fingerprint != expected:
                    raise ValueError("Missing or mismatched Project_v1_1 fingerprint: " + episode)
                fingerprints.add(fingerprint)
        if len(fingerprints) != 1:
            raise ValueError("Do not mix Project_v1_1 scene revisions")
        self.scene_fingerprint = next(iter(fingerprints))
        if set(self.train_episodes) & set(self.val_episodes):
            raise AssertionError("One episode crossed the train/validation split")
