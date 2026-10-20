"""V0_demo03 full 6x6 engineering rack and in-chamber A adapter geometry.

All dimensions here are explicit engineering design values, not measured rack
CAD. Units are metres, Z-up. Original supplied vessel dimensions are preserved.
"""
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parents[2]
ASSETS=ROOT/'assets/lab_cuvette_loading/V0_demo03'
A_ORIGIN=np.array([-.14991553560697635,.14762935326296264,.145])
ORIGINAL_A_VISUAL='/Asset/Visual/Source/newnew4/newnew4/tn__2_ZBFi3j3'
ORIGINAL_A_COLLISION='/Asset/Collision/SourceMesh3'


def get(cfg,path,default=None):
    value=cfg
    try:
        for key in path.split('.'):value=value[key]
        return value
    except (KeyError,TypeError,AttributeError):return default


def rz(degrees):
    a=np.radians(float(degrees));return np.array([[np.cos(a),-np.sin(a),0],[np.sin(a),np.cos(a),0],[0,0,1.]])


def rack_dimensions(cfg):
    n=int(get(cfg,'rack.rows',6));m=int(get(cfg,'rack.columns',6))
    if (n,m)!=(6,6):raise ValueError('V0_demo03 design is a complete6x6 rack')
    inner=float(get(cfg,'rack.inner_m',.016));wall=float(get(cfg,'rack.wall_m',.002));depth=float(get(cfg,'rack.depth_m',.025));base=float(get(cfg,'rack.base_m',.003))
    return dict(rows=n,columns=m,inner_m=inner,wall_m=wall,depth_m=depth,base_m=base,outer_xy_m=np.array([m*inner+(m+1)*wall,n*inner+(n+1)*wall]),total_height_m=base+depth,pitch_m=inner+wall)


def rack_parts(cfg):
    """50 nonoverlapping-interior boxes: base,7 X walls,42 short Y walls."""
    d=rack_dimensions(cfg);a=d['inner_m'];w=d['wall_m'];h=d['depth_m'];b=d['base_m'];sx,sy=d['outer_xy_m'];pitch=d['pitch_m']
    parts=[('Base',np.array([0,0,b/2]),np.array([sx,sy,b]))]
    for column in range(7):parts.append((f'XWall_{column}',np.array([-sx/2+w/2+column*pitch,0,b+h/2]),np.array([w,sy,h])))
    for row in range(7):
        for column in range(6):parts.append((f'YWall_{row}_{column}',np.array([(column-2.5)*pitch,-sy/2+w/2+row*pitch,b+h/2]),np.array([a,w,h])))
    return parts


def rack_slots(cfg):
    """A is negative rack-local Y (camera/front edge);1 is negative local X.

    With default rack yaw0 A1 is the world(-X,-Y) corner and F6 the(+X,+Y)
    far corner. These IDs follow the rack rigid transform in randomized scenes.
    """
    d=rack_dimensions(cfg);result=[]
    for row in range(6):
        for col in range(6):
            point=np.array([(col-2.5)*d['pitch_m'],(row-2.5)*d['pitch_m'],d['base_m']]);matrix=np.eye(4);matrix[3,:3]=point
            result.append(dict(id=chr(65+row)+str(col+1),row=row,column=col,origin_local_m=point,local_frame_row_matrix=matrix,inner_m=d['inner_m'],depth_m=d['depth_m']))
    return result


def adapter_parts(cfg):
    outer=float(get(cfg,'adapter.outer_m',.0204));inner=float(get(cfg,'adapter.inner_m',.016));height=float(get(cfg,'adapter.height_m',.029));base=float(get(cfg,'adapter.base_m',.002));w=(outer-inner)/2;h=height-base
    if not (outer>inner>0 and height>base>0):raise ValueError('Invalid adapter material dimensions')
    return [('Base',np.array([0,0,base/2]),np.array([outer,outer,base])),('West',np.array([-(inner+w)/2,0,base+h/2]),np.array([w,outer,h])),('East',np.array([(inner+w)/2,0,base+h/2]),np.array([w,outer,h])),('South',np.array([0,-(inner+w)/2,base+h/2]),np.array([inner,w,h])),('North',np.array([0,(inner+w)/2,base+h/2]),np.array([inner,w,h]))]


