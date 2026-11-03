#!/usr/bin/env python3
"""Build reproducible trial/cost inputs from the frozen policy evaluation.

No model calls or credential access. Closed episodes are audited before H5 is
read; active or startup-failed trials remain explicitly represented. Diagnostic
episodes are listed separately and never included in formal denominators.
"""
from __future__ import annotations

import argparse
import collections
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import statistics
import sys


def sha(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 << 20), b''):
            value.update(block)
    return value.hexdigest()


def read(path, default=None):
    path = Path(path)
    return json.loads(path.read_text()) if path.is_file() else default


def rows(path):
    path = Path(path)
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')


def finite(value):
    return isinstance(value, (float, int)) and not isinstance(value, bool) and math.isfinite(value)


def distribution(values):
    values = [float(x) for x in values if finite(x)]
    return dict(n=len(values), mean=statistics.mean(values) if values else None,
                median=statistics.median(values) if values else None,
                min=min(values) if values else None, max=max(values) if values else None)


def observed_sum(values):
    present = [float(value) for value in values if finite(value)]
    return sum(present) if present else None


def supervisor_started(directory):
    # Do not infer a start from an empty output folder or a planned manifest.
    return (directory/'supervisor.json').is_file() or (directory/'environment/process_exit.json').is_file()


def closed_process(directory):
    proof = read(directory/'environment/process_exit.json')
    if proof is None:
        supervisor = read(directory/'supervisor.json', {})
        if supervisor.get('status') != 'supervisor_error':
            return False
        # Startup can fail before an environment directory or episode exists.
        # The finally-updated child receipts still distinguish a closed failed
        # attempt from a running writer. Nothing is opened as H5 in this case.
        children = supervisor.get('children', [])
        return all(row.get('process_exited') is True and row.get('native_pid_gone') is True and
                   not Path('/proc', str(row['pid'])).exists() for row in children)
    if proof.get('process_exited') is not True:
        return False
    if any(row.get('process_exited') is not True or row.get('native_pid_gone') is not True
           for row in proof.get('children', [])):
        return False
    manifest = read(directory/'environment/run_manifest.json', {})
    pids = {int(row['pid']) for row in proof.get('children', []) if row.get('pid')}
    pids.update(int(item[key]) for item in (proof, manifest) for key in ('pid', 'process_id') if item.get(key))
    return all(not Path('/proc', str(pid)).exists() for pid in pids)


def seal_evidence(run_root, plan):
    """Require the protocol's real budget stop and its completed paired trial."""
    exhausted = []
    by_id = {item['trial_id']: item for item in plan['trials']}
    for item in plan['trials']:
        directory = run_root/('formal_'+item['trial_id'])
        if supervisor_started(directory) and not closed_process(directory):
            raise ValueError('Cannot seal while a started trial is not closed: '+item['trial_id'])
        if item['group_id'] != 'gpt6':
            continue
        episode = run_root/item['expected_episode_relative_path']
        summary = read(episode/'gpt_control/summary.json', {})
        if summary.get('termination_reason') != 'COST_BUDGET_EXHAUSTED':
            continue
        paired = by_id.get(item['paired_trial_id'])
        if paired is None or not closed_process(run_root/('formal_'+paired['trial_id'])):
            raise ValueError('Budget-exhausted GPT trial has no closed paired pi05 trial')
        exhausted.append(dict(trial_id=item['trial_id'], paired_trial_id=paired['trial_id'],
                              summary_path=str(episode/'gpt_control/summary.json'),
                              summary_sha256=sha(episode/'gpt_control/summary.json')))
    if not exhausted:
        raise ValueError('No closed formal GPT COST_BUDGET_EXHAUSTED episode; budget seal is unavailable')
    return dict(sealed=True, reason='declared_shared_API_budget_exhausted_after_completed_pair',
                evidence=exhausted)


