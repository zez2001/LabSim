"""Verify historical evidence, unchanged runtime/assets and bounded API ledger.

Read-only checks use the final Progress v1.2 receipt as a pinned reference.
Only this round's authorized ledger append is exempt from byte-for-byte file
identity. Its old 333-attempt prefix and original caps are audited separately.
No model imports, GPU initialization, downloads or credential reads occur.

Run after committing and pushing the final source, using a new receipt path::

    python docs/lab_cuvette_loading/Policy_eval_v1/tools/protection.py \
      --root . --output outputs/lab_cuvette_loading/Policy_eval_v1/protection_final.json

The optional --self-test uses only temporary local fixture files and Git.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile


SCHEMA = "labsim.Policy_eval_v1.final_protection.v1"
BASELINE_COMMIT = "3ca253324b1ec540ae5ec07f2110c9c091f6ddd1"
REFERENCE = "outputs/lab_cuvette_loading/Progress_v1_2/publication/protection_final.json"
REFERENCE_SHA256 = "aa4c3c2efbf856d58c3d8c05ef42d067f888ee729113afd8dcf61bd96636a0c6"
ORIGINAL_ROOT = Path("/home/wujing/Desktop/vla/LabSim")
LEDGER = "outputs/lab_cuvette_loading/Project_v1/cubence_budget.json"
EXPECTED_HISTORY_COUNT = 599
EXPECTED_TEACHER_COUNT = 10
HF_REVISION = "bb880f098180c291f6f65995f969d48047207067"
ALLOWED_PREFIXES = (
    "config/lab_cuvette_loading/Policy_eval_v1/",
    "demos/lab_cuvette_policy_eval_v1/",
    "docs/lab_cuvette_loading/Policy_eval_v1/",
    "docs/agent_handoff/Policy_eval_v1_current/",
    "tests/test_lab_cuvette_policy_eval_",
)
ALLOWED_FILES = {
    "README.md", "README_CN.md", "README_EN.md",
    "scripts/run_lab_cuvette_policy_eval.py",
    "docs/agent_handoff/package.json",
    "docs/agent_handoff/README.md",
    ".github/workflows/cpu-contracts.yml",
    ".gitattributes",
}
PROTECTED_PATHS = (
    "assets", "collectors", "controllers", "tasks", "SLAI_Lab", "local_assets",
    "policy", "policy_backends", "factories",
    "config/lab_cuvette_loading/Project_release_v1",
    "config/lab_cuvette_loading/Project_v1",
    "config/lab_cuvette_loading/Project_v1_1",
    "config/lab_cuvette_loading/Progress_v1",
    "config/lab_cuvette_loading/Progress_v1_2",
    "demos/lab_cuvette_progress_v1", "demos/lab_cuvette_env_v1",
    "demos/lab_cuvette_size_v1", "demos/lab_cuvette_project_v1",
    "demos/lab_cuvette_project_v1_1", "demos/lab_cuvette_project_release_v1",
)


def sha(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(8 << 20), b""):
            value.update(block)
    return value.hexdigest()


def git(root, *args):
    # Per-invocation option avoids Git's C-quoted Chinese path false positive;
    # never modify the user's global or repository Git configuration.
    return subprocess.check_output(
        ["git", "-c", "core.quotepath=false", *args], cwd=root, text=True)


def changed_names(root, *args):
    # NUL delimiters preserve whitespace and Unicode in actual file names.
    # Insert the option before any '--' separator and literal pathspecs.
    return [value for value in git(root, args[0], "-z", *args[1:]).split("\0") if value]


def allowed_path(name):
    return name in ALLOWED_FILES or name.startswith(ALLOWED_PREFIXES)


def relative_source(name):
    path = Path(name)
    if path.is_absolute():
        try:
            return path.relative_to(ORIGINAL_ROOT).as_posix()
        except ValueError as error:
            raise ValueError("Historical source is outside the recorded repository: " + str(path)) from error
    if path.as_posix() != name or ".." in path.parts or not name:
        raise ValueError("Invalid historical source path: " + str(name))
    return path.as_posix()


def rooted(root, name):
    path = (root / relative_source(name)).resolve()
    if not path.is_relative_to(root):
        raise ValueError("Historical source escapes the selected root: " + str(name))
    return path


def verify_file(root, record):
    relative = relative_source(record["path"])
    source = rooted(root, relative)
    actual = sha(source) if source.is_file() else None
    expected = record["expected_sha256"]
    return dict(path=relative, expected_sha256=expected, actual_sha256=actual,
                bytes=source.stat().st_size if source.is_file() else None,
                unchanged=actual == expected)


def historical_groups(reference):
    old = reference["historical_files"]
    excluded = [row for row in old if relative_source(row["path"]) == LEDGER]
    protected = [row for row in old if relative_source(row["path"]) != LEDGER]
    teacher = reference["new_closed_run_files"]
    if len(excluded) != 1 or len(protected) != EXPECTED_HISTORY_COUNT:
        raise ValueError("Reference must contain exactly 599 protected historical files and one authorized ledger")
    if len(teacher) != EXPECTED_TEACHER_COUNT:
        raise ValueError("Reference must contain exactly 10 closed Teacher files")
    names = [relative_source(row["path"]) for row in protected]
    if len(names) != len(set(names)):
        raise ValueError("Duplicate historical identities in reference")
    if not all(row.get("unchanged") is True for row in [*old, *teacher]):
        raise ValueError("Reference itself does not assert intact historical evidence")
    return protected, teacher, excluded[0]


def import_file(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError("Cannot load explicit local audit tool: " + str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verify(root, *, asset_root=None):
    root = Path(root).resolve()
    errors = []
    reference_path = root / REFERENCE
    actual_reference_sha = sha(reference_path)
    if actual_reference_sha != REFERENCE_SHA256:
        raise ValueError("Pinned Progress v1.2 protection receipt SHA256 differs")
    reference = json.loads(reference_path.read_text())
    if reference["final_commit"] != BASELINE_COMMIT:
        raise ValueError("Reference final commit is not the frozen Progress v1.2 source")
    historical, teacher, excluded = historical_groups(reference)
    head = git(root, "rev-parse", "HEAD").strip()
    branch = git(root, "branch", "--show-current").strip()
    subprocess.check_call(["git", "merge-base", "--is-ancestor", BASELINE_COMMIT, head], cwd=root)
    status = git(root, "status", "--short").strip()
    committed = changed_names(root, "diff", "--no-renames", "--name-only", BASELINE_COMMIT, head)
    working = changed_names(root, "diff", "--no-renames", "--name-only", "HEAD")
    untracked = changed_names(root, "ls-files", "--others", "--exclude-standard")
    outside_scope = [name for name in committed if not allowed_path(name)]
    protected_changes = changed_names(root, "diff", "--no-renames", "--name-only", BASELINE_COMMIT,
                                      head, "--", *PROTECTED_PATHS)
    protected_working = changed_names(root, "diff", "--no-renames", "--name-only", "HEAD", "--", *PROTECTED_PATHS)
    if outside_scope:
        errors.append("Committed files outside this round's evaluation scope")
    if protected_changes or protected_working:
        errors.append("Protected physical/policy/Progress runtime paths changed")
    if status:
        errors.append("Worktree is dirty; final protection requires a committed clean source")

    historical_checks = [verify_file(root, row) for row in historical]
    teacher_checks = [verify_file(root, row) for row in teacher]
    if not all(row["unchanged"] for row in historical_checks):
        errors.append("At least one protected historical file changed or is missing")
    if not all(row["unchanged"] for row in teacher_checks):
        errors.append("At least one previous closed Teacher file changed or is missing")

    identity_path = root / "docs/lab_cuvette_loading/Policy_eval_v1/gpt_identity.json"
    identity = json.loads(identity_path.read_text())
    before = identity["budget_before"]
    ledger_identity_bound = (
        before["ledger_path"] == LEDGER
        and before["ledger_sha256"] == excluded["expected_sha256"]
        and int(before["prefix_attempt_count"]) == 333
        and int(before["max_requests"]) == 1500
        and float(before["max_estimated_usd"]) == 30.0)
    if not ledger_identity_bound:
        errors.append("Policy identity is not bound to the authorized original ledger/caps/prefix")
    auditor_path = root / "docs/lab_cuvette_loading/Policy_eval_v1/tools/audit_policy_identity.py"
    auditor = import_file("labsim_policy_eval_budget_protection", auditor_path)
    budget = auditor.audit(root, identity, allow_budget_progress=True)
    if budget.get("passed") is not True:
        errors.append("Frozen policy identity or append-only ledger audit failed")

    # Reuse the current project checker, which is standard-library-only and
    # validates local content against the unchanged lock. It never downloads.
    assets_path = root / "demos/lab_cuvette_project_v1/assets.py"
    assets = import_file("labsim_policy_eval_asset_protection", assets_path)
    selected_asset_root = Path(asset_root or reference["published_assets"]["asset_root"]).resolve()
    published = assets.check_assets(selected_asset_root,
        lock_path=root / "config/lab_cuvette_loading/Project_v1/assets.lock.json")
    if published.get("all_files_verified") is not True or published.get("required_files") != 83:
        errors.append("Published 83-file asset dependency check failed")
    if published.get("revision") != HF_REVISION:
        errors.append("Published HF asset revision changed")
    head_after = git(root, "rev-parse", "HEAD").strip()
    status_after = git(root, "status", "--short").strip()
    if head_after != head or status_after != status:
        errors.append("Source HEAD/worktree changed while protection checks were running")

    value = dict(
        schema=SCHEMA, utc=datetime.now(timezone.utc).isoformat(), passed=not errors, errors=errors,
        baseline_commit=BASELINE_COMMIT, head=head, final_commit=head, branch=branch,
        checked_source_state="clean_committed" if not status else "dirty_not_final",
        reference=dict(path=REFERENCE, sha256=actual_reference_sha, pinned_sha256=REFERENCE_SHA256),
        historical_files=historical_checks, historical_file_count=len(historical_checks),
        all_historical_hashes_unchanged=all(row["unchanged"] for row in historical_checks),
        prior_closed_teacher_files=teacher_checks, prior_closed_teacher_file_count=len(teacher_checks),
        prior_closed_teacher_hashes_unchanged=all(row["unchanged"] for row in teacher_checks),
        authorized_ledger_exception=dict(path=LEDGER,
            historical_file_sha256=excluded["expected_sha256"],
            whole_file_hash_not_required_to_match=True, frozen_identity_bound=ledger_identity_bound,
            justification="User-authorized actual calls append to this shared ledger; old333 prefix and caps remain protected"),
        budget_and_policy_audit=dict(identity_path=str(identity_path.relative_to(root)),
            identity_sha256=sha(identity_path), auditor_path=str(auditor_path.relative_to(root)),
            auditor_sha256=sha(auditor_path), **budget),
        changed_files_since_baseline=committed, outside_evaluation_scope_changes=outside_scope,
        protected_runtime_tree_changes=protected_changes,
        protected_runtime_working_changes=protected_working,
        protected_runtime_unchanged=not protected_changes and not protected_working,
        git_worktree_status=status, git_worktree_status_after=status_after, head_after=head_after,
        working_tree_changes=working, untracked_files=untracked,
        published_assets=published,
        scope="Historical evidence and last Teacher hashes, unchanged runtime/Progress/source assets, local83 assets, append-only budget; no credential access, model call, network upload or asset publication")
    return value


def self_test():
    """Exercise Unicode Git paths, scope rules and ledger exclusion locally."""
    checks = []
    with tempfile.TemporaryDirectory(prefix="labsim-eval-protection-test-") as temporary:
        root = Path(temporary).resolve()
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        source = root / "历史几何.txt"
        source.write_text("original geometry\n")
        git(root, "add", "历史几何.txt")
        subprocess.run(["git", "-c", "user.name=Protection test", "-c", "user.email=test@example.invalid",
                        "commit", "-qm", "baseline"], cwd=root, check=True)
        baseline = git(root, "rev-parse", "HEAD").strip()
        record = dict(path="历史几何.txt", expected_sha256=sha(source))
        assert verify_file(root, record)["unchanged"]
        source.write_text("changed geometry\n")
        assert not verify_file(root, record)["unchanged"]
        names = changed_names(root, "diff", "--name-only", baseline)
        assert names == ["历史几何.txt"]
        assert changed_names(root, "diff", "--name-only", baseline, "--", "历史几何.txt") == names
        checks.extend(["original hash accepted", "tampered hash rejected", "Unicode Git path preserved"])
        fixture = dict(historical_files=[dict(path=f"history/{i}", expected_sha256="0" * 64, unchanged=True)
                       for i in range(EXPECTED_HISTORY_COUNT)] +
                       [dict(path=LEDGER, expected_sha256="1" * 64, unchanged=True)],
                       new_closed_run_files=[dict(path=f"teacher/{i}", expected_sha256="2" * 64, unchanged=True)
                       for i in range(EXPECTED_TEACHER_COUNT)])
        old, teacher, excluded = historical_groups(fixture)
        assert len(old) == 599 and len(teacher) == 10 and excluded["path"] == LEDGER
        assert all(row["path"] != LEDGER for row in old)
        checks.append("only authorized ledger excluded;599 history and10 Teacher retained")
        assert allowed_path("docs/lab_cuvette_loading/Policy_eval_v1/报告.docx")
        assert allowed_path("scripts/run_lab_cuvette_policy_eval.py")
        assert not allowed_path("config/lab_cuvette_loading/Project_release_v1/standard.yaml")
        assert not allowed_path("demos/lab_cuvette_progress_v1/core.py")
        checks.append("new evaluation scope allowed; old physics/Progress rejected")
        try:
            rooted(root, "../escape")
        except ValueError:
            checks.append("path escape rejected")
        else:
            raise AssertionError("Escaping evidence path accepted")
    return dict(schema=SCHEMA, passed=True, checks=checks, check_count=len(checks),
                real_project_protection_performed=False)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, help="New receipt JSON, required for real final verification")
    parser.add_argument("--asset-root", type=Path, help="Default to the last verified83-file local installation")
    parser.add_argument("--self-test", action="store_true", help="Temporary local fixtures only; do not hash project outputs")
    args = parser.parse_args(argv)
    if args.output is not None and args.output.exists():
        parser.error("Output already exists: " + str(args.output))
    if args.output is None and not args.self_test:
        parser.error("Real final verification requires --output NEW.json")
    value = self_test() if args.self_test else verify(args.root, asset_root=args.asset_root)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as destination:
            json.dump(value, destination, ensure_ascii=False, indent=2, allow_nan=False)
            destination.write("\n")
    compact = {key: value[key] for key in ("schema", "passed", "errors", "head", "branch",
               "historical_file_count", "prior_closed_teacher_file_count", "protected_runtime_unchanged",
               "check_count", "real_project_protection_performed") if key in value}
    print(json.dumps(compact, ensure_ascii=False, allow_nan=False))
    return 0 if value["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
