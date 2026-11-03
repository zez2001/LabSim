"""Optional release-only diagnostics around existing recorder/collector instances.

The wrappers run after the original methods, consume copies, and never call a
simulation, observation, controller, scorer, or reward method. No class in the
shared physical implementation is patched.
"""
from __future__ import annotations

import copy
import functools
import json
from pathlib import Path
import subprocess


def _get(value, key, default=None):
    return value.get(key, default) if hasattr(value, 'get') else getattr(value, key, default)


def enabled(task):
    return bool(_get(_get(getattr(task, 'base_cfg', {}), 'progress', {}), 'enabled', False))


def _plain(value):
    from omegaconf import OmegaConf
    if OmegaConf.is_config(value):
        return OmegaConf.to_container(value, resolve=True)
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if hasattr(value, 'tolist'):
        return value.tolist()
    return value


def _write_failure(path, value):
    # A full disk must not make diagnostic error reporting fail the task too.
    try:
        from .io import atomic_json
        atomic_json(path, value)
    except Exception:
        pass


class OnlineProgressSession:
    """One episode's sidecar owner, including failure and interruption closure."""

    def __init__(self, task, recorder):
        self.task, self.recorder = task, recorder
        self.output = Path(task.episode_dir)
        self.writer, self.summary = None, None
        self.errors, self.finalized = [], False
        self.physics_count = self.transition_count = 0
        self.metadata = dict(episode_id=task.episode_id,
            scene_version=str(_get(task.cfg, 'version', 'unknown')),
            task=str(_get(task.cfg, 'task_type', 'lab_cuvette_loading')),
            source_episode_directory=str(self.output.resolve()),
            evidence_source='original PhysicsRecorder.capture; every physical step including reset step 0',
            evidence_coverage='physics_rate', progress_mode='online',
            original_reward_unchanged=True, evaluator_does_not_control_simulation=True)

    def _failure(self, error, operation):
        self.errors.append(dict(operation=operation, type=type(error).__name__, message=str(error)))
        _write_failure(self.output / 'progress_failure.json', dict(
            schema='labsim.lab_cuvette_loading.progress.online_failure.v1',
            episode_id=self.metadata['episode_id'], progress_status='partial',
            errors=self.errors, original_task_result_preserved=True))

    def _start(self, sample):
        from .config import resolve_config
        from .io import ProgressWriter, atomic_json
        cfg = _plain(self.task.cfg)
        self.metadata.update(asset_id=cfg.get('asset_id'),
            asset_sha256=cfg.get('asset_selection', {}).get('asset_sha256'),
            asset_registry_sha256=cfg.get('asset_selection', {}).get('registry_sha256'),
            source_slot_id=cfg.get('rack', {}).get('selected_slot_id'),
            target_seat_id=cfg.get('adapter', {}).get('selected_target_seat_id'),
            layout=_plain(getattr(self.recorder, 'layout', {})))
        vertices = getattr(self.recorder, 'vertices', None)
        if vertices is not None:
            self.metadata['vessel_body_local_bounds_m'] = _plain([vertices.min(0), vertices.max(0)])
        meta_path = self.output / 'physics_capture_meta.json'
        if meta_path.exists():
            self.metadata['physics_capture_meta'] = json.loads(meta_path.read_text())
        try:
            self.metadata['code_commit'] = subprocess.check_output(
                ['git', 'rev-parse', 'HEAD'], cwd=Path(__file__).resolve().parents[2], text=True).strip()
        except (OSError, subprocess.CalledProcessError):
            self.metadata['code_commit'] = 'unknown'
        # This also makes fixed geometry inputs reproducible by offline replay.
        atomic_json(self.output / 'progress_input_metadata.json', self.metadata)
        config = resolve_config(cfg, episode_metadata=self.metadata, initial_sample=sample,
                                overrides=cfg.get('progress', {}).get('configuration', {}))
        self.writer = ProgressWriter(self.output, config, metadata=self.metadata)

    def physical(self, row):
        if self.errors or self.finalized:
            return
        try:
            sample = copy.deepcopy(row)
            trace = getattr(self.task, '_tick_trace', None)
            if (not trace or trace.get('action', {}).get('episode_id') != self.task.episode_id
                    or float(sample.get('t', 0.)) <= 1e-12):
                trace = None
            sample['_execution'] = dict(available=bool(trace),
                raw_action=copy.deepcopy(trace.get('action')) if trace else None,
                command_q9=sample.get('command_q9'), gripper_target_m=sample.get('gripper_target_m'),
                source='executed control action' if trace else 'reset initialization; no control action')
            if self.writer is None:
                self._start(sample)
            self.writer.physical(sample)
            self.physics_count += 1
        except Exception as error:
            self._failure(error, 'physical')

    def transition(self, state, command, next_state, flags):
        if self.errors or self.finalized:
            return
        try:
            if self.writer is None:
                raise RuntimeError('Control transition has no recorded physical samples')
            raw = command.get('raw_output') or {}
            self.writer.transition(float(state['simulation_time']), float(next_state['simulation_time']),
                transition_metadata=dict(obs_step=int(state['step_index']),
                    next_obs_step=int(next_state['step_index']),
                    terminated=bool(flags.get('terminated')), truncated=bool(flags.get('truncated')),
                    action_id=raw.get('action_id') if isinstance(raw, dict) else None,
                    original_reward=flags.get('reward'),
                    source='original collector.cache_transition after successful cache'))
            self.transition_count += 1
        except Exception as error:
            self._failure(error, 'transition')

    def _source_identity(self):
        from .io import file_sha256
        paths = [self.output / 'config.yaml']
        for name in ('physics_records.jsonl', 'native_contact_events.jsonl'):
            path = self.output / name
            paths.append(path if path.exists() else path.with_suffix(path.suffix + '.gz'))
        self.metadata['source_files'] = [dict(path=str(path.resolve()), bytes=path.stat().st_size,
            sha256=file_sha256(path)) for path in paths if path.exists()]
        self.metadata['source_h5_identity'] = dict(
            path=str(getattr(getattr(self.task, 'collector', None), 'path', 'unknown')),
            hash_status='not_hashed_before_original_publication_commit',
            reason='Original collector publication mutates H5 completion metadata after sidecar closure')

    def finalize(self, termination=None, original_result=None, *, interrupted=False):
        if self.finalized:
            return copy.deepcopy(self.summary)
        termination = dict(termination or {})
        self.finalized = True
        try:
            self._source_identity()
            if self.writer is None:
                raise RuntimeError('Progress initialization did not produce a physical sample')
            self.writer.metadata.update(self.metadata)
            if self.errors:
                termination['progress_status'] = 'partial'
                self.summary = self.writer.abort(RuntimeError(str(self.errors)),
                    termination=termination, original_result=original_result)
            else:
                termination['progress_status'] = 'interrupted' if interrupted else 'complete'
                self.summary = self.writer.finalize(termination=termination, original_result=original_result)
        except Exception as error:
            self._failure(error, 'finalize')
            if self.writer is not None:
                try:
                    self.summary = self.writer.abort(error, termination=dict(termination, progress_status='partial'),
                                                      original_result=original_result)
                except Exception as close_error:
                    self._failure(close_error, 'abort')
        finally:
            if self.writer is not None:
                try:
                    self.writer.close()
                except Exception as error:
                    self._failure(error, 'close')
        if self.summary is None or self.errors:
            self.summary = dict(self.summary or {})
            integrity = self.summary.get('output_integrity', {})
            integrity = dict(integrity) if isinstance(integrity, dict) else {}
            integrity.update(status='partial', complete=False, errors=copy.deepcopy(self.errors))
            self.summary.update(
                schema='labsim.lab_cuvette_loading.progress.v1',
                episode_id=self.metadata['episode_id'], progress_status='partial',
                output_integrity=integrity, errors=copy.deepcopy(self.errors),
                physics_samples_processed=self.physics_count, control_transitions_written=self.transition_count,
                original_task_result_preserved=True)
            _write_failure(self.output / 'progress_summary.json', self.summary)
        return copy.deepcopy(self.summary)


