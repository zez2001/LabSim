"""Read-only report input contracts; no DOCX construction or renderer calls."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


PATH = Path(__file__).resolve().parents[1] / 'docs/lab_cuvette_loading/Project_v1_1/report/generate_report.py'
SPEC = importlib.util.spec_from_file_location('project_v11_report_builder', PATH)
builder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(builder)


@pytest.fixture
def inputs(tmp_path, monkeypatch):
    monkeypatch.setattr(builder, 'ROOT', tmp_path)
    evidence = tmp_path / 'docs/Project_v1_1/closed.json'
    evidence.parent.mkdir(parents=True)
    evidence.write_text(json.dumps({'task_success': None, 'ticks': 3}), encoding='utf-8')
    data = dict(schema=builder.SCHEMA, project_version='Project_v1_1', finalized=True,
        metadata=dict(title=builder.TITLE, date='2026-10-27', audience='CPU contract fixture',
                      conclusion='Fixture only not a physical result'),
        sources=[dict(id='current', scope='diagnostic', path='docs/Project_v1_1/closed.json',
                      sha256=hashlib.sha256(evidence.read_bytes()).hexdigest())],
        cohorts=[dict(kind='diagnostic', status='closed', completed_count=1,
                      summary_source='current', note='One synthetic closed fixture')] +
                [dict(kind=kind, status='not_run', completed_count=0, note='Not executed by this fixture')
                 for kind in ('teacher', 'gpt_debug', 'gpt_formal')],
        pages=[dict(title=topic.replace('_', ' '), topics=[topic],
                    blocks=[dict(type='paragraph', text='Fixture scope only')])
               for topic in ('summary', 'executor', 'camera', 'grasp', 'gpt', 'teacher_data', 'release')],
        limitations=['Synthetic input contract only no simulation evidence'])
    return data


def test_unknown_task_outcome_is_not_coerced_to_failure(inputs):
    inputs['pages'][0]['blocks'] = [dict(type='table', headers=['Outcome', 'Ticks'], widths=[3, 1],
        align=['left', 'center'], rows=[[dict(source='current', pointer='/task_success'),
                                      dict(source='current', pointer='/ticks', format='.0f')]])]
    report = builder.prepare(inputs)
    assert report['pages'][0]['blocks'][0]['rows'] == [['null 未判定', '3']]
    assert report['cohorts'][3]['status'] == 'not_run'


def test_final_sources_require_unchanged_complete_hash(inputs, tmp_path):
    (tmp_path / inputs['sources'][0]['path']).write_text('{"ticks":99}', encoding='utf-8')
    with pytest.raises(ValueError, match='changed'):
        builder.prepare(inputs)
    inputs['sources'][0].pop('sha256')
    with pytest.raises(ValueError, match='saved SHA256'):
        builder.prepare(inputs)


def test_old_report_results_cannot_supply_current_sources(inputs, tmp_path):
    legacy = tmp_path / 'docs/Project_v1/closed.json'
    legacy.parent.mkdir(); legacy.write_text('{}', encoding='utf-8')
    inputs['sources'][0].update(path='docs/Project_v1/closed.json', sha256=builder.digest(legacy))
    with pytest.raises(ValueError, match='fixed public URL'):
        builder.prepare(inputs)


@pytest.mark.parametrize('path', ['/etc/passwd', '../outside.json'])
def test_traversal_and_absolute_evidence_rejected(inputs, path):
    inputs['sources'][0]['path'] = path
    with pytest.raises(ValueError, match='repository-relative'):
        builder.prepare(inputs)


def test_history_links_must_pin_commit_and_cannot_supply_metrics(inputs):
    inputs['sources'].append(dict(id='history', scope='history',
        url='https://github.com/example/repo/blob/codex/labsim/history.json'))
    with pytest.raises(ValueError, match='fixed complete commit'):
        builder.prepare(inputs)
    inputs['sources'][-1]['url'] = 'https://github.com/example/repo/blob/' + 'a' * 40 + '/history.json'
    inputs['pages'][0]['blocks'] = [dict(type='paragraph', text=dict(source='history', pointer='/ticks'))]
    with pytest.raises(ValueError, match='Historical evidence'):
        builder.prepare(inputs)


def test_formal_count_and_teacher_evidence_are_not_interchangeable(inputs):
    formal = inputs['cohorts'][3]
    formal.update(status='closed', completed_count=4, planned_count=5, summary_source='current')
    with pytest.raises(ValueError, match='own version and evidence scope'):
        builder.prepare(inputs)
    inputs['sources'][0]['scope'] = 'gpt_formal'
    inputs['cohorts'][0].update(status='not_run', completed_count=0)
    with pytest.raises(ValueError, match='every attempted episode'):
        builder.prepare(inputs)


def test_draft_requires_explicit_validation_and_never_authorizes_creation(inputs, tmp_path):
    inputs['finalized'] = False
    with pytest.raises(ValueError, match='not finalized'):
        builder.prepare(inputs)
    assert builder.prepare(inputs, allow_draft=True)['finalized'] is False
    source = tmp_path / 'draft_inputs.json'
    source.write_text(json.dumps(inputs), encoding='utf-8')
    with pytest.raises(SystemExit) as error:
        builder.main(['--inputs', str(source), '--author', '--allow-draft', '--marker-already-run'])
    assert error.value.code == 2
    assert list(tmp_path.rglob('*.docx')) == []


def test_logical_pages_and_distinct_cohort_declarations_required(inputs):
    missing = copy.deepcopy(inputs)
    missing['pages'] = missing['pages'][:5]
    with pytest.raises(ValueError, match='6 to 8'):
        builder.prepare(missing)
    missing = copy.deepcopy(inputs)
    missing['cohorts'].pop()
    with pytest.raises(ValueError, match='separately'):
        builder.prepare(missing)


def test_markdown_fragment_requires_explicit_hashed_links_and_figures():
    assert builder.markdown_fragment('## Plain heading\n\nA connected paragraph\ncontinued.') == [
        dict(type='heading', text='Plain heading', level=2),
        dict(type='paragraph', text='A connected paragraph continued.')]
    with pytest.raises(ValueError, match='explicit table/figure/links'):
        builder.markdown_fragment('[local](../unregistered.mp4)')
