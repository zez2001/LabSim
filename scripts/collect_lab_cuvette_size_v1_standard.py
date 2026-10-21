"""Thin sequential Size_v1 standard collector; no new environment or labels.

verify5 must pass before success/controlled_failure phases are explicitly allowed.
Only observed, closed official runs in this collection count towards quotas.
--dry-run validates and prints a plan without creating files or starting Isaac.
"""
from __future__ import annotations

import argparse
import copy
import datetime
import fcntl
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import h5py
from omegaconf import OmegaConf
from demos.lab_cuvette_size_v1.frozen_scene import (file_sha, load_frozen, plain,
    validate_frozen_scene)
from scripts.archive_lab_cuvette_size_v1_logs import archive_episode
from utils.episode_selection import episode_matches_filter

TARGET = 20
DEPTHS_M = (.001, .005, .010, .018)
NON_TASK_REASONS = {"PREVIEW_COMPLETE", "DIAGNOSTIC_ONLY", "REPLAY_SOURCE_EXHAUSTED"}


def write_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")


def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def fast_episode(path, fingerprint, asset_id):
    """Read only small metadata/counts; full data audit remains a separate tool."""
    errors = []
    with h5py.File(path, "r") as source:
        attrs = {k: (v.item() if hasattr(v, "item") else v) for k, v in source.attrs.items()
                 if not hasattr(v, "shape") or v.shape == ()}
        if attrs.get("frozen_scene_sha256") != fingerprint or attrs.get("asset_id") != asset_id:
            errors.append("frozen_scene_or_asset_mismatch")
        if attrs.get("scene_mode") != "standard" or attrs.get("task_type") != "loading":
            errors.append("not_standard_full_loading")
        group = attrs.get("condition_group")
        if group not in {"natural", "deterministic_action_deviation"}:
            errors.append("unqualified_condition_group")
        for key in ("source_slot_id", "target_seat_id", "control_config_sha256", "code_commit", "episode_id"):
            if attrs.get(key) in (None, "", "unknown", "unavailable"):
                errors.append("missing_" + key)
        reason = str(attrs.get("termination_reason", "")).upper()
        if "preview" in str(attrs.get("policy_id", "")).lower() or reason in NON_TASK_REASONS or "BUDGET" in reason or reason.startswith("REPLAY_") or attrs.get("failure_type") == "DIAGNOSTIC_ONLY":
            errors.append("non_task_interface_diagnostic")
        try:
            deviation = json.loads(attrs.get("deterministic_action_deviation_json", "null"))
        except (ValueError, TypeError):
            deviation = None
            errors.append("invalid_deviation_json")
        if group == "natural" and deviation:
            errors.append("natural_group_hides_deviation")
        if group == "deterministic_action_deviation" and (not isinstance(deviation, dict) or
                not all(key in deviation for key in ("stage", "value", "unit", "controller_version", "stop_insertion_at_depth_m"))):
            errors.append("missing_deterministic_deviation_metadata")
        frames = len(source["actions"]) if "actions" in source else 0
        if not frames or attrs.get("frames") != frames:
            errors.append("missing_or_inconsistent_frames")
        success = episode_matches_filter(source.attrs, "success")[0] and not errors
        failure = episode_matches_filter(source.attrs, "failure")[0] and not errors
    return dict(path=str(Path(path).resolve()), episode_id=attrs.get("episode_id"),
        success=bool(success), failure=bool(failure), condition_group=group,
        record_valid=attrs.get("record_valid") is True, task_success=attrs.get("task_success"),
        failure_type=attrs.get("failure_type"), termination_reason=attrs.get("termination_reason"),
        frames=frames, complete=attrs.get("complete") is True, admission_errors=errors)


