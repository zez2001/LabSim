"""Validate every persisted control record and event against the v1.2 schema."""
import argparse,gzip,json,time
from pathlib import Path
from jsonschema import Draft202012Validator


def audit(directory,schema,output):
    directory,output=Path(directory),Path(output)
    if output.exists():raise FileExistsError(output)
    schema=json.loads(Path(schema).read_text());Draft202012Validator.check_schema(schema)
    def validator(name):return Draft202012Validator({'$schema':schema['$schema'],'$ref':'#/$defs/'+name,'$defs':schema['$defs']})
    errors=[];counts={};start=time.perf_counter()
    for name,definition in [('progress_summary.json','summary'),('progress_config.resolved.json','resolvedConfiguration')]:
        data=json.loads((directory/name).read_text());found=list(validator(definition).iter_errors(data));errors += [dict(file=name,path=list(x.path),message=x.message)for x in found];counts[name]=1
    for name,definition in [('progress_v1.jsonl.gz','transition'),('progress_events.jsonl','event')]:
        count=0;v=validator(definition)
        opener=gzip.open if name.endswith('.gz')else open
        with opener(directory/name,'rt')as stream:
            for line in stream:
                if not line.strip():continue
                data=json.loads(line);count+=1
                errors += [dict(file=name,row=count,path=list(x.path),message=x.message)for x in v.iter_errors(data)]
                if len(errors)>20:raise ValueError(errors)
        counts[name]=count
    s=json.loads((directory/'progress_summary.json').read_text())
    assert counts['progress_events.jsonl']==s['recording']['event_count']
    assert counts['progress_v1.jsonl.gz']==s['recording']['control_transitions']
    value=dict(schema='labsim.Progress_v1_2.schema_validation.v1',source=str(directory.resolve()),counts=counts,errors=errors,passed=not errors,wall_seconds=time.perf_counter()-start)
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
    assert not errors,errors
    return value

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('directory');p.add_argument('--schema',default='docs/lab_cuvette_loading/Progress_v1_2/schema.json');p.add_argument('--output',required=True);a=p.parse_args();print(audit(a.directory,a.schema,a.output))
