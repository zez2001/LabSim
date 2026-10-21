"""CPU fixtures and mocked process waits; no Isaac or experiment data generated."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import h5py
import numpy as np
from omegaconf import OmegaConf

from demos.lab_cuvette_size_v1.frozen_scene import freeze_scene, prepare_standard_config
from scripts import collect_lab_cuvette_size_v1_standard as driver


class DriverTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.repo = Path(self.temporary.name)
        self.collection = self.repo / "outputs/lab_cuvette_loading/Size_v1/official"
        self.config, self.frozen_path = self.repo / "standard.yaml", self.repo / "frozen.json"
        (self.repo / "fixture.usda").write_text("#usda 1.0\n")
        cfg = prepare_standard_config(dict(version="Size_v1", asset_id="fixture",
            env=dict(task_type="loading"), experiment=dict(condition_group="natural", controller_version="CPU-fixture")))
        self.frozen = freeze_scene(cfg, ["fixture.usda"], self.repo, code_commit="CPU-fixture")
        OmegaConf.save(OmegaConf.create(cfg), self.config)
        self.frozen_path.write_text(json.dumps(self.frozen))
        self.sequence = 0

    def tearDown(self):
        self.temporary.cleanup()

    def args(self, phase="verify5"):
        return ["--phase", phase, "--collection", str(self.collection), "--config", str(self.config),
                "--frozen-scene", str(self.frozen_path)]

    def completed(self, command, run, log, *, bad_first=False, interrupted=False):
        run.mkdir(parents=True)
        log.write_text("CPU mocked process only\n")
        cfg = OmegaConf.load(command[command.index("--config") + 1])
        count = int(command[command.index("--episodes") + 1])
        for number in range(count):
            self.sequence += 1
            group = cfg.experiment.condition_group
            success = group == "natural" and not (bad_first and number == 0)
            path = run / f"episode_{number:04d}/dataset/episode_0000.h5"
            path.parent.mkdir(parents=True)
            with h5py.File(path, "w") as record:
                record.attrs.update(episode_id=f"CPU-fixture-{self.sequence}", complete=True, frames=2,
                    record_valid=True, task_success=success, success=success, eligible_for_success_bc=success,
                    eligible_for_failure_analysis=not success, task_type="loading", scene_mode="standard",
                    condition_group=group, asset_id="fixture", frozen_scene_sha256=self.frozen["frozen_scene_sha256"],
                    source_slot_id="A1", target_seat_id="A", control_config_sha256="CPU-fixture",
                    code_commit="CPU-fixture", policy_id="truth_teacher", failure_type="NONE" if success else "BLOCKED",
                    termination_reason="WORKFLOW_COMPLETE" if success else "DETERMINISTIC_EARLY_STOP",
                    deterministic_action_deviation_json=json.dumps(plain_deviation(cfg)))
                record.create_dataset("actions", data=np.zeros((2, 8), np.float32))
        evidence = dict(run_directory=str(run), process_exited=True, exit_code=0,
            pid=99999999, argv=command, interrupted=interrupted)
        driver.write_new(run / "process_exit.json", evidence)
        return evidence

    def call(self, argv, executor=None, resource_error=False):
        with (patch.object(driver, "ROOT", self.repo), patch.object(driver, "execute_process", side_effect=executor or self.completed) as execute,
             patch.object(driver, "archive_closed_run", return_value=[dict(archived=True, manifest="CPU-fixture")]),
             patch.object(driver, "check_run_resources", side_effect=RuntimeError("disk below8GiB") if resource_error else None,
                          return_value=dict(free_bytes=10 << 30)), contextlib.redirect_stdout(io.StringIO())):
            return driver.main(argv), execute

    def test_dry_run_creates_nothing_and_launches_nothing(self):
        result, execute = self.call(self.args() + ["--dry-run"])
        self.assertTrue(result["no_GPU_or_files_created"])
        self.assertFalse(self.collection.exists())
        execute.assert_not_called()

    def test_failed_verification_stops_and_cannot_collect(self):
        result, execute = self.call(self.args(), lambda *a: self.completed(*a, bad_first=True))
        self.assertEqual(result["status"], "verification_failed_stop_no_collection")
        self.assertEqual(execute.call_count, 1)
        self.assertFalse((self.collection / "verify5_passed.json").exists())
        with self.assertRaises((ValueError, FileNotFoundError)):
            self.call(self.args("success") + ["--allow-after-verified-five"])

    def test_verify_success_then_explicit_success_and_controlled_quota(self):
        result, execute = self.call(self.args())
        self.assertEqual(result["totals"]["success"], 5)
        self.assertTrue((self.collection / "verify5_passed.json").exists())
        with self.assertRaisesRegex(ValueError, "Explicit"):
            self.call(self.args("success"))
        result, execute = self.call(self.args("success") + ["--allow-after-verified-five"])
        self.assertEqual(result["status"], "target_reached")
        self.assertEqual(result["totals"]["success"], 20)
        self.assertEqual(execute.call_count, 3)
        result, execute = self.call(self.args("controlled_failure") + ["--allow-after-verified-five"])
        self.assertEqual(result["totals"]["failure"], 20)
        self.assertEqual(execute.call_count, 4)
        self.assertEqual(result["totals"]["controlled_failure"], 20)
        specs = [OmegaConf.load(path).experiment.deviation for path in (self.collection / "controller_configs").glob("*.yaml")]
        self.assertEqual({float(spec.value) for spec in specs}, set(driver.DEPTHS_M))
        self.assertTrue(all(spec.stage == "INSERT" and spec.unit == "m" for spec in specs))

    def test_resource_stop_has_zero_start_and_preserves_reason(self):
        result, execute = self.call(self.args(), resource_error=True)
        self.assertEqual(result["status"], "resource_precheck_stop_no_process_started")
        self.assertEqual(result["totals"]["started_processes"], 0)
        execute.assert_not_called()

    def test_process_wait_precedes_exit_evidence_creation(self):
        run, log = self.repo / "mock-run", self.repo / "mock.log"
        process = MagicMock()
        process.pid = 99999999
        def wait():
            self.assertFalse((run / "process_exit.json").exists())
            return 0
        process.wait.side_effect = wait
        result = driver.execute_process(["mock-no-isaac"], run, log,
            popen=MagicMock(return_value=process))
        self.assertTrue(result["process_exited"])
        self.assertEqual(json.loads((run / "process_exit.json").read_text())["exit_code"], 0)
        process.wait.assert_called_once()

    def test_no_more_than_five_and_no_random_cli(self):
        with self.assertRaises(ValueError):
            driver.build_command(self.config, self.repo / "run", 6)
        command = driver.build_command(self.config, self.repo / "run", 5)
        self.assertEqual(command[command.index("--layout-mode") + 1], "standard")


def plain_deviation(cfg):
    return OmegaConf.to_container(cfg.experiment.deviation, resolve=True) if "deviation" in cfg.experiment else None


if __name__ == "__main__":
    unittest.main()
