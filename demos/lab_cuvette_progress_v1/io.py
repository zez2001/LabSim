"""Causal, bounded-memory Progress sidecars; never writes source HDF5 data."""
from __future__ import annotations

from collections import deque
import copy
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
import time


SCHEMA_VERSION = 'labsim.lab_cuvette_loading.progress.v1.2'
OUTPUT_NAMES = ('progress_v1.jsonl.gz', 'progress_events.jsonl',
                'progress_summary.json', 'progress_config.resolved.json')


def json_safe(value):
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    if hasattr(value, 'tolist'):
        return json_safe(value.tolist())
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Path):
        return str(value)
    return value


def json_text(value):
    return json.dumps(json_safe(value), ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False)


def object_sha256(value):
    return hashlib.sha256(json_text(value).encode('utf-8')).hexdigest()


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path, value):
    path = Path(path)
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name + '.', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(json.dumps(json_safe(value), ensure_ascii=False,
                                    indent=2, allow_nan=False) + '\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def iter_json_rows(path):
    """Read JSONL/gzip or legacy JSON arrays without changing original bytes."""
    path = Path(path)
    opener = gzip.open if path.suffix == '.gz' else open
    with opener(path, 'rt', encoding='utf-8') as stream:
        if path.name.endswith('.json'):
            rows = json.load(stream)
            if not isinstance(rows, list):
                raise ValueError('Expected a JSON array: ' + str(path))
            yield from rows
        else:
            for number, line in enumerate(stream, 1):
                if line.strip():
                    row = json.loads(line)
                    if not isinstance(row, dict):
                        raise ValueError(f'Expected a JSON object at {path}:{number}')
                    yield row


def compact_snapshot(snapshot):
    """Evaluator diagnostics only: raw scenes, camera pixels and actions stay upstream."""
    return {key: json_safe(value) for key, value in snapshot.items() if key != 'events'}


class ProgressWriter:
    """One instance per episode, updated at physics rate and saved at control rate.

    A transition owns events in ``(t_obs, t_next]``. The reset sample and events
    through the first control observation are retained separately in the summary.
    No future state is interpolated back to an earlier observation timestamp.
    """

    def __init__(self, output_directory, config, metadata=None, *, evaluator=None):
        self.output = Path(output_directory).resolve()
        self.output.mkdir(parents=True, exist_ok=True)
        if any((self.output / name).exists() for name in OUTPUT_NAMES):
            raise FileExistsError('Progress outputs already exist; use a new directory: ' + str(self.output))
        self.config, self.metadata = copy.deepcopy(config), copy.deepcopy(metadata or {})
        self.config_sha256 = object_sha256(self.config)
        if evaluator is None:
            from .core import ProgressEvaluator
            evaluator = ProgressEvaluator(self.config)
        self.evaluator = evaluator
        self.evaluator.reset(self.metadata)
        self.status, self.summary, self.closed = 'recording', None, False
        self.errors, self._snapshots, self._pending_events = [], deque(), []
        self._all_events, self._initial_events = [], []
        self.reset_snapshot = self.first_control_observation = None
        self._last_t = self._last_transition_end = None
        self.physics_count = self.transition_count = self._uncompressed_bytes = 0
        self.compute_wall_seconds = self.write_wall_seconds = self.physical_wall_seconds = 0.
        self._started = time.perf_counter()
        self._gzip = self._events = None
        atomic_json(self.output / 'progress_config.resolved.json', self.config)
        try:
            # Exclusive creation prevents accidental reuse even in a nonempty episode directory.
            self._raw = (self.output / OUTPUT_NAMES[0]).open('xb')
            self._gzip = gzip.GzipFile(filename='', mode='wb', fileobj=self._raw,
                                       compresslevel=1, mtime=0)
            self._events = (self.output / OUTPUT_NAMES[1]).open('x', encoding='utf-8')
        except BaseException:
            self._close_streams()
            raise

    def _assert_open(self):
        if self.closed or self.summary is not None:
            raise RuntimeError('Progress writer is closed or finalized')

    def _error(self, exc, operation):
        self.errors.append(dict(operation=operation, type=type(exc).__name__, message=str(exc)))
        self.status = 'interrupted'

    def physical(self, sample):
        self._assert_open()
        started = time.perf_counter()
        try:
            t = float(sample.get('t', sample.get('simulation_time')))
            if not math.isfinite(t) or (self._last_t is not None and t <= self._last_t):
                raise ValueError('Progress physics timestamps must increase strictly')
            snapshot = json_safe(self.evaluator.update(sample))
            self._last_t = t
            self.physics_count += 1
            self.compute_wall_seconds += time.perf_counter() - started
            compact = compact_snapshot(snapshot)
            self._snapshots.append((t, compact))
            if self.reset_snapshot is None:
                self.reset_snapshot = copy.deepcopy(compact)
            for event in snapshot.get('events', []):
                event = json_safe(event)
                self._all_events.append(event)
                self._pending_events.append(event)
                self._events.write(json_text(dict(schema=SCHEMA_VERSION, **event)) + '\n')
            self.physical_wall_seconds += time.perf_counter() - started
            return snapshot
        except BaseException as exc:
            self._error(exc, 'physical')
            raise

    def _at(self, t):
        # Exact physical samples are expected; missing samples stay explicitly unknown.
        for sample_t, snapshot in reversed(self._snapshots):
            if abs(sample_t - t) <= 1e-8:
                return copy.deepcopy(snapshot)
        return None

    def transition(self, t_obs, t_next, before=None, after=None, transition_metadata=None):
        self._assert_open()
        started = time.perf_counter()
        try:
            t_obs, t_next = float(t_obs), float(t_next)
            if not math.isfinite(t_obs + t_next) or t_next < t_obs:
                raise ValueError('Invalid Progress control interval')
            if self._last_transition_end is not None and t_obs < self._last_transition_end - 1e-8:
                raise ValueError('Overlapping or repeated Progress control interval')
            if self._last_t is None or t_next > self._last_t + 1e-8:
                raise ValueError('Control transition cannot consume future physics samples')
            before = compact_snapshot(before) if before is not None else self._at(t_obs)
            after = compact_snapshot(after) if after is not None else self._at(t_next)
            if self.first_control_observation is None:
                self.first_control_observation = copy.deepcopy(before)
                self._initial_events = [e for e in self._pending_events if float(e['t']) <= t_obs]
            events = [e for e in self._pending_events if t_obs < float(e['t']) <= t_next]
            gaps = [e for e in self._pending_events if float(e['t']) <= t_obs and
                    e not in self._initial_events]
            record = dict(schema=SCHEMA_VERSION, episode_id=self.metadata.get('episode_id'),
                transition_index=self.transition_count, t_obs=t_obs, t_next=t_next,
                interval_convention='(t_obs,t_next]', before=before, after=after,
                events=events, unassigned_gap_event_ids=[e.get('event_id') for e in gaps],
                transition=json_safe(transition_metadata or {}),
                evidence_alignment=dict(before_available=before is not None, after_available=after is not None))
            encoded = (json_text(record) + '\n').encode('utf-8')
            self._gzip.write(encoded)
            self._uncompressed_bytes += len(encoded)
            self.transition_count += 1
            self._last_transition_end = t_next
            self._pending_events = [e for e in self._pending_events if float(e['t']) > t_next]
            # Keep the next before state and any later captures, not an episode of raw scenes.
            while len(self._snapshots) > 1 and self._snapshots[1][0] <= t_next + 1e-8:
                self._snapshots.popleft()
            self.write_wall_seconds += time.perf_counter() - started
            return record
        except BaseException as exc:
            self._error(exc, 'transition')
            raise

    def flush(self):
        if self.closed:
            return
        if self._gzip is not None:
            self._gzip.flush()
            self._raw.flush()
        if self._events is not None:
            self._events.flush()

    def _close_streams(self):
        for name in ('_gzip', '_raw', '_events'):
            stream = getattr(self, name, None)
            if stream is not None and not stream.closed:
                try:
                    stream.close()
                except BaseException as exc:
                    self._error(exc, 'close:' + name)
        self.closed = True

    def finalize(self, termination=None, original_result=None):
        if self.summary is not None:
            return copy.deepcopy(self.summary)
        termination = copy.deepcopy(termination or {})
        try:
            result = json_safe(self.evaluator.finalize(termination))
            known = {e.get('event_id') for e in self._all_events}
            for event in result.get('events', []):
                if event.get('event_id') not in known:
                    # Finalization is a lifecycle emission, not a retroactive control label.
                    self._all_events.append(event)
                    self._pending_events.append(event)
                    self._events.write(json_text(dict(schema=SCHEMA_VERSION,
                        emission='finalize', **event)) + '\n')
                    known.add(event.get('event_id'))
        except BaseException as exc:
            self._error(exc, 'finalize_evaluator')
            result = dict(progress_complete=None, termination=termination,
                          last_snapshot=copy.deepcopy(self._snapshots[-1][1]) if self._snapshots else None)
        self._close_streams()
        requested_status = termination.get('progress_status', 'complete')
        self.status = 'interrupted' if self.errors else requested_status
        if self.status not in {'complete', 'partial', 'interrupted'}:
            self.status = 'partial'
        files = {}
        for name in OUTPUT_NAMES:
            path = self.output / name
            if name != 'progress_summary.json' and path.exists():
                files[name] = dict(bytes=path.stat().st_size, sha256=file_sha256(path))
        original = json_safe(original_result)
        self.summary = dict(result, schema=SCHEMA_VERSION, progress_schema_version=SCHEMA_VERSION,
            progress_evaluator_version=self.config.get('progress_evaluator_version', getattr(self.evaluator, 'VERSION', 'progress.v1')),
            evaluator_schema_version=self.config.get('progress_schema_version'),
            output_integrity=dict(status=self.status, complete=self.status == 'complete', errors=self.errors,
                                  files=files, hashes_exclude='progress_summary.json (self), report and linked videos'),
            metadata=json_safe(self.metadata), config_sha256=self.config_sha256,
            reset_snapshot=self.reset_snapshot, first_control_observation=self.first_control_observation,
            initial_events=self._initial_events or ([e for e in self._all_events
                if self.reset_snapshot and float(e['t']) <= float(self.reset_snapshot['t'])]),
            unassigned_terminal_events=self._pending_events,
            original_result=original, original_result_sha256=object_sha256(original),
            recording=dict(physics_samples=self.physics_count, control_transitions=self.transition_count,
                event_count=len(self._all_events), uncompressed_transition_bytes=self._uncompressed_bytes,
                stored_bytes_excluding_summary=sum(v['bytes'] for v in files.values()),
                compute_wall_seconds=self.compute_wall_seconds, write_wall_seconds=self.write_wall_seconds,
                physical_annotation_wall_seconds=self.physical_wall_seconds,
                total_annotation_wall_seconds=self.physical_wall_seconds + self.write_wall_seconds,
                lifecycle_wall_seconds=time.perf_counter() - self._started,
                interval_convention='(t_obs,t_next]', reset_separate=True))
        atomic_json(self.output / 'progress_summary.json', self.summary)
        return copy.deepcopy(self.summary)

    def abort(self, error, termination=None, original_result=None):
        if self.summary is not None:
            return copy.deepcopy(self.summary)
        if error is not None:
            self._error(error if isinstance(error, BaseException) else RuntimeError(str(error)), 'abort')
        return self.finalize(dict(termination or {}, progress_status='interrupted'), original_result)

    def close(self):
        if self.summary is None:
            return self.abort(None, {'termination_reason': 'writer_closed_without_finalize'})
        self._close_streams()
        return copy.deepcopy(self.summary)

    def __enter__(self):
        return self

    def __exit__(self, kind, error, traceback):
        if error is not None:
            self.abort(error)
        else:
            self.close()
        return False
