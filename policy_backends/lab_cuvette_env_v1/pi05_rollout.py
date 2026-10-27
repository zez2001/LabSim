"""Finite real-policy interaction with auditable execution receipts.

This module has no model, RPC, Isaac or checkpoint imports. Tests use protocol
fixtures only; actual model and physics evidence are recorded by the caller.
"""
from __future__ import annotations

import copy
import hashlib
import json

from .policy_adapters import append_event


class PolicyStageError(RuntimeError):
    def __init__(self, stage, cause):
        super().__init__(str(cause))
        self.stage = stage
        self.cause = cause


def _identity(observation):
    return (str(observation["episode_id"]), int(observation["step_index"]),
            float(observation["simulation_time"]))


def run_pi05_rollout(env, adapter, observation, result, *, output,
                     maximum_model_requests, maximum_actions,
                     maximum_simulation_s=None):
    """Execute real inferred chunks against fresh public observations.

    A rejected interval is not an executed action. A partial action is never
    replayed or completed from the remainder of its old chunk. No automatic
    repair, task-space search, teacher action or policy retry is performed.
    """
    result.update(submitted_actions=0, accepted_actions=0,
                  executed_control_ticks=0, rejected_actions=0,
                  partial_actions=0, target_reached_actions=0,
                  receipt_available_actions=0, waiting_pause_checks=0,
                  maximum_simulation_s=maximum_simulation_s,
                  actual_policy_simulation_duration_s=None,
                  last_acknowledged_policy_simulation_duration_s=0.,
                  execution_counter_scope="acknowledged RPC results only; closed environment trace is authoritative for an interrupted/unanswered call")
    initial_time = float(observation["simulation_time"])
    initial_episode = str(observation["episode_id"])
    stage = "MODEL_INFERENCE"
    try:
        stop = False
        for _ in range(int(maximum_model_requests)):
            if stop or result["submitted_actions"] >= maximum_actions:
                break
            if maximum_simulation_s is not None and float(observation["simulation_time"]) - initial_time >= maximum_simulation_s - 1e-9:
                result["termination_reason"] = "POLICY_SIMULATION_LIMIT"
                break
            stage = "MODEL_INFERENCE"
            origin = _identity(observation)
            raw, inference = adapter.infer(observation)
            result["actual_model_requests"] += 1
            append_event(output / "policy_events.jsonl", {
                "event": "actual_model_inference", "inference": inference,
                "selected_raw_actions": raw})
            # This read never advances simulation. Do not silently rebase a
            # chunk if another client changed the environment while inferring.
            stage = "ENV_POST_INFERENCE_OBSERVATION"
            after_wait = env.get_observation()
            paused = _identity(after_wait) == origin
            append_event(output / "policy_events.jsonl", {
                "event": "model_wait_pause_check", "before": origin,
                "after": _identity(after_wait), "physics_paused": paused})
            if not paused:
                raise ValueError("environment changed during model inference; stale chunk refused")
            result["waiting_pause_checks"] += 1
            observation = after_wait
            for row_index, row in enumerate(raw):
                if result["submitted_actions"] >= maximum_actions:
                    stop = True
                    break
                elapsed = float(observation["simulation_time"]) - initial_time
                if maximum_simulation_s is not None and elapsed + 1.0 / adapter.contract.policy_action_hz > maximum_simulation_s + 1e-9:
                    result["termination_reason"] = "POLICY_SIMULATION_LIMIT"
                    stop = True
                    break
                stage = "POLICY_ACTION_ADAPTATION"
                command = adapter.convert_action(row, observation)
                command["inference_wall_time_s"] = inference["inference_wall_s"]
                command["policy_inference_call"] = inference["inference_call"]
                identity = [initial_episode, int(inference["inference_call"]), row_index,
                            int(observation["step_index"])]
                command["action_id"] = "pi05:" + hashlib.sha256(json.dumps(identity).encode()).hexdigest()
                previous = _identity(observation)
                stage = "ENV_ACTION"
                append_event(output / "policy_events.jsonl", {
                    "event": "model_action_submitted", "raw_model_action": row,
                    "adapted_action": copy.deepcopy(command), "source_observation": previous})
                result["submitted_actions"] += 1
                observation, reward, terminated, truncated, info = env.step(command)
                if str(observation["episode_id"]) != initial_episode:
                    raise ValueError("environment episode changed after action")
                result["last_acknowledged_policy_simulation_duration_s"] = float(observation["simulation_time"]) - initial_time
                receipt = info.get("action_receipt")
                if isinstance(receipt, dict):
                    result["receipt_available_actions"] += 1
                    ticks = int(receipt.get("executed_control_ticks", 0))
                    result["accepted_actions"] += int(receipt.get("accepted") is True)
                    result["executed_actions"] += int(ticks > 0)
                    result["executed_control_ticks"] += ticks
                    result["rejected_actions"] += int(receipt.get("accepted") is False)
                    result["partial_actions"] += int(receipt.get("partial_execution") is True)
                    result["target_reached_actions"] += int(receipt.get("target_reached") is True)
                    successor_available = receipt.get("successor_observation_available", True)
                    rejected = receipt.get("accepted") is False
                    partial = receipt.get("partial_execution") is True
                else:
                    # Historical Env_v1 has no rich receipt. Preserve its
                    # compatibility but never infer executed ticks from a request.
                    advanced = float(observation["simulation_time"]) > previous[2] + 1e-9
                    result["executed_actions"] += int(advanced)
                    successor_available, rejected, partial = True, False, False
                result["task_success"] = info.get("task_success")
                result["integration_complete"] = result["executed_actions"] > 0
                append_event(output / "policy_events.jsonl", {
                    "event": "model_action", "raw_model_action": row,
                    "adapted_action": copy.deepcopy(command),
                    "action_receipt": receipt,
                    "successor_episode_id": observation["episode_id"],
                    "successor_step_index": observation["step_index"],
                    "simulation_time": observation["simulation_time"],
                    "reward": reward, "terminated": terminated, "truncated": truncated})
                if terminated or truncated:
                    result["termination_reason"] = info.get("termination_reason") or "ENVIRONMENT_TERMINATED"
                    stop = True
                elif not successor_available:
                    result["termination_reason"] = "POLICY_SUCCESSOR_UNAVAILABLE"
                    stop = True
                elif rejected:
                    result["termination_reason"] = "POLICY_ACTION_REJECTED"
                    stop = True
                elif partial:
                    result["termination_reason"] = "POLICY_ACTION_PARTIAL"
                    stop = True
                if stop:
                    break
        result["actual_policy_simulation_duration_s"] = float(observation["simulation_time"]) - initial_time
        result["termination_reason"] = result.get("termination_reason") or "POLICY_BUDGET"
        return observation
    except Exception as error:
        raise PolicyStageError(stage, error) from error
