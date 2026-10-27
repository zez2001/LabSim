import json,pathlib,numpy as np
from pxr import Usd,UsdGeom,UsdPhysics,Gf
from omegaconf import OmegaConf
from trimesh.triangles import closest_point
R=pathlib.Path('/home/wujing/Desktop/vla/LabSim');E=R/'outputs/lab_cuvette_loading/Project_v1_1/gpt_debug_05/episode_0000';cfg=OmegaConf.load(E/'config.yaml')
s=Usd.Stage.CreateInMemory();xf=UsdGeom.Xform.Define(s,'/World/Instrument');xf.GetPrim().GetReferences().AddReference(str(pathlib.Path(cfg.asset_directory)/'instrument_native.usda'));xf.AddTranslateOp().Set(Gf.Vec3d(*cfg.scene.instrument_xyz_m));xf.AddRotateZOp().Set(float(cfg.scene.instrument_yaw_deg));cache=UsdGeom.XformCache()
p=np.array([.2593122124671936,-.1653902530670166,1.3130004405975342]);out=[]
for pr in Usd.PrimRange.Stage(s,Usd.TraverseInstanceProxies()):
 if not pr.IsA(UsdGeom.Mesh) or '/Visual/' not in str(pr.GetPath()):continue
 m=UsdGeom.Mesh(pr);v=np.array(m.GetPointsAttr().Get());M=np.array(cache.GetLocalToWorldTransform(pr));v=(np.c_[v,np.ones(len(v))]@M)[:,:3]
 aabb=[v.min(0),v.max(0)];dd=np.maximum(np.maximum(aabb[0]-p,p-aabb[1]),0);lower=np.linalg.norm(dd)
 record={'prim':str(pr.GetPath()),'vertices':len(v),'world_AABB_m':[x.tolist() for x in aabb],'point_to_AABB_lowerbound_m':float(lower),'world_row_matrix':M.tolist(),'displayName':pr.GetDisplayName(),'customData':pr.GetCustomData()}
 if lower<.005:
  ind=np.array(m.GetFaceVertexIndicesAttr().Get());faces=[];off=0
  for c in m.GetFaceVertexCountsAttr().Get():
   ix=ind[off:off+c];faces.extend(ix[[0,i,i+1]] for i in range(1,c-1));off+=c
  tri=v[np.array(faces)];cc=closest_point(tri,np.tile(p,(len(tri),1)));ds=np.linalg.norm(cc-p,axis=1);idx=int(ds.argmin());record.update(point_to_visual_triangle_m=float(ds[idx]),nearest_triangle_world_m=tri[idx].tolist(),nearest_world_m=cc[idx].tolist(),nearest_triangle_index=idx)
 out.append(record)
out.sort(key=lambda r:r.get('point_to_visual_triangle_m',r['point_to_AABB_lowerbound_m']))
f=pathlib.Path('/tmp/labsim-gpt05-collision-cpu-20261027/visual_source_mapping.json');f.write_text(json.dumps({'scope':'CPU composed exact referenced visual USD at actual runtime instrument transform; point is offline actual callback point, not model input','visual_mesh_count':len(out),'records':out},ensure_ascii=False,indent=2)+'\n')
print(json.dumps(out[:3],ensure_ascii=False,indent=2))
