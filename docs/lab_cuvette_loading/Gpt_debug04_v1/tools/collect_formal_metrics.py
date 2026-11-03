"""Collect one explicitly authorized restored-debug04 trial, after native close.

This small adapter reuses the frozen evaluation's cost/action/initial-state
collectors and public analysis manifest. It never calls a model, opens a live
H5, changes labels, or treats historical episodes as new formal trials.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.util
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))


def helper():
    path = ROOT/'docs/lab_cuvette_loading/Policy_eval_v1/tools/collect_metrics.py'
    spec = importlib.util.spec_from_file_location('debug04_existing_metrics', path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def check_ledger(ledger, original, authorization, episode_id):
    """Keep immutable history, new episode cost, and grant consumption distinct."""
    base = authorization['base_attempt_count']
    attempts = ledger['attempts']
    if len(original['attempts']) != base or attempts[:base] != original['attempts']:
        raise ValueError('Historical ledger prefix differs from the authorized immutable base')
    if not math.isclose(ledger['max_estimated_usd'],
            authorization['base_estimated_usd']+authorization['additional_estimated_usd'], abs_tol=1e-9):
        raise ValueError('Authorized cumulative USD cap differs')
    if ledger['max_requests'] != base+authorization['additional_network_attempts']:
        raise ValueError('Authorized cumulative network-attempt cap differs')
    prefix = 'policy:'+episode_id+':'
    if any(row.get('label', '').startswith(prefix) for row in attempts[:base]):
        raise ValueError('New episode identity unexpectedly appears in historical ledger')
    new = attempts[base:]
    selected = [row for row in new if row.get('label', '').startswith(prefix)]
    foreign = [row.get('label') for row in new if not row.get('label', '').startswith(prefix)]
    if foreign:
        raise ValueError('The one-episode grant contains foreign new requests: '+str(foreign))
    if any(row.get('status') == 'RESERVED' for row in selected):
        raise ValueError('Episode has unfinished request reservations')
    if len(selected) > authorization['additional_network_attempts']:
        raise ValueError('New episode exceeds authorized network-attempt count')
    amount = sum(float(row['charged_estimate_usd']) for row in selected)
    if amount > authorization['additional_estimated_usd']+1e-9:
        raise ValueError('New episode exceeds authorized estimated USD')
    return dict(schema='labsim.gpt_debug04.new_episode_ledger_scope.v1',
        episode_id=episode_id, ledger_episode_binding_prefix=prefix,
        base_attempt_count=base, historical_prefix_preserved=True,
        selected_attempt_indices_zero_based=list(range(base, len(attempts))),
        new_network_attempts=len(selected), estimated_usd=round(amount, 12),
        authorized_additional_usd=authorization['additional_estimated_usd'],
        authorized_additional_network_attempts=authorization['additional_network_attempts'],
        remaining_authorized_estimate_usd=round(authorization['additional_estimated_usd']-amount, 12),
        remaining_authorized_network_attempts=authorization['additional_network_attempts']-len(selected),
        historical_requests_charged_to_new_episode=0, foreign_new_requests=[],
        request_ids=[row.get('request_id') for row in selected],
        estimate_scope='Only exact new episode UUID policy: labels after the immutable 377-request base; not supplier invoice')


def legacy_current_inputs(common, episode, ledger):
    """Bind exact archived debug04 observation artifacts to attempted labels.

    The restored vendor predates the temporal-context wire-manifest extension.
    Its saved JPEGs/state are exact current observation contents. This does not
    invent a hash for the full provider request or retained conversation.
    """
    controller = episode/'gpt_control'
    labels = {row.get('label') for row in ledger['attempts']}
    prepared = sorted((controller/'observations').glob('decision_*/manifest.json'))
    sent = [path for path in prepared if common.read(path)['request_label'] in labels]
    def packet(path):
        if path is None:
            return None
        value = common.read(path)
        sources = [value['public_observation'], *value['images']]
        for entry in sources:
            source = controller/entry['path']
            if common.sha(source) != entry['sha256'] or source.stat().st_size != entry['bytes']:
                raise ValueError('Saved exact observation artifact changed: '+str(source))
        return dict(source=common.snapshot_source(path), request_label=value['request_label'],
            network_attempted=value['request_label'] in labels, episode_id=value['episode_id'],
            observation_id=value['observation_id'], simulation_time_s=value.get('simulation_time_s'),
            public_observation=value['public_observation'], images=value['images'],
            full_wire_input_canonical_sha256=None,
            full_wire_input_status='Unavailable in exact historical vendor; exact current public state and two encoded JPEGs are preserved; no invented full-conversation hash')
    def observation(path):
        if path is None:
            return None
        value = common.read(path)
        return common.observation_snapshot(controller/value['public_observation']['path'])
    return dict(first_policy_observation=observation(sent[0] if sent else None),
        last_policy_observation=observation(sent[-1] if sent else None),
        first_actual_model_packet=packet(sent[0] if sent else None),
        last_actual_model_packet=packet(sent[-1] if sent else None),
        last_prepared_model_packet=packet(prepared[-1] if prepared else None),
        last_prepared_observation=observation(prepared[-1] if prepared else None),
        prepared_packet_count=len(prepared), actually_sent_packet_count=len(sent),
        actual_input_selection='Exact archived observation manifest.request_label membership in new episode ledger. These saved state/JPEG packets exclude unrecorded full wire/conversation serialization.')


def collect(run_root, authorization_path, closure_path, output):
    common = helper()
    run_root, authorization_path, closure_path, output = map(
        lambda p: Path(p).resolve(), (run_root, authorization_path, closure_path, output))
    if output.exists():
        raise FileExistsError(output)
    authorization = common.read(authorization_path)
    if authorization.get('approved') is not True or authorization['maximum_formal_episodes'] != 1:
        raise ValueError('This collector requires the explicit one-formal-episode grant')
    directory = run_root/'formal_debug04_01'
    episode = directory/'environment/episode_0000'
    # Must precede every source H5 hash/read or closure-tool invocation.
    if not common.closed_process(directory):
        raise ValueError('Native process and all supervised PIDs must be closed first; no active H5 access')
    protocol_path = directory/'environment.frozen_protocol.json'
    protocol = common.read(protocol_path)
    result = common.read(episode/'result.json')
    if not result or result.get('complete') is not True or result.get('publication_state') != 'complete':
        raise ValueError('Authoritative closed episode publication is unavailable')
    if not list(episode.glob('episode_*_complete.json')):
        raise ValueError('No transactional episode completion marker')
    if protocol.get('status') != 'frozen' or protocol['authorization_sha256'] != common.sha(authorization_path):
        raise ValueError('Frozen runtime protocol does not bind the exact authorization')
    closure = common.read(closure_path)
    if not closure or closure.get('passed') is not True or closure.get('episode_id') != result['episode_id']:
        raise ValueError('Passed closure audit with the exact episode identity is required')
    if closure.get('record_complete') is not True or closure.get('source_hashes_unchanged') is not True:
        raise ValueError('Closure evidence does not prove complete immutable recording')
    if not Path(closure['h5']['path']).is_file() or common.sha(closure['h5']['path']) != closure['h5']['sha256']:
        raise ValueError('Closure audit no longer binds the unchanged source H5')
    ledger_path = Path(protocol['ledger'])
    original_path = Path(protocol['original_budget_ledger'])
    if common.sha(original_path) != authorization['original_ledger_sha256']:
        raise ValueError('Original read-only budget ledger hash differs')
    ledger_bytes = ledger_path.read_bytes()
    ledger = json.loads(ledger_bytes)
    ledger_scope = check_ledger(ledger, common.read(original_path), authorization, result['episode_id'])
    process = common.read(directory/'environment/process_exit.json')
    manifest = common.read(directory/'environment/run_manifest.json')
    costs = common.gpt_cost(episode, ledger)
    if not math.isclose(costs['estimated_usd'], ledger_scope['estimated_usd'], abs_tol=1e-9):
        raise ValueError('Existing cost collector disagrees with independent new-prefix sum')
    action = common.action_summary(episode)
    costs.update(schema='labsim.gpt_debug04.episode_costs.v1', trial_id='debug04_01',
        episode_id=result['episode_id'], runtime_commit=process.get('runtime_commit'),
        record_purpose=result.get('record_purpose'), simulation_seconds=result.get('simulation_seconds'),
        control_steps=result.get('actual_control_steps'), actions=action,
        executed_action_count=action['executed_action_count'], executed_actions=action['executed_action_count'],
        returned_actions=costs.get('returned_action_count'), executed_control_ticks=action['executed_control_ticks'],
        executed_action_seconds=action['executed_duration_s'],
        wall_seconds=process.get('wall_seconds'), supervisor_wall_seconds=process.get('wall_seconds'),
        wall_scope=process.get('measurement_scope'),
        whole_process_wall_seconds=process.get('whole_process_wall_seconds'),
        whole_process_wall_status=process.get('whole_process_wall_status'),
        native_startup_seconds=process.get('native_startup_seconds'),
        native_shutdown_seconds=process.get('native_shutdown_seconds'),
        sum_measured_native_components_seconds=process.get('sum_measured_native_components_seconds'),
        task_wall_seconds=result.get('wall_seconds'),
        retry_count=costs.get('retries'), cost_usd=costs.get('estimated_usd'),
        action_rejections=costs.get('requested_motion_tool_rejections'),
        action_clipped=0 if common.finite(costs.get('action_requests')) else None,
        action_execution_errors=action.get('execution_errors'), service_wait_seconds=None,
        latencies_s=costs.get('inference_latencies_s'),
        action_execution_durations_s=[row['executed_duration_s'] for row in action['action_spans']
            if common.finite(row['executed_duration_s']) and row['executed_duration_s'] > 0],
        ledger_scope=ledger_scope,
        measurement_scope='Episode-local exact UUID ledger requests only; wall_seconds is the measured native run phase after app startup and before app shutdown (not whole-process elapsed). whole_process_wall_seconds is unavailable because the outer wrapper had no independent start timer. Separately measured native startup, run and shutdown components are summed only as measured components, not exact whole-process time. Policy wall is the original policy timer; inference is elapsed HTTP attempt including network/service wait; supplier invoice and separate service queue timer unavailable')
    domain_excluded = result.get('failure_domain') in {'service', 'protocol', 'recording', 'unknown',
        'initialization', 'preflight', 'model_service', 'backend', 'input_contract', 'executor', 'interruption', 'simulation'}
    task_evaluable = bool(closure.get('environment_valid') and closure.get('record_complete') and
        result.get('record_valid') is True and not domain_excluded)
    output.mkdir(parents=True, exist_ok=False)
    common.write(output/'costs/debug04_01.json', costs)
    common.write(output/'ledger_scope.json', ledger_scope)
    evidence = dict(protocol_path=str(protocol_path), protocol_sha256=common.sha(protocol_path),
        authorization_path=str(authorization_path), authorization_sha256=common.sha(authorization_path),
        collector_sha256=common.sha(__file__), original_ledger_path=str(original_path),
        original_ledger_sha256=common.sha(original_path), ledger_path=str(ledger_path),
        ledger_snapshot_sha256=__import__('hashlib').sha256(ledger_bytes).hexdigest(),
        created_utc=datetime.now(timezone.utc).isoformat(), runtime_commit=process.get('runtime_commit'),
        historical_and_P9_and_pi05_excluded=True)
    trials = []
    for planned in protocol['trials']:
        trial = dict(planned, purpose='formal', planned=True,
            policy_identity='GPT-6 Astra restored historical debug04 profile on Project_release_v1',
            authorized=planned['trial_id']=='debug04_01')
        if trial['authorized']:
            trial.update(started=True, status='closed', process_closed=True, episode_id=result['episode_id'],
                episode_dir=str(episode), episode_directory=str(episode), record_purpose=result.get('record_purpose'),
                record_valid=result.get('record_valid'), record_complete=closure.get('record_complete'),
                environment_valid=closure.get('environment_valid'), task_success=result.get('task_success'),
                task_evaluable=task_evaluable,
                task_evaluable_rule='closed finite geometry/reset evidence and original record_valid; no service/input/executor/interruption/simulation failure; task/safety outcomes remain evaluable',
                closure_receipt_path=str(closure_path), closure_receipt_sha256=common.sha(closure_path),
                cost_summary_path=str(output/'costs/debug04_01.json'),
                cost_summary_sha256=common.sha(output/'costs/debug04_01.json'),
                runtime_commit=process.get('runtime_commit'), scene_fingerprint=manifest.get('project_scene_fingerprint'),
                termination_reason=result.get('termination_reason'), failure_type=result.get('failure_type'),
                failure_domain=result.get('failure_domain'))
        else:
            if common.supervisor_started(run_root/('formal_'+trial['trial_id'])):
                raise ValueError('Unauthorized additional formal trial has started')
            trial.update(started=False, status='unstarted_not_authorized',
                unstarted_reason='Owner explicitly authorized one new formal episode only; remaining nine planned trials were not authorized or started',
                record_complete=None, environment_valid=None, task_evaluable=None)
        trials.append(trial)
    common.write(output/'trials.json', dict(schema='labsim.Policy_eval_v1.analysis_trials.v1',
        protocol_id=protocol['profile_id'], groups=[dict(group_id='restored_debug04',
            label='Restored debug04 GPT-6 Astra, current standard environment')], trials=trials,
        planned=10, authorized=1, started=1, unstarted_not_authorized=9,
        historical_and_diagnostic_in_formal=False, diagnostics=[], source_identity=evidence))
    initial_trial = dict(trials[0], group_id='gpt6')
    initial = common.initial_state(directory, episode, initial_trial, manifest, ledger)
    initial['group_id'] = 'restored_debug04'
    initial.update(legacy_current_inputs(common, episode, ledger))
    common.write(output/'initial_states.json', dict(schema='labsim.gpt_debug04.initial_states.v1',
        episodes=[initial], comparison=common.compare_initial_states([initial]), source_identity=evidence))
    common.write(output/'costs_summary.json', dict(schema='labsim.gpt_debug04.costs_summary.v1',
        group_id='restored_debug04', planned=10, authorized=1, started=1, closed=1, unstarted_not_authorized=9,
        actual_billing_usd=None, source_identity=evidence,
        episode_cost_statistics={key:common.distribution([costs.get(key)]) for key in
            ('simulation_seconds','control_steps','model_calls','network_attempts','executed_action_count',
             'inference_seconds','policy_wall_seconds','wall_seconds','estimated_usd')}, ledger_scope=ledger_scope))
    return dict(episode_id=result['episode_id'], planned=10, authorized=1, started=1,
        estimated_usd=costs['estimated_usd'], network_attempts=costs['network_attempts'],
        model_calls=costs['model_calls'], simulation_seconds=costs['simulation_seconds'],
        task_success=result.get('task_success'), task_evaluable=task_evaluable)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-root', required=True, type=Path)
    parser.add_argument('--authorization', required=True, type=Path)
    parser.add_argument('--closure', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(argv)
    print(json.dumps(collect(args.run_root,args.authorization,args.closure,args.output),ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
