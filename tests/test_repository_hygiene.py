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
        self.write('docs/old-feedback.zip', b'old immutable zip')
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

    def test_zip_is_controlled_by_default_in_plain_directories_and_any_language(self):
        names = ['docs/feedback.zip', 'docs/report.zip', 'docs/结果包.zip', 'source/archive.ZIP']
        for name in names:
            self.write(name, b'tiny archive')
        self.stage(*names)
        report = self.check()
        self.assertEqual({e['path'] for e in report['errors'] if e['code'] == 'generated_runtime_output'}, set(names))
        self.assertFalse(any(e.get('path') == 'docs/old-feedback.zip' for e in report['errors']))

    def test_zip_source_fixture_requires_exact_purpose_and_size_exception(self):
        source_zip = 'tests/fixtures/source-layout.zip'
        self.policy['exceptions'].append(dict(path=source_zip, purpose='Synthetic source-layout parser fixture', max_bytes=32))
        self.write(source_zip, b'small source fixture')
        self.stage(source_zip)
        self.assertTrue(self.check()['passed'])
        self.write('tests/fixtures/other-layout.zip', b'tiny')
        self.stage('tests/fixtures/other-layout.zip')
        self.assertIn('generated_runtime_output', self.codes(self.check()))
        self.write(source_zip, b'x' * 33)
        self.stage(source_zip)
        self.assertIn('exception_size_exceeded', self.codes(self.check()))

    def test_unmodified_historical_zip_is_not_rechecked(self):
        self.write('source.txt', 'ordinary source change\n')
        self.stage('source.txt')
        report = self.check()
        self.assertTrue(report['passed'])
        self.assertEqual(report['changed_file_count'], 1)

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

    def referenced_target(self, target='docs/current/topic.txt'):
        self.write(target, 'source text\n')
        self.write('README.md', '# Start\n\n[topic](' + target + ')\n[old unrelated](already-missing.md)\n')
        self.stage(target, 'README.md')
        self.commit()
        return target

    def test_deleted_target_is_checked_even_when_readme_is_unchanged(self):
        target = self.referenced_target()
        self.git('rm', '-q', '--', target)
        report = self.check()
        missing = [e for e in report['errors'] if e['code'] == 'missing_local_link']
        self.assertEqual(len(missing), 1)
        self.assertEqual(missing[0]['path'], 'README.md')
        self.assertEqual(missing[0]['target'], target)
        self.assertIn('README.md', report['removal_checked_documents'])
        self.assertEqual(report['deleted_file_count'], 1)

    def test_deleted_target_with_fixed_readme_passes(self):
        target = self.referenced_target()
        self.git('rm', '-q', '--', target)
        self.write('README.md', '# Start\n\nUpdated current guide.\n')
        self.stage('README.md')
        self.assertTrue(self.check()['passed'])

    def test_renamed_target_requires_link_update_in_staged_and_commit_modes(self):
        target = self.referenced_target()
        old_head = self.git('rev-parse', 'HEAD').strip()
        self.git('mv', target, 'docs/current/renamed.txt')
        self.assertIn('missing_local_link', self.codes(self.check()))
        self.commit()
        self.assertIn('missing_local_link', self.codes(self.check(base=old_head, head='HEAD')))
        self.write('README.md', '# Start\n\n[topic](docs/current/renamed.txt)\n')
        self.stage('README.md')
        self.assertTrue(self.check()['passed'])
        self.commit()
        self.assertTrue(self.check(base=old_head, head='HEAD')['passed'])

    def test_removed_directory_target_is_checked_and_other_old_errors_are_ignored(self):
        target = 'docs/topic/source.txt'
        self.write(target, 'source\n')
        self.write('README.md', '# Start\n\n[directory](docs/topic/)\n[old](missing-before.md)\n')
        self.stage(target, 'README.md')
        self.commit()
        self.git('rm', '-q', '--', target)
        missing = [e for e in self.check()['errors'] if e['code'] == 'missing_local_link']
        self.assertEqual([e['target'] for e in missing], ['docs/topic/'])

    def test_removed_html_media_target_in_unchanged_readme_is_checked(self):
        self.write('docs/showcase/demo.mp4', b'historical demo')
        self.write('README.md', '# Start\n\n<video controls><source src="docs/showcase/demo.mp4" type="video/mp4"></video>\n')
        self.stage('docs/showcase/demo.mp4', 'README.md')
        self.commit()
        self.git('rm', '-q', '--', 'docs/showcase/demo.mp4')
        missing = [e for e in self.check()['errors'] if e['code'] == 'missing_local_link']
        self.assertEqual([e['target'] for e in missing], ['docs/showcase/demo.mp4'])

    def archive_fixture(self):
        import hashlib
        target = 'docs/frozen/report.docx'
        original = b'original historical report bytes'
        history = 'HISTORY.md'
        helper = 'scripts/restore_history_archive.py'
        manifest_path = 'docs/archive/pilot/manifest.json'
        index = 'docs/archive/pilot/README.md'
        self.write(target, original)
        self.write(history, '# Frozen history\n\n[report](' + target + ')\n')
        self.write(helper, '# verified restoration helper fixture\n')
        self.stage(target, history, helper)
        self.commit()
        source = self.git('rev-parse', 'HEAD').strip()
        oid = self.git('rev-parse', 'HEAD:' + target).strip()
        repository = 'https://github.com/zez2001/LabSim'
        archive_sha = hashlib.sha256(b'fixture archive').hexdigest()
        download = repository + '/releases/download/history-pilot/archive.zip'
        manifest = dict(schema='labsim.historical_archive.v1', baseline_commit=source,
                        repository_url=repository,
                        archive=dict(filename='archive.zip', sha256=archive_sha, size_bytes=123, format='zip'),
                        release=dict(target_commit=source, tag='history-pilot', archive_download_url=download),
                        files=[dict(path=target, size_bytes=len(original), sha256=hashlib.sha256(original).hexdigest(),
                                    git_blob_oid=oid, git_mode='100644', lfs_pointer=False,
                                    source=repository + '/blob/' + source + '/' + target)],
                        restoration=dict(helper=helper))
        self.write(manifest_path, json.dumps(manifest))
        self.write(index, '# Verified archive\n\n[Download](' + download + ')\nSHA256: `' + archive_sha + '`\nRestore: `' + helper + '`\n')
        self.stage(manifest_path, index)
        self.commit()
        verified = self.git('rev-parse', 'HEAD').strip()
        self.policy['historical_archive_mappings'] = [dict(manifest=manifest_path, archive_index=index,
                                                          verified_commit=verified, historical_documents=[history])]
        self.git('rm', '-q', '--', target)
        return target, history, manifest_path, manifest

    def test_verified_archive_mapping_preserves_unchanged_historical_report_links(self):
        target, history, _manifest_path, _manifest = self.archive_fixture()
        report = self.check()
        self.assertTrue(report['passed'], report['errors'])
        self.assertEqual(report['archived_links'], [dict(document=history, target=target)])

    def test_archive_mapping_does_not_exempt_current_readme(self):
        target, _history, _manifest_path, _manifest = self.archive_fixture()
        self.write('README.md', '# Start\n\n[report](' + target + ')\n')
        self.stage('README.md')
        self.assertIn('missing_local_link', self.codes(self.check()))
        self.policy['historical_archive_mappings'][0]['historical_documents'].append('README.md')
        with self.assertRaises(guard.GuardError):
            self.check()

    def test_archive_mapping_rejects_modified_original_history(self):
        _target, history, _manifest_path, _manifest = self.archive_fixture()
        self.write(history, (self.root / history).read_text() + '\nNew claims.\n')
        self.stage(history)
        self.assertIn('invalid_historical_archive_mapping', self.codes(self.check()))

    def test_archive_mapping_requires_verified_manifest_bytes(self):
        _target, _history, manifest_path, manifest = self.archive_fixture()
        manifest['files'][0]['sha256'] = '0' * 64
        self.write(manifest_path, json.dumps(manifest))
        self.stage(manifest_path)
        self.assertIn('invalid_historical_archive_mapping', self.codes(self.check()))

    def test_archive_mapping_checks_original_hash_release_and_restore_entry(self):
        import copy
        target, history, manifest_path, manifest = self.archive_fixture()
        for mutate in ('hash', 'release', 'helper'):
            changed = copy.deepcopy(manifest)
            if mutate == 'hash':
                changed['files'][0]['sha256'] = '0' * 64
            elif mutate == 'release':
                changed['release']['archive_download_url'] = 'https://example.invalid/archive.zip'
            else:
                changed['restoration']['helper'] = 'scripts/missing-restore.py'
            self.write(manifest_path, json.dumps(changed))
            self.stage(manifest_path)
            self.commit()
            self.policy['historical_archive_mappings'][0]['verified_commit'] = self.git('rev-parse', 'HEAD').strip()
            self.assertFalse(guard.archive_mapping(self.root, self.policy['historical_archive_mappings'][0], history,
                                                  target, guard.tree(self.root)))

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
