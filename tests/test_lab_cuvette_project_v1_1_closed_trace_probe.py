"""CPU fixtures only: declared replay semantics, closure and normal admission.

These tests use the real ManualProbe/ProjectV11RobotTools adapter with a tiny
receipt environment. Its counter/pose changes are not physics evidence.
"""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from types import ModuleType

import numpy as np
import pytest

from demos.lab_cuvette_project_v1_1 import closed_trace_probe as replay
from demos.lab_cuvette_project_v1_1.probes import ManualProbe


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + '\n')
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def closed(tmp_path):
    run = tmp_path / 'closed_run'
    episode = run / 'episode_0000'
    control = episode / 'gpt_control'
    source = control / 'policy_trace.jsonl'
    proof = run / 'process_exit.json'
    asset_sha, commit = 'a' * 64, '1' * 40
    config = dict(scene_mode='standard', env=dict(mode='standard', scene_randomization_enabled=False),
        randomization=dict(enabled=False), asset_id='cuvette_xy_1000',
        vessel=dict(asset_id='cuvette_xy_1000'), asset_selection=dict(asset_sha256=asset_sha))
    contract = dict(schema='labsim.Project_v1_1.scene_contract.v1', config=config,
        dependencies={}, assets={'assets/cup.usda': asset_sha}, acceptance_version='Project_v1_1.independent.v1')
    fingerprint = hashlib.sha256(replay.canonical(contract)).hexdigest()
    contract['frozen_scene_sha256'] = fingerprint
    dump(episode / 'project_scene_contract.json', contract)
    dump(episode / 'release_metadata.json', dict(scene_version='Project_v1_1', scene_mode='standard',
        frozen_scene_sha256=fingerprint, control_config_sha256=fingerprint,
        code_commit=commit, actual_execution_commit=commit, asset_id='cuvette_xy_1000', asset_sha256=asset_sha))
    dump(episode / 'result.json', dict(episode_id='old', asset_id='cuvette_xy_1000', seed=0))
    dump(episode / 'options.json', dict(mode='standard', teacher=False))
    dump(run / 'geometry_audit.json', dict(geometry_valid=True, binding=dict(files=contract['assets'])))
    dump(run / 'run_manifest.json', dict(backend='gpt6', episodes_completed=1, project_scene_fingerprint=fingerprint))
    dump(run / 'launch_config.yaml', config)  # JSON is also valid YAML; fixture never starts Isaac.
    limits = json.loads(replay.LIMITS_CONFIG.read_text())['action_limits']
    dump(control / 'controller.json', dict(provider_config=dict(action_limits=limits)))
    events = []
    for decision in range(3):
        arguments = dict(episode_id='old', observation_id='old:' + str(decision * 120),
            action_id='a' + str(decision + 1), mode='ee_delta', frame='world',
            values=[.035 if decision == 2 else .01, 0, 0, 0, 0, 0], duration_s=2)
        event = dict(event='error' if decision == 2 else 'decision', decision_index=decision,
            episode_id='old', observation_id=arguments['observation_id'])
        call = dict(name='move_ee', arguments=json.dumps(arguments) if decision == 2 else arguments)
        if decision == 2:
            event.update(model_tool_calls=[call], action_receipt=dict(partial_execution=True,
                executed_control_ticks=114, stop_reason='ROBOT_ENVIRONMENT_COLLISION'))
        else:
            event['tool_call'] = call
        relative = 'observations/decision_' + str(decision)
        public_path = relative + '/public_observation.json'
        public_sha = dump(control / public_path, dict(episode_id='old', observation_id=arguments['observation_id']))
        public = dict(path=public_path, sha256=public_sha, bytes=(control / public_path).stat().st_size)
        image_path = relative + '/wrist_camera.jpg'
        (control / image_path).write_bytes(b'CPU image provenance fixture')
        image = dict(path=image_path, sha256=replay.sha256(control / image_path), bytes=(control / image_path).stat().st_size)
        manifest = dict(episode_id='old', observation_id=arguments['observation_id'], public_observation=public, images=[image])
        manifest_path = relative + '/manifest.json'
        manifest_sha = dump(control / manifest_path, manifest)
        event['observation_artifacts'] = dict(manifest_path=manifest_path, manifest_sha256=manifest_sha,
            public_observation=public, images=[image])
        events.append(event)
    source.write_text('\n'.join(json.dumps(event) for event in events) + '\n')
    dump(proof, dict(run_directory=str(run), process_exited=True, pid=999999999,
        exit_code=0, runtime_commit=commit, command=['python', '-m', 'fixture', '--output', str(run)]))
    return SimpleNamespace(run=run, episode=episode, source=source, proof=proof,
        events=events, contract=contract, limits=limits)


