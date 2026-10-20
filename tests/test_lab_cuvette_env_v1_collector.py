"""HDF5 contract tests; fixtures are explicitly not physical experiment evidence."""
import tempfile
import unittest
from pathlib import Path
import h5py
import numpy as np
from data_collectors.lab_cuvette_env_v1_collector import LabCuvetteEnvV1Collector
from policy.dataset.minimal_pick_dataset import MinimalPickDataset


class EnvV1CollectorContractTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.output = Path(self.temp.name)
        self.collector = LabCuvetteEnvV1Collector(dict(version='Env_v1', physics=dict(hz=240, control_hz=60)),
            self.output, save_video=False, camera_meta={'side_camera': {'frame': 'world'}, 'wrist_camera': {'frame': 'panda_hand'}})
        self.collector.begin_episode(0, episode_id='fixture-not-simulation', metadata=dict(task_type='loading', seed=0))
        self.meta = dict(obs={k:dict(type='rgb', shape=[3,4,4]) for k in ('side_camera_rgb','wrist_camera_rgb')}, action=dict(shape=[8]))
        self.meta['obs']['agent_pose'] = dict(type='low_dim', shape=[8])

    def tearDown(self):
        self.collector.close()
        self.temp.cleanup()

    def transition(self, step=0, old_episode=False):
        def state(t):
            return dict(joint_positions=np.arange(9)*.01, simulation_time=t/60., step_index=t,
                episode_id='old' if old_episode else 'fixture-not-simulation', phase='GRASP',
                camera_data={k:np.full((3,4,4), 100+t, np.uint8) for k in ('side_camera_rgb','wrist_camera_rgb')},
                debug={'object_pose':[0,0,0]})
        action = dict(command_q=np.arange(9)*.02, raw_output={'action':[1,2]}, gripper_effort_limit_N=[3,4],
                      gripper_target_m=.006, conversion={'input_semantics':'fixture'})
        self.collector.cache_transition(state(step), action, state(step+1), {'terminated':False})

    def score(self, **kwargs):
        return dict(episode_id='fixture-not-simulation', record_valid=True, task_success=False,
                    failure_type='GRASP_SLIP', geometry_valid=True, task_type='loading', **kwargs)

    def test_physical_failure_labels_preserved_through_merge_and_normal_dataset(self):
        self.transition()
        self.transition(1)
        labels = self.collector.finish_episode({'termination_reason':'test fixture'}, self.score())
        self.assertTrue(labels['record_valid'])
        self.assertFalse(labels['task_success'])
        self.assertTrue(labels['eligible_for_failure_analysis'])
        merged, count = self.collector.merge()
        self.assertEqual(count, 1)
        dataset = MinimalPickDataset(self.meta, merged, horizon=2, val_ratio=0, sample_filter='failure')
        sample = dataset[0]
        self.assertFalse(sample['labels']['task_success'])
        with h5py.File(self.output/'dataset/episode_0000.h5') as h:
            self.assertEqual(h['camera_1_rgb'].id, h['side_camera_rgb'].id)
            np.testing.assert_array_equal(h['control_auxiliary/command_q'][0], np.arange(9)*.02)
            np.testing.assert_array_equal(h['control_auxiliary/gripper_effort_limit_N'][0], [3,4])
            self.assertFalse(h.attrs['success'])
            self.assertEqual(h['privileged/state_json'].asstr()[0], '{"object_pose": [0, 0, 0]}')

    def test_partial_terminal_physics_interval_is_retained_explicitly(self):
        state=dict(joint_positions=np.arange(9)*.01,simulation_time=0.,step_index=0,
            episode_id='fixture-not-simulation',camera_data={k:np.ones((3,4,4),np.uint8)*100
            for k in ('side_camera_rgb','wrist_camera_rgb')})
        after=dict(state,simulation_time=1/240.,step_index=1)
        self.collector.cache_transition(state,dict(command_q=np.arange(9)*.01,
            gripper_effort_limit_N=8.,gripper_target_m=.006),after,dict(terminated=True))
        labels=self.collector.finish_episode({},self.score())
        self.assertTrue(labels['record_valid'])
        with h5py.File(self.output/'dataset/episode_0000.h5') as h:
            self.assertAlmostEqual(h['control_interval_s'][0],1/240.)
            self.assertTrue(h['partial_terminal_control_interval'][0])

    def test_valid_subtask_is_all_valid_but_never_full_loading_quota(self):
        self.transition();score=self.score();score.update(task_type='grasp_hold',task_success=True)
        labels=self.collector.finish_episode({},score)
        self.assertTrue(labels['record_valid'])
        self.assertFalse(labels['eligible_for_success_bc'])
        self.assertFalse(labels['eligible_for_failure_analysis'])
        data=MinimalPickDataset(self.meta,self.output/'dataset/episode_0000.h5',horizon=2,val_ratio=0,sample_filter='all_valid')
        self.assertTrue(data[0]['labels']['task_success'])

    def test_missing_independent_score_stays_unknown(self):
        self.transition()
        labels = self.collector.finish_episode({'status':'SUCCESS'})
        self.assertIsNone(labels['task_success'])
        self.assertFalse(labels['record_valid'])
        self.assertFalse(labels['eligible_for_success_bc'])

    def test_model_error_is_not_a_physical_failure_even_if_caller_says_valid(self):
        self.transition()
        score = self.score()
        score['failure_type'] = 'MODEL_SERVICE_ERROR'
        labels = self.collector.finish_episode({}, score)
        self.assertFalse(labels['record_valid'])
        self.assertFalse(labels['eligible_for_failure_analysis'])

    def test_preinsert_subtask_cannot_become_full_loading_success(self):
        self.transition()
        score = self.score()
        score.update(task_type='preinsert_diagnostic', task_success=True)
        labels = self.collector.finish_episode({}, score)
        self.assertTrue(labels['task_success'])
        self.assertFalse(labels['eligible_for_success_bc'])
        with h5py.File(self.output/'dataset/episode_0000.h5') as h:
            self.assertFalse(h.attrs['workflow_success'])
            self.assertFalse(h.attrs['success'])

    def test_old_episode_action_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'old episode'):
            self.transition(old_episode=True)

if __name__ == '__main__':
    unittest.main()
