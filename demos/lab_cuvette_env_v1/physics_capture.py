"""Synchronized raw PhysX/contact recording, separate from control and scoring.

All detailed rows are streamed as JSONL. Native-seat overlap is unavailable;
normal contact points partition bottom support from wall/entrance contacts.
"""
from __future__ import annotations
from collections import deque
import json
from pathlib import Path
import numpy as np
from scipy.spatial.transform import Rotation


def safe(value):
    if isinstance(value,dict):return {str(k):safe(v) for k,v in value.items()}
    if isinstance(value,np.ndarray):return safe(value.tolist())
    if isinstance(value,(list,tuple)):return [safe(v) for v in value]
    if isinstance(value,(np.bool_,bool)):return bool(value)
    if isinstance(value,(np.integer,int)):return int(value)
    if isinstance(value,(np.floating,float)):return float(value) if np.isfinite(value) else None
    return value


def rot(quat):
    q=np.asarray(quat,float);return Rotation.from_quat(np.r_[q[1:],q[0]])


def q_wxyz(r):
    q=r.as_quat();return np.r_[q[3],q[:3]]


def resolve_contact_sign(raw_vectors,aggregate):
    """Resolve point-force convention against same-pair API aggregate; retain residual."""
    raw_vectors=np.asarray(raw_vectors,float).reshape(-1,3)
    aggregate=np.asarray(aggregate,float).reshape(3)
    total=raw_vectors.sum(0)
    plus=float(np.linalg.norm(total-aggregate));minus=float(np.linalg.norm(-total-aggregate))
    selected=1 if plus<=minus else -1
    residual=min(plus,minus);norm=float(np.linalg.norm(aggregate))
    resolved=bool(np.isfinite([plus,minus,norm]).all() and residual<=max(1e-6,norm*.005))
    return dict(sign=selected if resolved else None,resolved=resolved,residual_N=residual,
        plus_residual_N=plus,minus_residual_N=minus,aggregate_norm_N=norm,
        method='min || sign*sum(rawscalar*normal)-samepair_force_matrix ||; tolerance max1uN or0.5percent')


def classify_seat_point(point_world,force_on_cup,floor,rotation,depth,tolerance=.00005):
    point=(np.asarray(point_world)-np.asarray(floor))@np.asarray(rotation)
    force=np.asarray(force_on_cup)@np.asarray(rotation)
    norm=np.linalg.norm(force)
    upward=norm>1e-12 and force[2]>0 and force[2]/norm>=.5
    if abs(point[2])<=tolerance and upward:return 'bottom',point,force
    if point[2]>=float(depth)-.0015:return 'entrance_or_top_feature',point,force
    return 'wall_or_other',point,force


