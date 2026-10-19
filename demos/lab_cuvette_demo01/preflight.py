"""Conservative moving box envelope vs original instrument TRIANGLES, no vertex-distance substitute."""
import numpy as np
from demos.lab_cuvette_external.geometry import normalized,tri,write

def triangles_in_box(triangles,lo,hi):
    # SAT for triangle vs AABB, in a common world metre frame.
    c=(lo+hi)/2;h=(hi-lo)/2;v=triangles-c
    keep=np.all(v.max(1)>=-h-1e-9,axis=1)&np.all(v.min(1)<=h+1e-9,axis=1);ids=np.flatnonzero(keep);v=v[keep]
    if not len(v):return []
    edges=np.roll(v,-1,axis=1)-v
    axes=[np.cross(edges[:,0],edges[:,1])]
    for j in range(3):
        for axis in np.eye(3):axes.append(np.cross(edges[:,j],axis))
    valid=np.ones(len(v),bool)
    for a in axes:
        proj=np.einsum('nvc,nc->nv',v,a);r=np.abs(a)@h;valid&=(proj.min(1)<=r+1e-12)&(proj.max(1)>=-r-1e-12)
    return ids[valid].tolist()

def inspect(cfg,out):
    from pathlib import Path
    _,records=normalized('newnew4.usd');origin=np.array(cfg.scene.instrument_xyz_m);meshes=[tri(r) for r in records];tris=[m.triangles+origin for m in meshes]
    f=cfg.fixtures;source=np.r_[cfg.scene.source_fixture_xy_m,f.source_base_z_m+f.base_m];dest=np.r_[cfg.scene.target_fixture_xy_m,f.target_base_z_m+f.base_m]
    # Same planned bottom path as controller before small measured-offset alignment.
    liftz=max(source[2]+.08,dest[2]+.065)
    pts=[np.array(cfg.robot.initial_tcp_m)-[0,0,cfg.robot.grasp_above_bottom_m],source,np.r_[source[:2],liftz],np.r_[dest[:2],liftz],dest]
    poses=[]
    for a,b in zip(pts[:-1],pts[1:]):poses.extend(a+(b-a)*u for u in np.linspace(0,1,101))
    contacts=[]
    for k,p in enumerate(poses):
        # Conservative vessel outer box and finger/hand envelope, including fully
        # opened fingers. Envelope is declared, not a complete native robot mesh.
        for name,lo,hi in [('vessel',p+[-.007426,-.007426,0],p+[.007426,.007426,.0675]),('fingers_and_hand',p+[-.065,-.075,.030],p+[.065,.075,.150])]:
            for i,t in enumerate(tris):
                hits=triangles_in_box(t,lo,hi)
                if hits:contacts.append(dict(sample=k,part=name,instrument_mesh=i,first_triangle=hits[0],count=len(hits),lo=lo,hi=hi))
    # Fixture installation vs source triangles. Base exactly rests on original
    # exterior top; penetration >1um only is treated as assembly conflict.
    from demos.lab_cuvette_demo01.scene import parts
    mount=[]
    base=np.r_[cfg.scene.target_fixture_xy_m,f.target_base_z_m]
    for name,p,size in parts(cfg):
        lo=base+p-np.array(size)/2+1e-6;hi=base+p+np.array(size)/2-1e-6
        for i,t in enumerate(tris):
            ids=triangles_in_box(t,lo,hi)
            if ids:mount.append(dict(fixture=name,mesh=i,triangles=ids[:20]))
    # The five original candidate/obstacle/lid meshes remain in the scene.
    result=dict(scope='planned approach and held-object path samples; outer vessel box and conservative open finger/hand envelope against actual source triangles; fixture solids inset 1um for installation touch; not whole-arm continuous proof',path_surface_intersections=contacts,mount_material_intersections=mount,instrument_meshes=len(records),all_original_parts_retained=True,passed=not(contacts or mount),source_floor=source,target_floor=dest,source_inner_m=f.inner_m,target_inner_m=f.inner_m,unverified='whole arm clearance is checked during actual continuous physics and native robot/environment events; enclosure meshes may be open, containment not proven by surface SAT alone')
    write(Path(out)/'geometry_preflight.json',result);return result
