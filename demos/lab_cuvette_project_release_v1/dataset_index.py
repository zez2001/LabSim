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


def build_index(run_directory, destination, *, mode='relative-links', require_closed_process=True):
    run, destination = Path(run_directory).resolve(), Path(destination).resolve()
    if mode not in {'copy', 'relative-links'}:
        raise ValueError('Index mode must be copy or relative-links')
    manifest = json.loads((run / 'run_manifest.json').read_text())
    pid = int(manifest['process_id'])
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
    started = time.perf_counter()
    try:
        with h5py.File(temporary, 'x') as index:
            index.attrs.update(schema_version='labsim.Project_release_v1.index.v1',
                index_mode=mode, complete=False,
                self_contained=(mode == 'copy'), external_links_relative=(mode == 'relative-links'))
            for source in sorted(run.glob('episode_*/dataset/episode_*.h5')):
                with h5py.File(source) as episode:
                    identity = str(episode.attrs['episode_id'])
                    if identity in identities:
                        raise ValueError('Duplicate episode identity in source cohort')
                    identities.add(identity)
                    filters = {name: episode_matches_filter(episode.attrs, name)[0]
                               for name in ('success', 'failure', 'all_valid')}
                    complete = bool(episode.attrs.get('complete', False)) and episode.attrs.get('publication_state') == 'complete'
                    row = dict(episode_id=identity, source=os.path.relpath(source, destination.parent),
                        source_bytes=source.stat().st_size, complete=complete,
                        task_success=bool(episode.attrs.get('task_success')) if episode.attrs.get('task_success_known') else None,
                        failure_type=str(episode.attrs.get('failure_type', 'UNKNOWN')), filters=filters)
                    rows.append(row)
                    if not complete:
                        counts['incomplete'] += 1
                        continue
                    for name, accepted in filters.items():
                        counts[name] += int(accepted)
                    # The index contains every completed record. Existing reader
                    # filters choose qualification; no score or success is changed.
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
    result = dict(schema='labsim.Project_release_v1.index_build.v1', index=str(destination),
        mode=mode, self_contained=mode == 'copy',
        portability='one HDF5 file' if mode == 'copy' else 'move this index and every declared relative source H5 together',
        source_isaac_process_absent=require_closed_process, source_pid=pid,
        counts=counts, episodes=rows, wall_seconds=time.perf_counter() - started,
        index_bytes=destination.stat().st_size,
        index_sha256=digest.hexdigest())
    atomic_text(destination.with_suffix('.index.json'), json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_directory', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--mode', choices=('relative-links', 'copy'), default='relative-links')
    args = parser.parse_args(argv)
    print(json.dumps(build_index(args.run_directory, args.output, mode=args.mode), indent=2))


if __name__ == '__main__':
    main()
