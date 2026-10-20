"""Render an honestly labelled CAD review; never call it a physical trajectory."""
from pathlib import Path
import json
import time
import numpy as np


def render(args, app):
    import cv2
    import omni.usd
    import omni.timeline
    import omni.replicator.core as rep
    from isaacsim.core.api import World
    from isaacsim.sensors.camera import Camera
    from isaacsim.core.utils.viewports import set_camera_view
    from pxr import UsdGeom
    start = time.monotonic()
    omni.usd.get_context().open_stage(str(args.scene.resolve()))
    world = World(stage_units_in_meters=1., physics_dt=1/240, rendering_dt=1/60, backend='numpy', device='cpu')
    # Do not reset/play the physics world: reset can internally integrate setup
    # ticks even before a user's first explicit step. The robot is CAD pose only.
    omni.timeline.get_timeline_interface().pause()
    stage = omni.usd.get_context().get_stage()
    cache = UsdGeom.XformCache()
    initial = np.array(cache.GetLocalToWorldTransform(stage.GetPrimAtPath('/World/VesselPreview')))[3, :3]
    before = float(world.current_time)
    views = [
        ('reference', [1.60, 1.90, 2.30], [.50, .27, 1.05], 1.8),
        ('top', [.36, .20, 2.30], [.36, .20, .87], 2.1),
        ('side', [1.70, .26, 1.25], [.35, .26, 1.03], 1.9),
        ('chamber', [.24, .78, 1.38], [.21, .275, .92], 3.7),
    ]
    cameras = []
    for name, eye, target, focal in views:
        path = '/World/ReviewCamera_'+name
        camera = Camera(path, name=name, frequency=60, resolution=(1920, 1080))
        camera.set_focal_length(focal)
        camera.set_clipping_range(.0001, 10.0)
        set_camera_view(np.array(eye), np.array(target), camera_prim_path=path)
        camera.initialize()
        cameras.append((name, camera, eye, target))
    for _ in range(4):
        rep.orchestrator.step(rt_subframes=4, delta_time=0.0, pause_timeline=True)
    print('REVIEW_RENDER_WARMUP_COMPLETE', flush=True)
    saved = []
    for name, camera, eye, target in cameras:
        for _ in range(3):
            world.render()
        rgb = camera.get_rgb()
        print('REVIEW_RGB', name, None if rgb is None else rgb.shape, flush=True)
        if rgb is None or rgb.shape[:2] != (1080, 1920):
            raise RuntimeError(f'No valid rendered camera frame: {name}')
        image = cv2.cvtColor(rgb[:, :, :3], cv2.COLOR_RGB2BGR)
        lines = ['V0_demo02 | STATIC CAD REVIEW | NO PHYSICAL EPISODE',
                 'COMPLETE SOURCE RACK MISSING | NATIVE VESSEL / SEAT FIT NOT ACCEPTED',
                 'Lid pose: near-vertical image estimate; vessel is an UNSUPPORTED preview above candidate']
        for i, text in enumerate(lines):
            cv2.putText(image, text, (18, 33+i*30), cv2.FONT_HERSHEY_SIMPLEX, .66, (0, 0, 0), 4)
            cv2.putText(image, text, (18, 33+i*30), cv2.FONT_HERSHEY_SIMPLEX, .66, (255, 255, 255), 1)
        path = args.output/(name+'.png')
        assert cv2.imwrite(str(path), image)
        saved.append(dict(view=name, file=path.name, eye_m=eye, target_m=target))
    cache.Clear()
    final = np.array(cache.GetLocalToWorldTransform(stage.GetPrimAtPath('/World/VesselPreview')))[3, :3]
    result = dict(version='V0_demo02', status='STATIC_REVIEW_ONLY', scene=str(args.scene),
                  physical_episode_executed=False, workflow_success=False,
                  scene_correspondence_accepted=False, native_pair_success=False,
                  real_calibrated=False, data_eligible=False, source_rack_present=False,
                  physics_clock_before_s=before, physics_clock_after_s=float(world.current_time),
                  preview_pose_displacement_m=float(np.linalg.norm(final-initial)),
                  world_reset_called=False, physics_steps_requested=0,
                  views=saved, wall_seconds=time.monotonic()-start,
                  limitation='rendering and USD composition verification only; no contacts, support, grasp, release or retreat validation')
    (args.output/'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    print('STATIC_REVIEW_SAVED', args.output, flush=True)
    if not args.headless:
        while app.is_running():
            world.render()
    return result
