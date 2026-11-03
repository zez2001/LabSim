"""Instrument tasks implement the current LabSim public executor task protocol.

The release ProjectEnvironment owns bounded actions and receipts. Only this
module knows task truth; it never includes it in public observations.
"""

import hashlib
import json
from pathlib import Path
import uuid

import numpy as np
from omegaconf import OmegaConf
from scipy.spatial.transform import Rotation

from demos.cell_assets.cameras import VideoRecorder, read_rgb
from demos.cell_assets.motion import sample_joints
from demos.cell_units import registry, sensors
from demos.cell_units.recording import Recorder
from demos.cell_units.scorer import score


class UnitTask:
    """One fixed instrument episode behind the shared release executor.

    Args:
        unit_id: Registered task ID from config/cell_units/units.json.
        output: New run directory; existing results are never overwritten.
        cache: Source asset cache, or None for the configured default.
        backend: Controller label recorded in the episode, not a controller factory.
        initial_state: Default scene or the explicitly separated placement preparation.
    """

    ACTION_SPECS = {
        "joint_position": "7 radians; symmetric opening separately",
        "ee_delta": "world/tcp translation3 metres + rotvec3 radians",
        "ee_pose": "world xyz metres + quaternion wxyz",
    }

    def __init__(self, unit_id, output, cache=None, backend="teacher", initial_state="default"):
        self.unit = registry.get_unit(unit_id)
        if initial_state not in {"default", "placement-ready"}:
            raise ValueError(f"Unknown initial state: {initial_state}")
        if initial_state == "placement-ready" and (
            unit_id not in {"flex_load", "magsep_transfer"} or backend == "teacher"
        ):
            raise ValueError("placement-ready requires a Flex/MagSep policy controller")
        self.output, self.cache, self.backend = Path(output), cache, backend
        self.output.mkdir(parents=True, exist_ok=False)
        self.episode_index = 0
        self.ended, self._result = True, None
        self.cfg = OmegaConf.create(
            dict(
                physics=dict(hz=120, control_hz=120),
                project=dict(backend_gripper_effort_N=8),
                robot=dict(base_m=[0, 0, 0]),
                release=dict(record_mode="collect" if backend == "teacher" else "eval"),
            )
        )
        self.world = None
        self.views, self.policy_views = {}, {}
        self.video = self.recorder = None
        self.initial_state = initial_state

    @staticmethod
    def _write(path, value):
        Path(path).write_text(
            json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        )

    def reset(self, seed=0, options=None):
        if not self.ended:
            self.finalize_episode("RESET_INTERRUPTED", "PROCESS_INTERRUPTED")
        self._clear_scene()
        self.episode_dir = self.output / f"episode_{self.episode_index:04d}"
        self.episode_index += 1
        self.episode_id = str(uuid.uuid4())
        registry.build(self.unit, self.episode_dir, self.cache, self._bind)
        hz = round(1 / self.scene["dt"])
        self.cfg.physics.hz = self.cfg.physics.control_hz = hz
        if self.initial_state == "placement-ready":
            from demos.cell_units.placement import prepare

            prepare(self)
        from isaacsim.core.prims import Articulation

        self.robot_view = Articulation(prim_paths_expr="/World/Franka", name="unit_robot_view")
        self.robot_view.initialize()
        self.control_steps = self.steps = 0
        self.t = 0.0
        self.start = self.world.current_time
        self._result = None
        self.records = []
        self.qcmd = self.robot.get_joint_positions().copy()
        self.grip = float(sum(self.qcmd[-2:]))
        self.effort = self.unit.get("effort_limit_N", 8.0)
        self.camera_paths, self.policy_views = sensors.create(self.scene["stage"])
        for _ in range(6):
            self.world.render()
        self.video = VideoRecorder(self.episode_dir, self.views)
        self.video.write()
        self.cfg.robot.base_m = self.robot.get_world_pose()[0].tolist()
        source_files = list((registry.ROOT / "demos/cell_units").glob("*.py")) + [registry.REGISTRY]
        source_files += list((registry.ROOT / "config/cell_units").glob("*.json"))
        source_files += [
            registry.ROOT / ("demos/cell_assets/" + n)
            for n in ("handling.py", "cap_cycle.py", "hood_open.py", "motion.py", "cameras.py")
        ]
        source_files += [
            registry.ROOT / n
            for n in (
                "utils/cell_assets.py",
                "utils/ika_gas_springs.py",
                "config/cell_assets/catalog.json",
                "config/cell_assets/ika_gas_springs.json",
                "demos/minimal_pick/scene.py",
                "assets/robots/Franka.usd",
                "demos/lab_cuvette_project_v1/environment.py",
                "demos/lab_cuvette_project_v1/rpc.py",
                "demos/lab_cuvette_project_v1_1/environment.py",
                "demos/lab_cuvette_project_release_v1/environment.py",
                "demos/lab_cuvette_project_release_v1/rpc.py",
                "policy_backends/lab_cuvette_env_v1/policy_adapters.py",
                "policy_backends/lab_cuvette_env_v1/pi05_rollout.py",
                "policy/backends/cubence.py",
                "policy/backends/cubence_project_v1_1_tools.py",
            )
        ]
        provenance = dict(
            unit=self.unit,
            scene_version=registry.VERSION,
            seed=seed,
            physical_setup=self.metadata,
            upstream_commit=json.loads(registry.REGISTRY.read_text())["upstream_commit"],
            code_sha256={
                str(p.relative_to(registry.ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in source_files
            },
            real_calibrated=False,
            policy_object_truth_visible=False,
        )
        self._write(self.episode_dir / "scene_contract.json", provenance)
        self.recorder = Recorder(
            self.episode_dir,
            dict(
                scene_version=registry.VERSION,
                unit_id=self.unit["id"],
                backend=self.backend,
                episode_id=self.episode_id,
                initial_state=self.initial_state,
                record_purpose=(
                    "demonstration" if self.backend == "teacher" else "policy_evaluation"
                ),
                physics_hz=hz,
                observation_hz=30,
                real_calibrated=False,
                action_semantics=f"{hz}Hz joint targets; physics_count excludes padding",
                scene_contract_sha256=hashlib.sha256(
                    json.dumps(provenance, sort_keys=True).encode()
                ).hexdigest(),
            ),
        )
        self._refresh()
        self.recorder.observation(self._observation)
        self.ended = False

    def _bind(
        self,
        *,
        scene,
        views,
        motions,
        measure,
        targets,
        grip_offset,
        metadata,
        contact,
        before_step=None,
        teacher_control=None,
    ):
        self.scene, self.views = scene, views
        self.world, self.robot, self.solver = scene["world"], scene["robot"], scene["solver"]
        self.motions = motions[
            : next(i for i, m in enumerate(motions) if m.name == self.unit["last_phase"]) + 1
        ]
        self.measure, self.targets, self.grip_offset = measure, targets, grip_offset
        self.metadata, self.contact, self.before_step = metadata, contact, before_step
        self.teacher_control = teacher_control
        if self.unit["id"] == "magsep_transfer":
            from isaacsim.core.api.objects import VisualCuboid

            self.world.scene.add(
                VisualCuboid(
                    prim_path="/World/TargetMarker",
                    name="target_marker",
                    position=np.asarray(targets["loaded"]) - [0, 0, 0.0008],
                    scale=np.array([0.14, 0.07, 0.0002]),
                    color=np.array([0.5, 0.8, 0.05]),
                )
            )

    def _refresh(self):
        self.world.render()
        position, rotation = self.solver.compute_end_effector_pose()
        self._observation = dict(
            episode_id=self.episode_id,
            observation_id=f"{self.episode_id}:{self.control_steps}",
            step_index=self.control_steps,
            simulation_time=self.t,
            scene_version=registry.VERSION,
            task_language=self.unit["goal"],
            joint_positions=self.robot.get_joint_positions().copy(),
            joint_velocities=self.robot.get_joint_velocities().copy(),
            TCPpose=dict(
                position_m=position.tolist(),
                quaternion_wxyz=np.roll(Rotation.from_matrix(rotation).as_quat(), 1).tolist(),
            ),
            gripper_opening_m=float(sum(self.robot.get_joint_positions()[-2:])),
            gripper_effort_limit_N=self.effort,
            finger_contact_N=np.linalg.norm(
                self.contact.get_contact_force_matrix(dt=self.scene["dt"]), axis=-1
            )
            .ravel()
            .tolist(),
            images={name: read_rgb(view) for name, view in self.policy_views.items()},
        )

    def get_observation(self):
        # RGB is refreshed at action boundaries before a public observation.
        if self._observation["step_index"] != self.control_steps:
            self._refresh()
        return dict(self._observation)

    def get_camera_meta(self, name):
        return sensors.metadata(self.scene["stage"], self.camera_paths[name], name, self.t)

    def forward(self, q):
        kin = self.solver.get_kinematics_solver()
        return kin.compute_forward_kinematics(self.solver.get_end_effector_frame(), np.asarray(q))

    def joint_bounds(self):
        properties = self.robot.dof_properties
        return properties["lower"][:7], properties["upper"][:7], np.array([2.175] * 4 + [2.61] * 3)

    def plan_cartesian(self, references):
        from demos.cell_units.kinematics import solve_step

        current = self.qcmd[:7].copy()
        path = []
        lower, upper, speed = self.joint_bounds()
        failure = None
        diagnostic = None
        for position, rotation in references:
            q, ok, diagnostic = solve_step(
                self.forward, current, position, rotation, lower, upper, speed * self.scene["dt"]
            )
            if not ok:
                failure = "IK_OR_CONTINUITY_LIMIT"
                break
            path.append(q)
            current = q
        return dict(
            success=failure is None,
            q7=path,
            failure=failure,
            summary=dict(
                planned_ticks=len(path), requested_ticks=len(references), failure_detail=diagnostic
            ),
        )

    def hold_actual_joints(self):
        from isaacsim.core.utils.types import ArticulationAction

        self.qcmd = self.robot.get_joint_positions().copy()
        self.robot.apply_action(ArticulationAction(joint_positions=self.qcmd))

    def _advance(self, q, phase):
        from isaacsim.core.utils.types import ArticulationAction

        if self.ended:
            raise ValueError("Episode ended")
        mechanism = self.before_step() if self.before_step else []
        self.qcmd = np.asarray(q).copy()
        self.robot.apply_action(ArticulationAction(joint_positions=self.qcmd))
        self.world.step(render=False)
        self.control_steps += 1
        self.steps += 1
        self.t = self.control_steps * self.scene["dt"]
        row = self.measure(q, phase, self.start)
        if mechanism:
            row["gas_springs"] = mechanism
        self.records.append(row)
        self.recorder.physics(row)
        if len(self.recorder.targets) == self.recorder.stride:
            self._refresh()
            self.recorder.transition(self._observation)
            self.video.write()
        hood = self.unit["builder"] == "hood"
        force = max(
            row["unintended_robot_device_force_n" if hood else "robot_device_force_n"],
            row["robot_environment_force_n" if hood else "robot_table_force_n"],
        )
        if force > 5:
            self.finalize_episode("UNINTENDED_COLLISION", "SAFETY_FAILURE")

    def step(self, action):
        # All public commands arrive through the release facade's preplanner.
        self.grip = float(action["gripper_opening_m"])
        self.effort = min(
            float(action["gripper_effort_limit_N"]), self.unit.get("effort_limit_N", 8.0)
        )
        self.robot_view.set_max_efforts(
            np.array([[self.effort, self.effort]]), joint_indices=np.array([7, 8])
        )
        q = np.r_[action["_executor_q7"], self.grip / 2, self.grip / 2]
        self._advance(q, "policy")

    def run_teacher(self):
        for motion in self.motions:
            opening = float(self.qcmd[-1])
            for i in range(round(motion.duration / self.scene["dt"])):
                if self.ended:
                    return self._result
                f = (i + 1) * self.scene["dt"] / motion.duration
                blend = f * f * (3 - 2 * f)
                aperture = (
                    opening + (motion.aperture - opening) * blend
                    if self.unit.get("smooth_gripper")
                    else motion.aperture
                )
                q = np.r_[sample_joints(motion.joints, blend), aperture, aperture]
                if self.teacher_control is not None:
                    q = self.teacher_control(q, motion.name, blend)
                self.grip = 2 * aperture
                self._advance(q, motion.name)
            print("UNIT_PHASE", self.unit["id"], motion.name, round(self.t, 3), flush=True)
        return self.finalize_episode("TEACHER_FINISHED")

    def finalize_episode(self, reason, failure_type=None):
        if self.ended:
            return self._result
        result = score(self.unit, self.records, self.targets, self.grip_offset, self.scene["dt"])
        result.update(
            episode_id=self.episode_id,
            unit_id=self.unit["id"],
            backend=self.backend,
            termination_reason=reason,
            failure_type=failure_type,
            steps=self.steps,
            duration_s=self.t,
            real_calibrated=False,
        )
        if failure_type:
            result["task_success"] = False
        if self.recorder.targets:
            self._refresh()
            self.recorder.transition(self._observation)
        self.video.close()
        self.recorder.close(result)
        self._write(self.episode_dir / "independent_score.json", result)
        self._write(self.episode_dir / "result.json", result)
        self._write(
            self.episode_dir / "complete.json", dict(episode_id=self.episode_id, closed=True)
        )
        self.ended, self._result = True, result
        return result

    def _clear_scene(self):
        if self.world is None:
            return
        for view in (*self.views.values(), *self.policy_views.values()):
            view.detach()
        self.world.stop()
        self.world.clear()
        self.world.clear_instance()
        self.world = self.scene = self.robot = self.robot_view = self.solver = None
        self.contact = self.measure = self.before_step = self.teacher_control = None
        self.views, self.policy_views = {}, {}

    def close(self):
        """Close partial initialization without inventing a completed episode."""
        try:
            if not self.ended:
                self.finalize_episode("APPLICATION_CLOSED", "PROCESS_INTERRUPTED")
        finally:
            if self.video is not None:
                self.video.close()
            if self.recorder is not None:
                self.recorder.close()
            self._clear_scene()