def _bind_owner(task, name, owner):
    """Install only on new release-owned instances, before reset's first capture."""
    if not enabled(task):
        return
    if name == 'recorder':
        session = OnlineProgressSession(task, owner)
        task._progress_session = session
        task._progress_unhandled_error = None
        original = owner.capture

        @functools.wraps(original)
        def capture(*args, **kwargs):
            row = original(*args, **kwargs)
            session.physical(row)
            return row
        owner.capture = capture
    elif name == 'collector':
        session = getattr(task, '_progress_session', None)
        if session is None:
            return
        original = owner.cache_transition

        @functools.wraps(original)
        def cache_transition(state, command, next_state, flags):
            result = original(state, command, next_state, flags)
            session.transition(state, command, next_state, flags)
            return result
        owner.cache_transition = cache_transition


def bind_owner(task, name, owner):
    try:
        _bind_owner(task, name, owner)
    except Exception as error:
        session = getattr(task, '_progress_session', None)
        if session is not None:
            session._failure(error, 'bind:' + name)
        else:
            task._progress_installation_error = dict(type=type(error).__name__, message=str(error))
            if getattr(task, 'episode_dir', None):
                _write_failure(Path(task.episode_dir) / 'progress_failure.json', dict(
                    progress_status='partial', errors=[task._progress_installation_error]))


def finish(task, termination=None, *, interrupted=False):
    session = getattr(task, '_progress_session', None)
    if session is None:
        if enabled(task) and isinstance(getattr(task, '_result', None), dict):
            task._result.update(progress_status='partial', progress_summary='progress_failure.json')
        return None
    summary = session.finalize(termination, getattr(task, '_result', None), interrupted=interrupted)
    status = ('partial' if session.errors or getattr(task, '_progress_unhandled_error', None) else
              summary.get('progress_status', getattr(session.writer, 'status', 'interrupted')))
    if isinstance(getattr(task, '_result', None), dict):
        task._result.update(progress_status=status, progress_summary='progress_summary.json')
    return status
