"""Measured-pose checks of vessel material against the unchanged seat input mesh.

All geometric queries use millimetres to avoid trimesh's metre-scale numerical
tolerances. Distances are point-to-triangle distances, never nearest vertices.
This module does not read cooked PhysX geometry. A finite surface sample and
edge/triangle crossing test is an observed-error check, not a global error bound.
The original seat has open boundary edges; its signed-distance classification is
therefore explicitly qualified rather than advertised as an exact solid oracle.
"""
from __future__ import annotations

import hashlib
import time

import numpy as np
import trimesh
from scipy.spatial.transform import Rotation


def _rotation(quaternion_wxyz):
    q = np.asarray(quaternion_wxyz, dtype=float)
    if q.shape != (4,) or not np.isfinite(q).all() or np.linalg.norm(q) < .5:
        raise ValueError('Expected finite vessel quaternion wxyz')
    return Rotation.from_quat(np.r_[q[1:], q[0]])


def _boundary_count(mesh):
    _, counts = np.unique(np.sort(mesh.edges, axis=1), axis=0, return_counts=True)
    return int(np.count_nonzero(counts == 1))


def _samples(mesh, maximum_face_samples=256):
    # Keep every actual vertex. Additional centroid samples are chosen by stable
    # face-index stratification, rather than an unrecorded stochastic sample.
    # The complete edge set is independently checked for triangle crossings.
    count=min(int(maximum_face_samples),len(mesh.faces))
    ids=np.linspace(0,len(mesh.faces)-1,count,dtype=int)
    return np.vstack((mesh.vertices,mesh.triangles_center[ids]))


def _in_bounds(points, bounds, padding=0.):
    return np.all((points >= bounds[0]-padding) & (points <= bounds[1]+padding), axis=1)


def _segment_crossings(origins, ends, mesh, *, endpoint_epsilon_mm=1e-5):
    if not len(origins):
        return dict(count=0, point_mm=None, tested_segments=0)
    delta = ends-origins
    lengths = np.linalg.norm(delta, axis=1)
    valid = lengths > 2*endpoint_epsilon_mm
    origins, delta, lengths = origins[valid], delta[valid], lengths[valid]
    if not len(origins):
        return dict(count=0, point_mm=None, tested_segments=0)
    # Query *finite segment* AABBs. trimesh's infinite-ray broadphase made long
    # vessel edges query most of the instrument even when only29mm is relevant.
    pairs=[]
    for i,(origin,end) in enumerate(zip(origins,origins+delta)):
        bounds=np.r_[np.minimum(origin,end)-endpoint_epsilon_mm,
                     np.maximum(origin,end)+endpoint_epsilon_mm]
        pairs.extend((i,j) for j in mesh.triangles_tree.intersection(bounds))
    locations=np.empty((0,3))
    if pairs:
        pairs=np.asarray(pairs,int)
        ray_ids,triangle_ids=pairs[:,0],pairs[:,1]
        triangles=mesh.triangles[triangle_ids]
        a=triangles[:,1]-triangles[:,0];b=triangles[:,2]-triangles[:,0]
        direction=delta[ray_ids]
        h=np.cross(direction,b);det=np.einsum('ij,ij->i',a,h)
        nonparallel=np.abs(det)>1e-12
        inverse=np.divide(1.,det,out=np.zeros_like(det),where=nonparallel)
        s=origins[ray_ids]-triangles[:,0]
        u=np.einsum('ij,ij->i',s,h)*inverse
        q=np.cross(s,a)
        v=np.einsum('ij,ij->i',direction,q)*inverse
        fraction=np.einsum('ij,ij->i',b,q)*inverse
        eps_fraction=endpoint_epsilon_mm/lengths[ray_ids]
        valid=nonparallel&(u>=-1e-9)&(v>=-1e-9)&(u+v<=1.+1e-9)&(fraction>eps_fraction)&(fraction<1.-eps_fraction)
        locations=origins[ray_ids[valid]]+direction[valid]*fraction[valid,None]
        if len(locations):locations=np.unique(np.round(locations,8),axis=0)
    return dict(count=int(len(locations)),
                point_mm=locations[0].tolist() if len(locations) else None,
                tested_segments=int(len(origins)))


