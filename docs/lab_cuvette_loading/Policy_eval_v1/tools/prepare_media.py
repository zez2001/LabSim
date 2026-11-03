"""Create portable Progress reports and faithful display media for closed trials.

Source episodes, H5s, videos, labels and sidecars are read-only. The original
dual-view sequence is encoded to H264 with no scaling, temporal resampling,
frame synthesis or scene edits. Stills select real source frames using the
recorded simulation-time-to-video-frame map. Large H5s are hashed, not copied.
"""
from __future__ import annotations

import argparse
import bisect
from datetime import datetime, timezone
from fractions import Fraction
import gzip
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time


SCHEMA = "labsim.Policy_eval_v1.portable_media.v1"
ROOT = Path(__file__).resolve().parents[4]
SIDECARS = ("progress_v1.jsonl.gz", "progress_events.jsonl", "progress_summary.json", "progress_config.resolved.json")


def sha(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(8 << 20), b""):
            value.update(block)
    return value.hexdigest()


def file_record(path):
    path = Path(path)
    return dict(path=str(path), bytes=path.stat().st_size, sha256=sha(path))


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def probe(path, *, count_frames=False):
    command = ["ffprobe", "-v", "error", "-select_streams", "v:0"]
    if count_frames:
        command.append("-count_frames")
    command += ["-show_entries", "stream=codec_name,width,height,nb_frames,nb_read_frames,r_frame_rate,avg_frame_rate,duration",
                "-of", "json", str(path)]
    streams = json.loads(subprocess.check_output(command, text=True)).get("streams", [])
    if len(streams) != 1:
        raise ValueError("Expected one selected video stream: " + str(path))
    return streams[0]


def source_closure(episode):
    run = episode.parent
    proof_path = run / "process_exit.json"
    if not proof_path.is_file():
        raise RuntimeError("Episode parent has no process_exit.json; do not read active trial")
    proof = load(proof_path)
    if proof.get("process_exited") is not True:
        raise RuntimeError("Source environment has not exited")
    pids = [row["pid"] for row in proof.get("children", []) if row.get("pid") is not None]
    if proof.get("pid") is not None:
        pids.append(proof["pid"])
    if not pids:
        raise RuntimeError("Closed-process proof has no actual child/native PID")
    still_present = [pid for pid in pids if Path("/proc", str(int(pid))).exists()]
    if still_present:
        raise RuntimeError("Recorded source PID still exists locally: " + str(still_present))
    result = load(episode / "result.json")
    marker_path = episode / "episode_0000_complete.json"
    marker = load(marker_path)
    collector = load(episode / "episode_0000_result.json")
    streams = load(episode / "recording_closed_receipt.json")
    progress = load(episode / "progress_summary.json")
    identities = [result.get("episode_id"), marker.get("episode_id"), collector.get("episode_id"), progress.get("episode_id")]
    # Historical collector envelopes keep their episode identity in labels.
    if collector.get("episode_id") is None:
        identities[2] = collector.get("labels", {}).get("episode_id") or collector.get("result", {}).get("episode_id")
    if not identities[0] or len(set(identities)) != 1:
        raise RuntimeError("Closed result/collector/Progress episode identity mismatch")
    if result.get("complete") is not True or result.get("publication_state") != "complete":
        raise RuntimeError("Original episode result is not completely published")
    finalization = result.get("finalization_id")
    collector_finalization = collector.get("finalization_id") or collector.get("labels", {}).get("finalization_id")
    if finalization is None or finalization != marker.get("finalization_id") or finalization != collector_finalization:
        raise RuntimeError("Closed collector/result finalization identity mismatch")
    if not streams.get("streams") or not all(row.get("closed") is True and row.get("close_succeeded") is True
            for row in streams["streams"].values()):
        raise RuntimeError("Physical/contact recorder streams are not closed")
    integrity = progress.get("output_integrity", {})
    if integrity.get("complete") is not True or integrity.get("errors"):
        raise RuntimeError("Progress sidecar integrity is not complete")
    for name, row in integrity.get("files", {}).items():
        source = episode / name
        if not source.is_file() or sha(source) != row["sha256"]:
            raise RuntimeError("Progress source differs from closed integrity receipt: " + name)
    return dict(episode_id=identities[0], finalization_id=finalization,
                source_process_proof=file_record(proof_path), process_exit_code=proof.get("exit_code"),
                recorded_native_PIDs_absent=pids, record_integrity_valid=result.get("record_integrity_valid"),
                task_success=result.get("task_success"), termination_reason=result.get("termination_reason"),
                marker=file_record(marker_path), all_recorder_streams_closed=True,
                progress_integrity_complete=True)


