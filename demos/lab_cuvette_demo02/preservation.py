"""Snapshot and verify old experiment files without modifying any old result."""
import argparse
import hashlib
import json
from pathlib import Path
import time

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'outputs/lab_cuvette_loading/V0_demo02'


def files():
    scopes = ['demos/lab_cuvette_loading', 'demos/lab_cuvette_external',
              'demos/lab_cuvette_ext02', 'demos/lab_cuvette_demo01',
              'assets/lab_cuvette_loading', 'config/lab_cuvette_loading',
              'docs/lab_cuvette_loading', 'docs/series_20261019',
              'outputs/lab_cuvette_loading']
    return sorted({p for name in scopes for p in (ROOT/name).rglob('*')
                   if p.is_file() and '__pycache__' not in p.parts
                   and 'V0_demo02' not in p.parts})


def fingerprint(paths):
    cache, records = {}, {}
    for p in paths:
        if not p.exists():
            continue
        st = p.stat()
        key = (st.st_dev, st.st_ino)
        if key not in cache:
            h = hashlib.sha256()
            with p.open('rb') as f:
                for block in iter(lambda: f.read(8*1024*1024), b''):
                    h.update(block)
            cache[key] = h.hexdigest()
        records[str(p.relative_to(ROOT))] = dict(sha256=cache[key], size=st.st_size,
                                                inode=st.st_ino, nlink=st.st_nlink)
    return records


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['snapshot', 'verify'])
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    dest = OUT / ('preservation_before.json' if args.mode == 'snapshot' else 'preservation_after.json')
    if dest.exists():
        raise FileExistsError(dest)
    start = time.monotonic()
    if args.mode == 'snapshot':
        result = fingerprint(files())
    else:
        before = json.loads((OUT/'preservation_before.json').read_text())
        after = fingerprint([ROOT/name for name in before])
        missing = sorted(set(before)-set(after))
        changed = [name for name in after if any(before[name][k] != after[name][k] for k in ['sha256', 'size'])]
        inode_changes = [name for name in after if any(before[name][k] != after[name][k] for k in ['inode', 'nlink'])]
        result = dict(protected_files=len(before), missing=missing, changed=changed,
                      inode_changes=inode_changes, passed=not(missing or changed or inode_changes),
                      wall_seconds=time.monotonic()-start)
    dest.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    print(args.mode, len(result) if args.mode == 'snapshot' else result, flush=True)


if __name__ == '__main__':
    main()
