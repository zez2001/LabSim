"""Audit Size_v1 quotas and read normal ACT/DP batches without changing labels.

Optionally copy eligible complete episodes into the existing merged HDF5 index.
Diagnostics, initialization/service failures and unknown scene membership are
reported separately and cannot fill the 20-success / 20-failure quotas.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import h5py
import numpy as np
from omegaconf import OmegaConf

from demos.lab_cuvette_size_v1.frozen_scene import (CONDITION_GROUPS, file_sha,
    load_frozen, validate_frozen_scene)
from policy.dataset.lab_cuvette_size_v1_dataset import LabCuvetteSizeV1Dataset
from scripts.read_lab_cuvette_env_v1_data import describe, inspect
from utils.episode_selection import episode_matches_filter


def scalar(value):
    if isinstance(value, bytes):
        return value.decode("utf-8")
    if isinstance(value, np.generic):
        return value.item()
    return value


def episode_attributes(episode):
    return {str(key): scalar(value) for key, value in episode.attrs.items()
            if np.ndim(value) == 0}


def audit_episode(path, expected_sha):
    errors = []
    with h5py.File(path, "r") as episode:
        attrs = episode_attributes(episode)
        count = len(episode["actions"]) if "actions" in episode else 0
        if attrs.get("frozen_scene_sha256") != expected_sha:
            errors.append("missing_or_different_frozen_scene")
        if attrs.get("scene_mode") != "standard":
            errors.append("not_standard_scene")
        if attrs.get("condition_group") not in CONDITION_GROUPS:
            errors.append("unknown_condition_group")
        for key in ("asset_id", "source_slot_id", "target_seat_id", "control_config_sha256", "code_commit"):
            if attrs.get(key) in (None, "", "unknown", "unavailable"):
                errors.append("missing_" + key)
        if attrs.get("condition_group") == "deterministic_action_deviation":
            deviation = attrs.get("deterministic_action_deviation_json")
            if deviation is None and "episode_metadata_json" in episode:
                metadata = json.loads(episode["episode_metadata_json"][()].decode())
                deviation = metadata.get("deterministic_action_deviation")
            if not deviation:
                errors.append("missing_action_deviation_specification")
        if count:
            for camera in ("side_camera_rgb", "wrist_camera_rgb"):
                if camera not in episode or len(episode[camera]) != count:
                    errors.append("missing_or_misaligned_" + camera)
            required = ("timestamp", "next_timestamp", "joint_positions", "next_joint_positions",
                        "control_auxiliary/command_q", "actions_raw_json", "task_events_json", "phase")
            for key in required:
                if key not in episode or len(episode[key]) != count:
                    errors.append("missing_or_misaligned_" + key)
            if "timestamp" in episode and "next_timestamp" in episode:
                before, after = episode["timestamp"][:], episode["next_timestamp"][:]
                if not np.isfinite(before).all() or not np.isfinite(after).all() or np.any(after <= before):
                    errors.append("invalid_timestamps")
                if count > 1 and not np.allclose(after[:-1], before[1:], atol=1e-6, rtol=0):
                    errors.append("discontinuous_successor_time")
            if "control_auxiliary/command_q" in episode:
                command = episode["control_auxiliary/command_q"][:]
                if command.shape != (count, 9) or not np.array_equal(command[:, :8].astype(np.float32), episode["actions"][:]):
                    errors.append("legacy_action_mapping_mismatch")
        accepted = {}
        for selection in ("success", "failure", "all_valid"):
            match, reason = episode_matches_filter(episode.attrs, selection)
            accepted[selection] = bool(match and not errors and attrs.get("task_type") == "loading")
            accepted[selection + "_filter_reason"] = reason
    return dict(path=str(Path(path).resolve()), source_sha256=file_sha(path), transitions=count,
                labels=attrs, admission_errors=errors, **accepted)


def make_index(rows, destination):
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with h5py.File(destination, "x") as merged:
        merged.attrs.update(schema_version="labsim.Size_v1.index.v1", sample_filter="all_valid")
        for row in rows:
            if not (row["success"] or row["failure"]):
                continue
            with h5py.File(row["path"], "r") as source:
                target = merged.create_group(f"episode_{count:04d}")
                target.attrs.update(dict(source.attrs))
                for key in source:
                    source.copy(key, target)
            count += 1
    return count


def validate_reader(index, frozen_path, config_path, *, sample_filter="success", policy_type="act"):
    # Real normal reader verifies saved RGB and executed action alignment first.
    normal = inspect(index, sample_filter, policy_type, horizon=16,
                     n_obs_steps=1 if policy_type == "act" else 2)
    guarded = LabCuvetteSizeV1Dataset(describe(index), index, horizon=16,
        n_obs_steps=1 if policy_type == "act" else 2, policy_type=policy_type,
        sample_filter=sample_filter, val_ratio=.1, seed=42, split_group_keys=[],
        frozen_scene_path=frozen_path, scene_config_path=config_path, repository_root=ROOT)
    normal.update(train_episode_ids=guarded.train_episodes,
        validation_episode_ids=guarded.val_episodes, episode_split_disjoint=not bool(
            set(guarded.train_episodes) & set(guarded.val_episodes)),
        train_and_validation_same_frozen_standard_scene=True,
        scene_randomization_enabled=False, optimizer_or_training_executed=False)
    return normal


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("episodes_root", type=Path)
    parser.add_argument("--frozen-scene", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--index", type=Path, help="Create a new portable normal-reader HDF5 index; never overwrite")
    parser.add_argument("--read-index", type=Path, help="Read an existing index without creating one")
    parser.add_argument("--output-json", type=Path, required=True)
    args = parser.parse_args(argv)
    frozen = load_frozen(args.frozen_scene)
    validate_frozen_scene(OmegaConf.load(args.config), frozen, ROOT, purpose="collect")
    files = sorted(args.episodes_root.rglob("episode_*.h5"))
    rows, seen, duplicates = [], set(), []
    for path in files:
        row = audit_episode(path, frozen["frozen_scene_sha256"])
        identity = row["labels"].get("episode_id") or row["source_sha256"]
        if identity in seen:
            duplicates.append(str(path))
            continue
        seen.add(identity)
        rows.append(row)
    success = sum(row["success"] for row in rows)
    failure = sum(row["failure"] for row in rows)
    grouped = {group: dict(success=sum(row["success"] and row["labels"].get("condition_group") == group for row in rows),
        failure=sum(row["failure"] and row["labels"].get("condition_group") == group for row in rows)) for group in CONDITION_GROUPS}
    result = dict(schema="labsim.Size_v1.collection_audit.v1", frozen_scene_sha256=frozen["frozen_scene_sha256"],
        scene_mode="standard", scene_randomization_enabled=False, inspected_episode_count=len(rows),
        qualified_success_count=success, qualified_failure_count=failure,
        success_quota=20, failure_quota=20, success_missing=max(0, 20-success), failure_missing=max(0, 20-failure),
        condition_groups=grouped, archived_not_counted=len(rows)-success-failure,
        duplicate_episode_files_not_counted=duplicates, episodes=rows, reader_validation=[],
        labels_modified=False, random10_is_not_an_acceptance_requirement=True)
    if args.index:
        result["merged_episodes"] = make_index(rows, args.index)
    index = args.index or args.read_index
    if index:
        for selection, count in (("success", success), ("failure", failure)):
            if count:
                for policy in ("act", "dp"):
                    result["reader_validation"].append(validate_reader(index, args.frozen_scene,
                        args.config, sample_filter=selection, policy_type=policy))
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    with args.output_json.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    print(json.dumps({key: result[key] for key in ("qualified_success_count", "qualified_failure_count",
        "success_missing", "failure_missing", "archived_not_counted")}, ensure_ascii=False))
    return result


if __name__ == "__main__":
    main()
