"""Replay saved typed control commands through the same real environment.

This module imports no Isaac code. Loading validates immutable source data;
execution only calls reset/step/finalize, never a teacher or object-pose setter.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

import h5py
import numpy as np
from omegaconf import OmegaConf

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = "labsim.lab_cuvette_loading.Env_v1.v1"
SEMANTICS = "absolute_position_9d:7_arm_rad+left_and_right_finger_m"


def sha256(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as file:
        for block in iter(lambda: file.read(4 << 20), b""):
            value.update(block)
    return value.hexdigest()


def plain(value):
    if isinstance(value, dict):
        return {str(k): plain(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [plain(v) for v in value]
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return plain(value.item())
    if isinstance(value, bytes):
        return value.decode("utf-8")
    if isinstance(value, Path):
        return str(value)
    return value


def write(path, value):
    Path(path).write_text(json.dumps(plain(value), indent=2, allow_nan=False) + "\n")


def self_contained(group, visited=None):
    visited = set() if visited is None else visited
    address = h5py.h5o.get_info(group.id).addr
    if address in visited:
        return
    visited.add(address)
    for name in group:
        if not isinstance(group.get(name, getlink=True), h5py.HardLink):
            raise ValueError(f"Replay source must be self-contained; HDF5 link at {group.name}/{name}")
        node = group[name]
        if isinstance(node, h5py.Group):
            self_contained(node, visited)
        elif node.is_virtual or node.id.get_create_plist().get_external_count():
            raise ValueError(f"Replay source has virtual/external dataset storage at {node.name}")


@dataclass
class ReplaySource:
    directory: Path
    config: object
    launch_config: object
    seed: int
    options: dict
    commands: np.ndarray
    gripper: np.ndarray
    effort: np.ndarray
    phases: list
    intervals: np.ndarray
    manifest: dict


def configure_runtime(source: ReplaySource, *, zero_delay=True):
    """Apply an explicit renderer-only exception to source configuration.

    The source config object and files remain untouched. No physical/action,
    layout, seed, camera FPS or saved-position setting is overridden here.
    """
    original = source.config.env.get("render_zero_delay")
    source.launch_config.env.render_zero_delay = bool(zero_delay)
    source.manifest["source_config_authoritative_scope"] = "physics/control/action/layout/seed; renderer-only override below"
    source.manifest["runtime_overrides"] = {"env.render_zero_delay": {
        "source": original, "runtime": bool(zero_delay), "render_only": True,
        "basis": "Previously validated Hydra waitIdle and checkForHydraRenderComplete ordering; no extra world.step, physics/control dt, FPS or layout change."}}


def load_source(path) -> ReplaySource:
    path = Path(path).expanduser().resolve()
    directory = path if path.is_dir() else path.parent.parent
    config_path = directory / "config.yaml"
    candidates = list((directory / "dataset").glob("episode_*.h5")) if path.is_dir() else [path]
    if len(candidates) != 1 or not config_path.is_file():
        raise ValueError("Replay requires one closed episode directory with config.yaml and exactly one dataset/episode_*.h5")
    h5_path = candidates[0]
    cfg = OmegaConf.load(config_path)
    if str(cfg.version) != "Env_v1" or str(cfg.task_type) != "lab_cuvette_env_v1":
        raise ValueError("Replay only supports the formal Env_v1 source schema/task")
    hz = float(cfg.physics.control_hz)
    if hz != 60 or float(cfg.physics.hz) / hz != round(float(cfg.physics.hz) / hz):
        raise ValueError("Replay requires the source 60Hz control clock and an integer physical-step ratio")
    with h5py.File(h5_path, "r") as file:
        self_contained(file)
        attrs = {k: plain(v) for k, v in file.attrs.items()}
        if attrs.get("schema_version") != SCHEMA or attrs.get("executed_action_semantics") != SEMANTICS:
            raise ValueError("Replay source schema or nine-dimensional position command semantics differ")
        if attrs.get("complete") is not True:
            raise ValueError("Replay source episode is not complete/closed")
        if float(attrs.get("control_hz", -1)) != hz or float(attrs.get("physics_hz", -1)) != float(cfg.physics.hz):
            raise ValueError("Source H5/config clock mismatch")
        if any(str(attrs.get(key)) != str(expected) for key, expected in [
            ("scene_version", cfg.version), ("task_type", cfg.env.task_type),
            ("source_slot_id", cfg.rack.selected_slot_id), ("target_seat_id", cfg.adapter.selected_target_seat_id)]):
            raise ValueError("Source H5/config scene, task or slot identity mismatch")
        required = ["control_auxiliary/command_q", "control_auxiliary/gripper_target_m",
                    "control_auxiliary/gripper_effort_limit_N", "control_auxiliary/available",
                    "control_interval_s", "timestamp", "next_timestamp", "phase",
                    "partial_terminal_control_interval", "episode_id"]
        if any(key not in file for key in required):
            raise ValueError("Replay source is missing full command, effort, phase or time records")
        q = np.asarray(file[required[0]][:], float)
        gripper = np.asarray(file[required[1]][:], float)
        effort = np.asarray(file[required[2]][:], float)
        dt = np.asarray(file["control_interval_s"][:], float)
        t = np.asarray(file["timestamp"][:], float)
        nt = np.asarray(file["next_timestamp"][:], float)
        phases = [plain(value) for value in file["phase"][:]]
        n = len(q)
        if not n or q.shape != (n, 9) or effort.shape != (n, 2) or any(a.shape != (n,) for a in [gripper, dt, t, nt]):
            raise ValueError("Replay source has invalid or empty command/time shapes")
        if not all(np.isfinite(a).all() for a in [q, gripper, effort, dt, t, nt]):
            raise ValueError("Replay source command/time is nonfinite")
        if len(phases) != n or not file["control_auxiliary/available"][:].all():
            raise ValueError("Replay source command auxiliary data unavailable")
        if np.asarray(file["partial_terminal_control_interval"][:], bool).any() or not np.allclose(dt, 1 / hz, atol=1e-9, rtol=0):
            raise ValueError("Partial/non-60Hz control intervals cannot be faithfully replayed")
        if not np.allclose(nt - t, dt, atol=1e-9, rtol=0) or not np.allclose(t[1:], nt[:-1], atol=1e-9, rtol=0):
            raise ValueError("Replay source time/obs-successor alignment is discontinuous")
        if any(plain(value) != attrs.get("episode_id") for value in file["episode_id"][:]):
            raise ValueError("Replay source contains mixed episode IDs")
        if not np.allclose(q[:, 7:].sum(axis=1), 2 * gripper, atol=1e-8, rtol=0):
            raise ValueError("Replay source full9 finger commands contradict saved gripper target")
    result_path = directory / "result.json"
    if not result_path.is_file():
        raise ValueError("Replay requires the finalized source result.json")
    result = json.loads(result_path.read_text())
    if result.get("complete") is not True or result.get("episode_id") != attrs.get("episode_id"):
        raise ValueError("Replay source result is incomplete or belongs to another episode")
    seed = int(cfg.env.seed)
    options = dict(mode=str(cfg.env.mode), subtask=str(cfg.env.task_type),
                   source_slot_id=str(cfg.rack.selected_slot_id), policy_id="saved_joint_command_replay",
                   demonstrator_id="recorded_control_auxiliary", truth_visible=False)
    launch = OmegaConf.create(OmegaConf.to_container(cfg, resolve=True))
    if options["mode"] == "random":
        actual = cfg.randomization.get("actual")
        if actual is None or int(actual.seed) != seed:
            raise ValueError("Random replay requires the actual saved perturbation and matching seed; refusing double randomization")
        for target, field, key in [(launch.rack, "origin_m", "rack_translation_m"),
                                   (launch.scene, "instrument_xyz_m", "instrument_assembly_translation_m")]:
            delta = np.asarray(actual[key], float)
            if delta.shape != (2,) or not np.isfinite(delta).all():
                raise ValueError("Invalid saved random assembly translation")
            target[field] = (np.asarray(target[field], float) - np.r_[delta, 0]).tolist()
    manifest = dict(schema="labsim.Env_v1.command_replay_source.v1", source_episode=str(directory),
        source_config=str(config_path), source_h5=str(h5_path), source_result=str(result_path),
        source_config_sha256=sha256(config_path), source_h5_sha256=sha256(h5_path),
        source_result_sha256=sha256(result_path), source_episode_id=attrs["episode_id"],
        source_labels={k: attrs.get(k) for k in ["task_success", "record_valid", "failure_type", "termination_reason", "task_type"]},
        source_control_rows=n, source_control_hz=hz, source_physics_hz=float(cfg.physics.hz),
        source_phase_semantics="Saved pre-action observation phase; retained as source_phase, not a teacher phase.",
        source_config_authoritative=True, runtime_random_base_reconstructed=options["mode"] == "random",
        source_success_inherited=False, object_pose_setters_used=False, teacher_used=False)
    return ReplaySource(directory, cfg, launch, seed, options, q, gripper, effort, phases, dt, manifest)


def execute_replay(env, source: ReplaySource, output, *, max_ticks=None):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    if max_ticks is not None and max_ticks < 1:
        raise ValueError("replay-max-ticks must be positive")
    count = len(source.commands) if max_ticks is None else min(max_ticks, len(source.commands))
    write(output / "replay_source.json", source.manifest)
    obs, info = env.reset(source.seed, source.options)
    summary = dict(schema="labsim.Env_v1.command_replay_result.v1", source=source.manifest,
                   episode_id=obs["episode_id"], requested_control_ticks=count, executed_control_ticks=0,
                   startup_terminated=bool(info.get("terminated")), original_success_inherited=False,
                   exact_executed_commands=None, command_difference_max_abs=None, control_method="normal typed joint_position",
                   mixed_numeric_difference_note="Legacy max of native rad/m components, not a physical norm or contact accuracy.",
                   max_arm_joint_difference_rad=None, max_finger_difference_m=None,
                   source_phase_preserved_in_command_trace=True)
    if not info.get("terminated"):
        for index in range(count):
            if not env.app.is_running():
                break
            q = source.commands[index]
            action = dict(episode_id=obs["episode_id"], observation_step=obs["step_index"],
                type="joint_position", frame="joint", values=q.tolist(),
                gripper_opening_m=float(2 * source.gripper[index]),
                gripper_effort_limit_N=source.effort[index].tolist(), duration_s=float(source.intervals[index]),
                raw_output=dict(source_control_row=index, command_q9=q.tolist(), source_phase=source.phases[index]),
                metadata=dict(phase="REPLAY", source_phase=source.phases[index], source_control_row=index))
            before = obs["step_index"]
            obs, _, terminated, truncated, info = env.step(action)
            actual = np.asarray(env.qcmd).copy()
            difference = float(np.max(np.abs(actual - q)))
            previous = summary["command_difference_max_abs"]
            summary["command_difference_max_abs"] = difference if previous is None else max(previous, difference)
            for key, value in [("max_arm_joint_difference_rad", float(np.max(np.abs(actual[:7] - q[:7])))),
                               ("max_finger_difference_m", float(np.max(np.abs(actual[7:] - q[7:]))))]:
                summary[key] = value if summary[key] is None else max(summary[key], value)
            summary["executed_control_ticks"] += int(obs["step_index"] - before)
            with (output / "replay_commands.jsonl").open("a") as file:
                file.write(json.dumps(plain(dict(source_control_row=index, source_phase=source.phases[index],
                    source_command_q9=q, requested_action=action, actual_command_q9=actual,
                    source_effort_limit_N=source.effort[index], actual_effort_limit_N=getattr(env, "effort", None),
                    max_abs_command_difference=difference, successor_step_index=obs["step_index"],
                    successor_simulation_time=obs["simulation_time"], terminated=terminated, truncated=truncated)), allow_nan=False) + "\n")
            if terminated or truncated:
                break
    reason = "REPLAY_SOURCE_EXHAUSTED" if count == len(source.commands) else "REPLAY_TICK_BUDGET"
    interrupted = not env.app.is_running() and summary["executed_control_ticks"] < count
    final = env.finalize_episode("APPLICATION_INTERRUPTED" if interrupted else reason,
                                 "PROCESS_INTERRUPTED" if interrupted else None)
    summary.update(independent_result=final, exact_executed_commands=None if summary["command_difference_max_abs"] is None else summary["command_difference_max_abs"] <= 1e-12,
                   bitwise_physical_replay_claimed=False,
                   source_files_unchanged=all(sha256(source.manifest[key]) == source.manifest[key + "_sha256"]
                                              for key in ["source_h5", "source_config", "source_result"]))
    write(output / "replay_result.json", summary)
    print("REPLAY_RESULT", json.dumps(plain(summary), allow_nan=False), flush=True)
    return summary
