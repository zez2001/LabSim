"""One-shot, read-only acceptance audit for completed V0_demo03 batches.

This deliberately waits for the executor's post-close adjudication and summary
files before opening any H5. It neither runs simulation nor rewrites raw data.
Use a NEW --output directory. Pending episodes are reported, never polled.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

import h5py
import numpy as np
from omegaconf import OmegaConf

from demos.lab_cuvette_demo03.analyze import CHECK_NAMES, json_safe, load_json, sha256, write_new
from demos.lab_cuvette_demo03.data_check import decode, inspect_episode
from demos.lab_cuvette_demo03.scene import layout

COMPLETION_MARKERS = ("independent_score.json", "adjudication.json", "execution_summary.json")
QUALIFICATION_GATES = {
    "raw_success", "raw_data_eligible", "raw_full_task_eligible", "raw_workflow_success",
    "independently_data_eligible", "independently_workflow_success", "all_required_independent_checks",
}
SEMANTICS = {
    "raw_result": "result.json is saved before independent adjudication. Its data_eligible=false and full_task_eligible=false are conservative provisional fields, not the final H5 eligibility.",
    "final_qualification": "independent_score.json, post-close adjudication.json and completed H5 qualification attributes determine adapted-scene eligibility. execution_summary.data_eligible copies the independent score; its legacy full_task_eligible remains provisional.",
    "sampled_progress": "privileged/progress is controller progress at transition caching. Final VERIFY adjudication occurs after the last cached transition. A last sampled stable=false is preserved; final stability is independently measured from the actual post-retreat physics window, not filled into progress.",
    "scope": "video_demo_adapted simulated workflow; native_pair_success=false and real_calibrated=false remain separate facts even for eligible success.",
    "failure": "A physically failed episode can pass schema/timestamp/label-consistency checks while correctly remaining ineligible. Expected false qualification gates are not malformed-data errors.",
    "geometry": "Assembly verification recomputes config layout and compares saved preflight plus actual initial pose. It is not an independent reread of composed USD/cooked PhysX surfaces or a proof of global collision accuracy.",
}


def near(a, b, tolerance=1e-10):
    try:
        a, b = np.asarray(a, float), np.asarray(b, float)
        return bool(a.shape == b.shape and np.isfinite(a).all() and np.isfinite(b).all()
                    and np.allclose(a, b, atol=tolerance, rtol=0))
    except (TypeError, ValueError):
        return False


def label_checks(score, adjudication, summary, attrs):
    """Pure checks; false workflow is a valid observed result, not an error."""
    checks = score.get("checks", {})
    complete_score = set(checks) == set(CHECK_NAMES)
    success = bool(complete_score and all(v is True for v in checks.values()))
    return dict(
        score_check_set=complete_score,
        workflow_derived_from_all_independent_checks=score.get("workflow_success") is success,
        eligible_derived_from_independent_workflow=score.get("data_eligible") is success,
        final_workflow_labels_agree=all(x is success for x in (
            adjudication.get("workflow_success"), summary.get("independent_workflow_success"),
            attrs.get("workflow_success"), attrs.get("success"))),
        final_eligibility_labels_agree=all(x is success for x in (
            adjudication.get("data_eligible"), summary.get("data_eligible"),
            attrs.get("data_eligible"), attrs.get("full_task_eligible"))),
        no_native_pair_claim=all(x is False for x in (
            score.get("native_pair_success"), adjudication.get("native_pair_success"),
            summary.get("native_pair_success"), bool(attrs.get("native_pair_success", True)))),
        no_real_calibration_claim=all(x is False for x in (
            score.get("real_calibrated"), summary.get("real_calibrated"),
            bool(attrs.get("real_calibrated", True)))),
    )


def assembly_audit(trial, config, preflight, initial, score, batch_kind):
    """Config/preflight/initial-state assembly check; no USD/Isaac import."""
    run_root = trial.parent
    candidates = list((run_root / "source_snapshot/config/lab_cuvette_loading/V0_demo03").glob("*.yaml"))
    if len(candidates) != 1:
        return dict(checks={"unique_original_config_snapshot": False}, candidates=[str(p) for p in candidates])
    baseline_path = candidates[0]
    baseline = OmegaConf.to_container(OmegaConf.load(baseline_path), resolve=True)
    actual = config.get("randomization", {}).get("actual")
    computed = layout(config)
    checks = dict(
        source_slot_matches_config_preflight_score=(bool(computed["source_slot_id"])
            and computed["source_slot_id"] == preflight.get("source_slot_id") == score.get("source_slot_id")),
        target_seat_matches_config_preflight_score=(bool(computed["target_seat_id"])
            and computed["target_seat_id"] == preflight.get("target_seat_id") == score.get("target_seat_id")),
        source_floor_matches_recomputed_layout=near(computed["source_floor"], preflight.get("source_floor")),
        target_floor_matches_recomputed_layout=near(computed["target_floor"], preflight.get("target_floor")),
        preflight_passed=preflight.get("passed") is True,
        full_rack_slots_retained=len(computed["slots"]) == preflight.get("rack_slots") == 36,
        legal_source_slot=computed["source_slot_id"] in baseline.get("randomization", {}).get("legal_slots", []),
        initial_pose_at_selected_source_safe_gap=near(initial.get("position"),
            computed["source_floor"] + [0, 0, config["scene"]["initial_bottom_gap_m"]], 3e-7),
        initial_measured_slot_and_seat=(initial.get("independent_geometry", {}).get("source_slot_id") == computed["source_slot_id"]
            and initial.get("independent_geometry", {}).get("target_seat_id") == computed["target_seat_id"]),
    )
    # Local geometry stays unchanged. Only entire rack/instrument assemblies move.
    for section, keys in (("rack", ("rows", "columns", "inner_m", "wall_m", "depth_m", "base_m", "yaw_deg", "blue_slot_id")),
                          ("adapter", ("inner_m", "outer_m", "height_m", "base_m", "origin_in_instrument_m", "selected_target_seat_id"))):
        checks[section + "_local_geometry_unchanged"] = all(
            config.get(section, {}).get(k) == baseline.get(section, {}).get(k) for k in keys)
    checks["instrument_yaw_unchanged"] = config["scene"].get("instrument_yaw_deg", 0) == baseline["scene"].get("instrument_yaw_deg", 0)
    if actual is None:
        checks["randomization_record_present_when_requested"] = batch_kind != "random"
        checks["fixed_assembly_origins_unchanged"] = (near(config["rack"]["origin_m"], baseline["rack"]["origin_m"])
            and near(config["scene"]["instrument_xyz_m"], baseline["scene"]["instrument_xyz_m"]))
        checks["fixed_source_slot_unchanged"] = config["rack"]["selected_slot_id"] == baseline["rack"]["selected_slot_id"]
    else:
        ds, di = actual.get("rack_translation_m"), actual.get("instrument_assembly_translation_m")
        checks["random_record_slot_matches"] = actual.get("source_slot_id") == computed["source_slot_id"]
        checks["recorded_rack_assembly_shift_applied"] = near(config["rack"]["origin_m"],
            np.asarray(baseline["rack"]["origin_m"]) + np.r_[ds, 0.]) if np.shape(ds) == (2,) else False
        checks["recorded_instrument_assembly_shift_applied"] = near(config["scene"]["instrument_xyz_m"],
            np.asarray(baseline["scene"]["instrument_xyz_m"]) + np.r_[di, 0.]) if np.shape(di) == (2,) else False
        for name, shift, half in (("rack", ds, baseline["randomization"]["rack_translation_half_range_m"]),
                                  ("instrument", di, baseline["randomization"]["instrument_translation_half_range_m"])):
            checks[name + "_shift_inside_declared_range"] = bool(np.shape(shift) == (2,) and
                np.isfinite(shift).all() and np.max(np.abs(shift)) <= float(half) + 1e-12)
        checks["no_unrecorded_in_slot_translation"] = near(actual.get("within_slot_translation_m"), [0., 0.])
        checks["no_unrecorded_rotation"] = actual.get("rotations_randomized") is False
    provenance_path = run_root / "provenance.json"
    provenance = load_json(provenance_path) if provenance_path.exists() else {}
    relative = str(baseline_path.relative_to(run_root / "source_snapshot"))
    checks["snapshot_config_bound_to_provenance"] = provenance.get("sha256", {}).get(relative) == sha256(baseline_path)
    return json_safe(dict(checks=checks, baseline_config=str(baseline_path),
        baseline_config_sha256=sha256(baseline_path), randomization_actual=actual,
        source_floor_m=computed["source_floor"], target_floor_m=computed["target_floor"],
        selected_slot_local_m=computed["source_floor_frame"]["origin_local_m"],
        target_origin_in_instrument_m=computed["target_origin_in_instrument"],
        git_commit_at_run=provenance.get("git_commit"), dirty_at_run=provenance.get("dirty")))


def inspect_trial(trial, kind):
    trial = Path(trial).resolve()
    missing = [name for name in COMPLETION_MARKERS if not (trial / name).is_file()]
    if missing:
        return dict(trial=str(trial), batch=kind, status="PENDING_NOT_OPENED", missing_completion_markers=missing,
                    h5_opened=False, reason="executor writes these markers only after collector.close(); no polling or H5 read attempted")
    score, adjudication, summary, raw, preflight, initial = [load_json(trial / name) for name in (
        "independent_score.json", "adjudication.json", "execution_summary.json", "result.json", "geometry_preflight.json", "initial.json")]
    h5s = list((trial / "dataset").glob("episode_*.h5"))
    if len(h5s) != 1:
        return dict(trial=str(trial), batch=kind, status="MALFORMED", h5_opened=False,
                    errors=["expected one H5"], candidates=[str(p) for p in h5s])
    raw_path = h5s[0]
    data = inspect_episode(raw_path, trial / "independent_score.json")
    attrs = data["attributes"]
    labels = label_checks(score, adjudication, summary, attrs)
    labels["adjudication_bound_to_score"] = adjudication.get("score_sha256") == sha256(trial / "independent_score.json")
    labels["saved_physics_hash_matches_score"] = score.get("physics_records_sha256") == sha256(trial / "physics_records.json")
    labels["saved_events_hash_matches_score"] = score.get("events_sha256") == sha256(trial / "events.json")
    labels["raw_controller_result_hash_matches_score"] = score.get("original_controller_result_sha256") == sha256(trial / "result.json")
    labels["raw_quality_flags_preserved_in_independent_score"] = set(raw.get("physics_quality_flags", [])).issubset(score.get("physics_quality_flags", []))
    labels["summary_quality_flags_preserved_in_independent_score"] = set(summary.get("physics_quality_flags", [])).issubset(score.get("physics_quality_flags", []))
    with h5py.File(raw_path, "r") as h:
        labels["embedded_score_matches_sidecar"] = json.loads(decode(h["independent_score_json"][()])) == score
        progress_names = str(attrs.get("progress_columns", "")).split(",")
        progress = dict(zip(progress_names, map(bool, h["privileged/progress"][-1]))) if len(h["timestamp"]) else None
        last_timestamp = float(h["next_timestamp"][-1]) if len(h["timestamp"]) else None
    config = OmegaConf.to_container(OmegaConf.load(trial / "config.yaml"), resolve=True)
    assembly = assembly_audit(trial, config, preflight, initial, score, kind)
    interface_checks = {k: v for k, v in data["checks"].items() if k not in QUALIFICATION_GATES}
    verify_available = score.get("post_retreat_window", {}).get("available") is True
    labels["unavailable_post_retreat_has_null_stability"] = (verify_available or score.get("stable_after_retreat") is None)
    labels["terminal_time_matches_score_summary_and_h5"] = (near(last_timestamp, score.get("trajectory_end_time_s"), 1e-6)
        and near(last_timestamp, summary.get("simulation_seconds"), 1e-6))
    all_checks = {**{"interface." + k: v for k, v in interface_checks.items()},
                  **{"labels." + k: v for k, v in labels.items()},
                  **{"assembly." + k: v for k, v in assembly["checks"].items()},
                  "raw_unchanged_after_read": data["raw_unchanged_after_read"]}
    errors = [k for k, value in all_checks.items() if value is not True]
    return json_safe(dict(trial=str(trial), batch=kind, status="AUDIT_PASS" if not errors else "AUDIT_FAIL",
        h5_opened=True, audit_pass=not errors, errors=errors, workflow_success=score.get("workflow_success"),
        data_eligible=score.get("data_eligible"), loader_qualification=data["eligible"],
        source_slot_id=score.get("source_slot_id"), target_seat_id=score.get("target_seat_id"),
        native_pair_success=score.get("native_pair_success"), real_calibrated=score.get("real_calibrated"),
        final_status=score.get("status"), failed_independent_checks=[k for k,v in score.get("checks", {}).items() if v is not True],
        simulation_seconds=score.get("simulation_seconds"), wall_seconds=score.get("wall_seconds"),
        frames=data["diagnostics"].get("frames"), last_timestamp=last_timestamp,
        raw_controller_provisional_labels={k: raw.get(k) for k in ("data_eligible", "full_task_eligible", "full_success")},
        sampled_terminal_progress=progress, final_controller_progress=raw.get("stage_progress"),
        post_retreat_window=score.get("post_retreat_window"), stable_after_retreat=score.get("stable_after_retreat"),
        physics_quality_flags=score.get("physics_quality_flags", []), assembly=assembly,
        independent_label_checks=labels, interface_checks=interface_checks,
        data_inspection=data, video_paths=[str(p) for p in sorted(trial.glob("*.mp4"))],
        semantic_notes=SEMANTICS))


def audit_batches(roots, output, expected):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    records, seen = [], set()
    for kind, root in roots:
        root = Path(root).resolve()
        for trial in sorted(p for p in root.rglob("trial_*") if p.is_dir() and "source_snapshot" not in p.parts):
            if trial in seen:
                continue
            seen.add(trial)
            try:
                records.append(inspect_trial(trial, kind))
            except (OSError, ValueError, KeyError, TypeError) as exc:
                records.append(dict(trial=str(trial), batch=kind, status="AUDIT_ERROR",
                                    error=f"{type(exc).__name__}: {exc}", audit_pass=False))
    counts = {}
    for kind in expected:
        entries = [r for r in records if r["batch"] == kind]
        counts[kind] = dict(expected=expected[kind], observed=len(entries),
            completed=sum(r.get("h5_opened") is True for r in entries),
            pending=sum(r["status"] == "PENDING_NOT_OPENED" for r in entries),
            audit_pass=sum(r.get("audit_pass") is True for r in entries),
            workflow_success=sum(r.get("workflow_success") is True for r in entries),
            actual_failed_workflow=sum(r.get("workflow_success") is False for r in entries),
            qualified=sum(r.get("data_eligible") is True and r.get("loader_qualification") is True for r in entries),
            expected_trial_count_met=len(entries) == expected[kind])
    report = dict(schema="labsim.V0_demo03.formal_batch_audit.v1", roots=[dict(kind=k,path=str(Path(p).resolve())) for k,p in roots],
        source_script_sha256=sha256(__file__), read_only=True, training_executed=False,
        semantic_notes=SEMANTICS, counts=counts, records=records,
        batch_audit_complete=all(c["expected_trial_count_met"] and c["completed"] == c["expected"]
                                 and c["audit_pass"] == c["expected"] for c in counts.values()))
    write_new(output / "audit.json", report)
    columns = ("batch", "trial", "status", "audit_pass", "workflow_success", "data_eligible", "loader_qualification",
               "source_slot_id", "target_seat_id", "native_pair_success", "real_calibrated", "frames", "simulation_seconds", "wall_seconds")
    with (output / "episodes.csv").open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows({k: r.get(k) for k in columns} for r in records)
    with (output / "README.md").open("x", encoding="utf-8") as stream:
        stream.write("# V0_demo03 completed-batch data audit\n\nRead-only, one-shot CPU audit. No physics, raw H5 rewriting, training or synthetic trajectories.\n\n")
        for name, note in SEMANTICS.items():
            stream.write(f"- **{name}**: {note}\n")
        stream.write("\n`audit.json` retains every per-episode timestamp/label/assembly check and source H5 SHA; `episodes.csv` is compact. Actual failed workflow is counted separately from malformed data. Uncompleted trials are not opened. Native calibration and OEM pairing remain false.\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixed-root", type=Path)
    parser.add_argument("--random-root", type=Path)
    parser.add_argument("--expected-fixed", type=int, default=5)
    parser.add_argument("--expected-random", type=int, default=10)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    roots = [(name, path) for name,path in (("fixed", args.fixed_root), ("random", args.random_root)) if path]
    if not roots:
        parser.error("at least one batch root is required")
    expected = {name: getattr(args, "expected_" + name) for name,_ in roots}
    if any(n < 0 for n in expected.values()):
        parser.error("expected counts must be nonnegative")
    result = audit_batches(roots, args.output, expected)
    print(json.dumps(dict(batch_audit_complete=result["batch_audit_complete"], counts=result["counts"])))


if __name__ == "__main__":
    main()
