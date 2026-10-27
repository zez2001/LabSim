"""Sequential release acceptance in one Isaac process; no provider or training."""
from __future__ import annotations

import argparse
import fcntl
import json
import os
from pathlib import Path
import subprocess
import time

from omegaconf import OmegaConf

from demos.lab_cuvette_project_v1.runtime import ROOT, resolve_config
from demos.lab_cuvette_project_v1_1.run import ensure_audit

CONDITIONS = ('teacher', 'early_finish', 'no_progress', 'unreachable', 'service_timeout', 'user_interrupt')


def controlled_case(facade, condition, *, seconds=1.):
    """Real bounded physics plus explicitly labelled controlled failure paths."""
    task = facade.task
    hz = float(task.cfg.physics.control_hz)
    ticks = round(seconds * hz)
    start = int(task.control_steps)
    records = []
    while not task.ended and task.control_steps - start < ticks:
        observation = facade.observe()
        count = min(ticks - (task.control_steps - start), int(3 * hz))
        records.append(facade.execute(dict(action_id=f'{task.episode_id}:wait:{task.control_steps}',
            episode_id=task.episode_id, observation_id=observation['observation_id'],
            type='ee_delta', frame='world', values=[0.] * 6, duration_s=count / hz)))
    injected = False
    if condition == 'unreachable' and not task.ended:
        observation = facade.observe()
        values = list(observation['joint_positions'][:7])
        # A target beyond the declared robot joint limit is physically
        # unreachable. The actual public preplanner must reject it, not step.
        _, upper, _ = task.joint_bounds()
        values[0] = float(upper[0]) + 1.
        before = int(task.control_steps)
        receipt = facade.execute(dict(action_id=f'{task.episode_id}:unreachable',
            episode_id=task.episode_id, observation_id=observation['observation_id'],
            type='joint_position', values=values, duration_s=1.))
        records.append(receipt)
        if receipt['accepted'] or task.control_steps != before or receipt['stop_reason'] != 'JOINT_PLAN_REJECTED':
            raise RuntimeError('Unreachable preplan rejection contract violated')
        facade.finish('CONTROLLED_UNREACHABLE_REQUEST_END')
    elif condition == 'service_timeout':
        # Exercise the same finalization category as a real service timeout;
        # no network failure or model inference is claimed by this injection.
        try:
            raise TimeoutError('controlled model-service timeout injection')
        except TimeoutError:
            injected = True
            facade.finish('PROVIDER_TIMEOUT', failure_type='MODEL_SERVICE_ERROR')
    elif condition == 'user_interrupt':
        try:
            raise KeyboardInterrupt('controlled user-interruption path injection')
        except KeyboardInterrupt:
            injected = True
            facade.finish('USER_INTERRUPTED', failure_type='PROCESS_INTERRUPTED')
    elif condition == 'no_progress' and not task.ended:
        task.finalize_episode('CONTROLLED_NO_PROGRESS_LIMIT', 'TIMEOUT')
    elif condition == 'early_finish':
        facade.finish('CONTROLLED_EARLY_FINISH')
    first = facade.status()
    facade.finish('DUPLICATE_FINISH_MUST_NOT_RELABEL')
    second = facade.status()
    if first != second:
        raise RuntimeError('Repeated finish changed terminal status')
    evidence = dict(schema='labsim.Project_release_v1.controlled_termination.v1',
        condition=condition, controlled_fault_injection=injected,
        real_model_service_failure=False, actual_user_keyboard_action=False,
        declared_duration_s=seconds, control_steps_advanced=int(task.control_steps) - start,
        action_receipts=records, repeated_finish_preserved_status=True,
        terminal_status=second)
    task._write(task.episode_dir / 'controlled_termination.json', evidence)
    return evidence


