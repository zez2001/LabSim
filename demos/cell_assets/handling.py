"""Contact-driven handling of sourced parts, with independent release checks.

The default task moves the original MagSep rack to the sourced Flex D2 surface,
releases it, withdraws, then retrieves it. Geometry is never resized, attached
to a gripper, or teleported after initialization.
"""

import argparse
import hashlib
import json
from pathlib import Path
import traceback

import numpy as np

from demos.cell_assets.cameras import VideoRecorder, create_views, read_rgb
from demos.cell_assets.motion import Motion, cartesian_joint_path, sample_joints
from utils.cell_assets import convert_asset, fetch_asset, load_asset

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config/cell_assets/rack_loading.json"


def dynamic_part(stage, path, position, config):
    """Retain original triangles, recenter and rigidly rotate the selected part."""
    import trimesh
    from pxr import Gf, PhysxSchema, UsdGeom, UsdPhysics, UsdShade, Vt
    from isaacsim.core.prims import SingleRigidPrim

    mesh = UsdGeom.Mesh.Get(stage, path)
    points = np.asarray(mesh.GetPointsAttr().Get(), dtype=float)
    faces = np.asarray(mesh.GetFaceVertexIndicesAttr().Get()).reshape(-1, 3)
    origin = np.r_[(points.min(0)[:2] + points.max(0)[:2]) / 2, points.min(0)[2]]
    yaw = np.deg2rad(config["payload_yaw_deg"])
    rotation = np.array([[np.cos(yaw), -np.sin(yaw), 0],
                         [np.sin(yaw), np.cos(yaw), 0], [0, 0, 1]])
    local = (points - origin) @ rotation.T
    shape = trimesh.Trimesh(vertices=local, faces=faces, process=True)
    if not shape.is_watertight or shape.volume <= 0:
        raise ValueError("Handling requires a watertight positive-volume source part")
    mesh.GetPointsAttr().Set(Vt.Vec3fArray.FromNumpy(local.astype(np.float32)))
    mesh.GetExtentAttr().Set([Gf.Vec3f(*local.min(0)), Gf.Vec3f(*local.max(0))])
    mesh.CreateDisplayColorAttr([Gf.Vec3f(0.35, 0.62, 0.12)])
    prim = mesh.GetPrim()
    UsdPhysics.MeshCollisionAPI.Apply(prim).CreateApproximationAttr("sdf")
    PhysxSchema.PhysxSDFMeshCollisionAPI.Apply(prim).CreateSdfResolutionAttr(config["sdf_resolution"])
    physics = PhysxSchema.PhysxRigidBodyAPI.Apply(prim)
    physics.CreateEnableCCDAttr(True)
    physics.CreateSolverPositionIterationCountAttr(32)
    physics.CreateSolverVelocityIterationCountAttr(8)
    material = UsdShade.Material.Define(stage, "/World/HandlingMaterial")
    friction = UsdPhysics.MaterialAPI.Apply(material.GetPrim())
    friction.CreateStaticFrictionAttr(config["static_friction"])
    friction.CreateDynamicFrictionAttr(config["dynamic_friction"])
    friction.CreateRestitutionAttr(0)
    UsdShade.MaterialBindingAPI.Apply(prim).Bind(material, materialPurpose="physics")
    mass = float(shape.volume * config["density_kg_m3"])
    body = SingleRigidPrim(prim_path=path, name="payload", position=position, mass=mass)
    return body, {"source_triangles": len(faces), "source_origin_m": origin.tolist(),
                  "local_bounds_m": [local.min(0).tolist(), local.max(0).tolist()],
                  "mesh_volume_m3": float(shape.volume), "mass_kg": mass,
                  "collision": "SDF from unchanged source triangles; rigid transform only"}


