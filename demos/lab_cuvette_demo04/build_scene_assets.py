"""Non-destructive references: full unchanged rack and all original seat solids."""
from pathlib import Path
import os,argparse,hashlib
from pxr import Usd,UsdGeom,UsdPhysics
from omegaconf import OmegaConf
from demos.lab_cuvette_demo04.scene import ROOT,ASSETS,layout
from demos.lab_cuvette_external.geometry import write

def build(cfg):
    ASSETS.mkdir(exist_ok=True,parents=True)
    sources={'rack.usda':ROOT/'assets/lab_cuvette_loading/V0_demo03/rack.usda','instrument_native.usda':ROOT/'assets/lab_cuvette_loading/V0_demo02/video_pose_verified/instrument_native.usda'}
    for name,source in sources.items():
        path=ASSETS/name
        if path.exists():raise FileExistsError(path)
        s=Usd.Stage.CreateNew(str(path));r=UsdGeom.Xform.Define(s,'/Asset');s.SetDefaultPrim(r.GetPrim());UsdGeom.SetStageMetersPerUnit(s,1.);UsdGeom.SetStageUpAxis(s,'Z');r.GetPrim().GetReferences().AddReference(os.path.relpath(source,ASSETS));r.GetPrim().SetCustomDataByKey('version','V0_demo04 original geometry reference; no seat replacement');s.GetRootLayer().Save()
    checks={}
    for name,expected in [('rack.usda',50),('instrument_native.usda',8)]:
        s=Usd.Stage.Open(str(ASSETS/name),Usd.Stage.LoadAll);cols=[str(p.GetPath()) for p in Usd.PrimRange.Stage(s,Usd.TraverseInstanceProxies()) if p.HasAPI(UsdPhysics.CollisionAPI)];assert len(cols)==expected
        checks[name]={'colliders':cols,'count':len(cols),'engineering_adapter_absent':not bool(s.GetPrimAtPath('/Asset/EngineeringAdapterA'))}
    files=[ASSETS/k for k in sources]+[ASSETS/'vessel_125_mm.usda']
    if not all(p.exists() for p in files):raise RuntimeError('Build corrected vessel first')
    write(ASSETS/'manifest.json',dict(version='V0_demo04',scene_mode='native_nominal',instrument_count=1,rack_slots=36,nominal_vessel_xy_m=.0125,nominal_seat_central_width_m=.0126,nominal_dimension_source='user2026-10-20',real_calibrated=False,source_CAD_unchanged=True,original_A_and_B_restored=True,engineering16mm_adapter_in_native_scene=False,checks=checks,layout=layout(cfg),source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources.values()},asset_sha256={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in files}))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--config',type=Path,default=ROOT/'config/lab_cuvette_loading/V0_demo04/native_nominal.yaml');a=p.parse_args();build(OmegaConf.load(a.config))
