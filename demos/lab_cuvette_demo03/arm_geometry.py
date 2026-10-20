"""Whole-Franka collision INPUT geometry for offline pose/FK diagnostics.

This module loads source rigid-link frames and mesh coordinates without starting
Isaac, reading live state, modifying a stage, or computing IK. Callers provide
actual body poses or independently computed FK. Source metersPerUnit=.01 is not
multiplied again: existing metre-World references already use authored0.01 mesh
scales and metre-sized link transforms.

PhysX cooked buffers exist in the robot asset but are not decoded here. Declared
convexHull colliders can be rebuilt from input points; this is still an authored
approximation reconstruction, never a claim of exact cooked-shape readback.
"""
from __future__ import annotations

import argparse
from functools import lru_cache
from importlib.util import find_spec
from pathlib import Path
import numpy as np
from scipy.spatial import ConvexHull
from scipy.spatial.transform import Rotation
from pxr import Usd, UsdGeom, UsdPhysics

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ROBOT = ROOT/'assets/robots/Franka.usd'


def capabilities():
    """Report available local narrow-phase backends; do not install anything."""
    return {'python_fcl_available': find_spec('fcl') is not None,
            'rtree_available': find_spec('rtree') is not None,
            'triangle_SAT_available': True,
            'physx_cooked_geometry_readback': False}


def _triangles(mesh):
    indices = np.asarray(mesh.GetFaceVertexIndicesAttr().Get(), int)
    faces, offset = [], 0
    for count in mesh.GetFaceVertexCountsAttr().Get():
        ids = indices[offset:offset+count]
        faces.extend(ids[[0, i, i+1]] for i in range(1, count-1))
        offset += count
    return np.asarray(faces, int).reshape(-1, 3)


@lru_cache(maxsize=4)
def load_collision_model(robot_usd=DEFAULT_ROBOT):
    """Return every native rigid body, including empty panda_link8.

    model['links'][name]['meshes'] have vertices_local_m and faces in each own
    body frame. Empty bodies are explicit, not silently omitted. Returned arrays
    are cached; callers should not mutate them.
    """
    path = Path(robot_usd).resolve()
    stage = Usd.Stage.Open(str(path), Usd.Stage.LoadAll)
    cache = UsdGeom.XformCache()
    bodies = [p for p in stage.Traverse() if p.HasAPI(UsdPhysics.RigidBodyAPI)]
    colliders = [p for p in Usd.PrimRange.Stage(stage, Usd.TraverseInstanceProxies())
                 if p.HasAPI(UsdPhysics.CollisionAPI)]
    result = {}
    for body in bodies:
        name = body.GetName()
        if name in result:
            raise ValueError(f'Nonunique body name {name}; use a disambiguated asset')
        inverse = np.linalg.inv(np.asarray(cache.GetLocalToWorldTransform(body)))
        meshes = []
        for collider in colliders:
            # Match the nearest rigid ancestor if another rigid body is nested.
            owners = [b for b in bodies if str(collider.GetPath()).startswith(str(b.GetPath())+'/')]
            if not owners or max(owners, key=lambda p: len(str(p.GetPath()))) != body:
                continue
            if not collider.IsA(UsdGeom.Mesh):
                raise NotImplementedError(f'Unhandled real collider primitive {collider.GetPath()}:{collider.GetTypeName()}')
            mesh = UsdGeom.Mesh(collider)
            points = np.asarray(mesh.GetPointsAttr().Get(), float)
            matrix = np.asarray(cache.GetLocalToWorldTransform(collider)) @ inverse
            points = (np.c_[points, np.ones(len(points))] @ matrix)[:, :3]
            approximate = UsdPhysics.MeshCollisionAPI(collider).GetApproximationAttr().Get()
            options = {a.GetName(): str(a.Get()) for a in collider.GetAttributes()
                       if a.GetName().startswith(('physxConvexHullCollision:', 'physxConvexDecompositionCollision:'))}
            meshes.append({'path': str(collider.GetPath()), 'vertices_local_m': points,
                           'faces': _triangles(mesh), 'approximation_authored': approximate,
                           'convex_hull_faces_input': ConvexHull(points).simplices,
                           'cooking_options_authored': options,
                           'cooked_attributes_present': any(a.GetName().startswith('physxCookedData:')
                                                            and a.HasAuthoredValueOpinion()
                                                            for a in collider.GetAttributes())})
        result[name] = {'body_path': str(body.GetPath()), 'meshes': meshes,
                        'has_collision_geometry': bool(meshes),
                        'source_body_world_row_matrix': np.asarray(cache.GetLocalToWorldTransform(body))}
    required = {f'panda_link{i}' for i in range(8)} | {'panda_hand', 'panda_leftfinger', 'panda_rightfinger'}
    missing = required-set(result)
    if missing:
        raise ValueError(f'Required robot bodies missing: {sorted(missing)}')
    return {'robot_usd': str(path), 'source_meters_per_unit': float(UsdGeom.GetStageMetersPerUnit(stage)),
            'units_policy': 'Numeric local coordinates as referenced into existing metre World; authored mesh scale included once, no extra source metadata unit multiplication.',
            'links': result, 'required_pose_names': [n for n, r in result.items() if r['has_collision_geometry']],
            'empty_body_names': [n for n, r in result.items() if not r['has_collision_geometry']],
            'capabilities': capabilities(),
            'limitations': ['Collision input and reconstructed input hulls, not actual PhysX cooked shape readback.',
                            'External FK/body poses and joint values are supplied by caller; no source rest-pose assumption during motion.',
                            'Robot collision/material/drive parameters are unchanged by this module.']}


