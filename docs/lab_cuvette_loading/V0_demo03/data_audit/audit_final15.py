"""Explicit completed roots -> formal15 audit -> existing-loader filtered index.

CPU only. Invoke after the batch owner confirms all selected runs are complete.
The original interrupted seed8008 is recorded separately and NEVER opened.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from audit_formal_batches import COMPLETION_MARKERS, audit_batches
from demos.lab_cuvette_demo03.analyze import load_json, sha256, write_new
from demos.lab_cuvette_demo03.data_check import build_index


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixed-root", type=Path, required=True)
    parser.add_argument("--random-seed-root", type=Path, action="append", required=True,
                        help="repeat for each selected completed seed; do NOT pass interrupted parent batch root")
    parser.add_argument("--excluded-trial", type=Path, required=True)
    parser.add_argument("--interruption-evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="new directory; never overwrite previous acceptance")
    args = parser.parse_args()
    fixed = args.fixed_root.resolve()
    selected = [p.resolve() for p in args.random_seed_root]
    excluded = args.excluded_trial.resolve()
    if len(selected) != 10 or len(set(selected)) != 10:
        parser.error("exactly ten unique completed random seed roots are required")
    if any(excluded == p or p in excluded.parents or excluded in p.parents for p in selected):
        parser.error("a selected random root includes the interrupted trial")
    evidence = args.interruption_evidence.resolve()
    if not evidence.is_file():
        parser.error("save explicit interruption evidence before final acceptance")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    exclusion = dict(schema="labsim.V0_demo03.interruption_exclusion.v1", trial=str(excluded),
        status="INTERRUPTED_UNADJUDICATED", workflow_success=None, data_eligible=None,
        physical_failure_verdict=None, index_excluded=True, H5_opened=False,
        reason="tool/session terminated143 before terminal state and independent score; no physical-task-failure verdict obtained; preserved without a success or physical-failure claim",
        missing_completion_markers=[n for n in COMPLETION_MARKERS if not (excluded / n).is_file()],
        evidence=str(evidence), evidence_sha256=sha256(evidence), evidence_content=load_json(evidence))
    write_new(output / "excluded_interruption.json", exclusion)
    # Explicit seed roots prevent accidental recursive opening of the original
    # random parent, which still contains the unclosed interrupted H5.
    roots = [("fixed", fixed)] + [("random", p) for p in selected]
    audit = audit_batches(roots, output / "formal_audit", {"fixed": 5, "random": 10})
    candidates = [dict(episode=r["data_inspection"]["episode"], score=r["data_inspection"]["independent_score"])
                  for r in audit["records"] if r.get("audit_pass") is True and r.get("data_eligible") is True]
    write_new(output / "qualified_candidates.json", candidates)
    if audit["batch_audit_complete"]:
        index = build_index(candidates, output / "qualified_index")
        original_hashes = {r["data_inspection"]["episode"]: r["data_inspection"]["original_sha256"]
                           for r in audit["records"] if r.get("h5_opened") is True}
        raw_unchanged = {path: sha256(path) == digest for path,digest in original_hashes.items()}
        result = dict(schema="labsim.V0_demo03.final15_acceptance.v1", audit_complete=True,
            counts=audit["counts"], qualified_count=index["eligible_count"], loader=index["loader"],
            source_H5_sha256=original_hashes, source_H5_unchanged_after_complete_audit_and_index=raw_unchanged,
            all_source_H5_unchanged=all(raw_unchanged.values()), index_path=index["index_path"],
            native_pair_success=False, real_calibrated=False, optimizer_or_training_executed=False,
            interrupted_trial_excluded=str(excluded), interrupted_H5_opened=False,
            explicit_random_seed_roots=[str(p) for p in selected], source_script_sha256=sha256(__file__))
    else:
        result = dict(schema="labsim.V0_demo03.final15_acceptance.v1", audit_complete=False,
            counts=audit["counts"], qualified_index_executed=False, training_batch_read=False,
            reason="selected formal batch audit incomplete or inconsistent; do not manufacture qualified data",
            native_pair_success=False, real_calibrated=False, optimizer_or_training_executed=False,
            interrupted_H5_opened=False, source_script_sha256=sha256(__file__))
    write_new(output / "acceptance.json", result)
    with (output / "README.md").open("x", encoding="utf-8") as stream:
        stream.write("# Formal15 completed-run acceptance\n\n")
        stream.write("The audit explicitly selects fixed5, original random seeds8000–8007, and recovered random seeds8008/8009. Original interrupted seed8008 is preserved and excluded. Its H5 was not opened. Interruption is an unadjudicated tool termination; no physical-task-failure verdict was obtained (physical_failure_verdict=null). A physical fault has neither been confirmed nor ruled out.\n\n")
        stream.write("`acceptance.json` and `formal_audit/audit.json` preserve all actual labels, source hashes, per-episode checks, assembly shifts, controller/terminal semantics and false native/calibration flags. `qualified_index/` uses external links to qualified original H5s. The loader reads a real batch through the existing MinimalPickDataset; no optimizer, model inference or training occurs.\n\n")
        stream.write("The8D action is7absolute arm position targets(rad) plus1finger position target(m). Phase-dependent finger effort caps remain auxiliary physics records; this read does not verify complete8D-only replay. See the source action_scope.md.\n")
    print(json.dumps({k: result.get(k) for k in ("audit_complete", "qualified_count", "all_source_H5_unchanged", "counts", "loader")}))


if __name__ == "__main__":
    main()
