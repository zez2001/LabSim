"""Rehash protected original V0 files; never alter a shared result inode."""
import hashlib,json,time
from demos.lab_cuvette_external.geometry import ROOT,DOC,write

def main():
    before=json.loads((DOC/'baseline_before.json').read_text());cache={};changed=[];missing=[];hardlink_changes=[];start=time.monotonic()
    for row in before['files']:
        path=ROOT/row['path']
        if not path.is_file():missing.append(row['path']);continue
        st=path.stat();key=(st.st_dev,st.st_ino)
        if key not in cache:
            h=hashlib.sha256()
            with path.open('rb') as f:
                while data:=f.read(8*1024*1024):h.update(data)
            cache[key]=h.hexdigest()
        if cache[key]!=row['sha256']:changed.append(row['path'])
        if st.st_ino!=row['inode'] or st.st_nlink!=row['nlink']:hardlink_changes.append(row['path'])
    source=json.loads((DOC/'source_manifest.json').read_text());source_bad=[]
    for row in source['files']:
        if hashlib.sha256((ROOT/row['path']).read_bytes()).hexdigest()!=row['sha256']:source_bad.append(row['path'])
    result=dict(protected_files=len(before['files']),unique_inodes=len(cache),changed=changed,missing=missing,old_inode_or_link_count_changes=hardlink_changes,source_content_changes=source_bad,passed=not(changed or missing or hardlink_changes or source_bad),wall_seconds=time.monotonic()-start)
    write(DOC/'baseline_after.json',result);print('V0_PRESERVED',result['passed'],result['protected_files'])
    if not result['passed']:raise SystemExit(1)

if __name__=='__main__':main()
