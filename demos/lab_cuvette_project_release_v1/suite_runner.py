"""Sequential evaluation of fixed release scenes through the ordinary launcher.

Each scene definition is immutable during reset. Scene membership, repetition
and global episode ordinal are separate fields; a failed member is retained.
The runner never starts a second Isaac process before the previous one exits.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

from demos.lab_cuvette_project_release_v1.scene_suite import (
    SUITE_VERSION, load_scene_definition, suite_scene_ids, validate_selection,
)

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config/lab_cuvette_loading/Project_release_v1/standard.yaml"
INITIALIZATION_FAILURES = frozenset(("INVALID_INITIAL_STATE", "INITIALIZATION_INVALID",
    "INIT_INVALID", "GEOMETRY_PREFLIGHT_BLOCKED", "GEOMETRY_PRECHECK_BLOCKED"))


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    selection = p.add_mutually_exclusive_group(required=True)
    selection.add_argument("--scene", help="One fixed scene ID, including standard")
    selection.add_argument("--suite", choices=("random10",))
    p.add_argument("--config", type=Path, default=CONFIG)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--episodes-per-scene", type=int, default=1)
    p.add_argument("--reset-checks", type=int, choices=(0, 3), default=0,
        help="Validate three independent resets before each formal child episode")
    p.add_argument("--backend", choices=("teacher", "gpt6"), default="teacher")
    p.add_argument("--record-mode", choices=("collect", "eval", "diagnostic"), default="eval")
    p.add_argument("--asset-id")
    p.add_argument("--provider-config", type=Path)
    p.add_argument("--budget-ledger", type=Path)
    p.add_argument("--max-calls", type=int)
    p.add_argument("--headless", action="store_true")
    p.add_argument("--gui", action="store_true")
    p.add_argument("--progress", action="store_true")
    p.add_argument("--dry-run", action="store_true", help="Print the complete plan without creating files or starting Isaac")
    return p


def _sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(4 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def make_plan(args):
    output = args.output.resolve()
    if output.exists() or output.is_symlink():
        raise FileExistsError("Output already exists; use a new directory: " + str(output))
    if not args.config.is_file():
        raise ValueError("Config does not exist: " + str(args.config))
    if not 1 <= args.episodes_per_scene <= 20:
        raise ValueError("episodes-per-scene must be 1..20")
    if args.gui and args.headless:
        raise ValueError("Choose --gui or --headless")
    scenes = tuple(suite_scene_ids(args.suite)) if args.suite else (args.scene,)
    rows = []
    for scene_id in scenes:
        validate_selection(scene_id, purpose="eval")
        definition = load_scene_definition(scene_id)
        for repetition in range(args.episodes_per_scene):
            ordinal = len(rows)
            child = output / scene_id / f"repetition_{repetition:03d}"
            command = [sys.executable, "-m", "demos.lab_cuvette_project_release_v1.launch",
                "--config", str(args.config.resolve()), "--backend", args.backend,
                "--scene", scene_id, "--episodes", "1", "--seed", "0",
                "--execution-purpose", "eval", "--record-mode", args.record_mode,
                "--record-purpose", "policy_evaluation", "--output", str(child),
                "--suite-run-id", output.name, "--scene-repetition-index", str(repetition),
                "--suite-episode-index", str(ordinal)]
            for key in ("headless", "gui", "progress"):
                if getattr(args, key):
                    command.append("--" + key.replace("_", "-"))
            if args.reset_checks:
                command += ["--reset-checks", str(args.reset_checks)]
            for key in ("asset_id", "provider_config", "budget_ledger", "max_calls"):
                value = getattr(args, key)
                if value is not None:
                    command.extend(("--" + key.replace("_", "-"), str(value)))
            rows.append(dict(scene_id=scene_id, scene_repetition_index=repetition,
                suite_episode_index=ordinal, output=str(child), argv=command,
                scene_definition=definition))
    return dict(schema="labsim.scene_suite.execution_plan.v1", suite_version=SUITE_VERSION,
        suite=args.suite, scene_ids=list(scenes), episodes_per_scene=args.episodes_per_scene,
        episodes_requested=len(rows), backend=args.backend, output=str(output),
        record_purpose="policy_evaluation", sequential_single_gpu=True,
        reset_checks_per_formal_episode=args.reset_checks,
        fixed_definitions_reused_on_reset=True, episodes=rows)


def _read_json(path):
    return json.loads(path.read_text()) if path.is_file() else None


def classify_result(result, *, initialization_failure, process_closed, complete,
                    independent_outcome_matches, backend="teacher"):
    if initialization_failure:
        return "initialization_failure"
    if not process_closed or not complete or not independent_outcome_matches:
        return "environment_exception"
    if result.get("task_success") is True and result.get("record_valid") is True:
        return "full_task_success"
    return "reference_controller_failure" if backend == "teacher" else "policy_task_failure"


def inspect_closed_run(output, exit_code, *, backend="teacher", expected_scene_id=None):
    """Read the independent task result and immutable, closed normal-reader data."""
    output = Path(output)
    episodes = sorted(output.glob("episode_*/result.json"))
    result = _read_json(episodes[0]) if len(episodes) == 1 else {}
    result = result or {}
    independent = _read_json(episodes[0].parent / "independent_score.json") if len(episodes) == 1 else None
    manifest = _read_json(output / "run_manifest.json")
    shutdown = _read_json(output / "application_shutdown.json") or {}
    runner_failure = _read_json(output / "runner_failure.json")
    reason = str(result.get("termination_reason", result.get("reason", "NO_COMPLETED_EPISODE")))
    failure_type = str(result.get("failure_type", "UNKNOWN"))
    initialization_failure = failure_type in INITIALIZATION_FAILURES or reason in INITIALIZATION_FAILURES
    if not episodes and runner_failure:
        message = str(runner_failure.get("error", ""))
        initialization_failure = initialization_failure or "initial" in message.lower() or "geometry precheck" in message.lower()
    complete = result.get("complete") is True and result.get("publication_state") == "complete"
    process_closed = exit_code == 0 and manifest is not None and shutdown.get("successful_cleanup_calls") is True
    row = dict(process_exit_code=exit_code, process_exited=True,
        record_closed=complete, orderly_cleanup=shutdown.get("successful_cleanup_calls") is True,
        task_success=result.get("task_success"), record_valid=result.get("record_valid"),
        termination_reason=reason, failure_type=failure_type,
        recorded_episode_id=result.get("episode_id"), reader_check=None,
        result_path=str(episodes[0]) if len(episodes) == 1 else None,
        independent_score_present=independent is not None,
        independent_outcome_matches=(independent is not None and independent.get("task_success") == result.get("task_success")),
        run_manifest_present=manifest is not None)
    row["outcome"] = classify_result(result, initialization_failure=initialization_failure,
        process_closed=process_closed and len(episodes) == 1, complete=complete,
        independent_outcome_matches=row["independent_outcome_matches"], backend=backend)
    sources = sorted(output.glob("episode_*/dataset/episode_*.h5"))
    if complete and process_closed and len(sources) == 1:
        try:
            import h5py
            from demos.lab_cuvette_project_release_v1.dataset_index import build_index
            from demos.lab_cuvette_project_release_v1.scene_data import scene_identity
            from policy.dataset.lab_cuvette_project_release_dataset import LabCuvetteProjectReleaseDataset
            from scripts.read_lab_cuvette_project_v1_data import read_check
            with h5py.File(sources[0]) as source:
                identity = scene_identity(source)
                row["recorded_scene_id"] = identity["scene_id"]
                row["scene_suite_version"] = identity["scene_suite_version"]
            if expected_scene_id is not None and identity["scene_id"] != expected_scene_id:
                raise ValueError("Recorded scene does not match the requested fixed member")
            index = output / "evaluation_index/episode_data.hdf5"
            build_index(output, index, purpose="policy_evaluation", data_use="evaluation")
            check = read_check(index, sample_filter="all_valid", dataset_class=LabCuvetteProjectReleaseDataset,
                dataset_options=dict(data_use="evaluation"))
            (output / "evaluation_index/reader_check.json").write_text(json.dumps(check, indent=2) + "\n")
            row["reader_check"] = dict(passed=True, index=str(index),
                report=str(output / "evaluation_index/reader_check.json"))
        except Exception as error:
            row["reader_check"] = dict(passed=False, error_type=type(error).__name__, error=str(error))
            row["outcome"] = "environment_exception"
    elif row["outcome"] in ("full_task_success", "reference_controller_failure", "policy_task_failure"):
        row["outcome"] = "environment_exception"
        row["reader_check"] = dict(passed=False, error="Expected one transactionally closed H5")
    return row


def summarize(plan, rows):
    def group(scene_id):
        selected = [row for row in rows if row["scene_id"] == scene_id]
        successes = sum(row["outcome"] == "full_task_success" for row in selected)
        requested = plan["episodes_per_scene"]
        return dict(scene_id=scene_id, requested=plan["episodes_per_scene"], started=len(selected),
            not_started=requested - len(selected), execution_coverage=len(selected) / requested,
            completed=sum(row.get("record_closed") is True for row in selected),
            full_task_successes=successes,
            full_success_rate=(successes / requested) if len(selected) == requested else None,
            observed_full_success_rate=(successes / len(selected)) if selected else None,
            outcome_counts={name: sum(row["outcome"] == name for row in selected)
                for name in ("initialization_failure", "environment_exception", "reference_controller_failure",
                             "policy_task_failure", "full_task_success")})
    groups = [group(scene) for scene in plan["scene_ids"]]
    random = [row for row in groups if row["scene_id"] != "standard"]
    observed_random = [row for row in random if row["started"] > 0]
    random_complete = (set(row["scene_id"] for row in random) == set(suite_scene_ids("random10"))
        and all(row["full_success_rate"] is not None for row in random))
    coverage = dict(expected_scene_count=10, requested_scene_count=len(random),
        started_scene_count=len(observed_random),
        fully_started_scene_count=sum(row["started"] == row["requested"] for row in random),
        requested_episodes=sum(row["requested"] for row in random),
        started_episodes=sum(row["started"] for row in random), complete=random_complete)
    return dict(schema="labsim.scene_suite.summary.v1", suite_version=SUITE_VERSION,
        episodes_requested=plan["episodes_requested"], episodes_started=len(rows),
        standard=next((row for row in groups if row["scene_id"] == "standard"), None),
        random_per_scene=random,
        random_coverage=coverage,
        random_mean_full_success_rate=(sum(row["full_success_rate"] for row in random) / 10)
            if random_complete else None,
        observed_random_scene_mean_full_success_rate=(sum(row["observed_full_success_rate"]
            for row in observed_random) / len(observed_random)) if observed_random else None,
        denominator="full_success_rate uses all requested repetitions only after they have all started; actual initialization/environment failures are retained; unstarted members are unavailable",
        observed_denominator="observed_full_success_rate uses started episodes; observed_random_scene_mean_full_success_rate is a macro mean over started scenes and is not the Random-10 overall result",
        complete=len(rows) == plan["episodes_requested"], episodes=rows)


def run(args, *, process_runner=subprocess.run, run_inspector=inspect_closed_run):
    plan = make_plan(args)
    if args.dry_run:
        return dict(plan, dry_run=True, files_created=False, simulation_started=False)
    output = Path(plan["output"])
    output.mkdir(parents=True, exist_ok=False)
    git_head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    changes = subprocess.check_output(["git", "diff", "--binary", "HEAD"], cwd=ROOT)
    identity = dict(plan, code_commit=git_head, tracked_worktree_diff_sha256=hashlib.sha256(changes).hexdigest(),
        source_config_sha256=_sha(args.config))
    (output / "suite_manifest.json").write_text(json.dumps(identity, ensure_ascii=False, indent=2) + "\n")
    rows = []
    try:
        for member in plan["episodes"]:
            child = Path(member["output"])
            child.parent.mkdir(parents=True, exist_ok=True)
            start = time.perf_counter()
            # The child owns creation of its episode output. A subprocess owns
            # all Isaac state and exits before this loop advances.
            log = child.parent / (child.name + ".log")
            with log.open("x") as stream:
                completed = process_runner(member["argv"], cwd=ROOT, stdout=stream,
                    stderr=subprocess.STDOUT, check=False)
            observation = run_inspector(child, completed.returncode, backend=args.backend,
                expected_scene_id=member["scene_id"])
            row = {key: member[key] for key in ("scene_id", "scene_repetition_index", "suite_episode_index", "output")}
            row.update(observation, wall_seconds=time.perf_counter() - start, process_log=str(log))
            rows.append(row)
            child.mkdir(parents=True, exist_ok=True)
            (child / "suite_process_exit.json").write_text(json.dumps(dict(process_exited=True,
                exit_code=completed.returncode, **{key: row[key] for key in ("scene_id", "scene_repetition_index", "suite_episode_index")}), indent=2) + "\n")
            (output / "suite_summary.json").write_text(json.dumps(summarize(plan, rows), indent=2) + "\n")
    finally:
        result = summarize(plan, rows)
        (output / "suite_summary.json").write_text(json.dumps(result, indent=2) + "\n")
        if rows:
            fields = ("scene_id", "scene_repetition_index", "suite_episode_index", "outcome", "task_success",
                "record_valid", "record_closed", "process_exit_code", "termination_reason", "failure_type", "wall_seconds", "output")
            with (output / "suite_results.csv").open("w", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(rows)
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        result = run(args)
    except (ValueError, OSError) as error:
        parser().error(str(error))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.dry_run:
        return 0
    return 0 if result["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
