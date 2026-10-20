"""V0_demo03 video_demo_adapted physical adjudication, no label rewriting.

This module imports no Isaac code and never edits an episode or an earlier score.
``independent_geometry`` fields must come from an offline source-mesh/target check,
not controller progress flags. Missing evidence produces unknown, not a zero or a
success. The scene contract must bind the checked source slot and internal seat.
The adapted mode does not certify OEM pairing or real calibration; both labels
remain false even when this explicitly scoped simulated workflow succeeds.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import yaml
from scipy.spatial.transform import Rotation

PHASES = ("RESET", "APPROACH_SOURCE", "GRASP", "EXTRACT", "TRANSPORT",
          "ALIGN", "INSERT", "SUPPORT_TRANSFER", "OPEN", "RETREAT", "VERIFY")
CHECK_NAMES = (
    "scene_and_geometry_contract", "asset_and_slot_bindings", "initial_source_slot_and_support",
    "all_workflow_stages_in_order", "source_slot_actually_cleared", "correct_internal_seat_loaded",
    "supported_before_open", "both_fingers_open_and_detached", "actual_retreat_clearance",
    "post_retreat_stable_3s", "measured_penetration_within_original_gate",
    "no_forbidden_robot_environment_contact", "finite_native_signals",
    "no_forbidden_kinematic_or_attachment", "physics_samples_contiguous")


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def json_safe(value):
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, np.ndarray)):
        return [json_safe(v) for v in value]
    if isinstance(value, np.generic):
        return json_safe(value.item())
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def write_new(path, value):
    """Do not replace raw records, previous analyses, or another invocation."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(json_safe(value), stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def event_time(events, phase):
    values = [float(e["t"]) for e in events if e.get("next") == phase]
    return min(values) if values else None


def unavailable(reason):
    return dict(available=False, status="unavailable", reason=reason,
                duration_s=None, position_drift_m=None, rotation_change_deg=None,
                stable=None)


def summarize_window(rows, start, stop, label):
    selected = [r for r in rows if start - 1e-8 <= float(r["t"]) <= stop + 1e-8]
    if not selected:
        return unavailable("no recorded physics states in requested window")
    t = np.asarray([r["t"] for r in selected], dtype=float)
    p = np.asarray([r["position"] for r in selected], dtype=float)
    q = np.asarray([r["quaternion"] for r in selected], dtype=float)
    if not np.isfinite(p).all() or not np.isfinite(q).all() or np.any(np.linalg.norm(q, axis=1) == 0):
        return dict(available=True, status="invalid", label=label,
                    duration_s=float(t[-1] - t[0]), stable=False,
                    reason="non-finite position/orientation or zero quaternion")
    q = q / np.linalg.norm(q, axis=1)[:, None]
    drift = np.linalg.norm(p - p[0], axis=1)
    angle = np.degrees(2 * np.arccos(np.clip(abs(q @ q[0]), 0, 1)))

    def extreme(key, maximum=True, component=None, norm=False):
        if any(key not in r for r in selected):
            return None
        values = np.asarray([r[key] for r in selected], dtype=float)
        if component is not None:
            values = values[:, component]
        if norm:
            values = np.linalg.norm(values, axis=-1)
        if not np.isfinite(values).all():
            return None
        return float(values.max() if maximum else values.min())

    gap = [abs(float(r["independent_geometry"]["bottom_signed_gap_m"])) for r in selected
           if r.get("independent_geometry", {}).get("bottom_signed_gap_m") is not None]
    return dict(available=True, status="observed", label=label,
                start_s=float(t[0]), end_s=float(t[-1]), duration_s=float(t[-1] - t[0]),
                recorded_samples=len(selected),
                max_sample_interval_s=float(np.diff(t).max()) if len(t) > 1 else None,
                position_drift_m=float(drift.max()), rotation_change_deg=float(angle.max()),
                max_tilt_deg=extreme("tilt_deg"),
                max_penetration_m=extreme("source_penetration_m"),
                max_abs_target_bottom_gap_m=max(gap) if len(gap) == len(selected) else None,
                min_support_Fz_N=extreme("target_support_force_vector_N", maximum=False, component=2),
                min_environment_support_Fz_N=extreme("support_force_vector_N", maximum=False, component=2),
                max_native_speed_m_s=extreme("linear_velocity", norm=True),
                max_native_angular_rad_s=extreme("angular_velocity", norm=True),
                max_fd_COM_speed_m_s=extreme("fd_com_velocity", norm=True),
                max_fd_angular_rad_s=extreme("fd_angular_velocity", norm=True),
                stable=None)


