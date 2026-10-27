"""Small supplemental audit of closed publication authority, preserving raw scores."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import shutil
import h5py
import numpy as np

R=Path('/home/wujing/Desktop/vla/LabSim')
S=R/'outputs/lab_cuvette_loading/Project_release_v1/termination_cases_01'
O=R/'docs/lab_cuvette_loading/Project_release_v1/validation/termination_cases_01_closed'
checks=[];rows=[];sources=[]
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def ck(name,ok,**x):checks.append(dict(name=name,passed=bool(ok),**x))
def plain(x):
 if isinstance(x,np.generic):return x.item()
 if isinstance(x,bytes):return x.decode()
 return x
for i in range(5):
 e=S/f'episode_{i:04d}';hp=e/'dataset/episode_0000.h5'
 before=sha(hp)
 result=json.loads((e/'result.json').read_text())
 rawscore=json.loads((e/'independent_score.json').read_text())
 collector=json.loads((e/'episode_0000_result.json').read_text())
 marker=json.loads((e/'episode_0000_complete.json').read_text())
 index=json.loads((e/'dataset/meta/episode.jsonl').read_text().strip())
 with h5py.File(hp,'r') as f:
  attrs={k:plain(f.attrs[k]) for k in ['episode_id','finalization_id','task_success','record_valid',
    'record_integrity_valid','eligibility_pending_collector_integrity','publication_state','complete',
    'failure_type','failure_domain','termination_reason','eligible_for_success_bc','eligible_for_failure_analysis']}
  if attrs['task_success']=='unknown':attrs['task_success']=None
  props=json.loads(f['task_properties'][()])
  qual=json.loads(f['qualification_json'][()])
  task=json.loads(f['task_result_json'][()])
  embedded=json.loads(f['independent_score_json'][()])
  ck(f'episode{i}.task_properties_matches_collector_blob',props==collector)
  authority={'H5_attrs':attrs,'task_properties_labels':props['labels'],
             'collector_result_labels':collector['labels'],'index_labels':index['labels'],
             'final_result':result}
  fields=['finalization_id','task_success','record_valid','record_integrity_valid',
          'eligibility_pending_collector_integrity','publication_state','complete','failure_type',
          'failure_domain','termination_reason','eligible_for_success_bc','eligible_for_failure_analysis']
  mismatches=[dict(object=name,field=k,actual=obj.get(k),expected=result.get(k))
              for name,obj in authority.items() for k in fields if obj.get(k)!=result.get(k)]
  ck(f'episode{i}.all_publication_authorities_semantically_equal',not mismatches,mismatches=mismatches)
  ck(f'episode{i}.marker_transaction_binding', marker['finalization_id']==result['finalization_id']==
     props['finalization_id']==index['finalization_id'] and marker['episode_id']==result['episode_id'])
  ck(f'episode{i}.task_result_equality',task==result['task_result']==props['labels']['task_result']==
     collector['labels']['task_result']==index['labels']['task_result']==qual['task_result'])
  qualfields=['record_integrity_valid','eligibility_pending_collector_integrity','failure_domain',
              'record_integrity_errors','physics_trustworthy','physics_trust_scope',
              'success_bc_eligible','trajectory_analysis_eligible']
  qm=[dict(field=k,actual=qual.get(k),expected=result.get(k)) for k in qualfields
      if qual.get(k)!=result.get(k)]
  ck(f'episode{i}.qualification_matches_final_fields',not qm,mismatches=qm)
  verdicts=['task_success','record_valid','failure_type','failure_domain','termination_reason',
            'eligible_for_success_bc','eligible_for_failure_analysis']
  vm=[dict(object=name,field=k,actual=obj.get(k),expected=result.get(k)) for name,obj in
      [('raw_independent_score',rawscore),('embedded_independent_score',embedded),('collector_result_snapshot',collector['result'])]
      for k in verdicts if obj.get(k)!=result.get(k)]
  ck(f'episode{i}.pre_close_physical_verdict_compatible',not vm,mismatches=vm)
  rows.append(dict(episode_index=i,episode_id=result['episode_id'],finalization_id=result['finalization_id'],
       authoritative_task_success=result['task_success'],authoritative_record_valid=result['record_valid'],
       authoritative_record_integrity_valid=result['record_integrity_valid'],
       authoritative_eligibility_pending=result['eligibility_pending_collector_integrity'],
       pre_close_scores={name:dict(record_integrity_valid=obj.get('record_integrity_valid'),
          eligibility_pending_collector_integrity=obj.get('eligibility_pending_collector_integrity'),
          schema=obj.get('schema')) for name,obj in [('external',rawscore),('embedded',embedded),
                                                   ('collector_result_snapshot',collector['result'])]},
       qualification_schema=qual['schema'],marker_schema=marker['schema']))
 after=sha(hp);sources.append(dict(path=str(hp),sha256_before=before,sha256_after=after,unchanged=before==after))
 ck(f'episode{i}.H5_unchanged',before==after)
receipt=dict(schema='labsim.Project_release_v1.termination_authority_audit.v1',
  created_utc=datetime.now(timezone.utc).isoformat(),all_checks_passed=all(x['passed'] for x in checks),
  check_count=len(checks),checks=checks,episodes=rows,sources=sources,
  authority_definition='Final attrs, task_properties.labels, qualification_json, task_result_json, collector-result labels, final result, marker and index; compare corresponding semantic fields, not all JSON bytes.',
  raw_snapshot_definition='Original independent_score.json, H5 independent_score_json and collector-result result subtree are physical score snapshots from before collector-close integrity confirmation. Integrity null/pending=true is intentional and retained. Their physical task verdicts remain compatible with final labels.',
  historical_evidence_modified=False)
(O/'authoritative_fields_addendum.json').write_text(json.dumps(receipt,indent=2)+'\n')
shutil.copyfile(__file__,O/'authoritative_fields_audit.py')
with (O/'README.md').open('a') as f:f.write('\n`authoritative_fields_addendum.json` additionally checks all final H5 task-properties/qualification/task-result publication layers against external labels and preserves pre-close physical-score snapshots unchanged.\n')
manifest=[dict(path=str(p.relative_to(O)),bytes=p.stat().st_size,sha256=sha(p))
 for p in sorted(O.iterdir()) if p.is_file() and p.name!='evidence_manifest.json']
(O/'evidence_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps(dict(all_checks_passed=receipt['all_checks_passed'],check_count=len(checks),
 failed_checks=[x for x in checks if not x['passed']],sha256=sha(O/'authoritative_fields_addendum.json'))))
