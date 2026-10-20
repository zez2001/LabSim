"""Normal failure reads preserve false labels and exclude nonphysical aborts."""
import tempfile
import unittest
from pathlib import Path
import h5py
import numpy as np
from policy.dataset.minimal_pick_dataset import MinimalPickDataset


class DatasetFilterTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / 'episode_data.hdf5'
        self.meta = dict(obs={'side_camera_rgb': dict(type='rgb', shape=[3, 4, 4]),
                              'wrist_camera_rgb': dict(type='rgb', shape=[3, 4, 4]),
                              'agent_pose': dict(type='low_dim', shape=[8])}, action=dict(shape=[8]))
        with h5py.File(self.path, 'w') as f:
            for i, (success, valid, failure, eligible) in enumerate([
                (True, True, 'NONE', False), (False, True, 'GRASP_SLIP', True),
                (False, False, 'PHYSICS_INVALID', False), (False, True, 'MODEL_SERVICE_ERROR', True),
                (False, False, 'GEOMETRY_PREFLIGHT_BLOCKED', False)]):
                g = f.create_group(f'episode_{i:04}')
                g.attrs.update(complete=True, success=success, task_success=success, record_valid=valid,
                               failure_type=failure, eligible_for_success_bc=success,
                               eligible_for_failure_analysis=eligible)
                q = np.ones((3, 8), np.float32) * i
                g.create_dataset('agent_pose', data=q)
                g.create_dataset('actions', data=q + 1)
                for c in ('side_camera_rgb', 'wrist_camera_rgb'):
                    g.create_dataset(c, data=np.ones((3, 3, 4, 4), np.uint8) * i)

    def tearDown(self):
        self.directory.cleanup()

    def dataset(self, **kwargs):
        return MinimalPickDataset(self.meta, self.path, horizon=4, val_ratio=0, **kwargs)

    def test_default_remains_success_and_explicit_failure_keeps_false_label(self):
        success = self.dataset()
        failure = self.dataset(sample_filter='failure')
        self.assertEqual(success.episode_ids, ['episode_0000'])
        self.assertEqual(failure.episode_ids, ['episode_0001'])
        batch = failure.collate_fn([failure[2]])
        self.assertFalse(bool(batch['labels']['task_success'][0]))
        self.assertEqual(batch['labels']['failure_type'], ['GRASP_SLIP'])
        np.testing.assert_array_equal(batch['is_pad'][0], [False, True, True, True])
        with h5py.File(self.path) as f:
            self.assertFalse(bool(f['episode_0001'].attrs['success']))

    def test_all_valid_rejects_contradictory_nonphysical_error_metadata(self):
        # A contradictory record_valid=true cannot turn a model error into physical task data.
        data = self.dataset(sample_filter='all_valid')
        self.assertEqual(set(data.episode_ids), {'episode_0000', 'episode_0001'})
        self.assertEqual(data.excluded_episodes['episode_0003'], 'not_physical_task_record')

    def test_dp_failure_history_does_not_cross_episode(self):
        data = self.dataset(sample_filter='failure', policy_type='dp', n_obs_steps=2)
        self.assertEqual(data[0]['obs']['agent_pose'].shape, (2, 8))
        self.assertFalse(data[0]['labels']['task_success'])

    def test_direct_self_contained_episode_is_read_without_index(self):
        direct = Path(self.directory.name) / 'direct.h5'
        with h5py.File(self.path) as source, h5py.File(direct, 'x') as out:
            group = source['episode_0001']
            out.attrs.update(dict(group.attrs), episode_id='actual_episode_uuid')
            for k in group:
                group.copy(k, out)
        data = MinimalPickDataset(self.meta, direct, horizon=4, val_ratio=0, sample_filter='failure')
        self.assertEqual(data.episode_ids, ['actual_episode_uuid'])
        self.assertFalse(data[0]['labels']['task_success'])

    def test_nonphysical_aliases_never_enter_failure_or_all_valid(self):
        from utils.episode_selection import episode_matches_filter
        for alias in ('GEOMETRY_PRECHECK_BLOCKED','PREFLIGHT_BLOCKED','INPUT_CONTRACT_ERROR'):
            attributes=dict(complete=True,record_valid=True,task_success=False,
                eligible_for_failure_analysis=True,failure_type=alias)
            for selection in ('failure','all_valid'):
                self.assertFalse(episode_matches_filter(attributes,selection)[0])

    def test_wrong_action_semantics_rejected_even_at_same_dimension(self):
        with h5py.File(self.path, 'r+') as f:
            f['episode_0001'].attrs['action_semantics'] = 'joint_velocity_rad_per_second'
        with self.assertRaisesRegex(ValueError, 'Unsupported 8D action semantics'):
            self.dataset(sample_filter='failure')

if __name__ == '__main__':
    unittest.main()
