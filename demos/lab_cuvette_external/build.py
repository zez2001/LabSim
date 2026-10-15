"""Derived layers only: metre/Z-up visuals and source-exact authored collision meshes."""
from pathlib import Path
import json,sys,os
import numpy as np
from scipy.spatial.transform import Rotation
from omegaconf import OmegaConf
from pxr import Gf,Sdf,Usd,UsdGeom,UsdPhysics,UsdShade,PhysxSchema
from demos.lab_cuvette_external.geometry import ROOT,SOURCE,DOC,normalized,tri,write,radial_hulls

def mat(stage,path,cfg,visual=False,opacity=1.):
    m=UsdShade.Material.Define(stage,path)
    if visual:
        sh=UsdShade.Shader.Define(stage,path+'/Surface');sh.CreateIdAttr('UsdPreviewSurface')
        sh.CreateInput('diffuseColor',Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(.70,.86,.90))
        sh.CreateInput('opacity',Sdf.ValueTypeNames.Float).Set(float(opacity));sh.CreateInput('roughness',Sdf.ValueTypeNames.Float).Set(.18)
        m.CreateSurfaceOutput().ConnectToSource(sh.ConnectableAPI(),'surface')
    else:
        a=UsdPhysics.MaterialAPI.Apply(m.GetPrim());a.CreateStaticFrictionAttr(cfg.physics.static_friction);a.CreateDynamicFrictionAttr(cfg.physics.dynamic_friction);a.CreateRestitutionAttr(cfg.physics.restitution)
        a=PhysxSchema.PhysxMaterialAPI.Apply(m.GetPrim());a.CreateFrictionCombineModeAttr('average');a.CreateRestitutionCombineModeAttr('average')
    return m

def stage(path):
    s=Usd.Stage.CreateNew(str(path));s.SetDefaultPrim(UsdGeom.Xform.Define(s,'/Asset').GetPrim());UsdGeom.SetStageMetersPerUnit(s,1.);UsdGeom.SetStageUpAxis(s,'Z');return s

def add_mesh(s,path,vertices,faces):
    m=UsdGeom.Mesh.Define(s,path);m.CreatePointsAttr([Gf.Vec3f(*v) for v in vertices]);m.CreateFaceVertexCountsAttr([3]*len(faces));m.CreateFaceVertexIndicesAttr(np.array(faces).ravel().tolist());m.CreateSubdivisionSchemeAttr('none');m.CreateDoubleSidedAttr(True)
    return m

