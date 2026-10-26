"""Preview or explicitly send one observation-only QA over closed public frames.

Default is offline. There is no environment, robot action, H5, raw physics,
private task data, or task-success label in this diagnostic.
"""
from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import json
from pathlib import Path
import shutil
import time

from policy.backends.cubence import BudgetLedger, CubenceClient, ProviderError, canonical_hash, load_config, response_text
from policy.backends.cubence_project_v1_1_visual_context import (
    PublicTemporalVisualClient, _public_snapshot, reconstruct_input_items, validate_visual_context)

ROOT=Path(__file__).resolve().parents[2]
DEFAULT_PROFILE=ROOT/'config/lab_cuvette_loading/Project_v1_1/policies/cubence_gpt6_context4_640high_temporal.json'
DEFAULT_LEDGER=ROOT/'outputs/lab_cuvette_loading/Project_v1/cubence_budget.json'
QA_INSTRUCTIONS='''This is an observation-only retrospective diagnostic over already closed public snapshots. No simulator or tools are available. Return no tool call, execute no action, assign no task/grasp success, and infer no hidden object state. The labelled historical references are stale. The first public bilateral-contact reference is not verified grasp, support, insertion, or a 3D object pose.
Compare CURRENT with the previous wrist image, and separately with the first public bilateral-contact wrist reference. Is a change in vessel mouth/top edge relative to the black finger pads and intended seat rim visually discernible? Describe its direction as upward/downward/no discernible change/uncertain and identify the visible features supporting that assessment. Account for perspective, tilt and occlusion. Same-pixel overlap is not three-dimensional insertion.
Is there sufficient visible/public evidence that the vessel bottom is independently supported or that free passage has been established? Answer established/not established/uncertain with visible evidence or missing information. Finger contact and a robot endpoint alone do not establish bottom support. Do not output world object coordinates, numerical insertion depth, unobserved contact events, or success labels.
Return concise JSON containing relative_change_vs_previous, relative_change_vs_contact_reference, visual_evidence, free_passage_evidence, bottom_support_evidence, uncertainty_and_missing_view. This is not a robot control request or a full-task evaluation.'''


def _sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def _read(path):return json.loads(Path(path).read_text())
def _write(path,value):Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')


class _OfflineCapture:
    """Only prepares input; None is not a fabricated model response."""
    def __init__(self,cfg):self.cfg=copy.deepcopy(cfg);self.ledger=None;self.last_input=None;self.calls=0
    def responses(self,items,**kwargs):
        self.last_input=copy.deepcopy(items);self.calls+=1
        return None


