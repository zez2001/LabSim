"""Native LabUtopia task launcher shared by teacher and public policy backends."""
from __future__ import annotations
import argparse
import fcntl
import json
from pathlib import Path
import sys
import time
from omegaconf import OmegaConf
from demos.lab_cuvette_project_v1.runtime import ROOT, resolve_config, usd_environment


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config', type=Path, default=ROOT / 'config/lab_cuvette_loading/Project_v1/standard.yaml')
    p.add_argument('--backend', choices=('teacher', 'gpt6', 'rpc'), default='teacher')
    p.add_argument('--port', type=int, default=8097)
    p.add_argument('--layout-mode', '--scene', dest='scene', choices=('standard',), default='standard')
    p.add_argument('--task', choices=('lab_cuvette_loading',), default='lab_cuvette_loading')
    p.add_argument('--episodes', type=int, default=1)
    p.add_argument('--seed', type=int, default=0)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--headless', action='store_true')
    p.add_argument('--gui', action='store_true')
    p.add_argument('--controlled-stop-depth-mm', type=float)
    p.add_argument('--provider-config', type=Path, default=ROOT / 'config/lab_cuvette_loading/Project_v1/policies/cubence_gpt6.json')
    p.add_argument('--budget-ledger', type=Path)
    p.add_argument('--max-calls', type=int, default=160)
    p.add_argument('--audit-only', action='store_true')
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
    cfg = resolve_config(OmegaConf.load(args.config))
    if args.controlled_stop_depth_mm is not None:
        depth = args.controlled_stop_depth_mm / 1000
        if not 0 < depth < cfg.geometry.target_depth_m:
            raise ValueError('Controlled stop depth must be within original seat insertion depth')
        cfg.experiment.condition_group = 'deterministic_action_deviation'
        cfg.experiment.deviation = dict(stage='INSERT', value=depth, unit='m',
            stop_insertion_at_depth_m=depth, controller_version=cfg.experiment.controller_version,
            method='normal teacher action stops before support/release; no scenario change')
    OmegaConf.save(cfg, output / 'launch_config.yaml')
    audit = ensure_audit(cfg, output)
    (output / 'geometry_audit.json').write_text(json.dumps(audit, indent=2) + '\n')
    if args.audit_only:
        return 0 if audit.get('geometry_valid') is True else 2
    if audit.get('geometry_valid') is not True:
        raise RuntimeError('Current asset geometry precheck did not pass; no physical task started')
    lock = open('/tmp/labsim-V0_ext01-gpu.lock', 'a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    import os
    os.environ['OMNI_KIT_ACCEPT_EULA'] = 'YES'
    from isaacsim import SimulationApp
    extra = ['--/app/extensions/fsWatcherEnabled=false', '--/app/hydraEngine/waitIdle=true',
             '--/app/updateOrder/checkForHydraRenderComplete=1000']
    app = SimulationApp(dict(headless=args.headless, width=1280, height=720, extra_args=extra))
    env = None
    results = []
    wall = time.perf_counter()
    try:
        from factories.task_factory import create_task
        from factories.controller_factory import create_controller
        from demos.lab_cuvette_project_v1.environment import ProjectEnvironment
        env = create_task(cfg.task_type, cfg, app, output, geometry_audit=audit)
        facade = ProjectEnvironment(env)
        if args.backend == 'rpc':
            from demos.lab_cuvette_project_v1.rpc import serve_environment
            serve_environment(facade, port=args.port, ready_path=output / 'rpc_ready.json')
            return 0
        client = None
        if args.backend == 'gpt6':
            from policy.backends.cubence import CubenceClient, BudgetLedger, load_config
            provider = load_config(args.provider_config)
            ledger = args.budget_ledger or (output.parent / 'cubence_budget_ledger.json')
            client = CubenceClient(provider, BudgetLedger(ledger, provider))
        for index in range(args.episodes):
            facade.reset(args.seed + index, dict(mode='standard', teacher=args.backend == 'teacher',
                policy_id='truth_teacher' if args.backend == 'teacher' else 'cubence_gpt6_astra',
                demonstrator_id='LabCuvetteTeacher' if args.backend == 'teacher' else 'CubenceGenericTools'))
            if args.backend == 'teacher':
                teacher = create_controller(cfg.controller_type, env.cfg, env.ctx['fixtures'])
                teacher.reset(env.get_observation(), env.get_debug_observation())
                while app.is_running() and not env.ended:
                    action = teacher.act(env.get_observation(), env.get_debug_observation())
                    if teacher.finished:
                        env.finalize_episode(teacher.status, None if teacher.status.endswith('_COMPLETE') else teacher.status)
                        break
                    env.step(action)
                    if env.control_steps % 600 == 0:
                        print('PROJECT_PROGRESS', index, round(env.t, 3), env.phase, flush=True)
                env._write(env.episode_dir / 'teacher_events.json', teacher.events)
            else:
                from policy.backends.cubence_tools import run_episode
                run_episode(facade, client, env.episode_dir / 'gpt_control', max_calls=args.max_calls)
            if not env.ended:
                env.finalize_episode('APPLICATION_INTERRUPTED', 'PROCESS_INTERRUPTED')
            results.append(env._result)
            env._write(output / 'summary.json', results)
            print('PROJECT_RESULT', json.dumps(env._result, default=str), flush=True)
        env._write(output / 'run_manifest.json', dict(schema='labsim.Project_v1.run.v1',
            backend=args.backend, episodes_requested=args.episodes, episodes_completed=len(results),
            wall_seconds=time.perf_counter() - wall, physics_hz=int(cfg.physics.hz),
            control_hz=int(cfg.physics.control_hz), sequential_single_gpu=True,
            teacher_object_truth=args.backend == 'teacher', physics_paused_during_provider_requests=True,
            project_scene_fingerprint=env.release_contract['frozen_scene_sha256']))
        return 0
    finally:
        if env is not None:
            env.close()
        from omni.kit.app import get_app
        get_app().post_quit(0)
        app.close()
        lock.close()


if __name__ == '__main__':
    raise SystemExit(main())