def plan(closed, **kwargs):
    return replay.preflight(closed.source, closed.proof, process_exists=lambda pid: False, **kwargs)


def test_default_keeps_error_row_command_and_all_source_values(closed):
    value = plan(closed)
    assert value['recorded_actions'] == value['prefix_actions'] == 3
    assert value['mode'] == 'unchanged_closed_trace'
    final = value['actions'][-1]
    assert final['source_event'] == 'error' and final['source_decision_index'] == 2 and final['source_line'] == 3
    assert final['arguments'] == json.loads(closed.events[-1]['model_tool_calls'][0]['arguments'])
    assert final['arguments']['values'] == [.035, 0, 0, 0, 0, 0]
    assert final['arguments']['duration_s'] == 2  # Not the source's partial 1.9 seconds.
    assert value['model_calls'] == 0 and value['diagnostic_not_GPT_demonstration'] is True
    assert value['condition_group'] == 'control_diagnostic' and value['full_loading_training_admission'] is False
    body = {key: item for key, item in value.items() if key != 'derived_plan_sha256'}
    assert value['derived_plan_sha256'] == hashlib.sha256(replay.canonical(body)).hexdigest()


@pytest.mark.parametrize('field,value,match', [
    ('process_exited', False, 'completed Popen'), ('pid', 0, 'positive PID'),
    ('exit_code', None, 'exit_code'), ('exit_code', True, 'exit_code'),
    ('run_directory', '/another_run', 'run_directory'), ('runtime_commit', 'short', 'exact runtime commit'),
    ('runtime_commit', '2' * 40, 'commit identity'), ('command', ['python'], 'output identity')])
def test_refuses_incomplete_or_mismatched_closure_proof(closed, field, value, match):
    proof = json.loads(closed.proof.read_text())
    proof[field] = value
    dump(closed.proof, proof)
    with pytest.raises(ValueError, match=match):
        plan(closed)


def test_refuses_live_or_reused_source_pid(closed):
    with pytest.raises(ValueError, match='PID still exists'):
        replay.preflight(closed.source, closed.proof, process_exists=lambda pid: True)


def test_explicit_nonzero_native_exit_is_preserved_as_source_evidence(closed):
    proof = json.loads(closed.proof.read_text())
    proof['exit_code'] = 139
    dump(closed.proof, proof)
    assert plan(closed)['run_identity']['process_exit_code'] == 139


@pytest.mark.parametrize('kind', ['image', 'public', 'manifest'])
def test_refuses_corrupted_public_evidence_including_final_error_row(closed, kind):
    artifacts = closed.events[-1]['observation_artifacts']
    name = artifacts['images'][0]['path'] if kind == 'image' else artifacts['public_observation']['path'] if kind == 'public' else artifacts['manifest_path']
    (closed.source.parent / name).write_bytes(b'changed source')
    with pytest.raises(ValueError, match='SHA/size mismatch'):
        plan(closed)


def test_refuses_source_trace_result_identity_mismatch(closed):
    dump(closed.episode / 'result.json', dict(episode_id='different', asset_id='cuvette_xy_1000', seed=0))
    with pytest.raises(ValueError, match='trace/result/release identity'):
        plan(closed)


def test_declared_suffix_replaces_only_the_explicit_boundary(closed, tmp_path):
    suffix_path = tmp_path / 'suffix.json'
    actions = [dict(tool='observe', arguments={}),
        dict(tool='gripper', arguments=dict(opening_m=.009, effort_limit_N=4, duration_s=1)),
        dict(tool='move_ee', arguments=dict(mode='ee_delta', values=[0, 0, .02, 0, 0, 0], frame='world', duration_s=2)),
        dict(tool='wait', arguments=dict(duration_s=.5))]
    dump(suffix_path, dict(schema=replay.SUFFIX_SCHEMA, description='Explicit manual raised-height collision control', actions=actions))
    value = plan(closed, prefix_actions=2, suffix_plan=suffix_path)
    assert value['prefix_actions'] == 2 and len(value['actions']) == 6
    assert value['actions'][:2] == plan(closed)['actions'][:2]
    assert [dict(tool=a['tool'], arguments=a['arguments']) for a in value['actions'][2:]] == actions
    assert value['actions'][2]['origin'] == 'explicit_manual_suffix'
    assert value['suffix_plan_sha256'] == replay.sha256(suffix_path)
    assert value['derived_plan_sha256'] != plan(closed)['derived_plan_sha256']


