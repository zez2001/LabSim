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


class VideoRecorder:
    """Record camera RGB frames; callers render before write and close in finally.

    Uses the same 30 fps, 960 x 720 MPEG-4 settings as the interaction demos.
    Imports OpenCV only on construction, so CLI help remains CPU-only.
    """

    def __init__(self, output, views):
        import cv2

        self.views = views
        self.writers = {}
        try:
            for name in views:
                writer = cv2.VideoWriter(
                    str(output / f"{name}.mp4"),
                    cv2.VideoWriter_fourcc(*"mp4v"), 30, (960, 720),
                )
                self.writers[name] = writer
                if not writer.isOpened():
                    raise RuntimeError(f"Cannot open video encoder for {name}")
        except Exception:
            self.close()
            raise

    def write(self):
        """Append one frame from each view without advancing physics or rendering."""
        import cv2

        for name, view in self.views.items():
            self.writers[name].write(cv2.cvtColor(read_rgb(view), cv2.COLOR_RGB2BGR))

    def close(self):
        """Release all encoders, including partially constructed recordings."""
        for writer in self.writers.values():
            writer.release()
        self.writers.clear()
