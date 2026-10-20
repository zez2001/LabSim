"""Recompose exact native instrument geometry and explicit provisional frames.

This is a static asset review, not a completed replica or a physical episode.
No rack is invented and no exterior engineering holder is added.
"""
import argparse
import hashlib
import os
from pathlib import Path
import numpy as np
from omegaconf import OmegaConf
from pxr import Gf, Sdf, Usd, UsdGeom, UsdLux, UsdPhysics, UsdShade, PhysxSchema
from scipy.spatial.transform import Rotation
import trimesh
from demos.lab_cuvette_external.geometry import ROOT, normalized, write
from demos.lab_cuvette_external.build import stage as asset_stage, add_mesh, mat

OUT = ROOT/'assets/lab_cuvette_loading/V0_demo02/video_pose_verified'


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def visual_records(stage, prefix):
    cache = UsdGeom.XformCache()
    result = []
    for p in Usd.PrimRange.Stage(stage, Usd.TraverseInstanceProxies()):
        if p.IsA(UsdGeom.Mesh) and str(p.GetPath()).startswith(prefix):
            v = np.array(UsdGeom.Mesh(p).GetPointsAttr().Get(), dtype=float)
            matrix = np.array(cache.GetLocalToWorldTransform(p))
            result.append((str(p.GetPath()), (np.c_[v, np.ones(len(v))]@matrix)[:, :3]))
    return result


def xform(stage, path, xyz):
    p = UsdGeom.Xform.Define(stage, path)
    p.AddTranslateOp().Set(Gf.Vec3d(*map(float, xyz)))
    return p


