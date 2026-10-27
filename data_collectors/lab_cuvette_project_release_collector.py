"""Release-only transactional closure on the existing Env_v1 HDF5 payload.

This is not a resume mechanism. A failed/interrupted new episode remains
incomplete and is excluded by normal readers. Historical collectors are intact.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time

import cv2
import h5py
import numpy as np

from data_collectors.lab_cuvette_env_v1_collector import (
    LabCuvetteEnvV1Collector, _known_bool, json_safe, json_text,
)
from utils.episode_selection import NON_PHYSICAL_FAILURES


def atomic_text(path, text):
    """Replace one small metadata file, never exposing a partial JSON line."""
    path = Path(path)
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name + '.', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class LabCuvetteProjectReleaseCollector(LabCuvetteEnvV1Collector):
    VERSION = 'Project_release_v1'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.configuration.get('version') != self.VERSION:
            raise ValueError('Release collector requires Project_release_v1 config')
        self._finalized = None
        self._finalize_fingerprint = None
        self._finalizing = False
        self._publication_failed = False

    def begin_episode(self, *args, **kwargs):
        super().begin_episode(*args, **kwargs)
        self._finalized = self._finalize_fingerprint = None
        self._finalizing = self._publication_failed = False
        self.file.attrs.update(
            schema_version='labsim.lab_cuvette_loading.Project_release_v1.v1',
            qualification_schema='labsim.Project_v1_1.qualifications.v1',
            publication_state='recording', finalization_id='',
            record_integrity_valid='unknown', physics_trustworthy='unknown',
            success_bc_eligible=False, trajectory_analysis_eligible=False,
        )

    def _index_rows(self):
        path = self.output / 'dataset/meta/episode.jsonl'
        rows = [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
        return path, rows

    def _publish_index(self, row):
        path, rows = self._index_rows()
        if any(item.get('episode_id') == self.episode_id for item in rows):
            raise RuntimeError('Episode already present in publication index')
        atomic_text(path, ''.join(json_text(item) + '\n' for item in [*rows, row]))

    def _remove_own_index(self):
        path, rows = self._index_rows()
        if path.exists():
            atomic_text(path, ''.join(json_text(item) + '\n' for item in rows
                                     if item.get('episode_id') != self.episode_id))

    def _labels(self, result, evidence):
        if evidence.get('episode_id') != self.episode_id:
            self._integrity_errors.append('missing_or_different_independent_score_episode_id')
        if not self.count:
            self._integrity_errors.append('no_transitions')
        def check_stream_lengths(name, dataset):
            if (isinstance(dataset, h5py.Dataset) and dataset.ndim and
                    dataset.maxshape and dataset.maxshape[0] is None and
                    dataset.shape[0] != self.count):
                self._integrity_errors.append('incomplete_stream:' + name)
        self.file.visititems(check_stream_lengths)
        if self.count and not self.file['control_auxiliary/available'][:].all():
            self._integrity_errors.append('auxiliary_control_incomplete')
        for camera, count in self._camera_black_counts.items():
            if self.count and count == self.count:
                self._integrity_errors.append('all_frames_black:' + camera)
        errors = list(self._integrity_errors) + list(evidence.get('record_integrity_errors', []))
        if _known_bool(evidence.get('record_integrity_valid')) is False and not errors:
            errors.append('independent_score_declared_record_integrity_invalid')
        integrity = not errors
        outcome = _known_bool(evidence.get('task_success'))
        geometry = _known_bool(evidence.get('geometry_valid'))
        physics = _known_bool(evidence.get('physics_trustworthy'))
        domain = str(evidence.get('failure_domain', 'unknown'))
        failure = str(evidence.get('failure_type', result.get('failure_type', 'UNKNOWN')))
        reason = str(evidence.get('termination_reason', result.get('termination_reason', 'UNKNOWN')))
        task_type = str(evidence.get('task_type', self.file.attrs.get('task_type', 'loading')))
        valid = bool(_known_bool(evidence.get('record_valid')) is True and integrity and
                     physics is True and domain in {'none', 'task', 'safety', 'budget'} and
                     failure.upper() not in NON_PHYSICAL_FAILURES)
        success = bool(valid and outcome is True and geometry is True and task_type == 'loading'
                       and evidence.get('success_bc_eligible') is True)
        failure_eligible = bool(valid and outcome is False and task_type == 'loading' and
                                domain in {'task', 'safety', 'budget'} and failure != 'UNKNOWN')
        task_result = copy.deepcopy(evidence.get('task_result', dict(success=outcome, status='unknown')))
        qualification = dict(schema='labsim.Project_v1_1.qualifications.v1',
            task_result=task_result, record_integrity_valid=integrity,
            record_integrity_source='streaming_collector_checks_at_flush_close',
            record_integrity_errors=errors, physics_trustworthy=physics,
            physics_trust_scope=evidence.get('physics_trust_scope', 'unavailable'),
            failure_domain=domain, success_bc_eligible=success,
            trajectory_analysis_eligible=bool(integrity and self.count > 0),
            eligibility_pending_collector_integrity=False)
        labels = dict(record_valid=valid, task_success=outcome, geometry_valid=geometry,
            failure_type=failure, termination_reason=reason, task_type=task_type,
            eligible_for_success_bc=success, eligible_for_failure_analysis=failure_eligible,
            real_calibrated=False, complete=True, frames=self.count,
            qualification_schema=qualification['schema'],
            **{key: value for key, value in qualification.items() if key != 'schema'})
        return labels, qualification, task_result

    def finish_episode(self, result, independent_score=None):
        evidence = (json.loads(Path(independent_score).read_text(encoding='utf-8'))
                    if isinstance(independent_score, (str, Path)) else dict(independent_score or {}))
        fingerprint = hashlib.sha256(json_text(dict(result=result, score=evidence)).encode()).hexdigest()
        if self._finalized is not None:
            if fingerprint != self._finalize_fingerprint:
                raise ValueError('Finalized episode cannot be relabelled')
            return copy.deepcopy(self._finalized)
        if self.file is None or self._publication_failed:
            raise RuntimeError('No open publishable episode; failed closure requires a new episode')
        if self._finalizing:
            raise RuntimeError('Reentrant episode finalization')
        self._finalizing = True
        wall = time.perf_counter()
        summary = self.output / (self.name + '_result.json')
        marker = self.output / (self.name + '_complete.json')
        try:
            if summary.exists() or marker.exists():
                raise FileExistsError('Refusing existing result/completion metadata')
            labels, qualification, task_result = self._labels(result, evidence)
            finalization_id = hashlib.sha256((self.episode_id + fingerprint).encode()).hexdigest()
            attrs = {key: ('unknown' if value is None else value) for key, value in labels.items()
                     if not isinstance(value, (dict, list))}
            attrs.update(complete=False, publication_state='finalizing', finalization_id=finalization_id,
                success=labels['eligible_for_success_bc'], task_success_known=labels['task_success'] is not None,
                workflow_success=bool(labels['task_success'] is True and labels['task_type'] == 'loading'),
                phase_names_json=json_text(self._phases),
                independent_score_sha256=hashlib.sha256(json_text(evidence).encode()).hexdigest(),
                record_integrity_json=json_text(labels['record_integrity_errors']),
                camera_black_frame_counts_json=json_text(self._camera_black_counts))
            self.file.attrs.update(attrs)
            properties = dict(result=result, labels=labels,
                record_integrity_errors=labels['record_integrity_errors'], finalization_id=finalization_id)
            for name, value in (('independent_score_json', evidence), ('task_properties', properties),
                                ('qualification_json', qualification), ('task_result_json', task_result)):
                self.file.create_dataset(name, data=json_text(value), dtype=h5py.string_dtype())
            if self._terminal_observation is not None:
                terminal = self.file.create_group('terminal_observation')
                terminal.attrs.update(simulation_time=self._terminal_observation['simulation_time'],
                                      step_index=self._terminal_observation['step_index'])
                terminal.create_dataset('joint_positions', data=self._terminal_observation['joint_positions'])
                for camera, rgb in self._terminal_observation['camera_data'].items():
                    terminal.create_dataset(camera, data=rgb, compression=self.cfg.collector.compression)
                if self.writer is not None:
                    rgb = np.concatenate([np.transpose(self._terminal_observation['camera_data'][name], (1, 2, 0))
                                          for name in self.CAMERAS], axis=1)
                    self.writer.write(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
            if self.count:
                self.file['done'][-1] = True
                self.file['reward'][-1] = float(labels['task_success'] is True)
            self.file.attrs['video_frame_count'] = self.count + 1 if self.writer is not None else 0
            if self.writer is not None:
                self.writer.release()
                self.writer = None
            self.file.flush()
            self.file.close()
            self.file = None
            atomic_text(summary, json.dumps(json_safe(properties), ensure_ascii=False, indent=2, allow_nan=False) + '\n')
            atomic_text(marker, json_text(dict(schema='labsim.Project_release_v1.complete.v1',
                episode_id=self.episode_id, finalization_id=finalization_id, h5=self.path.name,
                result=summary.name, finalize_wall_seconds=time.perf_counter() - wall)) + '\n')
            # A raw H5 becomes eligible only after payload and sidecar closure.
            # The formal JSONL index is published last and can never advertise
            # an H5 that is still being written. No recovery/resume is implied.
            with h5py.File(self.path, 'r+') as output:
                output.attrs.update(publication_state='complete', complete=True)
                output.flush()
            self._publish_index(dict(episode_id=self.episode_id, episode_index=self.index,
                                     length=self.count, labels=labels, finalization_id=finalization_id))
            self._finalized = copy.deepcopy(labels)
            self._finalize_fingerprint = fingerprint
            self.episode_count += 1
            return copy.deepcopy(labels)
        except BaseException as error:
            self._publication_failed = True
            self.close()
            try:
                with h5py.File(self.path, 'r+') as output:
                    output.attrs.update(complete=False, publication_state='failed', record_valid=False,
                        eligible_for_success_bc=False, eligible_for_failure_analysis=False, success=False)
                self._remove_own_index()
                marker.unlink(missing_ok=True)
                if summary.exists():
                    atomic_text(summary, json_text(dict(episode_id=self.episode_id,
                        complete=False, record_valid=False, publication_state='failed',
                        failure='FINALIZATION_FAILED', error_type=type(error).__name__,
                        error=str(error))) + '\n')
                atomic_text(self.output / (self.name + '_incomplete.json'), json_text(dict(
                    episode_id=self.episode_id, complete=False, error_type=type(error).__name__,
                    error=str(error), failure='FINALIZATION_FAILED')) + '\n')
            except BaseException:
                # Disk/I/O may prevent any marker. H5 was never committed before
                # the last operation; no recovery/resume or success is implied.
                pass
            raise
        finally:
            self._finalizing = False
