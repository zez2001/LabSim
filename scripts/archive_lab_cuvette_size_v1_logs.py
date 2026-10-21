"""Losslessly archive CLOSED Size_v1 physics/contact JSONL; default is dry-run.

Only the two declared raw logs are eligible. HDF5, labels, videos, source assets
and all historical version directories are untouched. Restore with gzip -dk.
The caller must supply real process-exit evidence; a result file alone is not
evidence that the simulation process has closed its writers.
"""
from __future__ import annotations

import argparse
import datetime
import gzip
import hashlib
import json
import os
from pathlib import Path
import stat
import uuid

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_ROOT = ROOT / "outputs/lab_cuvette_loading/Size_v1"
LOG_NAMES = ("physics_records.jsonl", "native_contact_events.jsonl")


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def snapshot(path):
    value = Path(path).stat()
    if not stat.S_ISREG(value.st_mode):
        raise ValueError("Raw log must be a regular file: " + str(path))
    return dict(device=value.st_dev, inode=value.st_ino, bytes=value.st_size,
                mtime_ns=value.st_mtime_ns, ctime_ns=value.st_ctime_ns)


def assert_unchanged(path, expected):
    if snapshot(path) != expected:
        raise RuntimeError("Raw log changed; preserving original: " + str(path))


def open_write_handles(paths, *, inspection_gaps=None):
    """Inspect accessible same-user Linux writers by inode.

    Nondumpable system helpers such as sd-pam may deny /proc access even to the
    same UID. Those gaps are recorded, never described as inspected handles.
    Independent observed simulation-process exit remains mandatory.
    """
    expected = {(p.stat().st_dev, p.stat().st_ino): str(p) for p in paths}
    writers = []
    for process in Path("/proc").iterdir():
        if not process.name.isdigit():
            continue
        try:
            if process.stat().st_uid != os.getuid():
                continue
            descriptors = list((process / "fd").iterdir())
        except FileNotFoundError:
            continue
        except PermissionError:
            if inspection_gaps is not None:
                inspection_gaps.append(dict(pid=int(process.name), reason="same-user /proc fd access denied"))
            continue
        for descriptor in descriptors:
            try:
                info = descriptor.stat()
                if (info.st_dev, info.st_ino) not in expected:
                    continue
                flags = next(line.split()[1] for line in (process / "fdinfo" / descriptor.name).read_text().splitlines()
                             if line.startswith("flags:"))
                access = int(flags, 8) & os.O_ACCMODE
                if access in (os.O_WRONLY, os.O_RDWR):
                    writers.append(dict(pid=int(process.name), fd=int(descriptor.name),
                        path=expected[(info.st_dev, info.st_ino)]))
            except (FileNotFoundError, ProcessLookupError):
                continue
    return writers


def validate_closed_episode(episode, process_exit_json, *, archive_root=ARCHIVE_ROOT):
    import h5py
    episode, allowed = Path(episode).resolve(), Path(archive_root).resolve()
    if not episode.is_relative_to(allowed) or episode == allowed or not episode.name.startswith("episode_"):
        raise ValueError("Only an episode beneath outputs/lab_cuvette_loading/Size_v1 is allowed")
    proof_path = Path(process_exit_json).resolve()
    proof = json.loads(proof_path.read_text())
    run = Path(proof.get("run_directory", "")).resolve()
    if run != episode.parent or proof.get("process_exited") is not True:
        raise ValueError("Process-exit evidence does not match the closed run directory")
    code = proof.get("exit_code")
    if not isinstance(code, int) or isinstance(code, bool):
        raise ValueError("Real integer process exit_code is required")
    if not (proof.get("pid") or proof.get("session_id")):
        raise ValueError("Process-exit evidence requires the observed PID or exec session_id")
    if proof.get("pid") and Path("/proc", str(proof["pid"])).exists():
        raise ValueError("The recorded simulation PID is still present; refusing archive")
    paths = [episode / name for name in LOG_NAMES]
    for path in paths:
        if path.is_symlink() or not path.is_file():
            raise ValueError("Missing/linked raw log (already archived or incomplete): " + str(path))
    gaps = []
    writers = open_write_handles(paths, inspection_gaps=gaps)
    if writers:
        raise RuntimeError("Simulation/log writers are still open: " + json.dumps(writers))
    result_path, score_path = episode / "result.json", episode / "independent_score.json"
    result = json.loads(result_path.read_text())
    score = json.loads(score_path.read_text())
    if result.get("complete") is not True or not result.get("termination_reason"):
        raise ValueError("A complete result with termination reason is required")
    frames = result.get("frames")
    if not isinstance(frames, int) or isinstance(frames, bool) or frames <= 0:
        raise ValueError("A closed recorded episode requires positive frames evidence")
    with h5py.File(episode / "dataset/episode_0000.h5", "r") as record:
        if not bool(record.attrs.get("complete", False)) or len(record["actions"]) != frames:
            raise ValueError("HDF5 complete/frames disagree with final result")
        identity = str(record.attrs.get("episode_id", ""))
        if not identity or result.get("episode_id") != identity or score.get("episode_id") != identity:
            raise ValueError("Result, independent score and HDF5 episode IDs disagree")
        if int(record.attrs.get("frames", -1)) != frames:
            raise ValueError("HDF5 frame attribute disagrees with final result")
    return dict(episode_id=identity, frames=frames, termination_reason=result["termination_reason"],
        process_exit_evidence=dict(path=str(proof_path), sha256=sha256(proof_path), evidence=proof),
        complete_result_sha256=sha256(result_path), independent_score_sha256=sha256(score_path),
        writer_check="no observed accessible same-user /proc writable handle to either raw log inode; independent process-exit evidence also required",
        process_writer_inspection_gaps=gaps,
        paths=paths)


