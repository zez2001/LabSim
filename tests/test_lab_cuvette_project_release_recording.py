"""Lossless persistence tests, not measured native simulator performance."""
import gzip
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import h5py
from omegaconf import OmegaConf
import pytest

from demos.lab_cuvette_project_release_v1.recording import (
    LosslessGzipTextSink, adopt_existing_stream, install, iter_jsonl, persist_closed_receipts,
    verify_closed_episode,
)


def test_sink_preserves_every_utf8_byte_line_and_sha(tmp_path):
    text = '{"阶段":"RESET","t":0}\n{"phase":"MOVE","t":0.004166666666666667}\n'
    sink = LosslessGzipTextSink(tmp_path / 'physics.jsonl.gz')
    for part in (text[:7], text[7:40], text[40:]):
        sink.write(part)
    sink.flush()
    sink.close()
    sink.close()
    assert gzip.decompress(sink.path.read_bytes()) == text.encode('utf-8')
    assert sink.receipt()['line_count'] == 2
    assert sink.receipt()['uncompressed_sha256'] == hashlib.sha256(text.encode()).hexdigest()
    assert list(iter_jsonl(sink.path))[0]['阶段'] == 'RESET'
    with pytest.raises(ValueError, match='closed'):
        sink.write('must fail')


def test_adopt_preserves_all_initial_rows_then_continues_same_stream(tmp_path):
    raw = tmp_path / 'physics_records.jsonl'
    initial = '{"step":0}\n{"step":1}\n'
    raw.write_text(initial)
    recorder = SimpleNamespace(_physics=raw.open('a', encoding='utf-8'))
    sink = adopt_existing_stream(recorder, '_physics', raw)
    recorder._physics.write('{"step":2}\n')
    recorder._physics.close()
    assert not raw.exists()
    assert sink.receipt()['line_count'] == 3
    assert [row['step'] for row in iter_jsonl(sink.path)] == [0, 1, 2]
    assert [row['step'] for row in iter_jsonl(raw)] == [0, 1, 2]


def test_existing_compressed_file_is_not_overwritten_and_raw_remains_writable(tmp_path):
    raw = tmp_path / 'physics_records.jsonl'
    raw.write_text('{"step":0}\n')
    compressed = raw.with_suffix('.jsonl.gz')
    compressed.write_bytes(b'protected-history')
    recorder = SimpleNamespace(_physics=raw.open('a', encoding='utf-8'))
    with pytest.raises(FileExistsError):
        adopt_existing_stream(recorder, '_physics', raw)
    assert compressed.read_bytes() == b'protected-history'
    recorder._physics.write('{"step":1}\n')
    recorder._physics.close()
    assert [row['step'] for row in iter_jsonl(raw)] == [0, 1]


@pytest.mark.parametrize('mode,compressed,duplicate_video', [
    ('diagnostic', False, True), ('collect', True, False), ('eval', True, False)])
def test_record_modes_change_only_persistence(tmp_path, mode, compressed, duplicate_video):
    task = SimpleNamespace(episode_dir=tmp_path,
        cfg=OmegaConf.create(dict(release=dict(record_mode=mode), physics=dict(hz=240, control_hz=60))),
        recorder=SimpleNamespace(), collector=SimpleNamespace(save_video=True))
    for attribute, filename in (('_physics', 'physics_records.jsonl'), ('_contacts', 'native_contact_events.jsonl')):
        path = tmp_path / filename
        path.write_text('{"step":0}\n')
        setattr(task.recorder, attribute, path.open('a', encoding='utf-8'))
    task.collector.file = h5py.File(tmp_path / 'fixture.h5', 'x')
    task._write = lambda path, value: Path(path).write_text(json.dumps(value))
    install(task)
    assert task.collector.save_video is duplicate_video
    for attribute, filename in (('_physics', 'physics_records.jsonl'), ('_contacts', 'native_contact_events.jsonl')):
        getattr(task.recorder, attribute).write('{"step":1}\n')
        getattr(task.recorder, attribute).close()
        path = tmp_path / (filename + ('.gz' if compressed else ''))
        assert [row['step'] for row in iter_jsonl(path)] == [0, 1]
    task.collector.file.close()
    persist_closed_receipts(task)
    config = json.loads((tmp_path / 'recording_configuration.json').read_text())
    assert config['online_physics_hz'] == config['online_scoring_hz'] == 240
    assert config['policy_observation_hz'] == config['h5_images_hz'] == 60
    assert config['physics_contact_rows_dropped'] is False
    assert config['native_videos'] == ['side_camera.mp4', 'wrist_camera.mp4', 'dual_view.mp4']
    if compressed:
        receipt = json.loads((tmp_path / 'recording_closed_receipt.json').read_text())
        assert all(row['closed'] and row['line_count'] == 2 for row in receipt['streams'].values())
    verified = verify_closed_episode(tmp_path)
    assert all(row['line_count'] == 2 for row in verified['streams'].values())


def test_release_reuses_exact_step_and_scorer_sampling():
    from tasks.lab_cuvette_loading_project_release import LabCuvetteProjectRelease
    from tasks.lab_cuvette_loading_project_v1_1 import LabCuvetteProjectV11
    assert LabCuvetteProjectRelease.step is LabCuvetteProjectV11.step