def statistics(collection, fingerprint, asset_id):
    records, episodes, quarantined, seen = [], [], [], set()
    for path in sorted((Path(collection) / "driver_records").glob("batch_*.json")):
        batch = json.loads(path.read_text())
        if batch.get("official_collection_run") is not True or batch.get("process_exited") is not True:
            continue
        records.append(batch)
        run = Path(batch["run_directory"]).resolve()
        if not run.is_relative_to(Path(collection).resolve() / "runs"):
            raise ValueError("Official run outside collection tree")
        if batch.get("exit_code") != 0 or batch.get("interrupted"):
            quarantined.extend(str(path) for path in run.glob("episode_*/dataset/episode_0000.h5"))
            continue
        for source in sorted(run.glob("episode_*/dataset/episode_0000.h5")):
            try:
                item = fast_episode(source, fingerprint, asset_id)
            except Exception as error:
                item = dict(path=str(source), episode_id="unreadable:" + str(source), success=False,
                    failure=False, complete=False, condition_group="unknown", frames=None,
                    admission_errors=[type(error).__name__ + ": " + str(error)])
            if item["episode_id"] in seen:
                continue
            seen.add(item["episode_id"])
            item["phase"] = batch["phase"]
            episodes.append(item)
    return dict(started_processes=len(records), completed_processes=sum(r["exit_code"] == 0 and not r.get("interrupted") for r in records),
        interrupted_processes=sum(bool(r.get("interrupted")) for r in records),
        nonzero_exit_processes=sum(r["exit_code"] != 0 for r in records),
        controlled_processes=sum(r["phase"] == "controlled_failure" for r in records),
        requested_episodes=sum(r["requested_episodes"] for r in records),
        started_episode_directories=sum(len(list(Path(r["run_directory"]).glob("episode_*"))) for r in records),
        completed_episodes=sum(e["complete"] for e in episodes), inspected_record_files=len(episodes),
        quarantined_nonzero_or_interrupted_process_record_files=quarantined,
        success=sum(e["success"] for e in episodes), failure=sum(e["failure"] for e in episodes),
        natural_failure=sum(e["failure"] and e["condition_group"] == "natural" for e in episodes),
        controlled_failure=sum(e["failure"] and e["condition_group"] == "deterministic_action_deviation" for e in episodes),
        archived_not_counted=sum(not e["success"] and not e["failure"] for e in episodes), episodes=episodes)


def controlled_config(base, depth, controller_version):
    cfg = copy.deepcopy(plain(base))
    cfg.setdefault("experiment", {}).update(condition_group="deterministic_action_deviation",
        run_role="standard_collection", deviation=dict(stage="INSERT", value=float(depth), unit="m",
            controller_version=controller_version, stop_insertion_at_depth_m=float(depth),
            action="stop normal insertion at actual depth; preserve physical failure result"))
    return cfg


def build_command(config, run, episodes, *, headless=False, root=ROOT):
    if not 1 <= episodes <= 5:
        raise ValueError("Each Isaac process may request only1..5 episodes")
    command = ["bash", str(Path(root) / "demos/lab_cuvette_env_v1/run.sh"), "--mode", "teacher",
        "--config", str(config), "--layout-mode", "standard", "--seed", "0", "--episodes", str(episodes),
        "--output", str(run)]
    if headless:
        command.append("--headless")
    return command


