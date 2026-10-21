"""Actual closed first10 only: explicit source allowlist; no tree episode scan.

The ongoing controlled run is deliberately outside this list. This script uses
existing audit/reader/index functions and never changes a source HDF5 label.
"""
from pathlib import Path
import csv
import json
import sys

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT))

import h5py
import numpy as np
from omegaconf import OmegaConf
from demos.lab_cuvette_size_v1.frozen_scene import (canonical_sha, file_sha,
    load_frozen, scene_projection, validate_frozen_scene)
from scripts.validate_lab_cuvette_size_v1_data import (audit_episode, make_index,
    official_process_gate, validate_reader)

OUT = Path(__file__).resolve().parent
COLLECTION = ROOT / "outputs/lab_cuvette_loading/Size_v1/collection_standard"
RUN_NAMES = ("verify5_20261021T021430Z_274d1b2d_00", "success_20261021T034658Z_8928651a_00")
EXPLICIT_EPISODES = tuple(COLLECTION / "runs" / run / f"episode_{index:04d}"
                          for run in RUN_NAMES for index in range(5))


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_new(name, value):
    with (OUT / name).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def main():
    config_path = ROOT / "config/lab_cuvette_loading/Size_v1/standard.yaml"
    frozen_path = ROOT / "config/lab_cuvette_loading/Size_v1/frozen_scene.json"
    frozen = load_frozen(frozen_path)
    validate_frozen_scene(OmegaConf.load(config_path), frozen, ROOT, purpose="collect")
    fingerprint = frozen["frozen_scene_sha256"]
    processes = []
    for run in RUN_NAMES:
        manifest = COLLECTION / "driver_records" / ("batch_" + run + ".json")
        batch, process = read(manifest), read(COLLECTION / "runs" / run / "process_exit.json")
        for evidence in (batch, process):
            assert evidence["process_exited"] is True and evidence["exit_code"] == 0
            assert not evidence["interrupted"]
        assert batch["official_collection_run"] is True
        assert batch["requested_episodes"] == 5
        processes.append(dict(run=run, driver_manifest=str(manifest.relative_to(ROOT)),
            driver_manifest_sha256=file_sha(manifest), source_process_exit_sha256=file_sha(COLLECTION / "runs" / run / "process_exit.json"),
            process_exited=True, exit_code=0, interrupted=False, pid=process["pid"],
            elapsed_wall_s=process["elapsed_wall_s"], requested_episodes=5))
    rows, initial_rows = [], []
    for number, episode in enumerate(EXPLICIT_EPISODES):
        source = episode / "dataset/episode_0000.h5"
        print("READ_ONLY_CLOSED_SOURCE", number + 1, str(source), flush=True)
        result = read(episode / "result.json")
        assert result["complete"] is True
        row = official_process_gate(audit_episode(source, fingerprint), COLLECTION)
        assert row["success"] is True and row["failure"] is False, row["admission_errors"]
        assert row["labels"]["condition_group"] == "natural"
        assert json.loads(row["labels"]["deterministic_action_deviation_json"]) in (None, {})
        rows.append(row)
        cfg = OmegaConf.to_container(OmegaConf.load(episode / "config.yaml"), resolve=True)
        initial = read(episode / "initial_debug.json")
        with h5py.File(source, "r") as record:
            first_q = record["joint_positions"][0].tolist()
            debug = record["privileged/next_state_json"][-1]
            debug = json.loads(debug.decode() if isinstance(debug, bytes) else debug)
            assert np.array_equal(first_q, initial["joints9"])
            assert record.attrs["complete"] and len(record["actions"]) == result["frames"]
        post = result["post_retreat_window"]
        initial_rows.append(dict(episode=str(episode.relative_to(COLLECTION)), episode_id=result["episode_id"],
            source_slot_id=row["labels"]["source_slot_id"], target_seat_id=row["labels"]["target_seat_id"],
            asset_id=row["labels"]["asset_id"], frozen_scene_sha256=fingerprint,
            seed=row["labels"]["seed"], controller_version=cfg["experiment"]["controller_version"],
            scene_projection_sha256=canonical_sha(scene_projection(cfg)),
            control_physics_robot_sha256=canonical_sha({key: cfg[key] for key in
                ("control", "physics", "robot", "gripper", "acceptance", "demo_release")}),
            cameras_sha256=canonical_sha(cfg["cameras"]),
            initial_position_m=initial["object_position_m"], initial_quaternion_wxyz=initial["object_quaternion_wxyz"],
            initial_joints9=first_q, initial_t_s=initial["simulation_time"],
            initial_source_bottom_gap_m=initial["source_bottom_gap_m"],
            initial_source_penetration_m=initial["source_rack_penetration_m"],
            task_success=result["task_success"], record_valid=result["record_valid"],
            release_observed=result["release_observed"], retreat_observed=result["retreat_observed"],
            post_retreat_stable=post["stable"], post_retreat_window_s=post["measured_duration_s"],
            post_retreat_position_drift_m=post["position_drift_m"],
            post_retreat_orientation_change_deg=post["orientation_change_deg"],
            final_depth_m=debug["depth_m"], final_tilt_deg=debug["tilt_deg"],
            final_bottom_gap_m=debug["target_bottom_gap_m"],
            final_bottom_support_N=debug["target_bottom_support_N"],
            actual_control_steps=result["actual_control_steps"], simulation_seconds=result["simulation_seconds"],
            physics_quality_flags=result["physics_quality_flags"], child_process_exit_code=0, child_interrupted=False))
    reference = initial_rows[0]
    for row in initial_rows:
        row["initial_position_delta_from_first_m"] = float(np.linalg.norm(np.array(row["initial_position_m"]) - reference["initial_position_m"]))
        q, q0 = np.array(row["initial_quaternion_wxyz"]), np.array(reference["initial_quaternion_wxyz"])
        row["initial_orientation_delta_from_first_deg"] = float(np.degrees(2 * np.arccos(np.clip(abs(np.dot(q / np.linalg.norm(q), q0 / np.linalg.norm(q0))), -1, 1))))
        row["initial_arm_max_delta_from_first_rad"] = float(np.max(abs(np.array(row["initial_joints9"][:7]) - reference["initial_joints9"][:7])))
        row["initial_finger_max_delta_from_first_m"] = float(np.max(abs(np.array(row["initial_joints9"][7:]) - reference["initial_joints9"][7:])))
    index = COLLECTION / "checks/ten/dataset/episode_data.hdf5"
    count = make_index(rows, index, collection_root=COLLECTION)
    assert count == 10
    readers = [validate_reader(index, frozen_path, config_path, policy_type=policy) for policy in ("act", "dp")]
    audit = dict(schema="labsim.Size_v1.collection_audit.v1", admission_scope="official_collection_closed_exit0_explicit10_allowlist",
        official_collection_quota_evidence=True, frozen_scene_sha256=fingerprint,
        scene_mode="standard", scene_randomization_enabled=False, inspected_episode_count=10,
        qualified_success_count=10, qualified_failure_count=0, success_target=20, failure_target=20,
        success_missing=10, failure_missing=20, archived_not_counted=0,
        condition_groups=dict(natural=dict(success=10, failure=0), deterministic_action_deviation=dict(success=0, failure=0)),
        explicit_source_HDF5_files=[str((episode / "dataset/episode_0000.h5").relative_to(ROOT)) for episode in EXPLICIT_EPISODES],
        ongoing_controlled_episode_opened=False, episode_tree_scanning_performed=False,
        process_statistics=dict(started=2, completed_exit0=2, interrupted=0, nonzero_exit=0, started_episodes=10, completed_episodes=10),
        process_evidence=processes, episodes=rows, reader_validation=readers,
        index_path=str(index.relative_to(ROOT)), index_bytes=index.stat().st_size,
        index_storage="relative_external_links", final_default_index_created=False,
        labels_modified=False, random10_is_not_an_acceptance_requirement=True)
    write_new("collection10_audit.json", audit)
    write_new("normal_ACT_DP_read.json", dict(scope="Actual10 qualified frozen standard successes; normal readers and guarded dataset", readers=readers))
    fixed_fields = ("source_slot_id", "target_seat_id", "asset_id", "frozen_scene_sha256", "controller_version",
                    "scene_projection_sha256", "control_physics_robot_sha256", "cameras_sha256")
    write_new("initial_state_and_results.json", dict(schema="labsim.Size_v1.closed10_initial_state_check.v1",
        episode_count=10, compared_to_episode=reference["episode_id"],
        all_fixed_fields_equal={key: len({row[key] for row in initial_rows}) == 1 for key in fixed_fields},
        max_position_delta_m=max(row["initial_position_delta_from_first_m"] for row in initial_rows),
        max_orientation_delta_deg=max(row["initial_orientation_delta_from_first_deg"] for row in initial_rows),
        max_arm_joint_delta_rad=max(row["initial_arm_max_delta_from_first_rad"] for row in initial_rows),
        max_finger_joint_delta_m=max(row["initial_finger_max_delta_from_first_m"] for row in initial_rows),
        scope="Actual initial_debug and first/last small HDF5 state fields from explicit10 closed sources only",
        reset_seed_note="0..4 in each process are bookkeeping; scene randomization disabled; no broad probability claim",
        real_calibrated=False, raw_labels_or_states_modified=False, episodes=initial_rows))
    columns = list(initial_rows[0])
    with (OUT / "initial_state_and_results.csv").open("x", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows({key: json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else value
                         for key, value in row.items()} for row in initial_rows)
    print(json.dumps(dict(qualified_success=10, qualified_failure=0, active_episode_opened=False,
        index_bytes=index.stat().st_size, reader_policies=[item["policy_type"] for item in readers]), ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
