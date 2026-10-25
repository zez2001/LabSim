"""Convert, load, simulate and photograph one external device asset.

Run with ``python -m demos.cell_assets.preview --help``. This demonstrates asset
loading, not robot interaction or the instrument's biochemical operation.
"""

import argparse
import json
import traceback
from pathlib import Path

from demos.cell_assets.cameras import create_views, read_rgb
from utils.cell_assets import convert_asset, fetch_asset, get_asset, list_assets, load_asset


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--asset-id", required=True, choices=[a["asset_id"] for a in list_assets()])
    parser.add_argument(
        "--output", type=Path, required=True, help="New output directory; never overwritten"
    )
    parser.add_argument("--cache", type=Path, help="Source asset cache (default ~/LabSim-assets)")
    parser.add_argument("--offline", action="store_true", help="Use already downloaded assets")
    parser.add_argument("--gui", action="store_true", help="Show the Isaac window")
    args = parser.parse_args()
    output = args.output.expanduser().resolve()
    if output.exists():
        parser.error(f"Output directory already exists: {output}")
    fetch_asset(args.asset_id, args.cache, offline=args.offline)

    from isaacsim import SimulationApp

    app = SimulationApp({
        "headless": not args.gui, "renderer": "RayTracedLighting",
        "limit_cpu_threads": 8, "multi_gpu": False, "width": 960, "height": 720,
    })
    exit_code = 1
    try:
        import numpy as np
        import omni.usd
        from PIL import Image
        from isaacsim.core.api import World
        from pxr import Usd, UsdGeom, UsdLux, UsdPhysics

        output.mkdir(parents=True)
        usd_path = convert_asset(args.asset_id, output / "usd", args.cache)
        world = World(stage_units_in_meters=1.0)
        stage = omni.usd.get_context().get_stage()
        UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
        prim = load_asset(usd_path, "/World/Device")
        world.scene.add_default_ground_plane()
        light = UsdLux.DomeLight.Define(stage, "/World/Light")
        light.CreateIntensityAttr(900)
        bounds = UsdGeom.BBoxCache(
            Usd.TimeCode.Default(), ["default", "render"]
        ).ComputeWorldBound(prim).ComputeAlignedRange()
        lower, upper = np.array(bounds.GetMin()), np.array(bounds.GetMax())
        extent = upper - lower
        if not np.isfinite(extent).all() or np.any(extent <= 0):
            raise RuntimeError(f"Invalid loaded asset bounds: {extent}")
        center = (lower + upper) / 2
        distance = float(max(extent)) * 2.5
        annotators = create_views(stage, center, distance)
        world.reset()
        for _ in range(120):
            world.step(render=True)
        for name, annotator in annotators.items():
            pixels = read_rgb(annotator)
            Image.fromarray(pixels).save(output / f"{name}.png")
        device_prims = list(Usd.PrimRange(prim, Usd.TraverseInstanceProxies()))
        result = {
            "asset_id": args.asset_id,
            "source": get_asset(args.asset_id),
            "steps": 120,
            "bbox_extent_m": extent.tolist(),
            "meshes": sum(p.IsA(UsdGeom.Mesh) for p in device_prims),
            "colliders": sum(p.HasAPI(UsdPhysics.CollisionAPI) for p in device_prims),
            "joints": sum(p.IsA(UsdPhysics.Joint) for p in device_prims),
            "asset_load": "passed",
            "robot_interaction": "not_run",
            "real_calibrated": False,
        }
        if not result["meshes"] or not result["colliders"]:
            raise RuntimeError(f"Imported geometry/colliders are missing: {result}")
        (output / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        print("CELL_ASSET_PREVIEW_OK " + json.dumps(result, ensure_ascii=False), flush=True)
        exit_code = 0
    except Exception:
        traceback.print_exc()
        raise
    finally:
        import omni.kit.app

        omni.kit.app.get_app().post_quit(exit_code)
        app.close(wait_for_replicator=False)


if __name__ == "__main__":
    main()
