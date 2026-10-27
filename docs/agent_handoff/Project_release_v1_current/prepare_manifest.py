#!/usr/bin/env python3
"""Select this release's closed evidence; never build/archive, launch Isaac, or read H5."""
from __future__ import annotations
import argparse
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
NATIVE_RUNS = ('baseline_diagnostic_01', 'gui_finish_02', 'same_process_collect_01',
               'pi05_standard_01_env', 'termination_cases_01')
BULK = {'.h5', '.hdf5', '.zip', '.pt', '.pth', '.safetensors'}

def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()

def cpu_attempt(path):
    return any('CPU' in part and 'attempt' in part for part in path.parts)

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
        return data.get('process_exited', True) is True
    return False

def category(path):
    if path.suffix in {'.h5', '.hdf5'}:
        return 'h5'
    if path.suffix == '.mp4':
        return 'video'
    if path.name.startswith('physics_records.jsonl'):
        return 'physics'
    if path.name.startswith('native_contact_events.jsonl'):
        return 'contact'
    if path.name == 'execution_trace.jsonl':
        return 'execution_trace'
    return None

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--finalize', action='store_true', help='Require all native runs and final meeting media to be closed and present')
    args = parser.parse_args()
    selected = {}
    def add(path, destination=None):
        path = Path(path)
        if not path.is_absolute():
            path = ROOT / path
        if not path.is_file() or path.is_symlink():
            raise ValueError(f'Missing or symlink package selection: {path}')
        if path.suffix.lower() in BULK:
            raise ValueError(f'Forbidden bulk artifact: {path}')
        source = path.relative_to(ROOT).as_posix()
        destination = source if destination is None else str(destination)
        if source in selected and selected[source] != destination:
            raise ValueError(f'Source has conflicting destinations: {source}')
        selected[source] = destination

    # Only this release's evidence. Failed CPU audit attempts remain available
    # in Git history but are not competing primary evidence in this handoff.
    for path in RELEASE.rglob('*'):
        if not path.is_file() or path.is_symlink() or cpu_attempt(path):
            continue
        if path.parent.name == 'meeting_source' and (
                '.pending.' in path.name or 'pending_link_check' in path.name or
                path.name in {'meeting_preview_qa.json', 'gpt08_terminal.png', 'teacher_scene.png', 'teacher_retreat.png'}):
            continue
        if path.suffix.lower() in BULK or path.stat().st_size > 5_000_000:
            continue
        if path.suffix.lower() in {'.md', '.json', '.csv', '.xml', '.py', '.log', '.png', '.jpg'}:
            if path.suffix.lower() == '.json':
                json.loads(path.read_text(encoding='utf-8'))
            add(path)

    source_files = [
        'README.md', 'README_CN.md', 'README_EN.md',
        'docs/agent_handoff/README.md', 'docs/agent_handoff/00_给Agent阅读说明.md',
        'config/lab_cuvette_loading/Project_release_v1/standard.yaml',
        'config/lab_cuvette_loading/Project_v1/assets.lock.json',
        'config/lab_cuvette_loading/Project_v1/policies/pi05_libero.yaml',
        'assets/lab_cuvette_loading/Size_v1/registry.json',
        'data_collectors/lab_cuvette_project_release_collector.py',
        'tasks/lab_cuvette_loading_project_release.py',
        'factories/task_factory.py', 'factories/collector_factory.py',
        'policy/dataset/lab_cuvette_project_release_dataset.py',
        'policy/dataset/lab_cuvette_project_v1_1_dataset.py',
        'policy_backends/lab_cuvette_env_v1/pi05_rollout.py',
        'policy_backends/lab_cuvette_env_v1/pi05_server.py',
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
    # Like raw run receipts, this ignored source is finalized after the code
    # push. It avoids inventing a future commit or a self-referential CI proof.
    publication = RUNS / 'publication_evidence/final_publication.json'
    if publication.is_file():
        add(publication, '发布信息.json')

    closed_names, pending_names = [], []
    for name in NATIVE_RUNS:
        run = RUNS / name
        if not closed_run(run):
            pending_names.append(name)
            continue
        closed_names.append(name)
        # Process-gone gate: select raw small publication/scoring/reset metadata.
        # Do not open H5, videos, high-frequency physics/contact streams.
        for path in run.rglob('*'):
            if path.is_file() and not path.is_symlink() and path.stat().st_size <= 256_000:
                if path.suffix.lower() in {'.json', '.yaml'} or path.name == 'episode.jsonl':
                    if path.suffix.lower() == '.json':
                        json.loads(path.read_text(encoding='utf-8'))
                    add(path)
    if args.finalize and pending_names:
        raise RuntimeError(f'Native processes not closed: {pending_names}')

    # One actual model episode; ten subsequent 0.05-s reset probes are not ten
    # policy failures. Preserve the client events and real model endpoints.
    if 'pi05_standard_01_env' in closed_names:
        for name in ('pi05_standard_01_policy', 'pi05_standard_01_model'):
            run = RUNS / name
            if not closed_run(run):
                raise RuntimeError(f'Model/client not closed: {name}')
            for path in run.iterdir():
                if path.is_file() and path.suffix in {'.json', '.jsonl'}:
                    add(path)
        audit = RELEASE / 'external_policy/pi05_standard_01_closed_audit'
        for name in ('input_000001.npz', 'input_000069.npz', 'output_000001.npy', 'output_000069.npy'):
            add(audit / name)
        for name in ('resource_probe.json', 'shutdown_requested.json'):
            add(RUNS / 'reset_resource_probe_01' / name)

    media = []
    media_sources = [
        (RELEASE / 'report/LabSim_环境与评测进展_20261028.docx', '组会材料/LabSim_环境与评测进展_20261028.docx'),
        (RELEASE / 'media/teacher_full.mp4', '组会材料/teacher_full.mp4'),
        (RELEASE / 'media/pi05_collision.mp4', '组会材料/pi05_collision.mp4'),
    ]
    if args.finalize:
        qa = json.loads((RELEASE / 'meeting_source/meeting_final_media_QA.json').read_text())
        if qa.get('pages') != 4 or not qa.get('latest_all_pages_visually_inspected_at_original_resolution'):
            raise RuntimeError('Final meeting DOCX visual QA missing')
        qa_media = {entry['file']: entry for entry in qa['media']}
        for path, destination in media_sources:
            digest = sha(path)
            expected = qa['DOCX_SHA256'] if path.suffix == '.docx' else qa_media[path.name]['sha256']
            if digest != expected:
                raise RuntimeError(f'Media differs from completed QA: {path}')
            add(path, destination)
            media.append(dict(source=path.relative_to(ROOT).as_posix(), destination=destination,
                              bytes=path.stat().st_size, sha256=digest))

    # Declare raw data without copying it. Hashes come from completed before/
    # after audits; stat verifies the same source byte size without reading H5.
    external = {}
    def external_record(source, digest, bytes_count, evidence):
        if category(source) is None:
            return
        if not source.is_file() or source.stat().st_size != int(bytes_count):
            raise RuntimeError(f'Closed source missing or changed size: {source}')
        rel = source.relative_to(ROOT).as_posix()
        external[rel] = dict(local_source_path=str(source), repository_relative_source=rel,
            category=category(source), bytes=int(bytes_count), sha256=digest,
            hash_source=evidence, source_bytes_verified_at_preparation=True,
            hash_scope='completed closed audit; original data not rehashed by package preparation',
            included_as_original_path=(rel in selected),
            equivalent_package_copy=(
                '组会材料/teacher_full.mp4' if rel.endswith('same_process_collect_01/episode_0000/dual_view.mp4') and args.finalize else
                '组会材料/pi05_collision.mp4' if rel.endswith('pi05_standard_01_env/episode_0000/dual_view.mp4') and args.finalize else None),
            availability='owner-local source; request complete run directory or reproduce; no public raw-trajectory download claimed')

    for inventory in sorted(RELEASE.glob('validation/*/source_inventory.csv')):
        if cpu_attempt(inventory):
            continue
        audit = inventory.parent.name
        run_name = audit.removesuffix('_closed').removesuffix('_data')
        if run_name not in closed_names:
            continue
        with inventory.open(newline='') as stream:
            for row in csv.DictReader(stream):
                source = RUNS / run_name / row['path']
                external_record(source, row['sha256'], row['bytes'], inventory.relative_to(ROOT).as_posix())

    pi_hashes = RELEASE / 'validation/pi05_standard_01_env_closed/source_SHA256_before_after.json'
    if pi_hashes.is_file() and 'pi05_standard_01_env' in closed_names:
        data = json.loads(pi_hashes.read_text())
        for relative, digest in data['before'].items():
            source = RUNS / 'pi05_standard_01_env' / relative
            if category(source) is None:
                continue
            if data['after'].get(relative) != digest:
                raise RuntimeError(f'Closed audit hash changed: {relative}')
            external_record(source, digest, source.stat().st_size, pi_hashes.relative_to(ROOT).as_posix())

    termination_manifest = RELEASE / 'validation/termination_cases_01_closed/source_manifest.json'
    if termination_manifest.is_file() and 'termination_cases_01' in closed_names:
        for row in json.loads(termination_manifest.read_text()):
            source = Path(row['path'])
            if not source.is_relative_to(RUNS) or category(source) is None:
                continue
            if row['sha256_before'] != row['sha256_after']:
                raise RuntimeError(f'Termination source changed: {source}')
            external_record(source, row['sha256_after'], row['bytes'], termination_manifest.relative_to(ROOT).as_posix())

    dump(HERE / 'external_data_sources.json', dict(
        schema='labsim.Project_release_v1.external_data_sources.v1',
        raw_data_included=False, physical_H5_indices_included=False,
        source='closed CPU audit inventories + closed source stat; no H5 or high-frequency stream decoded by package preparation',
        asset_download=dict(repository='Txie000/SLAI-Labsim', revision='bb880f098180c291f6f65995f969d48047207067',
            url='https://huggingface.co/datasets/Txie000/SLAI-Labsim/tree/bb880f098180c291f6f65995f969d48047207067',
            assets_lock='config/lab_cuvette_loading/Project_v1/assets.lock.json',
            actual_download_manifest='docs/lab_cuvette_loading/Project_release_v1/validation/fresh_assets/manifest.json',
            assets_are_not_this_round_raw_trajectories=True),
        model_checkpoint_source='docs/lab_cuvette_loading/Project_release_v1/external_policy/preflight_20261027.json',
        model_checkpoint_included=False, model_checkpoint_newly_downloaded=False,
        real_policy_episode='pi05_standard_01_env/episode_0000',
        reset_resource_probes='pi05_standard_01_env/episode_0001 through episode_0010: diagnostics only',
        files=[external[key] for key in sorted(external)]))
    add(HERE / 'external_data_sources.json')

    readiness = dict(
        schema='labsim.Project_release_v1.package_readiness.v1',
        status='closed_evidence_and_media_recipe_ready_for_final_commit' if args.finalize else 'preparation_only',
        source_commit_at_preparation=subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip(),
        runtime_source_sha='122c4c03586abdfa7e3117c13e62f8d46f786b04',
        termination_CLI_sha='73b1a9db9470f9706a3068a8ce24e7e09d8cfc65',
        qualified_reader_sha='4a716359376de0132cc83cba3e5c7d27c791069e',
        final_delivery_commit_authority='generated 文件清单.json source_commit at post-commit package build; not the older preparation snapshot',
        closed_runs_with_metadata_selected=closed_names, unclosed_native_runs=pending_names,
        actual_evidence=dict(same_process_results=[True, False, True],
            formal_clean_reader_counts=dict(success=2, failure=1, all_valid=3),
            actual_pi05_model_episodes=1, reset_resource_probe_episodes=10,
            actual_pi05_inferences=69, actual_pi05_actions=341, actual_pi05_control_ticks=1021,
            actual_pi05_action_sim_seconds=1021/60, actual_pi05_result='SAFETY_COLLISION',
            pi05_formal_clean_reader_counts=dict(failure=1, all_valid=1),
            termination_checks=145, authoritative_qualification_checks=35,
            termination_service_timeout_and_interrupt='controlled injection, task_success=null, record_valid=false'),
        remaining_product_limitations=['SDK ManipulatorFactory shutdown NameError persists after valid data closure',
            'RSS growth attribution and long-lived process memory plateau not resolved',
            'Second-machine installation and real-world calibration not verified'],
        preparation_snapshot_scope='This records the pre-package recipe; final source commit and copied-file authority are generated 文件清单.json',
        post_freeze_procedure=['Final commit/push and actual remote/CI check by root',
            'Build final technical ZIP only after final commit; verify moved package links/checksums',
            'Build separate meeting ZIP with exactly one DOCX and two native videos'],
        selected_meeting_material=media,
        exclusions=['all H5/HDF5 including small external-link indices',
                    'CPU attempt audit copies as primary evidence',
                    'Isaac environment, weights, credentials and credential-bearing task attachments'],
        package_built=False,
    )
    dump(HERE / 'package_readiness.json', readiness)
    add(HERE / 'package_readiness.json')
    add(Path(__file__))
    if (HERE / 'review_manifest.py').is_file():
        add(HERE / 'review_manifest.py')
    if (HERE / 'static_review.json').is_file():
        add(HERE / 'static_review.json')
    add(HERE / 'package.json')
    manifest = dict(schema='labsim.agent_results_package.v1',
        repository_url='https://github.com/zez2001/LabSim',
        readme='docs/agent_handoff/Project_release_v1_current/00_给Agent阅读说明.md',
        directories=[], files=[dict(source=p, destination=selected[p]) for p in sorted(selected)],
        status='closed_native_results_selected_waiting_final_commit_and_archive' if args.finalize else 'preparation_only',
        preferred_bytes=60_000_000, hard_limit_bytes=120_000_000,
        readiness='docs/agent_handoff/Project_release_v1_current/package_readiness.json')
    dump(HERE / 'package.json', manifest)
    print(json.dumps(dict(selected_files=len(selected), selected_bytes=sum((ROOT / p).stat().st_size for p in selected),
        closed_runs=closed_names, unclosed_runs=pending_names, final_selection=args.finalize, built=False), ensure_ascii=False))

if __name__ == '__main__':
    main()
