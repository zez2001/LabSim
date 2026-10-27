"""Physically remove, park and replace the sourced DIYNAFLUOR light baffle.

The original hollow cap becomes a dynamic SDF collider. Only Franka joint
commands move it after initialization; no attachment or cap pose writes occur.
This verifies mechanical handling, not optical measurement or tube loading.
"""

import argparse
import hashlib
import json
from pathlib import Path
import traceback

import numpy as np

from demos.cell_assets.cameras import VideoRecorder, create_views, read_rgb
from demos.cell_assets.motion import Motion, cartesian_joint_path, sample_joints
from utils.cell_assets import convert_asset, fetch_asset, get_asset, load_asset

CONFIG = Path(__file__).resolve().parents[2] / "config/cell_assets/diynafluor_cap_cycle.json"


def plan_cycle(solver, home, closed, parked, config):
    """Plan both transfers with one continuous IK branch and explicit releases."""
    from isaacsim.core.utils.rotations import euler_angles_to_quat

    kinematics = solver.get_kinematics_solver()
    frame = solver.get_end_effector_frame()
    rotation = euler_angles_to_quat(np.array([np.pi, 0, np.pi / 2]))
    above = closed + [0, 0, config["lift_m"]]
    joints, success = kinematics.compute_inverse_kinematics(frame, above, rotation, home[:7])
    if not success:
        raise RuntimeError("Unreachable initial cap approach")
    motions = [Motion("approach", 3, np.array([home[:7], joints]), 0.04)]
    position = above

    def add(name, duration, target, aperture):
        nonlocal position, joints
        path = cartesian_joint_path(kinematics, frame, position, rotation,
                                    target, rotation, joints, duration)
        motions.append(Motion(name, duration, path, aperture))
        position, joints = target, path[-1]

    add("engage_cap", 2, closed, 0.04)
    add("grasp_cap", 1.5, closed, 0)
    add("uncap", 2.5, above, 0)
    add("transfer_to_park", 2.5, parked + [0, 0, config["lift_m"]], 0)
    add("place_on_park", 2.5, parked, 0)
    add("release_on_park", 1.5, parked, 0.04)
    add("withdraw_from_park", 2, parked + [0, 0, config["lift_m"] + 0.04], 0.04)
    add("parked_settle", 3.5, position, 0.04)
    add("reengage_cap", 2, parked, 0.04)
    add("regrasp_cap", 1.5, parked, 0)
    add("lift_from_park", 2.5, parked + [0, 0, config["lift_m"]], 0)
    add("transfer_to_sample", 2.5, above, 0)
    add("recap", 2.5, closed, 0)
    add("release_closed", 1.5, closed, 0.04)
    add("withdraw_closed", 2, above + [0, 0, 0.04], 0.04)
    add("closed_settle", 3.5, position, 0.04)
    return motions


