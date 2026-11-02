"""A calibrated fixed side camera and a real robot-mounted wrist camera."""

import numpy as np
from scipy.spatial.transform import Rotation


def create(stage):
    import omni.replicator.core as rep
    from pxr import Gf, UsdGeom

    path = "/World/Franka/panda_hand/UnitWristCamera"
    camera = UsdGeom.Camera.Define(stage, path)
    # Look down the hand's local +Z axis along the fingers; camera -Z is optical.
    xform = UsdGeom.Xformable(camera)
    xform.AddTranslateOp().Set(Gf.Vec3d(0.055, 0, 0.02))
    xform.AddRotateXYZOp().Set(Gf.Vec3f(180, 0, 0))
    camera.CreateClippingRangeAttr(Gf.Vec2f(0.005, 100))
    camera.CreateFocalLengthAttr(18)
    paths = {"side_camera": "/World/Camera_side", "wrist_camera": path}
    views = {}
    for name, path in paths.items():
        product = rep.create.render_product(path, (256, 256))
        annotator = rep.AnnotatorRegistry.get_annotator("rgb")
        annotator.attach([product])
        views[name] = annotator
    return paths, views


def metadata(stage, path, name, time):
    from pxr import Usd, UsdGeom

    camera = UsdGeom.Camera.Get(stage, path)
    matrix = np.array(
        UsdGeom.Xformable(camera).ComputeLocalToWorldTransform(Usd.TimeCode.Default())
    ).T
    cv = np.diag([1, -1, -1, 1]) @ np.linalg.inv(matrix)
    focal = float(camera.GetFocalLengthAttr().Get())
    aperture = float(camera.GetHorizontalApertureAttr().Get())
    fy = fx = 256 * focal / aperture
    quat = np.roll(Rotation.from_matrix(matrix[:3, :3]).as_quat(), 1)
    return dict(
        name=name,
        physical_parent="panda_hand" if name == "wrist_camera" else "world",
        world_pose_position_m=matrix[:3, 3].tolist(),
        world_pose_quaternion_wxyz=quat.tolist(),
        camera_cv_from_world=cv.tolist(),
        intrinsic_matrix_native=[[fx, 0, 128], [0, fy, 128], [0, 0, 1]],
        resolution_wh=[256, 256],
        sensor_rendering_time_s=time,
        source="USD camera world transform at the recorded physics boundary",
    )
