"""Check staged changes (default) or an ancestor commit range without LFS downloads.

Only changed Git blobs are inspected. Exit 0 means passed, 2 means findings or
invalid input. This CPU-only guard neither installs a hook nor starts simulation.
"""
from __future__ import annotations

import argparse
import difflib
import fnmatch
import hashlib
import json
from pathlib import Path, PurePosixPath
import posixpath
import re
import subprocess
import tempfile
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
ANCHOR = '137f1b20b36f821894b6387ba36ee592231c8b1f'
LEGACY_COUNT = 414
# SHA256 of sorted UTF-8 baseline paths joined by LF, with a final LF.
LEGACY_DIGEST = 'fdb79c149b3752cf7b9802d6998a8ca92e1f998907ddf118ef0d179efb5193ee'
POLICY_PATH = 'config/repository_hygiene.json'
LEGACY_PATH = 'config/repository_hygiene_legacy_ignored.json'
TOKEN = re.compile(r'\b(?:sk-(?:(?:proj|svcacct)-)?[A-Za-z0-9_-]{20,}|hf_[A-Za-z0-9]{20,})\b')
PRIVATE_PATH = re.compile(r'(?:(?:/home|/Users|/mnt/[a-z]/Users)/[^\s\"\'<>`;,\])}]+|[A-Za-z]:[\\/]Users[\\/][^\s\"\'<>`;,\])}]+)')
CREDENTIAL = re.compile(r'''(?ix)["']?\b(?:api[_-]?key|api[_-]?token|access[_-]?token|auth[_-]?token|password|client[_-]?secret|secret[_-]?key|authorization)\b["']?\s*[:=]\s*(?:["']([^"'\n]*)["']|([^\s,\#}\]]+))''')
CONFIG_CREDENTIAL = re.compile(r'''(?ix)["']?\b(?:token|secret|hf[_-]?token|huggingface[_-]?token)\b["']?\s*[:=]\s*(?:["']([^"'\n]*)["']|([^\s,\#}\]]+))''')
GENERATED = re.compile(r'(^|/)(?:outputs|test_outputs|results|runs|recordings|checkpoints|trajectories|rollouts|wandb|__pycache__)(/|$)', re.I)
GENERATED_SUFFIXES = {'.mp4', '.mov', '.avi', '.webm', '.mkv', '.docx', '.zip', '.h5', '.hdf5', '.pt', '.pth', '.ckpt', '.safetensors'}
CONFIG_SUFFIXES = {'.yaml', '.yml', '.json', '.toml', '.ini', '.cfg', '.env'}
CURRENT_ENTRYPOINTS = {'README.md', 'README_CN.md', 'README_EN.md', 'AGENTS.md', 'CONTRIBUTING.md', 'DELIVERY.md'}


class GuardError(Exception):
    """Deliberately contains a generic diagnostic, never Git stderr/content."""


