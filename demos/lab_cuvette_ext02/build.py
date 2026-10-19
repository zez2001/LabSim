"""Independent material-volume partition and explicit local-coordinate cooking test.

Source dimensions never change: local millimetre coordinates are cancelled by
a 0.001 prim scale. This tests cooking scale, not a smaller world collider.
"""
from pathlib import Path
import json, shutil, hashlib
import numpy as np
from pxr import Usd, UsdGeom, UsdPhysics, PhysxSchema, Gf
from demos.lab_cuvette_external.geometry import ROOT, clipped_hull, write
from demos.lab_cuvette_external.build import add_mesh
import trimesh

OUT=ROOT/'assets/lab_cuvette_loading/V0_ext02'

def source_mesh():
    s=Usd.Stage.Open(str(ROOT/'assets/lab_cuvette_loading/V0_ext01/derived/vessel_debug.usda'))
    m=UsdGeom.Mesh(s.GetPrimAtPath('/Asset/Visual/Mesh'))
    return trimesh.Trimesh(np.array(m.GetPointsAttr().Get()),np.array(m.GetFaceVertexIndicesAttr().Get()).reshape(-1,3),process=True)

def build(output=None):
    global OUT
    OUT=Path(output or OUT).resolve()
    if not any(OUT.is_relative_to(ROOT/p) for p in ['assets/lab_cuvette_loading/V0_ext02','outputs/lab_cuvette_loading/V0_ext02']):raise ValueError('Ext02 namespace only')
    OUT.mkdir(exist_ok=False,parents=True); m=source_mesh(); floor=.00488398969
    # Four complete thick side panels and four thick rounded corner regions.
    # Cut at the measured straight-wall/inner-corner transition (~5.868 mm).
    cut=.005867; b=m.bounds; parts=[('bottom',clipped_hull(m,[([0,0,floor],[0,0,-1])]))]
    bands=[floor+1e-7,.005163099,.0672209008,b[1,2]]
    for k,(z0,z1) in enumerate(zip(bands[:-1],bands[1:])):
        for ix in [-1,0,1]:
            for iy in [-1,0,1]:
                if ix==iy==0:continue
                planes=[([0,0,z0],[0,0,1]),([0,0,z1],[0,0,-1])]
                for axis,i in enumerate([ix,iy]):
                    n=np.eye(3)[axis]
                    if i==0:planes.extend([(n*(-cut),n),(n*cut,-n)])
                    else:planes.append((n*cut*i,n*i))
                parts.append((f'band{k}_cell{ix+1}{iy+1}',clipped_hull(m,planes)))
    src=ROOT/'assets/lab_cuvette_loading/V0_ext01/derived/vessel_debug.usda'
    for scheme in ['control193','control193_mm','walls25','walls25_mm','sdf_cpu','walls28_mm','walls28_conditioned']:
        path=OUT/(scheme+'.usda')
        if path.exists():raise FileExistsError(path)
        shutil.copyfile(src,path);s=Usd.Stage.Open(str(path))
        if scheme=='control193':pass
        elif scheme=='control193_mm':
            for p in Usd.PrimRange(s.GetPrimAtPath('/Asset/Collision')):
                if p.IsA(UsdGeom.Mesh):
                    a=UsdGeom.Mesh(p);a.GetPointsAttr().Set([Gf.Vec3f(*v) for v in np.array(a.GetPointsAttr().Get(),dtype=float)*1000]);a.AddScaleOp().Set(Gf.Vec3f(.001))
        else:
            s.RemovePrim('/Asset/Collision')
            objects=[('sdf',m)] if scheme=='sdf_cpu' else parts
            if scheme in ['walls28_mm','walls28_conditioned']:
                # Whole thick base quadrants keep each rounded base hull below
                # 64 vertices; no change to the input material-volume union.
                objects=[(f'bottom{i}{j}',clipped_hull(parts[0][1],[([0,0,0],[i,0,0]),([0,0,0],[0,j,0])])) for i in [-1,1] for j in [-1,1]]+parts[1:]
            for i,(name,h) in enumerate(objects):
                scale=1e6 if scheme=='walls28_conditioned' else (1000 if scheme.endswith('_mm') else 1)
                mesh=add_mesh(s,f'/Asset/Collision/{name.replace("-","n")}',h.vertices*scale,h.faces)
                if scale!=1:mesh.AddScaleOp().Set(Gf.Vec3f(1/scale))
                p=mesh.GetPrim();mesh.CreateVisibilityAttr('invisible');UsdPhysics.CollisionAPI.Apply(p)
                UsdPhysics.MeshCollisionAPI.Apply(p).CreateApproximationAttr('sdf' if scheme=='sdf_cpu' else 'convexHull')
                if scheme=='sdf_cpu':
                    a=PhysxSchema.PhysxSDFMeshCollisionAPI.Apply(p);a.CreateSdfResolutionAttr(512);a.CreateSdfSubgridResolutionAttr(6)
                else:
                    a=PhysxSchema.PhysxConvexHullCollisionAPI.Apply(p);a.CreateHullVertexLimitAttr(256);a.CreateMinThicknessAttr(0.)
                a=PhysxSchema.PhysxCollisionAPI.Apply(p);a.CreateContactOffsetAttr(.00005);a.CreateRestOffsetAttr(0.)
                from pxr import UsdShade
                UsdShade.MaterialBindingAPI.Apply(p).Bind(UsdShade.Material(s.GetPrimAtPath('/Asset/Looks/Physics')),materialPurpose='physics')
        s.GetRootLayer().Save()
    write(OUT/'partition.json',dict(method='closed-material bottom + four thick planar panels + four rounded corner blocks, separated at source fillet Z levels',parts=[dict(name=n,vertices=len(h.vertices),bounds=h.bounds) for n,h in parts],source_bounds=m.bounds,source_sha256=hashlib.sha256(src.read_bytes()).hexdigest(),coordinate_rebasing='points *1000, per-mesh scale 0.001; world dimensions identical; not collider shrink',mass_inertia='unchanged source-material integration, 20g assumption',sdf_grid_nominal_longest_spacing_m=float(m.extents.max()/512),sdf_actual_grid_readback=None))
    print('BUILT',len(parts),'material parts; old 193 control retained')

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path);build(parser.parse_args().output)
