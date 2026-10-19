"""Physical tabletop diagnostic, full external loading remains gated."""
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
    source=np.r_[cfg.scene.cup_xy_m,cfg.scene.table_top_m]
    cup_start=source+[0,0,cfg.scene.initial_bottom_gap_m]
    add_reference_to_stage(str(assets/(cfg.get('collision_scheme','walls28_mm')+'.usda')),'/World/Cuvette')
    cup=world.scene.add(SingleRigidPrim(prim_path='/World/Cuvette',name='external_vessel',position=cup_start))
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
    if args.initial_state:
        q=np.array(json.loads(args.initial_state.read_text())['joints'],dtype=float);robot.set_joints_default_state(positions=q)
    errors=[]
    for _ in range(2):
        world.reset();errors.append(float(np.linalg.norm(cup.get_world_pose()[0]-cup_start)))
    robot.set_joint_positions(q);ac=robot.get_articulation_controller();ac.set_gains(kps=np.r_[old.robot.arm_kp,[old.robot.finger_kp]*2],kds=np.r_[old.robot.arm_kd,[old.robot.finger_kd]*2]);ac.set_max_efforts(np.array(old.robot.max_effort));robot._articulation_view.set_max_joint_velocities(np.array([old.robot.max_velocity]));ac.apply_action(ArticulationAction(joint_positions=q))
    for v in [env,fingers]:v.initialize()
    write(output/'reset_check.json',dict(errors_m=errors,passed=max(errors)<1e-6))
    return locals()

