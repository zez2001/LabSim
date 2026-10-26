"""Create sanitized *release copies*; never edit historical repository assets.

Only nonoperative USD layer documentation is changed in geometry files. Numeric
mesh data, collision/physics properties and references must remain identical; an
offline USD semantic comparison is a separate required publication check. The
release registry records both original and released hashes.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re

from stage_lab_cuvette_assets import stage, ROOT, FRANKA, CAD_LICENSE

PREFIX = "releases/Project_v1_portable"
GITHUB_COMMIT = "d5aab4ff85b7b591b3870995160451c8223875ab"
FRANKA_URL = ("https://media.githubusercontent.com/media/zez2001/LabSim/" +
              GITHUB_COMMIT + "/assets/robots/Franka.usd")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + "\n")


def replace_hf_prefix(value):
    if isinstance(value, dict):
        return {k: replace_hf_prefix(v) for k, v in value.items()}
    if isinstance(value, list):
        return [replace_hf_prefix(v) for v in value]
    return value.replace("releases/Project_v1/", PREFIX + "/") if isinstance(value, str) else value


def prepare(destination):
    destination = Path(destination).resolve()
    manifest = stage(destination, cad_authorized=True)
    previous = destination / "releases/Project_v1"
    release = destination / PREFIX
    previous.rename(release)
    manifest = replace_hf_prefix(manifest)
    manifest["release"] = "Project_v1_portable"
    alterations = []
    for row in manifest["files"]:
        row["original_sha256"] = row["sha256"]
        if row["distribution"] != "public_hf":
            continue
        path = destination / row["hf_path"]
        if path.suffix != ".usda":
            continue
        original = path.read_text()
        # A composed USD export puts its source filename in the layer doc string.
        # Limit replacement to that string, never a mesh/property/reference field.
        pattern = re.compile(r'(?ms)^    doc = """(.*?)"""')
        def change(match):
            text = match.group(1).replace(str(ROOT) + "/", "")
            return '    doc = """' + text + '"""'
        sanitized, doc_count = pattern.subn(change, original)
        if "/home/" in sanitized or "/Users/" in sanitized:
            raise ValueError("Unaccounted author path outside recognized layer doc: " + str(path))
        if sanitized != original:
            path.write_text(sanitized)
            alterations.append(dict(path=row["path"], source_sha256=row["original_sha256"],
                released_sha256=sha(path), layer_documentation_fields_found=doc_count,
                operation="Remove repository absolute prefix from nonoperative layer documentation only"))

    family_directory = release / "assets/lab_cuvette_loading/Size_v1"
    control = release / "assets/lab_cuvette_loading/V0_demo04/vessel_125_mm.usda"
    registry = json.loads((family_directory / "registry.json").read_text())
    portable_records = {}
    for ident, record in registry["assets"].items():
        old = json.loads(json.dumps(record))
        record["asset_sha256"] = sha(release / record["asset_path"])
        record["source"]["sha256"] = sha(control)
        record["portable_release"] = dict(version="Project_v1_portable",
            original_registered_asset_sha256=old["asset_sha256"],
            original_control_source_sha256=old["source"]["sha256"],
            original_metadata_sha256=sha(ROOT / record["asset_path"].replace(".usda", ".json")),
            physical_geometry_modified=False, reference_paths_modified=False,
            transformation="Only remove author-machine path prefix in USD layer documentation; refresh released-file hashes")
        write(family_directory / (ident + ".json"), record)
        portable_records[ident] = record
    registry["assets"] = portable_records
    registry["portable_release"] = dict(version="Project_v1_portable",
        original_registry_sha256=sha(ROOT / "assets/lab_cuvette_loading/Size_v1/registry.json"),
        geometric_and_physical_parameters_unchanged=True)
    write(family_directory / "registry.json", registry)

    scene_manifest_path = release / "assets/lab_cuvette_loading/V0_demo04/manifest.json"
    scene_manifest = json.loads(scene_manifest_path.read_text())
    for name in scene_manifest["asset_sha256"]:
        target = scene_manifest_path.parent / name
        if target.exists():
            scene_manifest["asset_sha256"][name] = sha(target)
    scene_manifest["portable_release"] = dict(version="Project_v1_portable",
        original_manifest_sha256=sha(ROOT / "assets/lab_cuvette_loading/V0_demo04/manifest.json"),
        geometry_unchanged=True, metadata_hashes_refreshed=True)
    write(scene_manifest_path, scene_manifest)

    provenance_path = release / "metadata/size_family_numeric_provenance.json"
    provenance = json.loads(provenance_path.read_text())
    for record in provenance["assets"]:
        current = portable_records[record["asset_id"]]
        record["asset_sha256"] = current["asset_sha256"]
        record["source"] = current["source"]
        record["portable_release"] = current["portable_release"]
    write(provenance_path, provenance)
    rack_path = release / "metadata/rack_6x6_parametric_v1.json"
    write(rack_path, replace_hf_prefix(json.loads(rack_path.read_text())))

    for row in manifest["files"]:
        if row["distribution"] == "public_hf":
            path = destination / row["hf_path"]
            row.update(sha256=sha(path), size_bytes=path.stat().st_size,
                       release_bytes_changed=row["original_sha256"] != sha(path))
        elif row["path"] == FRANKA:
            row.update(distribution="external_pinned", download_url=FRANKA_URL,
                external_repository="https://github.com/zez2001/LabSim",
                external_revision=GITHUB_COMMIT,
                acquisition_basis="Download existing project public Git LFS file at pinned commit; not republished to HF; file license remains unverified",
                publicly_downloadable=True, license="unknown")
    for asset in manifest["assets"]:
        if asset.get("asset_id") == "franka_legacy_labsim":
            asset.update(distribution="external_pinned", download_url=FRANKA_URL,
                         external_revision=GITHUB_COMMIT)
    manifest["sanitization"] = dict(method="USD layer documentation-only author-path removal; released registries refresh corresponding hashes",
        geometry_changes=False, physics_parameter_changes=False, historical_repository_assets_modified=False,
        changed_usd_count=len(alterations), usd_files=alterations,
        semantic_validation_required="Offline USD canonical comparison with only layer.documentation cleared; all other authored data must match")
    manifest["complete_publicly_downloadable_task_bundle"] = True
    manifest["complete_task_bundle"] = False
    manifest["required_local_assets_instruction"] = "No author-local asset tree required: HF provides CAD/rack/variants; exact legacy robot is downloaded from pinned existing public Git LFS. Robot redistribution license remains unverified and robot is not republished to HF."
    write(release / "manifest.json", manifest)
    card_path = destination / "README.md"
    card = replace_hf_prefix(card_path.read_text()).replace(
        "A matching\nauthorized robot file and an installed Isaac Sim runtime remain necessary to run.",
        "The exact legacy robot is fetched automatically from the existing public\nproject Git LFS at a pinned commit with SHA256 verification; it is not republished\nto HF. An installed Isaac Sim runtime remains necessary to run.")
    card = card.replace(
        "Supply the unchanged legacy Franka file in an authorized local tree preserving\n`assets/robots/Franka.usd`, then install/check the complete dependency tree:",
        "The installer acquires the unchanged legacy Franka file from the pinned\nexisting public project Git LFS and installs/checks the complete dependency tree:")
    card = card.replace(" " + chr(92) + "\n  --private-root /path/to/authorized-robot-tree", "")
    card += ("\nThe portable release removes author-machine absolute paths only from\nnonoperative USD layer documentation. No vertices, physical attributes or active\nreferences change. Both original and released SHA256 values are recorded; old\nrepository assets and the earlier HF revision remain preserved.\n")
    card_path.write_text(card)
    license_path = destination / "LICENSE-CAD.md"
    license_path.write_text(replace_hf_prefix(license_path.read_text()))
    return manifest


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", required=True, type=Path)
    args = p.parse_args()
    result = prepare(args.output)
    print(json.dumps(dict(staging=str(args.output.resolve()), changed_USD_docs=result["sanitization"]["changed_usd_count"],
        HF_payload_files=sum(f["distribution"] == "public_hf" for f in result["files"]),
        external_pinned_files=sum(f["distribution"] == "external_pinned" for f in result["files"]),
        uploaded=False), indent=2))