def quiet(window, spec, required_seconds):
    if not window.get("available"):
        return None
    keys = ("duration_s", "position_drift_m", "rotation_change_deg",
            "max_penetration_m", "max_tilt_deg")
    if any(window.get(k) is None for k in keys):
        return None
    if window["duration_s"] < required_seconds - 1e-6:
        return None
    if spec.get("physics_dt_s") is not None and (
        window.get("max_sample_interval_s") is None or
        window["max_sample_interval_s"] > spec["physics_dt_s"]*1.5+1e-8):
        return None
    return bool(window["position_drift_m"] <= spec["position_drift_m"]
                and window["rotation_change_deg"] <= spec["orientation_change_deg"]
                and window["max_penetration_m"] <= spec["penetration_m"]
                and window["max_tilt_deg"] <= spec["max_tilt_deg"])


def measured_windows(rows, events, spec):
    if not rows:
        return dict(post_retreat_window=unavailable("no physics trajectory"),
                    terminal_window=unavailable("no physics trajectory"),
                    pre_open_window=unavailable("no physics trajectory"))
    stop = float(rows[-1]["t"])
    observe = float(spec["observe_s"])
    terminal = summarize_window(rows, max(float(rows[0]["t"]), stop-observe), stop,
                                "terminal_window; does not imply retreat")
    opened, verify = event_time(events, "OPEN"), event_time(events, "VERIFY")
    pre = (summarize_window(rows, opened-spec["support_window_s"], opened, "pre_open_window")
           if opened is not None else unavailable("OPEN was not entered"))
    # Starting RETREAT is not evidence that retreat finished. VERIFY marks the
    # completed-retreat boundary; clearance is checked separately for demo03.
    if verify is None:
        post = unavailable("VERIFY/completed retreat was not recorded")
    else:
        post = summarize_window(rows, verify, stop, "post_retreat_window")
        stable = quiet(post, spec, observe)
        if stable is True:
            support = post.get("min_support_Fz_N")
            stable = (support >= spec["min_support_N"]) if support is not None else None
        post["stable"] = stable
        post["required_duration_s"] = observe
    return dict(post_retreat_window=post, terminal_window=terminal, pre_open_window=pre)


def velocity_audit(rows):
    """Same-step raw channels remain intact; backward differences use actual dt."""
    if len(rows) < 2:
        return dict(available=False, reason="less than two recorded states")
    t = np.asarray([r["t"] for r in rows], dtype=float)
    dt = np.diff(t)
    if not np.isfinite(dt).all() or np.any(dt <= 0):
        return dict(available=False, reason="timestamps not strictly increasing")
    if any(k not in r for r in rows for k in ("com_world_m", "linear_velocity", "angular_velocity")):
        return dict(available=False, reason="native velocity or world COM is absent")
    com = np.asarray([r["com_world_m"] for r in rows], dtype=float).reshape(-1, 3)
    q = np.asarray([r["quaternion"] for r in rows], dtype=float)
    native_v = np.asarray([r["linear_velocity"] for r in rows], dtype=float)
    native_w = np.asarray([r["angular_velocity"] for r in rows], dtype=float)
    finite = bool(np.isfinite(com).all() and np.isfinite(q).all()
                  and np.isfinite(native_v).all() and np.isfinite(native_w).all())
    if not finite or np.any(np.linalg.norm(q, axis=1) == 0):
        return dict(available=True, finite=False)
    rot = Rotation.from_quat(q[:, [1, 2, 3, 0]])
    fd = np.diff(com, axis=0) / dt[:, None]
    fd_w = (rot[1:] * rot[:-1].inv()).as_rotvec() / dt[:, None]
    return dict(available=True, finite=True, first_difference_sample_available=False,
                native_linear_frame="world COM; m/s", native_angular_frame="world; rad/s",
                usd_angular_raw_unit="degree/s; retained, not replaced",
                difference="backward COM difference and world rotation vector at same-step endpoints",
                max_linear_disagreement_m_s=float(np.linalg.norm(native_v[1:]-fd, axis=1).max()),
                max_angular_disagreement_rad_s=float(np.linalg.norm(native_w[1:]-fd_w, axis=1).max()),
                mismatch_is_warning_only=True)


