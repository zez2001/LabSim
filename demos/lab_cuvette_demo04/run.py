"""V0_demo04: original-seat geometry gate and dynamic preinsert diagnosis."""
from pathlib import Path
import argparse,sys,json,time,datetime,hashlib,subprocess
import numpy as np
from omegaconf import OmegaConf
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from demos.lab_cuvette_external.run import write
from demos.lab_cuvette_ext02.support import measure
def make_scene(args,app,output,cfg):
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

    assert substeps*control==hz
    omni.usd.get_context().new_stage();World.clear_instance()
    omni.physx.get_physx_cooking_interface().release_local_mesh_cache();omni.physx.get_physx_cooking_private_interface().release_runtime_mesh_cache()
    world=World(stage_units_in_meters=1.,physics_dt=1/hz,rendering_dt=1/control,backend='numpy',device='cpu');stage=omni.usd.get_context().get_stage()
    stage.SetDefaultPrim(UsdGeom.Xform.Define(stage,'/World').GetPrim());UsdGeom.SetStageUpAxis(stage,'Z')
    GroundPlane(prim_path='/World/Ground',size=10.)
    size=np.array(cfg.scene.table_size_m);table=world.scene.add(FixedCuboid(prim_path='/World/Table',name='table',position=np.array([.05,0,cfg.scene.table_top_m-size[2]/2]),scale=size,color=np.array([.6,.52,.42])))
    UsdLux.DomeLight.Define(stage,'/World/Light').CreateIntensityAttr(1000)
    assets=ROOT/cfg.derived_directory
    full=cfg.mode=='workflow'
    if full:
        from demos.lab_cuvette_demo04.scene import add_scene
        fixtures=add_scene(world,stage,cfg)
        source=fixtures['source_floor'].copy()
    else:source=np.r_[cfg.scene.cup_xy_m,cfg.scene.table_top_m]
    cup_start=source+[0,0,cfg.scene.initial_bottom_gap_m]
    add_reference_to_stage(str(assets/(cfg.get('collision_scheme','walls28_mm')+'.usda')),'/World/Cuvette')
    cup=world.scene.add(SingleRigidPrim(prim_path='/World/Cuvette',name='external_vessel',position=cup_start,orientation=euler_angles_to_quat(np.array([0.,0.,np.radians(float(cfg.vessel.yaw_deg))]))))
    body_api=PhysxSchema.PhysxRigidBodyAPI.Apply(stage.GetPrimAtPath('/World/Cuvette'));body_api.CreateSolverPositionIterationCountAttr(cfg.physics.position_iterations);body_api.CreateSolverVelocityIterationCountAttr(cfg.physics.velocity_iterations)
    robot=world.scene.add(Franka(prim_path='/World/Franka',name='franka',usd_path=str(ROOT/cfg.robot.usd_path),position=np.array(cfg.robot.base_m)))
    from demos.lab_cuvette_ext02.build import source_mesh
    from demos.lab_cuvette_external.build import mat
    UsdShade.MaterialBindingAPI.Apply(table.prim).Bind(mat(stage,'/World/TablePhysics',cfg),materialPurpose='physics')
    ct=PhysxSchema.PhysxCollisionAPI.Apply(table.prim);ct.CreateContactOffsetAttr(cfg.physics.contact_offset_m);ct.CreateRestOffsetAttr(0.)
    old=OmegaConf.load(ROOT/'config/lab_cuvette_loading/V0.yaml');robot.set_joints_default_state(positions=np.array([0,-.785,0,-2.356,0,1.571,.785,.04,.04]))
    api=PhysxSchema.PhysxSceneAPI.Apply(stage.GetPrimAtPath('/physicsScene'));api.CreateEnableGPUDynamicsAttr(False);api.CreateBroadphaseTypeAttr('MBP');api.CreateSolverTypeAttr(cfg.physics.solver);api.CreateEnableCCDAttr(cfg.physics.ccd)
    pm=UsdShade.Material.Define(stage,'/World/FingerPhysics');ma=UsdPhysics.MaterialAPI.Apply(pm.GetPrim());ma.CreateStaticFrictionAttr(cfg.physics.finger_static_friction);ma.CreateDynamicFrictionAttr(cfg.physics.finger_dynamic_friction);ma.CreateRestitutionAttr(cfg.physics.restitution)
    pa=PhysxSchema.PhysxMaterialAPI.Apply(pm.GetPrim());pa.CreateFrictionCombineModeAttr('average');pa.CreateRestitutionCombineModeAttr('average')
    for prim in stage.Traverse():
        if prim.HasAPI(UsdPhysics.ArticulationRootAPI):
            a=PhysxSchema.PhysxArticulationAPI.Apply(prim);a.CreateSolverPositionIterationCountAttr(cfg.physics.position_iterations);a.CreateSolverVelocityIterationCountAttr(cfg.physics.velocity_iterations)
        if str(prim.GetPath()).startswith('/World/Franka') and prim.HasAPI(UsdPhysics.RigidBodyAPI):
            PhysxSchema.PhysxContactReportAPI.Apply(prim).CreateThresholdAttr(0.)
        if str(prim.GetPath()).startswith('/World/Franka') and prim.HasAPI(UsdPhysics.CollisionAPI):
            a=PhysxSchema.PhysxCollisionAPI.Apply(prim);a.CreateContactOffsetAttr(cfg.physics.contact_offset_m);a.CreateRestOffsetAttr(cfg.physics.rest_offset_m)
            if 'finger' in str(prim.GetPath()):UsdShade.MaterialBindingAPI.Apply(prim).Bind(pm,materialPurpose='physics')
        n=prim.GetName()
        if n.startswith('panda_joint') and prim.IsA(UsdPhysics.RevoluteJoint):
            i=int(n.replace('panda_joint',''))-1;a=UsdPhysics.DriveAPI.Apply(prim,'angular');a.CreateTypeAttr('force');a.CreateStiffnessAttr(old.robot.arm_kp[i]*np.pi/180);a.CreateDampingAttr(old.robot.arm_kd[i]*np.pi/180);a.CreateMaxForceAttr(old.robot.max_effort[i]);PhysxSchema.PhysxJointAPI.Apply(prim).CreateMaxJointVelocityAttr(old.robot.max_velocity[i]*180/np.pi)
        if n in ['panda_finger_joint1','panda_finger_joint2']:
            a=UsdPhysics.DriveAPI.Apply(prim,'linear');a.CreateTypeAttr('force');a.CreateStiffnessAttr(old.robot.finger_kp);a.CreateDampingAttr(old.robot.finger_kd);a.CreateMaxForceAttr(old.robot.max_effort[7]);PhysxSchema.PhysxJointAPI.Apply(prim).CreateMaxJointVelocityAttr(old.robot.max_velocity[7])
    hand=world.scene.add(SingleRigidPrim(prim_path='/World/Franka/panda_hand',name='hand'))
    gripper_bodies={'panda_hand':hand}
    for name in ['panda_leftfinger','panda_rightfinger']:gripper_bodies[name]=world.scene.add(SingleRigidPrim(prim_path='/World/Franka/'+name,name=name+'_state'))
    filters=[str(p.GetPath()) for p in stage.Traverse() if p.HasAPI(UsdPhysics.CollisionAPI) and not any(str(p.GetPath()).startswith('/World/'+x) for x in ['Franka','Cuvette','Distractor'])]
    env=RigidContactView(prim_paths_expr='/World/Cuvette',filter_paths_expr=filters,name='external_contacts',max_contact_count=4096)
    fingers=RigidContactView(prim_paths_expr=['/World/Franka/panda_leftfinger','/World/Franka/panda_rightfinger'],filter_paths_expr=[['/World/Cuvette'],['/World/Cuvette']],name='external_fingers',max_contact_count=256)
    world.reset();solver=KinematicsSolver(robot);solver.get_kinematics_solver().set_robot_base_pose(np.array(cfg.robot.base_m),np.array([1.,0,0,0]));orientation=euler_angles_to_quat(np.array([np.pi,0,np.radians(float(cfg.robot.gripper_yaw_deg))]))
    initial_tcp=source+np.array([0,0,.28]);cfg.robot.initial_tcp_m=initial_tcp.tolist();ik,valid=solver.compute_inverse_kinematics(initial_tcp,orientation)
    if not valid:raise RuntimeError('Initial TCP unreachable')
    q=robot.get_joint_positions().copy();q[np.array(ik.joint_indices,dtype=int)]=ik.joint_positions;q[7:]=.04;robot.set_joints_default_state(positions=q)
    if args.initial_state:
        q=np.array(json.loads(args.initial_state.read_text())['joints'],dtype=float);robot.set_joints_default_state(positions=q)
    errors=[]
    for _ in range(2):
        world.reset();errors.append(float(np.linalg.norm(cup.get_world_pose()[0]-cup_start)))
    robot.set_joint_positions(q);ac=robot.get_articulation_controller();ac.set_gains(kps=np.r_[old.robot.arm_kp,[old.robot.finger_kp]*2],kds=np.r_[old.robot.arm_kd,[old.robot.finger_kd]*2]);ac.set_max_efforts(np.array(old.robot.max_effort));robot._articulation_view.set_max_joint_velocities(np.array([old.robot.max_velocity]));ac.apply_action(ArticulationAction(joint_positions=q))
    cup_fingers=RigidContactView(prim_paths_expr='/World/Cuvette',filter_paths_expr=['/World/Franka/panda_leftfinger','/World/Franka/panda_rightfinger'],name='cup_fingers',max_contact_count=1024)
    for v in [env,fingers,cup_fingers]:v.initialize()
    write(output/'reset_check.json',dict(errors_m=errors,passed=max(errors)<1e-6))
    return locals()

