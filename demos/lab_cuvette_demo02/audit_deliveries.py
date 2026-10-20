"""Read-only delivery search used by the V0_demo02 additional source audit.

Enumerates every CAD/archive filename in the requested roots, inspects all ZIP,
RAR and 7z member names without a model-name filter, hashes CAD member contents,
and deep-opens distinct possible external-source identities with offline USD or
Trimesh. Known libraries/generated outputs are classified, not falsely reported
as deeply parsed. No Isaac process, simulation, source extraction, or source edit.

The 2026-10-20 evidence recorded 49 archives, 131 CAD member occurrences and 5
opened content identities. These are historical observations, not fixed expected
counts: a new run records the filesystem as it exists at that run.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import zipfile
from zoneinfo import ZoneInfo

PROJECT = Path(__file__).resolve().parents[2]
CAD_SUFFIXES = {'.usd', '.usda', '.usdc', '.usdz', '.obj', '.stl', '.stp',
                '.step', '.igs', '.iges', '.sldprt', '.sldasm'}
ARCHIVE_SUFFIXES = {'.zip', '.rar', '.7z'}
SKIP = {'.git', '.cache', 'site-packages', 'node_modules', 'venv', '.venv',
        'env', '__pycache__', 'extscache', 'exts', 'extsDeprecated', 'extsPhysics',
        'kit', 'plugins', 'build', 'target', 'dist', 'checkpoints', 'wandb', 'runs'}
EXTERNAL = 'potential_external_delivery_requires_deep_open'
SUPPLIED = 'supplied_external_sources_and_delivery_copies'
KNOWN = {
    '8261714be7250b61466e9b3537a25438a5cc441c20a465ea6b3c27b43383a1dc':
        ('supplied_instrument', 'Original newnew4:8 rendered instrument mesh instances;6 abstract prototype meshes. See source_audit component pictures; no separate rack.'),
    'c7d6897a1e555c282ac30a53e95cb872fda4e112821d2a013a9612bd40e39f36':
        ('supplied_vessel_baked', 'Original single vessel /TestTube/Mesh; not rack.'),
    'dfb0480b5fa8106fdc444fded0bff2dbaa018409839d70207a6319392073b19f':
        ('legacy_vessel_entry', '151-byte original entry referencing absolute OBJ. Composed geometry may be unavailable; absence of geometry is not successful asset loading.'),
    'bd21a0050e832662bb08995d20fa4a3b179d80c103dbbf0546924dfbc9add0af':
        ('supplied_vessel_obj', 'Original vessel OBJ, also baked into the supplied single-mesh USD.'),
    'd00886f1bd5b62068fc9aa785273f6805e780772706d2e98878004f075de2f40':
        ('historical_minimal_pick_beaker', 'Old minimal_pick beaker: root customData cites LabUtopia8df7278 /World/beaker2/mesh, resized60mm. Added in commit77b3253; see minimal_pick README.'),
}


def classify(path, project):
    """Documented provenance/path exclusions; these are not deep-parse claims."""
    text = str(path)
    project_segment = '/'+project.name+'/'
    if '/physicalrsi-runtime/' in text:
        return 'physicalrsi_runtime_robot_asset_library'
    if '/physicalrsi-runs/' in text:
        return 'physicalrsi_previous_runs_runtime_cache_or_generated_scene'
    if '/LabUtopia/' in text:
        return 'original_LabUtopia_project_asset_library'
    if project_segment+'assets/lab_cuvette_loading/' in text and '/source/' in text:
        return SUPPLIED
    if project_segment+'assets/' in text:
        return 'LabSim_existing_library_or_versioned_generated_assets'
    if project_segment+'outputs/' in text or '/04_原始记录/' in text:
        return 'historical_generated_output_or_source_snapshot'
    if project_segment+'demos/minimal_precision_insertion/assets/' in text:
        return 'generated_precision_insertion_demo_assets'
    if '/reports/LabSim_亚毫米插入_' in text:
        return 'historical_generated_precision_insertion_delivery'
    return EXTERNAL


def hash_file(path, cache):
    stat = path.stat()
    key = (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns)
    if key not in cache:
        h = hashlib.sha256()
        with path.open('rb') as stream:
            for block in iter(lambda: stream.read(1024*1024), b''):
                h.update(block)
        cache[key] = h.hexdigest()
    return cache[key]


def enumerate_roots(roots, archive_tool):
    models, archives, errors, root_counts = [], [], [], {}
    for root in roots:
        count = 0
        if not root.exists():
            root_counts[str(root)] = {'exists': False}
            continue
        def onerror(error):
            errors.append({'path': error.filename, 'error': str(error)})
        for directory, dirs, files in os.walk(root, onerror=onerror):
            dirs[:] = [d for d in dirs if d not in SKIP and not d.endswith('-env')]
            for name in files:
                count += 1
                path = Path(directory)/name
                suffix = path.suffix.lower()
                if suffix not in CAD_SUFFIXES | ARCHIVE_SUFFIXES:
                    continue
                try:
                    size = path.stat().st_size
                except OSError as error:
                    errors.append({'path': str(path), 'error': str(error)})
                    continue
                if suffix in CAD_SUFFIXES:
                    models.append({'path': str(path), 'bytes': size})
                    continue
                entry = {'path': str(path), 'bytes': size, 'format': suffix,
                         'cad_members': [], 'member_count': None, 'error': None}
                try:
                    if suffix == '.zip':
                        with zipfile.ZipFile(path) as archive:
                            members = archive.infolist()
                            entry['member_count'] = len(members)
                            entry['cad_members'] = [
                                {'name': m.filename, 'bytes': m.file_size}
                                for m in members
                                if Path(m.filename).suffix.lower() in CAD_SUFFIXES]
                        entry['inspection_tool'] = 'zipfile.infolist; no name filter'
                    elif archive_tool:
                        result = subprocess.run([archive_tool, '-tf', str(path)],
                                                capture_output=True, text=True, check=True)
                        names = result.stdout.splitlines()
                        entry['member_count'] = len(names)
                        entry['all_members'] = names
                        entry['cad_members'] = [{'name': n, 'bytes': None} for n in names
                                                if Path(n).suffix.lower() in CAD_SUFFIXES]
                        entry['inspection_tool'] = 'bsdtar -tf; no name filter'
                    else:
                        entry['error'] = 'bsdtar unavailable; archive not inspected'
                except Exception as error:
                    entry['error'] = type(error).__name__+': '+str(error)
                archives.append(entry)
        root_counts[str(root)] = {'exists': True, 'files_enumerated': count}
    return models, archives, errors, root_counts


def archive_bytes(entry, member, archive_tool):
    if entry['format'] == '.zip':
        with zipfile.ZipFile(entry['path']) as archive:
            return archive.read(member)
    return subprocess.run([archive_tool, '-xOf', entry['path'], member],
                          capture_output=True, check=True).stdout


def deep_open(sha, paths, np, trimesh, Usd, UsdGeom):
    path = Path(paths[0])
    identity, basis = KNOWN.get(sha, ('unknown_requires_manual_review',
                                    'Not a previously audited content identity; inspect geometry before assigning a physical role.'))
    row = {'sha256': sha, 'copies': paths, 'primary_opened_path': str(path),
           'bytes': path.stat().st_size, 'known_content_identity': identity,
           'identity_evidence': basis, 'error': None, 'source_rack_identity': None}
    try:
        if path.suffix.lower() in {'.usd', '.usda', '.usdc', '.usdz'}:
            stage = Usd.Stage.Open(str(path), Usd.Stage.LoadAll)
            prims = list(Usd.PrimRange.Stage(
                stage, Usd.TraverseInstanceProxies(Usd.PrimAllPrimsPredicate)))
            active = list(Usd.PrimRange.Stage(stage, Usd.TraverseInstanceProxies()))
            cache = UsdGeom.XformCache()
            meshes = []
            for prim in prims:
                if not prim.IsA(UsdGeom.Mesh):
                    continue
                mesh = UsdGeom.Mesh(prim)
                v = np.asarray(mesh.GetPointsAttr().Get(), float).reshape(-1, 3)
                if len(v):
                    v = (np.c_[v, np.ones(len(v))] @
                         np.asarray(cache.GetLocalToWorldTransform(prim)))[:, :3]
                meshes.append({'path': str(prim.GetPath()), 'abstract': prim.IsAbstract(),
                               'active': prim.IsActive(), 'instance_proxy': prim.IsInstanceProxy(),
                               'visibility': UsdGeom.Imageable(prim).ComputeVisibility(),
                               'purpose': UsdGeom.Imageable(prim).ComputePurpose(),
                               'vertex_count': len(v),
                               'face_count': len(mesh.GetFaceVertexCountsAttr().Get() or []),
                               'world_stage_unit_bounds': np.asarray([v.min(0), v.max(0)]) if len(v) else None})
            row.update(format='USD', method='LoadAll + all prims and instance proxies, including abstract prototypes',
                       default_prim=str(stage.GetDefaultPrim().GetPath()) if stage.GetDefaultPrim() else None,
                       root_custom_data=stage.GetDefaultPrim().GetCustomData() if stage.GetDefaultPrim() else None,
                       meters_per_unit=UsdGeom.GetStageMetersPerUnit(stage),
                       up_axis=str(UsdGeom.GetStageUpAxis(stage)), all_prims_including_proxies=len(prims),
                       renderable_meshes=sum(p.IsA(UsdGeom.Mesh) for p in active), all_meshes=meshes,
                       external_references=list(stage.GetRootLayer().GetExternalReferences()))
            row['composed_geometry_available'] = row['renderable_meshes'] > 0
            if not row['composed_geometry_available']:
                row['geometry_warning'] = 'Stage opened but no rendered mesh composed; inspect dependency errors. This is not a complete asset-load success.'
        elif path.suffix.lower() in {'.obj', '.stl'}:
            mesh = trimesh.load(path, force='mesh', process=False)
            row.update(format=path.suffix[1:].upper(), method='trimesh process=False',
                       vertices=len(mesh.vertices), faces=len(mesh.faces),
                       raw_bounds=mesh.bounds, raw_dimensions=mesh.extents,
                       units='not inferred from filename; OBJ has no declared unit')
        else:
            row['error'] = 'No configured offline parser; not treated as inspected'
    except Exception as error:
        row['error'] = type(error).__name__+': '+str(error)
    return row


def raw_archive_layer(data, Sdf):
    """Parse unmatched text layers without resolving potentially broken references."""
    result = {'tool': 'Sdf.Layer.ImportFromString', 'error': None}
    try:
        layer = Sdf.Layer.CreateAnonymous('delivery_audit.usda')
        result['success'] = layer.ImportFromString(data.decode('utf-8'))
        prims = []
        def collect(path):
            spec = layer.GetObjectAtPath(path)
            if isinstance(spec, Sdf.PrimSpec):
                prims.append({'path': str(path), 'type': spec.typeName,
                              'references': str(spec.referenceList)})
        layer.Traverse(Sdf.Path.absoluteRootPath, collect)
        result.update(prims=prims, mesh_count=sum(p['type'] == 'Mesh' for p in prims))
    except Exception as error:
        result['error'] = type(error).__name__+': '+str(error)
        result['limitation'] = 'Binary/other CAD bytes require a format-specific parser; not declared inspected.'
    return result


def audit(args):
    # Imported after CLI validation so --help and existing-output rejection do not
    # require loading USD or inspecting any input files.
    import numpy as np
    import trimesh
    from pxr import Sdf, Usd, UsdGeom

    models, archives, errors, root_counts = enumerate_roots(args.roots, args.bsdtar)
    classified = defaultdict(list)
    for model in models:
        model['classification'] = classify(model['path'], args.project)
        classified[model['classification']].append(model)
    sizes = {m['bytes'] for a in archives for m in a['cad_members'] if m['bytes'] is not None}
    hashes, byhash = {}, defaultdict(list)
    for model in models:
        if model['bytes'] in sizes or model['classification'] in {SUPPLIED, EXTERNAL}:
            try:
                model['sha256'] = hash_file(Path(model['path']), hashes)
                byhash[model['sha256']].append(model['path'])
            except OSError as error:
                errors.append({'path': model['path'], 'error': str(error)})
    unmatched = []
    for entry in archives:
        try:
            entry['sha256'] = hash_file(Path(entry['path']), hashes)
            for member in entry['cad_members']:
                data = archive_bytes(entry, member['name'], args.bsdtar)
                h = hashlib.sha256(data).hexdigest()
                matches = byhash.get(h, [])
                member.update(sha256=h, same_content_local_file_count=len(matches),
                              same_content_local_files=matches[:5],
                              same_content_local_classifications=sorted({classify(p, args.project) for p in matches}))
                try:
                    member['legacy_gbk_recovered_name'] = member['name'].encode('cp437').decode('gbk')
                except UnicodeError:
                    member['legacy_gbk_recovered_name'] = None
                if not matches:
                    raw = {'archive': entry['path'], **member,
                           'raw_layer_inspection': raw_archive_layer(data, Sdf),
                           'provenance_status': 'requires_manual_review'}
                    if entry['format'] == '.zip':
                        with zipfile.ZipFile(entry['path']) as archive:
                            manifests = {n: json.loads(archive.read(n)) for n in archive.namelist()
                                         if n.endswith('manifest.json')}
                        raw['embedded_manifests'] = manifests
                        if manifests and all(m.get('version') == 'V0_demo02' and
                                             m.get('rack_asset_available') is False and
                                             m.get('workflow_executed') is False
                                             for m in manifests.values()):
                            raw['provenance_status'] = 'documented_V0_demo02_generated_review_draft'
                    unmatched.append(raw)
        except Exception as error:
            entry['content_inspection_error'] = type(error).__name__+': '+str(error)
    groups = defaultdict(list)
    for category in [SUPPLIED, EXTERNAL]:
        for model in classified[category]:
            if model.get('sha256'):
                groups[model['sha256']].append(model['path'])
    deep = [deep_open(h, paths, np, trimesh, Usd, UsdGeom) for h, paths in groups.items()]
    unresolved = [r for r in deep if r['error'] or r['known_content_identity'] == 'unknown_requires_manual_review']
    return {
        'date_local': datetime.now(ZoneInfo('Asia/Shanghai')).date().isoformat(),
        'scope_roots': root_counts, 'excluded_directory_names': sorted(SKIP),
        'regular_files_enumerated': sum(r.get('files_enumerated', 0) for r in root_counts.values()),
        'model_files_enumerated': len(models), 'archive_files_enumerated': len(archives),
        'archive_model_member_occurrences': sum(len(a['cad_members']) for a in archives),
        'archive_entries_checked_without_model_name_filter': True,
        'all_archive_directories_inspected': all(not a.get('error') for a in archives),
        'archives': archives,
        'model_path_classification_counts': dict(Counter(m['classification'] for m in models)),
        'classification_basis': 'Explicit previous-project library/generated-output paths, with external source subdirectory included; exclusions are not deep-parse claims.',
        'potential_external_models_before_deep_resolution': classified[EXTERNAL],
        'supplied_source_file_paths': classified[SUPPLIED],
        'deep_opened_unique_source_identities': deep,
        'unresolved_source_identities': unresolved,
        'unmatched_archive_CAD_members': unmatched,
        'errors': errors,
        'depth_claim_boundary': f'{len(models)} model files enumerated/classified; {len(deep)} distinct potential source contents actually opened. Generic libraries and historical generated outputs were NOT all deep-parsed. Archive names alone never establish geometry or physical role.',
        'source_rack_conclusion': 'Requires geometry/identity review of unknown or newly found candidates; this program does not label every unfamiliar model as not-a-rack.',
        'historical_reference': 'The separate 2026-10-20 additional_delivery_check.json recorded 49 archives, 131 CAD member occurrences and 5 opened identities; this fresh run does not overwrite or assert those counts.',
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True,
                        help='New JSON file; existing files/symlinks are refused before scanning.')
    parser.add_argument('--root', dest='roots', type=Path, action='append',
                        help='Read-only search root, repeatable. Default: Desktop, Downloads, Documents, ~/.codex/attachments.')
    parser.add_argument('--project', type=Path, default=PROJECT,
                        help='Existing LabSim project path used to classify generated/library paths.')
    parser.add_argument('--bsdtar', default=shutil.which('bsdtar'),
                        help='Optional bsdtar executable for RAR/7z listing; unavailability is reported, not silently skipped.')
    args = parser.parse_args()
    args.output = args.output.expanduser().absolute()
    if args.output.exists() or args.output.is_symlink():
        parser.error(f'Refusing to overwrite existing output: {args.output}')
    args.project = args.project.expanduser().resolve()
    args.roots = [p.expanduser().absolute() for p in (args.roots or [
        Path.home()/'Desktop', Path.home()/'Downloads', Path.home()/'Documents',
        Path.home()/'.codex/attachments'])]
    result = audit(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation also protects against another process creating the same
    # result path between initial validation and the end of a long audit.
    with args.output.open('x') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2,
                  default=lambda x: x.tolist() if hasattr(x, 'tolist') else str(x))
        stream.write('\n')
    print('DELIVERY_AUDIT_SAVED', args.output,
          'archives', result['archive_files_enumerated'],
          'deep_unique', len(result['deep_opened_unique_source_identities']),
          'unresolved', len(result['unresolved_source_identities']))


if __name__ == '__main__':
    main()
