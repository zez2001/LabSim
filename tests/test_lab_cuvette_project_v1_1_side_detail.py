"""CPU exact-public-JPEG tests; fake transports are not actual model results."""
import base64
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import types

import numpy as np
from PIL import Image
import pytest

from policy.backends.cubence import BudgetLedger, CubenceClient, ProviderError, canonical_hash, input_token_bound, load_config
from policy.backends.cubence_tools import observation_content, save_observation_artifacts, tool_definitions
from policy.backends.cubence_project_v1_1_visual_context import reconstruct_input_items
from policy.backends import cubence_project_v1_1_side_detail as detail

ROOT = Path(__file__).resolve().parents[1]
PROFILE = detail.DEFAULT_PROFILE
spec = importlib.util.spec_from_file_location('side_detail_helpers', ROOT/'tests/test_cubence_project_v1_1_tools.py')
helpers = importlib.util.module_from_spec(spec); spec.loader.exec_module(helpers)


class Client:
    def __init__(self):
        self.cfg = load_config(PROFILE)
        self.ledger = object()
        self.calls = []
    def responses(self, items, **kwargs):
        self.calls.append((copy.deepcopy(items), copy.deepcopy(kwargs)))
        return dict(output=[]), dict(request_id='CPU')


def request(client, output, index, *, step=None, episode='e1', forces=(0.,0.), width=640, height=480, history=None):
    step = index if step is None else step
    image = np.zeros((height, width, 3), dtype=np.uint8)
    image[...,0] = np.arange(width, dtype=np.uint16)[None,:] % 256
    image[...,1] = np.arange(height, dtype=np.uint16)[:,None] % 256
    image[...,2] = (index*23) % 256
    source_K = [[500.,0.,320.],[0.,400.,240.],[0.,0.,1.]]
    camera = dict(physical_parent='/World',
        local_pose_position_m=detail.FIXED_SIDE_DETAIL['expected_local_position_m'],
        local_pose_quaternion_wxyz=detail.FIXED_SIDE_DETAIL['expected_local_quaternion_wxyz'],
        intrinsic_matrix_native=source_K, resolution_wh=[width,height],
        camera_cv_from_world=np.eye(4).tolist(), sensor_rendering_time_s=step/60)
    obs = dict(episode_id=episode, observation_id=f'{episode}:{step}', step_index=step,
        simulation_time=step/60, joint_positions=[0.]*9, joint_velocities=[0.]*9,
        TCPpose=dict(position_m=[0.,0.,1.],quaternion_wxyz=[1.,0.,0.,0.]),
        gripper_opening_m=.01, gripper_effort_limit_N=4., finger_contact_N=list(forces),
        task_language='Public nominal task', source_slot_id='A1', target_seat_id='candidate_far_hinge',
        camera_meta={'side_camera':camera,'wrist_camera':camera},
        images={'side_camera':image,'wrist_camera':image},
        object_position_m=[999.,999.,999.],teacher_phase='FORBIDDEN_SENTINEL')
    contents = observation_content(obs, image_config=client.cfg['images'])
    label = f'CPU:{episode}:decision{index}'
    save_observation_artifacts(contents,output,index,label)
    items = [dict(role='user',content='Task: Public nominal task'),*(history or []),dict(role='user',content=contents)]
    return items,label


def send(client,output,index,**kwargs):
    items,label=request(client,output,index,**kwargs)
    original=copy.deepcopy(items)
    client.responses(items,instructions='CPU',label=label,deadline_monotonic=123.)
    assert items==original
    path=output/'temporal_visual_context'/f'decision_{index:06d}'/'input_items_manifest.json'
    return json.loads(path.read_text()),path,original


def test_profile_only_adds_fixed_detail_and_context2_without_changing_P6_or_budget():
    baseline=load_config(PROFILE.with_name('cubence_gpt6_context4_640high_temporal.json'))
    candidate=load_config(PROFILE)
    assert candidate.pop('fixed_side_detail')==detail.FIXED_SIDE_DETAIL
    assert candidate['max_context_messages']==2 and baseline['max_context_messages']==4
    candidate['max_context_messages']=4
    assert candidate==baseline
    assert detail.FIXED_SIDE_DETAIL['max_side_px']==480


