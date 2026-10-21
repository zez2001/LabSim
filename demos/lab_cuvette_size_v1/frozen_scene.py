"""Standard-only collection/training contract for the independent Size_v1 task.

This module has no Isaac dependency. A training RNG seed is deliberately absent
from the scene fingerprint: changing it never enables scene randomization.
Controller deviations are recorded separately and never change scene geometry.
"""
from __future__ import annotations

import copy
import hashlib
import json
import subprocess
from pathlib import Path


SCHEMA = "labsim.lab_cuvette_loading.Size_v1.frozen_scene.v1"
SCENE_KEYS = ("version", "scene_mode", "source", "asset_id", "asset_directory",
              "derived_directory", "collision_scheme", "vessel", "scene", "rack",
              "adapter", "robot", "physics", "cameras", "lights", "lighting",
              "video", "acceptance", "demo_release", "geometry", "gripper")
RANDOM_RANGES = ("rack_translation_half_range_m", "instrument_translation_half_range_m",
                 "yaw_half_range_deg", "in_slot_translation_m")
CONDITION_GROUPS = ("natural", "deterministic_action_deviation")


def plain(config):
    """Return JSON primitives from a dict or existing OmegaConf configuration."""
    try:
        from omegaconf import OmegaConf
        if OmegaConf.is_config(config):
            config = OmegaConf.to_container(config, resolve=True)
    except ImportError:
        pass
    return json.loads(json.dumps(config, allow_nan=False))


def canonical_sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def file_sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def prepare_standard_config(config):
    """Explicitly disable inherited scene randomization; preserve source cfg.

    Call this while creating the new Size_v1 config, then save that config. At
    runtime use validation, not this function, so silent overrides are rejected.
    """
    value = copy.deepcopy(plain(config))
    value.setdefault("env", {})["mode"] = "standard"
    value["env"]["scene_randomization_enabled"] = False
    randomization = value.setdefault("randomization", {})
    randomization["enabled"] = False
    randomization.pop("actual", None)
    for key in RANDOM_RANGES:
        randomization[key] = 0.0
    randomization["asset_randomization_enabled"] = False
    randomization["light_randomization_enabled"] = False
    randomization["physics_randomization_enabled"] = False
    randomization["layout_randomization_enabled"] = False
    value.setdefault("collection", {}).update(mode="standard", scene_randomization_enabled=False)
    value.setdefault("training_scene", {}).update(mode="standard", scene_randomization_enabled=False,
        automatic_validation_mode="standard", automatic_validation_randomization_enabled=False)
    return value


def _nonzero(value):
    if isinstance(value, (list, tuple)):
        return any(_nonzero(item) for item in value)
    if isinstance(value, dict):
        return any(_nonzero(item) for item in value.values())
    return isinstance(value, (int, float)) and not isinstance(value, bool) and abs(value) > 1e-15


def validate_execution_mode(config, purpose="collect", *, explicit_random=False):
    """Reject hidden layout/asset/light/physics changes before reset or training.

    Explicit random is supported only for a future evaluation call. It cannot
    enter this round's collect/train/automatic-validation entry points.
    """
    cfg = plain(config)
    if purpose not in {"collect", "train", "validation", "eval"}:
        raise ValueError("Unknown execution purpose")
    mode = cfg.get("env", {}).get("mode")
    if mode == "random":
        if purpose != "eval" or explicit_random is not True:
            raise ValueError("Size_v1 random requires explicit eval; collect/train/validation are standard only")
        return dict(purpose=purpose, mode=mode, explicit_random=True)
    if mode != "standard":
        raise ValueError("Size_v1 requires explicit env.mode=standard")
    errors = []
    if cfg.get("env", {}).get("scene_randomization_enabled") is not False:
        errors.append("env.scene_randomization_enabled must be false")
    section = cfg.get("randomization")
    if not isinstance(section, dict) or section.get("enabled") is not False:
        errors.append("randomization.enabled must be explicitly false")
        section = section if isinstance(section, dict) else {}
    for key, value in section.items():
        lower = key.lower()
        if (lower.endswith("enabled") or lower.startswith("enable_")) and value is not False:
            errors.append(f"randomization.{key} must be false")
        if any(word in lower for word in ("range", "jitter", "sigma", "noise", "perturb", "translation", "yaw")) and _nonzero(value):
            errors.append(f"randomization.{key} must be zero")
    actual = section.get("actual")
    if actual:
        errors.append("randomization.actual from a previous random reset is forbidden")
    for name in ("scene", "rack", "vessel", "physics", "lights", "lighting", "cameras"):
        def scan(value, path):
            if not isinstance(value, dict):
                return
            for key, item in value.items():
                token = key.lower()
                if ("random" in token and token not in {"random_seed", "training_random_seed"}) and item not in (False, None, 0, "standard"):
                    errors.append(f"{path}.{key} contains active/unknown scene randomization")
                scan(item, path + "." + key)
        scan(cfg.get(name, {}), name)
    for name in ("collection", "training_scene"):
        value = cfg.get(name, {})
        if value.get("mode", "standard") != "standard" or value.get("scene_randomization_enabled", False) is not False:
            errors.append(f"{name} must remain standard with randomization false")
        if name == "training_scene" and (value.get("automatic_validation_mode", "standard") != "standard" or value.get("automatic_validation_randomization_enabled", False) is not False):
            errors.append("automatic validation must remain standard")
    if errors:
        raise ValueError("Invalid Size_v1 frozen scene: " + "; ".join(errors))
    return dict(purpose=purpose, mode="standard", scene_randomization_enabled=False)


