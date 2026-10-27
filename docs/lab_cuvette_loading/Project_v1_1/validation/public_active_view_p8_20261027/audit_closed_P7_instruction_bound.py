"""Counterfactual P8 instruction bound on actual closed P7 payloads, offline."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo',type=Path,default=Path.cwd())
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--ledger',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(argv)
    repo,source,output=args.repo.resolve(),args.source.resolve(),args.output.resolve()
    if output.exists() or output.is_relative_to(source.parent.parent) or source.parent.parent.is_relative_to(output):
        raise ValueError('New output must be separate from the entire closed source run')
    sys.path.insert(0,str(repo))
    from policy.backends.cubence import input_token_bound,load_config
    from policy.backends.cubence_project_v1_1_active_view import SYSTEM_PROMPT
    from policy.backends.cubence_project_v1_1_side_detail import _closed_source_proof,SYSTEM_PROMPT as P7_PROMPT
    from policy.backends.cubence_project_v1_1_visual_context import reconstruct_input_items
    proof_path=source.parent.parent/'process_exit.json'
    proof=_closed_source_proof(source,proof_path)
    assert proof['runtime_commit']=='9a4713cf8c71bed4d697625ab052b378608780cc'
    tracked={}
    def read(path):
        data=path.read_bytes();tracked[str(path)]=hashlib.sha256(data).hexdigest();return json.loads(data)
    controller=read(source/'controller.json');assert controller['prompt']==P7_PROMPT
    cfg=load_config(repo/'config/lab_cuvette_loading/Project_v1_1/policies/cubence_gpt6_context2_640high_temporal_detail_active_view.json')
    old_cfg=controller['provider_config'];comparable=dict(cfg);comparable.pop('active_view_control');assert comparable==old_cfg
    ledger=read(args.ledger.resolve())
    old_instructions=P7_PROMPT+'\nAction limits: '+json.dumps(cfg['action_limits'])
    new_instructions=SYSTEM_PROMPT+'\nAction limits: '+json.dumps(cfg['action_limits'])
    delta=len(json.dumps(new_instructions,ensure_ascii=False).encode())-len(json.dumps(old_instructions,ensure_ascii=False).encode())
    def payload(items,instructions):
        return dict(model=cfg['model'],input=items,instructions=instructions,
            max_output_tokens=cfg['max_output_tokens'],store=False,
            reasoning={'effort':cfg['reasoning_effort']},tools=controller['tool_schema'],parallel_tool_calls=False)
    rows=[];exact=0;redacted=0
    for folder in sorted((source/'temporal_visual_context').glob('decision_*')):
        path=folder/'input_items_manifest.json';manifest=read(path)
        attempts=[row for row in ledger['attempts'] if row['label']==manifest['request_label']]
        assert attempts and len({row['reservation_input_tokens'] for row in attempts})==1
        original=attempts[0]['reservation_input_tokens'];counterfactual=original+delta
        if manifest['exact_full_input_reconstructable']:
            items=reconstruct_input_items(path)
            assert input_token_bound(payload(items,old_instructions),10**9)==original
            assert input_token_bound(payload(items,new_instructions),10**9)==counterfactual
            exact+=1
        else:
            assert manifest['private_provider_items_redacted'];redacted+=1
        rows.append(dict(decision_index=manifest['decision_index'],request_label=manifest['request_label'],
            original_network_attempts=len(attempts),images=manifest['total_image_count'],
            original_actual_P7_reservation=original,added_serialized_instruction_bytes=delta,
            P8_counterfactual_same_input_bound=counterfactual,margin_to_80000=80000-counterfactual,
            private_items_not_reconstructed=len(manifest['private_provider_items_redacted']),
            original_input_items_SHA256=manifest['full_wire_input_canonical_sha256'],
            original_full_input_reconstructable=manifest['exact_full_input_reconstructable']))
    for path,digest in tracked.items():assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==digest
    assert rows and all(row['P8_counterfactual_same_input_bound']<=80000 for row in rows)
    output.mkdir(parents=True,exist_ok=False)
    summary=dict(schema='labsim.P8.closed_P7_same_input_instruction_bound.v1',API_calls=0,GPU=False,
        source_runtime=proof['runtime_commit'],source_decisions=len(rows),source_network_attempts=sum(row['original_network_attempts'] for row in rows),
        full_original_inputs_independently_rebuilt=exact,redacted_inputs_not_rebuilt=redacted,
        added_serialized_instruction_bytes=delta,
        max_P8_counterfactual_same_input_bound=max(row['P8_counterfactual_same_input_bound'] for row in rows),
        min_margin_to_80000=min(row['margin_to_80000'] for row in rows),rows=rows,source_SHA256=tracked,
        method='The real P7 reservation already includes the original private items. Hold all input_items unchanged and add only the exact serialized instructions string byte difference. Reconstruct public-only cases as an independent check; never infer or reconstruct hidden items.',
        caveats=['Counterfactual on these closed P7 payloads, not actual P8 requests or future response histories.',
            '8192/image plus text-byte sizing is the existing local heuristic, not actual model tokens or billing.',
            'Future larger model outputs/history remain checked by the unchanged client before network/reservation.'])
    (output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    with (output/'bounds.csv').open('w') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    print(json.dumps({key:summary[key] for key in ('source_decisions','source_network_attempts','added_serialized_instruction_bytes','max_P8_counterfactual_same_input_bound','min_margin_to_80000')}))


if __name__=='__main__':main()
