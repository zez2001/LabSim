"""Create a new, non-overwriting public asset release staging directory.

By default only the independently parameterized rack and numeric provenance are
staged. The explicit CAD publication flag records the project owner's confirmed
redistribution authorization. The legacy Franka USD remains a local dependency
until its separate file-level redistribution basis is established. No upload is
performed by this staging command.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_GEOMETRY = [
    "assets/lab_cuvette_loading/V0_demo03/rack.usda",
    "assets/lab_cuvette_loading/V0_demo04/rack.usda",
]
CAD_DEPENDENCIES = [
    "assets/lab_cuvette_loading/V0_demo04/manifest.json",
    "assets/lab_cuvette_loading/V0_demo04/instrument_native.usda",
    "assets/lab_cuvette_loading/V0_demo02/video_pose_verified/instrument_native.usda",
    "assets/lab_cuvette_loading/V0_ext01/source/newnew4.usd",
    "assets/lab_cuvette_loading/V0_ext01/source/TestTube_Baked.usd",
    "assets/lab_cuvette_loading/V0_ext02/walls28_mm.usda",
    "assets/lab_cuvette_loading/V0_demo04/vessel_125_mm.usda",
]
FRANKA = "assets/robots/Franka.usd"
SCHEMA = "labsim.project.asset_release.v1"
HF_REPOSITORY = "Txie000/SLAI-Labsim"
CAD_LICENSE = "LicenseRef-LabSim-UserAuthorizedCADRedistribution"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def row(path, distribution, *, reason=None, root=ROOT):
    source = root / path
    if source.read_bytes()[:128].startswith(b"version https://git-lfs.github.com/spec/v1"):
        raise ValueError("Fetch real LFS content first: " + path)
    result = dict(path=path, sha256=digest(source), size_bytes=source.stat().st_size,
        tasks=["lab_cuvette_loading"], distribution=distribution,
        license="MIT" if distribution == "public_hf" else "unknown",
        license_basis="Self-created parameterized geometry or project numeric analysis"
            if distribution == "public_hf" else reason)
    if distribution == "public_hf":
        result["hf_path"] = "releases/Project_v1/" + path
    else:
        result["required_for_current_task"] = not (
            path.startswith("assets/lab_cuvette_loading/Size_v1/cuvette_") and
            path.endswith(".usda") and not any(i in path for i in ("_1000.", "_1250.")))
    return result


def stage(destination, *, cad_authorized=False):
    destination = Path(destination).resolve()
    destination.mkdir(parents=True, exist_ok=False)
    release = destination / "releases/Project_v1"
    for path in PUBLIC_GEOMETRY:
        target = release / path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / path, target)

    original = json.loads((ROOT / "assets/lab_cuvette_loading/V0_demo03/manifest.json").read_text())
    rack = dict(schema="labsim.project.rack_metadata.v1", asset_id="rack_6x6_parametric_v1",
        version="Project_v1", type="static_source_rack", license="MIT",
        source=dict(method="Python parameterization with separate UsdGeom.Cube visual and collision solids",
                    code="demos/lab_cuvette_demo03/build_assets.py:build",
                    geometry_function="demos/lab_cuvette_demo03/scene.py:rack_parts",
                    source_cad_used=False, source_model_sha256=None),
        files=[row(p, "public_hf") for p in PUBLIC_GEOMETRY],
        meters_per_unit=1, up_axis="Z", default_prim="/Asset",
        datum="rack bottom Z=0; XY centre; A1=negativeX/negativeY; F6=positiveX/positiveY",
        dimensions_m=[.110, .110, .028], row_count=6, column_count=6,
        slot_inner_xy_m=[.016, .016], pitch_m=.018, wall_m=.002,
        slot_depth_m=.025, bottom_thickness_m=.003,
        parameter_source="Video-confirmed6x6; all lengths explicit demo engineering assumptions, not measured CAD",
        static=True, mass_kg=None, center_of_mass_m=None, inertia_kg_m2=None,
        mass_basis="Static fixed rack: no dynamic mass/inertia authored",
        visual_collision_separate=True, visual_collision_dimensions_equal=True,
        collision_representation="50 analytic boxes with real walls and floor; open cavities; no filled convex hull",
        material=dict(static_friction=.6, dynamic_friction=.5, restitution=0,
                      friction_combine="average", restitution_combine="average",
                      contact_offset_m=.00005, rest_offset_m=0,
                      basis="Engineering assumptions inherited from current fixed baseline; not calibrated"),
        slots=original["slots"], geometry_parts=original["rack_parts"],
        reload_validation=original["reload_checks"]["rack.usda"],
        references=[dict(from_path=PUBLIC_GEOMETRY[1], to_path=PUBLIC_GEOMETRY[0],
                         reference="../V0_demo03/rack.usda")],
        runtime_override="Project physics baseline reapplies contact/material properties at scene initialization; see current configuration",
        real_calibrated=False)
    write(release / "metadata/rack_6x6_parametric_v1.json", rack)

    registry = json.loads((ROOT / "assets/lab_cuvette_loading/Size_v1/registry.json").read_text())
    family = []
    keys = ["asset_id", "version", "asset_path", "asset_sha256", "source", "axis_scale",
            "nominal_outer_xy_mm", "actual_outer_dimensions_mm", "height_nominal_mm",
            "inner_cavity_sections", "mass_kg", "mass_source", "mass_distribution_assumption",
            "mass_properties", "meters_per_unit", "up_axis", "default_prim"]
    for record in registry["assets"].values():
        family.append({**{k: record.get(k) for k in keys},
                       "source_geometry_license": CAD_LICENSE if cad_authorized else "unknown; not included in this public release",
                       "geometry_available_from_public_release": cad_authorized,
                       "real_calibrated": False})
    write(release / "metadata/size_family_numeric_provenance.json", dict(
        schema="labsim.project.size_family_provenance.v1", metadata_license="MIT",
        scope="Project-created numeric analysis and source hashes only; no CAD mesh or texture included",
        default_asset_id="cuvette_xy_1000", assets=family))

    private = CAD_DEPENDENCIES + [FRANKA]
    private += [str(p.relative_to(ROOT)) for p in sorted(
        (ROOT / "assets/lab_cuvette_loading/Size_v1").glob("*.json"))]
    private += [str(p.relative_to(ROOT)) for p in sorted(
        (ROOT / "assets/lab_cuvette_loading/Size_v1").glob("*.usda"))]
    files = [row(p, "public_hf") for p in PUBLIC_GEOMETRY]
    for path in ["metadata/rack_6x6_parametric_v1.json", "metadata/size_family_numeric_provenance.json"]:
        files.append(row(path, "public_hf", root=release))
    for path in sorted(set(private)):
        reason = ("Legacy project Franka USD has no verified file-level redistribution license; "
                  "NVIDIA Isaac Sim models are separately licensed. Obtain an authorized matching file."
                  if path == FRANKA else
                  "User-supplied CAD or derivative metadata/geometry; original attachment contains no model redistribution license. "
                  "Provide an authorized local copy; code MIT does not cover it.")
        entry = row(path, "local_only", reason=reason)
        if cad_authorized and path != FRANKA:
            entry.update(distribution="public_hf", license=CAD_LICENSE,
                         license_basis="Project owner confirmed ownership/authority and explicitly authorized public redistribution of supplied CAD and its derivatives on2026-10-26; no manufacturer license inferred",
                         hf_path="releases/Project_v1/" + path)
            target = release / path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / path, target)
        files.append(entry)

    assets = [rack, dict(asset_id="instrument_native_A", type="CAD-derived_static_instrument",
        version="Project_v1", source_sha256=digest(ROOT / "assets/lab_cuvette_loading/V0_ext01/source/newnew4.usd"),
        files=[p for p in CAD_DEPENDENCIES if "instrument" in p or "newnew4" in p],
        selected_seat="candidate_far_hinge", geometry_unchanged=True,
        meters_per_unit=1, up_axis="Z", default_prim="/Asset",
        datum="Normalized assembly origin from preserved source-to-metre transform; complete root transform retained",
        transform_basis="V0_demo02 video_pose_verified derived layer; original source millimetre/Z-up and existing root rotation preserved by derivation",
        dimensions_basis="Current per-mesh transformed-vertex geometry audit; refer to task geometry audit, not nominal seat width alone",
        mass_kg=None, center_of_mass_m=None, inertia_kg_m2=None,
        mass_basis="Static fixed assembly; no dynamic mass/inertia used",
        visual_collision_separate=True,
        collision_representation="Separate static triangle meshes copied from source solids; internal empty channel retained",
        collision_cooking_complete_validation=False,
        material_contact_basis="Current task physics configuration overrides authored engineering friction/contact assumptions; not physically calibrated",
        license="unknown", distribution="local_only", real_calibrated=False),
        dict(asset_id="franka_legacy_labsim", type="robot", version="legacy_baseline",
             path=FRANKA, sha256=digest(ROOT / FRANKA), license="unknown",
             meters_per_unit=.01, up_axis="Z", default_prim="/Franka",
             datum="Legacy authored robot root; runtime world metre semantics preserved without additional automatic metadata scaling",
             transform_basis="Legacy file has centimetre metadata and explicit geometry scales; replacement robot requires size/frame verification",
             mass_kg=None, center_of_mass_m=None, inertia_kg_m2=None,
             mass_basis="Per-link authored properties/defaults inherited from legacy robot; real masses/COM/inertia not independently verified",
             visual_collision_separate=True,
             collision_representation="Legacy per-link collision meshes; runtime articulation/drive/contact configuration applied by task",
             material_contact_basis="Current runtime configuration; finger friction assumptions and phase force limits are not real calibration",
             official_asset_documentation="https://docs.isaacsim.omniverse.nvidia.com/5.1.0/assets/usd_assets_robots.html",
             official_asset_path="Robots/FrankaRobotics/FrankaPanda/franka.usd",
             official_install_documentation="https://docs.isaacsim.omniverse.nvidia.com/5.1.0/installation/download.html",
             terms="https://docs.isaacsim.omniverse.nvidia.com/5.1.0/common/licenses-isaac-sim.html",
             official_asset_byte_identity_to_legacy="not verified; do not substitute without revalidation",
             unresolved_offline_dependency="OmniPBR.mdl is supplied by the installed Isaac renderer; no external texture dependencies detected",
             real_calibrated=False)]
    manifest = dict(schema=SCHEMA, release="Project_v1", repository=HF_REPOSITORY,
        default_asset_id="cuvette_xy_1000", complete_task_bundle=False,
        redistribution_policy="Per-file allowlist; unknown rights excluded from public upload",
        files=files, assets=assets,
        required_local_assets_instruction="Set LABSIM_PRIVATE_ASSET_ROOT to an authorized tree preserving assets/...; install verifies exact hashes",
        historical_datasets_unchanged=True, raw_61GB_dataset_included=False,
        references=["https://huggingface.co/docs/hub/repositories-licenses",
                    "https://docs.isaacsim.omniverse.nvidia.com/5.1.0/common/licenses-isaac-sim.html"])
    if cad_authorized:
        manifest["user_cad_publication_authorization"] = dict(
            confirmed_date="2026-10-26", confirmation_source="Direct project-owner instruction in the current release session",
            scope="Original supplied instrument/vessel CAD USDs and their LabSim derivatives, including all registered size variants",
            permission="Public redistribution authorized by project owner after a file-level rights question",
            license_id=CAD_LICENSE, manufacturer_license_claimed=False,
            raw_attachment_zip_included=False, private_user_messages_or_credentials_included=False)
        assets[1].update(license=CAD_LICENSE, distribution="public_hf")
    write(release / "manifest.json", manifest)
    shutil.copyfile(ROOT / "LICENSE", destination / "LICENSE")
    if cad_authorized:
        (destination / "LICENSE-CAD.md").write_text(CAD_GRANT, encoding="utf-8")
    (destination / "README.md").write_text(FULL_CARD if cad_authorized else CARD, encoding="utf-8")
    return manifest


CARD = """---
license: mit
task_categories:
  - robotics
