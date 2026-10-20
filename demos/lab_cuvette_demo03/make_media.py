"""Make traceable, CPU-only review media from one saved V0_demo03 episode.

Example::
    python -m demos.lab_cuvette_demo03.make_media --episode RUN/trial_00 \
        --output NEW_MEDIA_DIRECTORY --representative-success

Phase boundaries come from the episode's saved events, never a different run.
Missing phases produce unavailable entries rather than fabricated clips.
"""
from __future__ import annotations

import argparse
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import shutil
import subprocess
import textwrap


PHASES = ["RESET", "APPROACH_SOURCE", "GRASP", "EXTRACT", "TRANSPORT", "ALIGN",
          "INSERT", "SUPPORT_TRANSFER", "OPEN", "RETREAT", "VERIFY"]
FONT = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def probe(path: Path) -> dict:
    data = json.loads(subprocess.check_output([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=codec_name,width,height,avg_frame_rate,r_frame_rate,nb_frames,duration",
        "-show_entries", "format=duration", "-of", "json", str(path)
    ], text=True))
    stream = data["streams"][0]
    fps = float(Fraction(stream["avg_frame_rate"]))
    return dict(codec=stream["codec_name"], width=int(stream["width"]),
                height=int(stream["height"]), fps=fps,
                frames=int(stream["nb_frames"]),
                duration_s=float(stream.get("duration", data["format"]["duration"])))


def phase_times(events: list, stop: float) -> dict:
    starts = {"RESET": 0.0}
    previous_time = 0.0
    for event in events:
        if event.get("event") != "phase":
            continue
        phase = event.get("next")
        time = float(event["t"])
        if phase not in PHASES or not math.isfinite(time) or time < previous_time or time > stop + 1e-6:
            raise ValueError("Invalid or unordered saved phase event")
        if phase in starts:
            raise ValueError("Repeated phase entry needs an explicitly separate media analysis")
        starts[phase] = time
        previous_time = time
    return starts


def validate_success(episode: Path, result: dict, score: dict, starts: dict) -> list:
    errors = []
    if result.get("workflow_success") is not True:
        errors.append("controller did not report workflow_success")
    if score.get("workflow_success") is not True:
        errors.append("independent score did not pass workflow_success")
    if score.get("historical_semantics_only") is True:
        errors.append("historical analysis is not a new successful episode")
    if Path(score.get("source_episode", "")).resolve() != episode:
        errors.append("independent score refers to a different episode")
    if any(p not in starts for p in PHASES):
        errors.append("complete ordered workflow was not recorded")
    else:
        if list(starts) != PHASES:
            errors.append("recorded phase order differs from workflow")
    post = score.get("post_retreat_window", {})
    if not (post.get("available") is True and post.get("stable") is True
            and post.get("duration_s") is not None and float(post["duration_s"]) >= 3.0 - 1e-6):
        errors.append("independent post-retreat stable window of at least 3 s is missing")
    checks = score.get("checks", {})
    if not checks or not all(value is True for value in checks.values()):
        errors.append("one or more independent checks are missing or failed")
    for key, name in [("events_sha256", "events.json"),
                      ("physics_records_sha256", "physics_records.json")]:
        if score.get(key) != sha256(episode / name):
            errors.append("independent score does not bind current " + name)
    return errors


def filter_path(path: Path) -> str:
    # Subprocess arguments never go through a shell; this escapes FFmpeg's filter grammar.
    text = str(path)
    if "\n" in text or "\r" in text:
        raise ValueError("Newlines in media paths are unsupported")
    for char in ["\\", ":", "'", ",", "[", "]"]:
        text = text.replace(char, "\\" + char)
    return text


def run_command(command: list[str]) -> None:
    subprocess.run(command, check=True, stdout=subprocess.DEVNULL)


