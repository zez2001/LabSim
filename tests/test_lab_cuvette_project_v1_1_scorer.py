"""Synthetic CPU contract fixtures only; these are not simulation evidence."""
import copy
import importlib.util
from pathlib import Path

import pytest

from demos.lab_cuvette_project_v1_1.scorer import Scorer
from demos.lab_cuvette_size_v1.scorer import Scorer as SizeScorer


spec = importlib.util.spec_from_file_location("original_scorer_test_fixtures", Path(__file__).with_name("test_lab_cuvette_env_v1_scorer.py"))
fixtures = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixtures)


def rows():
    result = fixtures.fixture_rows()
    for row in result:
        row["input_geometry_overlap_observed_m"] = 0.0
    return result


def scorer_with_prefix():
    scorer = Scorer(fixtures.CFG, fixtures.LAYOUT, {"geometry_valid": True})
    for row in rows()[:3]:
        scorer.update(row)
    return scorer


def test_success_uses_the_identical_size_task_predicates_and_thresholds():
    new = Scorer(fixtures.CFG, fixtures.LAYOUT, {"geometry_valid": True})
    old = SizeScorer(fixtures.CFG, fixtures.LAYOUT, {"geometry_valid": True})
    for row in rows():
        old.update(row)
        new.update(row)
    baseline = old.finalize("cpu_fixture", "loading")
    result = new.finalize("cpu_fixture", "loading")
    assert result["task_success"] is baseline["task_success"] is True
    for key in ("grasp_success", "transport_success", "release_observed", "retreat_observed", "post_retreat_window", "grasp_relative_pose"):
        assert result[key] == baseline[key]
    assert result["physics_trustworthy"] is True
    assert result["record_integrity_valid"] is None
    assert result["success_bc_eligible"] is True
    assert result["eligibility_pending_collector_integrity"] is True


def test_finite_robot_collision_is_a_safety_stop_and_preserves_legacy_diagnostics():
    scorer = scorer_with_prefix()
    row = copy.deepcopy(rows()[3])
    row["forbidden_robot_environment_contact"] = True
    stop = scorer.update(row)
    assert stop["terminate"] is True
    assert stop["failure_type"] == "SAFETY_COLLISION"
    result = scorer.finalize("cpu_fixture", "loading", stop["termination_reason"], stop["failure_type"])
    assert result["failure_domain"] == "safety"
    assert result["task_success"] is False
    assert result["record_valid"] is True
    assert result["physics_trustworthy"] is True
    assert result["eligible_for_failure_analysis"] is True
    assert result["legacy_guard_events"][0]["failure_type"] == "PHYSICS_INVALID"
    assert "robot_contact_with_original_instrument_or_rack" in result["legacy_invalid_state_reasons"]
    assert result["invalid_state_reasons"] == []
    assert result["stable_after_retreat"] is None


@pytest.mark.parametrize("reason", ["CONTROL_OR_IK_FAILURE", "TRACKING_ERROR_POSITION", "PHYSICS_ACTION_EXECUTION_FAILURE"])
def test_executor_failure_is_not_a_claim_of_numerical_simulation_corruption(reason):
    result = scorer_with_prefix().finalize("cpu_fixture", "loading", reason, "EXECUTOR_FAILURE")
    assert result["failure_type"] == "EXECUTOR_FAILURE"
    assert result["failure_domain"] == "executor"
    assert result["termination_reason"] == reason
    assert result["physics_trustworthy"] is True
    assert result["task_success"] is None
    assert result["record_valid"] is False
    assert result["success_bc_eligible"] is False
    assert result["trajectory_analysis_eligible"] is True


@pytest.mark.parametrize("mutation", ["nonfinite", "jump", "jump_and_collision"])
def test_state_invalidity_overrides_contact_reclassification(mutation):
    scorer = scorer_with_prefix()
    row = copy.deepcopy(rows()[3])
    row["object_position_m"][0] += 0.01
    if mutation == "nonfinite":
        row["object_position_m"][0] = float("nan")
    if mutation == "jump_and_collision":
        row["forbidden_robot_environment_contact"] = True
    stop = scorer.update(row)
    assert stop["failure_type"] == "SIMULATION_FAILURE"
    result = scorer.finalize("cpu_fixture", "loading", stop["termination_reason"], stop["failure_type"])
    assert result["failure_domain"] == "simulation"
    assert result["physics_trustworthy"] is False
    assert result["task_success"] is None
    assert result["record_valid"] is False
    assert result["trajectory_analysis_eligible"] is True


def test_declared_material_limit_still_stops_without_changing_the_threshold():
    scorer = scorer_with_prefix()
    row = copy.deepcopy(rows()[3])
    row["input_geometry_overlap_observed_m"] = scorer.tolerance_m + 1e-8
    stop = scorer.update(row)
    assert stop["terminate"] is True
    assert stop["failure_type"] == "SAFETY_GEOMETRY_VIOLATION"
    result = scorer.finalize("cpu_fixture", "loading", stop["termination_reason"], stop["failure_type"])
    assert result["physics_trustworthy"] is True
    assert result["task_success"] is False
    assert "observed_input_material_overlap_above_declared_limit" in result["legacy_invalid_state_reasons"]


def test_service_error_keeps_finite_physics_distinct_from_the_unknown_task_result():
    result = scorer_with_prefix().finalize("cpu_fixture", "loading", "PROVIDER_TIMEOUT", "MODEL_SERVICE_ERROR")
    assert result["failure_domain"] == "service"
    assert result["physics_trustworthy"] is True
    assert result["task_success"] is None
    assert result["record_valid"] is False


def test_velocity_warning_and_unmeasured_cooked_geometry_are_not_removed():
    scorer = scorer_with_prefix()
    row = copy.deepcopy(rows()[3])
    row.update(native_target_overlap_m=None, native_linear_velocity_m_s=[1, 0, 0], fd_linear_velocity_m_s=[0, 0, 0])
    scorer.update(row)
    result = scorer.finalize("cpu_fixture", "loading", "POLICY_FINISH_REQUEST")
    assert result["physics_trustworthy"] is True
    assert "NATIVE_TARGET_OVERLAP_UNAVAILABLE" in result["physics_quality_flags"]
    assert "NATIVE_FD_LINEAR_VELOCITY_DISAGREEMENT" in result["physics_quality_flags"]
    assert result["real_calibrated"] is False


def test_missing_physics_remains_unknown_and_never_success_bc():
    result = Scorer(fixtures.CFG, fixtures.LAYOUT, {}).finalize("cpu_fixture", "loading", "PROCESS_INTERRUPTED", "PROCESS_INTERRUPTED")
    assert result["physics_trustworthy"] is None
    assert result["task_success"] is None
    assert result["success_bc_eligible"] is False


def test_nonmonotonic_trace_is_a_recording_failure_not_a_simulator_root_cause_claim():
    scorer = scorer_with_prefix()
    row = copy.deepcopy(rows()[3])
    row["t"] = 0.0
    stop = scorer.update(row)
    assert stop["failure_type"] == "RECORDING_FAILURE"
    result = scorer.finalize("cpu_fixture", "loading", stop["termination_reason"], stop["failure_type"])
    assert result["physics_trustworthy"] is None
    assert result["record_integrity_valid"] is False
    assert result["task_success"] is None


def test_episode_wall_budget_is_not_mislabeled_as_a_provider_failure():
    result = scorer_with_prefix().finalize("cpu_fixture", "loading", "POLICY_EPISODE_WALL_TIMEOUT", "MODEL_SERVICE_ERROR")
    assert result["failure_domain"] == "budget"
    assert result["physics_trustworthy"] is True
