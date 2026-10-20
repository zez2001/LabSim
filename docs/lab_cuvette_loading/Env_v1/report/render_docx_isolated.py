#!/usr/bin/env python3
"""Run unchanged Codex bundled renderer in an existing modern-glibc Docker image.
No install, runtime edit, system-LibreOffice fallback, network, or GPU access.
The input and bundle are read-only; only a chosen QA directory is writable.
"""
import argparse, json, os, subprocess, sys
from pathlib import Path

DEPS=Path('/home/wujing/.cache/codex-runtimes/codex-primary-runtime/dependencies')
SKILL=Path('/home/wujing/.codex/plugins/cache/openai-primary-runtime/documents/26.1015.12040/skills/documents')
IMAGE='47442d7252b7'
EXCLUDE={'libc.so.6','libm.so.6','libpthread.so.0','libdl.so.2','librt.so.1','libresolv.so.2','libstdc++.so.6','libgcc_s.so.1','ld-linux-x86-64.so.2'}
p=argparse.ArgumentParser()
p.add_argument('input',type=Path)
p.add_argument('--output-dir',type=Path,required=True)
p.add_argument('--emit-pdf',action='store_true')
p.add_argument('--verbose',action='store_true')
a=p.parse_args(); source=a.input.resolve(strict=True); out=a.output_dir.resolve()
if source.suffix.lower()!='.docx':p.error('input must be DOCX')
if out==source.parent or source.parent in out.parents:p.error('use a separate QA output directory outside input parent')
out.mkdir(parents=True,exist_ok=True)
names=['libsoftokn3.so','libfreebl3.so','libfreeblpriv3.so','libnssdbm3.so','libnssckbi.so','libsqlite3.so.0','libssl3.so','libnss3.so','libnspr4.so','libcurl.so.4','libsmime3.so','libplc4.so','liblcms2.so.2','libfontconfig.so.1','libfreetype.so.6','libpixman-1.so.0']; found={}; pending=list(names)
while pending:
 name=pending.pop()
 if name in found or name in EXCLUDE:continue
 loc=Path('/usr/lib/x86_64-linux-gnu')/name
 if not loc.exists():loc=Path('/usr/lib/x86_64-linux-gnu/nss')/name
 if not loc.exists():raise RuntimeError('missing existing host dependency '+name)
 found[name]=str(loc)
 for line in subprocess.check_output(['ldd',str(loc)],text=True).splitlines():
  bits=line.strip().split()
  if len(bits)>=3 and bits[1]=='=>' and bits[2].startswith('/'):pending.append(bits[0])
args=['docker','run','--rm','--read-only','--network','none','--tmpfs','/tmp','--user',f'{os.getuid()}:{os.getgid()}','--env','HOME=/tmp','--env','SAL_USE_VCLPLUGIN=svp','--env','LD_LIBRARY_PATH=/compat']
for loc in [DEPS,SKILL,source.parent,Path('/usr/share/fonts'),Path('/etc/fonts')]:
 args+=['--mount',f'type=bind,src={loc},dst={loc},readonly']
args+=['--mount',f'type=bind,src={out},dst={out}']
for name,loc in sorted(found.items()):args+=['--mount',f'type=bind,src={loc},dst=/compat/{name},readonly']
args+=['--entrypoint',str(DEPS/'python/bin/python3'),IMAGE,str(SKILL/'render_docx.py'),str(source),'--output_dir',str(out)]
if a.emit_pdf:args+=['--emit_pdf']
if a.verbose:args+=['--verbose']
print(json.dumps({'image':IMAGE,'host_compat_non_glibc_libraries':len(found),'bundled_renderer':str(SKILL/'render_docx.py'),'bundled_python':str(DEPS/'python/bin/python3'),'input_read_only':str(source),'qa_output':str(out),'network':'none','runtime_modified':False},ensure_ascii=False),flush=True)
raise SystemExit(subprocess.call(args))