def make_media(episode: Path, output: Path, representative_success: bool = False) -> dict:
    episode = episode.resolve()
    output = output.resolve()
    result = load(episode / "result.json")
    score = load(episode / "independent_score.json")
    events = load(episode / "events.json")
    stop = float(result["simulation_seconds"])
    if not math.isfinite(stop) or stop <= 0 or result.get("version") != "V0_demo03":
        raise ValueError("Expected a completed, recorded V0_demo03 episode")
    starts = phase_times(events, stop)
    success_errors = validate_success(episode, result, score, starts)
    if representative_success and success_errors:
        raise ValueError("Refusing to label representative success: " + "; ".join(success_errors))
    verified_success = not success_errors
    if verified_success:
        label = "WORKFLOW_SUCCESS"
    elif score.get("workflow_success") is False:
        label = "FAILURE"
    else:
        label = "UNVERIFIED"
    status = str(result.get("status", "UNKNOWN"))
    sources = {name: episode / filename for name, filename in
               [("wide", "main.mp4"), ("closeup", "closeup.mp4")]}
    source_probes = {name: probe(path) for name, path in sources.items()}
    for name, metadata in source_probes.items():
        expected = math.floor(stop * metadata["fps"] + 1e-6) + 1
        if metadata["frames"] != expected:
            raise ValueError(f"{name} video count does not support t=frame/fps mapping: "
                             f'{metadata["frames"]} != {expected}')
    if output.exists():
        raise FileExistsError("Media output must be a new directory: " + str(output))
    if not FONT.exists():
        raise FileNotFoundError(FONT)
    output.mkdir(parents=True, exist_ok=False)
    captions = output / ".captions"
    captions.mkdir()
    commands = []
    artifacts = []
    phase_segments = []

    def caption(kind: str) -> Path:
        metadata = source_probes[kind]
        width = 110 if metadata["width"] >= 1000 else 65
        text = f"RECORDED {label}: {status}\n"
        text += f"ONE EPISODE | adapted scene | native_pair={result.get('native_pair_success') is True}"
        text = "\n".join(textwrap.fill(line, width=width) for line in text.splitlines())
        path = captions / (kind + ".txt")
        path.write_text(text + "\n", encoding="utf-8")
        return path

    caption_paths = {kind: caption(kind) for kind in sources}

    def transcode(name: str, kind: str, start: float, end: float, *, speed: float = 1.0,
                  reason: str, exact_full: bool = False):
        metadata = source_probes[kind]
        fps = metadata["fps"]
        first = max(0, min(metadata["frames"] - 1, math.ceil(start * fps - 1e-8)))
        exclusive = metadata["frames"] if exact_full else min(
            metadata["frames"], math.ceil(end * fps - 1e-8))
        if exclusive <= first:
            return None
        font_size = 21 if metadata["width"] >= 1000 else 12
        filters = [f"trim=start_frame={first}:end_frame={exclusive}",
                   f"setpts=(PTS-STARTPTS)/{speed}",
                   f"fps={fps}",
                   "drawtext=fontfile=" + filter_path(FONT) + ":textfile=" +
                   filter_path(caption_paths[kind]) +
                   f":fontcolor=white:fontsize={font_size}:box=1:boxcolor=black@0.72:"
                   "boxborderw=5:x=12:y=h-th-12"]
        destination = output / (name + ".mp4")
        command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-n",
                   "-hwaccel", "none", "-i", str(sources[kind]), "-vf", ",".join(filters),
                   "-an", "-c:v", "libx264", "-preset", "medium", "-crf", "23",
                   "-pix_fmt", "yuv420p", "-threads", "2", "-movflags", "+faststart",
                   str(destination)]
        run_command(command)
        commands.append(command)
        rendered = probe(destination)
        if rendered["codec"] != "h264" or rendered["width"] != metadata["width"]:
            raise ValueError("Unexpected encoded media format")
        record = dict(file=destination.name, source=str(sources[kind]),
                      source_frame_range_inclusive=[first, exclusive - 1],
                      first_recorded_time_s=first / fps,
                      last_recorded_time_s=(exclusive - 1) / fps,
                      requested_event_window_s=[start, end], playback_speed=speed,
                      rationale=reason, output_probe=rendered,
                      bytes=destination.stat().st_size, sha256=sha256(destination),
                      posthoc_caption=True, continuous_same_run=True,
                      note="H264 software re-encode only; slow playback repeats frames, no state interpolation")
        artifacts.append(record)
        return record

    transcode("main_h264", "wide", 0.0, stop, exact_full=True,
              reason="All raw main-camera frames from this single run, without cuts or stitching")
    transcode("closeup_h264", "closeup", 0.0, stop, exact_full=True,
              reason="All raw fixed close-camera frames; camera may not show source operations")

    definitions = [
        ("initial", "RESET", "APPROACH_SOURCE", ["wide"]),
        ("source_extraction", "RESET", "TRANSPORT", ["wide"]),
        ("grasp_and_extraction", "GRASP", "TRANSPORT", ["wide"]),
        ("insertion_handoff", "ALIGN", "OPEN", ["wide", "closeup"]),
        ("open_retreat_stability", "OPEN", None, ["wide", "closeup"]),
    ]
    for name, begin, after, kinds in definitions:
        if begin not in starts:
            phase_segments.append(dict(segment=name, available=False,
                                       reason=begin + " was not entered", files=[]))
            continue
        start = starts[begin]
        end = starts.get(after, stop) if after else stop
        complete_boundary = after is None or after in starts
        files = []
        for kind in kinds:
            record = transcode(name + ("_closeup" if kind == "closeup" else ""),
                               kind, start, end,
                               reason=f"Saved event boundary {begin} to {after or 'recorded end'}; "
                               "clip existence does not assert phase success")
            if record:
                files.append(record["file"])
        phase_segments.append(dict(segment=name, available=bool(files), start_s=start, end_s=end,
                                   end_boundary_recorded=complete_boundary, files=files,
                                   workflow_verified_success=verified_success))

    if not verified_success:
        start = max(0.0, stop - 4.0)
        transcode("failure_terminal", "wide", start, stop, exact_full=True,
                  reason="Last four simulated seconds before recorded termination")
        transcode("failure_terminal_slow4x", "wide", start, stop, speed=.25, exact_full=True,
                  reason="Same terminal frames, playback slowed four times; not additional simulation")
        transcode("failure_terminal_closeup", "closeup", start, stop, exact_full=True,
                  reason="Fixed close-camera terminal window; may not contain the arm collision")

    def screenshot(name: str, video_file: str, frame: int, reason: str):
        source = output / video_file
        destination = output / (name + ".png")
        command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-n",
                   "-hwaccel", "none", "-i", str(source), "-vf", f"select=eq(n\\,{frame})",
                   "-frames:v", "1", "-threads", "2", str(destination)]
        run_command(command)
        commands.append(command)
        artifacts.append(dict(file=destination.name, source=video_file, source_frame=frame,
                              rationale=reason, bytes=destination.stat().st_size,
                              sha256=sha256(destination), posthoc_caption=True))

    screenshot("initial", "main_h264.mp4", 0, "First recorded video state")
    screenshot("terminal", "main_h264.mp4", source_probes["wide"]["frames"] - 1,
               "Last recorded video state, which can precede physics termination by one video period")
    if "TRANSPORT" in starts:
        frame = max(0, math.ceil(starts["TRANSPORT"] * source_probes["wide"]["fps"] - 1e-8) - 1)
        screenshot("source_extracted", "main_h264.mp4", frame,
                   "Last video frame before saved TRANSPORT transition; not an independent extraction verdict")
    contact = episode / "whole_arm_contact.png"
    if contact.exists():
        destination = output / "recorded_stop_contact.png"
        shutil.copyfile(contact, destination)
        artifacts.append(dict(file=destination.name, source=str(contact), source_sha256=sha256(contact),
                              bytes=destination.stat().st_size, sha256=sha256(destination),
                              posthoc_caption=False,
                              rationale="Unmodified simulator screenshot saved in the stopped episode; no added success label"))

    source_files = ["main.mp4", "closeup.mp4", "events.json", "result.json", "independent_score.json",
                    "execution_summary.json", "adjudication.json", "config.yaml", "initial.json",
                    "runtime.json", "scene_contract.json"]
    provenance = dict(schema="labsim.V0_demo03.review_media.v1", episode=str(episode),
                      episode_status=status, review_label=label, representative_success=representative_success,
                      independently_verified_workflow_success=verified_success,
                      success_validation_rejections=success_errors,
                      native_pair_success=result.get("native_pair_success") is True,
                      data_eligible=score.get("data_eligible") is True,
                      scene_mode=result.get("scene_mode"), source_slot_id=result.get("source_slot_id"),
                      target_seat_id=result.get("target_seat_id"), simulation_end_s=stop,
                      actual_phase_starts_s=starts, phase_segments=phase_segments,
                      source_files=[dict(file=name, path=str(episode / name),
                                         bytes=(episode / name).stat().st_size,
                                         sha256=sha256(episode / name))
                                    for name in source_files if (episode / name).exists()],
                      source_video_probes=source_probes, artifacts=artifacts,
                      timing_method="Raw run camera writer starts at t=0 and samples at nominal 30Hz; "
                                    "verified frame_count=floor(simulation_end*fps)+1. Segment bounds are "
                                    "mapped to actual integer frames with ceil(t*fps); final video frame "
                                    "can precede the last physics state. This is not camera exposure calibration.",
                      transformations="CPU libx264, CRF23, original frame size, no audio; "
                                      "posthoc result caption; no cross-run stitching or motion interpolation",
                      ffmpeg_commands=commands, source_records_modified=False,
                      physics_or_gpu_process_started=False)
    (output / "provenance.json").write_text(json.dumps(provenance, ensure_ascii=False, indent=2) + "\n")
    (output / "README.md").write_text(
        f"# V0_demo03 单次运行阅读媒体\n\n结果：**{label}**；原始状态 `{status}`。"
        f"仿真结束于 {stop:.6f} s。完整主录像为 `main_h264.mp4`，"
        "它来自同一次运行全部原视频帧，没有拼接其他尝试。\n\n"
        "各阶段片段按保存的events边界提取；未执行阶段在provenance中为unavailable，"
        "不会生成虚构片段。末段慢放仅重复播放原帧，没有增加仿真状态。"
        "固定近景相机可能不拍到来源抓取或手臂碰撞，应结合全景。\n\n"
        f"原episode：`{episode}`。逐文件SHA256、实际帧区间、结果标签及命令见 `provenance.json`。"
        "原CAD配套和真实标定结论未被媒体制作改变。\n", encoding="utf-8")
    return provenance


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episode", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="new directory; refuses overwrite")
    parser.add_argument("--representative-success", action="store_true",
                        help="requires independently passed same-run full workflow and 3s post-retreat evidence")
    args = parser.parse_args()
    result = make_media(args.episode, args.output, args.representative_success)
    print(json.dumps(dict(output=str(args.output.resolve()), label=result["review_label"],
                          artifacts=len(result["artifacts"])), ensure_ascii=False))


if __name__ == "__main__":
    main()