@pytest.mark.parametrize('bad',[None,False,{},dict(detail.FIXED_SIDE_DETAIL,max_side_px=640),
    dict(detail.FIXED_SIDE_DETAIL,roi_pixel_edges_xyxy=[239,32,520,312]),
    dict(detail.FIXED_SIDE_DETAIL,object_position_selector=True)])
def test_invalid_detail_configuration_is_not_silently_enabled(bad):
    cfg=load_config(PROFILE);cfg['fixed_side_detail']=bad
    with pytest.raises(ProviderError,match='INVALID_FIXED_SIDE_DETAIL_CONFIG'):
        detail.validate_fixed_side_detail(cfg)


def test_detail_requires_explicit_unchanged_temporal_configuration():
    cfg=load_config(PROFILE);cfg.pop('visual_context')
    with pytest.raises(ProviderError,match='REQUIRES_TEMPORAL_CONFIG'):
        detail.validate_fixed_side_detail(cfg)


def test_detail_context2_must_match_its_declared_memory_scope():
    cfg=load_config(PROFILE);cfg['max_context_messages']=4
    with pytest.raises(ProviderError,match='REQUIRES_CONTEXT2'):
        detail.validate_fixed_side_detail(cfg)


def test_P7_only_adds_generic_visual_clearance_facts_and_preserves_tools():
    assert detail.SYSTEM_PROMPT.startswith(detail.P6_PROMPT)
    assert '480-by-480' in detail.DETAIL_PROMPT
    assert 400<=len(detail.DETAIL_PROMPT)<=700
    assert 'terminal arm segment' in detail.DETAIL_PROMPT
    assert detail.tool_definitions()==tool_definitions()
    for forbidden in ('SourceMesh5','49.908','1.313','candidate_far_hinge','teacher_phase',
            'object_position','seat_position','stage_id','force_vector'):
        assert forbidden not in detail.DETAIL_PROMPT


def test_exact_source_crop_decode_new_K_and_current_remain_last(tmp_path):
    base=Client();client=detail.PublicFixedSideDetailClient(base,tmp_path)
    items,label=request(client,tmp_path,0)
    source=tmp_path/'observations/decision_000000/side_camera.jpg'
    original=source.read_bytes()
    client.responses(items,instructions='CPU',label=label,deadline_monotonic=123.)
    folder=tmp_path/'temporal_visual_context/decision_000000'
    record=json.loads((folder/'input_items_manifest.json').read_text())
    meta=record['fixed_side_detail']['metadata']
    assert source.read_bytes()==original
    assert len(base.calls)==1 and base.calls[0][1]['deadline_monotonic']==123.
    assert base.calls[0][0][-1]==items[-1]
    assert record['total_image_count']==3 and record['current_user_item_index']==len(base.calls[0][0])-1
    with Image.open(folder/'current_side_detail.jpg') as im:
        assert im.size==(480,480) and im.mode=='RGB'
    assert meta['source_encoded_side_jpeg_sha256']==hashlib.sha256(original).hexdigest()
    assert meta['roi_pixel_edges_xyxy']==[240,32,520,312]
    assert meta['source_jpeg_reencoded_or_modified'] is False
    assert meta['new_sensor_measurement'] is False and meta['no_physical_or_image_resolution_gain'] is True
    # Independent projection example: K maps the ray(-.04,-.1,1) to source(300,200).
    K=np.array(meta['intrinsic_matrix_detail']);projected=K@np.array([-.04,-.1,1.])
    assert projected[:2]/projected[2]==pytest.approx([103.21428571428571,288.35714285714283])
    A=np.array(meta['transmitted_pixel_from_source_pixel'])
    assert A@np.array([379.5,171.5,1.])==pytest.approx([239.5,239.5,1.])
    before=json.loads((folder/'pre_detail_input_items_manifest.json').read_text())
    assert before['total_image_count']==2
    assert json.loads((folder/'pre_detail_preparation.json').read_text())['API_sent'] is False
    assert reconstruct_input_items(folder/'input_items_manifest.json')==base.calls[0][0]
    assert canonical_hash(base.calls[0][0])==record['full_wire_input_canonical_sha256']
    assert 'FORBIDDEN_SENTINEL' not in (folder/'input_items_manifest.json').read_text()


