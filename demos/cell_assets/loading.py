"""Continuous loading paths and measured acceptance for the IKA hood cycle.

Plan backwards from an elbow configuration that clears the open hood. Reverse
those same joint paths for withdrawal, avoiding redundant-IK branch changes.
"""

import json
from pathlib import Path

import numpy as np

from demos.cell_assets.motion import Motion, cartesian_joint_path


CYCLE_CONFIG = Path(__file__).resolve().parents[2] / "config/cell_assets/ika_automatic_cycle.json"


def read_cycle_config():
    return json.loads(CYCLE_CONFIG.read_text())


def insert_loading(motions, solver, grip, target, config):
    """Insert contact-only loading between hood release and regrasp."""
    from isaacsim.core.utils.rotations import euler_angles_to_quat

    kinematics = solver.get_kinematics_solver()
    frame = solver.get_end_effector_frame()
    orientation = euler_angles_to_quat(np.array([np.pi, 0, np.pi / 2]))
    joints, success = kinematics.compute_inverse_kinematics(
        frame, target, orientation, np.array(config["placement_seed_rad"])
    )
    if not success:
        raise RuntimeError("Cannot reach the configured IKA loading target")
    last_joints, last_position = joints, target

    def backward(end, duration):
        nonlocal last_joints, last_position
        path = cartesian_joint_path(
            kinematics, frame, last_position, orientation,
            end, orientation, last_joints, duration,
        )
        last_joints, last_position = path[-1], end
        return path

    height = config["platform_clearance_m"]
    place = backward(target + [0, 0, height], 2.5)
    enter = backward(target + [0, -config["platform_front_offset_m"], height], 3)
    transfer = backward(grip + [0, 0, config["pickup_lift_m"]], 3)
    descend = backward(grip, 2)
    index = next(i for i, motion in enumerate(motions) if motion.name == "hood_reengage")
    origin, home = motions[index - 1].joints[-1], motions[0].joints[0]
    prefix = [
        Motion("home_for_loading", 4, np.array([origin, home]), 0.04),
        Motion("approach_beaker", 4, np.array([home, descend[0]]), 0.04),
    ]
    additions = prefix + [
        Motion("descend_beaker", 2, descend, 0.04),
        Motion("grasp_beaker", 1.5, np.array([descend[-1]] * 2), 0),
        Motion("lift_beaker", 2.5, descend[::-1], 0),
        Motion("transfer_beaker", 3, transfer[::-1], 0),
        Motion("above_platform", 3, enter[::-1], 0),
        Motion("place_beaker", 2.5, place[::-1], 0),
        Motion("release_beaker", 1.5, np.array([place[0]] * 2), 0.04),
        Motion("retreat_beaker", 2.5, place, 0.04),
        Motion("loaded_settle", 3.5, np.array([place[-1]] * 2), 0.04),
        Motion("return_platform", 3, enter, 0.04),
        Motion("return_transfer", 3, transfer, 0.04),
    ]
    additions += [Motion("return_" + m.name, m.duration, m.joints[::-1], 0.04)
                  for m in reversed(prefix)]
    return motions[:index] + additions + motions[index:]


def evaluate_loading(records, initial_position, target_base, surface_z, dt, grip_height):
    """Reject partial runs, retained grasps, unstable placement and closing loss."""
    required = round(3 / dt)
    held = [r for r in records if r["phase"] in
            {"lift_beaker", "transfer_beaker", "above_platform", "place_beaker"}]
    lifted = [r for r in records if r["phase"] == "lift_beaker"]
    during_loading = [r for r in records if r["phase"] in {
        "home_for_loading", "approach_beaker", "descend_beaker", "grasp_beaker",
        "lift_beaker", "transfer_beaker", "above_platform", "place_beaker",
        "release_beaker", "retreat_beaker", "loaded_settle", "return_platform",
        "return_transfer", "return_approach_beaker", "return_home_for_loading",
    }]
    checks = {
        "beaker_lifted_8cm": bool(lifted and max(r["beaker_position_m"][2] for r in lifted)
                                  - initial_position[2] >= 0.08),
        "beaker_bilateral_contact_during_carry": bool(held and all(
            min(r["beaker_force_n"]) > 0.05 for r in held)),
        "beaker_tracks_gripper_within_15mm": bool(held and all(
            np.linalg.norm(np.array(r["end_effector_m"]) - r["beaker_position_m"]
                           - [0, 0, grip_height]) < 0.015 for r in held)),
        "hood_remains_open_through_loading": bool(during_loading and all(
            1.2 < r["hood_angle_rad"] < 1.34 for r in during_loading)),
    }
    for label, phase in (("loaded", "loaded_settle"), ("final", "closed_settle")):
        stable = [r for r in records if r["phase"] == phase][-required:]
        complete = len(stable) == required
        positions = np.array([r["beaker_position_m"] for r in stable])
        rotations = np.array([r["beaker_orientation_wxyz"] for r in stable])
        checks.update({
            label + "_stable_window_3s": complete,
            label + "_target_xy_within_2cm": bool(complete and np.max(
                np.linalg.norm(positions[:, :2] - target_base[:2], axis=1)) < 0.02),
            label + "_on_platform_within_1cm": bool(complete and np.max(
                np.abs(positions[:, 2] - surface_z)) < 0.01),
            label + "_upright_within_5deg": bool(complete and np.min(
                1 - 2 * (rotations[:, 1] ** 2 + rotations[:, 2] ** 2)) > np.cos(np.deg2rad(5))),
            label + "_stable_within_3mm": bool(complete and np.max(
                np.linalg.norm(positions - positions[-1], axis=1)) < 0.003),
            label + "_gripper_open": bool(complete and all(
                min(r["joint_actual"][-2:]) > 0.035 for r in stable)),
            label + "_no_finger_contact": bool(complete and all(
                max(r["beaker_force_n"]) < 0.05 for r in stable)),
            label + "_gripper_retreated_12cm": bool(complete and all(
                np.linalg.norm(np.array(r["end_effector_m"]) - r["beaker_position_m"]
                               - [0, 0, grip_height]) > 0.12 for r in stable)),
        })
    return checks
