"""One original instrument assembly, corrected vessel, unchanged full rack."""
from pathlib import Path
import numpy as np
from demos.lab_cuvette_demo03.scene import rack_parts,rack_slots,rack_dimensions,rz,get,link_local_collision_points
ROOT=Path(__file__).resolve().parents[2]
ASSETS=ROOT/'assets/lab_cuvette_loading/V0_demo04'
SEATS={'candidate_far_hinge':np.array([-.14991553560697635,.14762935326296264,.145]),'candidate_near_hinge':np.array([-.14991553560698526,.04362935326296552,.145])}

def layout(cfg):
    origin=np.asarray(cfg.rack.origin_m,float);inst=np.asarray(cfg.scene.instrument_xyz_m,float)
    # CAD far-from-hinge direction is local+Y. Choose yaw from physical placement,
    # not from the camera and not a presumed180deg correction.
    design=np.asarray(get(cfg,'scene.design_rack_origin_m',origin),float)-np.asarray(get(cfg,'scene.design_instrument_origin_m',inst),float)
    yaw=float(get(cfg,'scene.instrument_yaw_deg',np.degrees(np.arctan2(design[1],design[0]))-90.))%360
    rr=rz(cfg.rack.yaw_deg);ir=rz(yaw);sid=str(cfg.rack.selected_slot_id);seat=str(cfg.adapter.selected_target_seat_id)
    slots=[dict(s,origin_world_m=rr@s['origin_local_m']+origin) for s in rack_slots(cfg)]
    source=next(s for s in slots if s['id']==sid);target_origin=SEATS[seat];floor=ir@(target_origin+[0,0,.002])+inst
    neighbors=[]
    for ident in [str(cfg.rack.blue_slot_id)]:
        p=next(s for s in slots if s['id']==ident)
        if ident==sid:raise ValueError('Selected source cannot equal occupied blue slot')
        neighbors.append(dict(slot_id=ident,position=p['origin_world_m']+[0,0,cfg.scene.initial_bottom_gap_m],prim_path='/World/NeighborCuvette_'+ident))
    return dict(source_slot_id=sid,target_seat_id=seat,target_geometry_id=seat,rack_origin=origin,rack_rotation=rr,instrument_origin=inst,instrument_rotation=ir,instrument_yaw_deg=yaw,opening_direction_world=ir@np.array([0,1.,0]),rack_direction_world=(origin-inst)/np.linalg.norm((origin-inst)[:2]),slots=slots,source_floor=source['origin_world_m'],source_rim_z=float(source['origin_world_m'][2]+cfg.rack.depth_m),source_inner_m=float(cfg.rack.inner_m),source_depth_m=float(cfg.rack.depth_m),target_origin_in_instrument=target_origin,target_floor=floor,target_rim_z=float(floor[2]+.027),target_inner_m=.0126,target_depth_m=.027,neighbors=neighbors,boxes=[dict(name='SourceRack/'+n,center=rr@p+origin,size=s,rotation=rr,kind='rack') for n,p,s in rack_parts(cfg)])

def add_scene(world,stage,cfg):
    from pxr import UsdGeom,Gf,UsdShade,Sdf
    d=layout(cfg);directory=ROOT/cfg.asset_directory
    for path,file,xyz,yaw in [('/World/SourceRack','rack.usda',d['rack_origin'],cfg.rack.yaw_deg),('/World/Instrument','instrument_native.usda',d['instrument_origin'],d['instrument_yaw_deg'])]:
        xf=UsdGeom.Xform.Define(stage,path);xf.GetPrim().GetReferences().AddReference(str(directory/file));xf.AddTranslateOp().Set(Gf.Vec3d(*xyz));xf.AddRotateZOp().Set(float(yaw))
    for neighbor in d['neighbors']:
        xf=UsdGeom.Xform.Define(stage,neighbor['prim_path']);xf.GetPrim().GetReferences().AddReference(str(ROOT/cfg.source.vessel_collision));xf.AddTranslateOp().Set(Gf.Vec3d(*neighbor['position']));xf.AddRotateZOp().Set(float(cfg.vessel.yaw_deg))
        material=UsdShade.Material.Define(stage,neighbor['prim_path']+'/BlueMaterial');shader=UsdShade.Shader.Define(stage,neighbor['prim_path']+'/BlueMaterial/Surface');shader.CreateIdAttr('UsdPreviewSurface');shader.CreateInput('diffuseColor',Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(.035,.23,.85));shader.CreateInput('roughness',Sdf.ValueTypeNames.Float).Set(.4);material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(),'surface')
        for prim in UsdGeom.Xform(xf).GetPrim().GetChildren():
            if prim.GetName()=='Visual':
                for child in prim.GetChildren():
                    if child.IsA(UsdGeom.Mesh):UsdShade.MaterialBindingAPI.Apply(child).Bind(material)
    return d
