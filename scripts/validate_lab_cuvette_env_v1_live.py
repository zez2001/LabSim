#!/usr/bin/env python3
"""Validate a retained real Env_v1 RPC; never starts Isaac or a model.

Run in the deployed RPent .venv. This deliberately creates small API-test
episodes, including random *initialization* checks, not task evaluation batches.
Local server sidecars are audit-only and never become policy observations.
"""
from __future__ import annotations

import argparse
import copy
import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

import numpy as np
import yaml
from PIL import Image
from rpent.utils.rpc.http_rpc import HttpRpcClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def compact(value):
    if isinstance(value, np.ndarray):
        result = {"shape": list(value.shape), "dtype": str(value.dtype),
                  "sha256": hashlib.sha256(value.tobytes()).hexdigest()}
        if value.size <= 64:
            result["values"] = value.tolist()
        return result
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {str(k): compact(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [compact(v) for v in value]
    if isinstance(value, Path):
        return str(value)
    return value


def state(obs):
    return {k: compact(obs[k]) for k in ("episode_id", "step_index", "simulation_time",
            "joint_positions", "joint_velocities", "TCPpose", "source_slot_id", "target_seat_id")}


class AttrMap(dict):
    __getattr__ = dict.__getitem__


def attr(value):
    if isinstance(value, dict):
        return AttrMap({k: attr(v) for k, v in value.items()})
    if isinstance(value, list):
        return [attr(v) for v in value]
    return value


class Validation:
    def __init__(self, args):
        self.args = args
        self.out = Path(args.output).resolve()
        self.out.mkdir(parents=True, exist_ok=False)
        self.client = HttpRpcClient(args.endpoint)
        self.server_root = Path(args.server_output).resolve()
        self.evidence = {"schema": "labsim.Env_v1.actual_live_api_validation.v1",
            "scope": "Actual retained Isaac RPC, not mock. Random checks cover initialization only; not a formal task batch.",
            "started_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "endpoint": args.endpoint, "output": str(self.out), "server_output": str(self.server_root),
            "command": [sys.executable, *sys.argv],
            "git_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "checks": [], "episodes": [], "model_calls_by_this_validator": 0,
            "real_calibrated": False, "full_loading_evaluations": 0}

    def save(self):
        text = json.dumps(compact(self.evidence), indent=2, allow_nan=False) + "\n"
        (self.out / "validation.json").write_text(text)
        target = Path(self.args.evidence).resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)

    def check(self, name, passed, **details):
        self.evidence["checks"].append(dict(name=name, passed=bool(passed), **compact(details)))
        self.save()
        print(json.dumps({"check": name, "passed": bool(passed)}), flush=True)

    def call(self, method, *, args=(), kwargs=None, timeout_s=180):
        event = dict(method=method, args=compact(args), kwargs=compact(kwargs or {}),
                     started_wall_unix_s=time.time())
        started = time.perf_counter()
        try:
            result = self.client.call(method, args=args, kwargs=kwargs, timeout_s=timeout_s)
            event.update(ok=True, result=compact(result))
            return result
        except Exception as error:
            event.update(ok=False, error_type=type(error).__name__, error=str(error))
            raise
        finally:
            event["wall_time_s"] = time.perf_counter() - started
            with (self.out / "requests.jsonl").open("a") as file:
                file.write(json.dumps(event, allow_nan=False) + "\n")

    def observe(self):
        return self.call("env.get_observation")

    def reset(self, mode, seed, subtask="preinsert_diagnostic"):
        previous = set(self.server_root.glob("episode_*"))
        obs, info = self.call("env.reset", kwargs={"seed": seed, "options": {
            "mode": mode, "subtask": subtask, "policy_id": "live_api_validation",
            "demonstrator_id": "none", "truth_visible": False}}, timeout_s=180)
        created = set(self.server_root.glob("episode_*")) - previous
        entry = dict(episode_id=obs["episode_id"], mode=mode, seed=seed, subtask=subtask,
                     initial_public_state=state(obs), reset_info=compact(info),
                     directory=str(next(iter(created))) if len(created) == 1 else None)
        self.evidence["episodes"].append(entry)
        if entry["directory"]:
            directory = Path(entry["directory"])
            cfg = yaml.safe_load((directory / "config.yaml").read_text())
            initial = json.loads((directory / "initial_debug.json").read_text())
            # Uses the actual saved configuration and recorded source pose;
            # this local audit is separate from the public RPC observation.
            from demos.lab_cuvette_demo04.scene import layout
            assembly = layout(attr(cfg))
            entry["audit_only_assembly"] = compact({k: assembly[k] for k in (
                "source_floor", "target_floor", "target_origin_in_instrument",
                "rack_origin", "rack_rotation", "instrument_origin", "instrument_rotation")})
            entry["audit_only_configuration"] = {"rack": cfg["rack"], "scene": cfg["scene"],
                "randomization": cfg["randomization"]}
            entry["audit_only_initial_support"] = {k: initial.get(k) for k in (
                "object_position_m", "source_rack_penetration_m", "source_bottom_gap_m",
                "source_reference_inside", "source_clearance_m", "tilt_deg")}
            manifest = directory / "geometry_audit_binding.json"
            if manifest.exists():
                audit = json.loads(manifest.read_text())
                entry["geometry_audit_fingerprint"] = audit.get("binding", {}).get("fingerprint")
        self.check(f"reset_{mode}_{seed}_{len(self.evidence['episodes'])}",
                   obs["step_index"] == 0 and info["debug_exposed"] is False,
                   episode_id=obs["episode_id"], info=info)
        return obs, info, entry

    @staticmethod
    def command(obs, duration=.05):
        return dict(episode_id=obs["episode_id"], observation_step=int(obs["step_index"]),
                    type="joint_velocity", values=[0.] * 7, frame="joint", duration_s=duration,
                    gripper_opening_m=float(np.asarray(obs["joint_positions"])[7:].sum()),
                    gripper_effort_limit_N=8.0, metadata={"phase": "API_VALIDATION"})

    def reject_without_advance(self, name, action):
        before = self.observe()
        error = None
        try:
            self.call("env.step", args=(action,))
        except Exception as exc:
            error = str(exc)
        after = self.observe()
        self.check(name, error is not None and after["step_index"] == before["step_index"]
                   and after["simulation_time"] == before["simulation_time"],
                   error=error, before=state(before), after=state(after))

    def finish(self, obs):
        return self.call("env.finalize_episode", kwargs={"episode_id": obs["episode_id"],
                        "termination_reason": "API_VALIDATION_BUDGET", "failure_type": "TASK_INCOMPLETE"})

    def compare(self, name, first, second):
        a, b = first[0], second[0]
        dq = float(np.max(np.abs(np.asarray(a["joint_positions"]) - np.asarray(b["joint_positions"]))))
        dp = float(np.max(np.abs(np.asarray(a["TCPpose"]["position_m"]) - np.asarray(b["TCPpose"]["position_m"]))))
        qa = np.asarray(a["TCPpose"]["quaternion_wxyz"])
        qb = np.asarray(b["TCPpose"]["quaternion_wxyz"])
        dquat = min(float(np.max(np.abs(qa - qb))), float(np.max(np.abs(qa + qb))))
        self.check(name, a["episode_id"] != b["episode_id"] and dq <= 1e-6 and dp <= 1e-6 and dquat <= 1e-6
                   and a["source_slot_id"] == b["source_slot_id"] and a["target_seat_id"] == b["target_seat_id"],
                   max_abs_joint_difference_rad_or_m=dq, max_abs_tcp_difference_m=dp,
                   quaternion_sign_aware_max_difference=dquat,
                   check_tolerances={"joint_coordinates": 1e-6, "tcp_m": 1e-6, "quaternion_component": 1e-6},
                   scope="Observed reset repeatability, not calibrated physical accuracy or task success.")

    def run(self):
        meta = self.call("env.get_env_meta")
        self.evidence["launch_metadata"] = meta
        current = self.observe()
        language = self.call("env.get_task_language")
        self.check("public_observation_contract", isinstance(language, str) and bool(language)
                   and not set(current).intersection({"debug", "object_pose", "object_position_m", "target_error", "teacher_internal"}),
                   keys=list(current), state=state(current), language=language)
        for name in ("side_camera", "wrist_camera"):
            image = self.call("env.render_camera", args=(name,))
            cm = self.call("env.get_camera_meta", args=(name,))
            Image.fromarray(image).save(self.out / (name + "_current.png"))
            self.check("render_and_meta_" + name, image.dtype == np.uint8 and image.ndim == 3 and image.shape[-1] == 3
                       and cm.get("channels") == "RGB" and cm.get("intrinsic_matrix_native") is not None,
                       image=image, camera_name=cm.get("name"), mounting=cm.get("mounting"),
                       resolution_wh=cm.get("resolution_wh"),
                       raw_metadata_contains_renderer_debug="renderer_debug" in cm,
                       note="Live RPC started before later default-metadata sanitization; model Toolkit independently whitelists metadata.")
        before = self.observe()
        started = time.perf_counter()
        time.sleep(self.args.pause_s)
        after = self.observe()
        self.check("actual_idle_physics_pause", before["step_index"] == after["step_index"]
                   and before["simulation_time"] == after["simulation_time"]
                   and np.array_equal(before["joint_positions"], after["joint_positions"]),
                   waited_wall_s=time.perf_counter() - started, before=state(before), after=state(after))
        obs, _, _ = self.reset("standard", 41)
        start = state(obs)
        obs, _, terminated, truncated, _ = self.call("env.step", args=(self.command(obs),))
        self.check("joint_velocity_zero_005s_three_ticks", obs["step_index"] == start["step_index"] + 3
                   and abs(obs["simulation_time"] - start["simulation_time"] - .05) < 1e-10
                   and not terminated and not truncated, before=start, after=state(obs))
        start = state(obs)
        action = self.command(obs, 1 / float(meta["control_hz"]))
        frames, _, terminated, truncated, _ = self.call("env.chunk_step", args=([action, copy.deepcopy(action)],),
                                                       kwargs={"return_all_frames": True})
        self.check("two_action_chunk_all_frames", isinstance(frames, list) and len(frames) == 2
                   and [x["step_index"] for x in frames] == [start["step_index"] + 1, start["step_index"] + 2]
                   and abs(frames[-1]["simulation_time"] - start["simulation_time"] - 2 / float(meta["control_hz"])) < 1e-10
                   and not terminated and not truncated, before=start, after=[state(x) for x in frames])
        obs = frames[-1]
        self.reject_without_advance("invalid_duration_rejected_no_advance", self.command(obs, .02))
        stale = self.command(obs)
        stale["observation_step"] -= 1
        self.reject_without_advance("stale_step_rejected_no_advance", stale)
        final = self.finish(obs)
        self.check("finalize_and_flush", final.get("complete") is True and final.get("task_success") is False,
                   final=final)
        self.reject_without_advance("terminated_episode_rejects_action", self.command(obs))
        first = self.reset("standard", 41)
        self.reject_without_advance("old_episode_rejected_after_reset", self.command(obs))
        self.finish(first[0])
        second = self.reset("standard", 41)
        self.compare("standard_same_seed_reset_repeatability", first, second)
        self.finish(second[0])
        first = self.reset("random", 7)
        self.finish(first[0])
        second = self.reset("random", 7)
        self.compare("random_seed7_reset_repeatability", first, second)
        a, b = first[2], second[2]
        support = b.get("audit_only_initial_support", {})
        self.check("random_B1_legal_source_and_rigid_assemblies", first[0]["source_slot_id"] == "B1"
                   and a.get("audit_only_configuration") == b.get("audit_only_configuration")
                   and a.get("audit_only_assembly") == b.get("audit_only_assembly")
                   and support.get("source_reference_inside") is True
                   and support.get("source_rack_penetration_m", 1.) <= .00005,
                   assembly=b.get("audit_only_assembly"), configuration=b.get("audit_only_configuration"),
                   observed_initial_support=support,
                   scope="Local saved configuration plus observed initial source containment; not robot reachability or full random task success.")
        self.finish(second[0])
        native = self.reset("standard", 0, "loading")
        info = native[1]
        self.check("native_loading_preflight_terminated", info.get("terminated") is True
                   and info.get("termination_reason") == "GEOMETRY_PRECHECK_BLOCKED"
                   and native[0]["step_index"] == 0 and info.get("geometry_valid") is False,
                   reset_info=info, public_state=state(native[0]),
                   note="Reset gravity/camera initialization physics is recorded; zero insertion/control steps and zero model calls.")
        self.reject_without_advance("native_gate_rejects_insertion_action", self.command(native[0]))

    def shutdown(self):
        response = self.call("shutdown", timeout_s=30)
        polls = []
        stopped = False
        for _ in range(30):
            try:
                response_health = self.client.call("healthz", timeout_s=1)
                polls.append({"reachable": True, "response": response_health})
            except Exception as error:
                polls.append({"reachable": False, "error_type": type(error).__name__, "error": str(error)})
                stopped = True
                break
            time.sleep(.5)
        self.evidence["shutdown"] = dict(response=response, readiness_polls=polls, endpoint_closed=stopped,
            launcher_exit_confirmation="Parent must poll retained launcher session; TCP closure alone does not prove app exit.")
        self.check("graceful_rpc_endpoint_closed", stopped)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", default="http://127.0.0.1:8097")
    parser.add_argument("--server-output", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--pause-s", type=float, default=2.)
    parser.add_argument("--shutdown", action="store_true", help="Gracefully stop this retained environment after validation")
    args = parser.parse_args()
    if not 0 < args.pause_s <= 30:
        parser.error("pause-s must be positive and <=30")
    validation = Validation(args)
    try:
        validation.run()
    except Exception as error:
        validation.evidence["unexpected_error"] = dict(error_type=type(error).__name__, error=str(error))
        validation.check("validation_completed_without_unexpected_error", False, error=str(error))
    finally:
        if args.shutdown:
            try:
                validation.shutdown()
            except Exception as error:
                validation.evidence["shutdown_error"] = str(error)
        validation.evidence["finished_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        validation.evidence["all_checks_passed"] = all(x["passed"] for x in validation.evidence["checks"])
        validation.save()
    return 0 if validation.evidence["all_checks_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
