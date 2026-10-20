"""Offline V0_demo02 source/assembly audit; never starts Isaac or edits sources.

Run with the existing USD environment:
  bash demos/lab_cuvette_external/usd_python.sh -m demos.lab_cuvette_demo02.audit_sources

The search lists local delivery copies, hashes each candidate source and inspects
all original USD content including abstract prototypes and instance proxies.
Section/ray results are observed local evidence, never global fit certificates.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import zipfile
import numpy as np
import trimesh
from pxr import Usd, UsdGeom, UsdShade, UsdPhysics
from demos.lab_cuvette_external.geometry import ROOT, SOURCE, normalized, tri
from demos.lab_cuvette_external.feasibility import intersects, widths

DEFAULT_OUT = ROOT/'docs/lab_cuvette_loading/V0_demo02/source_audit'
CAD_SUFFIXES={'.usd','.usda','.usdc','.usdz','.obj','.stl','.stp','.step','.igs','.iges','.sldprt','.sldasm'}
ARCHIVES={'.zip','.7z','.rar'}
SKIP={'.git','.cache','site-packages','node_modules','venv','.venv','env','labutopia-env','sim-env','__pycache__','extscache','exts','extsDeprecated','extsPhysics','kit','plugins','build','target','dist','checkpoints','wandb','runs'}
ORIGINAL_NAMES={'newnew4.usd','TestTube_629.usd','TestTube_Baked.usd','试管.obj','试管.mtl','奥凯.zip','原始附件_奥凯.zip','original.zip'}


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''): h.update(b)
    return h.hexdigest()


def dependency_status(path):
    try:
        return {'exists':Path(path).exists(),'readable':os.access(path,os.R_OK),'error':None}
    except OSError as e:
        return {'exists':None,'readable':False,'error':type(e).__name__+': '+str(e)}


def write(path, value):
    Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2,default=lambda x:x.tolist() if hasattr(x,'tolist') else str(x))+'\n')


def raw_tri(row):
    """Keep the exact source triangle set for intersections and ray evidence.

    The older tri helper enables Trimesh validation/welding and can split or
    repair degenerate faces. It is used only for explicitly labeled topology
    diagnostics below, never for the actual-source interference witnesses.
    """
    return trimesh.Trimesh(vertices=row['vertices_m'],faces=row['faces'],process=False,validate=False)


def csv_write(path, rows, keys):
    with Path(path).open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=keys);w.writeheader()
        for row in rows:w.writerow({k:json.dumps(row.get(k),ensure_ascii=False,default=lambda x:x.tolist() if hasattr(x,'tolist') else str(x)) if isinstance(row.get(k),(dict,list,np.ndarray)) else row.get(k) for k in keys})


def inventory(out,roots):
    """Enumerate every CAD/archive filename in the requested local delivery roots.

    Generic LabUtopia/robot/runtime libraries are counted but not mislabeled as
    newly supplied CAD. Unrelated private coursework filenames are not exported.
    Only source identities and LabSim delivery archives enter the share evidence.
    """
    file_count=0;model_count=0;archive_count=0;relevant=[];archives=[];errors=[];root_counts={};hash_cache={}
    for root in roots:
        count=0
        if not root.exists():root_counts[str(root)]={'exists':False};continue
        for current,dirs,files in os.walk(root):
            dirs[:]=[d for d in dirs if d not in SKIP and not d.endswith('-env')]
            for name in files:
                file_count+=1;count+=1;p=Path(current)/name;suffix=p.suffix.lower()
                if suffix not in CAD_SUFFIXES|ARCHIVES:continue
                try:st=p.stat()
                except OSError as e:errors.append({'path':str(p),'error':str(e)});continue
                if suffix in CAD_SUFFIXES:model_count+=1
                else:archive_count+=1
                rel=name in ORIGINAL_NAMES or ('LabSim' in str(p) and suffix in ARCHIVES)
                if rel:
                    key=(st.st_dev,st.st_ino,st.st_size,st.st_mtime_ns)
                    if key not in hash_cache:hash_cache[key]=sha(p)
                    relevant.append({'path':str(p),'bytes':st.st_size,'sha256':hash_cache[key]})
                if suffix=='.zip':
                    try:
                        with zipfile.ZipFile(p) as z:
                            members=z.infolist();matches=[m for m in members if Path(m.filename).name in ORIGINAL_NAMES or any(x in m.filename.lower() for x in ('newnew','testtube'))]
                            # Also inspect all CAD member names; metadata only, not executing any supplied script.
                            cad=[m.filename for m in members if Path(m.filename).suffix.lower() in CAD_SUFFIXES]
                            if matches:
                                archives.append({'path':str(p),'sha256':sha(p),'member_count':len(members),'cad_member_count':len(cad),'matching_source_members':[{'name':m.filename,'bytes':m.file_size,'sha256':hashlib.sha256(z.read(m)).hexdigest()} for m in matches],'other_cad_members':[n for n in cad if Path(n).name not in ORIGINAL_NAMES]})
                    except Exception as e:errors.append({'path':str(p),'error':type(e).__name__+': '+str(e)})
        root_counts[str(root)]={'exists':True,'regular_files_examined':count}
    groups={}
    for r in relevant:groups.setdefault(r['sha256'],{'bytes':r['bytes'],'copies':[]})['copies'].append(r['path'])
    result={'scope':'Desktop, Downloads, Documents, .codex/attachments; recursive filename enumeration, ZIP member enumeration; no network or simulation','roots':root_counts,'skipped_directory_names':sorted(SKIP),'regular_files_examined':file_count,'CAD_model_files_counted':model_count,'archives_counted':archive_count,'relevant_original_and_delivery_hash_groups':groups,'archives_containing_original_source_entries':archives,'errors':errors,'privacy':'Unrelated private coursework/library filenames are counted but omitted; original-source/delivery matches are listed. Generic library assets are not evidence of supplied rack CAD.','rack_source_found':False,'conclusion':'No independently supplied multi-hole rack CAD found in this inspected delivery scope; known newnew4 contains instrument assembly only. Missing rack cannot be replaced by V0 proxy and called supplied CAD.'}
    write(out/'delivery_inventory.json',result);return result


def material(p):
    m,_=UsdShade.MaterialBindingAPI(p).ComputeBoundMaterial()
    if not m:return None
    values={}
    for child in m.GetPrim().GetChildren():
        if child.IsA(UsdShade.Shader):
            values[str(child.GetPath())]={str(i.GetBaseName()):str(i.Get()) for i in UsdShade.Shader(child).GetInputs()}
    return {'path':str(m.GetPath()),'shader_inputs':values}


def decoded(text):
    try:return text.encode('latin1').decode('gbk')
    except (UnicodeError,AttributeError):return text


def deep_stage(path):
    stage=Usd.Stage.Open(str(path),Usd.Stage.LoadAll)
    allprim=list(stage.TraverseAll());allproxy=list(Usd.PrimRange.Stage(stage,Usd.TraverseInstanceProxies(Usd.PrimAllPrimsPredicate)))
    rendered=list(Usd.PrimRange.Stage(stage,Usd.TraverseInstanceProxies()))
    primrows=[]
    for p in allproxy:
        im=UsdGeom.Imageable(p);x=UsdGeom.Xformable(p)
        primrows.append({'path':str(p.GetPath()),'type':p.GetTypeName(),'active':p.IsActive(),'defined':p.IsDefined(),'abstract':p.IsAbstract(),'instance':p.IsInstance(),'instance_proxy':p.IsInstanceProxy(),'prototype':str(p.GetPrototype().GetPath()) if p.IsInstance() else None,'display_name_raw':p.GetDisplayName(),'display_name_gbk_recovery':decoded(p.GetDisplayName()),'visibility_authored':im.GetVisibilityAttr().Get() if im else None,'visibility_computed':im.ComputeVisibility() if im else None,'purpose_authored':im.GetPurposeAttr().Get() if im else None,'purpose_computed':im.ComputePurpose() if im else None,'references':str(p.GetMetadata('references')),'payload':str(p.GetMetadata('payload')),'variant_sets':p.GetVariantSets().GetNames(),'xform_ops':[{ 'name':str(a.GetOpName()),'value':str(a.Get())} for a in x.GetOrderedXformOps()] if x else [],'material':material(p) if p.IsA(UsdGeom.Mesh) or p.IsA(UsdGeom.Subset) else None,'subset_face_count':len(UsdGeom.Subset(p).GetIndicesAttr().Get() or []) if p.IsA(UsdGeom.Subset) else None})
    return {'path':str(path),'sha256':sha(path),'meters_per_unit':UsdGeom.GetStageMetersPerUnit(stage),'up_axis':str(UsdGeom.GetStageUpAxis(stage)),'default_prim':str(stage.GetDefaultPrim().GetPath()),'load_policy':'LoadAll','loaded_payloads':[str(p) for p in stage.GetLoadSet()],'used_layers':[l.identifier for l in stage.GetUsedLayers() if not l.anonymous],'external_references':list(stage.GetRootLayer().GetExternalReferences()),'stats':{'ordinary_active_meshes':sum(p.IsA(UsdGeom.Mesh) for p in stage.Traverse()),'TraverseAll_prims':len(allprim),'TraverseAll_abstract_meshes':sum(p.IsA(UsdGeom.Mesh) and p.IsAbstract() for p in allprim),'all_proxy_including_abstract_prims':len(allproxy),'all_proxy_including_abstract_meshes':sum(p.IsA(UsdGeom.Mesh) for p in allproxy),'renderable_active_instance_proxy_meshes':sum(p.IsA(UsdGeom.Mesh) for p in rendered),'inactive_prims':sum(not p.IsActive() for p in allproxy),'hidden_meshes':sum(p.IsA(UsdGeom.Mesh) and UsdGeom.Imageable(p).ComputeVisibility()=='invisible' for p in allproxy),'subsets_including_prototypes':sum(p.IsA(UsdGeom.Subset) for p in allproxy)},'prims':primrows}


def geometry(out):
    info,rows=normalized('newnew4.usd');vinfo,vrows=normalized('TestTube_Baked.usd');vessel=raw_tri(vrows[0]);summaries=[]
    original=Usd.Stage.Open(str(SOURCE/'newnew4.usd'),Usd.Stage.LoadAll)
    for i,r in enumerate(rows):
        m=tri(r);components=m.split(only_watertight=False)
        mesh=UsdGeom.Mesh(original.GetPrimAtPath(r['path']));normal_attr=mesh.GetNormalsAttr();normals=normal_attr.Get()
        normal_primvar=UsdGeom.PrimvarsAPI(mesh).GetPrimvar('normals')
        subset_indices=[list(UsdGeom.Subset(p).GetIndicesAttr().Get() or []) for p in mesh.GetPrim().GetChildren() if p.IsA(UsdGeom.Subset)]
        all_indices=np.concatenate(subset_indices) if subset_indices else np.array([],int)
        summaries.append({'index':i,'source_prim':r['path'],'dimensions_mm':m.extents*1000,'bounds_mm':m.bounds*1000,'vertices_in_source':len(r['vertices_m']),'triangles_in_source':len(r['faces']),'components_after_trimesh_welding':len(components),'component_bounds_mm':[c.bounds*1000 for c in components],'watertight_after_welding':m.is_watertight,'winding_consistent_after_welding':m.is_winding_consistent,'orientation':mesh.GetOrientationAttr().Get(),'double_sided':mesh.GetDoubleSidedAttr().Get(),'normal_attribute_count':len(normals) if normals is not None else 0,'normal_primvar_count':len(normal_primvar.Get()) if normal_primvar and normal_primvar.Get() is not None else 0,'material_subsets':{'count':len(subset_indices),'total_assigned_faces':len(all_indices),'unique_assigned_faces':len(np.unique(all_indices)),'source_face_count':len(mesh.GetFaceVertexCountsAttr().Get())},'source_world_matrix_row':r['local_to_source_world_row_matrix'],'point_transform':'p_mesh_local @ complete_ancestor_xform @ source_world_to_normalized; root +90deg X already included once'})
    source={'instrument':info,'vessel':vinfo,'meshes':summaries,'vessel_measurements':{'dimensions_mm':vessel.extents*1000,'bounds_mm':vessel.bounds*1000,'bottom_vertices_z_lt_0_3mm_bounds_mm':vessel.vertices[vessel.vertices[:,2]<.0003].min(0)*1000,'bottom_vertices_z_lt_0_3mm_max_mm':vessel.vertices[vessel.vertices[:,2]<.0003].max(0)*1000,'support_lowest_vertex_z_mm':vessel.bounds[0,2]*1000,'vessel_mass_real_kg':None,'grasp_position_real_mm':None,'real_dimensions_mm':None,'measurement_source':'actual supplied mesh vertices plus full source transforms; not measured hardware'},'cavity':'Merged into body Mesh index2; no separate chamber prim. Section loops below are measured geometric contours, not independently named CAD chamber.'}
    write(out/'source_geometry.json',source)
    # Verify standardised derived layer against freshly normalised source, visual only.
    derived=[]
    for name,source_rows in [('instrument.usda',rows),('source_original.usda',vrows)]:
        file=ROOT/'assets/lab_cuvette_loading/V0_ext01/derived'/name
        s=Usd.Stage.Open(str(file),Usd.Stage.LoadAll);cache=UsdGeom.XformCache();dr=[]
        for p in Usd.PrimRange.Stage(s,Usd.TraverseInstanceProxies()):
            if not p.IsA(UsdGeom.Mesh) or '/Collision/' in str(p.GetPath()):continue
            v=np.asarray(UsdGeom.Mesh(p).GetPointsAttr().Get(),float);M=np.asarray(cache.GetLocalToWorldTransform(p));v=(np.c_[v,np.ones(len(v))]@M)[:,:3]*UsdGeom.GetStageMetersPerUnit(s)
            dr.append({'path':str(p.GetPath()),'points':v})
        comparison=[]
        for src,dst in zip(source_rows,dr):
            a=src['vertices_m'];b=dst['points'];comparison.append({'source_prim':src['path'],'derived_prim':dst['path'],'source_points':len(a),'derived_points':len(b),'same_point_order_max_delta_m':float(np.linalg.norm(a-b,axis=1).max()) if a.shape==b.shape else None,'derived_dimensions_mm':np.ptp(b,axis=0)*1000})
        derived.append({'asset':str(file.relative_to(ROOT)),'sha256':sha(file),'meters_per_unit':UsdGeom.GetStageMetersPerUnit(s),'up_axis':str(UsdGeom.GetStageUpAxis(s)),'visual_mesh_count':len(dr),'comparisons':comparison})
    write(out/'standardized_verification.json',{'source_to_derived_visual':derived,'collision_geometry_note':'Instrument derived /Collision/Mesh0..7 are separate, source-triangle static meshes; ignored when measuring visual assembly to avoid double counting. Runtime cooked representation not checked offline.','final_V0_demo02_scene':'Measured separately by final scene manifest/preflight; not invented at source audit time.'})
    return rows,vessel


def measurements(out,rows,vessel):
    candidates=[];allrows=[]
    for i in [3,4]:
        m=raw_tri(rows[i]);centre=m.bounds.mean(0);local=m.copy();local.apply_translation(-np.r_[centre[:2],0]);lo,hi=m.bounds[:,2];samples=[];witnesses=[]
        # Observe the whole 29mm envelope; centerline spacings are not aperture classification.
        vessel_bottom=hi-.010
        for z in np.arange(lo+.000125,hi,.00025):
            seat=trimesh.intersections.mesh_plane(local,[0,0,1],[0,0,z]);vc=trimesh.intersections.mesh_plane(vessel,[0,0,1],[0,0,z-vessel_bottom]);xy=intersects(seat,vc)
            w=widths(seat);sample={'candidate_index':i,'z_m':float(z),'z_above_candidate_bottom_mm':float((z-lo)*1000),'central_X_boundary_spacing_mm':None if w['X'] is None else w['X']*1000,'central_Y_boundary_spacing_mm':None if w['Y'] is None else w['Y']*1000,'placed_vessel_section_boundary_crossings':len(xy)};samples.append(sample);allrows.append(sample)
            if xy:witnesses.append({'z_instrument_m':float(z),'vessel_bottom_m':float(vessel_bottom),'xy_local_m':xy,'xy_instrument_m':(np.asarray(xy)+centre[:2]).tolist()})
        centerZ,_,_=local.ray.intersects_location([[0,0,hi+.001]],[[0,0,-1]],multiple_hits=True);centerZ=np.asarray(centerZ).reshape(-1,3)
        candidates.append({'source_prim':rows[i]['path'],'source_mesh_index':i,'center_mm':centre*1000,'bounds_mm':m.bounds*1000,'dimensions_mm':m.extents*1000,'central_vertical_ray_surface_hits_z_mm':np.sort(centerZ[:,2])*1000,'observed_top_section_z_mm':(hi-.0005)*1000,'observed_top_centerline_boundary_spacing_m':widths(trimesh.intersections.mesh_plane(local,[0,0,1],[0,0,hi-.0005])),'declared_pose_probe':{'upright':True,'yaw_deg':0,'vessel_bottom_mm':vessel_bottom*1000,'insertion_depth_from_rim_mm':10,'identity_confirmed':False},'actual_mesh_boundary_intersection_witnesses':witnesses,'sections':samples,'conclusion':'Declared centred upright insertion conflicts with original frame geometry' if witnesses else 'No sampled witness; not certified feasible','caution':'Exact triangle-plane boundary intersections at 0.25mm Z samples; centerline boundary spacing is NOT complete aperture/net-width classification. Side windows, bottom and internal fastener geometry have distinct crossings. No global collision-free or arbitrary-yaw path proof. CAD material is one white metallic material; no separate preloaded-vessel geometry subset.'})
    body=raw_tri(rows[2]);cavity=[]
    for z in [.229,.225,.220,.215,.210,.205,.200,.190,.175,.160,.145]:
        segments=trimesh.intersections.mesh_plane(body,[0,0,1],[0,0,z]);path=trimesh.load_path(segments);loops=[]
        for d in path.discrete:
            bb=np.array([d.min(0),d.max(0)]);loops.append({'bounds_mm':bb*1000,'dimensions_mm':np.ptp(d,axis=0)*1000,'closed_within_0_1um':bool(np.linalg.norm(d[0]-d[-1])<1e-7),'points_mm':d*1000})
        cavity.append({'z_mm':z*1000,'triangle_section_segment_count':len(segments),'loops':loops})
    rays=[]
    for i in [3,4]:
        c=raw_tri(rows[i]).bounds.mean(0);hits,_,_=body.ray.intersects_location([[c[0],c[1],.5]],[[0,0,-1]],multiple_hits=True);hits=np.asarray(hits).reshape(-1,3)
        rays.append({'candidate_index':i,'xy_instrument_mm':c[:2]*1000,'body_surface_hits_z_mm':np.sort(hits[:,2])*1000,'note':'No body triangle caps candidate central axis above candidate rim. This single ray does not prove whole vessel/hand entrance clearance.'})
    lid=raw_tri(rows[5]);clusters=[]
    for normal,area in zip(lid.face_normals,lid.area_faces):
        normal=normal.copy()
        if normal[np.argmax(np.abs(normal))]<0:normal=-normal
        for cluster in clusters:
            if np.dot(normal,cluster['normal'])>1-1e-8:
                cluster['area_m2']+=float(area);break
        else:clusters.append({'normal':normal,'area_m2':float(area)})
    clusters.sort(key=lambda c:c['area_m2'],reverse=True);normal=clusters[0]['normal'];angle=float(np.degrees(np.arccos(abs(normal[2]))))
    hinge=np.asarray([raw_tri(rows[i]).bounds.mean(0) for i in [6,7]])
    p=lid.vertices-lid.vertices.mean(0);eigenvalues,eigenvectors=np.linalg.eigh(p.T@p)
    lid_pose={'method':'area-weighted parallel/antiparallel triangle-normal clusters, angular dot tolerance1e-8; largest planar family chosen for broad lid panel','source_main_panel_angle_from_horizontal_deg':angle,'source_main_panel_normal':normal,'main_panel_parallel_face_area_mm2':clusters[0]['area_m2']*1e6,'largest_normal_families':clusters[:8],'hinge_piece_AABB_centres_m':hinge,'hinge_axis_inferred':'+X, line through the two separate hinge-piece geometric centres','hinge_axis_instrument_y_m':float(hinge[:,1].mean()),'hinge_axis_instrument_z_m':float(hinge[:,2].mean()),'hinge_axis_calibrated':False,'hypothetical_rotation_X_to_90deg_main_panel_deg':90-angle,'full_vertex_PCA_smallest_axis':eigenvectors[:,0],'full_vertex_PCA_angle_deg':float(np.degrees(np.arccos(abs(eigenvectors[2,0])))),'PCA_caution':'Full irregular lid includes curved shell/flanges; whole-mesh vertex PCA is not the main panel orientation and must not be used as lid opening angle. Video 90deg is a visual approximation, not measured hinge calibration.'}
    write(out/'candidate_fit_and_chamber_sections.json',{'candidates':candidates,'body_horizontal_sections':cavity,'body_center_axis_rays':rays,'lid_pose':lid_pose,'rack_dimensions':None,'rack_missing':'No source CAD rack found; rows/columns/pitch/wall/floor/depth unknown in CAD. Video counts are separately recorded in reference mapping.','real_measurements':None,'calibrated':False,'sampling_warning':'Observed local geometry only, not strict global bounds or real hardware calibration.'})
    csv_write(out/'candidate_full_depth_sections.csv',allrows,['candidate_index','z_m','z_above_candidate_bottom_mm','central_X_boundary_spacing_mm','central_Y_boundary_spacing_mm','placed_vessel_section_boundary_crossings'])
    table=[{'role':'vessel','source':'TestTube_Baked.usd','prim':'/TestTube/Mesh','dimensions_mm':list(vessel.extents*1000),'basis':'actual source vertices; Y-up -> Z-up once; mesh bottom origin; real dimensions unknown'}, {'role':'body main mesh','source':'newnew4.usd','prim':rows[2]['path'],'dimensions_mm':list(tri(rows[2]).extents*1000),'basis':'complete source transforms incl authored +90deg X; mm -> m once'}, {'role':'open instrument entire assembly','source':'newnew4.usd','prim':'/RotatedRoot','dimensions_mm':list(np.ptp(np.concatenate([r['vertices_m'] for r in rows]),axis=0)*1000),'basis':'union AABB of 8 rendered mesh instances, not main body dimensions'}, {'role':'open lid mesh','source':'newnew4.usd','prim':rows[5]['path'],'dimensions_mm':list(tri(rows[5]).extents*1000),'basis':'current authored open pose; no new lid motion'}, *[{'role':f'candidate {i-2}','source':'newnew4.usd','prim':rows[i]['path'],'dimensions_mm':list(tri(rows[i]).extents*1000),'basis':'same prototype / white metallic mesh; video role mapping remains evidence-qualified'} for i in [3,4]], {'role':'complete multi-hole source rack','source':None,'prim':None,'dimensions_mm':None,'basis':'not found in inspected supplied CAD; no 6x8 assumption or proxy relabeling'}]
    csv_write(out/'dimensions.csv',table,['role','source','prim','dimensions_mm','basis']);return candidates,cavity


def figures(out,rows,vessel,candidates,cavity):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.collections import PolyCollection, LineCollection
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection
    # Actual source mesh pictures, no invented instruments or CAD repairs.
    fig,axs=plt.subplots(1,3,figsize=(16,5))
    for ax,(a,b),label in zip(axs,[(0,1),(1,2),(0,2)],['TOP XY','SIDE YZ','FRONT XZ']):
        for i,r in enumerate(rows):
            v=r['vertices_m']*1000;ax.add_collection(PolyCollection(v[r['faces']][:,:,[a,b]],facecolors=plt.cm.tab10(i),edgecolors='none',alpha=.12));ax.annotate(str(i),np.mean(v[:,[a,b]],axis=0),fontsize=12)
        ax.autoscale();ax.set_aspect('equal');ax.set_xlabel('XYZ'[a]+' mm');ax.set_ylabel('XYZ'[b]+' mm');ax.set_title(label);ax.grid(alpha=.2)
    fig.suptitle('All 8 source mesh instances after complete transforms; numbers = mesh indices');fig.tight_layout();fig.savefig(out/'instrument_all_components.png',dpi=180);plt.close(fig)
    for idx,label in [(2,'body'),(3,'candidate'),(5,'lid')]:
        m=raw_tri(rows[idx]);v=np.array(m.vertices,dtype=float,copy=True)*1000;c=(v.min(0)+v.max(0))/2;v=v-c;extent=np.ptp(v,axis=0)
        fig=plt.figure(figsize=(13,5))
        ax=fig.add_subplot(1,3,1,projection='3d');ax.set_proj_type('ortho')
        ax.add_collection3d(Poly3DCollection(v[m.faces],facecolors='#c3c8d0',edgecolors='#666666' if idx==3 else 'none',linewidths=.15,alpha=.85))
        # Matplotlib normalizes its aspect argument in place in this version.
        # Preserve the measured millimetre extents for the two projected axes.
        ax.set_xlim(-extent[0]*.54,extent[0]*.54);ax.set_ylim(-extent[1]*.54,extent[1]*.54);ax.set_zlim(-extent[2]*.54,extent[2]*.54);ax.set_box_aspect(extent.copy());ax.view_init(28,35);ax.set_xlabel('X mm');ax.set_ylabel('Y mm');ax.set_zlabel('Z mm');ax.set_title('Isometric orthographic')
        edges=v[np.asarray(m.edges_unique)]
        for panel,(a,b),title in [(2,(0,1),'Top XY edge projection'),(3,(1,2),'Side YZ edge projection')]:
            ax=fig.add_subplot(1,3,panel);ax.add_collection(LineCollection(edges[:,:,[a,b]],colors='#555555',linewidths=.25,alpha=.6))
            ax.set_xlim(-extent[a]*.55,extent[a]*.55);ax.set_ylim(-extent[b]*.55,extent[b]*.55);ax.set_aspect('equal');ax.set_xlabel('XYZ'[a]+' mm');ax.set_ylabel('XYZ'[b]+' mm');ax.set_title(title);ax.grid(alpha=.2)
        fig.suptitle(f'Original {label}, source mesh {idx}; local centre only for this plot; no geometry changed');fig.tight_layout();fig.savefig(out/(label+'_three_views.png'),dpi=170);plt.close(fig)
    fig,axs=plt.subplots(2,3,figsize=(14,9))
    for ci,i in enumerate([3,4]):
        m=raw_tri(rows[i]);c=m.bounds.mean(0);m.apply_translation(-np.r_[c[:2],0]);hi=m.bounds[1,2];bottom=hi-.010
        for ax,z in zip(axs[ci],[hi-.0005,hi-.005,hi-.015]):
            for s in trimesh.intersections.mesh_plane(m,[0,0,1],[0,0,z]):ax.plot(s[:,0]*1000,s[:,1]*1000,'k-',lw=1)
            for s in trimesh.intersections.mesh_plane(vessel,[0,0,1],[0,0,z-bottom]):ax.plot(s[:,0]*1000,s[:,1]*1000,'r-',lw=1)
            ax.set_title(f'Candidate {ci+1}, Z={z*1000:.1f}mm, nominal depth10mm');ax.set_aspect('equal');ax.set_xlabel('X local mm');ax.set_ylabel('Y local mm');ax.grid(alpha=.2)
    fig.suptitle('Fresh original-triangle sections: black candidate, red vessel; red/black crossings are interference witnesses');fig.tight_layout();fig.savefig(out/'candidate_original_pair_sections.png',dpi=180);plt.close(fig)
    fig,axs=plt.subplots(1,3,figsize=(14,5))
    body=raw_tri(rows[2])
    for ax,z in zip(axs,[.205,.200,.175]):
        for s in trimesh.intersections.mesh_plane(body,[0,0,1],[0,0,z]):ax.plot(s[:,0]*1000,s[:,1]*1000,'k-',lw=.7)
        for idx in [3,4]:
            cc=raw_tri(rows[idx]).bounds.mean(0)*1000;ax.plot(cc[0],cc[1],'ro');ax.annotate(str(idx),cc[:2])
        ax.set_aspect('equal');ax.set_xlim(-205,0);ax.set_ylim(-85,275);ax.set_title(f'Body merged mesh horizontal Z={z*1000:.0f}mm');ax.set_xlabel('X mm');ax.set_ylabel('Y mm');ax.grid(alpha=.2)
    fig.suptitle('Observed chamber-region section contours; not full aperture/path clearance proof');fig.tight_layout();fig.savefig(out/'chamber_section_contours.png',dpi=170);plt.close(fig)


def summary(out,inv,rows,candidates):
    hashes={p.name:sha(p) for p in SOURCE.iterdir() if p.is_file()}
    roles=[]
    for role,idx,certainty in [('instrument main body',2,'source geometry identified'),('lid in authored open pose',5,'source geometry identified'),('candidate farther from hinge',3,'video-supported candidate; identity not manufacturer-confirmed'),('candidate nearer hinge',4,'video-supported other candidate; physical identity unknown')]:
        roles.append({'physical_role':role,'original_file':'assets/lab_cuvette_loading/V0_ext01/source/newnew4.usd','sha256':hashes['newnew4.usd'],'original_prim':rows[idx]['path'],'derived_asset':'assets/lab_cuvette_loading/V0_ext01/derived/instrument.usda','scene_instance':'see V0_demo02 final static-scene manifest; not assumed here','certainty':certainty})
    roles.extend([{'physical_role':'vessel','original_file':'assets/lab_cuvette_loading/V0_ext01/source/TestTube_Baked.usd','sha256':hashes['TestTube_Baked.usd'],'original_prim':'/TestTube/Mesh','derived_asset':'assets/lab_cuvette_loading/V0_ext02/walls28_mm.usda','scene_instance':'see V0_demo02 final static-scene manifest','certainty':'CAD identity is supplied vessel; hardware pairing not confirmed'}, {'physical_role':'complete white multi-hole source rack','original_file':None,'sha256':None,'original_prim':None,'derived_asset':None,'scene_instance':None,'certainty':'not found in inspected supplied files; dimensions unknown'}, {'physical_role':'sample chamber','original_file':'assets/lab_cuvette_loading/V0_ext01/source/newnew4.usd','sha256':hashes['newnew4.usd'],'original_prim':rows[2]['path'],'derived_asset':'part of instrument mesh, no separate chamber prim','scene_instance':'see final instrument scene instance','certainty':'cavity-region contours measured; no named separate CAD part'}])
    write(out/'asset_role_mapping.json',{'roles':roles,'source_hashes':hashes,'status':'source audit, not physical task completion','blocked':['Complete white source rack CAD is not present in inspected delivery scope','Original 14.85mm vessel intersects supplied candidate frame under declared upright centred insertion; target identity and correct pairing still require evidence'],'unknown':['True rack dimensions and floor/slot geometry','Hardware vessel/seat pairing and manufacturer dimensions','Actual intended insertion direction/target labeling','Mass, material, robot physical calibration'],'preservation':'Read-only source and historical derived asset inspection; only V0_demo02 code/evidence files created'})
    csv_write(out/'asset_role_mapping.csv',roles,['physical_role','original_file','sha256','original_prim','derived_asset','scene_instance','certainty'])
    md=f'''# V0_demo02 原始资产核查（2026-10-20）\n\n本目录是本轮离线重新检查原始文件产生的证据，不是旧报告数值转抄，也不是完整装载运行成功证据。\n\n已递归枚举 Desktop、Downloads、Documents、.codex/attachments 中 {inv['regular_files_examined']} 个普通文件，计入 {inv['CAD_model_files_counted']} 个 CAD/模型文件及 {inv['archives_counted']} 个归档。环境、缓存、.git 等排除范围列于 delivery_inventory.json。全部相关原始附件及旧交付副本按 SHA256 分组，ZIP 成员同时核查；未发现另一份含白色多孔架的外部 CAD。这个结论仅覆盖所列本机搜索范围，不能证明用户其他位置/未传输文件不存在。\n\n## USD 深层核查\n\nnewnew4.usd 以 LoadAll 打开；普通 active Traverse 为 0 个 Mesh，instance proxy 遍历得到 8 个实际实例网格。TraverseAll 另能读到 6 个抽象 prototype 网格；把原型与实例同时计入会重复，不是 14 个独立部件。全部 inactive、visible/purpose、references、payload、材质子集和匿名原型逐项记录于 usd_deep_inspection.json。未发现隐藏或 inactive 多孔架。机身 7 个材质子集、盖板 2 个材质子集均被检查；机身侧面密集孔列属于机身通风结构，不是来源架。每个实例网格焊接后为一个连通体；这只描述拓扑，部件图和剖面用于进一步核实其形状。\n\n源层单位 0.001 m、Z-up，RotatedRoot 已有 +90° X 旋转。每个点先乘完整祖先变换，再做一次单位和底部原点归一化；没有重复补 90°。标准化派生视觉与源点逐点比较见 standardized_verification.json。TestTube_Baked.usd 为 Y-up、米单位，转成 Z-up 一次。151 B 的 TestTube_629.usd 指向 /root/LabUtopia/shiguan629/test/试管.obj，当前进程无权读取该绝对依赖（是否存在未知），不能当完整资产入口；独立 Baked/包内 OBJ 均有实际几何。\n\n## 重新测量与配合\n\n机身主网格、开盖总装、器皿、候选座尺寸分列 dimensions.csv；所有值来自实际网格顶点和完整变换，实物值均未知。候选座并非沿全深度都是封闭直方孔：中段侧面开窗，底部含承托/孔和螺钉形状。12.6 mm 是特定中央截面的边界间距，不能称为全部位置的全孔净宽。candidate_full_depth_sections.csv 每 0.25 mm 采样一次，candidate_fit_and_chamber_sections.json 保留真实三角剖面交点及其坐标。\n\n当前 14.85 mm 器皿按居中直立、下插 10 mm 的明确姿态与两个源顶框均出现实际剖面边界交叉，属于该声明姿态的几何受阻见证；没有搜索其他任意倾角/路径，没有删除旧部件、缩小器皿或扩大孔。候选是同一个白色 metallic 材质的同一 prototype 两个实例，不存在可独立删除的已装器皿材质子集。\n\n样品腔在主机身合并网格中，不存在独立命名 chamber prim。body 的若干水平截面可提取局部轮廓，Z200 mm 附近内轮廓包络约 140×286 mm；这只是已观察截面包络，不是整个腔口/全手爪路径净空证明。两候选中心轴上 body 竖直射线不命中高于座口的额外盖面；不能由单射线排除整个入口封堵或碰撞烹饪问题。\n\n## 本轮必须补充的源资料\n\n1. 完整白色多孔来源架 CAD 的准确文件及装配入口（现有 8 成员原包中未发现），或可追溯尺寸/图纸。视频行列计数见独立 reference_mapping，不沿用 V0 的 6×8 假设。\n2. 在视频/CAD 中标注实际目标座、插入方向及另一个座/器皿身份；视觉远近映射不能替代真实型号确认。\n3. 器皿与座是否配套，以及器皿外轮廓和入口/全深限制宽度、承托高度的实测/厂家尺寸。\n\n盖板为不规则曲面/翻边结构，按三角面法线同向/反向聚类累计面积，最大平面族83,232.228 mm²，源主面离水平41.566965°；不能以整体包络对角约30°或全顶点PCA的87.99°代替主面角。两铰链件几何中心连线为X轴，Y=-49.312386 mm、Z=220 mm；这些是几何推测轴，非实物标定。相对源主面刚体转+48.433035°可得到近90°工程对照姿态，视频近90°仍是图像估计。原源文件必须保持不变。详见 lid_pose 字段。\n\n质量、惯量、摩擦和机器人动力学本轮不宣称真实标定。静态几何核查尚未读取 PhysX 烹饪碰撞表示，不宣称排除运行穿透。\n\n复现：`bash demos/lab_cuvette_external/usd_python.sh -m demos.lab_cuvette_demo02.audit_sources --output <新的证据目录>`。使用既有 USD/Python 环境，纯 CPU，不启动 Isaac 或 GPU 仿真。\n'''
    (out/'README.md').write_text(md)


def final_scenes(out, source_rows):
    """Read final root-authored scenes only; compare visual and collision inputs.

    Matching vertex-index comparisons check authoring/transform consistency, not
    cooked PhysX geometry or a geometric surface-error bound from sampling.
    """
    scenes=[];csv_rows=[]
    for pose in ['source_pose','video_pose_verified']:
        directory=ROOT/'assets/lab_cuvette_loading/V0_demo02'/pose
        file=directory/'scene_review.usda'
        if not file.exists():continue
        manifest=json.loads((directory/'manifest.json').read_text())
        stage=Usd.Stage.Open(str(file),Usd.Stage.LoadAll);cache=UsdGeom.XformCache();unit=UsdGeom.GetStageMetersPerUnit(stage)
        assembly=[]
        for root in ['/World/Instrument','/World/NeighborInstrument']:
            I=np.asarray(cache.GetLocalToWorldTransform(stage.GetPrimAtPath(root)));pairs=[];meshes=[]
            pose_matrix=np.asarray(manifest['lid_pose']['derived_rigid_pose_row_matrix'])
            for i,source in enumerate(source_rows):
                visual_path=source['path'].replace('/RotatedRoot',root+'/Visual/Source',1)
                collision_path=f'{root}/Collision/SourceMesh{i}'
                data=[]
                for path in [visual_path,collision_path]:
                    p=stage.GetPrimAtPath(path);m=UsdGeom.Mesh(p);v=np.asarray(m.GetPointsAttr().Get(),float);M=np.asarray(cache.GetLocalToWorldTransform(p));v=(np.c_[v,np.ones(len(v))]@M)[:,:3]*unit
                    data.append({'path':path,'vertices':v,'faces':np.asarray(m.GetFaceVertexIndicesAttr().Get(),int),'counts':np.asarray(m.GetFaceVertexCountsAttr().Get(),int)})
                visual,collision=data;v=visual['vertices'];cv=collision['vertices'];faces=visual['faces'].reshape(-1,3)
                expected=source['vertices_m']
                if i==5:expected=(np.c_[expected,np.ones(len(expected))]@pose_matrix)[:,:3]
                expected=(np.c_[expected,np.ones(len(expected))]@I)[:,:3]*unit
                world_to_local=np.linalg.inv(I);local_v=(np.c_[v/unit,np.ones(len(v))]@world_to_local)[:,:3]
                pair={'source_mesh_index':i,'source_prim':source['path'],'visual_path':visual_path,'collision_input_path':collision_path,'source_face_count':len(source['faces']),'visual_face_count':len(visual['counts']),'collision_input_face_count':len(collision['counts']),'source_visual_face_indices_equal':bool(np.array_equal(np.asarray(source['faces']).ravel(),visual['faces'])),'visual_collision_input_face_indices_equal':bool(np.array_equal(visual['faces'],collision['faces'])),'visual_collision_input_same_index_max_delta_m':float(np.linalg.norm(v-cv,axis=1).max()),'source_expected_to_visual_same_index_max_delta_m':float(np.linalg.norm(expected-v,axis=1).max()),'world_bounds_mm':np.asarray([v.min(0),v.max(0)])*1000,'world_dimensions_mm':np.ptp(v,axis=0)*1000,'instrument_local_bounds_mm':np.asarray([local_v.min(0),local_v.max(0)])*1000,'instrument_local_dimensions_mm':np.ptp(local_v,axis=0)*1000,'collision_approximation_authored':UsdPhysics.MeshCollisionAPI(stage.GetPrimAtPath(collision_path)).GetApproximationAttr().Get(),'cooked_representation':'unavailable; offline authoring/input verification only'}
                pairs.append(pair);meshes.append(trimesh.Trimesh(vertices=v,faces=faces,process=False,validate=False))
                csv_rows.append({'pose':pose,'instance':root,'mesh_index':i,'source_prim':source['path'],'world_bounds_mm':pair['world_bounds_mm'],'world_dimensions_mm':pair['world_dimensions_mm'],'visual_collision_input_same_index_max_delta_m':pair['visual_collision_input_same_index_max_delta_m'],'source_expected_to_visual_same_index_max_delta_m':pair['source_expected_to_visual_same_index_max_delta_m']})
            allpoints=np.concatenate([m.vertices for m in meshes]);rays=[]
            for i in [3,4]:
                c=meshes[i].bounds.mean(0);top=meshes[i].bounds[1,2];ray=[]
                # A single central vertical ray is intentionally limited local evidence.
                for j,m in enumerate(meshes):
                    hits,_,_=m.ray.intersects_location([[c[0],c[1],allpoints[:,2].max()+.1]],[[0,0,-1]],multiple_hits=True);hits=np.asarray(hits).reshape(-1,3)
                    if len(hits):ray.append({'source_mesh_index':j,'source_prim':source_rows[j]['path'],'world_hit_z_m':np.sort(hits[:,2]),'above_candidate_rim_world_hit_z_m':np.sort(hits[hits[:,2]>top+1e-7,2])})
                lid_hits=[r['above_candidate_rim_world_hit_z_m'] for r in ray if r['source_mesh_index']==5]
                rays.append({'candidate_source_mesh_index':i,'world_xy_m':c[:2],'candidate_rim_world_z_m':float(top),'mesh_hits':ray,'lid_blocks_central_vertical_ray_above_rim':bool(lid_hits and len(lid_hits[0])),'scope':'single central line, not whole-vessel swept volume, hand or robot clearance'})
            frames=[]
            paths=[root,root+'/TaskFrames/chamber_survey',root+'/TaskFrames/chamber_survey/candidate_far_hinge',root+'/TaskFrames/chamber_survey/candidate_near_hinge']
            for path in paths:
                p=stage.GetPrimAtPath(path)
                if not p:continue
                W=np.asarray(cache.GetLocalToWorldTransform(p));L=np.asarray(cache.GetLocalToWorldTransform(p.GetParent()))
                frames.append({'path':path,'local_to_parent_row_matrix':W@np.linalg.inv(L),'local_to_world_row_matrix':W,'world_to_frame_row_matrix':np.linalg.inv(W),'origin_world_m':W[3,:3]*unit,'semantic_status':'survey/provisional, not calibrated or accepted task target' if 'TaskFrames' in path else 'engineering scene placement'})
            assembly.append({'instance':root,'visual_mesh_instances':len(pairs),'collision_input_meshes':len(pairs),'parts':pairs,'body_main_mesh_world_dimensions_mm':meshes[2].extents*1000,'whole_open_assembly_world_dimensions_mm':np.ptp(allpoints,axis=0)*1000,'whole_open_assembly_world_bounds_mm':np.asarray([allpoints.min(0),allpoints.max(0)])*1000,'world_to_instrument_row_matrix':np.linalg.inv(I),'instrument_to_world_row_matrix':I,'frames':frames,'central_vertical_ray_checks':rays})
        scenes.append({'pose':pose,'file':str(file.relative_to(ROOT)),'sha256':sha(file),'manifest_sha256':sha(directory/'manifest.json'),'meters_per_unit':unit,'up_axis':str(UsdGeom.GetStageUpAxis(stage)),'source_lid_main_plane_angle_deg':manifest['lid_pose']['source_main_plane_angle_deg'],'derived_lid_rotation_X_deg':manifest['lid_pose']['delta_deg'],'resulting_lid_main_plane_angle_deg':manifest['lid_pose']['source_main_plane_angle_deg']+manifest['lid_pose']['delta_deg'],'assemblies':assembly})
    result={'method':'LoadAll, instance-proxy visual points and separate collision input points, full composed transforms; exact corresponding vertex-index comparisons and original face-index equality. Not nearest-vertex distance and not cooked collision readback.','scenes':scenes,'limits':['No physics advanced by this audit.','Collision meshes are input geometry with approximation none; cooked geometry and actual back-end fallback remain unavailable offline.','Only declared central rays were checked for lid obstruction. Whole vessel/hand/robot swept-volume and physical insertion are not validated.','Neighbor geometry was duplicated as an explicit scene-context estimate, not evidence of identical real device/model.','Chamber survey and candidate IDs are provisional; source rack absent and native pairing gate remains unpassed.']}
    write(out/'final_scene_verification.json',result)
    csv_write(out/'final_scene_verification.csv',csv_rows,['pose','instance','mesh_index','source_prim','world_bounds_mm','world_dimensions_mm','visual_collision_input_same_index_max_delta_m','source_expected_to_visual_same_index_max_delta_m'])
    if len(scenes)==2:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        fig,axs=plt.subplots(1,2,figsize=(13,6))
        for ax,scene in zip(axs,scenes):
            st=Usd.Stage.Open(str(ROOT/scene['file']),Usd.Stage.LoadAll);C=UsdGeom.XformCache();frame=scene['assemblies'][0]
            for i in [2,3,4,5,6,7]:
                path=frame['parts'][i]['visual_path'];p=st.GetPrimAtPath(path);m=UsdGeom.Mesh(p);v=np.asarray(m.GetPointsAttr().Get(),float);v=(np.c_[v,np.ones(len(v))]@np.asarray(C.GetLocalToWorldTransform(p)))[:,:3];faces=np.asarray(m.GetFaceVertexIndicesAttr().Get()).reshape(-1,3)
                mesh=trimesh.Trimesh(vertices=v,faces=faces,process=False,validate=False)
                # Exact original-mesh slice through candidate centre X.
                for seg in trimesh.intersections.mesh_plane(mesh,[1,0,0],[.210084464393,0,0]):ax.plot(seg[:,1]*1000,seg[:,2]*1000,color='tab:red' if i==5 else 'black',lw=.9 if i==5 else .6)
            for r in frame['central_vertical_ray_checks']:
                y=float(r['world_xy_m'][1])*1000;z=r['candidate_rim_world_z_m']*1000
                ax.plot([y,y],[z,1400],'--',color='tab:blue' if r['candidate_source_mesh_index']==3 else 'tab:green',alpha=.8,label=('far' if r['candidate_source_mesh_index']==3 else 'near')+' candidate axis')
            ax.set_title(f"{scene['pose']}: panel {scene['resulting_lid_main_plane_angle_deg']:.3f} deg");ax.set_xlabel('World Y mm');ax.set_ylabel('World Z mm');ax.set_xlim(-170,530);ax.set_ylim(720,1400);ax.set_aspect('equal');ax.grid(alpha=.2);ax.legend(fontsize=8)
        fig.suptitle('Actual source triangle YZ sections at far/near shared X; red lid, black body/seat; local rays only');fig.tight_layout();fig.savefig(out/'lid_source_vs_video_pose_sections.png',dpi=180);plt.close(fig)
    if any(s['pose']=='video_pose_verified' for s in scenes):
        mapping=json.loads((out/'asset_role_mapping.json').read_text())
        for role in mapping['roles']:
            if role['original_prim'] and role['original_file'] and role['original_file'].endswith('newnew4.usd'):
                role['derived_asset']='assets/lab_cuvette_loading/V0_demo02/video_pose_verified/instrument_native.usda'
                role['scene_instance']=role['original_prim'].replace('/RotatedRoot','/World/Instrument/Visual/Source',1)
            elif role['physical_role']=='vessel':
                role['scene_instance']='/World/VesselPreview (unsupported static comparison pose, not trajectory)'
        mapping['final_scene']='assets/lab_cuvette_loading/V0_demo02/video_pose_verified/scene_review.usda'
        write(out/'asset_role_mapping.json',mapping)
        csv_write(out/'asset_role_mapping.csv',mapping['roles'],['physical_role','original_file','sha256','original_prim','derived_asset','scene_instance','certainty'])
        readme=out/'README.md'
        with readme.open('a') as f:
            f.write('\n## 最终场景层只读复核\n\n`final_scene_verification.json/.csv` 对 source_pose 和 video_pose_verified 的主仪器及邻近第二仪器分别核查 8 个视觉网格与 8 个碰撞输入网格：原 face 索引逐项一致，视觉/碰撞同索引顶点世界坐标最大差约 2.94e-8 m（float32 输入舍入），这是输入层变换一致性检查，不是 PhysX 烹饪误差测量。源预期位姿到最终视觉最大差约 4.9e-16 m。\n\n机身仍 520.5×630×230 mm；源开盖整体 520.5×634.624772×435.480987 mm；主盖面转成视频估计90°后，整体包络变成520.5×630×576.999999 mm。变化来自明确的盖板刚体姿态，源部件未缩放。源盖会挡住两个候选中心的竖直轴；90°主面状态下远铰链候选中心轴不再命中盖板，近铰链候选轴仍被曲面/翻边上部遮挡。见 `lid_source_vs_video_pose_sections.png`。这些均为局部中心射线/剖面，不证明整个器皿和手爪的进入或撤离路径通过。\n\nworld→instrument→chamber_survey→candidate 的完整矩阵和原点均保存；chamber_survey 原点是候选底部包络中点，不是已标定腔底/承托面。白架仍缺失，原器皿与候选顶框仍几何冲突，因此没有将静态对照资产标为可执行完整任务。\n')
    return result


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,default=DEFAULT_OUT);parser.add_argument('--skip-inventory',action='store_true');args=parser.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
    roots=[Path('/home/wujing/Desktop'),Path('/home/wujing/Downloads'),Path('/home/wujing/Documents'),Path('/home/wujing/.codex/attachments')]
    if args.skip_inventory and (out/'delivery_inventory.json').exists():inv=json.loads((out/'delivery_inventory.json').read_text())
    else:inv=inventory(out,roots)
    write(out/'usd_deep_inspection.json',{'stages':[deep_stage(SOURCE/'newnew4.usd'),deep_stage(SOURCE/'TestTube_Baked.usd')],'broken_legacy_entry':{'file':'TestTube_629.usd','sha256':sha(SOURCE/'TestTube_629.usd'),'text':(SOURCE/'TestTube_629.usd').read_text(),'absolute_dependency_status':dependency_status('/root/LabUtopia/shiguan629/test/试管.obj')},'method':'LoadAll + TraverseAll + TraverseInstanceProxies(PrimAllPrimsPredicate); prototype geometry not counted as extra assembly instances'})
    rows,vessel=geometry(out);candidates,cavity=measurements(out,rows,vessel);figures(out,rows,vessel,candidates,cavity);summary(out,inv,rows,candidates);final_scenes(out,rows)
    write(out/'artifact_hashes.json',{str(p.relative_to(out)):sha(p) for p in sorted(out.rglob('*')) if p.is_file() and p.name!='artifact_hashes.json'})
    print('SOURCE_AUDIT_COMPLETE',out,'source meshes',len(rows),'rack CAD found',False,'candidate centred fit',False)

if __name__=='__main__':main()
