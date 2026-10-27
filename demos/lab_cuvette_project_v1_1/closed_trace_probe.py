"""Replay a *closed* public-tool trace for an explicit control diagnostic.

This is an offline-declared experiment launcher, never a GPT tool or policy.
It makes no provider requests, chooses no coordinates, and stops at the first
rejected/partial/stopped action. The default preserves every recorded command,
including a final error-row ``model_tool_calls`` command. Only the three run IDs
are rebound. A manually supplied suffix is a separately labelled intervention.

``--help`` and ``--dry-run`` need neither Isaac nor a GPU. Dry-run validates and
hashes source evidence without creating an output directory.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / 'config/lab_cuvette_loading/Project_v1_1/standard.yaml'
LIMITS_CONFIG = ROOT / 'config/lab_cuvette_loading/Project_v1/policies/cubence_gpt6.json'
OUTPUT_ROOT = ROOT / 'outputs/lab_cuvette_loading/Project_v1_1'
SCHEMA = 'labsim.Project_v1_1.closed_trace_probe.v1'
SUFFIX_SCHEMA = 'labsim.Project_v1_1.closed_trace_suffix.v1'
IDENTITIES = frozenset(('episode_id', 'observation_id', 'action_id'))
SOURCE_TOOLS = frozenset(('move_ee', 'gripper', 'wait', 'observe', 'finish'))
SUFFIX_TOOLS = SOURCE_TOOLS - {'finish'}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def _json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'), parse_constant=_invalid_constant)


def _invalid_constant(value):
    raise ValueError('Nonfinite JSON value: ' + value)


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')


def pid_exists(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _safe_child(directory, name):
    relative = PurePosixPath(name)
    if relative.is_absolute() or '..' in relative.parts or not relative.parts:
        raise ValueError('Source evidence reference must be a relative child: ' + name)
    path = directory.joinpath(*relative.parts)
    resolved = path.resolve(strict=True)
    if not resolved.is_relative_to(directory.resolve()) or path.is_symlink() or not resolved.is_file():
        raise ValueError('Source evidence reference escapes its directory or is not a regular file: ' + name)
    return resolved


def _standard(metadata, contract):
    if metadata.get('scene_version') != 'Project_v1_1' or metadata.get('scene_mode') != 'standard':
        raise ValueError('Source is not a Project_v1_1 standard episode')
    cfg = contract.get('config', {})
    if cfg.get('scene_mode') != 'standard' or cfg.get('env', {}).get('mode') != 'standard':
        raise ValueError('Source scene contract is not standard')
    randomization = cfg.get('randomization', {})
    if any(value is True for key, value in randomization.items() if key.endswith('enabled')):
        raise ValueError('Source scene contract enables randomization')
    if cfg.get('env', {}).get('scene_randomization_enabled') is not False:
        raise ValueError('Source scene randomization must explicitly be disabled')
    if metadata.get('asset_id') != cfg.get('asset_id') or metadata.get('asset_id') != cfg.get('vessel', {}).get('asset_id'):
        raise ValueError('Source asset identity disagrees with its scene contract')
    fingerprint = contract.get('frozen_scene_sha256')
    body = {key: value for key, value in contract.items() if key != 'frozen_scene_sha256'}
    if not isinstance(fingerprint, str) or hashlib.sha256(canonical(body)).hexdigest() != fingerprint:
        raise ValueError('Source scene contract fingerprint does not match its contents')
    if metadata.get('frozen_scene_sha256') != fingerprint or metadata.get('control_config_sha256') != fingerprint:
        raise ValueError('Source release metadata disagrees with its scene fingerprint')
    if metadata.get('asset_sha256') != cfg.get('asset_selection', {}).get('asset_sha256'):
        raise ValueError('Source asset SHA disagrees with its selected asset')


def _number(value, field):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(field + ' must be a finite number')
    return value


def validate_parameters(tool, arguments, limits, *, suffix=False):
    """Static tool-shape checks; actual state-dependent checks stay in GenericTools."""
    if tool not in (SUFFIX_TOOLS if suffix else SOURCE_TOOLS) or not isinstance(arguments, dict):
        raise ValueError('Unsupported diagnostic tool or non-object arguments')
    if suffix and IDENTITIES.intersection(arguments):
        raise ValueError('Suffix IDs are supplied by the diagnostic runner, not by the plan')
    fields = dict(move_ee={'mode', 'values', 'frame', 'duration_s'},
                  gripper={'opening_m', 'effort_limit_N', 'duration_s'}, wait={'duration_s'},
                  observe=set(), finish={'reason'})[tool]
    supplied = set(arguments) - IDENTITIES
    if supplied != fields:
        raise ValueError(f'{tool} requires exactly these non-ID fields: {sorted(fields)}')
    canonical(arguments)  # Also reject nonfinite values nested in an unexpected representation.
    if tool in ('observe', 'finish'):
        if tool == 'finish' and not isinstance(arguments['reason'], str):
            raise ValueError('finish reason must be a string')
        return
    duration = _number(arguments['duration_s'], 'duration_s')
    if not limits['min_duration_s'] <= duration <= limits['max_duration_s']:
        raise ValueError('duration_s is outside the unchanged public action limit')
    # GenericTools owns duration quantization. No plan parameter is rewritten here.
    if tool == 'gripper':
        opening = _number(arguments['opening_m'], 'opening_m')
        effort = _number(arguments['effort_limit_N'], 'effort_limit_N')
        if not 0 <= opening <= limits['max_gripper_opening_m'] or not 0 <= effort <= limits['gripper_effort_limit_N']:
            raise ValueError('Gripper request is outside the unchanged public action limit')
    elif tool == 'move_ee':
        mode, values, frame = arguments['mode'], arguments['values'], arguments['frame']
        if mode not in ('ee_delta', 'ee_pose') or not isinstance(values, list) or len(values) != (6 if mode == 'ee_delta' else 7):
            raise ValueError('Invalid move_ee shape')
        if frame not in ('world', 'tcp') or mode == 'ee_pose' and frame != 'world':
            raise ValueError('Invalid move_ee frame')
        for value in values:
            _number(value, 'move_ee values')
        if mode == 'ee_delta':
            distance = math.sqrt(sum(value * value for value in values[:3]))
            angle = math.sqrt(sum(value * value for value in values[3:]))
            if (distance > limits['max_translation_m'] + 1e-9 or
                distance / duration > limits['max_linear_speed_m_s'] + 1e-9 or
                angle > limits['max_rotation_rad'] + 1e-9 or
                angle / duration > limits['max_angular_speed_rad_s'] + 1e-9):
                raise ValueError('Delta exceeds the unchanged public action limit')
        elif abs(math.sqrt(sum(value * value for value in values[3:])) - 1) > 1e-3:
            raise ValueError('ee_pose quaternion must be unit length')


def trace_actions(events, limits):
    """Do not discard a collision command merely because its event is an error."""
    actions, episode_ids, previous_decision = [], set(), -1
    for line_number, event in events:
        if not isinstance(event, dict):
            raise ValueError(f'Trace line {line_number} is not an object')
        call = event.get('tool_call')
        fallback = event.get('model_tool_calls', [])
        if call is None:
            if not fallback:
                if event.get('event') == 'error':
                    continue  # A service error without a command is not invented as an action.
                raise ValueError(f'Trace line {line_number} lacks a recorded command')
            if not isinstance(fallback, list) or len(fallback) != 1:
                raise ValueError('Exactly one recorded tool call is required per decision')
            call = fallback[0]
        elif fallback:
            raise ValueError('Ambiguous trace contains both tool_call and model_tool_calls')
        if not isinstance(call, dict):
            raise ValueError('Recorded tool call is not an object')
        args = copy.deepcopy(call.get('arguments'))
        if isinstance(args, str):
            args = json.loads(args, parse_constant=_invalid_constant)
        validate_parameters(call.get('name'), args, limits)
        decision = event.get('decision_index')
        if isinstance(decision, bool) or not isinstance(decision, int) or decision <= previous_decision:
            raise ValueError('Source decisions must have strictly increasing integer decision_index')
        previous_decision = decision
        episode = event.get('episode_id')
        observation = event.get('observation_id')
        if not isinstance(episode, str) or not episode or not isinstance(observation, str) or not observation.startswith(episode + ':'):
            raise ValueError('Source decision lacks coherent episode/observation identity')
        episode_ids.add(episode)
        if call['name'] != 'observe':
            if args.get('episode_id') != episode or args.get('observation_id') != observation:
                raise ValueError('Source tool IDs disagree with its decision')
            if call['name'] != 'finish' and (not isinstance(args.get('action_id'), str) or not args['action_id']):
                raise ValueError('Source action lacks action_id')
        actions.append(dict(origin='closed_source_trace', source_line=line_number, source_decision_index=decision,
            source_event=event.get('event'), source_tool_call_sha256=hashlib.sha256(canonical(call)).hexdigest(),
            tool=call['name'], arguments=args))
    if len(episode_ids) != 1 or not actions:
        raise ValueError('A nonempty single-episode trace is required')
    return actions, next(iter(episode_ids))


def preflight(source, proof, *, prefix_actions=None, suffix_plan=None, process_exists=pid_exists):
    """Read-only CPU source/closure/identity/plan checks, before output or Isaac."""
    source, proof = Path(source).resolve(strict=True), Path(proof).resolve(strict=True)
    if source.name != 'policy_trace.jsonl' or source.parent.name != 'gpt_control':
        raise ValueError('--source must name an episode gpt_control/policy_trace.jsonl')
    episode, run = source.parent.parent, source.parent.parent.parent
    files = {}

    def add(path, destination, expected_sha=None, expected_bytes=None):
        path = Path(path)
        if not path.is_file() or path.is_symlink():
            raise ValueError('Source evidence is not a regular file: ' + str(path))
        digest, size = sha256(path), path.stat().st_size
        if expected_sha is not None and digest != expected_sha or expected_bytes is not None and size != expected_bytes:
            raise ValueError('Source evidence SHA/size mismatch: ' + str(path))
        previous = files.get(destination)
        value = dict(source_path=str(path.resolve()), snapshot_path='source_evidence/' + destination, sha256=digest, bytes=size)
        if previous is not None and previous != value:
            raise ValueError('Conflicting source evidence destination')
        files[destination] = value
        return _json(path) if path.suffix == '.json' else None

    closure = add(proof, 'process_exit.json')
    pid = closure.get('pid')
    if closure.get('process_exited') is not True or isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
        raise ValueError('Explicit completed Popen process proof with positive PID is required')
    if process_exists(pid):
        raise ValueError('Source PID still exists; refuse a live or reused PID')
    if isinstance(closure.get('exit_code'), bool) or not isinstance(closure.get('exit_code'), int):
        raise ValueError('Source process proof needs an explicit integer exit_code')
    if Path(closure.get('run_directory', '')).resolve() != run:
        raise ValueError('Source proof run_directory does not identify the trace run')
    command = closure.get('command')
    if not isinstance(command, list) or '--output' not in command or command.count('--output') != 1:
        raise ValueError('Source proof command lacks an unambiguous output identity')
    output_index = command.index('--output') + 1
    if output_index == len(command) or Path(command[output_index]).resolve() != run:
        raise ValueError('Source proof command output does not identify the trace run')
    metadata = add(episode / 'release_metadata.json', 'episode/release_metadata.json')
    contract = add(episode / 'project_scene_contract.json', 'episode/project_scene_contract.json')
    result = add(episode / 'result.json', 'episode/result.json')
    options = add(episode / 'options.json', 'episode/options.json')
    launch = run / 'launch_config.yaml'
    add(launch, 'launch_config.yaml')
    manifest = add(run / 'run_manifest.json', 'run_manifest.json')
    audit = add(run / 'geometry_audit.json', 'geometry_audit.json')
    controller = add(source.parent / 'controller.json', 'episode/gpt_control/controller.json')
    _standard(metadata, contract)
    if manifest.get('backend') != 'gpt6' or manifest.get('episodes_completed') != 1:
        raise ValueError('Source is not one closed GPT episode')
    if manifest.get('project_scene_fingerprint') != metadata['frozen_scene_sha256']:
        raise ValueError('Source run manifest fingerprint mismatch')
    commit = closure.get('runtime_commit')
    if not isinstance(commit, str) or len(commit) != 40 or any(c not in '0123456789abcdef' for c in commit):
        raise ValueError('Source process proof needs its exact runtime commit')
    if metadata.get('actual_execution_commit') != commit or metadata.get('code_commit') != commit:
        raise ValueError('Source process/episode commit identity mismatch')
    if options.get('mode') != 'standard' or options.get('teacher') is not False:
        raise ValueError('Source options do not identify a standard non-teacher episode')
    if audit.get('geometry_valid') is not True:
        raise ValueError('Source geometry audit did not pass')
    source_assets = {name: digest for name, digest in audit.get('binding', {}).get('files', {}).items() if name.startswith('assets/')}
    if not source_assets or source_assets != contract.get('assets'):
        raise ValueError('Source audit assets disagree with its scene contract')
    add(source, 'episode/gpt_control/policy_trace.jsonl')
    events = [(line_number, json.loads(line, parse_constant=_invalid_constant))
              for line_number, line in enumerate(source.read_text().splitlines(), 1) if line.strip()]
    limits = _json(LIMITS_CONFIG)['action_limits']
    if controller.get('provider_config', {}).get('action_limits') != limits:
        raise ValueError('Source action limits differ from the unchanged ManualProbe/GenericTools limits')
    actions, source_episode_id = trace_actions(events, limits)
    if result.get('episode_id') != source_episode_id or result.get('asset_id') != metadata['asset_id']:
        raise ValueError('Source trace/result/release identity mismatch')
    # Check every public observation/JPEG referenced by every source decision,
    # including the partial-action error row. These are provenance, not feedback.
    for _, event in events:
        artifacts = event.get('observation_artifacts')
        if not artifacts:
            raise ValueError('Source decision lacks its public observation evidence')
        path = _safe_child(source.parent, artifacts['manifest_path'])
        observed = add(path, 'episode/gpt_control/' + artifacts['manifest_path'], artifacts['manifest_sha256'])
        if observed.get('episode_id') != source_episode_id or observed.get('observation_id') != event['observation_id']:
            raise ValueError('Public observation manifest identity mismatch')
        for item in [artifacts['public_observation'], *artifacts['images']]:
            add(_safe_child(source.parent, item['path']), 'episode/gpt_control/' + item['path'], item['sha256'], item['bytes'])
        public = _json(_safe_child(source.parent, artifacts['public_observation']['path']))
        if public.get('episode_id') != source_episode_id or public.get('observation_id') != event['observation_id']:
            raise ValueError('Public observation identity mismatch')
    count = len(actions) if prefix_actions is None else prefix_actions
    if isinstance(count, bool) or not isinstance(count, int) or not 0 <= count <= len(actions):
        raise ValueError('--prefix-actions must be between zero and the recorded action count')
    selected = copy.deepcopy(actions[:count])
    suffix_sha = None
    if suffix_plan is not None:
        if prefix_actions is None:
            raise ValueError('A suffix requires an explicit --prefix-actions intervention boundary')
        suffix = add(Path(suffix_plan).resolve(strict=True), 'manual_suffix_plan.json')
        if suffix.get('schema') != SUFFIX_SCHEMA or not isinstance(suffix.get('description'), str) or not suffix['description'].strip():
            raise ValueError('Suffix needs the explicit suffix schema and a human description')
        if not isinstance(suffix.get('actions'), list) or not suffix['actions']:
            raise ValueError('Suffix must explicitly list at least one generic action')
        for index, action in enumerate(suffix['actions']):
            if not isinstance(action, dict) or set(action) != {'tool', 'arguments'}:
                raise ValueError('Each suffix action must contain only tool and arguments')
            validate_parameters(action['tool'], action['arguments'], limits, suffix=True)
            selected.append(dict(origin='explicit_manual_suffix', suffix_index=index,
                                 tool=action['tool'], arguments=copy.deepcopy(action['arguments'])))
        suffix_sha = files['manual_suffix_plan.json']['sha256']
    if not selected:
        raise ValueError('The derived diagnostic plan has no actions')
    identity = dict(run_directory=str(run), episode_directory=str(episode), episode_id=source_episode_id,
        process_pid=pid, process_exit_code=closure['exit_code'], runtime_commit=commit,
        scene_version=metadata['scene_version'], scene_mode='standard', asset_id=metadata['asset_id'],
        asset_sha256=metadata['asset_sha256'], frozen_scene_sha256=metadata['frozen_scene_sha256'])
    plan = dict(schema=SCHEMA, run_identity=identity, source_trace_sha256=sha256(source),
        recorded_actions=len(actions), prefix_actions=count, suffix_plan_sha256=suffix_sha,
        mode='unchanged_closed_trace' if count == len(actions) and suffix_plan is None else 'declared_prefix_suffix_diagnostic',
        only_rebound_fields=sorted(IDENTITIES), actions=selected,
        source_files=list(files.values()), model_calls=0, diagnostic_not_GPT_demonstration=True,
        condition_group='control_diagnostic', full_loading_training_admission=False,
        admission_basis='Existing ProjectV11Dataset rejects condition_group=control_diagnostic; physical task labels are preserved')
    plan['derived_plan_sha256'] = hashlib.sha256(canonical(plan)).hexdigest()
    return plan


def verify_sources(plan, *, process_exists=pid_exists):
    if process_exists(plan['run_identity']['process_pid']):
        raise ValueError('Source PID exists at replay launch')
    for item in plan['source_files']:
        path = Path(item['source_path'])
        if not path.is_file() or path.stat().st_size != item['bytes'] or sha256(path) != item['sha256']:
            raise ValueError('Source evidence changed after preflight: ' + str(path))


def snapshot_sources(plan, output):
    verify_sources(plan)
    for item in plan['source_files']:
        target = Path(output) / item['snapshot_path']
        target.parent.mkdir(parents=True, exist_ok=True)
        with Path(item['source_path']).open('rb') as source, target.open('xb') as destination:
            shutil.copyfileobj(source, destination)
        if sha256(target) != item['sha256']:
            raise ValueError('Source snapshot changed while copying')


def check_runtime_identity(plan, contract, metadata=None):
    expected = plan['run_identity']
    if contract.get('frozen_scene_sha256') != expected['frozen_scene_sha256']:
        raise ValueError('Actual diagnostic scene fingerprint differs from the closed source scene')
    cfg = contract.get('config', {})
    if cfg.get('asset_id') != expected['asset_id'] or cfg.get('asset_selection', {}).get('asset_sha256') != expected['asset_sha256']:
        raise ValueError('Actual diagnostic asset differs from the closed source asset')
    if metadata is not None:
        for key in ('frozen_scene_sha256', 'asset_id', 'asset_sha256'):
            if metadata.get(key) != expected[key]:
                raise ValueError('Actual reset release metadata mismatch: ' + key)
        if metadata.get('condition_group') != 'control_diagnostic':
            raise ValueError('Diagnostic reset did not retain its isolated condition group')


def implementation_hashes():
    names = [Path(__file__).relative_to(ROOT).as_posix(),
        'demos/lab_cuvette_project_v1_1/run.py', 'demos/lab_cuvette_project_v1_1/probes.py',
        'demos/lab_cuvette_project_v1/runtime.py', 'demos/lab_cuvette_project_v1_1/contract.py',
        'policy/backends/cubence_project_v1_1_tools.py', 'policy/backends/cubence_tools.py',
        'factories/task_factory.py', LIMITS_CONFIG.relative_to(ROOT).as_posix()]
    return {name: sha256(ROOT / name) for name in names}


def isolated_output(path, plan):
    """A new direct child of this version's output tree, never an old run.

    A clean checkout may replay evidence held by another checkout. Therefore its
    own output base and the *verified proof run's* version base are allowed. The
    latter must have the exact outputs/lab_cuvette_loading/Project_v1_1 suffix;
    no development-machine absolute path is assumed.
    """
    path = Path(path).expanduser()
    if '..' in path.parts:
        raise ValueError('Diagnostic output must not contain parent traversal')
    absolute = path if path.is_absolute() else Path.cwd() / path
    for component in (absolute, *absolute.parents):
        if component.is_symlink():
            raise ValueError('Diagnostic output and all existing parents must not be symlinks')
    candidate = absolute.resolve()
    if candidate.exists():
        raise FileExistsError('Refusing to overwrite output: ' + str(candidate))
    source_run = Path(plan['run_identity']['run_directory'])
    if candidate.is_relative_to(source_run) or source_run.is_relative_to(candidate):
        raise ValueError('Diagnostic output must not overlap the closed source run')
    allowed = {OUTPUT_ROOT.resolve()}
    source_base = source_run.parent
    if source_base.parts[-3:] == ('outputs', 'lab_cuvette_loading', 'Project_v1_1'):
        allowed.add(source_base.resolve())
    if candidate.parent not in allowed:
        raise ValueError('Diagnostic output must be a new direct child of a verified Project_v1_1 output base')
    return candidate


def replay_plan(probe, plan, output):
    """Run the declared list via the real ManualProbe and its real GenericTools."""
    records, stopped = [], None
    for index, action in enumerate(plan['actions']):
        if probe.task.ended:
            stopped = 'EPISODE_ALREADY_ENDED'
            break
        # ManualProbe binds exactly these three fresh identities. Every other
        # parameter, including frame, duration, effort and the error-row delta,
        # remains byte-value equivalent to the declared plan.
        arguments = {key: copy.deepcopy(value) for key, value in action['arguments'].items() if key not in IDENTITIES}
        ok = probe.call(action['tool'], **arguments)
        record = probe.records[-1]
        record['closed_trace_provenance'] = dict(
            derived_plan_sha256=plan['derived_plan_sha256'], source_trace_sha256=plan['source_trace_sha256'],
            plan_action_index=index, source_decision_index=action.get('source_decision_index'),
            source_line=action.get('source_line'), source_event=action.get('source_event'),
            suffix_index=action.get('suffix_index'), origin=action['origin'],
            source_tool_call_sha256=action.get('source_tool_call_sha256'),
            original_identities={key: action['arguments'][key] for key in IDENTITIES if key in action['arguments']},
            only_rebound_fields=sorted(IDENTITIES), model_calls=0, diagnostic_not_GPT_demonstration=True)
        records.append(copy.deepcopy(record))
        write(probe.task.episode_dir / 'probe_actions.json', probe.records)
        write(Path(output) / 'replay_receipts.json', records)
        if 'error' in record:
            stopped = 'TOOL_ERROR'
        elif probe.task.ended:
            stopped = 'EPISODE_ENDED'
        elif action['tool'] not in ('observe', 'finish') and not ok:
            stopped = 'TARGET_NOT_REACHED_OR_REJECTED'
        if stopped:
            break  # Never replay, heal, or continue a partially executed action.
    return dict(actions_attempted=len(records), declared_actions=len(plan['actions']),
        all_declared_actions_attempted=len(records) == len(plan['actions']), stop_reason=stopped,
        source_trace_sha256=plan['source_trace_sha256'], derived_plan_sha256=plan['derived_plan_sha256'],
        actions=records, model_calls=0, diagnostic_not_GPT_demonstration=True,
        full_loading_training_admission=False, condition_group='control_diagnostic')


def parser():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--source', type=Path, required=True, help='Closed episode gpt_control/policy_trace.jsonl')
    p.add_argument('--proof', type=Path, required=True, help='Popen exit proof identifying this exact run directory/PID/commit')
    p.add_argument('--config', type=Path, default=DEFAULT_CONFIG, help='Unmodified standard configuration; actual fingerprint must match the source')
    p.add_argument('--output', type=Path, help='New diagnostic directory; refuses overwrite (required unless --dry-run)')
    p.add_argument('--prefix-actions', type=int, help='Explicit first N recorded commands, including zero; default replays every command')
    p.add_argument('--suffix-plan', type=Path, help='Explicit generic-action JSON intervention; requires --prefix-actions')
    p.add_argument('--headless', action='store_true')
    p.add_argument('--gui', action='store_true')
    p.add_argument('--dry-run', action='store_true', help='CPU-only source/proof/plan validation; no output, simulation or provider call')
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    if args.gui and args.headless:
        raise ValueError('Choose --gui or --headless')
    if not args.dry_run and args.output is None:
        raise ValueError('--output is required unless --dry-run')
    if args.output is not None and args.output.exists():
        raise FileExistsError('Refusing to overwrite output: ' + str(args.output))
    plan = preflight(args.source, args.proof, prefix_actions=args.prefix_actions, suffix_plan=args.suffix_plan)
    output = isolated_output(args.output, plan) if args.output is not None else None
    if args.dry_run:
        print(json.dumps(plan, indent=2, ensure_ascii=False, allow_nan=False))
        return 0
    # Imports below this line may inspect the selected Isaac distribution. The
    # source is already closed, hashed and internally coherent before that work.
    from omegaconf import OmegaConf
    from demos.lab_cuvette_project_v1.runtime import resolve_config
    from demos.lab_cuvette_project_v1_1.run import ensure_audit
    from demos.lab_cuvette_project_v1_1.contract import scene_contract
    cfg = resolve_config(OmegaConf.load(args.config))
    cfg.env.execution_purpose = 'eval'
    cfg.experiment.condition_group = 'control_diagnostic'
    verify_sources(plan)
    output.mkdir(parents=True, exist_ok=False)
    snapshot_sources(plan, output)
    write(output / 'derived_plan.json', plan)
    OmegaConf.save(cfg, output / 'launch_config.yaml')
    audit = ensure_audit(cfg, output)
    write(output / 'geometry_audit.json', audit)
    if audit.get('geometry_valid') is not True:
        raise RuntimeError('Geometry precheck failed; no physical diagnostic started')
    check_runtime_identity(plan, scene_contract(cfg, audit))
    source_seed = _json(Path(plan['run_identity']['episode_directory']) / 'result.json').get('seed')
    if isinstance(source_seed, bool) or not isinstance(source_seed, int):
        raise ValueError('Source result must declare an integer reset seed')
    import fcntl
    lock = open('/tmp/labsim-V0_ext01-gpu.lock', 'a')
    app = task = None
    started = time.perf_counter()
    manifest = dict(schema=SCHEMA, backend='diagnostic', model_calls=0, condition_group='control_diagnostic',
        diagnostic_not_GPT_demonstration=True, full_loading_training_admission=False,
        original_physical_scoring_preserved=True, source_run_identity=plan['run_identity'],
        source_trace_sha256=plan['source_trace_sha256'], derived_plan_sha256=plan['derived_plan_sha256'],
        implementation_sha256=implementation_hashes(), reset_seed=source_seed,
        runtime_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        lifecycle_reused_from='demos.lab_cuvette_project_v1_1.run.main',
        public_executor_reused_from='ManualProbe -> ProjectV11RobotTools -> ProjectEnvironment',
        sequential_single_gpu=True, physics_hz=int(cfg.physics.hz), control_hz=int(cfg.physics.control_hz),
        actual_reset_fingerprint_checked=False, physical_run_started=False)
    write(output / 'run_manifest.json', manifest)
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        verify_sources(plan)
        os.environ['OMNI_KIT_ACCEPT_EULA'] = 'YES'
        from isaacsim import SimulationApp
        extra = ['--/app/extensions/fsWatcherEnabled=false', '--/app/hydraEngine/waitIdle=true',
                 '--/app/updateOrder/checkForHydraRenderComplete=1000']
        app = SimulationApp(dict(headless=args.headless, width=1280, height=720, extra_args=extra, fast_shutdown=False))
        from factories.task_factory import create_task
        from demos.lab_cuvette_project_v1_1.environment import ProjectEnvironment
        from demos.lab_cuvette_project_v1_1.probes import ManualProbe
        task = create_task(cfg.task_type, cfg, app, output, geometry_audit=audit)
        facade = ProjectEnvironment(task)
        facade.reset(source_seed, dict(mode='standard', teacher=False,
            policy_id='closed_trace_control_diagnostic', demonstrator_id='ManualClosedTraceReplay'))
        check_runtime_identity(plan, task.release_contract, _json(task.episode_dir / 'release_metadata.json'))
        manifest.update(actual_reset_fingerprint_checked=True, physical_run_started=True,
            project_scene_fingerprint=task.release_contract['frozen_scene_sha256'], episode_id=task.episode_id)
        write(output / 'run_manifest.json', manifest)
        probe = ManualProbe(facade)
        probe.snapshot('closed_trace_initial')
        summary = replay_plan(probe, plan, output)
        probe.snapshot('closed_trace_terminal')
        if not task.ended:
            task.finalize_episode('CLOSED_TRACE_CONTROL_DIAGNOSTIC_END', 'POLICY_BUDGET')
        summary['independent_result'] = task._result
        write(output / 'diagnostic_summary.json', summary)
        print('CLOSED_TRACE_DIAGNOSTIC_RESULT', json.dumps(task._result, default=str), flush=True)
        return 0  # A reproduced physical failure is a valid diagnostic result.
    except BaseException as error:
        import traceback
        write(output / 'runner_failure.json', dict(type=type(error).__name__, error=str(error), traceback=traceback.format_exc()))
        raise
    finally:
        manifest['wall_seconds'] = time.perf_counter() - started
        try:
            if task is not None:
                task.close()
        finally:
            try:
                if app is not None:
                    from omni.kit.app import get_app
                    try:
                        get_app().post_quit(0)
                    finally:
                        app.close()
            finally:
                manifest['implementation_unchanged_during_run'] = implementation_hashes() == manifest['implementation_sha256']
                write(output / 'run_manifest.json', manifest)
                lock.close()


if __name__ == '__main__':
    # Same native-finalizer avoidance as run.py; preserve actual Python errors
    # and argparse codes. Authoritative process-exit proof is written by a parent
    # only after Popen.wait(), never optimistically by this still-running child.
    try:
        code = main()
    except SystemExit as error:
        code = int(error.code or 0)
    except BaseException:
        import traceback
        traceback.print_exc()
        code = 1
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(code)
