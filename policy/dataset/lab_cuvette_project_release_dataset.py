"""Transactional release gate and explicit standard/evaluation data use."""
from pathlib import Path

import h5py

from policy.dataset.lab_cuvette_project_v1_1_dataset import LabCuvetteProjectV11Dataset
from utils.episode_selection import _optional_bool


class LabCuvetteProjectReleaseDataset(LabCuvetteProjectV11Dataset):
    SCENE_VERSION = "Project_release_v1"
    ALLOWED_CONDITION_GROUPS = LabCuvetteProjectV11Dataset.ALLOWED_CONDITION_GROUPS | frozenset(("controlled_lifecycle_diagnostic",))

    def __init__(self, *args, data_use="train", **kwargs):
        if data_use not in ("train", "evaluation"):
            raise ValueError("data_use must be train or evaluation")
        # Inspect selected records before the training reader prepares a batch.
        # Historical episodes lacking scene_id retain their standard identity.
        path = kwargs.get("dataset_path", args[1] if len(args) > 1 else None)
        if path is not None:
            path = Path(path)
            if path.is_dir():
                path = path / "episode_data.hdf5"
            from utils.episode_selection import episode_matches_filter
            from demos.lab_cuvette_project_release_v1.scene_data import scene_identity
            with h5py.File(path, "r") as source:
                groups = [source] if "actions" in source and "agent_pose" in source else [
                    source[name] for name in source
                    if isinstance(source[name], h5py.Group) and "actions" in source[name] and "agent_pose" in source[name]]
                for group in groups:
                    if not episode_matches_filter(group.attrs, kwargs.get("sample_filter", "success"))[0]:
                        continue
                    identity = scene_identity(group)
                    scene_id = identity["scene_id"]
                    if scene_id != "standard":
                        if data_use != "evaluation":
                            raise ValueError("Random-10 scene " + scene_id + " is evaluation-only; training/demo export requires standard")
                        from demos.lab_cuvette_project_release_v1.scene_suite import validate_selection
                        validate_selection(scene_id, purpose="eval")
                        if group.attrs.get("record_purpose") != "policy_evaluation":
                            raise ValueError("Random-10 record must declare policy_evaluation: " + scene_id)
                    required = "training" if data_use == "train" else "policy_evaluation"
                    if required not in identity["scene_allowed_uses"]:
                        raise ValueError("Scene " + scene_id + " does not permit data use " + data_use)
        self.data_use = data_use
        self.ALLOW_MULTIPLE_SCENE_FINGERPRINTS = data_use == "evaluation"
        super().__init__(*args, **kwargs)
        with h5py.File(self.path, "r") as source:
            for episode, group_path in self.group_paths.items():
                attrs = source[group_path].attrs
                if attrs.get("schema_version") != "labsim.lab_cuvette_loading.Project_release_v1.v1":
                    raise ValueError("Not a release payload: " + episode)
                if attrs.get("publication_state") != "complete" or _optional_bool(attrs.get("complete")) is not True:
                    raise ValueError("Release episode is not transactionally complete: " + episode)
                if len(str(attrs.get("finalization_id", ""))) != 64:
                    raise ValueError("Missing release finalization identity: " + episode)