class SeatMaterialGeometry:
    """Immutable seat input mesh + current actual vessel pose, cached at control Hz.

    Args are metres, world coordinates for target vertices, body-local coordinates
    for vessel vertices. ``target_floor_m`` is the declared bearing plane origin;
    ``instrument_rotation`` maps seat-local vectors into world coordinates.
    A search-selected XY offset belongs in ``loading_center_offset_local_m``; it
    does not move, scale or edit the seat itself.
    """

    def __init__(self, vessel_local_vertices_m, vessel_faces,
                 target_world_vertices_m, target_faces, *, target_floor_m,
                 instrument_rotation, target_depth_m=.027, target_inner_m=.0126,
                 tolerance_m=.00005, control_hz=60., near_margin_m=.003,
                 loading_center_offset_local_m=(0., 0.)):
        self.vessel = trimesh.Trimesh(np.asarray(vessel_local_vertices_m)*1000.,
            np.asarray(vessel_faces), process=True, validate=True)
        self.target = trimesh.Trimesh(np.asarray(target_world_vertices_m)*1000.,
            np.asarray(target_faces), process=True, validate=True)
        if not len(self.vessel.faces) or not len(self.target.faces):
            raise ValueError('Runtime material check requires both triangle meshes')
        if not self.vessel.is_watertight or not self.vessel.is_winding_consistent:
            raise ValueError('Vessel source material must be closed and consistently oriented')
        self.floor = np.asarray(target_floor_m, float)
        self.rotation = np.asarray(instrument_rotation, float)
        self.depth, self.inner = float(target_depth_m), float(target_inner_m)
        self.tolerance = float(tolerance_m)
        self.control_hz, self.near_margin = float(control_hz), float(near_margin_m)
        self.offset = np.asarray(loading_center_offset_local_m, float)
        if self.offset.shape != (2,):
            raise ValueError('loading_center_offset_local_m requires two values')
        self.vessel_points = _samples(self.vessel)
        self.target_points = _samples(self.target)
        self.target_edges = self.target.vertices[self.target.edges_unique]
        self._cache_key, self._cache = None, None
        self.calls = self.computations = 0
        self.total_compute_wall_s = 0.
        self.source_paths = None

    @classmethod
    def from_stage(cls, stage, target_collision_prim_path,
                   vessel_vertices_m, vessel_faces, target_floor_m,
                   instrument_rotation, depth_m, *, tolerance_m=.00005,
                   cache_control_hz=60., **kwargs):
        """Read actual selected collider input and its full current world transform."""
        from pxr import UsdGeom
        prim = stage.GetPrimAtPath(str(target_collision_prim_path))
        if not prim or not prim.IsA(UsdGeom.Mesh):
            raise ValueError('Selected original seat collider must be an actual Mesh')
        mesh = UsdGeom.Mesh(prim)
        points = np.asarray(mesh.GetPointsAttr().Get(), float)
        matrix = np.asarray(UsdGeom.XformCache().GetLocalToWorldTransform(prim))
        world = (np.c_[points, np.ones(len(points))]@matrix)[:, :3]
        indices = np.asarray(mesh.GetFaceVertexIndicesAttr().Get(), int)
        faces, start = [], 0
        for count in mesh.GetFaceVertexCountsAttr().Get():
            polygon = indices[start:start+count]
            faces.extend((polygon[0], polygon[i], polygon[i+1]) for i in range(1, count-1))
            start += count
        # Current formal stage is metre-authored. Check instead of silently
        # assuming this when another caller references a millimetre root.
        unit = float(UsdGeom.GetStageMetersPerUnit(stage))
        instance = cls(vessel_vertices_m, vessel_faces, world*unit, faces,
            target_floor_m=target_floor_m,instrument_rotation=instrument_rotation,
            target_depth_m=depth_m,tolerance_m=tolerance_m,
            control_hz=cache_control_hz,**kwargs)
        instance.source_paths = dict(target_collision_prim_path=str(prim.GetPath()),
            target_meters_per_stage_unit=unit,
            world_transform_row_matrix=matrix.tolist(),
            authored_approximation=prim.GetAttribute('physics:approximation').Get())
        return instance

    def metadata(self):
        edge_lengths = self.vessel.edges_unique_length
        return dict(schema='labsim.Size_v1.actual_pose_input_material_check.v1',
            scope='Current source visual vessel material versus unchanged selected-seat collision input triangles; NOT cooked PhysX readback',
            query_units='mm; returned length fields use m',
            method='Exact closest point on triangles for every vertex and at most256 deterministic stratified face-centroids per mesh; both mesh directions; complete unique-edge finite segment-triangle crossing queries',
            target_watertight=bool(self.target.is_watertight),
            target_winding_consistent=bool(self.target.is_winding_consistent),
            target_boundary_edge_count=_boundary_count(self.target),
            vessel_watertight=bool(self.vessel.is_watertight),
            vessel_face_count=int(len(self.vessel.faces)),
            target_face_count=int(len(self.target.faces)),
            vessel_sample_count=int(len(self.vessel_points)),
            target_sample_count=int(len(self.target_points)),
            vessel_max_triangle_edge_m=float(edge_lengths.max()/1000),
            vessel_p95_triangle_edge_m=float(np.percentile(edge_lengths,95)/1000),
            sample_spacing_is_global_error_bound=False,
            numerical_endpoint_epsilon_m=1e-8,
            overlap_tolerance_m=self.tolerance,
            cache_control_hz=self.control_hz,
            loading_center_offset_local_m=self.offset.tolist(),
            native_target_overlap_measured=False,
            limitations=[
                'Finite surface samples can miss a maximum penetration between samples; reported depth is an observed value, not a global upper bound.',
                'Segment crossing detects transverse triangle crossings, not every coplanar overlap; coplanar contact is additionally sampled by point-to-triangle distance.',
                'Original seat input mesh has open boundary edges. Its signed-distance side classification uses local face orientation/ray parity and is qualified near open boundaries.',
                'No access to effective cooked PhysX shapes or solver material deformation; no claim to exclude all cooked-shape penetration.'],
            source_paths=self.source_paths,
            target_input_arrays_sha256=hashlib.sha256(
                self.target.vertices.tobytes()+self.target.faces.tobytes()).hexdigest())

    def measure(self, position_m, quaternion_wxyz, simulation_time_s, *, force=False):
        """Return one measured result per control time bin, with explicit sample age."""
        self.calls += 1
        t = float(simulation_time_s)
        key = int(np.floor(t*self.control_hz+1e-7))
        if not force and key == self._cache_key:
            result = dict(self._cache)
            result['input_geometry_cache_age_s'] = max(0., t-result['input_geometry_sample_time_s'])
            return result
        p = np.asarray(position_m, float)
        if p.shape != (3,) or not np.isfinite(p).all():
            raise ValueError('Expected finite actual vessel position')
        rotation = _rotation(quaternion_wxyz)
        start = time.perf_counter()
        world = rotation.apply(self.vessel.vertices)+p*1000.
        bounds = np.array([world.min(0), world.max(0)])
        delta = np.maximum(np.maximum(self.target.bounds[0]-bounds[1],
                                      bounds[0]-self.target.bounds[1]), 0.)
        near = bool(np.linalg.norm(delta) <= self.near_margin*1000.)
        base = dict(input_geometry_sample_time_s=t, input_geometry_cache_age_s=0.,
            input_geometry_near_selected_seat=near,
            native_target_overlap_m=None, native_target_overlap_measured=False,
            input_geometry_scope='authored vessel material/seat collision input, not cooked PhysX',
            input_geometry_overlap_observed_m=None,
            target_region_contains_object_sampled=None,
            target_region_contains_object=None,
            input_geometry_surface_crossing_count=None,
            input_geometry_min_sample_surface_distance_m=None,
            input_geometry_observed_worst_point_world_m=None,
            input_geometry_sign_qualified=not bool(self.target.is_watertight),
            input_method='All vertices plus deterministic face-centroid samples; exact point-to-triangle signed distances and complete unique-edge crossing checks in mm. Qualified input-mesh observation, not cooked PhysX.',
            input_limitations=self.metadata()['limitations'],
            input_geometry_assessment='unavailable_remote_from_selected_seat')
        if near:
            base.update(self._near_measure(p,rotation,world,bounds))
            base['input_geometry_aabb_distance_lower_bound_m']=float(np.linalg.norm(delta)/1000.)
        base['input_geometry_compute_wall_s'] = time.perf_counter()-start
        self.computations += 1
        self.total_compute_wall_s += base['input_geometry_compute_wall_s']
        self._cache_key, self._cache = key, dict(base)
        return base

    def _near_measure(self,p,rotation,world,bounds):
        vessel_world_samples = rotation.apply(self.vessel_points)+p*1000.
        tol_mm = self.tolerance*1000.
        # Only samples in the opposite AABB can be inside its material. Other
        # points cannot contribute to observed penetration; none are filled in.
        vp = vessel_world_samples[_in_bounds(vessel_world_samples,self.target.bounds,tol_mm)]
        tp = self.target_points[_in_bounds(self.target_points,bounds,tol_mm)]
        signed_v = (trimesh.proximity.signed_distance(self.target,vp)
                    if len(vp) else np.empty(0))
        target_in_body = rotation.inv().apply(tp-p*1000.)
        signed_t = (trimesh.proximity.signed_distance(self.vessel,target_in_body)
                    if len(tp) else np.empty(0))
        maximum = 0.
        worst = None
        direction = None
        for distance,points,name in ((signed_v,vp,'vessel_sample_inside_target_input'),
                                     (signed_t,tp,'target_input_sample_inside_vessel')):
            if len(distance) and np.max(distance)>maximum:
                i = int(np.argmax(distance));maximum = float(distance[i])
                worst, direction = points[i]/1000.,name
        # Test edges in both directions. AABB broadphase avoids ray queries for
        # segments which cannot touch the opposite mesh's actual finite bounds.
        vessel_edges = world[self.vessel.edges_unique]
        overlap = np.all(vessel_edges.max(1)>=self.target.bounds[0]-1e-6,axis=1)&np.all(vessel_edges.min(1)<=self.target.bounds[1]+1e-6,axis=1)
        ve = vessel_edges[overlap]
        crossing_v = _segment_crossings(ve[:,0],ve[:,1],self.target)
        overlap = np.all(self.target_edges.max(1)>=bounds[0]-1e-6,axis=1)&np.all(self.target_edges.min(1)<=bounds[1]+1e-6,axis=1)
        te = self.target_edges[overlap]
        local_edges = rotation.inv().apply(te.reshape(-1,3)-p*1000.).reshape(-1,2,3)
        crossing_t = _segment_crossings(local_edges[:,0],local_edges[:,1],self.vessel)
        crossings = crossing_v['count']+crossing_t['count']
        # Legal target region is explicitly the declared reference channel plus
        # both actual input-surface checks, never the reference envelope alone.
        local = ((world/1000.-self.floor)@self.rotation)
        relevant_parts=[local[(local[:,2]>=-self.tolerance)&(local[:,2]<=self.depth+self.tolerance)]]
        edges=local[self.vessel.edges_unique]
        for height in (0.,self.depth):
            dz=edges[:,1,2]-edges[:,0,2]
            crosses=(np.abs(dz)>1e-12)&((edges[:,0,2]-height)*(edges[:,1,2]-height)<0.)
            selected=edges[crosses]
            if len(selected):
                fraction=(height-selected[:,0,2])/(selected[:,1,2]-selected[:,0,2])
                relevant_parts.append(selected[:,0]+fraction[:,None]*(selected[:,1]-selected[:,0]))
        relevant=np.concatenate(relevant_parts)
        envelope = bool(len(relevant) and np.max(np.abs(relevant[:,:2])) <= self.inner/2+self.tolerance)
        distance_samples = np.r_[np.abs(signed_v), np.abs(signed_t)]
        # Crossing by itself is not a penetration-depth measurement. If all
        # samples report <= tolerance, leave this ambiguity explicit for the
        # independent scorer instead of manufacturing a zero penetration proof.
        uncertain_crossing = bool(crossings and maximum<=1e-6)
        valid_sampled = bool(envelope and maximum<=tol_mm and not uncertain_crossing)
        return dict(input_geometry_overlap_observed_m=maximum/1000. if len(distance_samples) else None,
            input_geometry_sampled_material_query_available=bool(len(distance_samples)),
            target_region_contains_object_sampled=valid_sampled,
            target_region_contains_object=valid_sampled,
            input_geometry_surface_crossing_count=int(crossings),
            input_geometry_crossing_without_resolved_depth=uncertain_crossing,
            input_geometry_min_sample_surface_distance_m=float(distance_samples.min()/1000.) if len(distance_samples) else None,
            input_geometry_observed_worst_point_world_m=worst.tolist() if worst is not None else None,
            input_geometry_observed_worst_direction=direction,
            input_geometry_query_sample_counts=dict(vessel=int(len(vp)),target=int(len(tp))),
            input_geometry_crossing_queries=dict(vessel_edges=crossing_v,target_edges_local=crossing_t),
            input_geometry_reference_envelope_contains=envelope,
            input_geometry_assessment='sampled_input_material_within_tolerance' if valid_sampled else
                'input_surface_crossing_depth_unresolved' if uncertain_crossing else
                'observed_input_material_overlap' if maximum>tol_mm else 'outside_declared_target_reference')
