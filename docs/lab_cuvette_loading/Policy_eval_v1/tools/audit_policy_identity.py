#!/usr/bin/env python3
"""Offline GPT policy identity and append-only budget audit; no model imports.

Reads only explicitly named files. Never reads process credentials, calls an
API, initializes a GPU, or opens the budget ledger for writing. Output is a
sanitized summary, not a copy of request/usage records.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical_digest(value):
    data = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(data.encode()).hexdigest()


def inside(root, relative):
    path = (root / relative).resolve()
    path.relative_to(root)
    return path


def audit(root, identity, *, allow_budget_progress=False):
    errors = []
    source_checks = []
    for relative, expected in identity["profile"]["frozen_policy_file_sha256"].items():
        path = inside(root, relative)
        actual = digest(path) if path.is_file() else None
        match = actual == expected
        source_checks.append(dict(path=relative, expected_sha256=expected,
                                  actual_sha256=actual, unchanged=match))
        if not match:
            errors.append("Frozen policy/config file changed or missing: " + relative)

    before = identity["budget_before"]
    budget_path = inside(root, before["ledger_path"])
    budget = json.loads(budget_path.read_text())
    attempts = budget["attempts"]
    count = int(before["prefix_attempt_count"])
    prefix_unchanged = (len(attempts) >= count and
                        canonical_digest(attempts[:count]) ==
                        before["prefix_attempts_canonical_sha256"])
    if not prefix_unchanged:
        errors.append("Historical budget prefix changed or removed")
    caps_unchanged = (budget["max_requests"] == before["max_requests"] and
                      budget["max_estimated_usd"] == before["max_estimated_usd"])
    if not caps_unchanged:
        errors.append("Shared budget caps changed")
    used = sum(float(item["charged_estimate_usd"]) for item in attempts)
    if used > float(before["max_estimated_usd"]) + 1e-8:
        errors.append("Estimated budget exceeded frozen cap")
    if len(attempts) > int(before["max_requests"]):
        errors.append("Network-attempt count exceeded frozen cap")
    exact_ledger_match = digest(budget_path) == before["ledger_sha256"]
    if not allow_budget_progress and not exact_ledger_match:
        errors.append("Ledger changed: use --allow-budget-progress after actual evaluation")
    statuses = collections.Counter(item["status"] for item in attempts)
    if statuses.get("RESERVED", 0):
        errors.append("Budget still has active/unresolved RESERVED attempts")

    profile = json.loads(inside(root, identity["profile"]["path"]).read_text())
    # No secrets or environment-variable values are read. The stored provider
    # profile contains only the name of the process credential variable.
    model_match = profile.get("model") == identity["model"]["requested_model"]
    if not model_match:
        errors.append("Requested model changed")
    return dict(
        schema="labsim.Policy_eval_v1.policy_identity_audit.v1",
        passed=not errors, errors=errors,
        frozen_policy_checks=source_checks,
        model_match=model_match,
        budget=dict(
            path=before["ledger_path"], sha256=digest(budget_path),
            historical_prefix_unchanged=prefix_unchanged,
            historical_prefix_attempt_count=count,
            historical_prefix_canonical_sha256=canonical_digest(attempts[:count]),
            caps_unchanged=caps_unchanged, exact_before_file_match=exact_ledger_match,
            allow_budget_progress=allow_budget_progress,
            max_estimated_usd=budget["max_estimated_usd"], max_requests=budget["max_requests"],
            before_attempts=count, before_estimated_usd=round(float(before["estimated_usd"]), 12),
            network_attempts=len(attempts), estimated_usd=round(used, 12),
            added_network_attempts=len(attempts) - count,
            added_estimated_usd=round(used - float(before["estimated_usd"]), 12),
            remaining_estimated_usd=round(float(before["max_estimated_usd"]) - used, 12),
            remaining_network_attempts=int(before["max_requests"]) - len(attempts),
            status_counts=dict(statuses), billing_actual_usd=None,
            cost_semantics="Returned usage times configured rates; unknown usage retains reservation. Actual intermediary invoice unavailable."),
        audit_scope="Policy source/config hashes and historical budget prefix/caps; no credential access or network/GPU activity")


def self_test():
    """Exercise real file mutation and budget-prefix failures in a temp tree."""
    with tempfile.TemporaryDirectory(prefix="labsim-policy-identity-test-") as temporary:
        root = Path(temporary)
        source = root / "policy.py"
        source.write_text("frozen policy\n")
        profile = root / "profile.json"
        profile.write_text(json.dumps(dict(model="gpt-6-astra")))
        ledger = root / "budget.json"
        initial = dict(max_requests=1500, max_estimated_usd=30.0,
                       attempts=[dict(status="OK", charged_estimate_usd=1.0)])
        ledger.write_text(json.dumps(initial))
        identity = dict(profile=dict(path="profile.json", frozen_policy_file_sha256={
                            "policy.py": digest(source), "profile.json": digest(profile)}),
                        model=dict(requested_model="gpt-6-astra"),
                        budget_before=dict(ledger_path="budget.json", ledger_sha256=digest(ledger),
                            prefix_attempt_count=1,
                            prefix_attempts_canonical_sha256=canonical_digest(initial["attempts"]),
                            max_requests=1500, max_estimated_usd=30.0, estimated_usd=1.0))
        assert audit(root, identity)["passed"]
        initial["attempts"].append(dict(status="OK", charged_estimate_usd=0.1))
        ledger.write_text(json.dumps(initial))
        assert not audit(root, identity)["passed"]
        assert audit(root, identity, allow_budget_progress=True)["passed"]
        source.write_text("changed policy\n")
        assert not audit(root, identity, allow_budget_progress=True)["passed"]
        source.write_text("frozen policy\n")
        initial["attempts"][0]["charged_estimate_usd"] = 0.0
        ledger.write_text(json.dumps(initial))
        assert not audit(root, identity, allow_budget_progress=True)["passed"]
        initial["attempts"][0]["charged_estimate_usd"] = 1.0
        initial["max_estimated_usd"] = 31.0
        ledger.write_text(json.dumps(initial))
        assert not audit(root, identity, allow_budget_progress=True)["passed"]
    return dict(passed=True, checks=6,
                cases=["unchanged", "strict budget change rejection", "valid append",
                       "source drift rejection", "historical prefix tamper rejection", "cap drift rejection"])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[4])
    parser.add_argument("--identity", type=Path,
                        default=Path(__file__).resolve().parents[1] / "gpt_identity.json")
    parser.add_argument("--allow-budget-progress", action="store_true",
                        help="Allow real appended calls; old attempts and original caps must remain unchanged")
    parser.add_argument("--output", type=Path, help="Optional new JSON receipt; refuses overwrite")
    parser.add_argument("--self-test", action="store_true", help="Six local fixture checks, no project writes")
    args = parser.parse_args(argv)
    if args.output is not None and args.output.exists():
        parser.error("Output already exists: " + str(args.output))
    if args.self_test:
        result = self_test()
    else:
        root = args.root.resolve()
        identity = json.loads(args.identity.read_text())
        result = audit(root, identity, allow_budget_progress=args.allow_budget_progress)
        result["identity_sha256"] = digest(args.identity)
        try:
            result["audit_code_commit"] = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
        except (FileNotFoundError, subprocess.CalledProcessError):
            result["audit_code_commit"] = None
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x") as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
    # Keep terminal output compact and credential-free.
    print(json.dumps({key: result[key] for key in ("passed", "errors", "checks", "budget")
                      if key in result}, ensure_ascii=False, allow_nan=False))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
