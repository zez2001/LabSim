"""Release-only lossless persistence modes; online physics sampling is untouched."""
from __future__ import annotations
import gzip
import hashlib
from pathlib import Path
import time

MODES = frozenset(('diagnostic', 'collect', 'eval'))


class LosslessGzipTextSink:
    """A text stream replacement with a receipt for every uncompressed byte."""
    def __init__(self, path, *, compresslevel=1):
        self.path = Path(path)
        self._binary = self.path.open('xb')
        try:
            self._gzip = gzip.GzipFile(filename='', mode='wb', fileobj=self._binary,
                                       compresslevel=compresslevel, mtime=0)
        except BaseException:
            self._binary.close()
            raise
        self._digest = hashlib.sha256()
        self.uncompressed_bytes = self.line_count = self.write_calls = 0
        self.close_wall_seconds = 0.
        self.closed = False
        self.close_succeeded = False
        self.compresslevel = compresslevel

    def write(self, text):
        if self.closed:
            raise ValueError('Write to closed lossless log sink')
        encoded = text.encode('utf-8')
        written = self._gzip.write(encoded)
        if written != len(encoded):
            raise OSError('Partial gzip log write')
        self._digest.update(encoded)
        self.uncompressed_bytes += len(encoded)
        self.line_count += text.count('\n')
        self.write_calls += 1
        return len(text)

    def flush(self):
        if not self.closed:
            self._gzip.flush()
            self._binary.flush()

    def close(self):
        if self.closed:
            return
        started = time.perf_counter()
        try:
            self._gzip.close()
            self.close_succeeded = True
        finally:
            self._binary.close()
            self.close_wall_seconds = time.perf_counter() - started
            self.closed = True

    def receipt(self):
        return dict(path=self.path.name, compression='gzip', compresslevel=self.compresslevel,
            closed=self.closed, line_count=self.line_count, write_calls=self.write_calls,
            close_succeeded=self.close_succeeded,
            uncompressed_bytes=self.uncompressed_bytes,
            uncompressed_sha256=self._digest.hexdigest(),
            stored_bytes=self.path.stat().st_size,
            close_wall_seconds=self.close_wall_seconds,
            semantics='Every original UTF-8 byte retained; no physics/contact rows dropped')


def adopt_existing_stream(recorder, attribute, original_path):
    """Preserve reset's already-written early fall, then continue the same stream."""
    original_path = Path(original_path)
    stream = getattr(recorder, attribute)
    stream.flush()
    stream.close()
    compressed_path = original_path.with_suffix(original_path.suffix + '.gz')
    sink = None
    try:
        sink = LosslessGzipTextSink(compressed_path)
        with original_path.open('r', encoding='utf-8', newline='') as initial:
            for block in iter(lambda: initial.read(64 * 1024), ''):
                sink.write(block)
        sink.flush()
        setattr(recorder, attribute, sink)
        original_path.unlink()  # only this new episode's newly created raw file
        return sink
    except BaseException:
        if sink is not None:
            sink.close()
            compressed_path.unlink(missing_ok=True)
        setattr(recorder, attribute, original_path.open('a', encoding='utf-8', newline=''))
        raise


def install(task):
    mode = str(task.cfg.release.get('record_mode', 'diagnostic'))
    if mode not in MODES:
        raise ValueError('record_mode must be diagnostic, collect or eval')
    task._recording_sinks = {}
    if mode != 'diagnostic':
        for attribute, filename in (('_physics', 'physics_records.jsonl'),
                                    ('_contacts', 'native_contact_events.jsonl')):
            task._recording_sinks[attribute] = adopt_existing_stream(
                task.recorder, attribute, task.episode_dir / filename)
        # H5 retains both full-frequency training cameras. The original native
        # side/wrist/dual 30 Hz videos also remain; only the fourth MP4 is omitted.
        task.collector.save_video = False
    task.collector.file.attrs.update(record_mode=mode,
        persisted_physics_sampling='all original physics steps; lossless gzip' if mode != 'diagnostic' else 'all original physics steps; plain JSONL',
        collector_duplicate_video_enabled=task.collector.save_video)
    task._write(task.episode_dir / 'recording_configuration.json', dict(
        schema='labsim.Project_release_v1.recording.v1', mode=mode,
        online_physics_hz=int(task.cfg.physics.hz), online_scoring_hz=int(task.cfg.physics.hz),
        policy_observation_hz=int(task.cfg.physics.control_hz), h5_images_hz=int(task.cfg.physics.control_hz),
        native_videos=['side_camera.mp4', 'wrist_camera.mp4', 'dual_view.mp4'], native_video_hz=30,
        collector_duplicate_video_enabled=task.collector.save_video,
        physics_contact_rows_dropped=False, execution_trace_unchanged=True,
        h5_schema_and_image_specification_unchanged=True,
        storage='plain JSONL' if mode == 'diagnostic' else 'lossless gzip level1',
        early_initialization_rows_retained=True))


