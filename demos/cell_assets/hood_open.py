"""Operate the sourced IKA hood through physical Franka finger contact.

Optional gas struts provide passive support through explicit sliding mechanisms.
Their dimensions and force parameters are uncalibrated engineering assumptions.
Use --load-test for a continuous opening, loading, release and closing cycle.
"""

import argparse
import hashlib
import json
from pathlib import Path
import traceback
import xml.etree.ElementTree as ET

import numpy as np

from demos.cell_assets.cameras import VideoRecorder, create_views, read_rgb
from demos.cell_assets.motion import Motion, cartesian_joint_path, sample_joints
from utils.cell_assets import convert_asset, fetch_asset, get_asset, load_asset


def read_hood_geometry(source):
    """Read the actual hinge and handle frames; reject a different mechanism."""
    tree = ET.parse(source).getroot()
    hinge = tree.find("joint[@name='hood_joint']")
    handle = tree.find("joint[@name='hood_handle_joint']")
    if (hinge is None or handle is None
            or hinge.find("axis").get("xyz") != "-1 0 0"
            or handle.find("parent").get("link") != "hood"):
        raise ValueError("This controller requires the sourced IKA -X hood hinge")
    return tuple(np.fromstring(j.find("origin").get("xyz"), sep=" ")
                 for j in (hinge, handle))


def plan_opening(solver, home, device_position, geometry, release_test, close_test=False):
    """Preflight a continuous IK path before touching the device."""
    from isaacsim.core.utils.rotations import euler_angles_to_quat

    kinematics = solver.get_kinematics_solver()
    frame = solver.get_end_effector_frame()
    hinge, offset = geometry
    hinge = device_position + hinge
    opening_angle = 1.3

    def hood_pose(angle):
        c, s = np.cos(angle), np.sin(angle)
        rotation = np.array([[1, 0, 0], [0, c, s], [0, -s, c]])
        # Six millimetres in front of the source handle center, within the jaws.
        position = hinge + rotation @ (offset + [0, -0.006, 0])
        orientation = euler_angles_to_quat(np.array([np.pi / 2 + angle, 0, np.pi]))
        return position, orientation

    def solve(position, orientation, seed):
        joints, success = kinematics.compute_inverse_kinematics(
            frame, position, orientation, seed
        )
        if not success:
            raise RuntimeError(f"IK preflight failed at {position.tolist()}")
        return joints

    closed, closed_rotation = hood_pose(0)
    opened, opened_rotation = hood_pose(opening_angle)
    closed_joints = solve(closed, closed_rotation,
                          np.array([0, -0.785, 0, -2.356, 0, 1.571, 0.785]))
    opening_path = [closed_joints]
    for angle in np.linspace(0, opening_angle, 100)[1:]:
        position, orientation = hood_pose(angle)
        joints = solve(position, orientation, opening_path[-1])
        if np.max(np.abs(joints - opening_path[-1])) > 0.12:
            raise RuntimeError("Discontinuous opening IK path")
        opening_path.append(joints)
    opening_path = np.asarray(opening_path)
    pregrasp = closed + [0, -0.16, 0]
    pre_joints = solve(pregrasp, closed_rotation, closed_joints)
    motions = [Motion("hood_approach", 3, np.array([home[:7], pre_joints]), 0.04)]
    last_position, last_rotation, last_joints = pregrasp, closed_rotation, pre_joints

    def cartesian(name, duration, end, orientation, aperture):
        nonlocal last_position, last_rotation, last_joints
        try:
            path = cartesian_joint_path(
                kinematics, frame, last_position, last_rotation,
                end, orientation, last_joints, duration,
            )
        except RuntimeError as error:
            raise RuntimeError(f"IK preflight failed in {name}: {error}") from error
        motions.append(Motion(name, duration, path, aperture))
        last_position, last_rotation, last_joints = end, orientation, path[-1]

    cartesian("hood_engage", 2, closed, closed_rotation, 0.04)
    cartesian("hood_grasp", 1.5, closed, closed_rotation, 0)
    # Use the preflight branch, avoiding physics-noise-induced IK branch changes.
    if np.max(np.abs(last_joints - opening_path[0])) > 0.12:
        raise RuntimeError("Grasp and opening paths use different IK branches")
    motions.append(Motion("hood_open", 8, opening_path, 0))
    last_position, last_rotation, last_joints = opened, opened_rotation, opening_path[-1]
    cartesian("hood_hold", 2, opened, opened_rotation, 0)
    if release_test:
        cartesian("hood_release", 2, opened, opened_rotation, 0.04)
        clear = opened + [0, -0.15, 0]
        cartesian("hood_withdraw", 2, clear, opened_rotation, 0.04)
        cartesian("release_settle", 3.5, clear, opened_rotation, 0.04)
    if close_test:
        cartesian("hood_reengage", 2, opened, opened_rotation, 0.04)
        cartesian("hood_regrasp", 1.5, opened, opened_rotation, 0)
        motions.append(Motion("hood_close", 8, opening_path[::-1], 0))
        last_position, last_rotation, last_joints = closed, closed_rotation, opening_path[0]
        cartesian("closed_hold", 2, closed, closed_rotation, 0)
        cartesian("closed_release", 1.5, closed, closed_rotation, 0.04)
        cartesian("closed_withdraw", 2, pregrasp, closed_rotation, 0.04)
        cartesian("closed_settle", 3.5, pregrasp, closed_rotation, 0.04)
    return motions


