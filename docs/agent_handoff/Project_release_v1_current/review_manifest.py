#!/usr/bin/env python3
"""CPU-only static review of release package sources; does not build a package."""
from pathlib import Path
from urllib.parse import urlsplit, unquote
import hashlib
import json
import re
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
VIRTUAL = Path('/__labsim_technical_package_preview_not_created__')


def main():
    manifest = HERE / 'package.json'
    config = json.loads(manifest.read_text())
    mapping = {ROOT / row['source']: VIRTUAL / row['destination'] for row in config['files']}
    readme = ROOT / config['readme']
    mapping[readme] = VIRTUAL / '00_给Agent阅读说明.md'
    errors, unresolved, credentials, pointers, selected_hashes = [], [], [], [], {}
    parsed = markdown_local = fixed_git = 0
    targets = set(mapping.values())
    if len(targets) != len(mapping):
        errors.append('Duplicate package destination')
    # Only selected files are scanned. Never open the credential store.
    secret = re.compile(rb'(?:sk-user-[0-9a-fA-F]{40,}|hf_[A-Za-z0-9]{25,}|Bearer\s+[A-Za-z0-9._-]{30,})')
    for source, target in mapping.items():
        rel = source.relative_to(ROOT).as_posix()
        if not source.is_file() or source.is_symlink():
            errors.append('Missing/symlink ' + rel)
            continue
        if source.suffix.lower() in {'.h5', '.hdf5', '.zip', '.pt', '.pth', '.safetensors'}:
            errors.append('Forbidden bulk ' + rel)
        if any('CPU' in part and 'attempt' in part for part in source.parts):
            errors.append('CPU attempt selected ' + rel)
        raw = source.read_bytes()
        if raw.startswith(b'version https://git-lfs.github.com/spec/v1'):
            pointers.append(rel)
        if secret.search(raw):
            credentials.append(rel)
        if source.name != 'static_review.json':
            selected_hashes[rel] = dict(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(),
                                       destination=target.relative_to(VIRTUAL).as_posix())
        if source.suffix == '.json':
            try:
                json.loads(raw)
                parsed += 1
            except Exception as exc:
                errors.append(f'JSON {rel}: {exc}')
        if source.suffix == '.xml':
            try:
                ET.fromstring(raw)
            except Exception as exc:
                errors.append(f'XML {rel}: {exc}')
        if source.suffix != '.md':
            continue
        for match in re.finditer(r'\]\(([^\n)]+)\)', raw.decode('utf-8')):
            value = match.group(1)
            url = urlsplit(value)
            if '{{' in value or url.scheme or url.netloc or not url.path:
                continue
            original = (ROOT / unquote(url.path)) if source == readme else (source.parent / unquote(url.path)).resolve()
            if source == readme:
                requested = (VIRTUAL / unquote(url.path)).resolve()
                if requested not in targets and not any(t.is_relative_to(requested) for t in targets):
                    unresolved.append(dict(source=rel, reference=value, scope='package readme'))
                else:
                    markdown_local += 1
            elif original in mapping or any(x.is_relative_to(original) for x in mapping):
                markdown_local += 1
            elif original.is_relative_to(ROOT) and original.exists():
                fixed_git += 1
            else:
                unresolved.append(dict(source=rel, reference=value, scope='repository source'))

    docx = ROOT / 'docs/lab_cuvette_loading/Project_release_v1/report/LabSim_环境与评测进展_20261028.docx'
    media_links = []
    with zipfile.ZipFile(docx) as archive:
        for name in archive.namelist():
            if not name.endswith('.rels'):
                continue
            for item in ET.fromstring(archive.read(name)):
                if not item.attrib.get('Type', '').endswith('/hyperlink'):
                    continue
                value = item.attrib.get('Target', '')
                url = urlsplit(value)
                if not url.scheme and not url.netloc:
                    target = mapping[docx].parent / unquote(url.path)
                    found = target in targets
                    media_links.append(dict(target=value, package_target=target.relative_to(VIRTUAL).as_posix(), selected=found))
                    if not found:
                        errors.append('Unresolved DOCX media ' + value)
    qa = json.loads((ROOT / 'docs/lab_cuvette_loading/Project_release_v1/meeting_source/meeting_final_media_QA.json').read_text())
    media_checks = []
    for row in qa['media']:
        native = Path(row['source'])
        copied = ROOT / 'docs/lab_cuvette_loading/Project_release_v1/media' / row['file']
        a = hashlib.sha256(native.read_bytes()).hexdigest()
        b = hashlib.sha256(copied.read_bytes()).hexdigest()
        good = a == b == row['sha256']
        media_checks.append(dict(file=row['file'], native_source_bytes=native.stat().st_size,
            package_source_bytes=copied.stat().st_size, sha256=b, byte_identical_to_native_and_QA=good))
        if not good:
            errors.append('Native/copied media mismatch ' + row['file'])
    if credentials:
        errors.append('Potential credential literal in selected paths')
    if pointers:
        errors.append('Unresolved LFS pointer')
    if unresolved:
        errors.append('Unresolved Markdown references')
    report = dict(schema='labsim.Project_release_v1.package_static_review.v2',
        status='selection_ready_no_archive_built' if not errors else 'blocked', package_built=False,
        manifest_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest(),
        selected_sources_including_readme=len(mapping),
        selected_bytes_before_this_review=sum(p.stat().st_size for p in mapping),
        selected_JSON_files_parsed=parsed, selected_LFS_pointers=pointers,
        credential_pattern_matching_paths=credentials,
        relative_Markdown_package_targets_resolved=markdown_local,
        repository_references_to_fixed_commit=fixed_git,
        unresolved_Markdown_references=unresolved, DOCX_relative_media_links=media_links,
        actual_native_videos_byte_identity=media_checks, errors=errors,
        provenance_scope='All selected sources hashed except this self-changing review; no H5/weights/high-frequency stream opened; no GPU/API/paid calls.',
        postcommit_procedure=['Root commits/pushes finalized files and checks actual remote/CI',
            'Run existing package_agent_results.py only after root final commit',
            'Verify generated SHA256SUMS, moved package links, archive content and absence of secrets'],
        source_files=selected_hashes)
    (HERE / 'static_review.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({key: value for key, value in report.items() if key != 'source_files'}, ensure_ascii=False, indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
