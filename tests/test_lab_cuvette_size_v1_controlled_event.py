"""CPU temporary fixtures only: no GPU lock, live HDF5, labels or simulations."""
import json
import unittest

import h5py
from omegaconf import OmegaConf

from demos.lab_cuvette_size_v1.frozen_scene import file_sha
from scripts.validate_lab_cuvette_size_v1_data import audit_episode, make_index
from tests import test_lab_cuvette_size_v1_relative_index as index_fixtures


class ControlledEventTests(unittest.TestCase):
    def setUp(self):
        self.fixture = index_fixtures.RelativeIndexTests()
        self.fixture.setUp()
        self.path = self.fixture.sources[2]
        self.episode = self.path.parent.parent
        self.spec = dict(stage="INSERT", value=.001, unit="m", controller_version="CPU-fixture",
                         stop_insertion_at_depth_m=.001)
        cfg = OmegaConf.create(self.fixture.cfg)
        cfg.experiment = dict(condition_group="deterministic_action_deviation", deviation=self.spec)
        OmegaConf.save(cfg, self.episode / "config.yaml")
        self.events = [dict(t=.05, event="deterministic_action_deviation", spec=self.spec,
            actual_depth_m=.001016965, normal_actions_only=True),
            dict(t=.05, event="teacher_stop_suggestion", status="CONTROLLED_EARLY_STOP", phase="INSERT")]
        self.write("teacher_events.json", self.events)
        self.result = dict(episode_id="test-only-2", complete=True, record_valid=True,
            task_success=False, failure_type="CONTROLLED_EARLY_STOP", termination_reason="CONTROLLED_EARLY_STOP",
            release_observed=False, retreat_observed=False,
            post_retreat_window=dict(status="unavailable", stable=None), stable_after_retreat=None,
            simulation_seconds=.05)
        self.write("result.json", self.result)
        with h5py.File(self.path, "r+") as source:
            source.attrs.update(condition_group="deterministic_action_deviation",
                deterministic_action_deviation_json=json.dumps(self.spec),
                failure_type="CONTROLLED_EARLY_STOP", termination_reason="CONTROLLED_EARLY_STOP")
            source.create_dataset("privileged/next_state_json", data=[json.dumps(dict(depth_m=depth))
                for depth in (-.001, .0005, .001016965)], dtype=h5py.string_dtype())

    def tearDown(self):
        self.fixture.tearDown()

    def write(self, name, data):
        (self.episode / name).write_text(json.dumps(data))

    def audit(self):
        return audit_episode(self.path, self.fixture.frozen["frozen_scene_sha256"])

    def test_actual_1mm_stop_passes_without_relabeling(self):
        before = file_sha(self.path)
        row = self.audit()
        self.assertTrue(row["failure"])
        self.assertFalse(row["success"])
        self.assertTrue(row["controlled_deviation_event_evidence"]["qualified"])
        self.assertFalse(row["labels"]["task_success"])
        self.assertEqual(file_sha(self.path), before)

    def test_configuration_only_missing_event_rejected_by_default_index(self):
        self.write("teacher_events.json", self.events[1:])
        row = self.audit()
        self.assertFalse(row["failure"])
        self.assertIn("controlled_event_check_failed:one_actual_deviation_event", row["admission_errors"])
        index = self.fixture.collection / "checks/rejected.hdf5"
        self.assertEqual(make_index([row], index, collection_root=self.fixture.collection), 0)
        with h5py.File(self.path, "r") as raw:
            self.assertTrue(bool(raw.attrs["eligible_for_failure_analysis"]))
            self.assertFalse(bool(raw.attrs["task_success"]))

    def test_event_depth_must_match_actual_physical_state(self):
        self.events[0]["actual_depth_m"] = .005
        self.write("teacher_events.json", self.events)
        row = self.audit()
        self.assertFalse(row["failure"])
        self.assertIn("controlled_event_check_failed:event_depth_matches_saved_physical_state", row["admission_errors"])

    def test_actual_phase_and_time_must_match_event(self):
        with h5py.File(self.path, "r+") as source:
            source["phase"][-1] = "TRANSPORT"
        row = self.audit()
        self.assertFalse(row["failure"])
        self.assertIn("controlled_event_check_failed:actual_saved_phase_INSERT", row["admission_errors"])
        with h5py.File(self.path, "r+") as source:
            source["phase"][-1] = "INSERT"
        self.events[0]["t"] = .04
        self.write("teacher_events.json", self.events)
        self.assertFalse(self.audit()["failure"])

    def test_HDF5_and_config_spec_must_match(self):
        altered = dict(self.spec, value=.005, stop_insertion_at_depth_m=.005)
        with h5py.File(self.path, "r+") as source:
            source.attrs["deterministic_action_deviation_json"] = json.dumps(altered)
        row = self.audit()
        self.assertFalse(row["failure"])
        self.assertIn("controlled_event_check_failed:HDF5_spec_matches_config", row["admission_errors"])

    def test_pre_retreat_failure_cannot_claim_post_retreat_stability(self):
        self.result["post_retreat_window"] = dict(status="complete", stable=True)
        self.result["stable_after_retreat"] = True
        self.write("result.json", self.result)
        self.assertFalse(self.audit()["failure"])


if __name__ == "__main__":
    unittest.main()
