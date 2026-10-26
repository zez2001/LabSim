"""CPU public-input protocol fakes; no API, physics, GPU or task-success claim."""
import base64
import copy
import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

from policy.backends.cubence import BudgetLedger, CubenceClient, ProviderError, canonical_hash, input_token_bound, load_config
from policy.backends.cubence_tools import observation_content, save_observation_artifacts
from policy.backends import cubence_project_v1_1_tools as tools_module
from policy.backends.cubence_project_v1_1_visual_context import (
    PublicTemporalVisualClient, VISUAL_CONTEXT, reconstruct_input_items, validate_visual_context)

ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT/'config/lab_cuvette_loading/Project_v1_1/policies/cubence_gpt6_context4_640high_temporal.json'
spec = importlib.util.spec_from_file_location('temporal_protocol_helpers', ROOT/'tests/test_cubence_project_v1_1_tools.py')
helpers = importlib.util.module_from_spec(spec);spec.loader.exec_module(helpers)


class Client:
    def __init__(self):
        self.cfg = load_config(PROFILE);self.ledger = object();self.calls = [];self.error = None
    def responses(self, items, **kwargs):
        self.calls.append((copy.deepcopy(items), copy.deepcopy(kwargs)))
        if self.error:raise self.error
        return {'output': []}, {'request_id': 'cpu'}


def request(client, output, index, *, episode='e1', step=None, force=(0., 0.), history=None, image_value=None):
    step = index if step is None else step
    image_value = step*30+1 if image_value is None else image_value
    obs = dict(episode_id=episode,observation_id=f'{episode}:{step}',step_index=step,simulation_time=step/60,
        joint_positions=[0.]*9,joint_velocities=[0.]*9,
        TCPpose=dict(position_m=[0.,0.,1.],quaternion_wxyz=[1.,0.,0.,0.]),
        finger_contact_N=list(force),gripper_opening_m=.01,gripper_effort_limit_N=4.,
        task_language='Static public nominal task',source_slot_id='A1',target_seat_id='candidate_far_hinge',
        images=dict(side_camera=np.full((24,32,3),image_value,np.uint8),
                    wrist_camera=np.full((24,32,3),image_value+1,np.uint8)),
        camera_meta={n:dict(name=n,intrinsic_matrix_native=[[500.,0.,16.],[0.,500.,12.],[0.,0.,1.]],
            camera_cv_from_world=np.eye(4).tolist(),sensor_rendering_time_s=step/60) for n in ('side_camera','wrist_camera')},
        object_position_m=[9.,9.,9.],teacher_phase='NEVER_FORWARD_THIS')
    contents = observation_content(obs, image_config=client.cfg['images'])
    label=f'policy:{episode}:decision{index}'
    save_observation_artifacts(contents, output, index, label)
    items=[dict(role='user', content='Task: Static public nominal task')]+copy.deepcopy(history or [])+[dict(role='user',content=contents)]
    return items, label


def send(wrapper, output, index, **kwargs):
    items,label=request(wrapper,output,index,**kwargs)
    before=copy.deepcopy(items)
    result=wrapper.responses(items,instructions='cpu public prompt',tools=[dict(type='function',name='wait')],label=label,deadline_monotonic=123.)
    assert items == before
    path=output/'temporal_visual_context'/f'decision_{index:06d}'/'input_items_manifest.json'
    return json.loads(path.read_text()),path,result,before


def test_new_profile_only_adds_visual_context_and_keeps_all_budgets_and_model_limits():
    old=load_config(PROFILE.with_name('cubence_gpt6_context4_640high.json'))
    new=load_config(PROFILE);assert new.pop('visual_context')==VISUAL_CONTEXT
    assert new==old


@pytest.mark.parametrize('value',[None,False,True,{},dict(VISUAL_CONTEXT,enabled=False),
    dict(VISUAL_CONTEXT,previous_distinct_wrist=1),dict(VISUAL_CONTEXT,bilateral_contact_threshold_N=.03),
    dict(VISUAL_CONTEXT,bilateral_contact_threshold_N=float('nan')),dict(VISUAL_CONTEXT,bilateral_contact_threshold_N=True),
    dict(VISUAL_CONTEXT,object_pose_selector=True)])
