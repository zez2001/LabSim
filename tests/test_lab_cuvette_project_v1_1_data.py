"""New H5/normal-reader CPU fixtures; no model, optimizer or Isaac app starts."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

try:
    import h5py
    import numpy as np
    from data_collectors.lab_cuvette_project_v1_1_collector import LabCuvetteProjectV11Collector
    from policy.dataset.lab_cuvette_project_v1_1_dataset import LabCuvetteProjectV11Dataset
    from policy.dataset.lab_cuvette_project_v1_dataset import LabCuvetteProjectV1Dataset
    HAVE_DATA_DEPS = True
except ImportError:
    HAVE_DATA_DEPS = False


@unittest.skipUnless(HAVE_DATA_DEPS, "Requires existing h5py/cv2/OmegaConf/Torch CPU-readable runtime")
class ProjectV11DataContractTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.output = Path(self.temp.name)
        self.collector = LabCuvetteProjectV11Collector(
            dict(version="Project_v1_1", physics=dict(hz=240, control_hz=60)), self.output, save_video=False)
        self.collector.begin_episode(0, episode_id="cpu_data_fixture", metadata=dict(task_type="loading",
            condition_group="natural", scene_mode="standard", frozen_scene_sha256="a" * 64))
        self.meta = dict(obs={k: dict(type="rgb", shape=[3, 4, 4]) for k in ("side_camera_rgb", "wrist_camera_rgb")}, action=dict(shape=[8]))
        self.meta["obs"]["agent_pose"] = dict(type="low_dim", shape=[8])

    def tearDown(self):
        self.collector.close()
        self.temp.cleanup()

    def transition(self, *, bad_interval=False):
        def state(t):
            return dict(joint_positions=np.arange(9) * .01, simulation_time=t,
                step_index=round(t * 60), episode_id="cpu_data_fixture", phase="POLICY",
                camera_data={k: np.full((3, 4, 4), 100, np.uint8) for k in ("side_camera_rgb", "wrist_camera_rgb")})
        self.collector.cache_transition(state(0), dict(command_q=np.arange(9) * .02,
            gripper_effort_limit_N=[3, 3], gripper_target_m=.006), state(.1 if bad_interval else 1 / 60), dict(terminated=False))

    def score(self, *, success=True, physics=True, domain="none", task_type="loading"):
        compatible = physics is True and domain in ("none", "task", "safety")
        return dict(schema="labsim.Project_v1_1.independent.v1", episode_id="cpu_data_fixture",
            record_valid=compatible, task_success=success, geometry_valid=True,
            failure_type="NONE" if success is True else "SAFETY_COLLISION" if domain == "safety" else "SIMULATION_FAILURE" if physics is False else "EXECUTOR_FAILURE",
            failure_domain=domain, termination_reason="CPU_FIXTURE", task_type=task_type,
            physics_trustworthy=physics, success_bc_eligible=bool(compatible and success is True and task_type == "loading"),
            task_result=dict(success=success, status="success" if success is True else "failure" if success is False else "unknown", scope="complete_loading" if task_type == "loading" else "diagnostic_subtask"))

    def reader(self, sample_filter="success"):
        return LabCuvetteProjectV11Dataset(self.meta, self.collector.path, horizon=1, val_ratio=0,
                                         sample_filter=sample_filter, split_group_keys=[])

    def test_success_roundtrip_keeps_hardlinks_action_mapping_and_new_axes(self):
        self.transition()
        evidence = self.score()
        labels = self.collector.finish_episode({}, evidence)
        self.assertTrue(labels["record_integrity_valid"])
        self.assertTrue(labels["physics_trustworthy"])
        self.assertTrue(labels["success_bc_eligible"])
        self.assertTrue(labels["record_valid"])
        self.assertNotIn("schema", labels)  # Task's independent schema must not be overwritten.
        self.assertEqual(tuple(self.reader()[0]["action"].shape), (1, 8))
        with h5py.File(self.collector.path) as source:
            self.assertEqual(source["side_camera_rgb"].id, source["camera_1_rgb"].id)
            np.testing.assert_array_equal(source["actions"][0], np.asarray(np.arange(9)[:8] * .02, np.float32))
            self.assertEqual(json.loads(source["independent_score_json"].asstr()[()]), evidence)
            self.assertTrue(json.loads(source["qualification_json"].asstr()[()])["record_integrity_valid"])

    def test_simulation_invalidity_does_not_destroy_an_intact_diagnostic_record(self):
        self.transition()
        labels = self.collector.finish_episode({}, self.score(success=None, physics=False, domain="simulation"))
        self.assertTrue(labels["record_integrity_valid"])
        self.assertFalse(labels["physics_trustworthy"])
        self.assertFalse(labels["record_valid"])
        self.assertTrue(labels["trajectory_analysis_eligible"])
        self.assertFalse(labels["success_bc_eligible"])
        with self.assertRaisesRegex(ValueError, "no complete successful"):
            self.reader()

    def test_final_integrity_source_matches_H5_and_preserves_independent_pending_snapshot(self):
        self.transition()
        evidence = self.score()
        evidence.update(record_integrity_valid=None, record_integrity_source="collector_pending")
        independent = self.output / "independent_score.json"
        independent.write_text(json.dumps(evidence, indent=2) + "\n")
        original_digest = hashlib.sha256(independent.read_bytes()).hexdigest()
        labels = self.collector.finish_episode({}, independent)
        expected = "streaming_collector_checks_at_flush_close"
        self.assertEqual(labels["record_integrity_source"], expected)
        # This is the same returned-label overlay used by the task's final result.
        final_result = {**evidence, **labels}
        self.assertEqual(final_result["record_integrity_source"], expected)
        summary = json.loads((self.output / "episode_0000_result.json").read_text())
        index = json.loads((self.output / "dataset/meta/episode.jsonl").read_text())
        self.assertEqual(summary["labels"]["record_integrity_source"], expected)
        self.assertEqual(index["labels"]["record_integrity_source"], expected)
        with h5py.File(self.collector.path) as source:
            self.assertEqual(source.attrs["record_integrity_source"], final_result["record_integrity_source"])
            self.assertEqual(json.loads(source["qualification_json"].asstr()[()])["record_integrity_source"], expected)
            self.assertEqual(json.loads(source["task_properties"].asstr()[()])["labels"]["record_integrity_source"], expected)
            snapshot = json.loads(source["independent_score_json"].asstr()[()])
            self.assertEqual(snapshot, evidence)
            self.assertEqual(snapshot["record_integrity_source"], "collector_pending")
            self.assertIsNone(snapshot["record_integrity_valid"])
        self.assertEqual(evidence["record_integrity_source"], "collector_pending")
        self.assertEqual(original_digest, hashlib.sha256(independent.read_bytes()).hexdigest())

    def test_bad_record_interval_does_not_relabel_trusted_physics_as_simulation_failure(self):
        self.transition(bad_interval=True)
        labels = self.collector.finish_episode({}, self.score())
        self.assertFalse(labels["record_integrity_valid"])
        self.assertTrue(labels["physics_trustworthy"])
        self.assertFalse(labels["record_valid"])
        self.assertFalse(labels["success_bc_eligible"])
        self.assertFalse(labels["trajectory_analysis_eligible"])
        self.assertEqual(labels["record_integrity_source"], "streaming_collector_checks_at_flush_close")

    def test_valid_safety_collision_can_use_normal_failure_reader(self):
        self.transition()
        labels = self.collector.finish_episode({}, self.score(success=False, domain="safety"))
        self.assertTrue(labels["record_valid"])
        self.assertTrue(labels["eligible_for_failure_analysis"])
        self.assertFalse(labels["success_bc_eligible"])
        self.assertFalse(self.reader("failure")[0]["labels"]["task_success"])

    def test_diffusion_reader_uses_the_same_new_qualification_and_8d_actions(self):
        self.transition()
        self.collector.finish_episode({}, self.score())
        reader = LabCuvetteProjectV11Dataset(self.meta, self.collector.path, horizon=2,
            n_obs_steps=2, policy_type="dp", val_ratio=0, split_group_keys=[])
        batch = reader[0]
        self.assertEqual(tuple(batch["action"].shape), (2, 8))
        self.assertEqual(tuple(batch["obs"]["side_camera_rgb"].shape), (2, 3, 4, 4))

    def test_diagnostics_are_not_full_loading_training_data(self):
        self.transition()
        self.collector.finish_episode({}, self.score(task_type="grasp_hold"))
        with self.assertRaisesRegex(ValueError, "Diagnostic subtasks"):
            self.reader("all_valid")

    def test_old_project_reader_refuses_new_scene_and_never_rewrites_the_h5(self):
        self.transition()
        self.collector.finish_episode({}, self.score())
        digest = hashlib.sha256(self.collector.path.read_bytes()).hexdigest()
        with self.assertRaisesRegex(ValueError, "not a Project_v1"):
            LabCuvetteProjectV1Dataset(self.meta, self.collector.path, horizon=1, val_ratio=0)
        self.assertEqual(digest, hashlib.sha256(self.collector.path.read_bytes()).hexdigest())

    def test_new_qualification_append_cannot_be_replayed_after_close(self):
        self.transition()
        self.collector.finish_episode({}, self.score())
        digest = hashlib.sha256(self.collector.path.read_bytes()).hexdigest()
        with self.assertRaisesRegex(RuntimeError, "newly created open episode"):
            self.collector.finish_episode({}, self.score())
        self.assertEqual(digest, hashlib.sha256(self.collector.path.read_bytes()).hexdigest())


if __name__ == "__main__":
    unittest.main()
