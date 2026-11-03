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