def prepare_archive(path, expected):
    temporary = path.with_name(path.name + ".gz.pending_" + uuid.uuid4().hex)
    digest, count = hashlib.sha256(), 0
    try:
        with path.open("rb") as source, temporary.open("xb") as destination:
            with gzip.GzipFile(fileobj=destination, mode="wb", compresslevel=1, mtime=0, filename="") as encoded:
                for chunk in iter(lambda: source.read(1 << 20), b""):
                    encoded.write(chunk)
                    digest.update(chunk)
                    count += len(chunk)
            destination.flush()
            os.fsync(destination.fileno())
        assert_unchanged(path, expected)
        decoded_sha, decoded_bytes = hashlib.sha256(), 0
        with gzip.open(temporary, "rb") as decoded:
            for chunk in iter(lambda: decoded.read(1 << 20), b""):
                decoded_sha.update(chunk)
                decoded_bytes += len(chunk)
        if count != expected["bytes"] or decoded_bytes != count or decoded_sha.hexdigest() != digest.hexdigest():
            raise RuntimeError("Streaming decompression differs from original; preserving raw log")
        assert_unchanged(path, expected)
        return dict(original_path=str(path), original_sha256=digest.hexdigest(), original_bytes=count,
            original_snapshot=expected, archive_path=str(path) + ".gz", temporary_path=str(temporary),
            archive_sha256=sha256(temporary), archive_bytes=temporary.stat().st_size,
            compression="gzip", compression_level=1, decompressed_sha256=decoded_sha.hexdigest(),
            decompressed_bytes=decoded_bytes, decompressed_bytes_equal_original=True, raw_removed=False)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def write_manifest(path, value, *, first=False):
    if first:
        with path.open("x", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
    else:
        temporary = path.with_name(path.name + ".pending")
        with temporary.open("x", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)


def archive_episode(episode, process_exit_json, *, replace=False, archive_root=ARCHIVE_ROOT):
    evidence = validate_closed_episode(episode, process_exit_json, archive_root=archive_root)
    paths = evidence.pop("paths")
    state = dict(schema="labsim.Size_v1.lossless_log_archive.v1", episode=str(Path(episode).resolve()),
        dry_run=not replace, closed_episode_evidence=evidence,
        files=[dict(original_path=str(path), original_bytes=path.stat().st_size,
                    archive_path=str(path) + ".gz") for path in paths],
        HDF5_labels_videos_modified=False, restore_command="gzip -dk EPISODE/physics_records.jsonl.gz EPISODE/native_contact_events.jsonl.gz",
        archive_scope="Only current Size_v1 closed-episode physics_records.jsonl and native_contact_events.jsonl",
        portable_export_currently_copies_gzip=True)
    if not replace:
        return state
    for path in paths:
        if Path(str(path) + ".gz").exists():
            raise FileExistsError(str(path) + ".gz")
    expected = {path: snapshot(path) for path in paths}
    prepared = []
    manifest_path = Path(episode) / ("log_archive_" + datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ_") + uuid.uuid4().hex[:8] + ".json")
    try:
        for path in paths:
            prepared.append(prepare_archive(path, expected[path]))
        validate_closed_episode(episode, process_exit_json, archive_root=archive_root)
        for path in paths:
            assert_unchanged(path, expected[path])
        for item in prepared:
            # Hard-link creation cannot overwrite an existing archive.
            os.link(item["temporary_path"], item["archive_path"])
            Path(item["temporary_path"]).unlink()
            item.pop("temporary_path")
        state.update(files=prepared, state="archives_verified_committed_originals_present",
                     archive_manifest=str(manifest_path))
        write_manifest(manifest_path, state, first=True)
        for item, path in zip(prepared, paths):
            assert_unchanged(path, expected[path])
            if open_write_handles([path]):
                raise RuntimeError("Writer appeared; preserving remaining originals")
            path.unlink()
            item["raw_removed"] = True
            write_manifest(manifest_path, state)
        state["state"] = "complete_original_bytes_recoverable_from_verified_gzip"
        write_manifest(manifest_path, state)
        return state
    except BaseException:
        for item in prepared:
            if item.get("temporary_path"):
                Path(item["temporary_path"]).unlink(missing_ok=True)
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("episode", type=Path)
    parser.add_argument("--process-exit-json", type=Path, required=True,
        help="Observed process exit: run_directory, process_exited=true, integer exit_code, and pid or session_id")
    parser.add_argument("--replace-with-lossless-archive", action="store_true")
    args = parser.parse_args(argv)
    result = archive_episode(args.episode, args.process_exit_json,
                             replace=args.replace_with_lossless_archive)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
