"""Isolated, CPU-only Git fixtures for the incremental submission guard."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from scripts import check_repository_changes as guard

PASSWORD_FIELD = 'pass' + 'word'
API_FIELD = 'api' + '_key'


class RepositoryHygieneTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='labsim-hygiene-test-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.git('init', '-q')
        self.write('.gitignore', 'outputs/\nresults/\n*.log\n')
        self.write('README.md', '# Start\n\nInitial guide.\n')
        self.write('docs/results/frozen.json', '{"historical": true}\n')
        self.write('docs/old.mp4', b'x' * 5000)
        self.write('data/existing.bin', b'x' * 5000)
        self.write('config/legacy.json', json.dumps({'local': '/home/' + 'legacy/old-model',
                                                 API_FIELD: 'previous-credential-value'}))
        self.git('add', '-f', '.')
        self.commit()
        self.anchor = self.git('rev-parse', 'HEAD').strip()
        self.legacy = {'docs/results/frozen.json'}
        self.policy = dict(baseline_commit=self.anchor, new_file_max_bytes=4096,
                           text_scan_max_bytes=2 * 1024 * 1024,
                           current_markdown=['*.md', 'docs/development/*.md'],
                           exceptions=[dict(path='tests/fixtures/repository_hygiene/sample_episode.h5',
                                            purpose='Deterministic reader fixture', max_bytes=64),
                                       dict(path='docs/assets/project-thumbnail.png',
                                            purpose='Curated navigation thumbnail', max_bytes=64),
                                       dict(path='assets/formal.usda', purpose='Formal scene input', max_bytes=8192),
                                       dict(path='docs/showcase/demo.mp4', purpose='Curated showcase', max_bytes=64)])

    def git(self, *args):
        result = subprocess.run(['git', *args], cwd=self.root, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                check=True, text=True)
        return result.stdout

    def write(self, name, value):
        target = self.root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(value if isinstance(value, bytes) else value.encode())

    def stage(self, *names):
        self.git('add', '-f', '--', *names)

    def commit(self):
        self.git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                 '-c', 'commit.gpgsign=false', 'commit', '-qm', 'fixture')

    def check(self, **kwargs):
        return guard.check(self.root, policy=self.policy, legacy=self.legacy, **kwargs)

    def codes(self, result):
        return {e['code'] for e in result['errors']}

    def test_unchanged_baseline_and_first_push_do_not_scan_history(self):
        base = guard.ci_comparison_base(self.root, '0' * 40, self.anchor, self.anchor)
        report = self.check(base=base, head=self.anchor)
        self.assertTrue(report['passed'])
        self.assertEqual(report['changed_file_count'], 0)
        self.assertEqual(report['baseline_ignored_count'], 1)
        self.assertEqual(self.check()['changed_file_count'], 0)

    def test_generated_outputs_and_force_added_ignored_path_are_blocked(self):
        names = ['outputs/new/summary.json', 'docs/episode.mp4', 'docs/report.docx',
                 'docs/results_bundle.zip', 'data/trajectory.h5', 'policy/new.ckpt']
        for name in names:
            self.write(name, 'new runtime output')
        self.stage(*names)
        report = self.check()
        blocked = {e['path'] for e in report['errors'] if e['code'] == 'generated_runtime_output'}
        self.assertEqual(blocked, set(names))
        self.assertIn('new_tracked_ignored_path', self.codes(report))

    def test_modified_recording_is_blocked_but_unchanged_recording_is_not(self):
        self.write('docs/old.mp4', b'y' * 5000)
        self.stage('docs/old.mp4')
        self.assertEqual(self.codes(self.check()), {'generated_runtime_output'})

    def test_narrow_purpose_and_size_bound_exceptions(self):
        for row in self.policy['exceptions']:
            self.write(row['path'], b'x' * (5000 if row['path'].endswith('.usda') else 32))
            self.stage(row['path'])
        self.assertTrue(self.check()['passed'])
        self.write('tests/fixtures/repository_hygiene/sample_episode.h5', b'x' * 65)
        self.stage('tests/fixtures/repository_hygiene/sample_episode.h5')
        self.assertIn('exception_size_exceeded', self.codes(self.check()))
        self.write('tests/fixtures/repository_hygiene/another_episode.h5', b'x')
        self.stage('tests/fixtures/repository_hygiene/another_episode.h5')
        self.assertIn('generated_runtime_output', self.codes(self.check()))

    def test_new_large_git_blob_and_lfs_declared_size_are_distinct(self):
        self.write('data/new.bin', b'x' * 4097)
        self.write('assets/new.usd', 'version https://git-lfs.github.com/spec/v1\noid sha256:' + 'a' * 64 + '\nsize 9999999\n')
        self.stage('data/new.bin', 'assets/new.usd')
        report = self.check()
        self.assertEqual(sum(e['code'] == 'new_large_file' for e in report['errors']), 2)
        pointer = next(row for row in report['files'] if row['path'] == 'assets/new.usd')
        self.assertTrue(pointer['lfs_pointer'])
        self.assertLess(pointer['blob_bytes'], 200)
        self.assertEqual(pointer['effective_bytes'], 9999999)

    def test_preexisting_large_file_shrink_passes_growth_is_blocked(self):
        self.write('data/existing.bin', b'y' * 4999)
        self.stage('data/existing.bin')
        self.assertTrue(self.check()['passed'])
        self.write('data/existing.bin', b'y' * 5001)
        self.stage('data/existing.bin')
        self.assertIn('new_large_file', self.codes(self.check()))

    def test_new_ignore_rule_does_not_expand_frozen_membership(self):
        self.write('.gitignore', 'outputs/\nresults/\n*.log\n*.csv\n')
        self.write('data/new.csv', 'value\n1\n')
        self.stage('.gitignore', 'data/new.csv')
        report = self.check()
        self.assertIn('new_tracked_ignored_path', self.codes(report))
        self.assertFalse(any(e.get('path') == 'docs/results/frozen.json' for e in report['errors']))

    def test_legacy_membership_requires_baseline_ignored_status(self):
        with self.assertRaises(guard.GuardError):
            guard.check(self.root, policy=self.policy, legacy=self.legacy | {'README.md'})

    def test_source_inputs_json_csv_usd_and_environment_placeholders_are_valid(self):
        values = {'config/valid.json': '{"api_key":"${LABSIM_API_KEY}","asset":"assets/formal.usda"}\n',
                  'data/input.csv': 'name,value\nfixture,1\n',
                  'assets/input.usda': '#usda 1.0\ndef Xform "Fixture" {}\n'}
        for name, value in values.items():
            self.write(name, value)
        self.stage(*values)
        self.assertTrue(self.check()['passed'])

    def test_added_tokens_inline_secrets_and_private_config_paths_are_redacted(self):
        token = 'sk-' + 'a' * 30
        hf_token = 'hf_' + 'b' * 30
        private = '/home/' + 'fixture-owner/private-model'
        self.write('config/bad.json', json.dumps({API_FIELD: token, PASSWORD_FIELD: 'real-password-value',
                                                'hub': hf_token, 'model': private}))
        self.stage('config/bad.json')
        report = self.check()
        self.assertTrue({'credential_token', 'inline_credential', 'private_machine_path_in_config'} <= self.codes(report))
        rendered = json.dumps(report)
        for value in (token, hf_token, private, 'real-password-value'):
            self.assertNotIn(value, rendered)

    def test_unrelated_edit_does_not_report_historical_config_values(self):
        old = (self.root / 'config/legacy.json').read_text()
        self.write('config/legacy.json', old + '\n')
        self.stage('config/legacy.json')
        self.assertTrue(self.check()['passed'])
        self.write('config/legacy.json', old + '\n' + PASSWORD_FIELD + ': newly-added-value\n')
        self.stage('config/legacy.json')
        self.assertEqual(self.codes(self.check()), {'inline_credential'})

    def test_index_and_committed_blobs_ignore_unstaged_worktree_values(self):
        self.write('config/safe.json', '{"api_key":"${API_KEY}"}\n')
        self.stage('config/safe.json')
        self.write('config/safe.json', json.dumps({PASSWORD_FIELD: 'unsafe-working-copy'}))
        self.assertTrue(self.check()['passed'])
        self.commit()
        self.assertTrue(self.check(base=self.anchor, head='HEAD')['passed'])

    def test_changed_current_markdown_links_and_anchors_use_git_snapshot(self):
        self.write('docs/development/guide.md', '# 中文标题\n\n# Repeat\n\n# Repeat\n')
        self.write('README.md', '# Start\n\n[guide](docs/development/guide.md#repeat-1)\n'
                   '[Unicode](docs/development/guide.md#中文标题)\n'
                   '[historical](https://example.invalid/blob/137f1b2/archive.md)\n'
                   '[review](codex://review?pr=example)\n')
        self.stage('README.md', 'docs/development/guide.md')
        (self.root / 'docs/development/guide.md').unlink()
        self.assertTrue(self.check()['passed'])
        self.write('README.md', '# Start\n\n[bad](missing.md) [anchor](#absent)\n')
        self.stage('README.md')
        self.assertEqual(self.codes(self.check()), {'missing_local_link', 'missing_local_anchor'})

    def test_historical_markdown_is_not_revalidated_by_root_glob(self):
        self.write('docs/history/frozen.md', '[old](missing-original-output.md)\n')
        self.stage('docs/history/frozen.md')
        self.assertTrue(self.check()['passed'])

    def test_range_requires_ancestor_and_rejects_zero_base(self):
        with self.assertRaises(guard.GuardError):
            self.check(base='0' * 40, head='HEAD')
        self.git('checkout', '-q', '--orphan', 'unrelated')
        self.git('rm', '-rf', '-q', '.')
        self.write('other', 'unrelated')
        self.stage('other')
        self.commit()
        with self.assertRaises(guard.GuardError):
            self.check(base=self.anchor, head='HEAD')
        with self.assertRaises(guard.GuardError):
            guard.ci_comparison_base(self.root, '0' * 40, 'HEAD', self.anchor)

    def test_cli_json_output_is_new_and_no_overwrite(self):
        target = self.root / 'receipt.json'
        with patch.object(guard, 'ROOT', self.root), patch.object(guard, 'load_policy', return_value=(self.policy, self.legacy)):
            with redirect_stdout(io.StringIO()) as output:
                self.assertEqual(guard.main(['--json', '--output', str(target)]), 0)
            self.assertTrue(json.loads(output.getvalue())['passed'])
            original = target.read_bytes()
            with redirect_stdout(io.StringIO()) as output:
                self.assertEqual(guard.main(['--json', '--output', str(target)]), 2)
            self.assertEqual(target.read_bytes(), original)
            self.assertNotIn(str(self.root), output.getvalue())

    def test_real_cli_failure_reports_path_reason_action_and_redacts_values(self):
        import hashlib
        import re
        import sys
        # Run the real CLI in a separate process with its fixed anchor bound to this isolated fixture.
        source = Path(guard.__file__).read_text()
        digest = hashlib.sha256(('\n'.join(sorted(self.legacy)) + '\n').encode()).hexdigest()
        source = re.sub(r"^ANCHOR = .+$", 'ANCHOR = ' + repr(self.anchor), source, flags=re.M)
        source = re.sub(r"^LEGACY_COUNT = .+$", 'LEGACY_COUNT = 1', source, flags=re.M)
        source = re.sub(r"^LEGACY_DIGEST = .+$", 'LEGACY_DIGEST = ' + repr(digest), source, flags=re.M)
        self.write('scripts/check_repository_changes.py', source)
        self.write(guard.POLICY_PATH, json.dumps(self.policy))
        self.write(guard.LEGACY_PATH, json.dumps(dict(baseline_commit=self.anchor, paths=sorted(self.legacy))))
        self.write('docs/session.docx', 'runtime report')
        token = 'sk-' + 'c' * 30
        self.write('config/bad.json', json.dumps({API_FIELD: token}))
        self.stage(guard.POLICY_PATH, guard.LEGACY_PATH, 'docs/session.docx', 'config/bad.json')
        command = [sys.executable, '-B', 'scripts/check_repository_changes.py']
        text = subprocess.run(command, cwd=self.root, text=True, capture_output=True)
        self.assertEqual(text.returncode, 2)
        self.assertIn('docs/session.docx', text.stdout)
        self.assertIn('runtime recording, report, trajectory', text.stdout)
        self.assertIn('Action: Write runtime output to ignored outputs/', text.stdout)
        self.assertIn('environment variable', text.stdout)
        self.assertNotIn(token, text.stdout + text.stderr)
        structured = subprocess.run(command + ['--json'], cwd=self.root, text=True, capture_output=True)
        self.assertEqual(structured.returncode, 2)
        errors = json.loads(structured.stdout)['errors']
        self.assertTrue(errors)
        self.assertTrue(all(e['path'] and e['message'] and e['remediation'] for e in errors))
        self.assertNotIn(token, structured.stdout + structured.stderr)

    def test_unstaged_policy_does_not_whitelist_staged_output(self):
        # Fixture policy is read through Git blobs; working policy changes are ignored.
        self.write(guard.POLICY_PATH, json.dumps(self.policy))
        self.write(guard.LEGACY_PATH, json.dumps(dict(baseline_commit=self.anchor, paths=sorted(self.legacy))))
        self.stage(guard.POLICY_PATH, guard.LEGACY_PATH)
        self.write('docs/new.mp4', 'runtime')
        self.stage('docs/new.mp4')
        edited = dict(self.policy, exceptions=self.policy['exceptions'] +
                      [dict(path='docs/new.mp4', purpose='Unstaged bypass', max_bytes=64)])
        self.write(guard.POLICY_PATH, json.dumps(edited))
        import hashlib
        digest = hashlib.sha256(('\n'.join(sorted(self.legacy)) + '\n').encode()).hexdigest()
        with patch.object(guard, 'ANCHOR', self.anchor), patch.object(guard, 'LEGACY_COUNT', 1), patch.object(guard, 'LEGACY_DIGEST', digest):
            report = guard.check(self.root)
            self.assertIn('generated_runtime_output', self.codes(report))
            self.commit()
            report = guard.check(self.root, base=self.anchor, head='HEAD')
            self.assertIn('generated_runtime_output', self.codes(report))

    def test_large_or_lfs_config_fails_closed_without_content_disclosure(self):
        self.policy['text_scan_max_bytes'] = 128
        self.write('config/large.json', json.dumps({'padding': 'x' * 200, PASSWORD_FIELD: 'sensitive-value'}))
        self.write('config/remote.json', 'version https://git-lfs.github.com/spec/v1\noid sha256:' + 'a' * 64 + '\nsize 1024\n')
        self.stage('config/large.json', 'config/remote.json')
        report = self.check()
        self.assertEqual(sum(e['code'] == 'config_requires_content_review' for e in report['errors']), 2)
        self.assertNotIn('sensitive-value', json.dumps(report))

    def test_real_policy_has_exact_frozen_414_paths(self):
        root = Path(guard.__file__).resolve().parents[1]
        policy = json.loads((root / guard.POLICY_PATH).read_text())
        legacy = json.loads((root / guard.LEGACY_PATH).read_text())['paths']
        guard.validate_policy(policy)
        import hashlib
        self.assertEqual(hashlib.sha256(('\n'.join(sorted(legacy)) + '\n').encode()).hexdigest(), guard.LEGACY_DIGEST)
        self.assertEqual(policy['baseline_commit'], guard.ANCHOR)
        self.assertEqual(len(legacy), 414)
        for exception in policy['exceptions']:
            self.assertTrue(exception['purpose'])
            self.assertGreater(exception['max_bytes'], 0)
            self.assertFalse(any(ch in exception['path'] for ch in '*?['))


if __name__ == '__main__':
    unittest.main()