tags:
  - isaac-sim
  - usd
  - laboratory-automation
  - labsim
language:
  - en
  - zh
size_categories:
  - n<1K
---

# LabSim assets — Project_v1

This version publishes the project's own white6×6 parameterized source rack,
its collision/visual geometry, dimensions, slot IDs, and numeric provenance for
the cuvette size family. Code and executable task interfaces live in
[LabSim](https://github.com/zez2001/LabSim/tree/codex/labsim).

**This first release is a partial asset release, not a complete runnable scene.**
The original external instrument, CAD-derived cuvettes, and legacy Franka model
are excluded because their file-level redistribution permissions have not been
established. The manifest lists each excluded path and exact SHA256. Obtain
authorized local copies rather than treating the code's MIT license as a model
license. No HF token is required to download the published files.

## Download and use

From the LabSim checkout:

```bash
./labsim assets list
./labsim assets download --cache /path/to/empty-or-reusable-cache
./labsim assets install --asset-root /path/to/portable-assets --public-only
```

The Git asset lock pins an actual immutable HF revision and verifies every file's
size and SHA256. Interrupted downloads resume. Already verified cached files work
with `--offline`. A complete task additionally needs the declared local-only
models in the same relative layout:

```bash
./labsim assets install --asset-root /path/to/portable-assets \\
  --private-root /path/to/authorized-model-tree
export LABSIM_ASSET_ROOT=/path/to/portable-assets
./labsim assets check --asset-root "$LABSIM_ASSET_ROOT"
```

An exact missing/changed dependency causes a clear failure. No model is silently
replaced or resized. A user path is an explicit dependency, not evidence that the
complete original CAD task can be reconstructed from public downloads alone.

## Contents and units

- `releases/Project_v1/assets/.../rack.usda`: the standalone generated rack plus
  its historical reference wrapper. Both paths are preserved so relative USD
  references resolve without author-machine absolute paths.
- `releases/Project_v1/metadata/`: rack metadata and numeric size-family analysis.
- `releases/Project_v1/manifest.json`: per-file source, hash, license, dependencies,
  units, parameter basis, and current publication gates.

The rack uses metres, Z-up, default prim `/Asset`, bottomZ=0, and centredXY.
It measures110×110×28mm with36 open16×16mm slots,18mm pitch,2mm walls,
25mm depth and3mm bottom. These are **engineering assumptions**, not measured
instrument dimensions. Visual and collision geometry are separate but use the
same dimensions:50 fixed box solids preserve real open cavities. The source rack
was generated from Python parameters, not reconstructed from external CAD.

The default task's10×10×67.5mm cuvette is a dimension hypothesis.20g mass,
uniform material-volume distribution, friction and contact settings are simulation
assumptions; they have not been physically calibrated. Numeric metadata does not
include the excluded mesh geometry or establish a real instrument's dimensions.

## License and attribution

MIT applies to the included self-created rack and project-created numeric
metadata; see `LICENSE`. It does not license excluded third-party CAD, derived
mesh geometry, NVIDIA robot assets, Isaac Sim, or runtime components. NVIDIA's
[Isaac Sim licensing](https://docs.isaacsim.omniverse.nvidia.com/5.1.0/common/licenses-isaac-sim.html)
separates source-code terms from additional3D models and textures. The official
[Franka asset catalog](https://docs.isaacsim.omniverse.nvidia.com/5.1.0/assets/usd_assets_robots.html)
and [asset downloads](https://docs.isaacsim.omniverse.nvidia.com/5.1.0/installation/download.html)
provide an authorized acquisition route; byte identity to this project's legacy
Franka file has not been verified, so substitutions need validation.

No user attachments, credentials, API keys, internal handoff packages, training
checkpoints or61GB raw trajectory collection are included.
"""


CAD_GRANT = """# LabSim supplied CAD — public redistribution authorization

License identifier: `LicenseRef-LabSim-UserAuthorizedCADRedistribution`.

On2026-10-26 the LabSim project owner confirmed the relevant rights and explicitly
authorized public redistribution of the supplied instrument/vessel CAD files and
their LabSim derivatives. This release relies on that direct authorization.

This permission record covers the instrument/vessel USD source files, normalized
instrument layers, thick-wall collision reconstruction,12.5mm control vessel,
registered Size_v1 size variants, and their asset metadata identified by exact
SHA256 in `releases/Project_v1/manifest.json`. Public download and redistribution
of those listed files is authorized for this release. It does not apply the
project code's MIT license to the supplied models, assert a manufacturer license,
or establish real-world calibration, product identity, or instrument compatibility.
Rights beyond this recorded public redistribution authorization have not been
separately established; contact the repository owner for any broader license.

NVIDIA/Franka assets, third-party runtime components, raw user attachment archives,
private messages and credentials are excluded from this grant. The independently
parameterized rack and project-created numeric analysis are licensed separately
under the included MIT `LICENSE`.
"""


FULL_CARD = """---
license: other
license_name: labsim-mixed-mit-user-authorized-cad-redistribution
license_link: https://huggingface.co/datasets/Txie000/SLAI-Labsim/blob/main/LICENSE-CAD.md
task_categories:
  - robotics
tags:
  - isaac-sim
  - usd
  - laboratory-automation
  - labsim
language:
  - en
  - zh
size_categories:
  - n<1K
---

# LabSim cuvette loading assets — Project_v1

Runtime assets and all35 registered cuvette size variants for the fixed standard
`lab_cuvette_loading` task. Executable code and evaluation interfaces are in
[LabSim](https://github.com/zez2001/LabSim/tree/codex/labsim).

The external instrument/vessel CAD and derivatives are published under explicit
project-owner public redistribution authorization recorded in `LICENSE-CAD.md`.
The self-created6×6 rack and project-created numeric analysis use MIT. The legacy
Franka robot USD is excluded until its file-level redistribution basis is verified;
the manifest lists its exact SHA256 and official acquisition references. A matching
authorized robot file and an installed Isaac Sim runtime remain necessary to run.
No HF login or token is required to download the published files.

## Download and use

From a LabSim checkout:

```bash
./labsim assets list
./labsim assets download --cache /path/to/empty-or-reusable-cache
./labsim assets install --asset-root /path/to/portable-assets --public-only
```

The Git asset lock pins an immutable HF commit and verifies byte size andSHA256.
Interrupted downloads resume; verified cached files work with `--offline`.
Supply the unchanged legacy Franka file in an authorized local tree preserving
`assets/robots/Franka.usd`, then install/check the complete dependency tree:

```bash
./labsim assets install --asset-root /path/to/portable-assets \\
  --private-root /path/to/authorized-robot-tree
export LABSIM_ASSET_ROOT=/path/to/portable-assets
./labsim assets check --asset-root "$LABSIM_ASSET_ROOT"
```

The importer rejects changed existing files and mismatching source hashes. It does
not silently substitute an official robot with different dynamics or frames.
The complete original task is not claimed to run from public HF alone while the
one declared legacy robot dependency remains outside this release.

## Contents

- `releases/Project_v1/assets/lab_cuvette_loading/Size_v1/`:35 independent USD
  variants, their metadata, and registry; default `cuvette_xy_1000`.
- `.../V0_demo04/`: original-seat instrument reference, rack reference,12.5mm
  control vessel. Original A seat is preserved; no16mm adapter is substituted.
- `.../V0_demo02/video_pose_verified/`: normalized open-lid instrument assembly.
- `.../V0_ext01/source/`: required original instrument/vessel USD dependencies.
- `.../V0_ext02/`: original28-part thick-wall collision reconstruction.
- `.../V0_demo03/`: self-created full white6×6 rack,50 real solid box colliders.
- `releases/Project_v1/metadata/` and `manifest.json`: provenance, dimensions,
  local frames, mass assumptions, collision representation, permissions and hashes.

Relative USD references retain the original directory layout; no author-machine
absolute asset paths or raw attachment ZIPs are needed to resolve them. The
selected cuvette USD is standalone, with separate visual/collision geometry and
an open cavity, wall thickness and bottom. Instrument static triangle meshes
retain the internal channel rather than filling it with one convex hull.

## Parameters and limits

Task assets use metres/Z-up/defaultPrim `/Asset`, with a common vessel bottomZ=0.
The rack measures110×110×28mm with36 open16×16mm slots,18mm pitch,2mm
walls,25mm depth and3mm bottom. These rack lengths are explicit engineering
assumptions based on the video, not measured original rack CAD.

All size variants apply the sameXY-only affine transform to visual and28 collision
input meshes; height stays67.5mm. The default10×10mm external width is a size
hypothesis, not a recovered real vessel dimension.20g fixed mass and uniform
visual material-volume distribution are assumptions; COM and inertia are recomputed
per variant, so fixed mass does not imply constant density. Friction, restitution,
contact offsets and robot dynamics are uncalibrated engineering parameters.
Input collision geometry is documented; this does not prove a global bound on
every cooked PhysX contact shape or certify submillimetre real-world accuracy.

## Licenses and exclusions

See per-file licenses in `manifest.json`, MIT `LICENSE`, and `LICENSE-CAD.md`.
No manufacturer license or real-world hardware compatibility is inferred from the
owner's publication authorization. NVIDIA models and runtime components have
[separate terms](https://docs.isaacsim.omniverse.nvidia.com/5.1.0/common/licenses-isaac-sim.html).
The official [Franka catalog](https://docs.isaacsim.omniverse.nvidia.com/5.1.0/assets/usd_assets_robots.html)
and [Isaac asset downloads](https://docs.isaacsim.omniverse.nvidia.com/5.1.0/installation/download.html)
provide an acquisition route; byte identity to the project's legacy robot has
not been verified. Replacing that robot requires task revalidation.

No credentials, private handoff messages, raw archives, training checkpoints or
61GB raw trajectory collection are included in this first asset release.
"""


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--cad-publication-authorized", action="store_true",
                   help="Use only after direct project-owner confirmation of CAD redistribution rights")
    args = p.parse_args()
    m = stage(args.output, cad_authorized=args.cad_publication_authorized)
    print(json.dumps(dict(staging=str(args.output.resolve()), public_files=sum(
        f["distribution"] == "public_hf" for f in m["files"]), local_only_files=sum(
        f["distribution"] == "local_only" for f in m["files"]), uploaded=False), indent=2))