def run(args,app,output,cfg):
    import cv2
    from scipy.spatial.transform import Rotation
    from pxr import UsdGeom
    from isaacsim.sensors.camera import Camera
    from isaacsim.core.utils.viewports import set_camera_view
    from isaacsim.core.utils.types import ArticulationAction
    from demos.lab_cuvette_ext02.build import source_mesh
    from demos.lab_cuvette_ext02.collector import DiagnosticCollector
    from demos.lab_cuvette_loading.scene import tcp
    start=time.monotonic();output.mkdir(exist_ok=False);OmegaConf.save(cfg,output/'config.yaml')
    ctx=make_scene(args,app,output,cfg)
    world=ctx['world'];stage=ctx['stage'];cup=ctx['cup'];robot=ctx['robot'];hand=ctx['hand'];solver=ctx['solver'];ac=ctx['ac'];env=ctx['env'];fingers=ctx['fingers'];old=ctx['old'];initial_tcp=ctx['initial_tcp'];orientation=ctx['orientation'];cup_start=ctx['cup_start'];q=ctx['q'];control=cfg.physics.control_hz;hz=cfg.physics.hz;substeps=hz//control;assert substeps*control==hz
    cameras={}
    for key,path,eye,target in [('camera_1_rgb','/World/Camera',[.6,-.75,1.15],[-.02,-.19,.80]),('camera_2_rgb','/World/Franka/panda_hand/WristCamera',[.1,-.18,.98],[-.04,-.22,.77])]:
        c=Camera(path,name=key,frequency=60,resolution=(256,256));c.set_focal_length(2.4 if key=='camera_1_rgb' else 1.2);c.set_clipping_range(.0001,10);set_camera_view(eye=np.array(eye),target=np.array(target),camera_prim_path=path);c.initialize();cameras[key]=c
        if key=='camera_2_rgb':
            eye=np.array([.1,0,.04]);target=np.array(cfg.robot.tcp_local_m)+[0,0,.015];z=eye-target;z/=np.linalg.norm(z);x=np.cross([0,1,0],z);x/=np.linalg.norm(x);y=np.cross(z,x);qc=Rotation.from_matrix(np.column_stack([x,y,z])).as_quat();c.set_local_pose(eye,np.r_[qc[3],qc[:3]],camera_axes='usd')
    close=Camera('/World/ReleaseCloseup',name='close',frequency=60,resolution=(512,512));close.set_focal_length(3.);close.set_clipping_range(.0001,10);set_camera_view(eye=np.array([.08,-.37,.85]),target=np.array([-.01,-.20,.775]),camera_prim_path='/World/ReleaseCloseup');close.initialize()
    for _ in range(5):world.render()
    # Initialization only. All subsequent motion is dynamic bilateral contact.
    cup.set_world_pose(cup_start,np.array([1.,0,0,0]));cup.set_linear_velocity(np.zeros(3));cup.set_angular_velocity(np.zeros(3));world.render()
    # Actual native shape consistency across the standalone and robot scenes.
    # Compare native ray hits directly; never substitute a cooking preview.
    import omni.physx
    expected=json.loads((args.support_evidence/'live_rays.json').read_text());query=omni.physx.get_physx_scene_query_interface();native_checks=[]
    for ray in expected:
        hit=query.raycast_closest(tuple(cup_start+np.array(ray['origin'])),tuple(ray['direction']),.04)
        valid=bool(hit.get('hit') and str(hit.get('collision')).startswith('/World/Cuvette'))
        point=np.array(hit['position'])-cup_start if valid else None
        native_checks.append(dict(valid_cup_hit=valid,error_m=float(np.linalg.norm(point-np.array(ray['hit_body_local']))) if valid else None,collider=hit.get('collision'),local_point_m=point))
    maximum=max((r['error_m'] for r in native_checks if r['error_m'] is not None),default=None)
    write(output/'live_shape_consistency.json',dict(compared=len(native_checks),missing=sum(not r['valid_cup_hit'] for r in native_checks),maximum_m=maximum,threshold_m=cfg.acceptance.support_geometry_m,checks=native_checks))
    if any(not r['valid_cup_hit'] for r in native_checks) or maximum is None or maximum>cfg.acceptance.support_geometry_m:
        result=dict(status='GEOMETRY_GATE_BLOCKED_NATIVE_MISMATCH',full_success=False,diagnostic_success=False,reason='Native cup surfaces differ from the support evidence')
        write(output/'result.json',result);world.stop();world.clear();return result
    m=source_mesh();rcfg=OmegaConf.create(OmegaConf.to_container(old));rcfg.version='V0_ext02';rcfg.physics.hz=hz;rcfg.physics.control_hz=control;rcfg.task.control_hz=control;rcfg.task.instruction='External vessel tabletop physical grasp, transport and supported release diagnostic'
    phases=['SETTLE','APPROACH','GRASP','LIFT','HOLD','TRANSPORT','LOWER','SUPPORT_CHECK','OPEN','CLEAR_FINGERS','RETREAT','OBSERVE'];rcfg.control.phases_s={k:0. for k in phases}
    collector=DiagnosticCollector(rcfg,output,True);collector.begin_episode(0,cup_start);collector.file.attrs.update(schema_version='labsim.lab_cuvette_loading.V0_ext02.tabletop.v1',base_learning_schema='labsim.lab_cuvette_loading.V0',task='lab_cuvette_loading_ext02_tabletop_diagnostic',scene_version='V0_ext02',full_task_eligible=False,full_success=False,full_task_executed=False,privileged_progress_columns='support_valid,grasp_success,hold_success,transport_success,released_stable,tabletop_success',omitted_task_metrics='depth_m,xy_error_m,yaw_error_rad,overlap_m')
    inertia_model=str(cfg.robot.get('inertia_model','inherited_uncalibrated'))
    collector.file.attrs.update(robot_inertia_model=inertia_model,task='lab_cuvette_loading_ext02_tabletop_inertia_proxy_diagnostic' if 'SYNTHETIC' in inertia_model else 'lab_cuvette_loading_ext02_tabletop_diagnostic')
    clip=cv2.VideoWriter(str(output/'release_closeup.mp4'),cv2.VideoWriter_fourcc(*'mp4v'),60,(512,512))
    rows=[];events=[];phase='SETTLE';phase_start=0.;t=0.;physics_steps=0;target=initial_tcp.copy();last_q=q.copy();grip=.04;anchor=None;lift=None;transport=None;relative_grip=None;bilateral_start=None;hold_start=None;ready_start=None;open_start=None;retreat_start=None;flags={k:False for k in ['support_valid','grasp_success','hold_success','transport_success','released_stable','tabletop_success']};outcome='RUNNING';tcp_cfg=OmegaConf.create(dict(robot=dict(tcp_local_m=list(cfg.robot.tcp_local_m))));s0=None;settled_report=None;cached_ik=None;cached_target=None;grip_closed=0.;grip_latched=False
    def capture():
        p,quat=cup.get_world_pose();R=Rotation.from_quat(np.r_[quat[1:],quat[0]]).as_matrix();bottom=float((m.vertices@R.T+p)[:,2].min());f=np.linalg.norm(np.asarray(fingers.get_contact_force_matrix(dt=1/hz)).reshape(2,-1,3),axis=2).sum(1);force=np.asarray(env.get_contact_force_matrix(dt=1/hz)).reshape(-1,3).sum(0)
        hp,hq=hand.get_world_pose();hr=Rotation.from_quat(np.r_[hq[1:],hq[0]]);relative_q=(hr.inv()*Rotation.from_quat(np.r_[quat[1:],quat[0]])).as_quat()
        return dict(t=t,engine_time=world.current_time,position=p,quaternion=quat,linear_velocity=cup.get_linear_velocity(),angular_velocity=cup.get_angular_velocity(),source_penetration_m=max(0.,cfg.scene.table_top_m-bottom),source_bottom_gap_m=max(0.,bottom-cfg.scene.table_top_m),source_bottom_z_m=bottom,support_force_vector_N=force,actual_tcp=tcp(dict(hand=hand),tcp_cfg),finger_force_N=f,joints=robot.get_joint_positions().copy(),joint_velocities=robot.get_joint_velocities().copy(),phase=phase,target_tcp=target.copy(),command_q=last_q.copy(),hand_position=hp,hand_quaternion=hq,cup_in_hand_position_m=hr.inv().apply(p-hp),cup_in_hand_quaternion=np.r_[relative_q[3],relative_q[:3]])
    def observation(r):
        return dict(camera_data={k:np.transpose(c.get_rgb()[:,:,:3],(2,0,1)).astype(np.uint8) for k,c in cameras.items()},joint_positions=r['joints'],simulation_time=r['t'],tcp=r['actual_tcp'],object_position=r['position'],object_orientation=r['quaternion'],phase=phase,target_tcp=target.copy(),metrics=dict(depth_m=np.nan,xy_error_m=[np.nan,np.nan],tilt_rad=float(np.arccos(np.clip(1-2*(r['quaternion'][1]**2+r['quaternion'][2]**2),-1,1))),yaw_error_rad=np.nan,overlap_m=np.nan,finger_contact_N=r['finger_force_N'],environment_contact_N=float(np.linalg.norm(r['support_force_vector_N']))),**{k:r[k] for k in ['linear_velocity','angular_velocity','source_penetration_m','source_bottom_gap_m','support_force_vector_N','cup_in_hand_position_m','cup_in_hand_quaternion']})
    def enter(name):
        nonlocal phase,phase_start
        events.append(dict(t=t,event='phase',previous=phase,next=name,actual=capture()));phase=name;phase_start=t
        print('TABLE_PHASE',output.name,f'{t:.3f}',name,flush=True)
    def smooth(a,b,f):
        f=np.clip(f,0.,1.);return a+(3*f*f-2*f*f*f)*(b-a)
    def supported(r):return abs(r['source_bottom_z_m']-cfg.scene.table_top_m)<=cfg.acceptance.release_bottom_gap_m and r['support_force_vector_N'][2]>=cfg.acceptance.release_support_force_N and np.linalg.norm(r['linear_velocity'])<=cfg.acceptance.linear_speed_m_s and np.linalg.norm(r['angular_velocity'])<=cfg.acceptance.angular_speed_rad_s
    import omni.physx
    from pxr import PhysicsSchemaTools
    native_events=[]
    def contact_callback(headers,data):
        def vec(v):return [float(v.x),float(v.y),float(v.z)]
        for h in headers:
            paths=[str(PhysicsSchemaTools.intToSdfPath(h.collider0)),str(PhysicsSchemaTools.intToSdfPath(h.collider1))]
            if not any(path.startswith('/World/Cuvette') for path in paths):continue
            points=[]
            for j in range(h.contact_data_offset,h.contact_data_offset+h.num_contact_data):
                d=data[j];impulse=vec(d.impulse);points.append(dict(position_m=vec(d.position),normal=vec(d.normal),impulse_Ns=impulse,force_N=(np.array(impulse)*hz).tolist(),separation_m=float(d.separation)))
            native_events.append(dict(t=t+1/hz,phase=phase,colliders=paths,type=str(h.type),points=points))
    subscription=omni.physx.get_physx_simulation_interface().subscribe_contact_report_events(contact_callback)
    r=capture();rows.append(r);state=observation(r);write(output/'initial.json',r)
    try:
        while t<65. and app.is_running():
            u=t-phase_start;r=rows[-1]
            if phase=='SETTLE':
                target=initial_tcp;grip=.04
                if u>=5.:
                    settled_report=measure(rows,cfg)
                    if not settled_report['static_pass']:outcome='INITIAL_SUPPORT_INVALID';break
                    flags['support_valid']=True;s0=r['position'].copy();anchor=np.r_[s0[:2],s0[2]+cfg.robot.grasp_above_bottom_m];lift=anchor+[0,0,.08];transport=lift+[.03,.02,0];enter('APPROACH')
            elif phase=='APPROACH':
                target=smooth(initial_tcp,anchor,u/6);grip=.04
                if u>=8.:
                    if np.linalg.norm(r['actual_tcp']-anchor)>.002:outcome='CONTROL_OR_IK_FAILURE';break
                    enter('GRASP')
            elif phase=='GRASP':
                target=anchor;grip=.04*(1-min(1.,u/2))
                if cfg.gripper.mode=='contact_latched' and u>=2.:
                    if not grip_latched:
                        mu=(cfg.physics.dynamic_friction+cfg.physics.finger_dynamic_friction)/2
                        nominal_N=float(cup.get_mass())*9.81/(2*mu)*cfg.gripper.contact_safety_factor
                        grip_closed=max(0.,float(np.mean(r['joints'][7:]))-nominal_N/old.robot.finger_kp);grip_latched=True
                        events.append(dict(t=t,event='grip_latch',nominal_normal_per_finger_N=nominal_N,closed_target_m=grip_closed,method='measured contact width minus calculated elastic drive preload; actual contact force still measured'))
                    grip=float(smooth(np.array(0.),np.array(grip_closed),(u-2)/1.))
                if np.all(r['finger_force_N']>.02):
                    if bilateral_start is None:bilateral_start=t
                    if t-bilateral_start>=.5:flags['grasp_success']=True
                else:bilateral_start=None
                if u>=(4. if cfg.gripper.mode=='contact_latched' else 2.5):
                    if not flags['grasp_success'] or not np.all(r['finger_force_N']>.02):outcome='GRASP_FAILED';break
                    relative_grip=r['position']-r['actual_tcp'];enter('LIFT')
            elif phase=='LIFT':
                target=smooth(anchor,lift,u/4);grip=grip_closed
                if u>=4.:enter('HOLD')
            elif phase=='HOLD':
                target=lift;grip=grip_closed
                if r['position'][2]-s0[2]>=cfg.acceptance.lift_m and np.all(r['finger_force_N']>.02):
                    if hold_start is None:hold_start=t
                    if t-hold_start>=cfg.acceptance.hold_s:flags['hold_success']=True
                else:hold_start=None
                if u>=2.:
                    if not flags['hold_success']:outcome='GRASP_SLIP';break
                    enter('TRANSPORT')
            elif phase=='TRANSPORT':
                target=smooth(lift,transport,u/4);grip=grip_closed
                if u>=4.:
                    flags['transport_success']=bool(np.linalg.norm((r['position']-s0)[:2]-[.03,.02])<.003 and np.all(r['finger_force_N']>.02))
                    if not flags['transport_success']:outcome='GRASP_SLIP_DURING_TRANSPORT';break
                    enter('LOWER')
            elif phase=='LOWER':
                target=smooth(transport,transport+[0,0,-.079],u/6);grip=grip_closed
                if u>=6.:enter('SUPPORT_CHECK')
            elif phase=='SUPPORT_CHECK':
                grip=grip_closed
                if supported(r) and all(supported(x) for x in rows[-substeps:]):
                    if ready_start is None:ready_start=t
                    if t-ready_start>=.5:open_start=target.copy();enter('OPEN')
                else:
                    ready_start=None
                    # Source bottom and actual attitude drive final descent. The
                    # TCP alone is never treated as proof of table support.
                    if cfg.get('placement_mode','hold_then_quiet')=='unload_to_weight':
                        recent=rows[-max(1,int(.1*hz)):];fz=float(np.mean([x['support_force_vector_N'][2] for x in recent]));weight=float(cup.get_mass())*9.81
                        if r['source_bottom_gap_m']>5e-5:dz=-min(.001/control,r['source_bottom_gap_m']*.25)
                        elif fz>weight+.05:dz=min(1e-6,2e-6*(fz-weight))
                        elif fz<weight-.05:dz=-min(1e-6,2e-6*(weight-fz))
                        else:dz=0.
                        target=target+[0,0,dz]
                    elif r['source_bottom_gap_m']>1e-5:target=target+[0,0,-min(.001/control,r['source_bottom_gap_m']*.25)]
                if u>=(10. if cfg.get('placement_mode','hold_then_quiet')=='unload_to_weight' else 6.):outcome='PLACEMENT_SUPPORT_NOT_ESTABLISHED';break
            elif phase=='OPEN':
                target=open_start;grip=grip_closed+(.04-grip_closed)*min(1.,u/3)
                if u>=3.:ready_start=None;enter('CLEAR_FINGERS')
            elif phase=='CLEAR_FINGERS':
                target=open_start;grip=.04
                clear=np.all(r['finger_force_N']<.01) and np.all(r['joints'][7:]>.02) and supported(r)
                if clear:
                    if ready_start is None:ready_start=t
                    if t-ready_start>=.5:retreat_start=target.copy();enter('RETREAT')
                else:ready_start=None
                if u>=4.:outcome='RELEASE_CONTACT_OR_SUPPORT_INVALID';break
            elif phase=='RETREAT':
                target=smooth(retreat_start,retreat_start+[0,0,.08],u/4);grip=.04
                if u>=4.:enter('OBSERVE')
            elif phase=='OBSERVE':
                target=retreat_start+[0,0,.08];grip=.04
                if u>=3.1:
                    release=measure(rows,cfg)
                    final_quat=np.array(r['quaternion'],dtype=float);final_quat/=np.linalg.norm(final_quat)
                    upright=float(np.degrees(np.arccos(np.clip(1-2*(final_quat[1]**2+final_quat[2]**2),-1,1))))
                    flags['released_stable']=bool(release['static_pass'] and upright<=cfg.acceptance.upright_after_release_deg and r['actual_tcp'][2]-(r['position'][2]+m.extents[2])>=cfg.acceptance.actual_retreat_clearance_m and np.all(r['finger_force_N']<.01))
                    flags['tabletop_success']=all(flags[k] for k in flags if k!='tabletop_success');outcome='DIAGNOSTIC_SUCCESS' if flags['tabletop_success'] else 'DIAGNOSTIC_FAILED';break
            if cached_target is None or not np.array_equal(target,cached_target):
                cached_ik,valid=solver.compute_inverse_kinematics(target,orientation,position_tolerance=old.robot.ik_position_tolerance_m,orientation_tolerance=old.robot.ik_orientation_tolerance_rad)
                if valid:cached_target=target.copy()
            else:valid=True
            ik=cached_ik
            if not valid:outcome='CONTROL_OR_IK_FAILURE';break
            q=r['joints'].copy();q[np.array(ik.joint_indices,dtype=int)]=ik.joint_positions;q[7:]=grip;limit=np.array(old.robot.max_velocity)/control;q=np.clip(q,last_q-limit,last_q+limit);last_q=q.copy();action=ArticulationAction(joint_positions=q);ac.apply_action(action);state['phase']=phase;state['target_tcp']=target.copy()
            for _ in range(substeps):
                world.step(render=False);physics_steps+=1;t=physics_steps/hz;r=capture();forces,pts,normals,seps,counts,starts=env.get_contact_force_data(dt=1/hz);idx=[]
                for count,st in zip(np.asarray(counts).ravel(),np.asarray(starts).ravel()):idx.extend(range(int(st),int(st)+int(count)))
                r.update(contact_points_m=np.asarray(pts)[idx],contact_separation_m=np.asarray(seps)[idx],contact_normal_force_N=np.asarray(forces)[idx].ravel(),grip_relative_world_m=r['position']-r['actual_tcp']);rows.append(r)
            world.render();nextstate=observation(r);collector.cache_transition(state,action,nextstate,dict(status='RUNNING',full_success=False,stage_progress=flags,seed=0));state=nextstate
            frame=cv2.cvtColor(close.get_rgb()[:,:,:3],cv2.COLOR_RGB2BGR);cv2.putText(frame,f'{t:.3f}s {phase} support={r["support_force_vector_N"][2]:.3f}N',(5,20),cv2.FONT_HERSHEY_SIMPLEX,.45,(255,255,255),1);clip.write(frame)
            if not np.isfinite(np.r_[r['position'],r['quaternion'],r['linear_velocity'],r['angular_velocity']]).all():outcome='PHYSICS_INVALID';break
        if outcome=='RUNNING':outcome='TIMEOUT'
        result=dict(status=outcome,reason=outcome,full_success=False,full_task_executed=False,full_task_eligible=False,diagnostic_success=flags['tabletop_success'],stage_progress=flags,initial_support=settled_report,final_support=measure(rows,cfg) if t>=3 else None,simulation_seconds=t,wall_seconds=time.monotonic()-start,frames=collector.count,calibrated=False,scheme=cfg.get('collision_scheme','walls28_mm'),source_rack_solved=False,robot_inertia_model=inertia_model)
        result=json.loads(json.dumps(result,default=lambda x:x.tolist() if hasattr(x,'tolist') else str(x)));collector.file['done'][-1]=True;collector.file.attrs.update(diagnostic_success=flags['tabletop_success']);collector.finish_episode(result);write(output/'result.json',result);write(output/'physics_records.json',rows);write(output/'events.json',events);print('TABLE_RESULT',output,outcome,flags,flush=True)
        for k,c in cameras.items():cv2.imwrite(str(output/(k+'_final.png')),cv2.cvtColor(c.get_rgb()[:,:,:3],cv2.COLOR_RGB2BGR))
        import omni.physx
        from pxr import PhysxSchema
        tests=omni.physx.get_physxunittests_interface();kp,kd=ac.get_gains();write(output/'runtime.json',dict(cup_mass=tests.get_mass_information('/World/Cuvette'),robot_mass={p:tests.get_mass_information(p) for p in ['/World/Franka/panda_link1','/World/Franka/panda_hand','/World/Franka/panda_leftfinger']},kp=kp,kd=kd,max_effort=ac.get_max_efforts(),max_velocity=robot._articulation_view.get_joint_max_velocities(),solver='TGS',physics_hz=hz,control_hz=control,physics_substeps=substeps,CPU=True,robot_dynamics_calibrated=False,contact_offsets_authored_m=cfg.physics.contact_offset_m,contact_offsets_native_readback=None,stats=tests.get_physics_stats()))
        stage.Flatten().Export(str(output/'scene.usda'));write(output/'native_contact_events.json',native_events)
    finally:collector.close();clip.release();world.stop();world.clear()
    result['execution_total_wall_seconds']=time.monotonic()-start;write(output/'result.json',result)
    return result