def build(cfg_path, out, source_pose=False):
    if out.exists():
        raise FileExistsError(out)
    out.mkdir(parents=True)
    cfg = OmegaConf.load(cfg_path)
    if source_pose:
        cfg.lid_pose.enabled = False
    source = ROOT/cfg.source.instrument
    info, rows = normalized(source.name, source.parent)
    lid = next(r for r in rows if '/tn__3_ZBFi3j3/' in r['path'])
    hinges = [r for r in rows if '/tn__4_ZBFi3j3/' in r['path'] or '/tn__4_1_dNPo5b5/' in r['path']]
    pivot = np.mean([(r['vertices_m'].min(0)+r['vertices_m'].max(0))/2 for r in hinges], axis=0)
    lm = trimesh.Trimesh(lid['vertices_m'], lid['faces'], process=False)
    groups = {}
    for i, normal in enumerate(lm.face_normals):
        n = normal.copy()
        if n[np.argmax(np.abs(n))] < 0:
            n = -n
        groups.setdefault(tuple(np.round(n, 6)), []).append(i)
    ids = max(groups.values(), key=lambda ids: lm.area_faces[ids].sum())
    n = lm.face_normals[ids].copy()
    n[n[:, 2] < 0] *= -1
    n = np.average(n, axis=0, weights=lm.area_faces[ids]); n /= np.linalg.norm(n)
    source_angle = float(np.degrees(np.arctan2(-n[1], n[2])))
    delta = float(cfg.lid_pose.target_main_plane_angle_deg-source_angle) if cfg.lid_pose.enabled else 0.0
    d = np.eye(4); d[:3, :3] = Rotation.from_euler('x', delta, degrees=True).as_matrix().T
    d[3, :3] = pivot-pivot@d[:3, :3]
    pose = dict(source_main_plane_angle_deg=source_angle, main_plane_area_m2=float(lm.area_faces[ids].sum()),
                main_plane_normal=n, target_main_plane_angle_deg=cfg.lid_pose.target_main_plane_angle_deg,
                delta_deg=delta, hinge_axis_origin_in_instrument_m=pivot, hinge_axis=[1, 0, 0],
                derived_rigid_pose_row_matrix=d, angle_source=cfg.lid_pose.angle_source,
                hinge_axis_source=cfg.lid_pose.hinge_axis_source,
                changed_source_file=False, source_geometry_rescaled=False)
    asset = out/'instrument_native.usda'
    s = asset_stage(asset)
    normalized_root = UsdGeom.Xform.Define(s, '/Asset/Visual')
    normalized_root.AddTransformOp().Set(Gf.Matrix4d(*np.array(info['source_world_to_normalized_row_matrix']).ravel()))
    ref = UsdGeom.Xform.Define(s, '/Asset/Visual/Source')
    ref.GetPrim().GetReferences().AddReference(os.path.relpath(source, out), Sdf.Path(cfg.source.instrument_prim))
    if abs(delta) > 1e-12:
        source_instance = lid['path'].rsplit('/', 2)[0]
        instance_path = source_instance.replace('/RotatedRoot', '/Asset/Visual/Source', 1)
        prim = s.GetPrimAtPath(instance_path)
        cache = UsdGeom.XformCache()
        parent_world = np.array(cache.GetLocalToWorldTransform(prim.GetParent()))
        world = np.array(cache.GetLocalToWorldTransform(prim))
        local = world@d@np.linalg.inv(parent_world)
        xf = UsdGeom.Xformable(prim); xf.ClearXformOpOrder()
        xf.AddTransformOp(opSuffix='videoPose').Set(Gf.Matrix4d(*local.ravel()))
    expected_vertices = {r['path']: ((np.c_[r['vertices_m'], np.ones(len(r['vertices_m']))]@d)[:, :3]
                         if r is lid else r['vertices_m']) for r in rows}
    pm = mat(s, '/Asset/Physics', cfg)
    collisions = []
    for i, row in enumerate(rows):
        mesh = add_mesh(s, f'/Asset/Collision/SourceMesh{i}', expected_vertices[row['path']], row['faces'])
        mesh.CreateVisibilityAttr('invisible')
        p = mesh.GetPrim()
        UsdPhysics.CollisionAPI.Apply(p)
        UsdPhysics.MeshCollisionAPI.Apply(p).CreateApproximationAttr('none')
        contact = PhysxSchema.PhysxCollisionAPI.Apply(p)
        contact.CreateContactOffsetAttr(cfg.physics.contact_offset_m)
        contact.CreateRestOffsetAttr(cfg.physics.rest_offset_m)
        UsdShade.MaterialBindingAPI.Apply(p).Bind(pm, materialPurpose='physics')
        collisions.append(dict(source_prim=row['path'], derived_prim=str(p.GetPath()),
                               approximation='static triangle mesh, original triangles, no convex fill',
                               nominal_analytic_vertex_change_m=0.0,
                               observed_float32_input_rounding_m=float(np.linalg.norm(np.array(mesh.GetPointsAttr().Get(), dtype=float)-expected_vertices[row['path']], axis=1).max()),
                               cooked_geometry_readback='unavailable'))
    candidates = [r for r in rows if '/tn__2_ZBFi3j3/' in r['path'] or '/tn__2_1_dNPo5b5/' in r['path']]
    candidates.sort(key=lambda r: -np.mean(r['vertices_m'][:, 1]))
    frames = []
    for name, row in zip(['candidate_far_hinge', 'candidate_near_hinge'], candidates):
        lo, hi = row['vertices_m'].min(0), row['vertices_m'].max(0)
        origin = np.r_[(lo[:2]+hi[:2])/2, lo[2]]
        f = xform(s, '/Asset/Frames/'+name, origin)
        f.GetPrim().CreateAttribute('labsim:identityStatus', Sdf.ValueTypeNames.String).Set('unconfirmed')
        frames.append(dict(id=name, source_prim=row['path'], origin_in_instrument_m=origin,
                           dimensions_m=hi-lo, lower_extent_z_m=lo[2], top_extent_z_m=hi[2],
                           source_world_to_normalized_row_matrix=info['source_world_to_normalized_row_matrix'],
                           support_height_m=None, support_note='lower extent is not the actual support; see measured surface rays'))
    chamber_origin = np.mean([f['origin_in_instrument_m'] for f in frames], axis=0)
    xform(s, '/Asset/Frames/chamber_survey', chamber_origin)
    s.GetRootLayer().Save()
    s = Usd.Stage.Open(str(asset))
    observed = visual_records(s, '/Asset/Visual/Source')
    diffs = []
    for row in rows:
        path = row['path'].replace('/RotatedRoot', '/Asset/Visual/Source', 1)
        points = next(v for p, v in observed if p == path)
        diffs.append(dict(source_prim=row['path'], normalized_to_derived_max_vertex_error_m=float(np.linalg.norm(points-expected_vertices[row['path']], axis=1).max()),
                          max_intentional_pose_displacement_m=float(np.linalg.norm(expected_vertices[row['path']]-row['vertices_m'], axis=1).max())))
    scene_path = out/'scene_review.usda'
    s = Usd.Stage.CreateNew(str(scene_path))
    s.SetDefaultPrim(UsdGeom.Xform.Define(s, '/World').GetPrim())
    UsdGeom.SetStageMetersPerUnit(s, 1.0)
    UsdGeom.SetStageUpAxis(s, 'Z')
    root = xform(s, '/World/Instrument', cfg.scene.instrument_xyz_m)
    root.AddRotateZOp().Set(float(cfg.scene.instrument_yaw_deg))
    root.GetPrim().GetReferences().AddReference('instrument_native.usda')
    neighbor = xform(s, '/World/NeighborInstrument', cfg.scene.neighbor_instrument_xyz_m)
    neighbor.GetPrim().GetReferences().AddReference('instrument_native.usda')
    neighbor.GetPrim().CreateAttribute('labsim:placementSource', Sdf.ValueTypeNames.String).Set('second instrument visible in video; placement engineering estimate, not calibrated')
    # Two explicit frame levels; IDs are provisional, not accepted task targets.
    chamber = xform(s, '/World/Instrument/TaskFrames/chamber_survey', chamber_origin)
    chamber.GetPrim().CreateAttribute('labsim:status', Sdf.ValueTypeNames.String).Set('survey frame only, not calibrated')
    for f in frames:
        xform(s, '/World/Instrument/TaskFrames/chamber_survey/'+f['id'], f['origin_in_instrument_m']-chamber_origin)
    missing = UsdGeom.Xform.Define(s, '/World/SourceRackUnavailable')
    missing.GetPrim().CreateAttribute('labsim:reason', Sdf.ValueTypeNames.String).Set('complete provided rack asset not found; no substitute geometry')
    table = UsdGeom.Cube.Define(s, '/World/Table')
    table.CreateSizeAttr(1.0)
    table.AddTranslateOp().Set(Gf.Vec3d(*cfg.scene.table_center_xy_m, cfg.scene.table_top_m-.04))
    table.AddScaleOp().Set(Gf.Vec3d(*cfg.scene.table_size_m))
    table.CreateDisplayColorAttr([Gf.Vec3f(.2, .5, .55)])
    UsdPhysics.CollisionAPI.Apply(table.GetPrim())
    UsdLux.DomeLight.Define(s, '/World/Light').CreateIntensityAttr(1000)
    robot = xform(s, '/World/Franka', cfg.robot.base_m)
    robot.GetPrim().GetReferences().AddReference(os.path.relpath(ROOT/cfg.robot.usd_path, out))
    preview_position = np.array(cfg.scene.instrument_xyz_m)+np.r_[frames[0]['origin_in_instrument_m'][:2], frames[0]['top_extent_z_m']+cfg.scene.preview_vessel_gap_above_candidate_m]
    cup = xform(s, '/World/VesselPreview', preview_position)
    cup.GetPrim().GetReferences().AddReference(os.path.relpath(ROOT/cfg.source.vessel_collision, out))
    cup.GetPrim().CreateAttribute('labsim:status', Sdf.ValueTypeNames.String).Set('unsupported initial CAD comparison pose; no physics steps or task claim')
    s.GetRootLayer().Save()
    loaded = Usd.Stage.Open(str(scene_path))
    final = visual_records(loaded, '/World/Instrument/Visual/Source')
    angle = np.radians(cfg.scene.instrument_yaw_deg)
    rotation = np.array([[np.cos(angle), -np.sin(angle), 0], [np.sin(angle), np.cos(angle), 0], [0, 0, 1]])
    for row in rows:
        path = row['path'].replace('/RotatedRoot', '/World/Instrument/Visual/Source', 1)
        points = next(v for p, v in final if p == path)
        expected = expected_vertices[row['path']]@rotation.T+np.array(cfg.scene.instrument_xyz_m)
        next(d for d in diffs if d['source_prim'] == row['path'])['normalized_to_scene_max_vertex_error_m'] = float(np.linalg.norm(points-expected, axis=1).max())
    data = dict(version='V0_demo02', source_file=str(source.relative_to(ROOT)), source_sha256=sha(source),
                source_metadata=info, frames=frames, chamber_survey_origin_in_instrument_m=chamber_origin, lid_pose=pose,
                transform_validation=diffs, collision_mapping=collisions,
                original_instrument_parts_retained=True, geometry_rescaled=False,
                rack_asset_available=False, target_identity_confirmed=False,
                scene_correspondence_accepted=False, workflow_executed=False,
                cad_pair_verified=False, real_calibrated=False, data_eligible=False,
                preview_initial_position_m=preview_position,
                preview_is_trajectory=False,
                assets={p.name: sha(p) for p in [asset, scene_path]},
                dependencies={str((ROOT/p).relative_to(ROOT)): sha(ROOT/p) for p in [cfg.source.vessel_collision, cfg.robot.usd_path]})
    write(out/'manifest.json', data)
    print('BUILT_NATIVE_REVIEW', out, 'max_transform_error_m', max(max(x['normalized_to_derived_max_vertex_error_m'], x['normalized_to_scene_max_vertex_error_m']) for x in diffs))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path, default=ROOT/'config/lab_cuvette_loading/V0_demo02/native_scene.yaml')
    parser.add_argument('--output', type=Path, default=OUT)
    parser.add_argument('--source-pose', action='store_true', help='retain original CAD lid pose as a control')
    args = parser.parse_args()
    build(args.config, args.output, args.source_pose)