def test_invalid_opt_in_is_rejected_without_calling_a_provider(value):
    with pytest.raises(ProviderError,match='PROTOCOL_INVALID_VISUAL_CONTEXT_CONFIG'):
        validate_visual_context(dict(visual_context=value))
    assert validate_visual_context({}) is None


def test_legacy_profile_passes_exact_original_client_prompt_and_tools(monkeypatch,tmp_path):
    base=Client();del base.cfg['visual_context'];captured={}
    def fake(environment, client, output, **kwargs):
        captured.update(client=client,output=output,kwargs=kwargs);return 'unchanged'
    monkeypatch.setattr(tools_module,'_run_episode',fake)
    assert tools_module.run_episode(object(),base,tmp_path,max_calls=7)=='unchanged'
    assert captured['client'] is base
    assert captured['kwargs']==dict(max_calls=7,prompt=tools_module.SYSTEM_PROMPT,tools_class=tools_module.ProjectV11RobotTools)
    assert tools_module.ProjectV11RobotTools.controller_metadata()['prompt_version']=='Project_v1_1.public_tools.v4'
    assert not list(tmp_path.iterdir())


def test_explicit_profile_wraps_only_new_version_prompt_metadata_and_same_ledger(monkeypatch,tmp_path):
    base=Client();captured={}
    def fake(environment,client,output,**kwargs):captured.update(client=client,kwargs=kwargs);return 'opted'
    monkeypatch.setattr(tools_module,'_run_episode',fake)
    assert tools_module.run_episode(object(),base,tmp_path)=='opted'
    wrapper=captured['client'];assert isinstance(wrapper,PublicTemporalVisualClient)
    assert wrapper.ledger is base.ledger and wrapper.cfg==base.cfg and wrapper.cfg is not base.cfg
    assert captured['kwargs']['prompt']==tools_module.TEMPORAL_SYSTEM_PROMPT
    meta=captured['kwargs']['tools_class'].controller_metadata()
    assert meta['prompt_version']=='Project_v1_1.public_tools.v6_temporal'
    assert meta['visual_context_profile']==VISUAL_CONTEXT
    helper=ROOT/'policy/backends/cubence_project_v1_1_visual_context.py'
    assert meta['implementation_sha256'][helper.name]==hashlib.sha256(helper.read_bytes()).hexdigest()


def test_previous_and_fixed_contact_anchor_give_at_most_four_images_with_exact_bytes(tmp_path):
    base=Client();wrapper=PublicTemporalVisualClient(base,tmp_path)
    first,*_=send(wrapper,tmp_path,0,force=(0.,0.))
    contact,*_=send(wrapper,tmp_path,1,force=(.2,.21))
    dedup,*_=send(wrapper,tmp_path,2,force=(.3,.31))
    fourth,path,_,original=send(wrapper,tmp_path,3,force=(0.,0.))
    assert first['total_image_count']==2 and first['first_public_bilateral_reference'] is None
    assert contact['first_reference_selected_this_observation'] is True
    assert dedup['historical_images_inserted']==1
    assert dedup['historical_references'][0]['reference_roles']==['previous_distinct_wrist','first_public_bilateral_wrist']
    assert fourth['total_image_count']==4
    assert fourth['previous']['observation_id']=='e1:2'
    assert fourth['first_public_bilateral_reference']['observation_id']=='e1:1'
    assert base.calls[-1][0][-1]==original[-1]  # Current five blocks/identity unchanged and last.
    assert base.calls[-1][1]['deadline_monotonic']==123.
    assert reconstruct_input_items(path)==base.calls[-1][0]
    for hist in fourth['historical_references']:
        saved=path.parent/hist['exact_jpeg']['path']
        previous=json.loads((tmp_path/'observations'/f"decision_{hist['source_decision_index']:06d}"/'public_observation.json').read_text())
        assert hashlib.sha256(saved.read_bytes()).hexdigest()==previous['model_image_transforms']['wrist_camera']['transmitted_jpeg_sha256']
        assert saved.read_bytes()==(tmp_path/'observations'/f"decision_{hist['source_decision_index']:06d}"/'wrist_camera.jpg').read_bytes()
    text=''.join(p.read_text() for p in (tmp_path/'temporal_visual_context').rglob('*.json'))
    assert 'NEVER_FORWARD_THIS' not in text and 'object_position_m' not in text
    assert 'no_action_or_success_label_generated' in text


