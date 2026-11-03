"""Explicit passive gas-strut prototype; source geometry remains unmodified.

Each strut is an independent barrel/rod pair, with two spherical mounting joints
and a bounded prismatic joint. Forces act on the barrel and rod, never on the
hood's hinge coordinate. The closed loops are excluded from the articulation's
reduced-coordinate tree and solved as ordinary PhysX joints.
"""

import json
from pathlib import Path

import numpy as np


DEFAULT_CONFIG = Path(__file__).resolve().parents[1] / "config/cell_assets/ika_gas_springs.json"


def read_config(path=DEFAULT_CONFIG):
    return json.loads(Path(path).read_text())


def mount_geometry(config, hinge_origin):
    """Compute pin distances from declared mount frames, in metres."""
    values = config["assumptions"]
    origin = np.asarray(hinge_origin)
    base = np.array([0, *values["base_mount_yz_m"]])
    top = np.array([0, *values["hood_mount_yz_m"]])
    angle = values["maximum_hood_angle_rad"]
    c, s = np.cos(angle), np.sin(angle)
    rotation = np.array([[1, 0, 0], [0, c, s], [0, -s, c]])
    minimum = float(np.linalg.norm(origin + top - base))
    maximum = float(np.linalg.norm(origin + rotation @ top - base))
    if not 0 < maximum - minimum < values["barrel_length_m"]:
        raise ValueError("Declared gas-strut stroke does not fit its barrel")
    if values["barrel_length_m"] + values["rod_length_m"] - maximum < values["minimum_rod_insertion_m"]:
        raise ValueError("Piston rod loses required insertion at full extension")
    if values["rod_length_m"] >= minimum:
        raise ValueError("Piston rod protrudes through the base pin when closed")
    return minimum, maximum


def axial_force(values, length, speed, minimum, maximum):
    """Passive expanding gas force with compression progression and damping."""
    extension = np.clip((length - minimum) / (maximum - minimum), 0, 1)
    gas = values["extended_force_n"] * (1 + values["compression_progression"] * (1 - extension))
    return float(np.clip(gas - values["damping_ns_per_m"] * speed,
                         0, values["maximum_force_n"]))