@pytest.mark.parametrize('prefix', [-1, 4, True])
def test_refuses_undeclared_or_invalid_prefix_boundaries(closed, prefix):
    with pytest.raises(ValueError, match='prefix-actions'):
        plan(closed, prefix_actions=prefix)


@pytest.mark.parametrize('tool,args', [
    ('finish', dict(reason='pretend success')), ('grasp', {}),
    ('wait', dict(duration_s=1, action_id='fixed')),
    ('move_ee', dict(mode='ee_delta', values=[.06, 0, 0, 0, 0, 0], frame='world', duration_s=3)),
    ('gripper', dict(opening_m=.009, effort_limit_N=99, duration_s=1)),
    ('wait', dict(duration_s=1, object_position=[1, 2, 3]))])
def test_suffix_allows_only_explicit_legal_generic_parameters(closed, tool, args):
    with pytest.raises(ValueError):
        replay.validate_parameters(tool, args, closed.limits, suffix=True)


def test_suffix_requires_explicit_prefix_argument(closed, tmp_path):
    suffix = tmp_path / 'suffix.json'
    dump(suffix, dict(schema=replay.SUFFIX_SCHEMA, description='Manual hold', actions=[dict(tool='wait', arguments=dict(duration_s=1))]))
    with pytest.raises(ValueError, match='explicit --prefix-actions'):
        plan(closed, suffix_plan=suffix)


def test_snapshot_contains_full_original_trace_and_verifies_all_consumed_sources(closed, tmp_path, monkeypatch):
    value = plan(closed)
    monkeypatch.setattr(replay, 'pid_exists', lambda pid: False)
    destination = tmp_path / 'new'
    replay.snapshot_sources(value, destination)
    assert (destination / 'source_evidence/episode/gpt_control/policy_trace.jsonl').read_bytes() == closed.source.read_bytes()
    for item in value['source_files']:
        assert replay.sha256(destination / item['snapshot_path']) == item['sha256']
    closed.source.write_text(closed.source.read_text() + '\n')
    with pytest.raises(ValueError, match='changed after preflight'):
        replay.verify_sources(value, process_exists=lambda pid: False)


class ReceiptEnvironment:
    def __init__(self, output, modes=()):
        self.step, self.executions, self.saved = 0, [], {}
        self.modes = list(modes)
        self.position = np.array([.1, .2, 1.05])
        self.task = SimpleNamespace(episode_dir=output, ended=False)
        output.mkdir()

    def observe(self):
        return dict(episode_id='new', observation_id='new:' + str(self.step), simulation_time=self.step / 60,
            joint_positions=[0.] * 7 + [.0053, .0053], joint_velocities=[0.] * 9,
            TCPpose=dict(position_m=self.position.tolist(), quaternion_wxyz=[1., 0., 0., 0.]),
            gripper_opening_m=.0106, gripper_effort_limit_N=4., finger_contact_N=[.3, .31],
            images={'side_camera': np.zeros((3, 4, 3), np.uint8), 'wrist_camera': np.zeros((3, 4, 3), np.uint8)})

    def status(self):
        return dict(episode_id='new', terminated=self.task.ended, simulation_time=self.step / 60)

    def receipt(self, action_id):
        return copy.deepcopy(self.saved.get(action_id))

    def execute(self, action):
        self.executions.append(copy.deepcopy(action))
        before, ticks = self.step, round(action['duration_s'] * 60)
        partial = bool(self.modes and self.modes.pop(0) == 'partial')
        if partial:
            ticks -= 6
            self.task.ended = True
        self.step += ticks
        if action['type'] == 'ee_delta':
            self.position += np.asarray(action['values'][:3]) * ticks / round(action['duration_s'] * 60)
        else:
            self.position[:] = action['values'][:3]
        receipt = dict(action_id=action['action_id'], episode_id='new', observation_id=action['observation_id'],
            accepted=True, execution_finished=True, target_reached=not partial, safety_stopped=partial,
            completed=True, partial_execution=partial, executed_control_ticks=ticks,
            executed_physics_steps=ticks * 4, simulation_time_before=before / 60,
            simulation_time_after=self.step / 60, executed_duration_s=ticks / 60,
            stop_reason='ROBOT_ENVIRONMENT_COLLISION' if partial else 'INTERVAL_FINISHED',
            actual_endpoint_TCP=self.observe()['TCPpose'], requested_target_TCP=self.observe()['TCPpose'])
        self.saved[action['action_id']] = receipt
        return copy.deepcopy(receipt)