def evaluate_cycle(records, targets, dt, expected_steps, grip_offset):
    """Require both released seating windows, two real grasps and full completion."""
    required = round(3 / dt)
    checks = {
        "complete_record_count": len(records) == expected_steps,
        "simulation_clock_matches_steps": bool(records and np.isclose(
            records[-1]["time_s"], len(records) * dt, atol=1e-4)),
        "no_robot_device_collision_above_1N": bool(records and max(
            r["robot_device_force_n"] for r in records) < 1),
        "no_robot_table_collision_above_1N": bool(records and max(
            r["robot_table_force_n"] for r in records) < 1),
    }
    for label, phase in (("parked", "parked_settle"), ("closed", "closed_settle")):
        window = [r for r in records if r["phase"] == phase][-required:]
        complete = len(window) == required
        positions = np.array([r["cap_position_m"] for r in window])
        rotations = np.array([r["cap_orientation_wxyz"] for r in window])
        target = np.asarray(targets[label])
        checks.update({
            label + "_stable_3s": complete,
            label + "_xy_within_1mm": bool(complete and np.max(np.linalg.norm(
                positions[:, :2] - target[:2], axis=1)) < 0.001),
            label + "_height_within_1mm": bool(complete and np.max(np.abs(
                positions[:, 2] - target[2])) < 0.001),
            label + "_upright_within_3deg": bool(complete and np.min(
                1 - 2 * (rotations[:, 1] ** 2 + rotations[:, 2] ** 2))
                > np.cos(np.deg2rad(3))),
            label + "_stable_within_0_5mm": bool(complete and np.max(np.linalg.norm(
                positions - positions[-1], axis=1)) < 0.0005),
            label + "_fingers_open": bool(complete and all(
                min(r["joint_actual"][-2:]) > 0.035 for r in window)),
            label + "_no_finger_contact": bool(complete and all(
                max(r["finger_force_n"]) < 0.01 for r in window)),
            label + "_withdrawn_12cm": bool(complete and all(np.linalg.norm(
                np.array(r["end_effector_m"]) - r["cap_position_m"] - grip_offset
            ) > 0.12 for r in window)),
        })
    for label, phases, start in (
        ("opening", {"uncap", "transfer_to_park"}, targets["closed"]),
        ("closing", {"lift_from_park", "transfer_to_sample"}, targets["parked"]),
    ):
        held = [r for r in records if r["phase"] in phases]
        checks[label + "_lifted_8cm"] = bool(held and max(
            r["cap_position_m"][2] for r in held) - start[2] > 0.08)
        checks[label + "_bilateral_contact"] = bool(held and all(
            min(r["finger_force_n"]) > 0.01 for r in held))
        checks[label + "_tracks_gripper_3mm"] = bool(held and all(np.linalg.norm(
            np.array(r["end_effector_m"]) - r["cap_position_m"] - grip_offset
        ) < 0.003 for r in held))
        checks[label + "_upright_during_carry_5deg"] = bool(held and all(
            1 - 2 * (r["cap_orientation_wxyz"][1] ** 2
                     + r["cap_orientation_wxyz"][2] ** 2) > np.cos(np.deg2rad(5))
            for r in held))
    return checks


def create_detail_view(stage, device_position):
    """Add an oblique close-up so the original 36 mm cap is visible."""
    import omni.replicator.core as rep
    from pxr import Gf, UsdGeom

    center = device_position + [0, 0.015, 0.085]
    eye = center + [0.23, -0.24, 0.24]
    camera = UsdGeom.Camera.Define(stage, "/World/Camera_detail")
    transform = Gf.Matrix4d().SetLookAt(
        Gf.Vec3d(*eye), Gf.Vec3d(*center), Gf.Vec3d(0, 0, 1)).GetInverse()
    UsdGeom.Xformable(camera).AddTransformOp().Set(transform)
    camera.CreateClippingRangeAttr(Gf.Vec2f(0.005, 100))
    camera.CreateFocalLengthAttr(40)
    product = rep.create.render_product(str(camera.GetPath()), (960, 720))
    annotator = rep.AnnotatorRegistry.get_annotator("rgb")
    annotator.attach([product])
    return annotator