class PhysicsRecorder:
    def __init__(self,ctx,cfg,output_dir):
        from pxr import Usd,UsdGeom,UsdPhysics,PhysicsSchemaTools
        import omni.physx
        from demos.lab_cuvette_demo03.runtime_geometry import fixture_measure,hand_clearance
        from demos.lab_cuvette_demo03.scene import link_local_collision_points
        self.ctx,self.cfg=ctx,cfg;self.output=Path(output_dir);self.output.mkdir(parents=True,exist_ok=True)
        self.dt=1./float(cfg.physics.hz);self.fixture_measure=fixture_measure;self.hand_clearance=hand_clearance
        self._PhysicsSchemaTools=PhysicsSchemaTools
        self.cup,self.hand,self.robot=ctx['cup'],ctx['hand'],ctx['robot']
        self.env=ctx.get('env',ctx.get('contact'));self.cf=ctx.get('cup_fingers',ctx.get('cf'))
        if self.env is None or self.cf is None:raise KeyError('Recorder needs environment and cup-on-finger contact views')
        self.layout=ctx.get('fixtures',ctx.get('layout'))
        self.filters=list(ctx['filters']);self.floor=np.asarray(self.layout['target_floor'],float)
        self.instrument_rotation=np.asarray(self.layout['instrument_rotation'],float)
        self.source=np.asarray(self.layout['source_floor'],float)
        self.depth=float(self.layout['target_depth_m'])
        selected=str(self.layout['target_seat_id']);suffix='SourceMesh3' if selected=='candidate_far_hinge' else 'SourceMesh4'
        self.target_indices=[i for i,path in enumerate(self.filters) if path.endswith('/Collision/'+suffix)]
        if len(self.target_indices)!=1:raise RuntimeError('Expected exactly one original selected seat collider: '+str(self.target_indices))
        self.body_api=UsdPhysics.RigidBodyAPI(self.cup.prim)
        self.com_local=np.asarray(self.cup.get_com()[0],float).reshape(3)
        self.tcp_local=np.asarray(cfg.robot.tcp_local_m,float)
        self.tcp_rotation=rot(getattr(cfg.robot,'tcp_quaternion_wxyz',[0.,0.,0.,1.]))
        self.tcp_fixed_check=dict(source='Installed Franka Lula right_gripper fixed frame,not hand frame',
            configured_translation_m=self.tcp_local.tolist(),configured_quaternion_wxyz=q_wxyz(self.tcp_rotation).tolist())
        # The installed URDF has link8->hand yaw -pi/4 and link8->right_gripper
        # yaw3pi/4: right_gripper is hand*Rz(pi), although their local Z axes agree.
        # Query both actual solver frames so this relation is not silently assumed.
        if ctx.get('solver') is not None:
            kin=ctx['solver'].get_kinematics_solver();joints=np.asarray(self.robot.get_joint_positions())[:7]
            hand_p,hand_R=kin.compute_forward_kinematics('panda_hand',joints)
            tcp_p,tcp_R=kin.compute_forward_kinematics('right_gripper',joints)
            fixed_p=np.asarray(hand_R).T@(np.asarray(tcp_p)-np.asarray(hand_p))
            fixed_R=Rotation.from_matrix(np.asarray(hand_R).T@np.asarray(tcp_R))
            position_error=float(np.linalg.norm(fixed_p-self.tcp_local))
            angle_error=float((fixed_R*self.tcp_rotation.inv()).magnitude())
            self.tcp_fixed_check.update(solver_FK_verified=True,solver_translation_m=fixed_p.tolist(),
                solver_quaternion_wxyz=q_wxyz(fixed_R).tolist(),configured_position_error_m=position_error,
                configured_orientation_error_rad=angle_error)
            if position_error>1e-6 or angle_error>1e-6:
                raise ValueError('Configured TCP pose differs from actual Lula right_gripper fixed frame')
        # Read actual derived source visual in rigid-body local coordinates. No
        # source scale or source file name assumption is made here.
        cache=UsdGeom.XformCache();root=self.cup.prim;root_path=str(root.GetPath())
        inverse=np.linalg.inv(np.asarray(cache.GetLocalToWorldTransform(root)))
        vertices=[];faces=[];mesh_paths=[]
        for prim in Usd.PrimRange.Stage(ctx['stage'],Usd.TraverseInstanceProxies()):
            path=str(prim.GetPath())
            if not prim.IsA(UsdGeom.Mesh) or not path.startswith(root_path+'/Visual/'):continue
            m=UsdGeom.Mesh(prim);v=np.asarray(m.GetPointsAttr().Get(),float)
            M=np.asarray(cache.GetLocalToWorldTransform(prim))@inverse
            v=(np.c_[v,np.ones(len(v))]@M)[:,:3];offset=sum(len(x) for x in vertices);vertices.append(v)
            ids=np.asarray(m.GetFaceVertexIndicesAttr().Get(),int);start=0
            for count in m.GetFaceVertexCountsAttr().Get():
                polygon=ids[start:start+count]+offset
                faces.extend([[polygon[0],polygon[i],polygon[i+1]] for i in range(1,count-1)]);start+=count
            mesh_paths.append(path)
        if not vertices:raise RuntimeError('Actual derived vessel visual meshes not found')
        self.vertices=np.concatenate(vertices);self.faces=np.asarray(faces,int)
        edges=np.concatenate([self.faces[:,[0,1]],self.faces[:,[1,2]],self.faces[:,[2,0]]])
        self.edges=np.unique(np.sort(edges,axis=1),axis=0)
        self.link_points=link_local_collision_points(cfg)
        self.bodies=ctx['gripper_bodies']
        self.rows=[];self.last=None;self._recent=deque(maxlen=max(2,int(cfg.physics.hz)*4))
        self.forbidden_contact=False;self.forbidden_this_step=False
        self._step,self._t,self._phase=0,0.,'RESET';self._seen=set();self.contact_count=0;self.closed=False
        self._physics=(self.output/'physics_records.jsonl').open('x',encoding='utf-8')
        self._contacts=(self.output/'native_contact_events.jsonl').open('x',encoding='utf-8')
        self.subscription=omni.physx.get_physx_simulation_interface().subscribe_contact_report_events(self._callback)
        metadata=dict(schema='labsim.Env_v1.physics_capture.v1',physics_dt_s=self.dt,
            source_visual_paths=mesh_paths,actual_body_local_visual_dimensions_m=np.ptp(self.vertices,axis=0),
            TCP_fixed_frame_verification=self.tcp_fixed_check,
            source_visual_scope='Actual current USD visual points,fullrelative transforms; not cooked PhysX readback',
            target_contact_filter_paths=[self.filters[i] for i in self.target_indices],
            contact_force_unit='N: every tensor contact API explicitly called with physics_dt; raw impulse separately Ns',
            gripper_target_semantics='symmetric per-finger joint target_m; total opening=2*target; raw action envelope retains totalopening',
            velocity_channels=dict(native_linear='SingleRigidPrim.get_linear_velocity,world axes,m/s,backend body velocity',
                native_angular='SingleRigidPrim.get_angular_velocity,world axes,rad/s',
                usd_linear='UsdPhysics.RigidBodyAPI.GetVelocityAttr,world axes,stage-length/s; may be stale under Fabric',
                usd_angular='UsdPhysics.RigidBodyAPI.GetAngularVelocityAttr,world axes,deg/s; may be stale under Fabric',
                fd_linear='World COM from actualpose+localCOM difference/currentphysics_dt,m/s',
                fd_angular='World rotation log(R_t*R_prev^-1)/physics_dt,rad/s'),
            timestamp_semantics='capture after completed physics step; initialrow0 FD unknown,allAPI reads same no-step interval',
            bottom_partition='selectedseat point within±50um ofdeclaredfloorsurface andupwardforce cosine>=0.5; no whole-seatFz substitute',
            bottom_partition_limitations='Contactpoint is solver report,not materialintersectionproof; sloped/unidentifiedsupport remains wall/unknown',
            native_target_overlap_measured=False)
        (self.output/'physics_capture_meta.json').write_text(json.dumps(safe(metadata),ensure_ascii=False,indent=2)+'\n')

    def before_step(self,step,t,phase):
        self._step,self._t,self._phase=int(step),float(t),str(phase)
        self._seen.clear();self.forbidden_this_step=False

    def _callback(self,headers,data):
        tools=self._PhysicsSchemaTools
        for header in headers:
            paths=[str(tools.intToSdfPath(header.collider0)),str(tools.intToSdfPath(header.collider1))]
            cup=any(p.startswith('/World/Cuvette') for p in paths)
            robot=any(p.startswith('/World/Franka') for p in paths)
            environment=any(p.startswith('/World/'+prefix) for prefix in ('Instrument','SourceRack','NeighborCuvette') for p in paths)
            if not (cup or (robot and environment)):continue
            points=[]
            for i in range(header.contact_data_offset,header.contact_data_offset+header.num_contact_data):
                item=data[i];vector=lambda v:[float(v.x),float(v.y),float(v.z)]
                impulse=np.asarray(vector(item.impulse));force=impulse/self.dt
                points.append(dict(position_m=vector(item.position),normal_raw=vector(item.normal),
                    impulse_raw_Ns=impulse,force_raw_N=force,separation_m=float(item.separation),
                    force_raw_convention='PhysX callback collider convention retained; not independently force-on-cup signed'))
            forbidden=bool(robot and environment and not cup and any(np.linalg.norm(p['force_raw_N'])>.01 or p['separation_m']<-.00005 for p in points))
            if forbidden:self.forbidden_contact=True;self.forbidden_this_step=True
            key=(tuple(sorted(paths)),tuple((tuple(np.round(p['position_m'],7)),tuple(np.round(p['impulse_raw_Ns'],8))) for p in points))
            duplicate=key in self._seen;self._seen.add(key)
            event=dict(physics_step=self._step,t=self._t,phase=self._phase,colliders=paths,type=str(header.type),
                points=points,possible_duplicate_same_step=duplicate,forbidden_robot_environment=forbidden,
                association='before_step declares current executing physics step; callback not used to doublecount tensor forces')
            self._contacts.write(json.dumps(safe(event),ensure_ascii=False,separators=(',',':'),allow_nan=False)+'\n')
            self.contact_count+=1

    def _friction(self,view):
        result=view.get_friction_data(dt=self.dt)
        if result is None:return None,[]
        forces,points,counts,starts=[np.asarray(x) for x in result]
        output=np.zeros(counts.shape+(3,));details=[]
        for shape,fil in np.ndindex(counts.shape):
            count,start=int(counts[shape,fil]),int(starts[shape,fil]);output[shape,fil]=forces[start:start+count].sum(0)
            for i in range(start,start+count):details.append(dict(shape=shape,filter_index=fil,position_m=points[i],force_N=forces[i]))
        return output.sum(0),details

    def _normal_contacts(self,matrix):
        result=self.env.get_contact_force_data(dt=self.dt)
        if result is None:return [],[],False
        scalars,points,normals,distances,counts,starts=[np.asarray(x) for x in result]
        signs=[];details=[];all_resolved=True
        for fil in range(len(self.filters)):
            current=[];indices=[]
            for shape in range(counts.shape[0]):
                count,start=int(counts[shape,fil]),int(starts[shape,fil])
                for i in range(start,start+count):current.append(normals[i]*float(scalars[i].reshape(-1)[0]));indices.append((shape,i))
            raw=np.asarray(current).reshape(-1,3)
            sign=resolve_contact_sign(raw,matrix[fil]);sign.update(filter_index=fil,filter_path=self.filters[fil]);signs.append(sign)
            if fil in self.target_indices:all_resolved &= sign['resolved']
            for vector,(shape,i) in zip(raw,indices):
                on_cup=vector*sign['sign'] if sign['resolved'] else None
                point=dict(shape=shape,filter_index=fil,filter_path=self.filters[fil],position_m=points[i],
                    normal_raw=normals[i],normal_force_raw_scalar_N=float(scalars[i].reshape(-1)[0]),
                    normal_force_on_cup_N=on_cup,separation_m=float(distances[i].reshape(-1)[0]),
                    force_sign_resolved=sign['resolved'])
                if fil in self.target_indices:
                    if on_cup is None:point.update(target_region='unknown_force_sign',seat_local_position_m=(points[i]-self.floor)@self.instrument_rotation)
                    else:
                        label,local,force=classify_seat_point(points[i],on_cup,self.floor,self.instrument_rotation,self.depth)
                        point.update(target_region=label,seat_local_position_m=local,seat_local_force_on_cup_N=force)
                details.append(point)
        return details,signs,all_resolved

    def capture(self,step,t,phase,command_q,gripper_target_m,effort):
        p,q=self.cup.get_world_pose();p,q=np.asarray(p),np.asarray(q);r=rot(q)
        world_vertices=r.apply(self.vertices)+p;bottom=float(world_vertices[:,2].min());com=r.apply(self.com_local)+p
        hp,hq=self.hand.get_world_pose();hp,hq=np.asarray(hp),np.asarray(hq);hr=rot(hq)
        tcp=hp+hr.apply(self.tcp_local)
        tcp_r=hr*self.tcp_rotation
        env_raw=self.env.get_contact_force_matrix(dt=self.dt)
        finger_raw=self.cf.get_contact_force_matrix(dt=self.dt)
        if env_raw is None or finger_raw is None:
            raise RuntimeError('Contact tensor view unavailable after physics initialization')
        em=np.asarray(env_raw).reshape(-1,len(self.filters),3).sum(0)
        fm=np.asarray(finger_raw).reshape(-1,2,3).sum(0)
        ef,efpoints=self._friction(self.env);ff,ffpoints=self._friction(self.cf)
        if ef is None:ef=np.full_like(em,np.nan)
        if ff is None:ff=np.full_like(fm,np.nan)
        normal_points,signs,seat_sign_valid=self._normal_contacts(em)
        normal_vectors=[p['normal_force_on_cup_N'] for p in normal_points if p.get('target_region')=='bottom' and p['normal_force_on_cup_N'] is not None]
        bottom_vector=np.sum(normal_vectors,axis=0) if normal_vectors else np.zeros(3)
        bottom_force=float(bottom_vector[2]) if seat_sign_valid else None
        wall_vectors=[p['normal_force_on_cup_N'] for p in normal_points if p.get('target_region') in ('wall_or_other','entrance_or_top_feature') and p['normal_force_on_cup_N'] is not None]
        wall_force=float(sum(np.linalg.norm(v) for v in wall_vectors)) if seat_sign_valid else None
        top_vectors=[p['normal_force_on_cup_N'] for p in normal_points if p.get('target_region')=='entrance_or_top_feature' and p['normal_force_on_cup_N'] is not None]
        top_force=float(sum(np.linalg.norm(v) for v in top_vectors)) if seat_sign_valid else None
        target=(em+ef)[self.target_indices].sum(0)
        source_measure=self.fixture_measure(world_vertices,self.edges,self.source,np.asarray(self.layout['rack_rotation']),float(self.layout['source_inner_m']),float(self.layout['source_depth_m']))
        target_measure=self.fixture_measure(world_vertices,self.edges,self.floor,self.instrument_rotation,float(self.layout['target_inner_m']),self.depth)
        xy=((p-self.floor)@self.instrument_rotation)[:2]
        near_target=np.max(np.abs(xy))<.015
        source_pen=max(0.,float(self.cfg.scene.table_top_m)-bottom,float(source_measure['penetration']))
        fd,omega=None,None
        if self.last is not None:
            elapsed=float(t)-self.last['t']
            if elapsed<=0:raise ValueError('Physics capture timestamp must increase')
            fd=(com-np.asarray(self.last['com_world_m']))/elapsed
            omega=(r*rot(self.last['quaternion_wxyz']).inv()).as_rotvec()/elapsed
        uv=self.body_api.GetVelocityAttr().Get();uw=self.body_api.GetAngularVelocityAttr().Get()
        relative=hr.inv()*r
        yaw=np.rad2deg(np.arctan2((self.instrument_rotation.T@r.as_matrix())[1,0],(self.instrument_rotation.T@r.as_matrix())[0,0]))
        clearance=self.hand_clearance(self.link_points,self.bodies,world_vertices)
        row=dict(t=float(t),simulation_time=float(t),engine_time=float(self.ctx['world'].current_time),physics_step=int(step),phase=str(phase),
            object_position_m=p,position=p,quaternion_wxyz=q,object_quaternion_wxyz=q,com_world_m=com,
            source_bottom_z_m=bottom,object_bottom_world_z_m=bottom,
            source_bottom_gap_m=source_measure['gap'],source_rack_penetration_m=source_pen,
            target_bottom_gap_m=target_measure['gap'] if near_target else None,
            depth_m=target_measure['depth'] if near_target else None,xy_error_target_m=xy,
            tilt_deg=float(np.rad2deg(np.arccos(np.clip(r.as_matrix()[2,2],-1,1)))),yaw_error_deg=float((yaw+180)%360-180),
            linear_velocity_native_m_s=np.asarray(self.cup.get_linear_velocity()),angular_velocity_native_rad_s=np.asarray(self.cup.get_angular_velocity()),
            linear_velocity_USD_m_s=np.asarray(uv) if uv is not None else None,angular_velocity_USD_deg_s=np.asarray(uw) if uw is not None else None,
            fd_com_velocity_m_s=fd,fd_angular_velocity_rad_s=omega,
            actual_tcp_position_m=tcp,actual_tcp_quaternion_wxyz=q_wxyz(tcp_r),
            cup_in_hand_position_m=hr.inv().apply(p-hp),cup_in_hand_quaternion_wxyz=q_wxyz(relative),
            joints9=np.asarray(self.robot.get_joint_positions()),joint_velocities9=np.asarray(self.robot.get_joint_velocities()),
            finger_contact_N=np.linalg.norm(fm,axis=1),finger_normal_force_on_cup_N=fm,finger_friction_force_on_cup_N=ff,
            finger_joint_positions_m=np.asarray(self.robot.get_joint_positions())[7:9],
            environment_normal_force_matrix_N=em,environment_friction_force_matrix_N=ef,
            environment_net_force_N=(em+ef).sum(0),environment_sum_force_magnitudes_N=float(np.linalg.norm(em+ef,axis=1).sum()),
            target_whole_seat_net_force_N=target,target_whole_seat_net_vertical_N=float(target[2]),
            target_bottom_support_N=bottom_force,target_bottom_normal_force_vector_N=bottom_vector if seat_sign_valid else None,
            wall_contact_N=wall_force,entrance_feature_contact_N=top_force,
            target_normal_contact_points=normal_points,contact_force_sign_checks=signs,
            environment_friction_points=efpoints,finger_friction_points=ffpoints,
            native_target_overlap_m=None,native_target_overlap_measured=False,
            target_region_contains_object=None,reference_12_6_square_envelope_contains=target_measure['inside'] if near_target else None,
            reference_12_6_envelope_warning='Necessary rectangularreference only; retainedoriginalfeatures not represented; not legal-voidproof',
            gripper_object_clearance_m=clearance,gripper_clearance_scope='AABB separation lowerbound fromactual threegripperlink inputvertices; notcookedshapes',
            source_clearance_m=bottom-float(self.layout['source_rim_z']),source_reference_inside=source_measure['inside'],
            forbidden_robot_environment_contact=self.forbidden_contact,forbidden_robot_environment_contact_this_step=self.forbidden_this_step,
            command_q9=np.asarray(command_q),gripper_target_m=float(gripper_target_m),gripper_effort_limit_N=effort,
            record_api_sample_time='aftercompletedphysicsstep,nointerveningstep',native_contact_events_count=self.contact_count)
        self._physics.write(json.dumps(safe(row),ensure_ascii=False,separators=(',',':'),allow_nan=False)+'\n')
        self.last=safe(row);self._recent.append(self.last)
        compact={key:self.last[key] for key in ('t','physics_step','phase','object_position_m','quaternion_wxyz','source_bottom_z_m','target_bottom_gap_m','depth_m','xy_error_target_m','tilt_deg','finger_contact_N','target_bottom_support_N','wall_contact_N','source_rack_penetration_m','native_target_overlap_m','gripper_object_clearance_m','forbidden_robot_environment_contact')}
        self.rows.append(compact)
        if int(step)%int(self.cfg.physics.hz)==0:self._physics.flush();self._contacts.flush()
        return self.last

    def close(self):
        if self.closed:return
        if self.subscription is not None:
            if hasattr(self.subscription,'unsubscribe'):self.subscription.unsubscribe()
            self.subscription=None
        self._physics.flush();self._contacts.flush();self._physics.close();self._contacts.close();self.closed=True