def nearest_frame(times, desired):
    index = bisect.bisect_left(times, desired)
    candidates = [i for i in (index - 1, index) if 0 <= i < len(times)]
    if not candidates:
        raise ValueError("No real video frame timestamps")
    return min(candidates, key=lambda i: (abs(times[i] - desired), i))


def selected_stills(events, result, times):
    """Choose first hold, observed progress, and terminal; never a fake stage."""
    by_name = {}
    for event in events:
        by_name.setdefault(event.get("name"), event)
    terminal_time = float(result.get("simulation_duration_s", result.get("simulation_seconds", times[-1])))
    first = by_name.get("grasp_confirmed")
    selected = [dict(label="grasp" if first else "initial", requested_simulation_time_s=float(first["t"]) if first else times[0],
                     selection_basis="first confirmed bilateral hold" if first else "first actual recorded frame",
                     source_event_id=first.get("event_id") if first else None)]
    advanced = None
    for name in ("release_retreat_confirmed", "support_transfer_confirmed", "insert_confirmed", "align_confirmed",
                 "transport_confirmed", "held_transport_observed", "extract_confirmed"):
        candidate = by_name.get(name)
        if candidate and float(candidate["t"]) < terminal_time - .1:
            advanced = candidate
            break
    if advanced:
        selected.append(dict(label=re.sub(r"[^a-z0-9_]", "_", advanced["name"]),
            requested_simulation_time_s=float(advanced["t"]), selection_basis="highest available physically observed milestone before termination",
            source_event_id=advanced.get("event_id")))
    else:
        selected.append(dict(label="preterminal", requested_simulation_time_s=max(times[0], terminal_time - 1.0),
                             selection_basis="one simulation second before actual terminal state; not a confirmed task stage",
                             source_event_id=None))
    selected.append(dict(label="terminal", requested_simulation_time_s=terminal_time,
                         selection_basis="actual episode terminal simulation time", source_event_id=None))
    unique = []
    seen = set()
    for item in selected:
        index = nearest_frame(times, item["requested_simulation_time_s"])
        if index in seen:
            continue
        item.update(frame_index_zero_based=index, actual_frame_simulation_time_s=times[index],
                    simulation_time_selection_error_s=times[index] - item["requested_simulation_time_s"])
        seen.add(index)
        unique.append(item)
    return unique


