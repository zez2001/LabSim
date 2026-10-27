"""Versioned external device assets for LabSim.

Catalog and download operations work without Isaac. Import and load operations
require an existing Isaac Sim 5.1 SimulationApp; they do not create one.
Source geometry lives in the ignored local_assets directory and is never rewritten.
"""

import hashlib
import json
import math
import os
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET
import zipfile


CATALOG_PATH = Path(__file__).resolve().parents[1] / "config/cell_assets/catalog.json"


def list_assets() -> list[dict]:
    """Return registered device metadata; registration does not imply validation."""
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))["assets"]


def get_asset(asset_id: str) -> dict:
    """Return an asset's metadata, or raise KeyError for an unknown identifier."""
    for asset in list_assets():
        if asset["asset_id"] == asset_id:
            return asset
    raise KeyError(f"Unknown device asset: {asset_id}")


def asset_cache(cache_root: str | Path | None = None) -> Path:
    """Resolve an explicit cache, environment override, or project local_assets."""
    location = cache_root or os.environ.get("LABSIM_ASSET_CACHE")
    return (
        Path(location).expanduser().resolve()
        if location
        else Path(__file__).resolve().parents[1] / "local_assets"
    )


def fetch_asset(
    asset_id: str,
    cache_root: str | Path | None = None,
    *,
    offline: bool = False,
) -> Path:
    """Fetch pinned source geometry and attribution, returning the entry file.

    Args:
        asset_id: Identifier from list_assets().
        cache_root: External cache directory, never an environment directory.
        offline: Inspect local files without contacting the source provider.

    Raises:
        KeyError: Unknown asset identifier.
        FileNotFoundError: Required local source files are missing.
        ValueError: Entry hash, mesh reference, or license metadata is invalid.
        OSError: Download or filesystem failure. Hub exceptions retain context.
    """
    asset = get_asset(asset_id)
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    source = catalog["sources"][asset["source"]]
    root = asset_cache(cache_root) / asset["source"] / source["revision"]
    if not offline:
        if source["provider"] == "github":
            _fetch_pinned_files(source, root)
        elif source["provider"] == "huggingface":
            from huggingface_hub import snapshot_download

            snapshot_download(
                source["repo_id"],
                repo_type="dataset",
                revision=source["revision"],
                local_dir=root,
                allow_patterns=[asset["source_directory"] + "/*", *source["notice_files"]],
                max_workers=4,
            )
        else:
            raise ValueError(f"Unsupported source provider: {source['provider']}")
    entry = root / asset["source_directory"] / asset["entry_file"]
    if not entry.is_file():
        raise FileNotFoundError(
            f"Asset is not cached: {entry}; call fetch_asset without offline=True"
        )
    if hashlib.sha256(entry.read_bytes()).hexdigest() != asset["entry_sha256"]:
        raise ValueError(f"Source entry differs from the pinned catalog: {entry}")
    for name, digest in source.get("files_sha256", {}).items():
        path = root / name
        if not path.is_file():
            raise FileNotFoundError(f"Missing pinned source file: {path}")
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError(f"Source file differs from the pinned catalog: {path}")
    _extract_source_members(source, root, offline=offline)
    for name in source["notice_files"]:
        if not (root / name).is_file():
            raise FileNotFoundError(f"Missing source attribution file: {root / name}")
    if asset.get("format", "urdf") == "urdf":
        validate_urdf_files(entry)
    return entry


def _fetch_pinned_files(source: dict, root: Path) -> None:
    """Download pinned source URLs with hash checks and atomic writes."""
    for name, digest in source["files_sha256"].items():
        target = (root / name).resolve()
        if not target.is_relative_to(root.resolve()):
            raise ValueError(f"Source filename escapes its cache: {name}")
        if target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest() == digest:
            continue
        url = source.get("file_urls", {}).get(name) or (
            f"https://raw.githubusercontent.com/{source['repo_id']}/"
            f"{source['revision']}/{quote(name)}"
        )
        with urlopen(Request(url, headers={"User-Agent": "LabSim-assets"}), timeout=30) as response:
            data = response.read()
        if hashlib.sha256(data).hexdigest() != digest:
            raise ValueError(f"Downloaded content does not match the pinned hash: {name}")
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + ".part")
        try:
            temporary.write_bytes(data)
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)


