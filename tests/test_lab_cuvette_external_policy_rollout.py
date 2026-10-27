"""CPU protocol fixtures only; these tests are not real-model/Isaac evidence."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

import numpy as np

from policy_backends.lab_cuvette_env_v1.pi05_rollout import PolicyStageError, run_pi05_rollout


class FixtureAdapter:
    contract = SimpleNamespace(policy_action_hz=20.0)

    def __init__(self):
        self.calls = 0
        self.after_infer = None

    def infer(self, observation):
        self.calls += 1
        if self.after_infer:
            self.after_infer()
        return np.zeros((5, 7)), {"inference_call": self.calls, "inference_wall_s": .01}

    def convert_action(self, row, observation):
        return dict(episode_id=observation["episode_id"], observation_step=observation["step_index"],
                    type="ee_delta", values=[0.] * 6, duration_s=.05, raw_model_action=row.tolist())


class FixtureEnvironment:
    def __init__(self, mode="normal"):
        self.mode = mode
        self.obs = dict(episode_id="fixture-episode", step_index=0, simulation_time=.0166666666667)
        self.actions = []

    def get_observation(self):
        return copy.deepcopy(self.obs)

    def step(self, action):
        self.actions.append(copy.deepcopy(action))
        ticks = 0 if self.mode == "reject" else 1 if self.mode == "partial" else 3
        self.obs["step_index"] += ticks
        self.obs["simulation_time"] += ticks / 60.
        terminated = self.mode == "safety"
        receipt = dict(accepted=self.mode != "reject", executed_control_ticks=ticks,
                       partial_execution=self.mode == "partial", target_reached=self.mode == "normal",
                       successor_observation_available=self.mode != "unavailable")
        info = dict(action_receipt=receipt, task_success=False,
                    termination_reason="SAFETY_COLLISION" if terminated else None)
        return self.get_observation(), 0., terminated, False, info


class ExternalPolicyRolloutContracts(unittest.TestCase):
    def run_case(self, env=None, adapter=None, **limits):
        env = env or FixtureEnvironment()
        adapter = adapter or FixtureAdapter()
        result = dict(actual_model_requests=0, executed_actions=0,
                      integration_complete=False, task_success=None, termination_reason=None)
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)
            observation = run_pi05_rollout(env, adapter, env.get_observation(), result,
                output=output, maximum_model_requests=limits.get("requests", 100),
                maximum_actions=limits.get("actions", 1000),
                maximum_simulation_s=limits.get("simulation_s", .5))
            events = [json.loads(s) for s in (output / "policy_events.jsonl").read_text().splitlines()]
        return result, events, observation, env

    def test_real_time_budget_uses_actual_successor_and_chunk_reobservation(self):
        result, events, _, env = self.run_case(simulation_s=.5)
        self.assertEqual(result["actual_model_requests"], 2)
        self.assertEqual(result["executed_actions"], 10)
        self.assertEqual(result["executed_control_ticks"], 30)
        self.assertEqual(result["termination_reason"], "POLICY_SIMULATION_LIMIT")
        self.assertAlmostEqual(result["actual_policy_simulation_duration_s"], .5)
        self.assertEqual(result["waiting_pause_checks"], 2)
        self.assertEqual(len({a["action_id"] for a in env.actions}), 10)
        self.assertEqual([a["observation_step"] for a in env.actions], list(range(0, 30, 3)))
        actions = [e for e in events if e["event"] == "model_action"]
        self.assertTrue(all(e["action_receipt"]["executed_control_ticks"] == 3 for e in actions))
        self.assertTrue(all("raw_model_action" in e and "adapted_action" in e for e in actions))

    def test_rejected_action_is_not_counted_executed_or_retried(self):
        result, _, _, env = self.run_case(FixtureEnvironment("reject"))
        self.assertEqual(len(env.actions), 1)
        self.assertEqual(result["submitted_actions"], 1)
        self.assertEqual(result["executed_actions"], 0)
        self.assertFalse(result["integration_complete"])
        self.assertEqual(result["rejected_actions"], 1)
        self.assertEqual(result["termination_reason"], "POLICY_ACTION_REJECTED")

    def test_partial_does_not_execute_remaining_chunk(self):
        result, _, _, env = self.run_case(FixtureEnvironment("partial"))
        self.assertEqual(len(env.actions), 1)
        self.assertEqual(result["executed_control_ticks"], 1)
        self.assertEqual(result["partial_actions"], 1)
        self.assertEqual(result["termination_reason"], "POLICY_ACTION_PARTIAL")

    def test_safety_result_wins_over_local_budget(self):
        result, _, _, env = self.run_case(FixtureEnvironment("safety"))
        self.assertEqual(len(env.actions), 1)
        self.assertEqual(result["termination_reason"], "SAFETY_COLLISION")

    def test_unavailable_successor_is_never_reused(self):
        result, _, _, env = self.run_case(FixtureEnvironment("unavailable"))
        self.assertEqual(len(env.actions), 1)
        self.assertEqual(result["termination_reason"], "POLICY_SUCCESSOR_UNAVAILABLE")

    def test_other_client_step_during_inference_is_refused(self):
        env, adapter = FixtureEnvironment(), FixtureAdapter()
        adapter.after_infer = lambda: env.obs.update(step_index=1)
        with self.assertRaisesRegex(PolicyStageError, "stale chunk") as caught:
            self.run_case(env, adapter)
        self.assertEqual(caught.exception.stage, "ENV_POST_INFERENCE_OBSERVATION")
        self.assertFalse(env.actions)

    def test_finite_action_and_request_budgets_are_independent(self):
        result, _, _, _ = self.run_case(actions=7, simulation_s=20)
        self.assertEqual(result["submitted_actions"], 7)
        self.assertEqual(result["actual_model_requests"], 2)
        self.assertEqual(result["termination_reason"], "POLICY_BUDGET")
        result, _, _, _ = self.run_case(requests=1, simulation_s=20)
        self.assertEqual(result["submitted_actions"], 5)
        self.assertEqual(result["termination_reason"], "POLICY_BUDGET")

    def test_model_exception_keeps_stage_and_original_exception(self):
        adapter = FixtureAdapter()
        def unavailable():
            raise TimeoutError("controlled fixture timeout")
        adapter.after_infer = unavailable
        with self.assertRaises(PolicyStageError) as caught:
            self.run_case(adapter=adapter)
        self.assertEqual(caught.exception.stage, "MODEL_INFERENCE")
        self.assertIsInstance(caught.exception.cause, TimeoutError)


if __name__ == "__main__":
    unittest.main()
