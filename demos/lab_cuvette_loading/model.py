"""SI geometry, deterministic sampling and independent box collision scoring."""
import json
from pathlib import Path
import numpy as np
from demos.minimal_precision_insertion.geometry import rotation

def rz(yaw):
 a=np.radians(yaw);c,s=np.cos(a),np.sin(a)
 return np.array([[c,-s,0],[s,c,0],[0,0,1]])

def sample_layout(cfg,mode,seed):
 rng=np.random.default_rng(seed)
 out=dict(mode=mode,seed=int(seed),rack_xy_m=list(cfg.layout.rack_xy_m),rack_yaw_deg=float(cfg.layout.rack_yaw_deg),instrument_xy_m=list(cfg.layout.instrument_xy_m),instrument_yaw_deg=float(cfg.layout.instrument_yaw_deg),source_slot=list(cfg.rack.source_slot),in_slot_xy_m=[0.,0.],light_scale=1.,background_rgb=[.08,.65,.08],mat_rgb=[.04,.40,.48],sampling_attempts=1,rejections=[])
 if mode in ('random','layout'):
  out['rack_xy_m']=(np.array(out['rack_xy_m'])+rng.uniform(-1,1,2)*cfg.random.rack_translation_mm*.001).tolist()
  out['rack_yaw_deg']+=float(rng.uniform(-cfg.random.rack_yaw_deg,cfg.random.rack_yaw_deg))
  out['instrument_xy_m']=(np.array(out['instrument_xy_m'])+rng.uniform(-1,1,2)*cfg.random.instrument_translation_mm*.001).tolist()
  out['instrument_yaw_deg']+=float(rng.uniform(-cfg.random.instrument_yaw_deg,cfg.random.instrument_yaw_deg))
  out['source_slot']=list(cfg.rack.random_legal_slots[int(rng.integers(len(cfg.rack.random_legal_slots)))])
  out['in_slot_xy_m']=rng.uniform(-cfg.random.in_slot_translation_mm,cfg.random.in_slot_translation_mm,2).tolist()
  out['in_slot_xy_m']=(np.array(out['in_slot_xy_m'])*.001).tolist()
 if mode in ('random','appearance'):
  out['light_scale']=float(rng.uniform(*cfg.random.light_scale))
  out['background_rgb']=[.05,float(rng.uniform(.5,.75)),.08]
  out['mat_rgb']=[.04,float(rng.uniform(.3,.48)),float(rng.uniform(.42,.58))]
 return out

def slots(cfg,layout):
 z=cfg.layout.table_top_m+cfg.rack.base_thickness_m
 return {f'r{r}c{c}':np.r_[layout['rack_xy_m'],z]+rz(layout['rack_yaw_deg'])@np.array([(c-(cfg.rack.columns-1)/2)*cfg.rack.pitch_m,(r-(cfg.rack.rows-1)/2)*cfg.rack.pitch_m,0]) for r in range(cfg.rack.rows) for c in range(cfg.rack.columns)}

def source_id(layout):return 'r%dc%d'%tuple(layout['source_slot'])

def box_overlap(p,A,half,q,B,h):
 """Minimum separating-axis translation for two OBBs; zero if disjoint."""
 axes=[*A.T,*B.T]
 axes.extend(np.cross(a,b) for a in A.T for b in B.T)
 minimum=float('inf');d=np.array(q)-p
 for axis in axes:
  norm=np.linalg.norm(axis)
  if norm<1e-10:continue
  axis=axis/norm
  overlap=np.sum(np.abs(A.T@axis)*half)+np.sum(np.abs(B.T@axis)*h)-abs(d@axis)
  if overlap<=0:return 0.
  minimum=min(minimum,float(overlap))
 return minimum

def cuvette_parts(cfg):
 w,d,h=map(float,cfg.cuvette.size_m);t=float(cfg.cuvette.wall_m)
 return [(np.array([0,0,-h/2+t/2]),np.array([w,d,t])),(np.array([-(w-t)/2,0,t/2]),np.array([t,d,h-t])),(np.array([(w-t)/2,0,t/2]),np.array([t,d,h-t])),(np.array([0,-(d-t)/2,t/2]),np.array([w-2*t,t,h-t])),(np.array([0,(d-t)/2,t/2]),np.array([w-2*t,t,h-t]))]

def overlap_all(cfg,position,quat,boxes):
 if not boxes:return 0.,''
 A=rotation(quat);maximum=0.;name=''
 # AABB broad phase excludes remote devices; SAT then tests actual hollow parts.
 centers=np.array([b['center'] for b in boxes]);halves=np.array([b['size'] for b in boxes])/2
 rotations=np.array([rz(b['yaw_deg']) for b in boxes]);bounds=np.einsum('nij,nj->ni',np.abs(rotations),halves)
 for center,size in cuvette_parts(cfg):
  p=position+A@center;bound=np.abs(A)@(size/2)
  candidates=np.flatnonzero(np.all(np.abs(centers-p)<bounds+bound,axis=1))
  for j in candidates:
   value=box_overlap(p,A,size/2,centers[j],rotations[j],halves[j])
   if value>maximum:maximum=value;name=boxes[j]['id']
 return maximum,name

