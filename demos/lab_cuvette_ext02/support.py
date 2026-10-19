"""Minimal recorded support experiment. No robot, rack or instrument is loaded."""
from pathlib import Path
import argparse,json,time,sys,hashlib,subprocess
import numpy as np
from omegaconf import OmegaConf
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from demos.lab_cuvette_external.run import write

def measure(rows,cfg):
    a=cfg.acceptance; last=[r for r in rows if r['t']>=rows[-1]['t']-a.window_s-1e-8]
    p=np.array([r['position'] for r in last],dtype=float);q=np.array([r['quaternion'] for r in last],dtype=float);q/=np.linalg.norm(q,axis=1)[:,None];drift=float(np.linalg.norm(p-p[0],axis=1).max());angle=float(np.degrees(2*np.arccos(np.clip(np.abs(q@q[0]),0,1))).max())
    pen=max(r['source_penetration_m'] for r in last);v=max(np.linalg.norm(r['linear_velocity']) for r in last);w=max(np.linalg.norm(r['angular_velocity']) for r in last)
    return dict(window_s=last[-1]['t']-last[0]['t'],position_drift_m=drift,orientation_change_deg=angle,source_penetration_m=pen,source_bottom_gap_max_m=max(r['source_bottom_gap_m'] for r in last),max_linear_speed_m_s=v,max_angular_speed_rad_s=w,static_pass=bool(drift<=a.position_drift_m and angle<=a.orientation_change_deg and pen<=a.steady_source_penetration_m and v<=a.linear_speed_m_s and w<=a.angular_speed_rad_s and last[-1]['t']-last[0]['t']>=a.window_s-1e-6))

