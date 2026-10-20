"""Read-only episode selection shared by collectors and policy datasets."""
import numpy as np


LEGACY_ABSOLUTE_ACTION_SEMANTICS = frozenset((
    "absolute_joint_position_target_7_arm_plus_1_finger",
    "absolute_7_arm_rad_and_symmetric_finger_metre",
))
NON_PHYSICAL_FAILURES = frozenset((
    "GEOMETRY_PREFLIGHT_BLOCKED", "GEOMETRY_PRECHECK_BLOCKED", "PREFLIGHT_BLOCKED",
    "INPUT_CONTRACT_ERROR", "GEOMETRY_BLOCKED", "GEOMETRY_BLOCKED_NOT_EXECUTED",
    "GEOMETRY_BLOCKED_PREINSERT", "INVALID_INITIAL_STATE", "MODEL_SERVICE_UNAVAILABLE",
    "INITIALIZATION_INVALID", "INIT_INVALID", "PHYSICS_INVALID", "MODEL_SERVICE_ERROR",
    "MODEL_ERROR", "PROCESS_ABORT", "PROCESS_ABORTED", "PROCESS_INTERRUPTED", "INTERRUPTED", "UNADJUDICATED",
))


def _optional_bool(value):
    # HDF5 scalar booleans are numpy.bool_; strings such as "unknown" are never truthy labels.
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (int, np.integer)) and value in (0, 1):
        return bool(value)
    return None


def episode_labels(attributes):
    modern = "record_valid" in attributes or "task_success" in attributes
    success = _optional_bool(attributes.get("task_success" if modern else "success"))
    valid = _optional_bool(attributes.get("record_valid")) if modern else (True if success is True else None)
    return dict(task_success=success, record_valid=valid,
                failure_type=str(attributes.get("failure_type", "NONE" if success else "UNKNOWN")),
                termination_reason=str(attributes.get("termination_reason", attributes.get("reason", "UNKNOWN"))))


def episode_matches_filter(attributes, sample_filter):
    """Select labels without modifying raw files or manufacturing successful indexes.

    Historical complete successes retain the old success-reader behavior. A
    historical false label alone does not establish physical failure validity.
    New failure/all-valid selection requires explicit record_valid evidence.
    """
    if _optional_bool(attributes.get("complete")) is not True:
        return False, "incomplete_record"
    labels = episode_labels(attributes)
    modern = "record_valid" in attributes or "task_success" in attributes
    if sample_filter == "success":
        if labels["task_success"] is not True:
            return False, "not_task_success"
        if modern and (labels["record_valid"] is not True or
                       _optional_bool(attributes.get("eligible_for_success_bc")) is not True):
            return False, "not_success_bc_eligible"
        return True, "accepted"
    if labels["record_valid"] is not True or labels["task_success"] is None:
        return False, "record_valid_or_task_outcome_unknown"
    if labels["task_success"] is False and labels["failure_type"].upper() in NON_PHYSICAL_FAILURES:
        return False, "not_physical_task_record"
    if sample_filter == "all_valid":
        return True, "accepted"
    if labels["task_success"] is not False:
        return False, "not_task_failure"
    if labels["failure_type"].upper() in NON_PHYSICAL_FAILURES:
        return False, "not_physical_task_failure"
    if _optional_bool(attributes.get("eligible_for_failure_analysis")) is not True:
        return False, "not_failure_analysis_eligible"
    return True, "accepted"