def make_dynamic_cap(stage, config, device_position):
    """Recenter original cap triangles and retain the concave cavity as an SDF."""
    import trimesh
    from pxr import Gf, PhysxSchema, UsdGeom, UsdPhysics, UsdShade, Vt
    from isaacsim.core.prims import SingleRigidPrim

    path = "/World/Device/Asset/" + config["cap_part"]
    mesh = UsdGeom.Mesh.Get(stage, path)
    points = np.asarray(mesh.GetPointsAttr().Get(), dtype=np.float64)
    indices = np.asarray(mesh.GetFaceVertexIndicesAttr().Get()).reshape(-1, 3)
    lower, upper = points.min(axis=0), points.max(axis=0)
    origin = np.r_[(lower[:2] + upper[:2]) / 2, lower[2]]
    # Mesh points differ only by one rigid translation; no geometric resizing.
    local = points - origin
    mesh.GetPointsAttr().Set(Vt.Vec3fArray.FromNumpy(local.astype(np.float32)))
    mesh.GetExtentAttr().Set([Gf.Vec3f(*local.min(axis=0)), Gf.Vec3f(*local.max(axis=0))])
    mesh.CreateDisplayColorAttr([Gf.Vec3f(0.22, 0.46, 0.12)])
    shape = trimesh.Trimesh(vertices=local, faces=indices, process=True)
    if not shape.is_watertight or shape.volume <= 0:
        raise ValueError("Source cap must be a watertight, positive-volume solid")
    mass = float(shape.volume * config["cap_density_kg_m3"])
    prim = mesh.GetPrim()
    UsdPhysics.MeshCollisionAPI.Apply(prim).CreateApproximationAttr("sdf")
    PhysxSchema.PhysxSDFMeshCollisionAPI.Apply(prim).CreateSdfResolutionAttr(config["sdf_resolution"])
    rigid = PhysxSchema.PhysxRigidBodyAPI.Apply(prim)
    rigid.CreateSolverPositionIterationCountAttr(32)
    rigid.CreateSolverVelocityIterationCountAttr(8)
    rigid.CreateEnableCCDAttr(True)
    material = UsdShade.Material.Define(stage, "/World/CapMaterial")
    physics = UsdPhysics.MaterialAPI.Apply(material.GetPrim())
    physics.CreateStaticFrictionAttr(config["cap_static_friction"])
    physics.CreateDynamicFrictionAttr(config["cap_dynamic_friction"])
    physics.CreateRestitutionAttr(0)
    UsdShade.MaterialBindingAPI.Apply(prim).Bind(material, materialPurpose="physics")
    parked = device_position + origin
    closed = parked + np.r_[np.array(config["sample_axis_source_m"])
                             - config["park_axis_source_m"], 0]
    cap = SingleRigidPrim(prim_path=path, name="cap", position=closed, mass=mass)
    metadata = {
        "source_vertices": len(points), "source_triangles": len(indices),
        "source_world_origin_m": origin.tolist(), "mesh_volume_m3": float(shape.volume),
        "mass_kg": mass, "cap_bounds_local_m": [local.min(0).tolist(), local.max(0).tolist()],
        "collision": "SDF from original triangles; concave underside retained",
        "color": "Green visualization override; original geometry retained",
    }
    return cap, {"closed": closed, "parked": parked}, metadata


