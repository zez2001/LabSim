"""Derive a 12.5 mm XY vessel from ext02, without starting Isaac or a GPU.

The declared affine map is diag(12.5/14.85, 12.5/14.85, 1).  It is
applied to every visual and collision INPUT vertex in the rigid-body frame.
Mass remains an explicit 20 g engineering assumption.  Inertia is integrated
over the closed source visual material volume and checked by an independent
central-second-moment affine transform.  Cooked PhysX geometry is not read.

Run through demos/lab_cuvette_external/usd_python.sh for pxr/Physx schemas.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np
from pxr import Gf, Usd, UsdGeom, UsdPhysics
from scipy.spatial import ConvexHull
from scipy.spatial.transform import Rotation
import trimesh

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "assets/lab_cuvette_loading/V0_ext02/walls28_mm.usda"
OUTPUT = ROOT / "assets/lab_cuvette_loading/V0_demo04/vessel_125_mm.usda"
EVIDENCE = ROOT / "docs/lab_cuvette_loading/V0_demo04/vessel"
EXPECTED_SOURCE_SHA256 = "70133b2a66b1705f6de80c52e46c857b02a9811386971ea14b6a188e1edfde4b"
SCALE = np.array([12.5 / 14.85, 12.5 / 14.85, 1.0])
MASS_KG = 0.020


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def serializable(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (np.floating, np.integer, np.bool_)):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    raise TypeError(type(value))


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=serializable,
                               allow_nan=False) + "\n", encoding="utf-8")


def read_geometry(stage):
    cache = UsdGeom.XformCache()
    body = stage.GetDefaultPrim()
    inverse_body = np.linalg.inv(np.asarray(cache.GetLocalToWorldTransform(body)))
    result = {}
    for prim in stage.Traverse():
        if not prim.IsA(UsdGeom.Mesh):
            continue
        mesh = UsdGeom.Mesh(prim)
        points = np.asarray(mesh.GetPointsAttr().Get(), dtype=float)
        counts = np.asarray(mesh.GetFaceVertexCountsAttr().Get(), dtype=int)
        if not np.all(counts == 3):
            raise ValueError("Unexpected non-triangle source: " + str(prim.GetPath()))
        indices = np.asarray(mesh.GetFaceVertexIndicesAttr().Get(), dtype=int).reshape(-1, 3)
        matrix = np.asarray(cache.GetLocalToWorldTransform(prim)) @ inverse_body
        world = (np.c_[points, np.ones(len(points))] @ matrix)[:, :3]
        result[str(prim.GetPath())] = dict(points=points, faces=indices, matrix=matrix,
            body_points=world, collision=prim.HasAPI(UsdPhysics.CollisionAPI),
            approximation=str(UsdPhysics.MeshCollisionAPI(prim).GetApproximationAttr().Get())
            if prim.HasAPI(UsdPhysics.MeshCollisionAPI) else None,
            normals_authored=mesh.GetNormalsAttr().HasAuthoredValue())
    return result


def integrate_material(points, faces, mass=MASS_KG):
    """Signed origin tetrahedra; exact polynomial integrals of indexed triangles.

    No convex hull, external surface area approximation, or collider-volume sum
    enters the material mass calculation.  Source must be a closed oriented
    material boundary including its cavity and base.
    """
    mesh = trimesh.Trimesh(vertices=points, faces=faces, process=True)
    if not mesh.is_watertight or not mesh.is_winding_consistent:
        raise ValueError("Visual material boundary is not closed/oriented")
    triangles = points[faces]
    volumes = np.einsum("ij,ij->i", triangles[:, 0],
                        np.cross(triangles[:, 1], triangles[:, 2])) / 6
    volume = volumes.sum()
    if volume <= 0:
        raise ValueError("Expected positive oriented material volume")
    sums = triangles.sum(axis=1)
    com = np.einsum("i,ij->j", volumes, sums) / (4 * volume)
    raw = np.einsum("i,ij,ik->jk", volumes / 20, sums, sums)
    raw += np.einsum("i,ipj,ipk->jk", volumes / 20, triangles, triangles)
    covariance = raw / volume - np.outer(com, com)
    inertia = mass * (np.trace(covariance) * np.eye(3) - covariance)
    mesh.density = mass / volume
    if not np.allclose(inertia, mesh.moment_inertia, atol=1e-17, rtol=1e-9):
        raise ValueError("Tetrahedral and trimesh surface-integral inertia disagree")
    if not np.allclose(com, mesh.center_mass, atol=1e-13, rtol=1e-9):
        raise ValueError("Tetrahedral and trimesh COM disagree")
    principal, axes = np.linalg.eigh(inertia)
    if np.linalg.det(axes) < 0:
        axes[:, -1] *= -1
    if np.any(principal <= 0):
        raise ValueError("Non-positive principal inertia")
    quat = Rotation.from_matrix(axes).as_quat()  # xyzw, columns are body-frame axes
    return dict(mass_kg=mass, material_volume_m3=volume, homogeneous_density_kg_m3=mass / volume,
                com_body_m=com, central_second_moment_m2=covariance,
                inertia_body_kg_m2=inertia, principal_inertia_kg_m2=principal,
                principal_axes_columns_in_body=axes,
                principal_axes_quaternion_wxyz=np.r_[quat[3], quat[:3]],
                boundary_watertight=True, boundary_winding_consistent=True,
                independent_trimesh_inertia_max_abs_delta_kg_m2=np.abs(inertia-mesh.moment_inertia).max())


def usd_mass_snapshot(stage):
    api = UsdPhysics.MassAPI(stage.GetDefaultPrim())
    quaternion = api.GetPrincipalAxesAttr().Get()
    row_rotation = np.asarray(Gf.Matrix3d(Gf.Quatd(quaternion)))
    principal = np.asarray(api.GetDiagonalInertiaAttr().Get(), dtype=float)
    return dict(mass_kg=float(api.GetMassAttr().Get()),
                com_body_m=np.asarray(api.GetCenterOfMassAttr().Get(), dtype=float),
                principal_inertia_kg_m2=principal,
                principal_axes_quaternion_wxyz=np.r_[quaternion.GetReal(), quaternion.GetImaginary()],
                inertia_body_kg_m2=row_rotation.T @ np.diag(principal) @ row_rotation)


def convex_input_mesh(geometry):
    """Mathematical hull of authored input vertices, not a PhysX cooked readback."""
    points = geometry["body_points"]
    hull = ConvexHull(points)
    faces = hull.simplices.copy()
    for index, face in enumerate(faces):
        normal = np.cross(points[face[1]] - points[face[0]], points[face[2]] - points[face[0]])
        if np.dot(normal, hull.equations[index, :3]) < 0:
            faces[index, [1, 2]] = faces[index, [2, 1]]
    return trimesh.Trimesh(vertices=points, faces=faces, process=False)


def section_segments(mesh, height):
    segments = trimesh.intersections.mesh_plane(mesh, [0, 0, 1], [0, 0, height])
    return segments[:, :, :2] if len(segments) else np.empty((0, 2, 2))


def section_measurements(geometries, evidence):
    heights_mm = [0.0001, 0.1, 1, 4.8, 4.9, 5.1, 5.2, 10, 25, 40, 60, 67.25, 67.45]
    rows = []
    sections = {}
    for version, geometry in geometries.items():
        visual = geometry["/Asset/Visual/Mesh"]
        visual_mesh = trimesh.Trimesh(vertices=visual["body_points"], faces=visual["faces"], process=False)
        hulls = [convex_input_mesh(g) for g in geometry.values() if g["collision"]]
        version_sections = []
        for height_mm in heights_mm:
            actual = section_segments(visual_mesh, height_mm / 1000)
            per_shape = [section_segments(hull, height_mm / 1000) for hull in hulls]
            union_segments = np.concatenate(per_shape)
            # Bounds of a union equal the bounds of all of its member points.
            # We do not sum per-hull areas or interpret partition internal
            # faces as material/exterior error.  No coverage metric is claimed.
            actual_width = np.ptp(actual.reshape(-1, 2), axis=0)*1000 if len(actual) else [None, None]
            collision_width = np.ptp(union_segments.reshape(-1, 2), axis=0)*1000 if len(union_segments) else [None, None]
            row = dict(version=version, height_mm=height_mm,
                       visual_width_X_mm=actual_width[0], visual_width_Y_mm=actual_width[1],
                       input_hull_union_bounds_width_X_mm=collision_width[0],
                       input_hull_union_bounds_width_Y_mm=collision_width[1],
                       visual_intersection_segments=len(actual),
                       active_input_hulls=sum(len(part)>0 for part in per_shape))
            rows.append(row)
            version_sections.append((height_mm, actual, union_segments))
        sections[version] = version_sections
    with (evidence / "sections.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return rows, sections


def plot_geometry(geometries, sections, evidence):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection
    from matplotlib.lines import Line2D
    fig, axes = plt.subplots(2, 3, figsize=(13, 10), constrained_layout=True)
    projections = [(0, 1, "XY top"), (0, 2, "XZ side"), (1, 2, "YZ side")]
    for row, (version, geometry) in enumerate(geometries.items()):
        for column, (i, j, title) in enumerate(projections):
            ax = axes[row, column]
            for g in geometry.values():
                p = g["body_points"] * 1000
                edges = p[g["faces"]][:, [0, 1, 2, 0], :][:, :, [i, j]]
                ax.add_collection(LineCollection(edges, colors="#e55c25" if g["collision"] else "#185999",
                    linewidths=.42 if g["collision"] else .5, alpha=.38 if g["collision"] else .65))
            ax.autoscale()
            ax.set_aspect("equal")
            ax.set_title(version + " | " + title)
            ax.set_xlabel("XYZ"[i] + " / mm")
            ax.set_ylabel("XYZ"[j] + " / mm")
            ax.grid(alpha=.2)
    axes[0, 0].legend(handles=[Line2D([0], [0], color="#185999", label="visual material boundary"),
                              Line2D([0], [0], color="#e55c25", label="28 collision INPUT meshes")], fontsize=8)
    fig.suptitle("V0_demo04: XY scale only; Z and base unchanged | offline input geometry, not cooked PhysX", fontsize=12)
    fig.savefig(evidence / "visual_collision_overlay.png", dpi=170)
    plt.close(fig)
    selected = [4.9, 25, 67.45]
    fig, axes = plt.subplots(2, 3, figsize=(12, 8), constrained_layout=True)
    for row, (version, slices) in enumerate(sections.items()):
        for col, height in enumerate(selected):
            _, actual, union_segments = next(x for x in slices if x[0] == height)
            ax = axes[row, col]
            for segments, color, style in [(actual, "#185999", "-"), (union_segments, "#e55c25", "--")]:
                ax.add_collection(LineCollection(segments*1000, colors=color, linestyles=style, linewidths=1.2))
            ax.autoscale()
            ax.set_title(f"{version} | Z={height:g} mm")
            ax.set_aspect("equal")
            ax.set_xlabel("X / mm")
            ax.set_ylabel("Y / mm")
            ax.grid(alpha=.2)
    fig.suptitle("Blue: visual material section; orange: INPUT convex-hull sections, including partition boundaries")
    fig.savefig(evidence / "material_sections.png", dpi=170)
    plt.close(fig)


def build(output=OUTPUT, evidence=EVIDENCE):
    output, evidence = Path(output).resolve(), Path(evidence).resolve()
    if output.exists() or evidence.exists():
        raise FileExistsError("Use a new output asset and new evidence directory")
    source_sha = sha256(SOURCE)
    if source_sha != EXPECTED_SOURCE_SHA256:
        raise ValueError("Source differs from the preserved ext02 baseline")
    source = Usd.Stage.Open(str(SOURCE), Usd.Stage.LoadAll)
    original = read_geometry(source)
    colliders = [g for g in original.values() if g["collision"]]
    if len(original) != 29 or len(colliders) != 28:
        raise ValueError("Expected one visual mesh and 28 collision inputs")
    if any(g["approximation"] != "convexHull" for g in colliders):
        raise ValueError("Source collision representation unexpectedly changed")
    visual = original["/Asset/Visual/Mesh"]
    before = integrate_material(visual["body_points"], visual["faces"])
    output.parent.mkdir(parents=True, exist_ok=True)
    evidence.mkdir(parents=True, exist_ok=False)
    # Fully flattened standalone layer: no absolute/external source references.
    source.Flatten().Export(str(output))
    derived = Usd.Stage.Open(str(output))
    records = []
    for path, g in original.items():
        mesh = UsdGeom.Mesh(derived.GetPrimAtPath(path))
        # Preserve every existing local transform, topology, mass/material API,
        # collider setting and path.  Pull the body-frame affine map back into
        # local points; this handles the inherited 0.001 collision mesh scale.
        target_body = g["body_points"] * SCALE
        local = (np.c_[target_body, np.ones(len(target_body))] @ np.linalg.inv(g["matrix"]))[:, :3]
        mesh.GetPointsAttr().Set([Gf.Vec3f(*point) for point in local])
        mesh.GetExtentAttr().Set([Gf.Vec3f(*local.min(axis=0)), Gf.Vec3f(*local.max(axis=0))])
        if g["normals_authored"]:
            raise ValueError("Source gained authored normals; affine inverse-transpose handling required")
        records.append(dict(path=path, vertex_count=len(local), triangle_count=len(g["faces"]),
                            collision=g["collision"], approximation=g["approximation"],
                            source_body_bounds_m=[g["body_points"].min(0), g["body_points"].max(0)]))
    derived.GetRootLayer().Save()
    intermediate = read_geometry(derived)
    transformed = intermediate["/Asset/Visual/Mesh"]
    after = integrate_material(transformed["body_points"], transformed["faces"])
    affine_q = np.diag(SCALE) @ before["central_second_moment_m2"] @ np.diag(SCALE)
    affine_i = MASS_KG * (np.trace(affine_q) * np.eye(3) - affine_q)
    affine_com = before["com_body_m"] * SCALE
    ideal_after = integrate_material(visual["body_points"] * SCALE, visual["faces"])
    ideal_affine_error = float(np.abs(ideal_after["inertia_body_kg_m2"]-affine_i).max())
    quantized_affine_error = float(np.abs(after["inertia_body_kg_m2"]-affine_i).max())
    # Comparing a 1e-14 off-diagonal value by its own relative magnitude is
    # ill-conditioned.  Bound the full tensor error relative to tensor scale,
    # and separately verify the unquantized independent integral to1e-15.
    affine_quantization_relative = quantized_affine_error / float(np.abs(affine_i).max())
    if ideal_affine_error > 1e-15 or affine_quantization_relative > 1e-6:
        raise ValueError("Reintegrated and full affine inertia disagree")
    mass_api = UsdPhysics.MassAPI(derived.GetDefaultPrim())
    mass_api.GetMassAttr().Set(MASS_KG)
    mass_api.GetCenterOfMassAttr().Set(Gf.Vec3f(*after["com_body_m"]))
    mass_api.GetDiagonalInertiaAttr().Set(Gf.Vec3f(*after["principal_inertia_kg_m2"]))
    q = after["principal_axes_quaternion_wxyz"]
    mass_api.GetPrincipalAxesAttr().Set(Gf.Quatf(float(q[0]), Gf.Vec3f(*q[1:])))
    derived.GetDefaultPrim().SetCustomDataByKey("labsim_vessel_version", "V0_demo04_vessel_125_mm")
    derived.GetDefaultPrim().SetCustomDataByKey("labsim_source_sha256", source_sha)
    derived.GetDefaultPrim().SetCustomDataByKey("labsim_geometry_change", "XY=12.5/14.85; Z=1; bottom origin unchanged; visual and all28 collision inputs transformed identically")
    derived.GetDefaultPrim().SetCustomDataByKey("labsim_mass_assumption", "20g engineering assumption; homogeneous source-material integral; not calibrated")
    derived.GetRootLayer().Save()
    derived = None
    reload = Usd.Stage.Open(str(output), Usd.Stage.LoadAll)
    final = read_geometry(reload)
    mass_written = usd_mass_snapshot(reload)
    max_errors, z_errors, unchanged_topology, unchanged_parameters = [], [], [], []
    for record in records:
        path = record["path"]
        src, dst = original[path], final[path]
        record["derived_body_bounds_m"] = [dst["body_points"].min(0), dst["body_points"].max(0)]
        err = np.abs(dst["body_points"] - src["body_points"] * SCALE)
        record["affine_vertex_max_abs_error_m"] = float(err.max())
        record["Z_max_abs_change_m"] = float(np.abs(dst["body_points"][:, 2]-src["body_points"][:, 2]).max())
        max_errors.append(record["affine_vertex_max_abs_error_m"])
        z_errors.append(record["Z_max_abs_change_m"])
        unchanged_topology.append(np.array_equal(src["faces"], dst["faces"]))
        # All properties other than points/extent/root mass/provenance must be
        # byte-identical USD values.  This explicitly catches changed offsets.
        for attr in source.GetPrimAtPath(path).GetAttributes():
            if attr.GetName() not in ["points", "extent"]:
                unchanged_parameters.append(str(attr.Get()) == str(reload.GetPrimAtPath(path).GetAttribute(attr.GetName()).Get()))
    checks = dict(standalone_no_external_used_layers=len(reload.GetUsedLayers()) == 2,
                  collision_count_28=sum(x["collision"] for x in final.values()) == 28,
                  one_visual_mesh=len(final) == 29,
                  topology_unchanged=all(unchanged_topology),
                  all_other_mesh_attributes_unchanged=all(unchanged_parameters),
                  all_meshes_same_declared_affine=max(max_errors) < 1e-8,
                  all_Z_vertices_unchanged=max(z_errors) < 1e-14,
                  bottom_origin_preserved=abs(final["/Asset/Visual/Mesh"]["body_points"][:, 2].min()) < 1e-14,
                  authored_inertia_reconstructs_full_tensor=np.allclose(mass_written["inertia_body_kg_m2"], after["inertia_body_kg_m2"], atol=2e-12, rtol=2e-6),
                  ideal_integral_matches_full_affine=ideal_affine_error <= 1e-15,
                  quantized_integral_matches_affine_tensor_norm=affine_quantization_relative <= 1e-6,
                  authored_COM_matches_reintegrated=np.allclose(mass_written["com_body_m"],after["com_body_m"],atol=2e-9,rtol=2e-6),
                  source_sha256_unchanged=sha256(SOURCE) == source_sha)
    if not all(checks.values()):
        raise ValueError("Reload check failed: " + str(checks))
    rows, sections = section_measurements({"source14.85": original, "derived12.5": final}, evidence)
    plot_geometry({"source14.85": original, "derived12.5": final}, sections, evidence)
    with (evidence / "mass_properties.csv").open("w", encoding="utf-8", newline="") as stream:
        writer=csv.writer(stream); writer.writerow(["version", "quantity", "value", "unit", "basis"])
        for version, result in [("source14.85", before), ("derived12.5", after)]:
            for name, unit in [("mass_kg", "kg"), ("material_volume_m3", "m3"),
                               ("homogeneous_density_kg_m3", "kg/m3"), ("com_body_m", "m"),
                               ("inertia_body_kg_m2", "kg*m2"), ("principal_inertia_kg_m2", "kg*m2"),
                               ("principal_axes_columns_in_body", "dimensionless"),
                               ("principal_axes_quaternion_wxyz", "dimensionless")]:
                writer.writerow([version, name, json.dumps(result[name], default=serializable), unit,
                                 "closed visual material volume; homogeneous distribution;20g assumed"])
    report = dict(schema="labsim.V0_demo04.vessel_derivation.v1", version="V0_demo04",
        source=dict(path=str(SOURCE.relative_to(ROOT)), sha256=source_sha),
        output=dict(path=str(output.relative_to(ROOT)) if output.is_relative_to(ROOT) else str(output), sha256=sha256(output)),
        builder=dict(path=str(Path(__file__).relative_to(ROOT)),sha256=sha256(Path(__file__))),
        affine=dict(axis_scale=SCALE, nominal_width_before_mm=14.85, nominal_width_after_mm=12.5,
                    scaling_about="rigid body origin; Z bottom0 unchanged", full_height_scaled=False),
        input_meshes=records, source_material_integrated=before, derived_material_integrated=after,
        source_USD_mass=usd_mass_snapshot(source), derived_USD_mass_reloaded=mass_written,
        affine_validation=dict(method="Q'=S Q S^T; I'=m*(trace(Q')Id-Q'); COM'=S COM, fixed20g mass",
            predicted_COM_m=affine_com, predicted_full_inertia_kg_m2=affine_i,
            COM_max_abs_error_m=np.abs(after["com_body_m"]-affine_com).max(),
            ideal_double_precision_integral_max_abs_error_kg_m2=ideal_affine_error,
            USD_float_quantized_integral_max_abs_error_kg_m2=quantized_affine_error,
            quantized_full_tensor_max_norm_relative_error=affine_quantization_relative,
            verification_tolerances=dict(ideal_absolute_kg_m2=1e-15, quantized_full_tensor_relative=1e-6),
            predicted_material_volume_m3=before["material_volume_m3"]*np.prod(SCALE),
            no_simple_uniform_s_squared_inertia_rule_used=True),
        checks=checks, section_method="actual triangle-plane visual sections; collision INPUT convex-hull section union bounds equal member-point bounds. Individual partition edges shown for debug, not interpreted as exterior error; area/coverage/penetration not measured here",
        sampled_heights_mm=sorted(set(row["height_mm"] for row in rows)),
        parameter_basis=dict(mass="20g retained engineering assumption, not real measured mass",
            density="uniform over material boundary, adjusted to keep20g after XY scaling; inferred numerical density, not material identification",
            dimensions="user-authorized uniform12.5/14.85 XY hypothesis, not correction of source CAD or manufacturer measurement",
            inertia="closed visual material-volume integral; 28 overlapping collider hulls are not summed for mass",
            material_contact="inherited ext02; not calibrated, rest_offset0 unchanged"),
        physical_runtime=dict(Isaac_started=False,GPU_started=False,physics_steps=0,
            PhysX_cooked_geometry_readback=False,task_success=None,native_pair_success=None,real_calibrated=False),
        limitations=["Independent derived experimental vessel, not original vessel identity or measured specimen.",
            "Sections and overlay concern input geometry only; no claim about cooked contact shape or global error bound.",
            "No local wall removal/reshaping to bypass native-seat protrusions; native fit remains a separate geometry gate.",
            "Inherited convex hull input triangulations are retained; mesh watertightness of individual collider inputs is not claimed."])
    write_json(evidence / "derivation.json", report)
    (evidence / "README.md").write_text(
        "# V0_demo04 独立12.5mm器皿派生\n\n"
        "从V0_ext02/walls28_mm.usda实际视觉材料网格与28块厚壁碰撞输入派生；"
        "所有点使用同一刚体局部仿射变换diag(12.5/14.85,12.5/14.85,1)。"
        "XY缩放，高度、底部Z=0、拓扑和全部原碰撞/材质参数不变，不对局部壁形作让位。"
        "这是经授权的新假设器皿，不能写成原CAD已修正或真实型号配套。\n\n"
        "质量继续设为20g（工程假设）。对闭合、定向的实际视觉材料边界进行有符号四面体体积积分，"
        "包括底部和内腔壁；同质材料分布假设不变。总质量固定，因此缩放后数值密度相应增大，"
        "不是同种材料实测密度。计算COM、完整惯量张量、主轴和主惯量；"
        "另由源中心二阶矩Q进行完整仿射Q'=SQSᵀ与I'=m(tr(Q')Id−Q')验证，"
        "没有套用等比缩放s²规则。用trimesh表面积分独立核对，并重载USD属性重建完整张量。\n\n"
        "尺寸来自实际顶点和完整局部变换；12.5mm是按源名义14.85mm定义的比例，"
        "源float顶点使实际包络略有数纳米舍入差异，不能当作真实精度。"
        "sections.csv覆盖底部、过渡、直壁和杯口13个实际高度。"
        "蓝线为实际视觉材料截面，橙线为28个碰撞输入点的数学凸包截面（含内部切分边，仅作调试显示）。"
        "CSV报告其几何并集的包络宽度；没有按内部切分边计算外表面误差，也没有相加重叠面积冒充实体体积。"
        "面积、覆盖误差及穿透未在此测量。这是输入几何检查，不是PhysX实际烹饪表示读取；未启动Isaac/GPU。\n\n"
        "产物：derivation.json、mass_properties.csv、sections.csv、visual_collision_overlay.png、material_sections.png。"
        "源文件SHA保持70133b2a66b1705f6de80c52e46c857b02a9811386971ea14b6a188e1edfde4b。"
        "原座配合由独立geometry gate判断，本文件不标注任务成功。\n\n"
        "复现（要求新目标文件与新证据目录）：\n\n```bash\n"
        "bash demos/lab_cuvette_external/usd_python.sh -m demos.lab_cuvette_demo04.build_vessel "
        "--output outputs/lab_cuvette_loading/V0_demo04/vessel_check/vessel_125_mm.usda "
        "--evidence outputs/lab_cuvette_loading/V0_demo04/vessel_check/evidence\n```\n", encoding="utf-8")
    write_json(evidence / "manifest.json", dict(schema="labsim.V0_demo04.vessel_evidence_manifest.v1",
        source_sha256=source_sha,asset_sha256=sha256(output),
        files=[dict(file=p.name,bytes=p.stat().st_size,sha256=sha256(p))
               for p in sorted(evidence.iterdir()) if p.is_file()]))
    print(json.dumps(dict(asset=str(output),evidence=str(evidence),sha256=sha256(output),
                         checks=checks,COM_m=after["com_body_m"],
                         principal_inertia_kg_m2=after["principal_inertia_kg_m2"]),default=serializable,indent=2))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--evidence", type=Path, default=EVIDENCE)
    args = parser.parse_args()
    build(args.output, args.evidence)
