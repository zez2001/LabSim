import os
import argparse
from isaacsim import SimulationApp

# Parse command line arguments
def parse_args():
    parser = argparse.ArgumentParser(description='LabSim Simulation Environment')
    parser.add_argument('--backend', type=str, default='numpy', 
                       choices=['numpy', 'gpu'], 
                       help='Backend choice: numpy (CPU) or gpu')
    parser.add_argument('--headless', action='store_true', 
                       help='Run in headless mode (default is with GUI)')
    parser.add_argument('--no-video', action='store_true', 
                       help='Disable video display and saving')
    parser.add_argument('--config-name', type=str, default='level3_Heat_Liquid',
                       help='Configuration file name (without .yaml extension)')
    parser.add_argument('--config-dir', type=str, default='config',
                       help='Configuration directory path (default: config)')
    parser.add_argument('--env-mode',choices=['teacher','preview','serve','audit','plan'],default='teacher')
    parser.add_argument('--env-config',type=str,default='config/lab_cuvette_loading/Env_v1/native.yaml')
    parser.add_argument('--subtask',choices=['loading','preinsert_diagnostic','grasp_hold','extract_transport'])
    parser.add_argument('--layout-mode',choices=['standard','random'],default='standard')
    parser.add_argument('--seed',type=int,default=0)
    parser.add_argument('--episodes',type=int,default=1)
    parser.add_argument('--output',type=str)
    parser.add_argument('--port',type=int,default=8097)
    parser.add_argument('--initial-state',type=str)
    return parser.parse_args()

# Get command line arguments
args = parse_args()

# Independent scenes use their own scene builder and the shared task registries.
# Existing laboratory configurations keep the original startup and run loop.
if args.config_name == 'lab_cuvette_env_v1':
    import sys
    from demos.lab_cuvette_env_v1.run import parser as env_parser,main as env_main
    env_args=env_parser().parse_args(['--config',args.env_config,'--mode',args.env_mode,'--layout-mode',args.layout_mode,'--seed',str(args.seed),'--episodes',str(args.episodes),'--port',str(args.port)]+(['--subtask',args.subtask] if args.subtask else [])+(['--headless'] if args.headless else [])+(['--output',args.output] if args.output else [])+(['--initial-state',args.initial_state] if args.initial_state else []))
    sys.exit(env_main(env_args))

if args.config_name == 'minimal_pick':
    import sys
    from pathlib import Path
    from demos.minimal_pick.pipeline import main as minimal_pick_main
    if args.backend != 'numpy':
        raise ValueError('minimal_pick currently uses the numpy physics backend')
    sys.exit(minimal_pick_main(argparse.Namespace(
        config=Path(args.config_dir) / 'minimal_pick.yaml', headless=args.headless,
        no_video=args.no_video, episodes=None, output=None, replay=None,
        episode='episode_0000', checkpoint=None, timeout_seconds=None, keep_open=False)))

if args.config_name == 'minimal_precision_insertion':
    import sys
    from pathlib import Path
    from demos.minimal_precision_insertion.run import run as precision_run
    if args.backend != 'numpy':
        raise ValueError('minimal_precision_insertion currently uses CPU PhysX with the numpy backend')
    precision_app = SimulationApp(dict(headless=args.headless, width=1280, height=720,
        extra_args=['--/app/extensions/fsWatcherEnabled=false']))
    precision_code = 1
    try:
        precision_code = precision_run(argparse.Namespace(
            config=Path(args.config_dir) / 'minimal_precision_insertion.yaml',
            headless=args.headless, no_video=args.no_video, output=None,
            offsets='0', physics_hz='120', repeats=1, diagnostic=False,
            contact_offset_mm=None, position_iterations=None, tube_segments=None), precision_app)
    except Exception:
        import traceback
        traceback.print_exc()
    finally:
        from omni.kit.app import get_app
        get_app().post_quit(precision_code)
        precision_app.close()
    sys.exit(precision_code)

if args.config_name == 'lab_cuvette_loading':
    import sys
    from demos.lab_cuvette_loading.run import main as cuvette_main
    if args.backend != 'numpy':
        raise ValueError('lab_cuvette_loading currently uses CPU PhysX')
    sys.argv = [sys.argv[0]] + (['--headless'] if args.headless else []) + (['--no-video'] if args.no_video else [])
    sys.exit(cuvette_main())

