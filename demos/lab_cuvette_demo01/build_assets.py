"""Export standalone fixtures; source assets are referenced unchanged elsewhere."""
from pathlib import Path
import argparse,hashlib
from omegaconf import OmegaConf
from pxr import Usd,UsdGeom,UsdPhysics,PhysxSchema,UsdShade,Gf
from demos.lab_cuvette_demo01.scene import parts,ROOT
from demos.lab_cuvette_external.build import mat
from demos.lab_cuvette_external.geometry import write

def build(out,cfg):
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    for label,color in [('source_fixture',[.05,.62,.72]),('target_fixture',[.95,.38,.06])]:
        s=Usd.Stage.CreateNew(str(out/(label+'.usda')));root=UsdGeom.Xform.Define(s,'/Asset');s.SetDefaultPrim(root.GetPrim());UsdGeom.SetStageMetersPerUnit(s,1.);UsdGeom.SetStageUpAxis(s,'Z');root.GetPrim().SetCustomDataByKey('provenance','V0_demo01 synthetic engineering fixture, not native supplied CAD')
        pm=mat(s,'/Asset/Physics',cfg)
        for name,p,size in parts(cfg):
            for kind in ['Visual','Collision']:
                c=UsdGeom.Cube.Define(s,f'/Asset/{name}/{kind}');c.CreateSizeAttr(1.);c.AddTranslateOp().Set(Gf.Vec3d(*p));c.AddScaleOp().Set(Gf.Vec3d(*size));c.CreateDisplayColorAttr([Gf.Vec3f(*color)])
                if kind=='Collision':
                    c.CreateVisibilityAttr('invisible');UsdPhysics.CollisionAPI.Apply(c.GetPrim());a=PhysxSchema.PhysxCollisionAPI.Apply(c.GetPrim());a.CreateContactOffsetAttr(cfg.physics.contact_offset_m);a.CreateRestOffsetAttr(0.);UsdShade.MaterialBindingAPI.Apply(c.GetPrim()).Bind(pm,materialPurpose='physics')
        s.GetRootLayer().Save();re=Usd.Stage.Open(str(out/(label+'.usda')));assert sum(p.HasAPI(UsdPhysics.CollisionAPI) for p in re.Traverse())==5
    files=[ROOT/'assets/lab_cuvette_loading/V0_ext02/walls28_mm.usda',ROOT/'assets/lab_cuvette_loading/V0_ext01/derived/instrument.usda',*out.glob('*.usda')]
    write(out/'manifest.json',dict(version='V0_demo01',synthetic=True,calibrated=False,dimensions=OmegaConf.to_container(cfg.fixtures),visual_collision_separate=True,collision='five analytic Cube solids per fixture; real empty interior; no convex hole',mass='fixed support, not dynamic mass',asset_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files},reload_pass=True))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=ROOT/'assets/lab_cuvette_loading/V0_demo01');a=p.parse_args();build(a.output,OmegaConf.load(ROOT/'config/lab_cuvette_loading/V0_demo01/engineering_demo.yaml'))
