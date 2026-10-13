"""Read shape coefficients from PhysX tensors, including unbound defaults."""
import numpy as np
from itertools import product


def runtime_shape_parameters(world,robot=None):
    rows={}
    for path in ('/World/Tube','/World/Franka/panda_leftfinger','/World/Franka/panda_rightfinger','/World/Franka/panda_hand'):
        try:
            view=world.physics_sim_view.create_rigid_body_view(path)
            if view.count==0:
                raise RuntimeError('No runtime rigid body matched')
            rows[path]=dict(count=view.count,max_shapes=view.max_shapes,
                static_dynamic_friction_restitution=np.asarray(view.get_material_properties()).tolist(),
                contact_offsets_m=np.asarray(view.get_contact_offsets()).tolist(),
                rest_offsets_m=np.asarray(view.get_rest_offsets()).tolist(),
                note='Per runtime shape, obtained from PhysX tensors; no parameter mutation.')
        except Exception as error:
            rows[path]=dict(error=str(error),verified=False)
    if robot is not None:
        try:
            view=robot._articulation_view._physics_view
            rows['articulation_runtime']=dict(
                max_joint_velocities=np.asarray(view.get_dof_max_velocities()).tolist(),
                max_joint_forces=np.asarray(view.get_dof_max_forces()).tolist(),
                joint_stiffness=np.asarray(view.get_dof_stiffnesses()).tolist(),
                joint_damping=np.asarray(view.get_dof_dampings()).tolist())
        except Exception as error:
            rows['articulation_runtime']=dict(error=str(error),verified=False)
    return rows


def gripper_vertical_clearance(world,stage,hole_mouth_z):
    """Conservative authored bounds at actual link poses, without moving actors."""
    from pxr import UsdGeom,UsdPhysics
    from demos.minimal_precision_insertion.geometry import rotation
    cache=UsdGeom.BBoxCache(0,['default','guide','proxy','render'],False,True)
    rows=[]
    for name in ('panda_leftfinger','panda_rightfinger','panda_hand'):
        path='/World/Franka/'+name
        view=world.physics_sim_view.create_rigid_body_view(path)
        pose=np.asarray(view.get_transforms())[0]
        r=rotation(np.r_[pose[6],pose[3:6]])
        link=stage.GetPrimAtPath(path)
        for prim in stage.Traverse():
            if str(prim.GetPath()).startswith(path+'/') and prim.HasAPI(UsdPhysics.CollisionAPI):
                box=cache.ComputeRelativeBound(prim,link).ComputeAlignedRange()
                if box.IsEmpty():continue
                bounds=np.array([box.GetMin(),box.GetMax()])
                corners=np.array(list(product(*zip(bounds[0],bounds[1]))))
                z=(corners@r.T+pose[:3])[:,2]
                rows.append(dict(collider=str(prim.GetPath()),lowest_world_z_m=float(z.min()),
                    above_hole_mouth_m=float(z.min()-hole_mouth_z)))
    return dict(colliders=rows,minimum_vertical_clearance_m=min(x['above_hole_mouth_m'] for x in rows) if rows else None,
        limitation='Author geometry AABBs transformed by actual runtime link poses; not a readback of cooked finger convexes.')


def tube_radial_probe(tube,n=128):
    """Sample actual ray-query geometry at three local axial slices, not contact shells."""
    import omni.physx
    from demos.minimal_precision_insertion.geometry import rotation
    p,q=tube.get_world_pose();r=rotation(q)
    query=omni.physx.get_physx_scene_query_interface()
    def tube_hits(origin,direction,length):
        hits=[]
        def collect(hit):
            if str(hit.collision).startswith('/World/Tube/'):
                hits.append(float(hit.distance))
            return True
        query.raycast_all(tuple(origin),tuple(direction),length,collect,True)
        return hits
    rays=[]
    for z in (-.02,0.,.02):
        for i in range(n):
            a=(i+.37)*2*np.pi/n;radial=np.array([np.cos(a),np.sin(a),0.])
            hits=tube_hits(p+r@(radial*.02+np.array([0,0,z])),r@(-radial),.04)
            rays.append(dict(z_local_m=z,angle_rad=float(a),radius_m=.02-min(hits) if hits else None))
    axial=[]
    for sign in (-1,1):
        origin=p+r@np.array([.001,.000317,sign*.04])
        hits=tube_hits(origin,r@np.array([0,0,-sign]),.08)
        axial.append(dict(sign=sign,end_z_local_m=sign*(.04-min(hits)) if hits else None))
    values=[x['radius_m'] for x in rays if x['radius_m'] is not None]
    return dict(radial_rays=rays,axial_rays=axial,radial_sample_count=len(values),
        sampled_radius_range_m=[min(values),max(values)] if values else [],
        sampled_max_radius_error_m=max(abs(x-.005) for x in values) if values else None,
        limitation='384 angular rays at three axial slices and two end-cap rays; not a complete runtime collision representation dump.')
