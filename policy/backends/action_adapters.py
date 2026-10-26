"""Explicit ACT/DP dataset action to the public robot-action envelope.

Dataset8: seven absolute arm joint targets (rad), then ONE finger target (m).
The public gripper command is TOTAL symmetric opening (m), hence twice that
last value. This is not an EE delta and does not select a teacher phase.
"""
from __future__ import annotations

import math


def act_dp_joint_action(values, observation, *, action_id, duration_s=1 / 60,
                        gripper_effort_limit_N=8.0):
    values = list(values)
    if len(values) != 8 or any(isinstance(x, bool) for x in values):
        raise ValueError('ACT/DP requires7 arm targets plus1 symmetric finger target')
    values = [float(x) for x in values]
    if not all(math.isfinite(x) for x in values):
        raise ValueError('ACT/DP targets must be finite')
    if not 0 <= values[-1] <= .04:
        raise ValueError('Dataset finger target must be within0..0.04metres')
    if not observation.get('episode_id') or not observation.get('observation_id'):
        raise ValueError('A current public observation is required')
    if not isinstance(action_id, str) or not action_id:
        raise ValueError('A unique action_id is required')
    return dict(action_id=action_id, episode_id=observation['episode_id'],
                observation_id=observation['observation_id'], type='joint_position',
                values=values[:7], gripper_opening_m=2 * values[-1],
                gripper_effort_limit_N=float(gripper_effort_limit_N),
                duration_s=float(duration_s))
