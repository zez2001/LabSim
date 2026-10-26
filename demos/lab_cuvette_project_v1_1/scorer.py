"""Project_v1_1 failure axes over the unchanged Size_v1 physical task gates.

This module changes classification, never scene geometry or acceptance numbers.
The historical scorer is imported, not edited. Its contact guard diagnostics are
retained even when a finite, coherent collision is classified as a safety failure.
"""
from __future__ import annotations

import copy

from demos.lab_cuvette_size_v1.scorer import Scorer as SizeScorer


class Scorer(SizeScorer):
    VERSION = "Project_v1_1.independent.v1"
    _SAFETY_REASONS = {
        "robot_contact_with_original_instrument_or_rack",
        "observed_input_material_overlap_above_declared_limit",
        "measured_native_target_overlap_above_declared_limit",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._legacy_automatic_failure = None
        self._legacy_invalid_reasons = set()
        self._legacy_guard_events = []
        self._safety_cause = None

    def _simulation_invalid_reasons(self):
        return {reason for reason in self.invalid_reasons if reason.startswith("nonfinite_")
                or reason in {"missing_or_nonfinite_required_physical_state", "actual_object_pose_jump_above_declared_limit"}}

    def update(self, row):
        # Let the original event/window machinery observe the identical row.
        # Restore its own automatic state rather than feeding new enum values
        # back into the historical implementation on the next physics sample.
        self._automatic_failure = self._legacy_automatic_failure
        raw = super().update(row)
        self._legacy_automatic_failure = self._automatic_failure
        self._legacy_invalid_reasons.update(self.invalid_reasons)
        if raw.get("terminate"):
            event = {"termination_reason": raw.get("termination_reason"),
                     "failure_type": raw.get("failure_type"),
                     "t": row.get("t", row.get("simulation_time"))}
            if not self._legacy_guard_events or event["termination_reason"] != self._legacy_guard_events[-1]["termination_reason"]:
                self._legacy_guard_events.append(event)

        # Contact and a declared input-geometry violation still stop execution,
        # but do not by themselves demonstrate numerical simulation corruption.
        safety_reasons = self.invalid_reasons & self._SAFETY_REASONS
        self.invalid_reasons.difference_update(self._SAFETY_REASONS)
        if safety_reasons and self._safety_cause is None:
            collision = "robot_contact_with_original_instrument_or_rack" in safety_reasons
            self._safety_cause = dict(
                failure_type="SAFETY_COLLISION" if collision else "SAFETY_GEOMETRY_VIOLATION",
                termination_reason="ROBOT_ENVIRONMENT_COLLISION" if collision else raw.get("termination_reason", "INPUT_MATERIAL_PENETRATION"),
                evidence_reasons=sorted(safety_reasons))
        if self._simulation_invalid_reasons():
            self._automatic_failure = "SIMULATION_FAILURE"
            return dict(raw, terminate=True, failure_type="SIMULATION_FAILURE",
                        termination_reason="SIMULATION_STATE_INVALID",
                        raw_termination_reason=raw.get("termination_reason"),
                        raw_failure_type=raw.get("failure_type"))
        if self.invalid_reasons:
            self._automatic_failure = "RECORDING_FAILURE"
            return dict(raw, terminate=True, failure_type="RECORDING_FAILURE",
                        termination_reason="PHYSICAL_TRACE_CLOCK_INVALID",
                        raw_termination_reason=raw.get("termination_reason"),
                        raw_failure_type=raw.get("failure_type"))
        if self._safety_cause is not None:
            self._automatic_failure = self._safety_cause["failure_type"]
            return dict(raw, terminate=True, **self._safety_cause,
                        raw_failure_type=raw.get("failure_type"),
                        raw_termination_reason=raw.get("termination_reason"))
        return raw

    @staticmethod
    def _domain(reason, failure):
        joined = (str(reason) + " " + str(failure)).upper()
        if any(code in joined for code in ("CONTROL_OR_IK", "TRACKING_ERROR", "EXECUTOR_FAILURE",
                "PHYSICS_ACTION_EXECUTION_FAILURE", "ACTION_EXECUTION_UNKNOWN_CHECK_RECEIPT")):
            return "executor", "EXECUTOR_FAILURE"
        if failure == "SIMULATION_FAILURE":
            return "simulation", "SIMULATION_FAILURE"
        if failure == "RECORDING_FAILURE":
            return "recording", "RECORDING_FAILURE"
        if failure.startswith("SAFETY_") or reason == "ROBOT_ENVIRONMENT_COLLISION":
            return "safety", failure if failure.startswith("SAFETY_") else "SAFETY_COLLISION"
        if failure == "INPUT_CONTRACT_ERROR" or "PROTOCOL" in joined or "LOCAL_CONTEXT" in joined:
            return "protocol", "PROTOCOL_FAILURE"
        if any(code in joined for code in ("COST_BUDGET", "REQUEST_BUDGET", "POLICY_BUDGET", "POLICY_EPISODE_WALL_TIMEOUT")):
            return "budget", "POLICY_BUDGET"
        if failure in {"MODEL_SERVICE_ERROR", "MODEL_ERROR", "SERVICE_FAILURE"} or reason.startswith("PROVIDER_"):
            return "service", "SERVICE_FAILURE"
        if any(code in joined for code in ("PROCESS_INTERRUPTED", "PROCESS_ABORT", "ENVIRONMENT_CLOSED", "RESET_INTERRUPTED")):
            return "interruption", "PROCESS_INTERRUPTED"
        if failure in {"INITIALIZATION_INVALID", "INITIAL_SUPPORT_INVALID", "INIT_INVALID"}:
            return "initialization", "INITIALIZATION_INVALID"
        if failure.startswith("GEOMETRY_") or failure in {"PREFLIGHT_BLOCKED", "SCENE_INVALID"}:
            return "preflight", "GEOMETRY_PRECHECK_BLOCKED"
        if failure == "PHYSICS_INVALID":
            return "unknown", "UNCLASSIFIED_FAILURE"
        return ("none" if failure == "NONE" else "task"), failure

    def finalize(self, episode_id, task_type, termination_reason=None, failure_type=None):
        raw_reason = str(termination_reason or self._automatic_failure or "EPISODE_ENDED")
        raw_failure = str(failure_type or self._automatic_failure or "NONE").upper()
        domain, failure = self._domain(raw_reason, raw_failure)
        if self._simulation_invalid_reasons():
            domain, failure = "simulation", "SIMULATION_FAILURE"
        elif self.invalid_reasons:
            domain, failure = "recording", "RECORDING_FAILURE"
        recording_errors = sorted(self.invalid_reasons - self._simulation_invalid_reasons())
        physics = False if self._simulation_invalid_reasons() or failure == "SIMULATION_FAILURE" else (
            True if len(self.rows) >= 2 and domain not in {"unknown", "recording"} else None)
        # Existing finalize supplies the exact grasp/insertion/support/release/
        # retreat/stability predicates. Non-task aborts use its conservative null
        # path; new failure enums are restored only after those predicates run.
        compatibility_failure = {
            "executor": "PHYSICS_INVALID", "simulation": "PHYSICS_INVALID",
            "service": "MODEL_SERVICE_ERROR", "protocol": "INPUT_CONTRACT_ERROR",
            "interruption": "PROCESS_INTERRUPTED", "unknown": "PHYSICS_INVALID",
            "recording": "INPUT_CONTRACT_ERROR", "initialization": "INITIALIZATION_INVALID",
            "preflight": "GEOMETRY_PRECHECK_BLOCKED",
        }.get(domain, failure)
        result = super().finalize(episode_id, task_type, raw_reason, compatibility_failure)
        base = {key: copy.deepcopy(result.get(key)) for key in (
            "failure_type", "termination_reason", "record_valid", "task_success", "invalid_state_reasons")}
        if domain == "safety" and physics is True:
            result["task_success"] = False
            result["record_valid"] = True
        elif domain in {"executor", "simulation", "service", "protocol", "interruption", "unknown", "recording", "initialization", "preflight"}:
            result["task_success"] = None
            result["record_valid"] = False
        else:
            failure = result["failure_type"]
            if failure != "NONE" and domain == "none":
                domain = "task"
        full = task_type == "loading"
        success = result["task_success"]
        compatible_valid = bool(result["record_valid"] and physics is True)
        success_bc = bool(compatible_valid and success is True and full and result.get("geometry_valid") is True)
        failure_analysis = bool(compatible_valid and success is False and full and domain in {"task", "safety"})
        result.update(
            schema="labsim.Project_v1_1.independent.v1", scene_version="Project_v1_1",
            scorer_version=self.VERSION, real_calibrated=False,
            failure_type=failure, failure_domain=domain, termination_reason=raw_reason,
            record_valid=compatible_valid,
            record_valid_scope="compatibility projection; collector additionally verifies action/sensor/time integrity",
            task_result=dict(success=success, status="success" if success is True else "failure" if success is False else "unknown",
                             scope="complete_loading" if full else "diagnostic_subtask", failure_domain=domain),
            workflow_success=success if full else None, full_success=success if full else None,
            variant_pair_success=success if full else None,
            record_integrity_valid=False if recording_errors else None, record_integrity_source="collector_pending",
            record_integrity_errors=recording_errors,
            physics_trustworthy=physics,
            physics_trust_scope="declared input geometry and recorded physical state; effective cooked geometry and real calibration remain unverified",
            success_bc_eligible=success_bc, eligible_for_success_bc=success_bc,
            eligible_for_failure_analysis=failure_analysis,
            trajectory_analysis_eligible=bool(self.rows), eligibility_pending_collector_integrity=True,
            raw_failure_type=raw_failure, raw_termination_reason=raw_reason,
            safety_event=copy.deepcopy(self._safety_cause), safety_attribution="not_determined_by_scorer",
            legacy_invalid_state_reasons=sorted(self._legacy_invalid_reasons),
            legacy_guard_events=copy.deepcopy(self._legacy_guard_events), base_scoring_diagnostics=base)
        return result
