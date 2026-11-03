"""A physical small-tube insertion unit in a clearly labelled derived PCR block.

The source instrument has textured wells on a solid block. This task replaces
that region with explicit blind pockets; it does not assert factory dimensions.
"""

import json

import numpy as np
import trimesh

from demos.cell_units.registry import ROOT
from demos.cell_assets.cameras import create_views, read_rgb
from demos.cell_assets.handling import plan_handling
from utils.cell_assets import convert_asset, load_asset

CONFIG = ROOT / "config/cell_units/pcr_insert.json"


def pocket_mesh(config):
    """Closed square cell with a cylindrical throat, tapered bottom and floor."""
    n = 32
    angle = np.arange(n) * 2 * np.pi / n
    xy = np.c_[np.cos(angle), np.sin(angle)]
    square = xy * (config["pitch_m"] / 2 / abs(xy).max(1))[:, None]
    depth = config["hole_depth_m"]
    rings = [
        (square, 0),
        (xy * config["hole_radius_m"], 0),
        (xy * config["hole_radius_m"], -config["hole_straight_depth_m"]),
        (xy * config["hole_bottom_radius_m"], -depth),
    ]
    vertices = [np.c_[ring, np.full(n, z)] for ring, z in rings]
    vertices.append(np.c_[square, np.full(n, -depth - 0.002)])
    vertices = np.concatenate(vertices).tolist() + [[0, 0, -depth], [0, 0, -depth - 0.002]]
    faces = []
    for a, b in ((0, 1), (1, 2), (2, 3), (4, 0)):
        for i in range(n):
            j = (i + 1) % n
            faces += [[a * n + i, a * n + j, b * n + j], [a * n + i, b * n + j, b * n + i]]
    for i in range(n):
        j = (i + 1) % n
        faces += [[3 * n + i, 3 * n + j, 5 * n], [4 * n + j, 4 * n + i, 5 * n + 1]]
    mesh = trimesh.Trimesh(vertices, faces, process=True)
    trimesh.repair.fix_normals(mesh)
    if not mesh.is_watertight or mesh.volume <= 0:
        raise ValueError("Pocket must have closed walls and a floor")
    return mesh


def outside_box(mesh, lower, upper):
    """Trim source surfaces only inside the inserted block's recess."""
    pieces, remaining = [], mesh
    for axis in range(3):
        for sign, bound in ((1, lower[axis]), (-1, upper[axis])):
            normal = np.eye(3)[axis] * sign
            point = np.eye(3)[axis] * bound
            outside = remaining.slice_plane(point, -normal)
            if len(outside.faces):
                pieces.append(outside)
            remaining = remaining.slice_plane(point, normal)
    return trimesh.util.concatenate(pieces)


def subtract_box(center, size, lower, upper):
    """Disjoint box pieces outside an axis-aligned recess (no disabled contact)."""
    lo, hi = np.array(center) - np.array(size) / 2, np.array(center) + np.array(size) / 2
    if np.any(hi <= lower) or np.any(lo >= upper):
        return [(center, size)]
    pieces = []
    for axis in range(3):
        if lo[axis] < lower[axis]:
            end = hi.copy()
            end[axis] = lower[axis]
            pieces.append(((lo + end) / 2, end - lo))
            lo[axis] = lower[axis]
        if hi[axis] > upper[axis]:
            start = lo.copy()
            start[axis] = upper[axis]
            pieces.append(((start + hi) / 2, hi - start))
            hi[axis] = upper[axis]
    return pieces


def write_mesh(stage, path, shape, color, collision=True):
    from pxr import Gf, UsdGeom, UsdPhysics, Vt

    mesh = UsdGeom.Mesh.Define(stage, path)
    mesh.CreatePointsAttr(Vt.Vec3fArray.FromNumpy(shape.vertices.astype(np.float32)))
    mesh.CreateFaceVertexCountsAttr([3] * len(shape.faces))
    mesh.CreateFaceVertexIndicesAttr(shape.faces.ravel().tolist())
    mesh.CreateSubdivisionSchemeAttr("none")
    mesh.CreateDisplayColorAttr([Gf.Vec3f(*color)])
    if collision:
        UsdPhysics.CollisionAPI.Apply(mesh.GetPrim())
        UsdPhysics.MeshCollisionAPI.Apply(mesh.GetPrim()).CreateApproximationAttr("none")
    return mesh