def resources():
    status = {}
    try:
        for line in Path('/proc/self/status').read_text().splitlines():
            if line.startswith(('VmRSS:', 'VmHWM:')):
                key, value, _ = line.split()
                status[key[:-1] + '_bytes'] = int(value) * 1024
        status['file_descriptors'] = len(list(Path('/proc/self/fd').iterdir()))
    except OSError:
        pass
    try:
        result = subprocess.run(['nvidia-smi', '--query-compute-apps=pid,used_gpu_memory',
            '--format=csv,noheader,nounits'], capture_output=True, text=True, timeout=5)
        status['VRAM_MiB'] = sum(float(line.split(',')[1]) for line in result.stdout.splitlines()
                                  if line.split(',')[0].strip() == str(os.getpid()))
    except (OSError, ValueError, subprocess.TimeoutExpired):
        status['VRAM_MiB'] = None
    return dict(status, wall_monotonic_s=time.perf_counter(), pid=os.getpid())


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config', type=Path, default=ROOT / 'config/lab_cuvette_loading/Project_release_v1/standard.yaml')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--sequence', nargs='+', choices=CONDITIONS,
                   default=['teacher', 'early_finish', 'teacher'])
    p.add_argument('--early-finish-after-s', type=float, default=3.)
    p.add_argument('--no-progress-after-s', type=float, default=5.)
    p.add_argument('--seed', type=int, default=0)
    p.add_argument('--headless', action='store_true')
    p.add_argument('--gui', action='store_true')
    p.add_argument('--record-mode', choices=('diagnostic', 'collect', 'eval'), default=None)
    p.add_argument('--execution-purpose', choices=('demo', 'collect', 'eval'), default=None)
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    if args.gui and args.headless:
        raise ValueError('Choose --gui or --headless')
    if not 1 <= len(args.sequence) <= 20:
        raise ValueError('Sequence must contain 1..20 episodes')
    if not 1 <= args.early_finish_after_s <= 30 or not 1 <= args.no_progress_after_s <= 30:
        raise ValueError('Controlled diagnostic intervals must be 1..30 seconds')
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    cfg = resolve_config(OmegaConf.load(args.config))
    if cfg.version != 'Project_release_v1':
        raise ValueError('Use the explicit Project_release_v1 config')
    if args.record_mode is not None:
        cfg.release.record_mode = args.record_mode
    if args.execution_purpose is not None:
        cfg.env.execution_purpose = args.execution_purpose
    from demos.lab_cuvette_project_v1.assets import load_lock
    asset_revision = load_lock()['revision']
    print('LABSIM_RELEASE', json.dumps(dict(version=cfg.version, config=str(args.config.resolve()),
        execution_purpose=str(cfg.env.get('execution_purpose', 'eval')),
        record_mode=str(cfg.release.record_mode), sequence=args.sequence,
        controller=cfg.controller_type, scorer=cfg.env.scorer_module,
        asset_id=cfg.asset_id, asset_revision=asset_revision,
        physics_hz=int(cfg.physics.hz), control_hz=int(cfg.physics.control_hz))), flush=True)
    OmegaConf.save(cfg, output / 'launch_config.yaml')
    audit = ensure_audit(cfg, output)
    if audit.get('geometry_valid') is not True:
        raise RuntimeError('Geometry precheck failed; no physical episode started')
    lock = open('/tmp/labsim-V0_ext01-gpu.lock', 'a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    os.environ['OMNI_KIT_ACCEPT_EULA'] = 'YES'
    started = time.perf_counter()
    before_app = resources()
    from isaacsim import SimulationApp
    app = SimulationApp(dict(headless=args.headless, width=1280, height=720,
        extra_args=['--/app/extensions/fsWatcherEnabled=false', '--/app/hydraEngine/waitIdle=true',
                    '--/app/updateOrder/checkForHydraRenderComplete=1000'], fast_shutdown=False))
    startup_s = time.perf_counter() - started
    env = None
    results, snapshots, reset_checks = [], [dict(event='before_app', **before_app)], []
    try:
        from tasks.lab_cuvette_loading_project_release import LabCuvetteProjectRelease
        from demos.lab_cuvette_project_release_v1.environment import ProjectEnvironment
        from factories.controller_factory import create_controller
        env = LabCuvetteProjectRelease(cfg, app, output, geometry_audit=audit)
        facade = ProjectEnvironment(env)
        old_observation = None
        for index, condition in enumerate(args.sequence):
            reset_start = time.perf_counter()
            observation = facade.reset(args.seed, dict(mode='standard', teacher=condition == 'teacher',
                policy_id='truth_teacher' if condition == 'teacher' else 'controlled_' + condition,
                demonstrator_id='LabCuvetteTeacher' if condition == 'teacher' else 'lifecycle_acceptance',
                lifecycle_condition=condition))
            snapshot = dict(event='after_reset', episode=index, condition=condition, **resources())
            snapshots.append(snapshot)
            check = dict(episode=index, episode_id=observation['episode_id'],
                reset_wall_seconds=time.perf_counter() - reset_start,
                prior_episode_rejected=None, reset_simulation_time_s=observation['simulation_time'])
            if old_observation is not None:
                before = env.control_steps
                stale = dict(action_id=old_observation['episode_id'] + ':stale_probe',
                    episode_id=old_observation['episode_id'], observation_id=old_observation['observation_id'],
                    type='ee_delta', frame='world', values=[0.] * 6, duration_s=1 / cfg.physics.control_hz)
                try:
                    facade.execute(stale)
                except ValueError as error:
                    check.update(prior_episode_rejected=True, stale_error=str(error),
                                 stale_probe_executed_ticks=env.control_steps - before)
                else:
                    raise RuntimeError('An old-episode action was accepted after reset')
            reset_checks.append(check)
            rollout_start = time.perf_counter()
            if condition == 'teacher':
                teacher = create_controller(cfg.controller_type, env.cfg, env.ctx['fixtures'])
                teacher.reset(env.get_observation(), env.get_debug_observation())
                while app.is_running() and not env.ended:
                    action = teacher.act(env.get_observation(), env.get_debug_observation())
                    if teacher.finished:
                        env.finalize_episode(teacher.status, None if teacher.status.endswith('_COMPLETE') else teacher.status)
                        break
                    env.step(action)
                    if env.control_steps % 600 == 0:
                        snapshots.append(dict(event='rollout', episode=index, **resources()))
                        print('RELEASE_PROGRESS', index, round(env.t, 3), env.phase, flush=True)
                env._write(env.episode_dir / 'teacher_events.json', teacher.events)
            else:
                duration = (args.early_finish_after_s if condition == 'early_finish' else
                            args.no_progress_after_s if condition == 'no_progress' else 1.)
                controlled_case(facade, condition, seconds=duration)
            if not env.ended:
                facade.finish('APPLICATION_INTERRUPTED', failure_type='PROCESS_INTERRUPTED')
            old_observation = facade.observe()
            row = dict(episode_index=index, condition=condition, episode_id=env.episode_id,
                result=env._result, rollout_wall_seconds=time.perf_counter() - rollout_start,
                resources=resources())
            results.append(row)
            env._write(output / 'summary.json', results)
            env._write(output / 'resource_samples.json', snapshots)
            env._write(output / 'reset_checks.json', reset_checks)
            print('RELEASE_RESULT', json.dumps(row, default=str), flush=True)
        env._write(output / 'run_manifest.json', dict(schema='labsim.Project_release_v1.same_process.v1',
            process_id=os.getpid(), sequence=args.sequence, seed=args.seed, standard_randomization=False,
            record_mode=str(cfg.release.record_mode),
            execution_purpose=str(cfg.env.get('execution_purpose', 'eval')),
            asset_revision=asset_revision,
            episodes_requested=len(args.sequence), episodes_completed=len(results),
            all_episodes_same_process=True, startup_wall_seconds=startup_s,
            rollout_wall_seconds=sum(item['rollout_wall_seconds'] for item in results),
            wall_seconds=time.perf_counter() - started, resources_after_episodes=resources(),
            code_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()))
        return 0
    except BaseException as error:
        import traceback
        if env is not None and not env.ended:
            try:
                env.finalize_episode('USER_INTERRUPTED' if isinstance(error, KeyboardInterrupt) else 'RUNNER_EXCEPTION',
                    'PROCESS_INTERRUPTED' if isinstance(error, KeyboardInterrupt) else 'EXECUTOR_FAILURE')
            except BaseException:
                pass
        (output / 'runner_failure.json').write_text(json.dumps(dict(type=type(error).__name__,
            error=str(error), traceback=traceback.format_exc()), indent=2) + '\n')
        raise
    finally:
        try:
            from demos.lab_cuvette_project_release_v1.shutdown import close_release_application
            close_release_application(app, environment=env, report_path=output / 'application_shutdown.json')
        finally:
            lock.close()


if __name__ == '__main__':
    import sys
    try:
        code = main()
    except SystemExit as error:
        code = int(error.code or 0)
    except BaseException:
        import traceback
        traceback.print_exc()
        code = 1
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(code)
