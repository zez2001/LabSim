exec(open('/tmp/labsim_gpt05_visual_source_map_20261027.py').read().split('p=np.array')[0])
from scipy.spatial import cKDTree
cache=UsdGeom.XformCache();names=['/World/Instrument/Collision/SourceMesh5','/World/Instrument/Visual/Source/newnew4/newnew4/tn__3_ZBFi3j3/tn__8_x1iBOa1g0Jv0g7n4/Mesh'];records=[];vs=[]
for name in names:
 pr=s.GetPrimAtPath(name);mesh=UsdGeom.Mesh(pr);v=np.array(mesh.GetPointsAttr().Get());M=np.array(cache.GetLocalToWorldTransform(pr));world=(np.c_[v,np.ones(len(v))]@M)[:,:3];vs.append(world);records.append({'path':name,'vertex_count':len(v),'world_AABB_m':[world.min(0).tolist(),world.max(0).tolist()],'world_row_matrix':M.tolist()})
d1=cKDTree(vs[1]).query(vs[0])[0];d2=cKDTree(vs[0]).query(vs[1])[0]
out={'schema':'labsim.Project_v1_1.GPT05_collision_visible_geometry_correspondence.v1','scope':'Actual runtime cached USD composed in CPU memory at frozen config transform; no rendering or physics','nodes':records,'max_collision_vertex_to_nearest_visible_vertex_m':float(d1.max()),'max_visible_vertex_to_nearest_collision_vertex_m':float(d2.max()),'same_index_vertex_max_difference_m':float(np.linalg.norm(vs[0]-vs[1],axis=1).max()) if len(vs[0])==len(vs[1]) else None,'cooked_shape_readback':False,'policy_input':False}
pathlib.Path('/tmp/labsim-gpt05-collision-cpu-20261027/visible_collision_vertex_correspondence.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
