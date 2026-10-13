"""Empty-stage V0 reconstruction; independent hollow assets and replaceable Franka."""
from pathlib import Path
import numpy as np
from demos.lab_cuvette_loading.model import rz,slots,source_id
from demos.minimal_precision_insertion.geometry import rotation

def build(cfg,layout,asset_dir,manifest,debug_material=False):
 import omni.usd
 from pxr import Gf,UsdGeom,UsdLux,UsdPhysics,PhysxSchema,UsdShade
 from isaacsim.core.api import World
 from isaacsim.core.api.objects import FixedCuboid,GroundPlane
 from isaacsim.core.prims import SingleRigidPrim
 from isaacsim.core.api.sensors import RigidContactView
 from isaacsim.core.utils.stage import add_reference_to_stage
 from isaacsim.core.utils.rotations import euler_angles_to_quat
 from isaacsim.core.utils.types import ArticulationAction
 from isaacsim.robot.manipulators.examples.franka import Franka
 from isaacsim.robot.manipulators.examples.franka.kinematics_solver import KinematicsSolver
 root=Path(__file__).resolve().parents[2]
 if cfg.robot.type!='franka_proxy':raise ValueError('Install a model/control adapter before using a different robot embodiment')
 if World.instance() is not None:World.clear_instance()
 omni.usd.get_context().new_stage();world=World(stage_units_in_meters=1.,physics_dt=1/cfg.physics.hz,rendering_dt=1/cfg.physics.control_hz,backend='numpy',device='cpu');stage=omni.usd.get_context().get_stage()
 stage.SetDefaultPrim(UsdGeom.Xform.Define(stage,'/World').GetPrim());UsdGeom.SetStageUpAxis(stage,'Z')
 world.scene.add(GroundPlane(prim_path='/World/Ground',name='ground',size=10,color=np.array([.3,.32,.34])))
 world.scene.add(FixedCuboid(prim_path='/World/Table',name='table',position=np.array([.05,0,cfg.layout.table_top_m-.04]),scale=np.array([1.3,1.,.08]),color=np.array([.62,.51,.38])))
 def visual_cube(name,p,size,color):
  c=UsdGeom.Cube.Define(stage,'/World/'+name);c.CreateSizeAttr(1);c.AddTranslateOp().Set(Gf.Vec3d(*p));c.AddScaleOp().Set(Gf.Vec3d(*size));c.CreateDisplayColorAttr([Gf.Vec3f(*color)]);return c
 visual_cube('BlueWorkspace',[.08,-.08,cfg.layout.table_top_m+.0001],[1.1,.67,.0002],layout['mat_rgb'])
 visual_cube('GreenScreen',[.05,.60,1.25],[1.5,.015,1.],layout['background_rgb'])
 visual_cube('BackgroundFlexFrame',[.70,.43,1.06],[.32,.13,.48],[.035,.035,.04])
 visual_cube('Monitor',[-.42,.38,1.02],[.012,.24,.22],[.025,.025,.03])
 light=UsdLux.DomeLight.Define(stage,'/World/Light');light.CreateIntensityAttr(cfg.light.intensity*layout['light_scale'])
 robot=world.scene.add(Franka(prim_path='/World/Franka',name='franka',usd_path=str(root/cfg.robot.usd_path),position=np.array(cfg.robot.base_m),gripper_open_position=np.array([.04,.04]),gripper_closed_position=np.zeros(2)))
 robot.set_joints_default_state(positions=np.array([0,-.785,0,-2.356,0,1.571,.785,.04,.04]))
 add_reference_to_stage(str(asset_dir/'rack.usda'),'/World/Rack');add_reference_to_stage(str(asset_dir/'instrument.usda'),'/World/Instrument')
 boxes=[]
 for name,xy,yaw,z,parts in [('Rack',layout['rack_xy_m'],layout['rack_yaw_deg'],cfg.layout.table_top_m+cfg.rack.base_thickness_m,manifest['rack_boxes']),('Instrument',layout['instrument_xy_m'],layout['instrument_yaw_deg'],cfg.layout.table_top_m,manifest['instrument_boxes'])]:
  xf=UsdGeom.Xformable(stage.GetPrimAtPath('/World/'+name));xf.AddTranslateOp().Set(Gf.Vec3d(*xy,z));xf.AddRotateZOp().Set(yaw)
  for n,p,size in parts:boxes.append(dict(id=name+'/'+n,prim='/World/'+name+'/'+n+'/Collision',center=(np.r_[xy,z]+rz(yaw)@np.array(p)).tolist(),size=size,yaw_deg=yaw))
 boxes.append(dict(id='Table',prim='/World/Table',center=[.05,0,cfg.layout.table_top_m-.04],size=[1.3,1.,.08],yaw_deg=0.))
 ss=slots(cfg,layout);source=ss[source_id(layout)]+rz(layout['rack_yaw_deg'])@np.r_[layout['in_slot_xy_m'],0]
 orientation=euler_angles_to_quat(np.array([0.,0.,np.radians(layout['rack_yaw_deg'])]))
 add_reference_to_stage(str(asset_dir/('cuvette_debug.usda' if debug_material else 'cuvette.usda')),'/World/Cuvette')
 cup=world.scene.add(SingleRigidPrim(prim_path='/World/Cuvette',name='cuvette',position=source+[0,0,cfg.cuvette.size_m[2]/2+.0002],orientation=orientation))
 distractors=[]
 for i,key in enumerate([k for k in ss if k!=source_id(layout) and k.startswith('r5')][:cfg.cuvette.distractor_count]):
  add_reference_to_stage(str(asset_dir/'cuvette_debug.usda'),f'/World/Distractor{i}');body=world.scene.add(SingleRigidPrim(prim_path=f'/World/Distractor{i}',name=f'distractor{i}',position=ss[key]+[0,0,cfg.cuvette.size_m[2]/2+.0002],orientation=orientation));distractors.append(body)
 api=PhysxSchema.PhysxSceneAPI.Apply(stage.GetPrimAtPath('/physicsScene'));api.CreateEnableGPUDynamicsAttr(False);api.CreateBroadphaseTypeAttr('MBP');api.CreateSolverTypeAttr(cfg.physics.solver);api.CreateEnableCCDAttr(cfg.physics.ccd)
 # USD angular stiffness is per degree; runtime tensor gains below are SI per radian.
 # Explicit finite efforts/velocities prevent the inherited extreme asset defaults.
 arm_index=0
 finger_mat=UsdShade.Material.Define(stage,'/World/FingerPhysics');ma=UsdPhysics.MaterialAPI.Apply(finger_mat.GetPrim());ma.CreateStaticFrictionAttr(cfg.physics.finger_static_friction);ma.CreateDynamicFrictionAttr(cfg.physics.finger_dynamic_friction);ma.CreateRestitutionAttr(0.)
 pa=PhysxSchema.PhysxMaterialAPI.Apply(finger_mat.GetPrim());pa.CreateFrictionCombineModeAttr('average');pa.CreateRestitutionCombineModeAttr('average')
 for prim in stage.Traverse():
  if prim.HasAPI(UsdPhysics.ArticulationRootAPI):
   a=PhysxSchema.PhysxArticulationAPI.Apply(prim);a.CreateSolverPositionIterationCountAttr(cfg.physics.position_iterations);a.CreateSolverVelocityIterationCountAttr(cfg.physics.velocity_iterations)
  if prim.HasAPI(UsdPhysics.CollisionAPI) and str(prim.GetPath()).startswith('/World/Franka'):
   a=PhysxSchema.PhysxCollisionAPI.Apply(prim);a.CreateContactOffsetAttr(cfg.physics.contact_offset_m);a.CreateRestOffsetAttr(0.)
   if 'finger' in str(prim.GetPath()):UsdShade.MaterialBindingAPI.Apply(prim).Bind(finger_mat,materialPurpose='physics')
  if prim.GetName().startswith('panda_joint') and prim.IsA(UsdPhysics.RevoluteJoint):
   i=int(prim.GetName().replace('panda_joint',''))-1
   drive=UsdPhysics.DriveAPI.Apply(prim,'angular');drive.CreateTypeAttr('force');drive.CreateStiffnessAttr(cfg.robot.arm_kp[i]*np.pi/180);drive.CreateDampingAttr(cfg.robot.arm_kd[i]*np.pi/180);drive.CreateMaxForceAttr(cfg.robot.max_effort[i]);PhysxSchema.PhysxJointAPI.Apply(prim).CreateMaxJointVelocityAttr(cfg.robot.max_velocity[i]*180/np.pi)
  if prim.GetName() in ['panda_finger_joint1','panda_finger_joint2']:
   drive=UsdPhysics.DriveAPI.Apply(prim,'linear');drive.CreateTypeAttr('force');drive.CreateStiffnessAttr(cfg.robot.finger_kp);drive.CreateDampingAttr(cfg.robot.finger_kd);drive.CreateMaxForceAttr(cfg.robot.max_effort[7]);PhysxSchema.PhysxJointAPI.Apply(prim).CreateMaxJointVelocityAttr(cfg.robot.max_velocity[7])
 world.reset();solver=KinematicsSolver(robot);solver.get_kinematics_solver().set_robot_base_pose(np.array(cfg.robot.base_m),np.array([1.,0,0,0]))
 oq=euler_angles_to_quat(np.array([np.pi,0.,0.]))
 ik,valid=solver.compute_inverse_kinematics(np.array(cfg.robot.initial_tcp_m),oq,position_tolerance=cfg.robot.ik_position_tolerance_m,orientation_tolerance=cfg.robot.ik_orientation_tolerance_rad)
 if not valid:raise RuntimeError('Initial TCP IK failed')
 q=robot.get_joint_positions().copy();q[np.array(ik.joint_indices,dtype=int)]=ik.joint_positions;q[7:]=.04
 robot.set_joints_default_state(positions=q)
 hand=world.scene.add(SingleRigidPrim(prim_path='/World/Franka/panda_hand',name='hand'))
 fingers=RigidContactView(prim_paths_expr=['/World/Franka/panda_leftfinger','/World/Franka/panda_rightfinger'],filter_paths_expr=[['/World/Cuvette'],['/World/Cuvette']],name='finger_cup',max_contact_count=256)
 contact=RigidContactView(prim_paths_expr='/World/Cuvette',filter_paths_expr=[b['prim'] for b in boxes],name='cup_environment',max_contact_count=2048)
 world.reset();robot.set_joint_positions(q);robot.set_joint_velocities(np.zeros(9));ac=robot.get_articulation_controller();ac.set_gains(kps=np.r_[cfg.robot.arm_kp,[cfg.robot.finger_kp]*2],kds=np.r_[cfg.robot.arm_kd,[cfg.robot.finger_kd]*2]);ac.set_max_efforts(np.array(cfg.robot.max_effort));robot._articulation_view.set_max_joint_velocities(np.array([cfg.robot.max_velocity]));ac.apply_action(ArticulationAction(joint_positions=q))
 for v in (fingers,contact):v.initialize()
 target=np.r_[layout['instrument_xy_m'],cfg.layout.chamber_floor_z_m]+rz(layout['instrument_yaw_deg'])@np.r_[cfg.layout.target_local_xy_m,0]
 return dict(world=world,stage=stage,robot=robot,cup=cup,hand=hand,solver=solver,fingers=fingers,contact=contact,boxes=boxes,source=source,target=target,initial_q=q,distractors=distractors,orientation=oq)

def tcp(scene,cfg):
 p,q=scene['hand'].get_world_pose();return p+rotation(q)@np.array(cfg.robot.tcp_local_m)