def git(root, *args, data=None, ok=(0,)):
    result = subprocess.run(['git', '-c', 'core.quotepath=false', *args], cwd=root,
                            input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode not in ok:
        raise GuardError('Git comparison failed; verify commits and repository state.')
    return result.stdout


def resolve(root, ref):
    if not ref or ref.startswith('-') or set(ref) == {'0'}:
        raise GuardError('A real commit reference is required; an all-zero push base is invalid.')
    return git(root, 'rev-parse', '--verify', ref + '^{commit}').decode().strip()


def tree(root, ref=None):
    entries = {}
    if ref is None:
        raw = git(root, 'ls-files', '--stage', '-z')
        for record in raw.split(b'\0'):
            if not record:
                continue
            meta, name = record.split(b'\t', 1)
            mode, oid, stage = meta.decode().split()
            if stage != '0':
                raise GuardError('Resolve unmerged index entries before checking staged changes.')
            entries[name.decode('utf-8', 'surrogateescape')] = (mode, oid)
    else:
        for record in git(root, 'ls-tree', '-r', '-z', ref).split(b'\0'):
            if record:
                meta, name = record.split(b'\t', 1)
                mode, kind, oid = meta.decode().split()
                if kind == 'blob':
                    entries[name.decode('utf-8', 'surrogateescape')] = (mode, oid)
    return entries


def blob(root, entry):
    return git(root, 'cat-file', 'blob', entry[1])


def blob_size(root, entry):
    return int(git(root, 'cat-file', '-s', entry[1]))


def ignored_paths(root, entries, paths):
    """Evaluate only versioned ignore rules, independent of the working tree/user excludes."""
    if not paths:
        return set()
    with tempfile.TemporaryDirectory(prefix='labsim-ignore-') as directory:
        sandbox = Path(directory)
        git(sandbox, 'init', '-q')
        for name, entry in entries.items():
            if PurePosixPath(name).name == '.gitignore' and entry[0] != '120000':
                target = sandbox / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(blob(root, entry))
        raw = git(sandbox, '-c', 'core.excludesFile=/dev/null', 'check-ignore', '--no-index', '-z', '--stdin',
                  data=b'\0'.join(p.encode('utf-8', 'surrogateescape') for p in paths) + b'\0', ok=(0, 1))
    return {p.decode('utf-8', 'surrogateescape') for p in raw.split(b'\0') if p}


def clean(value):
    return PRIVATE_PATH.sub('[redacted-private-path]', TOKEN.sub('[redacted-token]', str(value)))


FINDING_GUIDANCE = {
    'new_tracked_ignored_path': (
        'New tracked path matches the reviewed ignore rules.',
        'Keep runtime output under ignored outputs/ and remove it from the index. Legitimate fixtures or showcases need an exact path, purpose and max_bytes policy exception.'),
    'generated_runtime_output': (
        'The changed file is a runtime recording, report, trajectory, checkpoint or result output.',
        'Write runtime output to ignored outputs/. Publish formal assets through a pinned Hugging Face source; reviewed fixtures or showcases need an exact path, purpose and max_bytes exception.'),
    'new_large_file': (
        'The new payload or growth exceeds the size limit; LFS declared object bytes count.',
        'Publish formal assets through a pinned Hugging Face source and keep the manifest in Git. A necessary fixture or showcase needs an exact path, purpose and bounded max_bytes exception.'),
    'exception_size_exceeded': (
        'The file exceeds the maximum size of its reviewed exception.',
        'Reduce the curated file or review its exact path, purpose and size bound; put raw runtime output under ignored outputs/.'),
    'credential_token': (
        'Added or replaced text contains a credential-shaped token; the value is redacted.',
        'Remove the value, read credentials from environment variables and stage an environment-variable placeholder.'),
    'inline_credential': (
        'Added or replaced text assigns an inline credential; the value is redacted.',
        'Move the credential to an environment variable and stage a placeholder or environment lookup.'),
    'private_machine_path_in_config': (
        'Added or replaced config text contains a private machine path; the value is redacted.',
        'Use a repository-relative path or a portable environment-variable placeholder.'),
    'config_requires_content_review': (
        'The changed config cannot be scanned as bounded UTF-8 text.',
        'Keep a small reviewable UTF-8 config in Git; reference external assets through portable paths and credentials through environment variables.'),
    'local_link_outside_repository': (
        'A current Markdown link leaves the reviewed repository snapshot.',
        'Use a repository-relative target or a fixed published archive URL.'),
    'missing_local_link': (
        'A current Markdown link target is absent from the reviewed Git snapshot.',
        'Correct the target or stage the referenced file; use a fixed published archive URL for archived material.'),
    'missing_local_anchor': (
        'A current Markdown heading anchor is absent from the reviewed target.',
        'Correct the fragment to an existing heading or add the intended anchor to the staged target.'),
    'invalid_markdown_target': (
        'A linked Markdown target is not valid UTF-8 text.',
        'Stage a valid UTF-8 Markdown target or correct the link.'),
    'invalid_historical_archive_mapping': (
        'A removed historical target has no valid, fixed-commit archive mapping.',
        'Preserve the target or review a mapping with unchanged historical source, original hashes, same-repository Release URL and a verified restoration entry. Current guides must update their links.'),
    'invalid_comparison_or_policy': (
        'The comparison or reviewed policy is invalid.',
        'Stage the policy files together; supply an existing ancestor --base and --head pair, or omit both for staged changes. Compute a merge-base for divergent history.'),
    'report_output_unavailable': (
        'The requested receipt cannot be created without overwriting an existing file.',
        'Choose a new writable --output path.'),
}


def issue(code, path=None, **details):
    message, remediation = FINDING_GUIDANCE[code]
    result = {'code': code, 'message': message, 'remediation': remediation}
    if path is not None:
        result['path'] = clean(path)
    result.update(details)
    return result


def load_policy(root, entries):
    """Policy bytes come from the same reviewed index/commit as the changed blobs."""
    try:
        policy = json.loads(blob(root, entries[POLICY_PATH]))
        legacy = json.loads(blob(root, entries[LEGACY_PATH]))
    except (KeyError, OSError, ValueError):
        raise GuardError('Repository hygiene policy is missing from the reviewed Git snapshot or invalid JSON.') from None
    paths = legacy.get('paths', [])
    digest = hashlib.sha256(('\n'.join(sorted(paths)) + '\n').encode()).hexdigest()
    if (policy.get('baseline_commit') != ANCHOR or legacy.get('baseline_commit') != ANCHOR
            or len(paths) != LEGACY_COUNT or len(set(paths)) != LEGACY_COUNT or digest != LEGACY_DIGEST):
        raise GuardError('Frozen baseline ignored membership changed; restore the original 414-path policy.')
    validate_policy(policy)
    return policy, set(paths)


def validate_policy(policy):
    if not isinstance(policy.get('new_file_max_bytes'), int) or policy['new_file_max_bytes'] <= 0:
        raise GuardError('Policy requires a positive new_file_max_bytes limit.')
    if not isinstance(policy.get('text_scan_max_bytes'), int) or policy['text_scan_max_bytes'] <= 0:
        raise GuardError('Policy requires a positive bounded text_scan_max_bytes limit.')
    if not isinstance(policy.get('exceptions', []), list) or not all(isinstance(p, str) for p in policy.get('current_markdown', [])):
        raise GuardError('Policy exceptions and Markdown paths must be explicit lists.')
    for row in policy.get('exceptions', []):
        if (not isinstance(row, dict) or not isinstance(row.get('path'), str) or not row.get('purpose') or not isinstance(row.get('max_bytes'), int) or row['max_bytes'] <= 0
                or not row.get('path') or any(c in row['path'] for c in '*?[')
                or row['path'].startswith('/') or '..' in PurePosixPath(row['path']).parts):
            raise GuardError('Each exception requires an exact repository path, purpose and positive max_bytes.')
    mappings = policy.get('historical_archive_mappings', [])
    if not isinstance(mappings, list):
        raise GuardError('Historical archive mappings must be an explicit list.')
    for row in mappings:
        paths = [row.get('manifest'), row.get('archive_index')] if isinstance(row, dict) else []
        documents = row.get('historical_documents', []) if isinstance(row, dict) else []
        if (not paths or not all(repository_path(p) for p in paths)
                or not isinstance(documents, list) or not documents
                or not all(repository_path(p) and p not in CURRENT_ENTRYPOINTS for p in documents)
                or not re.fullmatch(r'[a-f0-9]{40}', row.get('verified_commit', ''))):
            raise GuardError('Archive mappings require exact paths, frozen historical documents and a full verified commit; current entrypoints cannot be exempted.')


def repository_path(value):
    return (isinstance(value, str) and bool(value) and not value.startswith('/')
            and '\\' not in value and '..' not in PurePosixPath(value).parts
            and not any(c in value for c in '*?[') and posixpath.normpath(value) == value)


def effective_size(root, entry):
    size = blob_size(root, entry)
    if size <= 1024:
        value = blob(root, entry)
        match = re.fullmatch(rb'version https://git-lfs.github.com/spec/v1\r?\noid sha256:[a-f0-9]{64}\r?\nsize ([0-9]+)\r?\n?', value)
        if match:
            return int(match.group(1)), size, True
    return size, size, False


def placeholder(value):
    value = value.strip()
    return (not value or value.lower() in {'none', 'null', 'false', 'true', 'env', 'redacted'}
            or value.startswith(('$', '<', 'os.getenv(', 'os.environ', 'getenv('))
            or bool(re.search(r'(?i)(example|placeholder|replace[_ -]?me|your[_ -]|dummy|changeme)', value))
            or bool(re.fullmatch(r'[A-Z][A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD)[A-Z0-9_]*', value)))


def added_text(old, new):
    """Scan added/replaced lines, so an unrelated edit does not re-report old content."""
    before, after = old.splitlines(), new.splitlines()
    return '\n'.join(line for tag, _a, _b, c, d in difflib.SequenceMatcher(None, before, after, autojunk=False).get_opcodes()
                     if tag in ('insert', 'replace') for line in after[c:d])


def headings(text):
    result, counts, fenced = set(), {}, False
    for line in text.splitlines():
        if line.lstrip().startswith(('```', '~~~')):
            fenced = not fenced
            continue
        match = re.match(r'^ {0,3}#{1,6}\s+(.+?)\s*#*$', line)
        if match and not fenced:
            value = re.sub(r'<[^>]*>', '', match.group(1))
            value = re.sub(r'\[([^]]+)\]\([^)]*\)', r'\1', value)
            value = re.sub(r'[^\w\- ]', '', value.lower()).replace(' ', '-')
            count = counts.get(value, 0)
            counts[value] = count + 1
            result.add(value if count == 0 else value + '-' + str(count))
    result.update(re.findall(r'<a\s+(?:name|id)=[\"\']([^\"\']+)', text))
    return result


def markdown_links(text):
    # Match the existing current-guide convention, including angle paths and titles.
    for match in re.finditer(r'\]\((<[^>]+>|[^)\n]+)\)|^ {0,3}\[[^]]+\]:\s*(<[^>]+>|\S+)', text, re.M):
        raw = (match.group(1) or match.group(2)).strip()
        yield raw[1:raw.index('>')] if raw.startswith('<') else raw.split(' ', 1)[0]
    for match in re.finditer(r'''(?is)<(?:a|img|video|source)\b[^>]*?\b(?:href|src)\s*=\s*["']([^"']+)["']''', text):
        yield match.group(1)


def local_link(name, raw):
    target = urlsplit(raw)
    if target.scheme or target.netloc:
        return None
    path = posixpath.normpath(posixpath.join(posixpath.dirname(name), unquote(target.path))) if target.path else name
    return path, target


def check_links(root, name, text, entries, *, removed=None, archive_allow=None):
    errors = []
    for raw in markdown_links(text):
        parsed = local_link(name, raw)
        if parsed is None:
            continue  # HTTP/archive/codex/mail links are inventoried by docs tools; never fetched here.
        path, target = parsed
        if removed is not None:
            # Scan unchanged guides only for targets removed in this comparison.
            # Existing broken historical links are not new findings.
            directory_removed = (any(p.startswith(path.rstrip('/') + '/') for p in removed)
                                 and not any(p.startswith(path.rstrip('/') + '/') for p in entries))
            if path not in removed and not directory_removed:
                continue
        if path.startswith('../') or path.startswith('/'):
            errors.append(issue('local_link_outside_repository', name, target=clean(raw)))
            continue
        if path not in entries:
            if target.fragment or not any(p.startswith(path.rstrip('/') + '/') for p in entries):
                archived = archive_allow(name, path) if archive_allow else False
                if not archived:
                    errors.append(issue('missing_local_link', name, target=clean(raw)))
            continue
        if target.fragment and path.lower().endswith('.md'):
            try:
                target_text = blob(root, entries[path]).decode('utf-8')
            except UnicodeError:
                errors.append(issue('invalid_markdown_target', name, target=clean(raw)))
                continue
            if unquote(target.fragment) not in headings(target_text):
                errors.append(issue('missing_local_anchor', name, target=clean(raw)))
    return errors


def archive_mapping(root, row, name, path, entries):
    """Validate a reviewed, fixed-commit mapping locally; never download an archive.

    The verification commit binds the already published archive index/manifest.
    Only an unchanged original historical document may keep its original link.
    """
    if name not in row['historical_documents']:
        return False
    try:
        verified = tree(root, resolve(root, row['verified_commit']))
        for target in (row['manifest'], row['archive_index']):
            if target not in entries or entries[target] != verified.get(target):
                return False
        manifest = json.loads(blob(root, entries[row['manifest']]))
        if manifest.get('schema') != 'labsim.historical_archive.v1':
            return False
        source_sha = manifest['baseline_commit']
        if not re.fullmatch(r'[a-f0-9]{40}', source_sha):
            return False
        source = tree(root, resolve(root, source_sha))
        if entries.get(name) != source.get(name) or name not in source:
            return False
        repository = manifest['repository_url'].rstrip('/')
        expected_repository = 'https://github.com/zez2001/LabSim'
        if repository != expected_repository:
            return False
        archive, release = manifest['archive'], manifest['release']
        if (not re.fullmatch(r'[a-f0-9]{64}', archive['sha256'])
                or not isinstance(archive['size_bytes'], int) or archive['size_bytes'] <= 0
                or not repository_path(archive['filename']) or '/' in archive['filename']
                or archive.get('format') != 'zip' or release['target_commit'] != source_sha
                or not re.fullmatch(r'[A-Za-z0-9._-]+', release['tag'])):
            return False
        download = repository + '/releases/download/' + release['tag'] + '/' + archive['filename']
        if release['archive_download_url'] != download:
            return False
        helper = manifest['restoration']['helper']
        if not repository_path(helper) or helper not in entries or helper not in verified:
            return False
        index = blob(root, entries[row['archive_index']]).decode('utf-8')
        if download not in index or archive['sha256'] not in index or helper not in index:
            return False
        member = next((f for f in manifest['files'] if f.get('path') == path), None)
        if member is None or path not in source or member.get('lfs_pointer') is not False:
            return False
        original = blob(root, source[path])
        expected_source = repository + '/blob/' + source_sha + '/' + path
        return (member.get('git_blob_oid') == source[path][1]
                and member.get('git_mode') == source[path][0]
                and member.get('size_bytes') == len(original)
                and member.get('sha256') == hashlib.sha256(original).hexdigest()
                and unquote(member.get('source', '')) == expected_source)
    except (GuardError, KeyError, ValueError, TypeError, UnicodeError, StopIteration):
        return False


def current_markdown(name, patterns):
    return any(fnmatch.fnmatchcase(name, pattern) and
               ('**' in pattern or name.count('/') == pattern.count('/')) for pattern in patterns)


def ci_comparison_base(root, before, head, anchor):
    """First branch push uses the audited anchor, never the empty tree."""
    first_push = not before or set(before) == {'0'}
    candidate = resolve(root, anchor if first_push else before)
    head = resolve(root, head)
    base = git(root, 'merge-base', candidate, head).decode().strip()
    if first_push and base != candidate:
        raise GuardError('First-push head must descend from the configured audited baseline.')
    return base


def check(root=ROOT, *, base=None, head=None, policy=None, legacy=None):
    root = Path(root)
    if (base is None) != (head is None):
        raise GuardError('Use --base and --head together, or omit both for the staged index.')
    if base is None:
        base_sha, head_sha, mode = resolve(root, 'HEAD'), None, 'staged'
        before, after = tree(root, base_sha), tree(root)
        reason = 'HEAD compared with the Git index; unstaged and untracked files are excluded.'
    else:
        base_sha, head_sha, mode = resolve(root, base), resolve(root, head), 'committed'
        if subprocess.run(['git', 'merge-base', '--is-ancestor', base_sha, head_sha], cwd=root,
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode:
            raise GuardError('Comparison base must be an ancestor of head; compute a merge-base first.')
        before, after = tree(root, base_sha), tree(root, head_sha)
        reason = 'Explicit ancestor commit range; CI uses merge-base (first push falls back to the fixed baseline).'
    if policy is None:
        policy, legacy = load_policy(root, after)
    else:
        validate_policy(policy)
        legacy = set(legacy or ())
    baseline = resolve(root, policy['baseline_commit'])
    baseline_entries = tree(root, baseline)
    # Frozen membership is verified against original rules, not whatever .gitignore says today.
    if not set(legacy).issubset(baseline_entries):
        raise GuardError('Frozen ignored paths must exist in the configured baseline.')
    if set(legacy) != ignored_paths(root, baseline_entries, sorted(baseline_entries)):
        raise GuardError('Frozen ignored paths do not match baseline tracked-and-ignored membership.')
    changes = sorted(name for name in after if before.get(name) != after[name])
    ignored = ignored_paths(root, after, changes)
    errors, rows = [], []
    removed = set(before) - set(after)
    archived_links, archive_failures = [], set()

    def allow_archived(name, target):
        candidates = [row for row in policy.get('historical_archive_mappings', [])
                      if name in row['historical_documents']]
        if any(archive_mapping(root, row, name, target, after) for row in candidates):
            receipt = dict(document=clean(name), target=clean(target))
            if receipt not in archived_links:
                archived_links.append(receipt)
            return True
        if candidates:
            archive_failures.add((name, target))
        return False

    for name in changes:
        state = 'modified' if name in before else 'added'
        size, stored_size, lfs = effective_size(root, after[name])
        row = dict(path=clean(name), change=state, blob_bytes=stored_size,
                   effective_bytes=size, lfs_pointer=lfs)
        rows.append(row)
        exception = next((e for e in policy.get('exceptions', []) if e['path'] == name), None)
        permitted = bool(exception and size <= exception['max_bytes'])
        if permitted:
            row['exception_purpose'] = exception['purpose']
        elif exception:
            errors.append(issue('exception_size_exceeded', name, max_bytes=exception['max_bytes'], effective_bytes=size))
        if name in ignored and name not in legacy and not permitted:
            errors.append(issue('new_tracked_ignored_path', name))
        suffix = PurePosixPath(name).suffix.lower()
        generated = bool(GENERATED.search(name) or suffix in GENERATED_SUFFIXES)
        if generated and not permitted:
            errors.append(issue('generated_runtime_output', name))
        old_size = effective_size(root, before[name])[0] if name in before else 0
        if size > policy['new_file_max_bytes'] and (state == 'added' or size > old_size) and not permitted:
            errors.append(issue('new_large_file', name, effective_bytes=size, previous_bytes=old_size,
                                limit_bytes=policy['new_file_max_bytes'], lfs_pointer=lfs))
        is_config = (name.startswith('config/') or suffix in CONFIG_SUFFIXES or PurePosixPath(name).name.startswith('.env'))
        if lfs or stored_size > policy.get('text_scan_max_bytes', 2 * 1024 * 1024):
            if is_config and not GENERATED.search(name):
                errors.append(issue('config_requires_content_review', name,
                                    message='Config content is an LFS pointer or exceeds the bounded text scan; use a small reviewable config.'))
            continue
        raw = blob(root, after[name])
        if b'\0' in raw:
            if is_config and not GENERATED.search(name):
                errors.append(issue('config_requires_content_review', name, message='Config must be reviewable UTF-8 text.'))
            continue
        try:
            text = raw.decode('utf-8')
        except UnicodeError:
            if is_config and not GENERATED.search(name):
                errors.append(issue('config_requires_content_review', name, message='Config must be reviewable UTF-8 text.'))
            continue
        old = blob(root, before[name]).decode('utf-8', 'replace') if name in before and blob_size(root, before[name]) <= policy.get('text_scan_max_bytes', 2 * 1024 * 1024) else ''
        fresh = added_text(old, text)
        if TOKEN.search(fresh):
            errors.append(issue('credential_token', name))
        if any(not placeholder(m.group(1) if m.group(1) is not None else m.group(2))
               and not (m.group(1) is None and not is_config and
                        re.fullmatch(r'[A-Za-z_][A-Za-z0-9_.]*', m.group(2)))
               for m in list(CREDENTIAL.finditer(fresh)) + (list(CONFIG_CREDENTIAL.finditer(fresh)) if is_config else [])):
            errors.append(issue('inline_credential', name))
        if is_config and not GENERATED.search(name) and PRIVATE_PATH.search(fresh):
            errors.append(issue('private_machine_path_in_config', name))
        if suffix in ('.md', '.mdc') and current_markdown(name, policy.get('current_markdown', [])):
            errors.extend(check_links(root, name, text, after, archive_allow=allow_archived))
    removal_checked_documents = []
    if removed:
        for name, entry in sorted(after.items()):
            if (name in changes or not current_markdown(name, policy.get('current_markdown', []))
                    or PurePosixPath(name).suffix.lower() not in ('.md', '.mdc')):
                continue
            removal_checked_documents.append(clean(name))
            size, stored_size, lfs = effective_size(root, entry)
            if lfs or stored_size > policy['text_scan_max_bytes']:
                raise GuardError('A current guide cannot be inspected for removed targets; use small UTF-8 Markdown.')
            try:
                text = blob(root, entry).decode('utf-8')
            except UnicodeError:
                errors.append(issue('invalid_markdown_target', name))
                continue
            errors.extend(check_links(root, name, text, after, removed=removed, archive_allow=allow_archived))
    errors.extend(issue('invalid_historical_archive_mapping', name, target=clean(target))
                  for name, target in sorted(archive_failures))
    return dict(schema='labsim.repository_hygiene.v1', passed=not errors, mode=mode,
                base_commit=base_sha, head_commit=head_sha, comparison_reason=reason,
                baseline_commit=baseline, baseline_ignored_count=len(legacy), changed_file_count=len(changes),
                deleted_file_count=len(removed), files=rows, errors=errors,
                removal_checked_documents=removal_checked_documents, archived_links=archived_links,
                simulation_started=False, lfs_downloaded=False, network_accessed=False)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', help='Ancestor commit reference (use with --head)')
    parser.add_argument('--head', help='Head commit reference (use with --base)')
    parser.add_argument('--json', action='store_true', help='Print the full JSON receipt')
    parser.add_argument('--output', type=Path, help='Write a new JSON receipt; never overwrite')
    args = parser.parse_args(argv)
    try:
        result = check(root=ROOT, base=args.base, head=args.head)
    except (GuardError, ValueError, TypeError, KeyError, OSError) as error:
        result = dict(schema='labsim.repository_hygiene.v1', passed=False,
                      errors=[issue('invalid_comparison_or_policy', message=str(error) if isinstance(error, GuardError) else 'Invalid comparison, policy structure or text format.')])
    if args.output:
        try:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open('x', encoding='utf-8') as stream:
                json.dump(result, stream, ensure_ascii=True, indent=2)
                stream.write('\n')
        except OSError:
            result = dict(passed=False, errors=[issue('report_output_unavailable')])
    if args.json:
        print(json.dumps(result, ensure_ascii=True, indent=2))
    else:
        print('Repository hygiene: ' + ('PASS' if result['passed'] else 'FAIL'))
        if 'changed_file_count' in result:
            print(f"Checked {result['changed_file_count']} changed file(s); baseline ignored membership: {result['baseline_ignored_count']}.")
        for error in result['errors']:
            print(error['code'] + (': ' + error['path'] if 'path' in error else '') +
                  (': ' + error['message'] if 'message' in error else ''))
            print('  Action: ' + error['remediation'])
    return 0 if result['passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