def prepare(args):
    source=args.source.resolve();output=args.output.resolve()
    if output.exists():raise FileExistsError('Refusing to overwrite QA output: '+str(output))
    if output.is_relative_to(source) or source.is_relative_to(output):
        raise ValueError('QA output must be separate from source public files')
    cfg=load_config(args.provider_config);validate_visual_context(cfg)
    if 'visual_context' not in cfg:raise ValueError('Use the explicit temporal profile')
    proof=args.source_process_proof or source.parent.parent/'process_exit.json'
    closed=_read(proof)
    if closed.get('process_exited') is not True or closed.get('exit_code')!=0:
        raise ValueError('Source process must actually be closed with its saved exit proof')
    pid=closed.get('pid')
    if not isinstance(pid,int) or pid<=0 or (Path('/proc')/str(pid)).exists():
        raise ValueError('Source process still exists or PID proof is unavailable')
    if args.current_decision<1:raise ValueError('Current decision must have a public predecessor')
    before={str(Path(proof).resolve()):_sha(proof)};snapshots=[];episode=None
    for index in range(args.current_decision+1):
        folder=source/'observations'/f'decision_{index:06d}'
        state_path=folder/'public_observation.json';manifest_path=folder/'manifest.json'
        state_text=state_path.read_text();state=json.loads(state_text);manifest=_read(manifest_path)
        if episode is None:episode=state.get('episode_id')
        if state.get('episode_id')!=episode:raise ValueError('Closed prefix must stay in one episode')
        label=manifest.get('request_label')
        if not isinstance(label,str) or manifest.get('decision_index')!=index:
            raise ValueError('Source decision provenance does not match directory')
        if manifest['public_observation']['sha256']!=_sha(state_path):raise ValueError('Source public JSON SHA mismatch')
        contents=[dict(type='input_text',text=state_text)]
        files=[state_path,manifest_path]
        for name in ('side_camera','wrist_camera'):
            image=folder/(name+'.jpg');data=image.read_bytes();row=next(r for r in manifest['images'] if r['camera_name']==name)
            if row['sha256']!=_sha(image):raise ValueError('Source exact JPEG SHA mismatch')
            contents.extend([dict(type='input_text',text='Synchronized RGB: '+name),
                dict(type='input_image',image_url='data:image/jpeg;base64,'+base64.b64encode(data).decode('ascii'),
                     detail=state['model_image_transforms'][name]['detail'])]);files.append(image)
        _public_snapshot(contents,index,label)  # Same strict public/finite/JPEG validation as normal adapter.
        before.update({str(p.resolve()):_sha(p) for p in files})
        snapshots.append((index,folder,contents,label))
    output.mkdir(parents=True,exist_ok=False)
    offline=output/'offline_preparation';capture=_OfflineCapture(cfg)
    wrapper=PublicTemporalVisualClient(capture,offline);seeds=[]
    for index,folder,contents,label in snapshots:
        target=offline/'observations'/f'decision_{index:06d}';target.mkdir(parents=True)
        for name in ('public_observation.json','manifest.json','side_camera.jpg','wrist_camera.jpg'):
            shutil.copy2(folder/name,target/name)
        # The neutral question lives only in instructions. CURRENT stays last,
        # preceded only by the same helper's explicitly historical references.
        items=[dict(role='user',content=contents)]
        wrapper.responses(items,instructions=QA_INSTRUCTIONS,tools=None,label=label)
        packet=offline/'temporal_visual_context'/f'decision_{index:06d}'
        for name in ('input_items_manifest.json','call_outcome.json'):
            record=_read(packet/name);record.update(api_sent=False,offline_seed=True,
                delegate_kind='offline_capture_only',model_response_generated=False)
            _write(packet/name,record)
        seed=dict(decision_index=index,source_request_label=label,api_sent=False,
            offline_seed=True,model_response_generated=False)
        _write(packet/'offline_seed.json',seed);seeds.append(seed)
    final=offline/'temporal_visual_context'/f'decision_{args.current_decision:06d}'/'input_items_manifest.json'
    assert reconstruct_input_items(final)==capture.last_input
    _write(output/'offline_seed_index.json',dict(api_sent=False,offline_only=True,seeds=seeds))
    (output/'observation_qa_instructions.txt').write_text(QA_INSTRUCTIONS)
    prepared=_read(final)
    summary=dict(schema='labsim.Project_v1_1.closed_public_temporal_observation_QA.v1',
        scope='closed public frames only; not a policy episode or task test',
        preview=True,API_sent=False,task_executed=False,task_success=None,task_dataset_eligible=False,
        source_process_proof=dict(path=str(Path(proof).resolve()),SHA256=_sha(proof),process_exited=True,pid=pid),
        source_current_decision=args.current_decision,current=prepared['current'],previous=prepared['previous'],
        first_public_bilateral_reference=prepared['first_public_bilateral_reference'],
        prepared_input_manifest=str(final.relative_to(output)),
        full_wire_input_canonical_sha256=prepared['full_wire_input_canonical_sha256'],
        total_images=prepared['total_image_count'],current_user_item_preserved=True,
        offline_capture_calls=capture.calls,offline_calls_are_API_decisions=False,
        actual_network_attempts=0,one_logical_responses_call=False,
        model=cfg['model'],instructions_SHA256=_sha(output/'observation_qa_instructions.txt'),
        QA_implementation_SHA256=_sha(Path(__file__)),
        provider_config_SHA256=_sha(args.provider_config),source_SHA256_before=before,
        source_SHA256_after=None,source_files_unchanged=None,
        note='No hidden reasoning, provider headers, credentials or private task labels are persisted.')
    _write(output/'qa_summary.json',summary)
    return cfg,summary,final,before


def request_payload(cfg,manifest):
    """Ordinary Responses body, without tool schema or a robot-control prompt."""
    payload=dict(model=cfg['model'],input=reconstruct_input_items(manifest),
        instructions=QA_INSTRUCTIONS,max_output_tokens=int(cfg['max_output_tokens']),store=False)
    if cfg.get('reasoning_effort'):payload['reasoning']=dict(effort=cfg['reasoning_effort'])
    return payload


