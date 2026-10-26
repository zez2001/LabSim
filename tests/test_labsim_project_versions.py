"""Public CLI version selection; these checks never import Isaac or start a run."""
import json

import pytest

from scripts import labsim_cli as cli


@pytest.mark.parametrize("command", ["demo", "eval", "collect", "serve"])
def test_new_version_routes_every_execution_entry_to_its_own_module_and_config(tmp_path, command):
    output = tmp_path / command
    args = cli.parser().parse_args([command, "--project-version", "Project_v1_1", "--output", str(output)])
    argv = cli.build_command(args)
    assert argv[argv.index("-m") + 1] == "demos.lab_cuvette_project_v1_1.run"
    assert argv[argv.index("--config") + 1] == str(cli.ROOT / "config/lab_cuvette_loading/Project_v1_1/standard.yaml")
    assert argv[argv.index("--execution-purpose") + 1] == ("eval" if command == "serve" else command)
    assert argv[argv.index("--backend") + 1] == ("rpc" if command == "serve" else "teacher")
    assert argv[argv.index("--layout-mode") + 1] == "standard"
    assert not output.exists()


@pytest.mark.parametrize("command", ["demo", "eval", "collect", "serve"])
def test_omitting_version_preserves_legacy_project_argv(tmp_path, command):
    base = [command, "--output", str(tmp_path / command)]
    default = cli.build_command(cli.parser().parse_args(base))
    explicit = cli.build_command(cli.parser().parse_args(base + ["--project-version", "Project_v1"]))
    assert default == explicit
    assert default[default.index("-m") + 1] == "demos.lab_cuvette_project_v1.run"


def test_new_version_refuses_historical_collection_phase_instead_of_ignoring_version():
    args = cli.parser().parse_args(["collect", "--project-version", "Project_v1_1", "--phase", "verify5",
        "--collection", "outputs/lab_cuvette_loading/Size_v1/unused"])
    with pytest.raises(ValueError, match="Historical --phase"):
        cli.build_command(args)


def test_new_version_dry_run_is_reviewable_without_creating_output(tmp_path, capsys):
    output = tmp_path / "new run"
    assert cli.main(["demo", "--project-version", "Project_v1_1", "--backend", "gpt6", "--headless",
        "--output", str(output), "--dry-run"]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["simulation_started"] is False and plan["files_created"] is False
    assert "demos.lab_cuvette_project_v1_1.run" in plan["argv"]
    assert plan["argv"][plan["argv"].index("--backend") + 1] == "gpt6"
    assert "--headless" in plan["argv"]
    assert not output.exists()


def test_unknown_project_version_is_rejected_by_parser(tmp_path):
    with pytest.raises(SystemExit):
        cli.parser().parse_args(["demo", "--project-version", "Project_v999", "--output", str(tmp_path / "new")])
