"""Faithful portable media for a closed legacy episode and new Progress.

Uses the existing v1.2 portable-report helper. Original recordings, H5, scores
and all Progress source files are read only. The dual display copy preserves
every original frame, native dimensions, frame rate and duration.
"""
from __future__ import annotations

import argparse
from fractions import Fraction
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from demos.lab_cuvette_progress_v1.io import file_sha256


def load(path):
    return json.loads(Path(path).read_text())


def helper(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def prepare(episode, progress, audit_path, quantification_path, output):
    episode, progress, audit_path, quantification_path, output = map(
        lambda p: Path(p).resolve(), (episode, progress, audit_path, quantification_path, output))
    if output.exists():
        raise FileExistsError(output)
    if episode == output or episode in output.parents or progress == output or progress in output.parents:
        raise ValueError('Media output must be independent of original evidence')
    audit, quant = load(audit_path), load(quantification_path)
    if audit.get('passed') is not True or audit.get('source_episode') != str(episode):
        raise ValueError('Passed legacy closure proof for this episode is required')
    if audit['episode_id'] != quant['episode_id']:
        raise ValueError('Historical identity mismatch')
    before = {path: file_sha256(Path(path)) for path in audit['source_files']}
    if any(before[path] != entry['sha256'] for path, entry in audit['source_files'].items()):
        raise ValueError('Historical source changed after the closure audit')
    progress_before = {str(path): file_sha256(path) for path in progress.iterdir() if path.is_file()}
    common = helper(ROOT/'docs/lab_cuvette_loading/Policy_eval_v1/tools/prepare_media.py', 'historical_common_media')
    portable = helper(ROOT/'docs/lab_cuvette_loading/Progress_v1_2/tools/portable_report.py', 'historical_existing_portable')
    timestamps_path = episode/'video_timestamps.json'
    timestamps = load(timestamps_path)
    times = [float(t) for t in timestamps['frame_simulation_times_s']]
    source_dual = episode/'dual_view.mp4'
    source_stream = common.probe(source_dual, count_frames=True)
    if len(times) != int(source_stream['nb_read_frames']):
        raise ValueError('Original timestamp/frame count mismatch')
    output.mkdir(parents=True, exist_ok=False)
    portable_receipt = portable.prepare(progress, episode, output/'progress')
    dual = output/'historical_debug04_dual.mp4'
    command = ['ffmpeg', '-v', 'error', '-nostdin', '-n', '-threads', '2', '-i', str(source_dual),
        '-map', '0:v:0', '-an', '-c:v', 'libx264', '-threads', '2', '-preset', 'fast', '-crf', '22',
        '-pix_fmt', 'yuv420p', '-vsync', '0', '-movflags', '+faststart', str(dual)]
    subprocess.run(command, check=True)
    display_stream = common.probe(dual, count_frames=True)
    for key in ('width', 'height', 'nb_frames', 'nb_read_frames', 'r_frame_rate', 'avg_frame_rate'):
        if source_stream[key] != display_stream[key]:
            raise ValueError('Full dual display identity changed: '+key)
    if abs(float(source_stream['duration'])-float(display_stream['duration'])) > 1e-5:
        raise ValueError('Full dual duration changed')
    (output/'frames').mkdir()
    points = [
        dict(label='first_grasp', requested_simulation_s=quant['phase_evidence'][1]['first_confirmed_t'],
            basis='first physically confirmed bilateral grasp'),
        dict(label='first_preinsert', requested_simulation_s=next(p['first_confirmed_t'] for p in quant['phase_evidence'] if p['stage']=='transport'),
            basis='first Progress fixed pre-insertion-region confirmation, not alignment'),
        dict(label='first_quality_warning', requested_simulation_s=quant['observed_control_times']['first_grasp_quality_false_t'],
            basis='first actual control endpoint with grasp_quality_current=false'),
        dict(label='terminal', requested_simulation_s=quant['simulation_seconds'],
            basis='original actual terminal simulation time after slip and second grasp attempt')]
    fps = Fraction(source_stream['avg_frame_rate'])
    for index, point in enumerate(points, 1):
        frame = common.nearest_frame(times, point['requested_simulation_s'])
        target = output/'frames'/f"historical_debug04_{index:02d}_{point['label']}.png"
        extract = ['ffmpeg', '-v', 'error', '-nostdin', '-n', '-threads', '2', '-i', str(source_dual),
            '-vf', f'select=eq(n\\,{frame})', '-frames:v', '1', '-vsync', '0', str(target)]
        subprocess.run(extract, check=True)
        point.update(path=target.relative_to(output).as_posix(), sha256=file_sha256(target),
            source_video='dual_view.mp4', source_video_sha256=file_sha256(source_dual),
            source_frame_index_zero_based=frame, actual_frame_simulation_s=times[frame],
            selected_time_error_s=times[frame]-point['requested_simulation_s'],
            source_video_time_s=float(Fraction(frame, 1)/fps), command=extract,
            generated_or_interpolated_motion=False)
    decoded = []
    for path in [dual, *(output/'progress'/row['display_copy'] for row in portable_receipt['media'])]:
        subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-threads', '2', '-i', str(path), '-f', 'null', '-'], check=True)
        decoded.append(dict(path=path.relative_to(output).as_posix(), full_decode=True))
    html = common.html_links(output/'progress')
    after = {path: file_sha256(Path(path)) for path in before}
    progress_after = {str(path): file_sha256(path) for path in progress.iterdir() if path.is_file()}
    if before != after or progress_before != progress_after:
        raise ValueError('Original source changed during media preparation')
    receipt = dict(schema='labsim.Gpt_debug04_v1.historical_portable_media.v1',
        historical_only=True, episode_id=audit['episode_id'], source_episode=str(episode), source_progress=str(progress),
        closure_proof=dict(path=str(audit_path), sha256=file_sha256(audit_path)),
        original_sources_unchanged=True, original_progress_unchanged=True, original_h5_copied=False,
        original_full_videos_preserved=True, synthesized_frames=False, temporal_resampling=False,
        source_hashes=before, progress_source_hashes=progress_before,
        full_dual=dict(path=dual.name, source_sha256=file_sha256(source_dual), display_sha256=file_sha256(dual),
            source_stream=source_stream, display_stream=display_stream, command=command,
            all_source_frames_native_dimensions_fps_and_duration_preserved=True),
        portable_progress=dict(receipt='progress/portable_media_receipt.json',
            compression_representation='lossless gzip9 display/transfer copy with decoded SHA proof; original gzip1 and summary retained',
            **html), frame_timestamp_source=dict(path=str(timestamps_path), sha256=file_sha256(timestamps_path)),
        screenshots=points, full_video_decode_checks=decoded,
        source_mutation_policy='none; historical values and all raw recordings remain authoritative')
    (output/'media_receipt.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2)+'\n')
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--episode', required=True)
    parser.add_argument('--progress', required=True)
    parser.add_argument('--audit', required=True)
    parser.add_argument('--quantification', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args(argv)
    r = prepare(args.episode, args.progress, args.audit, args.quantification, args.output)
    print(json.dumps(dict(episode_id=r['episode_id'], frames=r['full_dual']['display_stream']['nb_read_frames'],
        source_unchanged=r['original_sources_unchanged'], full_decode=True)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