def run_qa(args,*,client_factory=None):
    cfg,summary,final,before=prepare(args);output=args.output.resolve();error=None
    try:
        if args.allow_network:
            ledger=BudgetLedger(args.budget_ledger,cfg);start=ledger.summary()
            label='closed_public_temporal_QA:'+summary['current']['episode_id']+':decision'+str(args.current_decision)
            payload=request_payload(cfg,final)
            summary.update(preview=False,one_logical_responses_call=True,request_label=label,
                transport_kind='injected_CPU_test_transport' if client_factory else 'real_CubenceClient',
                retry_policy='allow_retry=False: at most one network attempt, original shared ledger and request deadline',
                wire_payload_canonical_sha256=canonical_hash(payload))
            _write(output/'qa_summary.json',summary)
            tick=time.monotonic()
            try:
                client=(client_factory(cfg,ledger) if client_factory else CubenceClient(cfg,ledger))
                response,meta=client.request(payload,endpoint='responses',allow_retry=False,
                    label=label,deadline_monotonic=tick+float(cfg['request_timeout_s']))
                visible=response_text(response)
                _write(output/'visible_response.json',dict(request_id=meta.get('request_id'),
                    response_id=response.get('id'),requested_model=cfg['model'],returned_model=response.get('model'),
                    usage=response.get('usage'),visible_output_text=visible,
                    provider_wall_seconds=meta.get('wall_seconds'),
                    hidden_reasoning_headers_credentials_saved=False))
                if any(item.get('type')=='function_call' for item in response.get('output',[]) if isinstance(item,dict)):
                    raise ProviderError('OBSERVATION_QA_UNEXPECTED_TOOL_RESPONSE')
                if not visible.strip():raise ProviderError('OBSERVATION_QA_EMPTY_VISIBLE_RESPONSE')
                summary.update(status='observation_response_received',request_id=meta.get('request_id'),
                    returned_model=response.get('model'),usage=response.get('usage'))
            except ProviderError as failure:
                error=failure;summary.update(status='provider_error',error_code=failure.code,
                    hidden_error_body_saved=False)
            finally:
                end=ledger.summary();attempts=end.get('total_network_attempts',0)-start.get('total_network_attempts',0)
                summary.update(provider_call_wall_seconds=time.monotonic()-tick,
                    API_sent=bool(attempts and not client_factory),
                    actual_network_attempts=0 if client_factory else attempts,
                    injected_test_transport_attempts=attempts if client_factory else 0,
                    ledger_attempt_delta=attempts,
                    ledger_estimated_USD_delta=end.get('total_estimated_usd',0)-start.get('total_estimated_usd',0))
        else:summary['status']='preview_ready_no_network'
    finally:
        after={p:_sha(p) for p in before};summary.update(source_SHA256_after=after,source_files_unchanged=before==after)
        _write(output/'qa_summary.json',summary)
    if not summary['source_files_unchanged']:raise ValueError('Source public files changed during QA')
    if error:raise error
    return summary


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',required=True,type=Path,help='Closed episode gpt_control directory with exact public observations')
    parser.add_argument('--current-decision',type=int,default=35)
    parser.add_argument('--source-process-proof',type=Path)
    parser.add_argument('--provider-config',type=Path,default=DEFAULT_PROFILE)
    parser.add_argument('--budget-ledger',type=Path,default=DEFAULT_LEDGER)
    parser.add_argument('--output',required=True,type=Path,help='New non-existing diagnostic directory')
    parser.add_argument('--allow-network',action='store_true',help='Explicitly send at most one observation-only network attempt through the original shared ledger; no retry')
    args=parser.parse_args(argv)
    try:summary=run_qa(args)
    except (ProviderError,ValueError,OSError,KeyError,StopIteration) as error:
        parser.exit(1,'Observation QA failed: '+(error.code if isinstance(error,ProviderError) else type(error).__name__)+'\n')
    print(json.dumps({k:summary[k] for k in ('status','API_sent','actual_network_attempts','task_executed','source_files_unchanged')},ensure_ascii=False))
    return 0


if __name__=='__main__':raise SystemExit(main())
