"""Continuous side/wrist sensors with explicit USD and policy image conventions.

Isaac imports happen only in create_cameras, after SimulationApp startup. This
module does not advance simulation or change sensor placement between phases.
"""
from __future__ import annotations
from copy import deepcopy
import json
from pathlib import Path
import numpy as np
from scipy.spatial.transform import Rotation

DEFAULT_CAMERA_CONFIG = {
    'side_camera': dict(eye_m=[-.55, 1.05, 1.60], target_m=[.08, -.08, 1.0], upworld=[0.,0.,1.],
                        focal_length_cm=1.2, horizontal_aperture_mm=20.955, resolution=[640,480], fps=60),
    'wrist_camera': dict(parent_link='/World/Franka/panda_hand', localeye_m=[.10,0.,.07],
                         localtarget_m=[0.,0.,.14], localup=[0.,0.,-1.],
                         focal_length_cm=1.2, horizontal_aperture_mm=20.955, resolution=[640,480], fps=60),
}


def look_at_usd(eye, target, up):
    """Camera-to-parent R: columns right,+Y-up,back; optical forward is -Z."""
    eye, target, up = (np.asarray(v, dtype=float) for v in (eye,target,up))
    if any(v.shape != (3,) or not np.isfinite(v).all() for v in (eye,target,up)):
        raise ValueError('Camera eye/target/up must be finite 3-vectors')
    z = eye-target
    if np.linalg.norm(z) < 1e-9:
        raise ValueError('Camera eye and target coincide')
    z /= np.linalg.norm(z)
    x = np.cross(up,z)
    if np.linalg.norm(x) < 1e-9:
        raise ValueError('Camera up is parallel to optical axis')
    x /= np.linalg.norm(x)
    y = np.cross(z,x)
    matrix = np.column_stack((x,y,z))
    xyzw = Rotation.from_matrix(matrix).as_quat()
    return matrix, np.r_[xyzw[3],xyzw[:3]]


def pose_matrix(position, quaternion_wxyz):
    q = np.asarray(quaternion_wxyz,float)
    result = np.eye(4)
    result[:3,:3] = Rotation.from_quat(np.r_[q[1:],q[0]]).as_matrix()
    result[:3,3] = np.asarray(position,float)
    return result


def authored_usd_transforms(stage,path,meters_per_unit):
    """Read authored xforms directly, respecting reset stacks; no Fabric writes."""
    from pxr import Usd,UsdGeom
    prim=stage.GetPrimAtPath(path);xf=UsdGeom.Xformable(prim);clock=Usd.TimeCode.Default()
    def matrix(value):
        value=np.asarray(value,float).T.copy();value[:3,3]*=meters_per_unit
        return value
    chain=[];current=prim
    while current and not current.IsPseudoRoot():
        item=UsdGeom.Xformable(current)
        if item:
            chain.append(dict(path=str(current.GetPath()),reset_xform_stack=bool(item.GetResetXformStack()),
                xform_op_order=list(current.GetAttribute('xformOpOrder').Get() or []),
                local_from_parent=matrix(item.GetLocalTransformation(clock)).tolist(),
                world_from_prim=matrix(item.ComputeLocalToWorldTransform(clock)).tolist()))
        current=current.GetParent()
    return matrix(xf.GetLocalTransformation(clock)),matrix(xf.ComputeLocalToWorldTransform(clock)),chain


