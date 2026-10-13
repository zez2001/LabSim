"""Synthetic SI assets and an independent, pose-aware geometric overlap check."""
import numpy as np

TUBE_RADIUS = .005
TUBE_LENGTH = .050
HOLE_RADIUS = .0053
DEPTH = .020


def cylinder_mesh(radius, length, n):
    angles = np.arange(n) * 2 * np.pi / n
    points = np.array([[radius*np.cos(a), radius*np.sin(a), z]
                       for z in (-length/2, length/2) for a in angles])
    faces = []
    for i in range(n):
        j = (i+1) % n
        faces.extend([[i, j, n+j], [i, n+j, n+i]])
    # Correct outward winding of flat end caps.
    faces.extend([[0, i+1, i] for i in range(1, n-1)])
    faces.extend([[n, n+i, n+i+1] for i in range(1, n-1)])
    return points, np.array(faces)


def annulus_mesh(inner, outer, length, n):
    angles = np.arange(n) * 2 * np.pi / n
    p = np.array([[r*np.cos(a), r*np.sin(a), z]
                  for z in (0., length) for r in (inner, outer) for a in angles])
    f = []
    for i in range(n):
        j = (i+1) % n
        # inner, outer, bottom and top; a single closed static triangle mesh.
        quads = [[i, 2*n+i, 2*n+j, j], [n+i, n+j, 3*n+j, 3*n+i],
                 [i, j, n+j, n+i], [2*n+i, 3*n+i, 3*n+j, 2*n+j]]
        for a,b,c,d in quads:
            f.extend([[a,b,c], [a,c,d]])
    return p, np.array(f)


def rotation(q):
    w,x,y,z = np.asarray(q) / np.linalg.norm(q)
    return np.array([[1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],
                     [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],
                     [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]])


def overlap_metrics(position, quaternion, vertices, edges, hole_center, floor_z, n=128):
    """Clip the actual cooked convex tube against the wall's Z slab.

    Inside a convex polygonal straight hole, every clipped vertex must satisfy
    every hole half-plane. Vertices + edge/slab intersections give the exact
    extrema of this convex set (floating arithmetic, not a sampled axis check).
    Returns maximum wall intrusion and base intrusion in metres. Applies only
    near this finite module; escaping/outside-module states are scored separately.
    """
    p = np.asarray(vertices) @ rotation(quaternion).T + position
    top = floor_z + DEPTH
    mask = (p[:,2] >= floor_z-1e-10) & (p[:,2] <= top+1e-10)
    clipped = [p[mask]]
    for z in (floor_z, top):
        a,b = p[edges[:,0]], p[edges[:,1]]
        dz = b[:,2]-a[:,2]
        keep = (np.abs(dz)>1e-12) & ((a[:,2]-z)*(b[:,2]-z)<=0)
        a,b,dz = a[keep], b[keep], dz[keep]
        clipped.append(a + ((z-a[:,2])/dz)[:,None]*(b-a))
    v = np.concatenate(clipped)
    angles = (np.arange(n)+.5)*2*np.pi/n
    normals = np.stack([np.cos(angles), np.sin(angles)], axis=1)
    containment_error=float(np.max((v[:,:2]-hole_center)@normals.T - HOLE_RADIUS*np.cos(np.pi/n))) if len(v) else 0.
    wall = 0.
    radial_intrusion=0.
    vertical_overlap=max(0.,min(top,float(p[:,2].max()))-max(floor_z,float(p[:,2].min())))
    if len(v):
        v = v[np.linalg.norm(v[:,:2]-hole_center, axis=1) < .009]
        if len(v):
            radial_intrusion = max(0., float(np.max((v[:,:2]-hole_center)@normals.T - HOLE_RADIUS*np.cos(np.pi/n))))
            # A shallow hit on the flat entry rim overlaps in Z by micrometres,
            # not by its entire lateral interference. Include the finite slab.
            wall=min(radial_intrusion,vertical_overlap)
    near_base = np.linalg.norm(p[:,:2]-hole_center, axis=1) < .009
    base = max(0., floor_z-float(p[near_base,2].min())) if near_base.any() else 0.
    axis = rotation(quaternion)[:,2]
    bottom_axis = np.asarray(position)-axis*TUBE_LENGTH/2
    return dict(depth_m=top-float(bottom_axis[2]), lowest_depth_m=top-float(p[:,2].min()),
                xy_error_m=(bottom_axis[:2]-hole_center).tolist(),
                tilt_rad=float(np.arccos(np.clip(axis[2], -1, 1))),
                containment_error_m=containment_error,
                wall_overlap_m=wall, base_overlap_m=base,
                wall_radial_intrusion_m=radial_intrusion,wall_vertical_overlap_m=vertical_overlap,
                overlap_m=max(wall, base))


