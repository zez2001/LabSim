"""Asset integrity, license gates, offline reuse, and interrupted HTTP transfer."""
import hashlib
import io
import json
from pathlib import Path

import pytest

from demos.lab_cuvette_project_v1.assets import (
    AssetError, check_assets, download_assets, load_lock, materialize_assets,
    relative_path, rooted_path)


CONTENT = b"#usda 1.0\nself-created rack geometry\n"
PRIVATE = b"locally authorized model\n"


def record(path, data, distribution="public_hf"):
    row = dict(path=path, size_bytes=len(data), sha256=hashlib.sha256(data).hexdigest(),
               tasks=["lab_cuvette_loading"], distribution=distribution,
               license="MIT" if distribution == "public_hf" else "unknown")
    if distribution == "public_hf":
        row["hf_path"] = "releases/Project_v1/" + path
    return row


def index(tmp_path, local=False):
    rows = [record("assets/rack.usda", CONTENT)]
    if local:
        rows.append(record("assets/instrument.usd", PRIVATE, "local_only"))
    p = tmp_path / "lock.json"
    p.write_text(json.dumps(dict(schema="labsim.project.asset_release.v1",
        repository="Example/Assets", revision="a" * 40, files=rows)))
    return p


class Response(io.BytesIO):
    def __init__(self, content, status=200, headers=None):
        super().__init__(content)
        self.status = status
        self.headers = headers or {}


def test_anonymous_download_is_pinned_verified_and_reused(tmp_path, monkeypatch):
    p = index(tmp_path)
    calls = []
    monkeypatch.setenv("HF_TOKEN", "must-not-be-used")
    def opener(request, timeout):
        calls.append(request)
        assert "Authorization" not in request.headers
        assert "/" + "a" * 40 + "/" in request.full_url
        assert timeout == 60
        return Response(CONTENT)
    first = download_assets(p, cache=tmp_path / "cache", opener=opener)
    second = download_assets(p, cache=tmp_path / "cache", offline=True)
    assert first["files_verified"] == second["files_verified"] == 1
    assert not first["files"][0]["reused"]
    assert second["files"][0]["reused"] and len(calls) == 1


def test_resume_requires_matching_content_range(tmp_path):
    p = index(tmp_path)
    target = tmp_path / "cache" / ("a" * 40) / "assets/rack.usda"
    target.parent.mkdir(parents=True)
    target.with_name("rack.usda.part").write_bytes(CONTENT[:7])
    def opener(request, timeout):
        assert request.headers["Range"] == "bytes=7-"
        return Response(CONTENT[7:], 206, {"Content-Range": f"bytes 7-{len(CONTENT)-1}/{len(CONTENT)}"})
    download_assets(p, cache=tmp_path / "cache", opener=opener)
    assert target.read_bytes() == CONTENT


def test_server_ignoring_resume_restarts_instead_of_appending(tmp_path):
    p = index(tmp_path)
    target = tmp_path / "cache" / ("a" * 40) / "assets/rack.usda"
    target.parent.mkdir(parents=True)
    target.with_name("rack.usda.part").write_bytes(CONTENT[:7])
    download_assets(p, cache=tmp_path / "cache", opener=lambda *a, **k: Response(CONTENT))
    assert target.read_bytes() == CONTENT


def test_corrupt_download_never_becomes_an_installed_asset(tmp_path):
    p = index(tmp_path)
    with pytest.raises(AssetError, match="SHA256"):
        download_assets(p, cache=tmp_path / "cache", opener=lambda *a, **k: Response(b"x" * len(CONTENT)))
    assert not (tmp_path / "cache" / ("a" * 40) / "assets/rack.usda").exists()


@pytest.mark.parametrize("value", ["/absolute", "../escape", "a/../../escape", "a\\b", "", ".", "a/./b", "a//b"])
def test_manifest_paths_cannot_escape_asset_root(value):
    with pytest.raises(AssetError):
        relative_path(value)


def test_symlink_inside_installation_is_rejected(tmp_path):
    (tmp_path / "outside").mkdir()
    (tmp_path / "assets").symlink_to(tmp_path / "outside", target_is_directory=True)
    with pytest.raises(AssetError, match="Symlink"):
        rooted_path(tmp_path, "assets/test.usd")