def existing_fabric_world_transform(path,meters_per_unit):
    """Read existing Fabric only. XformPrim's Fabric getter can CREATE world xforms."""
    import omni.usd,usdrt
    stage=usdrt.Usd.Stage.Attach(omni.usd.get_context().get_stage_id())
    prim=stage.GetPrimAtPath(path)
    if not prim or not prim.IsValid():return dict(available=False,reason='No existing Fabric prim')
    matrix_attr=prim.GetAttribute('omni:fabric:worldMatrix')
    if matrix_attr and matrix_attr.IsValid():
        raw=matrix_attr.Get()
        if raw is not None:
            matrix=np.asarray(raw,float).T.copy()
            if matrix.shape==(4,4) and np.isfinite(matrix).all():
                matrix[:3,3]*=meters_per_unit
                return dict(available=True,world_from_camera=matrix.tolist(),
                    API='Read pre-existing omni:fabric:worldMatrix attr directly; no hierarchy update, selection creation or transform authoring')
    rt=usdrt.Rt.Xformable(prim)
    if not rt.HasWorldXform():
        local=rt.GetLocalMatrixAttr().Get() if rt.HasLocalXform() else None
        return dict(available=False,reason='No pre-existing Fabric world xform; no world xform was created',
            local_matrix_row_convention=np.asarray(local,float).tolist() if local is not None else None)
    position=rt.GetWorldPositionAttr().Get();quaternion=rt.GetWorldOrientationAttr().Get()
    if position is None or quaternion is None:return dict(available=False,reason='Existing Fabric world pose attributes are empty')
    q=np.r_[float(quaternion.GetReal()),np.asarray(quaternion.GetImaginary(),float)]
    value=pose_matrix(np.asarray(position,float)*meters_per_unit,q)
    return dict(available=True,world_from_camera=value.tolist(),
        API='usdrt.Rt.Xformable existing WorldPosition/WorldOrientation attrs; no SetWorldXformFromUsd or hierarchy mutation')


def render_binding_snapshot(stage,camera):
    """Read render-product camera targets and actual transformation output settings."""
    import carb,omni.kit.app
    path=str(getattr(camera,'_render_product_path',''))
    product=stage.GetPrimAtPath(path) if path else None
    relationships={}
    if product and product.IsValid():
        relationships={str(rel.GetName()):[str(p) for p in rel.GetTargets()]
            for rel in product.GetRelationships() if 'camera' in str(rel.GetName()).lower()}
    keys=('/physics/updateToUsd','/physics/updateVelocitiesToUsd','/physics/updateParticlesToUsd',
        '/physics/updateForceSensorsToUsd','/app/useFabricSceneDelegate','/renderer/active','/rtx/rendermode',
        '/omnihydra/useSceneGraphInstancing','/persistent/omnigraph/updateToUsd',
        '/app/hydraEngine/waitIdle','/app/updateOrder/checkForHydraRenderComplete')
    settings=carb.settings.get_settings();manager=omni.kit.app.get_app().get_extension_manager()
    return dict(render_product_path=path,render_product_prim_exists=bool(product and product.IsValid()),
        camera_relationships=relationships,expected_camera_prim=camera.prim_path,
        expected_camera_is_target=any(camera.prim_path in targets for targets in relationships.values()),
        settings={key:settings.get(key) for key in keys},
        extensions={name:bool(manager.is_extension_enabled(name)) for name in ('omni.physx.fabric','omni.physx','omni.hydra.rtx')},
        semantics='Read-only actual settings/relationships; missing keys remain null and do not imply a default.')


def diagnostic_json(value):
    if isinstance(value,dict):return {str(k):diagnostic_json(v) for k,v in value.items()}
    if isinstance(value,np.ndarray):return diagnostic_json(value.tolist())
    if isinstance(value,(list,tuple)):return [diagnostic_json(v) for v in value]
    if isinstance(value,(np.bool_,bool)):return bool(value)
    if isinstance(value,(np.integer,int)):return int(value)
    if isinstance(value,(np.floating,float)):return float(value) if np.isfinite(value) else None
    return value


