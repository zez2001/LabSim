"""Upstream main entry routes to the release launcher without a second executor."""
from types import SimpleNamespace
import pytest
from demos.lab_cuvette_project_v1.native_entry import build_project_argv


def arguments(**values):
    baseline = dict(backend='numpy', no_video=False, subtask=None, initial_state=None,
        replay_episode=None, layout_mode='standard', env_mode='teacher', output='outputs/native_test',
        policy_backend='teacher', project_config='config/lab_cuvette_loading/Project_v1/standard.yaml',
        seed=0, episodes=1, port=8097, max_calls=160, headless=False,
        provider_config=None, budget_ledger=None)
    baseline.update(values)
    return SimpleNamespace(**baseline)


def test_native_entry_uses_same_release_config_and_launcher_arguments():
    argv = build_project_argv(arguments())
    assert argv[argv.index('--backend') + 1] == 'teacher'
    assert argv[argv.index('--config') + 1].endswith('/Project_v1/standard.yaml')
    assert argv[argv.index('--layout-mode') + 1] == 'standard'
    assert '--headless' not in argv


def test_gpt_and_rpc_selection_are_explicit():
    gpt = build_project_argv(arguments(policy_backend='gpt6', budget_ledger='outputs/shared_budget.json', headless=True))
    assert gpt[gpt.index('--backend') + 1] == 'gpt6'
    assert '--budget-ledger' in gpt and '--headless' in gpt
    rpc = build_project_argv(arguments(env_mode='serve'))
    assert rpc[rpc.index('--backend') + 1] == 'rpc'


@pytest.mark.parametrize('changed', [dict(backend='gpu'), dict(layout_mode='random'),
    dict(subtask='grasp_hold'), dict(no_video=True), dict(output=None), dict(env_mode='replay')])
def test_native_entry_refuses_unsupported_modes_without_initializing_isaac(changed):
    with pytest.raises(ValueError):
        build_project_argv(arguments(**changed))
