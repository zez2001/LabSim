"""Native release task: the validated environment with portable release metadata.

Scene construction, actual stepping, independent scoring and the streaming
collector remain the existing implementations; this subclass adds their project
lifecycle rather than a second physical executor.
"""
import copy
import json
from pathlib import Path
import subprocess
import sys
import numpy as np
from omegaconf import OmegaConf
from tasks.lab_cuvette_loading_env_v1 import LabCuvetteLoadingEnvV1
from demos.lab_cuvette_project_v1.contract import scene_contract, code_version
from demos.lab_cuvette_project_v1.runtime import ROOT, usd_environment


class LabCuvetteProjectV1(LabCuvetteLoadingEnvV1):
    def _ensure_bound_audit(self):
        from demos.lab_cuvette_project_v1.geometry_audit import binding
        previous = self.geometry_audit.get('binding')
        if previous and binding(self.cfg, previous['files'])['fingerprint'] == previous['fingerprint']:
            return
        config = self.episode_dir / 'audit_input.yaml'
        OmegaConf.save(self.cfg, config)
        cache = ROOT / self.cfg.env.geometry_audit_cache
        subprocess.run([sys.executable, '-m', self.cfg.env.geometry_audit_module,
            '--config', str(config), '--output', str(cache),
            '--geometry-site', str(self.cfg.env.shapely_site)], cwd=ROOT,
            env=usd_environment(), check=True)
        latest = json.loads((cache / 'latest.json').read_text())
        self.geometry_audit = json.loads((cache / latest['audit_relative_path']).read_text())

    def reset(self, seed=None, options=None):
        requested = dict(options or {})
        if requested.get('mode', 'standard') != 'standard':
            raise ValueError('Project_v1 native task supports only the fixed standard scene')
        if requested.get('subtask', requested.get('task_type', 'loading')) != 'loading':
            raise ValueError('Project_v1 native task supports the complete loading task only')
        # Validate the declared base scene before the inherited reset handler
        # can create physics or write an initialization error into a prior run.
        scene_contract(self.base_cfg)
        return super().reset(seed, options)

    def _reset(self, seed=None, options=None):
        observation, info = super()._reset(seed, options)
        # The first capture is at the distant source rack; correct the target
        # containment frame before any task action or target approach occurs.
        if self.recorder.material_geometry is not None:
            self.recorder.material_geometry.offset = np.asarray(self.cfg.geometry.target_loading_offset_local_m[:2], float)
            meta = self.episode_dir / 'physics_capture_meta.json'
            value = json.loads(meta.read_text())
            value['material_geometry'] = self.recorder.material_geometry.metadata()
            value['target_frames'] = dict(
                original_seat_floor_world_m=self.ctx['fixtures']['seat_original_floor'].tolist(),
                loading_floor_world_m=self.ctx['fixtures']['target_floor'].tolist(),
                loading_offset_seat_local_m=list(self.cfg.geometry.target_loading_offset_local_m),
                seat_geometry_changed=False)
            self._write(meta, value)
        contract = scene_contract(self.base_cfg, self.geometry_audit)
        self.release_contract = contract
        self._write(self.episode_dir / 'project_scene_contract.json', contract)
        metadata = dict(scene_version='Project_v1', scene_mode='standard',
            frozen_scene_sha256=contract['frozen_scene_sha256'],
            control_config_sha256=contract['frozen_scene_sha256'], code_commit=code_version(),
            actual_execution_commit=code_version(), asset_id=self.cfg.asset_id,
            asset_sha256=self.cfg.asset_selection.asset_sha256,
            condition_group=self.cfg.experiment.get('condition_group', 'natural'),
            deterministic_action_deviation_json=json.dumps(dict(self.cfg.experiment.get('deviation', {})), sort_keys=True),
            fixed_collection_eligible=True)
        if self.collector.file is not None:
            self.collector.file.attrs.update(metadata)
        self._write(self.episode_dir / 'release_metadata.json', metadata)
        return self.get_observation(), info

    def _public_observation(self):
        observation = super()._public_observation()
        observation.update(observation_id=f'{self.episode_id}:{self.control_steps}',
                           gripper_opening_m=float(np.sum(self.debug['finger_joint_positions_m'])),
                           gripper_effort_limit_N=float(self.effort),
                           finger_contact_N=np.asarray(self.debug['finger_contact_N']).copy())
        return observation