def execute_process(command, run, log, *, popen=subprocess.Popen):
    started, started_utc, interrupted = time.perf_counter(), utc(), False
    with Path(log).open("x", encoding="utf-8") as output:
        process = popen(command, cwd=ROOT, stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            code = process.wait()
        except KeyboardInterrupt:
            interrupted = True
            os.killpg(process.pid, signal.SIGINT)
            try:
                code = process.wait(timeout=60)
            except subprocess.TimeoutExpired:
                process.terminate()
                try:
                    code = process.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    process.kill()
                    code = process.wait()
    # wait() really returned before this evidence or any archive operation.
    run = Path(run)
    run.mkdir(parents=True, exist_ok=True)
    evidence = dict(run_directory=str(run.resolve()), process_exited=True, exit_code=int(code),
        pid=int(process.pid), argv=command, source="subprocess.Popen.wait observed by Size_v1 collection driver",
        started_utc=started_utc, exited_utc=utc(), elapsed_wall_s=time.perf_counter()-started,
        interrupted=interrupted, stdout_log=str(Path(log).resolve()))
    write_new(run / "process_exit.json", evidence)
    return evidence


def archive_closed_run(run):
    outcomes = []
    for episode in sorted(Path(run).glob("episode_*")):
        if not episode.is_dir():
            continue
        try:
            result = archive_episode(episode, Path(run) / "process_exit.json", replace=True)
            outcomes.append(dict(episode=str(episode), archived=True,
                                 manifest=result["archive_manifest"]))
        except Exception as error:
            # Incomplete/active logs remain untouched. Report, never conceal.
            outcomes.append(dict(episode=str(episode), archived=False,
                error_type=type(error).__name__, error=str(error)))
    return outcomes


def check_run_resources(collection):
    free = shutil.disk_usage(collection).free
    if free < 8 * (1 << 30):
        raise RuntimeError("Less than8GiB free disk; stopping before starting Isaac")
    with open("/tmp/labsim-V0_ext01-gpu.lock", "a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError("Another Isaac run holds the GPU lock; no collection process started") from error
        fcntl.flock(lock, fcntl.LOCK_UN)
    return dict(free_bytes=free, minimum_required_bytes=8 * (1 << 30), gpu_lock_observed_free=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=("verify5", "success", "controlled_failure"), required=True)
    parser.add_argument("--collection", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=ROOT / "config/lab_cuvette_loading/Size_v1/standard.yaml")
    parser.add_argument("--frozen-scene", type=Path, default=ROOT / "config/lab_cuvette_loading/Size_v1/frozen_scene.json")
    parser.add_argument("--allow-after-verified-five", action="store_true")
    parser.add_argument("--episodes-per-process", type=int, default=5)
    parser.add_argument("--max-processes", type=int, default=8)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    if not 1 <= args.episodes_per_process <= 5 or args.max_processes < 1:
        parser.error("episodes-per-process must be1..5; max-processes must be positive")
    cfg, frozen = OmegaConf.load(args.config), load_frozen(args.frozen_scene)
    validate_frozen_scene(cfg, frozen, ROOT, purpose="collect")
    if cfg.env.task_type != "loading" or cfg.experiment.get("condition_group") != "natural":
        raise ValueError("Base config must be full loading with the natural controller")
    collection = args.collection.resolve()
    allowed = (ROOT / "outputs/lab_cuvette_loading/Size_v1").resolve()
    if not collection.is_relative_to(allowed) or collection == allowed:
        raise ValueError("Collection must be a dedicated new tree beneath Size_v1 outputs")
    fingerprint, asset_id = frozen["frozen_scene_sha256"], str(cfg.asset_id)
    contract = dict(schema="labsim.Size_v1.official_standard_collection.v1", frozen_scene_sha256=fingerprint,
        asset_id=asset_id, source_config_sha256=file_sha(args.config), frozen_manifest_sha256=file_sha(args.frozen_scene),
        config_path=str(args.config.resolve()), frozen_manifest_path=str(args.frozen_scene.resolve()),
        scene_mode="standard", scene_randomization_enabled=False, success_target=20, failure_target=20)
    if args.phase == "verify5":
        if collection.exists():
            raise FileExistsError("verify5 requires a new collection tree; preserve previous outputs")
    else:
        if not args.allow_after_verified_five:
            raise ValueError("Explicit --allow-after-verified-five is required after reviewing actual verify5")
        previous = json.loads((collection / "collection_contract.json").read_text())
        if previous != contract:
            raise ValueError("Frozen collection/config contract changed; do not mix episodes")
        verification = json.loads((collection / "verify5_passed.json").read_text())
        if verification.get("passed") is not True or verification.get("frozen_scene_sha256") != fingerprint or verification.get("full_loading_successes") != 5:
            raise ValueError("The exact frozen scene has not passed5/5 full-loading verification")
        current = statistics(collection, fingerprint, asset_id)
        verified_ids = set(verification.get("episode_ids", []))
        actual_verified = {e["episode_id"] for e in current["episodes"] if e["phase"] == "verify5" and e["success"]}
        if len(verified_ids) != 5 or not verified_ids.issubset(actual_verified):
            raise ValueError("Verification evidence is missing or no longer matches actual qualified episodes")
        if args.phase == "controlled_failure" and current["success"] < TARGET:
            raise ValueError("Finish20 qualified standard successes before controlled failure supplementation")
    if args.dry_run:
        plan = dict(dry_run=True, no_GPU_or_files_created=True, phase=args.phase,
            collection=str(collection), frozen_scene_sha256=fingerprint, asset_id=asset_id,
            episodes_per_process=args.episodes_per_process, target=5 if args.phase == "verify5" else TARGET,
            maximum_processes=args.max_processes, controlled_depths_m=list(DEPTHS_M),
            command_example=build_command(args.config.resolve(), collection / "runs/EXAMPLE_NEW_RUN",
                min(5 if args.phase == "verify5" else 20, args.episodes_per_process), headless=args.headless))
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return plan
    if args.phase == "verify5":
        collection.mkdir(parents=True, exist_ok=False)
        write_new(collection / "collection_contract.json", contract)
    for name in ("runs", "driver_records", "process_logs", "controller_configs"):
        (collection / name).mkdir(exist_ok=True)
    driver_lock = open("/tmp/labsim-Size_v1-collection-driver.lock", "a")
    fcntl.flock(driver_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    phase_id = args.phase + "_" + datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ_") + uuid.uuid4().hex[:8]
    status, phase_episodes, batches, stops = "maximum_processes_reached", [], [], []
    try:
        for number in range(args.max_processes):
            totals = statistics(collection, fingerprint, asset_id)
            remaining = (5-len(phase_episodes)) if args.phase == "verify5" else TARGET-totals["success" if args.phase == "success" else "failure"]
            if remaining <= 0:
                status = "target_reached"
                break
            try:
                resource = check_run_resources(collection)
            except Exception as error:
                status = "resource_precheck_stop_no_process_started"
                stops.append(dict(error_type=type(error).__name__, error=str(error), time_utc=utc()))
                break
            count = min(args.episodes_per_process, remaining)
            batch_id = phase_id + f"_{number:02d}"
            run, config = collection / "runs" / batch_id, args.config.resolve()
            if args.phase == "controlled_failure":
                config = collection / "controller_configs" / (batch_id + ".yaml")
                altered = controlled_config(cfg, DEPTHS_M[totals["controlled_processes"] % len(DEPTHS_M)],
                    str(cfg.experiment.get("controller_version", "unknown")))
                validate_frozen_scene(altered, frozen, ROOT, purpose="collect")
                with config.open("x", encoding="utf-8") as stream:
                    stream.write(OmegaConf.to_yaml(OmegaConf.create(altered)))
            command = build_command(config, run, count, headless=args.headless)
            print("COLLECTION_START", batch_id, json.dumps(command), flush=True)
            try:
                evidence = execute_process(command, run, collection / "process_logs" / (batch_id + ".log"))
            except Exception as error:
                status = "launch_or_exit_evidence_error_stop"
                stops.append(dict(error_type=type(error).__name__, error=str(error), argv=command,
                    time_utc=utc(), no_closed_process_archive_attempted=True))
                break
            batch = dict(evidence, phase=args.phase, official_collection_run=True,
                requested_episodes=count, prelaunch_resources=resource, config_path=str(config),
                config_sha256=file_sha(config), frozen_scene_sha256=fingerprint,
                archive_results=archive_closed_run(run))
            write_new(collection / "driver_records" / ("batch_" + batch_id + ".json"), batch)
            batches.append(batch)
            totals = statistics(collection, fingerprint, asset_id)
            actual = [e for e in totals["episodes"] if Path(e["path"]).is_relative_to(run)]
            phase_episodes.extend(actual)
            print("COLLECTION_BATCH_RESULT", json.dumps({k: totals[k] for k in
                ("success", "failure", "natural_failure", "controlled_failure", "completed_episodes")}), flush=True)
            if evidence["interrupted"] or evidence["exit_code"] != 0:
                status = "process_interrupted" if evidence["interrupted"] else "process_nonzero_exit"
                break
            if args.phase == "verify5" and (len(actual) != count or any(not e["success"] for e in actual)):
                status = "verification_failed_stop_no_collection"
                break
            if any(not item["archived"] for item in batch["archive_results"]):
                status = "archive_incomplete_stop_to_preserve_disk"
                break
        totals = statistics(collection, fingerprint, asset_id)
        if args.phase == "verify5" and len(phase_episodes) == 5 and all(e["success"] for e in phase_episodes) and status in {"maximum_processes_reached", "target_reached"}:
            status = "target_reached"
            write_new(collection / "verify5_passed.json", dict(passed=True,
                frozen_scene_sha256=fingerprint, asset_id=asset_id, full_loading_successes=5,
                episode_ids=[e["episode_id"] for e in phase_episodes], phase_id=phase_id))
        elif args.phase != "verify5" and totals["success" if args.phase == "success" else "failure"] >= TARGET and status == "maximum_processes_reached":
            status = "target_reached"
        result = dict(schema="labsim.Size_v1.collection_phase_result.v1", phase=args.phase,
            phase_id=phase_id, status=status, totals=totals, batches=batches, prelaunch_or_driver_stops=stops,
            randomization_enabled=False, labels_modified=False, completed_utc=utc())
        write_new(collection / (phase_id + "_result.json"), result)
        print(json.dumps(dict(phase=args.phase, status=status, success=totals["success"],
            failure=totals["failure"], success_missing=max(0, 20-totals["success"]),
            failure_missing=max(0, 20-totals["failure"])), ensure_ascii=False), flush=True)
        return result
    finally:
        driver_lock.close()


if __name__ == "__main__":
    result = main()
    if not result.get("dry_run") and result.get("status") != "target_reached":
        raise SystemExit(2)
