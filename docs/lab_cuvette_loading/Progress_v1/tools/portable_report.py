#!/usr/bin/env python3
"""Package an existing Progress report with browser-compatible real-video copies.

Example (run after episode closure and offline analysis):
  python docs/lab_cuvette_loading/Progress_v1/tools/portable_report.py --progress OUTPUT_SIDECAR \
      --episode ORIGINAL_EPISODE --output NEW_PORTABLE_DIRECTORY

Requires the existing local ffmpeg/ffprobe. No simulation, frame synthesis,
temporal resampling or source modification occurs. The original MP4 remains
authoritative; H264 files are visibly documented display derivatives.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def probe(path):
    command = ['ffprobe', '-v', 'error', '-select_streams', 'v:0',
        '-show_entries', 'stream=codec_name,codec_tag_string,width,height,nb_frames,r_frame_rate,duration',
        '-of', 'json', str(path)]
    result = json.loads(subprocess.check_output(command, text=True))
    if len(result.get('streams', [])) != 1:
        raise ValueError('Expected exactly one selected video stream: ' + str(path))
    return result['streams'][0]


def prepare(progress, episode, output, *, width=480, crf=26):
    progress, episode, output = (Path(p).resolve() for p in (progress, episode, output))
    if output.exists():
        raise FileExistsError('Use a new portable output directory: ' + str(output))
    if output in progress.parents or progress == output or output == episode or episode in output.parents:
        raise ValueError('Portable output must be separate from source episodes and sidecars')
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
        raise RuntimeError('Existing local ffmpeg and ffprobe are required; this helper does not install tools')
    source_report = progress / 'progress_report.html'
    html = source_report.read_text(encoding='utf-8')
    marker, suffix = '<script type="application/json" id="data">', '</script>'
    prefix, tail = html.split(marker, 1)
    payload, ending = tail.split(suffix, 1)
    data = json.loads(payload)
    output.mkdir(parents=True)
    (output / 'media').mkdir()
    receipt = dict(schema='labsim.Progress_v1.portable_report.v1',
        source_progress=str(progress), source_episode=str(episode),
        source_report_sha256=sha256(source_report),
        source_summary_sha256=sha256(progress / 'progress_summary.json'),
        source_originals_preserved=True, synthesized_frames=False,
        time_resampling=False, media=[], sidecars=[])
    data['videos'] = []
    for camera in ('side_camera', 'wrist_camera'):
        source = episode / (camera + '.mp4')
        if not source.is_file():
            continue
        target = output / 'media' / (camera + '.h264.mp4')
        source_hash, source_probe = sha256(source), probe(source)
        command = ['ffmpeg', '-v', 'error', '-nostdin', '-n', '-i', str(source),
            '-map', '0:v:0', '-an', '-vf', f'scale={width}:-2', '-c:v', 'libx264',
            '-preset', 'fast', '-crf', str(crf), '-pix_fmt', 'yuv420p',
            '-movflags', '+faststart', str(target)]
        subprocess.run(command, check=True)
        derived_probe = probe(target)
        if source_probe.get('nb_frames') != derived_probe.get('nb_frames'):
            raise RuntimeError('Frame count changed while preparing display copy: ' + camera)
        if source_probe.get('r_frame_rate') != derived_probe.get('r_frame_rate'):
            raise RuntimeError('Frame rate changed while preparing display copy: ' + camera)
        if abs(float(source_probe.get('duration', 0)) - float(derived_probe.get('duration', 0))) > 1e-5:
            raise RuntimeError('Duration changed while preparing display copy: ' + camera)
        if sha256(source) != source_hash:
            raise RuntimeError('Original video changed during packaging: ' + camera)
        receipt['media'].append(dict(camera=camera, source=str(source),
            source_sha256=source_hash, source_bytes=source.stat().st_size, source_stream=source_probe,
            display_copy=str(target.relative_to(output)), display_sha256=sha256(target),
            display_bytes=target.stat().st_size, display_stream=derived_probe,
            command=command, frame_count_and_duration_preserved=True))
        data['videos'].append(dict(name=camera + ' · H264 display copy (original retained)',
                                  src=target.relative_to(output).as_posix()))
    for name in ('progress_summary.json', 'progress_config.resolved.json',
                 'progress_events.jsonl', 'progress_v1.jsonl.gz'):
        source, target = progress / name, output / name
        shutil.copy2(source, target)
        receipt['sidecars'].append(dict(path=name, bytes=target.stat().st_size,
            sha256=sha256(target), unchanged_copy=True))
    timestamp_path = episode / 'video_timestamps.json'
    if timestamp_path.is_file():
        shutil.copy2(timestamp_path, output / timestamp_path.name)
        receipt['frame_timestamp_source'] = dict(path=str(timestamp_path), sha256=sha256(timestamp_path))
    payload = json.dumps(data, ensure_ascii=False, separators=(',', ':')).replace('<', '\\u003c')
    html = prefix + marker + payload + suffix + ending
    html = html.replace('实际仿真录制</h2>', '实际仿真录制 · H264显示副本</h2>')
    (output / 'progress_report.html').write_text(html, encoding='utf-8')
    receipt['report_bytes'] = (output / 'progress_report.html').stat().st_size
    receipt['package_bytes_excluding_receipt'] = sum(p.stat().st_size for p in output.rglob('*') if p.is_file())
    (output / 'portable_media_receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--progress', type=Path, required=True)
    parser.add_argument('--episode', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--width', type=int, default=480)
    parser.add_argument('--crf', type=int, default=26)
    args = parser.parse_args(argv)
    if args.width < 2 or args.width % 2 or not 0 <= args.crf <= 51:
        parser.error('width must be positive and even; crf must be in 0..51')
    try:
        result = prepare(args.progress, args.episode, args.output, width=args.width, crf=args.crf)
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        print('Portable report error: ' + str(exc), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