def test_actual_four_images_enter_one_original_client_reservation(tmp_path,monkeypatch):
    cfg=load_config(PROFILE);ledger=BudgetLedger(tmp_path/'budget.json',cfg)
    opener=helpers._Opener([dict(model='gpt-6-astra',output=[],usage=dict(input_tokens=10,output_tokens=1)) for _ in range(4)])
    monkeypatch.setenv('CUBENCE_API_KEY','CPU-fixed-side-key')
    monkeypatch.setattr('policy.backends.cubence.time.monotonic',lambda:0.)
    base=CubenceClient(cfg,ledger,opener=opener,sleeper=lambda _:None)
    client=detail.PublicFixedSideDetailClient(base,tmp_path/'episode')
    for i,forces in enumerate([(0.,0.),(.2,.2),(.2,.2),(.2,.2)]):
        record,path,_=send(client,tmp_path/'episode',i,forces=forces)
    assert len(opener.bodies)==ledger.summary()['total_network_attempts']==4
    assert record['total_image_count']==4 and record['historical_images_inserted']==1
    assert record['historical_input_policy']['supplied_roles']==[['first_public_bilateral_wrist']]
    assert record['historical_input_policy']['omitted_roles']==[['previous_distinct_wrist']]
    assert reconstruct_input_items(path)==opener.bodies[-1]['input']
    body=opener.bodies[-1]
    assert sum(c.get('type')=='input_image' for x in body['input']
        if isinstance(x.get('content'),list) for c in x['content'] if isinstance(c,dict))==4
    sizes=[]
    for item in body['input']:
        if not isinstance(item.get('content'),list):continue
        for block in item['content']:
            if block.get('type')!='input_image':continue
            with Image.open(io.BytesIO(base64.b64decode(block['image_url'].split(',',1)[1]))) as im:
                im.load();sizes.append(im.size)
    assert sizes==[(640,480),(480,480),(640,480),(640,480)]
    entries=json.loads(ledger.path.read_text())['attempts']
    assert entries[-1]['reservation_input_tokens']==input_token_bound(body,cfg['max_context_input_tokens'])
    assert entries[-1]['reservation_input_tokens']>entries[0]['reservation_input_tokens']+8192
    assert base.cfg['max_estimated_usd']==30 and base.cfg['max_requests']==1500
    assert 'CPU-fixed-side-key' not in path.read_text()


def test_previous_is_only_fallback_until_first_reference_and_current_is_not_duplicated(tmp_path):
    base=Client();client=detail.PublicFixedSideDetailClient(base,tmp_path)
    send(client,tmp_path,0)
    previous,_,_=send(client,tmp_path,1)
    assert previous['historical_input_policy']['supplied_roles']==[['previous_distinct_wrist']]
    current_reference,_,_=send(client,tmp_path,2,forces=(.2,.2))
    assert current_reference['historical_images_inserted']==0
    assert current_reference['total_image_count']==3
    later,_,_=send(client,tmp_path,3)
    assert later['historical_input_policy']['supplied_roles']==[['previous_distinct_wrist','first_public_bilateral_wrist']]
    final,_,_=send(client,tmp_path,4)
    assert final['historical_input_policy']['supplied_roles']==[['first_public_bilateral_wrist']]
    assert final['historical_references'][0]['source_decision_index']==2


