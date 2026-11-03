"""CPU-only unit registry and existing source-scene builders."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "config/cell_units/units.json"
VERSION = json.loads(REGISTRY.read_text())["version"]


def list_units():
    return json.loads(REGISTRY.read_text())["units"]


def get_unit(unit_id):
    """Return one registry entry, or raise ValueError for an unknown task ID."""
    for unit in list_units():
        if unit["id"] == unit_id:
            return unit
    raise ValueError(f"Unknown single-cell unit: {unit_id}")


def build(unit, output, cache, driver):
    """Share asset import, physical setup and measurements with contact demos."""
    if unit["builder"] == "pcr":
        from demos.cell_units.pcr import build as build_pcr

        return build_pcr(output, cache, driver)
    if unit["builder"] == "hood":
        from demos.cell_assets.hood_open import run

        return run(output, cache, True, gas_springs=True, driver=driver)
    if unit["builder"] == "cap":
        from demos.cell_assets.cap_cycle import run, CONFIG

        return run(output, cache, json.loads(CONFIG.read_text()), driver=driver)
    from demos.cell_assets.handling import run, CONFIG

    config = json.loads(CONFIG.read_text())
    if unit["id"] == "magsep_transfer":
        config.update(
            device_asset=None,
            target_position_m=[0.05, 0.15, 0.7402],
            entry_offset_m=[0, 0, 0],
            camera_center_m=[0.0, 0.05, 0.95],
            camera_distance_m=1.4,
            task="magsep_table_transfer",
            support_surfaces={"loaded": "table", "returned": "table"},
        )
    return run(output, cache, config, driver=driver)
