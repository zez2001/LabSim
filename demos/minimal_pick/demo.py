"""One fixed-pose physical Franka grasp in a newly constructed USD stage."""
import argparse
import json
from pathlib import Path
import sys
import time
import traceback


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--exit-on-result", action="store_true")
    parser.add_argument("--timeout-seconds", type=float, default=30.0,
                        help="Task budget in simulation seconds, excluding startup.")
    parser.add_argument("--save-usd", type=Path)
    parser.add_argument("--result-json", type=Path)
    parser.add_argument("--screenshot", type=Path)
    args = parser.parse_args()
    if args.timeout_seconds <= 0:
        parser.error("--timeout-seconds must be positive")
    return args


def run(args, app):
    import numpy as np
    from pxr import UsdGeom
    from isaacsim.core.utils.types import ArticulationAction
    from isaacsim.core.utils.rotations import euler_angles_to_quat
    from scene import build_scene

    root = Path(__file__).resolve().parents[2]
    out = root / "outputs/minimal_pick"
    usd_path = (args.save_usd or out / "scene.usda").resolve()
    result_path = (args.result_json or out / "result.json").resolve()
    usd_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.parent.mkdir(parents=True, exist_ok=True)
    scene = build_scene()
    world, stage, robot, beaker = (scene[k] for k in ("world", "stage", "robot", "beaker"))
    body, contact_view, solver, viewport = (scene[k] for k in ("body", "contact_view", "solver", "viewport"))
    robot_base, dt = scene["robot_base"], scene["dt"]
    # Physics settling is initialization, before the task clock and success baseline.
    for _ in range(120):
        world.step(render=not args.headless)
    initial_position, _ = beaker.get_world_pose()
    initial_position = initial_position.copy()
    bbox = UsdGeom.BBoxCache(0, ["default", "render"]).ComputeWorldBound(body).ComputeAlignedRange()
    height = float(bbox.GetSize()[2])
    # Export the INITIAL settled scene; Flatten resolves both local USD references.
    stage.Flatten().Export(str(usd_path))
    print(f"SCENE_SAVED {usd_path}", flush=True)
    print("INITIAL " + json.dumps({"robot_base": robot_base.tolist(),
                                    "beaker_position": initial_position.tolist(),
                                    "beaker_height_m": height, "mass_kg": 0.08}), flush=True)
    grip_point = initial_position + np.array([0.0, 0.0, height * 0.55])
    approach = grip_point + np.array([0.0, 0.0, 0.16])
    lift = grip_point + np.array([0.0, 0.0, 0.12])
    orientation = euler_angles_to_quat(np.array([np.pi, 0.0, 0.0]))
    phases = [("approach", 3.0, approach, approach, 0.04),
              ("descend", 2.0, approach, grip_point, 0.04),
              ("grasp", 1.5, grip_point, grip_point, 0.0),
              ("lift", 2.5, grip_point, lift, 0.0),
              ("hold", 3.0, lift, lift, 0.0)]
    phase_index = 0
    phase_time = elapsed = held = max_held = max_lift = 0.0
    max_contacts = np.zeros(2)
    status = "TIMEOUT"
    reason = "task_simulation_time_budget"
    last_action = None
    print("PHASE approach", flush=True)
    started = time.monotonic()
    while elapsed < args.timeout_seconds:
        if not app.is_running():
            status, reason = "FAIL", "window_closed"
            break
        if time.monotonic() - started > max(120.0, args.timeout_seconds * 10):
            reason = "wall_clock_watchdog"
            break
        if not world.is_playing():
            app.update()
            continue
        name, duration, begin, end, aperture = phases[phase_index]
        fraction = min(phase_time / duration, 1.0)
        smooth = fraction * fraction * (3 - 2 * fraction)
        target = begin + smooth * (end - begin)
        ik_action, reachable = solver.compute_inverse_kinematics(target, orientation)
        if not reachable:
            status, reason = "FAIL", f"inverse_kinematics_unreachable_{name}"
            break
        joints = robot.get_joint_positions().copy()
        joints[np.asarray(ik_action.joint_indices, dtype=int)] = ik_action.joint_positions
        joints[-2:] = aperture
        last_action = ArticulationAction(joint_positions=joints)
        robot.get_articulation_controller().apply_action(last_action)
        world.step(render=not args.headless)
        elapsed += dt
        phase_time += dt
        position, _ = beaker.get_world_pose()
        rise = float(position[2] - initial_position[2])
        forces = contact_view.get_contact_force_matrix(dt=dt)
        contact_forces = np.linalg.norm(np.asarray(forces).reshape(2, -1, 3), axis=2).sum(axis=1)
        max_contacts = np.maximum(max_contacts, contact_forces)
        max_lift = max(max_lift, rise)
        # Consecutive contact on BOTH fingers prevents counting a launch or free fall.
        if name == "hold" and rise >= 0.05 and np.all(contact_forces > 0.01):
            held += dt
        else:
            held = 0.0
        max_held = max(max_held, held)
        if held + 1e-9 >= 1.0:
            status, reason = "SUCCESS", "lift_at_least_5cm_and_bilateral_contact_for_1s"
            break
        if position[2] < 0.65 or np.linalg.norm(position[:2] - initial_position[:2]) > 0.30:
            status, reason = "FAIL", "beaker_dropped_or_pushed_out_of_workspace"
            break
        if int(elapsed / dt) % 120 == 0:
            print(f"STATE t={elapsed:.2f} phase={name} lift={rise:.4f} "
                  f"contact_N={contact_forces.tolist()} held={held:.3f}", flush=True)
        if phase_time >= duration:
            if phase_index == len(phases) - 1:
                status, reason = "FAIL", "hold_finished_without_success"
                break
            phase_index += 1
            phase_time = 0.0
            print(f"PHASE {phases[phase_index][0]}", flush=True)
    final_position, _ = beaker.get_world_pose()
    result = {"status": status, "reason": reason, "simulation_seconds": elapsed,
              "initial_position_m": initial_position.tolist(), "final_position_m": final_position.tolist(),
              "final_lift_m": float(final_position[2] - initial_position[2]),
              "max_lift_m": max_lift, "continuous_hold_seconds": max_held,
              "peak_finger_contact_N": max_contacts.tolist(),
              "required_lift_m": 0.05, "required_hold_seconds": 1.0,
              "gui": not args.headless, "saved_initial_scene": str(usd_path)}
    result_path.write_text(json.dumps(result, indent=2) + "\n")
    print(status + " " + json.dumps(result), flush=True)
    if args.screenshot:
        if viewport is None:
            raise RuntimeError("Screenshot requested but no viewport is available")
        from omni.kit.viewport.utility import capture_viewport_to_file
        args.screenshot.parent.mkdir(parents=True, exist_ok=True)
        screenshot_path = args.screenshot.resolve()
        if screenshot_path.exists():
            screenshot_path.unlink()
        capture = capture_viewport_to_file(viewport, str(screenshot_path))
        capture_deadline = time.monotonic() + 15.0
        while time.monotonic() < capture_deadline:
            app.update()
            if screenshot_path.exists() and screenshot_path.stat().st_size > 0:
                break
        else:
            raise RuntimeError("Viewport screenshot did not finish within 15 seconds")
        print(f"SCREENSHOT_SAVED {screenshot_path}", flush=True)
    if not args.headless and not args.exit_on_result:
        print("GUI remains open; close the window or press Ctrl+C to exit.", flush=True)
        while app.is_running():
            if world.is_playing() and last_action is not None:
                robot.get_articulation_controller().apply_action(last_action)
                world.step(render=True)
            else:
                app.update()
    return 0 if status == "SUCCESS" else (124 if status == "TIMEOUT" else 1)


def main():
    args = arguments()
    from isaacsim import SimulationApp
    app = SimulationApp({"headless": args.headless, "width": 1280, "height": 720})
    code = 1
    try:
        code = run(args, app)
    except KeyboardInterrupt:
        print("FAIL interrupted_by_user", flush=True)
        code = 130
    except Exception:
        traceback.print_exc()
        print("FAIL setup_or_runtime_error", flush=True)
    finally:
        # Isaac Sim's native shutdown can exit Python before sys.exit(main()).
        # Set Kit's return code first so FAIL/TIMEOUT are visible to the shell.
        from omni.kit.app import get_app
        get_app().post_quit(code)
        app.close(skip_cleanup=False)
    return code


if __name__ == "__main__":
    sys.exit(main())
