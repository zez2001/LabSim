"""Prepared deterministic safety replay through public RPC; no model/provider.

Default is offline validation only. Root owns native GPU scheduling and must
explicitly provide --execute after the real model lifecycle has finished.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys
import time
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import numpy as np
from scipy.spatial.transform import Rotation


def sha(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def write(path, value):
    def encode(value):
        if isinstance(value, np.ndarray):
            return value.tolist()
        if isinstance(value, np.generic):
            return value.item()
        raise TypeError(type(value).__name__)
    with Path(path).open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False, default=encode) + '\n')


def observation_record(observation):
    value = copy.deepcopy({key: item for key, item in observation.items() if key != 'images'})
    value['observed_RGB'] = {name: dict(shape=list(image.shape), dtype=str(image.dtype),
        sha256=hashlib.sha256(np.ascontiguousarray(image).tobytes()).hexdigest(),
        pixels_location='Client saves native-RGB hashes only. Server H5 uses its declared image transform; native MP4 is encoded, not an exact raw-pixel copy.')
        for name, image in observation.get('images', {}).items()}
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, default=Path(__file__).with_name('envelopes.json'))
    parser.add_argument('--plan-sha256', required=True)
    parser.add_argument('--repository-root', type=Path, default=Path('/home/wujing/Desktop/vla/LabSim'))
    parser.add_argument('--endpoint', default='http://127.0.0.1:8097')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    if sha(args.plan) != args.plan_sha256:
        raise ValueError('Plan SHA256 differs')
    plan = json.loads(args.plan.read_text())
    if plan['action_count'] != 25 or len(plan['actions']) != 25:
        raise ValueError('Only the closed 25-action GPT05 prefix is accepted')
    for relative, record in plan['source_files'].items():
        if sha(args.repository_root / relative) != record['sha256']:
            raise ValueError('Closed source changed: ' + relative)
    if not all(plan['physical_executor_sources_unchanged_vs_source'].values()):
        raise ValueError('Physical-source equivalence was not established by the prepared audit')
    for relative, expected in plan['physical_executor_current_sha256'].items():
        if sha(args.repository_root / relative) != expected:
            raise ValueError('Prepared physical execution source changed: ' + relative)
    parsed = urlparse(args.endpoint)
    if parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', 'localhost'):
        raise ValueError('Only the existing unauthenticated loopback RPC is allowed')
    if not args.execute:
        print(json.dumps(dict(status='offline_plan_validated_not_executed', action_count=25,
            source_simulation_s=plan['source_result']['simulation_seconds'], model_calls=0,
            endpoint_contacted=False, plan_sha256=args.plan_sha256)))
        return 0
    if args.output is None:
        raise ValueError('--execute requires a new --output directory')
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    sys.path.insert(0, str(args.repository_root))
    from demos.lab_cuvette_project_v1.rpc import encode, decode
    def call(method, *positional, **keywords):
        body = json.dumps(dict(method=method, args=list(positional), kwargs=keywords),
                          default=encode, allow_nan=False).encode()
        request = Request(args.endpoint.rstrip('/') + '/call', data=body,
                          headers={'Content-Type': 'application/json'})
        with urlopen(request, timeout=1200) as response:
            result = decode(json.loads(response.read()))
        if result.get('ok') is not True:
            raise RuntimeError('RPC ' + method + ': ' + str(result.get('error_type')) + ': ' + str(result.get('error')))
        return result['result']
    metadata = call('env.get_env_meta')
    if (metadata.get('version') != 'Project_release_v1' or metadata.get('physics_hz') != 240
            or metadata.get('control_hz') != 60):
        raise ValueError('Expected the frozen 240Hz/60Hz Project_release_v1 server')
    write(output / 'server_metadata.json', metadata)
    observation, status = call('env.reset', 0, dict(mode='standard', policy_id='deterministic_closed_GPT05_safety_replay'))
    initial = plan['initial_public_robot_state']
    gate = plan['initial_equivalence_gate']
    q = np.asarray(observation['joint_positions']) - np.asarray(initial['joint_positions'])
    pose = observation['TCPpose']
    position_error = float(np.linalg.norm(np.asarray(pose['position_m']) - initial['TCPpose']['position_m']))
    angle_error = float((Rotation.from_quat(np.roll(pose['quaternion_wxyz'], -1)) *
                        Rotation.from_quat(np.roll(initial['TCPpose']['quaternion_wxyz'], -1)).inv()).magnitude())
    equivalent = bool(np.max(abs(q[:7])) <= gate['arm_rad'] and np.max(abs(q[7:])) <= gate['finger_m']
                      and position_error <= gate['TCP_position_m'] and angle_error <= gate['TCP_angle_rad'])
    write(output / 'initial_equivalence.json', dict(equivalent=equivalent,
        arm_error_rad=float(np.max(abs(q[:7]))), finger_error_m=float(np.max(abs(q[7:]))),
        TCP_position_error_m=position_error, TCP_angle_error_rad=angle_error, gate=gate))
    write(output / 'initial_observation.json', observation_record(observation))
    if not equivalent:
        call('project.finish', 'REPLAY_INITIAL_STATE_MISMATCH', failure_type='INPUT_CONTRACT_ERROR')
        raise RuntimeError('Initial robot state is not equivalent; no source action was replayed')
    started, rows, last_action, last_receipt = time.perf_counter(), [], None, None
    in_flight_action = None
    try:
        for index, original in enumerate(plan['actions']):
            before = call('project.observe')
            action = copy.deepcopy(original)
            action_id = f"closed-replay:{before['episode_id']}:{index:03d}"
            action.update(action_id=action_id, episode_id=before['episode_id'], observation_id=before['observation_id'])
            if 'execution_action_id' in action:
                action['execution_action_id'] = action_id
            changed = [key for key in original if action.get(key) != original[key]]
            if set(changed) - set(plan['allowed_rebindings']):
                raise RuntimeError('Replay changed nonidentity source fields')
            write(output / f'{index:02d}_before.json', observation_record(before))
            write(output / f'{index:02d}_action.json', action)
            in_flight_action = action
            receipt = call('project.execute', action)
            in_flight_action = None
            after = call('project.observe')
            after_status = call('project.status')
            row = dict(index=index, source_action_id=original['action_id'], execution_action_id=action_id,
                rebound_fields=changed, receipt=receipt, status=after_status)
            write(output / f'{index:02d}_receipt.json', row)
            write(output / f'{index:02d}_after.json', observation_record(after))
            rows.append(row)
            last_action, last_receipt = action, receipt
            print('SAFETY_REPLAY_PROGRESS', index + 1, receipt.get('status'),
                  receipt.get('simulation_time_after'), receipt.get('stop_reason'), flush=True)
            if after_status.get('terminated'):
                break
            if (receipt.get('accepted') is not True or receipt.get('target_reached') is not True
                    or receipt.get('partial_execution') or receipt.get('successor_observation_available') is not True):
                call('project.finish', 'REPLAY_UNEXPECTED_RECEIPT', failure_type='INPUT_CONTRACT_ERROR')
                break
        status = call('project.status')
        if not status.get('terminated'):
            call('project.finish', 'CLOSED_SAFETY_REPLAY_PREFIX_EXHAUSTED')
            status = call('project.status')
        # Actual cached retry after completion/safety is safe under the public
        # contract. It must return the original receipt without another step.
        retry = call('project.execute', last_action)
        after_retry = call('project.status')
        retry_check = dict(receipt_equal=(retry == last_receipt), status_unchanged=(after_retry == status),
                           simulation_time_before=status.get('simulation_time'), simulation_time_after=after_retry.get('simulation_time'))
        write(output / 'final_cached_retry.json', retry_check)
        if not all((retry_check['receipt_equal'], retry_check['status_unchanged'])):
            raise RuntimeError('Cached action retry advanced or changed the finished episode')
        write(output / 'replay_summary.json', dict(schema='labsim.Project_release_v1.safety_replay.v1',
            condition_group='deterministic_closed_action_replay', new_model_calls=0, paid_API_calls=0,
            source_plan_sha256=args.plan_sha256, actions_requested=25, actions_started=len(rows),
            status=status, wall_seconds=time.perf_counter() - started,
            actual_safety_stop_observed=bool(last_receipt.get('safety_stopped') and last_receipt.get('stop_domain') == 'safety'),
            cached_retry=retry_check, server_left_paused_and_running=True,
            native_dataset_video_and_independent_score_location='Same server episode_id under its existing output directory; audit only after native server exits'))
        return 0
    except BaseException as error:
        write(output / 'replay_client_failure.json', dict(type=type(error).__name__, error=str(error),
            completed_client_records=len(rows), no_action_is_automatically_retried=True))
        try:
            if in_flight_action is not None:
                ambiguous = call('project.receipt', in_flight_action['action_id'])
                write(output / 'ambiguous_action_receipt.json', dict(
                    action_id=in_flight_action['action_id'], receipt=ambiguous,
                    action_not_retried=True))
            if not call('project.status').get('terminated'):
                call('project.finish', 'REPLAY_CLIENT_INTERRUPTED', failure_type='PROCESS_INTERRUPTED')
        except BaseException:
            pass
        raise


if __name__ == '__main__':
    raise SystemExit(main())
