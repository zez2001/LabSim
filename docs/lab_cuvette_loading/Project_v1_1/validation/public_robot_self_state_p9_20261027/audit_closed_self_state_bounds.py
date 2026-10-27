"""Offline P9 bound delta on closed public GPT06/07; private items not recovered."""
import argparse
import base64
import copy
import csv
import hashlib
import json
from pathlib import Path
import sys


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--repo',type=Path,default=Path.cwd());p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    repo=a.repo.resolve();output=a.output.resolve();assert not output.exists();sys.path.insert(0,str(repo))
    from policy.backends.cubence import input_token_bound,canonical_hash
    from policy.backends.cubence_project_v1_1_self_state import SYSTEM_PROMPT,DEFAULT_PROFILE
    from policy.backends.cubence_project_v1_1_visual_context import reconstruct_input_items
    from policy.backends.cubence_project_v1_1_side_detail import _closed_source_proof
    from policy.robot_self_kinematics import derive_robot_self_state
    cfg=json.loads(DEFAULT_PROFILE.read_text());ledger=json.loads((repo/'outputs/lab_cuvette_loading/Project_v1/cubence_budget.json').read_text())
    tracked={};rows=[];summaries=[]
    def read(path):
        raw=path.read_bytes();tracked[str(path.relative_to(repo))]=hashlib.sha256(raw).hexdigest();return json.loads(raw)
    for name,commit in [('gpt_debug_06','9a4713cf8c71bed4d697625ab052b378608780cc'),('gpt_debug_07','42264193cc7fea92b467e14d29f28e7a05ba421f')]:
        source=repo/'outputs/lab_cuvette_loading/Project_v1_1'/name/'episode_0000/gpt_control'
        proof=_closed_source_proof(source,source.parent.parent/'process_exit.json');assert proof['runtime_commit']==commit
        controller=read(source/'controller.json');oldcfg=controller['provider_config']
        comparable=copy.deepcopy(cfg);comparable.pop('robot_self_state')
        if name.endswith('06'):comparable.pop('active_view_control')
        assert comparable==oldcfg
        old_instructions=controller['prompt']+'\nAction limits: '+json.dumps(cfg['action_limits'])
        new_instructions=SYSTEM_PROMPT+'\nAction limits: '+json.dumps(cfg['action_limits'])
        instruction_delta=len(json.dumps(new_instructions,ensure_ascii=False).encode())-len(json.dumps(old_instructions,ensure_ascii=False).encode())
        def payload(items,instructions):
            return dict(model=cfg['model'],input=items,instructions=instructions,max_output_tokens=cfg['max_output_tokens'],store=False,
                reasoning={'effort':cfg['reasoning_effort']},tools=controller['tool_schema'],parallel_tool_calls=False)
        local=[];full=0;redacted=0
        for folder in sorted((source/'temporal_visual_context').glob('decision_*')):
            path=folder/'input_items_manifest.json';manifest=read(path)
            current=read(source/'observations'/folder.name/'public_observation.json')
            selfstate=derive_robot_self_state(current['joint_positions'][:7],current['TCPpose'],episode_id=current['episode_id'],
                observation_id=current['observation_id'],simulation_time=current['simulation_time'])
            group=dict(role='user',content=[dict(type='input_text',text='CURRENT ROBOT SELF-STATE\n'+json.dumps(selfstate,ensure_ascii=False,separators=(',',':'),allow_nan=False))])
            # A top-level array element adds its serialization and one ', ' separator.
            own_delta=len(json.dumps(group,ensure_ascii=False).encode())+2
            entries=[row for row in ledger['attempts'] if row['label']==manifest['request_label']]
            assert entries and len({r['reservation_input_tokens'] for r in entries})==1
            original=entries[0]['reservation_input_tokens'];bound=original+instruction_delta+own_delta
            if manifest['exact_full_input_reconstructable']:
                items=reconstruct_input_items(path);assert input_token_bound(payload(items,old_instructions),10**9)==original
                items.insert(len(items)-1,group);assert input_token_bound(payload(items,new_instructions),10**9)==bound;full+=1
            else:
                assert manifest['private_provider_items_redacted'];redacted+=1
            row=dict(source_run=name,decision_index=manifest['decision_index'],request_label=manifest['request_label'],original_network_attempts=len(entries),
                original_input_bound=original,extra_serialized_instruction_bytes=instruction_delta,extra_serialized_current_robot_group_bytes=own_delta,
                P9_same_old_history_bound=bound,margin_to_80000=80000-bound,full_original_reconstructed=manifest['exact_full_input_reconstructable'],
                private_items_not_reconstructed=len(manifest['private_provider_items_redacted']))
            rows.append(row);local.append(row)
        summaries.append(dict(source_run=name,runtime=commit,source_decisions=len(local),network_attempts=sum(r['original_network_attempts'] for r in local),
            full_original_inputs_independently_rebuilt=full,private_item_inputs_not_rebuilt=redacted,
            max_P9_same_old_history_bound=max(r['P9_same_old_history_bound'] for r in local),minimum_margin=min(r['margin_to_80000'] for r in local)))
    for name,digest in tracked.items():assert hashlib.sha256((repo/name).read_bytes()).hexdigest()==digest
    assert all(r['P9_same_old_history_bound']<=80000 for r in rows)
    output.mkdir(parents=True)
    result=dict(schema='labsim.P9.closed_06_07.same_old_history_bound.v1',API_calls=0,GPU=False,source_summary=summaries,
        max_bound=max(r['P9_same_old_history_bound'] for r in rows),minimum_margin=min(r['margin_to_80000'] for r in rows),rows=rows,source_SHA256=tracked,
        method='Hold original input_items including private live items fixed; use original real ledger reservation plus exact serialized current group/instruction byte deltas. Public-only cases independently rebuilt. Private bytes/hashes are not recovered.',
        caveats=['Counterfactual closed histories, not actual P9 requests or future memory.','Original heuristic reserves8192/image and one text byte/token; not actual tokenizer/cost/accuracy.',
            'Future P9 tool response history can differ; unchanged client remains fail-closed at80k/$30/1500 before HTTP.'])
    (output/'summary.json').write_text(json.dumps(result,indent=2)+'\n')
    with (output/'bounds.csv').open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    print(json.dumps({k:result[k] for k in ['source_summary','max_bound','minimum_margin']}))


if __name__=='__main__':main()
