"""Closed-public QA plumbing; all transport tests are local CPU fakes."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import urllib.error

import pytest

from demos.lab_cuvette_project_v1_1 import temporal_observation_qa as qa
from policy.backends.cubence import CubenceClient, ProviderError, canonical_hash
from policy.backends.cubence_project_v1_1_visual_context import reconstruct_input_items

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('observation_qa_helpers',ROOT/'tests/test_lab_cuvette_project_v1_1_visual_context.py')
helpers=importlib.util.module_from_spec(spec);spec.loader.exec_module(helpers)


def write(path,value):path.write_text(json.dumps(value,indent=2)+'\n')
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def args(tmp_path):
    source=tmp_path/'run/episode_0000/gpt_control';base=helpers.Client()
    for index in range(4):helpers.request(base,source,index,force=(.2,.21) if index==1 else (0.,0.))
    proof=tmp_path/'run/process_exit.json';write(proof,dict(process_exited=True,exit_code=0,pid=99999999))
    return argparse.Namespace(source=source,output=tmp_path/'qa',current_decision=3,
        source_process_proof=None,provider_config=qa.DEFAULT_PROFILE,budget_ledger=tmp_path/'budget.json',allow_network=False)


def test_preview_uses_real_memory_exact_jpegs_and_no_client_or_ledger(args,monkeypatch):
    def forbidden(*_a,**_k):raise AssertionError('preview must not instantiate a provider')
    monkeypatch.setattr(qa,'CubenceClient',forbidden)
    before={str(p):sha(p) for p in args.source.rglob('*') if p.is_file()}
    result=qa.run_qa(args)
    assert result['status']=='preview_ready_no_network' and result['API_sent'] is False
    assert result['actual_network_attempts']==0 and not args.budget_ledger.exists()
    assert result['offline_capture_calls']==4 and result['offline_calls_are_API_decisions'] is False
    assert result['current']['observation_id']=='e1:3' and result['previous']['observation_id']=='e1:2'
    assert result['first_public_bilateral_reference']['observation_id']=='e1:1'
    assert result['total_images']==4 and result['task_executed'] is False and result['task_success'] is None
    manifest=args.output/result['prepared_input_manifest'];items=reconstruct_input_items(manifest)
    assert len(items)==2 and len(items[-1]['content'])==5
    assert json.loads(items[-1]['content'][0]['text'])['observation_id']=='e1:3'
    record=json.loads(manifest.read_text())
    for row in record['historical_references']:
        original=args.source/'observations'/f"decision_{row['source_decision_index']:06d}"/'wrist_camera.jpg'
        assert (manifest.parent/row['exact_jpeg']['path']).read_bytes()==original.read_bytes()
    assert canonical_hash(items)==result['full_wire_input_canonical_sha256']
    assert all(json.loads(p.read_text())['api_sent'] is False for p in args.output.rglob('offline_seed.json'))
    assert not (args.output/'visible_response.json').exists()
    assert {str(p):sha(p) for p in args.source.rglob('*') if p.is_file()}==before


def test_authorized_path_has_one_actual_client_request_and_no_tools_hidden_reasoning_or_credential(args,monkeypatch):
    args.allow_network=True
    reply=dict(model='gpt-6-astra',id='cpu-qa',usage=dict(input_tokens=10,output_tokens=5),output=[
        dict(type='reasoning',summary=[dict(text='PRIVATE_REASONING_SENTINEL')]),
        dict(type='message',content=[dict(type='output_text',text='{"bottom_support_evidence":"uncertain"}')])])
    opener=helpers.helpers._Opener([reply]);monkeypatch.setenv('CUBENCE_API_KEY','cpu-qa-placeholder')
    def factory(cfg,ledger):return CubenceClient(cfg,ledger,opener=opener,sleeper=lambda _:None)
    result=qa.run_qa(args,client_factory=factory)
    assert len(opener.bodies)==1 and result['ledger_attempt_delta']==1
    assert result['API_sent'] is False and result['actual_network_attempts']==0
    assert result['injected_test_transport_attempts']==1
    wire=opener.bodies[0]
    assert 'tools' not in wire and 'tool_choice' not in wire and wire['store'] is False
    assert wire['instructions']==qa.QA_INSTRUCTIONS and wire['model']=='gpt-6-astra'
    assert wire['reasoning']==dict(effort='low') and wire['max_output_tokens']==1024
    assert canonical_hash(wire)==result['wire_payload_canonical_sha256']
    assert json.loads(wire['input'][-1]['content'][0]['text'])['observation_id']=='e1:3'
    saved=''.join(p.read_text() for p in args.output.rglob('*.json'))
    assert 'PRIVATE_REASONING_SENTINEL' not in saved and 'cpu-qa-placeholder' not in saved
    assert 'Authorization' not in saved
    visible=json.loads((args.output/'visible_response.json').read_text())
    assert visible['visible_output_text']=='{"bottom_support_evidence":"uncertain"}'
    assert result['source_files_unchanged'] is True


def test_retryable_error_is_one_attempt_even_though_profile_allows_retries(args,monkeypatch):
    args.allow_network=True
    class ErrorOpener:
        calls=0
        def open(self,request,timeout):
            self.calls+=1;raise urllib.error.URLError('local CPU fake failure')
    opener=ErrorOpener();monkeypatch.setenv('CUBENCE_API_KEY','cpu-qa-placeholder')
    def factory(cfg,ledger):return CubenceClient(cfg,ledger,opener=opener,sleeper=lambda _:pytest.fail('must not retry'))
    with pytest.raises(ProviderError,match='PROVIDER_NETWORK_ERROR'):qa.run_qa(args,client_factory=factory)
    result=json.loads((args.output/'qa_summary.json').read_text())
    assert opener.calls==result['ledger_attempt_delta']==1 and result['status']=='provider_error'
    assert result['source_files_unchanged'] is True and result['API_sent'] is False


@pytest.mark.parametrize('output,error',[([], 'OBSERVATION_QA_EMPTY_VISIBLE_RESPONSE'),
    ([dict(type='function_call',name='move_ee',arguments='{}')],'OBSERVATION_QA_UNEXPECTED_TOOL_RESPONSE')])
def test_empty_or_tool_answer_is_retained_as_failure_and_cannot_execute_anything(args,monkeypatch,output,error):
    args.allow_network=True
    opener=helpers.helpers._Opener([dict(model='gpt-6-astra',output=output,usage=dict(input_tokens=10,output_tokens=1))])
    monkeypatch.setenv('CUBENCE_API_KEY','cpu-qa-placeholder')
    def factory(cfg,ledger):return CubenceClient(cfg,ledger,opener=opener,sleeper=lambda _:None)
    with pytest.raises(ProviderError,match=error):qa.run_qa(args,client_factory=factory)
    summary=json.loads((args.output/'qa_summary.json').read_text())
    assert len(opener.bodies)==summary['ledger_attempt_delta']==1
    assert summary['task_executed'] is False and summary['task_success'] is None
    assert summary['status']=='provider_error' and summary['source_files_unchanged'] is True


@pytest.mark.parametrize('damage',['missing_jpeg','wrong_jpeg_sha','wrong_json_sha','forbidden_truth','nonfinite','mixed_episode','bad_manifest_decision'])
def test_source_rejection_happens_before_new_output_and_network(args,damage):
    folder=args.source/'observations/decision_000002';state_path=folder/'public_observation.json';manifest_path=folder/'manifest.json'
    state=json.loads(state_path.read_text());manifest=json.loads(manifest_path.read_text())
    if damage=='missing_jpeg':(folder/'wrist_camera.jpg').unlink()
    elif damage=='wrong_jpeg_sha':(folder/'wrist_camera.jpg').write_bytes(b'bad')
    elif damage=='wrong_json_sha':state_path.write_text(state_path.read_text()+' ')
    elif damage=='bad_manifest_decision':manifest['decision_index']=90;write(manifest_path,manifest)
    else:
        if damage=='forbidden_truth':state['object_position_m']=[1,2,3]
        elif damage=='nonfinite':state['finger_contact_N']=[float('nan'),.3]
        elif damage=='mixed_episode':state['episode_id']='another'
        write(state_path,state);manifest['public_observation']['sha256']=sha(state_path);write(manifest_path,manifest)
    with pytest.raises((ProviderError,ValueError,OSError)):qa.run_qa(args)
    assert not args.output.exists() and not args.budget_ledger.exists()


def test_output_overwrite_and_active_source_refused(args):
    args.output.mkdir();sentinel=args.output/'keep.txt';sentinel.write_text('original')
    with pytest.raises(FileExistsError):qa.run_qa(args)
    assert sentinel.read_text()=='original'
    args.output=args.output.with_name('new-qa')
    write(args.source.parent.parent/'process_exit.json',dict(process_exited=True,exit_code=0,pid=os.getpid()))
    with pytest.raises(ValueError,match='still exists'):qa.run_qa(args)
    assert not args.output.exists()


def test_missing_credential_is_saved_as_provider_error_without_any_attempt(args,monkeypatch):
    args.allow_network=True;monkeypatch.delenv('CUBENCE_API_KEY',raising=False)
    with pytest.raises(ProviderError,match='MISSING_CUBENCE_API_KEY'):qa.run_qa(args)
    result=json.loads((args.output/'qa_summary.json').read_text())
    assert result['status']=='provider_error' and result['API_sent'] is False
    assert result['actual_network_attempts']==result['ledger_attempt_delta']==0
    assert result['source_files_unchanged'] is True


def test_cli_help_and_default_are_offline_and_instructions_are_observation_only(capsys):
    with pytest.raises(SystemExit) as result:qa.main(['--help'])
    assert result.value.code==0 and '--allow-network' in capsys.readouterr().out
    assert 'Return no tool call' in qa.QA_INSTRUCTIONS and 'No simulator or tools' in qa.QA_INSTRUCTIONS
    assert '0.0001' not in qa.QA_INSTRUCTIONS and '71.675' not in qa.QA_INSTRUCTIONS
