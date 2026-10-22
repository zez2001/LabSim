"""Explicit handoff selection, portability and non-overwrite contracts."""
import json
from pathlib import Path

import pytest

from scripts import package_agent_results as package


@pytest.fixture
def repo(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "handoff.md").write_text("Commit {{SOURCE_COMMIT}}\n", encoding="utf-8")
    (root / "docs").mkdir()
    (root / "docs/guide.md").write_text("Guide\n", encoding="utf-8")
    monkeypatch.setattr(package, "ROOT", root)
    monkeypatch.setattr(package, "git", lambda *args: {
        ("rev-parse", "HEAD"): "a" * 40, ("branch", "--show-current"): "codex/labsim",
        ("status", "--porcelain"): ""}[args])
    return root


def manifest(repo, *, directories=None, files=None):
    value = dict(schema="labsim.agent_results_package.v1", repository_url="https://example.test/LabSim",
        readme="handoff.md")
    if directories is not None:
        value["directories"] = directories
    if files is not None:
        value["files"] = files
    path = repo / "package.json"
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def test_legacy_directories_manifest_still_packages(repo, tmp_path):
    output = tmp_path / "old-compatible"
    result = package.build(manifest(repo, directories=[dict(source="docs", destination="guide")]), output)
    assert result["standalone_links_verified"]
    assert (output / "guide/guide.md").read_text() == "Guide\n"
    assert (output / "00_给Agent阅读说明.md").read_text() == "Commit " + "a" * 40 + "\n"
    record = json.loads((output / "文件清单.json").read_text())
    assert all(package.digest(output / item["path"]) == item["sha256"] for item in record["files"])


def test_files_and_directories_relocate_cross_links_and_pin_unselected_refs(repo, tmp_path):
    (repo / "README.md").write_text("[guide](docs/guide.md) [history](history.md)\n", encoding="utf-8")
    (repo / "history.md").write_text("Large evidence remains in GitHub\n", encoding="utf-8")
    (repo / "docs/guide.md").write_text("[project](../README.md)\n", encoding="utf-8")
    output = tmp_path / "mixed"
    result = package.build(manifest(repo,
        directories=[dict(source="docs", destination="01_docs")],
        files=[dict(source="README.md", destination="02_project/README.md")]), output)
    assert result["standalone_links_verified"]
    assert (output / "01_docs/guide.md").read_text() == "[project](../02_project/README.md)\n"
    text = (output / "02_project/README.md").read_text()
    assert "[guide](../01_docs/guide.md)" in text
    assert "https://example.test/LabSim/blob/" + "a" * 40 + "/history.md" in text
    assert not (output / "history.md").exists()


def test_files_only_manifest_is_supported(repo, tmp_path):
    output = tmp_path / "files-only"
    package.build(manifest(repo, files=[dict(source="docs/guide.md", destination="guide.md")]), output)
    assert (output / "guide.md").exists()


@pytest.mark.parametrize("source,destination", [
    ("../outside.md", "safe.md"), ("docs/guide.md", "../escape.md"),
    ("/etc/passwd", "safe.md"), ("docs/guide.md", "/tmp/escape.md"),
    ("docs/guide.md", "文件清单.json"), ("docs/guide.md", "SHA256SUMS.txt/child.md"),
])
def test_unsafe_or_reserved_file_selection_rejected_before_mkdir(repo, tmp_path, source, destination):
    output = tmp_path / "unsafe"
    with pytest.raises(ValueError):
        package.build(manifest(repo, files=[dict(source=source, destination=destination)]), output)
    assert not output.exists()


@pytest.mark.parametrize("mode", ["source_file", "source_parent", "directory_parent"])
def test_symlinks_rejected_before_mkdir(repo, tmp_path, mode):
    if mode == "source_file":
        (repo / "linked.md").symlink_to(repo / "docs/guide.md")
        selection = dict(files=[dict(source="linked.md", destination="guide.md")])
    elif mode == "source_parent":
        (repo / "alias").symlink_to(repo / "docs", target_is_directory=True)
        selection = dict(files=[dict(source="alias/guide.md", destination="guide.md")])
    else:
        (repo / "alias").symlink_to(repo / "docs", target_is_directory=True)
        selection = dict(directories=[dict(source="alias", destination="docs")])
    output = tmp_path / "linked"
    with pytest.raises(ValueError, match="symlink"):
        package.build(manifest(repo, **selection), output)
    assert not output.exists()


def test_lfs_pointer_file_rejected_before_mkdir(repo, tmp_path):
    (repo / "placeholder.usd").write_text("version https://git-lfs.github.com/spec/v1\noid sha256:abc\nsize 10\n")
    output = tmp_path / "pointer"
    with pytest.raises(ValueError, match="Git LFS"):
        package.build(manifest(repo, files=[dict(source="placeholder.usd", destination="asset.usd")]), output)
    assert not output.exists()


@pytest.mark.parametrize("destinations", [("guide.md", "guide.md"), ("node", "node/child.md")])
def test_duplicate_or_file_directory_destination_conflicts_rejected(repo, tmp_path, destinations):
    (repo / "second.md").write_text("Second\n")
    output = tmp_path / "conflict"
    with pytest.raises(ValueError, match="destination"):
        package.build(manifest(repo, files=[
            dict(source="docs/guide.md", destination=destinations[0]),
            dict(source="second.md", destination=destinations[1])]), output)
    assert not output.exists()


def test_same_source_selected_twice_is_rejected(repo, tmp_path):
    output = tmp_path / "duplicate-source"
    with pytest.raises(ValueError, match="Duplicate source"):
        package.build(manifest(repo, directories=[dict(source="docs", destination="docs")],
            files=[dict(source="docs/guide.md", destination="copy.md")]), output)
    assert not output.exists()


def test_existing_output_is_never_overwritten(repo, tmp_path):
    output = tmp_path / "existing"
    output.mkdir()
    sentinel = output / "keep.txt"
    sentinel.write_text("unchanged\n")
    with pytest.raises(FileExistsError):
        package.build(manifest(repo, files=[dict(source="docs/guide.md", destination="guide.md")]), output)
    assert sentinel.read_text() == "unchanged\n"
    assert len(list(output.iterdir())) == 1


def test_output_symlink_parent_is_rejected(repo, tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(real, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        package.build(manifest(repo, files=[dict(source="docs/guide.md", destination="guide.md")]), alias / "new")
    assert not (real / "new").exists()
