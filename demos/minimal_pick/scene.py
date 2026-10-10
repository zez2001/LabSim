"""Shared independent scene construction; no laboratory USD is loaded."""
from pathlib import Path


def build_scene():
    import numpy as np
    import omni.usd
    from pxr import Gf, PhysxSchema, UsdGeom, UsdLux, UsdPhysics
    from isaacsim.core.api import World
    from isaacsim.core.api.objects import FixedCuboid, GroundPlane
    from isaacsim.core.api.sensors import RigidContactView
    from isaacsim.core.prims import SingleRigidPrim
    from isaacsim.core.utils.stage import add_reference_to_stage
    from isaacsim.core.utils.types import ArticulationAction
    from isaacsim.core.utils.rotations import euler_angles_to_quat
    from isaacsim.core.utils.viewports import set_camera_view
    from isaacsim.robot.manipulators.examples.franka import Franka
    from isaacsim.robot.manipulators.examples.franka.kinematics_solver import KinematicsSolver

    root = Path(__file__).resolve().parents[2]
    dt = 1.0 / 120.0
    # Explicitly start an empty stage. No laboratory stage is opened at runtime.
    omni.usd.get_context().new_stage()
    world = World(stage_units_in_meters=1.0, physics_dt=dt, rendering_dt=1 / 60)
    stage = omni.usd.get_context().get_stage()
    world_prim = UsdGeom.Xform.Define(stage, "/World").GetPrim()
    stage.SetDefaultPrim(world_prim)
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    world.scene.add(GroundPlane(prim_path="/World/Ground", name="ground",
                                size=20.0, color=np.array([0.20, 0.27, 0.33])))
    world.scene.add(FixedCuboid(prim_path="/World/Table", name="table",
                               position=np.array([0.15, 0.0, 0.70]),
                               scale=np.array([1.2, 0.8, 0.08]),
                               color=np.array([0.52, 0.36, 0.22])))
    light = UsdLux.DomeLight.Define(stage, "/World/Light")
    light.CreateIntensityAttr(1000.0)
    robot_base = np.array([-0.30, 0.0, 0.74])
    robot = world.scene.add(Franka(
        prim_path="/World/Franka", name="franka",
        usd_path=str(root / "assets/robots/Franka.usd"), position=robot_base,
        gripper_open_position=np.array([0.04, 0.04]),
        gripper_closed_position=np.array([0.0, 0.0]),
    ))
    initial_joints = np.array([0.0, -0.785, 0.0, -2.356, 0.0, 1.571, 0.785, 0.04, 0.04])
    robot.set_joints_default_state(positions=initial_joints)
    add_reference_to_stage(str(Path(__file__).parent / "assets/beaker.usda"), "/World/Beaker")
    beaker = world.scene.add(SingleRigidPrim(
        prim_path="/World/Beaker", name="beaker", position=np.array([0.20, 0.0, 0.741]),
        mass=0.08,
    ))
    body = stage.GetPrimAtPath("/World/Beaker")
    PhysxSchema.PhysxRigidBodyAPI.Apply(body).CreateDisableGravityAttr(False)
    PhysxSchema.PhysxRigidBodyAPI(body).CreateSolverPositionIterationCountAttr(16)
    PhysxSchema.PhysxRigidBodyAPI(body).CreateSolverVelocityIterationCountAttr(4)
    PhysxSchema.PhysxRigidBodyAPI(body).CreateEnableCCDAttr(True)
    scene_api = PhysxSchema.PhysxSceneAPI.Apply(stage.GetPrimAtPath("/physicsScene"))
    scene_api.CreateEnableCCDAttr(True)
    # The finger drives squeeze; only contact and friction can move the beaker.
    for joint in ("panda_finger_joint1", "panda_finger_joint2"):
        candidates = [p for p in stage.Traverse() if p.GetName() == joint]
        if len(candidates) != 1:
            raise RuntimeError(f"Expected one {joint}, got {len(candidates)}")
        drive = UsdPhysics.DriveAPI.Apply(candidates[0], "linear")
        drive.CreateMaxForceAttr(40.0)
        drive.CreateStiffnessAttr(2000.0)
        drive.CreateDampingAttr(100.0)
    camera = UsdGeom.Camera.Define(stage, "/World/Camera")
    camera.CreateFocalLengthAttr(24.0)
    camera.CreateClippingRangeAttr(Gf.Vec2f(0.05, 100.0))
    set_camera_view(eye=np.array([1.3, -1.6, 1.6]), target=np.array([0.05, 0.0, 1.0]),
                    camera_prim_path="/World/Camera")
    from omni.kit.viewport.utility import get_active_viewport
    viewport = get_active_viewport()
    if viewport:
        viewport.set_active_camera("/World/Camera")
    contact_view = RigidContactView(
        prim_paths_expr=["/World/Franka/panda_leftfinger", "/World/Franka/panda_rightfinger"],
        filter_paths_expr=[["/World/Beaker"], ["/World/Beaker"]],
        name="finger_beaker_contacts", max_contact_count=64,
    )
    world.reset()
    contact_view.initialize()
    solver = KinematicsSolver(robot)
    solver.get_kinematics_solver().set_robot_base_pose(robot_base, np.array([1.0, 0.0, 0.0, 0.0]))
    return dict(world=world, stage=stage, robot=robot, beaker=beaker,
                body=body, contact_view=contact_view, solver=solver, viewport=viewport,
                robot_base=robot_base, dt=dt)