def run(output, cache, config):
    """Run a continuous, contact-driven cap cycle and write all measured evidence."""
    from PIL import Image
    from pxr import PhysxSchema, UsdPhysics
    from isaacsim.core.api.sensors import RigidContactView
    from isaacsim.core.utils.types import ArticulationAction
    from demos.minimal_pick.scene import build_scene

    output.mkdir(parents=True)
    source = fetch_asset("diynafluor", cache, offline=True)
    usd = convert_asset("diynafluor", output / "usd", cache)
    scene = build_scene()
    world, stage, robot = scene["world"], scene["stage"], scene["robot"]
    world.stop()
    world.scene.remove_object("beaker")
    device_position = np.array(config["device_position_m"])
    load_asset(usd, "/World/Device", device_position)
    cap, targets, geometry = make_dynamic_cap(stage, config, device_position)
    world.scene.add(cap)
    for prim in stage.Traverse():
        if prim.GetName() in {"panda_finger_joint1", "panda_finger_joint2"}:
            drive = UsdPhysics.DriveAPI.Apply(prim, "linear")
            drive.CreateMaxForceAttr(config["finger_max_force_n"])
            drive.CreateStiffnessAttr(config["finger_stiffness"])
            drive.CreateDampingAttr(config["finger_damping"])
        if prim.HasAPI(UsdPhysics.CollisionAPI):
            collision = PhysxSchema.PhysxCollisionAPI.Apply(prim)
            collision.CreateContactOffsetAttr(config["contact_offset_m"])
            collision.CreateRestOffsetAttr(0)
    fingers = ["/World/Franka/panda_leftfinger", "/World/Franka/panda_rightfinger"]
    cap_path = str(cap.prim_path)
    contacts = RigidContactView(prim_paths_expr=fingers,
        filter_paths_expr=[[cap_path] for _ in fingers], name="cap_contacts", max_contact_count=128)
    arm = [str(p.GetPath()) for p in stage.Traverse()
           if str(p.GetPath()).startswith("/World/Franka/")
           and p.HasAPI(UsdPhysics.RigidBodyAPI) and p.GetName() != "panda_link0"]
    obstacles = [str(p.GetPath()) for p in stage.Traverse()
                 if str(p.GetPath()).startswith("/World/Device/Asset/")
                 and p.HasAPI(UsdPhysics.CollisionAPI) and str(p.GetPath()) != cap_path]
    device_contact = RigidContactView(prim_paths_expr=arm,
        filter_paths_expr=[obstacles for _ in arm], name="device_contact", max_contact_count=1024)
    table_contact = RigidContactView(prim_paths_expr=arm,
        filter_paths_expr=[["/World/Table"] for _ in arm], name="table_contact", max_contact_count=512)
    views = create_views(stage, config["camera_center_m"], config["camera_distance_m"])
    views["detail"] = create_detail_view(stage, device_position)
    world.reset()
    for contact in (contacts, device_contact, table_contact):
        contact.initialize()
    kp, kd = robot.get_articulation_controller().get_gains()
    kp[-2:], kd[-2:] = config["finger_stiffness"], config["finger_damping"]
    robot.get_articulation_controller().set_gains(kp, kd)
    for _ in range(120):
        world.step(render=True)
    initial, _ = cap.get_world_pose()
    print("CAP_INITIAL", initial.tolist(), "TARGET", targets["closed"].tolist(), flush=True)
    if np.linalg.norm(initial - targets["closed"]) > 0.002:
        raise RuntimeError("Cap does not seat in the source measurement opening")
    geometry["kinematic_enabled"] = bool(
        UsdPhysics.RigidBodyAPI(cap.prim).GetKinematicEnabledAttr().Get())
    geometry["initial_cap_position_m"] = initial.tolist()
    geometry["cap_joint_count"] = sum(
        cap_path in [str(target) for relation in ("physics:body0", "physics:body1")
                     for target in prim.GetRelationship(relation).GetTargets()]
        for prim in stage.Traverse() if prim.IsA(UsdPhysics.Joint))
    grip_offset = np.array([0, 0, config["grip_above_cap_bottom_m"]])
    motions = plan_cycle(scene["solver"], robot.get_joint_positions(),
                         targets["closed"] + grip_offset, targets["parked"] + grip_offset, config)
    (output / "plan.json").write_text(json.dumps({
        "config": config, "geometry": geometry,
        "targets_m": {k: v.tolist() for k, v in targets.items()},
        "phases": [{"name": m.name, "duration_s": m.duration, "aperture_m": m.aperture,
                    "joints_rad": m.joints.tolist()} for m in motions],
    }, indent=2))
    stage.GetRootLayer().Export(str(output / "scene.usda"))
    for name, view in views.items():
        Image.fromarray(read_rgb(view)).save(output / f"initial-{name}.png")
    recorder = VideoRecorder(output, views)
    records, error, step = [], None, 0
    dt, start = scene["dt"], world.current_time

    def forces(view):
        return np.linalg.norm(view.get_contact_force_matrix(dt=dt), axis=-1)

    try:
        for motion in motions:
            for i in range(round(motion.duration / dt)):
                fraction = (i + 1) * dt / motion.duration
                q = np.r_[sample_joints(motion.joints, fraction * fraction * (3 - 2 * fraction)),
                          motion.aperture, motion.aperture]
                robot.apply_action(ArticulationAction(joint_positions=q))
                world.step(render=False)
                position, rotation = cap.get_world_pose()
                record = {
                    "time_s": world.current_time - start, "phase": motion.name,
                    "joint_target": q.tolist(), "joint_actual": robot.get_joint_positions().tolist(),
                    "cap_position_m": position.tolist(), "cap_orientation_wxyz": rotation.tolist(),
                    "end_effector_m": scene["solver"].compute_end_effector_pose()[0].tolist(),
                    "finger_force_n": forces(contacts).ravel().tolist(),
                    "robot_device_force_n": float(forces(device_contact).max()),
                    "robot_table_force_n": float(forces(table_contact).max()),
                }
                records.append(record)
                if step % 4 == 0:
                    world.render()
                    recorder.write()
                step += 1
                if max(record["robot_device_force_n"], record["robot_table_force_n"]) > 5:
                    raise RuntimeError("Unexpected robot collision during " + motion.name)
            print("CAP_PHASE", motion.name, position.tolist(), record["finger_force_n"], flush=True)
            if motion.name in {"grasp_cap", "uncap", "parked_settle", "closed_settle"}:
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
            for record in records:
                stream.write(json.dumps(record) + "\n")
    expected = sum(round(m.duration / dt) for m in motions)
    checks = evaluate_cycle(records, targets, dt, expected, grip_offset)
    checks["no_runtime_error"] = error is None
    checks["started_seated_within_1mm"] = bool(
        np.linalg.norm(initial - targets["closed"]) < 0.001)
    checks["dynamic_cap_without_attachment_joint"] = bool(
        not geometry["kinematic_enabled"] and geometry["cap_joint_count"] == 0)
    checks["all_phases_completed"] = all(
        sum(r["phase"] == m.name for r in records) == round(m.duration / dt)
        for m in motions)
    result = {
        "asset_id": "diynafluor", "asset": get_asset("diynafluor"),
        "task": "uncap_park_recap", "success": all(checks.values()),
        "checks": checks, "error": error, "real_calibrated": False,
        "config": config, "geometry": geometry, "physics_dt_s": dt, "steps": step,
        "config_sha256": hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest(),
        "source_files_sha256": {
            part["file"]: hashlib.sha256((source.parent / part["file"]).read_bytes()).hexdigest()
            for part in get_asset("diynafluor")["parts"]},
        "duration_s": world.current_time - start,
        "phase_durations_s": {m.name: m.duration for m in motions},
        "targets_m": {k: v.tolist() for k, v in targets.items()},
        "source_code_sha256": {str(p.relative_to(CONFIG.parents[2])): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in [Path(__file__), CONFIG, Path(__file__).with_name("motion.py"),
                      Path(__file__).with_name("cameras.py"),
                      CONFIG.parents[2] / "demos/minimal_pick/scene.py",
                      CONFIG.parents[2] / "utils/cell_assets.py",
                      CONFIG.parents[2] / "assets/robots/Franka.usd"]},
        "limitations": [config["assumptions"], "No sample tube or fluorescence assay is simulated.",
                        "One fixed scene; not hardware calibration or robustness certification."],
    }
    (output / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New result directory; never overwritten")
    parser.add_argument("--cache", type=Path)
    parser.add_argument("--config", type=Path, default=CONFIG)
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    output = args.output.expanduser().resolve()
    if output.exists():
        parser.error(f"Output directory already exists: {output}")
    config = json.loads(args.config.read_text())
    fetch_asset("diynafluor", args.cache, offline=args.offline)
    from isaacsim import SimulationApp
    app = SimulationApp({"headless": True, "renderer": "RayTracedLighting",
                         "limit_cpu_threads": 8, "multi_gpu": False})
    code = 1
    try:
        result = run(output, args.cache, config)
        code = 0 if result["success"] else 1
        print("CAP_RESULT " + json.dumps(result, ensure_ascii=False), flush=True)
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