def create_assets(directory, cfg):
    from pxr import Gf, PhysxSchema, Sdf, Usd, UsdGeom, UsdPhysics, UsdShade
    from pathlib import Path
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)

    def mesh(stage, path, p, f, collision=False, convex=False):
        obj = UsdGeom.Mesh.Define(stage, path)
        # Cook small convexes in millimetre-sized local coordinates, then use an
        # explicit uniform 0.001 transform. Avoid length-scale cooking simplification.
        obj.CreatePointsAttr([Gf.Vec3f(*x) for x in (p*1000 if collision else p)])
        if collision:
            obj.AddScaleOp().Set(Gf.Vec3f(.001))
        obj.CreateFaceVertexCountsAttr([3]*len(f))
        obj.CreateFaceVertexIndicesAttr(f.reshape(-1).tolist())
        obj.CreateSubdivisionSchemeAttr('none')
        if collision:
            UsdPhysics.CollisionAPI.Apply(obj.GetPrim())
            UsdPhysics.MeshCollisionAPI.Apply(obj.GetPrim()).CreateApproximationAttr('convexHull' if convex else 'none')
            api = PhysxSchema.PhysxCollisionAPI.Apply(obj.GetPrim())
            api.CreateContactOffsetAttr(cfg.physics.contact_offset_m)
            api.CreateRestOffsetAttr(0.)
            if convex:
                hull = PhysxSchema.PhysxConvexHullCollisionAPI.Apply(obj.GetPrim())
                hull.CreateHullVertexLimitAttr(256)
                hull.CreateMinThicknessAttr(0.)
            else:
                PhysxSchema.PhysxTriangleMeshCollisionAPI.Apply(obj.GetPrim()).CreateWeldToleranceAttr(0.)
        else:
            obj.CreateDisplayColorAttr([Gf.Vec3f(.1,.45,.8)])
        return obj

    for name in ('tube', 'module'):
        stage = Usd.Stage.CreateNew(str(directory / (name+'.usda')))
        root = UsdGeom.Xform.Define(stage, '/Asset').GetPrim()
        stage.SetDefaultPrim(root)
        UsdGeom.SetStageMetersPerUnit(stage, 1.)
        UsdGeom.SetStageUpAxis(stage, 'Z')
        material = UsdShade.Material.Define(stage, '/Asset/Material')
        physmat = UsdPhysics.MaterialAPI.Apply(material.GetPrim())
        physmat.CreateStaticFrictionAttr(cfg.physics.static_friction)
        physmat.CreateDynamicFrictionAttr(cfg.physics.dynamic_friction)
        physmat.CreateRestitutionAttr(0.)
        extra = PhysxSchema.PhysxMaterialAPI.Apply(material.GetPrim())
        extra.CreateFrictionCombineModeAttr('average')
        extra.CreateRestitutionCombineModeAttr('average')
        if name == 'tube':
            p,f = cylinder_mesh(TUBE_RADIUS, TUBE_LENGTH, cfg.geometry.tube_segments)
            mesh(stage, '/Asset/Visual', p, f)
            if cfg.geometry.collision == 'analytic_cylinder':
                collider = UsdGeom.Cylinder.Define(stage, '/Asset/Collision')
                collider.CreateRadiusAttr(TUBE_RADIUS)
                collider.CreateHeightAttr(TUBE_LENGTH)
                collider.CreateAxisAttr('Z')
                UsdPhysics.CollisionAPI.Apply(collider.GetPrim())
                api=PhysxSchema.PhysxCollisionAPI.Apply(collider.GetPrim())
                api.CreateContactOffsetAttr(cfg.physics.contact_offset_m)
                api.CreateRestOffsetAttr(0.)
            elif cfg.geometry.collision=='compound_convex':
                colliders=UsdGeom.Xform.Define(stage,'/Asset/Collision')
                for i in range(cfg.geometry.tube_segments):
                    a,b=2*np.pi*i/cfg.geometry.tube_segments,2*np.pi*(i+1)/cfg.geometry.tube_segments
                    wedge=np.array([[x,y,z] for z in (-.025,.025) for x,y in
                        [(0.,0.),(.005*np.cos(a),.005*np.sin(a)),(.005*np.cos(b),.005*np.sin(b))]])
                    triangles=np.array([[0,2,1],[3,4,5],[0,1,4],[0,4,3],[1,2,5],[1,5,4],[2,0,3],[2,3,5]])
                    col=mesh(stage,f'/Asset/Collision/sector_{i:03d}',wedge,triangles,True,True)
                    UsdGeom.Imageable(col).CreatePurposeAttr('guide')
                collider=colliders
            else:
                collider = mesh(stage, '/Asset/Collision', p, f, True, True)
            UsdGeom.Imageable(collider).CreatePurposeAttr('guide')
            UsdPhysics.RigidBodyAPI.Apply(root)
            mass = UsdPhysics.MassAPI.Apply(root)
            mass.CreateMassAttr(.02)
            mass.CreateCenterOfMassAttr(Gf.Vec3f(0))
            mass.CreateDiagonalInertiaAttr(Gf.Vec3f(.02*(3*.005**2+.05**2)/12,
                                                  .02*(3*.005**2+.05**2)/12, .02*.005**2/2))
            mass.CreatePrincipalAxesAttr(Gf.Quatf(1))
            PhysxSchema.PhysxRigidBodyAPI.Apply(root).CreateEnableCCDAttr(True)
        else:
            p,f = annulus_mesh(HOLE_RADIUS, .009, DEPTH, cfg.geometry.hole_segments)
            mesh(stage, '/Asset/WallVisual', p, f).CreateDisplayColorAttr([Gf.Vec3f(.7,.7,.75)])
            collider = mesh(stage, '/Asset/WallCollision', p, f, True)
            UsdGeom.Imageable(collider).CreatePurposeAttr('guide')
            for suffix, coll in (('Visual', False), ('Collision', True)):
                base = UsdGeom.Cube.Define(stage, '/Asset/Base'+suffix)
                base.CreateSizeAttr(1.)
                base.AddTranslateOp().Set(Gf.Vec3d(0,0,-.002))
                base.AddScaleOp().Set(Gf.Vec3f(.018,.018,.004))
                base.CreateDisplayColorAttr([Gf.Vec3f(.4,.4,.45)])
                if coll:
                    UsdGeom.Imageable(base).CreatePurposeAttr('guide')
                    UsdPhysics.CollisionAPI.Apply(base.GetPrim())
                    api = PhysxSchema.PhysxCollisionAPI.Apply(base.GetPrim())
                    api.CreateContactOffsetAttr(cfg.physics.contact_offset_m)
                    api.CreateRestOffsetAttr(0.)
        UsdShade.MaterialBindingAPI.Apply(root).Bind(material, materialPurpose='physics')
        stage.GetRootLayer().Save()
    return directory
