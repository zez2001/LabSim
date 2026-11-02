"""Self-contained RGB/state/action transitions with explicit pre/post timing."""

import json
from pathlib import Path

import h5py
import numpy as np

from demos.lab_cuvette_project_release_v1.recording import LosslessGzipTextSink


class Recorder:
    def __init__(self, directory, attributes):
        self.path = Path(directory) / "episode.h5"
        self.file = h5py.File(self.path, "x")
        self.file.attrs.update(attributes)
        self.file.attrs["closed"] = False
        self.stride = round(
            attributes.get("physics_hz", 120) / attributes.get("observation_hz", 30)
        )
        self.trace = LosslessGzipTextSink(Path(directory) / "physics.jsonl.gz")
        self.targets = []
        self.steps = []

    def append(self, key, value):
        value = np.asarray(value)
        if key not in self.file:
            self.file.create_dataset(
                key,
                shape=(0, *value.shape),
                maxshape=(None, *value.shape),
                chunks=(1, *value.shape),
                dtype=value.dtype,
                compression="gzip",
                compression_opts=1,
            )
        dataset = self.file[key]
        dataset.resize(dataset.shape[0] + 1, axis=0)
        dataset[-1] = value

    def observation(self, obs):
        self.append("observations/time_s", float(obs["simulation_time"]))
        self.append("observations/qpos", obs["joint_positions"])
        self.append("observations/qvel", obs["joint_velocities"])
        for name, image in obs["images"].items():
            self.append("observations/images/" + name, image)
        self.append(
            "observations/tcp",
            np.r_[obs["TCPpose"]["position_m"], obs["TCPpose"]["quaternion_wxyz"]],
        )

    def physics(self, row):
        self.trace.write(json.dumps(row, allow_nan=False) + "\n")
        self.targets.append(row["joint_target"])
        self.steps.append(row["time_s"])

    def transition(self, obs):
        if not self.targets:
            return
        # One physics_hz / observation_hz block per RGB transition. Last partial
        # intervals retain their true count/time; padding is never executed.
        count = len(self.targets)
        padded = np.zeros((self.stride, 9), dtype=np.float64)
        padded[:count] = self.targets
        self.append("actions/joint_targets", padded)
        self.append("actions/physics_count", count)
        self.append("actions/time_end_s", self.steps[-1])
        self.observation(obs)
        self.targets.clear()
        self.steps.clear()

    def close(self, result=None):
        """Release writers; only a supplied result marks a completed episode."""
        if not self.file.id.valid:
            return
        self.trace.close()
        if result is not None:
            self.file.attrs.update(
                task_success=result["task_success"],
                termination_reason=result["termination_reason"],
                closed=True,
            )
        self.file.flush()
        self.file.close()


def check_dataset(path):
    """Validate all action blocks and their clocks, then read a sample batch.

    Args:
        path: Closed unit H5 file or the directory containing episode.h5.

    Returns:
        Data version, dimensions, duration and recorded outcome. This is a CPU
        data-integrity check, not an independent physics success judgement.

    Raises:
        ValueError: The version, closure, shapes, actions or clocks are invalid.
    """
    path = Path(path)
    if path.is_dir():
        path = path / "episode.h5"
    with h5py.File(path, "r") as f:
        version = f.attrs.get("scene_version")
        if version not in {"SingleCellUnit_v1", "SingleCellUnit_v2"} or not f.attrs.get("closed"):
            raise ValueError("Expected a closed SingleCellUnit_v1/v2 episode")
        n = len(f["actions/joint_targets"])
        times = f["observations/time_s"][:]
        counts = f["actions/physics_count"][:]
        hz = int(f.attrs.get("physics_hz", 120))
        stride = round(hz / f.attrs.get("observation_hz", 30))
        if len(times) != n + 1 or n == 0 or not np.allclose(np.diff(times), counts / hz, atol=1e-6):
            raise ValueError("Incomplete or misaligned transition timeline")
        if not np.all((counts >= 1) & (counts <= stride)):
            raise ValueError("Invalid applied substep count")
        actions = f["actions/joint_targets"]
        if actions.shape != (n, stride, 9):
            raise ValueError("Joint target shape must be transitions x stride x 9")
        ends = f["actions/time_end_s"][:]
        # The simulator accumulates a float32 physics step while observation
        # timestamps use the nominal rate. Allow clock precision, not a substep.
        clock_tolerance = 1e-6 + np.finfo(np.float32).eps * np.abs(times[1:])
        if ends.shape != (n,) or not np.all(np.abs(ends - times[1:]) <= clock_tolerance):
            raise ValueError("Action end times disagree with observations")
        for key in ("qpos", "qvel", "tcp", "images/side_camera", "images/wrist_camera"):
            if len(f["observations/" + key]) != n + 1:
                raise ValueError("Observation length mismatch: " + key)
        for start in range(0, n, 256):
            if not np.isfinite(actions[start : start + 256]).all():
                raise ValueError("Nonfinite actions")
        batch = actions[: min(8, n)]
        return dict(
            scene_version=version,
            transitions=n,
            physics_steps=int(sum(counts)),
            batch_shape=list(batch.shape),
            task_success=bool(f.attrs["task_success"]),
            backend=f.attrs["backend"],
            record_purpose=f.attrs["record_purpose"],
            duration_s=float(times[-1] - times[0]),
            training_run=False,
            validated_action_blocks=n,
        )
