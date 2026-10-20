"""CPU-only original-seat fit audit for the explicitly corrected 12.5 mm vessel.

Reads original source triangles, including instance proxies and all source tabs.
No Isaac process, source edit, mesh repair, collision cooking or physics occurs.
Observed intersections are witnesses, not global error bounds or an arbitrary
six-DOF path search. The source vessel is affinely scaled in XY only.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

import numpy as np
import trimesh
from pxr import Usd, UsdGeom, UsdPhysics

from demos.lab_cuvette_external.geometry import ROOT, SOURCE, normalized, tri
from demos.lab_cuvette_external.feasibility import intersects, widths


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def serial(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    raise TypeError(type(value).__name__)


def write(path, value):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, default=serial, allow_nan=False)
        stream.write('\n')


def write_csv(path, rows):
    with Path(path).open('x', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def section(mesh, z):
    return trimesh.intersections.mesh_plane(mesh, [0, 0, 1], [0, 0, float(z)])


def sample_segments(segments, step_m=.000025):
    result = []
    for a, b in segments:
        result.extend(a+(b-a)*f for f in np.linspace(0, 1, max(2, int(np.ceil(np.linalg.norm(b-a)/step_m))+1)))
    return np.asarray(result).reshape(-1, 3)


def metadata(filename, row):
    stage = Usd.Stage.Open(str(SOURCE/filename), Usd.Stage.LoadAll)
    prim = stage.GetPrimAtPath(row['path'])
    ancestors = []
    while prim and not prim.IsPseudoRoot():
        ancestors.append(dict(path=str(prim.GetPath()), type=prim.GetTypeName(),
            custom_data=prim.GetCustomData(), applied_schemas=list(prim.GetAppliedSchemas()),
            custom_attributes={a.GetName(): str(a.Get()) for a in prim.GetAttributes() if a.IsCustom()}))
        prim = prim.GetParent()
    return dict(ancestors=ancestors, bound_material=row.get('material'),
                material_subsets=row.get('subsets'),
                mechanical_role='unknown: geometry/metallic appearance is not spring/elasticity or manufacturer specification',
                elastic_or_spring_api_present=any('Deform' in str(x) or 'Spring' in str(x) for x in ancestors))


def feature_identity(rows):
    """Explicit local region evidence; no inferred manufacturer/elastic role."""
    records=[]
    for label,index in [('A',3),('B',4)]:
        mesh=tri(rows[index]);origin=np.r_[mesh.bounds.mean(0)[:2],mesh.bounds[0,2]]
        mesh.apply_translation(-origin);v=mesh.vertices;features=[]
        for sign in [-1,1]:
            selected=(v[:,0]>=-.00550001)&(v[:,0]<=-.00469999)&(sign*v[:,1]>=.00479999)&(sign*v[:,1]<=.00630001)&(v[:,2]>=.02799999)
            ids=np.flatnonzero(selected);points=v[ids]
            faces=np.flatnonzero(selected[mesh.faces].all(1))
            features.append(dict(side_y_sign=sign,source_vertex_count=len(points),
                bounds_local_m=[points.min(0),points.max(0)],dimensions_m=np.ptp(points,axis=0),
                original_transformed_vertices_local_m=points,
                processed_mesh_triangle_indices_fully_in_region=faces,
                source_prim=rows[index]['path'],separate_source_prim=False,
                designation='top-frame inward rectangular block/plate feature; functional role unknown'))
        records.append(dict(seat=label,source_prim=rows[index]['path'],features=features,
            mechanical_identity='unknown: no named spring, manufacturer role, elastic properties or separate deformable material in original source metadata',
            inference_limit='Approximate0.8x1.5x1.0mm geometry is insufficient to establish an elastic spring or permission to remove/deform it.'))
    return dict(method='Original transformed source vertices in explicitly declared local feature regions; no source modification',seats=records)


def audit(output, section_step_m=.00005, path_step_m=.00025):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    info, rows = normalized('newnew4.usd')
    vessel_info, vessel_rows = normalized('TestTube_Baked.usd')
    original = tri(vessel_rows[0])
    vessel = original.copy()
    scale = .0125/.01485
    vessel.vertices[:, :2] *= scale
    assert np.allclose(vessel.extents[:2], .0125, atol=1e-8)
    section_cache = {}
    def vessel_section(z):
        key = round(float(z), 12)
        if key not in section_cache:
            section_cache[key] = section(vessel, key)
        return section_cache[key]
    reports, section_rows, path_rows, local_rows = [], [], [], []
    for label, index in [('A', 3), ('B', 4)]:
        seat = tri(rows[index])
        origin = np.r_[seat.bounds.mean(0)[:2], seat.bounds[0, 2]]
        seat.apply_translation(-origin)
        height = float(seat.extents[2])
        hits, _, _ = seat.ray.intersects_location([[0, 0, height+.001]], [[0, 0, -1]], multiple_hits=True)
        support = float(np.max(hits[:, 2]))
        zs = np.arange(section_step_m/2, height, section_step_m)
        sections = [(float(z), section(seat, z)) for z in zs]
        final_witnesses = []
        for z, ss in sections:
            crossing = intersects(ss, vessel_section(z-support))
            w = widths(ss)
            section_rows.append(dict(seat=label, source_mesh_index=index,
                z_above_source_seat_bottom_mm=z*1000, z_in_instrument_mm=(z+origin[2])*1000,
                central_X_boundary_spacing_mm=None if w['X'] is None else w['X']*1000,
                central_Y_boundary_spacing_mm=None if w['Y'] is None else w['Y']*1000,
                final_pose_boundary_crossing_count=len(crossing)))
            if crossing:
                final_witnesses.append(dict(z_above_seat_bottom_m=z,
                    z_in_instrument_m=z+origin[2], xy_local_m=crossing))
        def pose_probe(bottom):
            witnesses = []
            for z, ss in sections:
                if z < bottom-1e-12 or z > bottom+vessel.extents[2]+1e-12:
                    continue
                crossing = intersects(ss, vessel_section(z-bottom))
                if crossing:
                    witnesses.append(dict(z_above_seat_bottom_m=z, xy_local_m=crossing))
            return witnesses
        bottoms = np.arange(height+.005, support-path_step_m/2, -path_step_m)
        bottoms = sorted(set(float(max(support, b)) for b in bottoms) | {support}, reverse=True)
        first, preceding = None, None
        for bottom in bottoms:
            witnesses = pose_probe(bottom)
            path_rows.append(dict(seat=label, vessel_bottom_above_seat_bottom_mm=bottom*1000,
                depth_below_rim_mm=(height-bottom)*1000,
                observed_crossing_sections=len(witnesses),
                first_witness_z_mm=None if not witnesses else witnesses[0]['z_above_seat_bottom_m']*1000))
            if witnesses and first is None:
                first = dict(vessel_bottom_m=bottom, depth_below_rim_m=height-bottom,
                             preceding_sample_bottom_m=preceding, witnesses=witnesses[:3])
            preceding = bottom
        # Refine only the first observed change in this one declared path.
        refined = []
        if first and first['preceding_sample_bottom_m'] is not None:
            for bottom in np.arange(first['preceding_sample_bottom_m'], first['vessel_bottom_m']-.000005, -.000025):
                witnesses = pose_probe(float(bottom))
                refined.append(dict(vessel_bottom_m=float(bottom), depth_below_rim_m=height-bottom,
                                    observed_crossing_sections=len(witnesses), witnesses=witnesses[:1]))
        # Closed vessel material permits an independent point-in-solid test.
        # Distances are closest points on actual triangles, never nearest vertices.
        placed = vessel.copy()
        placed.apply_translation([0, 0, support])
        point_reports = []
        for z in [support+.000025, height-.0005]:
            points = sample_segments(section(seat, z))
            inside = placed.contains(points)
            selected = points[inside]
            if not len(selected):
                continue
            closest, distance, face = trimesh.proximity.closest_point(placed, selected)
            order = np.argsort(distance)[::-1][:8]
            seat_closest, seat_distance, seat_face = trimesh.proximity.closest_point(seat, selected[order])
            point_reports.append(dict(z_above_seat_bottom_m=z, points_sampled=len(points),
                source_boundary_points_inside_vessel_material=int(inside.sum()),
                worst_points=[dict(seat_surface_local_m=selected[k],
                    seat_surface_instrument_m=selected[k]+origin,
                    seat_processed_triangle_index=int(seat_face[n]),
                    seat_triangle_local_m=seat.triangles[seat_face[n]],
                    distance_to_original_seat_triangle_m=seat_distance[n],
                    point_to_vessel_triangle_distance_m=distance[k],
                    nearest_vessel_surface_local_m=closest[k], vessel_triangle_index=int(face[k]),
                    vessel_triangle_local_m=placed.triangles[face[k]]) for n,k in enumerate(order)]))
        # Limited legal XY and yaw check at a known obstructed complete pose.
        # This is not a new trajectory, an inclined insertion or parameter search.
        probe_z = height-.0005
        seat_section = section(seat, probe_z)
        original_section = vessel_section(probe_z-support)
        for dx in [-.00005, 0., .00005]:
            for dy in [-.00005, 0., .00005]:
                for yaw in [-.5, -.25, 0., .25, .5]:
                    theta = np.radians(yaw)
                    R = np.array([[np.cos(theta), -np.sin(theta)], [np.sin(theta), np.cos(theta)]])
                    rotated = original_section.copy()
                    rotated[:, :, :2] = rotated[:, :, :2]@R.T+[dx, dy]
                    crossing = intersects(seat_section, rotated)
                    local_rows.append(dict(seat=label, dx_mm=dx*1000, dy_mm=dy*1000,
                        yaw_deg=yaw, z_above_seat_bottom_mm=probe_z*1000,
                        observed_boundary_crossing_count=len(crossing)))
        reports.append(dict(seat=label, source_mesh_index=index, source_prim=rows[index]['path'],
            origin_in_instrument_m=origin, dimensions_m=seat.extents,
            source_seat_watertight=seat.is_watertight,
            source_metadata=metadata('newnew4.usd', rows[index]),
            center_axis_surface_hits_above_seat_bottom_m=np.sort(hits[:, 2]),
            candidate_support_plane_m=support,
            support_definition='Highest original-seat surface hit of central downward ray; local geometric reference, not validated physical support or manufacturer datum.',
            declared_final_vessel_bottom_m=support, declared_final_depth_m=height-support,
            final_pose_witnesses=final_witnesses,
            first_observed_path_crossing=first, refined_first_change=refined,
            conservative_preinsert_bottom_m=height+.0005,
            conservative_preinsert_scope='500um above original highest seat triangle; original-seat geometry only, not whole hand/chamber/robot clearance.',
            material_overlap_point_witnesses=point_reports,
            status='BLOCKED_ORIGINAL_MATERIAL_INTERSECTION' if final_witnesses else 'NO_SAMPLED_WITNESS_NOT_CERTIFIED'))
    result = dict(schema='labsim.V0_demo04.native_fit.v1', physics_executed=False,
        real_calibrated=False, source_changed=False, native_pair_success=False,
        source_files={str((SOURCE/name).relative_to(ROOT)): sha(SOURCE/name)
                      for name in ['newnew4.usd', 'TestTube_Baked.usd']},
        input_units_and_transforms=info, original_vessel_metadata=vessel_info,
        vessel=dict(source='TestTube_Baked.usd', original_dimensions_m=original.extents,
            new_dimensions_m=vessel.extents, scale_xyz=[scale, scale, 1.],
            basis='User corrected nominal external width12.5mm and retained67.5mm height; no local wall edit.',
            closed_material_mesh=vessel.is_watertight),
        method=dict(section_spacing_m=section_step_m, path_spacing_m=path_step_m,
            first_change_refinement_m=.000025, first_z_sample_offset_m=section_step_m/2,
            boundary_intersection='actual triangle-plane segments, pairwise 2D segment crossings',
            point_depth='original seat section points classified inside closed scaled vessel, nearest triangle-surface distance',
            limited_pose_grid='3x3 XY at-50/0/+50um and5yaw angles-0.5/-0.25/0/+0.25/+0.5deg; fixed final upright support pose',
            limitations=['Observed samples and local interference witnesses; not rigorous global bounds.',
                'Centerline12.6mm boundary spacing is not a complete full-aperture classification.',
                'No arbitrary tilt, elastic deformation, alternative compliant material, active search or physical insertion tested.',
                'Source seat is not watertight; no claim of signed distance to complete closed seat solid.',
                'Local source-frame point distance measures observed material intersection, not PhysX cooking or contact accuracy.']),
        seats=reports, limited_pose_grid_all_obstructed=all(r['observed_boundary_crossing_count']>0 for r in local_rows))
    write(output/'native_fit_audit.json', result)
    write_csv(output/'full_depth_sections.csv', section_rows)
    write_csv(output/'insertion_path.csv', path_rows)
    write_csv(output/'limited_xy_yaw.csv', local_rows)
    dimensions=[dict(role='corrected_vessel', quantity='outer_X', value_mm=vessel.extents[0]*1000, basis='source triangles with authorized uniform XY scale12.5/14.85'),
                dict(role='corrected_vessel', quantity='outer_Y', value_mm=vessel.extents[1]*1000, basis='same XY scale'),
                dict(role='corrected_vessel', quantity='height_Z', value_mm=vessel.extents[2]*1000, basis='original Z unchanged')]
    for report in reports:
        for axis,value in zip('XYZ',report['dimensions_m']):
            dimensions.append(dict(role='original_seat_'+report['seat'],quantity='outer_'+axis,value_mm=float(value*1000),basis='all original source vertices and complete transforms; no feature removed'))
        dimensions.extend([dict(role='original_seat_'+report['seat'],quantity='center_ray_support_above_bottom',value_mm=report['candidate_support_plane_m']*1000,basis=report['support_definition']),
            dict(role='original_seat_'+report['seat'],quantity='declared_insertion_depth',value_mm=report['declared_final_depth_m']*1000,basis='rim minus highest center-ray support; candidate datum only'),
            dict(role='original_seat_'+report['seat'],quantity='observed_material_overlap_point_depth_max',value_mm=max(w['point_to_vessel_triangle_distance_m'] for p in report['material_overlap_point_witnesses'] for w in p['worst_points'])*1000,basis='sampled original-seat boundary point within closed cuvette material, closest triangle surface distance; not global bound')])
    write_csv(output/'dimensions.csv',dimensions)
    write(output/'source_feature_identity.json',feature_identity(rows))
    figures(output, rows, vessel, reports)
    (output/'README.md').write_text(summary(result), encoding='utf-8')
    write(output/'provenance.json',dict(implementation=str(Path(__file__).resolve().relative_to(ROOT)),
        implementation_sha256=sha(__file__),physics_executed=False,
        input_source_files=result['source_files'],output_overwrite_allowed=False))
    write(output/'artifact_hashes.json', {p.name: sha(p) for p in output.iterdir() if p.is_file()})
    return result


def figures(output, rows, vessel, reports):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2, 3, figsize=(15, 9))
    for axes_row, report in zip(axes, reports):
        seat = tri(rows[report['source_mesh_index']])
        seat.apply_translation(-report['origin_in_instrument_m'])
        bottom = report['declared_final_vessel_bottom_m']
        for ax, z, title in zip(axes_row, [.0285, .002025, .0285], ['top frame full section', 'bottom transition', 'top obstruction close-up']):
            for seg in section(seat, z): ax.plot(seg[:, 0]*1000, seg[:, 1]*1000, 'k-', linewidth=1.)
            for seg in section(vessel, z-bottom): ax.plot(seg[:, 0]*1000, seg[:, 1]*1000, color='tab:orange', linewidth=1.1)
            crossing = intersects(section(seat, z), section(vessel, z-bottom))
            if crossing:
                xy = np.asarray(crossing)*1000
                ax.scatter(xy[:, 0], xy[:, 1], c='red', s=12, zorder=4)
            ax.set(title=f"{report['seat']}: {title}; z={z*1000:.3f}mm", xlabel='local X mm', ylabel='local Y mm', aspect='equal')
            ax.grid(alpha=.25)
            if title.endswith('close-up'):
                ax.set_xlim(-6.5, -4.)
                ax.set_ylim(4.5, 6.7)
        for witness in report['material_overlap_point_witnesses']:
            if abs(witness['z_above_seat_bottom_m']-.0285)<1e-8:
                positive=[w for w in witness['worst_points'] if w['seat_surface_local_m'][1]>0]
                w=(positive or witness['worst_points'])[0];p=np.asarray(w['seat_surface_local_m'])*1000;q=np.asarray(w['nearest_vessel_surface_local_m'])*1000
                axes_row[2].plot([p[0],q[0]],[p[1],q[1]],'m-',lw=2)
                axes_row[2].annotate(f"observed point-to-triangle\n{w['point_to_vessel_triangle_distance_m']*1000:.3f}mm",p[:2],xytext=(-6.45,6.45),fontsize=8)
    fig.suptitle('Original A/B retained: black source seat; orange12.5mm vessel material boundaries; red actual crossings')
    fig.tight_layout();fig.savefig(output/'native_pair_sections.png', dpi=170);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(12,4.5))
    with (output/'insertion_path.csv').open(newline='') as stream: path=list(csv.DictReader(stream))
    for label,color in [('A','tab:blue'),('B','tab:orange')]:
        selected=[r for r in path if r['seat']==label]
        axes[0].plot([float(r['depth_below_rim_mm']) for r in selected],[int(r['observed_crossing_sections']) for r in selected],color=color,linestyle='-' if label=='A' else '--',label='Original '+label)
        report=next(r for r in reports if r['seat']==label)
        axes[1].plot([r['depth_below_rim_m']*1000 for r in report['refined_first_change']], [r['observed_crossing_sections'] for r in report['refined_first_change']],marker='o',markersize=3,color=color,linestyle='-' if label=='A' else '--',label='Original '+label)
    for ax in axes:
        ax.set(xlabel='declared insertion depth below rim mm',ylabel='observed crossing sections')
        ax.grid(alpha=.25);ax.legend()
    axes[0].set_title('Complete upright insertion segment: source geometry')
    axes[1].set_title('First observed change:25um depth samples')
    fig.tight_layout();fig.savefig(output/'insertion_path_gate.png',dpi=170);plt.close(fig)


def summary(result):
    lines=['# V0_demo04 原座完整插入段几何关口', '',
        '本证据为重新读取源网格后的纯CPU检查，未启动Isaac、未执行物理插入。原座全部凸起保留，未扩孔、删面或修改原CAD。', '',
        '器皿按用户本轮更正外宽，将原网格XY统一乘12.5/14.85，Z及底定位不变。中央12.6mm边界间距不能代表所有离轴局部轮廓。', '']
    for report in result['seats']:
        depths=[w['point_to_vessel_triangle_distance_m'] for p in report['material_overlap_point_witnesses'] for w in p['worst_points']]
        first=next((r for r in report['refined_first_change'] if r['observed_crossing_sections']),None)
        lines += [f"## 原座{report['seat']}", '', f"源prim：`{report['source_prim']}`。状态：**{report['status']}**。", '',
            f"原座底包络instrument Z={report['origin_in_instrument_m'][2]*1000:.3f}mm；中央射线最高承托面高出该包络{report['candidate_support_plane_m']*1000:.3f}mm。",
            f"完整声明下插终态深度{report['declared_final_depth_m']*1000:.3f}mm，真实截面交叉层数{len(report['final_pose_witnesses'])}；观测到座边界点落入器皿材料内的最大点到三角面距离{max(depths)*1000:.6f}mm。", '']
        if first: lines += [f"25um纵向加密中的首个已观察交叉深度为{first['depth_below_rim_m']*1000:.6f}mm。受50um截面采样限制，这不是严格最早接触深度。", '']
    lines += ['## 有限姿态诊断及停止范围', '',
        f"±50um XY的3×3组合及yaw±0.5°内5个离散角，共每座45种最终姿态，均有真实边界交叉：{result['limited_pose_grid_all_obstructed']}。该有限检查不证明所有连续姿态或斜插路径均不可能。", '',
        '保守的座几何预插入终点为器皿最低点高于原座最高三角面0.5mm；不能将其当作已装载，也不包含整手/腔壁/整臂净空通过。', '',
        '原座单一网格含局部薄片/凸起，但源几何及属性不足以证明其是可弹性退让的弹片。厂家结构作用、材料和真实形变量均为未知；本轮刚性源座不能自行假设可弯曲。', '',
        '已观察实材干涉超过名义单边余量，不应开始以扩孔、删除凸起或负rest_offset强行完成的原生配对测试。物理接触、真实校准和烹饪碰撞均未由本离线审计验证。', '',
        '复现：`bash demos/lab_cuvette_external/usd_python.sh -m demos.lab_cuvette_demo04.native_fit_audit --output <新的目录>`。', '']
    return '\n'.join(lines)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--section-step-mm', type=float, default=.05)
    parser.add_argument('--path-step-mm', type=float, default=.25)
    args=parser.parse_args()
    if args.section_step_mm<=0 or args.path_step_mm<=0: parser.error('sampling steps must be positive')
    result=audit(args.output, args.section_step_mm/1000, args.path_step_mm/1000)
    print('NATIVE_FIT', [(r['seat'], r['status']) for r in result['seats']], 'limited45_each_obstructed',result['limited_pose_grid_all_obstructed'])


if __name__=='__main__':
    main()