# Set up simulation app based on arguments
simulation_config = {
    "headless": False,
    "extra_args": ["--/rtx/raytracing/fractionalCutoutOpacity=true"],
}

simulation_app = SimulationApp(simulation_config)

import hydra
from omegaconf import OmegaConf
import cv2
import numpy as np

import omni
from isaacsim.core.api import World
from isaacsim.core.utils.stage import add_reference_to_stage
import omni.usd
from isaacsim.core.utils import extensions

extensions.enable_extension("omni.physx.bundle")
extensions.enable_extension("omni.usdphysics.ui")

from factories.robot_factory import create_robot
from utils.object_utils import ObjectUtils
from factories.task_factory import create_task
from factories.controller_factory import create_controller

def main():
    hydra.initialize(config_path=args.config_dir, job_name=args.config_name)
    cfg = hydra.compose(config_name=args.config_name)
    os.makedirs(cfg.multi_run.run_dir, exist_ok=True)
    OmegaConf.save(cfg, cfg.multi_run.run_dir + "/config.yaml")

    # Set backend based on command line arguments
    if args.backend == 'gpu':
        world = World(stage_units_in_meters=1, device="cpu")
        physx_interface = omni.physx.get_physx_interface()
        physx_interface.overwrite_gpu_setting(1)
    else:
        world = World(stage_units_in_meters=1.0, physics_prim_path="/physicsScene", backend="numpy")
    
    # Override configuration based on command line arguments
    if args.no_video:
        save_video = False
        show_video = False
    else:
        save_video = True
        show_video = True

    robot = create_robot(
        cfg.robot.type,
        position=np.array(cfg.robot.position)
    )
    
    stage = omni.usd.get_context().get_stage()
    add_reference_to_stage(usd_path=os.path.abspath(cfg.usd_path), prim_path="/World")
    
    ObjectUtils.get_instance(stage)
    
    task = create_task(
        cfg.task_type,
        cfg=cfg,
        world=world,
        stage=stage,
        robot=robot,
    )
    
    task_controller = create_controller(
        cfg.controller_type,
        cfg=cfg,
        robot=robot,
    )
    
    video_writer = None
    task.reset()
    
    while simulation_app.is_running():
        world.step(render=True)
        
        if world.is_stopped():
            task_controller.reset_needed = True
            
        if world.is_playing():
            if task_controller.need_reset() or task.need_reset():
                if video_writer is not None:
                    video_writer.release()
                    video_writer = None
                           
                task_controller.reset()
                if task_controller.episode_num() >= cfg.max_episodes:
                    task_controller.close()
                    simulation_app.close()
                    cv2.destroyAllWindows()
                    break
                task.reset()
                
                continue
                
            state = task.step()
            if state is None:
                continue
            
            action, done, is_success = task_controller.step(state)
            if action is not None:
                robot.get_articulation_controller().apply_action(action)
            if done:
                task_controller.print_failure_reason()
                task.on_task_complete(is_success)
                continue
            
            if save_video or show_video:
                camera_images = []
                for _, image_data in state['camera_display'].items():
                    display_img = cv2.cvtColor(image_data.transpose(1, 2, 0), cv2.COLOR_RGB2BGR)
                    camera_images.append(display_img)
                
                if camera_images:
                    combined_img = np.hstack(camera_images)
                    total_width = 0
                    for idx, img in enumerate(camera_images):
                        label = f"Camera {idx+1} ({cfg.cameras[idx].image_type})"
                        cv2.putText(combined_img, label, (total_width + 2, 20),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.25, (255, 255, 255), 1)
                        total_width += img.shape[1]
                    if show_video:
                        cv2.imshow('Camera Views', combined_img)
                        cv2.waitKey(1)
                    if save_video:
                        output_dir = os.path.join(cfg.multi_run.run_dir, "video")
                        os.makedirs(output_dir, exist_ok=True)
                        output_path = os.path.join(output_dir, f"episode_{task_controller._episode_num}.mp4")
                        if video_writer is None:
                            height, width = combined_img.shape[:2]
                            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
                            video_writer = cv2.VideoWriter(output_path, fourcc, 60.0, (width, height))
                        video_writer.write(combined_img)


if __name__ == "__main__":
    main()
