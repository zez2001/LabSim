"""Collection selection/cost tests, with no simulator, provider or active H5."""
import importlib.util
import json
from pathlib import Path

import pytest


_PATH = Path(__file__).resolve().parents[1] / 'docs/lab_cuvette_loading/Policy_eval_v1/tools/collect_metrics.py'
_SPEC = importlib.util.spec_from_file_location('policy_eval_collect_metrics', _PATH)
metrics = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(metrics)


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def test_episode_label_join_excludes_other_episodes_and_tracks_unknown_usage(tmp_path):
    episode = tmp_path/'episode'
    dump(episode/'result.json', dict(episode_id='chosen'))
    dump(episode/'gpt_control/summary.json', dict(api_decisions=1))
    ledger = dict(attempts=[
        dict(label='policy:other:0:decision0', status='OK', charged_estimate_usd=9., usage=dict(input_tokens=999)),
        dict(label='policy:chosen:0:decision0', status='PROVIDER_TIMEOUT', charged_estimate_usd=.6,
             created_unix_s=1., wall_seconds=2.),
        dict(label='policy:chosen:0:decision0', status='OK', charged_estimate_usd=.04,
             created_unix_s=4., wall_seconds=.5,
             usage=dict(input_tokens=100, output_tokens=10, input_tokens_details=dict(cached_tokens=40)))])
    actual = metrics.gpt_cost(episode, ledger)
    assert actual['estimated_usd'] == .64
    assert actual['network_attempts'] == 2 and actual['retries'] == 1
    assert actual['input_tokens'] == 100 and actual['cached_input_tokens'] == 40
    assert actual['token_usage_unknown_attempts'] == 1
    assert actual['retry_inter_attempt_gaps_s'] == [1.]
    assert actual['actual_billing_usd'] is None


def test_local_budget_refusal_has_zero_actual_network_spend(tmp_path):
    dump(tmp_path/'result.json', dict(episode_id='budget'))
    dump(tmp_path/'gpt_control/summary.json', dict(api_decisions=0, termination_reason='COST_BUDGET_EXHAUSTED'))
    actual = metrics.gpt_cost(tmp_path, dict(attempts=[]))
    assert actual['model_calls'] == 0
    assert actual['network_attempts'] == 0
    assert actual['estimated_usd'] == 0
    assert actual['input_tokens'] is None


def test_native_receipt_idempotency_does_not_duplicate_executed_actions(tmp_path):
    receipt = dict(action_id='a', accepted=True, executed_control_ticks=3, executed_duration_s=.05)
    (tmp_path/'action_receipts.jsonl').write_text('\n'.join(json.dumps(x) for x in [receipt, receipt]))
    actual = metrics.action_summary(tmp_path)
    assert actual['physical_receipts'] == 1
    assert actual['duplicate_native_receipt_rows'] == 1
    assert actual['executed_action_count'] == 1
    assert actual['executed_control_ticks'] == 3


def test_seal_requires_actual_budget_exhaustion_and_closed_pair(tmp_path):
    plan = dict(trials=[dict(trial_id='gpt6_01', group_id='gpt6', paired_trial_id='pi05_01',
                            expected_episode_relative_path='formal_gpt6_01/environment/episode_0000'),
                        dict(trial_id='pi05_01', group_id='pi05', paired_trial_id='gpt6_01',
                            expected_episode_relative_path='formal_pi05_01/environment/episode_0000')])
    with pytest.raises(ValueError, match='No closed formal GPT'):
        metrics.seal_evidence(tmp_path, plan)
    for group in ('gpt6', 'pi05'):
        dump(tmp_path/('formal_'+group+'_01')/'environment/process_exit.json', dict(process_exited=True, children=[]))
    path = tmp_path/'formal_gpt6_01/environment/episode_0000/gpt_control/summary.json'
    dump(path, dict(termination_reason='POLICY_FINISH_REQUEST'))
    with pytest.raises(ValueError, match='No closed formal GPT'):
        metrics.seal_evidence(tmp_path, plan)
    dump(path, dict(termination_reason='COST_BUDGET_EXHAUSTED'))
    assert metrics.seal_evidence(tmp_path, plan)['sealed']
    (tmp_path/'formal_pi05_01/environment/process_exit.json').unlink()
    with pytest.raises(ValueError, match='no closed paired'):
        metrics.seal_evidence(tmp_path, plan)


