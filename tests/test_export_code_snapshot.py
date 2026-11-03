"""Check that delivery updates preserve source data and protect manual edits."""

import subprocess

import pytest

from scripts.export_code_snapshot import export_snapshot


@pytest.fixture
def source(tmp_path):
    root = tmp_path / "labsim"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run([
        "git", "-c", "user.name=Snapshot Test", "-c", "user.email=test@example.invalid",
        "-c", "commit.gpgsign=false", "commit", "--allow-empty", "-qm", "test baseline",
    ], cwd=root, check=True)
    for name, body in {
        "app.py": "print('working tree')\n",
        "README.md": "Use the asset mirror.\n",
        "assets/README.md": "Download models from the pinned HF mirror.\n",
        "assets/internal.md": "Asset-internal material is not a delivery entry point.",
        "assets/model.usd": "model bytes",
        "local_assets/source.py": "not code to deliver",
        "results/output.json": "{}",
        "docs/report.md": "verified results",
        "docs/trajectory.json": "{}",
        "docs/movie.mp4": "media bytes",
        ".env": "LOCAL_SECRET=test-only-fixture",
    }.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body)
    return root


def test_export_keeps_code_and_docs_without_assets_results_or_secrets(source):
    (source / "linked.py").symlink_to(source / "app.py")
    output = export_snapshot(source, "20261027")
    assert {p.relative_to(output).as_posix() for p in output.rglob("*") if p.is_file()} == {
        "app.py", "README.md", "assets/README.md", "docs/report.md", "snapshot.json",
    }
    assert (source / "assets/model.usd").read_text() == "model bytes"


def test_update_replaces_stale_copy_and_keeps_only_latest_date(source):
    previous = export_snapshot(source, "20261027")
    (source / "app.py").unlink()
    (source / "next.py").write_text("print('updated')\n")
    refreshed = export_snapshot(source, "20261027")
    assert not (refreshed / "app.py").exists()
    latest = export_snapshot(source, "20261028")
    assert not previous.exists()
    assert (latest / "next.py").read_text() == "print('updated')\n"


def test_export_refuses_to_overwrite_manual_snapshot_edits(source):
    output = export_snapshot(source, "20261027")
    (output / "README.md").write_text("manual reviewer changes")
    with pytest.raises(ValueError, match="edited manually"):
        export_snapshot(source, "20261027")
    assert (output / "README.md").read_text() == "manual reviewer changes"
