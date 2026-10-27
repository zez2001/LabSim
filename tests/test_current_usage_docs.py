"""Current usage examples are executable routes; archives retain their text."""
from scripts.check_current_usage_docs import anchors, check, cli_examples, inspect_guide


def test_current_usage_guides_links_versions_commands_and_homepage_parity():
    result = check()
    assert result['passed'], result['errors']
    assert result['command_count'] >= 15
    assert result['local_link_count'] >= 80


def test_shell_continuations_and_inline_examples_are_parsed_without_execution():
    text = '\n'.join(('```bash', './labsim demo --project-version Project_release_v1 ' + chr(92),
        ' --backend teacher --output "outputs/a b"', '```',
        '`./labsim doctor --project-version Project_release_v1 --json`'))
    rows = cli_examples(text)
    assert rows[0][1][-1] == 'outputs/a b'
    assert rows[0][1][1] == 'demo'
    assert rows[1][1][1] == 'doctor'


def test_heading_ids_support_current_unicode_and_repeated_sections():
    value = anchors('# 资产与物理规格\n## 图像：环境、训练数据和 checkpoint 三层接口\n## ABC\n## ABC\n')
    assert '资产与物理规格' in value
    assert '图像环境训练数据和-checkpoint-三层接口' in value
    assert {'abc', 'abc-1'} <= value


def test_guide_check_reports_missing_dependency_anchor_and_implicit_old_version(tmp_path):
    (tmp_path / 'target.md').write_text('# Existing heading\n')
    (tmp_path / 'guide.md').write_text('[missing](missing.md) [anchor](target.md#wrong)\n'
        '```bash\n./labsim doctor --json\n```\n')
    result = inspect_guide(tmp_path, 'guide.md')
    assert {error['type'] for error in result['errors']} == {
        'missing_local_link', 'missing_anchor', 'missing_explicit_version'}