class GasSpringPair:
    """Construct, initialize, and apply passive forces to two physical struts."""

    def __init__(self, stage, device_root, device_position, hinge_origin, config=None):
        from pxr import Gf, PhysxSchema, UsdGeom, UsdPhysics

        self.config = read_config() if config is None else config
        self.values = values = self.config["assumptions"]
        self.minimum, self.maximum = mount_geometry(self.config, hinge_origin)
        self.paths = []
        self.view = None
        self.stage = stage
        self.device_root = device_root
        device_position = np.asarray(device_position)
        hinge_origin = np.asarray(hinge_origin)

        # The source uses instanced collision meshes with centimetre-scale
        # default contact margins. Expose only these derived collision instances
        # so millimetre-clearance struts are not blocked before actual contact.
        source_instances = [prim for prim in stage.Traverse()
                            if str(prim.GetPath()).startswith(device_root + "/")
                            and prim.GetName() == "collisions" and prim.IsInstance()]
        for prim in source_instances:
            prim.SetInstanceable(False)
        for prim in stage.Traverse():
            if (str(prim.GetPath()).startswith(device_root + "/")
                    and prim.HasAPI(UsdPhysics.CollisionAPI)):
                collision = PhysxSchema.PhysxCollisionAPI.Apply(prim)
                collision.CreateRestOffsetAttr(0.)
                collision.CreateContactOffsetAttr(0.0005)

        def body(path, position, rotation, length, radius, mass, center_z, color):
            prim = UsdGeom.Xform.Define(stage, path).GetPrim()
            transform = UsdGeom.Xformable(prim)
            transform.AddTranslateOp().Set(Gf.Vec3d(*position))
            transform.AddOrientOp().Set(Gf.Quatf(rotation.GetReal(), Gf.Vec3f(rotation.GetImaginary())))
            UsdPhysics.RigidBodyAPI.Apply(prim)
            mass_api = UsdPhysics.MassAPI.Apply(prim)
            mass_api.CreateMassAttr(mass)
            mass_api.CreateCenterOfMassAttr(Gf.Vec3f(0, 0, center_z))
            inertia = (mass * (3 * radius * radius + length * length) / 12,
                       mass * (3 * radius * radius + length * length) / 12,
                       mass * radius * radius / 2)
            mass_api.CreateDiagonalInertiaAttr(Gf.Vec3f(*inertia))
            physics = PhysxSchema.PhysxRigidBodyAPI.Apply(prim)
            physics.CreateSolverPositionIterationCountAttr(32)
            physics.CreateSolverVelocityIterationCountAttr(8)
            physics.CreateEnableCCDAttr(True)
            geometry = UsdGeom.Cylinder.Define(stage, path + "/Tube")
            geometry.CreateAxisAttr("Z")
            geometry.CreateHeightAttr(length)
            geometry.CreateRadiusAttr(radius)
            geometry.AddTranslateOp().Set(Gf.Vec3d(0, 0, center_z))
            geometry.CreateDisplayColorAttr([Gf.Vec3f(*color)])
            UsdPhysics.CollisionAPI.Apply(geometry.GetPrim())
            collision = PhysxSchema.PhysxCollisionAPI.Apply(geometry.GetPrim())
            collision.CreateRestOffsetAttr(0.)
            collision.CreateContactOffsetAttr(0.0005)
            eye = UsdGeom.Sphere.Define(stage, path + "/Eye")
            eye.CreateRadiusAttr(0.01)
            eye.CreateDisplayColorAttr([Gf.Vec3f(0.18, 0.18, 0.19)])
            self.paths.append(path)

        def connect(joint, parent, child, parent_pin=(0, 0, 0), child_pin=(0, 0, 0)):
            joint.CreateBody0Rel().SetTargets([parent])
            joint.CreateBody1Rel().SetTargets([child])
            joint.CreateLocalPos0Attr(Gf.Vec3f(*parent_pin))
            joint.CreateLocalPos1Attr(Gf.Vec3f(*child_pin))
            joint.CreateExcludeFromArticulationAttr(True)
            joint.CreateCollisionEnabledAttr(False)

        def bracket(link, side, pin):
            wall = np.sign(pin[0]) * values["wall_attachment_x_m"]
            shape = UsdGeom.Cube.Define(stage, device_root + "/" + link + "/GasSpringBracket" + side)
            shape.CreateSizeAttr(1.)
            shape.AddTranslateOp().Set(Gf.Vec3d((wall + pin[0]) / 2, pin[1], pin[2]))
            shape.AddScaleOp().Set(Gf.Vec3d(abs(wall - pin[0]), 0.015, 0.015))
            shape.CreateDisplayColorAttr([Gf.Vec3f(0.3, 0.32, 0.34)])
            UsdPhysics.CollisionAPI.Apply(shape.GetPrim())
            collision = PhysxSchema.PhysxCollisionAPI.Apply(shape.GetPrim())
            collision.CreateRestOffsetAttr(0.)
            collision.CreateContactOffsetAttr(0.0005)

        for side, x in zip(("Left", "Right"), values["mount_x_m"]):
            root = "/World/GasSpring" + side
            UsdGeom.Xform.Define(stage, root)
            base = np.array([x, *values["base_mount_yz_m"]])
            top_local = np.array([x, *values["hood_mount_yz_m"]])
            bracket("housing", side, base)
            bracket("hood", side, top_local)
            start = device_position + base
            end = device_position + hinge_origin + top_local
            axis = (end - start) / np.linalg.norm(end - start)
            rotation = Gf.Rotation(Gf.Vec3d(0, 0, 1), Gf.Vec3d(*axis)).GetQuat()
            barrel, rod = root + "/Barrel", root + "/Rod"
            body(barrel, start, rotation, values["barrel_length_m"],
                 values["barrel_radius_m"], values["barrel_mass_kg"],
                 values["barrel_length_m"] / 2, (0.06, 0.065, 0.07))
            body(rod, end, rotation, values["rod_length_m"], values["rod_radius_m"],
                 values["rod_mass_kg"], -values["rod_length_m"] / 2, (0.6, 0.63, 0.65))
            base_joint = UsdPhysics.SphericalJoint.Define(stage, root + "/BasePin")
            connect(base_joint, device_root + "/housing", barrel, base)
            top_joint = UsdPhysics.SphericalJoint.Define(stage, root + "/HoodPin")
            connect(top_joint, rod, device_root + "/hood", child_pin=top_local)
            slide = UsdPhysics.PrismaticJoint.Define(stage, root + "/Piston")
            connect(slide, barrel, rod, parent_pin=(0, 0, self.minimum))
            slide.CreateAxisAttr("Z")
            slide.CreateLowerLimitAttr(0.)
            slide.CreateUpperLimitAttr(self.maximum - self.minimum)

    def export_asset(self, path):
        """Save composed mechanism geometry; gas force still requires step()."""
        from pxr import Usd, UsdGeom
        path = Path(path)
        if path.exists():
            raise FileExistsError(path)
        asset = Usd.Stage.Open(self.stage.Flatten())
        keep = {self.device_root.rsplit("/", 1)[0], "/World/GasSpringLeft", "/World/GasSpringRight"}
        for child in list(asset.GetPrimAtPath("/World").GetChildren()):
            if str(child.GetPath()) not in keep:
                asset.RemovePrim(child.GetPath())
        # Resolve retained instance references before dropping flattened prototypes.
        for prim in list(asset.Traverse()):
            if str(prim.GetPath()).startswith("/World/") and prim.IsInstance():
                prim.SetInstanceable(False)
        asset = Usd.Stage.Open(asset.Flatten())
        for child in list(asset.GetPseudoRoot().GetChildren()):
            if str(child.GetPath()) != "/World":
                asset.RemovePrim(child.GetPath())
        asset.SetDefaultPrim(asset.GetPrimAtPath("/World"))
        UsdGeom.SetStageUpAxis(asset, UsdGeom.Tokens.z)
        UsdGeom.SetStageMetersPerUnit(asset, 1.)
        asset.GetRootLayer().customLayerData = {
            "gas_force_runtime": "utils.ika_gas_springs.GasSpringPair.step at each physics tick",
            "real_calibrated": False,
            "configuration_json": json.dumps(self.config),
        }
        for prim in asset.Traverse():
            for relation in prim.GetRelationships():
                if relation.GetName() in {"physics:body0", "physics:body1", "material:binding"}:
                    for target in relation.GetTargets():
                        if not asset.GetPrimAtPath(target):
                            raise RuntimeError(f"Export contains a broken relationship: {relation.GetPath()} -> {target}")
        if not any(p.IsA(UsdGeom.Mesh) for p in asset.Traverse()):
            raise RuntimeError("Export contains no source meshes")
        asset.GetRootLayer().Export(str(path))

    def initialize(self):
        from isaacsim.core.prims import RigidPrim
        self.view = RigidPrim(prim_paths_expr=self.paths, name="gas_spring_bodies")
        self.view.initialize()
        if self.view.count != 4:
            raise RuntimeError("Expected four independent gas-strut rigid bodies")

    def step(self):
        """Apply equal and opposite axial gas/damping forces; return telemetry."""
        if self.view is None:
            raise RuntimeError("Initialize gas springs after World.reset()")
        positions, _ = self.view.get_world_poses()
        velocities = self.view.get_velocities()
        forces = np.zeros((4, 3), dtype=np.float32)
        telemetry = []
        for index in (0, 2):
            delta = positions[index + 1] - positions[index]
            length = float(np.linalg.norm(delta))
            direction = delta / length
            speed = float(np.dot(velocities[index + 1, :3] - velocities[index, :3], direction))
            force = axial_force(self.values, length, speed, self.minimum, self.maximum)
            forces[index], forces[index + 1] = -force * direction, force * direction
            telemetry.append({"length_m": length, "extension_speed_m_s": speed,
                              "axial_force_n": force})
        self.view.apply_forces_and_torques_at_pos(forces=forces, positions=positions, is_global=True)
        return telemetry
