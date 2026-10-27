"""Small project entry point over the existing Size_v1 implementation.

No physics, assets, labels, file formats, or training loop are implemented here.
Commands run from the repository root even when called from another directory.
Use --dry-run on a command to see exact argv without creating output files.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/lab_cuvette_loading/Size_v1/standard.yaml"
FROZEN = ROOT / "config/lab_cuvette_loading/Size_v1/frozen_scene.json"
REGISTRY = ROOT / "assets/lab_cuvette_loading/Size_v1/registry.json"
OUTPUT_ROOT = ROOT / "outputs/lab_cuvette_loading/Size_v1"
PROJECT_CONFIG = ROOT / "config/lab_cuvette_loading/Project_v1/standard.yaml"
PROJECT_RELEASES = {
    "Project_v1": ("demos.lab_cuvette_project_v1.run", PROJECT_CONFIG),
    "Project_v1_1": ("demos.lab_cuvette_project_v1_1.run",
        ROOT / "config/lab_cuvette_loading/Project_v1_1/standard.yaml"),
    "Project_release_v1": ("demos.lab_cuvette_project_release_v1.launch",
        ROOT / "config/lab_cuvette_loading/Project_release_v1/standard.yaml"),
}
CURRENT_PROJECT_VERSION = "Project_release_v1"
RECORD_PURPOSES = ("demonstration", "policy_evaluation", "lifecycle_diagnostic", "resource_probe")


def project_version(value):
    """Resolve the documented current alias before routing or recording argv."""
    return CURRENT_PROJECT_VERSION if value == "current" else value


def resolve_path(value):
    """CLI relative paths are always repository-relative, not caller-relative."""
    value = Path(value).expanduser()
    return (value if value.is_absolute() else ROOT / value).resolve()


def new_path(value):
    value = resolve_path(value)
    if value.exists() or value.is_symlink():
        raise ValueError(f"Output already exists; use a new path: {value}")
    return value


def existing_file(value):
    value = resolve_path(value)
    if not value.is_file():
        raise ValueError(f"File does not exist: {value}")
    return value


def dataset_file(value):
    value = resolve_path(value)
    if value.is_dir():
        for candidate in (value / "episode_data.hdf5", value / "dataset/episode_data.hdf5", value / "dataset/episode_0000.h5"):
            if candidate.is_file():
                return candidate
        raise ValueError("No normal episode/index HDF5 found in " + str(value))
    return existing_file(value)


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def lfs_pointer(path):
    with Path(path).open("rb") as stream:
        return stream.read(128).startswith(b"version https://git-lfs.github.com/spec/v1")


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    commands = p.add_subparsers(dest="command", required=True)
    doctor = commands.add_parser("doctor", help="CPU-only runtime, LFS and frozen-scene checks")
    doctor.add_argument("--json", action="store_true", help="Print a machine-readable diagnostic")
    doctor.add_argument("--project-version", type=project_version, choices=tuple(PROJECT_RELEASES), default="Project_v1",
        help="Configuration to inspect; current=Project_release_v1; omitted preserves Project_v1")
    doctor.add_argument("--config", help="Optional explicit config; its version must match --project-version")
    assets = commands.add_parser("assets", help="List registered size hypotheses; no simulation")
    assets.add_argument("operation", nargs="?", choices=("list", "download", "install", "check"), default="list")
    assets.add_argument("--asset-id")
    assets.add_argument("--json", action="store_true")
    assets.add_argument("--cache", type=Path)
    assets.add_argument("--asset-root", type=Path)
    assets.add_argument("--private-root", type=Path)
    assets.add_argument("--offline", action="store_true")
    demo = commands.add_parser("demo", help="Run one complete frozen standard teacher episode (GUI by default)")
    demo.add_argument("--output", required=True, help="New output directory; never overwrite an episode")
    demo.add_argument("--headless", action="store_true")
    demo.add_argument("--gui", action="store_true")
    demo.add_argument("--task", choices=("lab_cuvette_loading",), default="lab_cuvette_loading")
    demo.add_argument("--scene", choices=("standard",), default="standard")
    demo.add_argument("--backend", choices=("teacher", "gpt6"), default="teacher")
    demo.add_argument("--asset-id", help="Optional registered hypothesis for a separate demo; does not change the original seat")
    demo.add_argument("--provider-config")
    demo.add_argument("--budget-ledger")
    demo.add_argument("--max-calls", type=int, default=160)
    demo.add_argument("--dry-run", action="store_true")
    evaluation = commands.add_parser("eval", help="Sequential physical episodes with the same independent scorer")
    for flag in ("--headless", "--gui", "--dry-run"):
        evaluation.add_argument(flag, action="store_true")
    evaluation.add_argument("--output", required=True)
    evaluation.add_argument("--task", choices=("lab_cuvette_loading",), default="lab_cuvette_loading")
    evaluation.add_argument("--scene", choices=("standard",), default="standard")
    evaluation.add_argument("--backend", choices=("teacher", "gpt6"), default="teacher")
    evaluation.add_argument("--asset-id", help="Optional registered hypothesis for a separate evaluation")
    evaluation.add_argument("--episodes", type=int, default=5)
    evaluation.add_argument("--provider-config")
    evaluation.add_argument("--budget-ledger")
    evaluation.add_argument("--max-calls", type=int, default=160)
    serve = commands.add_parser("serve", help="Loopback policy RPC for existing Harness/pi0.5 adapters; physics pauses between requests")
    serve.add_argument("--output", required=True)
    serve.add_argument("--task", choices=("lab_cuvette_loading",), default="lab_cuvette_loading")
    serve.add_argument("--scene", choices=("standard",), default="standard")
    serve.add_argument("--port", type=int, default=8097)
    serve.add_argument("--headless", action="store_true")
    serve.add_argument("--dry-run", action="store_true")
    serve.set_defaults(backend="rpc", episodes=1)
    collect = commands.add_parser("collect", help="Existing sequential standard collector; one Isaac process at a time")
    collect.add_argument("--phase", choices=("verify5", "success", "controlled_failure"), help="Explicit historical Size_v1 collector")
    collect.add_argument("--collection", help="Dedicated historical Size_v1 collection")
    collect.add_argument("--output", help="New Project_v1 episode directory")
    collect.add_argument("--task", choices=("lab_cuvette_loading",), default="lab_cuvette_loading")
    collect.add_argument("--scene", choices=("standard",), default="standard")
    collect.add_argument("--backend", choices=("teacher",), default="teacher")
    collect.add_argument("--episodes", type=int, default=1)
    collect.add_argument("--controlled-stop-depth-mm", type=float)
    collect.add_argument("--episodes-per-process", type=int, choices=range(1, 6), default=5)
    collect.add_argument("--max-processes", type=int, default=8)
    collect.add_argument("--allow-after-verified-five", action="store_true")
    collect.add_argument("--headless", action="store_true")
    collect.add_argument("--dry-run", action="store_true")
    validate = commands.add_parser("validate", help="Audit a closed official collection and create a new relative-link index")
    validate.add_argument("--collection", required=True)
    validate.add_argument("--index", required=True, help="New HDF5 index inside the collection tree")
    validate.add_argument("--output", required=True, help="New JSON audit path")
    validate.add_argument("--dry-run", action="store_true")
    dataset = commands.add_parser("dataset-check", help="Read actual ACT/DP batches from an existing index; never train")
    dataset.add_argument("--index", "--path", dest="index", required=True)
    dataset.add_argument("--sample-filter", choices=("success", "failure", "all_valid"), default="success")
    dataset.add_argument("--policy", choices=("act", "dp", "both"), default="both")
    dataset.add_argument("--output", required=True, help="New JSON read-check path")
    dataset.add_argument("--dry-run", action="store_true")
    for command in (demo, evaluation, serve, collect):
        command.add_argument("--sequence", nargs="+", choices=("teacher", "early_finish", "no_progress", "unreachable", "service_timeout", "user_interrupt"),
            help="Release-only same-process acceptance: teacher/finish/time-limit/unreachable; service_timeout/user_interrupt are controlled injections. Omit for the normal selected backend")
        command.add_argument("--record-mode", choices=("collect", "eval", "diagnostic"),
            help="Explicit Project_release_v1 persistence mode; omitted preserves each version's default")
        command.add_argument("--record-purpose", choices=RECORD_PURPOSES,
            help="Release record intent, independent of success and qualification; ordinary teacher demo/collect=demonstration, eval/serve=policy_evaluation, sequence=lifecycle_diagnostic")
        command.add_argument("--project-version", type=project_version, choices=tuple(PROJECT_RELEASES), default="Project_v1",
            help="Explicit execution version; current=Project_release_v1; omitted keeps Project_v1")
    return p


def collection_path(value):
    collection = resolve_path(value)
    if collection == OUTPUT_ROOT or not collection.is_relative_to(OUTPUT_ROOT):
        raise ValueError(f"Collection must be a dedicated directory below {OUTPUT_ROOT}")
    return collection


def closed_collection(collection):
    """Refuse obvious live/incomplete runs before an audit opens their HDF5s.

    The underlying validator still makes the official per-episode decision.
    This check is an early guard, not a replacement for its process evidence.
    """
    contract = collection / "collection_contract.json"
    if not contract.is_file():
        raise ValueError(f"Official collection contract is missing: {contract}")
    runs = collection / "runs"
    for run in runs.iterdir() if runs.is_dir() else ():
        if run.is_dir():
            evidence = run / "process_exit.json"
            if not evidence.is_file() or json.loads(evidence.read_text()).get("process_exited") is not True:
                raise ValueError(f"Run is not closed; wait for the collector before reading it: {run}")


def build_command(args):
    """Build real subprocess argv without shell interpolation or output writes."""
    if getattr(args, "record_mode", None) is not None and getattr(args, "project_version", None) != "Project_release_v1":
        raise ValueError("--record-mode is supported only by --project-version Project_release_v1")
    if getattr(args, "record_purpose", None) is not None and getattr(args, "project_version", None) != "Project_release_v1":
        raise ValueError("--record-purpose is supported only by --project-version Project_release_v1")
    sequence = getattr(args, "sequence", None)
    if sequence is not None:
        if args.project_version != "Project_release_v1" or args.command not in ("demo", "collect", "eval"):
            raise ValueError("--sequence requires Project_release_v1 demo/collect/eval; serve has no acceptance sequence")
        if args.backend != "teacher" or getattr(args, "phase", None) is not None:
            raise ValueError("--sequence is an explicit teacher/lifecycle diagnostic, not a policy or historical collection")
        if args.record_purpose not in (None, "lifecycle_diagnostic", "resource_probe"):
            raise ValueError("--sequence records require lifecycle_diagnostic or resource_probe purpose")
        if any(getattr(args, key, None) is not None for key in ("provider_config", "budget_ledger", "asset_id", "controlled_stop_depth_mm")):
            raise ValueError("--sequence cannot silently ignore policy, asset or stop-depth overrides")
        if getattr(args, "gui", False) and args.headless:
            raise ValueError("Choose --gui or --headless")
        if not args.output:
            raise ValueError("Release --sequence requires a new --output directory")
        output = new_path(args.output)
        config = PROJECT_RELEASES["Project_release_v1"][1]
        record_mode = args.record_mode or ("collect" if args.command == "collect" else "eval")
        command = [sys.executable, "-m", "demos.lab_cuvette_project_release_v1.run",
            "--config", str(config), "--output", str(output), "--seed", "0",
            "--execution-purpose", args.command, "--record-mode", record_mode,
            "--record-purpose", args.record_purpose or "lifecycle_diagnostic",
            "--sequence", *sequence]
        if args.headless:
            command.append("--headless")
        if getattr(args, "gui", False):
            command.append("--gui")
        return command
    if args.command in ("demo", "eval", "serve") or (args.command == "collect" and args.phase is None):
        if not args.output:
            raise ValueError("Project collection requires --output; historical collection uses --phase and --collection")
        output = new_path(args.output)
        episodes = 1 if args.command == "demo" else args.episodes
        if not 1 <= episodes <= 20:
            raise ValueError("--episodes must be1..20")
        if getattr(args, "gui", False) and args.headless:
            raise ValueError("Choose --gui or --headless")
        module, config = PROJECT_RELEASES[args.project_version]
        command = [sys.executable, "-m", module,
            "--backend", args.backend, "--config", str(config), "--layout-mode", args.scene,
            "--seed", "0", "--episodes", str(episodes),
            "--execution-purpose", "eval" if args.command == "serve" else args.command,
            "--output", str(output)]
        if args.headless:
            command.append("--headless")
        if args.project_version == "Project_release_v1":
            record_mode = getattr(args, "record_mode", None) or ("collect" if args.command == "collect" else "eval")
            record_purpose = getattr(args, "record_purpose", None) or (
                "demonstration" if args.command in ("demo", "collect") and args.backend == "teacher"
                else "policy_evaluation")
            command += ["--record-mode", record_mode, "--record-purpose", record_purpose]
        for name in ("provider_config", "budget_ledger", "max_calls", "controlled_stop_depth_mm", "port", "asset_id"):
            value = getattr(args, name, None)
            if name == "max_calls" and args.backend != "gpt6":
                continue
            if value is not None:
                command += ["--" + name.replace("_", "-"), str(value)]
        return command
    if args.command == "collect":
        if args.project_version != "Project_v1":
            raise ValueError("Historical --phase belongs to Size_v1; omit --phase to collect Project_v1_1 episodes")
        if not args.collection:
            raise ValueError("Historical --phase requires --collection")
        collection = collection_path(args.collection)
        if args.max_processes < 1:
            raise ValueError("--max-processes must be positive")
        if args.phase == "verify5":
            new_path(collection)
        elif not args.allow_after_verified_five:
            raise ValueError("Review verify5 first, then explicitly use --allow-after-verified-five")
        command = [sys.executable, str(ROOT / "scripts/collect_lab_cuvette_size_v1_standard.py"),
            "--phase", args.phase, "--collection", str(collection), "--config", str(CONFIG),
            "--frozen-scene", str(FROZEN), "--episodes-per-process", str(args.episodes_per_process),
            "--max-processes", str(args.max_processes)]
        if args.allow_after_verified_five:
            command.append("--allow-after-verified-five")
        if args.headless:
            command.append("--headless")
        return command
    if args.command == "validate":
        collection = collection_path(args.collection)
        closed_collection(collection)
        index, output = new_path(args.index), new_path(args.output)
        if not index.is_relative_to(collection):
            raise ValueError("Relative-link index must stay inside its collection; move the whole tree together")
        if index == output:
            raise ValueError("Index and JSON audit must use different paths")
        return [sys.executable, str(ROOT / "scripts/validate_lab_cuvette_size_v1_data.py"),
            str(collection), "--config", str(CONFIG), "--frozen-scene", str(FROZEN),
            "--admission-scope", "official_collection", "--index", str(index), "--output-json", str(output)]
    if args.command == "dataset-check":
        index, output = dataset_file(args.index), new_path(args.output)
        return [sys.executable, str(Path(__file__).resolve()), "dataset-check", "--index", str(index),
            "--sample-filter", args.sample_filter, "--policy", args.policy, "--output", str(output)]
    raise ValueError("No subprocess command for " + args.command)


def frozen_check():
    from omegaconf import OmegaConf
    from demos.lab_cuvette_size_v1.frozen_scene import load_frozen, validate_frozen_scene
    frozen = load_frozen(FROZEN)
    value = validate_frozen_scene(OmegaConf.load(CONFIG), frozen, ROOT, purpose="collect")
    return dict(value, dependency_count=len(frozen["assets"]))


def doctor_configuration(project_version="Project_v1", config_path=None):
    from omegaconf import OmegaConf
    selected = existing_file(config_path) if config_path is not None else PROJECT_RELEASES[project_version][1]
    configuration = OmegaConf.load(selected)
    actual = str(configuration.get("version", ""))
    if actual != project_version:
        raise ValueError(f"Doctor config version {actual!r} conflicts with --project-version {project_version}; select the matching version/config")
    return selected


def doctor_report(project_version="Project_v1", config_path=None):
    """Portable CPU-only preflight; never starts SimulationApp or installs packages."""
    from demos.lab_cuvette_project_v1.runtime import isaac_paths, geometry_site, usd_environment
    selected_config = doctor_configuration(project_version, config_path)
    result = dict(schema="labsim.project_doctor.v2", repository=str(ROOT), python=sys.executable,
        python_version=sys.version.split()[0], simulation_started=False, GPU_initialized=False,
        files_modified=False, config=str(selected_config), project_version=project_version,
        config_sha256=sha256(selected_config), warnings=[], errors=[])
    result["modules"] = {}
    for name in ("omegaconf", "h5py", "numpy", "torch", "cv2", "scipy", "isaacsim"):
        try:
            spec = importlib.util.find_spec(name)
            result["modules"][name] = dict(available=spec is not None, origin=spec.origin if spec else None)
            if spec is None:
                result["errors"].append("Missing runtime module: " + name)
        except (ImportError, ValueError) as error:
            result["modules"][name] = dict(available=False, error=str(error))
            result["errors"].append("Runtime module lookup failed: " + name)
    if sys.version_info[:2] != (3, 11):
        result["errors"].append("Isaac Sim5.1 requires Python3.11; select existing runtime with LABSIM_PYTHON")
    try:
        paths = isaac_paths()
        result["USD_bootstrap"] = {key:str(value) for key,value in paths.items()}
        probe = subprocess.run([sys.executable, "-c", "from pxr import Usd,PhysxSchema;print(Usd.GetVersion())"],
            cwd=ROOT, env=usd_environment(), capture_output=True, text=True, timeout=30)
        result["USD_bootstrap"].update(import_exit_code=probe.returncode, USD_version=probe.stdout.strip())
        if probe.returncode:
            result["errors"].append("Discovered USD/PhysX bootstrap failed: " + probe.stderr[-1200:])
    except Exception as error:
        result["errors"].append("USD runtime discovery: " + str(error))
    try:
        geometry = geometry_site()
        probe = subprocess.run([sys.executable, "-c", "import sys;sys.path.insert(0,sys.argv[1]);import shapely;from shapely import constrained_delaunay_triangles;print(shapely.__version__)", geometry],
            cwd=ROOT, capture_output=True, text=True, timeout=30)
        result["geometry_dependency"] = dict(configured_site=geometry, import_exit_code=probe.returncode,
            shapely_version=probe.stdout.strip(), source="LABSIM_GEOMETRY_SITE, isolated default, or selected interpreter")
        if probe.returncode:
            result["errors"].append("Geometry dependency import failed: " + probe.stderr[-1200:])
    except Exception as error:
        result["errors"].append("Geometry dependency: " + str(error))
    try:
        from demos.lab_cuvette_project_v1.assets import check_assets
        from demos.lab_cuvette_project_v1.runtime import selected_asset_root
        asset_root = selected_asset_root()
        result["assets"] = check_assets(asset_root)
        if not result["assets"]["all_files_verified"]:
            result["warnings"].append("Pinned portable release not installed at selected asset root. Run ./labsim assets install --asset-root NEW_ROOT, then set LABSIM_ASSET_ROOT. Historical repository assets remain unchanged.")
    except Exception as error:
        result["errors"].append("Asset release check: " + str(error))
    result["warnings"].append("CPU preflight does not certify GUI/GPU operation or physical task success")
    result["ready_for_existing_runtime"] = not result["errors"]
    return result


def asset_rows(asset_id=None):
    registry_path = REGISTRY
    if REGISTRY == ROOT / "assets/lab_cuvette_loading/Size_v1/registry.json":
        from demos.lab_cuvette_project_v1.runtime import selected_asset_root
        cached = selected_asset_root() / "assets/lab_cuvette_loading/Size_v1/registry.json"
        if cached.is_file():
            registry_path = cached
    if lfs_pointer(registry_path):
        raise ValueError("Asset registry is a Git LFS pointer; run git lfs pull and retry")
    registry = json.loads(registry_path.read_text())
    if asset_id and asset_id not in registry["assets"]:
        raise ValueError(f"Unknown asset_id: {asset_id}")
    rows = []
    for key, item in sorted(registry["assets"].items(), key=lambda pair: pair[1]["nominal_outer_xy_mm"]):
        if asset_id and key != asset_id:
            continue
        rows.append(dict(asset_id=key, nominal_outer_xy_mm=item["nominal_outer_xy_mm"],
            actual_outer_dimensions_mm=item["actual_outer_dimensions_mm"], height_nominal_mm=item["height_nominal_mm"],
            mass_kg=item["mass_kg"], mass_source=item["mass_source"], asset_path=item["asset_path"],
            asset_sha256=item["asset_sha256"], frozen_standard_selected=key == "cuvette_xy_1000"))
    return rows


def dataset_project_version(index):
    """Inspect all episode headers; never guess a reader from the first group."""
    import h5py
    with h5py.File(index, "r") as source:
        groups = [source] if "actions" in source and "agent_pose" in source else [source[name] for name in source
            if isinstance(source[name], h5py.Group) and "actions" in source[name] and "agent_pose" in source[name]]
        versions = {str(group.attrs.get("scene_version", "")) for group in groups}
    project_versions = {version for version in versions if version.startswith("Project_v") or version == "Project_release_v1"}
    if project_versions and len(versions) != 1:
        raise ValueError("Do not mix project scene versions in one dataset-check index: " + repr(sorted(versions)))
    if project_versions:
        version = next(iter(project_versions))
        if version not in PROJECT_RELEASES:
            raise ValueError("Unsupported project scene version: " + version)
        return version
    return None  # Historical Size_v1 validation retains its existing route.


def dataset_check(args):
    index, output = dataset_file(args.index), new_path(args.output)
    version = dataset_project_version(index)
    if version:
        from scripts.read_lab_cuvette_project_v1_data import read_check
        policies = ("act", "dp") if args.policy == "both" else (args.policy,)
        options = {}
        if version == "Project_v1_1":
            from policy.dataset.lab_cuvette_project_v1_1_dataset import LabCuvetteProjectV11Dataset
            options["dataset_class"] = LabCuvetteProjectV11Dataset
        elif version == "Project_release_v1":
            from policy.dataset.lab_cuvette_project_release_dataset import LabCuvetteProjectReleaseDataset
            options["dataset_class"] = LabCuvetteProjectReleaseDataset
        value = read_check(index, sample_filter=args.sample_filter, policies=policies, **options)
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("x", encoding="utf-8") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
        print(json.dumps(dict(output=str(output), scene_version=version,
            sample_filter=args.sample_filter, policies=list(policies), optimizer_or_training_executed=False)))
        return 0
    from scripts.validate_lab_cuvette_size_v1_data import validate_reader
    frozen_check()
    policies = ("act", "dp") if args.policy == "both" else (args.policy,)
    results = [validate_reader(index, FROZEN, CONFIG, sample_filter=args.sample_filter, policy_type=policy)
               for policy in policies]
    value = dict(schema="labsim.project_dataset_check.v1", index=str(index),
        sample_filter=args.sample_filter, reader_validation=results, optimizer_or_training_executed=False,
        source_labels_modified=False)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps(dict(output=str(output), sample_filter=args.sample_filter,
        policies=list(policies), episodes=[len(row["episodes"]) for row in results],
        optimizer_or_training_executed=False), ensure_ascii=False))
    return 0


def main(argv=None):
    args = parser().parse_args(argv)
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    try:
        if args.command == "doctor":
            result = doctor_report(args.project_version, args.config)
            if args.json:
                print(json.dumps(result, ensure_ascii=False, indent=2))
            else:
                print(f"LabSim runtime: {result['python']} (Python {result['python_version']})")
                print("Project release: " + result['project_version'] + " (" + result['config'] + ")")
                print("Assets: " + json.dumps(result.get("assets", {}), ensure_ascii=False))
                for level in ("errors", "warnings"):
                    for message in result[level]:
                        print(level.upper() + ": " + message)
                print("CPU preflight: " + ("PASS" if result["ready_for_existing_runtime"] else "FAIL"))
            return 0 if result["ready_for_existing_runtime"] else 2
        if args.command == "assets":
            if args.operation != "list" or any((args.cache, args.asset_root, args.private_root, args.offline)):
                command = [sys.executable, str(ROOT / "scripts/labsim_assets.py"), args.operation]
                for name in ("cache", "asset_root", "private_root"):
                    value = getattr(args, name)
                    if value:
                        command += ["--" + name.replace("_", "-"), str(value)]
                if args.offline:
                    command.append("--offline")
                return subprocess.run(command, cwd=ROOT, check=False).returncode
            rows = asset_rows(args.asset_id)
            if args.json:
                print(json.dumps(rows, ensure_ascii=False, indent=2))
            else:
                for row in rows:
                    width = "×".join(str(value) for value in row["nominal_outer_xy_mm"])
                    selected = " [frozen standard]" if row["frozen_standard_selected"] else ""
                    print(f"{row['asset_id']}  {width}×{row['height_nominal_mm']} mm  {row['mass_kg']} kg{selected}")
                print("Size hypotheses; registry includes source hashes and mass assumptions. Frozen standard permits cuvette_xy_1000 only.")
            return 0
        command = build_command(args)
        if args.dry_run:
            print(json.dumps(dict(dry_run=True, files_created=False, simulation_started=False,
                cwd=str(ROOT), argv=command, shell_display=shlex.join(command)), ensure_ascii=False, indent=2))
            return 0
        if args.command == "dataset-check":
            return dataset_check(args)
        if args.command in ("validate",) or (args.command == "collect" and args.phase is not None):
            frozen_check()
        environment = dict(os.environ, LABSIM_PYTHON=sys.executable)
        return subprocess.run(command, cwd=ROOT, env=environment, check=False).returncode
    except (ValueError, OSError, ImportError) as error:
        print("LabSim: " + str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