def collision_local_points(model=None):
    """Each collision-bearing body's own-frame vertices, covering whole arm."""
    model = load_collision_model() if model is None else model
    return {name: np.concatenate([m['vertices_local_m'] for m in body['meshes']])
            for name, body in model['links'].items() if body['meshes']}


def _pose(value, quaternion_order):
    if isinstance(value, dict):
        position = value.get('position', value.get('world_position'))
        quaternion = value.get('quaternion', value.get('world_quaternion'))
    else:
        position, quaternion = value
    p, q = np.asarray(position, float).reshape(3), np.asarray(quaternion, float).reshape(4)
    if not np.isfinite(p).all() or not np.isfinite(q).all() or np.linalg.norm(q) < 1e-12:
        raise ValueError('Invalid/nonfinite body pose')
    if quaternion_order == 'wxyz':
        q = q[[1, 2, 3, 0]]
    elif quaternion_order != 'xyzw':
        raise ValueError('Specify quaternion_order wxyz or xyzw explicitly')
    return p, Rotation.from_quat(q).as_matrix()


def posed_meshes(model, poses, representation='declared', quaternion_order='wxyz', strict=True):
    """Produce all link meshes at external world poses.

    poses[name] = (position3, quaternion4), or a dict with position/quaternion.
    Declared mode rebuilds convexHull input; unavailable convexDecomposition uses
    original input triangles and labels that limitation. input mode preserves all
    source triangles; convex_hull mode uses a conservative whole-input hull even
    for fingers and labels that choice. Missing poses raise by default.
    """
    if representation not in {'input', 'declared', 'convex_hull'}:
        raise ValueError(representation)
    missing = set(model['required_pose_names'])-set(poses)
    if strict and missing:
        raise KeyError(f'Missing actual/FK body poses: {sorted(missing)}')
    result = {}
    for name in model['required_pose_names']:
        if name not in poses:
            continue
        position, R = _pose(poses[name], quaternion_order)
        body_meshes = []
        for mesh in model['links'][name]['meshes']:
            vertices, faces = mesh['vertices_local_m'], mesh['faces']
            use_hull = representation == 'convex_hull' or (representation == 'declared' and mesh['approximation_authored'] == 'convexHull')
            if use_hull:
                # Hull face indices refer to the complete input-point array.
                faces = mesh['convex_hull_faces_input']
            method = 'reconstructed_input_convex_hull' if use_hull else 'original_input_triangles'
            note = None
            if representation == 'declared' and mesh['approximation_authored'] == 'convexDecomposition':
                note = 'Actual convex decomposition unavailable; original triangles shown, not cooked contact representation.'
            if representation == 'convex_hull' and mesh['approximation_authored'] != 'convexHull':
                note = 'Conservative whole-input hull may fill concavities; potential false positives.'
            world = vertices @ R.T+position
            body_meshes.append({'path': mesh['path'], 'vertices_world_m': world, 'faces': faces,
                                'representation': method, 'approximation_authored': mesh['approximation_authored'],
                                'cooked_geometry_readback': False, 'warning': note,
                                'lo': world.min(0), 'hi': world.max(0)})
        result[name] = body_meshes
    return result


def world_aabbs(model, poses, quaternion_order='wxyz', strict=True):
    meshes = posed_meshes(model, poses, representation='input',
                          quaternion_order=quaternion_order, strict=strict)
    result = {}
    for name, records in meshes.items():
        points = np.concatenate([m['vertices_world_m'] for m in records])
        lo, hi = points.min(0), points.max(0)
        result[name] = {'lo': lo, 'hi': hi, 'center': (lo+hi)/2, 'size': hi-lo}
    return result