def test_actual_manual_probe_and_generic_tools_rebind_only_ids(closed, tmp_path):
    value = plan(closed)
    env = ReceiptEnvironment(tmp_path / 'episode')
    probe = ManualProbe(env)
    summary = replay.replay_plan(probe, value, tmp_path)
    assert len(env.executions) == summary['actions_attempted'] == 3
    for index, (source, record, action) in enumerate(zip(value['actions'], probe.records, env.executions)):
        assert {k: v for k, v in record['arguments'].items() if k not in replay.IDENTITIES} == {
            k: v for k, v in source['arguments'].items() if k not in replay.IDENTITIES}
        assert record['arguments']['episode_id'] == 'new'
        assert record['arguments']['action_id'] == f'diagnostic-{index:05d}'
        assert record['arguments']['observation_id'] == 'new:' + str(index * 120)
        assert action['model_action_id'] == record['arguments']['action_id']
        assert action['values'] == source['arguments']['values'] and action['duration_s'] == source['arguments']['duration_s']
        assert record['closed_trace_provenance']['source_decision_index'] == index
    assert probe.records[-1]['closed_trace_provenance']['source_event'] == 'error'
    assert summary['all_declared_actions_attempted'] is True and summary['model_calls'] == 0


def test_partial_collision_keeps_real_receipt_and_does_not_execute_suffix(closed, tmp_path):
    value = plan(closed)
    value['actions'].append(dict(origin='explicit_manual_suffix', suffix_index=0, tool='wait', arguments=dict(duration_s=1)))
    env = ReceiptEnvironment(tmp_path / 'episode', modes=['ok', 'ok', 'partial'])
    probe = ManualProbe(env)
    summary = replay.replay_plan(probe, value, tmp_path)
    assert len(env.executions) == 3 and env.step == 354
    assert summary['actions_attempted'] == 3 and summary['declared_actions'] == 4
    assert summary['stop_reason'] == 'TOOL_ERROR' and summary['all_declared_actions_attempted'] is False
    final = summary['actions'][-1]
    assert final['receipt']['partial_execution'] is True
    assert final['receipt']['executed_control_ticks'] == 114 and final['receipt']['stop_reason'] == 'ROBOT_ENVIRONMENT_COLLISION'
    assert final['closed_trace_provenance']['source_event'] == 'error'


def test_explicit_observe_gripper_wait_suffix_uses_same_generic_tools(closed, tmp_path):
    suffix = tmp_path / 'suffix.json'
    dump(suffix, dict(schema=replay.SUFFIX_SCHEMA, description='Explicit contact and lift probe', actions=[
        dict(tool='observe', arguments={}),
        dict(tool='gripper', arguments=dict(opening_m=.009, effort_limit_N=3, duration_s=1)),
        dict(tool='move_ee', arguments=dict(mode='ee_delta', values=[0, 0, .0001, 0, 0, 0], frame='tcp', duration_s=.1)),
        dict(tool='wait', arguments=dict(duration_s=.5))]))
    value = plan(closed, prefix_actions=0, suffix_plan=suffix)
    env = ReceiptEnvironment(tmp_path / 'episode')
    probe = ManualProbe(env)
    summary = replay.replay_plan(probe, value, tmp_path)
    assert summary['all_declared_actions_attempted'] is True
    assert len(probe.records) == 4 and len(env.executions) == 3
    assert env.step == 60 + 6 + 30
    assert env.executions[1]['frame'] == 'tcp' and env.executions[1]['values'][2] == .0001
    assert env.executions[1]['gripper_opening_m'] == env.executions[2]['gripper_opening_m'] == .009
    assert env.executions[1]['gripper_effort_limit_N'] == env.executions[2]['gripper_effort_limit_N'] == 3


