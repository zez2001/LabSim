"""Read-only V0_demo02 index/filter and existing-loader acceptance check.

The index contains external links to immutable raw episodes. It never copies or
rewrites their success labels. A usable simulated-training episode must pass the
new independent score AND its own completed-success metadata. No successful
episode means no training batch; loader rejection is recorded as such.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import h5py
import numpy as np

from demos.lab_cuvette_demo02.analyze import CHECK_NAMES, PHASES, json_safe, load_json, sha256, write_new

ACTION_SEMANTICS = "absolute_7_arm_rad_and_symmetric_finger_metre"
OBSERVATION_ALIGNMENT = "obs_before_action; next_state_after_explicit_substeps"


def decode(value):
    return value.decode() if isinstance(value, bytes) else value


def metadata_checks(attrs, score):
    """Public, inexpensive gate; real array and timestamp checks follow."""
    attrs = {k: decode(v) for k, v in attrs.items()}
    return dict(
        new_scene_only=attrs.get("scene_version") == "V0_demo02",
        new_task_only=attrs.get("task") == "lab_cuvette_loading_V0_demo02",
        raw_complete=bool(attrs.get("complete", False)),
        raw_success=bool(attrs.get("success", False)),
        raw_data_eligible=bool(attrs.get("data_eligible", False)),
        raw_full_task_eligible=bool(attrs.get("full_task_eligible", False)),
        raw_workflow_success=bool(attrs.get("workflow_success", False)),
        raw_scene_correspondence_accepted=bool(attrs.get("scene_correspondence_accepted", False)),
        independently_data_eligible=score.get("data_eligible") is True,
        independently_workflow_success=score.get("workflow_success") is True,
        scene_correspondence_accepted=score.get("scene_correspondence_accepted") is True,
        score_version=score.get("schema") == "labsim.V0_demo02.independent.v2",
        all_required_independent_checks=(set(score.get("checks", {})) == set(CHECK_NAMES)
                                        and all(v is True for v in score.get("checks", {}).values())),
        not_historical_rescore=score.get("historical_semantics_only") is False,
        source_slot_bound=bool(attrs.get("source_slot_id")) and
                          attrs.get("source_slot_id") == score.get("source_slot_id"),
        correct_internal_target=bool(attrs.get("target_is_internal_chamber", False)) and
                                bool(attrs.get("target_seat_id")) and
                                attrs.get("target_seat_id") == score.get("target_seat_id"),
        asset_version_bound=bool(attrs.get("asset_manifest_sha256")) and
                            attrs.get("asset_manifest_sha256") == score.get("asset_manifest_sha256"),
        action_semantics=attrs.get("action_semantics") == ACTION_SEMANTICS,
        observation_alignment=attrs.get("observation_alignment") == OBSERVATION_ALIGNMENT,
        declared_simulation_scope=attrs.get("data_scope") == "lab_cuvette_loading_V0_demo02_simulation",
    )


def inspect_episode(path, score_path):
    path, score_path = Path(path).resolve(), Path(score_path).resolve()
    score = load_json(score_path)
    initial_hash = sha256(path)
    with h5py.File(path, "r") as h:
        attrs = {k: decode(v) for k, v in h.attrs.items()}
        checks = metadata_checks(attrs, score)
        checks["score_same_episode"] = bool(score.get("source_episode") and
            Path(score["source_episode"]).resolve() == path.parent.parent)
        checks["score_matches_saved_h5_adjudication"] = (
            attrs.get("independent_score_sha256") == sha256(score_path))
        required = ("camera_1_rgb", "camera_2_rgb", "agent_pose", "actions", "next_agent_pose",
                    "joint_positions", "timestamp", "next_timestamp", "phase_code",
                    "privileged/object_pose", "privileged/next_object_pose")
        missing = [k for k in required if k not in h]
        checks["required_arrays_present"] = not missing
        diagnostics = {}
        if not missing:
            n = len(h["timestamp"])
            shapes = {k: list(h[k].shape) for k in required}
            checks["nonempty"] = n > 0
            checks["all_transition_lengths_equal"] = all(len(h[k]) == n for k in required)
            checks["action_and_agent_dimensions"] = h["actions"].shape == h["agent_pose"].shape == (n, 8)
            checks["robot_nine_positions"] = h["joint_positions"].shape == (n, 9)
            checks["dual_rgb_uint8_CHW_256"] = all(h[k].shape == (n, 3, 256, 256)
                                                    and h[k].dtype == np.uint8
                                                    for k in ("camera_1_rgb", "camera_2_rgb"))
            hz = attrs.get("control_hz")
            t, next_t = h["timestamp"][:], h["next_timestamp"][:]
            hz_valid = hz is not None and np.isfinite(hz) and float(hz) > 0
            checks["timestamp_action_hold"] = bool(hz_valid and n and np.isfinite(t).all()
                and np.isfinite(next_t).all() and np.all(np.diff(t) > 0)
                and np.allclose(next_t-t, 1/float(hz), atol=1e-7, rtol=0))
            checks["transition_timestamp_continuity"] = bool(n and np.allclose(next_t[:-1], t[1:], atol=1e-7, rtol=0))
            checks["next_robot_state_matches_next_observation"] = bool(n and np.allclose(
                h["next_agent_pose"][:-1], h["agent_pose"][1:], atol=1e-6, rtol=0))
            checks["next_object_state_matches_next_observation"] = bool(n and np.allclose(
                h["privileged/next_object_pose"][:-1], h["privileged/object_pose"][1:], atol=1e-7, rtol=0))
            checks["finite_actions_and_agent"] = bool(np.isfinite(h["actions"][:]).all()
                                                        and np.isfinite(h["agent_pose"][:]).all())
            try:
                names = json.loads(attrs.get("phase_names_json", "[]"))
                phase = h["phase_code"][:]
                checks["phase_map_and_codes"] = (names == list(PHASES) and n > 0
                    and int(phase.min()) >= 0 and int(phase.max()) < len(names))
            except (TypeError, ValueError):
                checks["phase_map_and_codes"] = False
            diagnostics = dict(frames=n, shapes=shapes,
                max_action_hold_error_s=float(np.max(abs(next_t-t-1/float(hz)))) if n and hz_valid else None,
                rgb_alignment_scope="writer contract and timestamp continuity checked; image content timing not independently measured")
        # Values of real_calibrated and native_pair_success remain separate facts;
        # simulated-training eligibility does not certify hardware or real CAD fit.
        result = dict(episode=str(path), original_sha256=initial_hash,
                      independent_score=str(score_path), independent_score_sha256=sha256(score_path),
                      eligible=all(v is True for v in checks.values()), checks=checks,
                      rejection_reasons=[k for k, value in checks.items() if value is not True],
                      missing_arrays=missing, attributes=attrs, diagnostics=diagnostics,
                      real_calibrated=score.get("real_calibrated"),
                      native_pair_success=score.get("native_pair_success"))
    result["raw_unchanged_after_read"] = sha256(path) == initial_hash
    return json_safe(result)


def loader_check(index):
    shape_meta = {"obs": {
        "camera_1_rgb": {"type": "rgb", "shape": [3, 256, 256]},
        "camera_2_rgb": {"type": "rgb", "shape": [3, 256, 256]},
        "agent_pose": {"type": "low_dim", "shape": [8]}}, "action": {"shape": [8]}}
    try:
        from policy.dataset.minimal_pick_dataset import MinimalPickDataset
    except ImportError as exc:
        return dict(executed=False, training_batch_executed=False,
                    reason="existing loader import unavailable", error=str(exc))
    try:
        dataset = MinimalPickDataset(shape_meta, str(index), horizon=16,
                                     n_obs_steps=1, val_ratio=0, policy_type="act")
    except ValueError as exc:
        return dict(executed=True, training_batch_executed=False,
                    status="rejected_no_eligible_complete_success" if
                    "no complete successful episodes" in str(exc) else "loader_error",
                    error=str(exc), original_loader="policy.dataset.minimal_pick_dataset.MinimalPickDataset")
    batch = dataset.collate_fn([dataset[0]])
    return dict(executed=True, training_batch_executed=True, status="read_one_batch",
                episodes=dataset.episode_ids, dataset_samples=len(dataset),
                obs_shapes={k: list(v.shape) for k, v in batch["obs"].items()},
                action_shape=list(batch["action"].shape), is_pad_shape=list(batch["is_pad"].shape),
                finite_action=bool(batch["action"].isfinite().all()),
                scope="one read-only batch; no optimizer, training run, or synthetic trajectory")


def build_index(candidates, destination):
    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=False)
    evaluations = [inspect_episode(c["episode"], c["score"]) for c in candidates]
    index = destination/"episode_data.hdf5"
    selected = []
    with h5py.File(index, "x") as h:
        h.attrs.update(schema="labsim.V0_demo02.filtered_index.v1",
                       scope="lab_cuvette_loading_V0_demo02_simulation",
                       raw_files_rewritten=False)
        for audit in evaluations:
            if not audit["eligible"]:
                continue
            name = f"episode_{len(selected):04d}"
            with h5py.File(audit["episode"], "r") as raw:
                group = h.create_group(name)
                group.attrs.update(dict(raw.attrs))
                # Individual root objects may be groups (privileged/diagnostic).
                # External links retain all original datasets and attributes.
                for key in raw:
                    group[key] = h5py.ExternalLink(audit["episode"], "/"+key)
                group.attrs["independent_score_sha256"] = audit["independent_score_sha256"]
            selected.append(dict(index_group=name, episode=audit["episode"],
                                 source_sha256=audit["original_sha256"]))
    loaded = loader_check(index)
    result = dict(schema="labsim.V0_demo02.data_audit.v1", candidates=evaluations,
                  selected=selected, eligible_count=len(selected), loader=loaded,
                  index_path=str(index), raw_files_rewritten=False,
                  index_portability="external links require original raw H5 paths; share report without claiming raw data included",
                  training_batch_status="executed" if loaded.get("training_batch_executed") else "not_executed",
                  eligibility_scope="complete correct-scene physical workflow in simulation; real calibration is a separate flag")
    write_new(destination/"result.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=Path,
                        help='JSON list of {"episode": "...h5", "score": "...json"}; empty list is valid')
    parser.add_argument("--episode", type=Path)
    parser.add_argument("--score", type=Path)
    parser.add_argument("--output", type=Path, required=True,
                        help="new directory; prior audits cannot be overwritten")
    args = parser.parse_args()
    if args.candidates and (args.episode or args.score):
        parser.error("use --candidates or --episode/--score, not both")
    if bool(args.episode) != bool(args.score):
        parser.error("--episode and --score must be supplied together")
    candidates = load_json(args.candidates) if args.candidates else (
        [dict(episode=str(args.episode), score=str(args.score))] if args.episode else [])
    result = build_index(candidates, args.output)
    print(json.dumps(dict(eligible_count=result["eligible_count"], loader=result["loader"]), ensure_ascii=False))


if __name__ == "__main__":
    main()