def _triangle_sat(a, b, tolerance_m):
    """Exact separating-axis surface overlap candidates, including coplanarity.

    a=(3,3), b=(N,3,3). Tolerance is normalized to metre distances. Tangency
    within tolerance counts as contact, not a measured penetration depth.
    """
    if not len(b):
        return np.zeros(0, bool)
    ea = np.roll(a, -1, axis=0)-a
    eb = np.roll(b, -1, axis=1)-b
    na = np.cross(ea[0], ea[1])
    nb = np.cross(eb[:, 0], eb[:, 1])
    axes = [np.tile(na, (len(b), 1)), nb]
    axes.extend(np.cross(np.tile(x, (len(b), 1)), eb[:, j]) for x in ea for j in range(3))
    # In-plane edge normals close the coplanar-triangle SAT case.
    axes.extend(np.tile(np.cross(na, edge), (len(b), 1)) for edge in ea)
    axes.extend(np.cross(nb, eb[:, j]) for j in range(3))
    overlap = np.ones(len(b), bool)
    origin = a[0]
    for axis in axes:
        norm = np.linalg.norm(axis, axis=1)
        valid = norm > 1e-14
        unit = np.divide(axis, norm[:, None], out=np.zeros_like(axis), where=valid[:, None])
        pa = (a-origin) @ unit.T
        pb = np.einsum('nvc,nc->nv', b-origin, unit)
        separated = (pa.max(0) < pb.min(1)-tolerance_m) | (pb.max(1) < pa.min(0)-tolerance_m)
        overlap &= ~(valid & separated)
    return overlap


class TriangleMeshIndex:
    """Static source triangle index with Rtree broad phase and triangle SAT.

    This removes AABB-only false positives. It checks surface crossing/contact;
    no closed-solid containment or numerical penetration depth is inferred.
    """
    def __init__(self, vertices, faces):
        import trimesh
        self.vertices = np.asarray(vertices, float)
        self.faces = np.asarray(faces, int).reshape(-1, 3)
        if not len(self.faces):
            raise ValueError('Static triangle index requires at least one face')
        self.triangles = self.vertices[self.faces]
        self.bounds = np.c_[self.triangles.min(1), self.triangles.max(1)]
        self.lo, self.hi = self.triangles.min((0, 1)), self.triangles.max((0, 1))
        self.tree = trimesh.util.bounds_tree(self.bounds)

    def intersections(self, moving_vertices, moving_faces, tolerance_m=1e-8, max_witnesses=16):
        moving = np.asarray(moving_vertices, float)[np.asarray(moving_faces, int)]
        witnesses, broad_pairs = [], 0
        if not len(moving) or np.any(moving.max((0, 1)) < self.lo-tolerance_m) or np.any(moving.min((0, 1)) > self.hi+tolerance_m):
            return {'surface_contact_or_crossing': False, 'witnesses': [],
                    'broad_phase_pairs_examined': 0, 'truncated': False,
                    'tolerance_m': tolerance_m, 'containment_checked': False,
                    'method': 'Disjoint whole-mesh AABB broad phase'}
        for i, triangle in enumerate(moving):
            bounds = np.r_[triangle.min(0)-tolerance_m, triangle.max(0)+tolerance_m]
            ids = np.asarray(list(self.tree.intersection(bounds)), int)
            if not len(ids):
                continue
            broad_pairs += len(ids)
            chosen = ids[_triangle_sat(triangle, self.triangles[ids], tolerance_m)]
            for j in chosen:
                witnesses.append({'moving_triangle': int(i), 'static_triangle': int(j),
                                  'moving_triangle_world_m': triangle.tolist(),
                                  'static_triangle_world_m': self.triangles[j].tolist()})
                if len(witnesses) >= max_witnesses:
                    return {'surface_contact_or_crossing': True, 'witnesses': witnesses,
                            'broad_phase_pairs_examined': broad_pairs, 'truncated': True,
                            'tolerance_m': tolerance_m, 'containment_checked': False,
                            'method': 'Rtree triangle AABB broad phase + normalized triangle SAT including coplanar axes'}
        return {'surface_contact_or_crossing': bool(witnesses), 'witnesses': witnesses,
                'broad_phase_pairs_examined': broad_pairs, 'truncated': False,
                'tolerance_m': tolerance_m, 'containment_checked': False,
                'method': 'Rtree triangle AABB broad phase + normalized triangle SAT including coplanar axes'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--robot', type=Path, default=DEFAULT_ROBOT)
    args = parser.parse_args()
    model = load_collision_model(args.robot)
    print('WHOLE_ARM_INPUT', 'rigid_bodies', len(model['links']),
          'collision_bodies', len(model['required_pose_names']),
          'empty', model['empty_body_names'], 'capabilities', model['capabilities'])
    for name, points in collision_local_points(model).items():
        print(name, len(points), 'lo', points.min(0), 'hi', points.max(0))


if __name__ == '__main__':
    main()
