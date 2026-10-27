"""Shared joint paths and continuous Cartesian IK for asset interaction demos."""

from dataclasses import dataclass

import numpy as np


@dataclass
class Motion:
    name: str
    duration: float
    joints: np.ndarray
    aperture: float


def blend_quaternion(start, end, fraction):
    """Interpolate unit wxyz quaternions along the shorter rotation."""
    end = np.asarray(end).copy()
    dot = float(np.dot(start, end))
    if dot < 0:
        end, dot = -end, -dot
    if dot > 0.9995:
        value = (1 - fraction) * start + fraction * end
        return value / np.linalg.norm(value)
    theta = np.arccos(np.clip(dot, -1, 1))
    return (np.sin((1 - fraction) * theta) * start
            + np.sin(fraction * theta) * end) / np.sin(theta)


def sample_joints(path, fraction):
    value = np.clip(fraction, 0, 1) * (len(path) - 1)
    index = min(int(value), len(path) - 2)
    return path[index] + (value - index) * (path[index + 1] - path[index])


def cartesian_joint_path(kinematics, frame, start_position, start_rotation,
                         end_position, end_rotation, start_joints, duration):
    """Precompute an IK path in metres and wxyz quaternions.

    Args:
        kinematics: Initialized Lula solver with its robot base pose set.
        frame: End-effector frame name.
        start_position: Initial world-space XYZ, in metres.
        start_rotation: Initial unit quaternion, in wxyz order.
        end_position: Target world-space XYZ, in metres.
        end_rotation: Target unit quaternion, in wxyz order.
        start_joints: Seven arm joint angles, in radians, used as the IK seed.
        duration: Segment duration in seconds; sampled at 30 Hz for planning.

    Returns:
        Array of joint samples, including the starting configuration.

    Raises:
        RuntimeError: IK is unreachable or jumps more than 0.12 rad per sample.
    """
    path = [start_joints]
    for fraction in np.linspace(0, 1, max(2, round(duration * 30)))[1:]:
        position = start_position + fraction * (end_position - start_position)
        rotation = blend_quaternion(start_rotation, end_rotation, fraction)
        joints, success = kinematics.compute_inverse_kinematics(
            frame, position, rotation, path[-1]
        )
        if not success or np.max(np.abs(joints - path[-1])) > 0.12:
            raise RuntimeError(f"Unreachable or discontinuous IK at {position.tolist()}")
        path.append(joints)
    return np.asarray(path)
