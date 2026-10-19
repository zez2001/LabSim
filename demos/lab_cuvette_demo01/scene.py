"""Visible engineering fixtures; original instrument meshes all remain collidable."""
import numpy as np
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]

def parts(cfg):
    f=cfg.fixtures; w=f.wall_m; a=f.inner_m; h=f.depth_m; b=f.base_m
    return [('Base',[0,0,b/2],[a+2*w,a+2*w,b]),('West',[-(a+w)/2,0,b+h/2],[w,a+2*w,h]),('East',[(a+w)/2,0,b+h/2],[w,a+2*w,h]),('South',[0,-(a+w)/2,b+h/2],[a,w,h]),('North',[0,(a+w)/2,b+h/2],[a,w,h])]

def add_engineering_scene(world,stage,cfg):
    from pxr import UsdGeom,Gf,UsdPhysics,PhysxSchema,UsdShade
    from isaacsim.core.utils.stage import add_reference_to_stage
    from demos.lab_cuvette_external.build import mat
    boxes=[]
    for label,asset,xy,z in [('SourceFixture','source_fixture',cfg.scene.source_fixture_xy_m,cfg.fixtures.source_base_z_m),('TargetFixture','target_fixture',cfg.scene.target_fixture_xy_m,cfg.fixtures.target_base_z_m)]:
        origin=np.r_[xy,z]
        add_reference_to_stage(str(ROOT/'assets/lab_cuvette_loading/V0_demo01'/(asset+'.usda')),'/World/'+label)
        UsdGeom.Xformable(stage.GetPrimAtPath('/World/'+label)).AddTranslateOp().Set(Gf.Vec3d(*origin))
        for name,p,size in parts(cfg):boxes.append(dict(name=label+'/'+name,center=(origin+p).tolist(),size=size))
    add_reference_to_stage(str(ROOT/'assets/lab_cuvette_loading/V0_ext01/derived/instrument.usda'),'/World/Instrument')
    xf=UsdGeom.Xformable(stage.GetPrimAtPath('/World/Instrument'));xf.AddTranslateOp().Set(Gf.Vec3d(*cfg.scene.instrument_xyz_m))
    # Only a visual mat; the original table remains the support collider.
    c=UsdGeom.Cube.Define(stage,'/World/BlueWorkspace');c.CreateSizeAttr(1.);c.AddTranslateOp().Set(Gf.Vec3d(.1,0,.74005));c.AddScaleOp().Set(Gf.Vec3d(1.2,1.05,.0001));c.CreateDisplayColorAttr([Gf.Vec3f(.04,.48,.56)])
    c=UsdGeom.Cube.Define(stage,'/World/GreenScreen');c.CreateSizeAttr(1.);c.AddTranslateOp().Set(Gf.Vec3d(.1,.65,1.2));c.AddScaleOp().Set(Gf.Vec3d(1.5,.01,1.));c.CreateDisplayColorAttr([Gf.Vec3f(.06,.45,.04)])
    return dict(boxes=boxes,source_floor=np.r_[cfg.scene.source_fixture_xy_m,cfg.fixtures.source_base_z_m+cfg.fixtures.base_m],target_floor=np.r_[cfg.scene.target_fixture_xy_m,cfg.fixtures.target_base_z_m+cfg.fixtures.base_m])
