"""CPU regression checks for offline asset retrieval and source dependencies."""

import hashlib
import json
import pytest

from utils import cell_assets


@pytest.fixture
def cached_asset(tmp_path, monkeypatch):
    root = tmp_path / "cache" / "test" / ("a" * 40)
    folder = root / "device"
    folder.mkdir(parents=True)
    (folder / "mesh.obj").write_text("v 0 0 0\n")
    entry = folder / "model.urdf"
    entry.write_text(
        '<robot name="test"><link name="base"><visual><geometry>'
        '<mesh filename="mesh.obj"/></geometry></visual></link></robot>'
    )
    (root / "LICENSE").write_text("Test fixture license")
    catalog = tmp_path / "catalog.json"
    catalog.write_text(json.dumps({
        "sources": {"test": {"revision": "a" * 40, "notice_files": ["LICENSE"]}},
        "assets": [{"asset_id": "test", "source": "test", "source_directory": "device",
                    "entry_file": "model.urdf",
                    "entry_sha256": hashlib.sha256(entry.read_bytes()).hexdigest()}],
    }))
    monkeypatch.setattr(cell_assets, "CATALOG_PATH", catalog)
    return tmp_path / "cache", entry


def test_offline_fetch_without_network(cached_asset):
    cache, entry = cached_asset
    assert cell_assets.fetch_asset("test", cache, offline=True) == entry


@pytest.mark.parametrize("damage", ["entry", "mesh", "license", "lfs"])
def test_incomplete_or_changed_sources_are_rejected(cached_asset, damage):
    cache, entry = cached_asset
    if damage == "entry":
        entry.write_text("changed")
    elif damage == "mesh":
        (entry.parent / "mesh.obj").unlink()
    elif damage == "license":
        (entry.parent.parent / "LICENSE").unlink()
    else:
        (entry.parent / "mesh.obj").write_text("version https://git-lfs.github.com/spec/v1\n")
    with pytest.raises((ValueError, FileNotFoundError)):
        cell_assets.fetch_asset("test", cache, offline=True)


def test_urdf_cannot_reference_outside_its_asset(cached_asset):
    _, entry = cached_asset
    entry.write_text(entry.read_text().replace('filename="mesh.obj"', 'filename="../LICENSE"'))
    with pytest.raises(ValueError, match="escapes"):
        cell_assets.validate_urdf_files(entry)


def test_unknown_asset_is_rejected():
    with pytest.raises(KeyError, match="Unknown"):
        cell_assets.fetch_asset("missing", offline=True)


def test_preview_help_does_not_require_isaac(capsys, monkeypatch):
    from demos.cell_assets import preview

    monkeypatch.setattr("sys.argv", ["preview", "--help"])
    with pytest.raises(SystemExit) as error:
        preview.main()
    assert error.value.code == 0
    assert "--asset-id" in capsys.readouterr().out