def main():
    p=argparse.ArgumentParser();p.add_argument('--headless',action='store_true');p.add_argument('--repetitions',type=int,default=1);p.add_argument('--hz',type=int,choices=[240,480],default=240);p.add_argument('--grip-mode',choices=['inherited_close','contact_latched']);p.add_argument('--config',type=Path,default=ROOT/'config/lab_cuvette_loading/V0_ext02.yaml');p.add_argument('--initial-state',type=Path);p.add_argument('--support-evidence',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    support=json.loads((args.support_evidence/'result.json').read_text());cfg=OmegaConf.load(args.config);cfg.physics.hz=args.hz
    if cfg.get('collision_scheme','walls28_mm')=='sdf_cpu':
        probe=json.loads((args.support_evidence/'native_triangle_probe.json').read_text())
        if probe['missing_samples'] or probe['observed_directional_surface_distance_m'] is None:raise RuntimeError('Incomplete native triangle sample coverage')
        geo=dict(observed_support_error_m=probe['observed_directional_surface_distance_m'])
    else:geo=json.loads((args.support_evidence/'geometry_audit.json').read_text())
    if args.grip_mode:cfg.gripper.mode=args.grip_mode
    if support['scheme']!=cfg.get('collision_scheme','walls28_mm'):raise ValueError('Evidence must match the exact selected asset; no cross-scheme gate reuse')
    args.output.mkdir(exist_ok=False,parents=True)
    if not support['static_pass'] or geo['observed_support_error_m']>cfg.acceptance.support_geometry_m:
        write(args.output/'gate_result.json',dict(status='SUPPORT_GATE_BLOCKED',simulation_started=False,full_success=False,tabletop_success=False,support_evidence=str(args.support_evidence),support_static_pass=support['static_pass'],observed_support_geometry_m=geo['observed_support_error_m'],fixed_geometry_threshold_m=cfg.acceptance.support_geometry_m,reason='fixed geometry and physical thresholds must both pass'))
        print('SUPPORT_GATE_BLOCKED: no robot simulation started',flush=True);return 2
    files=[*Path(__file__).parent.glob('*.py'),args.config.resolve(),*list((ROOT/cfg.derived_directory).glob('*'))];write(args.output/'provenance.json',dict(command=sys.argv,git_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),dirty=subprocess.check_output(['git','status','--short'],cwd=ROOT,text=True),sha256={str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in files if f.is_file()},support_evidence=str(args.support_evidence),initial_state_sha256=hashlib.sha256(args.initial_state.read_bytes()).hexdigest() if args.initial_state else None))
    import shutil
    for f in files:
        if f.is_file():
            dest=args.output/'source_snapshot'/f.relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(f,dest)
    from isaacsim import SimulationApp
    app=SimulationApp(dict(headless=args.headless,width=1280,height=720,extra_args=['--/app/extensions/fsWatcherEnabled=false']))
    try:
        results=[]
        for i in range(args.repetitions):results.append(run(args,app,args.output/f'trial_{i:02d}',cfg))
        write(args.output/'results.json',results)
    except BaseException:
        import traceback
        write(args.output/'failure.json',dict(traceback=traceback.format_exc()));raise
    finally:app.close()

if __name__=='__main__':sys.exit(main())
