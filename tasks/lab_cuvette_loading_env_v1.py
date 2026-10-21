"""Synchronous real-physics LabUtopia environment shared by teacher and policies.

SimulationApp is owned by the launcher. No teacher is called by reset or step.
Privileged vessel/geometry/contact state stays in the recorder/scorer channel.
"""
from pathlib import Path
import copy,json,time,uuid,subprocess
import numpy as np
from scipy.spatial.transform import Rotation
from omegaconf import OmegaConf
from data_collectors.lab_cuvette_env_v1_collector import json_safe
from tasks.lab_cuvette_loading_env_v1_scorer import CuvetteLoadingEnvV1Scorer
from demos.lab_cuvette_env_v1.scene import episode_config,layout,build_context
from demos.lab_cuvette_env_v1.cameras import create_cameras,policy_image
from demos.lab_cuvette_env_v1.physics_capture import PhysicsRecorder

class LabCuvetteLoadingEnvV1:
    # The recorder accesses rig.get_meta directly. Public calibration must not
    # expose debug depth/renderer state or any future private metadata fields.
    PUBLIC_CAMERA_META_FIELDS=frozenset((
        'name','prim_path','physical_parent','mounting',
        'local_pose_position_m','local_pose_quaternion_wxyz',
        'world_pose_position_m','world_pose_quaternion_wxyz',
        'world_from_camera_usd','camera_cv_from_world','extrinsic_translation_unit','meters_per_stage_unit',
        'optical_conventions','intrinsic_matrix_native','intrinsic_matrix_policy_256',
        'focal_length_cm','horizontal_aperture_mm','vertical_aperture_mm',
        'resolution_wh','channels','native_array_layout','policy_transform',
        'requested_fps','actual_sensor_frequency_hz','sensor_rendering_frame','sensor_rendering_time_s',
        'sensor_timestamp_clock','sensor_frame_token_semantics','read_simulation_time_s','source'))
    ACTION_SPECS={
      'joint_position':{'values':'7 arm rad or explicit9 with2 finger metres','frame':'joint','gripper':'total opening metres'},
      'joint_velocity':{'values':'7 arm rad/s; integrated per60Hz control tick','frame':'joint','gripper':'total opening metres'},
      'ee_pose':{'values':'world xyz metres + quaternion wxyz','frame':'world'},
      'ee_delta':{'values':'translation metres + rotation vector radians','frame':'world or tcp; explicit spatial composition'}}
    def __init__(self,cfg,app,output,*,geometry_audit=None,initial_state=None,world=None,stage=None,robot=None):
        self.base_cfg=cfg;self.app=app;self.output=Path(output);self.output.mkdir(parents=True,exist_ok=True)
        self.geometry_audit=dict(geometry_audit or {});self.initial_state=initial_state;self.ctx=None;self.collector=None;self.recorder=None;self.rig=None
        self.episode_index=-1;self.episode_id=None;self.closed=False;self.ended=True;self._obs=None;self._result=None;self.total_wall=time.perf_counter()
    @staticmethod
    def _write(path,value):Path(path).write_text(json.dumps(json_safe(value),ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    def _cleanup_episode(self):
        if self.collector is not None:self.collector.close();self.collector=None
        if self.recorder is not None:self.recorder.close();self.recorder=None
        if self.rig is not None:self.rig.close();self.rig=None
        if self.ctx is not None:
            self.ctx['world'].stop();self.ctx['world'].clear();self.ctx=None
    def reset(self,seed=None,options=None):
        try:return self._reset(seed,options)
        except Exception as error:
            self.ended=True
            root=getattr(self,'episode_dir',self.output)
            self._write(root/'initialization_failure.json',dict(record_valid=False,task_success=None,failure_type='INITIALIZATION_INVALID',error_type=type(error).__name__,error=str(error),episode_id=self.episode_id,physical_attempt_qualified=False))
            raise
    def _reset(self,seed=None,options=None):
        if self.closed:raise RuntimeError('Environment is closed')
        if not self.ended:self.finalize_episode('RESET_INTERRUPTED','PROCESS_INTERRUPTED')
        self._cleanup_episode();self.options=dict(options or {});self.cfg=episode_config(self.base_cfg,int(seed or 0),self.options)
        self.episode_index+=1;self.episode_id=str(uuid.uuid4());self.episode_dir=self.output/f'episode_{self.episode_index:04d}';self.episode_dir.mkdir(exist_ok=False)
        self.steps=0;self.control_steps=0;self.t=0.;self.phase='RESET';self.grip=.08;self.effort=float(self.cfg.env.gripper_effort_max_N);self._result=None;self._policy_latch=None;self._policy_latch_contact=None
        self.episode_wall=time.perf_counter();self._ensure_bound_audit();self._write(self.episode_dir/'options.json',self.options);OmegaConf.save(self.cfg,self.episode_dir/'config.yaml')
        self.ctx=build_context(self.cfg,self.app,self.episode_dir,self.initial_state)
        if self.cfg.env.get('probe_cooked_collision',False):
            from demos.lab_cuvette_size_v1.cooked_probe import probe
            probe(self.ctx['stage'],self.episode_dir/'cooked_collision_probe.json')
        self.world,self.robot,self.solver,self.ac=[self.ctx[k] for k in ['world','robot','solver','ac']];self.qcmd=self.robot.get_joint_positions().copy();self._ik_seed=self.qcmd[:7].copy();self._ik_goal=None;self._ik_solution=None
        self.engine_time_origin=float(self.world.current_time)
        pc=self.world.get_physics_context();pc.enable_fabric(False)
        pc.set_physx_update_transformations_settings(update_to_usd=True,update_velocities_to_usd=True,output_velocities_local_space=False)
        self.world.physics_sim_view.update_articulations_kinematic()
        self.recorder=PhysicsRecorder(self.ctx,self.cfg,self.episode_dir)
        scorer_class=CuvetteLoadingEnvV1Scorer
        if self.cfg.env.get('scorer_module'):
            from importlib import import_module
            scorer_class=import_module(self.cfg.env.scorer_module).Scorer
        self.scorer=scorer_class(self.cfg,self.ctx['fixtures'],self.geometry_audit)
        self.debug=self.recorder.capture(0,0.,self.phase,self.qcmd,self.grip/2,self.effort);self.scorer.update(self.debug)
        self.rig=create_cameras(self.ctx,self.cfg)
        for _ in range(8):self.world.render()
        # Record the entire initial gravity response, then obtain an actually
        # timestamped camera pair before exposing the first policy observation.
        for _ in range(self.cfg.physics.hz//self.cfg.physics.control_hz):
            self.recorder.before_step(self.steps+1,(self.steps+1)/self.cfg.physics.hz,'RESET_INITIALIZATION')
            self.world.step(render=False);self.steps+=1;self.t=self.steps/self.cfg.physics.hz
            self.debug=self.recorder.capture(self.steps,self.t,'RESET_INITIALIZATION',self.qcmd,self.grip/2,self.effort);self.scorer.update(self.debug)
        for _ in range(4):self.world.render()
        self.rig.reset_history()
        self.images=self.rig.get_images();self.camera_meta={n:self.rig.get_meta(n) for n in self.rig.names};self._write(self.episode_dir/'cameras.json',self.camera_meta)
        self._write(self.episode_dir/'geometry_audit_binding.json',self.geometry_audit)
        contract=dict(version=str(self.cfg.get('version','Env_v1')),source_slot_id=self.cfg.rack.selected_slot_id,target_seat_id=self.cfg.adapter.selected_target_seat_id,
            asset_manifest_sha256=__import__('hashlib').sha256((Path(__file__).resolve().parents[1]/self.cfg.asset_directory/'manifest.json').read_bytes()).hexdigest(),
            scene_mode=self.cfg.scene_mode,task_type=self.cfg.env.task_type,geometry_valid=self._geometry_valid(),action_specs=self.ACTION_SPECS,
            controller_in_default_step=False,real_calibrated=False)
        size_metadata={}
        if self.cfg.get('version')=='Size_v1':
            from demos.lab_cuvette_size_v1.frozen_scene import episode_metadata,validate_frozen_scene
            frozen_path=self.cfg.env.get('frozen_scene_manifest')
            if frozen_path:
                frozen=json.loads((Path(__file__).resolve().parents[1]/frozen_path).read_text())
                validate_frozen_scene(self.cfg,frozen,Path(__file__).resolve().parents[1],purpose='collect')
                deviation=OmegaConf.to_container(self.cfg.experiment.deviation,resolve=True) if 'deviation' in self.cfg.experiment else {}
                size_metadata=episode_metadata(self.cfg,frozen,condition_group=self.cfg.experiment.get('condition_group','natural'),deviation=deviation)
            else:
                size_metadata=dict(asset_id=self.cfg.vessel.asset_id,condition_group=self.cfg.experiment.get('condition_group','development'),scene_mode=self.cfg.scene_mode,code_commit=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip())
            contract.update(size_metadata)
            size_metadata['deterministic_action_deviation_json']=json.dumps(size_metadata.get('deterministic_action_deviation',{}),sort_keys=True)
        from factories.collector_factory import create_collector
        self.collector=create_collector(self.cfg.collector_type,self.cfg,self.episode_dir,save_video=True,scene_contract=contract,camera_meta=self.camera_meta)
        self.collector.begin_episode(0,np.array(self.debug['object_position_m']),episode_id=self.episode_id,metadata=dict(seed=int(seed or 0),
            policy_id=self.options.get('policy_id','teacher' if self.options.get('teacher') else 'external'),demonstrator_id=self.options.get('demonstrator_id','unknown'),
            task_type=self.cfg.env.task_type,source_slot_id=self.cfg.rack.selected_slot_id,target_seat_id=self.cfg.adapter.selected_target_seat_id,asset_version=contract['asset_manifest_sha256'],**size_metadata))
        self._obs=self._public_observation();self._record_state=self._collector_state();self.ended=False
        self._video_writers={};self._video_last_t=-1.;self._video_frame_times=[];self._write_video()
        self._write(self.episode_dir/'initial_debug.json',self.debug)
        self._write(self.episode_dir/'initialization_timing.json',dict(engine_clock_origin_s=self.engine_time_origin,first_observation_episode_time_s=self.t,physics_steps_recorded_before_first_observation=self.steps,reset_render_flush_passes=4,render_flush_passes_per_control=2,source_early_fall_recorded_from_step0=True,physics_backend='CPU PhysX',render_transform_path='Fabric disabled; explicit PhysX USD writeback',transform_update_settings=list(pc.get_physx_update_transformations_settings())))
        if self.cfg.env.task_type=='loading' and self._geometry_valid() is not True:
            self.finalize_episode('GEOMETRY_PRECHECK_BLOCKED','GEOMETRY_PRECHECK_BLOCKED')
        return self.get_observation(),self._public_info()
    def _ensure_bound_audit(self):
        from importlib import import_module
        binding=import_module(self.cfg.env.get('geometry_audit_module','demos.lab_cuvette_env_v1.geometry_audit')).binding
        previous=self.geometry_audit.get('binding')
        current=binding(self.cfg,previous['files']) if previous else None
        if current is not None and current['fingerprint']==previous['fingerprint']:return
        root=Path(__file__).resolve().parents[1];path=self.episode_dir/'audit_input.yaml';OmegaConf.save(self.cfg,path)
        cache=root/self.cfg.env.geometry_audit_cache
        subprocess.run(['bash',str(root/'demos/lab_cuvette_external/usd_python.sh'),'-m',self.cfg.env.get('geometry_audit_module','demos.lab_cuvette_env_v1.geometry_audit'),'--config',str(path),'--output',str(cache),'--ensure','--geometry-site',str(self.cfg.env.shapely_site)],cwd=root,check=True)
        latest=json.loads((cache/'latest.json').read_text());self.geometry_audit=json.loads((cache/latest['audit_relative_path']).read_text())

    def _geometry_valid(self):
        a=self.geometry_audit
        if isinstance(a.get('geometry_valid'),bool):return a['geometry_valid']
        if isinstance(a.get('selected_target_geometry_valid'),bool):return a['selected_target_geometry_valid']
        for key in ['selected','summary','verdict']:
            if isinstance(a.get(key),dict) and isinstance(a[key].get('geometry_valid'),bool):return a[key]['geometry_valid']
        return None
    def _public_observation(self):
        p=self.debug['actual_tcp_position_m'];q=self.debug['actual_tcp_quaternion_wxyz']
        return dict(episode_id=self.episode_id,step_index=self.control_steps,simulation_time=self.t,
            images={n:self.images[n].copy() for n in self.rig.names},joint_positions=np.asarray(self.debug.get('joints',self.robot.get_joint_positions())).copy(),
            joint_velocities=self.robot.get_joint_velocities().copy(),TCPpose=dict(position_m=p,quaternion_wxyz=q),
            task_language=self.get_task_language(),source_slot_id=self.cfg.rack.selected_slot_id,target_seat_id=self.cfg.adapter.selected_target_seat_id)
    def _collector_state(self):
        camera_meta={n:self.rig.get_meta(n) for n in self.rig.names}
        return dict(episode_id=self.episode_id,step_index=self.control_steps,simulation_time=self.t,joint_positions=self.robot.get_joint_positions().copy(),
            camera_data={n+'_rgb':policy_image(self.images[n]) for n in self.rig.names},phase=self.phase,debug=copy.deepcopy(self.debug),
            camera_timestamps={n+'_rgb':camera_meta[n].get('sensor_rendering_time_s',float('nan')) for n in self.rig.names},camera_poses=camera_meta,
            control_aux=dict(command_q=self.qcmd.copy(),gripper_effort_limit_N=self.effort,gripper_target_m=self.grip/2))
    def _public_info(self):
        return dict(episode_id=self.episode_id,step_index=self.control_steps,simulation_time=self.t,terminated=self.ended,
            task_type=self.cfg.env.task_type,task_success=None if self._result is None else self._result.get('task_success'),
            termination_reason=None if self._result is None else self._result.get('termination_reason'),
            geometry_valid=self._geometry_valid(),debug_exposed=False,action_specs=self.ACTION_SPECS)
    def get_observation(self):
        if self._obs is None:raise RuntimeError('reset first')
        return copy.deepcopy(self._obs)
    def get_debug_observation(self):return copy.deepcopy(self.debug)
    def get_camera_meta(self,camera_name,**kwargs):
        """Public camera calibration/time only; privileged diagnostics stay on disk."""
        if kwargs:raise ValueError('Public camera metadata does not accept debug/extra options')
        metadata=self.rig.get_meta(camera_name)
        return {key:copy.deepcopy(value) for key,value in metadata.items() if key in self.PUBLIC_CAMERA_META_FIELDS}
    def render_camera(self,camera_name,**kwargs):
        if camera_name not in self.images:raise KeyError(camera_name)
        return self.images[camera_name].copy()
    def get_task_language(self):
        base=f'Pick the light cuvette from white rack slot {self.cfg.rack.selected_slot_id} and transport it to the {self.cfg.adapter.selected_target_seat_id} internal seat of the single open instrument.'
        if self.cfg.env.task_type=='preinsert_diagnostic':return base+' Stop safely above the seat without inserting or releasing, then lift back and hold.'
        if self.cfg.env.task_type=='grasp_hold':return 'Approach the light cuvette in the source rack, physically grip it and hold without extracting.'
        if self.cfg.env.task_type=='extract_transport':return base+' Extract fully, transport above the target and hold for3seconds without inserting or releasing.'
        return base+' Insert, transfer support, open both fingers, retreat and leave the vessel stable.'
    def _convert_action(self,action):
        if not isinstance(action,dict):raise ValueError('Actions require explicit typed envelope; untyped arrays refused')
        if action.get('episode_id')!=self.episode_id:raise ValueError('Stale/missing episode_id')
        if int(action.get('observation_step',-1))!=self.control_steps:raise ValueError('Stale/missing observation_step')
        kind=action.get('type');v=np.asarray(action.get('values',[]),float)
        if not np.isfinite(v).all():raise ValueError('Nonfinite action')
        duration=float(action.get('duration_s',1/self.cfg.physics.control_hz));ticks=round(duration*self.cfg.physics.control_hz)
        if ticks<1 or duration>self.cfg.env.max_action_duration_s or abs(ticks/self.cfg.physics.control_hz-duration)>1e-6:raise ValueError('duration must be whole control ticks within declared limit')
        opening=float(action.get('gripper_opening_m',action.get('gripper',self.grip)))
        if not np.isfinite(opening):raise ValueError('Nonfinite gripper opening')
        opening=float(np.clip(opening,0,.08));effort=np.asarray(action.get('gripper_effort_limit_N',action.get('effort_limit_N',self.effort)),float)
        if not np.isfinite(effort).all() or effort.shape not in [(),(2,)]:raise ValueError('Effort must be scalar or2 finite caps')
        effort=float(np.clip(np.min(effort),0,self.cfg.env.gripper_effort_max_N));current=self.robot.get_joint_positions().copy();q=current.copy()
        conversion=dict(input_type=kind,control_hz=self.cfg.physics.control_hz,physics_hz=self.cfg.physics.hz,duration_s=duration,ticks=ticks,
            gripper_semantics='total two-finger opening in metres -> two symmetric position targets',truth_used_by_environment=False)
        target_pose=None
        if kind=='joint_position':
            if v.shape not in [(7,),(9,)]:raise ValueError('joint_position values must be7 or9')
            if len(v)==9 and abs(sum(v[7:])-opening)>1e-5:raise ValueError('9D finger targets contradict declared total opening')
            q[:7]=current[:7]+np.clip(v[:7]-current[:7],-self.cfg.env.action_max_joint_delta_rad,self.cfg.env.action_max_joint_delta_rad)
        elif kind=='joint_velocity':
            if v.shape!=(7,):raise ValueError('joint_velocity requires7 arm rad/s; fingers are absolute opening')
            limits=np.asarray(self.ctx['old'].robot.max_velocity[:7],float);q[:7]=current[:7]+np.clip(v,-limits,limits)/self.cfg.physics.control_hz
        elif kind in ['ee_pose','ee_delta']:
            p=np.asarray(self.debug['actual_tcp_position_m']);r=Rotation.from_quat(np.roll(self.debug['actual_tcp_quaternion_wxyz'],-1))
            if kind=='ee_pose':
                if v.shape!=(7,) or np.linalg.norm(v[3:])<.5:raise ValueError('ee_pose requires xyz+unit quaternion wxyz')
                goalp=v[:3];goalr=Rotation.from_quat(np.roll(v[3:],-1))
            else:
                if v.shape!=(6,):raise ValueError('ee_delta requires world/tcp translation3+spatial rotation vector3')
                delta=np.clip(v[:3],-self.cfg.env.action_max_translation_m,self.cfg.env.action_max_translation_m);rotvec=v[3:];norm=np.linalg.norm(rotvec)
                if norm>self.cfg.env.action_max_rotation_rad:rotvec=rotvec/norm*self.cfg.env.action_max_rotation_rad
                if action.get('frame','world')=='tcp':goalp=p+r.apply(delta);goalr=r*Rotation.from_rotvec(rotvec)
                elif action.get('frame','world')=='world':goalp=p+delta;goalr=Rotation.from_rotvec(rotvec)*r
                else:raise ValueError('Unknown delta frame')
            dp=goalp-p;norm=np.linalg.norm(dp)
            if norm>self.cfg.env.action_max_translation_m:goalp=p+dp/norm*self.cfg.env.action_max_translation_m
            dr=(goalr*r.inv()).as_rotvec();norm=np.linalg.norm(dr)
            if norm>self.cfg.env.action_max_rotation_rad:goalr=Rotation.from_rotvec(dr/norm*self.cfg.env.action_max_rotation_rad)*r
            quat=np.roll(goalr.as_quat(),1);goal=np.r_[goalp,quat]
            cache_hit=bool(self._ik_goal is not None and self._ik_solution is not None and np.allclose(goal,self._ik_goal,atol=1e-12,rtol=0))
            if not cache_hit:
                solution,valid=self.solver.get_kinematics_solver().compute_inverse_kinematics(self.solver.get_end_effector_frame(),goalp,quat,warm_start=self._ik_seed,position_tolerance=float(self.ctx['old'].robot.ik_position_tolerance_m),orientation_tolerance=float(self.ctx['old'].robot.ik_orientation_tolerance_rad))
                if not valid:raise RuntimeError('CONTROL_OR_IK_FAILURE')
                self._ik_seed=np.asarray(solution).copy();self._ik_solution=self.solver.get_joints_subset().make_articulation_action(solution,None);self._ik_goal=goal.copy()
            ik=self._ik_solution
            q[np.asarray(ik.joint_indices,int)]=ik.joint_positions;target_pose=dict(position_m=goalp.tolist(),quaternion_wxyz=quat.tolist())
            conversion['IK']=dict(frame=self.solver.get_end_effector_frame(),warm_start='previous IK solution; reset initial actual arm q',position_tolerance_m=float(self.ctx['old'].robot.ik_position_tolerance_m),orientation_tolerance_rad=float(self.ctx['old'].robot.ik_orientation_tolerance_rad),unchanged_goal_cache_enabled=True,unchanged_goal_cache_hit=cache_hit,solver_called=not cache_hit)
        else:raise ValueError('Unknown action type')
        q[7:]=opening/2
        rate=np.asarray(self.ctx['old'].robot.max_velocity[:7])/self.cfg.physics.control_hz
        q[:7]=self.qcmd[:7]+np.clip(q[:7]-self.qcmd[:7],-rate,rate)
        q[:7]=np.clip(q[:7],np.asarray(self.robot.dof_properties['lower'][:7]),np.asarray(self.robot.dof_properties['upper'][:7]))
        conversion.update(target_pose=target_pose,raw_values=v.tolist(),executed_q=q.tolist(),effort_limit_N=effort)
        return q,opening,effort,ticks,conversion
    def step(self,action):
        if self.closed or self.ctx is None:raise RuntimeError('reset first')
        if self.ended:raise RuntimeError('Episode terminated; reset before actions')
        q,opening,effort,ticks,conversion=self._convert_action(action);last=None
        for tick in range(ticks):
            if self.ended:break
            self.phase=str(action.get('metadata',{}).get('teacher_phase',action.get('metadata',{}).get('phase','POLICY')))
            if action['type']=='joint_velocity' and tick:
                current=self.robot.get_joint_positions().copy();limits=np.asarray(self.ctx['old'].robot.max_velocity[:7]);q[:7]=current[:7]+np.clip(np.asarray(action['values']),-limits,limits)/self.cfg.physics.control_hz
                q[:7]=np.clip(q[:7],self.robot.dof_properties['lower'][:7],self.robot.dof_properties['upper'][:7])
            applied_opening=opening
            if 'teacher_phase' not in action.get('metadata',{}):
                actual=np.asarray(self.debug['finger_joint_positions_m']);bilateral=np.all(np.asarray(self.debug['finger_contact_N'])>float(self.cfg.gripper.contact_threshold_N))
                if opening>float(actual.sum())+.001:self._policy_latch=None
                elif bilateral and self._policy_latch is None:
                    mu=np.sqrt(self.cfg.physics.dynamic_friction*self.cfg.physics.finger_dynamic_friction)
                    compression=min(float(self.cfg.gripper.maximum_compression_m),self.cfg.vessel.mass_kg*9.81*self.cfg.gripper.contact_safety_factor/(2*mu*self.ctx['old'].robot.finger_kp))
                    self._policy_latch=max(.002,float(actual.sum())-2*compression)
                if self._policy_latch is not None:applied_opening=max(opening,self._policy_latch)
                conversion['shared_gripper_contact_latch_total_m']=self._policy_latch
                conversion['requested_total_opening_m']=opening
            q[7:]=applied_opening/2
            self.qcmd=q.copy();self.grip=applied_opening;self.effort=effort
            conversion['executed_q']=self.qcmd.tolist()
            from isaacsim.core.utils.types import ArticulationAction
            self.ac.set_max_efforts(np.r_[self.ctx['old'].robot.max_effort[:7],[effort,effort]])
            self.ac.apply_action(ArticulationAction(joint_positions=self.qcmd))
            stop=None
            for _ in range(self.cfg.physics.hz//self.cfg.physics.control_hz):
                self.recorder.before_step(self.steps+1,(self.steps+1)/self.cfg.physics.hz,self.phase);self.world.step(render=False)
                self.steps+=1;self.t=self.steps/self.cfg.physics.hz;self.debug=self.recorder.capture(self.steps,self.t,self.phase,self.qcmd,self.grip/2,self.effort)
                evidence=self.scorer.update(self.debug)
                if evidence.get('terminate') and stop is None:stop=(evidence['termination_reason'],evidence.get('failure_type'))
            self.world.physics_sim_view.update_articulations_kinematic()
            for _ in range(int(self.cfg.env.get('render_flush_passes_per_control',2))):self.world.render()
            self.images=self.rig.get_images();self.control_steps+=1;self._obs=self._public_observation();next_state=self._collector_state()
            if self.t>=self.cfg.env.timeout_s:stop=stop or ('SIMULATION_TIMEOUT','TIMEOUT')
            if self._geometry_valid() is not True and np.linalg.norm(np.asarray(self.debug['object_position_m'])[:2]-self.ctx['fixtures']['target_floor'][:2])<.02 and self.debug['source_bottom_z_m']<self.ctx['fixtures']['target_rim_z']+.0005:
                stop=('GEOMETRY_SAFETY_STOP','GEOMETRY_PRECHECK_BLOCKED')
            command=dict(command_q=self.qcmd.copy(),episode_id=self.episode_id,gripper_target_m=self.grip/2,gripper_effort_limit_N=self.effort,
                raw_output=action.get('raw_model_action',action.get('raw_output',action)),conversion=conversion,
                inference_wall_time_s=action.get('inference_wall_time_s',action.get('inference_wall_s',np.nan)))
            truncated=bool(stop and stop[1] in ('TIMEOUT','POLICY_BUDGET'))
            self.collector.cache_transition(self._record_state,command,next_state,dict(terminated=bool(stop) and not truncated,truncated=truncated,reward=0.0))
            self._record_state=next_state;self._write_video();last=(self.get_observation(),0.,False,False,self._public_info())
            if stop:self.finalize_episode(*stop);last=(self.get_observation(),float(self._result.get('task_success') is True),not truncated,truncated,self._public_info())
        return last
    def chunk_step(self,actions,*,return_all_frames=False):
        results=[];actions=list(actions)
        if not actions:raise ValueError('Empty action chunk')
        if actions[0].get('episode_id')!=self.episode_id or int(actions[0].get('observation_step',-1))!=self.control_steps:raise ValueError('Stale action block origin')
        block_origin=self.control_steps
        for index,action in enumerate(actions):
            # An explicit action block is associated with its initial observation;
            # each subsequent element is rebased only inside this synchronous call.
            a=dict(action)
            if a.get('episode_id')!=self.episode_id:raise ValueError('Old-episode action chunk refused')
            a['observation_step']=self.control_steps
            a['metadata']=dict(a.get('metadata',{}),block_origin_observation_step=block_origin,block_index=index)
            results.append(self.step(a))
            if self.ended:break
        if not results:raise ValueError('Empty action chunk')
        result=results[-1]
        if return_all_frames:result=(*result[:4],dict(result[4],all_frames=[x[0] for x in results]))
        return result
    def _write_video(self,*,force=False):
        import cv2
        # The last control state can fall between native30Hz movie samples.
        # Append that actual terminal state once, without duplicating a state
        # already written at the same simulation time.
        if abs(self.t-self._video_last_t)<1e-9:return False
        if not force and self.t-self._video_last_t<1/30-1e-9:return False
        self._video_last_t=self.t;frames=[]
        for name in self.rig.names:
            frame=cv2.cvtColor(self.images[name],cv2.COLOR_RGB2BGR);h,w=frame.shape[:2]
            if name not in self._video_writers:self._video_writers[name]=cv2.VideoWriter(str(self.episode_dir/(name+'.mp4')),cv2.VideoWriter_fourcc(*'mp4v'),30,(w,h))
            self._video_writers[name].write(frame);frames.append(frame)
        both=np.concatenate(frames,axis=1)
        cv2.putText(both,f"{self.cfg.get('version','Env_v1')} {self.cfg.env.task_type} | t={self.t:.3f}s {self.phase}",(8,25),cv2.FONT_HERSHEY_SIMPLEX,.55,(255,255,255),2)
        if 'dual' not in self._video_writers:self._video_writers['dual']=cv2.VideoWriter(str(self.episode_dir/'dual_view.mp4'),cv2.VideoWriter_fourcc(*'mp4v'),30,(both.shape[1],both.shape[0]))
        self._video_writers['dual'].write(both)
        self._video_frame_times.append(float(self.t))
        return True
    def finalize_episode(self,termination_reason='POLICY_BUDGET',failure_type=None):
        if self._result is not None:return copy.deepcopy(self._result)
        if self.ctx is None:return None
        self._result=self.scorer.finalize(self.episode_id,self.cfg.env.task_type,termination_reason,failure_type)
        self._result.update(scene_version=str(self.cfg.get('version','Env_v1')),simulation_seconds=self.t,wall_seconds=time.perf_counter()-self.episode_wall,
            seed=int(self.cfg.env.seed),policy_id=self.options.get('policy_id','teacher'),actual_control_steps=self.control_steps,actual_physics_steps=self.steps)
        physical_score=copy.deepcopy(self._result);self._write(self.episode_dir/'independent_score.json',physical_score)
        labels=self.collector.finish_episode(self._result,independent_score=physical_score)
        self._result.update(labels);self._result['record_valid_scope']='independent physical trace AND collector action/sensor/time integrity'
        self._result['physical_score_record_valid']=physical_score.get('record_valid')
        self._result['record_integrity_errors']=list(self.collector._integrity_errors)
        self._write(self.episode_dir/'final_camera_meta.json',{n:self.rig.get_meta(n) for n in self.rig.names})
        terminal_frame_appended=self._write_video(force=True)
        self._write(self.episode_dir/'video_timestamps.json',dict(schema='labsim.Env_v1.native_video_timestamps.v1',
            videos=['side_camera.mp4','wrist_camera.mp4','dual_view.mp4'],nominal_fps=30,
            frame_simulation_times_s=self._video_frame_times,terminal_simulation_time_s=self.t,
            terminal_frame_appended_at_finalize=terminal_frame_appended,
            semantics='Actual sampled simulation times; final state appended once if not already sampled. Constant-rate MP4 endpoint spacing may differ from the final simulation interval.'))
        for writer in self._video_writers.values():writer.release()
        self._video_writers={};self.ended=True;self._write(self.episode_dir/'result.json',self._result)
        return copy.deepcopy(self._result)
    def close(self):
        if self.closed:return
        if not self.ended:self.finalize_episode('ENVIRONMENT_CLOSED','PROCESS_INTERRUPTED')
        self._cleanup_episode();self.closed=True
