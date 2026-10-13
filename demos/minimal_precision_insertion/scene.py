"""Independent synthetic insertion instrument, sharing the existing Franka asset."""
from pathlib import Path
import numpy as np
from demos.minimal_precision_insertion.geometry import rotation, create_assets


def build_scene(cfg, asset_dir):
    import omni.usd
    import carb
    carb.settings.get_settings().set_bool('/physics/collisionApproximateCylinders', False)
    from pxr import Gf, PhysxSchema, UsdGeom, UsdLux, UsdPhysics
    from isaacsim.core.api import World
    from isaacsim.core.api.objects import FixedCuboid, GroundPlane
    from isaacsim.core.api.sensors import RigidContactView
    from isaacsim.core.prims import SingleRigidPrim
    from isaacsim.core.utils.stage import add_reference_to_stage
    from isaacsim.core.utils.rotations import euler_angles_to_quat
    from isaacsim.robot.manipulators.examples.franka import Franka
    from isaacsim.robot.manipulators.examples.franka.kinematics_solver import KinematicsSolver
    if World.instance() is not None:
        World.clear_instance()
    omni.usd.get_context().new_stage()
    dt = 1. / cfg.physics.hz
    world = World(stage_units_in_meters=1., physics_dt=dt, rendering_dt=1/60., backend='numpy', device='cpu')
    stage = omni.usd.get_context().get_stage()
    stage.SetDefaultPrim(UsdGeom.Xform.Define(stage, '/World').GetPrim())
    UsdGeom.SetStageUpAxis(stage, 'Z')
    world.scene.add(GroundPlane(prim_path='/World/Ground', name='ground', size=20., color=np.array([.20,.27,.33])))
    world.scene.add(FixedCuboid(prim_path='/World/Table', name='table', position=np.array([.15,0,.70]),
                               scale=np.array([1.2,.8,.08]), color=np.array([.52,.36,.22])))
    UsdLux.DomeLight.Define(stage, '/World/Light').CreateIntensityAttr(1000.)
    # Plain synthetic exterior/support, leaving space above and around the 18 mm module.
    world.scene.add(FixedCuboid(prim_path='/World/Support', name='support', position=np.array([.2,0,.753]),
                               scale=np.array([.018,.018,.026]), color=np.array([.35,.35,.4])))
    world.scene.add(FixedCuboid(prim_path='/World/Housing', name='housing', position=np.array([.26,.04,.76]),
                               scale=np.array([.06,.06,.04]), color=np.array([.7,.72,.75])))
    robot_base = np.array([-.30,0,.74])
    root = Path(__file__).resolve().parents[2]
    robot = world.scene.add(Franka(prim_path='/World/Franka', name='franka',
        usd_path=str(root/'assets/robots/Franka.usd'), position=robot_base,
        gripper_open_position=np.array([.04,.04]), gripper_closed_position=np.zeros(2)))
    robot.set_joints_default_state(positions=np.array([0.,-.785,0.,-2.356,0.,1.571,.785,.005,.005]))
    assets = create_assets(asset_dir, cfg)
    add_reference_to_stage(str(assets/'tube.usda'), '/World/Tube')
    tube = world.scene.add(SingleRigidPrim(prim_path='/World/Tube', name='tube', mass=.02,
                                          position=np.array([.2,0,.817])))
    add_reference_to_stage(str(assets/'module.usda'), '/World/Module')
    module = UsdGeom.Xformable(stage.GetPrimAtPath('/World/Module'))
    module.AddTranslateOp().Set(Gf.Vec3d(.2,0,cfg.task.floor_z))
    rigid = PhysxSchema.PhysxRigidBodyAPI.Apply(stage.GetPrimAtPath('/World/Tube'))
    rigid.CreateEnableCCDAttr(cfg.physics.ccd)
    rigid.CreateSolverPositionIterationCountAttr(cfg.physics.position_iterations)
    rigid.CreateSolverVelocityIterationCountAttr(cfg.physics.velocity_iterations)
    api = PhysxSchema.PhysxSceneAPI.Apply(stage.GetPrimAtPath('/physicsScene'))
    api.CreateEnableGPUDynamicsAttr(False)
    api.CreateBroadphaseTypeAttr('MBP')
    api.CreateSolverTypeAttr(cfg.physics.solver)
    api.CreateEnableCCDAttr(cfg.physics.ccd)
    for p in stage.Traverse():
        if p.HasAPI(UsdPhysics.ArticulationRootAPI):
            a = PhysxSchema.PhysxArticulationAPI.Apply(p)
            a.CreateSolverPositionIterationCountAttr(cfg.physics.position_iterations)
            a.CreateSolverVelocityIterationCountAttr(cfg.physics.velocity_iterations)
        if p.HasAPI(UsdPhysics.CollisionAPI) and str(p.GetPath()).startswith('/World/Franka'):
            PhysxSchema.PhysxCollisionAPI.Apply(p).CreateContactOffsetAttr(cfg.physics.contact_offset_m)
            PhysxSchema.PhysxCollisionAPI(p).CreateRestOffsetAttr(0.)
        if p.GetName() in ('panda_finger_joint1', 'panda_finger_joint2'):
            drive = UsdPhysics.DriveAPI.Apply(p, 'linear')
            drive.CreateMaxForceAttr(40.)
            drive.CreateStiffnessAttr(2000.)
            drive.CreateDampingAttr(100.)
    world.reset()
    solver = KinematicsSolver(robot)
    solver.get_kinematics_solver().set_robot_base_pose(robot_base, np.array([1.,0,0,0]))
    orientation = euler_angles_to_quat(np.array([np.pi,0.,0.]))
    ik, valid = solver.compute_inverse_kinematics(np.array(cfg.task.initial_tcp), orientation,
        position_tolerance=cfg.task.ik_position_tolerance_m, orientation_tolerance=cfg.task.ik_orientation_tolerance_rad)
    if not valid:
        fk,_ = solver.get_kinematics_solver().compute_forward_kinematics('right_gripper',ik.joint_positions)
        raise RuntimeError(f'Initial IK did not converge: target={cfg.task.initial_tcp}, best FK={fk}, joints={ik.joint_positions}')
    q = robot.get_joint_positions().copy()
    q[np.asarray(ik.joint_indices,dtype=int)] = ik.joint_positions
    q[7:] = .005
    robot.set_joints_default_state(positions=q)
    hand = world.scene.add(SingleRigidPrim(prim_path='/World/Franka/panda_hand', name='hand_pose'))
    fingers = RigidContactView(prim_paths_expr=['/World/Franka/panda_leftfinger','/World/Franka/panda_rightfinger'],
        filter_paths_expr=[['/World/Tube'],['/World/Tube']], name='finger_tube_contacts', max_contact_count=1024)
    contacts = RigidContactView(prim_paths_expr='/World/Tube',
        filter_paths_expr=['/World/Module/WallCollision','/World/Module/BaseCollision'], name='tube_module_contacts', max_contact_count=4096)
    world.reset()
    return dict(world=world,stage=stage,robot=robot,tube=tube,hand=hand,solver=solver,
                fingers=fingers,contacts=contacts,q=q,dt=dt,orientation=orientation)


def tcp_pose(hand):
    p,q = hand.get_world_pose()
    return p+rotation(q)@np.array([0.,0.,.1]), q
