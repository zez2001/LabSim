"""Pinned, anonymous asset downloads and explicit local dependency installation.

This module uses the Python standard library only. It never reads an HF token,
uploads a file, imports Isaac, or changes an installed Python environment.
Unknown model redistribution rights are a per-file gate, not an implied license.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LOCK = ROOT / "config/lab_cuvette_loading/Project_v1/assets.lock.json"
SCHEMA = "labsim.project.asset_release.v1"


class AssetError(RuntimeError):
    """An actionable missing, invalid, or unavailable asset dependency."""


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for data in iter(lambda: stream.read(1 << 20), b""):
            digest.update(data)
    return digest.hexdigest()


def relative_path(value):
    if not isinstance(value, str) or not value or "\\" in value:
        raise AssetError("Asset path must be a nonempty POSIX relative path")
    path = PurePosixPath(value)
    if not path.parts or str(path) != value or path.is_absolute() \
            or any(part in {"", ".", ".."} for part in path.parts):
        raise AssetError("Asset path must not be absolute or escape its root: " + value)
    return path


def rooted_path(root, value):
    root = Path(root).expanduser().resolve()
    path = root / relative_path(value)
    for parent in [path, *path.parents]:
        if parent == root:
            break
        if parent.is_symlink():
            raise AssetError("Symlink is not an asset installation target: " + str(parent))
    if not path.resolve().is_relative_to(root):
        raise AssetError("Asset path escapes its root: " + value)
    return path


def load_lock(path=DEFAULT_LOCK):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("schema") != SCHEMA:
        raise AssetError("Unsupported asset release index schema")
    if not re.fullmatch(r"[0-9a-f]{40}", data.get("revision", "")):
        raise AssetError("Asset downloads require a pinned, actual HF commit revision")
    if not re.fullmatch(r"[\w.-]+/[\w.-]+", data.get("repository", "")):
        raise AssetError("Invalid HF repository ID")
    if not isinstance(data.get("files"), list) or not data["files"]:
        raise AssetError("Asset release index must declare a nonempty file list")
    seen = set()
    for row in data.get("files", []):
        relative_path(row["path"])
        if row["path"] in seen:
            raise AssetError("Duplicate asset path in release index")
        seen.add(row["path"])
        if not re.fullmatch(r"[0-9a-f]{64}", row.get("sha256", "")):
            raise AssetError("Missing asset SHA256")
        if not isinstance(row.get("size_bytes"), int) or row["size_bytes"] < 1:
            raise AssetError("Missing positive asset byte size")
        if row.get("distribution") not in {"public_hf", "external_pinned", "local_only"}:
            raise AssetError("Unknown asset distribution gate")
        if row["distribution"] == "public_hf":
            relative_path(row["hf_path"])
            if not row.get("license") or row["license"] == "unknown":
                raise AssetError("Public asset requires an explicit per-file license")
        if row["distribution"] == "external_pinned":
            url = urllib.parse.urlsplit(row.get("download_url", ""))
            revision = row.get("external_revision", "")
            if url.scheme != "https" or url.hostname not in {"media.githubusercontent.com", "raw.githubusercontent.com"} \
                    or url.username or url.password or not re.fullmatch(r"[0-9a-f]{40}", revision) \
                    or ("/" + revision + "/") not in url.path:
                raise AssetError("External asset requires an approved HTTPS Git source pinned to a commit")
    return data


def cache_root(value=None):
    if value:
        return Path(value).expanduser().resolve()
    base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return Path(os.environ.get("LABSIM_ASSET_CACHE", base / "labsim/assets")).expanduser().resolve()


def selected_files(lock, task="lab_cuvette_loading", *, include_local=False):
    task_files = [row for row in lock["files"] if task in row.get("tasks", [])]
    if not task_files:
        raise AssetError("No asset dependencies are registered for task: " + str(task))
    return [row for row in task_files
            if include_local or row["distribution"] in {"public_hf", "external_pinned"}]


def verified(path, row):
    path = Path(path)
    return path.is_file() and not path.is_symlink() and path.stat().st_size == row["size_bytes"] \
        and sha256(path) == row["sha256"]


def _download(url, destination, row, *, timeout=60.0, retries=3, opener=None):
    """Resume an interrupted download; validate size and content before install."""
    if timeout <= 0 or not 1 <= retries <= 8:
        raise AssetError("Download timeout must be positive and retries must be 1..8")
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(destination.name + ".part")
    if partial.is_symlink():
        raise AssetError("Refusing symlink partial download")
    open_url = opener or urllib.request.urlopen
    last_error = None
    for attempt in range(retries):
        start = partial.stat().st_size if partial.exists() else 0
        if start >= row["size_bytes"]:
            if start == row["size_bytes"] and verified(partial, row):
                os.replace(partial, destination)
                return
            partial.unlink()
            start = 0
        headers = {"User-Agent": "LabSim-Project-v1/1.0"}
        if start:
            headers["Range"] = f"bytes={start}-"
        request = urllib.request.Request(url, headers=headers)
        try:
            with open_url(request, timeout=timeout) as response:
                status = getattr(response, "status", 200)
                resume = start > 0 and status == 206
                if resume and not response.headers.get("Content-Range", "").startswith(f"bytes {start}-"):
                    raise AssetError("Server returned an inconsistent download range")
                with partial.open("ab" if resume else "wb") as stream:
                    while True:
                        chunk = response.read(1 << 20)
                        if not chunk:
                            break
                        stream.write(chunk)
                        if stream.tell() > row["size_bytes"]:
                            raise AssetError("Downloaded asset exceeds declared size")
            if not verified(partial, row):
                raise AssetError("Downloaded asset size or SHA256 mismatch: " + row["path"])
            os.replace(partial, destination)
            return
        except urllib.error.HTTPError as error:
            last_error = error
            if error.code not in {408, 429, 500, 502, 503, 504}:
                raise AssetError(f"HF download failed (HTTP {error.code}): {row['path']}. "
                                 "Check the pinned revision and public access.") from None
        except (OSError, TimeoutError, urllib.error.URLError) as error:
            last_error = error
        if attempt + 1 < retries:
            time.sleep(min(2 ** attempt, 8))
    raise AssetError(f"HF download failed after {retries} attempts for {row['path']}: "
                     f"{type(last_error).__name__}. Retry with the same cache; partial files resume.")


def download_assets(lock_path=DEFAULT_LOCK, *, task="lab_cuvette_loading", cache=None,
                    offline=False, timeout=60.0, retries=3, opener=None):
    lock = load_lock(lock_path)
    base = cache_root(cache) / lock["revision"]
    results = []
    for row in selected_files(lock, task):
        target = rooted_path(base, row["path"])
        reused = verified(target, row)
        if not reused:
            if offline:
                raise AssetError("Offline cache missing or invalid: " + row["path"] +
                                 "; run ./labsim assets download once while online")
            if row["distribution"] == "external_pinned":
                url = row["download_url"]
            else:
                url = "https://huggingface.co/datasets/" + lock["repository"] + "/resolve/" \
                    + lock["revision"] + "/" + urllib.parse.quote(row["hf_path"], safe="/")
            _download(url, target, row, timeout=timeout, retries=retries, opener=opener)
        results.append({"path": row["path"], "cache_path": str(target),
                        "sha256": row["sha256"], "size_bytes": row["size_bytes"],
                        "reused": reused, "verified": True, "distribution": row["distribution"],
                        "license": row.get("license", "unknown")})
    return {"schema": "labsim.project.asset_download.v1", "repository": lock["repository"],
            "revision": lock["revision"], "anonymous": True, "offline": offline,
            "cache_root": str(base), "files": results,
            "files_verified": len(results), "bytes_verified": sum(r["size_bytes"] for r in results),
            "local_only_files": len(selected_files(lock, task, include_local=True)) - len(results),
            "external_pinned_files": sum(r["distribution"] == "external_pinned" for r in results),
            "complete_task_bundle": all(r["distribution"] == "public_hf"
                                        for r in selected_files(lock, task, include_local=True)),
            "complete_publicly_downloadable_task_bundle": not any(r["distribution"] == "local_only"
                                        for r in selected_files(lock, task, include_local=True))}


def materialize_assets(destination, lock_path=DEFAULT_LOCK, *, task="lab_cuvette_loading",
                       cache=None, private_root=None, offline=False, include_local=True):
    """Install declared dependencies in one portable root, refusing changed files.

    Local CAD dependencies must be supplied by an authorized user; this does not
    grant rights or download those files from a hidden source. The exact same
    hashes are required regardless of the source directory.
    """
    lock = load_lock(lock_path)
    downloaded = download_assets(lock_path, task=task, cache=cache, offline=offline)
    downloaded_by_path = {row["path"]: Path(row["cache_path"]) for row in downloaded["files"]}
    private = private_root or os.environ.get("LABSIM_PRIVATE_ASSET_ROOT")
    rows = selected_files(lock, task, include_local=include_local)
    plan, missing = [], []
    for row in rows:
        target = rooted_path(destination, row["path"])
        if target.exists():
            if not verified(target, row):
                raise AssetError("Existing asset differs; refusing overwrite: " + str(target))
            plan.append((row, None, target))
            continue
        source = downloaded_by_path.get(row["path"])
        if source is None and private:
            source = rooted_path(private, row["path"])
        if source is None or not verified(source, row):
            missing.append(row["path"])
        else:
            plan.append((row, source, target))
    if missing:
        raise AssetError("Required local-only model files are missing or differ. Set "
                         "LABSIM_PRIVATE_ASSET_ROOT to an authorized asset tree preserving assets/...; "
                         "no public redistribution license has been established for these files:\n" +
                         "\n".join(missing))
    for row, source, target in plan:
        if source is not None:
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_name(target.name + ".install-part")
            if temporary.exists() or temporary.is_symlink():
                raise AssetError("Previous installation temporary exists: " + str(temporary))
            shutil.copyfile(source, temporary)
            if not verified(temporary, row):
                raise AssetError("Asset changed during installation: " + row["path"])
            os.replace(temporary, target)
    return {"schema": "labsim.project.asset_install.v1", "asset_root": str(Path(destination).resolve()),
            "revision": lock["revision"], "files_verified": len(rows),
            "bytes_verified": sum(row["size_bytes"] for row in rows),
            "local_only_files": sum(row["distribution"] == "local_only" for row in rows),
            "public_only": not include_local,
            "all_installed_files_verified": all(verified(rooted_path(destination, r["path"]), r) for r in rows)}


def check_assets(asset_root, lock_path=DEFAULT_LOCK, *, task="lab_cuvette_loading"):
    lock = load_lock(lock_path)
    rows = selected_files(lock, task, include_local=True)
    missing = [r["path"] for r in rows if not verified(rooted_path(asset_root, r["path"]), r)]
    return {"schema": "labsim.project.asset_check.v1", "asset_root": str(Path(asset_root).resolve()),
            "revision": lock["revision"], "required_files": len(rows),
            "all_files_verified": not missing, "missing_or_invalid": missing}
