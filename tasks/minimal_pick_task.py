"""Independent physical task with the repository's BaseTask state interface."""
import numpy as np
from pxr import UsdGeom
from isaacsim.sensors.camera import Camera
from isaacsim.core.utils.viewports import set_camera_view
from tasks.base_task import BaseTask
from demos.minimal_pick.scene import build_scene


class MinimalPickTask(BaseTask):
    def __init__(self, cfg, world=None, stage=None, robot=None):
        # This scene must be built from scratch, so lab object/material setup is omitted.
        self.cfg = cfg
        self.scene = build_scene()
        self.world, self.stage, self.robot = (self.scene[k] for k in ("world", "stage", "robot"))
        self.beaker = self.scene["beaker"]
        self.contacts = self.scene["contact_view"]
        self.solver = self.scene["solver"]
        self.dt = 1.0 / cfg.task.control_hz
        if not np.isclose(self.dt, 2 * self.scene["dt"]):
            raise ValueError("This task requires 60 Hz control and 120 Hz physics")
        self.cameras = {}
        for c in cfg.cameras:
            camera = Camera(prim_path=c.prim_path, name=c.name,
                            frequency=cfg.task.control_hz, resolution=tuple(c.resolution))
            camera.set_focal_length(c.focal_length)
            camera.set_clipping_range(0.03, 10.0)
            set_camera_view(eye=np.array(c.eye), target=np.array(c.target), camera_prim_path=c.prim_path)
            self.cameras[c.name + "_rgb"] = camera

    def reset(self):
        self.world.reset()
        self.contacts.initialize()
        for camera in self.cameras.values():
            camera.initialize()
        # Warm renderer and settle physics before taking the initial observation.
        for _ in range(60):
            self.world.step(render=True)
            self.world.step(render=True)
        self.initial_position = self.beaker.get_world_pose()[0].copy()
        self.height = float(UsdGeom.BBoxCache(0, ["default", "render"]).ComputeWorldBound(
            self.scene["body"]).ComputeAlignedRange().GetSize()[2])
        self.elapsed = self.held = self.max_held = self.max_lift = 0.0
        self.peak_contacts = np.zeros(2)
        self.status, self.reason = "RUNNING", ""
        self.reset_needed = False
        self.frame_idx = 0

    def step(self):
        position, orientation = self.beaker.get_world_pose()
        forces = self.contacts.get_contact_force_matrix(dt=self.scene["dt"])
        force = np.linalg.norm(np.asarray(forces).reshape(2, -1, 3), axis=2).sum(axis=1)
        images = {}
        for key, camera in self.cameras.items():
            rgb = camera.get_rgb()
            if rgb is None or rgb.size == 0:
                raise RuntimeError(f"Camera {key} produced no RGB after warmup")
            images[key] = np.transpose(rgb[:, :, :3], (2, 0, 1)).copy()
        return dict(joint_positions=self.robot.get_joint_positions().copy(),
                    camera_data=images, camera_display=images,
                    gripper_position=self.robot.end_effector.get_world_pose()[0].copy(),
                    object_position=position.copy(), object_orientation=orientation.copy(),
                    finger_contact_N=force, simulation_time=self.elapsed,
                    language_instruction=self.cfg.task.instruction, done=self.status != "RUNNING")

    def advance(self, action):
        self.robot.get_articulation_controller().apply_action(action)
        # Both physics steps contribute to the consecutive contact criterion.
        for _ in range(2):
            self.world.step(render=True)
            self.elapsed += self.scene["dt"]
            pos, _ = self.beaker.get_world_pose()
            force = np.linalg.norm(np.asarray(self.contacts.get_contact_force_matrix(
                dt=self.scene["dt"])).reshape(2, -1, 3), axis=2).sum(axis=1)
            rise = float(pos[2] - self.initial_position[2])
            self.max_lift = max(self.max_lift, rise)
            self.peak_contacts = np.maximum(self.peak_contacts, force)
            self.held = self.held + self.scene["dt"] if (
                rise >= self.cfg.task.required_lift_m and np.all(force > 0.01)) else 0.0
            self.max_held = max(self.max_held, self.held)
            if self.held + 1e-9 >= self.cfg.task.required_hold_seconds:
                self.status, self.reason = "SUCCESS", "lift_and_bilateral_contact_hold"
            elif pos[2] < 0.65 or np.linalg.norm(pos[:2] - self.initial_position[:2]) > 0.30:
                self.status, self.reason = "FAIL", "beaker_dropped_or_left_workspace"
            elif self.elapsed + 1e-9 >= self.cfg.task.timeout_seconds:
                self.status, self.reason = "TIMEOUT", "simulation_time_budget"
        self.frame_idx += 1

    def on_task_complete(self, success):
        self.reset_needed = True

    def result(self):
        final = self.beaker.get_world_pose()[0]
        return dict(status=self.status, reason=self.reason, frames=self.frame_idx,
                    simulation_seconds=self.elapsed, initial_position_m=self.initial_position.tolist(),
                    final_position_m=final.tolist(), final_lift_m=float(final[2] - self.initial_position[2]),
                    max_lift_m=self.max_lift, continuous_hold_seconds=self.max_held,
                    peak_finger_contact_N=self.peak_contacts.tolist())
