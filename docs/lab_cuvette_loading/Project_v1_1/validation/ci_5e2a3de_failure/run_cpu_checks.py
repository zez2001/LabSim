"""Run the frozen CI selections using existing CPU-capable environments only."""
import argparse
from datetime import datetime, timezone
import glob
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[5]
HERE = Path(__file__).resolve().parent
LIGHT = Path('/tmp/labsim-handoff-ci-py311-20261022/bin/python')
NORMAL = Path('/home/wujing/Desktop/vla/labutopia-env/bin/python')
PYTEST_SITE = '/tmp/labsim-handoff-ci-py311-20261022/lib/python3.11/site-packages'


def source_hashes():
    names = set()
    for pattern in ('demos/lab_cuvette_project_v1_1/*.py', 'policy/backends/cubence_project_v1_1*.py',
            'tasks/lab_cuvette_loading_project_v1_1.py', 'controllers/lab_cuvette_project_v1_1_controller.py',
            'data_collectors/lab_cuvette_project_v1_1_collector.py', 'policy/dataset/lab_cuvette_project_v1_1_dataset.py',
            'tests/test_lab_cuvette_project_v1_1_*.py', 'config/lab_cuvette_loading/Project_v1_1/**/*.yaml',
            '.github/workflows/cpu-contracts.yml', 'requirements/ci*.txt'):
        names.update(glob.glob(pattern, root_dir=ROOT, recursive=True))
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in sorted(names)}


def ci_tests(suite):
    text = (ROOT / '.github/workflows/cpu-contracts.yml').read_text()
    marker = 'Run CPU contracts without Isaac or training' if suite == 'contracts' else 'Read qualified H5 fixtures through normal ACT/DP datasets'
    part = text.split(marker, 1)[1].split('python -m pytest -q', 1)[1]
    result = []
    for line in part.splitlines():
        stripped = line.strip().rstrip('\\').strip()
        if stripped.startswith('tests/'):
            result.extend(sorted(glob.glob(stripped, root_dir=ROOT)))
        elif result and stripped:
            break
    assert result
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('suite', choices=('contracts', 'normal-readers'))
    args = parser.parse_args()
    suite = args.suite
    for suffix in ('_result.json', '_junit.xml', '.log'):
        if (HERE / (suite + suffix)).exists():
            raise FileExistsError('Refusing to overwrite ' + suite + suffix)
    env = dict(os.environ, CUDA_VISIBLE_DEVICES='', PYTEST_DISABLE_PLUGIN_AUTOLOAD='1')
    tests = ci_tests(suite)
    junit = HERE / (suite + '_junit.xml')
    command = [str(LIGHT)] if suite == 'contracts' else [str(NORMAL), '-c',
        "import sys;sys.path.append('" + PYTEST_SITE + "');import pytest;raise SystemExit(pytest.main(sys.argv[1:]))"]
    if suite == 'contracts':
        command += ['-m', 'pytest']
    command += ['-q', *tests, '--junitxml=' + str(junit)]
    before = source_hashes()
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    started = datetime.now(timezone.utc).isoformat()
    tick = time.perf_counter()
    process = subprocess.run(command, cwd=ROOT, env=env, text=True, capture_output=True)
    wall = time.perf_counter() - tick
    (HERE / (suite + '.log')).write_text(process.stdout + process.stderr)
    after = source_hashes()
    changed = sorted(k for k in before.keys() | after.keys() if before.get(k) != after.get(k))
    cases = []
    if junit.is_file():
        for node in ET.parse(junit).iter('testcase'):
            status = 'failed' if node.find('failure') is not None or node.find('error') is not None else 'skipped' if node.find('skipped') is not None else 'passed'
            cases.append(dict(id=node.get('classname', '') + '::' + node.get('name', ''), status=status,
                skip_reason=None if node.find('skipped') is None else node.find('skipped').get('message')))
    result = dict(schema='labsim.Project_v1_1.cpu_regression.v2', suite=suite, HEAD=head,
        started_at_utc=started, finished_at_utc=datetime.now(timezone.utc).isoformat(), wall_seconds=wall,
        argv=command, test_files=tests, exit_code=process.returncode,
        counts={k: sum(c['status'] == k for c in cases) for k in ('passed', 'skipped', 'failed')},
        test_cases=cases, CUDA_VISIBLE_DEVICES='', plugin_autoload_disabled=True,
        source_SHA256_before=before, source_SHA256_after=after, source_files_changed_during_run=changed,
        Isaac_started=False, GPU_started=False, API_called=False, dependency_installation_performed=False,
        scope='Actual CPU software/normal-reader fixture tests. No simulator, hardware precision or new physical verification.')
    (HERE / (suite + '_result.json')).write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps(dict(suite=suite, exit_code=process.returncode, counts=result['counts'],
        source_files_changed_during_run=changed, wall_seconds=wall)))
    return process.returncode or bool(changed)


if __name__ == '__main__':
    sys.exit(main())
