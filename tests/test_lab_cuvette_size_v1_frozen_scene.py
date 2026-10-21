"""CPU contract fixtures only; these synthetic files are not experiment data."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

import h5py
import numpy as np
from omegaconf import OmegaConf

from demos.lab_cuvette_size_v1.frozen_scene import (episode_metadata, freeze_scene,
    prepare_standard_config, validate_execution_mode, validate_frozen_scene)
from policy.dataset.lab_cuvette_size_v1_dataset import LabCuvetteSizeV1Dataset
from scripts.validate_lab_cuvette_size_v1_data import audit_episode


class FrozenSceneTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "asset.usda").write_text("#usda 1.0\n")
        self.cfg = prepare_standard_config(dict(version="Size_v1", asset_id="test_1100",
            scene=dict(instrument_count=1, instrument_xyz_m=[0, 0, 1]),
            physics=dict(hz=240, control_hz=60), control=dict(effort_N=8),
            rack=dict(selected_slot_id="A1"), adapter=dict(selected_target_seat_id="A"),
            env=dict(control_hz=60, physics_hz=240), cameras=dict(wrist=dict(parent="hand")),
            randomization=dict(rack_translation_half_range_m=.001)))
        self.frozen = freeze_scene(self.cfg, ["asset.usda"], self.root, code_commit="test-only")

    def tearDown(self):
        self.temp.cleanup()

    def test_prepare_does_not_mutate_original_and_explicit_standard(self):
        self.assertFalse(self.cfg["randomization"]["enabled"])
        self.assertEqual(self.cfg["randomization"]["rack_translation_half_range_m"], 0)
        self.assertTrue(validate_frozen_scene(self.cfg, self.frozen, self.root)["frozen_scene_match"])

    def test_random_collect_train_and_automatic_validation_rejected(self):
        cfg = copy.deepcopy(self.cfg)
        cfg["env"]["mode"] = "random"
        for purpose in ("collect", "train", "validation", "eval"):
            with self.assertRaises(ValueError):
                validate_execution_mode(cfg, purpose)
        self.assertEqual(validate_execution_mode(cfg, "eval", explicit_random=True)["mode"], "random")

    def test_nonzero_inherited_randomization_and_nested_light_override_rejected(self):
        cfg = copy.deepcopy(self.cfg)
        cfg["randomization"]["rack_translation_half_range_m"] = .0001
        with self.assertRaisesRegex(ValueError, "must be zero"):
            validate_execution_mode(cfg)
        cfg = copy.deepcopy(self.cfg)
        cfg["lighting"] = dict(randomize_intensity=True)
        with self.assertRaisesRegex(ValueError, "randomization"):
            validate_execution_mode(cfg)

    def test_scene_camera_physics_and_asset_change_rejected(self):
        for section, key, value in (("scene", "instrument_count", 2),
                                    ("physics", "hz", 480),
                                    ("cameras", "wrist", dict(parent="world"))):
            cfg = copy.deepcopy(self.cfg)
            cfg[section][key] = value
            with self.assertRaisesRegex(ValueError, "configuration changed"):
                validate_frozen_scene(cfg, self.frozen, self.root)
        (self.root / "asset.usda").write_text("changed source fixture")
        with self.assertRaisesRegex(ValueError, "asset missing or changed"):
            validate_frozen_scene(self.cfg, self.frozen, self.root)

    def test_controller_deviation_not_scene_and_metadata_remains_distinct(self):
        cfg = copy.deepcopy(self.cfg)
        cfg["control"]["offset_m"] = .002
        self.assertTrue(validate_frozen_scene(cfg, self.frozen, self.root)["frozen_scene_match"])
        natural = episode_metadata(self.cfg, self.frozen)
        deviation = episode_metadata(cfg, self.frozen,
            condition_group="deterministic_action_deviation",
            deviation=dict(stage="ALIGN", value=.002, unit="m", controller_version="test-only"))
        self.assertEqual(natural["frozen_scene_sha256"], deviation["frozen_scene_sha256"])
        self.assertNotEqual(natural["control_config_sha256"], deviation["control_config_sha256"])
        with self.assertRaises(ValueError):
            episode_metadata(cfg, self.frozen, condition_group="deterministic_action_deviation")

    def _index(self):
        index = self.root / "fixture.hdf5"
        with h5py.File(index, "w") as stream:
            for i in range(5):
                group = stream.create_group(f"episode_{i:04d}")
                group.attrs.update(episode_id=f"fixture-{i}", complete=True, record_valid=True,
                    task_success=True, success=True, eligible_for_success_bc=True,
                    eligible_for_failure_analysis=False, failure_type="NONE", task_type="loading",
                    scene_mode="standard", condition_group="natural", asset_id="test_1100",
                    frozen_scene_sha256=self.frozen["frozen_scene_sha256"], source_slot_id="A1",
                    target_seat_id="A", control_config_sha256="test", code_commit="test-only",
                    action_semantics="absolute_7_arm_rad_and_symmetric_finger_metre")
                group.create_dataset("actions", data=np.zeros((3, 8), np.float32))
                group.create_dataset("agent_pose", data=np.zeros((3, 8), np.float32))
                for camera in ("side_camera_rgb", "wrist_camera_rgb"):
                    group.create_dataset(camera, data=np.full((3, 3, 4, 4), 128, np.uint8))
        return index

    def test_one_shared_scene_can_split_whole_episodes_without_frame_leak(self):
        cfgpath, frozenpath = self.root / "scene.yaml", self.root / "frozen.json"
        OmegaConf.save(OmegaConf.create(self.cfg), cfgpath)
        frozenpath.write_text(json.dumps(self.frozen))
        index = self._index()
        shape = dict(obs={camera: dict(type="rgb", shape=[3, 4, 4])
            for camera in ("side_camera_rgb", "wrist_camera_rgb")}, action=dict(shape=[8]))
        shape["obs"]["agent_pose"] = dict(type="low_dim", shape=[8])
        data = LabCuvetteSizeV1Dataset(shape, index, horizon=2, val_ratio=.2,
            frozen_scene_path=frozenpath, scene_config_path=cfgpath, repository_root=self.root)
        validation = data.get_validation_dataset()
        self.assertEqual(len(data.train_episodes), 4)
        self.assertEqual(len(data.val_episodes), 1)
        self.assertFalse(set(data.episode_ids) & set(validation.episode_ids))
        self.assertEqual(data[0]["action"].shape, (2, 8))

    def test_diagnostic_success_never_counts_full_loading_quota(self):
        index = self._index()
        path = self.root / "episode_fixture.h5"
        with h5py.File(index, "r") as source, h5py.File(path, "w") as target:
            group = source["episode_0000"]
            target.attrs.update(dict(group.attrs))
            target.attrs["task_type"] = "preinsert_diagnostic"
            for key in group:
                group.copy(key, target)
        result = audit_episode(path, self.frozen["frozen_scene_sha256"])
        self.assertFalse(result["success"])
        self.assertFalse(result["failure"])


if __name__ == "__main__":
    unittest.main()
