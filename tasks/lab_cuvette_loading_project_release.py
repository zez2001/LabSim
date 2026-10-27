"""Opt-in release lifecycle; keeps the validated v1.1 physical implementation."""
from __future__ import annotations
import copy
import json
import time

from tasks.lab_cuvette_loading_project_v1_1 import LabCuvetteProjectV11


class LabCuvetteProjectRelease(LabCuvetteProjectV11):
    def _reset(self, seed=None, options=None):
        started = time.perf_counter()
        observation, info = super()._reset(seed, options)
        from demos.lab_cuvette_project_release_v1.contract import scene_contract
        self.release_contract = scene_contract(self.base_cfg, self.geometry_audit)
        self._write(self.episode_dir / 'project_scene_contract.json', self.release_contract)
        metadata_path = self.episode_dir / 'release_metadata.json'
        metadata = json.loads(metadata_path.read_text())
        metadata.update(scene_version='Project_release_v1',
            frozen_scene_sha256=self.release_contract['frozen_scene_sha256'],
            control_config_sha256=self.release_contract['frozen_scene_sha256'],
            action_interface_version='Project_release_v1.actions.v1',
            physical_baseline='Project_v1_1',
            lifecycle_version='Project_release_v1.transactional_lifecycle.v1')
        self._write(metadata_path, metadata)
        self.collector.file.attrs.update(metadata)
        self._write(self.episode_dir / 'reset_audit.json', dict(
            schema='labsim.Project_release_v1.reset.v1', episode_id=self.episode_id,
            episode_index=self.episode_index, control_steps=self.control_steps,
            physics_steps=self.steps, simulation_time=self.t,
            gripper_target_m=self.grip, effort_limit_N=self.effort,
            policy_latch=self._policy_latch, policy_latch_contact=self._policy_latch_contact,
            contact_hold_state=copy.deepcopy(self.contact_hold.__dict__),
            tracking_state=None if self.tracking_compensator is None else copy.deepcopy(self.tracking_compensator.__dict__),
            tracking_sample_control_step=self._tracking_sample_control_step,
            scorer_rows=len(self.scorer.rows), ended=self.ended,
            result_is_none=self._result is None, tick_trace_is_none=self._tick_trace is None,
            collector_count=self.collector.count, collector_file_open=self.collector.file is not None,
            reset_wall_seconds=time.perf_counter() - started))
        return observation, info

    def _cleanup_episode(self):
        # The old cleanup assumes finalize reached its video-release tail. A
        # disk/render exception can bypass it. Always close every current owner.
        errors = []
        for writer in getattr(self, '_video_writers', {}).values():
            try:
                writer.release()
            except Exception as error:
                errors.append(dict(resource='video', error_type=type(error).__name__, error=str(error)))
        self._video_writers = {}
        for name in ('collector', 'recorder', 'rig'):
            owner = getattr(self, name, None)
            if owner is not None:
                try:
                    owner.close()
                except Exception as error:
                    errors.append(dict(resource=name, error_type=type(error).__name__, error=str(error)))
                finally:
                    setattr(self, name, None)
        if self.ctx is not None:
            try:
                self.ctx['world'].stop()
                self.ctx['world'].clear()
            except Exception as error:
                errors.append(dict(resource='world', error_type=type(error).__name__, error=str(error)))
            finally:
                self.ctx = None
        self._cleanup_errors = errors
        if errors and getattr(self, 'episode_dir', None):
            self._write(self.episode_dir / 'cleanup_errors.json', errors)

    def finalize_episode(self, termination_reason='POLICY_BUDGET', failure_type=None):
        if self._result is not None and getattr(self, '_finalization_error', None):
            raise RuntimeError('Episode closure failed; reset before continuing')
        if self._result is not None:
            return copy.deepcopy(self._result)
        started = time.perf_counter()
        try:
            result = super().finalize_episode(termination_reason, failure_type)
            if result is not None:
                self._write(self.episode_dir / 'finalization_timing.json', dict(
                    wall_seconds=time.perf_counter() - started,
                    publication_state='complete', episode_id=self.episode_id))
            return result
        except BaseException as error:
            self._finalization_error = dict(type=type(error).__name__, error=str(error))
            self.ended = True
            result = dict(self._result or {})
            result.update(complete=False, record_valid=False, record_integrity_valid=False,
                eligible_for_success_bc=False, eligible_for_failure_analysis=False,
                success_bc_eligible=False, publication_state='failed',
                finalization_error=self._finalization_error)
            self._result = result
            try:
                self._write(self.episode_dir / 'finalization_failure.json', result)
            finally:
                self._cleanup_episode()
            raise

    def reset(self, *args, **kwargs):
        options = dict(kwargs.get('options') or (args[1] if len(args) > 1 else {}) or {})
        if options.get('source_slot_id', self.base_cfg.rack.selected_slot_id) != self.base_cfg.rack.selected_slot_id:
            raise ValueError('Project_release_v1 standard reset cannot change the frozen source slot')
        self._finalization_error = None
        return super().reset(*args, **kwargs)
