"""Project entry-point contracts; no Isaac/GPU or synthetic success data."""
import json
from pathlib import Path

import pytest

from scripts import labsim_cli as cli


def parse(*args):
    return cli.parser().parse_args(args)


def test_demo_is_one_standard_GUI_episode_and_accepts_spaces(tmp_path):
    output = tmp_path / "new run with spaces"
    command = cli.build_command(parse("demo", "--output", str(output)))
    assert command[-1] == str(output)
    assert command[command.index("--episodes") + 1] == "1"
    assert command[command.index("--layout-mode") + 1] == "standard"
    assert "--headless" not in command
    assert not output.exists()


def test_demo_headless_is_explicit(tmp_path):
    assert cli.build_command(parse("demo", "--output", str(tmp_path / "new"), "--headless"))[-1] == "--headless"


def test_demo_refuses_existing_output(tmp_path):
    with pytest.raises(ValueError, match="already exists"):
        cli.build_command(parse("demo", "--output", str(tmp_path)))


def test_paths_always_repository_relative():
    assert cli.resolve_path("outputs/new run") == cli.ROOT / "outputs/new run"


def test_dryrun_emits_exact_argv_and_does_not_create_files(tmp_path, capsys):
    output = tmp_path / "new"
    assert cli.main(["demo", "--output", str(output), "--dry-run"]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["files_created"] is False and plan["simulation_started"] is False
    assert plan["argv"][-1] == str(output)
    assert not output.exists()


def test_collect_refuses_outside_dedicated_outputs(tmp_path):
    with pytest.raises(ValueError, match="dedicated"):
        cli.build_command(parse("collect", "--phase", "verify5", "--collection", str(tmp_path / "x")))


def test_collect_requires_review_gate_for_later_phases():
    with pytest.raises(ValueError, match="verify5"):
        cli.build_command(parse("collect", "--phase", "success", "--collection", "outputs/lab_cuvette_loading/Size_v1/example"))


def test_collect_argv_preserves_sequential_driver_and_review_gate():
    command = cli.build_command(parse("collect", "--phase", "controlled_failure", "--collection",
        "outputs/lab_cuvette_loading/Size_v1/example", "--allow-after-verified-five", "--headless"))
    assert command[1].endswith("collect_lab_cuvette_size_v1_standard.py")
    assert "--allow-after-verified-five" in command and "--headless" in command
    assert command[command.index("--episodes-per-process") + 1] == "5"


def test_collect_rejects_nonpositive_process_budget():
    with pytest.raises(ValueError, match="positive"):
        cli.build_command(parse("collect", "--phase", "verify5", "--collection", "outputs/lab_cuvette_loading/Size_v1/example",
            "--max-processes", "0"))


def fake_collection(tmp_path, monkeypatch):
    monkeypatch.setattr(cli, "OUTPUT_ROOT", tmp_path)
    collection = tmp_path / "collection"
    collection.mkdir()
    (collection / "collection_contract.json").write_text("{}")
    return collection


def test_validator_rejects_active_run(tmp_path, monkeypatch):
    collection = fake_collection(tmp_path, monkeypatch)
    (collection / "runs/active/episode_0000").mkdir(parents=True)
    with pytest.raises(ValueError, match="not closed"):
        cli.build_command(parse("validate", "--collection", str(collection), "--index", str(collection / "dataset/episode_data.hdf5"),
            "--output", str(tmp_path / "audit.json")))


def test_validator_requires_new_index_inside_collection(tmp_path, monkeypatch):
    collection = fake_collection(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="inside"):
        cli.build_command(parse("validate", "--collection", str(collection), "--index", str(tmp_path / "outside.h5"),
            "--output", str(tmp_path / "audit.json")))


def test_validator_builds_official_admission_command(tmp_path, monkeypatch):
    collection = fake_collection(tmp_path, monkeypatch)
    command = cli.build_command(parse("validate", "--collection", str(collection), "--index", str(collection / "checks/episode_data.hdf5"),
        "--output", str(tmp_path / "audit.json")))
    assert command[command.index("--admission-scope") + 1] == "official_collection"
    assert "--copy-data" not in command


def test_dataset_check_defaults_to_success_both_readers(tmp_path):
    index = tmp_path / "existing.hdf5"
    index.touch()
    command = cli.build_command(parse("dataset-check", "--index", str(index), "--output", str(tmp_path / "read.json")))
    assert command[command.index("--sample-filter") + 1] == "success"
    assert command[command.index("--policy") + 1] == "both"


def test_dataset_check_refuses_existing_report(tmp_path):
    index, output = tmp_path / "existing.hdf5", tmp_path / "read.json"
    index.touch()
    output.touch()
    with pytest.raises(ValueError, match="already exists"):
        cli.build_command(parse("dataset-check", "--index", str(index), "--output", str(output)))


def test_assets_include_all_hypotheses_and_explicit_frozen_selected():
    rows = cli.asset_rows()
    assert len(rows) == 35
    assert [row["asset_id"] for row in rows if row["frozen_standard_selected"]] == ["cuvette_xy_1000"]
    assert cli.asset_rows("cuvette_xy_1250")[0]["nominal_outer_xy_mm"] == [12.5, 12.5]
    with pytest.raises(ValueError, match="Unknown"):
        cli.asset_rows("not_registered")


def test_lfs_pointer_is_not_mistaken_for_real_asset(tmp_path):
    pointer = tmp_path / "x.usda"
    pointer.write_text("version https://git-lfs.github.com/spec/v1\noid sha256:x\nsize 1\n")
    assert cli.lfs_pointer(pointer)
    pointer.write_text("#usda 1.0\n")
    assert not cli.lfs_pointer(pointer)
