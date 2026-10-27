"""CPU data-use and transfer behavior using real, tiny qualified H5 payloads."""
import hashlib
import json
import os
from pathlib import Path
import shutil

import h5py
import numpy as np
import pytest

from data_collectors.lab_cuvette_project_release_collector import LabCuvetteProjectReleaseCollector
from demos.lab_cuvette_project_release_v1.dataset_index import build_index, main as index_main
from demos.lab_cuvette_project_release_v1.membership import import_curated_policy, write_members
from demos.lab_cuvette_project_release_v1.transfer import check_dependencies, main as transfer_main
from scripts.read_lab_cuvette_env_v1_data import inspect


def make_run(root, successes=(False,) * 11):
    paths = []
    for ordinal, success in enumerate(successes):
        collector = LabCuvetteProjectReleaseCollector(dict(version="Project_release_v1",
            physics=dict(hz=240, control_hz=60)), root / f"episode_{ordinal:04d}", save_video=False)
        collector.begin_episode(0, episode_id=f"usage-fixture-{ordinal}", metadata=dict(
            task_type="loading", condition_group="natural", scene_mode="standard",
            scene_version="Project_release_v1", frozen_scene_sha256="a" * 64,
            source_slot_id="A1", target_seat_id="candidate_far_hinge", asset_id="cuvette_xy_1000"))
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


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_policy_default_cli_selects_one_of_eleven_using_existing_curated_membership(tmp_path, capsys):
    run = tmp_path / "run"
    paths = make_run(run)
    before = [sha(path) for path in paths]
    curated = tmp_path / "old_curated.json"
    curated.write_text(json.dumps(dict(included_actual_model_episode_ids=["usage-fixture-0"],
        excluded_diagnostic_episode_ids=[f"usage-fixture-{i}" for i in range(1, 11)], source_h5_sha256=before[0])))
    members = tmp_path / "members.json"
    import_curated_policy(run, curated, members)
    output = run / "index/policy.hdf5"
    index_main([str(run), "--output", str(output), "--members", str(members)])
    result = json.loads(capsys.readouterr().out)
    assert result["purpose_selection"] == "policy_evaluation"
    assert result["counts"] == dict(success=0, failure=1, all_valid=1, incomplete=0)
    assert len(result["excluded_episode_ids"]) == 10
    assert all(row["exclusion_reason"] == "purpose_mismatch" and row["record_purpose"] == "resource_probe"
               for row in result["episodes"] if not row["included"])
    for policy in ("act", "dp"):
        assert len(inspect(output, "failure", policy)["episodes"]) == 1
    diagnostic = build_index(run, run / "index/diagnostic.hdf5", purpose="all-completed", members=members)
    assert diagnostic["counts"]["all_valid"] == 11
    assert len(inspect(run / "index/diagnostic.hdf5", "all_valid")["episodes"]) == 11
    assert [sha(path) for path in paths] == before


def test_unknown_usage_excluded_from_formal_index_but_explicit_members_can_select_it(tmp_path):
    run = tmp_path / "run"
    paths = make_run(run, (True, False))
    report = build_index(run, run / "formal.hdf5", purpose="policy_evaluation")
    assert report["included_episode_ids"] == []
    assert {row["exclusion_reason"] for row in report["episodes"]} == {"purpose_unknown"}
    members = run / "members.json"
    write_members(run, members, {"usage-fixture-1": "unknown"})
    report = build_index(run, run / "explicit.hdf5", purpose="members", members=members)
    assert report["included_episode_ids"] == ["usage-fixture-1"]
    assert report["episodes"][1]["record_purpose"] == "unknown"
    with h5py.File(paths[1]) as source:
        assert source.attrs["task_success"] == False