def test_repeated_observation_and_new_episode_keep_current_detail_without_resetting_old_evidence(tmp_path):
    base=Client();client=detail.PublicFixedSideDetailClient(base,tmp_path)
    first,*_=send(client,tmp_path,0,step=0,forces=(.2,.2))
    duplicate,*_=send(client,tmp_path,1,step=0,forces=(.3,.3))
    next_obs,*_=send(client,tmp_path,2,step=1)
    assert duplicate['current_observation_is_duplicate_id'] is True
    assert duplicate['first_public_bilateral_reference']['source_decision_index']==0
    assert next_obs['previous']['source_decision_index']==0
    assert next_obs['historical_references'][0]['reference_roles']==['previous_distinct_wrist','first_public_bilateral_wrist']
    new,*_=send(client,tmp_path,3,step=0,episode='e2')
    assert new['total_image_count']==3 and new['previous'] is None
    assert new['first_public_bilateral_reference'] is None
    assert new['fixed_side_detail']['metadata']['episode_id']=='e2'
    assert len(list((tmp_path/'temporal_visual_context').glob('decision_*')))==4


@pytest.mark.parametrize('damage',['shape','mount','rotation','intrinsic','saved_JPEG'])
def test_wrong_camera_or_source_fails_before_delegation(tmp_path,damage):
    base=Client();client=detail.PublicFixedSideDetailClient(base,tmp_path)
    items,label=request(client,tmp_path,0,width=639 if damage=='shape' else 640)
    if damage=='saved_JPEG':
        (tmp_path/'observations/decision_000000/side_camera.jpg').write_bytes(b'bad')
    elif damage!='shape':
        state=json.loads(items[-1]['content'][0]['text'])
        if damage=='mount':state['camera_meta']['side_camera']['local_pose_position_m'][2]=1.65
        elif damage=='rotation':state['camera_meta']['side_camera']['local_pose_quaternion_wxyz']=[1,0,0,0]
        else:state['model_image_transforms']['side_camera']['intrinsic_matrix_transmitted'][0][0]=float('nan')
        items[-1]['content'][0]['text']=json.dumps(state)
        (tmp_path/'observations/decision_000000/public_observation.json').write_text(items[-1]['content'][0]['text'])
    with pytest.raises(ProviderError):client.responses(items,instructions='CPU',label=label)
    assert not base.calls


def test_private_memory_remains_live_but_is_not_persisted_and_detail_still_has_exact_SHA(tmp_path):
    base=Client();client=detail.PublicFixedSideDetailClient(base,tmp_path)
    send(client,tmp_path,0)
    history=[dict(type='reasoning',id='private',summary=[dict(text='SECRET_PRIVATE_SENTINEL')]),
        dict(type='function_call',call_id='c',name='wait',arguments='{}'),
        dict(type='function_call_output',call_id='c',output='{"accepted":true}')]
    record,path,_=send(client,tmp_path,1,history=history)
    assert base.calls[-1][0][1:4]==history
    assert record['exact_full_input_reconstructable'] is False
    assert record['private_provider_items_redacted'][0]['input_item_index']==1
    assert 'SECRET_PRIVATE_SENTINEL' not in path.read_text()
    with pytest.raises(ValueError):reconstruct_input_items(path)
    assert canonical_hash(base.calls[-1][0])==record['full_wire_input_canonical_sha256']


def test_unexpected_truth_is_rejected_before_packet_or_client(tmp_path):
    base=Client();client=detail.PublicFixedSideDetailClient(base,tmp_path)
    items,label=request(client,tmp_path,0)
    state=json.loads(items[-1]['content'][0]['text'])
    state['object_position_m']=[100.,200.,300.]
    items[-1]['content'][0]['text']=json.dumps(state)
    with pytest.raises(ProviderError,match='INVALID_TEMPORAL_PUBLIC_OBSERVATION'):
        client.responses(items,instructions='CPU',label=label)
    assert not base.calls
    assert not list((tmp_path/'temporal_visual_context').glob('decision_*'))


