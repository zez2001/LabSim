"""Normal episode reader with Project_v1 fixed-scene and outcome admission."""
from pathlib import Path
import json
import h5py
from policy.dataset.minimal_pick_dataset import MinimalPickDataset


class LabCuvetteProjectV1Dataset(MinimalPickDataset):
    def __init__(self, *args, scene_mode='standard', scene_randomization_enabled=False,
                 automatic_validation_mode='standard', scene_contract_path=None, **kwargs):
        if scene_mode != 'standard' or scene_randomization_enabled is not False or automatic_validation_mode != 'standard':
            raise ValueError('Project_v1 training and automatic validation use fixed standard only')
        if kwargs.get('split_group_keys'):
            raise ValueError('Split the fixed scene by complete episode, never adjacent frames')
        super().__init__(*args, split_group_keys=[], **kwargs)
        expected = None
        if scene_contract_path:
            expected = json.loads(Path(scene_contract_path).read_text())['frozen_scene_sha256']
        fingerprints = set()
        with h5py.File(self.path, 'r') as source:
            for episode, group_path in self.group_paths.items():
                attrs = source[group_path].attrs
                if attrs.get('scene_version') != 'Project_v1' or attrs.get('scene_mode') != 'standard':
                    raise ValueError('Episode is not a Project_v1 fixed standard member: ' + episode)
                if attrs.get('task_type') != 'loading':
                    raise ValueError('Diagnostic subtask cannot enter full-loading dataset: ' + episode)
                if attrs.get('condition_group') not in ('natural', 'deterministic_action_deviation'):
                    raise ValueError('Unknown condition group: ' + episode)
                value = str(attrs.get('frozen_scene_sha256', ''))
                if len(value) != 64 or expected and value != expected:
                    raise ValueError('Missing or mismatched Project_v1 scene fingerprint: ' + episode)
                fingerprints.add(value)
        if len(fingerprints) != 1:
            raise ValueError('Do not mix Project_v1 scene revisions in one fixed-scene dataset')
        self.scene_fingerprint = next(iter(fingerprints))
        if set(self.train_episodes) & set(self.val_episodes):
            raise AssertionError('One episode crossed the train/validation split')
