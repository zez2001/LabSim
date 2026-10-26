"""Real tiny CPU H5 fixtures exercise CLI routing and normal ACT/DP batch reads.

Fixture labels test the writer/reader contract; they are not simulation evidence.
"""
import hashlib
import json

import pytest

h5py = pytest.importorskip("h5py")
np = pytest.importorskip("numpy")
pytest.importorskip("torch")
pytest.importorskip("cv2")
pytest.importorskip("omegaconf")
pytest.importorskip("zarr")

from data_collectors.lab_cuvette_env_v1_collector import LabCuvetteEnvV1Collector
from data_collectors.lab_cuvette_project_v1_1_collector import LabCuvetteProjectV11Collector
from policy.dataset.lab_cuvette_project_v1_1_dataset import LabCuvetteProjectV11Dataset
from scripts import labsim_cli as cli
from scripts.read_lab_cuvette_project_v1_data import read_check


def fixture_episode(tmp_path, version="Project_v1_1", success=True, physics=True):
    writer = LabCuvetteProjectV11Collector if version == "Project_v1_1" else LabCuvetteEnvV1Collector
    collector = writer(dict(version=version, physics=dict(hz=240, control_hz=60)), tmp_path, save_video=False)
    collector.begin_episode(0, episode_id="cpu_fixture", metadata=dict(task_type="loading", condition_group="natural",
        scene_mode="standard", frozen_scene_sha256="a" * 64, source_slot_id="A1",
        target_seat_id="candidate_far_hinge", asset_id="cpu_fixture_asset"))
    def state(t):
        return dict(joint_positions=np.arange(9) * .01, simulation_time=t, step_index=round(t * 60),
            episode_id="cpu_fixture", phase="CPU_FIXTURE", camera_data={camera: np.full((3, 4, 4), 90, np.uint8)
                for camera in ("side_camera_rgb", "wrist_camera_rgb")})
    for tick in range(3):
        collector.cache_transition(state(tick / 60), dict(command_q=np.arange(9) * .02,
            gripper_effort_limit_N=[3, 3], gripper_target_m=.006), state((tick + 1) / 60), dict(terminated=False))
    score = dict(schema="labsim." + version + ".independent.v1", episode_id="cpu_fixture", record_valid=physics,
        task_success=success if physics else None, geometry_valid=True,
        failure_type="NONE" if success else "CONTROLLED_EARLY_STOP", failure_domain="none" if success else "task",
        termination_reason="CPU_FIXTURE", task_type="loading", physics_trustworthy=physics,
        success_bc_eligible=bool(physics and success), task_result=dict(success=success, status="success" if success else "failure"))
    collector.finish_episode({}, score)
    collector.close()
    return collector.path


@pytest.mark.parametrize("success", [True, False])
def test_dataset_check_automatically_uses_new_qualified_reader_and_preserves_source(tmp_path, success, capsys):
    source = fixture_episode(tmp_path / "episode", success=success)
    before = hashlib.sha256(source.read_bytes()).hexdigest()
    output = tmp_path / "read.json"
    sample_filter = "success" if success else "failure"
    assert cli.main(["dataset-check", "--path", str(source), "--sample-filter", sample_filter,
        "--output", str(output)]) == 0
    value = json.loads(output.read_text())
    assert value["scene_version"] == "Project_v1_1"
    assert value["dataset_class"].endswith(".LabCuvetteProjectV11Dataset")
    assert [row["policy_type"] for row in value["reader_validation"]] == ["act", "dp"]
    for reader in value["reader_validation"]:
        assert reader["batch"]["action"]["shape"] == [3, 16, 8]
        assert reader["batch"]["action"]["finite"] is True
        assert reader["episode_checks"][0]["executed_command_shape"] == [3, 9]
        assert reader["episode_checks"][0]["observation_action_time_aligned"] is True
        assert reader["episode_checks"][0]["task_success"] is success
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before
    assert json.loads(capsys.readouterr().out)["scene_version"] == "Project_v1_1"


def test_legacy_read_check_default_remains_original_class(tmp_path):
    source = fixture_episode(tmp_path / "old", version="Project_v1")
    result = read_check(source, policies=("act",))
    assert result["schema"] == "labsim.Project_v1.reader_check.v1"
    assert result["dataset_class"].endswith(".LabCuvetteProjectV1Dataset")


def test_explicit_new_class_enforces_physics_qualification(tmp_path):
    source = fixture_episode(tmp_path / "bad")
    # A deliberately inconsistent test fixture must still be refused by the
    # new qualification axes, even if its legacy success label was left true.
    with h5py.File(source, "r+") as target:
        target.attrs["physics_trustworthy"] = False
    with pytest.raises(ValueError, match="physics_trustworthy"):
        read_check(source, dataset_class=LabCuvetteProjectV11Dataset)


def test_mixed_and_unknown_versions_do_not_silently_fall_back_to_historical_reader(tmp_path):
    index = tmp_path / "mixed.h5"
    with h5py.File(index, "x") as target:
        for name, version in (("old", "Project_v1"), ("new", "Project_v1_1")):
            group = target.create_group(name)
            group.attrs["scene_version"] = version
            group.create_dataset("actions", data=np.zeros((1, 8)))
            group.create_dataset("agent_pose", data=np.zeros((1, 8)))
    with pytest.raises(ValueError, match="mix project scene versions"):
        cli.dataset_project_version(index)
    with h5py.File(index, "r+") as target:
        del target["old"]
        target["new"].attrs["scene_version"] = "Project_v999"
    with pytest.raises(ValueError, match="Unsupported project scene version"):
        cli.dataset_project_version(index)
