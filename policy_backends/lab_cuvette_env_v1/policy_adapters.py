"""Explicit policy boundaries; never expose scorer truth or infer action semantics.

The installed RPent checkpoint is LIBERO pi0.5, not a LabSim joint policy.
Its normalized seven numbers become bounded TCP deltas through a declared
embodiment transfer.  Low-level IK remains the environment's responsibility.
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
from scipy.spatial.transform import Rotation


def _finite_vector(value: Any, size: int, name: str) -> np.ndarray:
    a = np.asarray(value, dtype=np.float64)
    if a.shape != (size,) or not np.isfinite(a).all():
        raise ValueError(f"{name} must be finite [{size}], got {a.shape}")
    return a


def policy_observation(observation: dict) -> dict:
    """Whitelist robot proprioception, real images, language and provenance.

    Returning an allowlist rather than deleting a few known debug keys prevents
    future scorer additions from silently becoming model observations.
    """
    allowed = ("episode_id", "step_index", "simulation_time", "task_language",
               "images", "joint_positions", "joint_velocities", "TCPpose", "camera_meta", "action_spec",
               "source_slot_id", "target_seat_id", "scene_version", "asset_version")
    return {key: observation[key] for key in allowed if key in observation}


def _rgb(observation: dict, key: str) -> np.ndarray:
    image = np.asarray(observation["images"][key])
    if image.dtype != np.uint8 or image.ndim != 3 or image.shape[-1] != 3:
        raise ValueError(f"{key} must be actual uint8 HWC RGB, got {image.shape}/{image.dtype}")
    meta = observation.get("camera_meta", {}).get(key, {})
    if meta.get("synthetic_duplicate", False):
        raise ValueError(f"{key} is a duplicated view, not an independent sensor")
    return image


@dataclass(frozen=True)
class LiberoTransferContract:
    """Checkpoint semantics plus explicit conservative transfer to Franka.

    These are engineering transfer settings, not calibrated equivalence to
    LIBERO's OSC dynamics. Raw checkpoint outputs always remain recorded.
    """
    checkpoint_id: str = "RLinf-Pi05-LIBERO-130-fullshot-SFT"
    embodiment: str = "libero"
    expected_weights_sha256: str = "4d9089c941793f170b625c2ed0ac7a3aa09b6f103e52dbbc82e67301529d6683"
    policy_action_hz: float = 20.0
    control_hz: float = 60.0
    trained_translation_scale_m: float = 0.05
    trained_rotation_scale_rad: float = 0.5
    execution_translation_cap_m: float = 0.002
    execution_rotation_cap_rad: float = 0.02
    maximum_chunk: int = 5
    gripper_open_single_finger_m: float = 0.04
    gripper_close_single_finger_m: float = 0.0
    gripper_deadband: float = 0.05
    gripper_single_finger_delta_m: float = 0.008
    gripper_effort_limit_N: float = 8.0

    def __post_init__(self):
        ratio = self.control_hz / self.policy_action_hz
        if abs(ratio - round(ratio)) > 1e-9 or ratio < 1:
            raise ValueError("control_hz/policy_action_hz must be a positive integer")
        if self.maximum_chunk < 1:
            raise ValueError("maximum_chunk must be positive")
        if not 0 < self.execution_translation_cap_m <= self.trained_translation_scale_m:
            raise ValueError("invalid translation cap")
        if not 0 < self.execution_rotation_cap_rad <= self.trained_rotation_scale_rad:
            raise ValueError("invalid rotation cap")

    @property
    def contract_sha256(self) -> str:
        return hashlib.sha256(json.dumps(asdict(self), sort_keys=True).encode()).hexdigest()


class Pi05LiberoAdapter:
    """Actual RPent VLA RPC client plus auditable observation/action mapping."""
    def __init__(self, vla_rpc_client, *, contract: LiberoTransferContract | None = None,
                 robot_base_position_m=(0.0, 0.0, 0.0), robot_base_quaternion_xyzw=(0, 0, 0, 1)):
        from rpent.robots.components.pi05_vla_client import Pi05VLAClient
        from rpent.utils.rpc import wait_for_ready
        wait_for_ready(vla_rpc_client, timeout_s=60.0)
        self.contract = contract or LiberoTransferContract()
        self.server_metadata = vla_rpc_client.call("vla.get_metadata", timeout_s=30)
        expected = {"checkpoint_id": self.contract.checkpoint_id,
                    "weights_sha256": self.contract.expected_weights_sha256,
                    "embodiment": "libero", "output_action_dim": 7,
                    "output_semantics": "libero_normalized_osc_pose_delta_and_gripper_sign",
                    "output_unnormalized_by_server": True}
        for key, value in expected.items():
            if self.server_metadata.get(key) != value:
                raise ValueError(f"checkpoint endpoint contract mismatch at {key}: {self.server_metadata.get(key)!r}")
        self._model = Pi05VLAClient(vla_rpc_client, embodiment="libero")
        self.base_position = _finite_vector(robot_base_position_m, 3, "base position")
        self.base_rotation = Rotation.from_quat(_finite_vector(robot_base_quaternion_xyzw, 4, "base quaternion"))
        self.reset()

    def reset(self):
        self.episode_id = None
        self.inference_calls = 0
        self._last_gripper_target = None

    def encode_observation(self, observation: dict) -> dict:
        view = policy_observation(observation)
        robot = view["TCPpose"]
        # LIBERO state is EE xyz + axis-angle + signed two-finger coordinates.
        # Isaac Franka coordinates are nonnegative for both finger DOFs, whereas
        # LIBERO Panda second coordinate is negative; the sign conversion is explicit.
        position = _finite_vector(robot["position_m"], 3, "TCP position")
        quat_wxyz = _finite_vector(robot["quaternion_wxyz"], 4, "TCP quaternion")
        tcp = np.r_[position, quat_wxyz[1:], quat_wxyz[0]]
        joints = _finite_vector(view["joint_positions"], 9, "joint positions")
        fingers = joints[7:9]
        rel_position = self.base_rotation.inv().apply(tcp[:3] - self.base_position)
        rel_rotation = self.base_rotation.inv() * Rotation.from_quat(tcp[3:])
        states = np.r_[rel_position, rel_rotation.as_rotvec(), fingers[0], -fingers[1]].astype(np.float32)
        return {"main_images": _rgb(view, "side_camera"),
                "wrist_images": _rgb(view, "wrist_camera"),
                "extra_view_images": None, "states": states,
                "task_descriptions": str(view["task_language"])}

    def infer(self, observation: dict) -> tuple[np.ndarray, dict]:
        episode_id = str(observation["episode_id"])
        if self.episode_id is None:
            self.episode_id = episode_id
        if self.episode_id != episode_id:
            raise ValueError("episode changed: call adapter.reset before reusing model history")
        encoded = self.encode_observation(observation)
        started = time.perf_counter()
        raw = np.asarray(self._model.predict(encoded, {"mode": "eval"}), dtype=np.float64)
        elapsed = time.perf_counter() - started
        if raw.ndim != 2 or raw.shape[1] != 7 or raw.shape[0] < 1 or not np.isfinite(raw).all():
            raise ValueError(f"LIBERO checkpoint returned invalid [horizon,7]: {raw.shape}")
        self.inference_calls += 1
        return raw[:self.contract.maximum_chunk], {
            "policy_id": self.contract.checkpoint_id,
            "episode_id": episode_id, "observation_step": int(observation["step_index"]),
            "inference_wall_s": elapsed, "contract": asdict(self.contract),
            "contract_sha256": self.contract.contract_sha256,
            "state_vector": encoded["states"].tolist(),
            "raw_output_shape": list(raw.shape), "inference_call": self.inference_calls,
            "truth_used": False, "dynamics_equivalent_to_libero": False,
            "server_metadata": self.server_metadata,
        }

    def convert_action(self, raw: Any, observation: dict) -> dict:
        """One policy timestep, not an expert primitive and not joint positions."""
        row = _finite_vector(raw, 7, "LIBERO action")
        c = self.contract
        bounded = np.clip(row, -1.0, 1.0)
        dpos_base = np.clip(bounded[:3] * c.trained_translation_scale_m,
                            -c.execution_translation_cap_m, c.execution_translation_cap_m)
        drot_base = np.clip(bounded[3:6] * c.trained_rotation_scale_rad,
                            -c.execution_rotation_cap_rad, c.execution_rotation_cap_rad)
        current = float(np.mean(_finite_vector(np.asarray(observation["joint_positions"])[7:9], 2, "fingers")))
        if self._last_gripper_target is None:
            self._last_gripper_target = current
        direction = 1.0 if bounded[6] < -c.gripper_deadband else -1.0 if bounded[6] > c.gripper_deadband else 0.0
        self._last_gripper_target = float(np.clip(self._last_gripper_target + direction * c.gripper_single_finger_delta_m,
                                           c.gripper_close_single_finger_m, c.gripper_open_single_finger_m))
        return {
            "episode_id": str(observation["episode_id"]),
            "observation_step": int(observation["step_index"]),
            "type": "ee_delta", "frame": "world",
            "values": np.r_[self.base_rotation.apply(dpos_base), self.base_rotation.apply(drot_base)].tolist(),
            "gripper_opening_m": 2.0 * self._last_gripper_target,
            "gripper_effort_limit_N": c.gripper_effort_limit_N,
            "duration_s": 1.0 / c.policy_action_hz,
            "raw_model_action": row.tolist(),
            "conversion": {"checkpoint_semantics": "libero_normalized_osc_pose_delta_and_gripper_sign",
                           "normalized_action_clipped": bounded.tolist(),
                           "robot_base_to_world_rotation_xyzw": self.base_rotation.as_quat().tolist(),
                           "translational_cap_m": c.execution_translation_cap_m,
                           "rotational_cap_rad": c.execution_rotation_cap_rad,
                           "gripper_semantics": "+close/-open sign mapped to bounded stateful finger displacement",
                           "contract_sha256": c.contract_sha256},
        }


def append_event(path: str | Path, event: dict) -> None:
    def default(value):
        if isinstance(value, np.ndarray):
            return value.tolist()
        if isinstance(value, np.generic):
            return value.item()
        if isinstance(value, Path):
            return str(value)
        raise TypeError(type(value).__name__)
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a") as f:
        f.write(json.dumps(event, default=default, allow_nan=False) + "\n")