def build(output=None):
    cfg=OmegaConf.load(ROOT/'config/lab_cuvette_loading/V0_ext01.yaml');out=(ROOT/cfg.derived_directory if output is None else Path(output)).resolve()
    allowed=[(ROOT/'assets/lab_cuvette_loading/V0_ext01').resolve(),(ROOT/'outputs/lab_cuvette_loading/V0_ext01').resolve()]
    if not any(out.is_relative_to(base) for base in allowed):raise ValueError('Derived output must stay in the isolated V0_ext01 asset/output namespace')
    out.mkdir(parents=True,exist_ok=False)
    metadata=DOC if output is None else out/'metadata'
    metadata.mkdir(parents=True,exist_ok=True)
    conversion={};vessel_data=None
    for filename,label in [(cfg.source.vessel,'vessel'),(cfg.source.instrument,'instrument')]:
        source_dir=ROOT/cfg.source.directory;info,rows=normalized(filename,source_dir);conversion[label]=info
        target='source_original.usda' if label=='vessel' else 'instrument.usda'
        s=stage(out/target)
        # Put our correction on a new parent, never override the source root's existing rotation.
        parent=UsdGeom.Xform.Define(s,'/Asset/Normalized');parent.AddTransformOp().Set(Gf.Matrix4d(*np.array(info['source_world_to_normalized_row_matrix']).ravel()))
        ref=UsdGeom.Xform.Define(s,'/Asset/Normalized/Source')
        source_prim=cfg.source.vessel_prim if label=='vessel' else cfg.source.instrument_prim
        ref.GetPrim().GetReferences().AddReference(os.path.relpath(source_dir/filename,out),Sdf.Path(source_prim))
        if label=='instrument':
            pm=mat(s,'/Asset/Physics',cfg)
            for i,row in enumerate(rows):
                m=add_mesh(s,f'/Asset/Collision/Mesh{i}',row['vertices_m'],row['faces']);m.CreateVisibilityAttr('invisible')
                UsdPhysics.CollisionAPI.Apply(m.GetPrim());UsdPhysics.MeshCollisionAPI.Apply(m.GetPrim()).CreateApproximationAttr('none')
                c=PhysxSchema.PhysxCollisionAPI.Apply(m.GetPrim());c.CreateContactOffsetAttr(cfg.physics.contact_offset_m);c.CreateRestOffsetAttr(cfg.physics.rest_offset_m);UsdShade.MaterialBindingAPI.Apply(m.GetPrim()).Bind(pm,materialPurpose='physics')
                conversion[label].setdefault('collision_mapping',[]).append(dict(source_prim=row['path'],derived_prim=str(m.GetPath()),representation='static triangle mesh; all source triangles preserved',authoring_vertex_error_m=0.))
        s.GetRootLayer().Save()
        if label=='vessel':
            row=rows[0];m=tri(row)
            assert m.is_watertight and m.is_winding_consistent and m.volume>0,'Cannot integrate nonclosed source'
            density=cfg.vessel.mass_kg/m.volume;m.density=density;inertia=m.moment_inertia;values,axes=np.linalg.eigh(inertia)
            if np.linalg.det(axes)<0:axes[:,0]*=-1
            quat=Rotation.from_matrix(axes).as_quat();q=np.r_[quat[3],quat[:3]]
            vessel_data=dict(mass_kg=cfg.vessel.mass_kg,mass_source=cfg.vessel.mass_source,volume_m3=m.volume,uniform_density_kg_m3=density,center_of_mass_m=m.center_mass,inertia_tensor_about_com_kg_m2=inertia,principal_inertia_kg_m2=values,principal_axes_wxyz=q,closed=True,winding_consistent=True,assumption='uniform material density within source closed mesh; empty inner cavity excluded',coordinate_system='normalised bottom origin, Z up, metres')
            inner_floor,hulls=radial_hulls(m,cfg.vessel.radial_sectors)
            write(metadata/'collision_partition.json',dict(method='clip actual source triangles into radial sectors and three source-fillet height bands, convexify each; no box wall substitution',radial_sectors=cfg.vessel.radial_sectors,hull_count=len(hulls),inner_floor_m=inner_floor,floor_exclusion_epsilon_m=1e-7,vertices_max=max(len(h.vertices) for h in hulls),mass_integration_uses_original_closed_mesh=True))
            for variant,opacity in [('vessel',cfg.vessel.visual_opacity),('vessel_debug',1.)]:
                s=stage(out/(variant+'.usda'));vm=mat(s,'/Asset/Looks/DerivedVisual',cfg,True,opacity);pm=mat(s,'/Asset/Looks/Physics',cfg)
                vis=add_mesh(s,'/Asset/Visual/Mesh',row['vertices_m'],row['faces']);UsdShade.MaterialBindingAPI.Apply(vis.GetPrim()).Bind(vm)
                for i,hull in enumerate(hulls):
                    col=add_mesh(s,f'/Asset/Collision/Hull{i:03d}',hull.vertices,hull.faces);col.CreateVisibilityAttr('invisible');UsdPhysics.CollisionAPI.Apply(col.GetPrim());UsdPhysics.MeshCollisionAPI.Apply(col.GetPrim()).CreateApproximationAttr('convexHull')
                    a=PhysxSchema.PhysxConvexHullCollisionAPI.Apply(col.GetPrim());a.CreateHullVertexLimitAttr(cfg.vessel.max_hull_vertices);a.CreateMinThicknessAttr(cfg.vessel.convex_min_thickness_m)
                    c=PhysxSchema.PhysxCollisionAPI.Apply(col.GetPrim());c.CreateContactOffsetAttr(cfg.physics.contact_offset_m);c.CreateRestOffsetAttr(cfg.physics.rest_offset_m);UsdShade.MaterialBindingAPI.Apply(col.GetPrim()).Bind(pm,materialPurpose='physics')
                root=s.GetDefaultPrim();UsdPhysics.RigidBodyAPI.Apply(root);mass=UsdPhysics.MassAPI.Apply(root);mass.CreateMassAttr(cfg.vessel.mass_kg);mass.CreateCenterOfMassAttr(Gf.Vec3f(*m.center_mass));mass.CreateDiagonalInertiaAttr(Gf.Vec3f(*values));mass.CreatePrincipalAxesAttr(Gf.Quatf(float(q[0]),Gf.Vec3f(*q[1:])))
                a=PhysxSchema.PhysxRigidBodyAPI.Apply(root);a.CreateEnableCCDAttr(cfg.physics.ccd);a.CreateSolverPositionIterationCountAttr(cfg.physics.position_iterations);a.CreateSolverVelocityIterationCountAttr(cfg.physics.velocity_iterations)
                s.GetRootLayer().Save()
    # An independent COPY of the old rack, with source identity and hash retained; no shared inode.
    import shutil,hashlib
    rack=ROOT/'assets/lab_cuvette_loading/V0/rack.usda';shutil.copyfile(rack,out/'rack_V0_proxy.usda')
    conversion['rack']=dict(source=str(rack.relative_to(ROOT)),sha256=hashlib.sha256(rack.read_bytes()).hexdigest(),status='V0 parameterised proxy unchanged; no external rack provided',collision_parameters='inherited V0 contact offset 0.1mm/rest0 and material; not silently overwritten')
    write(metadata/'conversion.json',conversion);write(metadata/'vessel_mass_properties.json',vessel_data)
    print('DERIVED_ASSETS',out)

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,help='new empty directory in V0_ext01 namespace; existing output is never overwritten');args=p.parse_args();build(args.output)
