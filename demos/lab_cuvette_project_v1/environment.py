"""Public, synchronous and idempotent robot-control facade shared by backends."""
from __future__ import annotations
import copy
import hashlib
import json
from pathlib import Path
import time

import numpy as np
from scipy.spatial.transform import Rotation


def _jsonable(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


class ProjectEnvironment:
    """One environment; the teacher channel is never exposed by this facade.

    Inference does not call world.step: simulation is paused between explicit
    execute calls. A repeated action ID returns its receipt without movement.
    """
    MAX_DURATION_S = 3.0
    MAX_TRANSLATION_M = .04
    MAX_ROTATION_RAD = .15
    MAX_SPEED_M_S = .02

    def __init__(self, task):
        self.task = task
        self._receipts = {}
        self._payload_hashes = {}

    def reset(self, seed=0, options=None):
        requested = dict(options or {})
        if requested.get('mode', 'standard') != 'standard':
            raise ValueError('Project_v1 reset supports fixed standard only')
        if requested.get('subtask', requested.get('task_type', 'loading')) != 'loading':
            raise ValueError('Project_v1 reset supports complete loading only')
        self._receipts.clear()
        self._payload_hashes.clear()
        self.task.reset(seed, options or dict(mode='standard', policy_id='external'))
        return self.observe()

    def observe(self):
        observation = self.task.get_observation()
        observation['camera_meta'] = {name: self.task.get_camera_meta(name) for name in observation['images']}
        observation['action_limits'] = dict(max_translation_m=self.MAX_TRANSLATION_M,
            max_rotation_rad=self.MAX_ROTATION_RAD, max_speed_m_s=self.MAX_SPEED_M_S,
            max_duration_s=self.MAX_DURATION_S, control_hz=float(self.task.cfg.physics.control_hz),
            gripper_opening_range_m=[0, .08], gripper_effort_range_N=[0, 8],
            duration_semantics='whole control ticks; physics paused outside execute')
        return observation

    def status(self):
        return dict(episode_id=self.task.episode_id,
            observation_id=f'{self.task.episode_id}:{self.task.control_steps}',
            simulation_time=float(self.task.t), terminated=bool(self.task.ended),
            task_success=None if self.task._result is None else self.task._result.get('task_success'),
            termination_reason=None if self.task._result is None else self.task._result.get('termination_reason'))

    def receipt(self, action_id):
        return copy.deepcopy(self._receipts.get(str(action_id)))

    def execute(self, action):
        if not isinstance(action, dict):
            raise ValueError('Explicit action envelope required')
        action_id = str(action.get('action_id', ''))
        if not action_id or len(action_id) > 128:
            raise ValueError('action_id must contain1..128 characters')
        action = _jsonable(action)
        payload = json.dumps(action, sort_keys=True, allow_nan=False)
        digest = hashlib.sha256(payload.encode()).hexdigest()
        if action_id in self._receipts:
            if self._payload_hashes[action_id] != digest:
                raise ValueError('action_id was already used with a different payload')
            return self.receipt(action_id)
        if self.task.ended:
            raise ValueError('Episode ended; reset before executing actions')
        current = self.task.get_observation()
        if action.get('episode_id') != current['episode_id'] or action.get('observation_id') != current['observation_id']:
            raise ValueError('Stale episode_id or observation_id')
        if action.get('metadata'):
            raise ValueError('Public policies cannot select teacher phases or private control schedules')
        kind = action.get('type')
        if kind not in ('ee_pose', 'ee_delta', 'joint_position', 'joint_velocity'):
            raise ValueError('Unknown typed action')
        duration = float(action.get('duration_s', 1 / self.task.cfg.physics.control_hz))
        hz = float(self.task.cfg.physics.control_hz)
        ticks = round(duration * hz)
        if not np.isfinite(duration) or ticks < 1 or duration > self.MAX_DURATION_S or abs(ticks / hz - duration) > 1e-6:
            raise ValueError('duration_s must be positive whole control ticks up to3seconds')
        values = np.asarray(action.get('values', []), float)
        if not np.isfinite(values).all():
            raise ValueError('Nonfinite action values')
        p0 = np.asarray(current['TCPpose']['position_m'], float)
        r0 = Rotation.from_quat(np.roll(current['TCPpose']['quaternion_wxyz'], -1))
        if kind == 'ee_delta':
            if values.shape != (6,):
                raise ValueError('ee_delta requires translation3 metres + rotation vector3 radians')
            if action.get('frame', 'world') == 'tcp':
                p1, r1 = p0 + r0.apply(values[:3]), r0 * Rotation.from_rotvec(values[3:])
            elif action.get('frame', 'world') == 'world':
                p1, r1 = p0 + values[:3], Rotation.from_rotvec(values[3:]) * r0
            else:
                raise ValueError('Unknown EE frame')
        elif kind == 'ee_pose':
            if values.shape != (7,) or abs(np.linalg.norm(values[3:]) - 1) > 1e-3:
                raise ValueError('ee_pose requires world xyz metres + unit quaternion wxyz')
            p1, r1 = values[:3], Rotation.from_quat(np.roll(values[3:], -1))
        if kind.startswith('ee_'):
            distance = float(np.linalg.norm(p1 - p0))
            dr = (r1 * r0.inv()).as_rotvec()
            if distance > self.MAX_TRANSLATION_M + 1e-9 or np.linalg.norm(dr) > self.MAX_ROTATION_RAD + 1e-9:
                raise ValueError('EE action exceeds public per-action translation/rotation limit')
            if distance / duration > self.MAX_SPEED_M_S + 1e-9:
                raise ValueError('EE action exceeds0.02m/s; increase bounded duration or reduce distance')
        opening = float(action.get('gripper_opening_m', current['gripper_opening_m']))
        effort = float(action.get('gripper_effort_limit_N', self.task.cfg.project.backend_gripper_effort_N))
        if not np.isfinite([opening, effort]).all() or not 0 <= opening <= .08 or not 0 <= effort <= 8:
            raise ValueError('Gripper opening or effort outside declared public bounds')
        started = time.perf_counter()
        before = float(self.task.t)
        self._payload_hashes[action_id] = digest
        receipt = dict(action_id=action_id, episode_id=current['episode_id'],
            observation_id=current['observation_id'], accepted=True, completed=False,
            executed_control_ticks=0, simulation_time_before=before)
        # Reserve ID before the first physics step; a partial action is never
        # silently replayed after an exception.
        self._receipts[action_id] = receipt
        try:
            for tick in range(ticks):
                if self.task.ended:
                    break
                low = dict(episode_id=current['episode_id'], observation_step=self.task.control_steps,
                    type=kind, values=values.tolist(),
                    gripper_opening_m=float(current['gripper_opening_m']) + (opening - float(current['gripper_opening_m'])) * (tick + 1) / ticks,
                    gripper_effort_limit_N=effort, duration_s=1 / hz,
                    raw_model_action=copy.deepcopy(action))
                if kind.startswith('ee_'):
                    fraction = (tick + 1) / ticks
                    orientation = Rotation.from_rotvec(dr * fraction) * r0
                    low.update(type='ee_pose', values=np.r_[p0 + (p1 - p0) * fraction,
                        np.roll(orientation.as_quat(), 1)].tolist())
                self.task.step(low)
                receipt['executed_control_ticks'] += 1
            receipt['completed'] = True
        except Exception as error:
            receipt['error_type'] = type(error).__name__
            receipt['error'] = str(error)
            raise
        finally:
            after = self.task.get_observation()
            receipt.update(observation_id_after=after['observation_id'], simulation_time_after=float(self.task.t),
                wall_seconds=time.perf_counter() - started, terminated=bool(self.task.ended),
                TCPpose=copy.deepcopy(after['TCPpose']), gripper_opening_m=float(after['gripper_opening_m']))
            path = self.task.episode_dir / 'action_receipts.jsonl'
            with path.open('a', encoding='utf-8') as stream:
                stream.write(json.dumps(receipt, allow_nan=False) + '\n')
        return self.receipt(action_id)

    def finish(self, reason='POLICY_FINISH_REQUEST', *, failure_type=None):
        # A backend may mark service/protocol/interruption failures, never
        # submit successful task evidence or rewrite an already scored outcome.
        allowed = {'MODEL_SERVICE_ERROR', 'INPUT_CONTRACT_ERROR', 'PROCESS_INTERRUPTED', 'PHYSICS_INVALID'}
        normalized = None if failure_type is None else str(failure_type).upper()
        if normalized is not None and normalized not in allowed:
            raise ValueError('finish accepts only declared nonphysical backend failure classifications')
        if not self.task.ended:
            self.task.finalize_episode(str(reason), normalized)
        return self.status()

    def close(self):
        self.task.close()