def plan_handling(solver, home, pickup, target, config):
    """Plan load and unload on one IK branch, reversing the verified entry path."""
    from isaacsim.core.utils.rotations import euler_angles_to_quat

    kin, frame = solver.get_kinematics_solver(), solver.get_end_effector_frame()
    orientation = euler_angles_to_quat(np.array([np.pi, 0, np.deg2rad(config["gripper_yaw_deg"])]))
    position = pickup + [0, 0, config["lift_m"]]
    joints, ok = kin.compute_inverse_kinematics(frame, position, orientation, home[:7])
    if not ok:
        raise RuntimeError("Initial approach is unreachable")
    approach_aperture = config.get("approach_aperture_m", 0.04)
    motions = [Motion("approach", 4, np.array([home[:7], joints]), approach_aperture)]

    def add(name, seconds, goal, aperture):
        nonlocal position, joints
        path = cartesian_joint_path(kin, frame, position, orientation,
                                    goal, orientation, joints, seconds)
        motions.append(Motion(name, seconds, path, aperture))
        position, joints = goal, path[-1]

    add("engage", 2.5, pickup, approach_aperture)
    add("grasp", 1.5, pickup, 0)
    exit_offset = np.array(config.get("pickup_exit_offset_m", [0, 0, 0]))
    if np.any(exit_offset):
        add("unseat", 2, pickup + [0, 0, exit_offset[2]], 0)
        add("slide_out", 3, pickup + exit_offset, 0)
    add("lift", 3, pickup + exit_offset + [0, 0, config["lift_m"]], 0)
    above = target + [0, 0, config["lift_m"]]
    add("transfer", 3, above + config["entry_offset_m"], 0)
    add("enter", 3, above, 0)
    add("place", 3, target, 0)
    add("release", 1.5, target, 0.04)
    add("withdraw", 2.5, above, 0.04)
    add("loaded_settle", 3.5, above, 0.04)
    add("reengage", 2.5, target, 0.04)
    add("regrasp", 1.5, target, 0)
    add("retrieve", 3, above, 0)
    # Reuse the exact entry path in reverse; no redundant IK branch switching.
    forward = {m.name: m for m in motions}
    return_names = ["enter", "transfer", "lift"]
    if np.any(exit_offset):
        return_names += ["slide_out", "unseat"]
    for name in return_names:
        path = forward[name].joints[::-1]
        motions.append(Motion("return_" + name, forward[name].duration, path, 0))
    joints, position = motions[-1].joints[-1], pickup
    add("release_returned", 1.5, pickup, approach_aperture)
    add("withdraw_returned", 2.5, pickup + [0, 0, config["lift_m"]], approach_aperture)
    add("returned_settle", 3.5, position, 0.04)
    return motions


def evaluate_handling(records, targets, grip_offset, dt, motions, support_surfaces=None):
    """Reject collisions, retained grasps, incomplete runs and unstable seating."""
    support_surfaces = support_surfaces or {"loaded": "device", "returned": "table"}
    expected = sum(round(m.duration / dt) for m in motions)
    checks = {
        "complete_record_count": len(records) == expected,
        "all_phases_completed": all(sum(r["phase"] == m.name for r in records)
                                     == round(m.duration / dt) for m in motions),
        "simulation_clock_matches_steps": bool(records and np.isclose(
            records[-1]["time_s"], expected * dt, atol=1e-4)),
        "no_robot_device_collision_above_1N": bool(records and max(
            r["robot_device_force_n"] for r in records) < 1),
        "no_robot_table_collision_above_1N": bool(records and max(
            r["robot_table_force_n"] for r in records) < 1),
    }
    for label, phase in (("loaded", "loaded_settle"), ("returned", "returned_settle")):
        rows = [r for r in records if r["phase"] == phase][-round(3 / dt):]
        complete = len(rows) == round(3 / dt)
        xyz = np.array([r["position_m"] for r in rows])
        checks.update({
            label + "_stable_3s": complete,
            label + "_position_within_2mm": bool(complete and np.max(
                np.linalg.norm(xyz - targets[label], axis=1)) < 0.002),
            label + "_stable_within_0_5mm": bool(complete and np.max(
                np.linalg.norm(xyz - xyz[-1], axis=1)) < 0.0005),
            label + "_orientation_within_3deg": bool(complete and all(
                abs(r["orientation_wxyz"][0]) > np.cos(np.deg2rad(3) / 2) for r in rows)),
            label + "_fingers_open": bool(complete and all(
                min(r["joint_actual"][-2:]) > 0.035 for r in rows)),
            label + "_no_finger_contact": bool(complete and all(
                max(r["finger_force_n"]) < 0.01 for r in rows)),
            label + "_supported_after_release": bool(complete and all(
                r["payload_" + support_surfaces[label] + "_force_n"] > 0.01
                for r in rows)),
            label + "_withdrawn_12cm": bool(complete and all(np.linalg.norm(
                np.array(r["end_effector_m"]) - r["position_m"] - grip_offset) > 0.12 for r in rows)),
        })
    for label, phases, initial in (
        ("loading", {"lift", "transfer", "enter"}, targets["returned"]),
        ("unloading", {"retrieve", "return_enter", "return_transfer"}, targets["loaded"]),
    ):
        held = [r for r in records if r["phase"] in phases]
        checks[label + "_lifted_8cm"] = bool(held and max(r["position_m"][2] for r in held) - initial[2] > 0.08)
        checks[label + "_bilateral_contact"] = bool(held and all(min(r["finger_force_n"]) > 0.01 for r in held))
        checks[label + "_tracks_gripper_3mm"] = bool(held and all(np.linalg.norm(
            np.array(r["end_effector_m"]) - r["position_m"] - grip_offset) < 0.003 for r in held))
        checks[label + "_orientation_within_5deg"] = bool(held and all(
            abs(r["orientation_wxyz"][0]) > np.cos(np.deg2rad(5) / 2) for r in held))
    return checks


