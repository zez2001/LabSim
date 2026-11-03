"""Normal user routing, without starting Isaac or changing legacy defaults."""
import sys
import types

import pytest
from scripts.labsim_cli import parser, build_command, main


@pytest.mark.parametrize('command', ['demo', 'collect', 'eval', 'serve'])
def test_progress_is_explicit_release_only(command, tmp_path):
    args = parser().parse_args([command, '--project-version', 'Project_release_v1',
        '--output', str(tmp_path / 'new'), '--progress'])
    routed = build_command(args)
    assert '--progress' in routed
    assert 'demos.lab_cuvette_project_release_v1.launch' in routed
    assert 'Project_release_v1/standard.yaml' in ' '.join(routed)


def test_default_legacy_route_stays_unchanged(tmp_path):
    args = parser().parse_args(['demo', '--output', str(tmp_path / 'new')])
    routed = build_command(args)
    assert 'demos.lab_cuvette_project_v1.run' in routed
    assert '--progress' not in routed
    args.progress = True
    with pytest.raises(ValueError, match='Project_release_v1'):
        build_command(args)


def test_progress_current_alias_and_sequence(tmp_path):
    args = parser().parse_args(['collect', '--project-version', 'current', '--output', str(tmp_path / 'new'),
        '--sequence', 'teacher', 'early_finish', '--progress'])
    routed = build_command(args)
    assert args.project_version == 'Project_release_v1'
    assert '--progress' in routed
    assert 'demos.lab_cuvette_project_release_v1.run' in routed


def test_progress_subcommand_preserves_native_help_and_arguments(monkeypatch):
    received = []
    fake = types.ModuleType('demos.lab_cuvette_progress_v1.__main__')
    fake.main = lambda argv: received.append(argv) or 0
    monkeypatch.setitem(sys.modules, fake.__name__, fake)
    assert main(['progress', 'episode', '/data/closed', '--output', '/data/new']) == 0
    assert received == [['episode', '/data/closed', '--output', '/data/new']]


def test_replay_cli_checks_events_and_refuses_to_overwrite(tmp_path):
    import json
    from demos.lab_cuvette_progress_v1.__main__ import main as progress_main
    source = tmp_path / 'case'
    source.mkdir()
    (source / 'progress_events.jsonl').write_text('')
    (source / 'progress_summary.json').write_text(json.dumps({'attempts': [], 'retry_count': 0}))
    output = tmp_path / 'proof.json'
    assert progress_main(['replay', str(source), '--output', str(output)]) == 0
    assert json.loads(output.read_text())['passed'] is True
    before = output.read_bytes()
    assert progress_main(['replay', str(source), '--output', str(output)]) == 2
    assert output.read_bytes() == before


def test_publication_scope_audit_receives_real_unicode_paths(tmp_path):
    import importlib.util
    from pathlib import Path
    import subprocess
    tool = Path(__file__).resolve().parents[1] / 'docs/lab_cuvette_loading/Progress_v1_2/tools/protection.py'
    spec = importlib.util.spec_from_file_location('progress_protection', tool)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    subprocess.run(['git', 'init', '-q', str(tmp_path)], check=True)
    name = '中文验证报告.txt'
    (tmp_path / name).write_text('fixture only')
    subprocess.run(['git', 'config', 'core.quotepath', 'true'], cwd=tmp_path, check=True)
    subprocess.run(['git', 'add', '--', name], cwd=tmp_path, check=True)
    assert module.git(tmp_path, 'diff', '--cached', '--name-only') == name