def test_repeat_observe_does_not_overwrite_previous_or_fixed_reference(tmp_path):
    base=Client();wrapper=PublicTemporalVisualClient(base,tmp_path)
    send(wrapper,tmp_path,0,step=0)
    send(wrapper,tmp_path,1,step=1,force=(.2,.21))
    repeat,*_=send(wrapper,tmp_path,2,step=1,force=(.9,.9),image_value=90)
    assert repeat['current_observation_is_duplicate_id'] is True
    assert repeat['previous']['observation_id']=='e1:0'
    assert repeat['first_reference_selected_this_observation'] is False
    assert repeat['first_public_bilateral_reference']['source_decision_index']==1
    later,*_=send(wrapper,tmp_path,3,step=2)
    assert later['previous']['source_decision_index']==1
    assert later['first_public_bilateral_reference']['source_decision_index']==1


@pytest.mark.parametrize('forces',[(.02,.1),(.03,0.),(None,.5),(True,.3)])
def test_reference_selection_requires_both_finite_public_forces_and_never_guarantees_grasp(tmp_path,forces):
    wrapper=PublicTemporalVisualClient(Client(),tmp_path)
    manifest,*_=send(wrapper,tmp_path,0,force=forces)
    assert manifest['first_public_bilateral_reference'] is None
    assert manifest['first_reference_selected_this_observation'] is False
    assert manifest['no_action_or_success_label_generated'] is True


def test_new_episode_clears_both_memories_and_keeps_recording_paths_nonoverwriting(tmp_path):
    wrapper=PublicTemporalVisualClient(Client(),tmp_path)
    send(wrapper,tmp_path,0,force=(.3,.3));send(wrapper,tmp_path,1)
    new,*_=send(wrapper,tmp_path,2,episode='e2',step=0)
    assert new['historical_images_inserted']==0 and new['previous'] is None
    assert new['first_public_bilateral_reference'] is None
    assert new['current']['episode_id']=='e2'
    wrapper.reset();assert wrapper._last_distinct is wrapper._previous_distinct is wrapper._contact_reference is None


def test_full_turns_and_reasoning_stay_in_live_input_but_private_reasoning_is_not_saved(tmp_path):
    base=Client();wrapper=PublicTemporalVisualClient(base,tmp_path)
    send(wrapper,tmp_path,0)
    group=[dict(type='reasoning',id='private',summary=[{'text':'HIDDEN_REASONING_SENTINEL'}]),
        dict(type='function_call',id='f',call_id='c',name='wait',arguments='{}'),
        dict(type='function_call_output',call_id='c',output='{"accepted":true}')]
    record,path,_,_=send(wrapper,tmp_path,1,history=group)
    actual=base.calls[-1][0]
    assert actual[1:4]==group
    assert record['current_user_item_index']==5  # Task, three whole turn items, history, current.
    assert record['full_wire_input_canonical_sha256']==canonical_hash(actual)
    assert record['exact_full_input_reconstructable'] is False
    assert record['private_provider_items_redacted'][0]['input_item_index']==1
    assert 'HIDDEN_REASONING_SENTINEL' not in path.read_text()
    with pytest.raises(ValueError,match='deliberately not persisted'):reconstruct_input_items(path)


