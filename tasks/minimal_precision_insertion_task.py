"""Physical insertion task; independent scoring never reads the nominal offset."""
import json
from collections import deque
import numpy as np
from pxr import Gf, UsdGeom, UsdPhysics, PhysxSchema, UsdUtils, PhysicsSchemaTools
from isaacsim.sensors.camera import Camera
from isaacsim.core.utils.viewports import set_camera_view
from isaacsim.core.utils.types import ArticulationAction
from demos.minimal_precision_insertion.geometry import cylinder_mesh, rotation, overlap_metrics
from demos.minimal_precision_insertion.scene import build_scene, tcp_pose


class MinimalPrecisionInsertionTask:
    def __init__(self, cfg, asset_dir, **kwargs):
        self.cfg = cfg
        self.scene = build_scene(cfg,asset_dir)
        self.world,self.stage,self.robot,self.tube,self.solver = (self.scene[k] for k in ('world','stage','robot','tube','solver'))
        self.dt = 1./cfg.task.control_hz
        self.substeps = int(round(cfg.physics.hz/cfg.task.control_hz))
        if not np.isclose(self.substeps*self.scene['dt'],self.dt):
            raise ValueError('physics_hz must be an integer multiple of control_hz')
        self.cameras = {}
        for c in cfg.cameras:
            camera = Camera(prim_path=c.prim_path,name=c.name,frequency=cfg.task.control_hz,resolution=tuple(c.resolution))
            camera.set_focal_length(c.focal_length)
            camera.set_clipping_range(.001,10.)
            set_camera_view(eye=np.array(c.eye),target=np.array(c.target),camera_prim_path=c.prim_path)
            self.cameras[c.name+'_rgb'] = camera
        self.vertices,self.faces = cylinder_mesh(.005,.05,cfg.geometry.tube_segments)
        self.edges = np.unique(np.sort(np.concatenate([self.faces[:,[0,1]],self.faces[:,[1,2]],self.faces[:,[2,0]]]),axis=1),axis=0)
        self.cooked_available = False

    def cooked_snapshot(self):
        import omni.physx
        saved = {}
        if self.cfg.geometry.collision == 'analytic_cylinder':
            stats=omni.physx.get_physxunittests_interface().get_physics_stats()
            saved.update(physics_stats=stats,representation='analytic_cylinder',
                radius_m=float(self.stage.GetPrimAtPath('/World/Tube/Collision').GetAttribute('radius').Get()),
                height_m=float(self.stage.GetPrimAtPath('/World/Tube/Collision').GetAttribute('height').Get()),
                scoring_polygon_segments=self.cfg.geometry.tube_segments,
                scoring_radial_error_bound_m=.005*(1-np.cos(np.pi/self.cfg.geometry.tube_segments)),
                tube_runtime_dimensions_read=False,wall_runtime_triangle_vertices_read=False,
                wall_limitation='Authored dimensions checked; runtime shape types checked; cooked wall triangles not read back.')
            self.cooked_available=False
            return saved
        vertices,edges,statuses=[],[],[]
        paths=[str(p.GetPath()) for p in self.stage.GetPrimAtPath('/World/Tube/Collision').GetChildren()] if self.cfg.geometry.collision=='compound_convex' else ['/World/Tube/Collision']
        def result(status,convexes):
            statuses.append(str(status))
            if len(convexes)==1:
                convex=convexes[0]
                scale=float(self.stage.GetPrimAtPath(current_path).GetAttribute('xformOp:scale').Get()[0])
                points=np.array([[v.x,v.y,v.z] for v in convex.vertices])*scale
                base=sum(len(v) for v in vertices)
                pairs=[]
                for p in convex.polygons:
                    ix=convex.indices[p.index_base:p.index_base+p.num_vertices]
                    pairs.extend([[ix[i]+base,ix[(i+1)%len(ix)]+base] for i in range(len(ix))])
                vertices.append(points);edges.extend(pairs)
        try:
            for current_path in paths:
                omni.physx.get_physx_cooking_interface().request_convex_collision_representation(
                    stage_id=UsdUtils.StageCache.Get().GetId(self.stage).ToLongInt(),
                    collision_prim_id=PhysicsSchemaTools.sdfPathToInt(current_path),
                    run_asynchronously=False,on_result=result)
            if len(vertices)==len(paths):
                self.vertices=np.concatenate(vertices);self.edges=np.unique(np.sort(np.array(edges),axis=1),axis=0)
                self.cooked_available=True
                saved.update(vertices=self.vertices.tolist(),edges=self.edges.tolist(),statuses=statuses,
                    convex_count=len(paths),representation=self.cfg.geometry.collision,
                    radial_max_m=float(np.linalg.norm(self.vertices[:,:2],axis=1).max()),
                    z_min_m=float(self.vertices[:,2].min()),z_max_m=float(self.vertices[:,2].max()),
                    requested_outline_sagitta_m=.005*(1-np.cos(np.pi/self.cfg.geometry.tube_segments)))
        except Exception as e:
            saved['error']=str(e)
        saved['tube_cooked_available']=self.cooked_available
        saved['wall_runtime_triangle_vertices_read']=False
        saved['wall_limitation']='Authored static triangles validated; no read-back of runtime triangle cooking/cleaning.'
        return saved

    def reset(self, offset_mm=0.):
        self.world.reset()
        self.hole_center = np.array(self.cfg.task.hole_center) - np.array([offset_mm*.001,0.])
        self.stage.GetPrimAtPath('/World/Module').GetAttribute('xformOp:translate').Set(Gf.Vec3d(*self.hole_center,self.cfg.task.floor_z))
        # All pose writes occur here, before the experiment. No runtime object pose commands.
        self.robot.set_joint_positions(self.scene['q'])
        self.robot.set_joint_velocities(np.zeros(9))
        p,_ = tcp_pose(self.scene['hand'])
        center = p + np.array([0,0,.025-self.cfg.task.grip_above_bottom_m])
        self.tube.set_world_pose(center,np.array([1.,0,0,0]))
        self.tube.set_linear_velocity(np.zeros(3))
        self.tube.set_angular_velocity(np.zeros(3))
        for contact in (self.scene['fingers'],self.scene['contacts']):
            contact.initialize()
        for camera in self.cameras.values():
            camera.initialize()
        q=self.scene['q'].copy();q[7:]=0.
        self.robot.get_articulation_controller().apply_action(ArticulationAction(joint_positions=q))
        self.world.render()
        for step in range(self.cfg.physics.hz):
            self.world.step(render=False)
            if (step+1)%self.substeps==0:
                self.world.render()
        self.initial_position = self.tube.get_world_pose()[0].copy()
        self.initial_tcp = tcp_pose(self.scene['hand'])[0].copy()
        self.initial_relative = self.initial_position-self.initial_tcp
        self.elapsed = 0.; self.frame_idx=0;self.clock_origin=self.world.current_time
        self.status,self.reason,self.phase='RUNNING','','CLAMP'
        self.target_tcp=np.array(self.cfg.task.initial_tcp);self.ik_residual=0.
        self.max_depth=-1.;self.max_overlap=0.;self.peak_contacts=np.zeros(3)
        self.max_slip=0.;self.stable=0.;self.events=[];self.substep_records=[]
        self.stable_start=None
        self.precontact=None;self.first_contact=None;self.blocked_since=None;self.preentry=None
        self.prev_depth=None;self.depth_history=deque();self.release_pose=None;self.release_orientation=None
        self.nominal_offset_mm=offset_mm
        self.last_metrics=self.measure()
        self.initial_state = self.snapshot_state(self.last_metrics)

    def measure(self):
        position,orientation=self.tube.get_world_pose()
        m=overlap_metrics(position,orientation,self.vertices,self.edges,self.hole_center,self.cfg.task.floor_z,self.cfg.geometry.hole_segments)
        # Conservative 3 um scoring allowance for the analytic cylinder's 96-sided
        # numerical reference, valid for these nearly upright (<5 deg) runs.
        m['overlap_upper_m']=m['overlap_m']+(3e-6 if self.cfg.geometry.collision=='analytic_cylinder' and m['lowest_depth_m']>=0 else 0.)
        finger=np.linalg.norm(np.asarray(self.scene['fingers'].get_contact_force_matrix(dt=self.scene['dt'])).reshape(2,-1,3),axis=2).sum(axis=1)
        contact=np.linalg.norm(np.asarray(self.scene['contacts'].get_contact_force_matrix(dt=self.scene['dt'])).reshape(-1,3),axis=1).sum()
        tcp,_=tcp_pose(self.scene['hand'])
        m.update(position=position,orientation=orientation,finger_contact_N=finger,module_contact_N=float(contact),tcp=tcp,
                 slip_m=float(np.linalg.norm((position-tcp)-self.initial_relative)) if hasattr(self,'initial_relative') else 0.)
        forces,points,normals,separation,counts,starts=self.scene['contacts'].get_contact_force_data(dt=self.scene['dt'])
        indices=[]
        for count,start in zip(np.asarray(counts).reshape(-1),np.asarray(starts).reshape(-1)):
            indices.extend(range(int(start),int(start)+int(count)))
        m.update(contact_points_m=np.asarray(points)[indices].tolist(),
                 contact_normals=np.asarray(normals)[indices].tolist(),
                 contact_normal_force_N=np.asarray(forces)[indices].reshape(-1).tolist(),
                 contact_separation_m=np.asarray(separation)[indices].reshape(-1).tolist())
        m['joint_positions']=self.robot.get_joint_positions().tolist()
        m['target_tcp_m']=self.target_tcp.tolist() if hasattr(self,'target_tcp') else list(self.cfg.task.initial_tcp)
        m['phase']=self.phase if hasattr(self,'phase') else 'INITIALIZATION'
        m['linear_velocity_m_s']=self.tube.get_linear_velocity().tolist()
        m['angular_velocity_rad_s']=self.tube.get_angular_velocity().tolist()
        return m

    def snapshot_state(self,m):
        return {k: (v.tolist() if isinstance(v,np.ndarray) else v) for k,v in m.items()}

    def step(self):
        m=self.measure()
        images={}
        for key,camera in self.cameras.items():
            rgb=camera.get_rgb()
            if rgb is None or not rgb.size:
                raise RuntimeError('Missing camera RGB')
            images[key]=np.transpose(rgb[:,:,:3],(2,0,1)).copy()
        return dict(joint_positions=self.robot.get_joint_positions().copy(),camera_data=images,
                    object_position=m['position'],object_orientation=m['orientation'],
                    finger_contact_N=m['finger_contact_N'],simulation_time=self.elapsed,
                    tcp=m['tcp'],target_tcp=self.target_tcp.copy(),ik_residual_m=self.ik_residual,
                    metrics=self.snapshot_state(m),phase=self.phase,done=self.status!='RUNNING')

    def advance(self,action):
        self.robot.get_articulation_controller().apply_action(action)
        for i in range(self.substeps):
            self.world.step(render=False)
            self.elapsed+=self.scene['dt']
            if not np.isclose(self.world.current_time-self.clock_origin,self.elapsed,atol=1e-5,rtol=0):
                raise RuntimeError('Engine time disagrees with explicit physical substep clock')
            m=self.measure(); self.last_metrics=m
            self.depth_history.append((self.elapsed,m['depth_m']))
            while self.depth_history and self.depth_history[0][0]<self.elapsed-2.:
                self.depth_history.popleft()
            self.substep_records.append(dict(time=self.elapsed,**self.snapshot_state(m)))
            self.max_depth=max(self.max_depth,m['depth_m'])
            self.max_overlap=max(self.max_overlap,m['overlap_upper_m'])
            self.peak_contacts=np.maximum(self.peak_contacts,np.r_[m['finger_contact_N'],m['module_contact_N']])
            if self.elapsed<self.cfg.task.release_time_s:
                self.max_slip=max(self.max_slip,m['slip_m'])
            if self.first_contact is None:
                if m['module_contact_N'] > .005:
                    self.first_contact=self.snapshot_state(m)
                    self.events.append(dict(event='FIRST_MODULE_CONTACT',time=self.elapsed,**self.first_contact))
                else:
                    self.precontact=self.snapshot_state(m)
            if m['lowest_depth_m']<0 and self.first_contact is None:
                self.preentry=self.snapshot_state(m)
            if not np.isfinite(np.r_[m['position'],m['orientation'],m['finger_contact_N'],m['module_contact_N']]).all():
                self.status,self.reason='PHYSICS_INVALID','nonfinite_state'
            elif m['overlap_upper_m']>self.cfg.task.penetration_tolerance_m:
                self.status,self.reason='PHYSICS_INVALID','module_overlap_exceeds_fixed_tolerance'
            elif m['position'][2] < .735:
                self.status,self.reason='DROPPED','tube_below_table'
            elif self.elapsed<self.cfg.task.release_time_s and m['slip_m']>.008:
                self.status,self.reason='GRASP_SLIP','relative_grasp_translation_exceeds_8mm'
            elif (self.phase=='DESCEND' and self.elapsed<2.+(self.cfg.task.initial_bottom_gap_m+self.cfg.task.target_depth_m)/self.cfg.task.speed_m_s and m['depth_m']<self.cfg.task.required_depth_m
                  and m['module_contact_N']>.01 and self.depth_history[-1][0]-self.depth_history[0][0]>1.98
                  and np.ptp([x[1] for x in self.depth_history])<.0001):
                self.status,self.reason='BLOCKED','contact_and_less_than_0.1mm_descent_over_2s_while_target_descends'
                self.events.append(dict(event='BLOCKED_STALL',time=self.elapsed,**self.snapshot_state(m)))
            elif self.elapsed+1e-9>=self.cfg.task.check_time_s:
                if self.release_pose is None:
                    self.release_pose=m['position'].copy()
                    self.release_orientation=m['orientation'].copy()
                opened=np.all(self.robot.get_joint_positions()[7:]>.035)
                retreat=m['tcp'][2]-(self.cfg.task.floor_z+.02)>.035
                valid=(m['depth_m']>=self.cfg.task.required_depth_m and m['depth_m']<=.020+self.cfg.task.penetration_tolerance_m
                       and opened and retreat and m['containment_error_m']<=self.cfg.task.penetration_tolerance_m
                       and m['overlap_upper_m']<=self.cfg.task.penetration_tolerance_m and np.all(m['finger_contact_N']<.01))
                angle=2*np.arccos(np.clip(abs(np.dot(m['orientation'],self.release_orientation)),0,1))
                settled=np.linalg.norm(m['position']-self.release_pose)<.0001 and angle<np.radians(.5)
                if valid and settled:
                    if self.stable_start is None:
                        self.stable_start=self.elapsed
                    self.stable=self.elapsed-self.stable_start
                else:
                    self.stable_start=None;self.stable=0.
                if self.stable+1e-9>=self.cfg.task.hold_seconds:
                    self.status,self.reason='SUCCESS','depth_open_retreat_stable_1s_no_excess_overlap'
                elif self.elapsed>=self.cfg.task.check_time_s+2.:
                    if m['depth_m']<self.cfg.task.required_depth_m and self.first_contact is not None:
                        self.status,self.reason='BLOCKED','contact_depth_shortfall_after_descent_release'
                    else:
                        self.status,self.reason='UNSTABLE_AFTER_RELEASE','release_stability_or_depth_requirement_not_met'
            elif self.elapsed>=self.cfg.task.timeout_seconds:
                self.status,self.reason='TIMEOUT','simulation_budget'
            if self.status!='RUNNING':
                break
        self.frame_idx+=1
        self.world.render()

    def result(self):
        m=self.last_metrics
        return dict(status=self.status,reason=self.reason,frames=self.frame_idx,
            simulation_seconds=self.elapsed,physics_hz=self.cfg.physics.hz,substeps=self.substeps,
            engine_simulation_seconds=self.world.current_time-self.clock_origin,
            nominal_offset_mm=self.nominal_offset_mm,actual_precontact=self.precontact if self.first_contact is not None else None,first_contact=self.first_contact,
            actual_preentry=self.preentry,
            initial_state=self.initial_state,final_state=self.snapshot_state(m),max_depth_mm=self.max_depth*1000,
            max_overlap_mm=self.max_overlap*1000,max_grasp_slip_mm=self.max_slip*1000,
            continuous_hold_seconds=self.stable,peak_contacts_N=self.peak_contacts.tolist(),
            cooked_tube_verified=self.cooked_available,wall_cooking_readback=False,
            # Compatibility values are solely for the existing streaming writer.
            final_lift_m=float(m['position'][2]-self.initial_position[2]))

    def parameter_snapshot(self):
        import omni.physx
        import carb
        keys=('physics:','physx','drive:')
        attrs={str(p.GetPath()):{a.GetName():str(a.Get()) for a in p.GetAttributes()
                                  if a.GetName().startswith(keys)} for p in self.stage.Traverse()
                if any(a.GetName().startswith(keys) for a in p.GetAttributes())}
        mass=omni.physx.get_physxunittests_interface().get_mass_information('/World/Tube')
        mass={k:np.asarray(v).tolist() for k,v in mass.items()}
        gains=self.robot.get_articulation_controller().get_gains()
        from demos.minimal_precision_insertion.effective import runtime_shape_parameters
        material_paths={str(p.GetPath()):omni.physx.get_physxunittests_interface().get_materials_paths(str(p.GetPath()))
            for p in self.stage.Traverse() if p.HasAPI(UsdPhysics.CollisionAPI)}
        return dict(stage_attributes=attrs,physics_stats=omni.physx.get_physxunittests_interface().get_physics_stats(),
            runtime_mass=mass,
            runtime_drive_stiffness=np.asarray(gains[0]).tolist(),runtime_drive_damping=np.asarray(gains[1]).tolist(),
            runtime_joint_limits=np.asarray(self.robot.get_articulation_controller().get_joint_limits()).tolist(),
            runtime_max_efforts=np.asarray(self.robot.get_articulation_controller().get_max_efforts()).tolist(),
            runtime_material_paths=material_paths,
            runtime_shape_properties=runtime_shape_parameters(self.world,self.robot),
            physics_dt=self.world.get_physics_dt(),rendering_dt=self.world.get_rendering_dt(),
            control_dt=self.dt,substeps=self.substeps,backend='numpy',device='cpu',
            approximate_cylinders=carb.settings.get_settings().get('/physics/collisionApproximateCylinders'),
            ik_position_tolerance_m=self.cfg.task.ik_position_tolerance_m,
            ik_orientation_tolerance_rad=self.cfg.task.ik_orientation_tolerance_rad,
            note='USD effective attributes and runtime mass/types; runtime cooked triangle vertices are not exposed here.')

    def save_collision_debug(self,path):
        """Render the authored collision prims, separated from visuals; no physics steps."""
        import cv2
        changed=[]
        for p in self.stage.Traverse():
            pathstr=str(p.GetPath())
            if pathstr.startswith(('/World/Tube/','/World/Module/')) and p.IsA(UsdGeom.Gprim):
                imageable=UsdGeom.Imageable(p)
                purpose=imageable.GetPurposeAttr().Get();visible=imageable.GetVisibilityAttr().Get()
                changed.append((imageable,purpose,visible))
                if 'Collision' in pathstr:
                    imageable.CreatePurposeAttr('default');imageable.CreateVisibilityAttr('inherited')
                    UsdGeom.Gprim(p).CreateDisplayColorAttr([Gf.Vec3f(.15,.8,.2)])
                else:
                    imageable.CreateVisibilityAttr('invisible')
        c=self.cfg.cameras[0];camera=self.cameras['camera_1_rgb']
        camera.set_focal_length(3.5)
        set_camera_view(eye=np.array([.225,-.045,.820]),target=np.array([.2,.0003,.794]),camera_prim_path=c.prim_path)
        for _ in range(12):
            self.world.render()
        rgb=camera.get_rgb()
        cv2.imwrite(str(path),cv2.cvtColor(rgb,cv2.COLOR_RGB2BGR))
        for imageable,purpose,visible in changed:
            imageable.GetPurposeAttr().Set(purpose);imageable.GetVisibilityAttr().Set(visible)
        camera.set_focal_length(c.focal_length)
        set_camera_view(eye=np.array(c.eye),target=np.array(c.target),camera_prim_path=c.prim_path)
        for _ in range(6):
            self.world.render()

    def runtime_geometry_probe(self):
        """Query actual runtime hole surfaces while the tube is above the mouth.

        This verifies sampled dimensions/cavity, not a complete cooked-mesh dump.
        """
        import omni.physx
        query=omni.physx.get_physx_scene_query_interface()
        rays=[]
        for z in (.002,.010,.018):
            for i in range(self.cfg.geometry.hole_segments):
                angle=(i+.47)*2*np.pi/self.cfg.geometry.hole_segments
                direction=(float(np.cos(angle)),float(np.sin(angle)),0.)
                hit=query.raycast_closest(tuple(self.hole_center)+(self.cfg.task.floor_z+z,),direction,.015,True)
                rays.append(dict(height_above_floor_m=z,angle_rad=angle,hit=bool(hit.get('hit',False)),
                    distance_m=hit.get('distance'),collider=hit.get('collision'),face_index=hit.get('faceIndex')))
        vertical=[]
        for radius in (0.,.0052,.0054):
            origin=(float(self.hole_center[0]+radius),float(self.hole_center[1]),self.cfg.task.floor_z+.021)
            hit=query.raycast_closest(origin,(0.,0.,-1.),.03,True)
            vertical.append(dict(radius_m=radius,distance_m=hit.get('distance'),collider=hit.get('collision'),hit=bool(hit.get('hit',False))))
        values=[r['distance_m'] for r in rays if r['hit'] and r['collider']=='/World/Module/WallCollision']
        return dict(radial_rays=rays,vertical_rays=vertical,sampled_inner_radius_range_m=[min(values),max(values)] if values else [],
                    expected_polygon_apothem_m=.0053*np.cos(np.pi/self.cfg.geometry.hole_segments),
                    limitation='384 radial queries and 3 vertical queries; no complete cooked triangle read-back.')

    def tube_runtime_probe(self):
        import omni.physx
        query=omni.physx.get_physx_scene_query_interface()
        position,_=self.tube.get_world_pose()
        results=[]
        for axis in range(3):
            origin=position.copy();origin[axis]-=.04
            direction=np.eye(3)[axis]
            hits=[]
            def collect(hit):
                path=str(hit.collision)
                if path.startswith('/World/Tube/'):
                    hits.append(dict(path=path,distance_m=hit.distance,position_m=list(hit.position)))
                return True
            query.raycast_all(tuple(origin),tuple(direction),.08,collect,True)
            results.append(dict(axis=axis,origin_m=origin.tolist(),hits=sorted(hits,key=lambda x:x['distance_m'])[:3]))
        return results