def test_runtime_fingerprint_and_reset_asset_must_match_source(closed):
    value = plan(closed)
    metadata = json.loads((closed.episode / 'release_metadata.json').read_text())
    metadata['condition_group'] = 'control_diagnostic'
    replay.check_runtime_identity(value, closed.contract, metadata)
    changed = copy.deepcopy(closed.contract)
    changed['frozen_scene_sha256'] = 'f' * 64
    with pytest.raises(ValueError, match='fingerprint differs'):
        replay.check_runtime_identity(value, changed, metadata)
    metadata['asset_sha256'] = 'b' * 64
    with pytest.raises(ValueError, match='asset_sha256'):
        replay.check_runtime_identity(value, closed.contract, metadata)


def test_dry_run_creates_no_output_and_never_initializes_provider_or_simulator(closed, tmp_path, monkeypatch, capsys):
    import policy.backends.cubence as cubence
    def forbidden(*args, **kwargs):
        pytest.fail('CPU dry-run tried to initialize a provider or simulator')
    monkeypatch.setattr(cubence.CubenceClient, '__init__', forbidden)
    monkeypatch.setitem(sys.modules, 'isaacsim', SimpleNamespace(SimulationApp=forbidden))
    monkeypatch.setattr(replay, 'OUTPUT_ROOT', tmp_path)
    output = tmp_path / 'not_created'
    assert replay.main(['--source', str(closed.source), '--proof', str(closed.proof),
        '--output', str(output), '--dry-run']) == 0
    value = json.loads(capsys.readouterr().out)
    assert value['prefix_actions'] == 3 and value['model_calls'] == 0 and not output.exists()


def test_bad_source_and_existing_output_are_rejected_before_output_or_runtime_import(closed, tmp_path):
    output = tmp_path / 'unused'
    proof = json.loads(closed.proof.read_text())
    proof['process_exited'] = False
    dump(closed.proof, proof)
    with pytest.raises(ValueError, match='completed Popen'):
        replay.main(['--source', str(closed.source), '--proof', str(closed.proof), '--output', str(output)])
    assert not output.exists()
    output.mkdir()
    with pytest.raises(FileExistsError, match='overwrite'):
        replay.main(['--source', str(closed.source), '--proof', str(closed.proof), '--output', str(output)])


