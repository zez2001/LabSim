"""Read-only historical purpose acceptance; every output goes to a new directory."""
import argparse
import json
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repo, output = args.repo.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    sys.path.insert(0, str(repo))
    import h5py
    import torch
    torch.set_num_threads(1)
    from demos.lab_cuvette_project_release_v1.membership import file_sha256, import_curated_policy, write_members
    from demos.lab_cuvette_project_release_v1.dataset_index import build_index
    from demos.lab_cuvette_project_release_v1.transfer import check_dependencies
    from scripts.labsim_cli import main as cli_main

    def save(name, payload):
        (output / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")

    run = repo / "outputs/lab_cuvette_loading/Project_release_v1/pi05_standard_01_env"
    history = repo / "docs/lab_cuvette_loading/Project_release_v1/validation/pi05_standard_01_env_closed"
    curated = history / "curated_index_manifest.json"
    paths = sorted(run.glob("episode_*/dataset/episode_*.h5"))
    assert len(paths) == 11
    original_inventory = json.loads((history / "source_SHA256_before_after.json").read_text())["after"]

    def snapshot(source_paths):
        result = {}
        for path in source_paths:
            with h5py.File(path) as episode:
                labels = {key: str(episode.attrs.get(key, "ABSENT")) for key in (
                    "episode_id", "record_purpose", "record_valid", "task_success", "failure_type",
                    "termination_reason", "complete", "publication_state", "finalization_id",
                    "eligible_for_success_bc", "eligible_for_failure_analysis")}
            result[str(path.relative_to(repo))] = dict(sha256=file_sha256(path), labels=labels)
        return result

    before = snapshot(paths)
    for path in paths:
        assert before[str(path.relative_to(repo))]["sha256"] == original_inventory[str(path.relative_to(run))]
    curated_before = file_sha256(curated)
    members = output / "pi05_purpose_members.json"
    annotated = import_curated_policy(run, curated, members)
    assert len(annotated["members"]) == 11
    policy = build_index(run, output / "policy_only.hdf5", purpose="policy_evaluation", members=members)
    all_completed = build_index(run, output / "diagnostic_all_completed.hdf5", purpose="all-completed", members=members)
    probes = build_index(run, output / "resource_probes.hdf5", purpose="resource_probe", members=members)
    assert policy["counts"] == dict(success=0, failure=1, all_valid=1, incomplete=0)
    assert all_completed["counts"] == dict(success=0, failure=11, all_valid=11, incomplete=0)
    assert probes["counts"]["all_valid"] == 10
    for index, sample_filter, name in (
        (output / "policy_only.hdf5", "failure", "policy_failure_reader.json"),
        (output / "policy_only.hdf5", "all_valid", "policy_all_valid_reader.json"),
        (output / "diagnostic_all_completed.hdf5", "all_valid", "diagnostic_all_valid_reader.json")):
        assert cli_main(["dataset-check", "--index", str(index), "--sample-filter", sample_filter,
                         "--output", str(output / name)]) == 0
    transfer = check_dependencies(output / "policy_only.hdf5", verify_sha256=True)
    assert transfer["ok"]
    save("policy_transfer_check.json", transfer)
    after = snapshot(paths)
    assert before == after and curated_before == file_sha256(curated)
    save("historical_pi05_protection.json", dict(before=before, after=after,
        source_h5_bytes_unchanged=True, task_labels_unchanged=True,
        previous_audit_sha256_agrees=True, original_curated_manifest_unchanged=True,
        original_curated_manifest_sha256=curated_before))

    # Keep the former 2/1/3 qualification result under an explicit diagnostic use.
    lifecycle = repo / "outputs/lab_cuvette_loading/Project_release_v1/same_process_collect_01"
    lifecycle_paths = sorted(lifecycle.glob("episode_*/dataset/episode_*.h5"))
    lifecycle_before = snapshot(lifecycle_paths)
    assignments = {row["labels"]["episode_id"]: "lifecycle_diagnostic" for row in lifecycle_before.values()}
    lifecycle_members = output / "lifecycle_purpose_members.json"
    write_members(lifecycle, lifecycle_members, assignments,
        provenance=dict(method="explicit_run_intent", source_run="same_process_collect_01",
                        declared_sequence=["teacher", "early_finish", "teacher"]))
    lifecycle_index = output / "lifecycle_diagnostic.hdf5"
    lifecycle_report = build_index(lifecycle, lifecycle_index, purpose="lifecycle_diagnostic", members=lifecycle_members)
    assert lifecycle_report["counts"] == dict(success=2, failure=1, all_valid=3, incomplete=0)
    for sample_filter in ("success", "failure", "all_valid"):
        assert cli_main(["dataset-check", "--index", str(lifecycle_index), "--sample-filter", sample_filter,
                         "--output", str(output / ("lifecycle_" + sample_filter + "_reader.json"))]) == 0
    lifecycle_after = snapshot(lifecycle_paths)
    assert lifecycle_before == lifecycle_after
    save("historical_lifecycle_protection.json", dict(before=lifecycle_before, after=lifecycle_after,
        source_h5_bytes_unchanged=True, task_labels_unchanged=True))
    save("summary.json", dict(schema="labsim.Internal_use_v1.data_usage_acceptance.v1",
        actual_simulations_started=0, mode="closed_historical_H5_read_only",
        policy_qualification_counts=policy["counts"], diagnostic_all_completed_counts=all_completed["counts"],
        resource_probe_counts=probes["counts"], lifecycle_diagnostic_counts=lifecycle_report["counts"],
        historical_h5_count=len(paths) + len(lifecycle_paths), all_h5_sha256_and_task_labels_unchanged=True,
        source_hashes_match_previous_audit=True, normal_readers=["ACT", "DP"],
        policy_reader_success=True, diagnostic_reader_success=True, lifecycle_reader_success=True,
        qualification_semantics_changed=False, purpose_inferred_from_task_outcome_or_duration=False,
        source_files_are_external_dependencies=True,
        code_files={str(path.relative_to(repo)): file_sha256(path) for path in (
            repo / "demos/lab_cuvette_project_release_v1/dataset_index.py",
            repo / "demos/lab_cuvette_project_release_v1/membership.py",
            repo / "demos/lab_cuvette_project_release_v1/transfer.py")}))


if __name__ == "__main__":
    main()
