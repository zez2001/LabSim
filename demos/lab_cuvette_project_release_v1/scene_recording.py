"""Persist fixed scene identity separately from outcome and BC qualification."""
from __future__ import annotations

import json


def scene_metadata(config):
    from demos.lab_cuvette_project_release_v1.scene_suite import (
        SUITE_VERSION, load_scene_definition, validate_selection,
    )
    suite = config.get('scene_suite', {})
    scene_id = str(suite.get('scene_id', 'standard'))
    expected = validate_selection(scene_id, purpose='eval')
    if suite:
        if suite.get('suite_version') != SUITE_VERSION:
            raise ValueError('Unsupported fixed scene suite identity')
        definition = load_scene_definition(scene_id)
        if suite.get('scene_definition_sha256') != definition['definition_sha256']:
            raise ValueError('Scene definition differs from its registered fixed instance')
        if list(suite.get('allowed_uses', [])) != expected['allowed_uses']:
            raise ValueError('Scene allowed uses differ from the registered protocol')
    if scene_id != 'standard' and config.get('release', {}).get('record_purpose') != 'policy_evaluation':
        raise ValueError('Random-10 records must declare policy_evaluation')
    execution = config.get('scene_execution', {})
    ordinals = {}
    for field in ('scene_repetition_index', 'suite_episode_index'):
        value = execution.get(field, 0)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(field + ' must be a nonnegative integer')
        ordinals[field] = value
    return dict(scene_id=scene_id,
        scene_suite_version=SUITE_VERSION if suite else 'historical_standard',
        scene_definition_sha256=str(suite.get('scene_definition_sha256', '')),
        scene_allowed_uses=json.dumps(expected['allowed_uses']),
        suite_run_id=str(execution.get('suite_run_id', '')),
        **ordinals, fixed_collection_eligible=scene_id == 'standard')


def source_identity(root):
    """Bind actual worktree source bytes, including new untracked implementation.

    Paths and hashes are recorded; source text, environment and credentials are
    never copied. Generated output and ignored files do not enter this identity.
    """
    import hashlib
    from pathlib import Path
    import subprocess
    root = Path(root)
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
    names = subprocess.check_output(['git', 'ls-files', '-z', '--cached', '--others', '--exclude-standard'],
        cwd=root).decode('utf-8').split('\0')
    files = {}
    for name in sorted(set(names)):
        if not name or not name.endswith(('.py', '.yaml', '.json', '.yml', '.sh')):
            continue
        if not name.startswith(('demos/', 'tasks/', 'controllers/', 'data_collectors/',
                                'factories/', 'utils/', 'scripts/', 'config/')):
            continue
        path = root / name
        if path.is_file() and not path.is_symlink():
            data = path.read_bytes()
            files[name] = dict(sha256=hashlib.sha256(data).hexdigest(), bytes=len(data),
                lfs_pointer=data.startswith(b'version https://git-lfs.github.com/spec/v1\n'))
    canonical = json.dumps(files, sort_keys=True, separators=(',', ':')).encode()
    return dict(code_commit=commit, worktree_source_sha256=hashlib.sha256(canonical).hexdigest(),
        files=files, scope='tracked and unignored new source/config bytes; excludes credentials, outputs and asset entities')
