"""Stream aligned observations and commanded actions, without buffering RGB in RAM."""
import json
from pathlib import Path
import cv2
import h5py
import numpy as np


class MinimalPickCollector:
    def __init__(self, cfg, output_dir, save_video=True):
        self.cfg = cfg
        self.output = Path(output_dir)
        (self.output / "dataset/meta").mkdir(parents=True, exist_ok=True)
        self.video_dir = self.output / "video"
        self.video_dir.mkdir(exist_ok=True)
        self.save_video = save_video
        self.episode_count = 0
        self.file = self.writer = None

    def begin_episode(self, index, initial_position):
        self.index = index
        self.name = f"episode_{index:04d}"
        self.path = self.output / "dataset" / (self.name + ".h5")
        if self.path.exists():
            raise FileExistsError(self.path)
        self.file = h5py.File(self.path, "x")
        self.file.attrs.update(schema_version="labsim.minimal_pick.v1", task="minimal_pick",
                               control_hz=self.cfg.task.control_hz, physics_hz=120,
                               action_semantics="absolute_joint_position_target_7_arm_plus_1_finger",
                               observation_alignment="obs_t_before_action_t; next_state_after_two_physics_steps",
                               quaternion_order="wxyz", initial_position_m=initial_position,
                               success=False, complete=False)
        self.file.create_dataset("language_instruction", data=self.cfg.task.instruction,
                                 dtype=h5py.string_dtype())
        self.count = 0

    def _append(self, key, value):
        value = np.asarray(value)
        if key not in self.file:
            compression = self.cfg.collector.compression if value.ndim == 3 else None
            self.file.create_dataset(key, shape=(0,) + value.shape, maxshape=(None,) + value.shape,
                                     dtype=value.dtype, chunks=(1,) + value.shape, compression=compression)
        dataset = self.file[key]
        dataset.resize(self.count + 1, axis=0)
        dataset[self.count] = value

    def cache_transition(self, state, action, next_state, result):
        for key, rgb in state["camera_data"].items():
            self._append(key, rgb.astype(np.uint8))
        self._append("agent_pose", state["joint_positions"][:8].astype(np.float32))
        self._append("actions", action.joint_positions[:8].astype(np.float32))
        self._append("next_agent_pose", next_state["joint_positions"][:8].astype(np.float32))
        self._append("joint_positions", state["joint_positions"].astype(np.float32))
        self._append("object_pose", np.concatenate([state["object_position"], state["object_orientation"]]))
        self._append("next_object_pose", np.concatenate([next_state["object_position"], next_state["object_orientation"]]))
        self._append("finger_contact_N", next_state["finger_contact_N"].astype(np.float32))
        self._append("timestamp", np.float64(state["simulation_time"]))
        self._append("lift_m", np.float32(result["final_lift_m"]))
        self._append("hold_seconds", np.float32(result["continuous_hold_seconds"]))
        self._append("done", np.bool_(result["status"] != "RUNNING"))
        self._append("reward", np.float32(result["status"] == "SUCCESS"))
        if self.save_video:
            rgb = np.concatenate([np.transpose(x, (1, 2, 0)) for x in state["camera_data"].values()], axis=1)
            frame = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
            if self.writer is None:
                self.writer = cv2.VideoWriter(str(self.video_dir / (self.name + ".mp4")),
                                             cv2.VideoWriter_fourcc(*"mp4v"), self.cfg.task.control_hz,
                                             (frame.shape[1], frame.shape[0]))
                if not self.writer.isOpened():
                    raise RuntimeError("Could not open MP4 video writer")
            cv2.putText(frame, f"{state['simulation_time']:.2f}s lift={result['final_lift_m']:.3f}m "
                        f"{result['status']}", (8, 20), cv2.FONT_HERSHEY_SIMPLEX, .4, (255, 255, 255), 1)
            self.writer.write(frame)
        self.count += 1

    def finish_episode(self, result):
        self.file.attrs.update(success=result["status"] == "SUCCESS", complete=True,
                               status=result["status"], reason=result["reason"], frames=self.count)
        self.file.create_dataset("task_properties", data=json.dumps(result), dtype=h5py.string_dtype())
        self.close()
        (self.output / (self.name + "_result.json")).write_text(json.dumps(result, indent=2) + "\n")
        with (self.output / "dataset/meta/episode.jsonl").open("a") as f:
            f.write(json.dumps(dict(episode_index=self.index, length=self.count, tasks=[self.cfg.task.instruction],
                                   task_properties=result)) + "\n")
        self.episode_count += 1

    def merge(self):
        # Only complete successes enter imitation training; failures retain their individual logs.
        destination = self.output / "dataset/episode_data.hdf5"
        successes = 0
        with h5py.File(destination, "x") as merged:
            for path in sorted((self.output / "dataset").glob("episode_*.h5")):
                with h5py.File(path, "r") as episode:
                    if not episode.attrs.get("success", False) or not episode.attrs.get("complete", False):
                        continue
                    group = merged.create_group(path.stem)
                    group.attrs.update(dict(episode.attrs))
                    for key in episode:
                        episode.copy(key, group)
                    successes += 1
        return destination, successes

    def close(self):
        if self.writer is not None:
            self.writer.release()
            self.writer = None
        if self.file is not None:
            self.file.close()
            self.file = None