def test_packet_collision_does_not_overwrite_previous_detail(tmp_path):
    base=Client();client=detail.PublicFixedSideDetailClient(base,tmp_path)
    _,path,items=send(client,tmp_path,0)
    before=path.read_bytes();image=(path.parent/'current_side_detail.jpg').read_bytes()
    second=detail.PublicFixedSideDetailClient(base,tmp_path)
    with pytest.raises(ProviderError):
        second.responses(items,instructions='CPU',label='CPU:e1:decision0')
    assert path.read_bytes()==before and (path.parent/'current_side_detail.jpg').read_bytes()==image
    assert len(base.calls)==1


@pytest.mark.parametrize('profile_name',['cubence_gpt6_context4_640high.json','cubence_gpt6_context4_640high_temporal.json'])
def test_P4_and_P6_actual_payloads_match_frozen58da_without_detail(profile_name,tmp_path,monkeypatch):
    """Compare wire body, not source-derived controller metadata SHA."""
    from policy.backends import cubence_project_v1_1_tools as current
    source=subprocess.check_output(['git','show','58da857e14a0a1152884e13984607a286547a046:policy/backends/cubence_project_v1_1_tools.py'],cwd=ROOT,text=True)
    frozen_file=tmp_path/'frozen/cubence_project_v1_1_tools.py';frozen_file.parent.mkdir()
    frozen_file.write_text(source)
    frozen_file.with_name('cubence_project_v1_1_visual_context.py').write_bytes((ROOT/'policy/backends/cubence_project_v1_1_visual_context.py').read_bytes())
    module=types.ModuleType('policy.backends._frozen_P6_test');module.__package__='policy.backends';module.__file__=str(frozen_file)
    exec(compile(source,str(frozen_file),'exec'),module.__dict__)
    cfg=load_config(PROFILE.with_name(profile_name));all_bodies=[]
    monkeypatch.setenv('CUBENCE_API_KEY','CPU-P6-comparison')
    for i,runner in enumerate((module.run_episode,current.run_episode)):
        env=helpers.ReceiptEnvironment();replies=[helpers.reply('wait',helpers.args(env),0),helpers.reply('finish',dict(episode_id='e1',observation_id='e1:60',reason='CPU end'),1)]
        opener=helpers._Opener(replies);client=CubenceClient(cfg,BudgetLedger(tmp_path/f'budget{i}.json',cfg),opener=opener,sleeper=lambda _:None)
        runner(env,client,tmp_path/f'episode{i}',max_calls=2)
        all_bodies.append(opener.bodies)
    assert all_bodies[0]==all_bodies[1]


def test_opt_in_runner_calls_shared_runner_not_old_dispatch(monkeypatch,tmp_path):
    base=Client();captured={}
    monkeypatch.setattr(detail,'_run_episode',lambda env,client,out,**kw:captured.update(client=client,kwargs=kw) or 'CPU')
    assert detail.run_episode(object(),base,tmp_path,max_calls=3)=='CPU'
    assert isinstance(captured['client'],detail.PublicFixedSideDetailClient)
    assert captured['kwargs']['prompt']==detail.SYSTEM_PROMPT
    assert captured['kwargs']['tools_class']==detail.ProjectV11FixedSideDetailTools
    meta=detail.ProjectV11FixedSideDetailTools.controller_metadata()
    assert meta['prompt_version']=='Project_v1_1.public_tools.v7_fixed_side_detail'
    assert meta['fixed_side_detail_profile']['max_side_px']==480


