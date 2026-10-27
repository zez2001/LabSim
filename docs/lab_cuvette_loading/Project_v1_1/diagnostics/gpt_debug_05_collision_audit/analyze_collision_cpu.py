import pathlib,json,gzip,hashlib,collections,sys
import numpy as np
from scipy.spatial.transform import Rotation as Rot
from xml.etree import ElementTree as ET
from pxr import Usd,UsdGeom,UsdPhysics,Gf
from omegaconf import OmegaConf
from demos.lab_cuvette_demo03.arm_geometry import load_collision_model
from demos.lab_cuvette_demo04.preflight import instrument_triangles
from trimesh.triangles import closest_point
R=pathlib.Path('/home/wujing/Desktop/vla/LabSim'); E=R/'outputs/lab_cuvette_loading/Project_v1_1/gpt_debug_05/episode_0000'
O=pathlib.Path('/tmp/labsim-gpt05-collision-cpu-20261027');O.mkdir(exist_ok=True)
def save(n,x): (O/n).write_text(json.dumps(x,indent=2)+'\n')
keys=['t','physics_step','actual_tcp_position_m','actual_tcp_quaternion_wxyz','object_position_m','object_quaternion_wxyz','joints9','cup_in_hand_position_m','cup_in_hand_quaternion_wxyz','finger_contact_N','forbidden_robot_environment_contact','forbidden_robot_environment_contact_this_step','phase','depth_m','target_bottom_gap_m','xy_error_target_m','tilt_deg','target_bottom_support_N','command_q9']
native=[];robotenv=[];cupinstrument=[];hashes={};counts={};rows=[]
for name in ['native_contact_events.jsonl.gz','physics_records.jsonl.gz']:
 h=hashlib.sha256();byt=0;n=0
 with gzip.open(E/name,'rb') as f:
  for line in f:
   h.update(line);byt+=len(line);n+=1;d=json.loads(line)
   if name.startswith('native'):
    pair=d['colliders']
    if any('/Franka/' in p for p in pair) and any('/Instrument/' in p for p in pair):robotenv.append(d)
    if d.get('forbidden_robot_environment'):native.append(d)
    if any('/Cuvette/' in p for p in pair) and any('/Instrument/' in p for p in pair):cupinstrument.append(d)
   elif d['t']>=49.75 or any(abs(d['t']-v)<1e-9 for v in [44.016666666666666,46.016666666666666,48.016666666666666]):rows.append({k:d.get(k) for k in keys})
 hashes[name]={'decompressed_SHA256':h.hexdigest(),'decompressed_bytes':byt,'compressed_SHA256':hashlib.sha256((E/name).read_bytes()).hexdigest()};counts[name]=n
save('raw_extract.json',dict(counts=counts,raw_hashes=hashes,forbidden=native,all_robot_instrument_events=robotenv,cup_instrument_events=cupinstrument,physics=rows))
# URDF FK: configured real joint values, no IK/no simulation. Validate each TCP against recorded actual FK.
U=R/'robots/franka/lula_franka_gen.urdf';ur=ET.parse(U).getroot();joints=ur.findall('joint')
cfg=OmegaConf.load(E/'config.yaml');base=np.asarray(cfg.robot.base_m,float)
def fk(q):
 transforms={'panda_link0':np.block([[np.eye(3),base[:,None]],[np.array([[0,0,0,1]])]])}
 vals={f'panda_joint{i+1}':q[i] for i in range(7)};vals.update(panda_finger_joint1=q[7],panda_finger_joint2=q[8])
 pending=list(joints)
 while pending:
  progress=False
  for j in pending[:]:
   parent=j.find('parent').get('link');child=j.find('child').get('link')
   if parent not in transforms:continue
   origin=j.find('origin');xyz=np.fromstring(origin.get('xyz','0 0 0'),sep=' ') if origin is not None else np.zeros(3);rpy=np.fromstring(origin.get('rpy','0 0 0'),sep=' ') if origin is not None else np.zeros(3)
   T=np.eye(4);T[:3,:3]=Rot.from_euler('xyz',rpy).as_matrix();T[:3,3]=xyz
   act=np.eye(4);a=j.find('axis');axis=np.fromstring(a.get('xyz','0 0 1'),sep=' ') if a is not None else np.array([0,0,1]);v=vals.get(j.get('name'),0)
   if j.get('type')=='revolute':act[:3,:3]=Rot.from_rotvec(axis*v).as_matrix()
   elif j.get('type')=='prismatic':act[:3,3]=axis*v
   transforms[child]=transforms[parent]@T@act;pending.remove(j);progress=True
  if not progress:break
 return transforms
