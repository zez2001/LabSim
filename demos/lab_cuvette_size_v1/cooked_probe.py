"""Read-only collision evidence from an already running Isaac Sim 5.1 stage.

Call ``probe(stage, new_json_path)`` on the simulation main thread immediately
after reset. This module never changes USD, physics settings, stage attachment,
cache contents explicitly, rigid poses or simulation time. The cooking query
may populate the existing cooking cache. No extra physics step is performed.

5.1 exposes a convex cooking representation query but no Python read-back of
attached PxTriangleMesh vertices. Consequently convex query output, runtime
scene statistics and sampled runtime ray surfaces are reported separately.
The former is not claimed to be a pointer-level attached PxShape read-back.
"""
from __future__ import annotations

import json
from pathlib import Path
import time

import numpy as np


def triangulate(counts, indices):
    triangles, offset = [], 0
    for count in counts:
        face = indices[offset:offset + int(count)]
        triangles.extend((int(face[0]), int(face[j]), int(face[j + 1]))
                         for j in range(1, len(face) - 1))
        offset += int(count)
    return np.asarray(triangles, dtype=np.int64).reshape(-1, 3)


def point_to_triangles(point, triangles):
    """Euclidean point-to-face/edge distance, never nearest vertex distance."""
    point = np.asarray(point, float)
    triangles = np.asarray(triangles, float).reshape(-1, 3, 3)
    a, b, c = triangles[:, 0], triangles[:, 1], triangles[:, 2]
    ab, ac, ap = b-a, c-a, point-a
    normal = np.cross(ab, ac)
    nn = np.einsum("ij,ij->i", normal, normal)
    safe = nn > 1e-30
    projected = point - normal * np.divide(np.einsum("ij,ij->i", ap, normal), nn,
                                           out=np.zeros(len(nn)), where=safe)[:, None]
    v = projected-a
    d00 = np.einsum("ij,ij->i", ab, ab)
    d01 = np.einsum("ij,ij->i", ab, ac)
    d11 = np.einsum("ij,ij->i", ac, ac)
    d20, d21 = np.einsum("ij,ij->i", v, ab), np.einsum("ij,ij->i", v, ac)
    denominator = d00*d11-d01*d01
    valid = np.abs(denominator) > 1e-30
    u = np.divide(d11*d20-d01*d21, denominator, out=np.zeros(len(nn)), where=valid)
    w = np.divide(d00*d21-d01*d20, denominator, out=np.zeros(len(nn)), where=valid)
    inside = safe & valid & (u >= -1e-9) & (w >= -1e-9) & (u+w <= 1+1e-9)
    distances = np.full(len(triangles), np.inf)
    distances[inside] = np.linalg.norm(projected[inside]-point, axis=1)
    for start, end in ((a, b), (b, c), (c, a)):
        edge = end-start
        length2 = np.einsum("ij,ij->i", edge, edge)
        t = np.clip(np.divide(np.einsum("ij,ij->i", point-start, edge), length2,
                              out=np.zeros(len(nn)), where=length2 > 1e-30), 0, 1)
        distances = np.minimum(distances, np.linalg.norm(start+t[:, None]*edge-point, axis=1))
    return distances


def surface_comparison(input_vertices, input_triangles, cooked_vertices,
                       cooked_triangles, local_to_world, meters_per_stage_unit):
    """Compare all vertices and triangle centroids after the SAME full transform.

    Local coordinates need not be metres: the real stage uses mm-valued points
    below a0.001-scale Xform. Applying only stage metersPerUnit is insufficient.
    The returned sample maximum is never a strict global surface error bound.
    """
    matrix = np.asarray(local_to_world, float)
    def transform(points):
        points = np.asarray(points, float)
        return (np.c_[points, np.ones(len(points))] @ matrix)[:, :3] * meters_per_stage_unit
    inp, cooked = transform(input_vertices), transform(cooked_vertices)
    it = inp[np.asarray(input_triangles, int)]
    ct = cooked[np.asarray(cooked_triangles, int)]
    out_sample = np.r_[cooked, ct.mean(1)]
    in_sample = np.r_[inp, it.mean(1)]
    outward = np.array([point_to_triangles(point, it).min() for point in out_sample])
    inward = np.array([point_to_triangles(point, ct).min() for point in in_sample])
    vertex = outward[:len(cooked)]
    return dict(coordinate_system="world metres after full local-to-world transform then stage metersPerUnit",
        sample_rule="all vertices plus every fan-triangulated triangle centroid, per input block",
        cooked_to_input_sample_count=len(outward), input_to_cooked_sample_count=len(inward),
        cooked_to_input_distances_m=outward.tolist(), input_to_cooked_distances_m=inward.tolist(),
        sampled_cooked_vertex_to_input_surface_distance_m=vertex.tolist(),
        max_sampled_cooked_vertex_to_input_surface_distance_m=float(vertex.max()),
        max_observed_cooked_to_input_surface_distance_m=float(outward.max()),
        max_observed_input_to_cooked_surface_distance_m=float(inward.max()),
        worst_cooked_world_point_m=out_sample[int(outward.argmax())].tolist(),
        worst_input_world_point_m=in_sample[int(inward.argmax())].tolist(),
        cooked_world_bounds_m=[cooked.min(0).tolist(), cooked.max(0).tolist()],
        input_world_bounds_m=[inp.min(0).tolist(), inp.max(0).tolist()],
        scope="per-block point-to-triangle samples; not compound union exterior, cavity-fill or strict global Hausdorff bound")