def run(app,cfg,scheme,out):
    import omni.usd,omni.physx
    from pxr import Usd,UsdGeom,UsdLux,UsdPhysics,PhysxSchema,UsdUtils,PhysicsSchemaTools,Gf
    from isaacsim.core.api import World
    from isaacsim.core.api.objects import FixedCuboid
    from isaacsim.core.prims import SingleRigidPrim
    from isaacsim.core.api.sensors import RigidContactView
    from isaacsim.core.utils.stage import add_reference_to_stage
    from isaacsim.sensors.camera import Camera
    from isaacsim.core.utils.viewports import set_camera_view
    from scipy.spatial.transform import Rotation
    from demos.lab_cuvette_ext02.build import source_mesh
    import cv2,h5py
    start=time.monotonic();out.mkdir(exist_ok=False);OmegaConf.save(cfg,out/'config.yaml')
    import shutil
    files=[*Path(__file__).parent.glob('*.py'),Path(cfg.get('_config_source_path',ROOT/'config/lab_cuvette_loading/V0_ext02.yaml')),ROOT/cfg.derived_directory/(scheme+'.usda')]
    write(out/'provenance.json',dict(command=sys.argv,git_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),sha256={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in files}))
    for f in files:
        dest=out/'source_snapshot'/f.relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(f,dest)
    omni.usd.get_context().new_stage();World.clear_instance()
    # Clear caches before any actor is attached, not merely before the separate
    # visualisation query. This is a fixed reproducibility check, not retuning.
    omni.physx.get_physx_cooking_interface().release_local_mesh_cache()
    omni.physx.get_physx_cooking_private_interface().release_runtime_mesh_cache()
    world=World(stage_units_in_meters=1.,physics_dt=1/cfg.physics.hz,rendering_dt=1/cfg.physics.control_hz,backend='numpy',device='cpu');s=omni.usd.get_context().get_stage();UsdGeom.SetStageUpAxis(s,'Z');UsdGeom.SetStageMetersPerUnit(s,1.);s.SetDefaultPrim(UsdGeom.Xform.Define(s,'/World').GetPrim())
    top=cfg.scene.table_top_m;size=np.array(cfg.scene.table_size_m)
    table=world.scene.add(FixedCuboid('/World/Table',name='table',position=np.array([0.,0.,top-size[2]/2]),scale=size,color=np.array([.43,.39,.34])))
    UsdLux.DomeLight.Define(s,'/World/Light').CreateIntensityAttr(1200.)
    asset=ROOT/cfg.derived_directory/(scheme+'.usda');add_reference_to_stage(str(asset),'/World/Cuvette');p0=np.r_[cfg.scene.cup_xy_m,top+cfg.scene.initial_bottom_gap_m]
    cup=world.scene.add(SingleRigidPrim('/World/Cuvette',name='cup',position=p0))
    body_api=PhysxSchema.PhysxRigidBodyAPI.Apply(s.GetPrimAtPath('/World/Cuvette'));body_api.CreateSolverPositionIterationCountAttr(cfg.physics.position_iterations);body_api.CreateSolverVelocityIterationCountAttr(cfg.physics.velocity_iterations)
    api=PhysxSchema.PhysxSceneAPI.Apply(s.GetPrimAtPath('/physicsScene'));api.CreateEnableGPUDynamicsAttr(False);api.CreateBroadphaseTypeAttr('MBP');api.CreateSolverTypeAttr(cfg.physics.solver);api.CreateEnableCCDAttr(True)
    ct=PhysxSchema.PhysxCollisionAPI.Apply(s.GetPrimAtPath('/World/Table'));ct.CreateContactOffsetAttr(cfg.physics.contact_offset_m);ct.CreateRestOffsetAttr(0.)
    from demos.lab_cuvette_external.build import mat
    from pxr import UsdShade
    UsdShade.MaterialBindingAPI.Apply(s.GetPrimAtPath('/World/Table')).Bind(mat(s,'/World/TablePhysics',cfg),materialPurpose='physics')
    contacts=RigidContactView(prim_paths_expr='/World/Cuvette',filter_paths_expr=['/World/Table'],name='support_contacts',max_contact_count=4096)
    world.reset();contacts.initialize();cameras=[]
    contact_events=[];t=0.
    def native_contact(headers,data):
        def vec(v):return [float(v.x),float(v.y),float(v.z)]
        for h in headers:
            points=[]
            for j in range(h.contact_data_offset,h.contact_data_offset+h.num_contact_data):
                d=data[j];impulse=vec(d.impulse)
                points.append(dict(position_m=vec(d.position),normal=vec(d.normal),impulse_Ns=impulse,force_N=(np.array(impulse)*cfg.physics.hz).tolist(),separation_m=float(d.separation)))
            contact_events.append(dict(t=t+1/cfg.physics.hz,engine_time=world.current_time,collider0=str(PhysicsSchemaTools.intToSdfPath(h.collider0)),collider1=str(PhysicsSchemaTools.intToSdfPath(h.collider1)),type=str(h.type),points=points))
    subscription=omni.physx.get_physx_simulation_interface().subscribe_contact_report_events(native_contact)
    for i,(eye,target) in enumerate([([.15,-.44,.94],[-.04,-.22,.77]),([-.005,-.29,.766],[-.04,-.22,.747])]):
        path=f'/World/Camera{i}';c=Camera(path,name=f'view{i}',frequency=60,resolution=(512,512));c.set_focal_length(3.0);c.set_clipping_range(.0001,10.);set_camera_view(eye=np.array(eye),target=np.array(target),camera_prim_path=path);c.initialize();cameras.append(c)
    # Render warm-up with physics paused; no unrecorded falling segment.
    for _ in range(5):world.render()
    cup.set_world_pose(p0,np.array([1.,0,0,0]));cup.set_linear_velocity(np.zeros(3));cup.set_angular_velocity(np.zeros(3))
    cooking=omni.physx.get_physx_cooking_interface();cooking.release_local_mesh_cache();hulls=[];mapping=[];cache=UsdGeom.XformCache();rootmat=np.array(cache.GetLocalToWorldTransform(s.GetPrimAtPath('/World/Cuvette')));inverse=np.linalg.inv(rootmat)
    sid=UsdUtils.StageCache.Get().GetId(s).ToLongInt();paths=[];B=[]
    for prim in Usd.PrimRange(s.GetPrimAtPath('/World/Cuvette')):
        if not prim.HasAPI(UsdPhysics.CollisionAPI):continue
        path=str(prim.GetPath());paths.append(path);mesh=UsdGeom.Mesh(prim);matrix=np.array(cache.GetLocalToWorldTransform(prim))@inverse
        vertices=np.array(mesh.GetPointsAttr().Get(),dtype=float);v=(np.c_[vertices,np.ones(len(vertices))]@matrix)[:,:3]
        B.append(dict(path=path,vertices=v,faces=np.array(mesh.GetFaceVertexIndicesAttr().Get()).reshape(-1,3),local_to_body_row_matrix=matrix,approximation=UsdPhysics.MeshCollisionAPI(prim).GetApproximationAttr().Get(),hull_vertex_limit=PhysxSchema.PhysxConvexHullCollisionAPI(prim).GetHullVertexLimitAttr().Get(),min_thickness=PhysxSchema.PhysxConvexHullCollisionAPI(prim).GetMinThicknessAttr().Get()))
        if scheme=='sdf_cpu':continue
        def callback(result,convexes,path=path,matrix=matrix):
            mapping.append(dict(path=path,result=str(result),count=len(convexes)))
            for c in convexes:
                vs=np.array([[v.x,v.y,v.z] for v in c.vertices]);fs=[]
                for f in c.polygons:
                    ids=list(c.indices[f.index_base:f.index_base+f.num_vertices]);fs.extend([[ids[0],ids[j],ids[j+1]] for j in range(1,len(ids)-1)])
                hulls.append(dict(path=path,vertices=(np.c_[vs,np.ones(len(vs))]@matrix)[:,:3],faces=fs,raw_local_vertices=vs,raw_planes=[[f.plane.x,f.plane.y,f.plane.z,f.plane.w] for f in c.polygons],raw_polygon_counts=[f.num_vertices for f in c.polygons],local_to_body_row_matrix=matrix))
        cooking.request_convex_collision_representation(stage_id=sid,collision_prim_id=PhysicsSchemaTools.sdfPathToInt(path),run_asynchronously=False,on_result=callback)
    write(out/'B_input.json',B);write(out/'C_cooking_query.json',dict(hulls=hulls,status=mapping,limitation='cooking query, cross checked with live ray hits below; not full native actor mesh memory export'))
    tests=omni.physx.get_physxunittests_interface();write(out/'runtime.json',dict(physics_stats=tests.get_physics_stats(),body=tests.get_mass_information('/World/Cuvette'),mass=cup.get_mass(),inertia=cup._rigid_prim_view.get_inertias(),com=cup._rigid_prim_view.get_coms(),backend='CPU PhysX',gpu_dynamics=api.GetEnableGPUDynamicsAttr().Get(),solver=api.GetSolverTypeAttr().Get(),shape_paths=paths,source_dimensions_m=source_mesh().extents,asset_sha256=hashlib.sha256(asset.read_bytes()).hexdigest(),git_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),actual_contact_offsets_readback=None,sdf_actual_grid_readback=None))
    if scheme=='sdf_cpu':
        import resource
        try:
            import omni.physics.tensors as tensors
            view=tensors.create_simulation_view('numpy');view.set_subspace_roots('/')
            sdf=view.create_sdf_shape_view('/World/Cuvette/Collision/sdf',len(source_mesh().vertices))
            data=sdf.get_sdf_and_gradients(np.array(source_mesh().vertices,dtype=np.float32)[None])
            write(out/'sdf_probe.json',dict(count=sdf.count,query=data,points=source_mesh().vertices,cpu_query_succeeded=True,field_semantics='raw four components; validate implementation order before metric use',actual_spacing_m=None,peak_process_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss))
        except Exception as e:write(out/'sdf_probe.json',dict(cpu_query_succeeded=False,error=repr(e),peak_process_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,actual_spacing_m=None,sdf_memory_bytes=None,gpu_memory_bytes=None,table_pair_verified_only=True,gripper_and_instrument_pairs_verified=False))
    # Actual PhysX scene ray hits at t=0: each starts outside the cup, table excluded by height.
    query=omni.physx.get_physx_scene_query_interface();rays=[]
    for z in [.00001,.00005,.0001,.0002,.001,.005,.03,.0674]:
        for a in np.linspace(0,2*np.pi,32,endpoint=False):
            n=np.array([np.cos(a),np.sin(a),0.]);o=np.r_[p0[:2],p0[2]+z]+n*.02;hit=query.raycast_closest(tuple(o),tuple(-n),.04)
            if hit.get('hit'):rays.append(dict(origin=o-p0,direction=-n,hit_body_local=np.array(hit['position'])-p0,collider=hit.get('collision'),distance=hit.get('distance')))
    write(out/'live_rays.json',rays)
    if scheme=='sdf_cpu':
        src=source_mesh();checks=[]
        for i,(centre,normal) in enumerate(zip(src.triangles_center,src.face_normals)):
            origin=p0+centre+normal*2e-5;hit=query.raycast_closest(tuple(origin),tuple(-normal),4e-5,True)
            checks.append(dict(source_face=i,source_centroid_m=centre,hit=bool(hit.get('hit')),collider=hit.get('collision'),native_face_index=hit.get('faceIndex'),hit_local_m=np.array(hit['position'])-p0 if hit.get('hit') else None,centroid_to_hit_m=float(np.linalg.norm(np.array(hit['position'])-p0-centre)) if hit.get('hit') else None))
        valid=[r for r in checks if r['hit'] and str(r['collider']).startswith('/World/Cuvette')]
        maximum=max((r['centroid_to_hit_m'] for r in valid),default=None)
        write(out/'native_triangle_probe.json',dict(backend='CPU',representation='SDF-authored dynamic triangle mesh; documented CPU TriangleMesh fallback, NOT active GPU SDF',source_faces=len(checks),cup_hits=len(valid),observed_directional_surface_distance_m=maximum,missing_samples=len(checks)-len(valid),scope='source triangle-centroid to native ray surface samples; directional distance bounds sampled closest distance, NOT cooked vertex export or global bound',all_checks=checks))
    s.Flatten().Export(str(out/'scene.usda'));m=source_mesh();rows=[];writer=cv2.VideoWriter(str(out/'support.mp4'),cv2.VideoWriter_fourcc(*'mp4v'),60,(1024,512));t=0.;dt=1/cfg.physics.hz;sub=cfg.physics.hz//60
    def record():
        p,q=cup.get_world_pose();rot=Rotation.from_quat(np.r_[q[1:],q[0]]);vs=m.vertices@rot.as_matrix().T+p;com=rot.apply(np.array([8.9723807e-7,9.038207e-7,.029027632]))+p
        forces,pts,normals,seps,counts,starts=contacts.get_contact_force_data(dt=dt);idx=[]
        for count,st in zip(np.asarray(counts).ravel(),np.asarray(starts).ravel()):idx.extend(range(int(st),int(st)+int(count)))
        return dict(t=t,engine_time=world.current_time,position=p,quaternion=q,linear_velocity=cup.get_linear_velocity(),angular_velocity=cup.get_angular_velocity(),source_bottom_z_m=float(vs[:,2].min()),source_penetration_m=max(0.,float(top-vs[:,2].min())),source_bottom_gap_m=max(0.,float(vs[:,2].min()-top)),com_world_m=com,contact_points_m=np.asarray(pts)[idx],contact_separation_m=np.asarray(seps)[idx],contact_normal_force_N=np.asarray(forces)[idx].ravel(),support_force_vector_N=np.asarray(contacts.get_contact_force_matrix(dt=dt)).reshape(-1,3).sum(0))
    rows.append(record())
    for k in range(360):
        for _ in range(sub):world.step(render=False);t+=dt;rows.append(record())
        world.render();images=[c.get_rgb()[:,:,:3] for c in cameras];im=np.concatenate(images,axis=1);frame=cv2.cvtColor(im,cv2.COLOR_RGB2BGR);cv2.putText(frame,f'{scheme} t={t:.3f} source penetration={rows[-1]["source_penetration_m"]*1000:.4f} mm',(8,24),cv2.FONT_HERSHEY_SIMPLEX,.51,(255,255,255),1);writer.write(frame)
        if k in [0,30,359]:cv2.imwrite(str(out/f'support_{k:03d}.png'),frame)
    writer.release();write(out/'physics_records.json',rows);write(out/'native_contact_events.json',contact_events);result=measure(rows,cfg);result.update(scheme=scheme,full_success=False,full_task_executed=False,geometry_support_gate_pending=True,wall_seconds=time.monotonic()-start,simulation_seconds=t,initial_frame_recorded=True)
    native_shapes=tests.get_physics_stats()['numConvexShapes']+tests.get_physics_stats()['numTriMeshShapes']
    result['status']='PHYSICS_INVALID' if native_shapes==0 else ('STATIC_PASS_GEOMETRY_PENDING' if result['static_pass'] else 'SUPPORT_FAILED')
    write(out/'result.json',result)
    with h5py.File(out/'support.h5','x') as f:
        f.attrs.update(schema_version='labsim.V0_ext02.support.v1',full_success=False,full_task_eligible=False,physics_hz=cfg.physics.hz,control_hz=60)
        for key in ['t','position','quaternion','linear_velocity','angular_velocity','source_penetration_m','source_bottom_gap_m','support_force_vector_N']:f.create_dataset(key,data=np.array([r[key] for r in rows]))
    print('SUPPORT_RESULT',out,(out/'result.json').read_text(),flush=True);world.stop();world.clear();World.clear_instance()

def main():
    p=argparse.ArgumentParser();p.add_argument('--schemes',nargs='+',default=['control193','walls25','walls25_mm']);p.add_argument('--headless',action='store_true');p.add_argument('--hz',type=int,choices=[240,480],default=240);p.add_argument('--config',type=Path,default=ROOT/'config/lab_cuvette_loading/V0_ext02.yaml');p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(exist_ok=False,parents=True)
    cfg=OmegaConf.load(a.config);cfg.physics.hz=a.hz;cfg._config_source_path=str(a.config.resolve())
    from isaacsim import SimulationApp
    app=SimulationApp(dict(headless=a.headless,width=1280,height=720,extra_args=['--/app/extensions/fsWatcherEnabled=false']))
    try:
        for scheme in a.schemes:run(app,cfg,scheme,a.output/scheme)
    except BaseException:
        import traceback
        write(a.output/'failure.json',dict(traceback=traceback.format_exc()));raise
    finally:app.close()

if __name__=='__main__':main()