def test_provider_failure_still_saves_exact_public_request_without_error_body(tmp_path):
    base=Client();wrapper=PublicTemporalVisualClient(base,tmp_path)
    base.error=ProviderError('PROVIDER_NETWORK_ERROR')
    items,label=request(wrapper,tmp_path,0)
    with pytest.raises(ProviderError,match='PROVIDER_NETWORK_ERROR'):
        wrapper.responses(items,instructions='prompt',label=label)
    packet=tmp_path/'temporal_visual_context/decision_000000'
    assert json.loads((packet/'call_outcome.json').read_text())['status']=='failed'
    assert reconstruct_input_items(packet/'input_items_manifest.json')==base.calls[0][0]
    assert len(base.calls)==1


def test_empty_or_nonfinite_input_fails_closed_with_no_delegate(tmp_path):
    base=Client();wrapper=PublicTemporalVisualClient(base,tmp_path)
    with pytest.raises(ProviderError,match='CURRENT_OBSERVATION_MISSING'):
        wrapper.responses([],instructions='prompt')
    items,label=request(wrapper,tmp_path,0)
    state=json.loads(items[-1]['content'][0]['text']);state['finger_contact_N']=[float('nan'),.3]
    items[-1]['content'][0]['text']=json.dumps(state)
    with pytest.raises(ProviderError,match='INVALID_TEMPORAL_PUBLIC_OBSERVATION'):
        wrapper.responses(items,instructions='prompt',label=label)
    assert not base.calls


def test_mismatched_saved_current_artifact_prevents_network_and_overwrite(tmp_path):
    base=Client();wrapper=PublicTemporalVisualClient(base,tmp_path)
    items,label=request(wrapper,tmp_path,0)
    (tmp_path/'observations/decision_000000/wrist_camera.jpg').write_bytes(b'bad')
    with pytest.raises(ProviderError,match='RECORDING_FAILED'):
        wrapper.responses(items,instructions='prompt',label=label)
    assert not base.calls


def test_actual_provider_fake_receives_augmented_input_and_shared_ledger_bounds_all_images(tmp_path,monkeypatch):
    cfg=load_config(PROFILE);ledger=BudgetLedger(tmp_path/'budget.json',cfg)
    monkeypatch.setattr('policy.backends.cubence.time.monotonic',lambda: 0.)
    opener=helpers._Opener([dict(model='gpt-6-astra',output=[],usage=dict(input_tokens=10,output_tokens=1)) for _ in range(3)])
    monkeypatch.setenv('CUBENCE_API_KEY','cpu-temporal-placeholder')
    actual=CubenceClient(cfg,ledger,opener=opener,sleeper=lambda _:None)
    wrapper=PublicTemporalVisualClient(actual,tmp_path/'episode')
    for i in range(3):send(wrapper,tmp_path/'episode',i,force=(.2,.2))
    assert len(opener.bodies)==ledger.summary()['total_network_attempts']==3
    last=json.loads((tmp_path/'episode/temporal_visual_context/decision_000002/input_items_manifest.json').read_text())
    assert last['total_image_count']==4
    assert reconstruct_input_items(tmp_path/'episode/temporal_visual_context/decision_000002/input_items_manifest.json')==opener.bodies[-1]['input']
    attempts=json.loads(ledger.path.read_text())['attempts']
    assert attempts[-1]['reservation_input_tokens']==input_token_bound(opener.bodies[-1],cfg['max_context_input_tokens'])
    assert attempts[-1]['reservation_input_tokens']>attempts[0]['reservation_input_tokens']+16000
    saved=''.join(p.read_text() for p in tmp_path.rglob('*.json'))
    assert 'cpu-temporal-placeholder' not in saved and 'Authorization' not in saved


