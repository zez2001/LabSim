"""Standalone XY-only asset family; source, topology and contacts unchanged.

Widths are hypotheses, not measurements. Uniform material-volume mass
distribution and fixed20g mass are retained; numerical density changes.
This module does not start Isaac, cook PhysX shapes or run simulation.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
import trimesh
from pxr import Gf, Usd, UsdGeom, UsdPhysics, UsdShade
from demos.lab_cuvette_demo04.build_vessel import (
    read_geometry, integrate_material, serializable, usd_mass_snapshot)

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'assets/lab_cuvette_loading/V0_demo04/vessel_125_mm.usda'
DIRECTORY = ROOT / 'assets/lab_cuvette_loading/Size_v1'
EXPECTED_SOURCE_SHA = '8d52757227303edd4f38918ee04763481f08846fdd8daa6803295c8fc77c689d'
MASS_KG = .020
SCHEMA = 'labsim.Size_v1.asset_registry.v1'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def rel(path):
    return str(Path(path).resolve().relative_to(ROOT))


def write(path, data):
    Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False,
        default=serializable, allow_nan=False) + '\n')


def asset_id(width_mm):
    number = round(float(width_mm) * 100)
    if abs(number / 100 - float(width_mm)) > 1e-8:
        raise ValueError('Width precision must be0.01mm or coarser')
    return f'cuvette_xy_{number:04d}'


def _attributes(prim):
    return {a.GetName(): str(a.Get()) for a in prim.GetAttributes()}


def cavity_measurements(stage):
    """Actual internal central-axis ray intervals; not a square cavity proxy."""
    g = read_geometry(stage)['/Asset/Visual/Mesh']
    mesh = trimesh.Trimesh(g['body_points'], g['faces'], process=True)
    rows = []
    for z in (.010, .0265, .060):
        gaps = []
        for direction in ([1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0]):
            hits, _, _ = mesh.ray.intersects_location([[0, 0, z]], [direction], multiple_hits=True)
            if not len(hits):
                raise ValueError('Missing inner-cavity surface ray')
            gaps.append(float(np.linalg.norm(hits - [0, 0, z], axis=1).min()))
        rows.append({'height_above_bottom_mm': z * 1000,
            'actual_central_inner_clear_width_X_mm': (gaps[0] + gaps[1]) * 1000,
            'actual_central_inner_clear_width_Y_mm': (gaps[2] + gaps[3]) * 1000,
            'method': 'Nearest actual triangle-surface hit from cavity centre along each signedXY axis; local corners not replaced by this measurement'})
    return rows


def supplement_metadata(record, stage):
    record['inner_cavity_sections'] = cavity_measurements(stage)
    record['material_attributes'] = [{'prim': str(p.GetPath()), 'attributes': _attributes(p)}
                                    for p in stage.Traverse() if p.IsA(UsdShade.Material)]
    record['root_rigid_body_attributes'] = {a.GetName(): str(a.Get())
        for a in stage.GetDefaultPrim().GetAttributes()
        if a.GetName().startswith(('physics:', 'physxRigidBody:'))}
    for c in record['collision_input_shapes']:
        c.pop('all_authored_and_schema_attributes', None)
        c['configuration_attributes_excluding_vertex_arrays'] = {
            k: v for k, v in _attributes(stage.GetPrimAtPath(c['prim'])).items()
            if k not in {'points', 'extent', 'faceVertexCounts', 'faceVertexIndices'}}
    record['metadata_verification'] = {'builder_current_sha256': sha(__file__),
        'asset_sha256_rechecked': sha(ROOT / record['asset_path']) == record['asset_sha256'],
        'USD_geometry_rewritten_by_metadata_supplement': False}
    return record


def build_one(width_mm, directory=DIRECTORY):
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    if sha(SOURCE) != EXPECTED_SOURCE_SHA:
        raise ValueError('Preserved12.5mm source SHA differs')
    ident = asset_id(width_mm)
    out, evidence = directory / (ident + '.usda'), directory / (ident + '.json')
    if out.exists() or evidence.exists():
        if not (out.exists() and evidence.exists()):
            raise FileExistsError('Partial asset exists; use a fresh directory')
        old = json.loads(evidence.read_text())
        if old['asset_sha256'] != sha(out) or old['source']['sha256'] != sha(SOURCE):
            raise ValueError('Existing asset provenance differs')
        if old['nominal_outer_xy_mm'] != [float(width_mm)] * 2:
            raise ValueError('Existing asset size differs')
        supplement_metadata(old, Usd.Stage.Open(str(out)))
        write(evidence, old)
        return old
    src = Usd.Stage.Open(str(SOURCE), Usd.Stage.LoadAll)
    if UsdGeom.GetStageMetersPerUnit(src) != 1 or str(UsdGeom.GetStageUpAxis(src)) != 'Z':
        raise ValueError('Expected explicit metre/Z-up source')
    geometry = read_geometry(src)
    visual = geometry['/Asset/Visual/Mesh']
    if len(geometry) != 29 or sum(g['collision'] for g in geometry.values()) != 28:
        raise ValueError('Expected unchanged28-part thick-wall source')
    axis = np.array([float(width_mm) / 12.5, float(width_mm) / 12.5, 1.0])
    before = integrate_material(visual['body_points'], visual['faces'], MASS_KG)
    src.Flatten().Export(str(out))
    dst = Usd.Stage.Open(str(out), Usd.Stage.LoadAll)
    for path, g in geometry.items():
        if g['normals_authored']:
            raise ValueError('Source gained authored normals; requires inverse transpose')
        points = (np.c_[g['body_points'] * axis, np.ones(len(g['points']))]
                  @ np.linalg.inv(g['matrix']))[:, :3]
        mesh = UsdGeom.Mesh(dst.GetPrimAtPath(path))
        mesh.GetPointsAttr().Set([Gf.Vec3f(*p) for p in points])
        mesh.GetExtentAttr().Set([Gf.Vec3f(*points.min(0)), Gf.Vec3f(*points.max(0))])
    v = read_geometry(dst)['/Asset/Visual/Mesh']
    after = integrate_material(v['body_points'], v['faces'], MASS_KG)
    Q = np.diag(axis) @ before['central_second_moment_m2'] @ np.diag(axis)
    affine_I = MASS_KG * (np.trace(Q) * np.eye(3) - Q)
    if np.abs(affine_I - after['inertia_body_kg_m2']).max() / np.abs(affine_I).max() > 2e-6:
        raise ValueError('Reintegrated and fixed-mass affine inertia disagree')
    mass = UsdPhysics.MassAPI(dst.GetDefaultPrim())
    mass.GetMassAttr().Set(MASS_KG)
    mass.GetCenterOfMassAttr().Set(Gf.Vec3f(*after['com_body_m']))
    mass.GetDiagonalInertiaAttr().Set(Gf.Vec3f(*after['principal_inertia_kg_m2']))
    q = after['principal_axes_quaternion_wxyz']
    mass.GetPrincipalAxesAttr().Set(Gf.Quatf(float(q[0]), Gf.Vec3f(*q[1:])))
    root = dst.GetDefaultPrim()
    root.SetCustomDataByKey('labsim_vessel_version', 'Size_v1/' + ident)
    root.SetCustomDataByKey('labsim_source_sha256', sha(SOURCE))
    root.SetCustomDataByKey('labsim_asset_id', ident)
    root.SetCustomDataByKey('labsim_geometry_change',
        f'XY={width_mm}/12.5,Z=1,bottomZ=0; all visual and28 collision input points')
    root.SetCustomDataByKey('labsim_mass_assumption',
        'fixed20g assumed; uniform visual material-volume distribution; density adjusted, not measured')
    dst.GetRootLayer().Save()
    dst = None
    reloaded = Usd.Stage.Open(str(out), Usd.Stage.LoadAll)
    actual = read_geometry(reloaded)
    attrs_ok, topology_ok, delta, zdelta = True, True, 0., 0.
    for path, g in geometry.items():
        h = actual[path]
        topology_ok &= np.array_equal(g['faces'], h['faces'])
        delta = max(delta, float(np.abs(h['body_points'] - g['body_points'] * axis).max()))
        zdelta = max(zdelta, float(np.abs(h['body_points'][:, 2] - g['body_points'][:, 2]).max()))
        aa, bb = _attributes(src.GetPrimAtPath(path)), _attributes(reloaded.GetPrimAtPath(path))
        attrs_ok &= all(aa[k] == bb[k] for k in aa if k not in {'points', 'extent'})
    collision = []
    for path, g in actual.items():
        if not g['collision']:
            continue
        p = reloaded.GetPrimAtPath(path)
        collision.append({'prim': path, 'approximation': g['approximation'],
            'collision_enabled': UsdPhysics.CollisionAPI(p).GetCollisionEnabledAttr().Get(),
            'contact_offset_m': p.GetAttribute('physxCollision:contactOffset').Get(),
            'rest_offset_m': p.GetAttribute('physxCollision:restOffset').Get(),
            'bounds_m': [g['body_points'].min(0), g['body_points'].max(0)]})
    material = [{'prim': str(p.GetPath()), 'attributes': _attributes(p)}
                for p in reloaded.Traverse() if 'Material' in str(p.GetPath())]
    checks = {'source_sha_unchanged': sha(SOURCE) == EXPECTED_SOURCE_SHA,
        'mesh_topology_unchanged': bool(topology_ok),
        'all_other_mesh_attributes_unchanged': bool(attrs_ok),
        'same_XY_affine_every_mesh': delta < 1e-8,
        'height_and_bottom_Z_unchanged': zdelta < 1e-14,
        'collision_part_count_28': len(collision) == 28,
        'standalone_no_external_layers': len(reloaded.GetUsedLayers()) == 2,
        'mass_reloaded_20g': abs(usd_mass_snapshot(reloaded)['mass_kg'] - MASS_KG) < 1e-8}
    if not all(checks.values()):
        raise ValueError('Asset reload checks failed: ' + str(checks))
    record = {'schema': 'labsim.Size_v1.asset.v1', 'version': 'Size_v1',
        'asset_id': ident, 'asset_path': rel(out), 'asset_sha256': sha(out),
        'source': {'path': rel(SOURCE), 'sha256': sha(SOURCE), 'nominal_outer_xy_mm': [12.5, 12.5]},
        'builder': {'path': rel(__file__), 'sha256': sha(__file__)},
        'derivation_method': 'Same affine body-coordinate map applied to visual and28 thick-wall collision meshes; standalone flattened layer; no local reshaping',
        'axis_scale': axis, 'nominal_outer_xy_mm': [float(width_mm)] * 2,
        'actual_outer_dimensions_mm': np.ptp(v['body_points'], axis=0) * 1000,
        'actual_body_bounds_m': [v['body_points'].min(0), v['body_points'].max(0)],
        'height_nominal_mm': 67.5,
        'inner_cavity_sections': cavity_measurements(reloaded),
        'datum': 'sourceXYcenter; closedbottomZ=0; mouth+Z; metreZ-up/defaultPrimAsset',
        'default_prim': str(reloaded.GetDefaultPrim().GetPath()),
        'meters_per_unit': UsdGeom.GetStageMetersPerUnit(reloaded),
        'up_axis': str(UsdGeom.GetStageUpAxis(reloaded)), 'mass_kg': MASS_KG,
        'mass_source': 'retained20g engineering assumption, not measured',
        'mass_distribution_assumption': 'Uniform closed visual material volume, cavity excluded; fixed total mass means numerical density varies; no constant-density claim',
        'mass_properties': after, 'reloaded_mass_properties': usd_mass_snapshot(reloaded),
        'collision_input_shapes': collision, 'material_attributes': material,
        'checks': checks, 'affine_max_vertex_storage_error_m': delta,
        'physics_validation': None, 'complete_task_result': None, 'real_calibrated': False,
        'limitations': ['Actual PhysX cooked representation/fallback not read offline',
                        'Size hypothesis; not an inferred real specimen dimension']}
    supplement_metadata(record, reloaded)
    write(evidence, record)
    return record


def build(widths, directory=DIRECTORY):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / 'registry.json'
    old = json.loads(path.read_text()) if path.exists() else {
        'schema': SCHEMA, 'version': 'Size_v1', 'assets': {}}
    for width in widths:
        record = build_one(width, directory)
        old['assets'][record['asset_id']] = record
        write(path, old)
    return old


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--widths-mm', nargs='+', type=float, required=True)
    p.add_argument('--directory', type=Path, default=DIRECTORY)
    a = p.parse_args()
    r = build(a.widths_mm, a.directory)
    print(json.dumps({'registered_assets': len(r['assets']), 'registry': str(a.directory / 'registry.json')}))