def test_public_old_runner_dispatches_P7_and_all_images_reach_single_fake_transport(monkeypatch,tmp_path):
    from policy.backends.cubence_project_v1_1_tools import run_episode as public_runner
    class PublicCameraEnvironment(helpers.ReceiptEnvironment):
        def observe(self):
            result=super().observe()
            result['images']={name:np.zeros((480,640,3),dtype=np.uint8) for name in ('side_camera','wrist_camera')}
            camera=dict(physical_parent='/World',
                local_pose_position_m=detail.FIXED_SIDE_DETAIL['expected_local_position_m'],
                local_pose_quaternion_wxyz=detail.FIXED_SIDE_DETAIL['expected_local_quaternion_wxyz'],
                intrinsic_matrix_native=[[500.,0.,320.],[0.,500.,240.],[0.,0.,1.]])
            result['camera_meta']={name:camera for name in ('side_camera','wrist_camera')}
            return result
    env=PublicCameraEnvironment();cfg=load_config(PROFILE)
    replies=[helpers.reply('wait',helpers.args(env),0),helpers.reply('finish',
        dict(episode_id='e1',observation_id='e1:60',reason='CPU end'),1)]
    opener=helpers._Opener(replies)
    monkeypatch.setenv('CUBENCE_API_KEY','CPU-P7-only')
    ledger=BudgetLedger(tmp_path/'budget.json',cfg)
    client=CubenceClient(cfg,ledger,opener=opener,sleeper=lambda _:None)
    result=public_runner(env,client,tmp_path/'episode',max_calls=2)
    assert result['api_decisions']==2 and result['network_attempts_this_episode']==2
    assert result['task_result']['task_success'] is None  # CPU finish is not physical success.
    assert len(opener.bodies)==2 and len(env.executions)==1
    assert opener.bodies[0]['instructions'].startswith(detail.SYSTEM_PROMPT)
    assert opener.bodies[0]['tools']==tool_definitions()
    metadata=json.loads((tmp_path/'episode/controller.json').read_text())
    assert metadata['provider_config']['max_context_messages']==2
    assert metadata['controller_extension']['prompt_version']=='Project_v1_1.public_tools.v7_fixed_side_detail'
    final=tmp_path/'episode/temporal_visual_context/decision_000001/input_items_manifest.json'
    packet=json.loads(final.read_text())
    assert packet['total_image_count']==4 and packet['historical_images_inserted']==1
    assert packet['current']['observation_id']=='e1:60'
    assert json.loads(opener.bodies[-1]['input'][-1]['content'][0]['text'])['observation_id']=='e1:60'
    assert reconstruct_input_items(final)==opener.bodies[-1]['input']
    assert 'PRIVILEGED_SENTINEL' not in json.dumps(opener.bodies)


def test_explicit_reset_does_not_overwrite_packets_or_preserve_stale_history(tmp_path):
    base=Client();client=detail.PublicFixedSideDetailClient(base,tmp_path)
    send(client,tmp_path,0,forces=(.2,.2))
    old=(tmp_path/'temporal_visual_context/decision_000000/input_items_manifest.json').read_bytes()
    client.reset()
    fresh,_,_=send(client,tmp_path,1,step=0,forces=(0.,0.))
    assert fresh['previous'] is None and fresh['first_public_bilateral_reference'] is None
    assert fresh['total_image_count']==3
    assert (tmp_path/'temporal_visual_context/decision_000000/input_items_manifest.json').read_bytes()==old


def test_closed_public_preview_is_portable_and_never_creates_real_client(tmp_path):
    base=Client();source=tmp_path/'source/episode_0000/gpt_control'
    for i in range(4):request(base,source,i,forces=(.2,.2) if i==1 else (0.,0.))
    proof=source.parent.parent/'process_exit.json';proof.write_text(json.dumps(dict(
        process_exited=True,exit_code=0,pid=99999999,run_directory=str(source.parent.parent))))
    before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in source.rglob('*') if p.is_file()}
    result=detail.preview_closed_public(source,tmp_path/'preview',current_decision=3)
    assert result['API_sent'] is False and result['actual_network_attempts']==0
    assert result['total_images']==4 and result['original_sources_unchanged'] is True
    assert result['original_client_input_token_bound']<80000
    final=tmp_path/'preview'/result['final_manifest'];assert len(reconstruct_input_items(final)[-1]['content'])==5
    assert len(list((tmp_path/'preview/observations').iterdir()))==1
    assert len(list((tmp_path/'preview/temporal_visual_context').iterdir()))==1
    assert {str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in source.rglob('*') if p.is_file()}==before
    with pytest.raises(FileExistsError):detail.preview_closed_public(source,tmp_path/'preview',current_decision=3)


