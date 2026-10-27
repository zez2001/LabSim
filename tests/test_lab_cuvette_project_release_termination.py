"""Controlled termination path fixtures, never real model/physics evidence."""
import copy
from types import SimpleNamespace

import numpy as np
import pytest

from demos.lab_cuvette_project_release_v1.run import controlled_case, parser


class FixtureFacade:
    def __init__(self):
        self.task = SimpleNamespace(cfg=SimpleNamespace(physics=SimpleNamespace(control_hz=60)),
            episode_id='fixture', control_steps=0, ended=False)
        self.task.joint_bounds = lambda: (np.full(7, -2.), np.full(7, 2.), np.ones(7))
        self.task.finalize_episode = lambda reason, failure: self.finish(reason, failure_type=failure)
        self.task._write = lambda path, value: setattr(self, 'evidence', value)
        self.task.episode_dir = __import__('pathlib').Path('/unused-cpu-fixture')
        self.calls = []
        self.result = None

    def observe(self):
        return dict(episode_id='fixture', observation_id=f'fixture:{self.task.control_steps}',
                    joint_positions=np.zeros(9))

    def execute(self, action):
        self.calls.append(copy.deepcopy(action))
        accepted = action['type'] != 'joint_position'
        ticks = round(action['duration_s'] * 60) if accepted else 0
        self.task.control_steps += ticks
        return dict(accepted=accepted, executed_control_ticks=ticks,
                    stop_reason='INTERVAL_FINISHED' if accepted else 'JOINT_PLAN_REJECTED')

    def status(self):
        return dict(episode_id='fixture', terminated=self.task.ended,
                    reason=self.result)

    def finish(self, reason, failure_type=None):
        if not self.task.ended:
            self.result = dict(reason=reason, failure_type=failure_type)
            self.task.ended = True
        return self.status()


@pytest.mark.parametrize('condition,reason,failure,injected', [
    ('early_finish', 'CONTROLLED_EARLY_FINISH', None, False),
    ('no_progress', 'CONTROLLED_NO_PROGRESS_LIMIT', 'TIMEOUT', False),
    ('unreachable', 'CONTROLLED_UNREACHABLE_REQUEST_END', None, False),
    ('service_timeout', 'PROVIDER_TIMEOUT', 'MODEL_SERVICE_ERROR', True),
    ('user_interrupt', 'USER_INTERRUPTED', 'PROCESS_INTERRUPTED', True),
])
def test_termination_preserves_actions_and_first_terminal_result(condition, reason, failure, injected):
    facade = FixtureFacade()
    evidence = controlled_case(facade, condition, seconds=1.)
    assert facade.task.control_steps == 60
    assert facade.result == dict(reason=reason, failure_type=failure)
    assert evidence['controlled_fault_injection'] is injected
    assert evidence['repeated_finish_preserved_status']
    assert not evidence['real_model_service_failure']
    assert not evidence['actual_user_keyboard_action']
    if condition == 'unreachable':
        assert len(facade.calls) == 2
        assert evidence['action_receipts'][-1]['executed_control_ticks'] == 0


def test_native_diagnostic_argv_can_explicitly_select_recording_mode_and_conditions():
    args = parser().parse_args(['--record-mode', 'collect', '--execution-purpose', 'collect', '--sequence',
        'early_finish', 'no_progress', 'unreachable', 'service_timeout', 'user_interrupt',
        '--output', '/unused-cpu-fixture'])
    assert args.record_mode == 'collect' and args.execution_purpose == 'collect' and len(args.sequence) == 5
