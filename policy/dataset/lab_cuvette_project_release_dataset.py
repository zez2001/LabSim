"""Transactional release gate over the unchanged normal Project_v1_1 payload."""
import h5py

from policy.dataset.lab_cuvette_project_v1_1_dataset import LabCuvetteProjectV11Dataset
from utils.episode_selection import _optional_bool


class LabCuvetteProjectReleaseDataset(LabCuvetteProjectV11Dataset):
    SCENE_VERSION = "Project_release_v1"
    ALLOWED_CONDITION_GROUPS = LabCuvetteProjectV11Dataset.ALLOWED_CONDITION_GROUPS | frozenset(("controlled_lifecycle_diagnostic",))

    def __init__(self, *args, **kwargs):
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
