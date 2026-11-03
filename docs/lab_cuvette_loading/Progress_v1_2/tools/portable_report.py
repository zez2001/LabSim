"""Portable v1.2 results: genuine H264 copies and lossless sidecar recompression.

Original source files remain unchanged. Only gzip compression level changes;
all decompressed JSONL bytes are verified identical and source hashes retained.
"""
import argparse,gzip,hashlib,importlib.util,json,os,sys,time
from pathlib import Path


def digest(path,decoded=False):
    h=hashlib.sha256();opener=gzip.open if decoded else open
    with opener(path,'rb')as f:
        for b in iter(lambda:f.read(8<<20),b''):h.update(b)
    return h.hexdigest()


def prepare(progress,episode,output):
    helper=Path(__file__).resolve().parents[2]/'Progress_v1/tools/portable_report.py'
    spec=importlib.util.spec_from_file_location('legacy_portable',helper)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    start=time.perf_counter();receipt=module.prepare(progress,episode,output)
    source=Path(progress)/'progress_v1.jsonl.gz';target=Path(output)/source.name;temporary=target.with_suffix('.tmp')
    source_digest=digest(source);payload_digest=digest(source,True)
    with gzip.open(source,'rb')as incoming,temporary.open('xb')as raw:
        with gzip.GzipFile(filename='',fileobj=raw,mode='wb',compresslevel=9,mtime=0)as outgoing:
            for block in iter(lambda:incoming.read(8<<20),b''):outgoing.write(block)
    if digest(temporary,True)!=payload_digest:raise RuntimeError('Decoded JSONL changed during portable recompression')
    os.replace(temporary,target)
    assert digest(source)==source_digest
    for item in receipt['sidecars']:
        if item['path']==source.name:
            item.update(bytes=target.stat().st_size,sha256=digest(target),unchanged_copy=False,
                source_sha256=source_digest,source_bytes=source.stat().st_size,
                decoded_jsonl_sha256=payload_digest,decoded_bytes_identical=True,
                representation='gzip level 9 display/transfer copy; all original JSONL bytes retained')
    # Build the current presentation from the copied scalar sidecars. Keep the
    # source analysis HTML and source recordings unchanged, even when that HTML
    # was produced by an earlier presentation revision of the same evaluator.
    root=Path(__file__).resolve().parents[4]
    sys.path.insert(0,str(root))
    from demos.lab_cuvette_progress_v1.report import generate_report,REPORT_VERSION
    report=generate_report(output,episode)
    marker='<script type="application/json" id="data">'
    prefix,tail=report.read_text().split(marker,1);payload,ending=tail.split('</script>',1)
    data=json.loads(payload)
    data['videos']=[dict(name=m['camera']+' · H264显示副本',src=m['display_copy'],
        source_sha256=m['source_sha256'],display_sha256=m['display_sha256'])for m in receipt['media']]
    payload=json.dumps(data,ensure_ascii=False,separators=(',',':')).replace('<','\\u003c')
    report.write_text(prefix+marker+payload+'</script>'+ending)
    receipt.update(report_version=REPORT_VERSION,presentation_source_sha256=digest(root/'demos/lab_cuvette_progress_v1/report.py'),
        report_bytes=report.stat().st_size,report_sha256=digest(report),source_analysis_html_unchanged=True)
    receipt.update(schema='labsim.Progress_v1_2.portable_report.v1',wall_seconds=time.perf_counter()-start,
        package_bytes_excluding_receipt=sum(p.stat().st_size for p in Path(output).rglob('*')if p.is_file() and p.name!='portable_media_receipt.json'))
    (Path(output)/'portable_media_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
    return receipt

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--progress',required=True);p.add_argument('--episode',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    r=prepare(a.progress,a.episode,a.output);print(json.dumps({'output':a.output,'bytes':r['package_bytes_excluding_receipt'],'wall_seconds':r['wall_seconds']},indent=2))
