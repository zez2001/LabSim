"""CPU authored-geometry checks; explicitly separate static gates and path warnings.

No physics or IK is executed. Gripper checks use original collision-input mesh
vertices and candidate rigid poses, not a tiny TCP proxy or cooked-shape claim.
"""
from pathlib import Path
import argparse
import numpy as np
from omegaconf import OmegaConf
from pxr import Usd,UsdGeom,UsdPhysics
from scipy.spatial.transform import Rotation
from demos.lab_cuvette_demo03.scene import ROOT,ASSETS,layout,get,adapter_parts,link_local_collision_points,ORIGINAL_A_VISUAL,ORIGINAL_A_COLLISION
from demos.lab_cuvette_demo01.preflight import triangles_in_box
from demos.lab_cuvette_external.geometry import normalized,write


def instrument_triangles(cfg):
    directory=ROOT/get(cfg,'asset_directory','assets/lab_cuvette_loading/V0_demo03');stage=Usd.Stage.Open(str(directory/'instrument_demo.usda'),Usd.Stage.LoadAll);cache=UsdGeom.XformCache();data=layout(cfg);records=[]
    for p in Usd.PrimRange.Stage(stage,Usd.TraverseInstanceProxies()):
        if not p.IsA(UsdGeom.Mesh) or not p.HasAPI(UsdPhysics.CollisionAPI):continue
        mesh=UsdGeom.Mesh(p);v=np.asarray(mesh.GetPointsAttr().Get(),float);v=(np.c_[v,np.ones(len(v))]@np.asarray(cache.GetLocalToWorldTransform(p)))[:,:3];v=v@data['instrument_rotation'].T+data['instrument_origin'];f=np.asarray(mesh.GetFaceVertexIndicesAttr().Get(),int).reshape(-1,3);records.append(dict(path=str(p.GetPath()),triangles=v[f]))
    return stage,records


def _box_hits(records,lo,hi):
    out=[]
    for record in records:
        hits=triangles_in_box(record['triangles'],lo,hi)
        if hits:out.append(dict(path=record['path'],triangle_count=len(hits),first_triangle=int(hits[0])))
    return out


def hand_points_at_tcp(cfg,tcp,finger_q_m,local_points=None):
    """Nominal rigid three-link pose, zero yaw, fixed(pi,0,0) hand orientation.

    Uses joint frame position0.05839997m and mirrored prismatic Y directions.
    The native running joint/body readback is authoritative, not this plan model.
    """
    points=link_local_collision_points(cfg) if local_points is None else local_points;R=Rotation.from_euler('xyz',[np.pi,0,0]).as_matrix();origin=np.asarray(tcp)-R@np.asarray(get(cfg,'robot.tcp_local_m',[0,0,.1]));result={}
    for name,v in points.items():
        offset=np.zeros(3) if name=='panda_hand' else np.array([0,(1 if name=='panda_leftfinger' else -1)*finger_q_m,.05839997])
        result[name]=(v+offset)@R.T+origin
    return result


def planned_phase_poses(cfg):
    """Independent cup-bottom and hand-TCP paths, including released-cup hold.

    Before release the nominal held offset is grasp_above_bottom. OPEN and all
    subsequent phases leave the cup at the target; only fingers/robot withdraw.
    This is a geometric plan, never a prescribed runtime cup pose or constraint.
    """
    data=layout(cfg);source=data['source_floor'];target=data['target_floor'];grasp=float(get(cfg,'robot.grasp_above_bottom_m',.053));bottom_z=float(get(cfg,'control.transport_bottom_z_m',1.01));g=np.array([0,0,grasp])
    configured=get(cfg,'control.transport_waypoints_xy_m',None)
    if configured is None:
        one=get(cfg,'control.transport_waypoint_xy_m',None)
        if one is None and get(cfg,'control.transport_route','')=='source_x_then_target_y':one=[source[0],target[1]]
        configured=[] if one is None else [one]
    transport=[np.r_[source[:2],bottom_z],*[np.r_[np.asarray(xy,float),bottom_z] for xy in configured],np.r_[target[:2],bottom_z]]
    phases=[]
    def add(name,cup_a,cup_b,tcp_a,tcp_b,q_a,q_b,released=False):
        phases.append(dict(phase=name,cup_bottom_start_m=np.asarray(cup_a),cup_bottom_end_m=np.asarray(cup_b),hand_tcp_start_m=np.asarray(tcp_a),hand_tcp_end_m=np.asarray(tcp_b),finger_q_start_m=q_a,finger_q_end_m=q_b,cup_released=released))
    add('approach',source,source,source+[0,0,.28],source+g,.04,.04)
    add('grasp',source,source,source+g,source+g,.04,.0075)
    add('extract',source,transport[0],source+g,transport[0]+g,.0075,.0075)
    for i,(a,b) in enumerate(zip(transport[:-1],transport[1:])):add(f'transport_{i}',a,b,a+g,b+g,.0075,.0075)
    add('insert',transport[-1],target,transport[-1]+g,target+g,.0075,.0075)
    add('open',target,target,target+g,target+g,.0075,.04,True)
    lift=float(get(cfg,'control.retreat_lift_m',get(cfg,'control.retreat_m',.1)));lateral=np.asarray(get(cfg,'control.retreat_lateral_m',[0,0]),float).reshape(2);after_lift=target+g+[0,0,lift];after_lateral=after_lift+np.r_[lateral,0]
    add('retreat_lift',target,target,target+g,after_lift,.04,.04,True)
    add('retreat_lateral',target,target,after_lift,after_lateral,.04,.04,True)
    add('post_retreat_hold',target,target,after_lateral,after_lateral,.04,.04,True)
    return dict(phases=phases,transport_waypoints_m=transport,retreat_lift_m=lift,retreat_lateral_m=lateral,post_release_cup_bottom_m=target)