def run(args,app,output,cfg):
    import cv2,shutil
    from scipy.spatial.transform import Rotation
    from pxr import UsdGeom,UsdPhysics,PhysxSchema,PhysicsSchemaTools
    import omni.physx
    from isaacsim.sensors.camera import Camera
    from isaacsim.core.utils.viewports import set_camera_view
    from isaacsim.core.utils.types import ArticulationAction
    from demos.lab_cuvette_ext02.build import source_mesh
    from demos.lab_cuvette_demo04.collector import Demo04Collector
    from demos.lab_cuvette_loading.scene import tcp
    start=time.monotonic();output.mkdir(exist_ok=False);OmegaConf.save(cfg,output/'config.yaml');ctx=make_scene(args,app,output,cfg)
    world,stage,cup,robot,hand,solver,ac,env,fingers,cf,old,orientation,last_q=[ctx[k] for k in ['world','stage','cup','robot','hand','solver','ac','env','fingers','cup_fingers','old','orientation','q']]
    full=cfg.mode=='workflow';hz=cfg.physics.hz;control=cfg.physics.control_hz;sub=hz//control;dt=1/hz;spec=cfg.demo_release
    if full:
        from demos.lab_cuvette_demo04.preflight import inspect
        preflight=inspect(cfg,output)
        if not preflight['passed'] and not (args.preinsert_diagnostic and preflight['preinsert_passed']) and not args.scene_only:raise RuntimeError('Original seat geometry blocked; no full task executed. Use --preinsert-diagnostic only for the explicitly bounded non-inserting diagnostic.')
    source=ctx['source'];floor=ctx['fixtures']['target_floor'] if full else np.r_[source[:2]+[.03,.02],cfg.scene.table_top_m]
    cameras={}
    set_camera_view(eye=np.array([-.75,-.95,1.75]),target=np.array([.30,.12,1.02]))
    # The display camera is independent of the two recorded observation views.
    views=[('camera_1_rgb','/World/Observation',[-.75,-.95,1.75],[.30,.12,1.02],(256,256),2.4),('camera_2_rgb','/World/Franka/panda_hand/WristCamera',[.10,-.18,.98],[-.04,-.22,.77],(256,256),1.2),('wide','/World/Main',[-.75,-.95,1.75],[.30,.12,1.02],(1920,1080),float(cfg.video.get('main_focal_length_cm',1.6))),('close','/World/Close',floor+ctx['fixtures']['opening_direction_world']*.16+[0,0,.21],floor+[0,0,.037],(640,640),3.5)]
    for key,path,eye,target,size,focal in views:
        c=Camera(path,name=key,frequency=60,resolution=size);c.set_focal_length(focal);c.set_clipping_range(.0001,10.);set_camera_view(eye=np.array(eye),target=np.array(target),camera_prim_path=path);c.initialize();cameras[key]=c
        if key=='camera_2_rgb':
            eye=np.array([.1,0,.04]);target=np.array(cfg.robot.tcp_local_m)+[0,0,.015];z=eye-target;z/=np.linalg.norm(z);x=np.cross([0,1,0],z);x/=np.linalg.norm(x);y=np.cross(z,x);qq=Rotation.from_matrix(np.column_stack([x,y,z])).as_quat();c.set_local_pose(eye,np.r_[qq[3],qq[:3]],camera_axes='usd')
    for _ in range(5):world.render()
    # make_scene resets the initial state. No late teleport that invalidates broadphase.
    world.render()
    if args.scene_only:
        from demos.lab_cuvette_demo04.static_review import save_review
        result=save_review(ctx,cameras,cfg,output)
        world.stop();world.clear();return result
    m=source_mesh();m.vertices[:,:2]*=float(cfg.vessel.xy_scale);com_local=np.asarray(cup.get_com()[0]).reshape(3);rb=UsdPhysics.RigidBodyAPI(cup.prim)
    rcfg=OmegaConf.create(OmegaConf.to_container(cfg,resolve=True));rcfg.version='V0_demo04';rcfg.physics.hz=hz;rcfg.physics.control_hz=control;rcfg.task.control_hz=control;rcfg.task.instruction='White6x6 rack; corrected12.5mm vessel; original12.6mm internal A. Geometry gate controls full execution.'
    phases=['RESET','APPROACH_SOURCE','GRASP','EXTRACT','TRANSPORT','ALIGN','INSERT','SUPPORT_TRANSFER','OPEN','RETREAT','VERIFY','GATE_RETRACT','DIAGNOSTIC_HOLD','JAM_RETRACT'];rcfg.control.phases_s={k:0 for k in phases}
    contract=dict(version='V0_demo04',scene_mode='native_nominal',asset_manifest_sha256=hashlib.sha256((ROOT/cfg.asset_directory/'manifest.json').read_bytes()).hexdigest(),instrument_count=1,scene_correspondence=dict(accepted=bool(preflight['scene_structure_pass']),evidence=['single instrument root oriented toward rack; corrected nominal12.5mm vessel; all original seats active','geometry_preflight.json']),geometry_audit=dict(accepted=bool(preflight['geometry_gate_passed'])),source_slot=dict(id=ctx['fixtures']['source_slot_id'],required_clearance_m=.01),target_seat=dict(id=ctx['fixtures']['target_seat_id'],inside_sample_chamber=True,user_role_confirmed=True,manufacturer_identity_confirmed=False,minimum_depth_m=ctx['fixtures']['target_depth_m']-.0001),minimum_retreat_clearance_m=.04,native_pair_verified=False,real_calibrated=False,runtime_integrity=dict(verified=True,method='dynamic contact only; no runtime pose assignment, attachment or collision-disable code'))
    write(output/'scene_contract.json',contract)
    collector=Demo04Collector(rcfg,output,False,scene_contract=contract);collector.begin_episode(0,ctx['cup_start']);collector.file.attrs.update(overlap_scope='source rack analytic envelope and table only; native seat penetration unavailable',native_seat_overlap_measured=False,demonstrator_uses_object_truth=True,nominal_dimensions_source='user supplied',single_instrument=True)
    movie=cv2.VideoWriter(str(output/'main.mp4'),cv2.VideoWriter_fourcc(*'mp4v'),30,(1920,1080));close_movie=cv2.VideoWriter(str(output/'closeup.mp4'),cv2.VideoWriter_fourcc(*'mp4v'),30,(640,640));assert movie.isOpened() and close_movie.isOpened()
    rows=[];events=[];native=[];phase='RESET';phase_start=0.;t=0.;steps=0;target=ctx['initial_tcp'].copy();grip=.04;effort=8.;qcmd=last_q.copy();cached_target=None;cached_ik=None;initial_tcp=target.copy();anchor=lift=transport=align=None;contact_target=None;open_target=None;ready=None;clear=None;settled=None;relative=None;source_initial=None;status='RUNNING';flags={k:False for k in ['support_valid','grasp_success','extract_success','transport_success','loaded','released','retreated','stable']};quality=[];descent_stopped=False;last_video_t=-1.;forbidden_contact=False
    from demos.lab_cuvette_demo04.runtime_geometry import fixture_measure,hand_clearance
    from demos.lab_cuvette_demo04.scene import link_local_collision_points
    link_points=link_local_collision_points(cfg);link_points={k:np.array([[x,y,z] for x in [v[:,0].min(),v[:,0].max()] for y in [v[:,1].min(),v[:,1].max()] for z in [v[:,2].min(),v[:,2].max()]]) for k,v in link_points.items()}
    edges=np.asarray(m.edges_unique)
    target_base_indices=[i for i,p in enumerate(ctx['filters']) if p.endswith('/Collision/SourceMesh3')]
    if len(target_base_indices)!=1:raise RuntimeError('Unique target support base not found: '+str(ctx['filters']))
    def friction(view):
        fs,pts,counts,starts=view.get_friction_data(dt=dt);fs=np.asarray(fs);out=np.zeros(np.asarray(counts).shape+(3,))
        for index in np.ndindex(out.shape[:-1]):
            n=int(np.asarray(counts)[index]);st=int(np.asarray(starts)[index]);out[index]=fs[st:st+n].sum(0)
        return out
    def capture():
        p,quat=cup.get_world_pose();rot=Rotation.from_quat(np.r_[quat[1:],quat[0]]);vs=rot.apply(m.vertices)+p;bottom=float(vs[:,2].min());com=rot.apply(com_local)+p
        fm=np.asarray(cf.get_contact_force_matrix(dt=dt)).reshape(-1,2,3).sum(0);ff=friction(cf).reshape(-1,2,3).sum(0)
        em=np.asarray(env.get_contact_force_matrix(dt=dt)).reshape(-1,len(ctx['filters']),3).sum(0);ef=friction(env).reshape(-1,len(ctx['filters']),3).sum(0)
        force=em.sum(0)+ef.sum(0);finger_mag=np.linalg.norm(fm,axis=1)
        hp,hq=hand.get_world_pose();hr=Rotation.from_quat(np.r_[hq[1:],hq[0]]);relq=(hr.inv()*rot).as_quat();fd=np.full(3,np.nan);omega=np.full(3,np.nan)
        if rows:
            prev=rows[-1];fd=(com-prev['com_world_m'])/dt;qr=Rotation.from_quat(np.r_[prev['quaternion'][1:],prev['quaternion'][0]]);omega=(rot*qr.inv()).as_rotvec()/dt
        data=ctx['fixtures'];target_measure=fixture_measure(vs,edges,floor,data['instrument_rotation'],data['target_inner_m'],data['target_depth_m'])
        source_measure=fixture_measure(vs,edges,source,data['rack_rotation'],data['source_inner_m'],data['source_depth_m'])
        gap=target_measure['gap'];xy=((p-floor)@data['instrument_rotation'])[:2];depth=target_measure['depth'] if np.max(abs(xy))<.015 else float('nan')
        penetration=max(0.,cfg.scene.table_top_m-bottom,source_measure['penetration'])
        support_target=(em+ef)[target_base_indices].sum(0)
        clearance=hand_clearance(link_points,ctx['gripper_bodies'],vs)
        geom=dict(source_slot_id=data['source_slot_id'],target_seat_id=data['target_seat_id'],source_supported_inside_designated_slot=bool(source_measure['inside'] and abs(source_measure['gap'])<=spec.bottom_distance_m and force[2]>=spec.min_support_N),source_clearance_m=bottom-data['source_rim_z'],depth_m=depth,bottom_signed_gap_m=gap,inside_checked_target_void=None,native_target_penetration_m=None,native_target_penetration_available=False,robot_to_vessel_clearance_m=clearance,forbidden_robot_environment_contact=forbidden_contact)
        tilt=float(np.degrees(np.arccos(np.clip(rot.as_matrix()[2,2],-1,1))))
        # USD readback is synchronized but may be stale under Fabric; retain raw.
        uv=rb.GetVelocityAttr().Get();uw=rb.GetAngularVelocityAttr().Get()
        return dict(t=t,engine_time=world.current_time,physics_step=steps,phase=phase,position=np.array(p),quaternion=np.array(quat),com_world_m=com,linear_velocity=np.array(cup.get_linear_velocity()),angular_velocity=np.array(cup.get_angular_velocity()),usd_linear_velocity=np.array(uv if uv is not None else [np.nan]*3),usd_angular_velocity_deg_s=np.array(uw if uw is not None else [np.nan]*3),fd_com_velocity=fd,fd_angular_velocity=omega,source_bottom_z_m=bottom,source_bottom_gap_m=max(0.,source_measure['gap']),source_penetration_m=penetration,target_bottom_signed_gap_m=gap,depth_m=depth,xy_error_m=xy,tilt_deg=tilt,support_force_vector_N=force,target_support_force_vector_N=support_target,independent_geometry=geom,environment_normal_force_matrix_N=em,environment_friction_N=ef,environment_normal_sum_norms_N=float(np.linalg.norm(em,axis=1).sum()),finger_force_N=finger_mag,finger_force_vectors_on_cup_N=fm,finger_friction_on_cup_N=ff,actual_tcp=tcp(dict(hand=hand),cfg),target_tcp=target.copy(),command_q=qcmd.copy(),joints=robot.get_joint_positions().copy(),joint_velocities=robot.get_joint_velocities().copy(),gripper_effort_limit_N=effort,gripper_target_m=grip,native_seat_force_semantics='whole seat force; not separated bottom support',descent_stopped=descent_stopped,cup_in_hand_position_m=hr.inv().apply(p-hp),cup_in_hand_quaternion=np.r_[relq[3],relq[:3]])
    def observation(r):
        return dict(control_aux={k:r[k] for k in ['command_q','gripper_effort_limit_N','gripper_target_m']},independent_geometry=r['independent_geometry'],target_support_force_vector_N=r['target_support_force_vector_N'],camera_data={k:np.transpose(cameras[k].get_rgb()[:,:,:3],(2,0,1)).astype(np.uint8) for k in ['camera_1_rgb','camera_2_rgb']},joint_positions=r['joints'],simulation_time=r['t'],tcp=r['actual_tcp'],object_position=r['position'],object_orientation=r['quaternion'],phase=r['phase'],target_tcp=r['target_tcp'],metrics=dict(depth_m=r['depth_m'],xy_error_m=r['xy_error_m'],tilt_rad=np.radians(r['tilt_deg']),yaw_error_rad=np.nan,overlap_m=r['source_penetration_m'],finger_contact_N=r['finger_force_N'],environment_contact_N=float(np.linalg.norm(r['support_force_vector_N']))),**{k:r[k] for k in ['linear_velocity','angular_velocity','usd_linear_velocity','usd_angular_velocity_deg_s','fd_com_velocity','fd_angular_velocity','support_force_vector_N','source_bottom_z_m','source_penetration_m','finger_force_vectors_on_cup_N','finger_friction_on_cup_N']})
    def enter(name):
        nonlocal phase,phase_start,ready
        events.append(dict(t=t,event='phase',previous=phase,next=name,actual=rows[-1]));phase=name;phase_start=t;ready=None;print('DEMO_PHASE',output.name,f'{t:.3f}',name,flush=True)
    def smooth(a,b,u):
        u=np.clip(u,0.,1.);return a+(3*u*u-2*u*u*u)*(b-a)
    def quiet(seconds):
        w=[x for x in rows if x['t']>=t-seconds-1e-8]
        if not w or w[-1]['t']-w[0]['t']<seconds-1e-6:return False
        ps=np.array([x['position'] for x in w]);qs=np.array([x['quaternion'] for x in w]);qs/=np.linalg.norm(qs,axis=1)[:,None]
        return bool(np.linalg.norm(ps-ps[0],axis=1).max()<=spec.position_drift_m and np.degrees(2*np.arccos(np.clip(abs(qs@qs[0]),0,1))).max()<=spec.orientation_change_deg and max(x['source_penetration_m'] for x in w)<=spec.penetration_m)
    def supported(r):return bool(abs(r['target_bottom_signed_gap_m'])<=spec.bottom_distance_m and r['target_support_force_vector_N'][2]>=spec.min_support_N and r['tilt_deg']<=spec.max_tilt_deg and np.max(abs(r['xy_error_m']))<=float(cfg.control.alignment_budget_m))
    def video(r):
        nonlocal last_video_t
        if t-last_video_t<1/30-1e-8:return
        last_video_t=t;frame=cv2.cvtColor(cameras['wide'].get_rgb()[:,:,:3],cv2.COLOR_RGB2BGR);detail=cv2.cvtColor(cameras['close'].get_rgb()[:,:,:3],cv2.COLOR_RGB2BGR)
        if phase in ['ALIGN','INSERT','SUPPORT_TRANSFER','OPEN','RETREAT','VERIFY']:frame[432:1072,1272:1912]=detail
        gap_label=f'{r["target_bottom_signed_gap_m"]*1000:.3f}mm' if np.max(abs(r['xy_error_m']))<.015 else 'outside target'
        for text,y in [(f'V0_demo04  {cfg.variant}  {cfg.mode}  t={t:.3f}s  {phase}',32),('ONE INSTRUMENT | 12.5mm VESSEL + ORIGINAL12.6mm A | NOT CALIBRATED',63),(f'{ctx["fixtures"]["source_slot_id"]} -> internal A | bottom gap {gap_label} | tilt {r["tilt_deg"]:.3f}deg | seat total Fz {r["target_support_force_vector_N"][2]:.3f}N',94)]:
            cv2.putText(frame,text,(12,y),cv2.FONT_HERSHEY_SIMPLEX,.69,(0,0,0),4);cv2.putText(frame,text,(12,y),cv2.FONT_HERSHEY_SIMPLEX,.69,(255,255,255),1)
        cv2.putText(detail,f'{t:.3f}s {phase}',(8,24),cv2.FONT_HERSHEY_SIMPLEX,.55,(255,255,255),1);movie.write(frame);close_movie.write(detail)
    def callback(headers,data):
        nonlocal forbidden_contact
        for h in headers:
            paths=[str(PhysicsSchemaTools.intToSdfPath(h.collider0)),str(PhysicsSchemaTools.intToSdfPath(h.collider1))]
            if not (any(p.startswith('/World/Cuvette') for p in paths) or (any(p.startswith('/World/Franka') for p in paths) and any(p.startswith('/World/Instrument') or p.startswith('/World/SourceRack') or p.startswith('/World/NeighborCuvette') for p in paths))):continue
            pts=[]
            for j in range(h.contact_data_offset,h.contact_data_offset+h.num_contact_data):
                d=data[j];v=lambda a:[float(a.x),float(a.y),float(a.z)];imp=v(d.impulse);pts.append(dict(position_m=v(d.position),normal=v(d.normal),impulse_Ns=imp,force_N=(np.array(imp)/dt).tolist(),separation_m=float(d.separation)))
            if any(np.linalg.norm(p['force_N'])>.01 or p['separation_m']<-.00005 for p in pts) and any(p.startswith('/World/Franka') for p in paths) and not any(p.startswith('/World/Cuvette') for p in paths):forbidden_contact=True
            native.append(dict(step=steps+1,t=(steps+1)/hz,phase=phase,colliders=paths,type=str(h.type),points=pts))
    subscription=omni.physx.get_physx_simulation_interface().subscribe_contact_report_events(callback)
    r=capture();rows.append(r);state=observation(r);write(output/'initial.json',r);video(r)
    stage.Flatten().Export(str(output/'initial_scene.usda'))
    try:
        while t<cfg.control.timeout_s and app.is_running():
            r=rows[-1];u=t-phase_start
            if phase=='RESET':
                if u>=4.:
                    if not quiet(3.) or r['tilt_deg']>1.:status='INITIAL_SUPPORT_INVALID';break
                    flags['support_valid']=True;source_initial=r['position'].copy();anchor=source_initial+[0,0,cfg.robot.grasp_above_bottom_m]
                    lift=anchor+[0,0,float(cfg.control.transport_bottom_z_m-source_initial[2])];transport=np.r_[floor[:2],lift[2]];align=transport.copy();enter('APPROACH_SOURCE')
            elif phase=='APPROACH_SOURCE':
                target=smooth(initial_tcp,anchor,u/cfg.control.approach_s);grip=.04
                if u>=7.:
                    if np.linalg.norm(r['actual_tcp']-anchor)>.002:status='CONTROL_OR_IK_FAILURE';break
                    enter('GRASP')
            elif phase=='GRASP':
                target=anchor;grip=.04*(1-min(1.,u/2))
                if u>=2.5:
                    if not np.all(r['finger_force_N']>.02):status='GRASP_FAILED';break
                    flags['grasp_success']=True;relative=r['position']-r['actual_tcp'];enter('EXTRACT')
            elif phase=='EXTRACT':
                grip=0.;target=smooth(anchor,lift,u/cfg.control.extract_s)
                if u>=7.:
                    flags['extract_success']=bool(r['source_bottom_z_m']>ctx['fixtures']['source_rim_z']+.010 and np.all(r['finger_force_N']>.02))
                    if not flags['extract_success']:status='GRASP_SLIP';break
                    enter('TRANSPORT')
            elif phase=='TRANSPORT':
                waypoint=np.array([lift[0],transport[1],lift[2]]);duration=cfg.control.transport_s/2
                if u<duration:target=smooth(lift,waypoint,u/duration)
                elif u<cfg.control.transport_s:target=smooth(waypoint,transport,(u-duration)/duration)
                else:
                    # The held vessel can rotate within a real bilateral grasp.
                    # Use the already declared truth feedback during the final
                    # stationary second instead of confusing TCP arrival with
                    # vessel arrival. Keep the existing3mm stage gate unchanged.
                    target[:2]+=-ctx['fixtures']['instrument_rotation'][:2,:2]@np.clip(.15*np.asarray(r['xy_error_m']),-.00002,.00002)
                grip=0.
                if u>=cfg.control.transport_s+1.:
                    flags['transport_success']=bool(np.linalg.norm(r['position'][:2]-floor[:2])<.003 and np.all(r['finger_force_N']>.02))
                    if not flags['transport_success']:status='HELD_POSE_DEVIATION_AFTER_TRANSPORT';break
                    # Re-estimate the held offset after actual transport. Gravity
                    # tracking bias means nominal TCP/old grasp offsets do not
                    # guarantee that the physical vessel is over this narrow seat.
                    relative=r['position']-r['actual_tcp']
                    align=np.r_[floor[:2]-relative[:2],transport[2]];enter('ALIGN')
            elif phase=='ALIGN':
                grip=0.
                if u<.5:target=smooth(transport,align,u/.5)
                else:target[:2]+=-ctx['fixtures']['instrument_rotation'][:2,:2]@np.clip(.15*np.asarray(r['xy_error_m']),-.00002,.00002)
                if 2.5<=u<2.5+1/control:
                    if np.max(abs(r['xy_error_m']))>float(cfg.control.diagnostic_alignment_budget_m if args.preinsert_diagnostic else cfg.control.alignment_budget_m):status='ACTUAL_ALIGNMENT_FAILED';break
                    events.append(dict(t=t,event='prealignment_accepted_then_low_speed_approach',actual_xy_m=r['xy_error_m']))
                if u>=2.5:
                    stop=ctx['fixtures']['target_rim_z']+float(cfg.control.diagnostic_safe_bottom_above_rim_m)
                    if args.preinsert_diagnostic and r['source_bottom_z_m']<=stop+.00002:
                        descent_stopped=True;contact_target=target.copy();events.append(dict(t=t,event='known_geometry_gate_stop_before_native_tabs',source_bottom_z_m=r['source_bottom_z_m'],safe_stop_z_m=stop,actual_seat_force_N=r['target_support_force_vector_N']));enter('GATE_RETRACT')
                    elif args.preinsert_diagnostic:
                        speed=float(cfg.control.diagnostic_near_speed_m_s if r['source_bottom_z_m']-stop<.003 else cfg.control.diagnostic_approach_speed_m_s)
                        target[2]-=min(speed/control,max(0.,r['source_bottom_z_m']-stop)*.2+1e-7)
                    elif preflight['geometry_gate_passed']:
                        enter('INSERT')
                    else:status='GEOMETRY_BLOCKED_NOT_EXECUTED';break
            elif phase=='GATE_RETRACT':
                target=smooth(contact_target,contact_target+[0,0,.01],u/2);grip=0.
                if u>=2.5:enter('DIAGNOSTIC_HOLD')
            elif phase=='DIAGNOSTIC_HOLD':
                target=contact_target+[0,0,.01];grip=0.
                if u>=1.0:status='GEOMETRY_BLOCKED_PREINSERT';break
            elif phase=='JAM_RETRACT':
                target=smooth(contact_target,contact_target+[0,0,.01],u/2);grip=0.
                if u>=2.5:status='JAM_DETECTED';break
            elif phase=='INSERT':
                grip=0.
                from demos.lab_cuvette_demo04.safety import jam_reason
                jam=jam_reason(rows,cfg.control.jam_detection)
                if jam:
                    descent_stopped=True;contact_target=target.copy();events.append(dict(t=t,event='jam_stop_and_retract',reason=jam));enter('JAM_RETRACT')
                    continue
                # Privileged state feedback commands robot joints only. The
                # vessel remains dynamic and moves solely through contact.
                target[:2]+=-ctx['fixtures']['instrument_rotation'][:2,:2]@np.clip(.08*np.asarray(r['xy_error_m']),-.00001,.00001)
                if r['target_support_force_vector_N'][2]>.10 and abs(r['target_bottom_signed_gap_m'])<.0002:
                    descent_stopped=True;contact_target=target.copy();events.append(dict(t=t,event='stop_downward_command_on_actual_contact',force=r['support_force_vector_N'],bottom=r['source_bottom_z_m']));enter('SUPPORT_TRANSFER')
                else:
                    speed=cfg.control.final_speed_m_s if r['target_bottom_signed_gap_m']<.001 else cfg.control.insert_speed_m_s
                    target=target+[0,0,-min(speed/control,max(0.,r['target_bottom_signed_gap_m'])*.2+1e-6)]
                if u>35.:status='INSERT_BLOCKED';break
            elif phase=='SUPPORT_TRANSFER':
                # Stop descent; relieve compressive load with bounded upward-only
                # axial corrections, then reduce finger normal effort in stages.
                effort=float(8.-7.95*min(1.,u/spec.unload_seconds))
                recent=rows[-max(1,int(.1*hz)):];fz=float(np.mean([x['target_support_force_vector_N'][2] for x in recent]))
                if fz>.2462 and target[2]<contact_target[2]+.001:target=target+[0,0,min(1e-5,max(0.,fz-.2462)*2e-6)]
                if u>=spec.unload_seconds and supported(r) and all(supported(x) for x in rows[-sub:]) and quiet(spec.support_window_s):
                    if ready is None:ready=t
                    if t-ready>=spec.support_window_s:
                        flags['loaded']=True;open_target=target.copy();enter('OPEN')
                else:ready=None
                if u>=10.:
                    # Preserve actual trajectory; no perpetual speed-only veto.
                    status='SUPPORT_TRANSFER_FAILED';break
            elif phase=='OPEN':
                target=open_target;effort=.5;grip=.04*min(1.,u/spec.open_seconds)
                if np.all(r['finger_force_N']<.01) and np.all(r['joints'][7:]>.025) and supported(r):
                    if clear is None:clear=t
                    if t-clear>=spec.clear_seconds:flags['released']=True;enter('RETREAT')
                else:clear=None
                if u>7.:status='RELEASE_FAILED';break
            elif phase=='RETREAT':
                grip=.04;effort=8.;raised=open_target+np.array([0,0,cfg.control.retreat_lift_m]);withdrawn=raised+np.r_[cfg.control.retreat_lateral_m,0.]
                target=smooth(open_target,raised,u/2) if u<2 else smooth(raised,withdrawn,(u-2)/3)
                if u>=5.5:
                    flags['retreated']=bool(r['independent_geometry']['robot_to_vessel_clearance_m']>=.04 and np.all(r['finger_force_N']<.01))
                    if not flags['retreated']:status='RETREAT_FAILED';break
                    enter('VERIFY')
            elif phase=='VERIFY':
                target=open_target+np.r_[cfg.control.retreat_lateral_m,cfg.control.retreat_lift_m];grip=.04
                if u>=spec.observe_s+.1:
                    flags['stable']=bool(quiet(spec.observe_s) and supported(r) and np.all(r['finger_force_N']<.01));status='WORKFLOW_SUCCESS' if all(flags.values()) else 'UNSTABLE_AFTER_RELEASE';break
            if cached_target is None or not np.array_equal(target,cached_target):
                ik,ok=solver.compute_inverse_kinematics(target,orientation,position_tolerance=old.robot.ik_position_tolerance_m,orientation_tolerance=old.robot.ik_orientation_tolerance_rad)
                if not ok:status='CONTROL_OR_IK_FAILURE';break
                cached_target=target.copy();cached_ik=ik
            ik=cached_ik;q=r['joints'].copy();q[np.asarray(ik.joint_indices,int)]=ik.joint_positions;q[7:]=grip;limit=np.array(old.robot.max_velocity)/control;q=np.clip(q,last_q-limit,last_q+limit);last_q=q.copy();qcmd=q.copy()
            ac.set_max_efforts(np.r_[old.robot.max_effort[:7],[effort]*2]);action=ArticulationAction(joint_positions=q);ac.apply_action(action);state['phase']=phase;state['target_tcp']=target.copy()
            for _ in range(sub):
                world.step(render=False);steps+=1;t=steps/hz;r=capture();rows.append(r)
            world.render();after=observation(r);collector.cache_transition(state,action,after,dict(status='RUNNING',full_success=False,stage_progress=flags,seed=args.seed));state=after;video(r)
            if not np.isfinite(np.r_[r['position'],r['quaternion'],r['linear_velocity'],r['angular_velocity']]).all():status='PHYSICS_INVALID_NONFINITE';break
            if forbidden_contact:status='FORBIDDEN_ROBOT_ENVIRONMENT_CONTACT';break
            if phase!='RESET' and (r['source_penetration_m']>.00005 or r['tilt_deg']>spec.max_actual_tilt_deg):status='PHYSICS_INVALID_GEOMETRY';break
            if phase in ['SUPPORT_TRANSFER','OPEN','RETREAT','VERIFY'] and np.linalg.norm(r['fd_com_velocity'])>.10:status='DROPPED_OR_LARGE_MOTION';break
        if status=='RUNNING':status='TIMEOUT'
        quality=['ROBOT_AND_VESSEL_DYNAMICS_NOT_REAL_CALIBRATED','GEOMETRY_CHECKS_SAMPLED_NOT_GLOBAL_NATIVE_SHAPE_PROOF']
        if max(x['source_penetration_m'] for x in rows)>spec.penetration_m:
            quality.append('SOURCE_GEOMETRY_PENETRATION_EXCEEDS_50UM')
            if status=='WORKFLOW_SUCCESS':status='PHYSICS_INVALID_INITIAL_OR_TRANSIENT_PENETRATION'
        if any(np.linalg.norm(np.asarray(x['linear_velocity'])-np.asarray(x['fd_com_velocity']))>.001 for x in rows[-int(3*hz):]):quality.append('NATIVE_VS_POSE_VELOCITY_MISMATCH_RETAINED')
        unintended=[e for e in native if e['points'] and not any(p.startswith('/World/Cuvette') for p in e['colliders'])]
        if unintended:
            quality.append('UNINTENDED_ROBOT_ENVIRONMENT_CONTACT')
            if status=='WORKFLOW_SUCCESS':status='UNINTENDED_ROBOT_ENVIRONMENT_CONTACT'
        success=status=='WORKFLOW_SUCCESS';result=dict(status=status,reason=status,workflow_success=success if full else False,tabletop_release_success=success if not full else None,native_pair_success=False,native_pair_executed=False,full_success=False,full_task_eligible=False,stage_progress=flags,simulation_seconds=t,wall_seconds=time.monotonic()-start,frames=collector.count,calibrated=False,variant=cfg.variant,mode=cfg.mode,physics_quality_flags=quality,environment_filter_paths=ctx['filters'])
        result.update(geometry_gate_passed=bool(preflight['geometry_gate_passed']),diagnostic_only=bool(args.preinsert_diagnostic),full_workflow_executed=not args.preinsert_diagnostic,demonstrator_uses_object_truth=True,version='V0_demo04',scene_mode='native_nominal',real_calibrated=False,data_eligible=False,source_slot_id=ctx['fixtures']['source_slot_id'],target_seat_id=ctx['fixtures']['target_seat_id'])
        write(output/'result.json',result);write(output/'physics_records.json',rows);write(output/'events.json',events);write(output/'native_contact_events.json',native)
        collector.file.flush()
        from demos.lab_cuvette_demo04.analyze import analyze
        independent=analyze(output,contract=contract);write(output/'independent_score.json',independent)
        if collector.count:
            collector.file['done'][-1]=True
            adjudication=collector.finish_episode(result,independent_score=output/'independent_score.json')
            write(output/'adjudication.json',adjudication)
        result['independent_workflow_success']=independent['workflow_success'];result['data_eligible']=independent['data_eligible']
        write(output/'execution_summary.json',result)
        test=omni.physx.get_physxunittests_interface();kp,kd=ac.get_gains();write(output/'runtime.json',dict(cup_mass=test.get_mass_information('/World/Cuvette'),com_local_m=com_local,kp=kp,kd=kd,max_effort=ac.get_max_efforts(),max_velocity=robot._articulation_view.get_joint_max_velocities(),CPU=True,solver=cfg.physics.solver,position_iterations=cfg.physics.position_iterations,velocity_iterations=cfg.physics.velocity_iterations,physics_hz=hz,control_hz=control,substeps=sub,stats=test.get_physics_stats(),contact_offset_authored=cfg.physics.contact_offset_m,rest_offset_authored=0.,native_offsets_readback=None,calibrated=False))
        stage.Flatten().Export(str(output/'final_scene.usda'))
        for key,c in cameras.items():cv2.imwrite(str(output/(key+'_final.png')),cv2.cvtColor(c.get_rgb()[:,:,:3],cv2.COLOR_RGB2BGR))
        print('DEMO_RESULT',output,status,flags,flush=True)
    finally:collector.close();movie.release();close_movie.release();world.stop();world.clear()
    return result

