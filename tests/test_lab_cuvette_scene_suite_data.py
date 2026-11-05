"""Random scenes stay evaluation-only without relabelling task outcomes."""
import hashlib
import json

import pytest

h5py = pytest.importorskip("h5py")
np = pytest.importorskip("numpy")
pytest.importorskip("torch")
pytest.importorskip("cv2")
pytest.importorskip("zarr")

from data_collectors.lab_cuvette_project_release_collector import LabCuvetteProjectReleaseCollector
from demos.lab_cuvette_project_release_v1.dataset_index import build_index
from demos.lab_cuvette_project_release_v1.scene_suite import load_scene_definition
from policy.dataset.lab_cuvette_project_release_dataset import LabCuvetteProjectReleaseDataset
from scripts.read_lab_cuvette_project_v1_data import read_check
from utils.episode_selection import episode_matches_filter


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def episodes(root):
    paths = []
    for index, (scene, success) in enumerate((("standard", True), ("random_001", True), ("random_002", False))):
        purpose = "demonstration" if scene == "standard" else "policy_evaluation"
        definition = load_scene_definition(scene)
        suite_identity = dict(scene_id=scene, suite_version=definition["suite_version"],
            scene_definition_sha256=definition["definition_sha256"],
            allowed_uses=definition["allowed_uses"])
        collector = LabCuvetteProjectReleaseCollector(dict(version="Project_release_v1",
            release=dict(record_purpose=purpose), scene_suite=suite_identity,
            physics=dict(hz=240, control_hz=60)),
            root / f"episode_{index:04d}", save_video=False)
        collector.begin_episode(0, episode_id=f"scene-data-cpu-{index}", metadata=dict(
            task_type="loading", condition_group="natural", scene_mode="standard",
            scene_version="Project_release_v1",
            frozen_scene_sha256="abcdef"[index] * 64, source_slot_id="A1",
            target_seat_id="candidate_far_hinge", asset_id="cuvette_xy_1000"))
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
        paths.append(collector.path)
    (root / "run_manifest.json").write_text(json.dumps(dict(process_id=999999999)))
    return paths


def test_training_index_rejects_random_without_modifying_sources(tmp_path):
    root = tmp_path / "run"
    paths = episodes(root)
    hashes = [digest(path) for path in paths]
    with pytest.raises(ValueError, match="evaluation-only"):
        build_index(root, root / "training.hdf5", data_use="train")
    assert not (root / "training.hdf5").exists()
    report = build_index(root, root / "demonstrations.hdf5", purpose="demonstration")
    assert report["included_episode_ids"] == ["scene-data-cpu-0"]
    assert [row["exclusion_reason"] for row in report["episodes"] if not row["included"]] == [
        "random_scene_evaluation_only", "random_scene_evaluation_only"]
    assert [digest(path) for path in paths] == hashes


def test_random_normal_reader_defaults_to_training_rejection(tmp_path):
    paths = episodes(tmp_path / "run")
    with pytest.raises(ValueError, match="evaluation-only"):
        read_check(paths[1], dataset_class=LabCuvetteProjectReleaseDataset)
    # Standard stays readable through the same default reader.
    report = read_check(paths[0], dataset_class=LabCuvetteProjectReleaseDataset)
    assert report["data_use"] == "train"
    assert len(report["reader_validation"]) == 2


@pytest.mark.parametrize("sample_filter,count", [("success", 1), ("failure", 1), ("all_valid", 2)])
def test_random_evaluation_multiscene_index_reads_actual_act_dp_batches(tmp_path, sample_filter, count):
    root = tmp_path / "run"
    paths = episodes(root)
    hashes = [digest(path) for path in paths]
    index = root / "eval.hdf5"
    result = build_index(root, index, purpose="policy_evaluation")
    assert result["counts"] == dict(success=1, failure=1, all_valid=2, incomplete=0)
    assert len(result["included_episode_ids"]) == 2
    report = read_check(index, sample_filter=sample_filter, dataset_class=LabCuvetteProjectReleaseDataset,
        dataset_options=dict(data_use="evaluation"))
    for row in report["reader_validation"]:
        assert len(row["episodes"]) == count
        assert row["batch"]["action"]["shape"] == [3, 16, 8]
        assert len(row["scene_fingerprints"]) == count
    assert [digest(path) for path in paths] == hashes


def test_evaluation_does_not_relax_existing_integrity_or_outcome_qualification(tmp_path):
    paths = episodes(tmp_path / "run")
    with h5py.File(paths[2], "r+") as source:
        before = {name: episode_matches_filter(source.attrs, name) for name in ("success", "failure", "all_valid")}
        source.attrs["failure_domain"] = "simulation"
    with pytest.raises(ValueError, match="diagnostics are not task training data"):
        read_check(paths[2], sample_filter="failure", dataset_class=LabCuvetteProjectReleaseDataset,
            dataset_options=dict(data_use="evaluation"))
    with h5py.File(paths[2]) as source:
        assert {name: episode_matches_filter(source.attrs, name) for name in before} == before
        assert source.attrs["task_success"] == False


def test_embedded_scene_identity_prevents_missing_attribute_training_bypass(tmp_path):
    paths = episodes(tmp_path / "run")
    with h5py.File(paths[1], "r+") as source:
        if "scene_id" in source.attrs:
            del source.attrs["scene_id"]
    with pytest.raises(ValueError, match="evaluation-only"):
        read_check(paths[1], dataset_class=LabCuvetteProjectReleaseDataset)


@pytest.mark.parametrize("field,value", [("scene_id", "standard"),
    ("scene_definition_sha256", "f" * 64), ("scene_allowed_uses", '["training"]')])
def test_identity_conflicts_are_rejected_instead_of_permitting_training(tmp_path, field, value):
    paths = episodes(tmp_path / "run")
    with h5py.File(paths[1], "r+") as source:
        source.attrs[field] = value
    with pytest.raises(ValueError, match="Conflicting recorded scene identity"):
        read_check(paths[1], dataset_class=LabCuvetteProjectReleaseDataset,
            dataset_options=dict(data_use="evaluation"))


def test_real_configuration_attribute_is_cross_checked_with_episode_metadata(tmp_path):
    paths = episodes(tmp_path / "run")
    with h5py.File(paths[1], "r+") as source:
        configured = json.loads(source.attrs["configuration_json"])
        configured["scene_suite"] = dict(scene_id="standard")
        source.attrs["configuration_json"] = json.dumps(configured)
    with pytest.raises(ValueError, match="Conflicting recorded scene identity"):
        read_check(paths[1], dataset_class=LabCuvetteProjectReleaseDataset,
            dataset_options=dict(data_use="evaluation"))


def test_configuration_attribute_alone_cannot_hide_random_from_training(tmp_path):
    paths = episodes(tmp_path / "run")
    with h5py.File(paths[1], "r+") as source:
        configured = json.loads(source.attrs["configuration_json"])
        assert configured["scene_suite"]["scene_id"] == "random_001"
        if "scene_id" in source.attrs:
            del source.attrs["scene_id"]
        metadata = json.loads(source["episode_metadata_json"].asstr()[()])
        metadata.pop("scene_id")
        source["episode_metadata_json"][()] = json.dumps(metadata)
    with pytest.raises(ValueError, match="evaluation-only"):
        read_check(paths[1], dataset_class=LabCuvetteProjectReleaseDataset)