def action_summary(episode):
    """Count actual native receipts once, not repeated model idempotent reads."""
    receipt_path = episode/'action_receipts.jsonl'
    receipt_rows = rows(receipt_path)
    unique = {}
    for index, row in enumerate(receipt_rows):
        unique[row.get('action_id', 'missing:'+str(index))] = row
    receipts = list(unique.values())
    executed = [row for row in receipts if finite(row.get('executed_control_ticks')) and row['executed_control_ticks'] > 0]
    spans = []
    for row in receipts:
        elapsed = row.get('executed_duration_s')
        if not finite(elapsed) and finite(row.get('simulation_time_before')) and finite(row.get('simulation_time_after')):
            elapsed = row['simulation_time_after']-row['simulation_time_before']
        spans.append(dict(action_id=row.get('action_id'), accepted=row.get('accepted'),
            target_reached=row.get('target_reached'), partial_execution=row.get('partial_execution'),
            safety_stopped=row.get('safety_stopped'), executed_control_ticks=row.get('executed_control_ticks'),
            requested_duration_s=row.get('requested_duration_s'), executed_duration_s=elapsed,
            t_before=row.get('simulation_time_before'), t_after=row.get('simulation_time_after'),
            stop_reason=row.get('stop_reason'), requested_effort_limit_N=row.get('requested_effort_limit_N'),
            applied_effort_limit_N=row.get('applied_effort_limit_N')))
    return dict(receipt_path=str(receipt_path) if receipt_path.is_file() else None,
                receipt_sha256=sha(receipt_path) if receipt_path.is_file() else None,
                physical_receipts=len(receipts) if receipt_path.is_file() else None,
                duplicate_native_receipt_rows=len(receipt_rows)-len(receipts),
                accepted=sum(row.get('accepted') is True for row in receipts) if receipt_path.is_file() else None,
                rejected=sum(row.get('accepted') is False for row in receipts) if receipt_path.is_file() else None,
                executed_action_count=len(executed) if receipt_path.is_file() else None,
                executed_control_ticks=int(sum(row.get('executed_control_ticks', 0) for row in receipts)) if receipt_path.is_file() else None,
                executed_physics_steps=observed_sum([row.get('executed_physics_steps') for row in receipts]),
                partial=sum(row.get('partial_execution') is True for row in receipts) if receipt_path.is_file() else None,
                safety_stopped=sum(row.get('safety_stopped') is True for row in receipts) if receipt_path.is_file() else None,
                target_reached=sum(row.get('target_reached') is True for row in receipts) if receipt_path.is_file() else None,
                execution_errors=sum(bool(row.get('executor_error_type') or row.get('error_type')) for row in receipts) if receipt_path.is_file() else None,
                executed_duration_s=observed_sum([row['executed_duration_s'] for row in spans]),
                action_spans=spans,
                scope='Unique native environment receipts; requested/rejected GPT tools are also counted separately')


def tokens_from_usage(usage):
    if not isinstance(usage, dict):
        return None
    details = usage.get('input_tokens_details', usage.get('prompt_tokens_details', {})) or {}
    output_details = usage.get('output_tokens_details', usage.get('completion_tokens_details', {})) or {}
    return dict(input_tokens=int(usage.get('input_tokens', usage.get('prompt_tokens', 0))),
                output_tokens=int(usage.get('output_tokens', usage.get('completion_tokens', 0))),
                cached_input_tokens=int(details.get('cached_tokens', 0)),
                reasoning_output_tokens=int(output_details.get('reasoning_tokens', 0)))


