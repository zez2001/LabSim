"""Original A-seat geometry screening for registered XY-only cuvette variants.

Positive full-path results use a conservative continuous vertical sweep: every
actual original seat triangle above its floor is projected, including degenerate
vertical-wall line projections, and convolved with the cup's actual outer XY
silhouette. This checks surfaces rather than nearest vertices or centres. A
negative conservative result is inconclusive, not proof of impossible passage.
The entrance gate separately uses the actual closed bottom material section and
the exact polygonal XY configuration space at the original tab-bearing slice.
Neither gate is physical loading success or a cooked PhysX shape readback.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from demos.lab_cuvette_env_v1 import geometry_audit as previous

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = 'labsim.Size_v1.current_geometry.v1'
SEAT = 'candidate_far_hinge'


def binding(cfg, dependency_paths=None):
    cfg = previous.plain(cfg)
    old = previous.binding(cfg, dependency_paths)
    files = old['files']
    for p in Path(__file__).parent.glob('*.py'):
        files[previous.file_key(p)] = previous.sha(p)
    for p in (ROOT / 'assets/lab_cuvette_loading/Size_v1').glob('*.json'):
        # All variants remain traceable; changing family evidence invalidates
        # the audit rather than silently reusing an earlier search.
        files[previous.file_key(p)] = previous.sha(p)
    contract = dict(old['contract'])
    for key in ('asset_id', 'asset_registry', 'standard_scene', 'size_v1'):
        if key in cfg:
            contract[key] = cfg[key]
    contract['size_v1_target_offset'] = cfg.get('geometry', {}).get(
        'target_loading_offset_local_m', cfg.get('adapter', {}).get(
        'target_loading_offset_local_m', [.00065, .000001, 0]))
    body = {'schema': SCHEMA, 'files': files, 'contract': contract}
    return {**body, 'fingerprint': hashlib.sha256(previous.canonical(body)).hexdigest()}


def check_cached_binding(cfg, audit_path):
    p = Path(audit_path)
    if not p.is_file():
        return {'current': False, 'reason': 'missing_audit'}
    old = json.loads(p.read_text())
    if old.get('schema') != SCHEMA or 'binding' not in old:
        return {'current': False, 'reason': 'unbound_or_wrong_schema'}
    now = binding(cfg, old['binding']['files'])
    same = now['fingerprint'] == old['binding']['fingerprint']
    return {'current': same, 'reason': 'current' if same else 'binding_changed',
            'fingerprint': now['fingerprint'], 'previous_fingerprint': old['binding']['fingerprint']}


def ensure_current_audit(cfg, cache_directory, *, geometry_site=None):
    directory = Path(cache_directory)
    directory.mkdir(parents=True, exist_ok=True)
    for _ in range(3):
        bound = binding(cfg)
        folder = directory / bound['fingerprint']
        p = folder / 'geometry_audit.json'
        if p.exists() and check_cached_binding(cfg, p)['current']:
            result = json.loads(p.read_text())
        else:
            result = audit(cfg, folder, geometry_site=geometry_site, bound=bound)
        if check_cached_binding(cfg, p)['current']:
            previous.write(directory / 'latest.json', {'audit_relative_path': str(p.relative_to(directory)), 'fingerprint': bound['fingerprint']})
            return result
    raise RuntimeError('Geometry inputs changed during audit; freeze inputs and retry')


def load_geometry(cfg, site=None):
    import numpy as np
    import trimesh
    from pxr import UsdGeom
    from demos.lab_cuvette_external.geometry import mesh_records
    shp = previous._load_shapely(site or os.environ.get('LABSIM_GEOMETRY_SITE'))
    paths = previous.paths_for_config(cfg)
    stage, rows = mesh_records(paths['instrument'].name, paths['instrument'].parent)
    unit = UsdGeom.GetStageMetersPerUnit(stage)
    source = next(r for r in rows if r['path'].endswith('/Collision/SourceMesh3'))
    frame = np.asarray(UsdGeom.XformCache().GetLocalToWorldTransform(
        stage.GetPrimAtPath('/Asset/Frames/' + SEAT)))
    seat = trimesh.Trimesh(source['points'] * unit, source['faces'], process=True)
    seat.vertices = (seat.vertices - frame[3, :3] * unit) @ np.linalg.inv(frame[:3, :3])
    vst, vrows = mesh_records(paths['vessel'].name, paths['vessel'].parent)
    vu = UsdGeom.GetStageMetersPerUnit(vst)
    vr = next(r for r in vrows if '/Visual/' in r['path'])
    cup = trimesh.Trimesh(vr['points'] * vu, vr['faces'], process=True)
    hits, _, _ = seat.ray.intersects_location([[0, 0, .030]], [[0, 0, -1]], multiple_hits=True)
    floor = float(hits[:, 2].max())
    return {'np': np, 'trimesh': trimesh, 'shp': shp, 'seat': seat,
        'cup': cup, 'floor': floor, 'rim': float(seat.bounds[1, 2]),
        'seat_source_prim': source['path'], 'seat_frame_row_matrix': frame,
        'instrument_path': paths['instrument'], 'vessel_path': paths['vessel']}


def _clip_above(points, height):
    import numpy as np
    out = []
    for a, b in zip(points, np.roll(points, -1, axis=0)):
        ia, ib = a[2] >= height, b[2] >= height
        if ia:
            out.append(a)
        if ia != ib:
            out.append(a + (b - a) * ((height - a[2]) / (b[2] - a[2])))
    return np.asarray(out)


def projected_obstacles(g, floor_clip_epsilon_m=1e-7):
    np, shp = g['np'], g['shp']
    pieces, indices = [], []
    for index, t in enumerate(g['seat'].triangles):
        p = _clip_above(t, g['floor'] + floor_clip_epsilon_m)
        if len(p):
            pieces.append(shp['MultiPoint'](p[:, :2] * 1000).convex_hull)
            indices.append(index)
    return pieces, indices


def section_polygon(g, mesh, z, *, material=False):
    np, shp = g['np'], g['shp']
    seg = g['trimesh'].intersections.mesh_plane(mesh, [0, 0, 1], [0, 0, z])
    lines = [shp['LineString'](np.round(s[:, :2] * 1000, 8)) for s in seg
             if np.linalg.norm(s[0] - s[1]) > 1e-12]
    pp = list(shp['polygonize'](shp['unary_union'](lines)))
    if material:
        picked = []
        for p in pp:
            q = p.representative_point()
            if mesh.contains([[q.x / 1000, q.y / 1000, z]])[0]:
                picked.append(p)
        return shp['unary_union'](picked)
    return next(p for p in pp if p.contains(shp['Point'](0, 0)))


def _vertices(geom):
    import numpy as np
    return np.asarray(geom.exterior.coords)[:-1] if geom.geom_type == 'Polygon' else np.asarray(geom.coords)


def cspace(g, obstacles, kernel, domain):
    np, shp = g['np'], g['shp']
    kp = -_vertices(kernel)
    forbidden = [shp['MultiPoint']((_vertices(o)[:, None, :] + kp[None, :, :]).reshape(-1, 2)).convex_hull for o in obstacles]
    blocked = shp['unary_union'](forbidden)
    return domain.difference(blocked), blocked


def evaluate(g, *, yaw_deg=0, offset_mm=None, want_support=True):
    np, shp = g['np'], g['shp']
    cup = g['cup']
    silhouette = shp['MultiPoint'](cup.vertices[:, :2] * 1000).convex_hull
    silhouette = shp['rotate'](silhouette, yaw_deg, origin=(0, 0))
    bottom = section_polygon(g, cup, .001, material=True)
    bottom = shp['rotate'](bottom, yaw_deg, origin=(0, 0))
    bottom_convex_error = bottom.symmetric_difference(bottom.convex_hull).area
    if bottom_convex_error > 1e-8:
        raise ValueError('Closed bottom probe unexpectedly nonconvex; use material triangulation instead of convex convolution')
    aperture = section_polygon(g, g['seat'], g['rim'] - .0005)
    big = shp['box'](-12, -12, 12, 12)
    entrance_obstacles = list(shp['constrain'](big.difference(aperture)).geoms) if 'constrain' in shp else list(shp['constrained_delaunay_triangles'](big.difference(aperture)).geoms)
    entrance_residual = shp['unary_union'](entrance_obstacles).symmetric_difference(big.difference(aperture)).area
    if entrance_residual > 1e-8:
        raise ValueError('Entrance obstacle triangulation changed material region')
    aminx, aminy, amaxx, amaxy = aperture.bounds
    bminx, bminy, bmaxx, bmaxy = bottom.bounds
    domain = shp['box'](aminx - bminx, aminy - bminy, amaxx - bmaxx, amaxy - bmaxy)
    entry_free, _ = cspace(g, entrance_obstacles, bottom, domain)
    pieces, indices = projected_obstacles(g)
    kminx, kminy, kmaxx, kmaxy = silhouette.bounds
    # Bounded translation search is the same for every size and yaw: all XY
    # translations whose silhouette fits in the original centre-channel bbox.
    full_domain = shp['box'](aminx - kminx, -6.3 - kminy, amaxx - kmaxx, 6.3 - kmaxy)
    full_free, blocked = cspace(g, pieces, silhouette, full_domain)
    usable = not full_free.is_empty and full_free.area > 1e-12
    best = None
    if usable:
        from shapely.ops import polylabel
        polys = list(full_free.geoms) if full_free.geom_type == 'MultiPolygon' else [full_free]
        candidates = [polylabel(p, tolerance=.0001) for p in polys if p.geom_type == 'Polygon' and p.area > 1e-12]
        if candidates:
            best = max(candidates, key=lambda p: p.distance(blocked))
    if offset_mm is None:
        point = best or full_domain.centroid
    else:
        point = shp['Point'](*offset_mm)
    from shapely.affinity import translate
    placed = translate(silhouette, xoff=point.x, yoff=point.y)
    distances = [placed.distance(p) for p in pieces]
    worst = int(np.argmin(distances))
    selected_clear = float(min(distances))
    full_positive = full_free.contains(point) and selected_clear > 1e-8
    support = None
    if want_support and full_positive:
        # Use actual lowest coplanar triangles, rather than ray-parity at a
        # submicrometre slice where a point-in-volume tolerance is ill-conditioned.
        z0 = cup.bounds[0, 2]
        flat = cup.triangles[np.max(np.abs(cup.triangles[:, :, 2] - z0), axis=1) < 1e-9]
        if not len(flat):
            raise ValueError('No actual flat lowest-bottom triangles for support test')
        low = shp['unary_union']([shp['MultiPoint'](t[:, :2] * 1000).convex_hull for t in flat])
        low = translate(shp['rotate'](low, yaw_deg, origin=(0, 0)), xoff=point.x, yoff=point.y)
        xs = np.linspace(low.bounds[0], low.bounds[2], 15)
        ys = np.linspace(low.bounds[1], low.bounds[3], 15)
        samples = np.array([(x, y) for x in xs for y in ys if low.contains(shp['Point'](x, y))])
        origins = np.c_[samples / 1000, np.full(len(samples), g['floor'] + .0005)]
        hits, rays, _ = g['seat'].ray.intersects_location(origins, np.tile([0, 0, -1.], (len(origins), 1)), multiple_hits=True)
        maxima = {int(i): float(hits[rays == i, 2].max()) for i in np.unique(rays)}
        floor_hits = np.array([samples[i] for i, z in maxima.items() if abs(z - g['floor']) < 1e-6])
        polygon = shp['MultiPoint'](floor_hits).convex_hull if len(floor_hits) else shp['Point'](0, 0).buffer(0)
        a = np.radians(yaw_deg)
        rot = np.array([[np.cos(a), -np.sin(a)], [np.sin(a), np.cos(a)]])
        actual_com_xy = cup.center_mass[:2] @ rot.T * 1000 + [point.x, point.y]
        com = shp['Point'](*actual_com_xy)
        support = {'sample_count': len(samples), 'floor_hit_count': len(floor_hits),
            'floor_hit_fraction': len(floor_hits) / len(samples),
            'sampled_support_convex_hull_area_mm2': polygon.area,
            'COM_XY_inside_sampled_support_hull': polygon.contains(com),
            'COM_to_sampled_support_hull_boundary_mm': com.distance(polygon.boundary) if not polygon.is_empty else None,
            'actual_uniform_visual_material_COM_XY_mm': actual_com_xy,
            'support_height_mm': g['floor'] * 1000,
            'scope': '15x15 actual low-bottom-section interior ray samples; static geometric support candidate, not dynamic stability test'}
    result = {'yaw_deg': yaw_deg, 'entry_positive_clearance_XY_domain_present': bool(not entry_free.is_empty and entry_free.area > 1e-12),
        'entry_free_area_mm2': entry_free.area, 'entry_translation_bounds_mm': list(domain.bounds),
        'entry_triangulation_area_residual_mm2': entrance_residual,
        'actual_closed_bottom_convexity_area_residual_mm2': bottom_convex_error,
        'conservative_full_path_positive_XY_domain_present': bool(usable),
        'conservative_full_path_free_area_mm2': full_free.area,
        'best_offset_mm': [best.x, best.y] if best else None,
        'best_sweep_clearance_mm': best.distance(blocked) if best else None,
        'evaluated_offset_mm': [point.x, point.y],
        'evaluated_fixed_XY_full_path_valid': bool(full_positive),
        'evaluated_sweep_clearance_mm': selected_clear,
        'nearest_seat_processed_triangle_index': indices[worst],
        'nearest_seat_triangle_vertices_mm': g['seat'].triangles[indices[worst]] * 1000,
        'support': support, 'physics_validation': None, 'full_task_success': None}
    return result, {'aperture': aperture, 'silhouette': placed,
        'entry_free': entry_free, 'full_free': full_free, 'obstacles': shp['unary_union'](pieces)}


def audit(cfg, output, *, geometry_site=None, bound=None):
    cfg = previous.plain(cfg)
    if cfg.get('adapter', {}).get('selected_target_seat_id', SEAT) != SEAT:
        raise ValueError('Size_v1 freezes original A seat; switching toB is forbidden')
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    g = load_geometry(cfg, geometry_site)
    offset = cfg.get('geometry', {}).get('target_loading_offset_local_m',
        cfg.get('adapter', {}).get('target_loading_offset_local_m', [.00065, .000001, 0]))
    yaw = cfg.get('geometry', {}).get('target_vessel_yaw_local_deg', 0)
    r, shapes = evaluate(g, yaw_deg=yaw, offset_mm=[float(x) * 1000 for x in offset[:2]])
    support = r['support'] or {}
    valid = bool(r['evaluated_fixed_XY_full_path_valid'] and support.get('COM_XY_inside_sampled_support_hull'))
    bound = bound or binding(cfg)
    result = {'schema': SCHEMA, 'binding': bound, 'selected_target_seat_id': SEAT,
        'geometry_valid': valid, 'vessel_path_geometry_valid': valid,
        'whole_hand_path_valid': None, 'physics_executed': False,
        'source_modified': False, 'real_calibrated': False,
        'reason': 'REGISTERED_VARIANT_ORIGINAL_A_CONTINUOUS_VERTICAL_INPUT_PATH_CLEAR' if valid else 'ORIGINAL_A_PATH_NOT_CERTIFIED',
        'asset_id': cfg.get('asset_id'), 'actual_outer_dimensions_mm': g['cup'].extents * 1000,
        'original_instrument': {'path': previous.file_key(g['instrument_path']), 'sha256': previous.sha(g['instrument_path']), 'selected_collision_prim': g['seat_source_prim'], 'seat_frame_row_matrix': g['seat_frame_row_matrix']},
        'target_loading_offset_local_m': offset, 'target_vessel_yaw_local_deg': yaw,
        'candidate_support_height_m': g['floor'], 'candidate_insertion_depth_m': g['rim'] - g['floor'],
        'configured_requested_depth_m': float(cfg.get('geometry', {}).get('target_depth_m', g['rim'] - g['floor'])),
        'evaluation': r, 'method': {'entrance': 'Actual material slice at cupZ1mm and original A aperture at seatZ28.5mm; exact triangle-pair polygonal Minkowski union over all boundedXY translations',
            'full_path': 'Conservative outer silhouette swept vertically past every actual original triangle clipped above original floor+0.1um; projected triangles and vertical lines retained; full polygonalXY configuration space',
            'floor_clip_epsilon_m': 1e-7, 'support_plane': 'Original centre-ray floor; bottom contact excluded from positive sidewall clearance test, not removed from physics',
            'cooked_PhysX_representation_verified': False,
            'limitations': ['Positive full-path gate is conservative for actual authored cup and original triangle input surfaces; not cooked collision verification', 'Negative conservative sweep result is inconclusive, not a global impossibility certificate', 'Four upright yaw choices in family search; arbitrary6DoF inclined routes not searched', 'Support ray sample is a static geometric candidate, not measured bearing depth or post-release stability']},
        'wall_clock_s': time.monotonic() - started}
    previous.write(output / 'geometry_audit.json', result)
    _plot(output / 'selected_variant_path.png', shapes, r)
    return result


def _plot(path, shapes, result):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(11, 5), constrained_layout=True)
    for ax in axes:
        ax.set_aspect('equal'); ax.set_xlabel('Original A localX / mm'); ax.set_ylabel('Original A localY / mm'); ax.grid(alpha=.2)
    for geom, colour in ((shapes['aperture'], 'black'), (shapes['silhouette'], '#d54a1e')):
        axes[0].plot(*geom.exterior.xy, color=colour)
    axes[0].set_title('Original entrance and placed actual outer silhouette')
    free = shapes['full_free']
    polys = list(free.geoms) if free.geom_type == 'MultiPolygon' else [free]
    for p in polys:
        if p.geom_type == 'Polygon' and not p.is_empty:
            axes[1].fill(*p.exterior.xy, color='#61ad78', alpha=.4)
    axes[1].scatter(*result['evaluated_offset_mm'], c='red', label='evaluated fixedXY')
    axes[1].set_title('Continuous vertical sweep: allXY feasible domain')
    axes[1].legend(); fig.savefig(path, dpi=160); plt.close(fig)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config', required=True)
    p.add_argument('--output', required=True)
    p.add_argument('--ensure', action='store_true')
    p.add_argument('--geometry-site')
    a = p.parse_args()
    from omegaconf import OmegaConf
    cfg = OmegaConf.to_container(OmegaConf.load(a.config), resolve=True)
    r = (ensure_current_audit if a.ensure else audit)(cfg, a.output, geometry_site=a.geometry_site)
    print(json.dumps({'geometry_valid': r['geometry_valid'], 'fingerprint': r['binding']['fingerprint'], 'asset_id': r['asset_id']}))
