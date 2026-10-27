"""Release facade with explicit reset-cache evidence; physical executor unchanged."""
from demos.lab_cuvette_project_v1_1.environment import ProjectEnvironment as Previous


class ProjectEnvironment(Previous):
    def reset(self, *args, **kwargs):
        old_episode = getattr(self.task, 'episode_id', None)
        observation = super().reset(*args, **kwargs)
        if observation['episode_id'] == old_episode:
            raise RuntimeError('Reset must create a new episode identity')
        if self._receipts or self._payload_hashes:
            raise RuntimeError('Reset retained action receipt state')
        self.task._write(self.task.episode_dir / 'facade_reset_audit.json', dict(
            previous_episode_id=old_episode, episode_id=observation['episode_id'],
            receipt_count=len(self._receipts), payload_hash_count=len(self._payload_hashes),
            requested_opening_m=self.requested_opening,
            requested_effort_limit_N=self.requested_effort,
            observation_id=observation['observation_id']))
        return observation