def gpt_cost(episode, ledger):
    controller = episode/'gpt_control'
    summary = read(controller/'summary.json', {})
    result = read(episode/'result.json', {})
    episode_id = result.get('episode_id') or (summary.get('task_result') or {}).get('episode_id')
    prefix = 'policy:'+str(episode_id)+':'
    attempts = [row for row in ledger.get('attempts', []) if row.get('label', '').startswith(prefix)] if episode_id else []
    trace = rows(controller/'policy_trace.jsonl')
    decisions = [row for row in trace if row.get('event') == 'decision']
    usage = [tokens_from_usage(row.get('usage')) for row in attempts]
    measured = [item for item in usage if item is not None]
    labels = collections.Counter(row.get('label') for row in attempts)
    grouped_attempts = collections.defaultdict(list)
    for attempt in attempts:
        grouped_attempts[attempt.get('label')].append(attempt)
    retry_gaps = []
    for group in grouped_attempts.values():
        for previous, following in zip(group, group[1:]):
            if all(finite(x) for x in (previous.get('created_unix_s'), previous.get('wall_seconds'), following.get('created_unix_s'))):
                retry_gaps.append(max(0., following['created_unix_s']-previous['created_unix_s']-previous['wall_seconds']))
    successful = sum(row.get('status') == 'OK' for row in attempts)
    token_totals = {key: sum(item[key] for item in measured) if measured else None for key in
                    ('input_tokens', 'output_tokens', 'cached_input_tokens', 'reasoning_output_tokens')}
    returned_tools = [row['tool_call'] for row in decisions if isinstance(row.get('tool_call'), dict)]
    error_decisions = []
    for row in trace:
        if row.get('event') != 'error':
            continue
        for tool in row.get('model_tool_calls') or []:
            returned_tools.append(tool)
            error_decisions.append(dict(tool_call=tool, receipt=row.get('action_receipt') or {}))
    motions = [row for row in decisions+error_decisions if row.get('tool_call', {}).get('name') in ('move_ee', 'gripper', 'wait')]
    rejected = [row for row in motions if row.get('receipt', {}).get('accepted') is False or row.get('receipt', {}).get('status') == 'REJECTED']
    latency = [row.get('wall_seconds') for row in attempts]
    return dict(backend='gpt6', model_calls=summary.get('api_decisions', successful if attempts else None),
        logical_model_calls_successful=summary.get('api_decisions', successful if attempts else None),
        logical_model_requests_attempted=len(labels) if episode_id else None,
        network_attempts=len(attempts) if episode_id else None,
        retries=sum(max(0, count-1) for count in labels.values()) if episode_id else None,
        retry_inter_attempt_gaps_s=retry_gaps,
        retry_inter_attempt_gap_total_s=observed_sum(retry_gaps),
        retry_gap_scope='Wall-clock gap between same-label reservations after subtracting prior attempt duration; includes backoff and local overhead',
        network_status_counts=dict(collections.Counter(row.get('status') for row in attempts)),
        tokens=token_totals, token_usage_known_attempts=len(measured),
        token_usage_unknown_attempts=len(attempts)-len(measured),
        input_tokens=token_totals['input_tokens'], output_tokens=token_totals['output_tokens'],
        cached_input_tokens=token_totals['cached_input_tokens'],
        estimated_usd=round(sum(float(row['charged_estimate_usd']) for row in attempts), 12) if episode_id else None,
        actual_billing_usd=None, actual_billing_status='Unknown: no supplier invoice/account multiplier evidence',
        cost_basis='Returned usage times frozen rates; unknown usage retains full conservative reservation',
        summary_estimated_usd=summary.get('estimated_usd_this_episode'),
        request_latencies_s=latency, inference_latencies_s=latency,
        inference_seconds=observed_sum(latency), inference_time_s=observed_sum(latency),
        inference_latency_s=distribution(latency),
        inference_latency_scope='One elapsed HTTP attempt including service and network wait; retries remain separate samples',
        tool_calls=len(returned_tools) if (controller/'policy_trace.jsonl').is_file() else None,
        tool_name_counts=dict(collections.Counter(tool.get('name') for tool in returned_tools)),
        action_requests=len(motions) if (controller/'policy_trace.jsonl').is_file() else None,
        requested_motion_tool_rejections=len(rejected) if (controller/'policy_trace.jsonl').is_file() else None,
        returned_action_count=len(motions) if (controller/'policy_trace.jsonl').is_file() else None,
        policy_wall_seconds=summary.get('wall_seconds'),
        policy_termination_reason=summary.get('termination_reason'),
        ledger_episode_binding_prefix=prefix if episode_id else None,
        ledger_request_ids=[row.get('request_id') for row in attempts],
        returned_model_counts=dict(collections.Counter(str(row.get('returned_model')) for row in attempts)),
        request_error_codes=[row.get('code') for row in trace if row.get('event') == 'error'],
        missing_evidence=[] if attempts or summary.get('termination_reason') == 'COST_BUDGET_EXHAUSTED' else ['No episode-bound GPT ledger attempts found'])


