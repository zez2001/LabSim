"""Read-only final protection of the restored debug04 experiment.

Only a new JSON receipt is written. Source evidence, H5 files, assets and both
ledgers are read without modification; no model, Isaac or credential is loaded.
Use --allow-dirty only for a clearly labelled pre-publication assessment.
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


SCHEMA = 'labsim.Gpt_debug04_v1.final_protection.v1'
ORIGINAL_ROOT = Path('/home/wujing/Desktop/vla/LabSim')
BASELINE = '9bdf8c7c36b0c324cb9009bfe9aa0538dd6ff485'
RUNTIME = '801a3f704298faf00cc31b55d572e5e0ff4bb4b6'
OUTPUT_BASE = 'outputs/lab_cuvette_loading/Gpt_debug04_v1/20261103'
PROTOCOL = 'config/lab_cuvette_loading/Gpt_debug04_v1/protocol_template.json'
PROTOCOL_SHA = 'eef523608b143cee927203a15291c99d534be0dc23cec678694b340b433c3be7'
AUTHORIZATION = OUTPUT_BASE + '/authorization_02.json'
AUTHORIZATION_SHA = '2cc78f5725b232247e865ceb0a33972ef716ad4c59da2e8f8f7f43cc2f6441f1'
OLD_LEDGER = 'outputs/lab_cuvette_loading/Project_v1/cubence_budget.json'
NEW_EPISODE = '32bd28cb-aee3-4bea-9c10-5408fc1d1b55'
PREVIOUS = 'outputs/lab_cuvette_loading/Policy_eval_v1/20261103'
REFERENCES = {
    PREVIOUS + '/publication/protection_final.json':
        '53843788063677ed4a957090f4129b58c58d7ca3126bf58c202470d268a8f4a1',
    'docs/lab_cuvette_loading/Gpt_debug04_v1/results/historical/source_closed_audit.json':
        'b06d76bedeef5957ccb0f3c99c03573e6f1684aae92938259bf491a2c7da0dab',
    PREVIOUS + '/validation/formal_gpt6_01_closed.json':
        '5de97fcc68e581bf98929dc7ea3a55849b1a70db9fa8f306adc96ba6155f238e',
    PREVIOUS + '/metrics_final_01/validation/formal_pi05_01_closed.json':
        '9e71630838aecbc8577c073b03c5b35325c2c19cc5c476b8d77a977a7c072a8d',
    PREVIOUS + '/metrics_final_01/validation/formal_gpt6_02_closed.json':
        'a34d8da84f2f51caa24cc4d7ee6cbca27e61c4dfb75dba884e09796a23eb2511',
    PREVIOUS + '/metrics_final_01/validation/formal_pi05_02_closed.json':
        '3cdbee7446a45a210b792678fc3e50927596f185a04c4f1fdcd653babb425ea9',
}
ALLOWED_PREFIXES = (
    'config/lab_cuvette_loading/Gpt_debug04_v1/',
    'demos/lab_cuvette_gpt_debug04_v1/',
    'policy/backends/gpt_debug04_v1/',
    'docs/lab_cuvette_loading/Gpt_debug04_v1/',
    'docs/agent_handoff/Gpt_debug04_v1_current/',
    'tests/test_gpt_debug04_',
)
LAUNCH = 'demos/lab_cuvette_project_release_v1/launch.py'
ALLOWED_FILES = {
    'README.md', 'README_CN.md', 'README_EN.md', '.gitattributes',
    '.github/workflows/cpu-contracts.yml', LAUNCH,
    'docs/agent_handoff/README.md', 'docs/agent_handoff/package.json',
}
PROTECTED_PATHS = (
    'assets', 'collectors', 'data_collectors', 'controllers', 'tasks',
    'SLAI_Lab', 'local_assets', 'policy', 'policy_backends', 'factories',
    'utils', 'config/lab_cuvette_loading', 'demos',
)


def sha(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 << 20), b''):
            value.update(block)
    return value.hexdigest()


def load(path):
    return json.loads(Path(path).read_text())


def git(root, *args, binary=False):
    return subprocess.check_output(['git', '-c', 'core.quotepath=false', *args],
                                   cwd=root, text=not binary)


def names(root, command, *args):
    return [name for name in git(root, command, '-z', *args).split('\0') if name]


def relative(name):
    path = Path(name)
    if path.is_absolute():
        path = path.relative_to(ORIGINAL_ROOT)
    if not path.parts or '..' in path.parts or path.as_posix() == '.':
        raise ValueError('Invalid evidence path: ' + str(name))
    return path.as_posix()


def rooted(root, name):
    path = (root / relative(name)).resolve()
    if not path.is_relative_to(root):
        raise ValueError('Evidence escapes selected root: ' + str(name))
    return path


def records(values):
    if isinstance(values, dict):
        return [dict(path=name, expected_sha256=row['sha256']) for name, row in values.items()]
    return [dict(path=row['path'], expected_sha256=row.get('expected_sha256', row.get('sha256')))
            for row in values]


def verify_records(root, values, cache):
    answer = []
    for row in records(values):
        name = relative(row['path'])
        path = rooted(root, name)
        if name not in cache:
            cache[name] = sha(path) if path.is_file() else None
        answer.append(dict(path=name, expected_sha256=row['expected_sha256'],
                           actual_sha256=cache[name], unchanged=cache[name] == row['expected_sha256']))
    return answer


def funding_checks(old, current, authorization, *, ledger_path, original_sha):
    base = old['attempts']
    new = current['attempts'][len(base):]
    spent = sum(row['charged_estimate_usd'] for row in base)
    new_spent = sum(row['charged_estimate_usd'] for row in new)
    close = lambda a, b: abs(float(a) - float(b)) <= 1e-8
    checks = dict(
        explicit_grant=authorization.get('approved') is True,
        original_ledger_sha_exact=original_sha == authorization['original_ledger_sha256'],
        old377_prefix_exact=current['attempts'][:len(base)] == base and len(base) == 377,
        old_expense_exact=close(spent, 29.267746),
        old_caps_unchanged=old['max_requests'] == 1500 and close(old['max_estimated_usd'], 30),
        authorization_base_matches=authorization['base_attempt_count'] == len(base)
            and close(authorization['base_estimated_usd'], spent),
        authorized_delta_exact=authorization['additional_network_attempts'] == 480
            and close(authorization['additional_estimated_usd'], 20)
            and type(authorization['maximum_formal_episodes']) is int
            and authorization['maximum_formal_episodes'] == 1,
        unique_authorized_ledger=Path(authorization['authorized_ledger_path']).resolve() == ledger_path.resolve(),
        cumulative_caps_exact=current['max_requests'] == 857
            and close(current['max_estimated_usd'], 49.267746),
        only_formal_trial_claimed=set(current.get('restored_formal_trials', {})) == {'debug04_01'},
        new42_attempts=len(new) == 42,
        new_expense_exact=close(new_spent, 3.44501),
        only_new_episode_labels=all(row['label'].startswith('policy:' + NEW_EPISODE + ':') for row in new),
        no_unsettled_reservations=all(row['status'] != 'RESERVED' for row in current['attempts']),
        all_returned_identity_exact=all(row.get('requested_model') == row.get('returned_model') == 'gpt-6-astra' for row in new),
        total_within_grant=len(current['attempts']) <= current['max_requests']
            and spent + new_spent <= current['max_estimated_usd'] + 1e-8,
    )
    return dict(passed=all(checks.values()), checks=checks, historical_attempts=len(base),
        historical_estimated_usd=spent, new_network_attempts=len(new), new_estimated_usd=new_spent,
        total_network_attempts=len(current['attempts']), total_estimated_usd=spent + new_spent,
        max_requests=current['max_requests'], max_estimated_usd=current['max_estimated_usd'],
        actual_bill_usd=None, actual_bill_reason='Local ledger estimates; no provider account invoice read')


def verify(root, *, asset_root=None, allow_dirty=False):
    root = Path(root).resolve()
    head = git(root, 'rev-parse', 'HEAD').strip()
    status = git(root, 'status', '--porcelain').strip()
    branch = git(root, 'branch', '--show-current').strip()
    errors, references, loaded, cache = [], [], {}, {}
    for name, expected in REFERENCES.items():
        actual = sha(root / name)
        references.append(dict(path=name, expected_sha256=expected, actual_sha256=actual,
                               unchanged=actual == expected))
        if actual != expected:
            raise ValueError('Pinned protection reference changed: ' + name)
        loaded[name] = load(root / name)
        if loaded[name].get('passed') is not True:
            raise ValueError('Pinned reference was not a passed audit: ' + name)
    previous = loaded[PREVIOUS + '/publication/protection_final.json']
    historical = loaded['docs/lab_cuvette_loading/Gpt_debug04_v1/results/historical/source_closed_audit.json']
    if (previous['final_commit'] != BASELINE or len(previous['historical_files']) != 599
            or len(previous['prior_closed_teacher_files']) != 10 or len(historical['source_files']) != 246):
        raise ValueError('Pinned historical group identity/count differs')
    prior = verify_records(root, previous['historical_files'], cache)
    teacher = verify_records(root, previous['prior_closed_teacher_files'], cache)
    legacy = verify_records(root, historical['source_files'], cache)
    prior_formal = []
    for name, value in loaded.items():
        if 'formal_' in name:
            rows = verify_records(root, value['source_files'], cache)
            prior_formal.append(dict(reference=name, episode_id=value['episode_id'],
                                     source_file_count=len(rows), source_files=rows,
                                     unchanged=all(row['unchanged'] for row in rows)))
    for label, rows in [('previous599', prior), ('Teacher10', teacher), ('debug04_246', legacy)]:
        if not all(row['unchanged'] for row in rows):
            errors.append(label + ' source evidence changed or missing')
    if not all(row['unchanged'] for row in prior_formal):
        errors.append('Previous four formal episodes changed or missing')

    protocol_path, auth_path = root / PROTOCOL, root / AUTHORIZATION
    if sha(protocol_path) != PROTOCOL_SHA or sha(auth_path) != AUTHORIZATION_SHA:
        raise ValueError('Executed protocol or explicit authorization identity changed')
    protocol, authorization = load(protocol_path), load(auth_path)
    if authorization['protocol_template_sha256'] != PROTOCOL_SHA:
        raise ValueError('Authorization is not bound to the executed frozen protocol')
    old_path = root / OLD_LEDGER
    ledger_path = rooted(root, authorization['authorized_ledger_path'])
    old, ledger = load(old_path), load(ledger_path)
    funding = funding_checks(old, ledger, authorization, ledger_path=ledger_path, original_sha=sha(old_path))
    funding.update(original_ledger_path=OLD_LEDGER, original_ledger_sha256=sha(old_path),
                   cumulative_ledger_path=relative(str(ledger_path)), cumulative_ledger_sha256=sha(ledger_path),
                   authorization_path=AUTHORIZATION, authorization_sha256=sha(auth_path),
                   protocol_sha256=sha(protocol_path))
    if (ledger.get('restored_profile_authorization_sha256') != AUTHORIZATION_SHA
            or ledger.get('historical_ledger_sha256') != authorization['original_ledger_sha256']):
        funding['passed'] = False
        funding['checks']['ledger_bound_hashes'] = False
    else:
        funding['checks']['ledger_bound_hashes'] = True
    if not funding['passed']:
        errors.append('Authorized cumulative funding/prefix identity failed')

    frozen = []
    if len(protocol['locked_source_files']) != 32:
        errors.append('Expected exactly32 executed frozen source hashes')
    for name, expected in protocol['locked_source_files'].items():
        actual = sha(root / name) if (root / name).is_file() else None
        runtime_bytes = git(root, 'show', RUNTIME + ':' + name, binary=True)
        runtime_sha = hashlib.sha256(runtime_bytes).hexdigest()
        frozen.append(dict(path=name, expected_sha256=expected, current_sha256=actual,
            runtime_commit_sha256=runtime_sha, unchanged=actual == expected == runtime_sha))
    if not all(row['unchanged'] for row in frozen):
        errors.append('Executed32 source hashes no longer match current source and runtime commit')

    subprocess.run(['git', 'merge-base', '--is-ancestor', BASELINE, head], cwd=root, check=True)
    subprocess.run(['git', 'merge-base', '--is-ancestor', RUNTIME, head], cwd=root, check=True)
    committed = names(root, 'diff', '--no-renames', '--name-only', BASELINE, head)
    working = names(root, 'diff', '--no-renames', '--name-only', 'HEAD')
    untracked = names(root, 'ls-files', '--others', '--exclude-standard')
    allowed = lambda name: name in ALLOWED_FILES or name.startswith(ALLOWED_PREFIXES)
    outside = sorted({name for name in committed + working + untracked if not allowed(name)})
    protected = names(root, 'diff', '--no-renames', '--name-only', BASELINE, '--', *PROTECTED_PATHS)
    exceptions = {LAUNCH}
    protected_changes = [name for name in protected if name not in exceptions and not name.startswith((
        'config/lab_cuvette_loading/Gpt_debug04_v1/', 'demos/lab_cuvette_gpt_debug04_v1/',
        'policy/backends/gpt_debug04_v1/'))]
    launch_exact = sha(root / LAUNCH) == protocol['locked_source_files'][LAUNCH]
    if outside:
        errors.append('Changes outside this round namespace/documentation/approved launcher scope')
    if protected_changes or not launch_exact:
        errors.append('Protected physical/scorer/runtime scope changed beyond exact frozen injection')
    if status and not allow_dirty:
        errors.append('Final audit requires a clean committed worktree; use --allow-dirty only for assessment')

    current_receipt_path = root / OUTPUT_BASE / 'validation/formal_debug04_01_closed.json'
    current_receipt = load(current_receipt_path)
    current_files = verify_records(root, current_receipt['source_files'], cache)
    current_closed = (current_receipt.get('passed') is True and current_receipt.get('record_complete') is True
        and current_receipt.get('source_hashes_unchanged') is True
        and current_receipt.get('runtime_commit') == RUNTIME and current_receipt.get('episode_id') == NEW_EPISODE
        and all(row['unchanged'] for row in current_files))
    if not current_closed:
        errors.append('New formal closed source evidence no longer matches audit')

    # Existing local checker only verifies lock-declared files; never downloads.
    module_path = root / 'demos/lab_cuvette_project_v1/assets.py'
    spec = importlib.util.spec_from_file_location('debug04_local_asset_protection', module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    published = module.check_assets(Path(asset_root or previous['published_assets']['asset_root']),
        lock_path=root / 'config/lab_cuvette_loading/Project_v1/assets.lock.json')
    assets_valid = (published.get('required_files') == 83 and published.get('all_files_verified') is True
        and published.get('revision') == 'bb880f098180c291f6f65995f969d48047207067')
    if not assets_valid:
        errors.append('Existing HF83 asset verification failed')
    head_after, status_after = git(root, 'rev-parse', 'HEAD').strip(), git(root, 'status', '--porcelain').strip()
    if head != head_after or status != status_after:
        errors.append('HEAD/worktree file membership changed while audit ran; repeat when stable')
    return dict(schema=SCHEMA, utc=datetime.now(timezone.utc).isoformat(), passed=not errors, errors=errors,
        assessment_only=allow_dirty, final_commit=None if allow_dirty else head, head=head, head_after=head_after,
        runtime_commit=RUNTIME, baseline_commit=BASELINE, branch=branch,
        checked_source_state='dirty_assessment' if status else 'clean_committed',
        references=references, historical_files=prior, historical_file_count=len(prior),
        prior_closed_teacher_files=teacher, prior_closed_teacher_file_count=len(teacher),
        historical_debug04_files=legacy, historical_debug04_file_count=len(legacy),
        all_historical_hashes_unchanged=all(row['unchanged'] for row in prior + teacher + legacy),
        prior_formal_episodes=prior_formal, prior_formal_episode_count=len(prior_formal),
        prior_formal_sources_unchanged=all(row['unchanged'] for row in prior_formal),
        new_closed_run_files=current_files, new_closed_run_file_count=len(current_files),
        new_closed_run_sources_unchanged=current_closed,
        new_closed_receipt_path=str(current_receipt_path), new_closed_receipt_sha256=sha(current_receipt_path),
        budget_and_policy_audit=funding, frozen_source_files=frozen, frozen_source_file_count=len(frozen),
        frozen_source_hashes_unchanged=all(row['unchanged'] for row in frozen),
        changed_files_since_baseline=committed, working_tree_changes=working, untracked_files=untracked,
        outside_evaluation_scope_changes=outside, protected_runtime_tree_changes=protected_changes,
        approved_launch_injection=dict(path=LAUNCH, sha256=sha(root / LAUNCH), matches_executed_frozen_source=launch_exact),
        protected_runtime_unchanged=not protected_changes and launch_exact,
        git_worktree_status=status, git_worktree_status_after=status_after, published_assets=published,
        audit_tool_sha256=sha(Path(__file__)),
        scope='Read-only source/evidence/ledger/local asset hashes; no credentials, HTTP, API, GPU, training or source mutation')


def self_test():
    checks = []
    with tempfile.TemporaryDirectory(prefix='labsim-debug04-protection-') as temporary:
        root = Path(temporary).resolve()
        source = root / '历史几何.txt'
        source.write_text('original geometry\n')
        rows = [dict(path=source.name, sha256=sha(source))]
        assert verify_records(root, rows, {})[0]['unchanged']
        source.write_text('changed geometry\n')
        assert not verify_records(root, rows, {})[0]['unchanged']
        checks += ['original source accepted', 'changed source rejected']
        try:
            rooted(root, '../escape')
        except ValueError:
            checks.append('path escape rejected')
        else:
            raise AssertionError('Evidence escape accepted')
        old = dict(attempts=[dict(status='OK', charged_estimate_usd=0.) for _ in range(377)],
                   max_requests=1500, max_estimated_usd=30.)
        old['attempts'][-1]['charged_estimate_usd'] = 29.267746
        ledger_path = root / 'new.json'
        auth = dict(approved=True, original_ledger_sha256='oldSHA', base_attempt_count=377,
                    base_estimated_usd=29.267746, additional_network_attempts=480,
                    additional_estimated_usd=20., maximum_formal_episodes=1,
                    authorized_ledger_path=str(ledger_path))
        current = json.loads(json.dumps(old))
        current.update(max_requests=857, max_estimated_usd=49.267746,
                       restored_formal_trials={'debug04_01': {}})
        current['attempts'] += [dict(label='policy:' + NEW_EPISODE + ':' + str(i), status='OK',
            charged_estimate_usd=3.44501 / 42, requested_model='gpt-6-astra', returned_model='gpt-6-astra')
            for i in range(42)]
        options = dict(ledger_path=ledger_path, original_sha='oldSHA')
        assert funding_checks(old, current, auth, **options)['passed']
        checks.append('exact authorized377+42 funding accepted')
        for label, mutate in [
            ('old expense tamper', lambda x: x['attempts'][0].update(charged_estimate_usd=1)),
            ('extra claimed trial', lambda x: x['restored_formal_trials'].update(debug04_02={})),
            ('extra cap', lambda x: x.update(max_estimated_usd=1000)),
            ('extra call', lambda x: x['attempts'].append(dict(x['attempts'][-1]))),
            ('wrong episode', lambda x: x['attempts'][-1].update(label='policy:another:0')),
        ]:
            broken = json.loads(json.dumps(current))
            mutate(broken)
            assert not funding_checks(old, broken, auth, **options)['passed']
            checks.append(label + ' rejected')
    return dict(schema=SCHEMA, passed=True, checks=checks, check_count=len(checks),
                real_project_protection_performed=False, api_calls=0, credential_reads=False)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path.cwd())
    parser.add_argument('--output', type=Path, help='New ignored output JSON; never overwrite')
    parser.add_argument('--asset-root', type=Path)
    parser.add_argument('--allow-dirty', action='store_true', help='Assessment only; final_commit remains null')
    parser.add_argument('--self-test', action='store_true', help='Temporary CPU fixtures only')
    args = parser.parse_args(argv)
    if args.output is None and not args.self_test:
        parser.error('Real verification requires --output NEW.json')
    if args.output is not None:
        if args.output.exists():
            parser.error('Output already exists: ' + str(args.output))
        root = args.root.resolve()
        if not args.output.resolve().is_relative_to(root / OUTPUT_BASE):
            parser.error('Protection receipts belong in this round ignored outputs directory')
    value = self_test() if args.self_test else verify(args.root, asset_root=args.asset_root, allow_dirty=args.allow_dirty)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open('x') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write('\n')
    keys = ('schema', 'passed', 'errors', 'assessment_only', 'head', 'runtime_commit', 'final_commit',
            'historical_file_count', 'historical_debug04_file_count', 'prior_closed_teacher_file_count',
            'prior_formal_episode_count', 'frozen_source_file_count', 'protected_runtime_unchanged', 'check_count')
    print(json.dumps({key: value[key] for key in keys if key in value}, ensure_ascii=False))
    return 0 if value['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
