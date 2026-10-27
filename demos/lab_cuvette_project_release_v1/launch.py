"""Official release demo/collect/eval/RPC launcher over the validated v1.1 physics."""
from __future__ import annotations
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from omegaconf import OmegaConf
from demos.lab_cuvette_project_v1.runtime import ROOT, resolve_config, usd_environment


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config', type=Path, default=ROOT / 'config/lab_cuvette_loading/Project_release_v1/standard.yaml')
    p.add_argument('--backend', choices=('teacher', 'gpt6', 'rpc'), default='teacher')
    p.add_argument('--port', type=int, default=8097)
    p.add_argument('--layout-mode', '--scene', dest='scene', choices=('standard',), default='standard')
    p.add_argument('--task', choices=('lab_cuvette_loading',), default='lab_cuvette_loading')
    p.add_argument('--episodes', type=int, default=1)
    p.add_argument('--asset-id', help='Registered XY-size hypothesis; original seat and loading axis stay unchanged')
    p.add_argument('--execution-purpose', choices=('demo', 'eval', 'collect'), default='eval')
    p.add_argument('--seed', type=int, default=0)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--headless', action='store_true')
    p.add_argument('--gui', action='store_true')
    p.add_argument('--controlled-stop-depth-mm', type=float)
    p.add_argument('--provider-config', type=Path, default=ROOT / 'config/lab_cuvette_loading/Project_v1_1/policies/cubence_gpt6.json')
    p.add_argument('--budget-ledger', type=Path, default=ROOT/'outputs/lab_cuvette_loading/Project_v1/cubence_budget.json',
                   help='Existing shared ledger; previous attempts remain charged to this budget')
    p.add_argument('--max-calls', type=int, default=160)
    p.add_argument('--audit-only', action='store_true')
    p.add_argument('--record-mode', choices=('collect', 'eval', 'diagnostic'), default=None,
                   help='Persistence only; online safety/scoring sample rates are unchanged')
    return p


def ensure_audit(cfg, output):
    import subprocess
    config = output / 'audit_input.yaml'
    OmegaConf.save(cfg, config)
    cache = ROOT / cfg.env.geometry_audit_cache
    subprocess.run([sys.executable, '-m', cfg.env.geometry_audit_module,
        '--config', str(config), '--output', str(cache), '--geometry-site', str(cfg.env.shapely_site)],
        cwd=ROOT, env=usd_environment(), check=True)
    latest = json.loads((cache / 'latest.json').read_text())
    return json.loads((cache / latest['audit_relative_path']).read_text())


