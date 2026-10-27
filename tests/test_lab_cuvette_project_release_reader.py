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
from policy.dataset.lab_cuvette_project_v1_1_dataset import LabCuvetteProjectV11Dataset
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


def test_release_controlled_lifecycle_failure_reads_official_entry_without_relabelling(tmp_path):
    path = fixture_episode(tmp_path / "episode", success=False)
    with h5py.File(path, "r+") as source:
        source.attrs["condition_group"] = "controlled_lifecycle_diagnostic"
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    for sample_filter in ("failure", "all_valid"):
        direct = read_check(path, sample_filter=sample_filter, dataset_class=LabCuvetteProjectReleaseDataset)
        assert len(direct["reader_validation"]) == 2
        output = tmp_path / (sample_filter + ".json")
        assert cli.main(["dataset-check", "--index", str(path), "--sample-filter", sample_filter,
                         "--output", str(output)]) == 0
        result = json.loads(output.read_text())
        assert result["dataset_class"].endswith(".LabCuvetteProjectReleaseDataset")
        for reader in result["reader_validation"]:
            assert reader["episode_checks"][0]["condition_group"] == "controlled_lifecycle_diagnostic"
            assert reader["episode_checks"][0]["task_success"] is False
    with pytest.raises(ValueError):
        read_check(path, sample_filter="success", dataset_class=LabCuvetteProjectReleaseDataset)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


def test_original_v11_still_rejects_release_only_condition_group(tmp_path):
    path = fixture_episode(tmp_path / "episode", success=False)
    with h5py.File(path, "r+") as source:
        source.attrs.update(scene_version="Project_v1_1", condition_group="controlled_lifecycle_diagnostic")
    assert LabCuvetteProjectV11Dataset.ALLOWED_CONDITION_GROUPS == frozenset(("natural", "deterministic_action_deviation"))
    with pytest.raises(ValueError, match="Unknown condition group"):
        read_check(path, sample_filter="failure", dataset_class=LabCuvetteProjectV11Dataset)


@pytest.mark.parametrize("domain", ["service", "executor", "simulation", "recording", "protocol"])
def test_release_extended_group_cannot_bypass_qualification_domains(tmp_path, domain):
    path = fixture_episode(tmp_path / "episode", success=False)
    with h5py.File(path, "r+") as source:
        # Intentionally poisoned fixture: domain gate must still reject even
        # if an external caller wrongly left legacy valid/eligible attrs true.
        source.attrs.update(condition_group="controlled_lifecycle_diagnostic", failure_domain=domain)
    with pytest.raises(ValueError, match="diagnostics are not task training data"):
        read_check(path, sample_filter="failure", dataset_class=LabCuvetteProjectReleaseDataset)


def test_release_controlled_group_does_not_bypass_incomplete_gate(tmp_path):
    path = fixture_episode(tmp_path / "episode", success=False)
    with h5py.File(path, "r+") as source:
        source.attrs.update(condition_group="controlled_lifecycle_diagnostic", complete=False,
                            publication_state="prepared")
    with pytest.raises(ValueError):
        read_check(path, sample_filter="all_valid", dataset_class=LabCuvetteProjectReleaseDataset)
