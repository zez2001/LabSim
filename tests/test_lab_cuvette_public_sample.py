"""Synthetic file-contract tests only; no simulated experiment result is created."""
import json
from pathlib import Path

import pytest

h5py = pytest.importorskip("h5py")
np = pytest.importorskip("numpy")
cv2 = pytest.importorskip("cv2")

from scripts.export_lab_cuvette_public_sample import (
    export_sample, inspect_links, normal_reader_check, object_id, sha256)


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "source" / "episode" / "dataset" / "episode_0000.h5"
    path.parent.mkdir(parents=True)
    n = 18
    with h5py.File(path, "w", track_order=True) as f:
        f.attrs.update(scene_version="Project_v1", scene_mode="standard", task_type="loading",
            episode_id="synthetic-unit-test-only", condition_group="natural", complete=True,
            record_valid=True, task_success=True, eligible_for_success_bc=True,
            eligible_for_failure_analysis=False, failure_type="NONE", termination_reason="SUCCESS",
            frozen_scene_sha256="a" * 64, action_semantics="absolute_7_arm_rad_and_symmetric_finger_metre",
            source_slot_id="A1", target_seat_id="candidate_far_hinge", asset_id="cuvette_xy_1000",
            camera_meta_json=json.dumps({"K": [[100, 0, 128], [0, 100, 128], [0, 0, 1]],
                "resolution_wh": [256, 256], "prim": "/World/Franka/Camera",
                "diagnostic_path": "/home/author/LabSim/config/test.yaml"}),
            configuration_json=json.dumps({"source": "/tmp/private/asset-cache/assets/cuvette.usda", "mass": .02}))
        q = np.arange(n * 9, dtype=np.float64).reshape(n, 9) * .001
        for key, data in {"actions": q[:, :8].astype("float32"), "agent_pose": q[:, :8].astype("float32"),
            "joint_positions": q, "next_joint_positions": q + .0001,
            "control_auxiliary/command_q": q, "timestamp": np.arange(n) / 60,
            "next_timestamp": (np.arange(n) + 1) / 60, "inference_wall_time_s": np.full(n, np.nan)}.items():
            f.create_dataset(key, data=data)
        rng = np.random.default_rng(0)
        for camera, alias in [("side_camera_rgb", "camera_1_rgb"), ("wrist_camera_rgb", "camera_2_rgb")]:
            f.create_dataset(camera, data=rng.integers(0, 256, (n, 3, 256, 256), dtype="uint8"))
            f[alias] = f[camera]
            f.create_dataset("terminal_observation/" + camera, data=f[camera][-1])
        for key in ("actions_raw_json", "task_events_json", "privileged/state_json", "camera_pose_json"):
            f.create_dataset(key, data=[json.dumps({"i": i, "value": float(i) / 9,
                "source": "/home/author/LabSim/assets/part.usda", "prim": "/World/Cuvette"}) for i in range(n)],
                dtype=h5py.string_dtype("utf-8"))
        f.create_dataset("language_instruction", data="完整任务单元测试", dtype=h5py.string_dtype("utf-8"))
    return path


def test_complete_sequence_preserved_source_untouched_and_both_rgb_resized(source, tmp_path):
    before = sha256(source)
    manifest = export_sample(source, tmp_path / "public", verify_reader=False)
    assert sha256(source) == before == manifest["source_hdf5_sha256"]
    assert manifest["transitions"] == 18 and manifest["full_simulation_duration_s"] == .3
    assert manifest["temporal_subsampling"] is False
    with h5py.File(source, "r") as old, h5py.File(tmp_path / "public/episode.h5", "r") as new:
        assert new["actions"].shape == (18, 8)
        assert np.array_equal(new["actions"][:], old["actions"][:])
        assert np.array_equal(new["timestamp"][:], old["timestamp"][:])
        assert new["side_camera_rgb"].shape == new["wrist_camera_rgb"].shape == (18, 3, 96, 96)
        assert new["terminal_observation/side_camera_rgb"].shape == (3, 96, 96)
        assert object_id(new["side_camera_rgb"]) == object_id(new["camera_1_rgb"])
        assert object_id(new["wrist_camera_rgb"]) == object_id(new["camera_2_rgb"])
        assert inspect_links(new) == []
        assert new.attrs["task_success"] == old.attrs["task_success"]
        assert new["language_instruction"].asstr()[()] == old["language_instruction"].asstr()[()]
        assert new["task_events_json"].dtype.kind == "S"  # lossless string recompression
        assert new["task_events_json"].compression == "gzip"
        assert "/home/" not in new["camera_pose_json"].asstr()[0]
        meta = json.loads(new.attrs["camera_meta_json"])
        assert meta["K"] == json.loads(old.attrs["camera_meta_json"])["K"]
        assert meta["prim"] == "/World/Franka/Camera"
    assert manifest["metadata_sanitization"]
    assert "/home/" not in json.dumps(manifest)


def test_refuses_external_links_even_when_other_episode_labels_are_valid(source, tmp_path):
    with h5py.File(source, "a") as f:
        f["external"] = h5py.ExternalLink("elsewhere.h5", "/actions")
    with pytest.raises(ValueError, match="nonportable"):
        export_sample(source, tmp_path / "public", verify_reader=False)


def test_never_fabricates_success_or_exports_unclosed_file(source, tmp_path):
    with h5py.File(source, "a") as f:
        f.attrs["complete"] = False
    with pytest.raises(ValueError, match="closed eligible"):
        export_sample(source, tmp_path / "public", verify_reader=False)
    assert not (tmp_path / "public").exists()


def test_refuses_overwrite_and_size_limit_does_not_truncate(source, tmp_path):
    with pytest.raises(ValueError, match="never truncated"):
        export_sample(source, tmp_path / "public", verify_reader=False, max_bytes=1)
    with h5py.File(tmp_path / "public/episode.h5", "r") as f:
        assert len(f["actions"]) == 18 and len(f["side_camera_rgb"]) == 18
    with pytest.raises(FileExistsError):
        export_sample(source, tmp_path / "public", verify_reader=False)


def test_source_metadata_with_credential_like_value_is_not_publishable(source, tmp_path):
    with h5py.File(source, "a") as f:
        f.attrs["secret"] = "hf_" + "testfixture" * 4
    with pytest.raises(ValueError, match="Credential-like"):
        export_sample(source, tmp_path / "public", verify_reader=False)


def test_compact_sample_is_read_by_normal_project_act_dp_dataset(source, tmp_path):
    pytest.importorskip("torch")
    export_sample(source, tmp_path / "public", verify_reader=False)
    results = normal_reader_check(tmp_path / "public/episode.h5", 96)
    assert len(results) == 2
    assert results[0]["batch"]["obs"]["side_camera_rgb"]["shape"] == [3, 3, 96, 96]
    assert results[1]["batch"]["obs"]["wrist_camera_rgb"]["shape"] == [3, 3, 3, 96, 96]
    assert all(r["batch"]["action"]["shape"] == [3, 16, 8] for r in results)
