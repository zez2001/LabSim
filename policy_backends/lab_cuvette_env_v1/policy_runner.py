"""Run real policies against the same LabSim RPC; no Isaac/model installation.

Use the existing RPent .venv.  An environment server and (for pi05/Harness) an
actual checkpoint server must already be running.  Waiting for models does
not step physics; action durations are sent explicitly in simulation seconds.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import os
import time
import tomllib

import yaml
from pathlib import Path

from rpent.dashboard.events import NullDashboardEventSink
from rpent.planner.codex import CodexPlanner
from rpent.utils.rpc.http_rpc import HttpRpcClient
from rpent.utils.logging import init_output_dir

from .policy_adapters import LiberoTransferContract, Pi05LiberoAdapter, append_event, policy_observation, sensor_meta
from .rpent_extension import LabSimEnvClient, LabSimToolkit, _system_prompt
from .pi05_rollout import PolicyStageError, run_pi05_rollout


class RestrictedLabSimCodexPlanner(CodexPlanner):
    """Reuse RPent/auth while disabling unrelated installed tools per process."""
    def _build_config(self, mcp_url):
        cfg = super()._build_config(mcp_url)
        # Desktop runtime exposes MCP dispatch through code_mode_host. Disabling
        # it hides even our allowed tools; shell and unrelated MCPs stay disabled.
        extra = ["web_search=\"disabled\"", "agents.enabled=false", "tools.view_image=false",
                 "project_doc_max_bytes=0", "features.code_mode_host=true"]
        for name in ("shell_tool", "view_image", "apps", "browser_use", "browser_use_external",
                     "computer_use", "image_generation", "multi_agent", "skill_search",
                     "code_mode", "hooks", "memories"):
            extra.append(f"features.{name}=false")
        user_config = Path.home() / ".codex" / "config.toml"
        if user_config.exists():
            data = tomllib.loads(user_config.read_text())
            for name in data.get("plugins", {}):
                extra.append(f"plugins.{name}.enabled=false")
            for name in data.get("mcp_servers", {}):
                if name != "rpent":
                    extra.append(f"mcp_servers.{name}.enabled=false")
        return dataclasses.replace(cfg, config_overrides=(*cfg.config_overrides, *extra))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--backend", choices=["pi05", "harness", "astra"], required=True)
    p.add_argument("--policy-config", help="YAML overrides for the declared transfer contract; no source edits")
    p.add_argument("--env-endpoint", required=True)
    p.add_argument("--vla-endpoint")
    p.add_argument("--output", required=True)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--subtask", choices=["loading", "preinsert_diagnostic"], default="loading")
    p.add_argument("--layout-mode", choices=["standard", "random"], default="standard", help="passed as reset options.mode; assemblies remain governed by the scene randomizer")
    p.add_argument("--max-model-requests", "--max-planner-turns", dest="max_model_requests", type=int, default=100, help="pi05 predict-call budget; Astra/Harness RPent message-turn budget, not underlying HTTP request count")
    p.add_argument("--max-actions", type=int, default=1000)
    p.add_argument("--max-simulation-s", type=float, help="pi05 explicit executed simulation-time cap; model waiting does not consume it")
    p.add_argument("--planner-timeout-s", type=int, default=600)
    p.add_argument("--robot-base-position-m", type=float, nargs=3)
    p.add_argument("--robot-base-quaternion-xyzw", type=float, nargs=4,
                   help="explicit override; otherwise use environment launch metadata, then identity")
    p.add_argument("--codex-bin", default="/usr/lib/chatgpt/resources/codex")
    p.add_argument("--reasoning-effort", choices=["low", "medium", "high", "xhigh"], default="medium")
    args = p.parse_args(argv)
    if args.max_model_requests < 1 or args.max_actions < 1:
        p.error("model and action budgets must be positive")
    if args.max_simulation_s is not None:
        import math
        if args.backend != "pi05" or not math.isfinite(args.max_simulation_s) or args.max_simulation_s <= 0:
            p.error("--max-simulation-s must be finite positive and is currently pi05-only")
    policy_cfg = {}
    if args.policy_config:
        policy_cfg = yaml.safe_load(Path(args.policy_config).read_text()) or {}
        if not isinstance(policy_cfg, dict):
            p.error("policy config must be a mapping")
        if policy_cfg.get("truth_observation_allowed") is True or policy_cfg.get("expert_tools_allowed") is True:
            p.error("policy config cannot enable hidden truth or an expert")
        if args.backend == "astra" and policy_cfg.get("vla_tools_allowed") is True:
            p.error("Astra direct cannot enable VLA tools")
        if policy_cfg.get("model_id", "gpt-6-astra") != "gpt-6-astra":
            p.error("this direct/planner adapter is frozen to gpt-6-astra; no silent substitution")
    out = Path(args.output).resolve()
    out.mkdir(parents=True, exist_ok=False)
    init_output_dir(out / "rpent_runtime_log")
    request = vars(args) | {"started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                            "scorer_truth_visible": False, "physics_during_inference": "paused",
                            "model_id": "gpt-6-astra" if args.backend != "pi05" else "RLinf-Pi05-LIBERO-130-fullshot-SFT",
                            "expert_available": False, "vla_available": args.backend != "astra", "policy_config_snapshot": policy_cfg,
                            "observation_contract": "rgb_proprio_language_sensor_meta_whitelist_v1"}
    (out / "request.json").write_text(json.dumps(request, indent=2) + "\n")
    env = None
    stage = "ENV_CONNECT"
    started = time.perf_counter()
    result = {"backend": args.backend, "subtask": args.subtask, "layout_mode": args.layout_mode, "integration_complete": False, "task_success": None,
              "actual_model_requests": 0, "executed_actions": 0, "termination_reason": None}
    try:
        env = LabSimEnvClient(HttpRpcClient(args.env_endpoint))
        stage = "ENV_RESET"
        obs, info = env.reset(seed=args.seed, options={"subtask": args.subtask, "mode": args.layout_mode, "policy_id": {"pi05": "RLinf-Pi05-LIBERO-130-fullshot-SFT", "astra": "gpt-6-astra-direct", "harness": "harness-rpent-pi05-libero"}[args.backend], "truth_visible": False})
        result.update(episode_id=obs["episode_id"], reset_info=info)
        if info.get("terminated") is True or info.get("truncated") is True:
            # Loading can terminate at a geometry precheck. Do not connect to a
            # model service, fetch policy images or issue any action afterward.
            reason = info.get("termination_reason") or "STARTUP_TERMINATED"
            result.update(startup_terminated=True, termination_reason=reason,
                          task_success=info.get("task_success"),
                          attempt_category="geometry_precheck_blocked" if "GEOMETRY" in str(reason).upper() else "startup_terminated",
                          counts_as_physical_task_failure=False,
                          model_service_contacted=False)
            return 3
        result.update(startup_terminated=False, model_service_contacted=False)
        camera_meta = {name: env.get_camera_meta(name) for name in ("side_camera", "wrist_camera")}
        (out / "camera_meta.json").write_text(json.dumps(camera_meta, indent=2, default=lambda x: x.tolist() if hasattr(x, "tolist") else str(x)) + "\n")
        (out / "policy_camera_meta.json").write_text(json.dumps({name: sensor_meta(meta) for name, meta in camera_meta.items()}, indent=2, default=lambda x: x.tolist() if hasattr(x, "tolist") else str(x)) + "\n")
        result["model_visible_state_keys"] = list(policy_observation(obs).keys())
        adapter = None
        if args.backend in {"pi05", "harness"}:
            if not args.vla_endpoint:
                raise ValueError("pi05/Harness requires an actual --vla-endpoint")
            base = args.robot_base_position_m or env.meta.get("robot_base_position_m")
            if base is None:
                raise ValueError("Robot base transform must come from server metadata or --robot-base-position-m")
            contract_fields = {f.name for f in dataclasses.fields(LiberoTransferContract)}
            contract = LiberoTransferContract(**{k: v for k, v in policy_cfg.items() if k in contract_fields})
            stage = "MODEL_CONNECT"
            result["model_service_contacted"] = True
            adapter = Pi05LiberoAdapter(HttpRpcClient(args.vla_endpoint), contract=contract, robot_base_position_m=base,
                                       robot_base_quaternion_xyzw=args.robot_base_quaternion_xyzw or env.meta.get("robot_base_quaternion_xyzw", [0, 0, 0, 1]))
        if args.backend == "pi05":
            stage = "POLICY_ROLLOUT"
            obs = run_pi05_rollout(env, adapter, dict(obs, camera_meta=camera_meta), result,
                output=out, maximum_model_requests=args.max_model_requests,
                maximum_actions=args.max_actions, maximum_simulation_s=args.max_simulation_s)
        else:
            os.environ["CODEX_BIN"] = args.codex_bin
            toolkit = LabSimToolkit(env, output_dir=out / "planner", mode="direct" if args.backend == "astra" else "harness",
                                    vla_adapter=adapter, maximum_action_calls=args.max_actions)
            planner = RestrictedLabSimCodexPlanner(output_dir=str(out / "planner"), repo_root=str(out / "planner"),
                         timeout_s=args.planner_timeout_s, model="gpt-6-astra", reasoning_effort=args.reasoning_effort,
                         dashboard_events=NullDashboardEventSink(), output_path=out / "planner" / "astra.txt")
            initial = toolkit.observe()
            language = obs["task_language"]
            # The first tool call obtains actual images; never insert scorer truth into a prompt.
            prompt = f"Task: {language}\nBegin with observe. Use only the provided RPent tools; no files or shell.\n"
            if args.subtask == "preinsert_diagnostic":
                prompt += "This episode is explicitly preinsert_diagnostic: approach and transport only. Do not attempt blocked native insertion or claim loading success.\n"
            if args.backend == "harness":
                prompt += "For this real-chain attempt, call vla_primitive with an observation-grounded short instruction, then inspect the actual successor observation. Do not substitute a whole expert workflow.\n"
            else:
                prompt += "For this real-chain attempt, choose at least one bounded low-level action from the actual observation, then inspect its successor observation.\n"
            prompt += f"The declared maximum is {args.max_actions} actual actions. End with failure or stuck when the finite budget is spent unless the independent environment has reported success. Do not claim success from interface connectivity.\n"
            stage = "MODEL_PLANNER"
            result["model_service_contacted"] = True
            solved = planner.solve(system_prompt=_system_prompt(), user_message=prompt, toolkit=toolkit,
                                   max_turns=args.max_model_requests)
            result.update(task_success=toolkit._task_success, planner_error=solved.error,
                          planner_finish=solved.finish_result, planner_stats=solved.stats,
                          termination_reason="MODEL_SERVICE_ERROR" if solved.error else "PLANNER_ENDED",
                          executed_actions=toolkit._action_calls)
            # Recorded tool calls, not planner prose, establish actual integration.
            trace = out / "planner" / "policy_tools.jsonl"
            rows = [json.loads(s) for s in trace.read_text().splitlines()] if trace.exists() else []
            physical_calls = [r for r in rows if r.get("event") in {"bounded_action", "vla_action"}]
            result["executed_actions"] = len(physical_calls)
            result["planner_invocations"] = 1
            result["actual_model_requests"] = None
            result["model_request_count_scope"] = "Codex internal HTTP count unavailable; planner invocation and response messages recorded separately"
            result["planner_response_messages"] = solved.stats.get("turns_used", 0)
            result["actual_vla_predict_requests"] = sum(r.get("event") == "vla_inference" for r in rows)
            actual_vla = any(r.get("event") == "vla_inference" for r in rows)
            result["actual_vla_inference"] = actual_vla
            result["integration_complete"] = bool(physical_calls and (args.backend == "astra" or actual_vla))
    except KeyboardInterrupt:
        result.update(error_type="KeyboardInterrupt", error="user interrupted policy runner",
                      error_stage=stage, termination_reason="USER_INTERRUPTED",
                      finalization_failure_type="PROCESS_INTERRUPTED")
    except Exception as exc:
        if isinstance(exc, PolicyStageError):
            stage, exc = exc.stage, exc.cause
        reason = "GEOMETRY_PREFLIGHT_BLOCKED" if "GEOMETRY" in str(exc).upper() and stage == "ENV_RESET" else stage + "_ERROR"
        result.update(error_type=type(exc).__name__, error=str(exc), error_stage=stage, termination_reason=reason)
    finally:
        # Finalize this finite attempt without killing a shared Isaac process.
        # The environment recomputes labels from actual physics; no caller can
        # pass task_success. Service errors remain distinct from valid failures.
        if env is not None and result.get("episode_id"):
            try:
                failure_type = result.get("finalization_failure_type")
                if failure_type is None and (result.get("error") or result.get("planner_error")):
                    failure_type = ("MODEL_SERVICE_ERROR" if stage.startswith("MODEL_") else
                                    "INPUT_CONTRACT_ERROR" if stage in {"POLICY_ACTION_ADAPTATION", "ENV_POST_INFERENCE_OBSERVATION"} else
                                    "SIMULATION_FAILURE")
                result["finalization_failure_type"] = failure_type
                finalized = env.finalize_episode(termination_reason=result.get("termination_reason") or "POLICY_BUDGET",
                                                 failure_type=failure_type)
                result["episode_finalized"] = True
                result["environment_final_result"] = finalized
                if isinstance(finalized, dict) and finalized.get("termination_reason"):
                    result["requested_termination_reason"] = result.get("termination_reason")
                    result["termination_reason"] = finalized["termination_reason"]
                if isinstance(finalized, dict) and "task_success" in finalized:
                    result["task_success"] = finalized["task_success"]
            except Exception as finalize_error:
                result["episode_finalized"] = False
                result["finalization_error"] = str(finalize_error)
        result["wall_time_s"] = time.perf_counter() - started
        result["finished_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        (out / "result.json").write_text(json.dumps(result, indent=2, default=lambda x: x.tolist() if hasattr(x, "tolist") else str(x)) + "\n")
        print(json.dumps(result, indent=2, default=str))
    return 0 if result["integration_complete"] and result.get("episode_finalized") is True and not result.get("error") else 2


if __name__ == "__main__":
    raise SystemExit(main())