def _carve_block_recess(stage, offset, center):
    """Trim only the derived block recess; return modified source collider paths."""
    from pxr import Gf, Usd, UsdGeom, UsdPhysics

    lower, upper = center + [-0.061, -0.043, -0.032], center + [0.061, 0.043, 0.020]
    modified = []
    # Replace visual and collision geometry together, only in the working USD.
    for name in ("chassis", "deck", "lid_rails", "sample_block", "block_wells"):
        root = stage.GetPrimAtPath("/World/Device/Asset/" + name)
        for prim in list(UsdGeom.Imageable(root).GetPrim().GetChildren()):
            if prim.GetName() == "visuals" and name in ("sample_block", "block_wells"):
                UsdGeom.Imageable(prim).MakeInvisible()
        for prim in list(Usd.PrimRange(root)):
            if (
                prim.IsA(UsdGeom.Mesh)
                and "/visuals/" in str(prim.GetPath())
                and name in ("chassis", "deck")
            ):
                mesh = UsdGeom.Mesh(prim)
                shape = trimesh.Trimesh(
                    np.asarray(mesh.GetPointsAttr().Get()),
                    np.asarray(mesh.GetFaceVertexIndicesAttr().Get()).reshape(-1, 3),
                    process=False,
                )
                cut = outside_box(shape, lower, upper)
                write_mesh(stage, str(prim.GetPath()), cut, [0.25, 0.25, 0.27], collision=False)
            if prim.HasAPI(UsdPhysics.CollisionAPI):
                path = str(prim.GetPath())
                if name in ("sample_block", "block_wells"):
                    prim.SetActive(False)
                elif prim.IsA(UsdGeom.Cube):
                    matrix = np.array(
                        UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(Usd.TimeCode.Default())
                    ).T
                    size = abs(matrix[:3, :3]).sum(1) * float(
                        UsdGeom.Cube(prim).GetSizeAttr().Get()
                    )
                    position = matrix[:3, 3] - offset
                    parts = subtract_box(position, size, lower, upper)
                    prim.SetActive(False)
                    for index, (point, extent) in enumerate(parts):
                        cube = UsdGeom.Cube.Define(
                            stage, str(root.GetPath()) + f"/unit_recess_{len(modified)}_{index}"
                        )
                        cube.CreateSizeAttr(1)
                        xf = UsdGeom.Xformable(cube)
                        xf.AddTranslateOp().Set(Gf.Vec3d(*point))
                        xf.AddScaleOp().Set(Gf.Vec3f(*extent))
                        UsdPhysics.CollisionAPI.Apply(cube.GetPrim())
                        cube.CreateVisibilityAttr("invisible")
                modified.append(path)
    return modified


def _teacher_controller(scene, tube, grip, properties):
    """Create expert-only insertion feedback; policies use the shared executor."""
    from scipy.spatial.transform import Rotation
    from demos.cell_units.kinematics import solve_step

    release_pose = None
    release_joints = None
    commanded_joints = None
    robot, solver = scene["robot"], scene["solver"]
    kin, frame = solver.get_kinematics_solver(), solver.get_end_effector_frame()

    def teacher_control(q, phase, blend):
        """Expert-only tube alignment; policies never receive object poses."""
        nonlocal release_pose, release_joints, commanded_joints
        if phase not in {"enter", "place", "release", "withdraw", "loaded_settle"}:
            return q
        current = robot.get_joint_positions()[:7].astype(float)
        forward = lambda joints: kin.compute_forward_kinematics(frame, joints)
        point, matrix = forward(current)
        rotation = Rotation.from_matrix(matrix)
        if commanded_joints is None:
            commanded_joints = current
        if phase == "release":
            if release_pose is None:
                release_pose, release_joints = (point, rotation), current
            return np.r_[release_joints, q[-2:]]
        if phase in {"enter", "place"}:
            nominal, _ = forward(q[:7])
            tube_position, tube_quaternion = tube.get_world_pose()
            goal = nominal - grip + (point - tube_position)
            tube_rotation = Rotation.from_quat(np.roll(tube_quaternion, -1))
            target_rotation = tube_rotation.inv() * rotation
        else:
            goal = release_pose[0] + [0, 0, 0.16 * (blend if phase == "withdraw" else 1)]
            target_rotation = release_pose[1]
        command_point, command_matrix = forward(commanded_joints)
        command_rotation = Rotation.from_matrix(command_matrix)
        delta = goal - command_point
        delta *= min(1.0, 0.06 * scene["dt"] / max(np.linalg.norm(delta), 1e-12))
        angle = (target_rotation * command_rotation.inv()).as_rotvec()
        angle *= min(1.0, 0.24 * scene["dt"] / max(np.linalg.norm(angle), 1e-12))
        joints, ok, detail = solve_step(
            forward,
            commanded_joints,
            command_point + delta,
            Rotation.from_rotvec(angle) * command_rotation,
            properties["lower"][:7],
            properties["upper"][:7],
            np.array([2.175] * 4 + [2.61] * 3) * scene["dt"],
        )
        if not ok:
            raise RuntimeError(f"PCR expert alignment rejected: {detail}")
        commanded_joints = joints
        return np.r_[joints, q[-2:]]

    return teacher_control


