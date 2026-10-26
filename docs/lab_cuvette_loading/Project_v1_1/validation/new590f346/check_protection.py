"""Read-only Git, local asset-byte and declared threshold protection checks."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import yaml

ROOT = Path(__file__).resolve().parents[5]
HERE = Path(__file__).resolve().parent
BASELINE = 'f94f9451ea10022b2e747dae92e419b636f1f695'
PREVIOUS_NEW_VERSION = '21a0c7e44f2c7e1742a802b1acf27a5082586436'
EXPECTED = '590f346251b9a8145e7c0d82e825857cc961f8fe'


def git(*args):
    return subprocess.check_output(['git', '-c', 'core.quotePath=false', *args], cwd=ROOT)


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    output = HERE / 'protection_runtime_root_v2.json'
    if output.exists():
        raise FileExistsError(output)
    scopes = dict(old_configs=['config/lab_cuvette_loading/Project_v1/', 'config/lab_cuvette_loading/Size_v1/',
            'config/lab_cuvette_loading/Env_v1/'],
        old_implementation=['demos/lab_cuvette_project_v1/', 'demos/lab_cuvette_size_v1/', 'demos/lab_cuvette_env_v1/',
            'tasks/lab_cuvette_loading_project_v1.py', 'tasks/lab_cuvette_loading_env_v1.py',
            'tasks/lab_cuvette_loading_env_v1_scorer.py', 'controllers/lab_cuvette_env_v1_controller.py',
            'data_collectors/lab_cuvette_env_v1_collector.py', 'policy/dataset/lab_cuvette_project_v1_dataset.py',
            'policy/dataset/lab_cuvette_size_v1_dataset.py', 'policy/dataset/lab_cuvette_env_v1_dataset.py'],
        tracked_assets=['assets/'],
        old_release_evidence=['docs/lab_cuvette_loading/Project_v1/', 'docs/lab_cuvette_loading/Size_v1/',
            'docs/lab_cuvette_loading/Env_v1/'])
    head = git('rev-parse', 'HEAD').decode().strip()
    assert head == EXPECTED, head
    checks = {}
    for name, paths in scopes.items():
        checks[name] = dict(paths=paths,
            baseline_tracked_file_count=len(git('ls-tree', '-r', '--name-only', BASELINE, '--', *paths).splitlines()),
            changed_paths=git('diff', '--name-only', BASELINE, '--', *paths).decode().splitlines(),
            untracked_paths=git('ls-files', '--others', '--exclude-standard', '--', *paths).decode().splitlines())
    assets = []
    for path in git('ls-tree', '-r', '--name-only', BASELINE, '--', 'assets/').decode().splitlines():
        blob = git('show', BASELINE + ':' + path)
        lfs = blob.startswith(b'version https://git-lfs.github.com/spec/v1\n')
        expected = next(line.split(':', 1)[1] for line in blob.decode().splitlines() if line.startswith('oid sha256:')) if lfs else hashlib.sha256(blob).hexdigest()
        local = ROOT / path
        actual = sha(local) if local.is_file() else None
        assets.append(dict(path=path, identity_basis='baseline LFS object SHA256' if lfs else 'baseline Git blob SHA256',
            expected_SHA256=expected, actual_local_SHA256=actual, matches=expected == actual))
    configuration = 'config/lab_cuvette_loading/Project_v1_1/standard.yaml'
    old = yaml.safe_load(git('show', PREVIOUS_NEW_VERSION + ':' + configuration))
    current = yaml.safe_load((ROOT / configuration).read_text())
    groups = ('acceptance', 'demo_release', 'physics', 'robot', 'vessel', 'gripper', 'executor')
    threshold_checks = {group: dict(unchanged=old[group] == current[group],
        before=old[group], current=current[group]) for group in groups}
    scorers = ['demos/lab_cuvette_project_v1_1/scorer.py', 'tasks/lab_cuvette_loading_env_v1_scorer.py',
        'demos/lab_cuvette_size_v1/scorer.py']
    scorer_checks = {path: dict(unchanged=git('show', PREVIOUS_NEW_VERSION + ':' + path) == (ROOT / path).read_bytes(),
        current_SHA256=sha(ROOT / path)) for path in scorers}
    from demos.lab_cuvette_project_v1.assets import check_assets
    from demos.lab_cuvette_project_v1.runtime import asset_root_from_config
    # Source history intentionally retains original author-provenance bytes;
    # the portable release contains sanitized copies with separate hashes.
    # Use the actual closed-run config, not the repository source tree, for
    # runtime-release verification. Retain both checks to expose that boundary.
    runtime_config = ROOT / 'outputs/lab_cuvette_loading/Project_v1_1/teacher_camera_v2_02/launch_config.yaml'
    actual_asset_root = asset_root_from_config(yaml.safe_load(runtime_config.read_text()))
    runtime_assets = check_assets(actual_asset_root)
    source_tree_as_release_check = check_assets(ROOT)
    result = dict(schema='labsim.Project_v1_1.new590f346.protection.v1', checked_utc=datetime.now(timezone.utc).isoformat(),
        HEAD=head, old_release_baseline=BASELINE, previous_new_version_baseline=PREVIOUS_NEW_VERSION,
        scopes=checks, historical_git_scopes_unchanged=all(not row['changed_paths'] and not row['untracked_paths'] for row in checks.values()),
        local_tracked_asset_count=len(assets), local_tracked_assets_verified=sum(row['matches'] for row in assets),
        local_tracked_asset_checks=assets, runtime_release_asset_check=runtime_assets,
        runtime_root_basis=dict(source=str(runtime_config.relative_to(ROOT)), SHA256=sha(runtime_config),
            method='asset_root_from_config of actual closed-run launch configuration'),
        source_tree_checked_as_release=source_tree_as_release_check,
        source_tree_release_mismatch_explanation='Historical source assets retain original bytes; portable release sanitizes nonoperative provenance paths and has separate hashes. A source root is not an installed portable release root.',
        unchanged_threshold_and_physical_groups=threshold_checks, unchanged_scorer_checks=scorer_checks,
        all_declared_protection_checks_passed=all(not row['changed_paths'] and not row['untracked_paths'] for row in checks.values())
            and all(row['matches'] for row in assets) and runtime_assets['all_files_verified']
            and all(row['unchanged'] for row in threshold_checks.values()) and all(row['unchanged'] for row in scorer_checks.values()),
        ignored_historical_outputs_globally_rehashed=False, ignored_asset_caches_globally_rehashed=False,
        historical_output_scope='Existing localized closure/archive SHA evidence remains authoritative. No whole-history before/after snapshot is asserted.',
        runtime_or_assets_or_config_modified=False, GPU_used=False, provider_API_calls=0)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(dict(historical_git_scopes_unchanged=result['historical_git_scopes_unchanged'],
        local_asset_count=len(assets), local_asset_verified=result['local_tracked_assets_verified'],
        runtime_assets=runtime_assets, threshold_groups={k: v['unchanged'] for k, v in threshold_checks.items()},
        all_declared_protection_checks_passed=result['all_declared_protection_checks_passed'])))


if __name__ == '__main__':
    import sys
    sys.path.insert(0, str(ROOT))
    main()
