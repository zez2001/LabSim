"""Independent V0_ext01 scene and limited physical tests; complete loading is gated."""
from pathlib import Path
import argparse,sys,json,time,datetime,subprocess,hashlib
import numpy as np
from omegaconf import OmegaConf
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))

def write(path,data):
    def convert(x):
        if hasattr(x,'tolist'):return x.tolist()
        if all(hasattr(x,k) for k in ['x','y','z']):return [float(x.x),float(x.y),float(x.z)]
        try:return list(x)
        except TypeError:return str(x)
    Path(path).write_text(json.dumps(data,ensure_ascii=False,indent=2,default=convert)+'\n')

def snapshot(output,cfg,args):
    files=[ROOT/'config/lab_cuvette_loading/V0_ext01.yaml',*Path(__file__).parent.glob('*.py'),*Path(__file__).parent.glob('*.sh'),*list((ROOT/cfg.derived_directory).glob('*.usda'))]
    sources=json.loads((ROOT/'docs/lab_cuvette_loading/V0_ext01/source_manifest.json').read_text())
    write(output/'provenance.json',dict(command=sys.argv,utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),branch=subprocess.check_output(['git','branch','--show-current'],cwd=ROOT,text=True).strip(),commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),dirty=subprocess.check_output(['git','status','--short'],cwd=ROOT,text=True),scene_version=cfg.version,calibrated=False,sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files},source_manifest=sources,pairing=OmegaConf.to_container(cfg.pairing),test=args.test))
    import shutil
    for p in files:
        d=output/'source_snapshot'/p.relative_to(ROOT);d.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,d)
    OmegaConf.save(cfg,output/'config.yaml')

def gate(output,args):
    f=json.loads((ROOT/'docs/lab_cuvette_loading/V0_ext01/feasibility.json').read_text())
    r=dict(status=f['full_task_status'],requested_mode=args.mode,full_success=False,simulation_started=False,reason=f['reason'],candidate_pairings=[dict(path=x['candidate_path'],status=x['status']) for x in f['candidate_pairings']],thresholds=None,calibrated=False)
    write(output/'gate_result.json',r);print(r['status'],r['reason'],flush=True)
    return 0

