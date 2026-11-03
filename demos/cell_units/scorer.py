"""Score measured physical state independently of policy claims and phases."""

import numpy as np

SCORING_VERSION = "SingleCellUnitScore_v2"
STABLE_WINDOW_S = 3
MAX_UNINTENDED_FORCE_N = 1
MIN_GRASP_FORCE_N = 0.01
MAX_RELEASE_FORCE_N = 0.05
RELEASE_FINGER_OPENING_M = 0.035
WITHDRAW_DISTANCE_M = 0.12
TARGET_TOLERANCE_M = 0.002
STABILITY_TOLERANCE_M = 0.0005
MAX_TILT_DEG = 3
MIN_LIFT_M = 0.08
MIN_HOOD_ANGLE_RAD = 1.2
CLOSED_HOOD_TOLERANCE_RAD = 0.02
PCR_XY_TOLERANCE_M = 0.0006
MIN_PCR_INSERTION_M = 0.010
MIN_PCR_SUPPORT_N = 0.0005


def score(unit, records, targets, grip_offset, dt):
    """Judge measured contact and post-release stability independently of control.

    Args:
        unit: Registry entry, including any verified placement initial condition.
        records: Per-physics-step measurements in chronological order.
        targets: Task target positions in world metres (hood angle in radians).
        grip_offset: Object-to-TCP offset in metres at the nominal grasp.
        dt: Physics timestep in seconds.

    Returns:
        Overall success, named checks and scoring version. Thresholds are
        centralized above; modifying them requires a new scoring version.
    """
    n = round(STABLE_WINDOW_S / dt)
    tail = records[-n:]
    checks = {"stable_window_3s": len(tail) == n}
    if not records:
        return dict(task_success=False, checks=checks, scoring_version=SCORING_VERSION)
    hood = unit["builder"] == "hood"
    contact_key = "handle_force_n" if hood else "finger_force_n"
    obstacle = "unintended_robot_device_force_n" if hood else "robot_device_force_n"
    table = "robot_environment_force_n" if hood else "robot_table_force_n"
    checks["no_unintended_collision_above_1N"] = (
        max(max(r[obstacle], r[table]) for r in records) < MAX_UNINTENDED_FORCE_N
    )
    checks["physical_bilateral_grasp"] = any(
        min(r[contact_key]) > MIN_GRASP_FORCE_N for r in records
    )
    checks["released"] = all(
        min(r["joint_actual"][-2:]) > RELEASE_FINGER_OPENING_M
        and max(r[contact_key]) < MAX_RELEASE_FORCE_N
        for r in tail
    )
    if hood:
        checks["started_closed"] = abs(targets["initial_angle_rad"]) < CLOSED_HOOD_TOLERANCE_RAD
        checks["hood_remains_open"] = all(r["hood_angle_rad"] > MIN_HOOD_ANGLE_RAD for r in tail)
        last_grasp = next(
            (
                r
                for r in reversed(records)
                if min(r[contact_key]) > MIN_GRASP_FORCE_N
                and r["hood_angle_rad"] > MIN_HOOD_ANGLE_RAD
            ),
            None,
        )
        checks["withdrawn_12cm"] = last_grasp is not None and all(
            np.linalg.norm(np.asarray(r["end_effector_m"]) - last_grasp["end_effector_m"])
            > WITHDRAW_DISTANCE_M
            for r in tail
        )
    else:
        cap = unit["builder"] == "cap"
        key = "cap_position_m" if cap else "position_m"
        rotation = "cap_orientation_wxyz" if cap else "orientation_wxyz"
        target = np.asarray(targets["parked" if cap else "loaded"])
        xyz = np.array([r[key] for r in tail])
        checks["target_within_2mm"] = bool(
            np.max(np.linalg.norm(xyz - target, axis=1)) < TARGET_TOLERANCE_M
        )
        checks["stable_within_0_5mm"] = bool(
            np.max(np.linalg.norm(xyz - xyz[-1], axis=1)) < STABILITY_TOLERANCE_M
        )
        checks["upright_within_3deg"] = all(
            1 - 2 * (r[rotation][1] ** 2 + r[rotation][2] ** 2) > np.cos(np.deg2rad(MAX_TILT_DEG))
            for r in tail
        )
        checks["withdrawn_12cm"] = all(
            np.linalg.norm(np.array(r["end_effector_m"]) - r[key] - grip_offset)
            > WITHDRAW_DISTANCE_M
            for r in tail
        )
        initial = targets["closed" if cap else "returned"]
        checks["lifted_8cm_with_contact"] = any(
            r[key][2] - initial[2] > MIN_LIFT_M and min(r[contact_key]) > MIN_GRASP_FORCE_N
            for r in records
        )
        if not cap:
            support = (
                "payload_table_force_n"
                if unit["id"] == "magsep_transfer"
                else "payload_device_force_n"
            )
            threshold = MIN_PCR_SUPPORT_N if unit["builder"] == "pcr" else MIN_GRASP_FORCE_N
            checks["supported_after_release"] = all(r[support] > threshold for r in tail)
        if unit["builder"] == "pcr":
            checks["inside_target_hole_0_6mm"] = bool(
                np.max(np.linalg.norm(xyz[:, :2] - target[:2], axis=1)) < PCR_XY_TOLERANCE_M
            )
            hole_depth = targets["hole_top"][2] - target[2]
            checks["inserted_at_least_10mm"] = checks["inside_target_hole_0_6mm"] and all(
                MIN_PCR_INSERTION_M < r["insertion_depth_m"] <= hole_depth + PCR_XY_TOLERANCE_M
                for r in tail
            )

        if unit.get("initial_state") == "placement-ready":
            # Pickup is explicitly outside this policy episode.
            del checks["lifted_8cm_with_contact"]
            del checks["physical_bilateral_grasp"]
            checks["started_with_bilateral_grasp"] = (
                min(unit["initial_grasp_contact_N"]) > MIN_GRASP_FORCE_N
            )
            release = next(
                (
                    i
                    for i, r in enumerate(records)
                    if min(r["joint_actual"][-2:]) > RELEASE_FINGER_OPENING_M
                ),
                len(records),
            )
            support = (
                "payload_table_force_n"
                if unit["id"] == "magsep_transfer"
                else "payload_device_force_n"
            )
            checks["supported_before_release"] = any(
                r[support] > MIN_GRASP_FORCE_N
                and min(r[contact_key]) > MIN_GRASP_FORCE_N
                and np.linalg.norm(np.asarray(r[key]) - target) < TARGET_TOLERANCE_M
                for r in records[:release]
            )
    return dict(
        task_success=all(checks.values()),
        checks={k: bool(v) for k, v in checks.items()},
        scoring_version=SCORING_VERSION,
    )
