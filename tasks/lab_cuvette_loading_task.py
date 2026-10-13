"""Full physical cuvette loading task with unprivileged camera/state observations."""
import json
import time
from pathlib import Path
import numpy as np
from demos.lab_cuvette_loading.scene import build,tcp
from demos.lab_cuvette_loading.scoring import Scorer
from demos.lab_cuvette_loading.model import source_id,rotation

class LabCuvetteLoadingTask:
 def __init__(self,cfg,layout,asset_dir,manifest,debug_material=False):
  self.cfg,self.layout=cfg,layout;self.scene=build(cfg,layout,asset_dir,manifest,debug_material);self.world,self.stage,self.robot,self.cup,self.solver=(self.scene[k] for k in ['world','stage','robot','cup','solver'])
  self.substeps=cfg.physics.hz//cfg.physics.control_hz
  if self.substeps*cfg.physics.control_hz!=cfg.physics.hz:raise ValueError('noninteger physics/control ratio')
  self.cameras={};self.camera_meta={};self.phase='INITIALIZATION';self.target_tcp=np.array(cfg.robot.initial_tcp_m);self.last_action=None
 def initialize(self,restored=None):
  from isaacsim.core.utils.types import ArticulationAction
  from isaacsim.sensors.camera import Camera
  from isaacsim.core.utils.viewports import set_camera_view
  if restored:
   self.robot.set_joint_positions(np.array(restored['joints']));self.robot.set_joint_velocities(np.array(restored['joint_velocities']))
   for name,body in [('target',self.cup),*[(f'distractor{i}',b) for i,b in enumerate(self.scene['distractors'])]]:
    state=restored['objects'][name];body.set_world_pose(np.array(state['position']),np.array(state['orientation']));body.set_linear_velocity(np.array(state['linear_velocity']));body.set_angular_velocity(np.array(state['angular_velocity']))
   self.robot.get_articulation_controller().apply_action(ArticulationAction(joint_positions=np.array(restored['joints'])))
  else:
   for _ in range(int(self.cfg.physics.hz*.75)):self.world.step(render=False)
  for key,c,path in [('camera_1_rgb',self.cfg.cameras.external,'/World/ExternalCamera'),('camera_2_rgb',self.cfg.cameras.wrist,'/World/Franka/panda_hand/WristCamera')]:
   camera=Camera(prim_path=path,name=key,frequency=self.cfg.physics.control_hz,resolution=tuple(c.resolution));camera.set_focal_length(c.focal_length);camera.set_clipping_range(.001,10.)
   if key=='camera_1_rgb':eye,target=np.array(c.eye),np.array(c.target)
   else:
    hp,hq=self.scene['hand'].get_world_pose();eye=hp+rotation(hq)@np.array(c.local_eye);target=tcp(self.scene,self.cfg)-[0,0,c.target_below_tcp_m]
   set_camera_view(eye=eye,target=target,camera_prim_path=path);camera.initialize()
   if key=='camera_2_rgb':
    from scipy.spatial.transform import Rotation
    local_eye=np.array(c.local_eye);local_target=np.array(self.cfg.robot.tcp_local_m)+[0,0,c.target_below_tcp_m]
    z=local_eye-local_target;z=z/np.linalg.norm(z);x=np.cross([0,1,0],z);x=x/np.linalg.norm(x);y=np.cross(z,x)
    q=Rotation.from_matrix(np.column_stack([x,y,z])).as_quat();camera.set_local_pose(local_eye,np.r_[q[3],q[:3]],camera_axes='usd')
   self.cameras[key]=camera
   self.camera_meta[key]=dict(prim=path,resolution=list(c.resolution),focal_length=float(c.focal_length),eye_initial_m=eye.tolist(),target_initial_m=target.tolist(),mount='hand' if key=='camera_2_rgb' else 'world')
  from omni.kit.viewport.utility import get_active_viewport
  vp=get_active_viewport()
  if vp:vp.set_active_camera('/World/ExternalCamera')
  for _ in range(4):self.world.step(render=True)
  if restored:
   self.robot.set_joint_positions(np.array(restored['joints']));self.robot.set_joint_velocities(np.array(restored['joint_velocities']))
   for name,body in [('target',self.cup),*[(f'distractor{i}',b) for i,b in enumerate(self.scene['distractors'])]]:
    state=restored['objects'][name];body.set_world_pose(np.array(state['position']),np.array(state['orientation']));body.set_linear_velocity(np.array(state['linear_velocity']));body.set_angular_velocity(np.array(state['angular_velocity']))
   self.world.render()
  self.elapsed=0.;self.clock_origin=self.world.current_time;self.status,self.reason='RUNNING','';self.events=[];self.physics_records=[];self.frame=0
  self.initial=self.initial_snapshot();self.scorer=Scorer(self.cfg,self.scene,self.layout,self.initial);self.metrics=self.measure();self.max_clock_error=0.
  overlap=self.metrics['overlap_m'];s=self.scene['source'];bottom=np.array(self.metrics['bottom'])
  legal=(np.linalg.norm(bottom[:2]-s[:2])<.001 and abs(bottom[2]-s[2])<.0005 and self.metrics['tilt_rad']<np.radians(2.) and overlap<=self.cfg.scoring.penetration_tolerance_m)
  self.initial_validation=dict(valid=bool(legal),overlap_m=overlap,bottom_m=bottom.tolist(),source_floor_m=s.tolist(),criteria='source within 1mm XY, 0.5mm Z, tilt<2deg, fixed collision tolerance')
  if not legal:self.status,self.reason='INVALID_INITIAL_STATE','source_geometry_or_stability_check'
  if restored:
   error=np.max(np.abs(np.array(restored['joints'])-self.robot.get_joint_positions()));bodyerror=np.linalg.norm(np.array(restored['objects']['target']['position'])-self.cup.get_world_pose()[0]);self.restore_validation=dict(max_joint_error_rad=float(error),position_error_m=float(bodyerror),tolerance_m=1e-6)
   if error>1e-6 or bodyerror>1e-6:raise RuntimeError('Replay exact initial-state restore failed')
 def initial_snapshot(self):
  objects={}
  for name,body in [('target',self.cup),*[(f'distractor{i}',b) for i,b in enumerate(self.scene['distractors'])]]:
   p,q=body.get_world_pose();objects[name]=dict(position=p.tolist(),orientation=q.tolist(),linear_velocity=body.get_linear_velocity().tolist(),angular_velocity=body.get_angular_velocity().tolist())
  return dict(layout=self.layout,joints=self.robot.get_joint_positions().tolist(),joint_velocities=self.robot.get_joint_velocities().tolist(),objects=objects,source_slot_id=source_id(self.layout),target_object_id=self.cfg.cuvette.target_id,target_slot_id=self.cfg.holder.target_id,source_m=self.scene['source'].tolist(),target_m=self.scene['target'].tolist(),camera=self.camera_meta)
 def measure(self):
  p,q=self.cup.get_world_pose();dt=1/self.cfg.physics.hz
  fingers=np.linalg.norm(np.asarray(self.scene['fingers'].get_contact_force_matrix(dt=dt)).reshape(2,-1,3),axis=2).sum(axis=1)
  force=float(np.linalg.norm(np.asarray(self.scene['contact'].get_contact_force_matrix(dt=dt)).reshape(-1,3),axis=1).sum())
  m=self.scorer.measure(p,q,tcp(self.scene,self.cfg),self.robot.get_joint_positions(),fingers,force)
  m.update(linear_velocity=self.cup.get_linear_velocity().tolist(),angular_velocity=self.cup.get_angular_velocity().tolist(),joint_velocities=self.robot.get_joint_velocities().tolist(),target_tcp=self.target_tcp.tolist(),phase=self.phase,time=self.elapsed)
  # Explicit detail arrays from current-dt impulse conversion.
  f,p,n,sep,count,start=self.scene['contact'].get_contact_force_data(dt=dt);indices=[]
  for a,b in zip(np.asarray(count).ravel(),np.asarray(start).ravel()):indices.extend(range(int(b),int(b)+int(a)))
  m.update(contact_points_m=np.asarray(p)[indices].tolist(),contact_normals=np.asarray(n)[indices].tolist(),contact_force_N=np.asarray(f)[indices].ravel().tolist(),contact_separation_m=np.asarray(sep)[indices].ravel().tolist())
  return m
 def observation(self):
  images={}
  for key,c in self.cameras.items():
   rgb=c.get_rgb()
   if rgb is None or not rgb.size:raise RuntimeError('RGB missing '+key)
   images[key]=np.transpose(rgb[:,:,:3],(2,0,1)).astype(np.uint8)
  return dict(camera_data=images,joint_positions=self.robot.get_joint_positions().copy(),simulation_time=self.elapsed,tcp=tcp(self.scene,self.cfg),object_position=np.array(self.metrics['position']),object_orientation=np.array(self.metrics['orientation']),metrics=self.metrics,phase=self.phase)
 def advance(self,action):
  self.robot.get_articulation_controller().apply_action(action)
  for _ in range(self.substeps):
   self.world.step(render=False);self.elapsed+=1/self.cfg.physics.hz
   self.max_clock_error=max(self.max_clock_error,abs(self.world.current_time-self.clock_origin-self.elapsed))
   if self.max_clock_error>1e-5:raise RuntimeError('physics clock mismatch')
   self.metrics=self.measure();self.physics_records.append(self.metrics)
   previous=self.scorer.progress.copy();self.status,self.reason=self.scorer.update(self.elapsed,self.metrics)
   for key in previous:
    if self.scorer.progress[key] and not previous[key]:self.events.append(dict(event='ACTUAL_PROGRESS',time=self.elapsed,progress=key))
   if self.status!='RUNNING':break
  self.frame+=1;self.world.render()
 def result(self):
  return dict(status=self.status,reason=self.reason,full_success=self.status=='SUCCESS',stage_progress=self.scorer.progress,mode=self.layout['mode'],seed=self.layout['seed'],source_slot_id=source_id(self.layout),target_object_id=self.cfg.cuvette.target_id,target_slot_id=self.cfg.holder.target_id,frames=self.frame,simulation_seconds=self.elapsed,engine_simulation_seconds=self.world.current_time-self.clock_origin,max_clock_error_seconds=self.max_clock_error,max_depth_mm=self.scorer.max_depth*1000,max_overlap_mm=self.scorer.max_overlap*1000,max_lift_mm=self.scorer.max_lift*1000,stable_seconds=self.scorer.stable_seconds,final_state=self.metrics,policy='oracle_scripted_expert',scene_version=self.cfg.version,calibrated=False)
 def effective(self):
  from pxr import PhysxSchema,UsdPhysics
  ac=self.robot.get_articulation_controller();kp,kd=ac.get_gains();api=PhysxSchema.PhysxSceneAPI(self.stage.GetPrimAtPath('/physicsScene'))
  return dict(physics_backend='PhysX CPU',solver=api.GetSolverTypeAttr().Get(),gpu_dynamics=api.GetEnableGPUDynamicsAttr().Get(),physics_hz=self.cfg.physics.hz,control_hz=self.cfg.physics.control_hz,substeps=self.substeps,robot_dof_names=self.robot.dof_names,kp_SI=np.asarray(kp).tolist(),kd_SI=np.asarray(kd).tolist(),max_effort=np.asarray(ac.get_max_efforts()).tolist(),effective_max_velocity_SI=np.asarray(self.robot._articulation_view.get_joint_max_velocities()).tolist(),authored_max_velocity=list(self.cfg.robot.max_velocity),ccd=api.GetEnableCCDAttr().Get(),joint_units='7 rad + 2 metre',action='7 arm radians + symmetric finger metre, 8D; actual state preserves both fingers, 9D',contact_offset_m=self.cfg.physics.contact_offset_m,rest_offset_m=self.cfg.physics.rest_offset_m,penetration_tolerance_m=self.cfg.scoring.penetration_tolerance_m,camera=self.camera_meta,static_collision='native boxes, separate walls preserve holes',full_runtime_shape_vertices_read=False)
 def geometry_probe(self):
  import omni.physx
  query=omni.physx.get_physx_scene_query_interface();samples=[]
  for name,p in [('source',self.scene['source']),('target',self.scene['target'])]:
   found=query.raycast_closest((float(p[0]),float(p[1]),float(p[2]+.006)),(0.,0.,-1.),.02)
   # This ray starts below the cuvette bottom and above the physical base only
   # in target (empty at reset); source can hit the actual target vessel.
   samples.append(dict(name=name,query=dict(found),expected_floor_z_m=float(p[2])))
  return dict(samples=samples,limitation='Runtime ray samples and USD Cube dimensions; no complete PhysX actor shape dump.')
 def close(self):
  for c in self.cameras.values():
   try:c.destroy()
   except Exception:pass

 def save_views(self,directory,prefix,collision=False):
  from pxr import UsdGeom,UsdPhysics,Gf
  import cv2
  directory=Path(directory);directory.mkdir(exist_ok=True)
  altered=[]
  if collision:
   for prim in self.stage.Traverse():
    if not str(prim.GetPath()).startswith(('/World/Cuvette','/World/Rack','/World/Instrument')):continue
    if prim.IsA(UsdGeom.Cube):
     v=UsdGeom.Imageable(prim).GetVisibilityAttr();altered.append((v,v.Get()))
     v.Set('inherited' if prim.HasAPI(UsdPhysics.CollisionAPI) else 'invisible')
     if prim.HasAPI(UsdPhysics.CollisionAPI):UsdGeom.Gprim(prim).CreateDisplayColorAttr([Gf.Vec3f(.1,.7,1.)])
  for _ in range(4):self.world.render()
  for key,c in self.cameras.items():
   rgb=c.get_rgb()
   if rgb is not None and rgb.size:cv2.imwrite(str(directory/(prefix+'_'+key+'.png')),cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR))
  for attr,value in altered:attr.Set(value)
  if collision:
   for _ in range(4):self.world.render()
