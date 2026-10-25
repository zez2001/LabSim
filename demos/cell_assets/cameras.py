"""Front and side views shared by asset previews and interaction recordings."""


def create_views(stage, center, distance, resolution=(960, 720)):
    """Return RGB annotators looking at center (metres, Z up)."""
    import numpy as np
    import omni.replicator.core as rep
    from pxr import Gf, UsdGeom

    center = np.asarray(center, dtype=float)
    eyes = {
        "front": center + [0, -distance, distance * 0.45],
        "side": center + [distance, 0, distance * 0.45],
    }
    annotators = {}
    for name, eye in eyes.items():
        camera = UsdGeom.Camera.Define(stage, f"/World/Camera_{name}")
        transform = Gf.Matrix4d().SetLookAt(
            Gf.Vec3d(*eye), Gf.Vec3d(*center), Gf.Vec3d(0, 0, 1)
        ).GetInverse()
        UsdGeom.Xformable(camera).AddTransformOp().Set(transform)
        camera.CreateClippingRangeAttr(Gf.Vec2f(0.01, 100))
        camera.CreateFocalLengthAttr(30)
        product = rep.create.render_product(str(camera.GetPath()), resolution)
        annotator = rep.AnnotatorRegistry.get_annotator("rgb")
        annotator.attach([product])
        annotators[name] = annotator
    return annotators


def read_rgb(annotator):
    """Read a nonblank RGB frame; raise if rendering has not produced data."""
    pixels = annotator.get_data()
    if pixels.size == 0 or pixels[..., :3].std() < 1:
        raise RuntimeError("Camera produced no usable image")
    return pixels[..., :3].copy()
