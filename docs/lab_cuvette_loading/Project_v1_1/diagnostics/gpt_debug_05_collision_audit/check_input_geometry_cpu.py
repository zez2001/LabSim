exec(open('/tmp/labsim_gpt05_collision_cpu_20261027.py').read().split('native=[];')[0])
from demos.lab_cuvette_demo03.arm_geometry import TriangleMeshIndex
from scipy.spatial import ConvexHull
cfg=OmegaConf.load(E/'config.yaml');base=np.array(cfg.robot.base_m);U=R/'robots/franka/lula_franka_gen.urdf';ur=ET.parse(U).getroot();joints=ur.findall('joint')
# Reuse pure FK implementation from prior analyzed script without its IO driver.
src=open('/tmp/labsim_gpt05_collision_cpu_20261027.py').read();exec(src[src.index('def fk(q):'):src.index('model=load_collision_model();')])
x=json.loads((O/'raw_extract.json').read_text());model=load_collision_model();s,inst=instrument_triangles(cfg);tt=next(m['triangles'] for m in inst if m['path'].endswith('/SourceMesh5'));index=TriangleMeshIndex(tt.reshape(-1,3),np.arange(tt.size//3).reshape(-1,3))
checks=[]
for d in x['physics']:
 if min(abs(d['t']-v) for v in [49.9,49.90416666666667,49.90833333333333,49.9125])>1e-8:continue
 F=fk(d['joints9']);m=model['links']['panda_link6']['meshes'][0];v=(np.c_[m['vertices_local_m'],np.ones(len(m['vertices_local_m']))]@F['panda_link6'].T)[:,:3]
 point=np.array(x['forbidden'][0]['points'][-1]['position_m'])
 checks.append({'t':d['t'],'scope':'authored input triangle SAT, not actual attached cooked shape','link6_AABB_m':[v.min(0).tolist(),v.max(0).tolist()],
 'declared_input_hull_vs_mesh5':index.intersections(v,m['convex_hull_faces_input'],max_witnesses=2),
 'authored_material_triangles_vs_mesh5':index.intersections(v,m['faces'],max_witnesses=2)})
(O/'input_surface_crossing_checks.json').write_text(json.dumps(checks,indent=2,default=lambda v:v.tolist() if hasattr(v,'tolist') else v)+'\n')
print(json.dumps(checks,default=lambda v:v.tolist() if hasattr(v,'tolist') else v,indent=2)[:5000])
