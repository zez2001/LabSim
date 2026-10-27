"""Explicit, hash-bound usage annotations for immutable historical episodes."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

import h5py

from data_collectors.lab_cuvette_project_release_collector import atomic_text

PURPOSES = frozenset(("demonstration", "policy_evaluation", "lifecycle_diagnostic", "resource_probe"))
SCHEMA = "labsim.Project_release_v1.purpose_members.v1"


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_members(path):
    """Read explicit annotations. Every member binds identity, file, and bytes."""
    if path is None:
        return {}, None
    path = Path(path).resolve()
    payload = json.loads(path.read_text())
    if payload.get("schema") != SCHEMA:
        raise ValueError("Unsupported purpose members schema: " + str(path))
    members = {}
    for raw in payload["members"]:
        row = dict(raw)
        identity = row["episode_id"]
        if not isinstance(identity, str) or not identity or identity in members:
            raise ValueError("Missing or duplicate membership episode_id")
        purpose = row.get("record_purpose", "unknown")
        if purpose not in PURPOSES | {"unknown"}:
            raise ValueError("Unknown member record_purpose: " + str(purpose))
        digest = row.get("source_h5_sha256", "")
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError("Member requires source_h5_sha256: " + identity)
        row["source_path"] = (path.parent / row["source_h5"]).resolve()
        members[identity] = row
    return members, dict(path=str(path), sha256=file_sha256(path), schema=SCHEMA,
                         provenance=payload.get("provenance", {}))


def write_members(run_directory, destination, assignments, *, provenance=None, expected_hashes=None):
    """Create a new sidecar from caller-declared purposes; never relabel H5."""
    run, destination = Path(run_directory).resolve(), Path(destination).resolve()
    if destination.exists():
        raise FileExistsError(destination)
    rows, seen = [], set()
    for source in sorted(run.glob("episode_*/dataset/episode_*.h5")):
        with h5py.File(source) as episode:
            identity = str(episode.attrs["episode_id"])
        if identity in seen:
            raise ValueError("Duplicate source episode identity: " + identity)
        seen.add(identity)
        if identity not in assignments:
            continue
        purpose = assignments[identity]
        if purpose not in PURPOSES | {"unknown"}:
            raise ValueError("Unknown record_purpose: " + str(purpose))
        digest = file_sha256(source)
        if expected_hashes and identity in expected_hashes and digest != expected_hashes[identity]:
            raise ValueError("Curated policy source H5 hash no longer matches reviewed evidence")
        rows.append(dict(episode_id=identity,
            source_h5=os.path.relpath(source, destination.parent),
            source_h5_sha256=digest, source_bytes=source.stat().st_size,
            record_purpose=purpose))
    absent = sorted(set(assignments) - seen)
    if absent:
        raise ValueError("Explicit member episode IDs not found: " + ", ".join(absent))
    payload = dict(schema=SCHEMA, members=rows, provenance=provenance or {},
                   raw_h5_modified=False, task_labels_modified=False)
    destination.parent.mkdir(parents=True, exist_ok=True)
    atomic_text(destination, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return payload


def import_curated_policy(run_directory, curated_path, destination):
    """Reuse the reviewed historical π0.5 membership, not labels or duration."""
    curated_path = Path(curated_path).resolve()
    curated = json.loads(curated_path.read_text())
    assignments = {key: "policy_evaluation" for key in curated["included_actual_model_episode_ids"]}
    for key in curated["excluded_diagnostic_episode_ids"]:
        if key in assignments:
            raise ValueError("Curated membership overlap: " + key)
        assignments[key] = "resource_probe"
    expected = curated.get("source_h5_sha256")
    policy_ids = curated["included_actual_model_episode_ids"]
    if expected and len(policy_ids) != 1:
        raise ValueError("A single reviewed source H5 hash requires exactly one policy member")
    payload = write_members(run_directory, destination, assignments, provenance=dict(
        method="explicit_existing_curated_membership", source=str(curated_path),
        source_sha256=file_sha256(curated_path), purpose_inferred_from_labels_or_duration=False),
        expected_hashes={policy_ids[0]: expected} if expected else None)
    return payload


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_directory", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--curated-policy-manifest", type=Path)
    source.add_argument("--assign", action="append", metavar="PURPOSE=EPISODE_ID",
                        help="Repeat for explicit member annotations; unknown is allowed")
    args = parser.parse_args(argv)
    if args.curated_policy_manifest:
        result = import_curated_policy(args.run_directory, args.curated_policy_manifest, args.output)
    else:
        assignments = {}
        for value in args.assign:
            purpose, identity = value.split("=", 1)
            if identity in assignments:
                parser.error("Duplicate explicit episode ID: " + identity)
            assignments[identity] = purpose
        result = write_members(args.run_directory, args.output, assignments,
                               provenance=dict(method="explicit_command_line_assignment"))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
