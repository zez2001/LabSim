"""CPU-only launcher, budget routing and shutdown behavior; no Isaac is loaded."""
import ast
import json
from pathlib import Path
import subprocess
import sys
from types import ModuleType, SimpleNamespace

import pytest
from omegaconf import OmegaConf

from demos.lab_cuvette_project_v1_1 import run
from scripts import labsim_cli as cli


def test_help_is_a_successful_cpu_subprocess_and_exposes_diagnostics():
    result = subprocess.run([sys.executable, "-m", "demos.lab_cuvette_project_v1_1.run", "--help"],
        cwd=cli.ROOT, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    assert "teacher,gpt6,rpc,diagnostic" in result.stdout
    assert "--probe" in result.stdout
    assert all(probe in result.stdout for probe in ("fixed-replay", "free-space", "grasp-transport"))
    assert "--attempts" in result.stdout
    assert "Traceback" not in result.stderr


def test_default_budget_is_the_existing_shared_ledger_and_provider_is_new_version(tmp_path):
    args = run.parser().parse_args(["--output", str(tmp_path / "unused"), "--backend", "gpt6"])
    assert args.provider_config == cli.ROOT / "config/lab_cuvette_loading/Project_v1_1/policies/cubence_gpt6.json"
    assert args.budget_ledger == cli.ROOT / "outputs/lab_cuvette_loading/Project_v1/cubence_budget.json"
    assert not (tmp_path / "unused").exists()


@pytest.mark.parametrize("command", ["demo", "eval"])
def test_cli_does_not_override_module_default_provider_or_shared_budget(tmp_path, command):
    args = cli.parser().parse_args([command, "--project-version", "Project_v1_1", "--backend", "gpt6",
        "--output", str(tmp_path / "unused")])
    assert args.provider_config is None and args.budget_ledger is None
    argv = cli.build_command(args)
    assert "--provider-config" not in argv and "--budget-ledger" not in argv
    module_args = run.parser().parse_args(argv[3:])
    assert module_args.budget_ledger == cli.ROOT / "outputs/lab_cuvette_loading/Project_v1/cubence_budget.json"
    assert module_args.provider_config.parent.parent.name == "Project_v1_1"


@pytest.mark.parametrize("probe,attempts", [("fixed-replay", [1, 2]), ("free-space", [0]),
    ("pose-hold", [0]), ("grasp-transport", [0])])
def test_diagnostic_mode_and_probe_selection_are_explicit(tmp_path, probe, attempts):
    args = run.parser().parse_args(["--backend", "diagnostic", "--probe", probe,
        "--attempts", *map(str, attempts), "--output", str(tmp_path / "unused")])
    assert args.backend == "diagnostic" and args.probe == probe and args.attempts == attempts
    default = run.parser().parse_args(["--output", str(tmp_path / "default")])
    assert default.backend == "teacher"


def module(**values):
    value = ModuleType("cpu_launcher_stub")
    value.__dict__.update(values)
    return value


@pytest.fixture
def cpu_lifecycle(monkeypatch):
    events = []
    cfg = OmegaConf.create(dict(asset_id="cuvette_xy_1000", task_type="CPU_STUB",
        experiment=dict(condition_group="natural"), env=dict(execution_purpose="eval")))
    task = SimpleNamespace(cfg=cfg)
    task.close = lambda: events.append("env.close")
    app = SimpleNamespace(close=lambda: events.append("app.close"))
    lock = SimpleNamespace(close=lambda: events.append("lock.close"))
    def simulation_app(settings):
        events.append("app.create")
        assert settings["fast_shutdown"] is False
        return app
    def create_task(*args, **kwargs):
        events.append("env.create")
        return task
    monkeypatch.setattr(run, "resolve_config", lambda value, **kwargs: cfg)
    monkeypatch.setattr(run, "ensure_audit", lambda *args: dict(geometry_valid=True))
    monkeypatch.setattr(run, "open", lambda *args: lock, raising=False)
    monkeypatch.setattr(run.fcntl, "flock", lambda *args: None)
    monkeypatch.setitem(sys.modules, "isaacsim", module(SimulationApp=simulation_app))
    monkeypatch.setitem(sys.modules, "factories.task_factory", module(create_task=create_task))
    monkeypatch.setitem(sys.modules, "factories.controller_factory", module(create_controller=lambda *args: None))
    monkeypatch.setitem(sys.modules, "demos.lab_cuvette_project_v1_1.environment",
        module(ProjectEnvironment=lambda env: SimpleNamespace(task=env)))
    monkeypatch.setitem(sys.modules, "omni.kit.app",
        module(get_app=lambda: SimpleNamespace(post_quit=lambda code: events.append("app.post_quit"))))
    return SimpleNamespace(events=events, task=task, cfg=cfg)


def test_diagnostic_return_waits_for_environment_application_and_lock_close(tmp_path, monkeypatch, cpu_lifecycle):
    seen = []
    def probes(facade, mode, attempts, output):
        seen.append((facade.task, mode, attempts, output))
        return 7  # A CPU stub return code, not a physical task outcome.
    monkeypatch.setitem(sys.modules, "demos.lab_cuvette_project_v1_1.probes", module(run_probes=probes))
    output = tmp_path / "diagnostic"
    assert run.main(["--backend", "diagnostic", "--probe", "free-space", "--output", str(output)]) == 7
    assert seen == [(cpu_lifecycle.task, "free-space", [1, 2], output)]
    assert cpu_lifecycle.cfg.experiment.condition_group == "control_diagnostic"
    assert cpu_lifecycle.events == ["app.create", "env.create", "env.close", "app.post_quit", "app.close", "lock.close"]


def test_run_failure_is_recorded_and_still_closes_environment_application_and_lock(tmp_path, monkeypatch, cpu_lifecycle):
    def fail(*args):
        raise RuntimeError("CPU_STUB_FAILURE")
    monkeypatch.setitem(sys.modules, "demos.lab_cuvette_project_v1_1.probes", module(run_probes=fail))
    output = tmp_path / "diagnostic_failure"
    with pytest.raises(RuntimeError, match="CPU_STUB_FAILURE"):
        run.main(["--backend", "diagnostic", "--output", str(output)])
    evidence = json.loads((output / "runner_failure.json").read_text())
    assert evidence["type"] == "RuntimeError" and evidence["error"] == "CPU_STUB_FAILURE"
    assert cpu_lifecycle.events[-4:] == ["env.close", "app.post_quit", "app.close", "lock.close"]


@pytest.mark.parametrize("body,expected", [("return 0", 0), ("return 7", 7),
    ("raise RuntimeError('CPU_STUB_FAILURE')", 1), ("raise SystemExit(0)", 0), ("raise SystemExit(2)", 2)])
def test_native_exit_wrapper_preserves_return_error_and_argparse_codes(body, expected):
    # Execute only the real __main__ guard in a child process. Do not import
    # the launcher or simulator there; main is a deliberately tiny CPU stub.
    source = Path(run.__file__).read_text()
    tree = ast.parse(source)
    guard = tree.body[-1]
    assert isinstance(guard, ast.If)
    wrapper = ast.unparse(ast.Module(body=[guard], type_ignores=[]))
    program = "import sys\ndef main():\n    print('CPU_EXIT_WRAPPER')\n    " + body + "\n" + wrapper
    result = subprocess.run([sys.executable, "-c", program], capture_output=True, text=True, timeout=15)
    assert result.returncode == expected, result.stderr
    assert "CPU_EXIT_WRAPPER" in result.stdout