def layout(cfg):
    rack_origin=np.asarray(get(cfg,'rack.origin_m',get(cfg,'scene.rack_xyz_m',[-.04,-.22,.74])),float);rr=rz(get(cfg,'rack.yaw_deg',get(cfg,'scene.rack_yaw_deg',0)));inst_origin=np.asarray(get(cfg,'scene.instrument_xyz_m',[.36,.18,.74]),float);ir=rz(get(cfg,'scene.instrument_yaw_deg',0));d=rack_dimensions(cfg)
    slot_id=str(get(cfg,'rack.selected_slot_id',get(cfg,'scene.source_slot_id',get(cfg,'rack.source_slot_id','A1'))))
    slots=[]
    for slot in rack_slots(cfg):slots.append({**slot,'origin_world_m':rr@slot['origin_local_m']+rack_origin})
    selected=next((s for s in slots if s['id']==slot_id),None)
    if selected is None:raise ValueError(f'Unknown source slot {slot_id}')
    adapter_origin=np.asarray(get(cfg,'adapter.origin_in_instrument_m',A_ORIGIN),float)
    base=float(get(cfg,'adapter.base_m',.002));height=float(get(cfg,'adapter.height_m',.029))
    target=ir@(adapter_origin+[0,0,base])+inst_origin
    boxes=[]
    for name,p,size in rack_parts(cfg):boxes.append(dict(name='SourceRack/'+name,center=rr@p+rack_origin,size=size,rotation=rr,kind='rack'))
    for name,p,size in adapter_parts(cfg):boxes.append(dict(name='Instrument/EngineeringAdapterA/'+name,center=ir@(adapter_origin+p)+inst_origin,size=size,rotation=ir,kind='target'))
    neighbors=[]
    for entry in get(cfg,'rack.neighbor_slots',[get(cfg,'rack.blue_slot_id','F6')]):
        s=next((s for s in slots if s['id']==str(entry)),None)
        if s is None or s['id']==slot_id:raise ValueError(f'Invalid or duplicate neighbor slot {entry}')
        neighbors.append(dict(slot_id=s['id'],position=s['origin_world_m']+np.array([0,0,float(get(cfg,'scene.initial_bottom_gap_m',0))]),prim_path='/World/NeighborCuvette_'+s['id']))
    return dict(source_slot_id=slot_id,target_seat_id=str(get(cfg,'adapter.selected_target_seat_id','candidate_far_hinge')),target_geometry_id='engineering_adapter_A',rack_origin=rack_origin,rack_rotation=rr,instrument_origin=inst_origin,instrument_rotation=ir,slots=slots,source_floor=selected['origin_world_m'],source_floor_frame=selected,source_rim_z=float(selected['origin_world_m'][2]+d['depth_m']),target_floor=target,target_rim_z=float(target[2]+height-base),target_inner_m=float(get(cfg,'adapter.inner_m',.016)),target_depth_m=height-base,target_origin_in_instrument=adapter_origin,neighbors=neighbors,boxes=boxes,source_inner_m=d['inner_m'],source_depth_m=d['depth_m'])


