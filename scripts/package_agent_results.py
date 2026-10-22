#!/usr/bin/env python3
"""Copy an explicitly selected, portable agent results package; never overwrite."""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from urllib.parse import quote, unquote, urlsplit
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
LINK = re.compile(r"(\]\()([^\n)]+)(\))")


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def git(*args: str) -> str:
    return subprocess.check_output(["git", "-C", str(ROOT), *args], text=True).strip()


def within(path: Path, parent: Path) -> bool:
    return path.is_relative_to(parent)


def selection_path(parent: Path, name: str, *, source: bool) -> Path:
    """Selections are repository/package relative and cannot traverse symlinks."""
    relative = Path(name)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"Selection must use a relative path without '..': {name}")
    path = parent / relative
    current = parent
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"Selection traverses a symlink: {current}")
    resolved = path.resolve()
    if not within(resolved, parent):
        raise ValueError(f"Selection escapes its {'repository' if source else 'package'}: {name}")
    return resolved


def build(manifest_path: Path, output: Path) -> dict:
    manifest_path = manifest_path.expanduser().absolute()
    if not within(manifest_path, ROOT):
        raise ValueError("Package manifest must be a repository file")
    manifest_path = selection_path(ROOT, manifest_path.relative_to(ROOT).as_posix(), source=True)
    config = json.loads(manifest_path.read_text(encoding="utf-8"))
    if config["schema"] != "labsim.agent_results_package.v1":
        raise ValueError("Unsupported package manifest schema")
    output = output.expanduser().absolute()
    if any(path.is_symlink() for path in (output, *output.parents)):
        raise ValueError(f"Output path must not traverse a symlink: {output}")
    output = output.resolve()
    if output.exists():
        raise FileExistsError(f"保留旧包，输出目录必须不存在：{output}")
    head, branch = git("rev-parse", "HEAD"), git("branch", "--show-current")
    repo_url = config["repository_url"].rstrip("/")
    generated_at = datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds")
    mapping: dict[Path, Path] = {}

    def select_file(source: Path, target: Path) -> None:
        if not within(source, ROOT) or not source.is_file() or source.is_symlink():
            raise ValueError(f"Invalid package file: {source}")
        if not within(target, output) or target == output:
            raise ValueError(f"Invalid package destination: {target}")
        reserved = (output / "文件清单.json", output / "SHA256SUMS.txt")
        if any(target == item or within(target, item) for item in reserved):
            raise ValueError(f"Reserved package destination: {target}")
        if source in mapping:
            raise ValueError(f"Duplicate source selection: {source}")
        if any(target == item or within(target, item) or within(item, target)
               for item in mapping.values()):
            raise ValueError(f"Duplicate or conflicting destination: {target}")
        with source.open("rb") as stream:
            if stream.read(100).startswith(b"version https://git-lfs.github.com/spec/v1"):
                raise ValueError(f"Fetch the actual Git LFS object first: {source}")
        mapping[source] = target

    for entry in config.get("directories", []):
        source = selection_path(ROOT, entry["source"], source=True)
        dest = selection_path(output, entry["destination"], source=False)
        if not source.is_dir():
            raise ValueError(f"Invalid package directory: {entry}")
        for path in sorted(source.rglob("*")):
            if path.is_symlink():
                raise ValueError(f"Source symlink is not a standalone result: {path}")
            if path.is_file():
                target = dest / path.relative_to(source)
                select_file(path, target)
    for entry in config.get("files", []):
        source = selection_path(ROOT, entry["source"], source=True)
        target = selection_path(output, entry["destination"], source=False)
        select_file(source, target)
    readme = selection_path(ROOT, config["readme"], source=True)
    select_file(readme, output / "00_给Agent阅读说明.md")
    # Finish all selection validation before creating the output directory.
    output.mkdir(parents=True, exist_ok=False)
    records = []
    replacements = {
        "{{GENERATED_AT}}": generated_at, "{{SOURCE_COMMIT}}": head,
        "{{BRANCH}}": branch, "{{REPOSITORY_URL}}": repo_url,
    }
    for source, target in mapping.items():
        target.parent.mkdir(parents=True, exist_ok=True)
        source_sha256 = digest(source)
        shutil.copy2(source, target)
        if digest(target) != source_sha256:
            raise ValueError(f"Source changed during copying or copy is corrupt: {source}")
        transformations = []
        if source == readme:
            text = target.read_text(encoding="utf-8")
            for key, value in replacements.items():
                text = text.replace(key, value)
            target.write_text(text, encoding="utf-8")
            transformations.append("rendered handoff metadata placeholders")
        elif source.suffix == ".md":
            count = 0

            def relocate(match: re.Match) -> str:
                nonlocal count
                raw = match.group(2)
                url = urlsplit(raw)
                if url.scheme or url.netloc or not url.path:
                    return match.group(0)
                original = (source.parent / unquote(url.path)).resolve()
                if original in mapping:
                    href = os.path.relpath(mapping[original], target.parent)
                else:
                    # Directory links are local when a copied file lies below them.
                    children = [p for p in mapping if within(p, original)]
                    if children:
                        first = children[0]
                        parent = mapping[first]
                        for _ in first.relative_to(original).parts:
                            parent = parent.parent
                        href = os.path.relpath(parent, target.parent)
                    else:
                        if not within(original, ROOT) or not original.exists():
                            raise ValueError(f"Cannot resolve report reference: {source}: {raw}")
                        relative = original.relative_to(ROOT).as_posix()
                        kind = "tree" if original.is_dir() else "blob"
                        href = f"{repo_url}/{kind}/{head}/{quote(relative, safe='/')}"
                if url.fragment:
                    href += "#" + url.fragment
                if href != raw:
                    count += 1
                return match.group(1) + href + match.group(3)

            old = target.read_text(encoding="utf-8")
            new = LINK.sub(relocate, old)
            if new != old:
                target.write_text(new, encoding="utf-8")
                transformations.append(f"relocated {count} Markdown links")
        records.append({"path": target.relative_to(output).as_posix(),
                        "source": source.relative_to(ROOT).as_posix(),
                        "source_sha256": source_sha256, "sha256": digest(target),
                        "bytes": target.stat().st_size, "transformations": transformations})
    for target in mapping.values():
        if target.suffix != ".md":
            continue
        for match in LINK.finditer(target.read_text(encoding="utf-8")):
            url = urlsplit(match.group(2))
            if not url.scheme and not url.netloc and url.path:
                link = (target.parent / unquote(url.path)).resolve()
                if not within(link, output) or not link.exists():
                    raise ValueError(f"Broken standalone link: {target}: {url.path}")
    record = {"schema": config["schema"], "generated_at": generated_at,
              "repository_url": repo_url, "branch": branch, "source_commit": head,
              "working_tree_status_at_creation": git("status", "--porcelain"),
              "manifest_source": manifest_path.relative_to(ROOT).as_posix(),
              "manifest_source_sha256": digest(manifest_path),
              "files": records}
    (output / "文件清单.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    files = sorted(p for p in output.rglob("*") if p.is_file())
    (output / "SHA256SUMS.txt").write_text("".join(
        f"{digest(p)}  {p.relative_to(output).as_posix()}\n" for p in files), encoding="utf-8")
    for entry in records:
        if digest(output / entry["path"]) != entry["sha256"]:
            raise ValueError(f"Copy integrity mismatch: {entry['path']}")
    return {"output": str(output), "files": len(files) + 1,
            "bytes": sum(p.stat().st_size for p in output.rglob("*") if p.is_file()),
            "source_commit": head, "standalone_links_verified": True}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path,
                        default=ROOT / "docs/agent_handoff/package.json")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = build(args.manifest.absolute(), args.output)
    except (ValueError, FileExistsError) as exc:
        parser.exit(1, f"{exc}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
