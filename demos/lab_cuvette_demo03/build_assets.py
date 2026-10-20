"""Standalone synthetic full rack and in-chamber A replacement; source CAD intact."""
import argparse,hashlib,os
from pathlib import Path
import numpy as np
from omegaconf import OmegaConf
from pxr import Usd,UsdGeom,UsdPhysics,UsdShade,PhysxSchema,Gf,Sdf
from demos.lab_cuvette_demo03.scene import ROOT,ASSETS,rack_parts,rack_slots,adapter_parts,layout,get,ORIGINAL_A_VISUAL,ORIGINAL_A_COLLISION
from demos.lab_cuvette_external.build import mat
from demos.lab_cuvette_external.geometry import write


def _stage(file):
    s=Usd.Stage.CreateNew(str(file));root=UsdGeom.Xform.Define(s,'/Asset');s.SetDefaultPrim(root.GetPrim());UsdGeom.SetStageMetersPerUnit(s,1);UsdGeom.SetStageUpAxis(s,'Z');return s


def build(out,cfg):
    out=Path(out).resolve();out.mkdir(parents=True,exist_ok=False)
    data=layout(cfg)
    for file,parts,color in [('rack.usda',rack_parts(cfg),[.94,.94,.93]),('adapter_A.usda',adapter_parts(cfg),[.72,.74,.77])]:
        s=_stage(out/file);s.GetDefaultPrim().SetCustomDataByKey('provenance','V0_demo03 Python parameterized engineering reconstruction; not source rack CAD or native matched seat');pm=mat(s,'/Asset/Physics',cfg)
        for name,p,size in parts:
            for kind in ['Visual','Collision']:
                cube=UsdGeom.Cube.Define(s,f'/Asset/{name}/{kind}');cube.CreateSizeAttr(1);cube.AddTranslateOp().Set(Gf.Vec3d(*p));cube.AddScaleOp().Set(Gf.Vec3d(*size));cube.CreateDisplayColorAttr([Gf.Vec3f(*color)])
                if kind=='Collision':
                    cube.CreateVisibilityAttr('invisible');UsdPhysics.CollisionAPI.Apply(cube.GetPrim());a=PhysxSchema.PhysxCollisionAPI.Apply(cube.GetPrim());a.CreateContactOffsetAttr(float(cfg.physics.contact_offset_m));a.CreateRestOffsetAttr(0);UsdShade.MaterialBindingAPI.Apply(cube.GetPrim()).Bind(pm,materialPurpose='physics')
        if file=='rack.usda':
            for slot in rack_slots(cfg):
                frame=UsdGeom.Xform.Define(s,'/Asset/Slots/'+slot['id']);frame.AddTranslateOp().Set(Gf.Vec3d(*slot['origin_local_m']));frame.GetPrim().CreateAttribute('labsim:slotID',Sdf.ValueTypeNames.String).Set(slot['id'])
        s.GetRootLayer().Save()
    instrument=ROOT/'assets/lab_cuvette_loading/V0_demo02/video_pose_verified/instrument_native.usda'
    s=_stage(out/'instrument_demo.usda');s.GetDefaultPrim().GetReferences().AddReference(os.path.relpath(instrument,out))
    for path in [ORIGINAL_A_VISUAL,ORIGINAL_A_COLLISION]:
        prim=s.GetPrimAtPath(path)
        if not prim:raise RuntimeError(f'Original A not found for explicit replacement: {path}')
        prim.SetActive(False)
    a=UsdGeom.Xform.Define(s,'/Asset/EngineeringAdapterA');a.GetPrim().GetReferences().AddReference('adapter_A.usda');a.AddTranslateOp().Set(Gf.Vec3d(*data['target_origin_in_instrument']))
    frame=UsdGeom.Xform.Define(s,'/Asset/Frames/engineering_adapter_A');frame.AddTranslateOp().Set(Gf.Vec3d(*(data['target_origin_in_instrument']+[0,0,float(get(cfg,'adapter.base_m',.002))])));frame.GetPrim().CreateAttribute('labsim:targetID',Sdf.ValueTypeNames.String).Set('engineering_adapter_A');s.GetRootLayer().Save()
    checks={}
    for file,count in [('rack.usda',50),('adapter_A.usda',5),('instrument_demo.usda',12)]:
        reload=Usd.Stage.Open(str(out/file),Usd.Stage.LoadAll);cols=[str(p.GetPath()) for p in Usd.PrimRange.Stage(reload,Usd.TraverseInstanceProxies()) if p.HasAPI(UsdPhysics.CollisionAPI)]
        if len(cols)!=count:raise RuntimeError(f'{file}: expected {count} colliders, got {len(cols)}')
        checks[file]=dict(collision_count=len(cols),colliders=cols)
    original=Usd.Stage.Open(str(out/'instrument_demo.usda'))
    checks['no_duplicate_native_A']=not original.GetPrimAtPath(ORIGINAL_A_VISUAL).IsActive() and not original.GetPrimAtPath(ORIGINAL_A_COLLISION).IsActive()
    write(out/'manifest.json',dict(version='V0_demo03',calibrated=False,method='parameterized real Cube wall material and bottom; visual and collision separate but same dimensions',source_rack_CAD_used=False,original_cad_pair_success=False,original_A_explicitly_replaced=True,original_A_disabled=[ORIGINAL_A_VISUAL,ORIGINAL_A_COLLISION],original_B_retained=True,original_other_meshes_retained=7,full_rack_slot_count=36,rack_parts=rack_parts(cfg),adapter_parts=adapter_parts(cfg),slots=rack_slots(cfg),layout=data,reload_checks=checks,source_instrument_sha256=hashlib.sha256(instrument.read_bytes()).hexdigest(),asset_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.glob('*.usda')},scope='engineering scenario reenactment; no claim native supplied instrument/vessel pairing or true calibration'))
    print('V0_DEMO03_ASSETS',out,'36slots; originalA replaced once; originalB retained')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--config',type=Path,default=ROOT/'config/lab_cuvette_loading/V0_demo03/engineering_demo.yaml');p.add_argument('--output',type=Path,default=ASSETS);args=p.parse_args();build(args.output,OmegaConf.load(args.config))