def add_scene(world,stage,cfg):
    """Author references only; root executor owns World/robot/dynamic active cup."""
    from pxr import UsdGeom,Gf,UsdShade,Sdf
    data=layout(cfg);directory=ROOT/get(cfg,'asset_directory','assets/lab_cuvette_loading/V0_demo03')
    for path,file,origin,yaw in [('/World/SourceRack',directory/'rack.usda',data['rack_origin'],get(cfg,'rack.yaw_deg',get(cfg,'scene.rack_yaw_deg',0))),('/World/Instrument',directory/'instrument_demo.usda',data['instrument_origin'],get(cfg,'scene.instrument_yaw_deg',0))]:
        xf=UsdGeom.Xform.Define(stage,path);xf.GetPrim().GetReferences().AddReference(str(file));xf.AddTranslateOp().Set(Gf.Vec3d(*origin));xf.AddRotateZOp().Set(float(yaw))
    if get(cfg,'scene.include_neighbor_instrument',True):
        p=UsdGeom.Xform.Define(stage,'/World/NeighborInstrument');p.GetPrim().GetReferences().AddReference(str(ROOT/'assets/lab_cuvette_loading/V0_demo02/video_pose_verified/instrument_native.usda'));p.AddTranslateOp().Set(Gf.Vec3d(*get(cfg,'scene.neighbor_instrument_xyz_m',[.96,.53,.74])))
    for neighbor in data['neighbors']:
        p=UsdGeom.Xform.Define(stage,neighbor['prim_path']);p.GetPrim().GetReferences().AddReference(str(ROOT/get(cfg,'source.vessel_collision','assets/lab_cuvette_loading/V0_ext02/walls28_mm.usda')));p.AddTranslateOp().Set(Gf.Vec3d(*neighbor['position']))
        material=UsdShade.Material.Define(stage,neighbor['prim_path']+'/BlueNeighborMaterial');shader=UsdShade.Shader.Define(stage,neighbor['prim_path']+'/BlueNeighborMaterial/Surface');shader.CreateIdAttr('UsdPreviewSurface');shader.CreateInput('diffuseColor',Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(.035,.23,.85));shader.CreateInput('roughness',Sdf.ValueTypeNames.Float).Set(.4);material.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(),'surface')
        mesh=stage.GetPrimAtPath(neighbor['prim_path']+'/Visual/Mesh')
        if mesh:UsdShade.MaterialBindingAPI.Apply(mesh).Bind(material)
    return data


add_engineering_scene=add_scene


def link_local_collision_points(cfg):
    """Collision INPUT vertices in each of three rigid-link local metre frames.

    Runtime callers must use the actual tensor body pose for each link. These
    points do not include PhysX convex cooking margins or prove full-arm safety.
    """
    from pxr import Usd,UsdGeom,UsdPhysics
    stage=Usd.Stage.Open(str(ROOT/get(cfg,'robot.usd_path','assets/robots/Franka.usd')),Usd.Stage.LoadAll);cache=UsdGeom.XformCache();result={}
    for name in ['panda_hand','panda_leftfinger','panda_rightfinger']:
        candidates=[p for p in stage.Traverse() if p.GetName()==name and p.HasAPI(UsdPhysics.RigidBodyAPI)]
        if len(candidates)!=1:raise RuntimeError(f'Cannot identify unique rigid link {name}')
        link=candidates[0];inverse=np.linalg.inv(np.asarray(cache.GetLocalToWorldTransform(link)));points=[]
        for p in Usd.PrimRange.Stage(stage,Usd.TraverseInstanceProxies()):
            if p.IsA(UsdGeom.Mesh) and p.HasAPI(UsdPhysics.CollisionAPI) and str(p.GetPath()).startswith(str(link.GetPath())+'/'):
                # Match the existing metre World reference semantics exactly:
                # USD references do not automatically convert source layer units.
                # This legacy robot already authors0.01 geometry scales and
                # metre-sized link transforms despite metadata metersPerUnit=.01.
                v=np.asarray(UsdGeom.Mesh(p).GetPointsAttr().Get(),float);M=np.asarray(cache.GetLocalToWorldTransform(p))@inverse;points.append((np.c_[v,np.ones(len(v))]@M)[:,:3])
        if not points:raise RuntimeError(f'No collision input mesh for {name}')
        result[name]=np.concatenate(points)
    return result


hand_local_collision_points=link_local_collision_points
