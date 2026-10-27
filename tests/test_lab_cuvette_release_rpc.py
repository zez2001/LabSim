"""Release CPU protocol checks; no physical/model outcome is simulated as evidence."""
import copy
from types import SimpleNamespace
import unittest

import numpy as np

from demos.lab_cuvette_project_release_v1.rpc import ProjectRPC


class Config(SimpleNamespace):
    def get(self, name, default=None):
        return getattr(self, name, default)


class FixtureFacade:
    def __init__(self, mode="normal"):
        self.mode = mode
        self.steps = 0
        self.resets = 0
        self.episode = "e0"
        self.actions = []
        self.final = None
        self.task = SimpleNamespace(cfg=Config(robot=Config(base_m=[0, 0, .74]),
            physics=Config(hz=240, control_hz=60), release=dict(record_mode="diagnostic")), ACTION_SPECS={})

    def observe(self):
        return dict(episode_id=self.episode, observation_id=f"{self.episode}:{self.steps}",
                    step_index=self.steps, simulation_time=self.steps / 60,
                    images={"side_camera": np.zeros((2, 3, 3), np.uint8)})

    def status(self):
        return self.final or dict(episode_id=self.episode, simulation_time=self.steps / 60,
                                terminated=False, task_success=None)

    def execute(self, action):
        self.actions.append(copy.deepcopy(action))
        self.steps += 1 if self.mode == "partial" else 0 if self.mode == "reject" else 3
        if self.mode == "exception":
            raise RuntimeError("controlled fixture exception after advance")
        return dict(accepted=self.mode != "reject", executed_control_ticks=1 if self.mode == "partial" else 3,
                    partial_execution=self.mode == "partial", successor_observation_available=True)

    def reset(self, seed=0, options=None):
        self.resets += 1
        self.episode = "e" + str(self.resets)
        self.steps = 0
        self.final = None
        return self.observe()

    def finish(self, reason, failure_type=None):
        if self.final is None:
            self.final = dict(self.status(), terminated=True, task_success=False,
                              termination_reason=reason, failure_type=failure_type)
        return self.final


class ReleaseRPCContracts(unittest.TestCase):
    def command(self, env):
        return dict(episode_id=env.episode, observation_step=0, type="ee_delta", frame="world",
                    values=[0., 0., .0005, 0., 0., 0.], duration_s=.05)

    def test_actual_release_identity_and_rates(self):
        rpc = ProjectRPC(FixtureFacade())
        self.assertEqual(rpc.dispatch("healthz")["version"], "Project_release_v1")
        metadata = rpc.dispatch("env.get_env_meta")
        self.assertEqual(metadata["version"], "Project_release_v1")
        self.assertEqual(metadata["physics_steps_per_control"], 4)
        self.assertEqual(metadata["record_mode"], "diagnostic")

    def test_same_whole_chunk_is_idempotent_even_with_stale_origin(self):
        env = FixtureFacade()
        rpc = ProjectRPC(env)
        actions = [self.command(env), self.command(env)]
        first = rpc.chunk(actions, return_all_frames=True)
        again = rpc.chunk(actions, return_all_frames=False)
        self.assertEqual(len(env.actions), 2)
        self.assertEqual(env.steps, 6)
        self.assertEqual([x["step_index"] for x in first[0]], [3, 6])
        self.assertEqual(again[0]["step_index"], 6)
        self.assertTrue(again[4]["chunk_replayed"])
        self.assertEqual(actions[1]["observation_step"], 0)

    def test_partial_or_rejected_chunk_discards_remainder_and_retry_cannot_resume(self):
        for mode in ("partial", "reject"):
            env = FixtureFacade(mode)
            rpc = ProjectRPC(env)
            actions = [self.command(env)] * 3
            rpc.chunk(actions)
            rpc.chunk(actions)
            self.assertEqual(len(env.actions), 1, mode)

    def test_interrupted_chunk_cannot_replay_after_response_error(self):
        env = FixtureFacade("exception")
        rpc = ProjectRPC(env)
        actions = [self.command(env)] * 3
        with self.assertRaisesRegex(RuntimeError, "controlled fixture"):
            rpc.chunk(actions)
        with self.assertRaisesRegex(RuntimeError, "interrupted"):
            rpc.chunk(actions)
        self.assertEqual(env.steps, 3)
        self.assertEqual(len(env.actions), 1)

    def test_explicit_chunk_identity_cannot_change_payload(self):
        env = FixtureFacade()
        rpc = ProjectRPC(env)
        actions = [self.command(env)]
        rpc.chunk(actions, chunk_id="one")
        actions[0]["values"][2] = .0001
        with self.assertRaisesRegex(ValueError, "reused"):
            rpc.chunk(actions, chunk_id="one")
        self.assertEqual(len(env.actions), 1)

    def test_reset_clears_chunk_and_blocks_old_scene_or_private_overrides(self):
        env = FixtureFacade()
        rpc = ProjectRPC(env)
        actions = [self.command(env)]
        rpc.chunk(actions)
        rpc.reset()
        self.assertFalse(rpc._chunks)
        with self.assertRaisesRegex(ValueError, "Stale chunk"):
            rpc.chunk(actions)
        for options in (dict(source_slot_id="B2"), dict(target_seat_id="other"), dict(teacher=True), dict(truth_visible=True)):
            with self.assertRaises(ValueError):
                rpc.reset(options=options)

    def test_failure_classification_is_forwarded_and_old_safety_result_wins(self):
        env = FixtureFacade()
        rpc = ProjectRPC(env)
        final = rpc.finalize("MODEL_INFERENCE_ERROR", "model_service_error", env.episode)
        self.assertEqual(final["failure_type"], "MODEL_SERVICE_ERROR")
        with self.assertRaises(ValueError):
            rpc.finalize("fake", "invented", env.episode)
        env.final = dict(final, termination_reason="SAFETY_COLLISION", failure_type="SAFETY_FAILURE")
        kept = rpc.finalize("MODEL_INFERENCE_ERROR", "MODEL_SERVICE_ERROR", env.episode)
        self.assertEqual(kept["termination_reason"], "SAFETY_COLLISION")
        with self.assertRaisesRegex(ValueError, "Stale finalization"):
            rpc.finalize(episode_id="old")


if __name__ == "__main__":
    unittest.main()
