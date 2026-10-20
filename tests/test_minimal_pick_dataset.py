"""Guard action supervision, episode isolation, padding, and failure exclusion."""
import tempfile
import unittest
from pathlib import Path
import h5py
import numpy as np
from policy.dataset.minimal_pick_dataset import MinimalPickDataset


class DatasetContractTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "episode_data.hdf5"
        self.meta = dict(obs={"camera_1_rgb": dict(shape=[3, 4, 4], type="rgb"),
                              "camera_2_rgb": dict(shape=[3, 4, 4], type="rgb"),
                              "agent_pose": dict(shape=[8], type="low_dim")}, action=dict(shape=[8]))
        with h5py.File(self.path, "w") as f:
            for i in range(4):
                e = f.create_group(f"episode_{i:04d}")
                e.attrs.update(success=i != 3, complete=True)
                q = np.arange(5, dtype=np.float32)[:, None] + np.zeros((5, 8), dtype=np.float32) + 10*i
                e.create_dataset("agent_pose", data=q)
                e.create_dataset("actions", data=q + 100)
                for camera in ("camera_1_rgb", "camera_2_rgb"):
                    e.create_dataset(camera, data=np.full((5, 3, 4, 4), 10*i, np.uint8))

    def tearDown(self):
        self.temp.cleanup()

    def dataset(self, **kwargs):
        return MinimalPickDataset(self.meta, str(self.path), horizon=4, **kwargs)

    def test_act_actions_are_commanded_and_chunks_do_not_cross_episodes(self):
        data = self.dataset(val_ratio=0)
        first = data[0]
        np.testing.assert_array_equal(first["action"][0].numpy(), first["obs"]["agent_pose"].numpy() + 100)
        tail = data[4]
        np.testing.assert_array_equal(tail["is_pad"].numpy(), [False, True, True, True])
        expected = 104 + 10 * int(data.sequences[4][0][-4:])
        self.assertTrue((tail["action"] == expected).all())
        self.assertEqual(first["obs"]["camera_1_rgb"].shape, (3, 4, 4))
        self.assertEqual(len(data), 15)  # Failed fourth episode is excluded.

    def test_validation_split_is_by_episode_and_normalizer_uses_train_only(self):
        data = self.dataset(val_ratio=.34)
        validation = data.get_validation_dataset()
        self.assertFalse(set(data.episode_ids) & set(validation.episode_ids))
        self.assertEqual(len(validation.episode_ids), 1)
        expected = np.concatenate([np.arange(5) + 10*int(e[-4:]) + 100 for e in data.episode_ids])
        actual = data.get_all_actions().numpy()[:, 0]
        np.testing.assert_array_equal(actual, expected)
        normalized = data.get_normalizer()["action"].normalize(data.get_all_actions())
        self.assertAlmostEqual(float(normalized.min()), -1., places=5)
        self.assertAlmostEqual(float(normalized.max()), 1., places=5)

    def test_dp_history_and_current_action_alignment(self):
        data = self.dataset(val_ratio=0, policy_type="dp", n_obs_steps=3)
        start = data[0]
        self.assertEqual(start["obs"]["agent_pose"].shape, (3, 8))
        offset = 10 * int(data.sequences[0][0][-4:])
        self.assertTrue((start["obs"]["agent_pose"] == offset).all())
        middle = data[2]
        np.testing.assert_array_equal(middle["obs"]["agent_pose"][:, 0], np.array([0, 1, 2]) + offset)
        self.assertEqual(float(middle["action"][2, 0]), 102. + offset)

    def condition_attributes(self, *, one_condition=False):
        with h5py.File(self.path, "r+") as f:
            for index in range(3):
                f[f"episode_{index:04d}"].attrs.update(
                    source_slot_id="A1" if one_condition or index < 2 else "B1",
                    target_seat_id="candidate_far_hinge", scene_version="Env_v1",
                    asset_version="actual-fixture-version", task_type="loading")

    def test_scene_condition_groups_never_cross_train_validation(self):
        self.condition_attributes()
        keys = ["source_slot_id", "target_seat_id", "scene_version", "asset_version", "task_type"]
        data = self.dataset(val_ratio=.34, split_group_keys=keys)
        validation = data.get_validation_dataset()
        self.assertFalse(set(data.episode_ids) & set(validation.episode_ids))
        train = {tuple(g[k] for k in keys) for g in data.train_group_values}
        val = {tuple(g[k] for k in keys) for g in data.val_group_values}
        self.assertFalse(train & val)
        self.assertEqual(("episode_0000" in data.episode_ids), ("episode_0001" in data.episode_ids))
        self.assertEqual(set(data.episode_ids) | set(validation.episode_ids),
                         {"episode_0000", "episode_0001", "episode_0002"})
        repeat = self.dataset(val_ratio=.34, split_group_keys=keys)
        self.assertEqual(data.train_episodes, repeat.train_episodes)
        self.assertEqual(data.val_episodes, repeat.val_episodes)

    def test_requested_condition_field_missing_raises_without_fallback(self):
        self.condition_attributes()
        with h5py.File(self.path, "r+") as f:
            del f["episode_0000"].attrs["scene_version"]
        with self.assertRaisesRegex(ValueError, "Missing split_group_keys attribute 'scene_version'.*no fallback"):
            self.dataset(val_ratio=0, split_group_keys=["source_slot_id", "scene_version"])

    def test_same_conditions_keep_split_when_episode_names_reorder(self):
        self.condition_attributes()
        before = self.dataset(val_ratio=.34, split_group_keys=["source_slot_id"])
        with h5py.File(self.path, "r+") as f:
            f.move("episode_0000", "episode_zz00")
            f.move("episode_0001", "episode_zz01")
        after = self.dataset(val_ratio=.34, split_group_keys=["source_slot_id"])
        self.assertEqual(before.train_group_values, after.train_group_values)
        self.assertEqual(before.val_group_values, after.val_group_values)

    def test_default_and_empty_keys_keep_original_episode_split(self):
        self.condition_attributes(one_condition=True)
        expected = np.random.default_rng(42).permutation(
            ["episode_0000", "episode_0001", "episode_0002"]).tolist()
        for keys in (None, []):
            data = self.dataset(val_ratio=.34, split_group_keys=keys)
            self.assertEqual(data.val_episodes, expected[:1])
            self.assertEqual(data.train_episodes, expected[1:])

    def test_one_condition_cannot_fake_a_validation_holdout(self):
        self.condition_attributes(one_condition=True)
        with self.assertRaisesRegex(ValueError, "at least two distinct groups"):
            self.dataset(val_ratio=.34, split_group_keys=["source_slot_id"])
        data = self.dataset(val_ratio=0, split_group_keys=["source_slot_id"])
        self.assertEqual(len(data.episode_ids), 3)
        self.assertEqual(data.val_episodes, [])

    def test_unknown_condition_is_not_treated_as_a_measured_group(self):
        self.condition_attributes()
        with h5py.File(self.path, "r+") as f:
            f["episode_0000"].attrs["source_slot_id"] = "unknown"
        with self.assertRaisesRegex(ValueError, "known finite scalar"):
            self.dataset(val_ratio=0, split_group_keys=["source_slot_id"])


if __name__ == "__main__":
    unittest.main()
