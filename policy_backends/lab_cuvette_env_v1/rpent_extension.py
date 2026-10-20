"""LabSim extension of the already installed RLinf/RPent contracts.

Import in RPent's separate Python environment, not Isaac's. The facade accepts
an existing LabSim env and can be constructed inside its main-thread RPC loop;
it does not spawn Isaac or load a checkpoint.  Toolkits expose no expert call.
"""
from __future__ import annotations

import io
import hashlib
import json
import time
from pathlib import Path

import numpy as np
from PIL import Image

from rpent.dashboard.events import NullDashboardEventSink
from rpent.memory import MemoryManager
from rpent.robots.components.env_client_base import BaseEnvClient
from rpent.robots.components.env_facade_base import BaseEnvFacade
from rpent.robots.prompt_bundle import PromptBundle
from rpent.robots.robot_spec import RobotSpec, RunConfig
from rpent.session import EnvState
from rpent.tools.toolkit import Toolkit, readonly
from rpent.utils.rpc.http_rpc import HttpRpcClient

from .policy_adapters import Pi05LiberoAdapter, append_event, policy_observation


class LabSimEnvFacade(BaseEnvFacade):
    def __init__(self, environment, *, launch_meta: dict):
        self.env = environment
        self.launch_meta = launch_meta
        super().__init__()

    def _register_rpc(self):
        super()._register_rpc()
        self._rpc["env.get_observation"] = self.get_observation
        self._rpc["env.close"] = self.close
        self._rpc["env.finalize_episode"] = self.finalize_episode
        self._readonly_methods.add("env.get_observation")

    def get_env_meta(self):
        return self.launch_meta

    def reset(self, seed=None, options=None):
        return self.env.reset(seed=seed, options=options)

    def step(self, action):
        return self.env.step(action)

    def chunk_step(self, actions, *, return_all_frames=False):
        return self.env.chunk_step(actions, return_all_frames=return_all_frames)

    def get_observation(self):
        return self.env.get_observation()

    def render_camera(self, camera_name, **kwargs):
        return self.env.render_camera(camera_name, **kwargs)

    def get_camera_meta(self, camera_name, **kwargs):
        return self.env.get_camera_meta(camera_name, **kwargs)

    def get_task_language(self):
        return self.env.get_task_language()

    def finalize_episode(self, termination_reason="POLICY_BUDGET", failure_type=None, episode_id=None):
        if episode_id is not None and episode_id != getattr(self.env, "episode_id", None):
            raise ValueError("stale episode finalization refused")
        return self.env.finalize_episode(termination_reason=termination_reason, failure_type=failure_type)

    def close(self):
        self.env.close()


class LabSimEnvClient(BaseEnvClient):
    """Actual BaseEnvClient wire contract with explicit seed and public obs."""
    def __init__(self, rpc, *, expected_meta=None, reset_on_connect=False, ready_timeout_s=60.0):
        from rpent.utils.rpc import wait_for_ready
        self._client = rpc
        wait_for_ready(rpc, timeout_s=float(ready_timeout_s))
        actual = rpc.call("env.get_env_meta", timeout_s=30)
        if expected_meta is not None and actual != expected_meta:
            raise ValueError(f"server/client launch metadata differ: {actual!r}")
        self.meta = actual
        self.last_obs = None
        self.active_episode_id = None
        self.last_info = {}
        if reset_on_connect:
            self.reset()

    def reset(self, seed=None, options=None):
        result = self._client.call("env.reset", kwargs={"seed": seed, "options": options}, timeout_s=120)
        self.last_obs, self.last_info = result
        self.active_episode_id = self.last_obs["episode_id"]
        return result

    def get_observation(self):
        current = self._client.call("env.get_observation", timeout_s=30)
        if self.active_episode_id is not None and current["episode_id"] != self.active_episode_id:
            raise RuntimeError("environment episode changed outside this controller; reset its history before continuing")
        self.last_obs = current
        if self.active_episode_id is None:
            self.active_episode_id = current["episode_id"]
        return self.last_obs

    def finalize_episode(self, termination_reason="POLICY_BUDGET", failure_type=None):
        return self._client.call("env.finalize_episode", kwargs={"termination_reason": termination_reason, "failure_type": failure_type, "episode_id": self.active_episode_id}, timeout_s=120)

    def close(self):
        return self._client.call("env.close", timeout_s=30)


def _schema(name, description, properties=None, required=None):
    return {"name": name, "description": description,
            "input_schema": {"type": "object", "properties": properties or {},
                             "required": required or [], "additionalProperties": False}}