def main():
    import shutil
    p=argparse.ArgumentParser(description='Physical video-scene adapted rack to internal-seat workflow')
    p.add_argument('--headless',action='store_true');p.add_argument('--config',type=Path,default=ROOT/'config/lab_cuvette_loading/V0_demo04/native_nominal.yaml')
    p.add_argument('--scene-only',action='store_true');p.add_argument('--preinsert-diagnostic',action='store_true')
    p.add_argument('--arm-plan',type=Path);p.add_argument('--initial-state',type=Path);p.add_argument('--output',type=Path,required=True);p.add_argument('--seed',type=int,default=0)
    p.add_argument('--random-layout',action='store_true');p.add_argument('--source-slot');args=p.parse_args();cfg=OmegaConf.load(args.config)
    if cfg.scene_mode!='native_nominal':raise ValueError('This independent executor only implements native_nominal mode')
    if args.source_slot:cfg.rack.selected_slot_id=args.source_slot
    if args.random_layout:
        rng=np.random.default_rng(args.seed);legal=list(cfg.randomization.legal_slots);cfg.rack.selected_slot_id=legal[args.seed%len(legal)]
        ds=rng.uniform(-cfg.randomization.rack_translation_half_range_m,cfg.randomization.rack_translation_half_range_m,2)
        di=rng.uniform(-cfg.randomization.instrument_translation_half_range_m,cfg.randomization.instrument_translation_half_range_m,2)
        cfg.rack.origin_m=(np.asarray(cfg.rack.origin_m)+np.r_[ds,0.]).tolist();cfg.scene.instrument_xyz_m=(np.asarray(cfg.scene.instrument_xyz_m)+np.r_[di,0.]).tolist()
        cfg.randomization.actual=dict(seed=args.seed,source_slot_id=cfg.rack.selected_slot_id,rack_translation_m=ds.tolist(),instrument_assembly_translation_m=di.tolist(),within_slot_translation_m=[0.,0.],rotations_randomized=False)
    from demos.lab_cuvette_demo04.scene import layout
    geometry=layout(cfg);cfg.scene.instrument_yaw_deg=geometry['instrument_yaw_deg'];cfg.robot.initial_tcp_m=(geometry['source_floor']+[0,0,.28]).tolist();cfg.control.transport_waypoint_xy_m=[float(geometry['source_floor'][0]),float(geometry['target_floor'][1])];cfg.control.transport_route='source_x_then_target_y'
    args.output.mkdir(parents=True,exist_ok=False)
    files=[*Path(__file__).parent.glob('*.py'),args.config.resolve(),ROOT/'assets/lab_cuvette_loading/V0_demo04/vessel_125_mm.usda',*list((ROOT/cfg.asset_directory).glob('*'))]
    write(args.output/'provenance.json',dict(command=sys.argv,git_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),dirty=subprocess.check_output(['git','status','--short'],cwd=ROOT,text=True),sha256={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in files if f.is_file()},source_CAD_unchanged=True,derived_vessel_xy_nominal_m=.0125,scene_mode='native_nominal',native_pair_success=False,real_calibrated=False))
    for f in files:
        if f.is_file():
            dest=args.output/'source_snapshot'/f.relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(f,dest)
    from demos.lab_cuvette_demo04.preflight import inspect
    gate=inspect(cfg,args.output)
    if not args.scene_only and not args.preinsert_diagnostic and not gate['geometry_gate_passed']:
        write(args.output/'run_status.json',dict(status='GEOMETRY_BLOCKED_NOT_EXECUTED',physics_executed=False,workflow_success=None,native_pair_success=False,geometry_gate_passed=False,reason='Original A/B local tabs intersect corrected vessel; full task and fixed/random are not executed.'))
        print('DEMO_RESULT GEOMETRY_BLOCKED_NOT_EXECUTED',flush=True);return
    if args.preinsert_diagnostic:
        if args.arm_plan is None:raise RuntimeError('Diagnostic requires --arm-plan from this exact config')
        plan=json.loads(args.arm_plan.read_text())
        if not plan.get('selected') or plan.get('config_file_sha256')!=hashlib.sha256(args.config.read_bytes()).hexdigest():raise RuntimeError('Whole-arm plan missing/failed or config changed; recompute plan')
        if not np.allclose(plan['selected']['base_m'],cfg.robot.base_m,atol=1e-12,rtol=0):raise RuntimeError('Arm plan robot base differs from run')
    from isaacsim import SimulationApp
    app=SimulationApp(dict(headless=args.headless,width=1920,height=1080,extra_args=['--/app/extensions/fsWatcherEnabled=false']))
    try:run(args,app,args.output/'trial_00',cfg)
    except BaseException:
        import traceback
        write(args.output/'failure.json',dict(traceback=traceback.format_exc()));traceback.print_exc();raise
    finally:app.close()

if __name__=='__main__':main()