def _extract_source_members(source: dict, root: Path, *, offline: bool) -> None:
    """Extract only hash-pinned ZIP members; offline mode validates without writes."""
    for archive_name, members in source.get("zip_members_sha256", {}).items():
        archive_path = (root / archive_name).resolve()
        if not archive_path.is_relative_to(root.resolve()):
            raise ValueError(f"Archive filename escapes its cache: {archive_name}")
        with zipfile.ZipFile(archive_path) as archive:
            for member, digest in members.items():
                target = (root / member).resolve()
                if not target.is_relative_to(root.resolve()):
                    raise ValueError(f"Archive member escapes its cache: {member}")
                if target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest() == digest:
                    continue
                if offline:
                    raise ValueError(f"Missing or changed extracted source file: {target}")
                info = archive.getinfo(member)
                if info.is_dir() or info.file_size > 32 * 1024 * 1024:
                    raise ValueError(f"Invalid or oversized source archive member: {member}")
                data = archive.read(info)
                if hashlib.sha256(data).hexdigest() != digest:
                    raise ValueError(f"Archive member differs from the pinned hash: {member}")
                target.parent.mkdir(parents=True, exist_ok=True)
                temporary = target.with_name(target.name + ".part")
                try:
                    temporary.write_bytes(data)
                    temporary.replace(target)
                finally:
                    temporary.unlink(missing_ok=True)


def validate_urdf_files(entry: Path) -> None:
    """Check the source joint tree and local mesh/texture dependencies.

    A valid tree does not certify the mechanism against the physical instrument.
    Source-specific approximations still require review before admission.
    """
    root = entry.parent.resolve()
    document = ET.parse(entry).getroot()
    if document.tag != "robot" or not document.findall("link"):
        raise ValueError(f"Not a robot/device URDF: {entry}")
    _validate_urdf_topology(document)
    for node in [*document.findall(".//mesh"), *document.findall(".//texture")]:
        filename = node.get("filename", "")
        target = (root / filename).resolve()
        if not filename or not target.is_relative_to(root):
            raise ValueError(f"Asset reference escapes its source directory: {filename!r}")
        if not target.is_file():
            raise FileNotFoundError(f"Missing URDF dependency: {target}")
        with target.open("rb") as stream:
            if stream.read(80).startswith(b"version https://git-lfs.github.com/spec/v1"):
                raise ValueError(f"Unresolved Git LFS pointer: {target}")


def _validate_urdf_topology(document: ET.Element) -> None:
    """Reject broken trees, invalid joint frames and unusable motion axes."""
    names = [link.get("name") for link in document.findall("link")]
    if any(not name for name in names) or len(names) != len(set(names)):
        raise ValueError("URDF link names must be nonempty and unique")
    links = set(names)
    parents = {}
    joint_names = set()

    def vector(node, attribute, default):
        value = [float(v) for v in node.get(attribute, default).split()]
        if len(value) != 3 or not all(math.isfinite(v) for v in value):
            raise ValueError(f"Invalid URDF {attribute} vector")
        return value

    for node in document.iter("origin"):
        vector(node, "xyz", "0 0 0")
        vector(node, "rpy", "0 0 0")
    for joint in document.findall("joint"):
        name = joint.get("name")
        if not name or name in joint_names:
            raise ValueError("URDF joint names must be nonempty and unique")
        joint_names.add(name)
        parent, child = joint.find("parent"), joint.find("child")
        if parent is None or child is None:
            raise ValueError(f"URDF joint is missing parent or child: {name}")
        a, b = parent.get("link"), child.get("link")
        if a not in links or b not in links or a == b:
            raise ValueError(f"URDF joint references invalid links: {name}")
        if b in parents:
            raise ValueError(f"URDF link has multiple parents: {b}")
        parents[b] = a
        kind = joint.get("type")
        if kind not in {"fixed", "revolute", "prismatic", "continuous"}:
            raise ValueError(f"Unsupported device joint type: {kind}")
        if kind != "fixed":
            axis = joint.find("axis")
            values = [1.0, 0.0, 0.0] if axis is None else vector(axis, "xyz", "1 0 0")
            if math.sqrt(sum(v * v for v in values)) < 1e-12:
                raise ValueError(f"URDF joint axis must be nonzero: {name}")
        if kind in {"revolute", "prismatic"}:
            limit = joint.find("limit")
            if limit is None or "lower" not in limit.attrib or "upper" not in limit.attrib:
                raise ValueError(f"URDF bounded joint has no limits: {name}")
            lower, upper = float(limit.get("lower")), float(limit.get("upper"))
            if not math.isfinite(lower) or not math.isfinite(upper) or lower > upper:
                raise ValueError(f"Invalid URDF joint limits: {name}")
    if len(links - parents.keys()) != 1:
        raise ValueError("URDF must have exactly one root link")
    for link in links:
        seen = set()
        while link in parents:
            if link in seen:
                raise ValueError(f"URDF joint tree contains a cycle: {link}")
            seen.add(link)
            link = parents[link]


