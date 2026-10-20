"""Compact read-only V0_demo03 episode summary; no rescoring or label changes.

Accept dev/fixed/random roots together. Each invocation requires a NEW output
directory. Independent scores drive outcome/eligibility counts; controller and
writer labels remain separate, so missing evidence is not turned into success.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

import h5py
import yaml

from demos.lab_cuvette_demo03.analyze import json_safe, sha256, write_new

METADATA_FILES = ("result.json", "execution_summary.json", "independent_score.json",
                  "adjudication.json", "geometry_preflight.json", "config.yaml",
                  "scene_contract.json", "events.json", "runtime.json")


def read_json(path):
    return json.loads(path.read_text()) if path.is_file() else None


def artifact(path, hash_file=True):
    path = Path(path).resolve()
    before = path.stat()
    digest = sha256(path) if hash_file else None
    after = path.stat()
    unchanged = (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns)
    return dict(path=str(path), bytes=after.st_size, sha256=digest if unchanged else None,
                unchanged_during_hash=unchanged, hash_skipped=not hash_file)


def discover(roots):
    found, missing = set(), []
    for root in roots:
        root = Path(root).resolve()
        if not root.is_dir():
            missing.append(str(root))
            continue
        candidates = [root] + [p.parent for p in root.rglob("config.yaml")
                               if "source_snapshot" not in p.parts]
        candidates += [p.parent for name in ("independent_score.json", "execution_summary.json", "geometry_preflight.json")
                       for p in root.rglob(name) if "source_snapshot" not in p.parts]
        for folder in candidates:
            if any((folder/name).is_file() for name in METADATA_FILES):
                found.add(folder)
    return sorted(found), missing


def summarize_episode(folder):
    cfg_path = folder/"config.yaml"
    cfg = yaml.safe_load(cfg_path.read_text()) if cfg_path.is_file() else {}
    cfg = cfg or {}
    raw = read_json(folder/"result.json") or {}
    execution = read_json(folder/"execution_summary.json") or {}
    score = read_json(folder/"independent_score.json") or {}
    adjudication = read_json(folder/"adjudication.json") or {}
    preflight = read_json(folder/"geometry_preflight.json") or {}
    contract = read_json(folder/"scene_contract.json") or {}
    version = (score.get("scene_version") or raw.get("version") or cfg.get("version")
               or preflight.get("version") or contract.get("version"))
    if version != "V0_demo03":
        return None, dict(path=str(folder), reason="not an identified V0_demo03 episode", version=version)
    provenance_path = next((p for p in (folder/"provenance.json", folder.parent/"provenance.json")
                            if p.is_file()), None)
    provenance = read_json(provenance_path) if provenance_path else {}
    rows_path = folder/"physics_records.json"
    rows = read_json(rows_path) or []
    events = read_json(folder/"events.json") or []
    last = rows[-1] if rows else {}
    geometry = last.get("independent_geometry", {})
    phases = list(dict.fromkeys(r.get("phase") for r in rows if r.get("phase")))
    warnings, h5 = [], []
    for path in sorted((folder/"dataset").glob("episode_*.h5")):
        try:
            with h5py.File(path, "r") as stream:
                attrs = json_safe(dict(stream.attrs))
                frames = len(stream["timestamp"]) if "timestamp" in stream else None
            h5.append(dict(**artifact(path), frames=frames, attributes=attrs))
        except OSError as exc:
            h5.append(dict(path=str(path.resolve()), sha256=None, error=str(exc)))
            warnings.append("H5_UNREADABLE_OR_WRITER_STILL_ACTIVE")
    primary_h5 = h5[0] if len(h5) == 1 else {}
    if len(h5) > 1:
        warnings.append("MULTIPLE_H5_FILES_PER_TRIAL_NOT_SPLIT")
    attrs = primary_h5.get("attributes", {})
    advanced = bool(rows and float(last.get("t", 0)) > 0) or bool(primary_h5.get("frames"))
    executed = True if advanced else (None if raw.get("simulation_seconds", 0)
                                     or "H5_UNREADABLE_OR_WRITER_STILL_ACTIVE" in warnings else False)
    independent_valid = (score.get("schema") == "labsim.V0_demo03.independent.v1"
                         and score.get("historical_semantics_only") is False
                         and score.get("scene_mode") == "video_demo_adapted")
    workflow = score.get("workflow_success") if independent_valid and executed is True else None
    eligible = score.get("data_eligible") if independent_valid and executed is True else None
    outcome = ("NOT_EXECUTED" if executed is False else "SUCCESS" if workflow is True
               else "FAILED" if workflow is False else "UNSCORED_OR_INCOMPLETE")
    post = score.get("post_retreat_window")
    post_available = post.get("available") if post else None
    stable = score.get("stable_after_retreat") if post_available is True else None
    if post_available is not True and score.get("stable_after_retreat") is not None:
        warnings.append("POST_RETREAT_STABLE_LABEL_WITHOUT_AVAILABLE_WINDOW")
    peak = [(float(r["source_penetration_m"]), float(r["t"])) for r in rows
            if r.get("source_penetration_m") is not None and math.isfinite(float(r["source_penetration_m"]))]
    if any(r.get("source_penetration_m") is not None
           and not math.isfinite(float(r["source_penetration_m"])) for r in rows):
        warnings.append("NONFINITE_SOURCE_PENETRATION_RECORDS_RETAINED_AS_UNAVAILABLE")
    peak_pen, peak_time = max(peak, default=(None, None), key=lambda x: x[0])
    layout = cfg.get("randomization", {}).get("actual")
    video_paths = [p for p in (folder/"main.mp4", folder/"closeup.mp4") if p.is_file()]
    native_claim = score.get("native_pair_success", raw.get("native_pair_success"))
    calibration_claim = score.get("real_calibrated", raw.get("real_calibrated"))
    if native_claim is True or calibration_claim is True:
        warnings.append("FORBIDDEN_NATIVE_PAIR_OR_REAL_CALIBRATION_CLAIM")
    collector_eligible = adjudication.get("data_eligible")
    h5_eligible = attrs.get("data_eligible")
    end_to_end = bool(eligible is True and collector_eligible is True and h5_eligible is True
                     and attrs.get("success") is True and attrs.get("complete") is True)
    if eligible is True and not end_to_end:
        warnings.append("INDEPENDENT_ELIGIBILITY_AND_WRITER_LABELS_DISAGREE")
    metadata = {name: artifact(folder/name) for name in METADATA_FILES if (folder/name).is_file()}
    if provenance_path:
        metadata["provenance.json"] = artifact(provenance_path)
    command = provenance.get("command", [])
    seed = layout.get("seed") if isinstance(layout, dict) else raw.get("seed")
    if seed is None and "--seed" in command:
        seed = int(command[command.index("--seed")+1])
    result = dict(
        episode=str(folder), version=version, scene_mode=score.get("scene_mode", cfg.get("scene_mode")),
        record_kind="physical_episode" if executed is True else "static_preflight_or_incomplete_attempt",
        execution_state="EXECUTED" if executed is True else "NOT_EXECUTED" if executed is False else "UNKNOWN",
        outcome=outcome, controller_status=raw.get("status"), independent_status=score.get("status"),
        workflow_success=workflow, data_eligible=eligible, independent_and_writer_data_eligible=end_to_end,
        collector_data_eligible=collector_eligible, h5_data_eligible=h5_eligible,
        controller_workflow_success=raw.get("workflow_success"), native_pair_success=False, real_calibrated=False,
        scene_correspondence_accepted=score.get("scene_correspondence_accepted", contract.get("scene_correspondence", {}).get("accepted")),
        fail_phase=last.get("phase") if outcome in ("FAILED", "UNSCORED_OR_INCOMPLETE") else None,
        block_stage="STATIC_GEOMETRY_GATE" if executed is False and preflight.get("passed") is False else None,
        actual_phases=phases, controller_completed_phases=[e.get("previous") for e in events if e.get("next")],
        controller_stage_progress=raw.get("stage_progress"), independent_checks=score.get("checks"),
        source_slot_id=score.get("source_slot_id", attrs.get("source_slot_id")),
        configured_source_slot_id=cfg.get("rack", {}).get("selected_slot_id", preflight.get("source_slot_id")),
        target_seat_id=score.get("target_seat_id", attrs.get("target_seat_id")), seed=seed,
        configured_target_seat_id=cfg.get("adapter", {}).get("selected_target_seat_id", preflight.get("target_seat_id")),
        layout_kind="random_recorded" if isinstance(layout, dict) else "fixed_or_not_recorded",
        layout_perturbation=layout, rack_origin_m=cfg.get("rack", {}).get("origin_m"),
        instrument_origin_m=cfg.get("scene", {}).get("instrument_xyz_m"),
        max_observed_source_penetration_m=peak_pen, max_observed_source_penetration_time_s=peak_time,
        penetration_gate_m=cfg.get("demo_release", {}).get("penetration_m"),
        final_depth_m=geometry.get("depth_m", last.get("depth_m")),
        final_bottom_signed_gap_m=geometry.get("bottom_signed_gap_m"),
        post_retreat_available=post_available, stable_after_retreat=stable,
        post_retreat_duration_s=post.get("duration_s") if post_available is True else None,
        post_retreat_position_drift_m=post.get("position_drift_m") if post_available is True else None,
        post_retreat_rotation_change_deg=post.get("rotation_change_deg") if post_available is True else None,
        actual_retreat_clearance_m=score.get("actual_retreat_clearance_m") if post_available is True else None,
        terminal_window=score.get("terminal_window"), simulation_seconds=raw.get("simulation_seconds", last.get("t")),
        wall_seconds=raw.get("wall_seconds"), frames=primary_h5.get("frames"),
        physics_quality_flags=list(dict.fromkeys(raw.get("physics_quality_flags", [])+score.get("physics_quality_flags", []))),
        main_video_path=str((folder/"main.mp4").resolve()) if (folder/"main.mp4").is_file() else None,
        raw_h5_path=primary_h5.get("path"), raw_h5_sha256=primary_h5.get("sha256"),
        video_files=[artifact(p, hash_file=bool(raw or score)) for p in video_paths], raw_h5_files=h5,
        physics_records=artifact(rows_path) if rows_path.is_file() else None,
        metadata_files=metadata, git_commit=provenance.get("git_commit"),
        working_tree_dirty=provenance.get("dirty"), command=command,
        preflight_passed=preflight.get("passed"), provenance_source_hashes=provenance.get("sha256"),
        execution_summary=execution, warnings=warnings)
    return json_safe(result), None


def summarize(roots, output):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    folders, missing = discover(roots)
    episodes, skipped = [], []
    for folder in folders:
        result, exclusion = summarize_episode(folder)
        if result is not None:
            episodes.append(result)
        else:
            skipped.append(exclusion)
    counts = dict(episodes=len(episodes), executed=sum(e["execution_state"] == "EXECUTED" for e in episodes),
                  not_executed=sum(e["execution_state"] == "NOT_EXECUTED" for e in episodes),
                  unknown_execution=sum(e["execution_state"] == "UNKNOWN" for e in episodes),
                  independent_workflow_success=sum(e["workflow_success"] is True for e in episodes),
                  independent_workflow_failure=sum(e["workflow_success"] is False for e in episodes),
                  independent_workflow_unscored=sum(e["workflow_success"] is None and e["execution_state"] != "NOT_EXECUTED" for e in episodes),
                  independent_data_eligible=sum(e["data_eligible"] is True for e in episodes),
                  independent_and_writer_data_eligible=sum(e["independent_and_writer_data_eligible"] for e in episodes))
    result = dict(schema="labsim.V0_demo03.episode_summary.v1", roots=[str(Path(r).resolve()) for r in roots],
                  counts=counts, episodes=episodes, missing_roots=missing, skipped=skipped,
                  notes=["Independent workflow/data labels drive counts; raw controller labels remain separate.",
                         "Unavailable observations remain null; terminal_window never substitutes for post-retreat observation.",
                         "Empty CSV cells represent unavailable values; JSON is the canonical null representation.",
                         "Penetration is the maximum observed source-geometry sample, not a strict global cooked-shape error bound.",
                         "Writer eligibility is a label cross-check; this summary does not read a training batch. Use data_check for array/loader acceptance.",
                         "Videos and raw H5 are referenced and hashed, not copied. No source record or success label is edited."])
    write_new(output/"episodes.json", result)
    fields = [key for key, value in (episodes[0] if episodes else {}).items()
              if key not in ("raw_h5_files", "video_files", "metadata_files", "provenance_source_hashes", "execution_summary")]
    with (output/"episodes.csv").open("x", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for episode in episodes:
            writer.writerow({k: json.dumps(episode[k], ensure_ascii=False) if isinstance(episode[k], (dict, list))
                             else episode[k] for k in fields})
    write_new(output/"manifest.json", dict(schema="labsim.V0_demo03.summary_manifest.v1",
        script_path=str(Path(__file__).resolve()), script_sha256=sha256(__file__),
        files=[artifact(output/name) for name in ("episodes.json", "episodes.csv")], source_records_modified=False))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--roots", type=Path, nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True, help="new directory; existing output is never overwritten")
    args = parser.parse_args()
    result = summarize(args.roots, args.output)
    print(json.dumps(result["counts"], ensure_ascii=False))


if __name__ == "__main__":
    main()
