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
        self.collector.defer_publication = True
        from demos.lab_cuvette_project_release_v1.recording import install
        install(self)
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
        condition = self.options.get('lifecycle_condition')
        if condition:
            metadata['lifecycle_condition'] = str(condition)
            if condition != 'teacher':
                metadata['condition_group'] = 'controlled_lifecycle_diagnostic'
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
        from demos.lab_cuvette_project_release_v1.recording import persist_closed_receipts
        try:
            persist_closed_receipts(self)
        except Exception as error:
            errors.append(dict(resource='recording_receipt', error_type=type(error).__name__, error=str(error)))
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
                # The inherited tail has now written camera metadata, flushed
                # the terminal frame, released native video writers and saved
                # a PREPARED result. Finish every required log before eligibility.
                self.recorder.close()
                from demos.lab_cuvette_project_release_v1.recording import persist_closed_receipts
                persist_closed_receipts(self)
                self._write(self.episode_dir / 'finalization_timing.json', dict(
                    wall_seconds=time.perf_counter() - started,
                    publication_state='prepared_for_commit', episode_id=self.episode_id))
                final_labels = self.collector.prepared_labels(final=True)
                self._result.update(final_labels)
                from data_collectors.lab_cuvette_project_release_collector import atomic_text
                from data_collectors.lab_cuvette_env_v1_collector import json_text
                atomic_text(self.episode_dir / 'result.json', json_text(self._result) + '\n')
                self.collector.commit_publication()
                result = copy.deepcopy(self._result)
            return result
        except BaseException as error:
            self._finalization_error = dict(type=type(error).__name__, error=str(error))
            self.ended = True
            result = dict(self._result or {})
            result.update(complete=False, record_valid=False, record_integrity_valid=False,
                eligible_for_success_bc=False, eligible_for_failure_analysis=False,
                success_bc_eligible=False, trajectory_analysis_eligible=False, publication_state='failed',
                finalization_error=self._finalization_error)
            self._result = result
            try:
                if self.collector is not None:
                    self.collector.abort_publication(error)
                self._write(self.episode_dir / 'finalization_failure.json', result)
                self._write(self.episode_dir / 'result.json', result)
            finally:
                self._cleanup_episode()
            raise

    def reset(self, *args, **kwargs):
        options = dict(kwargs.get('options') or (args[1] if len(args) > 1 else {}) or {})
        if options.get('source_slot_id', self.base_cfg.rack.selected_slot_id) != self.base_cfg.rack.selected_slot_id:
            raise ValueError('Project_release_v1 standard reset cannot change the frozen source slot')
        self._finalization_error = None
        return super().reset(*args, **kwargs)
