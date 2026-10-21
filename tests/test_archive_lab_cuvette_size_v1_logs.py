"""Temporary byte fixtures only; never compresses real experiment outputs."""
import gzip
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import h5py
import numpy as np

from scripts.archive_lab_cuvette_size_v1_logs import (archive_episode,
    prepare_archive, sha256, snapshot, validate_closed_episode)


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "outputs/lab_cuvette_loading/Size_v1"
        self.run = self.root / "test_fixture"
        self.episode = self.run / "episode_0000"
        (self.episode / "dataset").mkdir(parents=True)
        self.proof = self.run / "process_exit.json"
        self.proof.write_text(json.dumps(dict(run_directory=str(self.run), process_exited=True,
            exit_code=0, session_id="synthetic-cpu-fixture")))
        self.logs = {"physics_records.jsonl": (b'{"step":1,"value":0.002}\n' * 1000),
                     "native_contact_events.jsonl": b'{"force_N":0.19}\n' * 150}
        for name, content in self.logs.items():
            (self.episode / name).write_bytes(content)
        result = dict(episode_id="test-fixture", frames=3, complete=True, termination_reason="TEST_FIXTURE")
        (self.episode / "result.json").write_text(json.dumps(result))
        (self.episode / "independent_score.json").write_text(json.dumps(result))
        with h5py.File(self.episode / "dataset/episode_0000.h5", "w") as record:
            record.attrs.update(episode_id="test-fixture", complete=True, frames=3, task_success=False)
            record.create_dataset("actions", data=np.zeros((3, 8)))
        self.h5sha = sha256(self.episode / "dataset/episode_0000.h5")

    def tearDown(self):
        self.temporary.cleanup()

    def test_default_dry_run_leaves_every_byte_untouched(self):
        result = archive_episode(self.episode, self.proof, archive_root=self.root)
        self.assertTrue(result["dry_run"])
        for name, content in self.logs.items():
            self.assertEqual((self.episode / name).read_bytes(), content)
        self.assertFalse(list(self.episode.glob("*.gz")))
        self.assertFalse(list(self.episode.glob("log_archive_*.json")))

    def test_verified_lossless_archive_removes_only_two_raw_logs(self):
        result = archive_episode(self.episode, self.proof, replace=True, archive_root=self.root)
        for name, content in self.logs.items():
            self.assertFalse((self.episode / name).exists())
            with gzip.open(self.episode / (name + ".gz"), "rb") as restored:
                self.assertEqual(restored.read(), content)
        self.assertEqual(sha256(self.episode / "dataset/episode_0000.h5"), self.h5sha)
        manifest = json.loads(Path(result["archive_manifest"]).read_text())
        self.assertTrue(all(item["raw_removed"] and item["decompressed_bytes_equal_original"] for item in manifest["files"]))
        self.assertFalse(manifest["HDF5_labels_videos_modified"])

    def test_live_write_handle_blocks_archive_even_if_exit_proof_exists(self):
        with (self.episode / "physics_records.jsonl").open("ab"):
            with self.assertRaisesRegex(RuntimeError, "writers are still open"):
                archive_episode(self.episode, self.proof, replace=True, archive_root=self.root)
        self.assertTrue((self.episode / "physics_records.jsonl").is_file())

    def test_incomplete_and_other_versions_rejected(self):
        with self.assertRaisesRegex(ValueError, "Only an episode"):
            validate_closed_episode(self.episode, self.proof, archive_root=self.root / "Other")
        result = self.episode / "result.json"
        item = json.loads(result.read_text())
        item["complete"] = False
        result.write_text(json.dumps(item))
        with self.assertRaisesRegex(ValueError, "complete result"):
            archive_episode(self.episode, self.proof, archive_root=self.root)

    def test_changed_file_aborts_and_preserves_original(self):
        source = self.episode / "physics_records.jsonl"
        before = snapshot(source)
        original = source.read_bytes()
        source.write_bytes(original + b'changed\n')
        with self.assertRaisesRegex(RuntimeError, "Raw log changed"):
            prepare_archive(source, before)
        self.assertEqual(source.read_bytes(), original + b'changed\n')
        self.assertFalse(list(self.episode.glob("*.gz.pending_*")))

    def test_second_file_failure_preserves_both_originals(self):
        from scripts import archive_lab_cuvette_size_v1_logs as module
        real = module.prepare_archive
        def fail_second(path, expected):
            if path.name.startswith("native_"):
                raise RuntimeError("test injected compressor failure")
            return real(path, expected)
        with patch.object(module, "prepare_archive", side_effect=fail_second):
            with self.assertRaisesRegex(RuntimeError, "injected compressor"):
                archive_episode(self.episode, self.proof, replace=True, archive_root=self.root)
        for name, content in self.logs.items():
            self.assertEqual((self.episode / name).read_bytes(), content)
        self.assertFalse(list(self.episode.glob("*.gz*")))


if __name__ == "__main__":
    unittest.main()
