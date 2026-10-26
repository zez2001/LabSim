"""Real checked runner with deterministic robot-tool stubs; no physics claims."""
import copy
import json
from types import SimpleNamespace

import numpy as np
import pytest
from scipy.spatial.transform import Rotation

from demos.lab_cuvette_project_v1_1 import checked_probes
from demos.lab_cuvette_project_v1_1.run import parser


class RobotFacade:
    def __init__(self, output, failure=None):
        self.output, self.failure = output, failure
        self.resets, self.probes, self.snapshots = [], [], []
        self.initial = dict(position_m=[.4, .1, .9], quaternion_wxyz=[0., 1., 0., 0.])
        self.task = SimpleNamespace(release_contract=dict(frozen_scene_sha256='a' * 64))
        self.task.finalize_episode = self.finalize

    def reset(self, seed, options):
        self.resets.append((seed, copy.deepcopy(options)))
        self.pose = copy.deepcopy(self.initial)
        self.episode_index = len(self.resets) - 1
        self.task.episode_dir = self.output / f'episode_{self.episode_index:04d}'
        self.task.episode_dir.mkdir()
        self.task.ended, self.task._result, self.t = False, None, 0.

    def observe(self):
        return dict(TCPpose=copy.deepcopy(self.pose))

    def finalize(self, reason, failure_type):
        self.task.ended = True
        self.task._result = dict(termination_reason=reason, failure_type=failure_type,
            task_success=None, task_type='control_diagnostic')


class RobotToolProbe:
    def __init__(self, facade):
        self.facade, self.task = facade, facade.task
        self.tools = SimpleNamespace(observe=facade.observe)
        self.records = []
        facade.probes.append(self)

    def snapshot(self, stage):
        self.facade.snapshots.append((self.facade.episode_index, stage))

    def call(self, name, **arguments):
        before = self.facade.observe()['TCPpose']
        record = dict(tool=name, arguments=copy.deepcopy(arguments), start_TCP=before)
        self.records.append(record)
        mode = arguments.get('mode')
        failure = self.facade.failure if self.facade.episode_index == 0 else None
        rejected = (failure == 'anchor_call' and len(self.records) == 1
            or failure == 'signed_call' and mode == 'ee_delta'
            or failure == 'wait_call' and name == 'wait'
            or failure == 'close_call' and name == 'gripper' and arguments['opening_m'] == .06)
        if rejected:
            record['receipt'] = dict(accepted=False, target_reached=False)
            return False
        if name == 'move_ee':
            if mode == 'ee_pose':
                values = arguments['values']
                self.facade.pose = dict(position_m=list(values[:3]), quaternion_wxyz=list(values[3:]))
                if failure == 'anchor_orientation':
                    rotation = Rotation.from_quat(np.roll(values[3:], -1))
                    self.facade.pose['quaternion_wxyz'] = np.roll(
                        (Rotation.from_rotvec([0, 0, .01]) * rotation).as_quat(), 1).tolist()
            else:
                values = np.asarray(arguments['values'])
                position = np.asarray(before['position_m'])
                rotation = Rotation.from_quat(np.roll(before['quaternion_wxyz'], -1))
                if arguments['frame'] == 'world':
                    position += values[:3]
                    rotation = Rotation.from_rotvec(values[3:]) * rotation
                else:
                    position += rotation.apply(values[:3])
                    rotation = rotation * Rotation.from_rotvec(values[3:])
                self.facade.pose = dict(position_m=position.tolist(), quaternion_wxyz=np.roll(rotation.as_quat(), 1).tolist())
        self.facade.t += arguments['duration_s']
        record.update(receipt=dict(accepted=True, target_reached=True),
            actual_endpoint_TCP=self.facade.observe()['TCPpose'])
        return True


def run(tmp_path, monkeypatch, failure=None):
    facade = RobotFacade(tmp_path, failure=failure)
    monkeypatch.setattr(checked_probes, 'ManualProbe', RobotToolProbe)
    assert checked_probes.run_checked_free_space(facade, tmp_path) == 0
    return facade, json.loads((tmp_path / 'diagnostic_summary.json').read_text()), json.loads(
        (tmp_path / 'free_space_plan.json').read_text())


