"""Explicit21 CLOSED records only: 20 natural successes and one actual failure.

No episode tree scan, active-process reads, label changes, simulation or training.
The in-progress5mm controlled batch is deliberately absent from RUNS.
"""
from pathlib import Path
import csv
import json
import os
import sys

for variable in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
                 "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    os.environ[variable] = "2"
ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT))

import h5py
import numpy as np
import torch
from omegaconf import OmegaConf
from demos.lab_cuvette_size_v1.frozen_scene import (canonical_sha, file_sha,
    load_frozen, scene_projection, validate_frozen_scene)
from scripts.validate_lab_cuvette_size_v1_data import (audit_episode, make_index,
    official_process_gate, validate_reader)

torch.set_num_threads(2)
torch.set_num_interop_threads(2)
OUT = Path(__file__).resolve().parent
COLLECTION = ROOT / "outputs/lab_cuvette_loading/Size_v1/collection_standard"
RUNS = (
    ("verify5_20261021T021430Z_274d1b2d_00", 5, "natural"),
    ("success_20261021T034658Z_8928651a_00", 5, "natural"),
    ("success_20261021T050557Z_1940849e_00", 5, "natural"),
    ("success_20261021T061505Z_8c146230_00", 5, "natural"),
    ("controlled_failure_20261021T045710Z_edfa49e9_00", 1, "deterministic_action_deviation"),
)


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
    index = COLLECTION / "checks/success20/dataset/episode_data.hdf5"
    if index.exists() or (OUT / "collection21_audit.json").exists():
        raise FileExistsError("Evidence and index use new paths; do not overwrite an earlier audit")
    processes, allowed = [], []
    # Validate every process BEFORE opening any input HDF5. Explicit archived
    # episode paths in each real closed driver record must match this allowlist.
    for name, expected_count, group in RUNS:
        run = COLLECTION / "runs" / name
        manifest_path = COLLECTION / "driver_records" / ("batch_" + name + ".json")
        batch, process = read(manifest_path), read(run / "process_exit.json")
        for evidence in (batch, process):
            assert evidence["process_exited"] is True and evidence["exit_code"] == 0
            assert evidence["interrupted"] is False
        assert batch["official_collection_run"] is True
        assert Path(batch["run_directory"]).resolve() == run.resolve()
        assert batch["frozen_scene_sha256"] == fingerprint
        assert batch["requested_episodes"] == expected_count
        episodes = [run / f"episode_{number:04d}" for number in range(expected_count)]
        assert {Path(item["episode"]).resolve() for item in batch["archive_results"]} == set(episodes)
        assert all(item["archived"] is True for item in batch["archive_results"])
        for episode in episodes:
            assert read(episode / "result.json")["complete"] is True
            allowed.append((episode, group))
        processes.append(dict(run=name, requested_episodes=expected_count,
            condition_group=group, driver_manifest=str(manifest_path.relative_to(ROOT)),
            driver_manifest_sha256=file_sha(manifest_path),
            process_exit_sha256=file_sha(run / "process_exit.json"), process_exited=True,
            exit_code=0, interrupted=False, pid=process["pid"],
            elapsed_wall_s=process["elapsed_wall_s"], archives_confirmed=expected_count))
    assert len(allowed) == 21
    rows, initial_rows, controlled = [], [], []
    for number, (episode, expected_group) in enumerate(allowed):
        source = episode / "dataset/episode_0000.h5"
        print("EXPLICIT_CLOSED_SOURCE", number + 1, str(source), flush=True)
        snapshot = source.stat()
        row = official_process_gate(audit_episode(source, fingerprint), COLLECTION)
        assert not row["admission_errors"], row["admission_errors"]
        assert row["labels"]["condition_group"] == expected_group
        if expected_group == "natural":
            assert row["success"] is True and row["failure"] is False
            assert json.loads(row["labels"]["deterministic_action_deviation_json"]) in (None, {})
        else:
            assert row["success"] is False and row["failure"] is True
            event = row["controlled_deviation_event_evidence"]
            assert event["qualified"] is True and all(event["checks"].values())
            controlled.append(event)
        rows.append(row)
        cfg = OmegaConf.to_container(OmegaConf.load(episode / "config.yaml"), resolve=True)
        initial, result = read(episode / "initial_debug.json"), read(episode / "result.json")
        with h5py.File(source, "r") as record:
            first_q = record["joint_positions"][0].tolist()
            raw = record["privileged/next_state_json"][-1]
            final = json.loads(raw.decode() if isinstance(raw, bytes) else raw)
            assert np.array_equal(first_q, initial["joints9"])
            assert bool(record.attrs["complete"]) and len(record["actions"]) == result["frames"]
        after = source.stat()
        assert (snapshot.st_size, snapshot.st_mtime_ns) == (after.st_size, after.st_mtime_ns)
        post = result["post_retreat_window"]
        initial_rows.append(dict(episode=str(episode.relative_to(COLLECTION)),
            episode_id=result["episode_id"], condition_group=expected_group,
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
            failure_type=result["failure_type"], termination_reason=result["termination_reason"],
            release_observed=result["release_observed"], retreat_observed=result["retreat_observed"],
            post_retreat_window_status=post.get("status"),
            post_retreat_stable=post.get("stable"), post_retreat_window_s=post.get("measured_duration_s"),
            post_retreat_position_drift_m=post.get("position_drift_m"),
            post_retreat_orientation_change_deg=post.get("orientation_change_deg"),
            stable_after_retreat=result["stable_after_retreat"],
            final_depth_m=final["depth_m"], final_tilt_deg=final["tilt_deg"],
            final_bottom_gap_m=final["target_bottom_gap_m"], final_bottom_support_N=final["target_bottom_support_N"],
            actual_control_steps=result["actual_control_steps"], simulation_seconds=result["simulation_seconds"],
            physics_quality_flags=result["physics_quality_flags"], child_process_exit_code=0,
            child_interrupted=False, source_file_unchanged_during_read=True))
    reference = initial_rows[0]
    for row in initial_rows:
        row["initial_position_delta_from_first_m"] = float(np.linalg.norm(np.array(row["initial_position_m"]) - reference["initial_position_m"]))
        q, q0 = np.array(row["initial_quaternion_wxyz"]), np.array(reference["initial_quaternion_wxyz"])
        row["initial_orientation_delta_from_first_deg"] = float(np.degrees(2 * np.arccos(np.clip(abs(np.dot(q / np.linalg.norm(q), q0 / np.linalg.norm(q0))), -1, 1))))
        row["initial_arm_max_delta_from_first_rad"] = float(np.max(abs(np.array(row["initial_joints9"][:7]) - reference["initial_joints9"][:7])))
        row["initial_finger_max_delta_from_first_m"] = float(np.max(abs(np.array(row["initial_joints9"][7:]) - reference["initial_joints9"][7:])))
    assert make_index(rows, index, collection_root=COLLECTION) == 21
    readers = [validate_reader(index, frozen_path, config_path, sample_filter=selection, policy_type=policy)
               for selection in ("success", "failure") for policy in ("act", "dp")]
    assert sum(row["success"] for row in rows) == 20 and sum(row["failure"] for row in rows) == 1
    audit = dict(schema="labsim.Size_v1.collection_audit.v1",
        admission_scope="official_closed_exit0_explicit21_with_production_actual_event_admission",
        official_collection_quota_evidence=True, frozen_scene_sha256=fingerprint,
        scene_mode="standard", scene_randomization_enabled=False, inspected_episode_count=21,
        qualified_success_count=20, qualified_failure_count=1, success_target=20, failure_target=20,
        success_missing=0, failure_missing=19, archived_not_counted=0,
        condition_groups=dict(natural=dict(success=20, failure=0), deterministic_action_deviation=dict(success=0, failure=1)),
        explicit_source_HDF5_files=[str((episode / "dataset/episode_0000.h5").relative_to(ROOT)) for episode, _ in allowed],
        active_controlled_batch_opened=False, episode_tree_scanning_performed=False,
        process_statistics=dict(started=5, completed_exit0=5, interrupted=0, nonzero_exit=0,
            started_episodes=21, completed_episodes=21), process_evidence=processes,
        episodes=rows, controlled_actual_event_evidence=controlled, reader_validation=readers,
        index_path=str(index.relative_to(ROOT)), index_bytes=index.stat().st_size,
        index_storage="relative_external_links", final_default_index_created=False,
        labels_modified=False, real_calibrated=False, random10_required=False,
        qualification_scope="Explicit closed21 snapshot only; not the final40 collection",
        CPU_thread_limit=2, GPU_started=False, training_executed=False)
    write_new("collection21_audit.json", audit)
    write_new("normal_ACT_DP_success_and_failure_read.json", dict(readers=readers,
        success_BC_filter_excludes_failure=True, failure_retains_task_success_false=True,
        source_labels_modified=False, training_executed=False))
    write_new("actual_controlled_event_admission.json", controlled[0])
    natural_rows = [row for row in initial_rows if row["condition_group"] == "natural"]
    fixed = ("source_slot_id", "target_seat_id", "asset_id", "frozen_scene_sha256", "controller_version",
             "scene_projection_sha256", "control_physics_robot_sha256", "cameras_sha256")
    write_new("initial_state_and_results.json", dict(schema="labsim.Size_v1.closed21_initial_state_check.v1",
        episode_count=21, natural_success_count=20, compared_to_episode=reference["episode_id"],
        all20_natural_fixed_fields_equal={key: len({row[key] for row in natural_rows}) == 1 for key in fixed},
        all21_fixed_fields_equal={key: len({row[key] for row in initial_rows}) == 1 for key in fixed},
        max_initial_position_delta_m=max(row["initial_position_delta_from_first_m"] for row in natural_rows),
        max_initial_orientation_delta_deg=max(row["initial_orientation_delta_from_first_deg"] for row in natural_rows),
        max_initial_arm_joint_delta_rad=max(row["initial_arm_max_delta_from_first_rad"] for row in natural_rows),
        max_initial_finger_joint_delta_m=max(row["initial_finger_max_delta_from_first_m"] for row in natural_rows),
        reset_seed_note="0..4 per natural process are bookkeeping; scene randomization disabled; exact repeated initial states do not establish broad-scene success probability",
        real_calibrated=False, raw_labels_or_states_modified=False, episodes=initial_rows))
    with (OUT / "initial_state_and_results.csv").open("x", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, list(initial_rows[0])); writer.writeheader()
        writer.writerows({key: json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else value
                          for key, value in row.items()} for row in initial_rows)
    print(json.dumps(dict(qualified_success=20, qualified_failure=1, readers=len(readers),
        final_default_index_created=False, active_controlled_batch_opened=False,
        success_split=[dict(policy=row["policy_type"], train=len(row["train_episode_ids"]),
            validation=len(row["validation_episode_ids"])) for row in readers if row["sample_filter"] == "success"]), ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