def pi05_cost(directory):
    model, policy = directory/'model', directory/'policy'
    inference = rows(model/'inference.jsonl')
    events = rows(policy/'policy_events.jsonl')
    summary = read(policy/'result.json', {})
    metadata = read(model/'model_metadata.json', {})
    actual_config = read(policy/'request.json', {}).get('policy_config_snapshot', {})
    calls = [row for row in events if row.get('event') == 'actual_model_inference']
    submissions = [row for row in events if row.get('event') == 'model_action_submitted']
    responses = [row for row in events if row.get('event') == 'model_action']
    rpc_latency = [row.get('inference', {}).get('inference_wall_s') for row in calls]
    forward_latency = [row.get('inherited_model_forward_wall_s') for row in inference]
    shapes = [row.get('raw_server_output_shape') for row in inference]
    returned = observed_sum([shape[-2] for shape in shapes if isinstance(shape, list) and len(shape) >= 2])
    selected = [row.get('inference', {}).get('selected_chunk_length') for row in calls]
    peak = [row.get('cuda_peak_allocated_bytes') for row in inference if finite(row.get('cuda_peak_allocated_bytes'))]
    clamped_components = 0
    translation_capped, rotation_capped, clipped_actions = 0, 0, 0
    for row in submissions:
        conversion = row.get('adapted_action', {}).get('conversion', {})
        raw = row.get('raw_model_action')
        clipped = conversion.get('normalized_action_clipped')
        if isinstance(raw, list) and isinstance(clipped, list):
            normalized_changed = sum(abs(a-b) > 1e-12 for a, b in zip(raw, clipped))
            clamped_components += normalized_changed
            ts, rs = actual_config.get('trained_translation_scale_m'), actual_config.get('trained_rotation_scale_rad')
            tc, rc = conversion.get('translational_cap_m'), conversion.get('rotational_cap_rad')
            t_changed = sum(abs(value*ts) > tc+1e-12 for value in clipped[:3]) if finite(ts) and finite(tc) else 0
            r_changed = sum(abs(value*rs) > rc+1e-12 for value in clipped[3:6]) if finite(rs) and finite(rc) else 0
            translation_capped += t_changed
            rotation_capped += r_changed
            clipped_actions += int(bool(normalized_changed or t_changed or r_changed))
    return dict(backend='pi05', model_calls=summary.get('actual_model_requests', len(calls) if events else None),
        server_inference_attempts=len(inference) if (model/'inference.jsonl').is_file() else None,
        server_actual_model_calls=sum(row.get('actual_model_call') is True for row in inference) if inference else None,
        network_attempts=None, retries=None, input_tokens=None, output_tokens=None, cached_input_tokens=None,
        estimated_usd=None, actual_billing_usd=None,
        actual_billing_status='Local GPU model; energy/cloud cost not measured',
        inference_latencies_s=rpc_latency, rpc_inference_latencies_s=rpc_latency,
        model_forward_latencies_s=forward_latency,
        inference_seconds=observed_sum(rpc_latency), inference_time_s=observed_sum(rpc_latency),
        model_forward_seconds=observed_sum(forward_latency),
        inference_latency_s=distribution(rpc_latency), model_forward_latency_s=distribution(forward_latency),
        inference_latency_scope='RPC predict elapsed at adapter; model_forward is inherited checkpoint forward only',
        checkpoint_id=metadata.get('checkpoint_id'), checkpoint_weights_sha256=metadata.get('weights_sha256'),
        normalization_sha256=metadata.get('norm_stats_sha256'),
        checkpoint_action_horizon=metadata.get('action_horizon'),
        server_action_chunk=metadata.get('action_chunk'),
        returned_action_shapes=shapes, returned_action_count=int(returned) if returned is not None else None,
        selected_chunk_lengths=selected, selected_action_count=int(sum(selected)) if selected and all(finite(x) for x in selected) else None,
        action_requests=summary.get('submitted_actions', len(submissions) if events else None),
        acknowledged_executed_actions=summary.get('executed_actions'),
        acknowledged_executed_control_ticks=summary.get('executed_control_ticks'),
        requested_action_clipped_components=clamped_components if submissions else None,
        execution_translation_capped_components=translation_capped if submissions else None,
        execution_rotation_capped_components=rotation_capped if submissions else None,
        clipped_action_requests=clipped_actions if submissions else None,
        action_response_count=len(responses) if events else None,
        acknowledged_accepted_actions=summary.get('accepted_actions'),
        acknowledged_rejected_actions=summary.get('rejected_actions'),
        model_gpu_peak_allocated_bytes=max(peak) if peak else None,
        model_gpu_peak_scope='torch.cuda.max_memory_allocated in model process; not whole-GPU RSS or Isaac memory',
        model_load_and_hash_wall_seconds=metadata.get('model_load_and_hash_wall_s'),
        policy_wall_seconds=summary.get('wall_time_s'), policy_termination_reason=summary.get('termination_reason'),
        server_error_count=sum(row.get('error') is not None for row in inference) if inference else None,
        waiting_pause_checks=summary.get('waiting_pause_checks'),
        missing_evidence=[] if inference and calls else ['Model inference or client inference evidence missing'])


def snapshot_source(path):
    return dict(path=str(path), sha256=sha(path), bytes=path.stat().st_size)


def observation_snapshot(path):
    value = read(path)
    if value is None:
        return None
    selected = {key: value.get(key) for key in ('episode_id', 'observation_id', 'simulation_time',
        'step_index', 'joint_positions', 'joint_velocities', 'TCPpose', 'gripper_opening_m',
        'finger_contact_N', 'source_slot_id', 'target_seat_id', 'model_image_transforms')}
    text = str(value.get('task_language', ''))
    selected.update(source=snapshot_source(path), task_text_sha256=hashlib.sha256(text.encode()).hexdigest())
    return selected


def model_packet_snapshot(path, attempted_labels):
    value = read(path)
    if value is None:
        return None
    return dict(source=snapshot_source(path), schema=value.get('schema'),
                request_label=value.get('request_label'),
                network_attempted=value.get('request_label') in attempted_labels,
                call_outcome=read(path.parent/'call_outcome.json'),
                full_wire_input_canonical_sha256=value.get('full_wire_input_canonical_sha256'),
                public_projection_canonical_sha256=value.get('public_projection_canonical_sha256'),
                total_image_count=value.get('total_image_count'), source_scope=value.get('source_scope'))


