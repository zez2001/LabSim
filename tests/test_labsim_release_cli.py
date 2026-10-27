"""CPU argv/version contracts; dry runs never initialize Isaac."""
from pathlib import Path
import tempfile
import unittest

from scripts import labsim_cli as cli


class ReleaseCLIContracts(unittest.TestCase):
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
