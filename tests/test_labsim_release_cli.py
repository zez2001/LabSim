"""CPU argv/version contracts; dry runs never initialize Isaac."""
from pathlib import Path
import tempfile
import unittest

from scripts import labsim_cli as cli


class ReleaseCLIContracts(unittest.TestCase):
    def test_current_alias_resolves_to_real_version_and_keeps_explicit_old_routes(self):
        args = cli.parser().parse_args(['doctor', '--project-version', 'current'])
        self.assertEqual(args.project_version, 'Project_release_v1')
        self.assertEqual(cli.doctor_configuration(args.project_version), cli.PROJECT_RELEASES['Project_release_v1'][1])
        for command in ('demo', 'collect', 'eval', 'serve'):
            args = cli.parser().parse_args([command, '--project-version', 'current',
                '--output', 'outputs/new-not-created', '--dry-run'])
            argv = cli.build_command(args)
            self.assertEqual(args.project_version, 'Project_release_v1')
            self.assertEqual(argv[2], 'demos.lab_cuvette_project_release_v1.launch')
            self.assertNotIn('current', argv)
        for version in ('Project_v1', 'Project_v1_1'):
            args = cli.parser().parse_args(['demo', '--project-version', version,
                '--output', 'outputs/new-not-created'])
            self.assertEqual(cli.build_command(args)[2], cli.PROJECT_RELEASES[version][0])

    def test_record_intent_is_explicit_and_not_derived_from_qualifications(self):
        for command, expected in (('demo', 'demonstration'), ('collect', 'demonstration'),
                                  ('eval', 'policy_evaluation'), ('serve', 'policy_evaluation')):
            args = cli.parser().parse_args([command, '--project-version', 'current',
                '--output', 'outputs/new-not-created'])
            argv = cli.build_command(args)
            self.assertEqual(argv[argv.index('--record-purpose') + 1], expected)
        args = cli.parser().parse_args(['eval', '--project-version', 'current', '--backend', 'teacher',
            '--record-purpose', 'resource_probe', '--output', 'outputs/new-not-created'])
        argv = cli.build_command(args)
        self.assertEqual(argv[argv.index('--record-purpose') + 1], 'resource_probe')
        for purpose in ('demonstration', 'policy_evaluation'):
            args = cli.parser().parse_args(['demo', '--project-version', 'current', '--sequence', 'early_finish',
                '--record-purpose', purpose, '--output', 'outputs/new-not-created'])
            with self.assertRaisesRegex(ValueError, 'sequence'):
                cli.build_command(args)

    def test_ordinary_teacher_cli_resolves_real_release_task_and_collector(self):
        from omegaconf import OmegaConf
        from demos.lab_cuvette_project_release_v1 import launch
        for command, mode in (('demo', 'eval'), ('collect', 'collect')):
            argv = cli.build_command(cli.parser().parse_args([command, '--project-version', 'current',
                '--backend', 'teacher', '--headless', '--output', 'outputs/new-not-created']))
            parsed = launch.parser().parse_args(argv[3:])
            cfg = OmegaConf.load(parsed.config)
            self.assertEqual(cfg.version, 'Project_release_v1')
            self.assertEqual(cfg.task_type, 'lab_cuvette_project_release_v1')
            self.assertEqual(cfg.collector_type, 'lab_cuvette_project_release_v1')
            self.assertEqual(cfg.controller_type, 'lab_cuvette_project_v1_1_teacher')
            self.assertEqual(parsed.record_mode, mode)
            self.assertEqual(parsed.record_purpose, 'demonstration')
            self.assertEqual(parsed.episodes, 1)
            self.assertNotIn('--sequence', argv)

    def test_usage_intent_does_not_change_physical_scene_fingerprint(self):
        from omegaconf import OmegaConf
        from demos.lab_cuvette_project_release_v1.contract import scene_contract
        cfg = OmegaConf.load(cli.PROJECT_RELEASES['Project_release_v1'][1])
        original = scene_contract(cfg)
        cfg.release.record_purpose = 'demonstration'
        self.assertEqual(scene_contract(cfg), original)
        cfg.release.record_purpose = 'resource_probe'
        self.assertEqual(scene_contract(cfg), original)

    def test_doctor_uses_explicit_release_config_and_refuses_conflict(self):
        args = cli.parser().parse_args(["doctor", "--project-version", "Project_release_v1", "--json"])
        selected = cli.doctor_configuration(args.project_version, args.config)
        self.assertEqual(selected, cli.PROJECT_RELEASES["Project_release_v1"][1])
        self.assertEqual(cli.doctor_configuration(), cli.PROJECT_CONFIG)
        with self.assertRaisesRegex(ValueError, "conflicts"):
            cli.doctor_configuration("Project_v1", selected)

    def test_all_release_entries_use_official_launcher(self):
        with tempfile.TemporaryDirectory() as folder:
            for command in ("demo", "collect", "eval", "serve"):
                args = cli.parser().parse_args([command, "--project-version", "Project_release_v1",
                    "--record-mode", "diagnostic", "--output", str(Path(folder) / command), "--dry-run"])
                argv = cli.build_command(args)
                self.assertEqual(argv[2], "demos.lab_cuvette_project_release_v1.launch")
                self.assertEqual(argv[argv.index("--record-mode") + 1], "diagnostic")
                self.assertFalse((Path(folder) / command).exists())

    def test_old_default_is_unchanged_and_explicit_new_modes_are_not_silently_ignored(self):
        args = cli.parser().parse_args(["demo", "--output", "outputs/new-not-created", "--dry-run"])
        self.assertEqual(args.project_version, "Project_v1")
        for version in ("Project_v1", "Project_v1_1"):
            args = cli.parser().parse_args(["demo", "--project-version", version,
                "--record-mode", "collect", "--output", "outputs/new-not-created", "--dry-run"])
            with self.assertRaisesRegex(ValueError, "Project_release_v1"):
                cli.build_command(args)

    def test_release_default_recording_is_selected_by_purpose(self):
        for purpose, mode in (("demo", "eval"), ("eval", "eval"), ("collect", "collect"), ("serve", "eval")):
            args = cli.parser().parse_args([purpose, "--project-version", "Project_release_v1",
                "--output", "outputs/new-not-created", "--dry-run"])
            argv = cli.build_command(args)
            self.assertEqual(argv[argv.index("--record-mode") + 1], mode)

    def test_sequence_uses_same_process_driver_and_precise_forwarding(self):
        args = cli.parser().parse_args(["collect", "--project-version", "Project_release_v1",
            "--sequence", "teacher", "early_finish", "teacher", "--output", "outputs/new-not-created",
            "--headless", "--dry-run"])
        argv = cli.build_command(args)
        self.assertEqual(argv[2], "demos.lab_cuvette_project_release_v1.run")
        self.assertEqual(argv[argv.index("--execution-purpose") + 1], "collect")
        self.assertEqual(argv[argv.index("--record-mode") + 1], "collect")
        self.assertEqual(argv[argv.index("--sequence") + 1:][:3], ["teacher", "early_finish", "teacher"])
        self.assertIn("--headless", argv)
        for command, version in (("serve", "Project_release_v1"), ("demo", "Project_v1"), ("eval", "Project_v1_1")):
            args = cli.parser().parse_args([command, "--project-version", version,
                "--sequence", "early_finish", "--output", "outputs/new-not-created", "--dry-run"])
            with self.assertRaisesRegex(ValueError, "sequence"):
                cli.build_command(args)

    def test_all_native_termination_cases_use_release_only_official_cli(self):
        from demos.lab_cuvette_project_release_v1.run import CONDITIONS
        requested = ["early_finish", "no_progress", "unreachable", "service_timeout", "user_interrupt"]
        declared = next(action.choices for action in cli.parser()._subparsers._group_actions[0].choices["demo"]._actions
                        if action.dest == "sequence")
        self.assertEqual(tuple(declared), tuple(CONDITIONS))
        for purpose in ("demo", "collect", "eval"):
            args = cli.parser().parse_args([purpose, "--project-version", "Project_release_v1",
                "--sequence", *requested, "--output", "outputs/new-not-created", "--headless", "--dry-run"])
            argv = cli.build_command(args)
            start = argv.index("--sequence") + 1
            self.assertEqual(argv[start:start + len(requested)], requested)
            self.assertEqual(argv[2], "demos.lab_cuvette_project_release_v1.run")
            self.assertEqual(argv[argv.index("--execution-purpose") + 1], purpose)
        for purpose, version in (("serve", "Project_release_v1"), ("demo", "Project_v1"), ("collect", "Project_v1_1")):
            args = cli.parser().parse_args([purpose, "--project-version", version,
                "--sequence", *requested, "--output", "outputs/new-not-created", "--dry-run"])
            with self.assertRaisesRegex(ValueError, "sequence"):
                cli.build_command(args)

    def test_release_index_is_identified_and_mixed_version_rejected(self):
        try:
            import h5py
        except ImportError:
            self.skipTest("H5 version detection runs in the separate normal-readers job")
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "index.h5"
            with h5py.File(path, "w") as source:
                group = source.create_group("episode0")
                group.create_dataset("actions", data=[[0.] * 8])
                group.create_dataset("agent_pose", data=[[0.] * 8])
                group.attrs["scene_version"] = "Project_release_v1"
            self.assertEqual(cli.dataset_project_version(path), "Project_release_v1")
            with h5py.File(path, "a") as source:
                group = source.create_group("episode1")
                group.create_dataset("actions", data=[[0.] * 8])
                group.create_dataset("agent_pose", data=[[0.] * 8])
                group.attrs["scene_version"] = "Project_v1_1"
            with self.assertRaisesRegex(ValueError, "mix"):
                cli.dataset_project_version(path)


if __name__ == "__main__":
    unittest.main()