def persist_closed_receipts(task):
    sinks = getattr(task, '_recording_sinks', {})
    if sinks:
        task._write(task.episode_dir / 'recording_closed_receipt.json', dict(
            schema='labsim.Project_release_v1.recording_closed.v1',
            mode=str(task.cfg.release.record_mode), streams={name: sink.receipt() for name, sink in sinks.items()},
            online_sampling_unchanged=True))
        task._recording_sinks = {}


def iter_jsonl(path):
    """Normal report/audit reader for either release mode; one row at a time."""
    import json
    path = Path(path)
    if not path.exists() and path.suffix != '.gz':
        path = path.with_suffix(path.suffix + '.gz')
    opener = gzip.open if path.suffix == '.gz' else open
    with opener(path, 'rt', encoding='utf-8') as stream:
        for line in stream:
            yield json.loads(line)


def verify_closed_episode(episode_dir):
    """Stream/decompress completed logs; check byte receipts without H5 mutation."""
    import json
    episode_dir = Path(episode_dir)
    receipt_path = episode_dir / 'recording_closed_receipt.json'
    expected = json.loads(receipt_path.read_text()) if receipt_path.exists() else {}
    results = {}
    for attribute, filename in (('_physics', 'physics_records.jsonl'),
                                ('_contacts', 'native_contact_events.jsonl')):
        source = episode_dir / filename
        if not source.exists():
            source = source.with_suffix(source.suffix + '.gz')
        digest, size, lines = hashlib.sha256(), 0, 0
        opener = gzip.open if source.suffix == '.gz' else open
        with opener(source, 'rb') as stream:
            for block in iter(lambda: stream.read(4 * 1024 * 1024), b''):
                digest.update(block)
                size += len(block)
                lines += block.count(b'\n')
        measured = dict(path=source.name, line_count=lines, uncompressed_bytes=size,
                        uncompressed_sha256=digest.hexdigest(), stored_bytes=source.stat().st_size)
        original = expected.get('streams', {}).get(attribute)
        if original is not None:
            measured['matches_streaming_receipt'] = all(measured[key] == original[key]
                for key in ('line_count', 'uncompressed_bytes', 'uncompressed_sha256', 'stored_bytes'))
            measured['writer_close_succeeded'] = original.get('close_succeeded') is True
            if not measured['matches_streaming_receipt'] or not measured['writer_close_succeeded']:
                raise ValueError('Closed log differs from streaming receipt: ' + source.name)
        results[attribute] = measured
    return dict(schema='labsim.Project_release_v1.lossless_log_verification.v1',
        mode=expected.get('mode', 'diagnostic'), streams=results,
        verifies='All uncompressed bytes, newline counts and gzip EOF/CRC; no rows sampled or changed')


if __name__ == '__main__':
    import argparse
    import json
    parser = argparse.ArgumentParser(description='Verify closed release physics/contact logs losslessly')
    parser.add_argument('episode_directory', type=Path)
    args = parser.parse_args()
    import os
    manifest = json.loads((args.episode_directory.parent / 'run_manifest.json').read_text())
    try:
        os.kill(int(manifest['process_id']), 0)
    except ProcessLookupError:
        pass
    else:
        raise RuntimeError('Source Isaac process still exists; verify logs only after it exits')
    print(json.dumps(verify_closed_episode(args.episode_directory), indent=2))