def run(output, cache, release_test, gas_springs=False, close_test=False, load_test=False):
    from PIL import Image
    from pxr import PhysxSchema, Usd, UsdGeom, UsdPhysics
    from isaacsim.core.api.objects import FixedCuboid
    from isaacsim.core.api.sensors import RigidContactView
    from isaacsim.core.prims import SingleArticulation
    from isaacsim.core.utils.types import ArticulationAction
    from demos.minimal_pick.scene import build_scene
    from demos.cell_assets.loading import evaluate_loading, insert_loading, read_cycle_config

    cycle = read_cycle_config() if load_test else None
    if load_test:
        gas_springs = release_test = close_test = True
    controller_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    output.mkdir(parents=True)
    source = fetch_asset("ika_ks4000", cache, offline=True)
    geometry = read_hood_geometry(source)
    usd = convert_asset("ika_ks4000", output / "usd", cache)
    scene = build_scene()
    world, stage, robot = scene["world"], scene["stage"], scene["robot"]
    world.stop()
    solver, dt = scene["solver"], scene["dt"]
    world.scene.get_object("table").set_local_scale(np.array([1.8, 1.8, 0.08]))
    robot_base = np.array(cycle["robot_base_m"] if cycle else [-0.35, 0.05, 1.0])
    robot.set_world_pose(position=robot_base)
    robot.set_default_state(position=robot_base)
    solver.get_kinematics_solver().set_robot_base_pose(robot_base, np.array([1., 0, 0, 0]))
    world.scene.add(FixedCuboid(
        prim_path="/World/Pedestal", name="pedestal",
        position=np.array([robot_base[0], robot_base[1], (robot_base[2] + 0.74) / 2]),
        scale=np.array([0.22, 0.22, robot_base[2] - 0.74]), color=np.array([0.35, 0.4, 0.42]),
    ))
    device_position = np.array(cycle["device_position_m"] if cycle else [0.1, 0.45, 0.74])
    load_asset(usd, "/World/Device", position_m=device_position)
    device = world.scene.add(SingleArticulation(
        prim_path="/World/Device/Asset", name="shaker"
    ))
    support = None
    if gas_springs:
        from utils.ika_gas_springs import GasSpringPair
        support = GasSpringPair(stage, "/World/Device/Asset", device_position, geometry[0])
    for prim in stage.Traverse():
        if cycle and prim.GetName() in {"panda_finger_joint1", "panda_finger_joint2"}:
            UsdPhysics.DriveAPI.Apply(prim, "linear").CreateMaxForceAttr(cycle["finger_max_force_n"])
        if prim.GetName() == "hood_joint":
            drive = UsdPhysics.DriveAPI.Apply(prim, "angular")
            drive.CreateStiffnessAttr(0.)
            drive.CreateDampingAttr(0.)
            drive.CreateMaxForceAttr(0.)
        if prim.HasAPI(UsdPhysics.CollisionAPI):
            collision = PhysxSchema.PhysxCollisionAPI.Apply(prim)
            collision.CreateRestOffsetAttr(0.)
            collision.CreateContactOffsetAttr(0.001)
    if support:
        support.export_asset(output / "ika_gas_springs.usdc")
    views = create_views(stage, cycle["camera_center_m"] if cycle else [0, 0.3, 1.3],
                         cycle["camera_distance_m"] if cycle else 2.3)
    contacts = RigidContactView(
        prim_paths_expr=["/World/Franka/panda_leftfinger", "/World/Franka/panda_rightfinger"],
        filter_paths_expr=[["/World/Device/Asset/hood_handle"],
                           ["/World/Device/Asset/hood_handle"]],
        name="handle_contacts", max_contact_count=128,
    )
    arm_paths = [str(p.GetPath()) for p in stage.Traverse()
                 if str(p.GetPath()).startswith("/World/Franka/")
                 and p.HasAPI(UsdPhysics.RigidBodyAPI)]
    obstacle_paths = [str(p.GetPath()) for p in stage.Traverse()
                      if (str(p.GetPath()).startswith("/World/Device/Asset/")
                          or str(p.GetPath()).startswith("/World/GasSpring"))
                      and p.HasAPI(UsdPhysics.RigidBodyAPI) and p.GetName() != "hood_handle"]
    arm_contacts = RigidContactView(
        prim_paths_expr=arm_paths,
        filter_paths_expr=[obstacle_paths for _ in arm_paths],
        name="arm_device_contacts", max_contact_count=2048,
    )
    moving_arm_paths = [p for p in arm_paths if not p.endswith("/panda_link0")]
    environment_contacts = RigidContactView(
        prim_paths_expr=moving_arm_paths,
        filter_paths_expr=[["/World/Table", "/World/Pedestal", "/World/Ground/CollisionPlane"]
                           for _ in moving_arm_paths],
        name="arm_environment_contacts", max_contact_count=512,
    )
    world.reset()
    contacts.initialize()
    arm_contacts.initialize()
    environment_contacts.initialize()
    if load_test:
        scene["contact_view"].initialize()
    if support:
        support.initialize()
    index = device.get_dof_index("hood_joint")
    device.set_joint_positions(np.zeros(device.num_dof))  # Closed initialization only.
    kp, kd = device.get_articulation_controller().get_gains()
    kp[index], kd[index] = 0, 0
    device.get_articulation_controller().set_gains(kp, kd)
    rkp, rkd = robot.get_articulation_controller().get_gains()
    rkp[-2:] = 10000
    robot.get_articulation_controller().set_gains(rkp, rkd)
    for _ in range(60):
        if support:
            support.step()
        world.step(render=True)
    initial_angle = float(device.get_joint_positions()[index])
    if abs(initial_angle) > 0.02:
        raise RuntimeError("Hood is not closed at initialization")
    motions = plan_opening(solver, robot.get_joint_positions(), device_position,
                           geometry, release_test, close_test)
    hood_phases = {motion.name for motion in motions}
    initial_beaker = scene["beaker"].get_world_pose()[0]
    target_base, surface_z = None, None
    if load_test:
        platform = stage.GetPrimAtPath("/World/Device/Asset/" + cycle["platform_link"] + "/collisions")
        bounds = UsdGeom.BBoxCache(
            Usd.TimeCode.Default(), ["default", "render", "proxy", "guide"], False, True,
        ).ComputeWorldBound(platform).ComputeAlignedRange()
        if bounds.IsEmpty():
            raise RuntimeError("Missing source platform collision bounds")
        surface_z = float(bounds.GetMax()[2])
        target_base = np.array(bounds.GetMidpoint())
        target_base[2] = surface_z + 0.001
        grip_offset = np.array([0, 0, cycle["grip_height_m"]])
        motions = insert_loading(motions, solver, initial_beaker + grip_offset,
                                 target_base + grip_offset, cycle)
    (output / "plan.json").write_text(json.dumps([
        {"phase": p.name, "duration_s": p.duration, "joints": p.joints.tolist(),
         "aperture_m": p.aperture} for p in motions
    ]))
    recording = VideoRecorder(output, views)
    records, error = [], None
    start_time, step = world.current_time, 0
    try:
        for motion in motions:
            if cycle:
                rkp[-2:] = cycle["hood_finger_stiffness"] if motion.name in hood_phases else cycle["beaker_finger_stiffness"]
                robot.get_articulation_controller().set_gains(rkp, rkd)
            for i in range(round(motion.duration / dt)):
                fraction = (i + 1) * dt / motion.duration
                eased = fraction * fraction * (3 - 2 * fraction)
                q = robot.get_joint_positions().copy()
                q[:7] = sample_joints(motion.joints, eased)
                q[-2:] = motion.aperture
                spring_state = support.step() if support else []
                robot.apply_action(ArticulationAction(joint_positions=q))
                world.step(render=False)
                record = {
                    "time_s": world.current_time - start_time, "phase": motion.name,
                    "joint_target": q.tolist(), "joint_actual": robot.get_joint_positions().tolist(),
                    "hood_angle_rad": float(device.get_joint_positions()[index]),
                    "hood_velocity_rad_s": float(device.get_joint_velocities()[index]),
                    "support_torque_nm": 0.,
                    "gas_springs": spring_state,
                    "handle_force_n": np.linalg.norm(contacts.get_contact_force_matrix(dt=dt), axis=-1).ravel().tolist(),
                    "unintended_robot_device_force_n": float(np.max(np.linalg.norm(
                        arm_contacts.get_contact_force_matrix(dt=dt), axis=-1))),
                    "robot_environment_force_n": float(np.max(np.linalg.norm(
                        environment_contacts.get_contact_force_matrix(dt=dt), axis=-1))),
                    "finger_stiffness": float(rkp[-1]),
                    "end_effector_m": solver.compute_end_effector_pose()[0].tolist(),
                }
                if load_test:
                    position, orientation = scene["beaker"].get_world_pose()
                    record.update({
                        "beaker_position_m": position.tolist(),
                        "beaker_orientation_wxyz": orientation.tolist(),
                        "beaker_force_n": np.linalg.norm(scene["contact_view"].get_contact_force_matrix(dt=dt), axis=-1).ravel().tolist(),
                    })
                records.append(record)
                if step % 4 == 0:
                    world.render()
                    recording.write()
                step += 1
                if load_test and max(record["unintended_robot_device_force_n"], record["robot_environment_force_n"]) > 5:
                    raise RuntimeError(f"Unexpected robot collision above 5 N during {motion.name}")
                if load_test and motion.name in {"lift_beaker", "transfer_beaker", "above_platform", "place_beaker"}:
                    distance = np.linalg.norm(np.array(record["end_effector_m"]) - record["beaker_position_m"] - grip_offset)
                    if distance > 0.03:
                        raise RuntimeError(f"Beaker lost from the gripper during {motion.name}")
            print("HOOD_PHASE", motion.name, record["hood_angle_rad"], flush=True)
            if load_test and motion.name == "release_beaker":
                if min(record["joint_actual"][-2:]) <= 0.035 or max(record["beaker_force_n"]) >= 0.05:
                    raise RuntimeError("Beaker release failed; stopping before gripper withdrawal")
            if load_test and motion.name == "loaded_settle":
                placement = evaluate_loading(records, initial_beaker, target_base, surface_z, dt, cycle["grip_height_m"])
                if not all(value for name, value in placement.items() if name.startswith("loaded_")):
                    raise RuntimeError("Placement stability failed; stopping before hood closing")
            if motion.name in {"hood_grasp", "hood_hold", "hood_release", "release_settle", "loaded_settle", "closed_settle"}:
                world.render()
                for name, view in views.items():
                    Image.fromarray(read_rgb(view)).save(output / f"{motion.name}-{name}.png")
    except Exception as exc:
        error = str(exc)
        traceback.print_exc()
    finally:
        recording.close()
        with (output / "trajectory.jsonl").open("w") as stream:
            for record in records:
                stream.write(json.dumps(record) + "\n")
    held = [r for r in records if r["phase"] == "hood_hold"]
    released = [r for r in records if r["phase"] == "hood_release"]
    checks = {
        "started_closed": abs(initial_angle) < 0.02,
        "opened_above_71deg": bool(held and min(r["hood_angle_rad"] for r in held) > 1.25),
        "bilateral_handle_contact": bool(held and all(min(r["handle_force_n"]) > 1 for r in held[-120:])),
        "held_for_2s": len(held) == round(2 / dt),
        "no_runtime_error": error is None,
        "simulation_clock_matches_steps": bool(np.isclose(world.current_time - start_time, step * dt, atol=1e-4)),
        "no_nonhandle_contact_above_1N": bool(records and max(r["unintended_robot_device_force_n"] for r in records) < 1.),
        "no_environment_contact_above_1N": bool(records and max(r["robot_environment_force_n"] for r in records) < 1.),
        "all_phases_completed": all(sum(r["phase"] == m.name for r in records) == round(m.duration / dt) for m in motions),
    }
    if release_test:
        stable = [r for r in records if r["phase"] == "release_settle"][-360:]
        checks["hood_stays_open_after_release"] = bool(len(stable) == 360 and min(r["hood_angle_rad"] for r in stable) > 1.2)
        checks["gripper_released"] = bool(released and min(released[-1]["joint_actual"][-2:]) > 0.035)
        checks["no_finger_contact_after_release"] = bool(stable and max(max(r["handle_force_n"]) for r in stable) < 0.05)
    if support:
        checks["gas_spring_stroke_limits"] = all(
            support.minimum - 0.002 <= spring["length_m"] <= support.maximum + 0.002
            for record in records for spring in record["gas_springs"]
        )
    if close_test:
        closed = [r for r in records if r["phase"] == "closed_settle"][-360:]
        checks["closed_and_stable_3s"] = bool(len(closed) == 360 and max(abs(r["hood_angle_rad"]) for r in closed) < 0.02)
        checks["no_finger_contact_after_closing"] = bool(closed and max(max(r["handle_force_n"]) for r in closed) < 0.05)
        checks["released_after_closing"] = bool(closed and min(closed[-1]["joint_actual"][-2:]) > 0.035)
    if load_test:
        checks.update(evaluate_loading(records, initial_beaker, target_base, surface_z, dt, cycle["grip_height_m"]))
    result = {
        "asset": get_asset("ika_ks4000"), "checks": checks, "success": all(checks.values()),
        "error": error, "task": "open_load_close" if load_test else ("open_release_close" if close_test else ("opening_and_release" if release_test else "opening_and_hold")),
        "cycle_config": cycle,
        "initial_beaker_position_m": initial_beaker.tolist() if load_test else None,
        "target_beaker_position_m": target_base.tolist() if load_test else None,
        "platform_surface_z_m": surface_z,
        "phase_durations_s": {m.name: m.duration for m in motions},
        "support_model": "physical_gas_strut_prototype" if support else "none",
        "gas_spring_config": support.config if support else None,
        "automatic_loading_verified": bool(load_test and all(checks.values())), "real_calibrated": False,
        "real_mechanism_complete": False, "device_position_m": device_position.tolist(),
        "robot_base_m": robot_base.tolist(),
        "final_hood_angle_rad": records[-1]["hood_angle_rad"] if records else initial_angle,
        "initial_hood_angle_rad": initial_angle, "physics_dt_s": dt, "steps": step,
        "duration_s": world.current_time - start_time,
        "source_urdf_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "controller_sha256": controller_hash,
        "hood_drive": {"stiffness": float(kp[index]), "damping": float(kd[index]), "max_force": 0.},
        "finger_stiffness": float(rkp[-1]),
        "source_dependencies_sha256": {
            name: hashlib.sha256((Path(__file__).resolve().parents[2] / name).read_bytes()).hexdigest()
            for name in ("assets/robots/Franka.usd", "demos/minimal_pick/scene.py",
                         "demos/cell_assets/cameras.py", "demos/cell_assets/motion.py",
                         "utils/cell_assets.py",
                         "config/cell_assets/catalog.json", "utils/ika_gas_springs.py",
                         "config/cell_assets/ika_gas_springs.json", "demos/cell_assets/loading.py",
                         "config/cell_assets/ika_automatic_cycle.json", "demos/minimal_pick/assets/beaker.usda")
        },
        "limitations": [
            "Source gas springs are absent. Optional parametric struts use uncalibrated mounting dimensions and force parameters; they are not manufacturer CAD.",
            "No direct hood hinge drive, gravity compensation or object attachment is used. See automatic_loading_verified for this run's status.",
            "Fixed layout with an elevated robot mount; mass, inertia, friction and controller gains are not hardware calibrated.",
            "Shaker stopped throughout; no heating, shaking, biochemical operation or real-device control.",
        ],
    }
    (output / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New result directory")
    parser.add_argument("--cache", type=Path)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--release-test", action="store_true", help="Release and withdraw; require the hood to remain open for 3 seconds")
    parser.add_argument("--gas-springs", action="store_true", help="Add the explicitly uncalibrated physical gas-strut prototype")
    parser.add_argument("--close-test", action="store_true", help="Also regrasp, close, release and verify closed stability; requires --gas-springs")
    parser.add_argument("--load-test", action="store_true", help="Run the full open/load/release/close cycle using the fixed cycle configuration; includes physical gas springs")
    args = parser.parse_args()
    if args.close_test and not (args.gas_springs or args.load_test):
        parser.error("--close-test requires --gas-springs for the intervening release")
    output = args.output.expanduser().resolve()
    if output.exists():
        parser.error(f"Refusing to overwrite {output}")
    fetch_asset("ika_ks4000", args.cache, offline=args.offline)
    from isaacsim import SimulationApp
    app = SimulationApp({"headless": True, "renderer": "RayTracedLighting",
                         "limit_cpu_threads": 8, "multi_gpu": False})
    exit_code = 1
    try:
        result = run(output, args.cache, args.release_test or args.close_test,
                     args.gas_springs, args.close_test, args.load_test)
        exit_code = 0 if result["success"] else 1
        print("HOOD_OPEN_RESULT", json.dumps(result, ensure_ascii=False), flush=True)
    except Exception as exc:
        traceback.print_exc()
        if output.is_dir():
            (output / "result.json").write_text(json.dumps({"success": False, "error": str(exc)}))
    finally:
        import omni.kit.app
        omni.kit.app.get_app().post_quit(exit_code)
        app.close(wait_for_replicator=False)
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