model=load_collision_model();stage,inst=instrument_triangles(cfg)
mesh5=next(x for x in inst if x['path'].endswith('/SourceMesh5'));tri5=mesh5['triangles'];points5=tri5.reshape(-1,3)
first=native[0];firstrow=next(x for x in rows if abs(x['t']-first['t'])<1e-9);F=fk(firstrow['joints9'])
tcp=F['right_gripper'];tr=Rot.from_quat(np.r_[firstrow['actual_tcp_quaternion_wxyz'][1:],firstrow['actual_tcp_quaternion_wxyz'][0]])
errp=np.linalg.norm(tcp[:3,3]-firstrow['actual_tcp_position_m']);errr=(Rot.from_matrix(tcp[:3,:3])*tr.inv()).magnitude()
assert errp<2e-6 and errr<2e-5,(errp,errr)
geom={'method':'CPU USD authored input mesh + URDF FK of recorded q9; no SimulationApp/IK/render/physics; no actual attached cooked-shape readback',
 'raw_first_contact_t':first['t'],'FK_TCP_position_error_m':float(errp),'FK_TCP_rotation_error_rad':float(errr),'robot_base_m':base.tolist(),
 'instrument_mesh5':{'path':mesh5['path'],'triangles':len(tri5),'world_AABB_m':[points5.min(0).tolist(),points5.max(0).tolist()]},'robot_links':{},'contact_points':[], 'state':firstrow}
for name,body in model['links'].items():
 if not body['meshes']:continue
 pp=[];meshes=[]
 for m in body['meshes']:
  vv=np.c_[m['vertices_local_m'],np.ones(len(m['vertices_local_m']))]@F[name].T;vv=vv[:,:3];pp.append(vv)
  meshes.append({'source_prim':m['path'],'approximation':m['approximation_authored'],'vertices':len(vv),'triangles':len(m['faces']),'world_AABB_m':[vv.min(0).tolist(),vv.max(0).tolist()]})
 vv=np.concatenate(pp)
 geom['robot_links'][name]={'world_transform_column_matrix':F[name].tolist(),'world_AABB_m':[vv.min(0).tolist(),vv.max(0).tolist()],'meshes':meshes}
# Distance to authored surface and reconstructed input convex hull; neither is attached cooked readback.
m6=model['links']['panda_link6']['meshes'][0];v6=(np.c_[m6['vertices_local_m'],np.ones(len(m6['vertices_local_m']))]@F['panda_link6'].T)[:,:3]
tri6=v6[m6['faces']];hull6=v6[m6['convex_hull_faces_input']]
def nearest(tri,p):
 cp=closest_point(tri,np.tile(p,(len(tri),1)));dist=np.linalg.norm(cp-p,axis=1);ii=int(np.argmin(dist));return {'distance_m':float(dist[ii]),'closest_world_m':cp[ii].tolist(),'triangle_index':ii,'triangle_vertices_world_m':tri[ii].tolist()}
for i,contact in enumerate(first['points']):
 pt=np.array(contact['position_m']);geom['contact_points'].append({'index':i,'raw':contact,'to_instrument_authored_mesh5':nearest(tri5,pt),'to_link6_authored_material_mesh':nearest(tri6,pt),'to_link6_reconstructed_input_hull':nearest(hull6,pt)})
# Store static instrument composed row transform and approximation; root stage assembly is identical to runtime add_scene.
s=Usd.Stage.CreateInMemory();xf=UsdGeom.Xform.Define(s,'/World/Instrument');xf.GetPrim().GetReferences().AddReference(str(R/cfg.asset_directory/'instrument_native.usda'));xf.AddTranslateOp().Set(Gf.Vec3d(*cfg.scene.instrument_xyz_m));xf.AddRotateZOp().Set(float(cfg.scene.instrument_yaw_deg));pr=s.GetPrimAtPath('/World/Instrument/Collision/SourceMesh5')
geom['instrument_mesh5'].update(usd_composed_world_row_matrix=np.array(UsdGeom.XformCache().GetLocalToWorldTransform(pr)).tolist(),authored_approximation=str(UsdPhysics.MeshCollisionAPI(pr).GetApproximationAttr().Get()),attributes={a.GetName():str(a.Get()) for a in pr.GetAttributes() if a.GetName().startswith(('physxCollision:','physics:approximation'))})
# Side camera fixed; project actual future contact to the static D24 camera only as offline audit, not policy input.
obs=json.loads((E/'gpt_control/observations/decision_000024/public_observation.json').read_text());cam=obs['camera_meta']['side_camera'];C=np.array(cam['camera_cv_from_world']);K=np.array(cam['intrinsic_matrix_native']);pp=np.array(first['points'][-1]['position_m']);campt=(C@np.r_[pp,1])[:3];uv=K@campt
geom['offline_side_projection_of_actual_contact']={'uv_pixels':(uv[:2]/uv[2]).tolist(),'camera_depth_m':float(campt[2]),'scope':'Uses actual later collision world point projected through fixed D24 side camera; not a point supplied to policy and not same-time rendered pixel/visibility certification.'}
save('geometry_extract.json',geom)
print(json.dumps({'raw_rows':counts,'forbidden_events':len(native),'all_robot_instrument_events':len(robotenv),'cup_instrument_events':len(cupinstrument),'first_pair':first['colliders'],'t':first['t'],'mesh5_AABB':geom['instrument_mesh5']['world_AABB_m'],'link6_AABB':geom['robot_links']['panda_link6']['world_AABB_m'],'FKerr_m':errp,'distances':[{k:v['distance_m'] for k,v in c.items() if k.startswith('to_')} for c in geom['contact_points']]},indent=2))