def test_started_supervisor_is_retained_without_opening_active_episode(tmp_path, monkeypatch):
    ledger = tmp_path/'ledger.json'
    dump(ledger, dict(max_estimated_usd=30., max_requests=1500, attempts=[]))
    protocol = tmp_path/'protocol.json'
    dump(protocol, dict(status='frozen', budget=dict(ledger=str(ledger), cap_estimated_usd=30., cap_network_attempts=1500)))
    plan = tmp_path/'plan.json'
    dump(plan, dict(protocol_sha256=metrics.sha(protocol), groups=[], trials=[
        dict(trial_id='gpt6_01', group_id='gpt6', paired_trial_id='pi05_01', purpose='formal',
             environment_seed=0, expected_episode_relative_path='formal_gpt6_01/environment/episode_0000')]))
    runs = tmp_path/'runs'
    dump(runs/'formal_gpt6_01/supervisor.json', dict(status='running', phase='formal'))
    def forbidden(*args, **kwargs):
        raise AssertionError('Active H5 must not be audited/opened')
    monkeypatch.setattr(metrics, 'audit_closed', forbidden)
    output = tmp_path/'output'
    actual = metrics.collect(runs, protocol, plan, output)
    trial = json.loads((output/'trials.json').read_text())['trials'][0]
    assert actual['started'] == 1 and actual['closed'] == 0
    assert trial['status'] == 'running' and trial['record_complete'] is None


def test_startup_failure_without_episode_remains_a_started_trial(tmp_path):
    directory = tmp_path/'formal_gpt6_01'
    dump(directory/'supervisor.json', dict(status='supervisor_error', children=[], error_type='ValueError'))
    assert metrics.supervisor_started(directory)
    assert metrics.closed_process(directory)


def test_cost_group_uses_per_episode_totals_not_request_weighting():
    trials = [dict(group_id='gpt6', started=True, process_closed=True,
                   _cost=dict(inference_seconds=1., model_calls=1)),
              dict(group_id='gpt6', started=True, process_closed=True,
                   _cost=dict(inference_seconds=10., model_calls=100))]
    actual = metrics.group_costs(trials)[0]
    assert actual['episode_cost_statistics']['inference_seconds']['mean'] == 5.5
    assert actual['episode_cost_statistics']['model_calls']['mean'] == 50.5


def test_budget_refused_prepared_observation_is_not_last_actual_model_input(tmp_path):
    episode = tmp_path/'environment/episode_0000'
    dump(episode/'result.json', dict(episode_id='episode', seed=0))
    for index, label in [(0, 'sent'), (1, 'prepared_only')]:
        folder = 'decision_'+str(index).zfill(6)
        dump(episode/'gpt_control/observations'/folder/'public_observation.json',
             dict(episode_id='episode', observation_id=str(index), task_language='task'))
        packet = episode/'gpt_control/temporal_visual_context'/folder/'input_items_manifest.json'
        dump(packet, dict(decision_index=index, request_label=label, full_wire_input_canonical_sha256=label))
        dump(packet.parent/'call_outcome.json', dict(status='returned' if index == 0 else 'failed',
             error_code=None if index == 0 else 'COST_BUDGET_EXHAUSTED'))
    actual = metrics.initial_state(tmp_path, episode,
        dict(trial_id='gpt6_01', group_id='gpt6'), {}, dict(attempts=[dict(label='sent')]))
    assert actual['actually_sent_packet_count'] == 1 and actual['prepared_packet_count'] == 2
    assert actual['last_actual_model_packet']['request_label'] == 'sent'
    assert actual['last_actual_model_packet']['network_attempted'] is True
    assert actual['last_prepared_model_packet']['request_label'] == 'prepared_only'
    assert actual['last_prepared_model_packet']['network_attempted'] is False
