"""CPU records test only: never treats physical success plus exit143 as quota."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from scripts.validate_lab_cuvette_size_v1_data import official_process_gate


class ProcessAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.run = self.root / "runs/verify5_fixture"
        self.run.mkdir(parents=True)
        (self.root / "driver_records").mkdir()
        self.row = dict(path=str(self.run / "episode_0000/dataset/episode_0000.h5"),
            labels=dict(task_success=True, record_valid=True), success=True, failure=False,
            all_valid=True, admission_errors=[])

    def tearDown(self):
        self.temporary.cleanup()

    def records(self, exit_code=0, interrupted=False):
        evidence = dict(run_directory=str(self.run), process_exited=True,
            exit_code=exit_code, interrupted=interrupted, official_collection_run=True)
        (self.root / "driver_records/batch_fixture.json").write_text(json.dumps(evidence))
        (self.run / "process_exit.json").write_text(json.dumps(evidence))

    def test_exit143_is_quarantined_without_relabeling_physical_success(self):
        self.records(143)
        result = official_process_gate(copy.deepcopy(self.row), self.root)
        self.assertFalse(result["success"])
        self.assertFalse(result["failure"])
        self.assertTrue(result["labels"]["task_success"])
        self.assertIn("official_process_nonzero_or_unknown_exit:143", result["admission_errors"])

    def test_exit0_official_record_is_accepted(self):
        self.records(0)
        result = official_process_gate(copy.deepcopy(self.row), self.root)
        self.assertTrue(result["success"])
        self.assertEqual(result["official_process_admission_errors"], [])

    def test_unobserved_and_interrupted_process_rejected(self):
        result = official_process_gate(copy.deepcopy(self.row), self.root)
        self.assertFalse(result["success"])
        self.records(0, interrupted=True)
        result = official_process_gate(copy.deepcopy(self.row), self.root)
        self.assertFalse(result["success"])

    def test_independent_exit_proof_cannot_disagree(self):
        self.records(0)
        evidence = json.loads((self.run / "process_exit.json").read_text())
        evidence["exit_code"] = 143
        (self.run / "process_exit.json").write_text(json.dumps(evidence))
        result = official_process_gate(copy.deepcopy(self.row), self.root)
        self.assertFalse(result["success"])


if __name__ == "__main__":
    unittest.main()