@pytest.mark.parametrize("mode", ["relative-links", "copy"])
def test_portable_move_and_camera_aliases_use_normal_readers(tmp_path, mode):
    run = tmp_path / "original_tree"
    make_run(run, (True, False, True))
    index = run / "index/data.hdf5"
    report = build_index(run, index, mode=mode, purpose="all-completed")
    assert report["counts"] == dict(success=2, failure=1, all_valid=3, incomplete=0)
    if mode == "relative-links":
        moved = tmp_path / "moved_tree"
        shutil.move(run, moved)
        relocated = moved / "index/data.hdf5"
    else:
        moved = tmp_path / "standalone"
        moved.mkdir()
        relocated = moved / "renamed.hdf5"
        shutil.move(index, relocated)
        shutil.rmtree(run)
    check = check_dependencies(relocated, verify_sha256=True)
    assert check["ok"] and check["self_contained"] == (mode == "copy")
    with h5py.File(relocated) as source:
        for group in source.values():
            assert group["side_camera_rgb"].id == group["camera_1_rgb"].id
            assert group["wrist_camera_rgb"].id == group["camera_2_rgb"].id
    for reader in ("act", "dp"):
        for sample_filter, count in (("success", 2), ("failure", 1), ("all_valid", 3)):
            assert len(inspect(relocated, sample_filter, reader)["episodes"]) == count


def test_missing_relative_source_reports_exact_path_and_nonzero_cli(tmp_path, capsys):
    run = tmp_path / "run"
    paths = make_run(run, (True,))
    index = run / "index/data.hdf5"
    build_index(run, index)
    missing = paths[0].resolve()
    paths[0].unlink()
    assert transfer_main([str(index)]) == 2
    result = json.loads(capsys.readouterr().out)
    assert not result["ok"]
    assert result["dependencies"][0]["dependency"] == str(missing)
    assert result["problems"] == ["Missing source H5: " + str(missing)]


@pytest.mark.parametrize("field,value,match", [("source_h5_sha256", "0" * 64, "hash mismatch"),
    ("source_h5", "wrong.h5", "path mismatch"), ("episode_id", "not-present", "absent from source")])
def test_membership_identity_and_bytes_are_binding(tmp_path, field, value, match):
    run = tmp_path / "run"
    paths = make_run(run, (True,))
    members = run / "members.json"
    payload = write_members(run, members, {"usage-fixture-0": "demonstration"})
    before = sha(paths[0])
    payload["members"][0][field] = value
    members.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match=match):
        build_index(run, run / "bad.hdf5", purpose="demonstration", members=members)
    assert not (run / "bad.hdf5").exists()
    assert sha(paths[0]) == before


def test_writer_process_protection_and_usage_qualification_independence(tmp_path):
    run = tmp_path / "run"
    make_run(run, (False,))
    (run / "run_manifest.json").write_text(json.dumps(dict(process_id=os.getpid())))
    with pytest.raises(RuntimeError, match="still exists"):
        build_index(run, run / "active.hdf5")
    (run / "run_manifest.json").write_text(json.dumps(dict(process_id=999999999)))
    members = run / "members.json"
    write_members(run, members, {"usage-fixture-0": "demonstration"})
    report = build_index(run, run / "demo.hdf5", purpose="demonstration", members=members)
    assert report["counts"] == dict(success=0, failure=1, all_valid=1, incomplete=0)
    assert report["episodes"][0]["filter_reasons"]["success"] == "not_task_success"


def test_curated_hash_mismatch_does_not_publish_a_sidecar(tmp_path):
    run = tmp_path / "run"
    paths = make_run(run, (False,))
    before = sha(paths[0])
    curated = tmp_path / "curated.json"
    curated.write_text(json.dumps(dict(included_actual_model_episode_ids=["usage-fixture-0"],
        excluded_diagnostic_episode_ids=[], source_h5_sha256="0" * 64)))
    output = tmp_path / "bad_members.json"
    with pytest.raises(ValueError, match="no longer matches"):
        import_curated_policy(run, curated, output)
    assert not output.exists()
    assert sha(paths[0]) == before