def run(args,app,output,cfg):
    import omni.usd,omni.physx
    from pxr import Usd,UsdGeom,UsdLux,Gf,UsdPhysics,PhysxSchema,UsdShade,UsdUtils,PhysicsSchemaTools
    from isaacsim.core.api import World
    from isaacsim.core.api.objects import GroundPlane,FixedCuboid
    from isaacsim.core.prims import SingleRigidPrim
    from isaacsim.core.api.sensors import RigidContactView
    from isaacsim.core.utils.stage import add_reference_to_stage
    from isaacsim.core.utils.types import ArticulationAction
    from isaacsim.core.utils.viewports import set_camera_view
    from isaacsim.sensors.camera import Camera
    from isaacsim.robot.manipulators.examples.franka import Franka
    from isaacsim.robot.manipulators.examples.franka.kinematics_solver import KinematicsSolver
    from isaacsim.core.utils.rotations import euler_angles_to_quat
    from demos.lab_cuvette_external.geometry import normalized,tri
    from demos.lab_cuvette_external.build import add_mesh
    from demos.lab_cuvette_loading.model import slots,rz
    from demos.lab_cuvette_loading.scene import tcp
    from demos.lab_cuvette_external.collector import ExternalCollector
    started=time.monotonic();hz=cfg.physics.hz;control=cfg.physics.control_hz;substeps=hz//control
    is_grasp=args.test in ['grasp','grasp_table']
    assert substeps*control==hz
    omni.usd.get_context().new_stage();world=World(stage_units_in_meters=1.,physics_dt=1/hz,rendering_dt=1/control,backend='numpy',device='cpu');stage=omni.usd.get_context().get_stage()
    stage.SetDefaultPrim(UsdGeom.Xform.Define(stage,'/World').GetPrim());UsdGeom.SetStageUpAxis(stage,'Z')
    GroundPlane(prim_path='/World/Ground',size=10.)
    size=np.array(cfg.scene.table_size_m);table=world.scene.add(FixedCuboid(prim_path='/World/Table',name='table',position=np.array([.05,0,cfg.scene.table_top_m-size[2]/2]),scale=size,color=np.array([.6,.52,.42])))
    UsdLux.DomeLight.Define(stage,'/World/Light').CreateIntensityAttr(1000)
    assets=ROOT/cfg.derived_directory
    add_reference_to_stage(str(assets/'instrument.usda'),'/World/Instrument');ix=UsdGeom.Xformable(stage.GetPrimAtPath('/World/Instrument'));ix.AddTranslateOp().Set(Gf.Vec3d(*cfg.scene.instrument_xyz_m));ix.AddRotateZOp().Set(cfg.scene.instrument_yaw_deg)
    add_reference_to_stage(str(assets/'rack_V0_proxy.usda'),'/World/Rack');rack=UsdGeom.Xformable(stage.GetPrimAtPath('/World/Rack'));rack.AddTranslateOp().Set(Gf.Vec3d(*cfg.scene.rack_xy_m,cfg.scene.table_top_m+.004));rack.AddRotateZOp().Set(cfg.scene.rack_yaw_deg)
    source=np.r_[cfg.scene.rack_xy_m,cfg.scene.table_top_m+.004]+np.r_[((cfg.scene.source_slot[1]-3.5)*.017),((cfg.scene.source_slot[0]-2.5)*.017),0]
    source[:2]+=np.array(cfg.scene.source_local_xy_m)
    if args.test=='grasp_table':source=np.array([-.04,-.22,cfg.scene.table_top_m])
    cup_start=source+[0,0,.0002]
    if args.test=='drop':cup_start=np.array([-.04,-.22,cfg.scene.table_top_m+.025])
    if args.test=='side':cup_start=np.array([-.04,-.22,cfg.scene.table_top_m+.025])
    add_reference_to_stage(str(assets/('vessel_debug.usda' if args.debug_material else 'vessel.usda')),'/World/Cuvette')
    cup=world.scene.add(SingleRigidPrim(prim_path='/World/Cuvette',name='external_vessel',position=cup_start))
    # Real external geometry for distractors too; rack remains explicitly the V0 proxy.
    for i,x in enumerate([.0905,.1075]):
        add_reference_to_stage(str(assets/'vessel_debug.usda'),f'/World/Distractor{i}');world.scene.add(SingleRigidPrim(prim_path=f'/World/Distractor{i}',name=f'distractor{i}',position=np.array([x,-.0975,.7442])))
    if args.test=='side':
        # A separate diagnostic wall, not a replacement for any instrument wall.
        world.scene.add(FixedCuboid(prim_path='/World/DiagnosticWall',name='diagnostic_wall',position=np.array([.005,-.22,.79]),scale=np.array([.010,.12,.10]),color=np.array([.3,.35,.4])))
    robot=world.scene.add(Franka(prim_path='/World/Franka',name='franka',usd_path=str(ROOT/cfg.robot.usd_path),position=np.array(cfg.robot.base_m)))
    old=OmegaConf.load(ROOT/'config/lab_cuvette_loading/V0.yaml');robot.set_joints_default_state(positions=np.array([0,-.785,0,-2.356,0,1.571,.785,.04,.04]))
    api=PhysxSchema.PhysxSceneAPI.Apply(stage.GetPrimAtPath('/physicsScene'));api.CreateEnableGPUDynamicsAttr(False);api.CreateBroadphaseTypeAttr('MBP');api.CreateSolverTypeAttr(cfg.physics.solver);api.CreateEnableCCDAttr(cfg.physics.ccd)
    pm=UsdShade.Material.Define(stage,'/World/FingerPhysics');ma=UsdPhysics.MaterialAPI.Apply(pm.GetPrim());ma.CreateStaticFrictionAttr(cfg.physics.finger_static_friction);ma.CreateDynamicFrictionAttr(cfg.physics.finger_dynamic_friction);ma.CreateRestitutionAttr(cfg.physics.restitution)
    pa=PhysxSchema.PhysxMaterialAPI.Apply(pm.GetPrim());pa.CreateFrictionCombineModeAttr('average');pa.CreateRestitutionCombineModeAttr('average')
    for prim in stage.Traverse():
        if prim.HasAPI(UsdPhysics.ArticulationRootAPI):
            a=PhysxSchema.PhysxArticulationAPI.Apply(prim);a.CreateSolverPositionIterationCountAttr(cfg.physics.position_iterations);a.CreateSolverVelocityIterationCountAttr(cfg.physics.velocity_iterations)
        if str(prim.GetPath()).startswith('/World/Franka') and prim.HasAPI(UsdPhysics.CollisionAPI):
            a=PhysxSchema.PhysxCollisionAPI.Apply(prim);a.CreateContactOffsetAttr(cfg.physics.contact_offset_m);a.CreateRestOffsetAttr(cfg.physics.rest_offset_m)
            if 'finger' in str(prim.GetPath()):UsdShade.MaterialBindingAPI.Apply(prim).Bind(pm,materialPurpose='physics')
        n=prim.GetName()
        if n.startswith('panda_joint') and prim.IsA(UsdPhysics.RevoluteJoint):
            i=int(n.replace('panda_joint',''))-1;a=UsdPhysics.DriveAPI.Apply(prim,'angular');a.CreateTypeAttr('force');a.CreateStiffnessAttr(old.robot.arm_kp[i]*np.pi/180);a.CreateDampingAttr(old.robot.arm_kd[i]*np.pi/180);a.CreateMaxForceAttr(old.robot.max_effort[i]);PhysxSchema.PhysxJointAPI.Apply(prim).CreateMaxJointVelocityAttr(old.robot.max_velocity[i]*180/np.pi)
        if n in ['panda_finger_joint1','panda_finger_joint2']:
            a=UsdPhysics.DriveAPI.Apply(prim,'linear');a.CreateTypeAttr('force');a.CreateStiffnessAttr(old.robot.finger_kp);a.CreateDampingAttr(old.robot.finger_kd);a.CreateMaxForceAttr(old.robot.max_effort[7]);PhysxSchema.PhysxJointAPI.Apply(prim).CreateMaxJointVelocityAttr(old.robot.max_velocity[7])
    hand=world.scene.add(SingleRigidPrim(prim_path='/World/Franka/panda_hand',name='hand'))
    filters=[str(p.GetPath()) for p in stage.Traverse() if p.HasAPI(UsdPhysics.CollisionAPI) and not any(str(p.GetPath()).startswith('/World/'+x) for x in ['Franka','Cuvette','Distractor'])]
    env=RigidContactView(prim_paths_expr='/World/Cuvette',filter_paths_expr=filters,name='external_contacts',max_contact_count=4096)
    fingers=RigidContactView(prim_paths_expr=['/World/Franka/panda_leftfinger','/World/Franka/panda_rightfinger'],filter_paths_expr=[['/World/Cuvette'],['/World/Cuvette']],name='external_fingers',max_contact_count=256)
    world.reset();solver=KinematicsSolver(robot);solver.get_kinematics_solver().set_robot_base_pose(np.array(cfg.robot.base_m),np.array([1.,0,0,0]));orientation=euler_angles_to_quat(np.array([np.pi,0,0]))
    initial_tcp=np.array([.10,-.18,.99]);ik,valid=solver.compute_inverse_kinematics(initial_tcp,orientation)
    if not valid:raise RuntimeError('Initial TCP unreachable')
    q=robot.get_joint_positions().copy();q[np.array(ik.joint_indices,dtype=int)]=ik.joint_positions;q[7:]=.04;robot.set_joints_default_state(positions=q)
    errors=[]
    for _ in range(2):
        world.reset();errors.append(float(np.linalg.norm(cup.get_world_pose()[0]-cup_start)))
    robot.set_joint_positions(q);ac=robot.get_articulation_controller();ac.set_gains(kps=np.r_[old.robot.arm_kp,[old.robot.finger_kp]*2],kds=np.r_[old.robot.arm_kd,[old.robot.finger_kd]*2]);ac.set_max_efforts(np.array(old.robot.max_effort));robot._articulation_view.set_max_joint_velocities(np.array([old.robot.max_velocity]));ac.apply_action(ArticulationAction(joint_positions=q))
    for v in [env,fingers]:v.initialize()
    write(output/'reset_check.json',dict(errors_m=errors,passed=max(errors)<1e-6))
    # PhysX cooking interface supplies the actual generated convex representation.
    cooked=[];cook_status=[]
    def on_cooked(result,convexes):
        cook_status.append(str(result))
        for c in convexes:
            vs=np.array([[v.x,v.y,v.z] for v in c.vertices]);faces=[]
            for poly in c.polygons:
                ids=list(c.indices[poly.index_base:poly.index_base+poly.num_vertices]);faces.extend([[ids[0],ids[i],ids[i+1]] for i in range(1,len(ids)-1)])
            cooked.append(dict(vertices=vs.tolist(),faces=faces))
    stage_id=UsdUtils.StageCache.Get().GetId(stage).ToLongInt()
    cooking=omni.physx.get_physx_cooking_interface()
    cup_colliders=[str(p.GetPath()) for p in Usd.PrimRange(stage.GetPrimAtPath('/World/Cuvette/Collision')) if p.HasAPI(UsdPhysics.CollisionAPI)]
    for path in cup_colliders:cooking.request_convex_collision_representation(stage_id=stage_id,collision_prim_id=PhysicsSchemaTools.sdfPathToInt(path),run_asynchronously=False,on_result=on_cooked)
    write(output/'cooked_convexes.json',dict(status=cook_status,hulls=cooked,source='PhysX cooking representation API; not configuration echo',coordinates='collision mesh local metres'))
    import trimesh
    _,src=normalized(cfg.source.vessel,ROOT/cfg.source.directory);srcmesh=tri(src[0]);convexmeshes=[trimesh.Trimesh(np.array(c['vertices']),np.array(c['faces']),process=True) for c in cooked]
    rng=np.random.default_rng(7900);samples=rng.uniform(srcmesh.bounds[0]-.0003,srcmesh.bounds[1]+.0003,(12000,3));actual=srcmesh.contains(samples);union=np.zeros(len(samples),dtype=bool)
    from scipy.spatial import ConvexHull
    for m in convexmeshes:
        equations=ConvexHull(m.vertices).equations;union|=np.all(samples@equations[:,:3].T+equations[:,3]<=1e-10,axis=1)
    over=samples[union&~actual];under=samples[actual&~union]
    over_dist=trimesh.proximity.closest_point(srcmesh,over)[1] if len(over) else np.array([0.])
    write(output/'cooked_comparison.json',dict(hull_count=len(cooked),sample_seed=7900,uniform_samples=12000,sampled_overreach_count=len(over),sampled_missing_count=len(under),sampled_overreach_max_m=float(over_dist.max()),resolution_limit='sampled lower bound on possible maximum error, not Hausdorff guarantee',tiny_clearance_m=.00007499725,tiny_clearance_resolved=False,source_visual_mesh_error_m=0.,collision_authoring_error_m=None))
    for i,c in enumerate(cooked):
        d=add_mesh(stage,f'/World/CookedDebug/Hull{i}',c['vertices'],c['faces']);d.CreateDisplayColorAttr([Gf.Vec3f(.75,.1,.65)])
    debugxf=UsdGeom.Xformable(stage.GetPrimAtPath('/World/CookedDebug'));debugxf.AddTranslateOp().Set(Gf.Vec3d(*cup_start));debugxf.AddOrientOp().Set(Gf.Quatf(1,Gf.Vec3f(0,0,0)));UsdGeom.Imageable(debugxf).CreateVisibilityAttr('invisible')
    cameras={}
    for key,path,eye,target in [('camera_1_rgb','/World/Camera',[1.10,-1.05,1.35],[.15,.02,.94]),('camera_2_rgb','/World/Franka/panda_hand/WristCamera',[-.08,-.18,.98],[.09,-.18,.77])]:
        c=Camera(prim_path=path,name=key,frequency=control,resolution=(256,256));c.set_focal_length(2.4 if key=='camera_1_rgb' else 1.2);c.set_clipping_range(.001,10);set_camera_view(eye=np.array(eye),target=np.array(target),camera_prim_path=path);c.initialize();cameras[key]=c
        if key=='camera_2_rgb':
            from scipy.spatial.transform import Rotation
            local_eye=np.array([.10,0,.04]);local_target=np.array(cfg.robot.tcp_local_m)+[0,0,.015]
            z=local_eye-local_target;z/=np.linalg.norm(z);x=np.cross([0,1,0],z);x/=np.linalg.norm(x);y=np.cross(z,x);qcam=Rotation.from_matrix(np.column_stack([x,y,z])).as_quat()
            c.set_local_pose(local_eye,np.r_[qcam[3],qcam[:3]],camera_axes='usd')
    # Sensor warm-up precedes the recorded t=0 and initialization restore.
    for _ in range(4):world.step(render=True)
    # Restore the declared initial body state AFTER sensor warm-up, before t=0
    # and before recording. Otherwise a drop can finish during render warm-up.
    cup.set_world_pose(cup_start,np.array([1.,0,0,0]));cup.set_linear_velocity(np.zeros(3));cup.set_angular_velocity(np.zeros(3));world.render()
    tests=omni.physx.get_physxunittests_interface();bodies={}
    for path in ['/World/Cuvette','/World/Franka/panda_link1','/World/Franka/panda_hand','/World/Franka/panda_leftfinger']:
        try:bodies[path]=tests.get_mass_information(path)
        except Exception as e:bodies[path]=dict(unknown=str(e))
    inertia=cup._rigid_prim_view.get_inertias();com=cup._rigid_prim_view.get_coms();kp,kd=ac.get_gains()
    write(output/'runtime_readback.json',dict(source='physics tensor and PhysX mass query after reset and stepping',bodies=bodies,cup_tensor_mass_kg=cup.get_mass(),cup_tensor_inertia=inertia,cup_tensor_com=com,kp=kp,kd=kd,max_effort=ac.get_max_efforts(),max_velocity=robot._articulation_view.get_joint_max_velocities(),backend_cpu=not api.GetEnableGPUDynamicsAttr().Get(),solver=api.GetSolverTypeAttr().Get(),material_paths=tests.get_materials_paths(cup_colliders[0]),physics_statistics=tests.get_physics_stats(),contact_offsets_usd_authored_only=True,contact_offsets_runtime_readback=None,robot_dynamics_calibrated=False,robot_inherited_unit_inertia_issue='readback recorded; no ungrounded repair'))
    stage.Flatten().Export(str(output/'scene.usda'))
    from PIL import Image
    def views(prefix):
        for k,c in cameras.items():
            rgb=c.get_rgb()
            if rgb is not None and rgb.size:Image.fromarray(rgb[:,:,:3]).save(output/f'{prefix}_{k}.png')
    views('initial')
    # Exact source geometry surface-ray evidence for static collisions and cavity.
    query=omni.physx.get_physx_scene_query_interface();p0=cup.get_world_pose()[0];ray=query.raycast_closest(tuple(p0+[0,0,.070]),(0.,0.,-1.),.080)
    write(output/'cavity_ray.json',dict(ray=ray,expected_inner_floor_above_origin_m=.00488399,limitation='single cooked cavity ray sample; not a full cavity accuracy proof'))
    if args.mode=='scene':
        write(output/'result.json',dict(status='SCENE_LOADED',full_success=False,calibrated=False,reset_passed=max(errors)<1e-6,physics_acceptance=False));views('scene')
        pos,quat=cup.get_world_pose();debugxf.GetOrderedXformOps()[0].Set(Gf.Vec3d(*map(float,pos)));debugxf.GetOrderedXformOps()[1].Set(Gf.Quatf(float(quat[0]),Gf.Vec3f(*map(float,quat[1:]))))
        UsdGeom.Imageable(stage.GetPrimAtPath('/World/Cuvette/Visual')).MakeInvisible();UsdGeom.Imageable(debugxf).MakeVisible()
        for _ in range(3):world.render()
        views('cooked_collision');UsdGeom.Imageable(debugxf).MakeInvisible();UsdGeom.Imageable(stage.GetPrimAtPath('/World/Cuvette/Visual')).MakeVisible()
        if args.keep_open:
            while app.is_running():world.render()
        return 0
    # Reuse the existing writer/schema; extension fields separate the subtask label.
    recordcfg=OmegaConf.create(OmegaConf.to_container(old));recordcfg.version='V0_ext01';recordcfg.physics.hz=hz;recordcfg.physics.control_hz=control;recordcfg.task.control_hz=control;recordcfg.task.instruction='External vessel physical diagnostic '+args.test
    phases=['SETTLE','APPROACH','GRASP','EXTRACT','HOLD','TRANSPORT','OPEN','RELEASE_CHECK'];recordcfg.control.phases_s={k:0. for k in phases}
    collector=ExternalCollector(recordcfg,output,True);collector.begin_episode(0,p0);collector.file.attrs.update(scene_version='V0_ext01',schema_version='labsim.lab_cuvette_loading.V0_ext01.diagnostic.v1',base_learning_schema='labsim.lab_cuvette_loading.V0',diagnostic=args.test,mode=args.mode,seed=0,privileged_progress_columns='actual_held',omitted_task_metrics='depth_m,xy_error_m,yaw_error_rad,overlap_m',full_task_eligible=False,geometry_gate='blocked_identity_and_geometry',overlap_measurement_available=False)
    if args.test=='side':cup.set_linear_velocity(np.array([.4,0,0]))
    t=0.;frame=0;records=[];hold_start=None;held=False;max_lift=0.;finite=True;last_q=q.copy();phase='SETTLE';target_tcp=initial_tcp.copy();outcome='RUNNING';origin_time=world.current_time;grasp_anchor=None;hold_pose=None;max_slide=0.;source0=cup.get_world_pose()[0].copy();support_history=[]
    scene=dict(hand=hand);tcpcfg=OmegaConf.create(dict(robot=dict(tcp_local_m=list(cfg.robot.tcp_local_m))))
    def observe():
        pos,quat=cup.get_world_pose();f=np.linalg.norm(np.asarray(fingers.get_contact_force_matrix(dt=1/hz)).reshape(2,-1,3),axis=2).sum(1);force=float(np.linalg.norm(np.asarray(env.get_contact_force_matrix(dt=1/hz)).reshape(-1,3),axis=1).sum())
        tilt=float(np.arccos(np.clip(1.-2.*(quat[1]**2+quat[2]**2),-1.,1.)))
        return dict(camera_data={k:np.transpose(c.get_rgb()[:,:,:3],(2,0,1)).astype(np.uint8) for k,c in cameras.items()},joint_positions=robot.get_joint_positions().copy(),simulation_time=t,tcp=tcp(scene,tcpcfg),object_position=pos,object_orientation=quat,phase=phase,target_tcp=target_tcp.copy(),metrics=dict(depth_m=0.,xy_error_m=[1.,1.],tilt_rad=tilt,yaw_error_rad=0.,overlap_m=0.,finger_contact_N=f,environment_contact_N=force))
    state=observe();initial=dict(position=source0,quaternion=state['object_orientation'],linear_velocity=cup.get_linear_velocity(),angular_velocity=cup.get_angular_velocity(),joints=state['joint_positions'],joint_velocities=robot.get_joint_velocities(),source_m=source,layout=OmegaConf.to_container(cfg.scene),distractors=[dict(pose=world.scene.get_object(f'distractor{i}').get_world_pose(),linear_velocity=world.scene.get_object(f'distractor{i}').get_linear_velocity()) for i in range(2)],initialization_only_pose_restore=True);write(output/'initial.json',initial)
    duration=28.5 if is_grasp else 4.
    try:
        while t<duration and app.is_running():
            if is_grasp:
                if 1.99<=t<2.02 and len(support_history)>=hz and max(support_history[-hz:])>.003:
                    outcome='INITIAL_SUPPORT_INVALID';break
                grasp=np.r_[source[:2],source[2]+cfg.robot.grasp_above_bottom_m];lift=grasp+[0,0,.10];transport=np.array([-.04,-.20,lift[2]])
                if t<2.:phase='SETTLE';target_tcp=initial_tcp;grip=.04
                elif t<8.:phase='APPROACH';f=(t-2)/6;target_tcp=initial_tcp+(3*f*f-2*f*f*f)*(grasp-initial_tcp);grip=.04
                elif t<10.:phase='APPROACH';target_tcp=grasp;grip=.04
                elif t<12.:
                    if t<10.02 and np.linalg.norm(state['tcp']-grasp)>.002:outcome='CONTROL_TRACKING_FAILURE_BEFORE_GRASP';break
                    phase='GRASP';target_tcp=grasp;grip=.04*(1-(t-10)/2)
                elif t<16.:phase='EXTRACT';f=(t-12)/4;target_tcp=grasp+(3*f*f-2*f*f*f)*(lift-grasp);grip=0.
                elif t<18.:phase='HOLD';target_tcp=lift;grip=0.
                elif t<22.:phase='TRANSPORT';f=(t-18)/4;target_tcp=lift+(3*f*f-2*f*f*f)*(transport-lift);grip=0.
                elif t<24.:phase='OPEN';target_tcp=transport;grip=.04*(t-22)/2
                else:phase='RELEASE_CHECK';target_tcp=transport+[0,0,min(.08,(t-24)*.04)];grip=.04
                ik,valid=solver.compute_inverse_kinematics(target_tcp,orientation,position_tolerance=old.robot.ik_position_tolerance_m,orientation_tolerance=old.robot.ik_orientation_tolerance_rad)
                if not valid:outcome='CONTROL_OR_IK_FAILURE';break
                q=state['joint_positions'].copy();q[np.array(ik.joint_indices,dtype=int)]=ik.joint_positions;q[7:]=grip;delta=np.array(old.robot.max_velocity)/control;q=np.clip(q,last_q-delta,last_q+delta)
            else:phase='SETTLE';q=last_q.copy()
            action=ArticulationAction(joint_positions=q);ac.apply_action(action);last_q=q.copy()
            for _ in range(substeps):
                world.step(render=False);t+=1/hz;pos,quat=cup.get_world_pose();vel=cup.get_linear_velocity();f=np.linalg.norm(np.asarray(fingers.get_contact_force_matrix(dt=1/hz)).reshape(2,-1,3),axis=2).sum(1)
                force_data=env.get_contact_force_data(dt=1/hz);forces,points,normals,seps,counts,starts=force_data;idx=[]
                for count,start in zip(np.asarray(counts).ravel(),np.asarray(starts).ravel()):idx.extend(range(int(start),int(start)+int(count)))
                liftactual=pos[2]-source0[2];max_lift=max(max_lift,liftactual);finite&=bool(np.isfinite(np.r_[pos,quat,vel]).all());support_history.append(float(np.linalg.norm(vel)))
                if liftactual>=cfg.acceptance.subtask_clearance_m and np.all(f>.02):
                    if hold_start is None:hold_start=t
                    if t-hold_start>=cfg.acceptance.subtask_hold_s:held=True
                else:hold_start=None
                pairforce=np.linalg.norm(np.asarray(env.get_contact_force_matrix(dt=1/hz)).reshape(-1,3),axis=1)
                records.append(dict(time=t,engine_elapsed=world.current_time-origin_time,phase=phase,position=pos,orientation=quat,linear_velocity=vel,actual_tcp=tcp(scene,tcpcfg),finger_force_N=f,target_tcp=target_tcp,environment_force_by_filter_N=pairforce,contact_force_N=np.asarray(forces)[idx].ravel(),contact_points_m=np.asarray(points)[idx],contact_separation_m=np.asarray(seps)[idx]))
            world.render();nextstate=observe();frame+=1
            result=dict(status='RUNNING',full_success=False,stage_progress=dict(actual_held=held),seed=0)
            state['phase']=phase;state['target_tcp']=target_tcp;collector.cache_transition(state,action,nextstate,result);state=nextstate
            if not finite:outcome='PHYSICS_INVALID';break
        finalpos,finalq=cup.get_world_pose();speed=np.linalg.norm(cup.get_linear_velocity());bottom_z=float(finalpos[2]);stable_speed=max(support_history[-hz:]) if len(support_history)>=hz else float('inf')
        supportlevel=.744 if args.test=='rack' else .74
        support_ok=abs(bottom_z-supportlevel)<.0003 and stable_speed<.003
        contact_seen=any(len(r['contact_points_m']) for r in records)
        side_contact_peak=max((r['environment_force_by_filter_N'][filters.index('/World/DiagnosticWall')] for r in records),default=0.) if args.test=='side' else None
        diagnostic_pass=finite and (held and support_ok if is_grasp else support_ok and contact_seen)
        if args.test=='side':diagnostic_pass&=side_contact_peak>.01
        if outcome=='RUNNING':outcome='SUBTASK_SUCCESS' if diagnostic_pass else 'SUBTASK_FAILED'
        result=dict(status=outcome,reason='independent_actual_lift_bilateral_contact_hold_and_release_support' if is_grasp else 'actual_support_contact_stability_check',full_success=False,diagnostic_pass=diagnostic_pass,subtask_held=held,max_lift_m=max_lift,final_position=finalpos,final_linear_speed_m_s=float(speed),last_second_max_speed_m_s=stable_speed,contact_seen=contact_seen,source_support_check_passed=support_ok,finite=finite,simulation_seconds=t,wall_seconds=time.monotonic()-started,frames=frame,full_task_status='blocked_identity_and_geometry',static_mesh_no_penetration_claim=False,calibrated=False,diagnostic_test=args.test,source_rack_task=args.test=='grasp')
        result['side_wall_contact_peak_N']=side_contact_peak
        write(output/'contact_filters.json',filters)
        result=json.loads(json.dumps(result,default=lambda x:x.tolist() if hasattr(x,'tolist') else str(x)))
        collector.file['done'][-1]=True;collector.finish_episode(result)
        write(output/'result.json',result);write(output/'physics_records.json',records);views('final')
        print('RESULT',outcome,'held',held,'lift_mm',max_lift*1000,'support',support_ok,flush=True)
        # Independently visualise cooked hulls, never call these authored source triangles.
        UsdGeom.Imageable(stage.GetPrimAtPath('/World/Cuvette/Visual')).MakeInvisible();UsdGeom.Imageable(debugxf).MakeVisible();debugxf.GetOrderedXformOps()[0].Set(Gf.Vec3d(*map(float,finalpos)))
        debugxf.GetOrderedXformOps()[1].Set(Gf.Quatf(float(finalq[0]),Gf.Vec3f(*map(float,finalq[1:]))))
        for _ in range(3):world.render()
        views('cooked_collision')
        if args.keep_open:
            while app.is_running():world.render()
    finally:collector.close()
    return 0

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--mode',choices=['scene','physics','task','standard','random'],default='scene');p.add_argument('--test',choices=['drop','rack','side','grasp','grasp_table'],default='rack');p.add_argument('--headless',action='store_true');p.add_argument('--keep-open',action='store_true');p.add_argument('--debug-material',action='store_true');p.add_argument('--output',type=Path);p.add_argument('--config',type=Path,default=ROOT/'config/lab_cuvette_loading/V0_ext01.yaml');args=p.parse_args()
    cfg=OmegaConf.load(args.config)
    if cfg.version!='V0_ext01':raise ValueError('This independent entry accepts V0_ext01 only; use original launcher for V0')
    output=(args.output or ROOT/cfg.output_root/datetime.datetime.now().strftime('%Y%m%d_%H%M%S')).resolve();output.mkdir(parents=True,exist_ok=False);snapshot(output,cfg,args)
    if args.mode in ['task','standard','random']:return gate(output,args)
    from isaacsim import SimulationApp
    app=SimulationApp(dict(headless=args.headless,width=1280,height=720,extra_args=['--/app/extensions/fsWatcherEnabled=false']));code=1
    try:code=run(args,app,output,cfg);return code
    except BaseException:
        import traceback
        write(output/'failure.json',dict(status='ENVIRONMENT_OR_IMPLEMENTATION_FAILURE',traceback=traceback.format_exc(),full_success=False));traceback.print_exc();raise
    finally:
        from omni.kit.app import get_app
        get_app().post_quit(code);app.close()

if __name__=='__main__':sys.exit(main())