def import_helper(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def html_links(progress):
    html = (progress / "progress_report.html").read_text()
    marker = '<script type="application/json" id="data">'
    data = json.loads(html.split(marker, 1)[1].split("</script>", 1)[0])
    paths = [row["src"] for row in data["videos"]]
    paths += re.findall(r'href="([^"]+)"', html)
    for relative in paths:
        path = Path(relative)
        if path.is_absolute() or ":" in relative or ".." in path.parts or not (progress / path).is_file():
            raise RuntimeError("Portable HTML contains missing/nonlocal playback or data link: " + relative)
    return dict(all_media_and_data_links_relative_and_present=True, paths=paths,
                cursor_original_control_endpoints=data["display_sampling"]["cursor_rows"],
                complete_events_including_finalize=len(data["events"]))


def prepare(episode, output, case_id):
    episode, output = Path(episode).resolve(), Path(output).resolve()
    if output.exists():
        raise FileExistsError("Refuse to overwrite media output: " + str(output))
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", case_id):
        raise ValueError("case-id must be a simple lower-case file-safe identifier")
    if output == episode or episode in output.parents or output in episode.parents:
        raise ValueError("Media output must be separate from the source episode")
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise RuntimeError("Existing ffmpeg and ffprobe are required")
    start = time.perf_counter()
    closure = source_closure(episode)
    result = load(episode / "result.json")
    timestamps_path = episode / "video_timestamps.json"
    timestamp_data = load(timestamps_path)
    times = [float(value) for value in timestamp_data["frame_simulation_times_s"]]
    if not times or not all(math.isfinite(value) for value in times) or any(b < a for a, b in zip(times, times[1:])):
        raise RuntimeError("Native video timestamps are missing, nonfinite or not monotonic")
    native_dual = episode / "dual_view.mp4"
    source_stream = probe(native_dual, count_frames=True)
    if int(source_stream["nb_read_frames"]) != len(times):
        raise RuntimeError("Video timestamp count does not match fully decoded native dual frames")
    events = [json.loads(line) for line in (episode / "progress_events.jsonl").read_text().splitlines() if line.strip()]
    inputs = [episode / name for name in SIDECARS]
    inputs += [episode / name for name in ("side_camera.mp4", "wrist_camera.mp4", "dual_view.mp4", "video_timestamps.json",
               "result.json", "independent_score.json", "episode_0000_complete.json", "episode_0000_result.json",
               "recording_closed_receipt.json", "config.yaml", "progress_input_metadata.json")]
    inputs += [episode / "dataset/episode_0000.h5", episode.parent / "process_exit.json"]
    source_before = [file_record(path) for path in inputs]
    output.mkdir(parents=True, exist_ok=False)
    (output / "frames").mkdir()
    sys.path.insert(0, str(ROOT))
    from demos.lab_cuvette_progress_v1.report import generate_report
    helper_path = ROOT / "docs/lab_cuvette_loading/Progress_v1_2/tools/portable_report.py"
    helper = import_helper(helper_path, "labsim_policy_eval_existing_portable_report")
    # Online records intentionally have no HTML. Generate it in an isolated
    # temporary copy, then reuse the existing portable report implementation.
    # No file is added to or rewritten inside the original episode.
    with tempfile.TemporaryDirectory(prefix="labsim-policy-eval-report-input-") as temporary:
        staging = Path(temporary)
        for name in SIDECARS:
            shutil.copy2(episode / name, staging / name)
        staged_report = generate_report(staging, episode)
        generated_source_report_sha = sha(staged_report)
        portable_receipt = helper.prepare(staging, episode, output / "progress")
    dual_target = output / f"{case_id}_dual.mp4"
    command = ["ffmpeg", "-v", "error", "-nostdin", "-n", "-i", str(native_dual),
        "-map", "0:v:0", "-an", "-c:v", "libx264", "-threads", "2", "-preset", "fast", "-crf", "22",
        # -vsync0 is the passthrough option in the existing local ffmpeg;
        # newer -fps_mode is unavailable on this preserved installation.
        "-pix_fmt", "yuv420p", "-vsync", "0", "-movflags", "+faststart", str(dual_target)]
    subprocess.run(command, check=True)
    target_stream = probe(dual_target, count_frames=True)
    equal_keys = ("width", "height", "nb_frames", "nb_read_frames", "r_frame_rate", "avg_frame_rate")
    if any(source_stream.get(key) != target_stream.get(key) for key in equal_keys):
        raise RuntimeError("Native dual video dimensions/frame count/fps changed")
    if abs(float(source_stream["duration"]) - float(target_stream["duration"])) > 1e-5:
        raise RuntimeError("Native dual video duration changed")
    # Full decode each display video, rather than trusting the MP4 frame header.
    displays = [dual_target, *(output / "progress" / row["display_copy"] for row in portable_receipt["media"])]
    decode_checks = []
    for path in displays:
        subprocess.run(["ffmpeg", "-v", "error", "-nostdin", "-threads", "2", "-i", str(path), "-f", "null", "-"], check=True)
        decode_checks.append(dict(path=path.relative_to(output).as_posix(), fully_decoded=True))
    fps = Fraction(source_stream["avg_frame_rate"])
    stills = selected_stills(events, result, times)
    for sequence, item in enumerate(stills, 1):
        target = output / "frames" / f"{case_id}_{sequence:02d}_{item['label']}.png"
        index = item["frame_index_zero_based"]
        frame_command = ["ffmpeg", "-v", "error", "-nostdin", "-n", "-threads", "2", "-i", str(native_dual),
            "-vf", f"select=eq(n\\,{index})", "-frames:v", "1", "-vsync", "0", str(target)]
        subprocess.run(frame_command, check=True)
        item.update(path=target.relative_to(output).as_posix(), sha256=sha(target), bytes=target.stat().st_size,
                    source_video_sha256=source_before[inputs.index(native_dual)]["sha256"],
                    source_video="dual_view.mp4", source_video_frame_time_s=float(Fraction(index, 1) / fps),
                    extraction_command=frame_command, generated_or_interpolated_motion=False)
    source_after = [file_record(path) for path in inputs]
    if source_before != source_after:
        raise RuntimeError("Original closed episode files changed during media preparation")
    # JSONL CRC and complete event stream are checked without loading H5.
    with gzip.open(output / "progress/progress_v1.jsonl.gz", "rt") as source:
        control_count = sum(1 for line in source if line.strip())
    html_check = html_links(output / "progress")
    if control_count != html_check["cursor_original_control_endpoints"] or len(events) != html_check["complete_events_including_finalize"]:
        raise RuntimeError("Portable report control/event count mismatch")
    outputs = [dict(path=path.relative_to(output).as_posix(), bytes=path.stat().st_size, sha256=sha(path))
               for path in sorted(output.rglob("*")) if path.is_file()]
    receipt = dict(schema=SCHEMA, utc=datetime.now(timezone.utc).isoformat(), case_id=case_id,
        episode_id=closure["episode_id"], source_episode=str(episode), closure=closure,
        source_files=source_before, source_hashes_unchanged=True, h5_copied=False,
        original_video_and_sidecars_preserved=True, synthesized_frames=False, temporal_resampling=False,
        portable_report=dict(path="progress/progress_report.html", helper=str(helper_path.relative_to(ROOT)),
            helper_sha256=sha(helper_path), staging="Temporary copies of original4 sidecars; temporary HTML generated from the same bytes; original episode untouched",
            generated_source_report_sha256=generated_source_report_sha,
            receipt_path="progress/portable_media_receipt.json", **html_check),
        full_dual_video=dict(path=dual_target.relative_to(output).as_posix(), source_sha256=sha(native_dual),
            display_sha256=sha(dual_target), source_stream=source_stream, display_stream=target_stream,
            full_frame_count_fps_duration_and_native_dimensions_preserved=True, command=command),
        frame_clock=dict(source="video_timestamps.json", source_sha256=sha(timestamps_path),
            count=len(times), nominal_fps=timestamp_data["nominal_fps"], first_frame_simulation_s=times[0],
            last_frame_simulation_s=times[-1], method="Nearest real recorded simulation timestamp; tie selects earlier source frame"),
        screenshots=stills, complete_video_decode_checks=decode_checks,
        raw_progress_control_steps=control_count, raw_progress_events=len(events),
        output_files_excluding_self=outputs, wall_seconds=time.perf_counter() - start)
    with (output / "media_receipt.json").open("x", encoding="utf-8") as destination:
        json.dump(receipt, destination, ensure_ascii=False, indent=2, allow_nan=False)
        destination.write("\n")
    return receipt


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episode", type=Path, required=True, help="Actual closed episode directory")
    parser.add_argument("--output", type=Path, required=True, help="New portable media directory")
    parser.add_argument("--case-id", required=True)
    args = parser.parse_args(argv)
    value = prepare(args.episode, args.output, args.case_id)
    print(json.dumps({key: value[key] for key in ("schema", "case_id", "episode_id", "source_hashes_unchanged",
                      "raw_progress_control_steps", "raw_progress_events", "wall_seconds")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
