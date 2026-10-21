"""Explicit closed11 only; independently verify actual early-stop task events.

No episode tree scan. The new ongoing natural process is not an input. The
event verifier is reusable for later explicitly selected, individually closed
controlled episodes; a config declaration alone never satisfies it.
"""
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT))

import h5py
import numpy as np
from omegaconf import OmegaConf
from demos.lab_cuvette_size_v1.frozen_scene import file_sha, load_frozen, validate_frozen_scene
from scripts.validate_lab_cuvette_size_v1_data import (audit_episode, make_index,
    official_process_gate, validate_reader)

OUT = Path(__file__).resolve().parent
COLLECTION = ROOT / "outputs/lab_cuvette_loading/Size_v1/collection_standard"
SUCCESS_RUNS = ("verify5_20261021T021430Z_274d1b2d_00", "success_20261021T034658Z_8928651a_00")
FAILURE_RUN = "controlled_failure_20261021T045710Z_edfa49e9_00"
EXPLICIT_EPISODES = tuple(COLLECTION / "runs" / run / f"episode_{index:04d}"
                         for run in SUCCESS_RUNS for index in range(5)) + (
    COLLECTION / "runs" / FAILURE_RUN / "episode_0000",)


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def text(value):
    return value.decode() if isinstance(value, bytes) else str(value)


def verify_controlled_failure_event(episode):
    """Read CLOSED data; return evidence without changing raw labels or config.

    Apply after official_process_gate. If configured but never executed (e.g.
    a grasp failure before INSERT), keep that raw physical record separately;
    it cannot fill the executed deterministic-action-deviation failure quota.
    """
    episode = Path(episode).resolve()
    if not episode.is_relative_to(COLLECTION / "runs"):
        raise ValueError("Controlled event verification only accepts the official collection")
    final = read(episode / "result.json")
    if final.get("complete") is not True:
        raise ValueError("Refusing an unclosed active controlled episode")
    cfg = OmegaConf.to_container(OmegaConf.load(episode / "config.yaml"), resolve=True)
    expected = cfg.get("experiment", {}).get("deviation", {})
    event_path = episode / "teacher_events.json"
    events = read(event_path)
    actual = [event for event in events if event.get("event") == "deterministic_action_deviation"]
    stops = [event for event in events if event.get("event") == "teacher_stop_suggestion"]
    checks = dict(one_actual_deviation_event=len(actual) == 1,
        configured_condition_group=cfg.get("experiment", {}).get("condition_group") == "deterministic_action_deviation",
        configured_INSERT_stage=expected.get("stage") == "INSERT", configured_metre_unit=expected.get("unit") == "m",
        complete_controller_version=bool(expected.get("controller_version")),
        task_failure_is_CONTROLLED_EARLY_STOP=final.get("failure_type") == "CONTROLLED_EARLY_STOP" and final.get("termination_reason") == "CONTROLLED_EARLY_STOP",
        raw_record_valid_and_task_failed=final.get("record_valid") is True and final.get("task_success") is False,
        no_release_or_retreat=final.get("release_observed") is False and final.get("retreat_observed") is False,
        post_retreat_window_unavailable=final.get("post_retreat_window", {}).get("status") == "unavailable",
        post_retreat_stability_unknown=final.get("stable_after_retreat") is None)
    event, state = actual[0] if len(actual) == 1 else None, None
    state_index = None
    with h5py.File(episode / "dataset/episode_0000.h5", "r") as source:
        assert bool(source.attrs.get("complete")), "Refusing unclosed HDF5"
        saved_spec = json.loads(text(source.attrs.get("deterministic_action_deviation_json", "null")))
        checks["HDF5_spec_matches_config"] = saved_spec == expected
        if event is not None:
            checks["event_spec_matches_config"] = event.get("spec") == expected
            times = source["next_timestamp"][:]
            state_index = int(np.argmin(abs(times - event["t"])))
            state = json.loads(text(source["privileged/next_state_json"][state_index]))
            phase = text(source["phase"][state_index])
            checks["event_matches_actual_successor_time"] = abs(float(times[state_index]) - float(event["t"])) <= 1e-8
            checks["actual_saved_phase_INSERT"] = phase == "INSERT"
            checks["event_depth_matches_saved_physical_state"] = abs(float(state["depth_m"]) - float(event["actual_depth_m"])) <= 1e-10
            checks["actual_depth_reached_requested_stop"] = float(state["depth_m"]) >= float(expected["stop_insertion_at_depth_m"])
            checks["normal_actions_only_flag"] = event.get("normal_actions_only") is True
            checks["teacher_stop_same_time_and_phase"] = any(stop.get("status") == "CONTROLLED_EARLY_STOP" and stop.get("phase") == "INSERT" and abs(float(stop["t"]) - float(event["t"])) <= 1e-10 for stop in stops)
            checks["final_simulation_time_matches_stop"] = abs(float(final["simulation_seconds"]) - float(event["t"])) <= 1e-8
    return dict(schema="labsim.Size_v1.actual_controlled_deviation_event_audit.v1",
        episode_id=final["episode_id"], source_episode=str(episode.relative_to(ROOT)),
        source_teacher_events_sha256=file_sha(event_path), source_result_sha256=file_sha(episode / "result.json"),
        configuration_spec=expected, actual_event=event, actual_event_count=len(actual),
        corresponding_successor_row=state_index, actual_depth_m=None if state is None else state["depth_m"],
        stop_depth_overshoot_m=None if state is None else float(state["depth_m"]) - float(expected["stop_insertion_at_depth_m"]),
        checks=checks, controlled_deviation_actually_executed_and_failure_qualified=all(checks.values()),
        raw_labels_or_config_modified=False,
        scope="Actual trajectory failure caused by observed normal-action INSERT early stop, not physical jam or short-budget interface test")


