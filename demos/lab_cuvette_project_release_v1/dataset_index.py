"""Closed-process multi-episode index for the unchanged normal ACT/DP reader."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import time

import h5py

from data_collectors.lab_cuvette_project_release_collector import atomic_text
from utils.episode_selection import episode_matches_filter
from demos.lab_cuvette_project_release_v1.membership import PURPOSES, file_sha256, load_members


def build_index(run_directory, destination, *, mode='relative-links', require_closed_process=True,
                purpose='all-completed', members=None):
    """Select usage independently of the unchanged success/failure qualification.

    Python's historical default retains all completed records. The CLI defaults
    to policy_evaluation; callers collecting demonstrations select that purpose.
    """
    run, destination = Path(run_directory).resolve(), Path(destination).resolve()
    if mode not in {'copy', 'relative-links'}:
        raise ValueError('Index mode must be copy or relative-links')
    manifest = json.loads((run / 'run_manifest.json').read_text())
    pid = int(manifest['process_id'])
    if pid <= 0:
        raise ValueError('Source process_id must be a positive PID')
    if purpose not in PURPOSES | {'all-completed', 'members'}:
        raise ValueError('Unknown purpose selection: ' + str(purpose))
    annotations, membership_provenance = load_members(members)
    if purpose == 'members' and members is None:
        raise ValueError('The members purpose selection requires --members')
    if require_closed_process:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            pass
        else:
            raise RuntimeError('Source Isaac process still exists; close it before building the release index')
    if destination.exists():
        raise FileExistsError(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name('.' + destination.name + '.pending')
    if temporary.exists():
        raise FileExistsError(temporary)
    rows, identities = [], set()
    counts = dict(success=0, failure=0, all_valid=0, incomplete=0)
    source_counts = dict(counts)
    started = time.perf_counter()
    try:
        with h5py.File(temporary, 'x') as index:
            index.attrs.update(schema_version='labsim.Project_release_v1.index.v2',
                index_mode=mode, complete=False,
                self_contained=(mode == 'copy'), external_links_relative=(mode == 'relative-links'),
                purpose_selection=purpose)
            for source in sorted(run.glob('episode_*/dataset/episode_*.h5')):
                with h5py.File(source) as episode:
                    identity = str(episode.attrs['episode_id'])
                    if identity in identities:
                        raise ValueError('Duplicate episode identity in source cohort')
                    identities.add(identity)
                    decisions = {name: episode_matches_filter(episode.attrs, name)
                                 for name in ('success', 'failure', 'all_valid')}
                    filters = {name: value[0] for name, value in decisions.items()}
                    complete = bool(episode.attrs.get('complete', False)) and episode.attrs.get('publication_state') == 'complete'
                    declared = str(episode.attrs.get('record_purpose', 'unknown'))
                    if declared not in PURPOSES | {'unknown'}:
                        raise ValueError('Unknown declared record_purpose for ' + identity)
                    annotation = annotations.get(identity)
                    source_sha = file_sha256(source)
                    if annotation:
                        if source != annotation['source_path']:
                            raise ValueError('Member source path mismatch: ' + identity)
                        if source_sha != annotation['source_h5_sha256']:
                            raise ValueError('Member source H5 hash mismatch: ' + identity)
                        annotated = annotation.get('record_purpose', 'unknown')
                        if declared != 'unknown' and annotated != declared:
                            raise ValueError('Member purpose conflicts with recorded purpose: ' + identity)
                        declared = annotated
                    accepted_purpose = purpose == 'all-completed' or (
                        purpose == 'members' and annotation is not None) or declared == purpose
                    # A supplied membership file is also an explicit cohort limit.
                    if members is not None and annotation is None:
                        accepted_purpose = False
                        exclusion = 'not_in_explicit_members'
                    elif not accepted_purpose:
                        exclusion = 'purpose_unknown' if declared == 'unknown' else 'purpose_mismatch'
                    else:
                        exclusion = None
                    if not complete:
                        exclusion = 'publication_not_complete'
                    row = dict(episode_id=identity, source=os.path.relpath(source, destination.parent),
                        source_bytes=source.stat().st_size, source_h5_sha256=source_sha,
                        complete=complete, record_purpose=declared,
                        purpose_source='members_sidecar' if annotation else ('recorded' if declared != 'unknown' else 'unknown'),
                        included=complete and accepted_purpose, exclusion_reason=exclusion,
                        task_success=bool(episode.attrs.get('task_success')) if episode.attrs.get('task_success_known') else None,
                        failure_type=str(episode.attrs.get('failure_type', 'UNKNOWN')), filters=filters,
                        filter_reasons={name: value[1] for name, value in decisions.items()},
                        finalization_id=str(episode.attrs.get('finalization_id', '')))
                    rows.append(row)
                    if not complete:
                        counts['incomplete'] += 1
                        source_counts['incomplete'] += 1
                        continue
                    for name, accepted in filters.items():
                        source_counts[name] += int(accepted)
                    if not accepted_purpose:
                        continue
                    for name, accepted in filters.items():
                        counts[name] += int(accepted)
                    # Purpose selects cohort membership; readers still apply
                    # the original qualification, score and success gates.
                    name = source.parent.parent.name
                    if name in index:
                        raise ValueError('Duplicate source directory name')
                    if mode == 'copy':
                        group = index.create_group(name)
                        group.attrs.update(dict(episode.attrs))
                        copied_objects = {}
                        for key in episode:
                            # Preserve root camera aliases as hard links. Calling
                            # H5Ocopy independently for each alias would duplicate
                            # every training image in an otherwise portable index.
                            address = h5py.h5o.get_info(episode[key].id).addr
                            if address in copied_objects:
                                group[key] = group[copied_objects[address]]
                            else:
                                episode.copy(key, group)
                                copied_objects[address] = key
                    else:
                        index[name] = h5py.ExternalLink(row['source'], '/')
            missing = sorted(set(annotations) - identities)
            if missing:
                raise ValueError('Explicit members absent from source run: ' + ', '.join(missing))
            index.attrs['membership_json'] = json.dumps(rows, ensure_ascii=False)
            index.attrs['complete'] = True
            index.flush()
        os.replace(temporary, destination)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    digest = hashlib.sha256()
    with destination.open('rb') as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            digest.update(block)
    result = dict(schema='labsim.Project_release_v1.index_build.v2', index=str(destination),
        mode=mode, self_contained=mode == 'copy',
        portability='one HDF5 file' if mode == 'copy' else 'move this index and every declared relative source H5 together',
        source_isaac_process_absent=require_closed_process, source_pid=pid,
        purpose_selection=purpose, membership_sidecar=membership_provenance,
        counts=counts, source_qualification_counts=source_counts,
        included_episode_ids=[row['episode_id'] for row in rows if row['included']],
        excluded_episode_ids=[row['episode_id'] for row in rows if not row['included']],
        episodes=rows, wall_seconds=time.perf_counter() - started,
        index_bytes=destination.stat().st_size,
        index_sha256=digest.hexdigest())
    atomic_text(destination.with_suffix('.index.json'), json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_directory', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--mode', choices=('relative-links', 'copy'), default='relative-links')
    parser.add_argument('--purpose', choices=sorted(PURPOSES) + ['all-completed', 'members'],
                        default='policy_evaluation', help='Explicit usage cohort; independent of reader sample-filter')
    parser.add_argument('--members', type=Path, help='Hash-bound historical purpose/member sidecar')
    args = parser.parse_args(argv)
    print(json.dumps(build_index(args.run_directory, args.output, mode=args.mode,
                                purpose=args.purpose, members=args.members), indent=2))


if __name__ == '__main__':
    main()