@pytest.mark.parametrize('identity',['missing','wrong_run','conflicting_command','duplicate_command'])
def test_preview_closed_proof_must_identify_this_run(tmp_path,identity):
    source=tmp_path/'source/episode_0000/gpt_control';source.mkdir(parents=True)
    proof=dict(process_exited=True,exit_code=0,pid=99999999)
    if identity=='wrong_run':proof['run_directory']=str(tmp_path/'other')
    if identity=='conflicting_command':
        proof.update(run_directory=str(source.parent.parent),command=['python','--output',str(tmp_path/'other')])
    if identity=='duplicate_command':
        proof['command']=['python','--output',str(source.parent.parent),'--output',str(tmp_path/'other')]
    path=tmp_path/'closed_other.json';path.write_text(json.dumps(proof))
    with pytest.raises(ValueError,match='does not identify'):
        detail.preview_closed_public(source,tmp_path/'preview',current_decision=0,source_process_proof=path)
    assert not (tmp_path/'preview').exists()


@pytest.mark.parametrize('equals',[False,True])
def test_closed_proof_can_use_matching_native_command_when_run_directory_absent(tmp_path,equals):
    source=tmp_path/'source/episode_0000/gpt_control';source.mkdir(parents=True)
    command=['python', '--output='+str(source.parent.parent)] if equals else ['python','--output',str(source.parent.parent)]
    proof=tmp_path/'closed.json';proof.write_text(json.dumps(dict(process_exited=True,exit_code=0,
        pid=99999999,command=command)))
    assert detail._closed_source_proof(source.resolve(),proof)['exit_code']==0


def test_preview_cannot_create_new_folder_anywhere_inside_the_closed_run(tmp_path):
    source=tmp_path/'source/episode_0000/gpt_control';source.mkdir(parents=True)
    with pytest.raises(ValueError,match='entire source run'):
        detail.preview_closed_public(source,source.parent/'preview',current_decision=0)
    assert not (source.parent/'preview').exists()


@pytest.mark.parametrize('old_size,new_size',[(0,0),(20,7000),(7000,20),(1800,2600)])
def test_private_bound_residual_encloses_actual_retained_item_without_its_content(old_size,new_size):
    path=ROOT/'docs/lab_cuvette_loading/Project_v1_1/validation/public_fixed_side_detail_p7_20261027/audit_context2_bounds.py'
    spec=importlib.util.spec_from_file_location('P7_bound_audit',path)
    audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)
    private=[dict(type='reasoning',id='r0',encrypted_content='x'*old_size),
        dict(type='reasoning',id='r1',encrypted_content='y'*new_size)]
    placeholders=[dict(type='private_provider_item_not_persisted',original_type='reasoning',
        canonical_sha256=canonical_hash(item)) for item in private]
    turn=lambda index:[dict(type='function_call',call_id=str(index),name='wait',arguments='{}'),
        dict(type='function_call_output',call_id=str(index),output='{"accepted":true}')]
    old=[dict(role='user',content='Task'),private[0],*turn(0),private[1],*turn(1),dict(role='user',content='Current')]
    projected=copy.deepcopy(old);projected[1]=placeholders[0];projected[4]=placeholders[1]
    latest,selected=audit.latest_turn(projected)
    candidate=[projected[0],*latest,dict(role='user',content='Fixed detail'),projected[-1]]
    actual=copy.deepcopy(candidate);actual[1]=private[1]
    bound=lambda items:input_token_bound(dict(model='gpt-6-astra',input=items),1000000)
    interval=audit.private_range(bound(old),bound(projected),projected,selected,bound(candidate))
    assert interval['lower']<=bound(actual)<=interval['upper']
    assert interval['kept']==[4] and interval['removed']==[1]