def read_contract(asset_id: str, cache_root: str | Path | None = None) -> dict:
    """Read the unmodified upstream contract, including ports and limitations.

    Port descriptions are source metadata, not calibrated robot target poses.
    This function is offline and does not execute upstream Python files.
    """
    entry = fetch_asset(asset_id, cache_root, offline=True)
    contract = entry.parent / "asset.contract.json"
    if not contract.is_file():
        raise FileNotFoundError(f"This source does not provide an instrument contract: {asset_id}")
    return json.loads(contract.read_text(encoding="utf-8"))


def convert_asset(
    asset_id: str,
    output_dir: str | Path,
    cache_root: str | Path | None = None,
) -> Path:
    """Convert cached URDF, STL or sourced STL assembly to USD.

    Requires a running SimulationApp. output_dir must not exist. The device base
    is fixed to the scene; source mass/inertia assumptions remain assumptions.
    No thermal, liquid, biochemical, or vendor control behavior is implemented.
    """
    entry = fetch_asset(asset_id, cache_root, offline=True)
    output = Path(output_dir).expanduser().resolve()
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite an asset conversion: {output}")
    asset = get_asset(asset_id)
    if asset["format"] in ("stl", "stl_assembly"):
        return _convert_static_mesh(entry, asset, output)
    if asset["format"] != "urdf":
        raise ValueError(f"Unsupported asset format: {asset['format']}")

    import omni.kit.commands
    from isaacsim.core.utils.extensions import enable_extension
    from pxr import Usd

    enable_extension("isaacsim.asset.importer.urdf")
    success, settings = omni.kit.commands.execute("URDFCreateImportConfig")
    if not success:
        raise RuntimeError("Isaac URDF importer could not create its configuration")
    settings.merge_fixed_joints = False
    settings.convex_decomp = False
    settings.import_inertia_tensor = True
    settings.fix_base = True
    settings.make_default_prim = True
    settings.collision_from_visuals = False
    settings.distance_scale = 1.0
    output.mkdir(parents=True)
    destination = output / "model.usd"
    success, _ = omni.kit.commands.execute(
        "URDFParseAndImportFile",
        urdf_path=str(entry),
        import_config=settings,
        dest_path=str(destination),
    )
    if not success or not destination.is_file():
        raise RuntimeError(f"Isaac URDF conversion failed: {entry}")
    stage = Usd.Stage.Open(str(destination))
    if stage is None or not stage.GetDefaultPrim():
        raise RuntimeError(f"Converted asset has no default prim: {destination}")
    _apply_glass_display(stage, asset)
    stage.GetRootLayer().Save()
    return destination


