"""Inspect release-index dependencies before moving or reading a data handoff."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import h5py

from data_collectors.lab_cuvette_project_release_collector import atomic_text
from demos.lab_cuvette_project_release_v1.membership import file_sha256


def check_dependencies(index_path, *, verify_sha256=False):
    """Read only. A relative-links index requires every listed source H5."""
    path = Path(index_path).resolve()
    rows, problems = [], []
    with h5py.File(path, "r") as index:
        mode = str(index.attrs.get("index_mode", "unknown"))
        complete = bool(index.attrs.get("complete", False))
        declared = json.loads(str(index.attrs.get("membership_json", "[]")))
        by_id = {row["episode_id"]: row for row in declared if row.get("included")}
        by_source = {row["source"]: row for row in declared if row.get("included")}
        if not complete:
            problems.append("Index is not complete")
        for key in index:
            link = index.get(key, getlink=True)
            external = isinstance(link, h5py.ExternalLink)
            target = (path.parent / link.filename).resolve() if external else path
            row = dict(index_group=key, link_type="external" if external else "contained",
                       dependency=str(target), relative_dependency=link.filename if external else None,
                       must_carry_separately=external, exists=target.is_file(), readable=False,
                       sha256_checked=False)
            if not row["exists"]:
                row["error"] = "Missing source H5: " + str(target)
            else:
                try:
                    group = index[key]
                    identity = str(group.attrs["episode_id"])
                    row["episode_id"] = identity
                    expected = by_id.get(identity)
                    if external:
                        path_expected = by_source.get(link.filename)
                        if path_expected and path_expected["episode_id"] != identity:
                            raise ValueError("External source episode identity changed")
                    if expected and expected.get("finalization_id") != str(group.attrs.get("finalization_id", "")):
                        raise ValueError("Episode finalization identity changed")
                    if external and verify_sha256:
                        if not expected or not expected.get("source_h5_sha256"):
                            raise ValueError("No hash-bound source declaration; rebuild the index with the current index entry")
                        digest = file_sha256(target)
                        row.update(sha256_checked=True, actual_sha256=digest,
                                   expected_sha256=expected["source_h5_sha256"])
                        if digest != expected["source_h5_sha256"]:
                            raise ValueError("Source H5 SHA256 mismatch")
                    row["readable"] = True
                except (OSError, KeyError, ValueError) as exc:
                    row["error"] = str(exc)
            if row.get("error"):
                problems.append(row["error"])
            rows.append(row)
    return dict(schema="labsim.Project_release_v1.transfer_check.v1", index=str(path),
        index_mode=mode, index_complete=complete,
        self_contained=(mode == "copy" and not any(row["must_carry_separately"] for row in rows)),
        dependencies=rows, required_files=[str(path)] + sorted({row["dependency"] for row in rows if row["must_carry_separately"]}),
        ok=not problems, problems=problems,
        transfer_instruction="Move the index together with every relative source H5, retaining their relative directory tree."
        if any(row["must_carry_separately"] for row in rows) else "Move this one H5 file; source H5 files are not required.")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("index", type=Path)
    parser.add_argument("--verify-sha256", action="store_true", help="Read and verify every external source file against the index declaration")
    parser.add_argument("--output", type=Path, help="Optional new JSON receipt; existing files are protected")
    args = parser.parse_args(argv)
    result = check_dependencies(args.index, verify_sha256=args.verify_sha256)
    if args.output:
        if args.output.exists():
            raise FileExistsError(args.output)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        atomic_text(args.output, json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