def write_new(name, value):
    with (OUT / name).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def main():
    cfgpath = ROOT / "config/lab_cuvette_loading/Size_v1/standard.yaml"
    frozenpath = ROOT / "config/lab_cuvette_loading/Size_v1/frozen_scene.json"
    frozen = load_frozen(frozenpath)
    validate_frozen_scene(OmegaConf.load(cfgpath), frozen, ROOT, purpose="collect")
    rows, controlled_evidence = [], []
    for number, episode in enumerate(EXPLICIT_EPISODES):
        print("EXPLICIT_CLOSED_SOURCE", number + 1, str(episode), flush=True)
        row = official_process_gate(audit_episode(episode / "dataset/episode_0000.h5", frozen["frozen_scene_sha256"]), COLLECTION)
        if row["labels"]["condition_group"] == "deterministic_action_deviation":
            evidence = verify_controlled_failure_event(episode)
            controlled_evidence.append(evidence)
            if not evidence["controlled_deviation_actually_executed_and_failure_qualified"]:
                row["admission_errors"].append("configured_deviation_not_independently_observed")
                row["success"] = row["failure"] = row["all_valid"] = False
            row["actual_controlled_event_admission"] = evidence["controlled_deviation_actually_executed_and_failure_qualified"]
        rows.append(row)
    assert len(rows) == 11 and sum(row["success"] for row in rows) == 10 and sum(row["failure"] for row in rows) == 1
    assert len(controlled_evidence) == 1 and controlled_evidence[0]["controlled_deviation_actually_executed_and_failure_qualified"]
    index = COLLECTION / "checks/first_failure_index/dataset/episode_data.hdf5"
    assert make_index(rows, index, collection_root=COLLECTION) == 11
    readers = [validate_reader(index, frozenpath, cfgpath, sample_filter=selection, policy_type=policy)
               for selection in ("success", "failure") for policy in ("act", "dp")]
    process_runs = []
    for name in (*SUCCESS_RUNS, FAILURE_RUN):
        proof_path = COLLECTION / "runs" / name / "process_exit.json"
        proof = read(proof_path)
        assert proof["process_exited"] is True and proof["exit_code"] == 0 and not proof["interrupted"]
        process_runs.append(dict(source=str(proof_path.relative_to(ROOT)), sha256=file_sha(proof_path),
            exit_code=0, interrupted=False, elapsed_wall_s=proof["elapsed_wall_s"], pid=proof["pid"]))
    result = dict(schema="labsim.Size_v1.collection_audit.v1", admission_scope="official_closed_exit0_explicit11_plus_actual_deviation_event",
        official_collection_quota_evidence=True, frozen_scene_sha256=frozen["frozen_scene_sha256"],
        qualified_success_count=10, qualified_failure_count=1, inspected_episode_count=11,
        success_target=20, failure_target=20, success_missing=10, failure_missing=19,
        condition_groups=dict(natural=dict(success=10, failure=0), deterministic_action_deviation=dict(success=0, failure=1)),
        process_statistics=dict(started=3, completed_exit0=3, interrupted=0, nonzero_exit=0),
        process_evidence=process_runs, explicit_source_HDF5_files=[str((ep / "dataset/episode_0000.h5").relative_to(ROOT)) for ep in EXPLICIT_EPISODES],
        episodes=rows, actual_controlled_event_evidence=controlled_evidence,
        reader_validation=readers, index_path=str(index.relative_to(ROOT)), index_bytes=index.stat().st_size,
        index_storage="relative_external_links", final_default_index_created=False,
        active_natural_episode_opened=False, episode_tree_scan_performed=False,
        original_labels_modified=False, random10_required=False,
        future_controlled_admission="Apply verify_controlled_failure_event to every individually closed explicit source; config spec alone is insufficient")
    write_new("collection11_audit.json", result)
    write_new("actual_INSERT_early_stop_event.json", controlled_evidence[0])
    write_new("normal_ACT_DP_success_and_failure_read.json", dict(readers=readers,
        success_BC_filter_excludes_failure=True, failure_retains_task_success_false=True,
        source_labels_modified=False, training_executed=False))
    print(json.dumps(dict(qualified_success=10, qualified_failure=1, actual_deviation_event=True,
        readers=len(readers), final_default_index_created=False), ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