def main(argv=None):
    args = parser().parse_args(argv)
    if args.episodes < 1 or args.episodes > 20:
        raise ValueError('episodes must be1..20; one sequential Isaac process')
    if args.gui and args.headless:
        raise ValueError('Choose --gui or --headless')
    if args.controlled_stop_depth_mm is not None and args.backend != 'teacher':
        raise ValueError('Controlled early-stop is an explicitly separate teacher condition')
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    cfg = resolve_config(OmegaConf.load(args.config), asset_id=args.asset_id)
    cfg.env.execution_purpose = args.execution_purpose
    if cfg.version != 'Project_release_v1':
        raise ValueError('Release launcher requires the explicit Project_release_v1 configuration')
    if args.asset_id is not None and args.asset_id != 'cuvette_xy_1000':
        raise ValueError('This release freezes cuvette_xy_1000; use a separate version for another asset')
    cfg.release.record_mode = args.record_mode or ('collect' if args.execution_purpose == 'collect' else 'eval')
    cfg.experiment.truth_teacher = args.backend == 'teacher'
    if args.execution_purpose == 'collect' and cfg.asset_id != 'cuvette_xy_1000':
        raise ValueError('Fixed Project_v1 collection retains cuvette_xy_1000; use an independent demo/eval configuration for another registered asset')
    if args.controlled_stop_depth_mm is not None:
        depth = args.controlled_stop_depth_mm / 1000
        if not 0 < depth < cfg.geometry.target_depth_m:
            raise ValueError('Controlled stop depth must be within original seat insertion depth')
        cfg.experiment.condition_group = 'deterministic_action_deviation'
        cfg.experiment.deviation = dict(stage='INSERT', value=depth, unit='m',
            stop_insertion_at_depth_m=depth, controller_version=cfg.experiment.controller_version,
            method='normal teacher action stops before support/release; no scenario change')
    OmegaConf.save(cfg, output / 'launch_config.yaml')
    from demos.lab_cuvette_project_v1.assets import load_lock
    asset_lock = load_lock()
    identity = dict(process_id=os.getpid(),
        code_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        source_config_sha256=hashlib.sha256(args.config.read_bytes()).hexdigest(),
        resolved_config_sha256=hashlib.sha256((output / 'launch_config.yaml').read_bytes()).hexdigest(),
        asset_revision=asset_lock['revision'], version=cfg.version, record_mode=cfg.release.record_mode)
    (output / 'launch_identity.json').write_text(json.dumps(identity, indent=2) + '\n')
    audit = ensure_audit(cfg, output)
    (output / 'geometry_audit.json').write_text(json.dumps(audit, indent=2) + '\n')
    if args.audit_only:
        return 0 if audit.get('geometry_valid') is True else 2
    if audit.get('geometry_valid') is not True:
        raise RuntimeError('Current asset geometry precheck did not pass; no physical task started')
    lock = open('/tmp/labsim-V0_ext01-gpu.lock', 'a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    os.environ['OMNI_KIT_ACCEPT_EULA'] = 'YES'
    app_start = time.perf_counter()
    from isaacsim import SimulationApp
    extra = ['--/app/extensions/fsWatcherEnabled=false', '--/app/hydraEngine/waitIdle=true',
             '--/app/updateOrder/checkForHydraRenderComplete=1000']
    app = SimulationApp(dict(headless=args.headless, width=1280, height=720, extra_args=extra, fast_shutdown=False))
    startup_seconds = time.perf_counter() - app_start
    env = None
    results = []
    wall = time.perf_counter()
    try:
        from factories.task_factory import create_task
        from factories.controller_factory import create_controller
        from demos.lab_cuvette_project_release_v1.environment import ProjectEnvironment
        env = create_task(cfg.task_type, cfg, app, output, geometry_audit=audit)
        facade = ProjectEnvironment(env)
        print('LABSIM_RELEASE', json.dumps(dict(version=cfg.version, task=cfg.task_type,
            config=str(args.config.resolve()), backend=args.backend, record_mode=cfg.release.record_mode,
            controller=cfg.controller_type, scorer=cfg.env.scorer_module, asset_id=cfg.asset_id,
            asset_revision=asset_lock['revision'],
            physics_hz=int(cfg.physics.hz), control_hz=int(cfg.physics.control_hz))), flush=True)
        if args.backend == 'rpc':
            from demos.lab_cuvette_project_release_v1.rpc import serve_environment
            serve_environment(facade, port=args.port, ready_path=output / 'rpc_ready.json')
            env._write(output / 'run_manifest.json', dict(identity,
                schema='labsim.Project_release_v1.run.v1', backend='rpc',
                physics_hz=int(cfg.physics.hz), control_hz=int(cfg.physics.control_hz),
                wall_seconds=time.perf_counter() - wall, startup_seconds=startup_seconds,
                cleanup_state='RPC server and environment closed; process exit checked externally',
                episodes_completed=int(getattr(env, 'episode_index', -1)) + 1,
                sequential_single_gpu=True, teacher_object_truth=False,
                physics_paused_during_provider_requests=True))
            return 0
        client = None
        if args.backend == 'gpt6':
            from policy.backends.cubence import CubenceClient, BudgetLedger, load_config
            provider = load_config(args.provider_config)
            ledger = args.budget_ledger
            client = CubenceClient(provider, BudgetLedger(ledger, provider))
        for index in range(args.episodes):
            facade.reset(args.seed + index, dict(mode='standard', teacher=args.backend == 'teacher',
                policy_id='truth_teacher' if args.backend == 'teacher' else 'cubence_gpt6_astra',
                demonstrator_id='LabCuvetteTeacher' if args.backend == 'teacher' else 'CubenceGenericTools'))
            if args.backend == 'teacher':
                teacher = create_controller(cfg.controller_type, env.cfg, env.ctx['fixtures'])
                teacher.reset(env.get_observation(), env.get_debug_observation())
                from demos.lab_cuvette_project_v1_1.camera_audit import TeacherCameraAudit
                camera_qa=TeacherCameraAudit(env.episode_dir/'teacher_camera_audit')
                camera_qa.capture_if_phase_changed(facade,'RESET')
                while app.is_running() and not env.ended:
                    action = teacher.act(env.get_observation(), env.get_debug_observation())
                    if teacher.finished:
                        env.finalize_episode(teacher.status, None if teacher.status.endswith('_COMPLETE') else teacher.status)
                        break
                    env.step(action)
                    camera_qa.capture_if_phase_changed(facade,teacher.phase)
                    if env.control_steps % 600 == 0:
                        print('PROJECT_PROGRESS', index, round(env.t, 3), env.phase, flush=True)
                camera_qa.capture(facade,teacher.phase,event='terminal')
                env._write(env.episode_dir / 'teacher_events.json', teacher.events)
            else:
                from policy.backends.cubence_project_v1_1_tools import run_episode
                run_episode(facade, client, env.episode_dir / 'gpt_control', max_calls=args.max_calls)
            if not env.ended:
                env.finalize_episode('APPLICATION_INTERRUPTED', 'PROCESS_INTERRUPTED')
            results.append(env._result)
            env._write(output / 'summary.json', results)
            print('PROJECT_RESULT', json.dumps(env._result, default=str), flush=True)
        env._write(output / 'run_manifest.json', dict(identity, schema='labsim.Project_release_v1.run.v1',
            startup_seconds=startup_seconds,
            backend=args.backend, episodes_requested=args.episodes, episodes_completed=len(results),
            wall_seconds=time.perf_counter() - wall, physics_hz=int(cfg.physics.hz),
            control_hz=int(cfg.physics.control_hz), sequential_single_gpu=True,
            teacher_object_truth=args.backend == 'teacher', physics_paused_during_provider_requests=True,
            project_scene_fingerprint=env.release_contract['frozen_scene_sha256']))
        return 0
    except BaseException as error:
        import traceback
        if env is not None and not env.ended:
            try:
                env.finalize_episode('USER_INTERRUPTED' if isinstance(error, KeyboardInterrupt) else 'RUNNER_EXCEPTION',
                    'PROCESS_INTERRUPTED' if isinstance(error, KeyboardInterrupt) else 'EXECUTOR_FAILURE')
            except BaseException:
                pass
        (output/'runner_failure.json').write_text(json.dumps(dict(type=type(error).__name__,error=str(error),traceback=traceback.format_exc()),indent=2)+'\n')
        raise
    finally:
        try:
            from demos.lab_cuvette_project_release_v1.shutdown import close_release_application
            close_release_application(app, environment=env, report_path=output / 'application_shutdown.json')
        finally:
            lock.close()


if __name__ == '__main__':
    # Isaac5.1 extension teardown can leave Python finalizers pointing into
    # unloaded native modules. Writers and app have already closed in main;
    # leave without running those finalizers a second time. Preserve failures
    # rather than the toolkit fastShutdown path's unconditional zero exit.
    import os
    try:
        code=main()
    except SystemExit as error:
        code=int(error.code or 0)
    except BaseException:
        import traceback
        traceback.print_exc()
        code=1
    sys.stdout.flush();sys.stderr.flush()
    os._exit(code)