def initial_state(directory, episode, trial, manifest, ledger=None):
    debug = read(episode/'initial_debug.json', {})
    reset = read(episode/'reset_audit.json')
    first = dict(trial_id=trial['trial_id'], group_id=trial['group_id'], episode_id=read(episode/'result.json', {}).get('episode_id'),
                 scope='Evaluation-only reset/initial state; object truth is never a policy input',
                 scene_fingerprint=manifest.get('project_scene_fingerprint'),
                 scene=manifest.get('scene'), seed=read(episode/'result.json', {}).get('seed'),
                 reset_audit=reset, reset_check=read(episode/'reset_check.json'),
                 initial_debug_source=snapshot_source(episode/'initial_debug.json') if debug else None,
                 measured_before_first_action={key: debug.get(key) for key in
                     ('t', 'physics_step', 'object_position_m', 'object_quaternion_wxyz',
                      'actual_tcp_position_m', 'actual_tcp_quaternion_wxyz', 'joints9',
                      'gripper_target_m', 'gripper_effort_limit_N', 'source_bottom_gap_m')})
    if trial['group_id'] == 'gpt6':
        public = sorted((episode/'gpt_control/observations').glob('decision_*/public_observation.json'))
        packets = sorted((episode/'gpt_control/temporal_visual_context').glob('decision_*/input_items_manifest.json'))
        attempted_labels = {row.get('label') for row in (ledger or {}).get('attempts', [])}
        sent_packets = [path for path in packets if read(path, {}).get('request_label') in attempted_labels]
        def paired_observation(path):
            index = read(path)['decision_index']
            return observation_snapshot(episode/'gpt_control/observations'/('decision_'+str(index).zfill(6))/'public_observation.json')
        first['first_policy_observation'] = paired_observation(sent_packets[0]) if sent_packets else None
        first['last_policy_observation'] = paired_observation(sent_packets[-1]) if sent_packets else None
        first['first_actual_model_packet'] = model_packet_snapshot(sent_packets[0], attempted_labels) if sent_packets else None
        first['last_actual_model_packet'] = model_packet_snapshot(sent_packets[-1], attempted_labels) if sent_packets else None
        first['last_prepared_model_packet'] = model_packet_snapshot(packets[-1], attempted_labels) if packets else None
        first['last_prepared_observation'] = observation_snapshot(public[-1]) if public else None
        first['prepared_packet_count'] = len(packets)
        first['actually_sent_packet_count'] = len(sent_packets)
        first['actual_input_selection'] = 'Exact packet.request_label membership in original shared network ledger; locally prepared budget-refused input is separate'
    else:
        inference = rows(directory/'model/inference.jsonl')
        effective = rows(directory/'model/effective_input_audit.jsonl')
        effective_by_index = {row.get('request_index'): row for row in effective}
        events = [row for row in rows(directory/'policy/policy_events.jsonl') if row.get('event') == 'actual_model_inference']
        def pi_input(row, event):
            if row is None:
                return None
            index = row.get('request_index')
            path = directory/'model'/('input_'+str(index).zfill(6)+'.npz')
            actual_effective = effective_by_index.get(index)
            array_binding = None
            array_specs = None
            binding_error = None
            if path.is_file():
                try:
                    import numpy as np
                    array_specs = {}
                    with np.load(path, allow_pickle=False) as archive:
                        for key in ('main_images', 'wrist_images', 'states'):
                            value = archive[key]
                            array_specs[key] = dict(shape=list(value.shape), dtype=str(value.dtype),
                                                    sha256=hashlib.sha256(value.tobytes()).hexdigest())
                    array_binding = all(array_specs[key] == row.get('inputs', {}).get(key) for key in array_specs)
                except (OSError, ValueError, KeyError) as error:
                    array_binding, binding_error = False, type(error).__name__+': '+str(error)
            return dict(source=snapshot_source(path) if path.is_file() else None,
                request_index=index, inputs=row.get('inputs'),
                npz_array_specs=array_specs, npz_matches_actual_inference_input=array_binding,
                npz_binding_error=binding_error,
                task_text_sha256=[hashlib.sha256(str(t).encode()).hexdigest() for t in row.get('task_descriptions', [])],
                observation_step=(event or {}).get('inference', {}).get('observation_step'),
                state_vector=(event or {}).get('inference', {}).get('state_vector'),
                effective_input_audit_path=str(directory/'model/effective_input_audit.jsonl') if effective else None,
                effective_input_audit_file_sha256=sha(directory/'model/effective_input_audit.jsonl') if effective else None,
                effective_input={key: actual_effective.get(key) for key in
                    ('request_index', 'task_text_sha256', 'raw_token_count', 'model_max_tokens',
                     'truncated', 'effective_tokens_sha256', 'active_token_count', 'effective_decoded',
                     'image', 'image_mask', 'sentencepiece_model_sha256', 'tokenizer_class',
                     'output_matches_installed_formatting')} if actual_effective else None,
                state_scope='Native LIBERO TCP/base+axis-angle+signed-finger encoding; not joint9 or normalized training-reader state')
        first['first_policy_observation'] = pi_input(inference[0], events[0] if events else None) if inference else None
        first['last_policy_observation'] = pi_input(inference[-1], events[-1] if events else None) if inference else None
    return first


