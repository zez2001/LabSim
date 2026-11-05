"""Fixed scene CLI routing and sequential suite identity; CPU protocol tests."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from demos.lab_cuvette_project_release_v1 import suite_runner
from scripts import labsim_cli as cli


def parse(command, output, *extra):
    return cli.parser().parse_args([command, "--project-version", "Project_release_v1",
        "--output", str(output), *extra])


@pytest.mark.parametrize("command", ["demo", "collect", "eval", "serve"])
def test_omitted_scene_preserves_standard_ordinary_entry(tmp_path, command):
    argv = cli.build_command(parse(command, tmp_path / command))
    assert argv[2] == "demos.lab_cuvette_project_release_v1.launch"
    assert argv[argv.index("--layout-mode") + 1] == "standard"
    assert argv[argv.index("--episodes") + 1] == ("5" if command == "eval" else "1")


@pytest.mark.parametrize("scene", ["random_001", "random_010"])
def test_random_single_eval_routes_fixed_runner(tmp_path, scene):
    argv = cli.build_command(parse("eval", tmp_path / scene, "--scene", scene, "--episodes", "2"))
    assert argv[2] == "demos.lab_cuvette_project_release_v1.suite_runner"
    assert argv[argv.index("--scene") + 1] == scene
    assert argv[argv.index("--episodes-per-scene") + 1] == "2"
    plan = suite_runner.make_plan(suite_runner.parser().parse_args(argv[3:]))
    assert plan["scene_ids"] == [scene]
    assert len(plan["episodes"]) == 2
    assert [row["scene_repetition_index"] for row in plan["episodes"]] == [0, 1]
    assert len({json.dumps(row["scene_definition"], sort_keys=True) for row in plan["episodes"]}) == 1
    assert not (tmp_path / scene).exists()


def test_random10_is_ten_fixed_scenes_with_separate_repetition_and_episode_ids(tmp_path):
    argv = cli.build_command(parse("eval", tmp_path / "suite", "--suite", "random10", "--episodes-per-scene", "2"))
    plan = suite_runner.make_plan(suite_runner.parser().parse_args(argv[3:]))
    assert plan["scene_ids"] == [f"random_{index:03d}" for index in range(1, 11)]
    assert plan["episodes_requested"] == 20
    assert [row["suite_episode_index"] for row in plan["episodes"]] == list(range(20))
    for index in range(10):
        members = plan["episodes"][index * 2:index * 2 + 2]
        assert [row["scene_repetition_index"] for row in members] == [0, 1]
        assert members[0]["scene_definition"] == members[1]["scene_definition"]
        for row in members:
            argv = row["argv"]
            assert argv[argv.index("--episodes") + 1] == "1"
            assert argv[argv.index("--record-purpose") + 1] == "policy_evaluation"


def test_conflicts_unknown_scenes_and_unintended_random_purpose_are_rejected(tmp_path):
    with pytest.raises(SystemExit):
        parse("eval", tmp_path / "x", "--scene", "standard", "--suite", "random10")
    for command in ("eval", "serve"):
        with pytest.raises(ValueError, match="Unknown scene"):
            cli.build_command(parse(command, tmp_path / "x", "--scene", "random_999"))
    for command in ("demo", "collect"):
        with pytest.raises(SystemExit):
            parse(command, tmp_path / "x", "--scene", "random_001")
    with pytest.raises(ValueError, match="policy_evaluation"):
        cli.build_command(parse("eval", tmp_path / "x", "--scene", "random_001", "--record-purpose", "demonstration"))


@pytest.mark.parametrize("extra", [["--episodes", "2"], ["--episodes-per-scene", "0"],
    ["--episodes-per-scene", "2", "--episodes", "2"]])
def test_suite_repetitions_are_explicit_and_valid(tmp_path, extra):
    with pytest.raises(ValueError):
        cli.build_command(parse("eval", tmp_path / "x", "--suite", "random10", *extra))


def test_random_serve_is_single_evaluation_scene(tmp_path):
    argv = cli.build_command(parse("serve", tmp_path / "rpc", "--scene", "random_003"))
    assert argv[2] == "demos.lab_cuvette_project_release_v1.launch"
    assert argv[argv.index("--layout-mode") + 1] == "random_003"
    assert argv[argv.index("--record-purpose") + 1] == "policy_evaluation"
    assert argv[argv.index("--episodes") + 1] == "1"


def test_old_versions_do_not_silently_run_random_as_standard(tmp_path):
    for version in ("Project_v1", "Project_v1_1"):
        args = cli.parser().parse_args(["eval", "--project-version", version,
            "--scene", "random_001", "--output", str(tmp_path / "x")])
        with pytest.raises(ValueError, match="Project_release_v1"):
            cli.build_command(args)


def test_suite_dry_run_neither_starts_process_nor_creates_files(tmp_path):
    args = suite_runner.parser().parse_args(["--suite", "random10", "--output", str(tmp_path / "suite"), "--dry-run"])
    def prohibited(*args, **kwargs):
        raise AssertionError("Dry run must not start a child process")
    result = suite_runner.run(args, process_runner=prohibited)
    assert result["episodes_requested"] == 10
    assert result["simulation_started"] is False
    assert not args.output.exists()


def test_runner_retains_failed_members_and_aggregates_standard_separately(tmp_path):
    args = suite_runner.parser().parse_args(["--suite", "random10", "--output", str(tmp_path / "suite")])
    calls = []
    def fake_process(argv, **kwargs):
        calls.append(argv)
        return SimpleNamespace(returncode=1 if len(calls) == 3 else 0)
    def inspect(output, exit_code, **kwargs):
        return dict(outcome="environment_exception" if exit_code else "full_task_success",
            task_success=exit_code == 0, record_valid=exit_code == 0,
            record_closed=exit_code == 0, process_exit_code=exit_code,
            termination_reason="CPU_PROTOCOL_FIXTURE", failure_type="CPU_PROTOCOL_FIXTURE")
    result = suite_runner.run(args, process_runner=fake_process, run_inspector=inspect)
    assert len(calls) == 10
    assert result["standard"] is None
    assert len(result["random_per_scene"]) == 10
    assert result["random_mean_full_success_rate"] == .9
    assert result["episodes"][2]["outcome"] == "environment_exception"
    assert (args.output / "suite_results.csv").is_file()
    assert (args.output / "random_003/repetition_000/suite_process_exit.json").is_file()


def test_reader_cli_requires_explicit_evaluation_use(tmp_path):
    path = tmp_path / "fixture.h5"
    path.touch()
    argv = cli.build_command(cli.parser().parse_args(["dataset-check", "--index", str(path),
        "--data-use", "evaluation", "--output", str(tmp_path / "read.json")]))
    assert argv[argv.index("--data-use") + 1] == "evaluation"


@pytest.mark.parametrize("failure,exit_code,expected", [
    ("INVALID_INITIAL_STATE", 1, "initialization_failure"),
    ("TASK_INCOMPLETE", 1, "environment_exception"),
    ("TASK_INCOMPLETE", 0, "reference_controller_failure")])
def test_inspector_distinguishes_initialization_environment_and_teacher_failures(tmp_path, failure, exit_code, expected):
    result = dict(complete=True, publication_state="complete", task_success=False,
        record_valid=True, termination_reason="CPU_CLASSIFICATION_FIXTURE", failure_type=failure)
    observed = suite_runner.classify_result(result, initialization_failure=failure == "INVALID_INITIAL_STATE",
        process_closed=exit_code == 0, complete=True, independent_outcome_matches=True)
    assert observed == expected


def test_completed_result_without_closed_h5_is_environment_exception(tmp_path):
    episode = tmp_path / "episode_0000"
    episode.mkdir()
    (episode / "result.json").write_text(json.dumps(dict(complete=True, publication_state="complete",
        task_success=True, record_valid=True)))
    (episode / "independent_score.json").write_text(json.dumps(dict(task_success=True)))
    (tmp_path / "run_manifest.json").write_text("{}")
    (tmp_path / "application_shutdown.json").write_text(json.dumps(dict(successful_cleanup_calls=True)))
    observed = suite_runner.inspect_closed_run(tmp_path, 0)
    assert observed["outcome"] == "environment_exception"
    assert not observed["reader_check"]["passed"]


def test_reset_checks_forward_to_standard_and_all_fixed_suite_members(tmp_path):
    args = parse("eval", tmp_path / "standard", "--reset-checks", "3", "--episodes", "1")
    ordinary = cli.build_command(args)
    assert ordinary[ordinary.index("--reset-checks") + 1] == "3"
    argv = cli.build_command(parse("eval", tmp_path / "suite", "--suite", "random10", "--reset-checks", "3"))
    plan = suite_runner.make_plan(suite_runner.parser().parse_args(argv[3:]))
    assert plan["reset_checks_per_formal_episode"] == 3
    assert all(row["argv"][row["argv"].index("--reset-checks") + 1] == "3" for row in plan["episodes"])


def test_reset_checks_default_is_compatible_and_invalid_values_are_rejected(tmp_path):
    assert "--reset-checks" not in cli.build_command(parse("eval", tmp_path / "standard"))
    with pytest.raises(SystemExit):
        parse("eval", tmp_path / "x", "--reset-checks", "2")
    with pytest.raises(ValueError, match="sequence"):
        cli.build_command(parse("eval", tmp_path / "x", "--reset-checks", "3", "--sequence", "teacher"))


@pytest.mark.parametrize("started", [0, 1])
def test_unstarted_random_scenes_are_unavailable_instead_of_false_failures(tmp_path, started):
    args = suite_runner.parser().parse_args(["--suite", "random10", "--output", str(tmp_path / "suite")])
    plan = suite_runner.make_plan(args)
    rows = [dict(scene_id="random_001", outcome="full_task_success", record_closed=True)] if started else []
    result = suite_runner.summarize(plan, rows)
    assert result["random_mean_full_success_rate"] is None
    assert result["random_coverage"]["started_scene_count"] == started
    assert result["random_coverage"]["complete"] is False
    assert result["observed_random_scene_mean_full_success_rate"] == (1. if started else None)
    for row in result["random_per_scene"][started:]:
        assert row["started"] == 0
        assert row["full_success_rate"] is None
        assert row["observed_full_success_rate"] is None
        assert row["outcome_counts"]["reference_controller_failure"] == 0


def test_partial_repetitions_do_not_publish_a_fixed_denominator_success_rate(tmp_path):
    args = suite_runner.parser().parse_args(["--scene", "random_001", "--episodes-per-scene", "2",
        "--output", str(tmp_path / "single")])
    result = suite_runner.summarize(suite_runner.make_plan(args), [dict(scene_id="random_001",
        outcome="full_task_success", record_closed=True)])
    row = result["random_per_scene"][0]
    assert (row["requested"], row["started"], row["not_started"]) == (2, 1, 1)
    assert row["full_success_rate"] is None
    assert row["observed_full_success_rate"] == 1.
    assert result["random_mean_full_success_rate"] is None


# Actual 20261105_165005 payload projection; the complete historical traceback
# is retained here so this regression has no runtime dependency on outputs/.
def _actual_scene_initialization_failure():
    return {'type': 'SceneInitializationError',
     'error': 'Configured scene differs from authored assembly; see '
              'authored_scene_validation.json',
     'traceback': 'Traceback (most recent call last):\n'
                  '  File '
                  '"/home/wujing/Desktop/vla/LabSim-projectization/demos/lab_cuvette_project_release_v1/launch.py", '
                  'line 198, in main\n'
                  "    facade.reset(args.seed + index, dict(mode='standard', teacher=args.backend "
                  "== 'teacher',\n"
                  '  File '
                  '"/home/wujing/Desktop/vla/LabSim-projectization/demos/lab_cuvette_project_release_v1/environment.py", '
                  'line 8, in reset\n'
                  '    observation = super().reset(*args, **kwargs)\n'
                  '                  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^\n'
                  '  File '
                  '"/home/wujing/Desktop/vla/LabSim-projectization/demos/lab_cuvette_project_v1_1/environment.py", '
                  'line 15, in reset\n'
                  '    result=super().reset(*args,**kwargs)\n'
                  '           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^\n'
                  '  File '
                  '"/home/wujing/Desktop/vla/LabSim-projectization/demos/lab_cuvette_project_v1/environment.py", '
                  'line 49, in reset\n'
                  "    self.task.reset(seed, options or dict(mode='standard', "
                  "policy_id='external'))\n"
                  '  File '
                  '"/home/wujing/Desktop/vla/LabSim-projectization/tasks/lab_cuvette_loading_project_release.py", '
                  'line 219, in reset\n'
                  '    return super().reset(*args, **kwargs)\n'
                  '           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^\n'
                  '  File '
                  '"/home/wujing/Desktop/vla/LabSim-projectization/tasks/lab_cuvette_loading_project_v1.py", '
                  'line 44, in reset\n'
                  '    return super().reset(seed, options)\n'
                  '           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^\n'
                  '  File '
                  '"/home/wujing/Desktop/vla/LabSim-projectization/tasks/lab_cuvette_loading_env_v1.py", '
                  'line 48, in reset\n'
                  '    try:return self._reset(seed,options)\n'
                  '               ^^^^^^^^^^^^^^^^^^^^^^^^^\n'
                  '  File '
                  '"/home/wujing/Desktop/vla/LabSim-projectization/tasks/lab_cuvette_loading_project_release.py", '
                  'line 66, in _reset\n'
                  '    observation, info = super()._reset(seed, options)\n'
                  '                        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^\n'
                  '  File '
                  '"/home/wujing/Desktop/vla/LabSim-projectization/tasks/lab_cuvette_loading_project_v1_1.py", '
                  'line 46, in _reset\n'
                  '    observation,info=super()._reset(seed,options)\n'
                  '                     ^^^^^^^^^^^^^^^^^^^^^^^^^^^^\n'
                  '  File '
                  '"/home/wujing/Desktop/vla/LabSim-projectization/tasks/lab_cuvette_loading_project_v1.py", '
                  'line 47, in _reset\n'
                  '    observation, info = super()._reset(seed, options)\n'
                  '                        ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^\n'
                  '  File '
                  '"/home/wujing/Desktop/vla/LabSim-projectization/tasks/lab_cuvette_loading_env_v1.py", '
                  'line 61, in _reset\n'
                  '    '
                  'self.ctx=build_context(self.cfg,self.app,self.episode_dir,self.initial_state)\n'
                  '    ^^^^^^^^\n'
                  '  File '
                  '"/home/wujing/Desktop/vla/LabSim-projectization/tasks/lab_cuvette_loading_project_release.py", '
                  'line 53, in __setattr__\n'
                  '    configure_context(self, value)\n'
                  '  File '
                  '"/home/wujing/Desktop/vla/LabSim-projectization/demos/lab_cuvette_project_release_v1/scene_validation.py", '
                  'line 256, in configure_context\n'
                  "    raise SceneInitializationError('Configured scene differs from authored "
                  "assembly; see authored_scene_validation.json')\n"
                  'demos.lab_cuvette_project_release_v1.scene_validation.SceneInitializationError: '
                  'Configured scene differs from authored assembly; see '
                  'authored_scene_validation.json\n'}


def _historical_unbound_initialization_receipt():
    return {'record_valid': False,
     'task_success': None,
     'failure_type': 'INITIALIZATION_INVALID',
     'error_type': 'SceneInitializationError',
     'error': 'Configured scene differs from authored assembly; see '
              'authored_scene_validation.json',
     'episode_id': 'bcdbacc9-3359-42b2-8fc1-7ba65cbbc5ca',
     'physical_attempt_qualified': False}


def test_actual_scene_initialization_exception_without_message_keywords(tmp_path):
    payload = _actual_scene_initialization_failure()
    assert "initial" not in payload["error"].lower()
    assert "geometry precheck" not in payload["error"].lower()
    (tmp_path / "runner_failure.json").write_text(json.dumps(payload))
    observed = suite_runner.inspect_closed_run(tmp_path, 1)
    assert observed["outcome"] == "initialization_failure"
    assert observed["failure_type"] == "UNKNOWN"  # Missing raw result is preserved.
    assert observed["termination_reason"] == "NO_COMPLETED_EPISODE"


@pytest.mark.parametrize("error_type,message", [
    ("RuntimeError", "initial buffer allocation failed"),
    ("RuntimeError", "geometry precheck text alone is insufficient"),
    ("ReferenceControlError", "Configured scene differs from authored assembly"),
    ("NotSceneInitializationError", "CPU fixture"),
])
def test_ordinary_environment_error_is_not_initialization_by_message(tmp_path, error_type, message):
    (tmp_path / "runner_failure.json").write_text(json.dumps(dict(type=error_type, error=message)))
    assert suite_runner.inspect_closed_run(tmp_path, 1)["outcome"] == "environment_exception"


@pytest.mark.parametrize("relative", ["episode_0000", "episode_notes", "episode_0001",
    "reset_validation/episode_0000"])
@pytest.mark.parametrize("ordinary_runner_failure", [False, True])
def test_unbound_receipt_does_not_override_ordinary_environment_failure(tmp_path, relative, ordinary_runner_failure):
    episode = tmp_path / relative
    episode.mkdir(parents=True)
    # A correctly formatted UUID in this sidecar alone does not bind it to
    # the current run; generic reset exceptions can produce the same flags.
    (episode / "initialization_failure.json").write_text(json.dumps(_historical_unbound_initialization_receipt()))
    if ordinary_runner_failure:
        (tmp_path / "runner_failure.json").write_text(json.dumps(dict(type="RuntimeError", error="render failed")))
    assert suite_runner.inspect_closed_run(tmp_path, 1)["outcome"] == "environment_exception"


def test_episode_directory_alone_is_not_initialization_evidence(tmp_path):
    (tmp_path / "episode_0000").mkdir()
    assert suite_runner.inspect_closed_run(tmp_path, 1)["outcome"] == "environment_exception"


@pytest.mark.parametrize("text", ["{", "[]", "null", '"unexpected"',
    '{"type": []}', '{"type": {}}', '{"type": null}'])
def test_bad_or_nonmapping_runner_failure_is_environment_exception(tmp_path, text):
    (tmp_path / "runner_failure.json").write_text(text)
    assert suite_runner.inspect_closed_run(tmp_path, 1)["outcome"] == "environment_exception"


@pytest.mark.parametrize("text", ["{", "[]", "null", '{}',
    '{"failure_type":"INITIALIZATION_INVALID"}'])
def test_bad_or_partial_initialization_sidecar_is_not_positive_evidence(tmp_path, text):
    episode = tmp_path / "episode_0000"
    episode.mkdir()
    (episode / "initialization_failure.json").write_text(text)
    assert suite_runner.inspect_closed_run(tmp_path, 1)["outcome"] == "environment_exception"


@pytest.mark.parametrize("episode_count", [1, 2])
def test_initialization_exception_does_not_override_existing_or_ambiguous_results(tmp_path, episode_count):
    for index in range(episode_count):
        episode = tmp_path / f"episode_{index:04d}"
        episode.mkdir()
        (episode / "result.json").write_text(json.dumps(dict(failure_type="SAFETY_COLLISION",
            termination_reason="ROBOT_ENVIRONMENT_COLLISION", task_success=False, record_valid=True)))
    (tmp_path / "runner_failure.json").write_text(json.dumps(_actual_scene_initialization_failure()))
    observed = suite_runner.inspect_closed_run(tmp_path, 1)
    assert observed["outcome"] == "environment_exception"
    if episode_count == 1:
        assert observed["failure_type"] == "SAFETY_COLLISION"
        assert observed["termination_reason"] == "ROBOT_ENVIRONMENT_COLLISION"


def test_structured_result_initialization_label_remains_authoritative(tmp_path):
    episode = tmp_path / "episode_0000"
    episode.mkdir()
    (episode / "result.json").write_text(json.dumps(dict(failure_type="INITIALIZATION_INVALID",
        task_success=None, record_valid=False)))
    assert suite_runner.inspect_closed_run(tmp_path, 1)["outcome"] == "initialization_failure"