class LabSimToolkit(Toolkit):
    """RPent planner tools. direct mode has only observe, action and finish.

    Harness mode additionally exposes a real VLA checkpoint primitive, bounded
    to five model actions. It never wraps a full loading script or teacher.
    Both modes use an empty, frozen per-episode memory repository.
    """
    def __init__(self, env_client: LabSimEnvClient, *, output_dir, mode="direct",
                 vla_adapter: Pi05LiberoAdapter | None = None,
                 dashboard_events=None, maximum_action_calls=1000):
        if mode not in {"direct", "harness"}:
            raise ValueError("mode must be direct or harness")
        if mode == "harness" and vla_adapter is None:
            raise ValueError("Harness mode requires a real checkpoint client")
        if mode == "direct" and vla_adapter is not None:
            raise ValueError("Direct mode forbids a VLA client")
        self.env = env_client
        self.mode = mode
        self.vla = vla_adapter
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        memory_root = self.output_dir / "frozen_empty_memory"
        memory_root.mkdir(exist_ok=False)
        self._action_calls = 0
        self._maximum_action_calls = int(maximum_action_calls)
        self._task_success = None
        self._last_motion_result = None
        self._input_images = {}
        super().__init__(dashboard_events=dashboard_events or NullDashboardEventSink(),
                         state=EnvState(self.output_dir / "rpent_states"),
                         memory=MemoryManager(memory_root, memory_access="read_only"))
        # No file read/write, shell, teacher or VLA tool can escape this allowlist.
        self._tools.clear()
        self.add_tool("observe", _schema("observe", "Read current real side and wrist camera images and robot proprioception; physics stays paused."), self.observe)
        self.add_tool("bounded_action", _schema("bounded_action", "Execute ONE bounded low-level EE delta or joint delta. Does not plan grasping or loading.", {
            "kind": {"enum": ["ee_delta", "joint_delta"]},
            "values": {"type": "array", "items": {"type": "number"}, "description": "ee_delta=[world dx,dy,dz in metres, spatial rotvec rx,ry,rz in radians]; joint_delta=[dq1..dq7] in radians. Caps are 2mm/0.02rad per axis."},
            "gripper_opening_m": {"type": "number", "minimum": 0, "maximum": 0.08, "description": "Total two-finger opening in metres: 0 closed, .08 fully open. Not single-finger position."},
            "duration_s": {"type": "number", "minimum": 1/60, "maximum": .05},
        }, ["kind", "values", "gripper_opening_m"]), self.bounded_action)
        self.add_tool("finish", _schema("finish", "End this planner attempt. Task success is computed independently by the environment.", {
            "status": {"enum": ["success", "failure", "stuck"]}, "summary": {"type": "string"}}, ["status", "summary"]), self.finish)
        if mode == "harness":
            self.add_tool("vla_primitive", _schema("vla_primitive", "Call the actual selected pi0.5 checkpoint with the current two real views and language, then execute a bounded short action chunk.", {
                "instruction": {"type": "string"}, "maximum_actions": {"type": "integer", "minimum": 1, "maximum": 5}}, ["instruction"]), self.vla_primitive)

    def get_tools_spec(self):
        # RPent's default template lookup requires CLI-global init_output_dir.
        # The reusable extension supplies its per-run variable explicitly.
        from rpent.utils.templates import substitute
        return substitute([spec for spec, _ in self._tools.values()],
                          variables={"output_dir": str(self.output_dir)})

    def _observation_payload(self):
        obs = policy_observation(self.env.get_observation())
        payload = {key: value.tolist() if isinstance(value, np.ndarray) else value
                   for key, value in obs.items() if key != "images"}
        payload["camera_meta"] = {name: self.env.get_camera_meta(name) for name in ("side_camera", "wrist_camera")}
        for name, result_key in (("side_camera", "_image_cam_bytes"), ("wrist_camera", "_image_wrist_bytes")):
            rgb = np.asarray(obs["images"][name])
            if rgb.dtype != np.uint8 or rgb.ndim != 3 or rgb.shape[-1] != 3:
                raise ValueError(f"invalid actual camera {name}")
            out = io.BytesIO()
            Image.fromarray(rgb).save(out, format="PNG")
            data = out.getvalue()
            payload[result_key] = data
            target = self.output_dir / "policy_inputs" / str(obs["episode_id"]) / f"{int(obs['step_index']):06d}_{name}.png"
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                target.write_bytes(data)
            image_record = {"path": str(target.relative_to(self.output_dir)), "sha256": hashlib.sha256(data).hexdigest(), "camera_name": name}
            self._input_images[name] = image_record
        payload["model_image_inputs"] = dict(self._input_images)
        return payload

    @readonly
    def observe(self):
        result = self._observation_payload()
        append_event(self.output_dir / "policy_tools.jsonl", {"event": "observe", "episode_id": result.get("episode_id"), "step_index": result.get("step_index"), "wall_time": time.time()})
        return result

    def _consume_action(self):
        self.raise_if_cancelled()
        if self._action_calls >= self._maximum_action_calls:
            raise RuntimeError("declared planner action call budget reached")
        self._action_calls += 1

    def bounded_action(self, kind, values, gripper_opening_m, duration_s=.05):
        self._consume_action()
        obs = self.env.get_observation()
        values = np.asarray(values, dtype=float)
        size = 6 if kind == "ee_delta" else 7 if kind == "joint_delta" else None
        if size is None or values.shape != (size,) or not np.isfinite(values).all():
            raise ValueError("expected finite ee_delta[6] or joint_delta[7]")
        raw = values.copy()
        if kind == "ee_delta":
            values[:3] = np.clip(values[:3], -.002, .002)
            values[3:] = np.clip(values[3:], -.02, .02)
            action_type = "ee_delta"
        else:
            values = np.asarray(obs["joint_positions"][:7]) + np.clip(values, -.02, .02)
            action_type = "joint_position"
        if not 0 <= float(gripper_opening_m) <= .08:
            raise ValueError("gripper opening must be [0,.08] m")
        if not 1/60 <= float(duration_s) <= .05:
            raise ValueError("action duration outside declared range")
        command = {"episode_id": obs["episode_id"], "observation_step": int(obs["step_index"]),
                   "type": action_type, "values": values.tolist(), "gripper_opening_m": float(gripper_opening_m),
                   "frame": "world", "duration_s": float(duration_s), "gripper_effort_limit_N": 8.0,
                   "raw_model_action": raw.tolist(),
                   "conversion": {"source": "astra_low_level_tool", "raw_kind": kind,
                                  "clipping_translation_m": .002, "clipping_rotation_rad": .02,
                                  "clipping_joint_delta_rad": .02, "gripper_semantics": "total_two_finger_opening_m"}}
        result = self.env.step(command)
        self._last_motion_result = result
        self._task_success = result[4].get("task_success")
        append_event(self.output_dir / "policy_tools.jsonl", {"event": "bounded_action", "raw_kind": kind,
                     "raw_values": raw, "executed_envelope": command, "reward": result[1],
                     "terminated": result[2], "truncated": result[3], "task_success": self._task_success,
                     "simulation_time": result[0].get("simulation_time")})
        return {"action": command, "terminated": result[2], "truncated": result[3], "task_success": self._task_success}

    def vla_primitive(self, instruction, maximum_actions=5):
        if self.vla is None or self.mode != "harness":
            raise RuntimeError("VLA is not available in direct mode")
        if not 1 <= int(maximum_actions) <= 5:
            raise ValueError("maximum_actions outside [1,5]")
        obs = self.env.get_observation()
        # Only the language is planner controlled; images and robot state stay real.
        model_obs = dict(obs, task_language=str(instruction))
        raw, inference = self.vla.infer(model_obs)
        append_event(self.output_dir / "policy_tools.jsonl", {"event": "vla_inference", "instruction": instruction, "inference": inference, "raw_actions": raw})
        executed = []
        for row in raw[:int(maximum_actions)]:
            self._consume_action()
            command = self.vla.convert_action(row, obs)
            command["inference_wall_time_s"] = inference["inference_wall_s"]
            command["policy_inference_call"] = inference["inference_call"]
            result = self.env.step(command)
            self._last_motion_result = result
            obs = result[0]
            self._task_success = result[4].get("task_success")
            executed.append(command)
            append_event(self.output_dir / "policy_tools.jsonl", {"event": "vla_action", "executed_envelope": command,
                         "terminated": result[2], "truncated": result[3], "task_success": self._task_success})
            if result[2] or result[3]:
                break
        return {"actual_vla_called": True, "checkpoint_id": self.vla.contract.checkpoint_id, "executed_actions": executed,
                "task_success": self._task_success, "inference_wall_s": inference["inference_wall_s"]}

    @readonly
    def finish(self, status, summary):
        return {"_finish": True, "status": status, "summary": summary,
                "environment_task_success": self._task_success}

    def get_env_state(self, *, command, result, elapsed_s):
        # Toolkit's standard tracing calls this after every physical tool.
        # Explicit traces above retain command/raw output; all returned images
        # are acquired again from the current physical state without stepping.
        payload = self._observation_payload()
        payload.update({"tool_result": result, "elapsed_s": elapsed_s})
        motion = self._last_motion_result
        state = {k: v for k, v in payload.items() if not k.startswith("_image")}
        with self.state.record_step(state=state, command=command, result=result,
                                    terminated=bool(motion and motion[2]), truncated=bool(motion and motion[3]),
                                    elapsed_s=elapsed_s):
            for name, key in (("side_camera", "_image_cam_bytes"), ("wrist_camera", "_image_wrist_bytes")):
                self.state.save(name + ".png", np.asarray(Image.open(io.BytesIO(payload[key]))))
        return payload

    def solved(self):
        return self._task_success is True

    def close(self):
        try:
            result = self.env.finalize_episode(termination_reason="PLANNER_ENDED")
            append_event(self.output_dir / "policy_tools.jsonl", {"event": "environment_finalized", "result": result})
            if isinstance(result, dict) and "task_success" in result:
                self._task_success = result["task_success"]
        except Exception as exc:
            append_event(self.output_dir / "policy_tools.jsonl", {"event": "finalization_failed", "error": str(exc)})


