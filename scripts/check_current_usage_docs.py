"""CPU-only current-guide links, anchors and real CLI routing checks.

Historical version commands and previous_guides archives are excluded from
current-version routing checks. Network links are inventoried, not fetched.
"""
from __future__ import annotations

import argparse
from contextlib import redirect_stderr
import io
import json
from pathlib import Path
import re
import shlex
import tempfile
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
CURRENT_GUIDES = (
    'README.md', 'README_EN.md', 'README_CN.md',
    'docs/development/ONBOARDING.md',
    'docs/lab_cuvette_loading/Project_release_v1/README.md',
    'docs/lab_cuvette_loading/Project_release_v1/data_usage.md',
    'docs/lab_cuvette_loading/Project_release_v1/external_policy/contract.md',
    'policy/backends/OPTIONAL_POLICIES.md',
)
HISTORICAL_NAVIGATION = ('docs/lab_cuvette_loading/Project_v1_1/README.md',)
VERSIONED_COMMANDS = frozenset(('doctor', 'demo', 'collect', 'eval', 'serve'))


def anchors(text):
    """GitHub-style heading IDs, including duplicate suffixes and Unicode."""
    result, counts = set(), {}
    fenced = False
    for line in text.splitlines():
        if line.lstrip().startswith(('```', '~~~')):
            fenced = not fenced
            continue
        match = re.match(r'^ {0,3}#{1,6}\s+(.+?)\s*#*$', line)
        if fenced or not match:
            continue
        value = re.sub(r'<[^>]*>', '', match.group(1))
        value = re.sub(r'\[([^]]+)\]\([^)]*\)', r'\1', value)
        value = re.sub(r'[^\w\- ]', '', value.lower()).replace(' ', '-')
        count = counts.get(value, 0)
        counts[value] = count + 1
        result.add(value if count == 0 else value + '-' + str(count))
    result.update(re.findall(r'<a\s+(?:name|id)=[\"\']([^\"\']+)', text))
    return result


def cli_examples(text):
    """Read ./labsim examples from shell fences and standalone inline code."""
    examples = []
    fenced, shell = False, False
    pending, first_line = '', None
    for number, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith('```'):
            if not fenced:
                fenced, shell = True, stripped[3:].strip() in ('bash', 'sh', 'shell', '')
            else:
                fenced, shell = False, False
            continue
        if fenced and shell:
            if not pending and (not stripped or stripped.startswith('#')):
                continue
            if first_line is None:
                first_line = number
            pending += (' ' if pending else '') + stripped.rstrip('\\').rstrip()
            if stripped.endswith('\\'):
                continue
            if pending.startswith('./labsim '):
                examples.append((first_line, shlex.split(pending, comments=True)))
            pending, first_line = '', None
        elif not fenced:
            for inline in re.findall(r'`([^`\n]+)`', line):
                if inline.startswith('./labsim '):
                    examples.append((number, shlex.split(inline)))
    return examples


def inspect_guide(root, relative, *, current=True):
    from scripts import labsim_cli as cli
    path = root / relative
    result = dict(path=relative, current=current, local_links=[], external_links=[], commands=[], errors=[])
    if not path.is_file():
        result['errors'].append(dict(type='missing_guide', path=relative))
        return result
    text = path.read_text()
    for match in re.finditer(r'\]\(([^)\n]+)\)', text):
        raw = match.group(1).strip()
        raw = raw[1:raw.index('>')] if raw.startswith('<') and '>' in raw else raw.split(' ', 1)[0]
        split = urlsplit(raw)
        if split.scheme or split.netloc:
            result['external_links'].append(raw)
            continue
        target = (path.parent / unquote(split.path)).resolve() if split.path else path
        row = dict(target=raw, exists=target.exists(), anchor=unquote(split.fragment) or None)
        result['local_links'].append(row)
        if not target.exists():
            result['errors'].append(dict(type='missing_local_link', target=raw))
        elif split.fragment and target.suffix.lower() == '.md' and unquote(split.fragment) not in anchors(target.read_text()):
            result['errors'].append(dict(type='missing_anchor', target=raw))
    if not current:
        return result
    for line, argv in cli_examples(text):
        if len(argv) < 2 or argv[1] not in VERSIONED_COMMANDS:
            continue
        row = dict(line=line, argv=argv, project_version=None, module=None)
        result['commands'].append(row)
        if '--project-version' not in argv:
            result['errors'].append(dict(type='missing_explicit_version', line=line, argv=argv))
            continue
        try:
            with redirect_stderr(io.StringIO()):
                parsed = cli.parser().parse_args(argv[1:])
            row['project_version'] = parsed.project_version
            if parsed.project_version != 'Project_release_v1':
                raise ValueError('Current usage example must select Project_release_v1')
            if argv[1] != 'doctor':
                # Check the real router without creating files or depending on
                # whether a user's illustrative output directory already exists.
                with tempfile.TemporaryDirectory(prefix='labsim-doc-route-') as directory:
                    parsed.output = str(Path(directory) / 'new_run')
                    command = cli.build_command(parsed)
                row['module'] = command[2]
                expected = ('demos.lab_cuvette_project_release_v1.run' if parsed.sequence else
                            'demos.lab_cuvette_project_release_v1.launch')
                if row['module'] != expected:
                    raise ValueError('Guide routed outside the declared release entry')
        except (ValueError, OSError, SystemExit) as error:
            result['errors'].append(dict(type='invalid_cli_route', line=line, error=str(error), argv=argv))
    return result


def check(root=ROOT):
    root = Path(root).resolve()
    rows = [inspect_guide(root, name) for name in CURRENT_GUIDES]
    rows += [inspect_guide(root, name, current=False) for name in HISTORICAL_NAVIGATION]
    errors = [dict(guide=row['path'], **error) for row in rows for error in row['errors']]
    chinese = [argv for _, argv in cli_examples((root / 'README.md').read_text())]
    english = [argv for _, argv in cli_examples((root / 'README_EN.md').read_text())]
    if chinese != english:
        errors.append(dict(type='homepage_command_mismatch', chinese=chinese, english=english))
    for name in ('README.md', 'README_EN.md', 'docs/development/ONBOARDING.md'):
        examples = [argv for _, argv in cli_examples((root / name).read_text())]
        for verb in ('demo', 'collect'):
            first = next((argv for argv in examples if argv[1] == verb), None)
            if (not first or '--sequence' in first or '--backend' not in first or
                    first[first.index('--backend') + 1] != 'teacher'):
                errors.append(dict(type='first_example_not_full_teacher', guide=name, command=verb))
    return dict(schema='labsim.current_usage_docs.v1', root=str(root),
        simulation_started=False, network_accessed=False, guides=rows, errors=errors,
        command_count=sum(len(row['commands']) for row in rows),
        local_link_count=sum(len(row['local_links']) for row in rows), passed=not errors)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, help='New JSON report path; never overwrite')
    args = parser.parse_args(argv)
    value = check()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open('x') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
    print(json.dumps({key: value[key] for key in ('passed', 'command_count', 'local_link_count', 'errors')},
                     ensure_ascii=False, indent=2))
    return 0 if value['passed'] else 2


if __name__ == '__main__':
    import sys
    sys.path.insert(0, str(ROOT))
    raise SystemExit(main())