def test_help_is_cpu_only_and_successful():
    result = subprocess.run([sys.executable, '-m', 'demos.lab_cuvette_project_v1_1.closed_trace_probe', '--help'],
        cwd=replay.ROOT, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    assert '--dry-run' in result.stdout and '--prefix-actions' in result.stdout and '--suffix-plan' in result.stdout


def test_output_accepts_only_new_sibling_directories_in_current_or_verified_proof_version_base(closed, tmp_path, monkeypatch):
    current = tmp_path / 'clean_checkout/outputs/lab_cuvette_loading/Project_v1_1'
    source_base = tmp_path / 'source_checkout/outputs/lab_cuvette_loading/Project_v1_1'
    monkeypatch.setattr(replay, 'OUTPUT_ROOT', current)
    value = plan(closed)
    value['run_identity']['run_directory'] = str(source_base / 'gpt_debug_05')
    assert replay.isolated_output(current / 'new_probe', value) == current / 'new_probe'
    assert replay.isolated_output(source_base / 'new_probe', value) == source_base / 'new_probe'
    assert not current.exists() and not source_base.exists()


@pytest.mark.parametrize('kind', ['source_child', 'source_ancestor', 'asset', 'historical_version', 'arbitrary', 'existing_run_child', 'traversal'])
def test_output_cannot_pollute_sources_assets_history_or_existing_runs(closed, tmp_path, monkeypatch, kind):
    allowed = tmp_path / 'outputs/lab_cuvette_loading/Project_v1_1'
    allowed.mkdir(parents=True)
    (allowed / 'old_run').mkdir()
    monkeypatch.setattr(replay, 'OUTPUT_ROOT', allowed)
    value = plan(closed)
    choices = dict(source_child=closed.run / 'new_probe', source_ancestor=closed.run.parent,
        asset=tmp_path / 'assets/new_probe', historical_version=tmp_path / 'outputs/lab_cuvette_loading/V0/new_probe',
        arbitrary=tmp_path / 'elsewhere/new_probe', existing_run_child=allowed / 'old_run/new_probe',
        traversal=allowed / '../Project_v1_1/new_probe')
    with pytest.raises((ValueError, FileExistsError)):
        replay.isolated_output(choices[kind], value)
    assert not (allowed / 'new_probe').exists()


def test_output_refuses_existing_and_broken_symlink_components(closed, tmp_path, monkeypatch):
    actual = tmp_path / 'actual/outputs/lab_cuvette_loading/Project_v1_1'
    actual.mkdir(parents=True)
    monkeypatch.setattr(replay, 'OUTPUT_ROOT', actual)
    link = tmp_path / 'linked'
    link.symlink_to(actual.parent.parent.parent, target_is_directory=True)
    with pytest.raises(ValueError, match='symlinks'):
        replay.isolated_output(link / 'outputs/lab_cuvette_loading/Project_v1_1/new_probe', plan(closed))
    broken = actual / 'broken'
    broken.symlink_to(tmp_path / 'absent')
    with pytest.raises(ValueError, match='symlinks'):
        replay.isolated_output(broken, plan(closed))


def cpu_module(**values):
    result = ModuleType('closed_trace_cpu_stub')
    result.__dict__.update(values)
    return result


@pytest.mark.parametrize('failure', [False, True])
def test_native_lifecycle_checks_reset_identity_and_closes_every_resource(closed, tmp_path, monkeypatch, failure):
    from omegaconf import OmegaConf
    import fcntl
    from demos.lab_cuvette_project_v1 import runtime
    from demos.lab_cuvette_project_v1_1 import contract, probes, run
    events = []
    output = tmp_path / 'native_cpu_stub'
    cfg = OmegaConf.create(dict(task_type='cpu', physics=dict(hz=240, control_hz=60),
        env=dict(execution_purpose='collect'), experiment=dict(condition_group='natural')))
    monkeypatch.setattr(replay, 'OUTPUT_ROOT', tmp_path)
    monkeypatch.setattr(runtime, 'resolve_config', lambda value: cfg)
    monkeypatch.setattr(run, 'ensure_audit', lambda *args: dict(geometry_valid=True))
    monkeypatch.setattr(contract, 'scene_contract', lambda *args: copy.deepcopy(closed.contract))
    monkeypatch.setattr(replay, 'open', lambda *args: SimpleNamespace(close=lambda: events.append('lock.close')), raising=False)
    monkeypatch.setattr(fcntl, 'flock', lambda *args: events.append('lock.acquire'))
    def create_app(settings):
        assert settings['fast_shutdown'] is False
        events.append('app.create')
        return SimpleNamespace(close=lambda: events.append('app.close'))
    monkeypatch.setitem(sys.modules, 'isaacsim', cpu_module(SimulationApp=create_app))
    task = SimpleNamespace(ended=False, episode_id='new', release_contract=copy.deepcopy(closed.contract), _result=None)
    def create_task(*args, **kwargs):
        task.episode_dir = output / 'episode_0000'
        task.episode_dir.mkdir()
        events.append('task.create')
        return task
    def reset(seed, options):
        assert seed == 0 and options['teacher'] is False and options['mode'] == 'standard'
        assert cfg.experiment.condition_group == 'control_diagnostic' and cfg.env.execution_purpose == 'eval'
        metadata = json.loads((closed.episode / 'release_metadata.json').read_text())
        metadata['condition_group'] = 'control_diagnostic'
        dump(task.episode_dir / 'release_metadata.json', metadata)
        events.append('reset')
    def finalize(reason, failure_type):
        task.ended = True
        task._result = dict(task_success=False, record_valid=True, termination_reason=reason)
        events.append('finalize')
    task.finalize_episode = finalize
    task.close = lambda: events.append('task.close')
    class Probe:
        def __init__(self, facade):
            self.task = task
        def snapshot(self, stage):
            events.append(stage)
    def run_plan(probe, value, destination):
        events.append('replay')
        assert value['actions'][-1]['source_event'] == 'error'
        if failure:
            raise RuntimeError('CPU_REPLAY_FAILURE')
        return dict(actions_attempted=3)
    monkeypatch.setattr(probes, 'ManualProbe', Probe)
    monkeypatch.setattr(replay, 'replay_plan', run_plan)
    monkeypatch.setitem(sys.modules, 'factories.task_factory', cpu_module(create_task=create_task))
    monkeypatch.setitem(sys.modules, 'demos.lab_cuvette_project_v1_1.environment',
        cpu_module(ProjectEnvironment=lambda value: SimpleNamespace(reset=reset)))
    monkeypatch.setitem(sys.modules, 'omni.kit.app',
        cpu_module(get_app=lambda: SimpleNamespace(post_quit=lambda code: events.append('app.post_quit'))))
    arguments = ['--source', str(closed.source), '--proof', str(closed.proof), '--output', str(output), '--headless']
    if failure:
        with pytest.raises(RuntimeError, match='CPU_REPLAY_FAILURE'):
            replay.main(arguments)
        assert json.loads((output / 'runner_failure.json').read_text())['error'] == 'CPU_REPLAY_FAILURE'
    else:
        assert replay.main(arguments) == 0
        assert json.loads((output / 'diagnostic_summary.json').read_text())['independent_result']['task_success'] is False
    assert events[-4:] == ['task.close', 'app.post_quit', 'app.close', 'lock.close']
    manifest = json.loads((output / 'run_manifest.json').read_text())
    assert manifest['actual_reset_fingerprint_checked'] is True and manifest['model_calls'] == 0
    assert manifest['condition_group'] == 'control_diagnostic' and manifest['full_loading_training_admission'] is False
    assert manifest['implementation_unchanged_during_run'] is True


@pytest.mark.parametrize('body,code', [('return 7', 7), ("raise RuntimeError('CPU_FAILURE')", 1),
    ('raise SystemExit(2)', 2)])
def test_native_exit_wrapper_retains_real_code_without_importing_isaac(body, code):
    import ast
    guard = ast.parse(Path(replay.__file__).read_text()).body[-1]
    wrapper = ast.unparse(ast.Module(body=[guard], type_ignores=[]))
    program = 'import sys, os\ndef main():\n    print("CPU_EXIT")\n    ' + body + '\n' + wrapper
    result = subprocess.run([sys.executable, '-c', program], capture_output=True, text=True, timeout=15)
    assert result.returncode == code and 'CPU_EXIT' in result.stdout


@pytest.mark.parametrize('success', [True, False])
def test_normal_full_loading_reader_refuses_control_diagnostic_without_relabelling(tmp_path, success):
    h5py = pytest.importorskip('h5py')
    pytest.importorskip('torch')
    pytest.importorskip('cv2')
    pytest.importorskip('zarr')
    from data_collectors.lab_cuvette_project_v1_1_collector import LabCuvetteProjectV11Collector
    from policy.dataset.lab_cuvette_project_v1_1_dataset import LabCuvetteProjectV11Dataset
    from scripts.read_lab_cuvette_project_v1_data import read_check
    collector = LabCuvetteProjectV11Collector(dict(version='Project_v1_1', physics=dict(hz=240, control_hz=60)),
        tmp_path / 'fixture', save_video=False)
    collector.begin_episode(0, episode_id='cpu', metadata=dict(task_type='loading', condition_group='control_diagnostic',
        scene_mode='standard', scene_version='Project_v1_1', frozen_scene_sha256='a' * 64))
    def state(t):
        return dict(episode_id='cpu', simulation_time=t, step_index=round(t * 60), joint_positions=np.zeros(9),
            phase='CPU_FIXTURE', camera_data={name: np.full((3, 4, 4), 90, np.uint8) for name in ('side_camera_rgb', 'wrist_camera_rgb')})
    for tick in range(3):
        collector.cache_transition(state(tick / 60), dict(command_q=np.zeros(9), gripper_effort_limit_N=[3, 3],
            gripper_target_m=.009), state((tick + 1) / 60), dict(terminated=False))
    score = dict(episode_id='cpu', task_type='loading', record_valid=True, task_success=success, geometry_valid=True,
        failure_type='NONE' if success else 'SAFETY_COLLISION', termination_reason='CPU_FIXTURE',
        failure_domain='none' if success else 'safety', physics_trustworthy=True, success_bc_eligible=success,
        task_result=dict(success=success, status='success' if success else 'failure'))
    collector.finish_episode({}, score)
    collector.close()
    before = replay.sha256(collector.path)
    with h5py.File(collector.path, 'r') as source:
        assert bool(source.attrs['task_success']) is success
        assert bool(source.attrs['record_valid']) is True
        assert source.attrs['condition_group'] == 'control_diagnostic'
    with pytest.raises(ValueError, match='Unknown condition group'):
        read_check(collector.path, policies=('act',), sample_filter='success' if success else 'failure',
            dataset_class=LabCuvetteProjectV11Dataset)
    assert replay.sha256(collector.path) == before
