"""Small adversarial fixtures for archive restore without project payloads."""
import hashlib
import json
from pathlib import Path
import stat
import tempfile
import unittest
import warnings
import zipfile

from scripts import restore_history_archive as tool


class RestoreHistoryArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.archive = self.root / "fixture.zip"

    def fixture(self, members=None):
        members = [("docs/old/report.docx", b"original bytes")] if members is None else members
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with zipfile.ZipFile(self.archive, "w") as archive:
                for name, data in members:
                    archive.writestr(name, data)
        manifest = {
            "schema": "labsim.historical_archive.v1", "baseline_commit": "1" * 40,
            "archive": {"size_bytes": self.archive.stat().st_size,
                        "sha256": hashlib.sha256(self.archive.read_bytes()).hexdigest()},
            "files": [{"path": name.filename if isinstance(name, zipfile.ZipInfo) else name,
                       "size_bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
                      for name, data in members],
        }
        path = self.root / "manifest.json"
        path.write_text(json.dumps(manifest))
        return path, manifest

    def test_verify_and_restore_exact_bytes_without_overwrite(self):
        path, _ = self.fixture()
        manifest = tool.load_manifest(path)
        destination = self.root / "restored"
        result = tool.restore(self.archive, manifest, destination)
        self.assertTrue(result["verified"])
        self.assertEqual((destination / "docs/old/report.docx").read_bytes(), b"original bytes")
        with self.assertRaises(FileExistsError):
            tool.restore(self.archive, manifest, destination)

    def test_reject_traversal_absolute_backslash_and_git_paths(self):
        for name in ("../outside", "/tmp/outside", "docs/../outside", "docs//file",
                     "docs\\outside", ".git/config", "docs/.GIT/config", "C:/outside"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                tool.safe_name(name)

    def test_reject_symlink_member_before_creating_destination(self):
        member = zipfile.ZipInfo("docs/link")
        member.create_system = 3
        member.external_attr = (stat.S_IFLNK | 0o777) << 16
        path, _ = self.fixture([(member, b"/tmp/target")])
        destination = self.root / "rejected"
        with self.assertRaises(ValueError):
            tool.restore(self.archive, tool.load_manifest(path), destination)
        self.assertFalse(destination.exists())

    def test_reject_missing_extra_and_duplicate_zip_members(self):
        for members in ([("one", b"a")], [("one", b"a"), ("two", b"b")],
                        [("one", b"a"), ("one", b"a")]):
            with self.subTest(members=members):
                _, manifest = self.fixture(members)
                manifest["files"] = [{"path": "expected", "size_bytes": 1,
                                      "sha256": hashlib.sha256(b"a").hexdigest()}]
                with self.assertRaises(ValueError):
                    tool.verify(self.archive, manifest)

    def test_reject_corrupt_archive_and_wrong_content_hash(self):
        path, manifest = self.fixture()
        manifest["files"][0]["sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            tool.verify(self.archive, manifest)
        manifest = tool.load_manifest(path)
        self.archive.write_bytes(self.archive.read_bytes() + b"changed")
        with self.assertRaises(ValueError):
            tool.verify(self.archive, manifest)

    def test_reject_duplicate_manifest_keys_or_paths(self):
        path, manifest = self.fixture()
        path.write_text('{"schema":"one","schema":"two"}')
        with self.assertRaises(ValueError):
            tool.load_manifest(path)
        manifest["files"].append(manifest["files"][0])
        path.write_text(json.dumps(manifest))
        with self.assertRaises(ValueError):
            tool.load_manifest(path)

    def test_reject_destination_symlink_and_git_worktree(self):
        path, _ = self.fixture()
        manifest = tool.load_manifest(path)
        (self.root / "link").symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ValueError):
            tool.restore(self.archive, manifest, self.root / "link/new")
        repository = self.root / "repository"
        repository.mkdir()
        (repository / ".git").write_text("gitdir: elsewhere\n")
        with self.assertRaises(ValueError):
            tool.restore(self.archive, manifest, repository / "new")
        self.assertEqual(list(repository.iterdir()), [repository / ".git"])


if __name__ == "__main__":
    unittest.main()