def test_checked_runner_resets_three_times_and_records_all_72_fixed_pose_probes(tmp_path, monkeypatch):
    facade, summary, plan = run(tmp_path, monkeypatch)
    assert len(facade.resets) == len(summary) == 3
    assert [row['group'] for row in summary] == ['pose0_world', 'pose1_world', 'pose1_tcp']
    assert all(seed == 0 and options['teacher'] is False and
        options['policy_id'] == 'deterministic_control_diagnostic' for seed, options in facade.resets)
    definitions = []
    for row, group in zip(summary, plan['episodes']):
        assert row['signed_probes_completed'] == 24 and row['full_diagnostic_passed'] is True
        assert row['failure'] is None
        assert row['result']['task_success'] is None  # Diagnostic pass is not loading success.
        assert all(check['reached'] for check in row['anchor_checks'])
        probes = [action for action in row['actions'] if 'probe_definition' in action]
        assert len(probes) == 24
        for record in probes:
            definition = record['probe_definition']
            definitions.append(definition)
            np.testing.assert_allclose(definition['actual_start']['position_m'], group['anchor_pose']['position_m'], atol=1e-14)
            actual_r = Rotation.from_quat(np.roll(definition['actual_start']['quaternion_wxyz'], -1))
            anchor_r = Rotation.from_quat(np.roll(group['anchor_pose']['quaternion_wxyz'], -1))
            assert (actual_r * anchor_r.inv()).magnitude() < 1e-12
            np.testing.assert_allclose(record['actual_endpoint_TCP']['position_m'],
                definition['expected_endpoint_if_exact_anchor']['position_m'], atol=1e-14)
            assert definition['anchor_start_check']['orientation_error_rad'] < 1e-12
        epilogue = [action for action in row['actions'] if action['tool'] in ('wait', 'gripper')]
        assert [action['tool'] for action in epilogue] == ['wait', 'gripper', 'gripper']
        assert row['actions'][-1]['arguments']['duration_s'] == 3.
        assert row['actions'][-1]['arguments']['values'] == group['anchor_pose']['position_m'] + group['anchor_pose']['quaternion_wxyz']
    assert len(definitions) == len({definition['probe_id'] for definition in definitions}) == 72
    manifest = json.loads((tmp_path / 'run_manifest.json').read_text())
    assert manifest['episodes_completed'] == 3 and manifest['model_calls'] == 0
    assert manifest['full_pose_anchor'] is True and manifest['independent_group_reset'] is True


@pytest.mark.parametrize('failure,expected,completed', [('anchor_call', 'FULL_POSE_ANCHOR_NOT_REACHED', 0),
    ('anchor_orientation', 'FULL_POSE_ANCHOR_NOT_REACHED', 0),
    ('signed_call', 'SIGNED_PROBE_NOT_COMPLETED', 0)])
def test_anchor_and_signed_failures_do_not_continue_into_epilogue(tmp_path, monkeypatch, failure, expected, completed):
    facade, summary, _ = run(tmp_path, monkeypatch, failure=failure)
    failed = summary[0]
    assert failed['failure'] == expected and failed['signed_probes_completed'] == completed
    assert failed['full_diagnostic_passed'] is False
    assert all(action['tool'] not in ('wait', 'gripper') for action in failed['actions'])
    assert not any(action['arguments'].get('duration_s') == 3. for action in failed['actions'])
    if failure == 'anchor_orientation':
        assert failed['anchor_checks'][0]['position_error_m'] == 0
        assert failed['anchor_checks'][0]['orientation_error_rad'] == pytest.approx(.01)
    assert len(facade.resets) == 3  # Later independent groups keep their own records.
    assert all(row['full_diagnostic_passed'] for row in summary[1:])


@pytest.mark.parametrize('failure,expected_tools', [('wait_call', ['wait']), ('close_call', ['wait', 'gripper'])])
def test_epilogue_failure_stops_before_later_open_or_hold(tmp_path, monkeypatch, failure, expected_tools):
    _, summary, _ = run(tmp_path, monkeypatch, failure=failure)
    failed = summary[0]
    assert failed['signed_probes_completed'] == 24
    assert failed['failure'] == 'EPILOGUE_NOT_COMPLETED' and failed['full_diagnostic_passed'] is False
    assert [action['tool'] for action in failed['actions'] if action['tool'] in ('wait', 'gripper')] == expected_tools
    assert not any(action['arguments'].get('duration_s') == 3. for action in failed['actions'])


def test_checked_mode_is_explicit_in_native_parser(tmp_path):
    args = parser().parse_args(['--backend', 'diagnostic', '--probe', 'free-space-checked', '--output', str(tmp_path / 'unused')])
    assert args.backend == 'diagnostic' and args.probe == 'free-space-checked'
    assert not (tmp_path / 'unused').exists()
