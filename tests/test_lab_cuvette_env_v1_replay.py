"""CPU replay contracts only; actual physical replay is separately recorded."""
import json
from pathlib import Path
import tempfile
import types
import unittest

import h5py
import numpy as np
from omegaconf import OmegaConf

from demos.lab_cuvette_env_v1.replay import load_source, configure_runtime, execute_replay, SCHEMA, SEMANTICS


class ReplayContractTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.episode = self.root / 'source'
        (self.episode / 'dataset').mkdir(parents=True)
        self.path = self.episode / 'dataset/episode_0000.h5'
        self.cfg = OmegaConf.create(dict(version='Env_v1', task_type='lab_cuvette_env_v1',
            physics=dict(control_hz=60, hz=240), env=dict(seed=1, mode='standard', task_type='preinsert_diagnostic'),
            rack=dict(selected_slot_id='A1', origin_m=[-.04, -.22, .74]),
            scene=dict(instrument_xyz_m=[.36, 0, .74]),
            adapter=dict(selected_target_seat_id='candidate_far_hinge')))
        OmegaConf.save(self.cfg, self.episode / 'config.yaml')
        (self.episode / 'result.json').write_text(json.dumps(dict(episode_id='source', complete=True, task_success=True)))
        with h5py.File(self.path, 'w') as file:
            file.attrs.update(schema_version=SCHEMA, executed_action_semantics=SEMANTICS,
                complete=True, episode_id='source', control_hz=60, physics_hz=240,
                scene_version='Env_v1', task_type='preinsert_diagnostic', source_slot_id='A1',
                target_seat_id='candidate_far_hinge', task_success=True, record_valid=True)
            file['control_auxiliary/command_q'] = np.tile(np.r_[np.full(7, .1), .04, .04], (2, 1))
            file['control_auxiliary/gripper_target_m'] = [.04, .04]
            file['control_auxiliary/gripper_effort_limit_N'] = [[8., 8.], [8., 8.]]
            file['control_auxiliary/available'] = [True, True]
            file['control_interval_s'] = [1/60, 1/60]
            file['timestamp'] = [1/60, 2/60]
            file['next_timestamp'] = [2/60, 3/60]
            file['partial_terminal_control_interval'] = [False, False]
            file.create_dataset('phase', data=['RESET', 'POLICY'], dtype=h5py.string_dtype())
            file.create_dataset('episode_id', data=['source', 'source'], dtype=h5py.string_dtype())

    def tearDown(self):
        self.temp.cleanup()

    def test_source_loads_full9_and_preserves_hash_labels(self):
        source = load_source(self.episode)
        self.assertEqual(source.commands.shape, (2, 9))
        self.assertTrue(source.manifest['source_labels']['task_success'])
        self.assertFalse(source.manifest['source_success_inherited'])
        self.assertEqual(source.config.env.task_type, 'preinsert_diagnostic')
        self.assertEqual(source.phases, ['RESET', 'POLICY'])

    def test_incomplete_or_wrong_schema_refused(self):
        with h5py.File(self.path, 'r+') as file:
            file.attrs['complete'] = False
        with self.assertRaisesRegex(ValueError, 'complete/closed'):
            load_source(self.episode)
        with h5py.File(self.path, 'r+') as file:
            file.attrs['complete'] = True
            file.attrs['schema_version'] = 'old-demo'
        with self.assertRaisesRegex(ValueError, 'schema'):
            load_source(self.episode)

    def test_zero_delay_override_changes_only_runtime_render_setting(self):
        source = load_source(self.episode)
        before = OmegaConf.to_container(source.config, resolve=True)
        configure_runtime(source)
        self.assertEqual(OmegaConf.to_container(source.config, resolve=True), before)
        after = OmegaConf.to_container(source.launch_config, resolve=True)
        self.assertTrue(after['env'].pop('render_zero_delay'))
        self.assertEqual(after, before)
        self.assertTrue(source.manifest['runtime_overrides']['env.render_zero_delay']['render_only'])

    def test_partial_control_tick_and_discontinuous_time_refused(self):
        with h5py.File(self.path, 'r+') as file:
            file['partial_terminal_control_interval'][1] = True
        with self.assertRaisesRegex(ValueError, 'Partial/non-60Hz'):
            load_source(self.episode)
        with h5py.File(self.path, 'r+') as file:
            file['partial_terminal_control_interval'][1] = False
            file['next_timestamp'][0] = .2
        with self.assertRaisesRegex(ValueError, 'discontinuous'):
            load_source(self.episode)

    def test_external_link_refused_without_dereferencing(self):
        with h5py.File(self.path, 'r+') as file:
            file['foreign'] = h5py.ExternalLink('missing.h5', '/data')
        with self.assertRaisesRegex(ValueError, 'self-contained'):
            load_source(self.episode)

    def test_random_source_is_unrandomized_once_for_reset(self):
        self.cfg.env.mode = 'random'
        self.cfg.rack.origin_m = [-.039, -.218, .74]
        self.cfg.scene.instrument_xyz_m = [.363, -.004, .74]
        self.cfg.randomization = dict(actual=dict(seed=1, rack_translation_m=[.001, .002],
                                                 instrument_assembly_translation_m=[.003, -.004]))
        OmegaConf.save(self.cfg, self.episode / 'config.yaml')
        source = load_source(self.episode)
        np.testing.assert_allclose(source.launch_config.rack.origin_m, [-.04, -.22, .74], atol=1e-12)
        np.testing.assert_allclose(source.launch_config.scene.instrument_xyz_m, [.36, 0, .74], atol=1e-12)
        self.assertEqual(source.options['mode'], 'random')
        self.assertTrue(source.manifest['runtime_random_base_reconstructed'])

    def environment(self, terminated=False):
        class FakeEnv:
            def __init__(self):
                self.app = types.SimpleNamespace(is_running=lambda: True)
                self.qcmd = np.zeros(9)
                self.effort = 8.
                self.calls = []
                self.step_index = 0
            def reset(self, seed, options):
                return dict(episode_id='replayed', step_index=0, simulation_time=1/60), dict(terminated=terminated)
            def step(self, action):
                self.calls.append(action)
                self.qcmd = np.asarray(action['values']).copy()
                self.qcmd[0] -= .001  # Explicit fixture clamp to test honest difference reporting.
                self.step_index += 1
                return dict(episode_id='replayed', step_index=self.step_index, simulation_time=(self.step_index+1)/60), 0., False, False, {}
            def finalize_episode(self, reason, failure):
                self.finalize_failure_type = failure
                return dict(task_success=False, termination_reason='GEOMETRY_PRECHECK_BLOCKED' if terminated else reason)
        return FakeEnv()

    def test_only_typed_commands_no_success_inheritance_and_clamp_retained(self):
        env = self.environment()
        result = execute_replay(env, load_source(self.episode), self.root / 'replay', max_ticks=1)
        self.assertEqual(len(env.calls), 1)
        self.assertEqual(env.calls[0]['type'], 'joint_position')
        self.assertNotIn('teacher_phase', env.calls[0]['metadata'])
        self.assertEqual(env.calls[0]['metadata']['source_phase'], 'RESET')
        self.assertFalse(result['independent_result']['task_success'])
        self.assertIsNone(env.finalize_failure_type)
        self.assertTrue(result['source']['source_labels']['task_success'])
        self.assertFalse(result['exact_executed_commands'])
        self.assertAlmostEqual(result['command_difference_max_abs'], .001)
        self.assertAlmostEqual(result['max_arm_joint_difference_rad'], .001)
        self.assertEqual(result['max_finger_difference_m'], 0)
        self.assertTrue(result['source_files_unchanged'])

    def test_startup_geometry_gate_executes_no_commands(self):
        env = self.environment(terminated=True)
        result = execute_replay(env, load_source(self.episode), self.root / 'blocked')
        self.assertEqual(env.calls, [])
        self.assertEqual(result['executed_control_ticks'], 0)
        self.assertIsNone(result['exact_executed_commands'])
        self.assertIsNone(result['command_difference_max_abs'])
        self.assertEqual(result['independent_result']['termination_reason'], 'GEOMETRY_PRECHECK_BLOCKED')


if __name__ == '__main__':
    unittest.main()