def depth_summary(depth):
    values=np.asarray(depth,float)
    good=np.isfinite(values)&(values>0)
    valid=values[good];height,width=values.shape
    return dict(shape_hw=[height,width],finite_positive_fraction=float(good.mean()),
        min_m=float(valid.min()) if valid.size else None,max_m=float(valid.max()) if valid.size else None,
        percentiles_5_50_95_m=np.percentile(valid,[5,50,95]).tolist() if valid.size else None,
        center_m=diagnostic_json(values[height//2,width//2]),
        semantics='Official distance_to_image_plane annotator, metres, optical-axis depth; debug only, not a policy channel')


def policy_image(native_hwc, size=(256,256)):
    """Explicit native HWC RGB -> stretched 256x256 CHW RGB uint8, no rotation.

    Pixel geometry changes under this resize; scaled intrinsics are in get_meta.
    The model adapter may add another declared checkpoint-specific transform.
    """
    import cv2
    image = np.asarray(native_hwc)
    if image.ndim != 3 or image.shape[2] != 3 or image.dtype != np.uint8:
        raise ValueError('Expected native HWC RGB uint8')
    return np.transpose(cv2.resize(image,tuple(size),interpolation=cv2.INTER_AREA),(2,0,1)).copy()


class CameraRig:
    names = ('side_camera','wrist_camera')

    def __init__(self, ctx, cameras, specifications, meters_per_unit):
        self.ctx, self.cameras, self.specifications = ctx, cameras, specifications
        self.meters_per_unit = float(meters_per_unit)
        self._last_tokens, self._last_read = {}, {}
        self.closed = False
        self.lifecycle_events=[]
        self._debug_last_depth={};self._debug_first_saved=set()

    def _render_debug(self,name):
        camera=self.cameras[name];annotators=getattr(camera,'_custom_annotators',{})
        result=dict(enabled=bool(self.specifications[name].get('debug_render_diagnostics',False)),
                    policy_observation=False)
        if not result['enabled']:return result
        for key in ('CameraParams','distance_to_image_plane'):
            if key not in annotators:
                result[key]=dict(available=False,reason='Annotator was not attached',
                    attach_errors=self.specifications[name].get('debug_annotator_attach_errors',[]));continue
            try:
                value=annotators[key].get_data()
                if key=='CameraParams':result[key]=dict(available=bool(value),raw=diagnostic_json(value),
                    semantics='Exact official renderer CameraParams output; raw view/projection convention must be verified, not assumed from field name')
                else:
                    array=np.asarray(value)
                    if array.ndim!=2 or not array.size:
                        result[key]=dict(available=False,reason='No 2D depth frame yet')
                    else:
                        result[key]=dict(available=True,statistics=depth_summary(array))
                        self._debug_last_depth[name]=array.copy()
                        if name not in self._debug_first_saved:
                            self._save_depth(name,array,'first');self._debug_first_saved.add(name)
            except Exception as exc:
                result[key]=dict(available=False,error_type=type(exc).__name__,message=str(exc))
        return result

    def _save_depth(self,name,depth,label):
        output=self.ctx.get('output')
        if output is None:return
        folder=Path(output)/'camera_debug';folder.mkdir(exist_ok=True)
        path=folder/(name+'_depth_'+label+'.npz')
        if path.exists():return
        np.savez_compressed(path,distance_to_image_plane_m=depth)

    def get_images(self):
        """Return native HWC RGB images keyed by physical camera name, never copied views."""
        if self.closed:
            raise RuntimeError('Camera rig is closed')
        images = {}
        for name in self.names:
            camera = self.cameras[name]
            rgb = np.asarray(camera.get_rgb())
            width,height = self.specifications[name]['resolution']
            if rgb.ndim != 3 or rgb.shape[:2] != (height,width) or rgb.shape[2] < 3:
                raise RuntimeError(f'{name} has no valid rendered frame; render/warm sensors before observation')
            rgb = rgb[:,:,:3]
            if rgb.dtype != np.uint8:
                raise ValueError(f'{name} RGB dtype is {rgb.dtype}, expected uint8')
            frame = camera.get_current_frame()
            token = (frame.get('rendering_frame'),frame.get('rendering_time'))
            self._last_read[name] = dict(sensor_rendering_frame=token[0],sensor_rendering_time_s=token[1],
                repeated_sensor_frame=(name in self._last_tokens and token == self._last_tokens[name]),
                black_frame=bool(np.max(rgb) <= 1), mean_intensity=float(rgb.mean()),
                image_orientation_transform='none; authored USD camera orientation only',
                observation_simulation_time_s=self._simulation_time())
            self._last_tokens[name] = token
            images[name] = rgb.copy()
        return images

    def _simulation_time(self):
        world = self.ctx['world']
        value = getattr(world,'current_time',None)
        return float(value) if value is not None else None

    def get_meta(self, name):
        if name not in self.names:
            raise KeyError(name)
        camera, spec = self.cameras[name], self.specifications[name]
        api_world_p,api_world_q=camera.get_world_pose(camera_axes='usd')
        api_local_p,api_local_q=camera.get_local_pose(camera_axes='usd')
        authored_local,world_usd,parent_chain=authored_usd_transforms(self.ctx['stage'],camera.prim_path,self.meters_per_unit)
        world_p=world_usd[:3,3];world_xyzw=Rotation.from_matrix(world_usd[:3,:3]).as_quat();world_q=np.r_[world_xyzw[3],world_xyzw[:3]]
        local_p=authored_local[:3,3];local_xyzw=Rotation.from_matrix(authored_local[:3,:3]).as_quat();local_q=np.r_[local_xyzw[3],local_xyzw[:3]]
        eye=spec['eye_m'] if name=='side_camera' else spec['localeye_m']
        target=spec['target_m'] if name=='side_camera' else spec['localtarget_m']
        up=spec['upworld'] if name=='side_camera' else spec['localup']
        _,expected_local_q=look_at_usd(eye,target,up)
        configured_local=pose_matrix(eye,expected_local_q)
        world_cv = world_usd @ np.diag([1.,-1.,-1.,1.])
        K = np.asarray(camera.get_intrinsics_matrix(),float)
        width,height = spec['resolution']
        scaled_K = np.diag([256/width,256/height,1.]) @ K
        pose_sources=dict(USD=dict(world_from_camera=world_usd.tolist(),available=True,
            API='UsdGeom.Xformable.ComputeLocalToWorldTransform(Default), respecting resetXformStack'),
            camera_API_USD=dict(available=True,world_from_camera=pose_matrix(np.asarray(api_world_p)*self.meters_per_unit,api_world_q).tolist(),
            API='Camera.get_world_pose(camera_axes=usd); vendor recursive helper may differ from direct USD reset-stack semantics'))
        try:
            pose_sources['Fabric']=existing_fabric_world_transform(camera.prim_path,self.meters_per_unit)
            if pose_sources['Fabric']['available']:
                fabric_T=np.asarray(pose_sources['Fabric']['world_from_camera'])
                pose_sources['Fabric'].update(position_delta_from_USD_m=float(np.linalg.norm(fabric_T[:3,3]-world_usd[:3,3])),
                    rotation_delta_from_USD_deg=float(np.rad2deg(Rotation.from_matrix(fabric_T[:3,:3]@world_usd[:3,:3].T).magnitude())))
        except Exception as exc:
            pose_sources['Fabric']=dict(available=False,error_type=type(exc).__name__,message=str(exc))
        if name=='wrist_camera' and self.ctx.get('hand') is not None:
            try:
                parent_p,parent_q=self.ctx['hand'].get_world_pose()
                parent_T=pose_matrix(np.asarray(parent_p)*self.meters_per_unit,parent_q)
                expected=parent_T@authored_local
                pose_sources['physics_hand_times_mount']=dict(available=True,world_from_camera=expected.tolist(),
                    position_delta_from_USD_m=float(np.linalg.norm(expected[:3,3]-world_usd[:3,3])),
                    rotation_delta_from_USD_deg=float(np.rad2deg(Rotation.from_matrix(expected[:3,:3]@world_usd[:3,:3].T).magnitude())),
                    API='SingleRigidPrim panda_hand world pose times authored local camera pose; not a camera pose setter')
            except Exception as exc:
                pose_sources['physics_hand_times_mount']=dict(available=False,error_type=type(exc).__name__,message=str(exc))
        frame = camera.get_current_frame()
        return dict(name=name,prim_path=camera.prim_path,physical_parent=spec['physical_parent'],
            mounting='fixed_world' if name == 'side_camera' else 'robot_hand_link',
            local_pose_position_m=np.asarray(local_p).tolist(),
            local_pose_quaternion_wxyz=np.asarray(local_q).tolist(),
            world_pose_position_m=np.asarray(world_p).tolist(),
            world_pose_quaternion_wxyz=np.asarray(world_q).tolist(),
            world_from_camera_usd=world_usd.tolist(),camera_cv_from_world=np.linalg.inv(world_cv).tolist(),
            extrinsic_translation_unit='metre',meters_per_stage_unit=self.meters_per_unit,
            authored_parent_chain=parent_chain,
            render_binding=render_binding_snapshot(self.ctx['stage'],camera),
            renderer_debug=self._render_debug(name),
            configured_mount_from_parent=configured_local.tolist(),
            authored_mount_position_difference_from_config_m=float(np.linalg.norm(authored_local[:3,3]-configured_local[:3,3])),
            authored_mount_rotation_difference_from_config_deg=float(np.rad2deg(Rotation.from_matrix(authored_local[:3,:3]@configured_local[:3,:3].T).magnitude())),
            vendor_API_local_pose_raw=dict(position_m=(np.asarray(api_local_p)*self.meters_per_unit).tolist(),
                quaternion_wxyz=np.asarray(api_local_q).tolist(),
                warning='Installed get_local_pose may divide Fabric camera world by USD parent world; not the authored fixed mount definition'),
            pose_sources=pose_sources,extrinsic_pose_source='Direct USD query with authored reset-stack semantics; Fabric and physical parent alternatives saved; rendered pixel association requires runtime validation',
            optical_conventions=dict(usd='+X right,+Y up,-Z forward',opencv='+X right,+Y down,+Z forward',
                                     world='+Z up',quaternion='wxyz'),
            intrinsic_matrix_native=K.tolist(),intrinsic_matrix_policy_256=scaled_K.tolist(),
            focal_length_cm=float(spec['focal_length_cm']),
            horizontal_aperture_mm=float(spec['horizontal_aperture_mm']),
            vertical_aperture_mm=float(spec['horizontal_aperture_mm'])*height/width,
            lens_units=dict(configuration='Synthetic nominal cm/mm camera convention; not measured real optics',
                USD_authored=dict(focalLength=float(camera.prim.GetAttribute('focalLength').Get()),
                    horizontalAperture=float(camera.prim.GetAttribute('horizontalAperture').Get()),
                    verticalAperture=float(camera.prim.GetAttribute('verticalAperture').Get()),
                    projection=str(camera.prim.GetAttribute('projection').Get()),
                    fStop=float(camera.prim.GetAttribute('fStop').Get())),
                Isaac_API_stage_unit_numbers=dict(focal_length=float(camera.get_focal_length()),
                    horizontal_aperture=float(camera.get_horizontal_aperture()),vertical_aperture=float(camera.get_vertical_aperture())),
                actual_optical_calibration=False,
                rationale='Normalize lens/aperture together to ordinary native USD camera number range; ratio and requested pinhole K unchanged. Renderer actual projection recorded independently.'),
            resolution_wh=[width,height],channels='RGB',native_array_layout='HWC uint8',
            policy_transform=dict(resize_wh=[256,256],interpolation='OpenCV INTER_AREA',layout='CHW uint8',
                                  crop='none',rotation_deg=0,flip='none',aspect_ratio='stretch 4:3 to1:1; scaled K saved'),
            requested_fps=float(spec['fps']),actual_sensor_frequency_hz=float(camera.get_frequency()),
            sensor_rendering_frame=frame.get('rendering_frame'),sensor_rendering_time_s=frame.get('rendering_time'),
            sensor_timestamp_clock='SimulationManager engine time; subtract recordedengine_time_origin for episodeelapsed',
            sensor_frame_token_semantics='ReferenceTime numerator/denominator token,not an integer controlstep or movieframe',
            read_simulation_time_s=self._simulation_time(),last_image_read=self._last_read.get(name),
            source='video-informed synthetic camera placement; not calibrated real camera',
            configuration=deepcopy(spec))

    def debug_projection(self,name,points_world_m):
        """Explicit debug-only projection; caller supplies points, no hidden truth in metadata."""
        meta=self.get_meta(name);points=np.asarray(points_world_m,float).reshape(-1,3)
        K=np.asarray(meta['intrinsic_matrix_native']);width,height=meta['resolution_wh'];result={}
        for source,value in meta['pose_sources'].items():
            if not value.get('available'):continue
            T=np.asarray(value['world_from_camera'])@np.diag([1.,-1.,-1.,1.])
            xyz=(np.c_[points,np.ones(len(points))]@np.linalg.inv(T).T)[:,:3]
            pixel=xyz@K.T;uv=np.full((len(points),2),np.nan);valid=xyz[:,2]>1e-9
            uv[valid]=pixel[valid,:2]/pixel[valid,2:3]
            inside=valid&(uv[:,0]>=0)&(uv[:,0]<width)&(uv[:,1]>=0)&(uv[:,1]<height)
            result[source]=dict(uv_native=uv.tolist(),depth_m=xyz[:,2].tolist(),within_image=inside.tolist())
        return dict(camera=name,channel='debug_only_explicit_worldpoints',projections=result)

    def reset_history(self):
        self._last_tokens.clear()
        self._last_read.clear()

    def initialize_after_reset(self):
        for camera in self.cameras.values():
            camera.initialize()
        self.reset_history()

    def close(self):
        if self.closed:return
        for name,depth in self._debug_last_depth.items():self._save_depth(name,depth,'last')
        # Camera.destroy in installed5.1 aborts midway if SyntheticData has
        # already invalidated a dependency node. Pause every sensor first,
        # detach each owned product explicitly, and still clean the other
        # camera/products on error. Do not retry broken detach in __del__.
        products=[]
        def attempt(name,operation,callback):
            try:
                callback()
                self.lifecycle_events.append(dict(camera=name,operation=operation,status='completed'))
            except Exception as exc:
                self.lifecycle_events.append(dict(camera=name,operation=operation,status='error',
                    exception_type=type(exc).__name__,message=str(exc)))
        for name,camera in self.cameras.items():
            attempt(name,'pause_acquisition',camera.pause)
            for attr in ('_acquisition_callback','_timer_reset_callback','_stage_open_callback'):
                if hasattr(camera,attr):setattr(camera,attr,None)
        for name,camera in self.cameras.items():
            path=getattr(camera,'_render_product_path',None)
            owned=getattr(camera,'_custom_annotators',{})
            # Remove ownership before detach so a failed vendor call cannot
            # fire again during Camera.__del__ after the stage is gone.
            annotators=list(owned.items());owned.clear()
            reference=getattr(camera,'_fabric_time_annotator',None)
            if reference is not None:
                setattr(camera,'_fabric_time_annotator',None)
                annotators.append(('ReferenceTime',reference))
            for label,annotator in annotators:
                if path is not None:
                    attempt(name,'detach_'+label,lambda annotator=annotator,path=path:annotator.detach([path]))
            frame=getattr(camera,'_current_frame',None)
            if isinstance(frame,dict):
                for label,_ in annotators:frame.pop(label,None)
            product=getattr(camera,'_render_product',None)
            setattr(camera,'_render_product',None)
            if product is not None:products.append((name,product))
        # Shared graph dependencies see all annotator detaches before any
        # render product disappears; the camera destructor is now a no-op.
        for name,product in products:attempt(name,'destroy_render_product',product.destroy)
        self.closed=True
        status=dict(schema='labsim.Env_v1.camera_lifecycle.v1',events=self.lifecycle_events,
            cleanup_errors_observed=any(e['status']=='error' for e in self.lifecycle_events),
            vendor_graph_cleanup_fully_verified=False if any(e['status']=='error' for e in self.lifecycle_events) else None,
            real_process_exit_requires_runtime_check=True)
        destination=self.ctx.get('output')
        if destination is not None:
            path=Path(destination)/'camera_lifecycle.json'
            path.write_text(json.dumps(status,ensure_ascii=False,indent=2)+'\n')
        return status


def normalized_camera_spec(name,source):
    """Honor explicit config aliases used by the formal task without silent fallback."""
    from omegaconf import OmegaConf
    source=OmegaConf.to_container(source,resolve=True) if OmegaConf.is_config(source) else dict(source)
    aliases=({'up':'upworld'} if name=='side_camera' else
             {'local_eye_m':'localeye_m','local_target_m':'localtarget_m','local_up':'localup'})
    for supplied,canonical in aliases.items():
        if supplied in source:
            if canonical in source and not np.array_equal(source[canonical],source[supplied]):
                raise ValueError('Conflicting camera aliases: '+supplied+' and '+canonical)
            source[canonical]=source[supplied]
    spec=deepcopy(DEFAULT_CAMERA_CONFIG[name]);spec.update(source)
    spec['resolution']=[int(x) for x in spec['resolution']]
    if len(spec['resolution'])!=2 or min(spec['resolution'])<=0:
        raise ValueError('Camera resolution must be [width,height]')
    if list(spec.get('policy_resolution',[256,256])) != [256,256]:
        raise ValueError('Current policy image contract is256x256; declare a new transform before changing it')
    return spec


def create_cameras(ctx, cfg):
    """Create only side_camera and wrist_camera; caller owns rendering cadence."""
    from pxr import UsdGeom
    from isaacsim.sensors.camera import Camera
    raw = cfg.get('cameras',{})
    specs, cameras = {}, {}
    units = float(UsdGeom.GetStageMetersPerUnit(ctx['stage']))
    if units <= 0:
        raise ValueError('Stage length unit must be positive')
    for name in CameraRig.names:
        source = raw.get(name,raw.get('side' if name == 'side_camera' else 'wrist',{}))
        spec = normalized_camera_spec(name,source)
        if name == 'side_camera':
            path = str(spec.get('prim_path','/World/SideCamera'))
            parent=path.rsplit('/',1)[0]
            if parent!='/World':raise ValueError('Side camera must have explicit fixed world parent /World')
            eye,target,up = (spec['eye_m'],spec['target_m'],spec['upworld'])
        else:
            parent = str(spec['parent_link'])
            if not ctx['stage'].GetPrimAtPath(parent).IsValid():
                raise ValueError('Wrist camera parent link does not exist: '+parent)
            path = str(spec.get('prim_path',parent+'/EnvV1WristCamera'))
            if path.rsplit('/',1)[0]!=parent:raise ValueError('Wrist camera prim must be a child of its declared physical parent')
            eye,target,up = (spec['localeye_m'],spec['localtarget_m'],spec['localup'])
        _, quaternion = look_at_usd(eye,target,up)
        # Author the complete native lens before creating sensor/render product.
        # The previous very small but ratio-correct USD values (.12/.20955)
        # produced an observed renderer default50/20.955 projection. Keep the
        # same nominal FOV but use ordinary USD camera lens number ranges;
        # fStop=0 means no uncalibrated optical depth-of-field interpretation.
        authored=UsdGeom.Camera.Define(ctx['stage'],path)
        authored.CreateProjectionAttr('perspective')
        authored.CreateFocalLengthAttr(float(spec['focal_length_cm'])*10.)
        authored.CreateHorizontalApertureAttr(float(spec['horizontal_aperture_mm']))
        authored.CreateVerticalApertureAttr(float(spec['horizontal_aperture_mm'])*spec['resolution'][1]/spec['resolution'][0])
        authored.CreateHorizontalApertureOffsetAttr(0.);authored.CreateVerticalApertureOffsetAttr(0.)
        authored.CreateFStopAttr(0.)
        camera = Camera(path,name='env_v1_'+name,frequency=float(spec['fps']),resolution=tuple(spec['resolution']))
        # Installed5.1 setters multiply their API argument by10 into USD attrs.
        # These numeric conventions preserve the requested f/aperture ratio;
        # they are explicitly not an independent physical camera calibration.
        camera.set_focal_length(float(spec['focal_length_cm']))
        camera.set_horizontal_aperture(float(spec['horizontal_aperture_mm'])/10.)
        camera.set_clipping_range(.001/units,10./units)
        if name == 'side_camera':
            camera.set_world_pose(np.asarray(eye)/units,quaternion,camera_axes='usd')
        else:
            camera.set_local_pose(np.asarray(eye)/units,quaternion,camera_axes='usd')
        # A wrist sensor must inherit its hand. Author once at construction;
        # never reposition a world camera each frame to imitate a wrist view.
        UsdGeom.Xformable(ctx['stage'].GetPrimAtPath(path)).SetResetXformStack(False)
        camera.initialize()
        spec.update(prim_path=path,physical_parent=parent)
        spec['debug_render_diagnostics']=bool(raw.get('debug_render_diagnostics',True))
        if spec['debug_render_diagnostics']:
            errors=[]
            for key in ('CameraParams','distance_to_image_plane'):
                try:camera.attach_annotator(key)
                except Exception as exc:errors.append(dict(annotator=key,error_type=type(exc).__name__,message=str(exc)))
            spec['debug_annotator_attach_errors']=errors
        specs[name],cameras[name] = spec,camera
    return CameraRig(ctx,cameras,specs,units)