def _xyz(value):
    return [float(value[i]) for i in range(3)]


def _hit(hit):
    if isinstance(hit, dict):
        return {key: value for key, value in hit.items()}
    value = {}
    for name in ("position", "normal", "distance", "faceIndex", "face_index", "collision", "rigidBody", "rigid_body", "protoIndex", "material"):
        if hasattr(hit, name):
            value[{"face_index": "faceIndex", "rigid_body": "rigidBody"}.get(name, name)] = getattr(hit, name)
    return value


def _json_hit(hit):
    value = _hit(hit)
    result = {}
    for key, item in value.items():
        if key in {"position", "normal"}:
            result[key] = _xyz(item)
        elif key in {"distance"}:
            result[key] = float(item)
        elif key in {"faceIndex", "protoIndex"}:
            result[key] = int(item)
        elif key in {"collision", "rigidBody", "material"}:
            result[key] = str(item)
    return result


def probe(stage, output, *, vessel_root="/World/Cuvette",
          target_paths=("/World/Instrument/Collision/SourceMesh3",),
          ray_grid=15, ray_padding_m=.003):
    """Capture convex cooking responses plus actual static-seat ray hit samples.

    ``ray_grid`` is sampling density, not a declared global geometric bound or
    physical contact precision. Rays query the existing runtime scene; they do
    not move the object or substitute a temporary static scene.
    """
    from pxr import Gf, PhysicsSchemaTools, Usd, UsdGeom, UsdPhysics, UsdUtils
    import omni.physx

    output = Path(output)
    if output.exists():
        raise FileExistsError(output)
    if ray_grid < 2:
        raise ValueError("ray_grid must be at least 2")
    started = time.perf_counter()
    stage_id = UsdUtils.StageCache.Get().GetId(stage).ToLongInt()
    if stage_id < 0:
        raise ValueError("Stage is not attached/registered; probe will not attach it")
    unit = float(UsdGeom.GetStageMetersPerUnit(stage))
    cooking = omni.physx.get_physx_cooking_interface()
    query = omni.physx.get_physx_scene_query_interface()
    xforms = UsdGeom.XformCache(Usd.TimeCode.Default())
    stage_before = stage.GetRootLayer().ExportToString()
    result = dict(schema="labsim.Size_v1.cooking_and_runtime_surface_probe.v1", stage_id=stage_id,
        meters_per_stage_unit=unit, up_axis=str(UsdGeom.GetStageUpAxis(stage)),
        simulation_steps_added=0, source_or_scene_edited=False, runtime_attachment_changed=False,
        convex_query_api="get_physx_cooking_interface.request_convex_collision_representation",
        convex_api_scope="PhysX cooking representation requested for this live stage USD prim; not attached PxShape pointer read-back",
        static_surface_api="get_physx_scene_query_interface.raycast_all",
        static_cooked_full_vertex_readback_available=False,
        static_effective_approximation_fully_verified=False,
        get_nb_convex_mesh_data_api_present=hasattr(cooking, "get_nb_convex_mesh_data"),
        get_convex_mesh_data_api_present=hasattr(cooking, "get_convex_mesh_data"),
        convexes=[], target_runtime_surface_samples=[], warnings=[])
    try:
        result["runtime_scene_statistics"] = dict(omni.physx.get_physxunittests_interface().get_physics_stats())
    except Exception as error:
        result["runtime_scene_statistics_error"] = repr(error)
    roots = [stage.GetPrimAtPath(vessel_root)]
    if not roots[0]:
        raise ValueError("Missing vessel root: " + vessel_root)
    for prim in Usd.PrimRange(roots[0], Usd.TraverseInstanceProxies()):
        if not prim.IsA(UsdGeom.Mesh) or not prim.HasAPI(UsdPhysics.CollisionAPI):
            continue
        enabled = UsdPhysics.CollisionAPI(prim).GetCollisionEnabledAttr().Get()
        if enabled is False:
            continue
        approximation = str(UsdPhysics.MeshCollisionAPI(prim).GetApproximationAttr().Get())
        item = dict(prim_path=str(prim.GetPath()), authored_approximation=approximation,
                    collision_enabled=True, callback_called=False, representations=[])
        if approximation not in {"convexHull", "convexDecomposition"}:
            item["query_skipped"] = "Convex query could misrepresent a non-convex authored approximation"
            result["convexes"].append(item)
            continue
        mesh = UsdGeom.Mesh(prim)
        source_points = np.asarray(mesh.GetPointsAttr().Get(), float)
        faces = triangulate(list(mesh.GetFaceVertexCountsAttr().Get()),
                            list(mesh.GetFaceVertexIndicesAttr().Get()))
        source_triangles = source_points[faces]
        matrix = xforms.GetLocalToWorldTransform(prim)
        item["usd_local_to_world_row_matrix"] = np.array(matrix).tolist()
        item["input_vertices_local_coordinates"] = source_points.tolist()
        item["input_triangle_vertex_indices"] = faces.tolist()
        item["local_coordinate_units_note"] = "Apply full saved local-to-world matrix before stage metersPerUnit; local numerical points may be millimetre-scaled"
        item["input_local_bounds_stage_units"] = [source_points.min(0).tolist(), source_points.max(0).tolist()]
        def received(status, convexes):
            item["callback_called"] = True
            item["status"] = str(status)
            item["status_value"] = int(status)
            for convex in convexes:
                vertices = np.array([_xyz(vertex) for vertex in convex.vertices], float)
                indices = [int(index) for index in convex.indices]
                polygons = [dict(index_base=int(p.index_base), num_vertices=int(p.num_vertices),
                                 plane=[float(p.plane[i]) for i in range(4)]) for p in convex.polygons]
                cooked_faces = []
                for polygon in polygons:
                    face = indices[polygon["index_base"]:polygon["index_base"] + polygon["num_vertices"]]
                    cooked_faces.extend((face[0], face[j], face[j + 1]) for j in range(1, len(face) - 1))
                comparison = surface_comparison(source_points, faces, vertices, cooked_faces, matrix, unit)
                deprecated = [float(np.min(point_to_triangles(point, source_triangles)) * unit) for point in vertices]
                item["representations"].append(dict(vertices_local_stage_units=vertices.tolist(),
                    indices=indices, polygons=polygons, cooked_triangle_vertex_indices=cooked_faces,
                    local_bounds_stage_units=[vertices.min(0).tolist(), vertices.max(0).tolist()],
                    sampled_vertex_to_input_surface_distance_m=comparison["sampled_cooked_vertex_to_input_surface_distance_m"],
                    max_sampled_vertex_to_input_surface_distance_m=comparison["max_sampled_cooked_vertex_to_input_surface_distance_m"],
                    surface_comparison_world_m=comparison,
                    deprecated_unscaled_local_vertex_distance_values=deprecated,
                    deprecated_unscaled_local_vertex_distance_note="Preview01 metric only multiplied stage metersPerUnit and omitted mesh Xform scale; never interpret nonzero values as world metres. Retained for provenance only.",
                    distance_scope="Returned vertices transformed to world metres, then point-to-input triangle surface; per-block samples only"))
        try:
            cooking.request_convex_collision_representation(stage_id=stage_id,
                collision_prim_id=PhysicsSchemaTools.sdfPathToInt(prim.GetPath()),
                run_asynchronously=False, on_result=received)
        except Exception as error:
            item["error"] = repr(error)
        result["convexes"].append(item)
    for path in target_paths:
        prim = stage.GetPrimAtPath(path)
        if not prim or not prim.IsA(UsdGeom.Mesh):
            result["target_runtime_surface_samples"].append(dict(prim_path=path, error="Missing target mesh"))
            continue
        mesh = UsdGeom.Mesh(prim)
        points = np.asarray(mesh.GetPointsAttr().Get(), float)
        matrix = xforms.GetLocalToWorldTransform(prim)
        world = np.array([matrix.Transform(Gf.Vec3d(*point)) for point in points], float)
        faces = triangulate(list(mesh.GetFaceVertexCountsAttr().Get()), list(mesh.GetFaceVertexIndicesAttr().Get()))
        world_triangles = world[faces]
        lower, upper = world.min(0), world.max(0)
        samples, rays, hits_on_target = [], 0, 0
        for axis in range(3):
            others = [index for index in range(3) if index != axis]
            for sign in (-1, 1):
                for a in np.linspace(lower[others[0]] + 1e-7/unit, upper[others[0]] - 1e-7/unit, ray_grid):
                    for b in np.linspace(lower[others[1]] + 1e-7/unit, upper[others[1]] - 1e-7/unit, ray_grid):
                        origin = (lower+upper)/2
                        origin[others] = [a, b]
                        origin[axis] = (lower[axis] - ray_padding_m/unit) if sign == 1 else (upper[axis] + ray_padding_m/unit)
                        direction = np.zeros(3)
                        direction[axis] = sign
                        distance = float(upper[axis]-lower[axis]+2*ray_padding_m/unit)
                        hit_list = []
                        def on_hit(hit):
                            converted = _json_hit(hit)
                            if converted.get("collision") == path:
                                hit_list.append(converted)
                            return True
                        query.raycast_all(tuple(origin), tuple(direction), distance, on_hit, bothSides=True)
                        rays += 1
                        if not hit_list:
                            continue
                        hits_on_target += len(hit_list)
                        for hit in hit_list:
                            p = np.asarray(hit["position"], float)
                            surface = point_to_triangles(p, world_triangles)
                            hit["distance_to_authored_surface_m"] = float(surface.min() * unit)
                            hit["nearest_authored_triangle_index"] = int(np.argmin(surface))
                            samples.append(dict(origin_world_stage_units=origin.tolist(), direction=direction.tolist(), hit=hit))
        distances = [sample["hit"]["distance_to_authored_surface_m"] for sample in samples]
        result["target_runtime_surface_samples"].append(dict(prim_path=path,
            authored_approximation=str(UsdPhysics.MeshCollisionAPI(prim).GetApproximationAttr().Get()),
            authored_triangle_count=len(faces), usd_local_to_world_row_matrix=np.array(matrix).tolist(),
            authored_world_bounds_stage_units=[lower.tolist(), upper.tolist()], ray_grid_per_projection=ray_grid,
            rays=rays, hits_on_target=hits_on_target, samples=samples,
            observed_max_surface_distance_m=max(distances, default=None),
            observed_face_indices=sorted({sample["hit"].get("faceIndex", -1) for sample in samples}),
            scope="Actual runtime hit surfaces sampled from six orthogonal directions; absent/internal faces and fallback may remain unobserved; not a global error bound"))
    result["convex_input_prim_count"] = len(result["convexes"])
    result["convex_valid_response_prim_count"] = sum(item.get("status_value") == 0 for item in result["convexes"])
    result["returned_convex_count"] = sum(len(item["representations"]) for item in result["convexes"])
    comparisons = [hull["surface_comparison_world_m"] for item in result["convexes"]
                   for hull in item["representations"]]
    result["cooking_surface_comparison_world_m"] = dict(
        cooked_to_input_sample_count=sum(item["cooked_to_input_sample_count"] for item in comparisons),
        input_to_cooked_sample_count=sum(item["input_to_cooked_sample_count"] for item in comparisons),
        max_observed_cooked_to_input_surface_distance_m=max((item["max_observed_cooked_to_input_surface_distance_m"] for item in comparisons), default=None),
        max_observed_input_to_cooked_surface_distance_m=max((item["max_observed_input_to_cooked_surface_distance_m"] for item in comparisons), default=None),
        scope="all returned/input vertices and face centroids, transformed with each full Xform; per-block observed distances, not a strict global or compound exterior error bound")
    result["root_layer_unchanged"] = stage.GetRootLayer().ExportToString() == stage_before
    result["wall_seconds"] = time.perf_counter()-started
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    return result
