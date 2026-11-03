"""CPU-only restoration tests: fake public environment/client, no HTTP/GPU."""
import ast
import copy
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from policy.backends import cubence_tools as current_generic
from policy.backends import cubence_project_v1_1_tools as current_tools
from policy.backends.gpt_debug04_v1.vendor import cubence as original_transport
from policy.backends.gpt_debug04_v1.vendor import cubence_tools as original_generic
from policy.backends.gpt_debug04_v1.vendor import cubence_project_v1_1_tools as original_tools


ROOT = Path(__file__).resolve().parents[1]
IDENTITY = json.loads((ROOT/'docs/lab_cuvette_loading/Gpt_debug04_v1/identity.json').read_text())
MANIFEST = json.loads((ROOT/'policy/backends/gpt_debug04_v1/source_manifest.json').read_text())
PROFILE_PATH = ROOT/'config/lab_cuvette_loading/Gpt_debug04_v1/provider.json'


def config():
    return json.loads(PROFILE_PATH.read_text())


def canonical(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def test_all_three_vendor_files_preserve_exact_git_blob_and_sha():
    assert len(MANIFEST['files']) == 3
    for item in MANIFEST['files']:
        data = (ROOT/item['destination']).read_bytes()
        assert len(data) == item['bytes']
        assert hashlib.sha256(data).hexdigest() == item['sha256']
        assert hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest() == item['source_git_blob']


def test_dependency_imports_close_inside_vendor_namespace():
    allowed = {'cubence', 'cubence_tools', 'cubence_project_v1_1_tools'}
    for item in MANIFEST['files']:
        tree = ast.parse((ROOT/item['destination']).read_bytes())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.level:
                assert node.level == 1 and node.module in allowed
            if isinstance(node, ast.ImportFrom) and not node.level:
                assert not str(node.module).startswith(('policy.', 'demos.', 'tasks.', 'isaac', 'openai'))
    assert original_generic.ProviderError is original_transport.ProviderError
    assert original_tools.ProviderError is original_transport.ProviderError
    assert original_generic.CubenceClient is original_transport.CubenceClient


def test_exact_original_profile_prompt_tools_and_static_task_instruction():
    assert hashlib.sha256(PROFILE_PATH.read_bytes()).hexdigest() == MANIFEST['provider_config']['sha256']
    assert PROFILE_PATH.read_bytes() == (ROOT/'config/lab_cuvette_loading/Project_v1_1/policies/cubence_gpt6_context4_640high.json').read_bytes()
    assert config() == IDENTITY['frozen_policy']['profile_snapshot']
    assert original_tools.SYSTEM_PROMPT == IDENTITY['frozen_policy']['SYSTEM_PROMPT'] == current_tools.SYSTEM_PROMPT
    assert original_generic.tool_definitions() == IDENTITY['frozen_policy']['tool_schema'] == current_generic.tool_definitions()
    assert canonical(original_generic.tool_definitions()) == IDENTITY['frozen_policy']['tool_schema_canonical_sha256']
    prompt = original_tools.SYSTEM_PROMPT+'\nAction limits: '+json.dumps(config()['action_limits'])
    assert hashlib.sha256(prompt.encode()).hexdigest() == IDENTITY['frozen_policy']['actual_instructions_sha256']
    task = IDENTITY['input_evidence']['task_language']
    assert hashlib.sha256(task.encode()).hexdigest() == IDENTITY['input_evidence']['first_public_state']['task_language_sha256']
    for key in ('visual_context', 'fixed_side_detail', 'active_view_control', 'robot_self_state'):
        assert key not in config()


class FakeEnvironment:
    """Robot-receipt protocol fixture; counters are not physical evidence."""
    def __init__(self):
        self.step = 0
        self.position = [.1, .2, 1.]
        self.opening = .08
        self.effort = 8.
        self.ended = False
        self.saved = {}
        self.executions = []
        self.finished = None

    def observe(self):
        return dict(episode_id='cpu-episode', observation_id='cpu-episode:'+str(self.step),
            step_index=self.step, simulation_time=self.step/60,
            images={'side_camera': np.zeros((8, 12, 3), np.uint8),
                    'wrist_camera': np.full((8, 12, 3), 32, np.uint8)},
            joint_positions=[0.]*7+[self.opening/2]*2, joint_velocities=[0.]*9,
            TCPpose=dict(position_m=list(self.position), quaternion_wxyz=[1., 0., 0., 0.]),
            gripper_opening_m=self.opening, gripper_effort_limit_N=self.effort,
            finger_contact_N=[.1, .1], source_slot_id='A1', target_seat_id='candidate_far_hinge',
            task_language=IDENTITY['input_evidence']['task_language'],
            object_position_m=[999., 999., 999.], progress={'stage': 'PRIVATE'},
            teacher_waypoint=[999., 999., 999.], scorer={'task_success': True},
            phase='PRIVATE', debug={'private': True})

    def status(self):
        return dict(episode_id='cpu-episode', terminated=self.ended, simulation_time=self.step/60)

    def receipt(self, action_id):
        return copy.deepcopy(self.saved.get(action_id))

    def execute(self, action):
        assert action['action_id'] not in self.saved
        self.executions.append(copy.deepcopy(action))
        before = self.step
        ticks = round(action['duration_s']*60)
        self.step += ticks
        if action['type'] == 'ee_delta':
            self.position = [a+b for a, b in zip(self.position, action['values'][:3])]
        elif action['type'] == 'ee_pose':
            self.position = list(action['values'][:3])
        self.opening = action['gripper_opening_m']
        self.effort = action['gripper_effort_limit_N']
        endpoint = self.observe()['TCPpose']
        value = dict(action_id=action['action_id'], episode_id='cpu-episode',
            observation_id=action['observation_id'], accepted=True,
            execution_finished=True, target_reached=True, safety_stopped=False,
            completed=True, partial_execution=False, executed_control_ticks=ticks,
            executed_physics_steps=ticks*4, simulation_time_before=before/60,
            simulation_time_after=self.step/60, executed_duration_s=ticks/60,
            observation_id_after='cpu-episode:'+str(self.step), stop_reason='INTERVAL_FINISHED',
            status='FINISHED', requested_target_TCP=endpoint, actual_endpoint_TCP=endpoint,
            TCPpose=endpoint, gripper_opening_m=self.opening,
            requested_gripper_opening_m=self.opening, applied_gripper_opening_m=self.opening,
            requested_effort_limit_N=self.effort, applied_effort_limit_N=self.effort,
            successor_observation_available=True, actual_endpoint_valid=True,
            wall_seconds=.001, object_position_m=[999., 999., 999.],
            plan=dict(planned_ticks=ticks, requested_ticks=ticks, wall_seconds=.001,
                      scope='robot_only_fixture', object_position_m=[999., 999., 999.]))
        self.saved[action['action_id']] = copy.deepcopy(value)
        return value

    def finish(self, reason, *, failure_type=None):
        self.ended = True
        self.finished = dict(task_success=None, termination_reason=reason, failure_type=failure_type)
        return self.finished


class FakeLedger:
    def __init__(self):
        self.calls = 0

    def summary(self):
        return dict(total_network_attempts=self.calls, total_estimated_usd=0.)


class FakeClient:
    """A scripted in-memory protocol fake; never constructs a provider client."""
    def __init__(self):
        self.cfg = config()
        self.ledger = FakeLedger()
        self.payloads = []

    def responses(self, inputs, *, instructions, tools, **kwargs):
        self.payloads.append(copy.deepcopy(dict(inputs=inputs, instructions=instructions, tools=tools)))
        index = self.ledger.calls
        self.ledger.calls += 1
        state = json.loads(inputs[-1]['content'][0]['text'])
        arguments = dict(episode_id=state['episode_id'], observation_id=state['observation_id'])
        if index == 0:
            name = 'gripper'
            arguments.update(action_id='a0', duration_s=.2, opening_m=.01, effort_limit_N=2.)
        elif index == 1:
            name = 'move_ee'
            arguments.update(action_id='a1', duration_s=.5, mode='ee_delta',
                             values=[.005, 0., 0., 0., 0., 0.], frame='world')
        elif index == 2:
            name = 'wait'
            arguments.update(action_id='a2', duration_s=.1)
        else:
            name = 'finish'
            arguments['reason'] = 'CPU protocol fixture finished'
        return (dict(model='gpt-6-astra', id='reply'+str(index), usage=dict(input_tokens=10, output_tokens=5),
            output=[dict(type='function_call', name=name, arguments=json.dumps(arguments), call_id='call'+str(index))]),
            dict(request_id='fixture'+str(index), wall_seconds=.01))


def test_vendor_full_runner_matches_current_no_extension_wire_and_actions(tmp_path, monkeypatch):
    import urllib.request
    monkeypatch.setattr(urllib.request.OpenerDirector, 'open', lambda *a, **k: pytest.fail('Unexpected HTTP'))
    old_env, current_env = FakeEnvironment(), FakeEnvironment()
    old_client, current_client = FakeClient(), FakeClient()
    old_summary = original_tools.run_episode(old_env, old_client, tmp_path/'vendor', max_calls=4)
    current_summary = current_tools.run_episode(current_env, current_client, tmp_path/'current', max_calls=4)
    assert old_client.payloads == current_client.payloads
    assert old_env.executions == current_env.executions
    assert old_env.step == current_env.step == 48
    assert old_summary['api_decisions'] == current_summary['api_decisions'] == 4
    assert old_env.executions[-1]['gripper_opening_m'] == .01
    assert old_env.executions[-1]['gripper_effort_limit_N'] == 2.
    frozen = json.loads((tmp_path/'vendor/controller.json').read_text())
    assert canonical(frozen) == IDENTITY['frozen_policy']['historical_controller_canonical_sha256']
    assert all('temporal_visual_context' not in str(p) for p in (tmp_path/'vendor').rglob('*'))
    # The fake private sentinels must not reach either model payload.
    wire = json.dumps(old_client.payloads)
    for text in ('object_position_m', 'teacher_waypoint', '"scorer"', '"progress"', '"debug"'):
        assert text not in wire


def test_vendor_and_current_public_observation_JPEG_encoding_are_equal():
    environment = FakeEnvironment()
    old = original_generic.observation_content(environment.observe(), image_config=config()['images'])
    current = current_generic.observation_content(environment.observe(), image_config=config()['images'])
    assert old == current
    public = json.loads(old[0]['text'])
    assert public['task_language'] == IDENTITY['input_evidence']['task_language']
    assert len([item for item in old if item['type'] == 'input_image']) == 2
    assert set(public).isdisjoint({'object_position_m', 'progress', 'phase', 'scorer', 'debug'})


def test_vendor_rejects_task_macros_with_vendor_ProviderError_only():
    from policy.backends.cubence import ProviderError as CurrentProviderError
    tool = original_tools.ProjectV11RobotTools(FakeEnvironment(), config()['action_limits'])
    with pytest.raises(original_transport.ProviderError) as error:
        tool.execute('grasp', {})
    assert error.value.code == 'PROTOCOL_UNKNOWN_TOOL'
    assert not isinstance(error.value, CurrentProviderError)
