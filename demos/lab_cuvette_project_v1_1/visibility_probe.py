"""Render-only camera comparison from explicitly marked closed-run states.

This initializes robot and vessel poses for visual diagnosis only. It is not a
task rollout, policy input, replay success or physical contact validation.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--states', type=Path, required=True)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    states = json.loads(args.states.read_text())
    if states.get('schema') != 'labsim.Project_v1_1.render_reconstruction_states.v1':
        raise ValueError('Use explicitly marked render-only closed-state evidence')
    if not states.get('states') or len(states['states']) > 10:
        raise ValueError('Expected1..10 closed reconstruction states')
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    lock = open('/tmp/labsim-V0_ext01-gpu.lock', 'a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    os.environ['OMNI_KIT_ACCEPT_EULA'] = 'YES'
    from isaacsim import SimulationApp
    app = SimulationApp(dict(headless=True, fast_shutdown=False,
        extra_args=['--/app/extensions/fsWatcherEnabled=false', '--/app/hydraEngine/waitIdle=true']))
    ctx = rig = None
    try:
        import numpy as np
        from PIL import Image
        from pxr import UsdGeom
        import omni.physx
        from omegaconf import OmegaConf
        from demos.lab_cuvette_project_v1.runtime import resolve_config
        from demos.lab_cuvette_env_v1.scene import build_context
        from demos.lab_cuvette_env_v1.cameras import create_cameras, look_at_usd

        cfg = resolve_config(OmegaConf.load(args.config))
        ctx = build_context(cfg, app, output)
        world = ctx['world']
        pc = world.get_physics_context()
        pc.enable_fabric(False)
        pc.set_physx_update_transformations_settings(update_to_usd=True,
            update_velocities_to_usd=True, output_velocities_local_space=False)
        rig = create_cameras(ctx, cfg)
        # Sensor warmup precedes reconstruction; these are not task samples.
        world.step(render=False)
        for _ in range(8):
            world.render()
        profiles = dict(original=dict(eye_m=list(cfg.cameras.side_camera.eye_m),
                            target_m=list(cfg.cameras.side_camera.target_m), focal_length_cm=float(cfg.cameras.side_camera.focal_length_cm)),
            lower_oblique=dict(eye_m=[-.70, -.85, 1.32], target_m=[.10, -.10, .98], focal_length_cm=2.),
            lower_front=dict(eye_m=[-.45, -1.05, 1.27], target_m=[.10, -.10, .98], focal_length_cm=2.),
            lower_wide=dict(eye_m=[-.70, -.85, 1.32], target_m=[.10, -.10, 1.05], focal_length_cm=1.7))
        records = []
        for index, state in enumerate(states['states']):
            q = np.asarray(state['joint_positions'], float)
            p = np.asarray(state['object_position_m'], float)
            r = np.asarray(state['object_quaternion_wxyz'], float)
            if q.shape != (9,) or p.shape != (3,) or r.shape != (4,) or not np.isfinite(np.r_[q,p,r]).all() or abs(np.linalg.norm(r)-1) > .001:
                raise ValueError('Invalid reconstructed state; no replacement or zero filling')
            ctx['robot'].set_joint_positions(q)
            world.physics_sim_view.update_articulations_kinematic()
            ctx['cup'].set_world_pose(p,r)
            ctx['cup'].set_linear_velocity(np.zeros(3))
            ctx['cup'].set_angular_velocity(np.zeros(3))
            # Native pose setters do not themselves guarantee renderer USD
            # writeback without another physical step. Explicitly synchronize
            # transforms without integrating the reconstructed state.
            omni.physx.get_physx_interface().update_transformations(False, True, True, False)
            cup_usd = np.asarray(UsdGeom.Xformable(ctx['stage'].GetPrimAtPath('/World/Cuvette')).ComputeLocalToWorldTransform(0.).ExtractTranslation(),float)
            if np.linalg.norm(cup_usd-p) > 1e-6:
                raise RuntimeError('Reconstructed native and rendered vessel transforms disagree')
            for name, profile in profiles.items():
                folder = output / f'state_{index:02d}' / name
                folder.mkdir(parents=True)
                rig.specifications['side_camera'].update(profile)
                _, quat = look_at_usd(profile['eye_m'], profile['target_m'], [0.,0.,1.])
                rig.cameras['side_camera'].set_world_pose(np.asarray(profile['eye_m']),quat,camera_axes='usd')
                rig.cameras['side_camera'].set_focal_length(profile['focal_length_cm'])
                for _ in range(6):
                    world.render()
                pictures = rig.get_images()
                meta = {camera:rig.get_meta(camera) for camera in rig.names}
                for camera, picture in pictures.items():
                    Image.fromarray(picture).save(folder/(camera+'.png'))
                (folder/'cameras.json').write_text(json.dumps(meta,indent=2)+'\n')
                records.append(dict(state_index=index,state_id=state['id'],profile=name,
                    directory=str(folder.relative_to(output)),api_sent=False,policy_actions=0,
                    physics_steps_after_pose_initialization=0,
                    measured_robot_q9=ctx['robot'].get_joint_positions().tolist(),
                    measured_vessel_position_m=ctx['cup'].get_world_pose()[0].tolist(),
                    rendered_vessel_position_m=cup_usd.tolist(),
                    USD_transform_writeback='IPhysx.update_transformations(False,True,True,False); no integration',
                    original_state_source=state))
                print('RENDER_ONLY',index,name,flush=True)
        manifest = dict(schema='labsim.Project_v1_1.render_visibility_comparison.v1',
            evidence_kind='render_only_reconstructed_closed_states', api_sent=False,
            physical_task_executed=False, scores_assigned=False, no_GT_crop=True,
            source_states=str(args.states), source_states_sha256=hashlib.sha256(args.states.read_bytes()).hexdigest(),
            profiles=profiles, snapshots=records,
            limitation='Pose initialization for visibility comparison only; not a physical trajectory or actual model input.')
        (output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
        return 0
    finally:
        if rig is not None:
            rig.close()
        if ctx is not None:
            ctx['world'].stop()
            ctx['world'].clear()
        try:
            from omni.kit.app import get_app
            get_app().post_quit(0)
            app.close()
        finally:
            lock.close()


if __name__ == '__main__':
    try:
        code = main()
    except BaseException:
        import traceback
        traceback.print_exc()
        code = 1
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(code)
