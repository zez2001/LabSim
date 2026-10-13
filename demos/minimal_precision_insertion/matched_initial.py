"""Compare physics frequencies from the same measured held-body initial state.

Only initialization differs from run.py. Its controller, timing, sensors,
geometry, recorder and outcome criteria are unchanged. No pose writes follow
initialization. This experiment isolates a frequency comparison from the
frequency-dependent one-second grasp initialization used in the full scan.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import run as runner


def main():
    selector=argparse.ArgumentParser(add_help=False)
    selector.add_argument('--reference',type=Path,required=True)
    extra,remaining=selector.parse_known_args()
    sys.argv=[sys.argv[0]]+remaining
    args=runner.arguments()
    if args.output is None:
        raise ValueError('Specify a new --output for the matched-state experiment')
    args.output=args.output.resolve()
    reference=extra.reference.resolve()
    ref=json.loads(reference.read_text())
    if args.diagnostic:
        raise ValueError('Matched initialization is for insertion comparisons')
    if ',' in args.physics_hz:
        args.output.mkdir(parents=True,exist_ok=False)
        combined=[];timing=[];codes=[]
        for hz in args.physics_hz.split(','):
            command=[sys.executable,str(Path(__file__).resolve()),'--reference',str(reference),
                '--config',str(args.config),'--output',str(args.output/f'hz_{hz}'),
                '--physics-hz',hz,'--offsets',args.offsets,'--repeats',str(args.repeats)]
            for name in ('headless','no_video'):
                if getattr(args,name):command.append('--'+name.replace('_','-'))
            for name in ('contact_offset_mm','position_iterations','tube_segments'):
                if getattr(args,name) is not None:
                    command.extend(['--'+name.replace('_','-'),str(getattr(args,name))])
            start=time.monotonic()
            with (args.output/f'hz_{hz}.log').open('w') as log:
                code=subprocess.run(command,cwd=runner.ROOT,stdout=log,stderr=subprocess.STDOUT).returncode
            codes.append(code);timing.append(dict(physics_hz=int(hz),process_wall_seconds=time.monotonic()-start,exit=code))
            summary=args.output/f'hz_{hz}'/'summary.json'
            if summary.exists():combined.extend(json.loads(summary.read_text()))
            print('MATCHED_CONFIGURATION_FINISHED',hz,code,flush=True)
        runner.jsonwrite(args.output/'summary.json',combined)
        runner.jsonwrite(args.output/'process_timing.json',timing)
        return 0 if all(c==0 for c in codes) else 1
    from isaacsim import SimulationApp
    app=SimulationApp(dict(headless=args.headless,width=1280,height=720,
        extra_args=['--/app/extensions/fsWatcherEnabled=false']))
    code=1
    try:
        import numpy as np
        from isaacsim.core.utils.types import ArticulationAction
        from tasks.minimal_precision_insertion_task import MinimalPrecisionInsertionTask
        original_reset=MinimalPrecisionInsertionTask.reset

        def matched_reset(task,offset_mm=0.):
            # Reuse the original setup/bookkeeping, then discard its warm-up
            # state with a fresh physics reset before writing the shared seed.
            original_reset(task,offset_mm)
            task.world.reset()
            q=np.array(ref['joints'])
            task.robot.set_joint_positions(q);task.robot.set_joint_velocities(np.zeros(9))
            task.tube.set_world_pose(np.array(ref['state']['position']),np.array(ref['state']['orientation']))
            task.tube.set_linear_velocity(np.zeros(3));task.tube.set_angular_velocity(np.zeros(3))
            for contact in (task.scene['fingers'],task.scene['contacts']):contact.initialize()
            for camera in task.cameras.values():camera.initialize()
            target=q.copy();target[7:]=0.
            task.robot.get_articulation_controller().apply_action(ArticulationAction(joint_positions=target))
            # Rendering synchronizes observation buffers without a physical step.
            for _ in range(6):task.world.render()
            from demos.minimal_precision_insertion.scene import tcp_pose
            task.initial_position=task.tube.get_world_pose()[0].copy()
            task.initial_tcp=tcp_pose(task.scene['hand'])[0].copy()
            task.initial_relative=task.initial_position-task.initial_tcp
            task.clock_origin=task.world.current_time
            task.last_metrics=task.measure();task.initial_state=task.snapshot_state(task.last_metrics)
            error=np.linalg.norm(task.initial_position-np.array(ref['state']['position']))
            tcp_error=np.linalg.norm(task.initial_tcp-np.array(ref['state']['tcp']))
            if max(error,tcp_error)>1e-6:
                raise RuntimeError(f'Matched initial pose failed the 1 um gate: body={error},tcp={tcp_error}')
            runner.jsonwrite(args.output/f'physics_{args.physics_hz}'/'matching_protocol.json',dict(
                reference_file=str(reference),reference_sha256=hashlib.sha256(reference.read_bytes()).hexdigest(),
                reference_state=ref,body_error_m=float(error),tcp_error_m=float(tcp_error),
                robot_joint_velocity_rad_s=[0.]*9,tube_linear_velocity_m_s=[0.]*3,tube_angular_velocity_rad_s=[0.]*3,
                initial_physical_steps=0,initialization_only=True,
                limitation='Matches measured poses, joints and zero velocities; internal solver cache is not serialized.'))

        MinimalPrecisionInsertionTask.reset=matched_reset
        code=runner.run(args,app)
    except Exception:
        import traceback
        traceback.print_exc();print('CONTROL_OR_IK_FAILURE matched_initializer_exception',flush=True)
    finally:
        from omni.kit.app import get_app
        get_app().post_quit(code);app.close()
    return code


if __name__=='__main__':
    sys.exit(main())
