"""Repository task pipeline for the independent Franka/beaker scene."""
import argparse
import json
from pathlib import Path
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "packages/openpi-client/src"))


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "config/minimal_pick.yaml")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--no-video", action="store_true")
    parser.add_argument("--episodes", type=int)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--replay", type=Path)
    parser.add_argument("--episode", default="episode_0000")
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--timeout-seconds", type=float)
    parser.add_argument("--keep-open", action="store_true")
    args = parser.parse_args()
    if args.replay and args.checkpoint:
        parser.error("Choose either --replay or --checkpoint")
    if args.episodes is not None and args.episodes < 1:
        parser.error("--episodes must be positive")
    if args.timeout_seconds is not None and args.timeout_seconds <= 0:
        parser.error("--timeout-seconds must be positive")
    return args


def run(args, app):
    from datetime import datetime
    from omegaconf import OmegaConf
    from factories.task_factory import create_task
    from factories.controller_factory import create_controller
    from factories.collector_factory import create_collector
    cfg = OmegaConf.load(args.config)
    OmegaConf.register_new_resolver("now", lambda fmt: datetime.now().strftime(fmt), replace=True)
    if args.episodes is not None:
        cfg.max_episodes = args.episodes
    if args.timeout_seconds is not None:
        cfg.task.timeout_seconds = args.timeout_seconds
    if cfg.max_episodes < 1 or cfg.task.timeout_seconds <= 0:
        raise ValueError("Episode count and timeout must be positive")
    if args.replay or args.checkpoint:
        cfg.mode = "infer"
        cfg.infer.type = "replay" if args.replay else "local"
        cfg.infer.replay_data_path = str(args.replay.resolve()) if args.replay else None
        cfg.infer.policy_model_path = str(args.checkpoint.resolve()) if args.checkpoint else None
        cfg.infer.episode = args.episode
    output = (args.output or ROOT / cfg.multi_run.run_dir).resolve()
    # Prevent accidental overwrite of a dataset/video from a previous run.
    output.mkdir(parents=True, exist_ok=False)
    cfg.multi_run.run_dir = str(output)
    OmegaConf.save(cfg, output / "config.yaml", resolve=True)
    task = create_task(cfg.task_type, cfg=cfg)
    recorder = create_collector(cfg.collector.type, cfg=cfg, output_dir=output, save_video=not args.no_video)
    results = []
    last_action = None
    try:
        for index in range(cfg.max_episodes):
            task.reset()
            task.stage.Flatten().Export(str(output / "initial_scene.usda"))
            controller = create_controller(cfg.controller_type, cfg=cfg, robot=task.robot, task=task) if index == 0 else controller
            controller.reset()
            recorder.begin_episode(index, task.initial_position)
            state = task.step()
            started = time.monotonic()
            while task.status == "RUNNING":
                if not app.is_running():
                    task.status, task.reason = "FAIL", "window_closed"
                    break
                if time.monotonic() - started > max(180., cfg.task.timeout_seconds * 30):
                    task.status, task.reason = "TIMEOUT", "wall_clock_watchdog"
                    break
                if not task.world.is_playing():
                    app.update()
                    continue
                last_action, _, _ = controller.step(state)
                task.advance(last_action)
                next_state = task.step()
                result = task.result()
                recorder.cache_transition(state, last_action, next_state, result)
                state = next_state
                if task.frame_idx % 120 == 0:
                    print(f"STATE episode={index} t={task.elapsed:.2f} lift={task.max_lift:.4f} "
                          f"held={task.held:.3f}", flush=True)
            result = task.result()
            recorder.finish_episode(result)
            results.append(result)
            controller._episode_num += 1
            task.on_task_complete(result["status"] == "SUCCESS")
            print(result["status"] + " " + json.dumps(result), flush=True)
            controller.close()
        dataset, successes = recorder.merge()
        summary = dict(mode=cfg.mode, inference_type=cfg.infer.type if cfg.mode == "infer" else "expert",
                       successes=successes, episodes=len(results), dataset=str(dataset), results=results)
        (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
        print("PIPELINE_SAVED " + str(output), flush=True)
        if args.keep_open and not args.headless:
            while app.is_running():
                if task.world.is_playing() and last_action is not None:
                    task.world.step(render=True)
                else:
                    app.update()
        return 0 if successes == len(results) else (124 if any(r["status"] == "TIMEOUT" for r in results) else 1)
    finally:
        recorder.close()


def main(args=None):
    args = args or arguments()
    from isaacsim import SimulationApp
    app = SimulationApp(dict(headless=args.headless, width=1280, height=720))
    code = 1
    try:
        code = run(args, app)
    except KeyboardInterrupt:
        code = 130
        print("FAIL interrupted", flush=True)
    except Exception:
        traceback.print_exc()
        print("FAIL pipeline_error", flush=True)
    finally:
        from omni.kit.app import get_app
        get_app().post_quit(code)
        app.close(skip_cleanup=False)
    return code


if __name__ == "__main__":
    sys.exit(main())