def test_end_to_end_runner_selects_temporal_v6_without_new_tools_or_actions(tmp_path,monkeypatch):
    cfg=load_config(PROFILE);env=helpers.ReceiptEnvironment();ledger=BudgetLedger(tmp_path/'budget.json',cfg)
    commands=[helpers.reply('wait',helpers.args(env),0),
        helpers.reply('finish',dict(episode_id='e1',observation_id='e1:60',reason='CPU contract end'),1)]
    opener=helpers._Opener(commands);monkeypatch.setenv('CUBENCE_API_KEY','cpu-temporal-placeholder')
    client=CubenceClient(cfg,ledger,opener=opener,sleeper=lambda _:None)
    out=tmp_path/'episode';result=tools_module.run_episode(env,client,out,max_calls=3)
    assert result['network_attempts_this_episode']==2 and len(env.executions)==1
    frozen=json.loads((out/'controller.json').read_text())
    assert frozen['controller_extension']['prompt_version']=='Project_v1_1.public_tools.v6_temporal'
    assert [x['name'] for x in frozen['tool_schema']]==['observe','move_ee','gripper','wait','finish']
    assert len(opener.bodies[-1]['input'][-1]['content'])==5
    assert json.loads(opener.bodies[-1]['input'][-1]['content'][0]['text'])['observation_id']=='e1:60'
    assert 'object_position_m' not in json.dumps(opener.bodies)


def test_nonadvancing_or_inconsistent_public_identity_fails_without_delegate(tmp_path):
    base=Client();wrapper=PublicTemporalVisualClient(base,tmp_path)
    send(wrapper,tmp_path,0,step=3)
    items,label=request(wrapper,tmp_path,1,step=2)
    with pytest.raises(ProviderError,match='TIME_INCONSISTENT'):
        wrapper.responses(items,instructions='prompt',label=label)
    assert len(base.calls)==1
    proof=json.loads((tmp_path/'temporal_visual_context/preflight_failure_000000.json').read_text())
    assert proof['provider_called'] is False
    assert proof['error_code']=='PROTOCOL_TEMPORAL_OBSERVATION_TIME_INCONSISTENT'


def test_exact_original_historical_public_json_is_saved_and_reference_is_episode_fixed(tmp_path):
    base=Client();wrapper=PublicTemporalVisualClient(base,tmp_path)
    send(wrapper,tmp_path,0,force=(.3,.3));send(wrapper,tmp_path,1,force=(0.,0.))
    record,path,*_=send(wrapper,tmp_path,2,force=(9.,9.))
    assert record['first_public_bilateral_reference']['source_decision_index']==0
    for row in record['historical_references']:
        assert (path.parent/row['public_observation']['path']).read_bytes()==(
            tmp_path/'observations'/f"decision_{row['source_decision_index']:06d}"/'public_observation.json').read_bytes()
    assert record['no_action_or_success_label_generated'] is True


def test_unknown_opaque_provider_items_not_persisted_or_removed_from_live_protocol(tmp_path):
    base=Client();wrapper=PublicTemporalVisualClient(base,tmp_path)
    send(wrapper,tmp_path,0)
    opaque=dict(type='future_private_provider_item',payload='OPAQUE_SECRET_SENTINEL')
    record,path,*_=send(wrapper,tmp_path,1,history=[opaque])
    assert base.calls[-1][0][1]==opaque
    assert 'OPAQUE_SECRET_SENTINEL' not in path.read_text()
    assert record['exact_full_input_reconstructable'] is False


def test_saved_history_images_cannot_be_tampered_without_reconstruction_failure(tmp_path):
    wrapper=PublicTemporalVisualClient(Client(),tmp_path)
    send(wrapper,tmp_path,0);record,path,*_=send(wrapper,tmp_path,1)
    saved=path.parent/record['historical_references'][0]['exact_jpeg']['path']
    saved.write_bytes(saved.read_bytes()+b'tampered')
    with pytest.raises(ValueError,match='JPEG hash mismatch'):reconstruct_input_items(path)


def test_nested_public_state_is_not_promoted_to_historical_private_data(tmp_path):
    base=Client();wrapper=PublicTemporalVisualClient(base,tmp_path)
    items,label=request(wrapper,tmp_path,0)
    state=json.loads(items[-1]['content'][0]['text']);state['object_position_m']=[9.,9.,9.]
    items[-1]['content'][0]['text']=json.dumps(state)
    with pytest.raises(ProviderError,match='INVALID_TEMPORAL_PUBLIC_OBSERVATION'):
        wrapper.responses(items,instructions='prompt',label=label)
    assert not base.calls
    saved=''.join(p.read_text() for p in (tmp_path/'temporal_visual_context').rglob('*.json'))
    assert 'object_position_m' not in saved