def analyze(folder, contract=None, historical=False):
    folder = Path(folder).resolve()
    rows = load_json(folder/"physics_records.json")
    events = load_json(folder/"events.json")
    raw = load_json(folder/"result.json")
    cfg = yaml.safe_load((folder/"config.yaml").read_text())
    spec = dict(cfg["demo_release"])
    spec["physics_dt_s"] = 1/float(cfg["physics"]["hz"])
    windows = measured_windows(rows, events, spec)
    velocity = velocity_audit(rows)
    original_path = folder/"independent_score.json"
    original = load_json(original_path) if original_path.exists() else None
    result = dict(schema="labsim.V0_demo03.independent.v1", source_episode=str(folder),
                  historical_semantics_only=bool(historical),
                  physics_records_sha256=sha256(folder/"physics_records.json"),
                  events_sha256=sha256(folder/"events.json"),
                  record_count=len(rows), trajectory_end_time_s=rows[-1]["t"] if rows else None,
                  simulation_seconds=raw.get("simulation_seconds"), wall_seconds=raw.get("wall_seconds"),
                  original_controller_status=raw.get("status"),
                  original_controller_result_sha256=sha256(folder/"result.json"),
                  original_independent_score_sha256=sha256(original_path) if original else None,
                  original_independent_score=original, original_records_unchanged=True,
                  **windows, velocity_audit=velocity)
    post = windows["post_retreat_window"]
    result["stable_after_retreat"] = post.get("stable")
    result["actual_retreat_clearance_m"] = None
    result["physics_quality_flags"] = list(dict.fromkeys(raw.get("physics_quality_flags", [])
                                                       + (original or {}).get("physics_quality_flags", [])))
    result["physics_quality_flags"].extend([
        "VIDEO_DEMO_ADAPTED_SCENE_NOT_OEM_PAIR_VALIDATION",
        "ROBOT_VESSEL_MATERIAL_DYNAMICS_NOT_REAL_CALIBRATED"])
    if velocity.get("finite") and (velocity["max_linear_disagreement_m_s"] > .001
                                   or velocity["max_angular_disagreement_rad_s"] > .05):
        result["physics_quality_flags"].append("NATIVE_VS_POSE_VELOCITY_MISMATCH_RETAINED")
    result["physics_quality_flags"] = list(dict.fromkeys(result["physics_quality_flags"]))
    if historical:
        result.update(scene_correspondence_accepted=False, workflow_success=None,
                      historical_workflow_success=(original or {}).get("workflow_success"),
                      native_pair_success=False, real_calibrated=False, data_eligible=False,
                      data_scope="historical_demo01_only; not a demo03 training episode",
                      semantic_changes=[
                          "final_window renamed terminal_window; a terminal window is not a post-retreat observation",
                          "post_retreat_window unavailable and stable_after_retreat null if VERIFY never entered",
                          "last TCP-to-object-top separation is not an observed actual retreat clearance",
                          "old independent_score.json and raw H5 are not changed; physical pass/fail is not relabelled"])
        if rows and rows[-1].get("actual_tcp") is not None:
            result["terminal_tcp_world_m"] = rows[-1]["actual_tcp"]
        result["status"] = "HISTORICAL_SEMANTICS_AUDITED"
        return json_safe(result)

    contract = contract or {}
    correspondence = contract.get("scene_correspondence", {})
    source = contract.get("source_slot", {})
    target = contract.get("target_seat", {})
    geometry = [r.get("independent_geometry", {}) for r in rows]
    last = rows[-1] if rows else {}
    measured = geometry[-1] if geometry else {}
    asset_hash = contract.get("asset_manifest_sha256")
    contract_ok = bool(contract.get("version") == "V0_demo03"
                       and contract.get("scene_mode") == "video_demo_adapted" and asset_hash
                       and correspondence.get("accepted") is True
                       and correspondence.get("evidence")
                       and source.get("id") and target.get("id")
                       and target.get("inside_sample_chamber") is True
                       and contract.get("geometry_audit", {}).get("accepted") is True)
    ids_match = bool(source.get("id") and target.get("id") and geometry
                    and all(g.get("source_slot_id") == source.get("id")
                                   and g.get("target_seat_id") == target.get("id")
                                   for g in geometry))

    def finite(key, row=measured):
        value = row.get(key)
        return value is not None and bool(np.isfinite(np.asarray(value, dtype=float)).all())

    ordered = [event_time(events, name) for name in PHASES[1:]]
    ordered_ok = all(t is not None for t in ordered) and ordered == sorted(ordered)
    cleared = any(g.get("source_clearance_m") is not None
                  and g["source_clearance_m"] >= source.get("required_clearance_m", .010)
                  and np.all(np.asarray(r.get("finger_force_N", [0, 0])) > .02)
                  for r, g in zip(rows, geometry))
    target_loaded = (finite("depth_m") and finite("bottom_signed_gap_m")
                     and measured.get("inside_checked_target_void") is True
                     and measured["depth_m"] >= target.get("minimum_depth_m", float("inf"))
                     and abs(measured["bottom_signed_gap_m"]) <= spec["bottom_distance_m"])
    verify = event_time(events, "VERIFY")
    reset_rows = [r for r in rows if r.get("phase") == "RESET"]
    if reset_rows:
        reset_end = float(reset_rows[-1]["t"])
        initial_source_window = summarize_window(rows, reset_end-3., reset_end, "initial_source_window")
        initial_rows = [r for r in reset_rows if r["t"] >= reset_end-3.-1e-8]
        initial_geometry_valid = bool(initial_rows and all(
            r.get("independent_geometry", {}).get("source_supported_inside_designated_slot") is True
            for r in initial_rows))
        initial_force = initial_source_window.get("min_environment_support_Fz_N")
        initial_supported = bool(initial_geometry_valid and quiet(initial_source_window, spec, 3.) is True
                                 and initial_force is not None and initial_force >= spec["min_support_N"])
    else:
        initial_source_window = unavailable("RESET was not recorded")
        initial_supported = False
    result["initial_source_window"] = initial_source_window
    clearance = [g.get("robot_to_vessel_clearance_m") for r, g in zip(rows, geometry)
                 if verify is not None and r["t"] >= verify-1e-8]
    clearance_valid = bool(clearance and all(x is not None and np.isfinite(x) for x in clearance))
    if clearance_valid:
        result["actual_retreat_clearance_m"] = min(clearance)
    retreat_verified = bool(clearance_valid and min(clearance) >=
                            contract.get("minimum_retreat_clearance_m", .04))
    if verify is not None and not retreat_verified:
        result["controller_verify_window"] = post
        post = unavailable("controller entered VERIFY but independent robot-to-vessel clearance is missing or insufficient")
        result["post_retreat_window"] = post
        result["stable_after_retreat"] = None
    detached = bool(verify is not None and rows and all(
        len(r.get("joints", [])) >= 9 and np.all(np.asarray(r["joints"])[7:] > .025)
        and np.all(np.asarray(r.get("finger_force_N", [np.inf]*2)) < .01)
        for r in rows if r["t"] >= verify-1e-8))
    pre = windows["pre_open_window"]
    handoff = bool(quiet(pre, spec, spec["support_window_s"]) is True
                   and pre.get("min_support_Fz_N") is not None
                   and pre["min_support_Fz_N"] >= spec["min_support_N"]
                   and pre.get("max_abs_target_bottom_gap_m") is not None
                   and pre["max_abs_target_bottom_gap_m"] <= spec["bottom_distance_m"])
    pen_values = [r.get("source_penetration_m") for r in rows]
    penetration_valid = bool(pen_values and all(v is not None and np.isfinite(v)
                                               and v <= spec["penetration_m"] for v in pen_values))
    intervals = np.diff([r["t"] for r in rows])
    contiguous = bool(len(intervals) and np.isfinite(intervals).all()
                      and np.allclose(intervals, spec["physics_dt_s"], atol=1e-8, rtol=0))
    checks = dict(scene_and_geometry_contract=contract_ok, asset_and_slot_bindings=ids_match,
                  initial_source_slot_and_support=initial_supported,
                  all_workflow_stages_in_order=bool(ordered_ok), source_slot_actually_cleared=bool(cleared),
                  correct_internal_seat_loaded=bool(target_loaded), supported_before_open=handoff,
                  both_fingers_open_and_detached=detached,
                  actual_retreat_clearance=retreat_verified,
                  post_retreat_stable_3s=post.get("stable"),
                  measured_penetration_within_original_gate=penetration_valid,
                  no_forbidden_robot_environment_contact=bool(geometry and all(
                      g.get("forbidden_robot_environment_contact") is False for g in geometry)),
                  finite_native_signals=velocity.get("finite") is True,
                  physics_samples_contiguous=contiguous,
                  no_forbidden_kinematic_or_attachment=contract.get("runtime_integrity", {}).get("verified") is True)
    assert set(checks) == set(CHECK_NAMES)
    success = all(value is True for value in checks.values())
    result.update(status="WORKFLOW_SUCCESS" if success else "EVIDENCE_INCOMPLETE_OR_FAILED",
                  scene_correspondence_accepted=contract_ok, checks=checks,
                  workflow_success=success,
                  native_pair_success=False,
                  real_calibrated=False,
                  data_eligible=success, data_scope="lab_cuvette_loading_V0_demo03_video_demo_adapted",
                  scene_version="V0_demo03", scene_mode="video_demo_adapted", asset_manifest_sha256=asset_hash,
                  source_slot_id=source.get("id"), target_seat_id=target.get("id"))
    return json_safe(result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("episode", type=Path)
    parser.add_argument("--contract", type=Path)
    parser.add_argument("--historical", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    contract = load_json(args.contract) if args.contract else None
    result = analyze(args.episode, contract=contract, historical=args.historical)
    if args.contract:
        result["scene_contract_sha256"] = sha256(args.contract)
    write_new(args.output, result)
    print(json.dumps({k: result.get(k) for k in ("status", "workflow_success", "data_eligible")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