def compare_initial_states(states):
    import numpy as np
    valid = [row for row in states if row.get('measured_before_first_action', {}).get('actual_tcp_position_m') is not None]
    if not valid:
        return dict(reference_trial_id=None, comparisons=[], actual_initial_state_coverage=0)
    reference = valid[0]
    comparisons = []
    for row in valid:
        a, b = reference['measured_before_first_action'], row['measured_before_first_action']
        def delta(key):
            if a.get(key) is None or b.get(key) is None:
                return None
            return float(np.linalg.norm(np.asarray(a[key], float)-np.asarray(b[key], float)))
        q0, q1 = a.get('actual_tcp_quaternion_wxyz'), b.get('actual_tcp_quaternion_wxyz')
        angle = None
        if q0 is not None and q1 is not None:
            dot = abs(float(np.dot(q0, q1)/np.linalg.norm(q0)/np.linalg.norm(q1)))
            angle = 2*math.acos(min(1., dot))
        joints = None
        fingers = None
        if a.get('joints9') is not None and b.get('joints9') is not None:
            difference = abs(np.asarray(a['joints9'])-np.asarray(b['joints9']))
            joints, fingers = float(difference[:7].max()), float(difference[7:].max())
        comparisons.append(dict(trial_id=row['trial_id'],
            same_standard_layout=(row.get('scene') == reference.get('scene') == 'standard' and
                                  row.get('scene_fingerprint') == reference.get('scene_fingerprint')),
            TCP_position_delta_m=delta('actual_tcp_position_m'), TCP_rotation_delta_rad=angle,
            object_position_delta_m=delta('object_position_m'),
            maximum_arm_joint_delta_rad=joints, maximum_finger_joint_delta_m=fingers,
            note='Measured initial-state differences, not a calibrated accuracy acceptance threshold'))
    return dict(reference_trial_id=reference['trial_id'], comparisons=comparisons,
                actual_initial_state_coverage=len(valid))