def export_assets(directory,cfg):
 from pxr import Gf,Usd,UsdGeom,UsdPhysics,PhysxSchema,UsdShade
 directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
 def stage(name):
  s=Usd.Stage.CreateNew(str(directory/(name+'.usda')));s.SetDefaultPrim(UsdGeom.Xform.Define(s,'/Asset').GetPrim());UsdGeom.SetStageUpAxis(s,'Z');UsdGeom.SetStageMetersPerUnit(s,1.);return s
 def material(s,path,color,opacity=1.,physics=False,finger=False):
  m=UsdShade.Material.Define(s,path)
  if not physics:
   shader=UsdShade.Shader.Define(s,path+'/Surface');shader.CreateIdAttr('UsdPreviewSurface')
   from pxr import Sdf
   shader.CreateInput('diffuseColor',Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*color));shader.CreateInput('opacity',Sdf.ValueTypeNames.Float).Set(float(opacity));shader.CreateInput('roughness',Sdf.ValueTypeNames.Float).Set(.18 if opacity<1 else .5);shader.CreateInput('ior',Sdf.ValueTypeNames.Float).Set(1.46)
   m.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(),'surface')
  else:
   api=UsdPhysics.MaterialAPI.Apply(m.GetPrim());api.CreateStaticFrictionAttr(cfg.physics.finger_static_friction if finger else cfg.physics.static_friction);api.CreateDynamicFrictionAttr(cfg.physics.finger_dynamic_friction if finger else cfg.physics.dynamic_friction);api.CreateRestitutionAttr(cfg.physics.restitution)
   a=PhysxSchema.PhysxMaterialAPI.Apply(m.GetPrim());a.CreateFrictionCombineModeAttr('average');a.CreateRestitutionCombineModeAttr('average')
  return m
 def cube(s,path,center,size,visual=None,collision=False,physmat=None):
  c=UsdGeom.Cube.Define(s,path);c.CreateSizeAttr(1.);c.AddTranslateOp().Set(Gf.Vec3d(*center));c.AddScaleOp().Set(Gf.Vec3d(*size))
  if visual:UsdShade.MaterialBindingAPI.Apply(c.GetPrim()).Bind(visual)
  if collision:
   UsdPhysics.CollisionAPI.Apply(c.GetPrim());a=PhysxSchema.PhysxCollisionAPI.Apply(c.GetPrim());a.CreateContactOffsetAttr(cfg.physics.contact_offset_m);a.CreateRestOffsetAttr(cfg.physics.rest_offset_m)
   if physmat:UsdShade.MaterialBindingAPI.Apply(c.GetPrim()).Bind(physmat,materialPurpose='physics')
  return c
 white=(.86,.87,.85);black=(.025,.028,.032)
 for variant in ['cuvette','cuvette_debug']:
  s=stage(variant);v=material(s,'/Asset/Looks/Visual',(.70,.86,.90) if variant=='cuvette' else (.08,.45,.8),cfg.cuvette.opacity if variant=='cuvette' else 1.);pm=material(s,'/Asset/Looks/Physics',(0,0,0),physics=True)
  for i,(center,size) in enumerate(cuvette_parts(cfg)):
   cube(s,f'/Asset/Visual/Part{i}',center,size,v)
   c=cube(s,f'/Asset/Collision/Part{i}',center,size,None,True,pm);c.CreateVisibilityAttr('invisible')
  root=s.GetDefaultPrim();UsdPhysics.RigidBodyAPI.Apply(root);m=UsdPhysics.MassAPI.Apply(root);m.CreateMassAttr(cfg.cuvette.mass_kg);m.CreateCenterOfMassAttr(Gf.Vec3f(*cfg.cuvette.center_of_mass_m))
  w,d,h=cfg.cuvette.size_m;mass=cfg.cuvette.mass_kg;m.CreateDiagonalInertiaAttr(Gf.Vec3f(*cfg.cuvette.inertia_diagonal_kg_m2))
  a=PhysxSchema.PhysxRigidBodyAPI.Apply(root);a.CreateEnableCCDAttr(True);a.CreateSolverPositionIterationCountAttr(cfg.physics.position_iterations);a.CreateSolverVelocityIterationCountAttr(cfg.physics.velocity_iterations);s.GetRootLayer().Save()
 s=stage('rack');v=material(s,'/Asset/Looks/White',white);pm=material(s,'/Asset/Looks/Physics',(0,0,0),physics=True)
 W=cfg.rack.columns*cfg.rack.pitch_m;D=cfg.rack.rows*cfg.rack.pitch_m;t=cfg.rack.pitch_m-cfg.rack.slot_inner_m
 rack_boxes=[('Base',[0,0,-cfg.rack.base_thickness_m/2],[W+t,D+t,cfg.rack.base_thickness_m])]
 for i in range(cfg.rack.columns+1):rack_boxes.append((f'X{i}',[(i-cfg.rack.columns/2)*cfg.rack.pitch_m,0,cfg.rack.depth_m/2],[t,D+t,cfg.rack.depth_m]))
 for i in range(cfg.rack.rows+1):rack_boxes.append((f'Y{i}',[0,(i-cfg.rack.rows/2)*cfg.rack.pitch_m,cfg.rack.depth_m/2],[W+t,t,cfg.rack.depth_m]))
 for n,p,size in rack_boxes:
  cube(s,'/Asset/'+n+'/Visual',p,size,v)
  cube(s,'/Asset/'+n+'/Collision',p,size,None,True,pm).CreateVisibilityAttr('invisible')
 s.GetRootLayer().Save()
 s=stage('instrument');wv=material(s,'/Asset/Looks/White',white);bv=material(s,'/Asset/Looks/Black',black);pm=material(s,'/Asset/Looks/Physics',(0,0,0),physics=True)
 # Local z=table top; actual sample holder remains inside the open cavity.
 f=cfg.layout.chamber_floor_z_m-cfg.layout.table_top_m;top=cfg.layout.shell_top_z_m-cfg.layout.table_top_m
 W,D=cfg.instrument.size_xy_m;wall=cfg.instrument.wall_m;ew=cfg.instrument.electronics_width_m;lx,ly=cfg.instrument.lid_center_local_xy_m;ls=list(cfg.instrument.lid_size_m)
 instrument_boxes=[('Base',[0,0,f/2],[W,D,f]),('Left',[-(W-wall)/2,0,(f+top)/2],[wall,D,top-f]),('Right',[(W-wall)/2,0,(f+top)/2],[wall,D,top-f]),('Back',[0,(D-wall)/2,(f+top)/2],[W-2*wall,wall,top-f]),('Front',[0,-(D-wall)/2,(f+top)/2],[W-2*wall,wall,top-f]),('Electronics',[(W-ew)/2-wall,0,(f+top)/2],[ew,D-2*wall,top-f]),('Lid',[lx,ly,top+ls[2]/2],ls)]
 H=cfg.holder.inner_m/2;w=cfg.holder.wall_m;d=cfg.holder.depth_m;x,y=cfg.layout.target_local_xy_m
 instrument_boxes.extend([('HolderX0',[x-H-w/2,y,f+d/2],[w,2*(H+w),d]),('HolderX1',[x+H+w/2,y,f+d/2],[w,2*(H+w),d]),('HolderY0',[x,y-H-w/2,f+d/2],[2*H,w,d]),('HolderY1',[x,y+H+w/2,f+d/2],[2*H,w,d])])
 for n,p,size in instrument_boxes:
  cube(s,'/Asset/'+n+'/Visual',p,size,bv if n.startswith('Holder') or n in ['Lid','Base'] else wv)
  cube(s,'/Asset/'+n+'/Collision',p,size,None,True,pm).CreateVisibilityAttr('invisible')
 # Separate empty neighboring slot within the chamber, also physically represented.
 x2,y2=x+cfg.instrument.neighbor_offset_xy_m[0],y+cfg.instrument.neighbor_offset_xy_m[1]
 for n,p,size in [('NeighborX0',[x2-H-w/2,y2,f+d/2],[w,2*(H+w),d]),('NeighborX1',[x2+H+w/2,y2,f+d/2],[w,2*(H+w),d]),('NeighborY0',[x2,y2-H-w/2,f+d/2],[2*H,w,d]),('NeighborY1',[x2,y2+H+w/2,f+d/2],[2*H,w,d])]:
  cube(s,'/Asset/'+n+'/Visual',p,size,bv)
  cube(s,'/Asset/'+n+'/Collision',p,size,None,True,pm).CreateVisibilityAttr('invisible');instrument_boxes.append((n,p,size))
 s.GetRootLayer().Save()
 manifest=dict(version=cfg.version,units='m',rack_boxes=rack_boxes,instrument_boxes=instrument_boxes,source='Synthetic V0 from supplied video/photo observations; no measured dimensions.',inertia='uniform solid outer box approximation for empty cuvette proxy, configurable; not measured hollow-body inertia')
 (directory/'geometry_manifest.json').write_text(json.dumps(manifest,indent=2));return manifest