def run(output, cache, config):
    """Build the source scene and record actual poses, contacts and arm commands."""
    from PIL import Image
    from pxr import PhysxSchema, UsdPhysics
    from isaacsim.core.api.sensors import RigidContactView
    from isaacsim.core.utils.types import ArticulationAction
    from demos.cell_assets.cap_cycle import create_detail_view
    from demos.minimal_pick.scene import build_scene

    output.mkdir(parents=True)
    scene = build_scene()
    world, stage, robot = scene["world"], scene["stage"], scene["robot"]
    world.stop()
    world.scene.remove_object("beaker")
    robot.set_world_pose(position=np.array(config["robot_base_m"]))
    robot.set_default_state(position=np.array(config["robot_base_m"]))
    scene["solver"].get_kinematics_solver().set_robot_base_pose(
        np.array(config["robot_base_m"]), np.array([1., 0, 0, 0]))
    # Extend the independent demonstration table, keeping its top at 0.74 m.
    table = world.scene.get_object("table")
    table.set_local_scale(np.array([1.5, 1.65, 0.08]))
    table.set_world_pose(position=np.array([0.1, 0.3, 0.7]))
    sources = {}
    for role in ("device", "payload"):
        asset_id = config[role + "_asset"]
        if role == "payload" and asset_id == config["device_asset"]:
            continue
        sources[asset_id] = fetch_asset(asset_id, cache, offline=True)
        usd = convert_asset(asset_id, output / (role + "-usd"), cache)
        load_asset(usd, "/World/" + role.title(), config["device_position_m"] if role == "device" else [0, 0, 0])
    part_root = "Device" if config["payload_asset"] == config["device_asset"] else "Payload"
    path = f"/World/{part_root}/Asset/{config['payload_part']}"
    payload, geometry = dynamic_part(stage, path, np.array(config["pickup_position_m"]), config)
    world.scene.add(payload)
    # URDF collision shapes live under instance proxies. Make this scenario's
    # referenced instances editable before setting contact offsets/sensors.
    for prim in list(stage.Traverse()):
        if str(prim.GetPath()).startswith("/World/Device/") and prim.IsInstance():
            prim.SetInstanceable(False)
    for prim in stage.Traverse():
        if prim.GetName() in {"panda_finger_joint1", "panda_finger_joint2"}:
            drive = UsdPhysics.DriveAPI.Apply(prim, "linear")
            drive.CreateMaxForceAttr(config["finger_max_force_n"])
            drive.CreateStiffnessAttr(config["finger_stiffness"])
            drive.CreateDampingAttr(config["finger_damping"])
        if prim.HasAPI(UsdPhysics.CollisionAPI):
            PhysxSchema.PhysxCollisionAPI.Apply(prim).CreateContactOffsetAttr(config["contact_offset_m"])
            PhysxSchema.PhysxCollisionAPI.Apply(prim).CreateRestOffsetAttr(0)
    fingers = ["/World/Franka/panda_leftfinger", "/World/Franka/panda_rightfinger"]
    arms = [str(p.GetPath()) for p in stage.Traverse() if str(p.GetPath()).startswith("/World/Franka/")
            and p.HasAPI(UsdPhysics.RigidBodyAPI) and p.GetName() != "panda_link0"]
    obstacles = [str(p.GetPath()) for p in stage.Traverse() if str(p.GetPath()).startswith("/World/Device/Asset/")
                 and p.HasAPI(UsdPhysics.RigidBodyAPI) and str(p.GetPath()) != path]
    if not obstacles:
        obstacles = [str(p.GetPath()) for p in stage.Traverse() if str(p.GetPath()).startswith("/World/Device/Asset/")
                     and p.HasAPI(UsdPhysics.CollisionAPI) and str(p.GetPath()) != path]
    if not obstacles:
        raise RuntimeError("No device contact filters; collision checks cannot be valid")
    geometry["device_contact_filters"] = obstacles
    contacts = RigidContactView(prim_paths_expr=fingers, filter_paths_expr=[[path]] * 2,
                                name="payload_contacts", max_contact_count=256)
    device_contacts = RigidContactView(prim_paths_expr=arms, filter_paths_expr=[obstacles] * len(arms),
                                       name="device_contacts", max_contact_count=2048)
    table_contacts = RigidContactView(prim_paths_expr=arms, filter_paths_expr=[["/World/Table"]] * len(arms),
                                      name="table_contacts", max_contact_count=512)
    payload_device = RigidContactView(prim_paths_expr=[path], filter_paths_expr=[obstacles],
                                      name="payload_device", max_contact_count=1024)
    payload_table = RigidContactView(prim_paths_expr=[path], filter_paths_expr=[["/World/Table"]],
                                     name="payload_table", max_contact_count=256)
    views = create_views(stage, config["camera_center_m"], config["camera_distance_m"])
    views["detail"] = create_detail_view(stage, np.array(config["target_position_m"]) - [0, 0.015, 0.04])
    world.reset()
    for contact in (contacts, device_contacts, table_contacts, payload_device, payload_table):
        contact.initialize()
    kp, kd = robot.get_articulation_controller().get_gains()
    kp[-2:], kd[-2:] = config["finger_stiffness"], config["finger_damping"]
    robot.get_articulation_controller().set_gains(kp, kd)
    for _ in range(120):
        world.step(render=True)
    initial, _ = payload.get_world_pose()
    geometry["initial_position_m"] = initial.tolist()
    geometry["kinematic_enabled"] = bool(UsdPhysics.RigidBodyAPI(payload.prim).GetKinematicEnabledAttr().Get())
    geometry["attachment_joints"] = [str(p.GetPath()) for p in stage.Traverse() if p.IsA(UsdPhysics.Joint)
        and any(path in [str(t) for t in p.GetRelationship(rel).GetTargets()] for rel in ("physics:body0", "physics:body1"))]
    target = np.array(config["target_position_m"])
    grip = np.array(config["grip_offset_m"])
    motions = plan_handling(scene["solver"], robot.get_joint_positions(), initial + grip, target + grip, config)
    (output / "plan.json").write_text(json.dumps({"config": config, "geometry": geometry,
        "phases": [{"name": m.name, "seconds": m.duration, "joints": m.joints.tolist(), "aperture_m": m.aperture} for m in motions]}, indent=2))
    stage.GetRootLayer().Export(str(output / "scene.usda"))
    for name, view in views.items():
        Image.fromarray(read_rgb(view)).save(output / f"initial-{name}.png")
    recorder = VideoRecorder(output, views)
    records, error = [], None
    dt, start = scene["dt"], world.current_time

    def force(view):
        return np.linalg.norm(view.get_contact_force_matrix(dt=dt), axis=-1)

    try:
        for motion in motions:
            for i in range(round(motion.duration / dt)):
                f = (i + 1) * dt / motion.duration
                q = np.r_[sample_joints(motion.joints, f * f * (3 - 2 * f)), motion.aperture, motion.aperture]
                robot.apply_action(ArticulationAction(joint_positions=q))
                world.step(render=False)
                pos, rot = payload.get_world_pose()
                row = {"time_s": world.current_time - start, "phase": motion.name,
                       "joint_target": q.tolist(), "joint_actual": robot.get_joint_positions().tolist(),
                       "position_m": pos.tolist(), "orientation_wxyz": rot.tolist(),
                       "end_effector_m": scene["solver"].compute_end_effector_pose()[0].tolist(),
                       "finger_force_n": force(contacts).ravel().tolist(),
                       "payload_device_force_n": float(force(payload_device).sum()),
                       "payload_table_force_n": float(force(payload_table).sum()),
                       "robot_device_force_n": float(force(device_contacts).max()),
                       "robot_table_force_n": float(force(table_contacts).max())}
                if row["robot_device_force_n"] > 0.1:
                    matrix = force(device_contacts)
                    body_index, filter_index = np.unravel_index(matrix.argmax(), matrix.shape)
                    row["robot_device_contact_pair"] = [arms[body_index], obstacles[filter_index]]
                records.append(row)
                if (len(records) - 1) % 4 == 0:
                    world.render()
                    recorder.write()
                if max(row["robot_device_force_n"], row["robot_table_force_n"]) > 5:
                    raise RuntimeError("Unexpected robot collision in " + motion.name)
            print("HANDLING_PHASE", motion.name, pos.tolist(), row["finger_force_n"], flush=True)
            if motion.name in {"grasp", "regrasp"} and min(row["finger_force_n"]) <= 0.01:
                raise RuntimeError("No bilateral grasp in " + motion.name)
            if motion.name in {"grasp", "loaded_settle", "returned_settle"}:
                world.render()
                for name, view in views.items():
                    Image.fromarray(read_rgb(view)).save(output / f"{motion.name}-{name}.png")
    except Exception as exc:
        error = str(exc)
        traceback.print_exc()
    finally:
        recorder.close()
        world.render()
        for name, view in views.items():
            Image.fromarray(read_rgb(view)).save(output / f"final-{name}.png")
        with (output / "trajectory.jsonl").open("w") as stream:
            for row in records:
                stream.write(json.dumps(row) + "\n")
    targets = {"loaded": target, "returned": initial}
    checks = evaluate_handling(records, targets, grip, dt, motions, config.get("support_surfaces"))
    checks["no_runtime_error"] = error is None
    checks["dynamic_without_attachment"] = not geometry["kinematic_enabled"] and not geometry["attachment_joints"]
    checks["initial_position_within_2mm"] = bool(np.linalg.norm(initial - config["pickup_position_m"]) < 0.002)
    result = {"task": config["task"], "asset_id": config["device_asset"], "payload_asset": config["payload_asset"],
              "success": all(checks.values()), "checks": checks, "error": error, "config": config,
              "geometry": geometry, "real_calibrated": False, "physics_dt_s": dt,
              "steps": len(records), "duration_s": world.current_time - start,
              "phase_durations_s": {m.name: m.duration for m in motions},
              "targets_m": {k: v.tolist() for k, v in targets.items()},
              "config_sha256": hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest(),
              "source_entries_sha256": {k: hashlib.sha256(p.read_bytes()).hexdigest() for k, p in sources.items()},
              "source_code_sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in [Path(__file__), Path(__file__).with_name("motion.py"),
                            Path(__file__).with_name("cameras.py"), Path(__file__).with_name("cap_cycle.py"),
                            ROOT / "demos/minimal_pick/scene.py", ROOT / "config/cell_assets/catalog.json",
                            ROOT / "utils/cell_assets.py", ROOT / "assets/robots/Franka.usd"]},
              "limitations": [config["assumptions"], "One fixed scene; no hardware calibration or experimental process validation."]}
    (output / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=CONFIG)
    parser.add_argument("--output", type=Path, required=True, help="New result directory; never overwritten")
    parser.add_argument("--cache", type=Path)
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    output = args.output.expanduser().resolve()
    if output.exists():
        parser.error(f"Output directory already exists: {output}")
    config = json.loads(args.config.read_text())
    for asset_id in {config["device_asset"], config["payload_asset"]}:
        fetch_asset(asset_id, args.cache, offline=args.offline)
    from isaacsim import SimulationApp
    app = SimulationApp({"headless": True, "renderer": "RayTracedLighting",
                         "limit_cpu_threads": 8, "multi_gpu": False})
    code = 1
    try:
        result = run(output, args.cache, config)
        code = 0 if result["success"] else 1
        print("HANDLING_RESULT", result["success"], result["checks"], flush=True)
    except Exception as exc:
        traceback.print_exc()
        if output.is_dir():
            (output / "result.json").write_text(json.dumps({"success": False, "error": str(exc)}))
    finally:
        import omni.kit.app
        omni.kit.app.get_app().post_quit(code)
        app.close(wait_for_replicator=False)


if __name__ == "__main__":
    main()
