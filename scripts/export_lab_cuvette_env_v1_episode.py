"""Copy one closed Env_v1 record for normal dataset reading on another machine.

This is a native HDF5/media export, without action conversion, resampling,
training-platform conversion or changes to independent outcome labels.
"""
from __future__ import annotations
import argparse,hashlib,json,shutil,sys
from pathlib import Path
import h5py

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from scripts.actual_episode_inspect import plain,scan_links
from scripts.read_lab_cuvette_env_v1_data import inspect as normal_read


def sha256(path):
    value=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):value.update(chunk)
    return value.hexdigest()


def export_portable_episode(source,destination,*,validate_reader=True):
    source,destination=Path(source).resolve(),Path(destination).resolve()
    source_h5=source/'dataset/episode_0000.h5'
    if not source_h5.is_file():raise FileNotFoundError(source_h5)
    if source==destination or source in destination.parents:
        raise ValueError('Export must be a separate directory outside the source episode')
    with h5py.File(source_h5,'r') as h:
        if not bool(h.attrs.get('complete',False)):raise ValueError('Only a closed complete episode may be exported')
        dependencies=scan_links(h)
        if dependencies:raise ValueError('Source has external HDF5 dependencies; refusing to copy them silently: '+str(dependencies))
        labels={k:plain(h.attrs.get(k)) for k in ('episode_id','scene_version','task_type','complete','record_valid','task_success',
            'failure_type','termination_reason','eligible_for_success_bc','eligible_for_failure_analysis','real_calibrated')}
        semantics={k:plain(h.attrs.get(k)) for k in ('action_semantics','legacy_8d_mapping','executed_action_semantics','observation_alignment','control_hz','physics_hz')}
        transitions=len(h['actions'])
    destination.mkdir(parents=True,exist_ok=False)
    candidates=[source_h5]
    candidates += sorted(p for p in source.iterdir() if p.is_file() and (p.suffix in ('.json','.yaml','.yml','.jsonl','.mp4','.png') or p.name.endswith('.jsonl.gz')))
    candidates += sorted((source/'video').glob('*.mp4'))
    candidates += sorted((source/'dataset/meta').glob('*.jsonl'))
    files=[]
    for path in candidates:
        relative=path.relative_to(source);target=destination/relative;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(path,target)
        source_hash=sha256(path);copied_hash=sha256(target)
        if source_hash!=copied_hash:raise RuntimeError('Copy hash mismatch: '+str(relative))
        files.append(dict(path=relative.as_posix(),bytes=target.stat().st_size,sha256=copied_hash,source_sha256=source_hash))
    copied_h5=destination/source_h5.relative_to(source)
    with h5py.File(copied_h5,'r') as h:
        copied_dependencies=scan_links(h)
        if copied_dependencies:raise RuntimeError('Export unexpectedly contains HDF5 external links')
    reader={}
    if validate_reader:
        for policy,nobs in (('act',1),('dp',3)):
            reader[policy]=normal_read(copied_h5,'all_valid',policy,16,nobs)
    manifest=dict(schema='labsim.Env_v1.portable_native_episode.v1',source_episode_provenance=str(source),
        episode_id=labels['episode_id'],labels=labels,transitions=transitions,semantics=semantics,files=files,
        original_HDF5_bytes_preserved=True,HDF5_external_dependencies=copied_dependencies,
        data_reading_requires_original_machine=False,
        source_absolute_strings='Provenance/configuration strings may retain original paths; HDF5 observations and actions do not dereference them.',
        scope='Native recorded episode and present media/config/diagnostic sidecars. Simulation environment, source assets, model weights and Python runtime are not bundled.',
        conversion=dict(action_semantics_changed=False,frame_rate_changed=False,labels_changed=False,training_platform_conversion=False),
        normal_reader_validation=reader,
        reader_command='python scripts/read_lab_cuvette_env_v1_data.py PORTABLE_DIR/dataset/episode_0000.h5 --sample-filter all_valid --policy-type act',
        task_scope='Use recorded task_type/independent labels. Diagnostic records are not full-loading success/failure training quota.')
    with (destination/'portable_manifest.json').open('x') as stream:json.dump(plain(manifest),stream,ensure_ascii=False,indent=2,allow_nan=False);stream.write('\n')
    return manifest


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('episode',help='Closed source episode directory')
    parser.add_argument('--output',required=True,help='New destination directory; never overwritten')
    parser.add_argument('--manifest-copy',help='Optional separate evidence JSON path, also never overwritten')
    parser.add_argument('--skip-reader-validation',action='store_true',help='Copy and hash only, for records intentionally excluded by all_valid')
    args=parser.parse_args()
    evidence=Path(args.manifest_copy) if args.manifest_copy else None
    if evidence is not None and evidence.exists():raise FileExistsError(evidence)
    manifest=export_portable_episode(args.episode,args.output,validate_reader=not args.skip_reader_validation)
    if evidence is not None:
        evidence.parent.mkdir(parents=True,exist_ok=True)
        with evidence.open('x') as stream:json.dump(plain(manifest),stream,ensure_ascii=False,indent=2,allow_nan=False);stream.write('\n')
    print(json.dumps(dict(output=str(Path(args.output).resolve()),files=len(manifest['files']),
        total_bytes=sum(f['bytes'] for f in manifest['files']),labels=manifest['labels'],
        original_HDF5_bytes_preserved=True,HDF5_external_dependencies=manifest['HDF5_external_dependencies'],
        normal_reader_validation=list(manifest['normal_reader_validation'])),ensure_ascii=False,indent=2))

if __name__=='__main__':main()
