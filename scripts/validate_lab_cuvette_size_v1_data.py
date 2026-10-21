"""Audit Size_v1 quotas and read normal ACT/DP batches without changing labels.

Default indexes contain relative links to self-contained episode HDF5 files in
the same collection tree; --copy-data explicitly creates a self-contained copy.
Diagnostics, initialization/service failures and unknown scene membership are
reported separately and cannot fill the 20-success / 20-failure quotas.
"""
from __future__ import annotations

import argparse
import json
import os
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
from scripts.actual_episode_inspect import scan_links
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
        policy = str(attrs.get("policy_id", "")).lower()
        reason = str(attrs.get("termination_reason", "")).upper()
        failure = str(attrs.get("failure_type", "")).upper()
        diagnostic_termination = (reason in {"PREVIEW_COMPLETE", "DIAGNOSTIC_ONLY", "REPLAY_SOURCE_EXHAUSTED"}
            or "BUDGET" in reason or reason.startswith("REPLAY_"))
        if "preview" in policy or diagnostic_termination or failure == "DIAGNOSTIC_ONLY":
            errors.append("preview_or_short_budget_interface_diagnostic_not_task_quota")
        if attrs.get("task_type") != "loading":
            errors.append("not_full_loading_task")
        if attrs.get("task_success") is False and failure in {"", "UNKNOWN", "NONE", "UNAVAILABLE"}:
            errors.append("missing_physical_task_failure_type")
        if attrs.get("frozen_scene_sha256") != expected_sha:
            errors.append("missing_or_different_frozen_scene")
        if attrs.get("scene_mode") != "standard":
            errors.append("not_standard_scene")
        if attrs.get("condition_group") not in CONDITION_GROUPS:
            errors.append("unknown_condition_group")
        for key in ("asset_id", "source_slot_id", "target_seat_id", "control_config_sha256", "code_commit"):
            if attrs.get(key) in (None, "", "unknown", "unavailable"):
                errors.append("missing_" + key)
        deviation = attrs.get("deterministic_action_deviation_json")
        try:
            if isinstance(deviation, str):
                deviation = json.loads(deviation)
            if deviation is None and "episode_metadata_json" in episode:
                metadata = json.loads(episode["episode_metadata_json"][()].decode())
                deviation = metadata.get("deterministic_action_deviation")
        except (ValueError, TypeError, AttributeError):
            errors.append("invalid_action_deviation_json")
            deviation = None
        if attrs.get("condition_group") == "natural" and deviation:
            errors.append("natural_group_contains_action_deviation")
        if attrs.get("condition_group") == "deterministic_action_deviation":
            if not isinstance(deviation, dict) or not all(deviation.get(key) is not None for key in
                    ("stage", "value", "unit", "controller_version")):
                errors.append("missing_action_deviation_specification")
            else:
                if any(not isinstance(deviation[key], str) or not deviation[key].strip()
                       for key in ("stage", "unit", "controller_version")):
                    errors.append("invalid_action_deviation_stage_unit_or_controller")
                try:
                    values = np.asarray(deviation["value"], float)
                    if not values.size or not np.isfinite(values).all():
                        errors.append("nonfinite_action_deviation_value")
                except (ValueError, TypeError):
                    errors.append("nonnumeric_action_deviation_value")
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


def official_process_gate(row, collection_root):
    """Independently enforce real closed official driver provenance for quotas.

    This never changes the HDF5's raw physical outcome. Standalone portable
    episode reading uses audit_episode directly and needs no driver files.
    """
    root = Path(collection_root).resolve()
    source = Path(row["path"]).resolve()
    run = source.parents[2]
    errors, matching = [], []
    if not source.is_relative_to(root / "runs") or source.parent.name != "dataset":
        errors.append("not_an_official_collection_run_path")
    for manifest in sorted((root / "driver_records").glob("batch_*.json")):
        record = json.loads(manifest.read_text())
        if Path(record.get("run_directory", "")).resolve() == run:
            matching.append((manifest, record))
    if len(matching) != 1:
        errors.append("official_driver_record_missing_or_ambiguous")
    else:
        manifest, record = matching[0]
        if record.get("official_collection_run") is not True or record.get("process_exited") is not True:
            errors.append("official_process_exit_not_observed")
        if record.get("exit_code") != 0 or isinstance(record.get("exit_code"), bool):
            errors.append("official_process_nonzero_or_unknown_exit:" + str(record.get("exit_code")))
        if record.get("interrupted"):
            errors.append("official_process_interrupted")
        proof_path = run / "process_exit.json"
        if not proof_path.is_file():
            errors.append("independent_process_exit_evidence_missing")
        else:
            proof = json.loads(proof_path.read_text())
            if Path(proof.get("run_directory", "")).resolve() != run or proof.get("process_exited") is not True or proof.get("exit_code") != 0 or isinstance(proof.get("exit_code"), bool) or proof.get("interrupted"):
                errors.append("independent_process_exit_evidence_nonzero_interrupted_or_mismatched")
        row["official_driver_evidence"] = dict(path=str(manifest), sha256=file_sha(manifest),
            observed_exit_code=record.get("exit_code"), interrupted=record.get("interrupted"))
    row["official_process_admission_errors"] = errors
    if errors:
        row["admission_errors"].extend(errors)
        for key in ("success", "failure", "all_valid"):
            row[key] = False
    row["source_HDF5_labels_preserved"] = True
    return row


