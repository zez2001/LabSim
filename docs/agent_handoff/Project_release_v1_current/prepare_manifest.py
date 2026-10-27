#!/usr/bin/env python3
"""Refresh release-only package selection; never build/archive or read live streams/H5."""
from __future__ import annotations
import csv
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
RELEASE = ROOT / 'docs/lab_cuvette_loading/Project_release_v1'
RUNS = ROOT / 'outputs/lab_cuvette_loading/Project_release_v1'

def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()

def closed_run(run):
    proof = run / 'process_exit.json'
    if not proof.is_file():
        return False
    data = json.loads(proof.read_text())
    pid = data.get('pid', data.get('process_id'))
    if pid is None:
        return False
    try:
        os.kill(int(pid), 0)
    except ProcessLookupError:
        return True
    return False

def main():
    selected = set()
    def add(path):
        path = Path(path)
        if not path.is_absolute():
            path = ROOT / path
        if not path.is_file() or path.is_symlink():
            raise ValueError(f'Missing or symlink package selection: {path}')
        if path.suffix.lower() in {'.h5', '.hdf5', '.zip', '.pt', '.pth', '.safetensors'}:
            raise ValueError(f'Forbidden bulk artifact: {path}')
        selected.add(path.relative_to(ROOT).as_posix())

    # Explicit subtree is this release only; exclude incomplete CPU attempts and
    # relative-link H5 indices. Keep small valid raw/derived evidence, not logs of
    # unclosed native runs. No broad outputs traversal.
    for path in RELEASE.rglob('*'):
        if not path.is_file() or path.is_symlink():
            continue
        if any('incomplete_CPU_attempt' in part for part in path.parts):
            continue
        if path.suffix.lower() in {'.h5', '.hdf5'}:
            continue
        if path.stat().st_size > 5_000_000:
            continue
        if path.suffix.lower() in {'.md', '.json', '.csv', '.xml', '.py', '.log', '.png', '.jpg'}:
            if path.suffix.lower() == '.json':
                json.loads(path.read_text(encoding='utf-8'))
            add(path)

    source_files = [
        'config/lab_cuvette_loading/Project_release_v1/standard.yaml',
        'config/lab_cuvette_loading/Project_v1/assets.lock.json',
        'assets/lab_cuvette_loading/Size_v1/registry.json',
        'data_collectors/lab_cuvette_project_release_collector.py',
        'tasks/lab_cuvette_loading_project_release.py',
        'factories/task_factory.py', 'factories/collector_factory.py',
        'policy/dataset/lab_cuvette_project_release_dataset.py',
        'policy/dataset/lab_cuvette_project_v1_1_dataset.py',
        'policy_backends/lab_cuvette_env_v1/pi05_rollout.py',
        'policy_backends/lab_cuvette_env_v1/policy_adapters.py',
        'policy_backends/lab_cuvette_env_v1/policy_runner.py',
        'scripts/labsim_cli.py', 'scripts/labsim_assets.py', 'scripts/package_agent_results.py',
        'utils/episode_selection.py', 'requirements.txt',
        'requirements/ci.txt', 'requirements/ci-readers.txt',
        '.github/workflows/cpu-contracts.yml', '.gitattributes', 'LICENSE',
    ]
    source_files += [p.relative_to(ROOT).as_posix() for p in (ROOT / 'demos/lab_cuvette_project_release_v1').glob('*.py')]
    source_files += [p.relative_to(ROOT).as_posix() for p in (ROOT / 'tests').glob('test_*release*.py')]
    source_files += ['tests/test_lab_cuvette_external_policy_rollout.py']
    for path in source_files:
        add(path)

    raw_run_names = ['baseline_diagnostic_01', 'gui_finish_02', 'same_process_collect_01',
                     'pi05_standard_01_env', 'termination_cases_01']
    closed_names, pending_names = [], []
    for name in raw_run_names:
        run = RUNS / name
        if not closed_run(run):
            pending_names.append(name)
            continue
        closed_names.append(name)
        # The process is proven gone. Copy metadata/results only; source media,
        # H5 and high-frequency logs are deliberately not opened by this tool.
        for path in run.rglob('*'):
            if path.is_file() and not path.is_symlink() and path.stat().st_size <= 256_000:
                if path.suffix.lower() in {'.json', '.yaml'} or path.name == 'episode.jsonl':
                    if path.suffix.lower() == '.json':
                        json.loads(path.read_text(encoding='utf-8'))
                    add(path)

    external_rows = []
    for inventory in sorted(RELEASE.glob('validation/*/source_inventory.csv')):
        if 'incomplete_CPU_attempt' in str(inventory):
            continue
        with inventory.open(newline='') as stream:
            for row in csv.DictReader(stream):
                if row.get('category') not in {'h5', 'video', 'physics', 'contact', 'execution_trace'}:
                    continue
                audit = inventory.parent.name
                run_name = audit.removesuffix('_closed').removesuffix('_data')
                source = RUNS / run_name / row['path']
                external_rows.append(dict(
                    audit_inventory=inventory.relative_to(ROOT).as_posix(),
                    local_source_path=str(source), category=row['category'],
                    bytes=int(row['bytes']), sha256=row['sha256'],
                    included_in_technical_package_at_preparation=False,
                    final_selection_authority='final generated 文件清单.json; media may be selected later',
                    availability='owner-local source; request complete run directory or reproduce; no public trajectory download claimed'))
    dump(HERE / 'external_data_sources.json', dict(
        schema='labsim.Project_release_v1.external_data_sources.v1',
        source='already-closed CPU audit inventory; no H5/stream/video opened by this preparation',
        physical_indices_included=False,
        HF_assets_revision='bb880f098180c291f6f65995f969d48047207067',
        HF_assets_are_not_raw_trajectory_distribution=True,
        selection_status='draft before final media selection; final generated 文件清单.json is authoritative',
        files=external_rows))
    add(HERE / 'external_data_sources.json')

    pending = dict(
        schema='labsim.Project_release_v1.package_readiness.v1',
        status='draft_not_final_delivery',
        inspected_checkout=subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip(),
        runtime_source_sha='122c4c03586abdfa7e3117c13e62f8d46f786b04',
        closed_runs_with_metadata_selected=closed_names,
        running_or_not_started_runs_not_selected=pending_names,
        final_publication_gates=[
            'Same-process three-episode proof, closed H5/result/index agreement and reset audit',
            'Real pi0.5 RPC rollout closed proof, model/action receipts, labels and normal reader',
            'Termination diagnostics with actual/injected evidence separated',
            'Like-for-like optimized teacher measurement and caveats',
            'Final report/README/CI/remote SHA and clean-checkout validation',
            'Final media source/hash/full-decode/relocated DOCX QA; add selected actual native videos explicitly',
            'Validate final package after commit; refresh this manifest only after all files stop changing'],
        pending_media=[],
        pending_media_policy='No nonexistent or active media path selected; root adds actual closed native teacher and policy videos at final freeze',
        exclusions=['all H5/HDF5, including small external-link indices',
                    'Isaac environment, model checkpoints, source attachments with credentials, tokens',
                    'historical reports and old media except provenance needed to identify preview'],
        package_built=False,
    )
    dump(HERE / 'package_readiness.json', pending)
    add(HERE / 'package_readiness.json')
    add(Path(__file__))
    # Include this record as a source selection: the package script separately
    # emits the actual commit, file manifest and checksums, with no self-hash.
    manifest = dict(schema='labsim.agent_results_package.v1',
        repository_url='https://github.com/zez2001/LabSim',
        readme='docs/agent_handoff/Project_release_v1_current/00_给Agent阅读说明.md',
        directories=[], files=[dict(source=p, destination=p) for p in sorted(selected)],
        status='draft_waiting_closed_native_evidence_and_final_commit',
        preferred_bytes=60_000_000, hard_limit_bytes=120_000_000,
        pending_evidence='docs/agent_handoff/Project_release_v1_current/package_readiness.json')
    dump(HERE / 'package.json', manifest)
    print(json.dumps(dict(selected_files=len(selected), selected_bytes=sum((ROOT / p).stat().st_size for p in selected),
                          closed_runs=closed_names, pending_runs=pending_names, built=False), ensure_ascii=False))

if __name__ == '__main__':
    main()
