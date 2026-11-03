"""Policy-evaluation closure semantics: failures remain real task outcomes."""
import importlib.util
from pathlib import Path

import numpy as np
import pytest


_PATH = Path(__file__).resolve().parents[1] / 'docs/lab_cuvette_loading/Policy_eval_v1/tools/audit_episode.py'
_SPEC = importlib.util.spec_from_file_location('policy_eval_episode_audit', _PATH)
audit = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(audit)


@pytest.mark.parametrize('domain', ['budget', 'task', 'safety', 'model_service', 'input_contract'])
def test_policy_or_service_failure_does_not_invalidate_physical_environment(domain):
    result = dict(geometry_valid=True, task_success=False, record_valid=False, failure_domain=domain)
    assert audit.environment_status(result, dict(passed=True))['environment_valid'] is True


def test_explicit_physics_failure_and_nonfinite_state_are_environment_invalid():
    result = dict(geometry_valid=True, task_success=False, failure_domain='simulation')
    assert audit.environment_status(result, dict(passed=True))['environment_valid'] is False
    result['failure_domain'] = 'task'
    actual = audit.environment_status(result, dict(passed=True), physical_nonfinite_rows=1)
    assert actual['environment_valid'] is False
    assert actual['reasons'] == ['nonfinite_recorded_physical_state']


def test_bad_reset_not_hidden_by_task_success_label():
    result = dict(geometry_valid=True, task_success=True, failure_domain='none')
    assert audit.environment_status(result, dict(passed=False))['environment_valid'] is False


def test_time_and_observation_successor_adjacency():
    t0, t1 = np.array([1., 1.1]), np.array([1.1, 1.2])
    assert audit.check_time_alignment(t0, t1, np.array([.1, .1]), np.array([0, 1]), np.array([1, 2]))
    # A valid duration does not mask a skipped observation or nonadjacent state.
    assert not audit.check_time_alignment(t0, t1, np.array([.1, .1]), np.array([0, 2]), np.array([1, 3]))
    assert not audit.check_time_alignment(t0, np.array([1.1, 1.1]), np.array([.1, 0.]), np.array([0, 1]), np.array([1, 2]))
    assert not audit.check_time_alignment(t0, np.array([1.05, 1.2]), np.array([.05, .1]), np.array([0, 1]), np.array([1, 2]))


def test_nonfinite_time_fails_even_if_steps_are_adjacent():
    assert not audit.check_time_alignment(np.array([np.nan]), np.array([1.]),
        np.array([.1]), np.array([0]), np.array([1]))
