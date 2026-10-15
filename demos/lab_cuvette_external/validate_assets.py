"""New-process independent USD loading and actual-vertex transformation validation."""
import json
from pathlib import Path
import numpy as np
from pxr import Usd,UsdGeom,UsdPhysics,UsdShade,Sdf
from omegaconf import OmegaConf
from scipy.spatial import cKDTree
from demos.lab_cuvette_external.geometry import ROOT,DOC,SOURCE,normalized,write

def vertices(stage,which):
    cache=UsdGeom.XformCache();out=[]
    for prim in Usd.PrimRange.Stage(stage,Usd.TraverseInstanceProxies()):
        if prim.IsA(UsdGeom.Mesh) and which(str(prim.GetPath())):
            p=np.asarray(UsdGeom.Mesh(prim).GetPointsAttr().Get());out.append((np.c_[p,np.ones(len(p))]@np.array(cache.GetLocalToWorldTransform(prim)))[:,:3])
    return np.concatenate(out)

def main():
    cfg=OmegaConf.load(ROOT/'config/lab_cuvette_loading/V0_ext01.yaml');asset=ROOT/cfg.derived_directory;rows=[]
    for name in ['instrument.usda','source_original.usda','vessel.usda','vessel_debug.usda','rack_V0_proxy.usda']:
        s=Usd.Stage.Open(str(asset/name));required=[str(x) for x in s.GetRootLayer().GetExternalReferences() if x]
        item=dict(file=name,loaded=bool(s),default_prim=str(s.GetDefaultPrim().GetPath()),units=UsdGeom.GetStageMetersPerUnit(s),up_axis=str(UsdGeom.GetStageUpAxis(s)),dependencies=required,all_required_dependencies_resolved=all((asset/x).resolve().exists() for x in required),collision_prims=sum(p.HasAPI(UsdPhysics.CollisionAPI) for p in s.Traverse()))
        if name in ['instrument.usda','source_original.usda','vessel.usda','vessel_debug.usda']:
            sourcefile='newnew4.usd' if name=='instrument.usda' else 'TestTube_Baked.usd';info,src=normalized(sourcefile);expected=np.concatenate([r['vertices_m'] for r in src]);v=vertices(s,lambda path: '/Normalized/' in path or '/Visual/' in path)
            err=float(cKDTree(expected).query(v)[0].max());item.update(actual_vertex_dimensions_m=v.max(0)-v.min(0),normalization_max_vertex_error_m=err,physical_dimensions_preserved=bool(err<1e-7))
        rows.append(item)
    sources=[]
    for filename in ['newnew4.usd','TestTube_Baked.usd','TestTube_629.usd']:
        layer=Sdf.Layer.FindOrOpen(str(SOURCE/filename));sources.append(dict(file=filename,external_references=list(layer.GetExternalReferences()),used_as_formal_input=filename!='TestTube_629.usd'))
    materials=[]
    for filename in ['newnew4.usd','TestTube_Baked.usd']:
        s=Usd.Stage.Open(str(SOURCE/filename));root=s.GetDefaultPrim() or s.GetPrimAtPath('/TestTube');x=UsdGeom.Xformable(root)
        rootinfo=dict(file=filename,path=str(root.GetPath()),root_xform_ops=[dict(name=o.GetOpName(),value=str(o.Get())) for o in x.GetOrderedXformOps()])
        for p in Usd.PrimRange.Stage(s,Usd.TraverseInstanceProxies()):
            if p.IsA(UsdGeom.Subset):
                bound,_=UsdShade.MaterialBindingAPI(p).ComputeBoundMaterial();materials.append(dict(file=filename,subset=str(p.GetPath()),bound_material=str(bound.GetPath()) if bound else None))
            if p.IsA(UsdShade.Shader):
                sh=UsdShade.Shader(p);materials.append(dict(file=filename,shader=str(p.GetPath()),shader_id=sh.GetIdAttr().Get(),inputs={i.GetBaseName():str(i.Get()) for i in sh.GetInputs()}))
        sources.append(rootinfo)
    result=dict(independent_usd_process=True,assets=rows,source_roots_and_references=sources,source_materials=materials,passed=all(x['loaded'] and x['units']==1 and x['up_axis']=='Z' and x['all_required_dependencies_resolved'] and x.get('physical_dimensions_preserved',True) for x in rows),physics_test=False)
    write(DOC/'independent_load_validation.json',result);print('INDEPENDENT_USD_LOAD',result['passed'])

if __name__=='__main__':main()
