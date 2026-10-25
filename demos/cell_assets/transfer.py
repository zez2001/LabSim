"""Franka transfers an existing beaker onto a sourced IKA shaker platform.

The hood is initialized open. This tests physical loading and release, not hood
opening, thermal control, shaking, or compatibility with a biological protocol.
"""

import argparse
import hashlib
import json
from pathlib import Path
import traceback

from demos.cell_assets.cameras import create_views, read_rgb
from utils.cell_assets import convert_asset, fetch_asset, get_asset, load_asset


def run(output, cache):
    """Run one deterministic loading attempt and return its measured result."""
    import cv2
    import numpy as np
    from PIL import Image
    from isaacsim.core.prims import SingleArticulation
    from isaacsim.core.utils.rotations import euler_angles_to_quat
    from isaacsim.core.utils.types import ArticulationAction
    from pxr import Usd, UsdGeom

    from demos.minimal_pick.scene import build_scene

    output.mkdir(parents=True)
    usd = convert_asset("ika_ks4000", output / "usd", cache)
    scene = build_scene()
    world, stage, robot = scene["world"], scene["stage"], scene["robot"]
    beaker, solver = scene["beaker"], scene["solver"]
    world.scene.get_object("table").set_local_scale(np.array([1.8, 1.8, 0.08]))
    device_position = np.array([0.20, 0.55, 0.74])
    load_asset(usd, "/World/Device", position_m=device_position)
    device = world.scene.add(SingleArticulation(
        prim_path="/World/Device/Asset", name="shaker"
    ))
    views = create_views(stage, [0.1, 0.3, 1.03], 1.9)
    world.reset()
    scene["contact_view"].initialize()
    device_q = np.zeros(device.num_dof)
    device_q[device.get_dof_index("hood_joint")] = np.pi / 2
    device.set_joint_positions(device_q)
    device.apply_action(ArticulationAction(joint_positions=device_q))
    for _ in range(60):
        world.step(render=True)

    # Use the imported platform collision surface, not an invented device size.
    platform = stage.GetPrimAtPath("/World/Device/Asset/sample_port_1/collisions")
    bounds = UsdGeom.BBoxCache(
        Usd.TimeCode.Default(), ["default", "render", "proxy", "guide"],
        False, True,
    ).ComputeWorldBound(platform).ComputeAlignedRange()
    surface_z = float(bounds.GetMax()[2])
    if bounds.IsEmpty() or not device_position[2] < surface_z < device_position[2] + 0.5:
        raise RuntimeError(f"Invalid imported platform collision bounds: {bounds}")
    initial, _ = beaker.get_world_pose()
    grip = initial + [0, 0, 0.0396]
    target_base = np.array(bounds.GetMidpoint())
    target_base[2] = surface_z + 0.001
    target_grip = target_base + [0, 0, 0.0396]
    approach = grip + [0, 0, 0.18]
    lift = grip + [0, 0, 0.24]
    above = target_grip + [0, 0, 0.18]
    phases = [
        ("approach", 3.0, approach, approach, 0.04),
        ("descend", 2.0, approach, grip, 0.04),
        ("grasp", 1.5, grip, grip, 0.0),
        ("lift", 2.5, grip, lift, 0.0),
        ("transfer", 3.0, lift, above, 0.0),
        ("place", 2.5, above, target_grip, 0.0),
        ("release", 1.5, target_grip, target_grip, 0.04),
        ("retreat", 2.0, target_grip, above, 0.04),
        ("settle", 3.5, above, above, 0.04),
    ]
    writers = {
        name: cv2.VideoWriter(
            str(output / f"{name}.mp4"), cv2.VideoWriter_fourcc(*"mp4v"),
            30, (960, 720)
        ) for name in views
    }
    if not all(w.isOpened() for w in writers.values()):
        raise RuntimeError("Could not open video encoders")
    records = []
    # Fingers close along X, leaving room between the source fixture's rollers.
    orientation = euler_angles_to_quat(np.array([np.pi, 0.0, np.pi / 2]))
    step = 0
    start_time = world.current_time
    try:
        for phase, duration, start, end, aperture in phases:
            for i in range(round(duration / scene["dt"])):
                f = min((i + 1) * scene["dt"] / duration, 1.0)
                target = start + f * f * (3 - 2 * f) * (end - start)
                action, reachable = solver.compute_inverse_kinematics(target, orientation)
                if not reachable:
                    raise RuntimeError(f"Unreachable IK target in {phase}: {target}")
                q = robot.get_joint_positions().copy()
                q[np.asarray(action.joint_indices, dtype=int)] = action.joint_positions
                q[-2:] = aperture
                robot.apply_action(ArticulationAction(joint_positions=q))
                world.step(render=False)
                if step % 4 == 0:
                    world.render()
                position, rotation = beaker.get_world_pose()
                forces = scene["contact_view"].get_contact_force_matrix(dt=scene["dt"])
                records.append({
                    "time_s": world.current_time - start_time, "phase": phase,
                    "joint_target": q.tolist(),
                    "joint_actual": robot.get_joint_positions().tolist(),
                    "beaker_position_m": position.tolist(),
                    "beaker_orientation_wxyz": rotation.tolist(),
                    "finger_force_n": np.linalg.norm(forces, axis=-1).ravel().tolist(),
                    "end_effector_m": solver.compute_end_effector_pose()[0].tolist(),
                })
                if step % 4 == 0:
                    for name, view in views.items():
                        writers[name].write(cv2.cvtColor(read_rgb(view), cv2.COLOR_RGB2BGR))
                step += 1
        for name, view in views.items():
            Image.fromarray(read_rgb(view)).save(output / f"{name}.png")
    finally:
        for writer in writers.values():
            writer.release()
        with (output / "trajectory.jsonl").open("w") as stream:
            for record in records:
                stream.write(json.dumps(record) + "\n")

    stable = [r for r in records if r["phase"] == "settle"][-360:]
    positions = np.array([r["beaker_position_m"] for r in stable])
    final = positions[-1]
    lift_height = max(
        r["beaker_position_m"][2] for r in records if r["phase"] == "lift"
    ) - initial[2]
    bilateral = any(
        min(r["finger_force_n"]) > 0.05
        for r in records if r["phase"] in ("grasp", "lift")
    )
    actual_q = robot.get_joint_positions()
    rotations = np.array([r["beaker_orientation_wxyz"] for r in stable])
    upright_cos = 1 - 2 * (rotations[:, 1] ** 2 + rotations[:, 2] ** 2)
    final_ee = np.array(records[-1]["end_effector_m"])
    checks = {
        "lifted_8cm": bool(lift_height >= 0.08),
        "bilateral_finger_contact": bool(bilateral),
        "target_xy_within_2cm": bool(np.linalg.norm(final[:2] - target_base[:2]) < 0.02),
        "on_platform_within_1cm": bool(abs(final[2] - surface_z) < 0.01),
        "released": bool(np.min(actual_q[-2:]) > 0.035),
        "retreated_12cm": bool(np.linalg.norm(final_ee - (final + [0, 0, 0.0396])) > 0.12),
        "no_finger_contact_after_release": bool(
            max(max(r["finger_force_n"]) for r in stable) < 0.05
        ),
        "upright_within_5deg": bool(np.min(upright_cos) > np.cos(np.deg2rad(5))),
        "settled_for_3s": len(stable) == 360,
        "simulation_clock_matches_steps": bool(np.isclose(
            world.current_time - start_time, step * scene["dt"], atol=1e-4
        )),
        "stable_3s_within_3mm": bool(np.max(np.linalg.norm(positions - final, axis=1)) < 0.003),
    }
    result = {
        "asset": get_asset("ika_ks4000"), "checks": checks,
        "success": all(checks.values()), "real_calibrated": False,
        "device_position_m": device_position.tolist(), "hood_initial_angle_rad": np.pi / 2,
        "platform_surface_z_m": surface_z, "target_base_m": target_base.tolist(),
        "final_base_m": final.tolist(), "lift_height_m": float(lift_height),
        "physics_dt_s": scene["dt"], "steps": step,
        "simulation_duration_s": world.current_time - start_time,
        "phase_durations_s": {p[0]: p[1] for p in phases},
        "gripper_orientation_wxyz": orientation.tolist(),
        "local_source_sha256": {
            name: hashlib.sha256(
                (Path(__file__).resolve().parents[2] / name).read_bytes()
            ).hexdigest()
            for name in ("assets/robots/Franka.usd", "demos/minimal_pick/assets/beaker.usda")
        },
        "limitations": [
            "Existing LabSim beaker geometry; no new equipment geometry created.",
            "Hood initialized open, shaker stopped; no thermal or mixing simulation.",
            "Simulation layout and contact parameters are engineering assumptions.",
        ],
    }
    (output / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New result directory")
    parser.add_argument("--cache", type=Path)
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    output = args.output.expanduser().resolve()
    if output.exists():
        parser.error(f"Output directory already exists: {output}")
    fetch_asset("ika_ks4000", args.cache, offline=args.offline)
    from isaacsim import SimulationApp

    app = SimulationApp({
        "headless": True, "renderer": "RayTracedLighting",
        "limit_cpu_threads": 8, "multi_gpu": False,
    })
    exit_code = 1
    try:
        result = run(output, args.cache)
        print("CELL_ASSET_TRANSFER " + json.dumps(result, ensure_ascii=False), flush=True)
        exit_code = 0 if result["success"] else 1
    except Exception as error:
        traceback.print_exc()
        if output.is_dir():
            (output / "result.json").write_text(json.dumps({
                "success": False, "status": "error", "error": str(error),
                "real_calibrated": False,
            }, indent=2) + "\n")
        raise
    finally:
        import omni.kit.app

        omni.kit.app.get_app().post_quit(exit_code)
        app.close(wait_for_replicator=False)


if __name__ == "__main__":
    main()
