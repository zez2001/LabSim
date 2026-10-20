"""Continuous side/wrist sensors with explicit USD and policy image conventions.

Isaac imports happen only in create_cameras, after SimulationApp startup. This
module does not advance simulation or change sensor placement between phases.
"""
from __future__ import annotations
from copy import deepcopy
import numpy as np
from scipy.spatial.transform import Rotation

DEFAULT_CAMERA_CONFIG = {
    'side_camera': dict(eye_m=[-.5, 1.0, 1.65], target_m=[0., -.07, 1.0], upworld=[0.,0.,1.],
                        focal_length_cm=1.8, horizontal_aperture_mm=20.955, resolution=[640,480], fps=60),
    'wrist_camera': dict(parent_link='/World/Franka/panda_hand', localeye_m=[.055,0.,.035],
                         localtarget_m=[0.,0.,.12], localup=[0.,0.,-1.],
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
        world_p, world_q = camera.get_world_pose(camera_axes='usd')
        local_p, local_q = camera.get_local_pose(camera_axes='usd')
        world_usd = pose_matrix(np.asarray(world_p)*self.meters_per_unit,world_q)
        world_cv = world_usd @ np.diag([1.,-1.,-1.,1.])
        K = np.asarray(camera.get_intrinsics_matrix(),float)
        width,height = spec['resolution']
        scaled_K = np.diag([256/width,256/height,1.]) @ K
        frame = camera.get_current_frame()
        return dict(name=name,prim_path=camera.prim_path,physical_parent=spec['physical_parent'],
            mounting='fixed_world' if name == 'side_camera' else 'robot_hand_link',
            local_pose_position_m=(np.asarray(local_p)*self.meters_per_unit).tolist(),
            local_pose_quaternion_wxyz=np.asarray(local_q).tolist(),
            world_pose_position_m=(np.asarray(world_p)*self.meters_per_unit).tolist(),
            world_pose_quaternion_wxyz=np.asarray(world_q).tolist(),
            world_from_camera_usd=world_usd.tolist(),camera_cv_from_world=np.linalg.inv(world_cv).tolist(),
            extrinsic_translation_unit='metre',meters_per_stage_unit=self.meters_per_unit,
            optical_conventions=dict(usd='+X right,+Y up,-Z forward',opencv='+X right,+Y down,+Z forward',
                                     world='+Z up',quaternion='wxyz'),
            intrinsic_matrix_native=K.tolist(),intrinsic_matrix_policy_256=scaled_K.tolist(),
            focal_length_cm=float(camera.get_focal_length()*self.meters_per_unit*100),
            horizontal_aperture_mm=float(camera.get_horizontal_aperture()*self.meters_per_unit*1000),
            vertical_aperture_mm=float(camera.get_vertical_aperture()*self.meters_per_unit*1000),
            resolution_wh=[width,height],channels='RGB',native_array_layout='HWC uint8',
            policy_transform=dict(resize_wh=[256,256],interpolation='OpenCV INTER_AREA',layout='CHW uint8',
                                  crop='none',rotation_deg=0,flip='none',aspect_ratio='stretch 4:3 to1:1; scaled K saved'),
            requested_fps=float(spec['fps']),actual_sensor_frequency_hz=float(camera.get_frequency()),
            sensor_rendering_frame=frame.get('rendering_frame'),sensor_rendering_time_s=frame.get('rendering_time'),
            read_simulation_time_s=self._simulation_time(),last_image_read=self._last_read.get(name),
            source='video-informed synthetic camera placement; not calibrated real camera',
            configuration=deepcopy(spec))

    def reset_history(self):
        self._last_tokens.clear()
        self._last_read.clear()

    def initialize_after_reset(self):
        for camera in self.cameras.values():
            camera.initialize()
        self.reset_history()

    def close(self):
        if not self.closed:
            for camera in self.cameras.values():
                camera.destroy()
            self.closed = True


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
        camera = Camera(path,name='env_v1_'+name,frequency=float(spec['fps']),resolution=tuple(spec['resolution']))
        # This installed5.1 API uses stage units for focal length and aperture.
        # Convert the config's physical cm/mm explicitly, preserving the FOV ratio.
        camera.set_focal_length(float(spec['focal_length_cm'])*.01/units)
        camera.set_horizontal_aperture(float(spec['horizontal_aperture_mm'])*.001/units)
        camera.set_clipping_range(.001/units,10./units)
        if name == 'side_camera':
            camera.set_world_pose(np.asarray(eye)/units,quaternion,camera_axes='usd')
        else:
            camera.set_local_pose(np.asarray(eye)/units,quaternion,camera_axes='usd')
        camera.initialize()
        spec.update(prim_path=path,physical_parent=parent)
        specs[name],cameras[name] = spec,camera
    return CameraRig(ctx,cameras,specs,units)