def _apply_glass_display(stage, asset: dict, root=None) -> None:
    """Apply an uncalibrated glass look to the derived USD's listed visual links.

    Strong binding above instance meshes preserves source files, geometry,
    collision shapes, articulation transforms and physics properties.
    """
    display = asset.get("glass_display")
    if not display:
        return
    from pxr import Gf, Sdf, UsdShade

    root = stage.GetDefaultPrim() if root is None else root
    targets = [stage.GetPrimAtPath(root.GetPath().AppendPath(f"{link}/visuals"))
               for link in display["links"]]
    if not all(targets):
        raise ValueError("Glass display link is missing from the imported asset")
    material = UsdShade.Material.Define(stage, root.GetPath().AppendPath("Looks/HoodGlass"))
    shader = UsdShade.Shader.Define(stage, material.GetPath().AppendChild("Shader"))
    shader.CreateImplementationSourceAttr(UsdShade.Tokens.sourceAsset)
    shader.SetSourceAsset(Sdf.AssetPath("OmniGlass.mdl"), "mdl")
    shader.SetSourceAssetSubIdentifier("OmniGlass", "mdl")
    shader.CreateInput("glass_color", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*display["color"]))
    shader.CreateInput("glass_ior", Sdf.ValueTypeNames.Float).Set(display["ior"])
    shader.CreateInput("frosting_roughness", Sdf.ValueTypeNames.Float).Set(display["roughness"])
    shader.CreateInput("depth", Sdf.ValueTypeNames.Float).Set(display["absorption_depth_m"])
    shader.CreateInput("thin_walled", Sdf.ValueTypeNames.Bool).Set(False)
    shader.CreateOutput("out", Sdf.ValueTypeNames.Token)
    material.CreateSurfaceOutput("mdl").ConnectToSource(shader.ConnectableAPI(), "out")
    for target in targets:
        UsdShade.MaterialBindingAPI.Apply(target).Bind(
            material, bindingStrength=UsdShade.Tokens.strongerThanDescendants
        )
    root.SetCustomDataByKey("glass_display_assumption", json.dumps(display, ensure_ascii=False))


def _read_static_parts(entry: Path, asset: dict) -> list:
    """Read original triangles with catalogued rigid assembly transforms and scale."""
    import numpy as np
    import trimesh

    parts = asset.get("parts", [{"name": "Geometry", "file": entry.name}])
    result = []
    for part in parts:
        path = (entry.parent / part["file"]).resolve()
        if not path.is_relative_to(entry.parent.resolve()):
            raise ValueError(f"Assembly part escapes its source directory: {path}")
        mesh = trimesh.load_mesh(path, process=False)
        if not isinstance(mesh, trimesh.Trimesh) or mesh.is_empty:
            raise ValueError(f"Source does not contain a triangle mesh: {path}")
        if "selection_bounds_source_units" in part:
            bounds = np.asarray(part["selection_bounds_source_units"], dtype=float)
            if (bounds.shape != (2, 3) or not np.isfinite(bounds).all()
                    or np.any(bounds[1] <= bounds[0])):
                raise ValueError(f"Invalid source part selection bounds: {part['name']}")
            inside = np.all((mesh.triangles >= bounds[0]) & (mesh.triangles <= bounds[1]), axis=2)
            selected = inside.all(axis=1)
            if not selected.any() or np.any(inside.any(axis=1) != selected):
                raise ValueError(f"Selection must contain whole source triangles: {part['name']}")
            mesh.update_faces(selected)
            mesh.remove_unreferenced_vertices()
        rotation = np.asarray(part.get("rotation", np.eye(3)), dtype=float)
        translation = np.asarray(part.get("translation_source_units", [0, 0, 0]), dtype=float)
        if (rotation.shape != (3, 3) or translation.shape != (3,)
                or not np.isfinite(rotation).all() or not np.isfinite(translation).all()
                or not np.allclose(rotation.T @ rotation, np.eye(3))
                or not np.isclose(np.linalg.det(rotation), 1)):
            raise ValueError(f"Assembly transform must be rigid: {part['name']}")
        vertices = (np.asarray(mesh.vertices) @ rotation.T + translation) * asset["meters_per_unit"]
        if not np.isfinite(vertices).all() or np.any(np.ptp(vertices, axis=0) <= 0):
            raise ValueError(f"Source mesh has invalid dimensions: {path}")
        result.append((part, mesh, vertices))
    return result