def _system_prompt(variables=None):
    return ("Control the LabSim Franka using the provided real side and wrist images and robot proprioception. "
            "Do not access hidden scorer state, expert scripts or files. Each bounded_action is a single small movement; "
            "inspect feedback. The simulator pauses during reasoning. The environment, not finish(), decides task success. "
            "In direct mode no VLA primitive is available. In Harness mode use actual vla_primitive calls and inspect results.")


def _user_prompt(variables=None):
    return "{{task_language}}"


def get_robot_spec() -> RobotSpec:
    def add_args(parser, use_dashboard):
        parser.add_argument("--env-endpoint", required=True)
        parser.add_argument("--vla-endpoint")
        parser.add_argument("--seed", type=int, default=0)
        parser.add_argument("--robot-base-position-m", type=float, nargs=3)
        parser.add_argument("--labsim-mode", choices=["direct", "harness"], default="direct")
        parser.add_argument("--subtask", choices=["loading", "preinsert_diagnostic"], default="loading")
    def parse(args):
        out = Path(args.output_dir) if args.output_dir else Path("outputs/lab_cuvette_loading/Env_v1/rpent_runs") / (time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + f"_seed{args.seed}")
        return RunConfig(recipe_tag=f"labsim_s{args.seed}", output_dir=out,
                         prompt_vars={"task_language": "Load the cuvette from the source rack into the instrument's selected internal seat."},
                         task_desc={"task": "lab_cuvette_loading", "version": "Env_v1", "seed": args.seed})
    def runtime(args, output_dir, events, components):
        # Explicitly attach only: no implicit process creation, shared GPU model
        # lifecycle remains under the caller's sequential scheduling.
        env_rpc = HttpRpcClient(args.env_endpoint)
        kwargs = {"env_client": LabSimEnvClient(env_rpc), "mode": args.labsim_mode}
        kwargs["env_client"].reset(seed=args.seed, options={"subtask": args.subtask})
        if args.labsim_mode == "harness":
            if not args.vla_endpoint:
                raise ValueError("Harness requires --vla-endpoint of an actual checkpoint server")
            base = args.robot_base_position_m or kwargs["env_client"].meta.get("robot_base_position_m")
            if base is None:
                raise ValueError("actual robot base transform is required for LIBERO transfer")
            kwargs["vla_adapter"] = Pi05LiberoAdapter(HttpRpcClient(args.vla_endpoint), robot_base_position_m=base)
        return [], kwargs
    return RobotSpec(name="labsim_cuvette", prompts=PromptBundle(system=_system_prompt, user=_user_prompt),
                     add_cli_args=add_args, parse_config=parse, init_runtime=runtime,
                     memory_repo_id="labsim/frozen_empty_no_download")


def get_toolkit(*, primitives_kwargs, dashboard_events, config, mode="evaluation",
                attempts_per_session=0, state_output_dir=None):
    """RPent's concrete toolkit factory, parallel to robots.libero.get_toolkit."""
    return LabSimToolkit(**primitives_kwargs,
                         output_dir=state_output_dir or config.output_dir / "policy_tools",
                         dashboard_events=dashboard_events)
