"""Formal Env_v1 streaming collector, independent of teacher/policy implementation.

The legacy 8D reader mapping is explicit: arm q[0:7] in rad and the left
finger q[7] in metres. The actual two-finger 9D command, raw model output,
conversion, effort caps, successor state and independent outcomes are retained.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path

import cv2
import h5py
import numpy as np
from omegaconf import OmegaConf

from data_collectors.minimal_pick_collector import MinimalPickCollector
from utils.episode_selection import NON_PHYSICAL_FAILURES, episode_matches_filter


def json_safe(value):
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, np.ndarray):
        return json_safe(value.tolist())
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, (np.integer, int)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return float(value) if np.isfinite(value) else None
    if isinstance(value, Path):
        return str(value)
    return value


def json_text(value):
    return json.dumps(json_safe(value), ensure_ascii=False, sort_keys=True, allow_nan=False)


def _known_bool(value):
    return bool(value) if isinstance(value, (bool, np.bool_)) else None


class LabCuvetteEnvV1Collector(MinimalPickCollector):
    """begin/cache/finish lifecycle compatible with existing streaming collectors.

    ``finish_episode`` needs a separate scorer mapping/path. Missing adjudication
    leaves outcome unknown, never a success or a physical-failure training label.
    ``close`` alone closes an incomplete episode after an interrupted process.
    """
    CAMERAS = ("side_camera_rgb", "wrist_camera_rgb")

    def __init__(self, cfg, output_dir, save_video=True, *, scene_contract=None,
                 camera_meta=None):
        data = OmegaConf.to_container(cfg, resolve=True) if OmegaConf.is_config(cfg) else dict(cfg)
        data = json.loads(json_text(data))
        physics = data.setdefault("physics", {})
        physics.setdefault("control_hz", 60)
        physics.setdefault("hz", 240)
        if not isinstance(data.get("task"), dict):
            data["task"] = {}
        data["task"].setdefault("instruction", "Load the vessel from the specified rack slot into the internal instrument seat.")
        data["task"].setdefault("control_hz", physics["control_hz"])
        data.setdefault("collector", {}).setdefault("compression", "lzf")
        super().__init__(OmegaConf.create(data), output_dir, save_video)
        self.configuration = data
        self.scene_contract = dict(scene_contract or {})
        self.camera_meta = dict(camera_meta or {})
        self._integrity_errors = []

    def begin_episode(self, index, initial_position=None, *, episode_id=None, metadata=None):
        self.index, self.name = int(index), f"episode_{int(index):04d}"
        self.path = self.output / "dataset" / (self.name + ".h5")
        if self.file is not None:
            raise RuntimeError("Finish/close current episode before beginning another")
        self.file = h5py.File(self.path, "x")
        self.episode_id = str(episode_id or uuid.uuid4())
        self.count, self._integrity_errors, self._last_time = 0, [], None
        self._camera_black_counts = dict.fromkeys(self.CAMERAS, 0)
        self._phases = []
        self._terminal_observation = None
        attrs = dict(schema_version="labsim.lab_cuvette_loading.Env_v1.v1", task="lab_cuvette_loading",
            scene_version=self.configuration.get("version", "Env_v1"), episode_id=self.episode_id,
            action_semantics="absolute_7_arm_rad_and_symmetric_finger_metre",
            legacy_8d_mapping="agent_pose/actions=[arm_q0..q6(rad),left_finger_q7(m)]; actual right_finger_q8 stored separately",
            executed_action_semantics="absolute_position_9d:7_arm_rad+left_and_right_finger_m",
            observation_alignment="obs_before_action; next_state_after_explicit_substeps",
            control_hz=float(self.cfg.physics.control_hz), physics_hz=float(self.cfg.physics.hz),
            policy_observation_scope="camera_data+proprioception+task language; privileged/* excluded",
            complete=False, success=False, task_success="unknown", task_success_known=False,
            record_valid=False, eligible_for_success_bc=False, eligible_for_failure_analysis=False,
            real_calibrated=False, quaternion_order="wxyz",
            camera_legacy_mapping_json=json_text({"camera_1_rgb": "side_camera_rgb", "camera_2_rgb": "wrist_camera_rgb"}),
            camera_meta_json=json_text(self.camera_meta), scene_contract_json=json_text(self.scene_contract),
            configuration_json=json_text(self.configuration))
        initial = initial_position if initial_position is not None else [np.nan] * 3
        attrs["initial_position_m"] = np.asarray(initial, float)
        metadata = dict(metadata or {})
        attrs.update(seed="unknown", policy_id="unknown", demonstrator_id="unknown",
                     asset_version=self.scene_contract.get("asset_manifest_sha256", "unknown"),
                     task_type="loading")
        for key in ("seed", "policy_id", "demonstrator_id", "asset_version", "source_slot_id", "target_seat_id", "task_type"):
            if metadata.get(key) is not None:
                attrs[key] = metadata[key]
            elif self.scene_contract.get(key) is not None:
                attrs[key] = self.scene_contract[key]
        self.file.attrs.update(attrs)
        self.file.create_dataset("language_instruction", data=self.cfg.task.instruction, dtype=h5py.string_dtype())
        self.file.create_dataset("episode_metadata_json", data=json_text(metadata), dtype=h5py.string_dtype())

    def _append_text(self, key, value):
        if key not in self.file:
            self.file.create_dataset(key, shape=(0,), maxshape=(None,), chunks=(1,), dtype=h5py.string_dtype())
        self.file[key].resize(self.count + 1, axis=0)
        self.file[key][self.count] = str(value)

    def cache_transition(self, state, action, next_state, result):
        if self.file is None:
            raise RuntimeError("begin_episode must precede cache_transition")
        for observed in (state, next_state):
            if observed.get("episode_id", self.episode_id) != self.episode_id:
                raise ValueError("Refusing transition from a different/old episode")
        q, next_q = np.asarray(state["joint_positions"], float), np.asarray(next_state["joint_positions"], float)
        if q.shape != (9,) or next_q.shape != (9,):
            raise ValueError("Expected measured nine joint positions, including both fingers")
        auxiliary = next_state.get("control_aux", {})
        command = dict(action) if isinstance(action, dict) else {"command_q": getattr(action, "joint_positions", None)}
        if command.get("episode_id", self.episode_id) != self.episode_id:
            raise ValueError("Refusing action from a different/old episode")
        executed = command.get("command_q", command.get("executed_q", auxiliary.get("command_q")))
        executed = np.asarray(executed, float)
        if executed.shape != (9,) or not np.isfinite(executed).all():
            raise ValueError("Executed command must be finite nine-dimensional absolute position")
        before, after = float(state["simulation_time"]), float(next_state["simulation_time"])
        dt = 1.0 / float(self.cfg.physics.control_hz)
        measured_dt=after-before
        physics_dt=1./float(self.cfg.physics.hz)
        terminal=bool(result.get("terminated",False) or result.get("truncated",False))
        partial_terminal=bool(terminal and np.isfinite(measured_dt) and physics_dt-1e-8<=measured_dt<dt-1e-6
            and abs(measured_dt/physics_dt-round(measured_dt/physics_dt))<1e-6)
        if not np.isfinite([before, after]).all() or (abs(measured_dt-dt)>1e-6 and not partial_terminal):
            self._integrity_errors.append(f"invalid_control_interval_at_{self.count}")
        if self._last_time is not None and abs(before-self._last_time) > 1e-6:
            self._integrity_errors.append(f"discontinuous_observation_time_at_{self.count}")
        self._last_time = after
        if not np.isfinite(q).all() or not np.isfinite(next_q).all():
            self._integrity_errors.append(f"nonfinite_robot_state_at_{self.count}")
        camera_data = state["camera_data"]
        for camera in self.CAMERAS:
            rgb = np.asarray(camera_data[camera])
            if rgb.ndim != 3 or rgb.shape[0] != 3 or rgb.dtype != np.uint8:
                raise ValueError(f"{camera} must be CHW RGB uint8")
            self._append(camera, rgb)
            self._camera_black_counts[camera] += int(np.max(rgb) <= 1)
            alias = "camera_1_rgb" if camera == self.CAMERAS[0] else "camera_2_rgb"
            if alias not in self.file:
                self.file[alias] = self.file[camera]  # hard link, not an external dependency or copied image
        effort = command.get("gripper_effort_limit_N", auxiliary.get("gripper_effort_limit_N"))
        effort = np.asarray(effort if effort is not None else [np.nan, np.nan], float)
        if effort.shape == ():
            effort = np.repeat(effort, 2)
        if effort.shape != (2,):
            raise ValueError("Gripper effort cap must be per-finger scalar or two-vector")
        grip = command.get("gripper_target_m", auxiliary.get("gripper_target_m"))
        grip = float(grip) if grip is not None else np.nan
        # Keep one terminal frame only; images are streamed, not accumulated in RAM.
        self._terminal_observation = dict(joint_positions=next_q.copy(), simulation_time=after,
            step_index=next_state.get("step_index", self.count+1),
            camera_data={k: np.asarray(next_state["camera_data"][k]).copy() for k in self.CAMERAS})
        phase = str(state.get("phase", "UNKNOWN"))
        if phase not in self._phases:
            self._phases.append(phase)
        fields = dict(agent_pose=q[:8].astype(np.float32), actions=executed[:8].astype(np.float32),
            next_agent_pose=next_q[:8].astype(np.float32), joint_positions=q, next_joint_positions=next_q,
            timestamp=np.float64(before), next_timestamp=np.float64(after),
            control_interval_s=np.float64(measured_dt),partial_terminal_control_interval=np.bool_(partial_terminal),
            obs_step=np.int64(state.get("step_index", self.count)), next_obs_step=np.int64(next_state.get("step_index", self.count+1)),
            done=np.bool_(result.get("terminated", False) or result.get("truncated", False)),
            reward=np.float32(result.get("reward", 0.0)), phase_code=np.int32(self._phases.index(phase)),
            **{"control_auxiliary/command_q": executed, "control_auxiliary/gripper_effort_limit_N": effort,
               "control_auxiliary/gripper_target_m": np.float64(grip),
               "control_auxiliary/available": np.bool_(np.isfinite(effort).all() and np.isfinite(grip)),
               "inference_wall_time_s": np.float64(command.get("inference_wall_time_s", np.nan))})
        for camera in self.CAMERAS:
            capture = state.get("camera_timestamps", {}).get(camera, before)
            fields["camera_timestamp/" + camera] = np.float64(capture)
        for key, value in fields.items():
            self._append(key, value)
        for key, value in (("phase", phase), ("episode_id", self.episode_id),
                           ("actions_raw_json", json_text(command.get("raw_output", command.get("raw_action", {"command_q": executed})))),
                           ("action_conversion_json", json_text(command.get("conversion", {}))),
                           ("task_events_json", json_text(result.get("events", []))),
                           ("camera_pose_json", json_text(state.get("camera_poses", state.get("camera_meta"))))):
            self._append_text(key, value)
        # The environment may pass arbitrary scorer truth separately. It never
        # becomes a default visual policy observation through this collector.
        self._append_text("privileged/state_json", json_text(state.get("debug", {})))
        self._append_text("privileged/next_state_json", json_text(next_state.get("debug", {})))
        if self.save_video:
            rgb = np.concatenate([np.transpose(camera_data[k], (1, 2, 0)) for k in self.CAMERAS], axis=1)
            frame = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
            if self.writer is None:
                self.writer = cv2.VideoWriter(str(self.video_dir / (self.name + ".mp4")),
                    cv2.VideoWriter_fourcc(*"mp4v"), float(self.cfg.physics.control_hz), (frame.shape[1], frame.shape[0]))
                if not self.writer.isOpened():
                    raise RuntimeError("Could not open continuous dual-view writer")
            cv2.putText(frame, f"side | wrist  t={before:.3f}s  {phase}", (6, 18),
                        cv2.FONT_HERSHEY_SIMPLEX, .4, (255, 255, 255), 1)
            self.writer.write(frame)
        self.count += 1

    def finish_episode(self, result, independent_score=None):
        if self.file is None:
            raise RuntimeError("No open episode")
        score_sha = None
        if isinstance(independent_score, (str, Path)):
            source = Path(independent_score)
            evidence = json.loads(source.read_text(encoding="utf-8"))
            score_sha = hashlib.sha256(source.read_bytes()).hexdigest()
        elif isinstance(independent_score, dict):
            evidence = dict(independent_score)
            score_sha = hashlib.sha256(json_text(evidence).encode()).hexdigest()
        else:
            evidence = {}
        if evidence.get("episode_id") != self.episode_id:
            self._integrity_errors.append("missing_or_different_independent_score_episode_id")
        if not self.count:
            self._integrity_errors.append("no_transitions")
        if self.count and not self.file["control_auxiliary/available"][:].all():
            self._integrity_errors.append("auxiliary_control_incomplete")
        for camera, count in self._camera_black_counts.items():
            if self.count and count == self.count:
                self._integrity_errors.append(f"all_frames_black:{camera}")
        outcome = _known_bool(evidence.get("task_success"))
        geometry = _known_bool(evidence.get("geometry_valid"))
        failure = str(evidence.get("failure_type", result.get("failure_type", "UNKNOWN")))
        reason = str(evidence.get("termination_reason", result.get("termination_reason", result.get("reason", "UNKNOWN"))))
        task_type = str(evidence.get("task_type", self.file.attrs.get("task_type", "loading")))
        record_valid = bool(_known_bool(evidence.get("record_valid")) is True and not self._integrity_errors)
        if failure.upper() in NON_PHYSICAL_FAILURES:
            record_valid = False
        success_bc = bool(record_valid and outcome is True and geometry is True and task_type == "loading")
        failure_analysis = bool(record_valid and outcome is False and task_type == "loading"
                                and failure.upper() not in NON_PHYSICAL_FAILURES and failure != "UNKNOWN")
        labels = dict(record_valid=record_valid, task_success=outcome, geometry_valid=geometry,
            failure_type=failure, termination_reason=reason, task_type=task_type,
            eligible_for_success_bc=success_bc, eligible_for_failure_analysis=failure_analysis,
            real_calibrated=False, complete=True, frames=self.count)
        attrs = {k: ("unknown" if v is None else v) for k, v in labels.items()}
        attrs.update(success=success_bc, workflow_success=bool(outcome is True and task_type == "loading"),
            task_success_known=outcome is not None, phase_names_json=json_text(self._phases),
            independent_score_sha256=score_sha or "unavailable", record_integrity_json=json_text(self._integrity_errors),
            camera_black_frame_counts_json=json_text(self._camera_black_counts))
        self.file.attrs.update(attrs)
        self.file.create_dataset("independent_score_json", data=json_text(evidence), dtype=h5py.string_dtype())
        properties = dict(result=result, labels=labels, record_integrity_errors=self._integrity_errors)
        self.file.create_dataset("task_properties", data=json_text(properties), dtype=h5py.string_dtype())
        if self._terminal_observation is not None:
            terminal = self.file.create_group("terminal_observation")
            terminal.attrs.update(simulation_time=self._terminal_observation["simulation_time"],
                                  step_index=self._terminal_observation["step_index"])
            terminal.create_dataset("joint_positions", data=self._terminal_observation["joint_positions"])
            for camera, rgb in self._terminal_observation["camera_data"].items():
                terminal.create_dataset(camera, data=rgb, compression=self.cfg.collector.compression)
            if self.writer is not None:
                rgb = np.concatenate([np.transpose(self._terminal_observation["camera_data"][k], (1, 2, 0))
                                      for k in self.CAMERAS], axis=1)
                self.writer.write(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
            self.file.attrs["video_frame_count"] = self.count + 1 if self.writer is not None else 0
        if self.count:
            self.file["done"][-1] = True
            self.file["reward"][-1] = float(outcome is True)
        self.close()
        with (self.output / (self.name + "_result.json")).open("x", encoding="utf-8") as stream:
            stream.write(json.dumps(json_safe(properties), ensure_ascii=False, indent=2, allow_nan=False) + "\n")
        with (self.output / "dataset/meta/episode.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json_text(dict(episode_id=self.episode_id, episode_index=self.index,
                                       length=self.count, labels=labels)) + "\n")
        self.episode_count += 1
        return labels

    def merge(self, sample_filter="all_valid"):
        """Create a portable normal-reader index, copying complete selected data."""
        destination = self.output / "dataset/episode_data.hdf5"
        copied = 0
        with h5py.File(destination, "x") as merged:
            merged.attrs.update(schema_version="labsim.Env_v1.index.v1", sample_filter=sample_filter)
            for source in sorted((self.output / "dataset").glob("episode_*.h5")):
                with h5py.File(source, "r") as episode:
                    accepted, _ = episode_matches_filter(episode.attrs, sample_filter)
                    if not accepted:
                        continue
                    group = merged.create_group(source.stem)
                    group.attrs.update(dict(episode.attrs))
                    for key in episode:
                        episode.copy(key, group)
                    copied += 1
        return destination, copied
