"""Actual tiny closed H5 fixtures exercise the release normal-reader route.

These fixtures are CPU interface evidence only, not physical task results.
"""
import hashlib
import json

import pytest

h5py = pytest.importorskip("h5py")
np = pytest.importorskip("numpy")
pytest.importorskip("torch")
pytest.importorskip("cv2")
pytest.importorskip("zarr")

from data_collectors.lab_cuvette_project_release_collector import LabCuvetteProjectReleaseCollector
from policy.dataset.lab_cuvette_project_release_dataset import LabCuvetteProjectReleaseDataset
from scripts import labsim_cli as cli
from scripts.read_lab_cuvette_project_v1_data import read_check


def fixture_episode(path, success=True):
    collector = LabCuvetteProjectReleaseCollector(dict(version="Project_release_v1",
        physics=dict(hz=240, control_hz=60)), path, save_video=False)
    collector.begin_episode(0, episode_id="release-cpu-fixture", metadata=dict(task_type="loading",
        condition_group="natural", scene_mode="standard", scene_version="Project_release_v1",
        frozen_scene_sha256="a" * 64, source_slot_id="A1", target_seat_id="candidate_far_hinge",
        asset_id="cuvette_xy_1000"))
    def state(tick):
        return dict(episode_id=collector.episode_id, simulation_time=tick / 60, step_index=tick,
            joint_positions=np.arange(9) * .001, phase="CPU_FIXTURE",
            camera_data={name: np.full((3, 4, 4), 90 + tick, np.uint8) for name in collector.CAMERAS})
    for tick in range(3):
        collector.cache_transition(state(tick), dict(command_q=np.arange(9) * .001,
            gripper_effort_limit_N=[3., 3.], gripper_target_m=.006), state(tick + 1), dict(terminated=False))
    collector.finish_episode({}, dict(episode_id=collector.episode_id, record_valid=True,
        task_success=success, geometry_valid=True, physics_trustworthy=True, task_type="loading",
        failure_domain="none" if success else "task", failure_type="NONE" if success else "TASK_INCOMPLETE",
        termination_reason="CPU_FIXTURE", success_bc_eligible=success,
        task_result=dict(success=success, status="success" if success else "failure")))
    collector.close()
    return collector.path


@pytest.mark.parametrize("success,sample_filter", [(True, "success"), (False, "failure"), (True, "all_valid")])
def test_release_dataset_check_reads_both_normal_batches_without_relabelling(tmp_path, success, sample_filter):
    path = fixture_episode(tmp_path / "episode", success)
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    output = tmp_path / "reader.json"
    assert cli.main(["dataset-check", "--index", str(path), "--sample-filter", sample_filter,
                     "--output", str(output)]) == 0
    result = json.loads(output.read_text())
    assert result["scene_version"] == "Project_release_v1"
    assert result["dataset_class"].endswith(".LabCuvetteProjectReleaseDataset")
    for reader in result["reader_validation"]:
        assert reader["batch"]["action"]["shape"] == [3, 16, 8]
        assert reader["episode_checks"][0]["executed_command_shape"] == [3, 9]
        assert reader["episode_checks"][0]["task_success"] is success
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


def test_release_reader_checks_finalization_identity(tmp_path):
    path = fixture_episode(tmp_path / "episode")
    with h5py.File(path, "r+") as source:
        source.attrs["finalization_id"] = "missing"
    with pytest.raises(ValueError, match="finalization identity"):
        read_check(path, dataset_class=LabCuvetteProjectReleaseDataset)


def test_release_reader_rejects_pending_even_when_task_success_true(tmp_path):
    path = fixture_episode(tmp_path / "episode")
    with h5py.File(path, "r+") as source:
        source.attrs["publication_state"] = "finalizing"
    with pytest.raises(ValueError):
        read_check(path, dataset_class=LabCuvetteProjectReleaseDataset)