def make_index(rows, destination, *, copy_data=False, collection_root=None):
    destination = Path(destination).resolve()
    if not copy_data and collection_root is None:
        raise ValueError("Relative link index requires an explicit collection_root")
    collection = Path(collection_root).resolve() if collection_root is not None else None
    if not copy_data and not destination.is_relative_to(collection):
        raise ValueError("Relative index must remain within the collection tree")
    selected = []
    for row in rows:
        if not (row["success"] or row["failure"]):
            continue
        source = Path(row["path"]).resolve()
        if collection is not None and not source.is_relative_to(collection):
            raise ValueError("Episode lies outside the selected collection tree: " + str(source))
        if source == destination:
            raise ValueError("Index cannot replace an episode source")
        with h5py.File(source, "r") as record:
            dependencies = scan_links(record)
            if dependencies:
                raise ValueError("Original episode must be self-contained, without external links/VDS: " + str(source))
        selected.append((row, source))
    destination.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with h5py.File(destination, "x") as merged:
        merged.attrs.update(schema_version="labsim.Size_v1.index.v1", sample_filter="all_valid",
            storage_mode="copied_episode_data" if copy_data else "relative_external_links",
            portability_scope="self-contained index" if copy_data else "move entire collection tree including original episode HDF5 files")
        sources = []
        for row, source_path in selected:
            relative = Path(os.path.relpath(source_path, destination.parent)).as_posix()
            name = f"episode_{count:04d}"
            if copy_data:
                with h5py.File(source_path, "r") as source:
                    target = merged.create_group(name)
                    target.attrs.update(dict(source.attrs))
                    for key in source:
                        source.copy(key, target)
            else:
                merged[name] = h5py.ExternalLink(relative, "/")
            sources.append(dict(index_group=name, relative_episode_file=relative,
                                source_sha256=row.get("source_sha256")))
            count += 1
        merged.attrs["episode_sources_json"] = json.dumps(sources, ensure_ascii=False, sort_keys=True)
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
    parser.add_argument("--index", type=Path, help="Create a small relative-link index within episodes_root; move whole collection tree together")
    parser.add_argument("--copy-data", action="store_true", help="Explicitly copy complete selected HDF5 contents instead of lightweight relative links")
    parser.add_argument("--read-index", type=Path, help="Read an existing index without creating one")
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--admission-scope", choices=("auto", "official_collection", "standalone_record"), default="auto",
        help="auto requires actual driver exit evidence when collection_contract.json exists; standalone reads are not official20/20 quota evidence")
    args = parser.parse_args(argv)
    if args.copy_data and not args.index:
        parser.error("--copy-data requires --index")
    frozen = load_frozen(args.frozen_scene)
    validate_frozen_scene(OmegaConf.load(args.config), frozen, ROOT, purpose="collect")
    contract_path = args.episodes_root / "collection_contract.json"
    official = contract_path.is_file()
    if args.admission_scope == "official_collection" and not official:
        raise ValueError("Official collection scope requires collection_contract.json")
    if args.admission_scope == "standalone_record" and official:
        raise ValueError("Cannot bypass actual official collection process evidence with standalone scope")
    if official and json.loads(contract_path.read_text()).get("frozen_scene_sha256") != frozen["frozen_scene_sha256"]:
        raise ValueError("Official collection frozen-scene contract differs from current audit")
    files = sorted(args.episodes_root.rglob("episode_*.h5"))
    rows, seen, duplicates = [], set(), []
    for path in files:
        row = audit_episode(path, frozen["frozen_scene_sha256"])
        if official:
            row = official_process_gate(row, args.episodes_root)
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
        admission_scope="official_collection_closed_exit0" if official else "standalone_record_reading_only",
        official_collection_quota_evidence=official,
        scene_mode="standard", scene_randomization_enabled=False, inspected_episode_count=len(rows),
        qualified_success_count=success, qualified_failure_count=failure,
        success_quota=20, failure_quota=20, success_missing=max(0, 20-success), failure_missing=max(0, 20-failure),
        condition_groups=grouped, archived_not_counted=len(rows)-success-failure,
        duplicate_episode_files_not_counted=duplicates, episodes=rows, reader_validation=[],
        labels_modified=False, random10_is_not_an_acceptance_requirement=True)
    if args.index:
        result["merged_episodes"] = make_index(rows, args.index, copy_data=args.copy_data,
                                               collection_root=args.episodes_root)
        result["index_storage"] = "copied_episode_data" if args.copy_data else "relative_external_links"
        result["index_portability"] = "self-contained copied index" if args.copy_data else "move the entire collection tree, preserving relative paths"
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
