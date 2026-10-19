"""Read-only SHA256 and hardlink/inode verification against pre-run inventory."""
import json,hashlib,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def verify():
 start=time.monotonic();before=json.loads((ROOT/'outputs/lab_cuvette_loading/V0_ext02/preservation_before.json').read_text());cache={};changed=[];missing=[];inode_changes=[]
 for path,row in before.items():
  f=ROOT/path
  if not f.exists():missing.append(path);continue
  st=f.stat();key=(st.st_dev,st.st_ino)
  if key not in cache:
   h=hashlib.sha256()
   with f.open('rb') as fp:
    for b in iter(lambda:fp.read(8*1024*1024),b''):h.update(b)
   cache[key]=h.hexdigest()
  if row['sha256']!=cache[key] or row['size']!=st.st_size:changed.append(path)
  if row['inode']!=st.st_ino or row['nlink']!=st.st_nlink:inode_changes.append(path)
 result=dict(protected_files=len(before),unique_inodes=len(cache),changed=changed,missing=missing,inode_or_link_count_changes=inode_changes,passed=not(changed or missing or inode_changes),wall_seconds=time.monotonic()-start)
 dest=ROOT/'outputs/lab_cuvette_loading/V0_ext02/preservation_after.json';dest.write_text(json.dumps(result,indent=2));print(result)
if __name__=='__main__':verify()
