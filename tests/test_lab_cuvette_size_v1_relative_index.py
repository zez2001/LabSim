"""CPU synthetic fixtures for relative indexes and strict quota admission."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest

import h5py
import numpy as np
from omegaconf import OmegaConf

from demos.lab_cuvette_size_v1.frozen_scene import file_sha, freeze_scene, prepare_standard_config
from policy.dataset.lab_cuvette_size_v1_dataset import LabCuvetteSizeV1Dataset
from scripts.actual_episode_inspect import scan_links
from scripts.read_lab_cuvette_env_v1_data import describe, inspect
from scripts.validate_lab_cuvette_size_v1_data import audit_episode, make_index


class RelativeIndexTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.repo = Path(self.temporary.name)
        self.collection = self.repo / "collection"
        self.collection.mkdir()
        (self.repo / "asset.usda").write_text("#usda 1.0\n")
        self.cfg = prepare_standard_config(dict(version="Size_v1", asset_id="fixture",
            physics=dict(hz=240, control_hz=60), scene=dict(instrument_count=1), env={}))
        self.frozen = freeze_scene(self.cfg, ["asset.usda"], self.repo, code_commit="synthetic-only")
        self.config_path, self.frozen_path = self.repo / "standard.yaml", self.repo / "frozen.json"
        OmegaConf.save(OmegaConf.create(self.cfg), self.config_path)
        self.frozen_path.write_text(json.dumps(self.frozen))
        self.sources = [self._episode(index, success=index < 2) for index in range(3)]
        self.rows = [audit_episode(path, self.frozen["frozen_scene_sha256"]) for path in self.sources]

    def tearDown(self):
        self.temporary.cleanup()

    def _episode(self, index, success=True):
        path = self.collection / f"run_{index:02d}/episode_0000/dataset/episode_0000.h5"
        path.parent.mkdir(parents=True)
        with h5py.File(path, "w") as record:
            record.attrs.update(episode_id=f"test-only-{index}", complete=True, record_valid=True,
                task_success=success, success=success, eligible_for_success_bc=success,
                eligible_for_failure_analysis=not success, failure_type="NONE" if success else "BLOCKED",
                termination_reason="WORKFLOW_COMPLETE" if success else "BLOCKED",
                task_type="loading", scene_mode="standard", condition_group="natural", asset_id="fixture",
                frozen_scene_sha256=self.frozen["frozen_scene_sha256"], source_slot_id="A1",
                target_seat_id="A", control_config_sha256="test", code_commit="synthetic-only",
                deterministic_action_deviation_json="null", policy_id="truth_teacher",
                action_semantics="absolute_7_arm_rad_and_symmetric_finger_metre")
            q = np.arange(27, dtype=float).reshape(3, 9) / 100
            record.create_dataset("actions", data=q[:, :8].astype(np.float32))
            record.create_dataset("agent_pose", data=q[:, :8].astype(np.float32))
            for key in ("joint_positions", "next_joint_positions", "control_auxiliary/command_q"):
                record.create_dataset(key, data=q)
            before = np.arange(3) / 60
            record.create_dataset("timestamp", data=before)
            record.create_dataset("next_timestamp", data=before + 1 / 60)
            for key, value in (("actions_raw_json", "{}"), ("task_events_json", "[]"), ("phase", "INSERT")):
                record.create_dataset(key, data=[value] * 3, dtype=h5py.string_dtype())
            for camera in ("side_camera_rgb", "wrist_camera_rgb"):
                record.create_dataset(camera, data=np.full((3, 3, 4, 4), 50 + index, np.uint8))
        return path

    def test_relative_index_reads_act_dp_and_moves_as_collection(self):
        checksums = {str(path): file_sha(path) for path in self.sources}
        index = self.collection / "dataset/episode_data.hdf5"
        self.assertEqual(make_index(self.rows, index, collection_root=self.collection), 3)
        with h5py.File(index, "r") as record:
            self.assertEqual(record.attrs["storage_mode"], "relative_external_links")
            for name in record:
                link = record.get(name, getlink=True)
                self.assertIsInstance(link, h5py.ExternalLink)
                self.assertFalse(Path(link.filename).is_absolute())
                self.assertTrue((index.parent / link.filename).resolve().is_relative_to(self.collection))
        for path in self.sources:
            with h5py.File(path, "r") as record:
                self.assertEqual(scan_links(record), [])
            self.assertEqual(file_sha(path), checksums[str(path)])
        moved = self.repo / "moved_whole_collection"
        shutil.move(self.collection, moved)
        moved_index = moved / "dataset/episode_data.hdf5"
        for policy, observations in (("act", 1), ("dp", 2)):
            report = inspect(moved_index, "success", policy, horizon=4, n_obs_steps=observations)
            self.assertEqual(len(report["episodes"]), 2)
            guarded = LabCuvetteSizeV1Dataset(describe(moved_index), moved_index,
                horizon=4, n_obs_steps=observations, policy_type=policy, val_ratio=.5,
                frozen_scene_path=self.frozen_path, scene_config_path=self.config_path,
                repository_root=self.repo)
            self.assertEqual(len(guarded.train_episodes), 1)
            self.assertEqual(len(guarded.val_episodes), 1)
            self.assertFalse(set(guarded.train_episodes) & set(guarded.val_episodes))
            self.assertEqual(guarded[0]["action"].shape, (4, 8))

    def test_copy_data_is_explicit_and_self_contained(self):
        index = self.collection / "copied.hdf5"
        make_index(self.rows, index, copy_data=True, collection_root=self.collection)
        with h5py.File(index, "r") as record:
            self.assertEqual(scan_links(record), [])
            self.assertEqual(record.attrs["storage_mode"], "copied_episode_data")
        for path in self.sources:
            path.unlink()
        self.assertEqual(len(inspect(index, "success")["episodes"]), 2)

    def test_default_index_rejects_cross_tree_sources_or_destination(self):
        with self.assertRaisesRegex(ValueError, "within the collection"):
            make_index(self.rows, self.repo / "outside.hdf5", collection_root=self.collection)
        with self.assertRaisesRegex(ValueError, "outside the selected collection"):
            make_index(self.rows, self.collection / "dataset/invalid.hdf5",
                       collection_root=self.collection / "dataset")

    def test_preview_and_short_budget_excluded_even_with_frozen_metadata(self):
        for name, value in (("policy_id", "preview"), ("termination_reason", "PREVIEW_COMPLETE"),
                            ("failure_type", "DIAGNOSTIC_ONLY"), ("termination_reason", "POLICY_BUDGET"),
                            ("termination_reason", "REPLAY_TICK_BUDGET")):
            path = self.sources[2]
            with h5py.File(path, "r+") as record:
                original = record.attrs[name]
                record.attrs[name] = value
            report = audit_episode(path, self.frozen["frozen_scene_sha256"])
            self.assertFalse(report["failure"])
            self.assertIn("preview_or_short_budget_interface_diagnostic_not_task_quota", report["admission_errors"])
            with h5py.File(path, "r+") as record:
                record.attrs[name] = original

    def test_natural_and_controlled_failures_remain_separate(self):
        path = self.sources[2]
        self.assertTrue(audit_episode(path, self.frozen["frozen_scene_sha256"])["failure"])
        deviation = dict(stage="ALIGN", value=[.001, 0, 0], unit="m", controller_version="test-only")
        with h5py.File(path, "r+") as record:
            record.attrs["deterministic_action_deviation_json"] = json.dumps(deviation)
        self.assertIn("natural_group_contains_action_deviation",
                      audit_episode(path, self.frozen["frozen_scene_sha256"])["admission_errors"])
        with h5py.File(path, "r+") as record:
            record.attrs["condition_group"] = "deterministic_action_deviation"
        # A configured spec alone is not evidence the actual action deviation
        # happened. Production quota admission also requires closed sidecars
        # and matching teacher event / physical successor state.
        configured = audit_episode(path, self.frozen["frozen_scene_sha256"])
        self.assertFalse(configured["failure"])
        self.assertIn("missing_actual_controlled_event_result_or_configuration_sidecar", configured["admission_errors"])
        with h5py.File(path, "r+") as record:
            record.attrs["deterministic_action_deviation_json"] = "{}"
        self.assertFalse(audit_episode(path, self.frozen["frozen_scene_sha256"])["failure"])


if __name__ == "__main__":
    unittest.main()