def build(output, cache, driver):
    """Build the derived PCR scene and pass it to the unit driver.

    Args:
        output: New episode directory for derived USD, images and geometry evidence.
        cache: Original source-asset cache; it is never modified.
        driver: Callback accepting the common cell_assets scene bindings.

    Returns:
        The driver return value. All dimensions and uncalibrated assumptions are
        recorded from config/cell_units/pcr_insert.json.
    """
    from PIL import Image
    from pxr import Gf, PhysxSchema, UsdGeom, UsdPhysics, UsdShade
    from isaacsim.core.prims import SingleArticulation, SingleRigidPrim
    from isaacsim.core.api.sensors import RigidContactView
    from demos.minimal_pick.scene import build_scene
    from demos.cell_assets.cap_cycle import create_detail_view

    cfg = json.loads(CONFIG.read_text())
    output.mkdir(parents=True)
    usd = convert_asset(cfg["asset_id"], output / "device-usd", cache)
    scene = build_scene()
    world, stage, robot = scene["world"], scene["stage"], scene["robot"]
    world.stop()
    scene["dt"] = 1 / cfg["physics_hz"]
    world.set_simulation_dt(physics_dt=scene["dt"], rendering_dt=1 / 60)
    world.scene.remove_object("beaker")
    base = np.array(cfg["robot_base_m"])
    robot.set_world_pose(position=base)
    robot.set_default_state(position=base)
    scene["solver"].get_kinematics_solver().set_robot_base_pose(base, np.array([1.0, 0, 0, 0]))
    world.scene.get_object("table").set_local_scale(np.array([1.4, 1.6, 0.08]))
    world.scene.get_object("table").set_world_pose(position=np.array([0.05, 0.25, 0.7]))
    offset = np.array(cfg["device_position_m"])
    load_asset(usd, "/World/Device", offset)
    device = world.scene.add(SingleArticulation(prim_path="/World/Device/Asset", name="pcr"))
    for prim in list(stage.Traverse()):
        if prim.IsInstance():
            prim.SetInstanceable(False)
    center = np.array(cfg["block_center_local_m"])
    modified = _carve_block_recess(stage, offset, center)
    cell = pocket_mesh(cfg)
    cells = []
    for row in range(cfg["rows"]):
        for column in range(cfg["columns"]):
            part = cell.copy()
            part.apply_translation(
                offset
                + center
                + [
                    (column - (cfg["columns"] - 1) / 2) * cfg["pitch_m"],
                    (row - (cfg["rows"] - 1) / 2) * cfg["pitch_m"],
                    0,
                ]
            )
            cells.append(part)
    write_mesh(
        stage, "/World/PCRBlock", trimesh.util.concatenate(cells), [0.55, 0.57, 0.59]
    )
    # Empty space below the pockets is filled, preserving the source block depth.
    from isaacsim.core.api.objects import FixedCuboid

    world.scene.add(
        FixedCuboid(
            prim_path="/World/BlockBase",
            name="block_base",
            position=offset + center + [0, 0, -0.024],
            scale=np.array([0.122, 0.086, 0.015]),
            color=np.array([0.45, 0.47, 0.49]),
        )
    )
    target_top = (
        offset
        + center
        + [
            (cfg["target_column"] - (cfg["columns"] - 1) / 2) * cfg["pitch_m"],
            (cfg["target_row"] - (cfg["rows"] - 1) / 2) * cfg["pitch_m"],
            0,
        ]
    )
    holder_top = np.r_[cfg["pickup_xy_m"], cfg["holder_top_m"]]
    holder = cell.copy()
    holder.apply_translation(holder_top)
    write_mesh(stage, "/World/TubeHolder", holder, [0.12, 0.22, 0.3])
    world.scene.add(
        FixedCuboid(
            prim_path="/World/HolderBase",
            name="holder_base",
            position=holder_top + [0, 0, -0.023],
            scale=np.array([0.03, 0.03, 0.014]),
            color=np.array([0.12, 0.22, 0.3]),
        )
    )
    body = UsdGeom.Xform.Define(stage, "/World/Tube").GetPrim()
    profile = np.array(
        [
            [0, 0],
            [cfg["tube_tip_radius_m"], 0],
            [cfg["tube_radius_m"], cfg["tube_cone_height_m"]],
            [cfg["tube_radius_m"], cfg["tube_body_height_m"]],
            [0, cfg["tube_body_height_m"]],
        ]
    )
    tube_shape = trimesh.creation.revolve(profile, sections=32)
    mesh = write_mesh(stage, "/World/Tube/Body", tube_shape, [0.75, 0.88, 0.86])
    UsdPhysics.MeshCollisionAPI(mesh.GetPrim()).CreateApproximationAttr("convexHull")
    cap = trimesh.creation.cylinder(
        radius=cfg["cap_radius_m"], height=cfg["cap_height_m"], sections=32
    )
    cap.apply_translation([0, 0, cfg["tube_body_height_m"] + cfg["cap_height_m"] / 2])
    mesh = write_mesh(stage, "/World/Tube/Cap", cap, [0.08, 0.45, 0.8])
    UsdPhysics.MeshCollisionAPI(mesh.GetPrim()).CreateApproximationAttr("convexHull")
    pickup = holder_top - [0, 0, cfg["hole_depth_m"] - 0.0002]
    tube = world.scene.add(
        SingleRigidPrim(
            prim_path="/World/Tube", name="tube", position=pickup, mass=cfg["tube_mass_kg"]
        )
    )
    material = UsdShade.Material.Define(stage, "/World/TubeFriction")
    mat = UsdPhysics.MaterialAPI.Apply(material.GetPrim())
    mat.CreateStaticFrictionAttr(0.7)
    mat.CreateDynamicFrictionAttr(0.6)
    mat.CreateRestitutionAttr(0)
    UsdShade.MaterialBindingAPI.Apply(body).Bind(material, materialPurpose="physics")
    for path in (
        "/World/Tube/Body",
        "/World/Tube/Cap",
        "/World/Franka/panda_leftfinger/geometry/panda_leftfinger",
        "/World/Franka/panda_rightfinger/geometry/panda_rightfinger",
    ):
        UsdShade.MaterialBindingAPI.Apply(stage.GetPrimAtPath(path)).Bind(
            material, materialPurpose="physics"
        )
    rb = PhysxSchema.PhysxRigidBodyAPI.Apply(body)
    rb.CreateEnableCCDAttr(True)
    rb.CreateSolverPositionIterationCountAttr(128)
    rb.CreateSolverVelocityIterationCountAttr(32)
    rb.CreateMaxDepenetrationVelocityAttr(0.05)
    for prim in stage.Traverse():
        if prim.HasAPI(UsdPhysics.CollisionAPI):
            phys = PhysxSchema.PhysxCollisionAPI.Apply(prim)
            phys.CreateContactOffsetAttr(cfg["contact_offset_m"])
            phys.CreateRestOffsetAttr(0)
    fingers = ["/World/Franka/panda_leftfinger", "/World/Franka/panda_rightfinger"]
    arms = [
        str(p.GetPath())
        for p in stage.Traverse()
        if str(p.GetPath()).startswith("/World/Franka/")
        and p.HasAPI(UsdPhysics.RigidBodyAPI)
        and p.GetName() != "panda_link0"
    ]
    obstacles = [
        str(p.GetPath())
        for p in stage.Traverse()
        if str(p.GetPath()).startswith("/World/Device/Asset/") and p.HasAPI(UsdPhysics.RigidBodyAPI)
    ] + ["/World/PCRBlock", "/World/BlockBase", "/World/TubeHolder", "/World/HolderBase"]

    def sensor(name, paths, filters):
        return RigidContactView(
            prim_paths_expr=paths,
            filter_paths_expr=[filters] * len(paths),
            name=name,
            max_contact_count=2048,
        )

    contacts = sensor("tube_fingers", fingers, ["/World/Tube"])
    robot_device = sensor("robot_device", arms, obstacles)
    robot_table = sensor("robot_table", arms, ["/World/Table"])
    support = sensor("tube_support", ["/World/Tube"], ["/World/PCRBlock"])
    views = create_views(stage, [0.07, 0.12, 1.04], 1.5)
    views["detail"] = create_detail_view(stage, target_top)
    world.reset()
    lid = device.get_dof_index("lid_joint")
    from isaacsim.core.utils.types import ArticulationAction

    q = device.get_joint_positions()
    q[lid] = 0.232
    device.set_joint_positions(q)
    device.apply_action(ArticulationAction(joint_positions=q))
    kp, kd = robot.get_articulation_controller().get_gains()
    kp[-2:] = 200
    kd[-2:] = 20
    robot.get_articulation_controller().set_gains(kp, kd)
    from isaacsim.core.prims import Articulation

    robot_view = Articulation(prim_paths_expr="/World/Franka")
    robot_view.initialize()
    robot_view.set_max_efforts(
        np.array([[cfg["finger_max_force_n"]] * 2]), joint_indices=np.array([7, 8])
    )
    for view in (contacts, robot_device, robot_table, support):
        view.initialize()
    for _ in range(cfg["physics_hz"]):
        world.step(render=True)
    initial = tube.get_world_pose()[0]
    target = target_top - [0, 0, cfg["hole_depth_m"]]
    grip = np.array([0, 0, cfg["grip_height_m"]])
    from functools import partial
    from demos.cell_units.kinematics import cartesian_path

    properties = robot.dof_properties
    precise_path = partial(
        cartesian_path, lower=properties["lower"][:7], upper=properties["upper"][:7]
    )
    motions = plan_handling(
        scene["solver"],
        robot.get_joint_positions(),
        initial + grip,
        target + grip,
        dict(
            gripper_yaw_deg=0, lift_m=0.16, entry_offset_m=[0, -0.05, 0], approach_aperture_m=0.012
        ),
        path_solver=precise_path,
    )
    for motion in motions:
        if motion.aperture == 0:
            motion.aperture = cfg["grasp_aperture_m"]
        if motion.name == "place":
            motion.duration = 6
        if motion.name == "withdraw":
            motion.duration = 5
    stage.GetRootLayer().Export(str(output / "scene.usda"))
    metadata = dict(
        config=cfg,
        source_asset="biorad_cfxopus",
        modified_collision_paths=modified,
        hole_count=cfg["rows"] * cfg["columns"],
        target_top_m=target_top.tolist(),
        target_bottom_m=target.tolist(),
        source_cache_modified=False,
        tube_attachment_joints=[],
        lid_initially_open=True,
        expert_object_feedback=True,
    )
    (output / "geometry.json").write_text(json.dumps(metadata, indent=2))
    for name, view in views.items():
        Image.fromarray(read_rgb(view)).save(output / f"initial-{name}.png")

    def force(view):
        return np.linalg.norm(view.get_contact_force_matrix(dt=scene["dt"]), axis=-1)

    def measure(q, phase, start):
        pos, rot = tube.get_world_pose()
        row = dict(
            time_s=world.current_time - start,
            phase=phase,
            joint_target=q.tolist(),
            joint_actual=robot.get_joint_positions().tolist(),
            position_m=pos.tolist(),
            orientation_wxyz=rot.tolist(),
            end_effector_m=scene["solver"].compute_end_effector_pose()[0].tolist(),
            finger_force_n=force(contacts).ravel().tolist(),
            robot_device_force_n=float(force(robot_device).max()),
            robot_table_force_n=float(force(robot_table).max()),
            payload_device_force_n=float(force(support).sum()),
            insertion_depth_m=float(target_top[2] - pos[2]),
        )
        if row["robot_device_force_n"] > 0.1:
            i, j = np.unravel_index(force(robot_device).argmax(), force(robot_device).shape)
            row["robot_device_contact_pair"] = [arms[i], obstacles[j]]
        return row

    teacher_control = _teacher_controller(scene, tube, grip, properties)

    return driver(
        scene=scene,
        views=views,
        motions=motions,
        measure=measure,
        targets=dict(loaded=target, returned=initial, hole_top=target_top),
        grip_offset=grip,
        metadata=metadata,
        contact=contacts,
        teacher_control=teacher_control,
    )
