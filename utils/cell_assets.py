"""Versioned external device assets for LabSim.

Catalog and download operations work without Isaac. Import and load operations
require an existing Isaac Sim 5.1 SimulationApp; they do not create one.
Source geometry remains outside the Git checkout and is never rewritten.
"""

import hashlib
import json
import os
from pathlib import Path
import xml.etree.ElementTree as ET


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
    """Resolve the cache; LABSIM_ASSET_CACHE overrides ~/LabSim-assets."""
    location = cache_root or os.environ.get("LABSIM_ASSET_CACHE")
    return Path(location).expanduser().resolve() if location else Path.home() / "LabSim-assets"


def fetch_asset(
    asset_id: str,
    cache_root: str | Path | None = None,
    *,
    offline: bool = False,
) -> Path:
    """Fetch the pinned source folder and attribution files, returning its URDF.

    Args:
        asset_id: Identifier from list_assets().
        cache_root: External cache directory, never an environment directory.
        offline: Inspect local files without contacting Hugging Face.

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
        from huggingface_hub import snapshot_download

        snapshot_download(
            source["repo_id"],
            repo_type="dataset",
            revision=source["revision"],
            local_dir=root,
            allow_patterns=[asset["source_directory"] + "/*", *source["notice_files"]],
            max_workers=4,
        )
    entry = root / asset["source_directory"] / asset["entry_file"]
    if not entry.is_file():
        raise FileNotFoundError(
            f"Asset is not cached: {entry}; call fetch_asset without offline=True"
        )
    if hashlib.sha256(entry.read_bytes()).hexdigest() != asset["entry_sha256"]:
        raise ValueError(f"Source entry differs from the pinned catalog: {entry}")
    for name in source["notice_files"]:
        if not (root / name).is_file():
            raise FileNotFoundError(f"Missing source attribution file: {root / name}")
    validate_urdf_files(entry)
    return entry


def validate_urdf_files(entry: Path) -> None:
    """Check that URDF mesh/texture references are local, complete source files."""
    root = entry.parent.resolve()
    document = ET.parse(entry).getroot()
    if document.tag != "robot" or not document.findall("link"):
        raise ValueError(f"Not a robot/device URDF: {entry}")
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


def read_contract(asset_id: str, cache_root: str | Path | None = None) -> dict:
    """Read the unmodified upstream contract, including ports and limitations.

    Port descriptions are source metadata, not calibrated robot target poses.
    This function is offline and does not execute upstream Python files.
    """
    entry = fetch_asset(asset_id, cache_root, offline=True)
    return json.loads((entry.parent / "asset.contract.json").read_text(encoding="utf-8"))


def convert_asset(
    asset_id: str,
    output_dir: str | Path,
    cache_root: str | Path | None = None,
) -> Path:
    """Convert cached URDF to USD with source collisions and joints preserved.

    Requires a running SimulationApp. output_dir must not exist. The device base
    is fixed to the scene; source mass/inertia assumptions remain assumptions.
    No thermal, liquid, biochemical, or vendor control behavior is implemented.
    """
    entry = fetch_asset(asset_id, cache_root, offline=True)
    output = Path(output_dir).expanduser().resolve()
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite an asset conversion: {output}")

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
