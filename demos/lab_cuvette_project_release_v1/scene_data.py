"""Read scene-use identity without changing episode labels or source H5 bytes."""
from __future__ import annotations

import json


def _object(group, key):
    values = []
    # configuration_json is an H5 attribute in the normal collector;
    # episode_metadata_json is a scalar dataset. Honor both representations.
    if key in group.attrs:
        values.append(group.attrs[key])
    if key in group:
        try:
            values.append(group[key].asstr()[()])
        except (AttributeError, TypeError, ValueError) as error:
            raise ValueError("Invalid embedded scene metadata: " + key) from error
    decoded = []
    for raw in values:
        try:
            value = json.loads(raw)
        except (TypeError, ValueError) as error:
            raise ValueError("Invalid embedded scene metadata: " + key) from error
        if not isinstance(value, dict):
            raise ValueError("Embedded scene metadata must be an object: " + key)
        decoded.append(value)
    if any(value != decoded[0] for value in decoded[1:]):
        raise ValueError("Conflicting embedded scene metadata: " + key)
    return decoded[0] if decoded else {}


def scene_identity(group):
    """Cross-check attrs and embedded metadata; missing historical ID is standard.

    The legacy collector's attribute whitelist did not include scene_id. The
    embedded metadata therefore remains a required fallback and disagreement
    between recorded identity layers is an error, not permission to train.
    """
    attrs = dict(group.attrs)
    embedded = _object(group, "episode_metadata_json")
    configured = _object(group, "configuration_json").get("scene_suite", {})
    if configured is None:
        configured = {}
    if not isinstance(configured, dict):
        raise ValueError("Invalid configured scene_suite identity")
    configured = dict(configured)
    if "suite_version" in configured:
        configured["scene_suite_version"] = configured["suite_version"]
    if "allowed_uses" in configured:
        configured["scene_allowed_uses"] = configured["allowed_uses"]
    sources = (("attributes", attrs), ("episode_metadata_json", embedded), ("configuration_json", configured))
    values = {}
    for field in ("scene_id", "scene_suite_version", "scene_definition_sha256", "scene_allowed_uses"):
        found = []
        for name, source in sources:
            value = source.get(field)
            if value is None:
                continue
            if field == "scene_allowed_uses":
                if isinstance(value, str):
                    try:
                        value = json.loads(value)
                    except ValueError as error:
                        raise ValueError("Invalid scene_allowed_uses metadata") from error
                if not isinstance(value, (list, tuple)) or any(not isinstance(item, str) for item in value):
                    raise ValueError("scene_allowed_uses must be a string list")
                value = sorted(value)
            else:
                value = str(value)
            found.append((name, value))
        if found and any(value != found[0][1] for _, value in found[1:]):
            raise ValueError("Conflicting recorded scene identity: " + field)
        if found:
            values[field] = found[0][1]
    values.setdefault("scene_id", "standard")
    values.setdefault("scene_suite_version", "historical_standard")
    values.setdefault("scene_allowed_uses", ["demonstration", "training", "policy_evaluation"]
        if values["scene_id"] == "standard" else ["policy_evaluation"])
    if values["scene_id"] != "standard":
        from demos.lab_cuvette_project_release_v1.scene_suite import SUITE_VERSION, validate_selection
        validate_selection(values["scene_id"], purpose="eval")
        if values["scene_suite_version"] != SUITE_VERSION:
            raise ValueError("Random-10 record is missing the current scene suite identity")
        digest = values.get("scene_definition_sha256", "")
        if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
            raise ValueError("Random-10 record is missing scene_definition_sha256")
    return values
