#!/usr/bin/env python3
"""Verify a historical archive; restore only into a new directory outside Git."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import zipfile


def digest(stream) -> str:
    checksum = hashlib.sha256()
    for block in iter(lambda: stream.read(1024 * 1024), b""):
        checksum.update(block)
    return checksum.hexdigest()


def unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate manifest key: {key}")
        result[key] = value
    return result


def safe_name(name: str) -> str:
    if not isinstance(name, str) or not name or "\\" in name or ":" in name or "\x00" in name:
        raise ValueError(f"Invalid archive path: {name!r}")
    path = PurePosixPath(name)
    if path.is_absolute() or any(part in (".", "..", "") for part in name.split("/")):
        raise ValueError(f"Archive path must be relative and canonical: {name!r}")
    if ".git" in (part.lower() for part in path.parts):
        raise ValueError(f"Archive must not contain Git metadata: {name!r}")
    return name


def load_manifest(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_keys)
    if data.get("schema") != "labsim.historical_archive.v1":
        raise ValueError("Unsupported archive manifest schema")
    if not re.fullmatch(r"[0-9a-f]{40}", data.get("baseline_commit", "")):
        raise ValueError("A full baseline Git SHA is required")
    archive = data["archive"]
    if not re.fullmatch(r"[0-9a-f]{64}", archive.get("sha256", "")):
        raise ValueError("Invalid archive SHA256")
    if type(archive.get("size_bytes")) is not int or archive["size_bytes"] < 0:
        raise ValueError("Invalid archive size")
    files = data["files"]
    if not isinstance(files, list) or not files:
        raise ValueError("Manifest must list files")
    names = set()
    for entry in files:
        name = safe_name(entry["path"])
        if name in names:
            raise ValueError(f"Duplicate manifest path: {name}")
        if any(name.startswith(old + "/") or old.startswith(name + "/") for old in names):
            raise ValueError(f"Conflicting file paths: {name}")
        names.add(name)
        if type(entry.get("size_bytes")) is not int or entry["size_bytes"] < 0:
            raise ValueError(f"Invalid file size: {name}")
        if not re.fullmatch(r"[0-9a-f]{64}", entry.get("sha256", "")):
            raise ValueError(f"Invalid file SHA256: {name}")
    return data


def verify(archive_path: Path, manifest: dict) -> dict:
    """Validate the complete member set and content before creating any output."""
    if archive_path.is_symlink() or not archive_path.is_file():
        raise ValueError("Archive must be a regular local file")
    with archive_path.open("rb") as stream:
        actual_sha = digest(stream)
    expected = manifest["archive"]
    if archive_path.stat().st_size != expected["size_bytes"] or actual_sha != expected["sha256"]:
        raise ValueError("Archive size or SHA256 differs from the manifest")
    records = {entry["path"]: entry for entry in manifest["files"]}
    with zipfile.ZipFile(archive_path) as archive:
        members = archive.infolist()
        names = [safe_name(info.filename) for info in members]
        if len(names) != len(set(names)):
            raise ValueError("Duplicate ZIP member")
        if set(names) != set(records):
            raise ValueError("ZIP member set differs from manifest (missing or extra files)")
        for info in members:
            mode = info.external_attr >> 16
            if info.is_dir() or stat.S_IFMT(mode) not in (0, stat.S_IFREG):
                raise ValueError(f"Non-regular ZIP member: {info.filename}")
            if info.flag_bits & 1:
                raise ValueError(f"Encrypted ZIP member: {info.filename}")
            entry = records[info.filename]
            if info.file_size != entry["size_bytes"]:
                raise ValueError(f"ZIP member size mismatch: {info.filename}")
            with archive.open(info) as stream:
                if digest(stream) != entry["sha256"]:
                    raise ValueError(f"ZIP member SHA256 mismatch: {info.filename}")
    return {"verified": True, "file_count": len(records),
            "payload_bytes": sum(entry["size_bytes"] for entry in records.values()),
            "archive_sha256": actual_sha, "baseline_commit": manifest["baseline_commit"]}


def destination_path(destination: Path) -> Path:
    destination = destination.expanduser().absolute()
    if ".." in destination.parts:
        raise ValueError("Restore destination cannot contain '..'")
    if any(path.is_symlink() for path in (destination, *destination.parents)):
        raise ValueError("Restore destination cannot traverse a symlink")
    if destination.exists():
        raise FileExistsError(f"Restore destination must not exist: {destination}")
    if not destination.parent.is_dir():
        raise ValueError("Restore parent directory must already exist")
    if any((parent / ".git").exists() or (parent / ".git").is_symlink()
           or ((parent / "HEAD").is_file() and (parent / "objects").is_dir()
               and (parent / "refs").is_dir()) for parent in destination.parents):
        raise ValueError("Restore destination must be outside existing Git worktrees")
    return destination


def restore(archive_path: Path, manifest: dict, destination: Path) -> dict:
    destination = destination_path(destination)
    result = verify(archive_path, manifest)
    # Exclusive creation prevents replacing an existing tree. No extractall(), links,
    # permissions, timestamps, or Git files from the ZIP are applied to the host.
    destination.mkdir(exist_ok=False)
    try:
        with zipfile.ZipFile(archive_path) as archive:
            for entry in manifest["files"]:
                target = destination / entry["path"]
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(entry["path"]) as source, target.open("xb") as output:
                    shutil.copyfileobj(source, output, length=1024 * 1024)
                with target.open("rb") as stream:
                    if target.stat().st_size != entry["size_bytes"] or digest(stream) != entry["sha256"]:
                        raise ValueError(f"Restored file differs: {entry['path']}")
    except Exception:
        # Leave a failed partial restore for inspection; never remove existing data.
        raise
    result["restored_to"] = str(destination)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--restore-to", type=Path,
                        help="New directory outside any existing Git worktree; omitted means verify only")
    args = parser.parse_args()
    try:
        manifest = load_manifest(args.manifest)
        result = (restore(args.archive, manifest, args.restore_to) if args.restore_to
                  else verify(args.archive, manifest))
    except (ValueError, KeyError, TypeError, OSError, zipfile.BadZipFile) as error:
        parser.exit(2, f"Archive rejected: {error}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