def _convert_static_mesh(entry: Path, asset: dict, output: Path) -> Path:
    """Place sourced parts as fixed triangle colliders without filling holes.

    Units, assembly transforms and their evidence are stored in the catalog.
    A common bottom-centred origin preserves relative part placement.
    """
    import numpy as np
    from pxr import Gf, Usd, UsdGeom, UsdPhysics, Vt

    parts = _read_static_parts(entry, asset)
    lower = np.min([vertices.min(axis=0) for _, _, vertices in parts], axis=0)
    upper = np.max([vertices.max(axis=0) for _, _, vertices in parts], axis=0)
    offset = np.array([(lower[0] + upper[0]) / 2, (lower[1] + upper[1]) / 2, lower[2]])
    output.mkdir(parents=True)
    destination = output / "model.usd"
    stage = Usd.Stage.CreateNew(str(destination))
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    root = UsdGeom.Xform.Define(stage, "/Device").GetPrim()
    stage.SetDefaultPrim(root)
    root.SetCustomDataByKey("source_asset_id", asset["asset_id"])
    root.SetCustomDataByKey("source_entry_sha256", asset["entry_sha256"])
    source = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))["sources"][asset["source"]]
    for key in ("url", "revision", "license", "license_url", "attribution"):
        root.SetCustomDataByKey("source_" + key, source[key])
    root.SetCustomDataByKey("unit_basis", asset["unit_basis"])
    root.SetCustomDataByKey("source_origin_offset_m", Gf.Vec3d(*offset))
    if "assembly_basis" in asset:
        root.SetCustomDataByKey("assembly_basis", asset["assembly_basis"])
    for part, mesh, vertices in parts:
        vertices = vertices - offset
        geometry = UsdGeom.Mesh.Define(stage, "/Device/" + part["name"])
        geometry.GetPrim().SetCustomDataByKey("source_file", part["file"])
        geometry.GetPrim().SetCustomDataByKey("source_transform_json", json.dumps(part))
        geometry.CreatePointsAttr(Vt.Vec3fArray.FromNumpy(vertices.astype(np.float32)))
        geometry.CreateFaceVertexCountsAttr(
            Vt.IntArray.FromNumpy(np.full(len(mesh.faces), 3, dtype=np.int32))
        )
        geometry.CreateFaceVertexIndicesAttr(Vt.IntArray.FromNumpy(mesh.faces.flatten().astype(np.int32)))
        geometry.CreateSubdivisionSchemeAttr(UsdGeom.Tokens.none)
        geometry.CreateExtentAttr([Gf.Vec3f(*vertices.min(axis=0)), Gf.Vec3f(*vertices.max(axis=0))])
        color = part.get("display_color", asset.get("display_color", [0.2, 0.5, 0.65]))
        geometry.CreateDisplayColorAttr([Gf.Vec3f(*color)])
        UsdPhysics.CollisionAPI.Apply(geometry.GetPrim())
        UsdPhysics.MeshCollisionAPI.Apply(geometry.GetPrim()).CreateApproximationAttr("none")
    stage.GetRootLayer().Save()
    return destination


def load_asset(usd_path: str | Path, prim_path: str, position_m=(0.0, 0.0, 0.0)):
    """Reference a converted asset into the active Z-up, metre-based stage.

    Args:
        usd_path: USD returned by convert_asset(), including its adjacent files.
        prim_path: New absolute USD prim path, such as /World/PCR.
        position_m: Root translation in metres in the stage coordinate frame.

    Returns:
        The newly created USD prim. Existing prims are never overwritten.
    """
    import math
    import omni.usd
    from pxr import Gf, Sdf, Usd, UsdGeom

    path = Path(usd_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    target = Sdf.Path(prim_path)
    if not target.IsAbsolutePath() or not target.IsPrimPath():
        raise ValueError(f"Expected an absolute prim path: {prim_path}")
    if len(position_m) != 3 or not all(math.isfinite(v) for v in position_m):
        raise ValueError("position_m must contain three finite coordinates in metres")
    stage = omni.usd.get_context().get_stage()
    if stage is None:
        raise RuntimeError("Create a SimulationApp stage before loading assets")
    if UsdGeom.GetStageUpAxis(stage) != "Z" or not math.isclose(
        UsdGeom.GetStageMetersPerUnit(stage), 1.0
    ):
        raise ValueError("Device loading requires a Z-up stage with metresPerUnit=1")
    if stage.GetPrimAtPath(target):
        raise ValueError(f"A prim already exists at {prim_path}")
    source = Usd.Stage.Open(str(path))
    if source is None or not source.GetDefaultPrim():
        raise ValueError(f"USD source has no default prim: {path}")
    prim = stage.DefinePrim(target, "Xform")
    child = stage.DefinePrim(target.AppendChild("Asset"), "Xform")
    child.GetReferences().AddReference(str(path))
    UsdGeom.Xformable(prim).AddTranslateOp().Set(Gf.Vec3d(*position_m))
    return prim