def audit_closed(episode, run_root, trial_id, output):
    candidate = run_root/'validation'/('formal_'+trial_id+'_closed.json')
    existing = read(candidate)
    if existing and existing.get('episode_id') == read(episode/'result.json', {}).get('episode_id'):
        # Reuse a genuine closed-run receipt only while its H5 remains identical.
        h5 = existing.get('h5', {})
        if h5.get('path') and Path(h5['path']).is_file() and sha(h5['path']) == h5.get('sha256'):
            return existing, candidate
    path = Path(__file__).with_name('audit_episode.py')
    spec = importlib.util.spec_from_file_location('Policy_eval_v1_episode_audit', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    try:
        receipt = module.audit(episode, expected_purpose='policy_evaluation')
    except Exception as error:
        receipt = dict(schema='labsim.Policy_eval_v1.closed_episode_audit.v1',
                       episode=str(episode), passed=False, record_complete=False,
                       environment_valid=None, errors=[type(error).__name__+': '+str(error)])
    receipt['audit_tool_sha256'] = sha(path)
    target = output/'validation'/('formal_'+trial_id+'_closed.json')
    write(target, receipt)
    return receipt, target


def group_costs(trials):
    groups = []
    for group in ('gpt6', 'pi05'):
        selected = [row for row in trials if row['group_id'] == group]
        started = [row for row in selected if row['started']]
        costs = [row.get('_cost') for row in started if row.get('_cost')]
        metrics = {key: distribution([cost.get(key) for cost in costs]) for key in
            ('simulation_seconds', 'control_steps', 'model_calls', 'executed_action_count',
             'inference_seconds', 'policy_wall_seconds', 'wall_seconds', 'estimated_usd')}
        groups.append(dict(group_id=group, planned=len(selected), started=len(started),
            closed=sum(row.get('process_closed') is True for row in started),
            unstarted=len(selected)-len(started), episode_cost_statistics=metrics,
            aggregation='Summarize each episode first, then equally weight observed episode totals; missing remains null'))
    return groups


def collect(run_root, protocol_path, plan_path, output, *, seal_unstarted_budget=False):
    protocol, plan = read(protocol_path), read(plan_path)
    protocol_hash = sha(protocol_path)
    if plan.get('protocol_sha256') != protocol_hash:
        raise ValueError('Trial plan does not bind this exact frozen protocol')
    if protocol.get('status') != 'frozen':
        raise ValueError('A frozen protocol is required')
    trial_ids = [row['trial_id'] for row in plan['trials']]
    if len(trial_ids) != len(set(trial_ids)):
        raise ValueError('Trial IDs are not unique')
    seal = seal_evidence(run_root, plan) if seal_unstarted_budget else dict(sealed=False, reason='Collection remains open; unstarted trials stay planned')
    ledger_path = Path(protocol['budget']['ledger'])
    ledger_bytes = ledger_path.read_bytes()
    ledger = json.loads(ledger_bytes)
    if ledger['max_estimated_usd'] != protocol['budget']['cap_estimated_usd'] or ledger['max_requests'] != protocol['budget']['cap_network_attempts']:
        raise ValueError('Shared API budget caps differ from frozen protocol')
    output.mkdir(parents=True, exist_ok=False)
    trials, initials = [], []
    for planned in plan['trials']:
        row = dict(planned)
        row['policy_identity'] = next((group.get('label') for group in plan.get('groups', [])
                                      if group.get('group_id') == planned['group_id']), None)
        directory = run_root/('formal_'+planned['trial_id'])
        episode = run_root/planned['expected_episode_relative_path']
        row.update(started=supervisor_started(directory), run_directory=str(directory),
                   episode_directory=str(episode), episode_dir=str(episode),
                   record_purpose=None, environment_valid=None, record_complete=None,
                   task_success=None, task_evaluable=None, closure_receipt_path=None,
                   cost_summary_path=None, environment_seed=planned['environment_seed'])
        if not row['started']:
            row.update(status='unstarted_budget' if seal['sealed'] else 'planned',
                       not_started_reason=seal['reason'] if seal['sealed'] else 'Not started at collection time',
                       unstarted_reason=seal['reason'] if seal['sealed'] else 'Not started at collection time',
                       process_closed=None)
            trials.append(row)
            continue
        supervisor = read(directory/'supervisor.json', {})
        process = read(directory/'environment/process_exit.json', {})
        is_closed = closed_process(directory)
        row.update(process_closed=is_closed, status='closed' if is_closed else 'running',
                   actual_phase=supervisor.get('phase', process.get('phase')),
                   supervisor_path=str(directory/'supervisor.json'),
                   startup_or_service_error_type=supervisor.get('error_type'),
                   startup_or_service_error=supervisor.get('error'))
        result = read(episode/'result.json', {}) if is_closed else {}
        manifest = read(directory/'environment/run_manifest.json', {}) if is_closed else {}
        if is_closed and result:
            row.update(episode_id=result['episode_id'], task_success=result.get('task_success'),
                record_valid=result.get('record_valid'), record_purpose=result.get('record_purpose'),
                termination_reason=result.get('termination_reason'), failure_type=result.get('failure_type'),
                failure_domain=result.get('failure_domain'), runtime_commit=process.get('runtime_commit'),
                scene_fingerprint=manifest.get('project_scene_fingerprint'))
            closure, closure_path = audit_closed(episode, run_root, row['trial_id'], output)
            row.update(closure_receipt_path=str(closure_path), closure_receipt_sha256=sha(closure_path),
                       record_complete=closure.get('record_complete'), environment_valid=closure.get('environment_valid'),
                       closure_audit_passed=closure.get('passed'))
            excluded = result.get('failure_domain') in ('service', 'protocol', 'recording', 'unknown',
                'initialization', 'preflight', 'model_service', 'backend', 'input_contract',
                'executor', 'interruption', 'simulation')
            row['task_evaluable'] = bool(closure.get('environment_valid') and closure.get('record_complete') and
                                         result.get('record_valid') is True and not excluded)
            row['task_evaluable_rule'] = 'closed physical evidence and no declared service/input/executor/interruption/simulation failure; all started remain in end-to-end denominator'
            initials.append(initial_state(directory, episode, row, manifest, ledger))
        elif is_closed:
            row.update(status='closed_without_episode', termination_reason='SUPERVISOR_OR_STARTUP_FAILURE',
                       record_complete=False, task_evaluable=False,
                       exclusion_reason='Started supervisor has no closed episode result; retain as end-to-end noncompletion')
        else:
            row['pending_reason'] = 'No H5 access before process_exit and native PID closure'
        cost = gpt_cost(episode, ledger) if row['group_id'] == 'gpt6' and is_closed else pi05_cost(directory) if is_closed else dict(backend=row['group_id'])
        if is_closed:
            cost.update(schema='labsim.Policy_eval_v1.episode_costs.v1', trial_id=row['trial_id'],
                episode_id=result.get('episode_id'), record_purpose=result.get('record_purpose'),
                runtime_commit=process.get('runtime_commit'),
                simulation_seconds=result.get('simulation_seconds'), control_steps=result.get('actual_control_steps'),
                supervisor_wall_seconds=process.get('wall_seconds', supervisor.get('wall_seconds')),
                wall_seconds=process.get('wall_seconds', supervisor.get('wall_seconds')),
                wall_scope='Entire trial supervisor: environment/model startup, resets, inference/actions, finalization and full cleanup',
                task_wall_seconds=result.get('wall_seconds'), actual_billing_usd=None)
            if result:
                action = action_summary(episode)
                cost.update(actions=action, executed_action_count=action['executed_action_count'],
                            executed_control_ticks=action['executed_control_ticks'],
                            accepted_actions=action['accepted'], rejected_actions=action['rejected'],
                            executed_action_seconds=action['executed_duration_s'])
            # Explicit names consumed by the public episode-weighted analyzer.
            # USD is an estimate; GPT's HTTP timing is not a separate vendor
            # compute-only timer, and service queue wait is not independently measured.
            cost.update(returned_actions=cost.get('returned_action_count'),
                executed_actions=cost.get('executed_action_count'),
                retry_count=cost.get('retries'), cost_usd=cost.get('estimated_usd'),
                service_wait_seconds=None,
                action_rejections=(cost.get('requested_motion_tool_rejections') if row['group_id'] == 'gpt6' else cost.get('acknowledged_rejected_actions')),
                action_clipped=(0 if finite(cost.get('action_requests')) else None) if row['group_id'] == 'gpt6' else cost.get('clipped_action_requests'),
                action_execution_errors=cost.get('actions', {}).get('execution_errors'),
                latencies_s=cost.get('inference_latencies_s'),
                action_execution_durations_s=[item['executed_duration_s'] for item in cost.get('actions', {}).get('action_spans', [])
                    if finite(item.get('executed_duration_s')) and item['executed_duration_s'] > 0],
                measurement_scope='Each episode first; wall_seconds includes trial startup/model load/reset/inference/action/recording export/cleanup. Inference is GPT elapsed HTTP attempt or pi05 adapter RPC predict; model_forward is pi05 inherited checkpoint forward only. Service queue wait and actual invoice are unavailable. cost_usd is local usage-based estimate, never an actual invoice.')
            target = output/'costs'/(row['trial_id']+'.json')
            write(target, cost)
            row['cost_summary_path'] = str(target)
            row['cost_summary_sha256'] = sha(target)
            row['_cost'] = cost
        trials.append(row)
    group_summary = group_costs(trials)
    for row in trials:
        row.pop('_cost', None)
    diagnostics = []
    for directory in sorted(run_root.glob('diagnostic_*')):
        if not directory.is_dir():
            continue
        for episode in sorted((directory/'environment').glob('episode_*')):
            if not episode.is_dir() or not (episode/'result.json').is_file():
                continue
            result = read(episode/'result.json', {})
            diagnostics.append(dict(directory=str(episode), episode_id=result.get('episode_id'),
                record_purpose=result.get('record_purpose'), task_success=result.get('task_success'),
                included_in_formal=False, purpose='diagnostic'))
    identity = dict(protocol_path=str(protocol_path), protocol_sha256=protocol_hash,
        plan_path=str(plan_path), plan_sha256=sha(plan_path), collector_sha256=sha(__file__),
        created_utc=datetime.now(timezone.utc).isoformat(),
        ledger_path=str(ledger_path), ledger_snapshot_sha256=hashlib.sha256(ledger_bytes).hexdigest(),
        ledger_network_attempts=len(ledger['attempts']),
        ledger_estimated_usd=round(sum(float(r['charged_estimate_usd']) for r in ledger['attempts']), 12))
    write(output/'trials.json', dict(schema='labsim.Policy_eval_v1.analysis_trials.v1',
        groups=plan['groups'], trials=trials, protocol=identity, budget_seal=seal,
        protocol_id=protocol.get('protocol_id'), protocol_sha256=protocol_hash,
        diagnostics=diagnostics, diagnostics_in_formal=False))
    write(output/'initial_states.json', dict(schema='labsim.Policy_eval_v1.initial_states.v1',
        episodes=initials, comparison=compare_initial_states(initials), source_identity=identity))
    write(output/'costs_summary.json', dict(schema='labsim.Policy_eval_v1.costs_summary.v1',
        groups=group_summary, source_identity=identity, billing_actual_usd=None,
        incomplete_or_unstarted_counts=dict(collections.Counter(row['status'] for row in trials))))
    return dict(output=str(output), planned=len(trials), started=sum(row['started'] for row in trials),
                closed=sum(row.get('process_closed') is True for row in trials),
                diagnostic_episodes=len(diagnostics), budget_sealed=seal['sealed'])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-root', required=True, type=Path)
    parser.add_argument('--protocol', required=True, type=Path)
    parser.add_argument('--plan', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--seal-unstarted-budget', action='store_true')
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error('Output directory already exists: '+str(args.output))
    result = collect(args.run_root.resolve(), args.protocol.resolve(), args.plan.resolve(),
                     args.output.resolve(), seal_unstarted_budget=args.seal_unstarted_budget)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
