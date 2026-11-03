"""CPU-only rigid-frame arithmetic; no simulation steps or scene mutations."""
from __future__ import annotations

import itertools
import math

import numpy as np


def vector(value, size=3):
    try:
        result = np.asarray(value, dtype=float)
        return result if result.shape == (size,) and np.isfinite(result).all() else None
    except (TypeError, ValueError):
        return None


def number(value):
    try:
        return float(value) if value is not None and np.ndim(value) == 0 and math.isfinite(float(value)) else None
    except (TypeError, ValueError):
        return None


def rotation(quaternion):
    q = vector(quaternion, 4)
    if q is None or np.linalg.norm(q) < 1e-9:
        return None
    w, x, y, z = q / np.linalg.norm(q)
    return np.array([[1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],
                     [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],
                     [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]])


def rotation_distance(a, b):
    """Geodesic angle in radians, invariant to the quaternion sign."""
    ra, rb = rotation(a), rotation(b)
    if ra is None or rb is None:
        return None
    return matrix_angle(ra @ rb.T)


def matrix_angle(matrix):
    return float(np.arccos(np.clip((np.trace(matrix)-1.)/2., -1., 1.)))


def yaw_rotation(radians):
    c, s = math.cos(radians), math.sin(radians)
    return np.array([[c, -s, 0.], [s, c, 0.], [0., 0., 1.]])


def bounds_corners(bounds):
    try:
        b = np.asarray(bounds, dtype=float)
        if b.shape != (2, 3) or not np.isfinite(b).all() or np.any(b[1] < b[0]):
            return None
        return np.array(list(itertools.product(*zip(b[0], b[1]))))
    except (TypeError, ValueError):
        return None


def measured_geometry(row, geometry):
    """Prefer actual capture measurements; bounds fallback is conservative.

    AABB corners are a body envelope, not the material surface. They can only
    underestimate world minimum Z, so never falsely clear a tilted vessel.
    The selected original-seat void cannot be established by this envelope.
    """
    p = vector(row.get('object_position_m', row.get('position')))
    r = rotation(row.get('object_quaternion_wxyz', row.get('quaternion_wxyz')))
    floor = vector(geometry.get('target_loading_floor_world_m'))
    target_r = np.asarray(geometry.get('target_rotation_world'), float)
    if target_r.shape != (3, 3) or not np.isfinite(target_r).all():
        target_r = None
    result = dict(position=p, rotation=r, bottom=None, bottom_reference=None,
                  top_reference=None, lateral=None, tilt=None, yaw=None, depth=None,
                  preinsert_distance=None, tcp_distance=None, approach_distance=None,
                  approach_orientation=None, bottom_source=None)
    bottom = number(row.get('object_bottom_world_z_m', row.get('source_bottom_z_m')))
    if bottom is not None:
        result.update(bottom=bottom, bottom_source='PhysicsRecorder.actual_visual_vertices_min_world_Z')
    if p is None or r is None:
        return result
    local_bottom = vector(geometry.get('vessel_bottom_reference_body_m'))
    local_top = vector(geometry.get('vessel_top_reference_body_m'))
    if local_bottom is not None:
        result['bottom_reference'] = p + r @ local_bottom
    if local_top is not None:
        result['top_reference'] = p + r @ local_top
    if bottom is None:
        corners = bounds_corners(geometry.get('vessel_body_local_bounds_m'))
        if corners is not None:
            result.update(bottom=float((corners @ r.T + p)[:, 2].min()),
                          bottom_source='conservative_transformed_body_AABB_envelope')
    xy = vector(row.get('xy_error_target_m'), 2)
    if xy is None and floor is not None and target_r is not None:
        xy = ((p-floor) @ target_r)[:2]
    result['lateral'] = float(np.linalg.norm(xy)) if xy is not None else None
    tilt = number(row.get('tilt_deg'))
    relative = target_r.T @ r if target_r is not None else None
    result['tilt'] = math.radians(tilt) if tilt is not None else float(np.arccos(np.clip(relative[2, 2], -1, 1))) if relative is not None else None
    yaw = number(row.get('yaw_error_deg'))
    measured_yaw = math.radians(yaw) if yaw is not None else math.atan2(relative[1, 0], relative[0, 0]) if relative is not None else None
    symmetry = int(geometry.get('allowed_yaw_symmetry_order', 1))
    period = 2*math.pi/max(1, symmetry)
    result['yaw'] = float((measured_yaw+period/2) % period-period/2) if measured_yaw is not None else None
    depth = number(row.get('depth_m'))
    if depth is None and floor is not None and target_r is not None and result['bottom_reference'] is not None and geometry.get('target_depth_m') is not None:
        # Datum-depth fallback is explicitly distinct from capture's envelope
        # depth; only separate containment evidence can qualify insertion.
        depth = float(geometry['target_depth_m'] - np.dot(result['bottom_reference']-floor, target_r[:, 2]))
    result['depth'] = depth
    if floor is not None and target_r is not None and result['bottom_reference'] is not None and geometry.get('target_depth_m') is not None:
        preinsert = floor + target_r[:, 2]*(float(geometry['target_depth_m'])+float(geometry['preinsert_above_rim_m']))
        result['preinsert_distance'] = float(np.linalg.norm(result['bottom_reference']-preinsert))
    tcp = vector(row.get('actual_tcp_position_m'))
    if tcp is not None:
        result['tcp_distance'] = float(np.linalg.norm(tcp-p))
        anchor = vector(geometry.get('grasp_reference_body_m'))
        if anchor is not None:
            result['approach_distance'] = float(np.linalg.norm(tcp-(p+r @ anchor)))
    tcp_r = rotation(row.get('actual_tcp_quaternion_wxyz'))
    goal = geometry.get('grasp_tcp_rotation_world')
    if tcp_r is not None and goal is not None:
        result['approach_orientation'] = matrix_angle(tcp_r @ np.asarray(goal, float).T)
    return result