def scene_projection(config):
    cfg = plain(config)
    projection = {key: cfg[key] for key in SCENE_KEYS if key in cfg}
    # Time discretization, sensor ordering and nominal initial state are fixed.
    projection["env"] = {key: cfg.get("env", {}).get(key) for key in
        ("mode", "scene_randomization_enabled", "control_hz", "physics_hz", "render_zero_delay")}
    projection["randomization"] = cfg.get("randomization")
    return projection


def freeze_scene(config, asset_paths, root, *, code_commit=None):
    """Bind explicit scene fields and all supplied USD/material dependencies.

    ``asset_paths`` must include transitive asset dependencies selected by the
    existing USD asset audit. This function does not pretend to discover USD
    references without loading USD. Paths under root are portable relative IDs.
    """
    cfg = plain(config)
    validate_execution_mode(cfg, "collect")
    root = Path(root).resolve()
    assets = {}
    resolved_paths = {(Path(path) if Path(path).is_absolute() else root / path).resolve()
                      for path in asset_paths}
    for source in sorted(resolved_paths, key=str):
        if not source.is_file():
            raise FileNotFoundError(source)
        try:
            name = source.relative_to(root).as_posix()
        except ValueError as error:
            raise ValueError("Frozen asset must be a repository-relative file: " + str(source)) from error
        assets[name] = dict(sha256=file_sha(source), bytes=source.stat().st_size)
    if not assets:
        raise ValueError("Frozen scene requires explicit asset dependencies")
    projection = scene_projection(cfg)
    payload = dict(scene=projection, assets=assets)
    if code_commit is None:
        code_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    return dict(schema=SCHEMA, frozen_scene_sha256=canonical_sha(payload), **payload,
        asset_dependency_scope="explicit transitive list supplied by existing USD audit",
        code_commit=code_commit, control_config_sha256=canonical_sha({
            key: cfg.get(key) for key in ("control", "experiment", "env")}),
        mode_rules=dict(collect="standard", train="standard", automatic_validation="standard",
            eval_random="explicit option only; not part of this collection"),
        training_rng_seed_is_not_scene_randomization=True, real_calibrated=False)


def load_frozen(path):
    manifest = json.loads(Path(path).read_text(encoding="utf-8"))
    if manifest.get("schema") != SCHEMA:
        raise ValueError("Unsupported frozen scene manifest")
    if manifest.get("frozen_scene_sha256") != canonical_sha({
        "scene": manifest.get("scene"), "assets": manifest.get("assets")}):
        raise ValueError("Frozen manifest payload hash does not match")
    return manifest


def validate_frozen_scene(config, manifest, root, *, purpose="collect", explicit_random=False):
    validate_execution_mode(config, purpose, explicit_random=explicit_random)
    if isinstance(manifest, (str, Path)):
        manifest = load_frozen(manifest)
    expected = manifest.get("frozen_scene_sha256")
    if expected != canonical_sha({"scene": manifest.get("scene"), "assets": manifest.get("assets")}):
        raise ValueError("Frozen manifest payload was modified")
    if plain(config).get("env", {}).get("mode") == "random":
        # An explicitly separate future evaluation may randomize assemblies. It
        # must not claim membership of the fixed-scene collection.
        return dict(frozen_scene_match=False, mode="random", fixed_collection_eligible=False)
    actual_scene = scene_projection(config)
    if canonical_sha(actual_scene) != canonical_sha(manifest["scene"]):
        changed = [key for key in sorted(set(actual_scene) | set(manifest["scene"]))
                   if actual_scene.get(key) != manifest["scene"].get(key)]
        raise ValueError("Frozen scene configuration changed: " + ", ".join(changed))
    root = Path(root).resolve()
    for name, evidence in manifest["assets"].items():
        source = (root / name).resolve()
        if not source.is_relative_to(root) or not source.is_file() or file_sha(source) != evidence["sha256"]:
            raise ValueError("Frozen asset missing or changed: " + name)
    return dict(frozen_scene_match=True, frozen_scene_sha256=expected, mode="standard",
                fixed_collection_eligible=True)


def episode_metadata(config, manifest, *, condition_group="natural", deviation=None):
    if condition_group not in CONDITION_GROUPS:
        raise ValueError("condition_group must be natural or deterministic_action_deviation")
    if condition_group == "natural" and deviation:
        raise ValueError("Natural controller episodes cannot hide action deviations")
    if condition_group == "deterministic_action_deviation" and not deviation:
        raise ValueError("Action deviation episodes require the actual stage, value, unit and controller version")
    cfg = plain(config)
    return dict(asset_id=cfg.get("asset_id", cfg.get("vessel", {}).get("asset_id", "unknown")),
        condition_group=condition_group, frozen_scene_sha256=manifest["frozen_scene_sha256"],
        control_config_sha256=canonical_sha({key: cfg.get(key) for key in ("control", "experiment", "env")}),
        code_commit=manifest["code_commit"], scene_mode="standard",
        deterministic_action_deviation=copy.deepcopy(deviation), real_calibrated=False)