@pytest.mark.parametrize("field,value,match", [
    ("revision", "main", "pinned"),
    ("files", [record("assets/rack.usda", CONTENT) | {"license": "unknown"}], "license"),
    ("files", [record("assets/rack.usda", CONTENT)] * 2, "Duplicate"),
])
def test_release_index_refuses_unpinned_or_unlicensed_public_files(tmp_path, field, value, match):
    p = index(tmp_path)
    data = json.loads(p.read_text()); data[field] = value; p.write_text(json.dumps(data))
    with pytest.raises(AssetError, match=match):
        load_lock(p)


def seed_cache(tmp_path, p):
    download_assets(p, cache=tmp_path / "cache", opener=lambda *a, **k: Response(CONTENT))


def test_local_only_assets_require_explicit_authorized_tree_and_matching_hash(tmp_path):
    p = index(tmp_path, local=True)
    seed_cache(tmp_path, p)
    output = tmp_path / "portable"
    with pytest.raises(AssetError, match="local-only"):
        materialize_assets(output, p, cache=tmp_path / "cache", offline=True)
    assert not output.exists()  # validate entire plan before copying any files
    source = tmp_path / "authorized" / "assets" / "instrument.usd"
    source.parent.mkdir(parents=True); source.write_bytes(PRIVATE)
    result = materialize_assets(output, p, cache=tmp_path / "cache",
        private_root=tmp_path / "authorized", offline=True)
    assert result["files_verified"] == 2 and result["local_only_files"] == 1
    assert check_assets(output, p)["all_files_verified"]
    source.write_bytes(b"different")
    assert materialize_assets(output, p, cache=tmp_path / "cache", offline=True)["all_installed_files_verified"]


def test_install_never_overwrites_changed_destination(tmp_path):
    p = index(tmp_path)
    seed_cache(tmp_path, p)
    target = tmp_path / "portable" / "assets/rack.usda"
    target.parent.mkdir(parents=True); target.write_bytes(b"user edits")
    with pytest.raises(AssetError, match="refusing overwrite"):
        materialize_assets(tmp_path / "portable", p, cache=tmp_path / "cache", offline=True)
    assert target.read_bytes() == b"user edits"


def test_offline_missing_has_actionable_error(tmp_path):
    with pytest.raises(AssetError, match="assets download"):
        download_assets(index(tmp_path), cache=tmp_path / "cache", offline=True)


def test_external_robot_is_downloaded_from_existing_pinned_source_not_republished(tmp_path):
    p = index(tmp_path)
    data = json.loads(p.read_text())
    robot = record("assets/robots/Franka.usd", PRIVATE, "local_only")
    robot.update(distribution="external_pinned", external_revision="b" * 40,
        download_url="https://media.githubusercontent.com/media/Example/Project/" +
                     "b" * 40 + "/assets/robots/Franka.usd")
    data["files"].append(robot); p.write_text(json.dumps(data))
    calls = []
    def opener(request, timeout):
        calls.append(request.full_url)
        return Response(PRIVATE if request.full_url.startswith("https://media.") else CONTENT)
    result = download_assets(p, cache=tmp_path / "cache", opener=opener)
    assert result["files_verified"] == 2 and result["external_pinned_files"] == 1
    assert not result["complete_task_bundle"]
    assert result["complete_publicly_downloadable_task_bundle"]
    assert result["local_only_files"] == 0
    assert calls[1] == robot["download_url"]


@pytest.mark.parametrize("url", ["http://media.githubusercontent.com/media/a/b/" + "b" * 40 + "/f",
                                "https://untrusted.example/" + "b" * 40 + "/f",
                                "https://media.githubusercontent.com/media/a/b/main/f"])
def test_external_download_requires_https_approved_host_and_immutable_revision(tmp_path, url):
    p = index(tmp_path)
    data = json.loads(p.read_text())
    robot = record("assets/robots/Franka.usd", PRIVATE, "local_only")
    robot.update(distribution="external_pinned", external_revision="b" * 40, download_url=url)
    data["files"].append(robot); p.write_text(json.dumps(data))
    with pytest.raises(AssetError, match="pinned"):
        load_lock(p)
