"""Missing evidence and diagnostics never become physical failures or quotas."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts.summarize_lab_cuvette_size_v1 import (
    DEFAULT_GEOMETRY, candidate_table, scan_runs, summarize, launch_only_attempts)


class SummaryTests(unittest.TestCase):
    def episode(self, root, name, *, outcome=None, complete=False, policy='teacher', ident=None):
        p = Path(root) / name / 'episode_0000'
        p.mkdir(parents=True)
        (p / 'config.yaml').write_text('version: Size_v1\nasset_id: cuvette_xy_1000\nenv:\n  task_type: loading\n  mode: standard\n  scene_randomization_enabled: false\nexperiment:\n  condition_group: natural\n')
        (p / 'options.json').write_text(json.dumps({'policy_id': policy, 'subtask': 'loading'}))
        if complete:
            (p / 'result.json').write_text(json.dumps({'episode_id': ident or name,
                'task_type': 'loading', 'complete': True, 'task_success': outcome,
                'record_valid': True, 'failure_type': 'NONE' if outcome else 'GRASP_SLIP',
                'actual_control_steps': 200, 'actual_physics_steps': 800}))
        return p

    def test_unclosed_episode_never_reads_live_H5_or_fills_unknowns(self):
        with tempfile.TemporaryDirectory() as d:
            self.episode(d, 'preview01', policy='preview')
            with patch('scripts.summarize_lab_cuvette_size_v1.read_closed_h5_metadata', side_effect=AssertionError('live H5 read')):
                rows, _ = scan_runs(d, [])
            self.assertIsNone(rows[0]['task_success'])
            self.assertIsNone(rows[0]['actual_physics_steps'])
            self.assertIn('preview_or_interface_diagnostic', rows[0]['qualification_exclusions'])
            self.assertIsNone(rows[0]['qualified_failure'])

    def test_uncertified_path_is_unknown_not_failed(self):
        rows = candidate_table(DEFAULT_GEOMETRY, [])
        candidate = next(r for r in rows if r['asset_id'] == 'cuvette_xy_1090')
        self.assertIsNone(candidate['full_path_feasible'])
        self.assertFalse(candidate['conservative_full_path_certificate_present'])
        self.assertIsNone(candidate['physics_validation'])
        self.assertIsNone(candidate['complete_task_result'])

    def test_duplicate_closed_episode_is_not_counted_twice_as_qualified(self):
        with tempfile.TemporaryDirectory() as d:
            self.episode(d, 'first', outcome=False, complete=True, ident='same')
            self.episode(d, 'copy', outcome=False, complete=True, ident='same')
            rows, _ = scan_runs(d, [])
            self.assertEqual(sum(r['duplicate_of'] is not None for r in rows), 1)
            self.assertEqual(sum('duplicate_episode_id' in r['qualification_exclusions'] for r in rows), 1)

    def test_new_directory_only_and_explicit_standard5_selection(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / 'runs'
            self.episode(root, 'dev01', outcome=True, complete=True)
            self.episode(root, 'fixed5_01', outcome=True, complete=True)
            target = Path(d) / 'summary'
            result = summarize(root, DEFAULT_GEOMETRY, target, verification_prefixes=['fixed5_'])
            self.assertEqual(result['standard5']['selected_episode_count'], 1)
            self.assertIsNone(result['standard5']['all_five_successful'])
            self.assertIsNone(result['collection20_success20_failure']['qualified_success_count'])
            with self.assertRaises(FileExistsError):
                summarize(root, DEFAULT_GEOMETRY, target)

    def test_launch_without_episode_is_not_invented_task_failure(self):
        with tempfile.TemporaryDirectory() as d:
            launch = Path(d) / 'startup01'
            launch.mkdir()
            (launch / 'launch_config.yaml').write_text('asset_id: cuvette_xy_1000\n')
            rows = launch_only_attempts(d, [], [])
            self.assertEqual(len(rows), 1)
            self.assertIsNone(rows[0]['task_success'])
            self.assertIsNone(rows[0]['actual_physics_steps'])
            self.assertFalse(rows[0]['counts_as_task_failure'])

    def test_nested_official_verify_prefix_selects_only_verification_runs(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / 'runs'
            self.episode(root, 'collection_standard/runs/verify5_batch_00', outcome=True, complete=True)
            self.episode(root, 'collection_standard/runs/verify5_batch_01', outcome=True, complete=True)
            self.episode(root, 'collection_standard/runs/success_batch_02', outcome=True, complete=True)
            self.episode(root, 'collection_standard/runs/controlled_failure_batch_03', outcome=False, complete=True)
            self.episode(root, 'collection_standard/runs/notverify5_batch_04', outcome=False, complete=True)
            result = summarize(root, DEFAULT_GEOMETRY, Path(d) / 'summary',
                               verification_prefixes=['verify5_'])
            self.assertEqual(result['standard5']['selected_episode_count'], 2)
            self.assertEqual(result['standard5']['independently_scored_success_count'], 2)
            self.assertEqual(result['standard5']['independently_scored_failure_count'], 0)
            self.assertTrue(all('/verify5_' in name for name in result['standard5']['episodes']))


if __name__ == '__main__':
    unittest.main()