def inspect(cfg,out=None):
    data=layout(cfg);stage,records=instrument_triangles(cfg);static=[]
    # Inset1um excludes intended bottom face support, not wall interference.
    inv=data['instrument_rotation'].T
    native_local=[dict(path=r['path'],triangles=(r['triangles']-data['instrument_origin'])@inv.T) for r in records]
    for name,p,size in adapter_parts(cfg):
        center=data['target_origin_in_instrument']+p;hits=_box_hits(native_local,center-size/2+1e-6,center+size/2-1e-6)
        if hits:static.append(dict(adapter_part=name,hits=hits))
    # All slots retain original vessel outer dimensions and exact source mesh.
    _,vrows=normalized('TestTube_Baked.usd');vertices=vrows[0]['vertices_m'];outer=np.ptp(vertices,axis=0);source_clearance=(data['source_inner_m']-outer[:2])/2;target_clearance=(data['target_inner_m']-outer[:2])/2
    defaults=dict(source_floor=data['source_floor'],target_floor=data['target_floor'],vessel_dimensions_m=outer,source_side_clearance_m=source_clearance,target_side_clearance_m=target_clearance)
    box_mount=[]
    for box in data['boxes']:
        if box['kind']!='rack':continue
        # Default yaw0; a rotated rack is bounded conservatively for this check.
        h=np.abs(box['rotation'])@(np.asarray(box['size'])/2);hits=_box_hits(records,box['center']-h+1e-6,box['center']+h-1e-6)
        if hits:box_mount.append(dict(rack_part=box['name'],hits=hits))
    plan=planned_phase_poses(cfg);transport_points=plan['transport_waypoints_m'];local_points=link_local_collision_points(cfg)
    warnings=[];vessel_hits=[]
    for phase_data in plan['phases']:
        phase=phase_data['phase']
        for fraction in np.linspace(0,1,61):
            lerp=lambda a,b:np.asarray(a)+(np.asarray(b)-np.asarray(a))*fraction
            bottom=lerp(phase_data['cup_bottom_start_m'],phase_data['cup_bottom_end_m']);tcp=lerp(phase_data['hand_tcp_start_m'],phase_data['hand_tcp_end_m']);q=float(phase_data['finger_q_start_m']+(phase_data['finger_q_end_m']-phase_data['finger_q_start_m'])*fraction);lo=vertices.min(0)+bottom;hi=vertices.max(0)+bottom
            hits=_box_hits(records,lo+1e-6,hi-1e-6)
            if hits:vessel_hits.append(dict(phase=phase,fraction=float(fraction),bottom=bottom,hits=hits))
            for link,points in hand_points_at_tcp(cfg,tcp,q,local_points).items():
                lo=points.min(0);hi=points.max(0);hits=_box_hits(records,lo,hi)
                if hits:warnings.append(dict(phase=phase,fraction=float(fraction),link=link,lo=lo,hi=hi,hits=hits))
    no_duplicate=not stage.GetPrimAtPath(ORIGINAL_A_VISUAL).IsActive() and not stage.GetPrimAtPath(ORIGINAL_A_COLLISION).IsActive()
    result=dict(version='V0_demo03',**defaults,source_slot_id=data['source_slot_id'],target_seat_id=data['target_seat_id'],target_geometry_id=data['target_geometry_id'],rack_slots=len(data['slots']),rack_mount_intersections=box_mount,adapter_mount_intersections=static,no_duplicate_native_A=no_duplicate,all_source_slots_geometrically_valid=bool(np.all(source_clearance>0)),adapter_analytic_fit_valid=bool(np.all(target_clearance>0)),static_geometry_pass=not(static or box_mount) and no_duplicate and np.all(source_clearance>0) and np.all(target_clearance>0),transport_waypoints_m=transport_points,independent_cup_and_hand_plan=plan,post_release_cup_remains_in_target=True,planned_vessel_outer_AABB_intersections=vessel_hits,planned_hand_link_AABB_intersections=warnings,path_warning_count=len(warnings)+len(vessel_hits),passed=not(static or box_mount) and no_duplicate and np.all(source_clearance>0) and np.all(target_clearance>0) and not(vessel_hits or warnings),scope='static install actual source triangles vs solid boxes;61 samples per declared path phase; actual input-link vertices bounded by AABB, not cooked collision mesh; root actual contacts/poses remain authoritative',limitations=['No full-arm IK or whole-arm path validated here.','AABB overlap is a conservative potential collision, not proof of triangle material overlap.','Hand/finger nominal rigid poses use fixed(pi,0,0) and mirrored prismatic0.05839997 joint offsets; actual body state must be measured.','Runtime cooked convex geometry and contact skins remain unverified by this CPU check.','Source support and insertion/release must still be physically executed.'])
    if out is not None:
        out=Path(out);out.mkdir(parents=True,exist_ok=True);write(out/'geometry_preflight.json',result)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--config',type=Path,default=ROOT/'config/lab_cuvette_loading/V0_demo03/video_demo_adapted.yaml');p.add_argument('--output',type=Path,required=True);a=p.parse_args();result=inspect(OmegaConf.load(a.config),a.output);print('V0_DEMO03_PREFLIGHT','static',bool(result['static_geometry_pass']),'path warnings',result['path_warning_count'])
