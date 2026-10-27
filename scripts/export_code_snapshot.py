"""Export the current working tree as a dated, asset-free delivery snapshot.

Run after a completed and verified local update. This does not commit or push Git.
The source checkout and its experiment evidence remain unchanged.
"""

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from zoneinfo import ZoneInfo


MARKER = "snapshot.json"
SCHEMA = "labsim-code-snapshot-v1"
EXCLUDED_ROOTS = {
    "assets", "images", "local_assets", "results", "local_setup", "outputs",
    "test_outputs", ".git", ".cursor", ".vscode", ".agents", ".codex", ".aws",
}
TEXT_EXTENSIONS = {
    ".py", ".md", ".rst", ".txt", ".json", ".yaml", ".yml", ".toml",
    ".ini", ".cfg", ".sh", ".bash", ".xml", ".patch",
}
ROOT_FILES = {"labsim", "LICENSE", ".gitignore", ".gitattributes"}


def include_file(relative: Path) -> bool:
    """Select source, configuration and Markdown; exclude media and results."""
    if relative.as_posix() == "assets/README.md":
        return True
    if relative.parts[0] in EXCLUDED_ROOTS:
        return False
    if any(part in {"__pycache__", ".cache", ".pytest_cache", ".git"}
           for part in relative.parts):
        return False
    if relative.name.startswith(".env") or relative.suffix.lower() in {".pem", ".key"}:
        return False
    if relative.parts[0] == "docs":
        return relative.suffix.lower() in {".md", ".rst"}
    return relative.suffix.lower() in TEXT_EXTENSIONS or relative.as_posix() in ROOT_FILES


def fingerprint(path: Path) -> dict:
    """Return a reproducible size/hash record for one delivery file."""
    data = path.read_bytes()
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def check_managed_snapshot(folder: Path, source: Path) -> None:
    """Refuse to replace snapshots edited by hand or unrelated directories."""
    if folder.is_symlink():
        raise ValueError(f"Snapshot destination cannot be a symlink: {folder}")
    metadata = json.loads((folder / MARKER).read_text())
    if metadata.get("schema") != SCHEMA or metadata.get("source") != str(source):
        raise ValueError(f"Not a snapshot owned by this checkout: {folder}")
    actual = {p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file()}
    if actual != set(metadata["files"]) | {MARKER}:
        raise ValueError(f"Snapshot files changed manually; preserve edits first: {folder}")
    for relative, expected in metadata["files"].items():
        path = folder / relative
        if path.is_symlink() or fingerprint(path) != expected:
            raise ValueError(f"Snapshot edited manually; preserve edits first: {path}")


def export_snapshot(source: Path, date: str) -> Path:
    """Publish one current code snapshot and retire unchanged older exports."""
    source = source.resolve()
    if not re.fullmatch(r"\d{8}", date):
        raise ValueError("Date must use YYYYMMDD")
    datetime.strptime(date, "%Y%m%d")
    parent = source.parent / "codex"
    parent.mkdir(exist_ok=True)
    if parent.is_symlink():
        raise ValueError("The codex delivery directory cannot be a symlink")
    destination = parent / f"labsim_junjie_yao_{date}"
    previous = []
    for folder in parent.glob("labsim_junjie_yao_*"):
        if re.fullmatch(r"labsim_junjie_yao_\d{8}", folder.name):
            check_managed_snapshot(folder, source)
            previous.append(folder)
    tracked = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=source,
    ).decode().split("\0")
    staging = Path(tempfile.mkdtemp(prefix=".labsim-snapshot-", dir=parent))
    try:
        files = {}
        excluded = 0
        for name in sorted(set(filter(None, tracked))):
            relative = Path(name)
            original = source / relative
            if not original.is_file() or original.is_symlink() or not include_file(relative):
                excluded += 1
                continue
            if original.stat().st_size > 1024 * 1024:
                raise ValueError(f"Large text file needs review before export: {relative}")
            target = staging / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(original, target)
            files[name] = fingerprint(target)
        metadata = {
            "schema": SCHEMA,
            "source": str(source),
            "updated_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
            "intended_branch": f"codex/labsim_junjie_yao_{date}",
            "source_branch": subprocess.check_output(
                ["git", "branch", "--show-current"], cwd=source, text=True).strip(),
            "source_head": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=source, text=True).strip(),
            "includes_uncommitted_changes": True,
            "excluded_files": excluded,
            "files": files,
        }
        (staging / MARKER).write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n")
        check_managed_snapshot(staging, source)
        # Keep the previous same-day snapshot until the new copy is complete.
        backup = None
        if destination.exists():
            backup = parent / f".labsim-backup-{date}"
            if backup.exists():
                raise FileExistsError(backup)
            destination.rename(backup)
        try:
            staging.rename(destination)
        except OSError:
            if backup is not None:
                backup.rename(destination)
            raise
        if backup is not None:
            shutil.rmtree(backup)
        for folder in previous:
            if folder != destination:
                shutil.rmtree(folder)
        return destination
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", default=datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y%m%d"))
    args = parser.parse_args()
    output = export_snapshot(Path(__file__).resolve().parents[1], args.date)
    metadata = json.loads((output / MARKER).read_text())
    print(f"Exported {len(metadata['files'])} code/document files to {output}")


if __name__ == "__main__":
    main()
