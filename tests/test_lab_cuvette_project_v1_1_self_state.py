"""Robot-self FK and P9 protocol tests; no API/GPU/native-task claims."""
import base64
import copy
import hashlib
import importlib.util
import inspect
import json
import math
from pathlib import Path

import numpy as np
import pytest

from policy import robot_self_kinematics as kin
from policy.backends import cubence_project_v1_1_self_state as selfstate
from policy.backends import cubence_project_v1_1_active_view as active
from policy.backends import cubence_project_v1_1_side_detail as detail
from policy.backends.cubence import BudgetLedger,CubenceClient,ProviderError,canonical_hash,load_config,input_token_bound
from policy.backends.cubence_project_v1_1_tools import run_episode as public_runner
from policy.backends.cubence_project_v1_1_visual_context import reconstruct_input_items
from policy.backends.cubence_tools import observation_content,save_observation_artifacts

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('p9_active_helpers',ROOT/'tests/test_lab_cuvette_project_v1_1_active_view.py')
helpers=importlib.util.module_from_spec(spec);spec.loader.exec_module(helpers)
PROFILE=selfstate.DEFAULT_PROFILE
Q=[.31,-.58,.42,-1.92,.27,1.46,-.38]


def mdh(q):
    """Independent modified-DH reference; no numeric model/parser reuse."""
    alpha=[0,-math.pi/2,math.pi/2,math.pi/2,-math.pi/2,math.pi/2,math.pi/2]
    a=[0,0,0,.0825,-.0825,0,.088];d=[.333,0,.316,0,.384,0,0]
    result={};t=np.eye(4)
    for i,(angle,al,aa,dd) in enumerate(zip(q,alpha,a,d),1):
        c,s=math.cos(angle),math.sin(angle);ca,sa=math.cos(al),math.sin(al)
        t=t@np.array([[c,-s,0,aa],[s*ca,c*ca,-sa,-dd*sa],[s*sa,c*sa,ca,dd*ca],[0,0,0,1.]])
        result[f'panda_link{i}']=t.copy()
    link8=np.eye(4);link8[2,3]=.107
    c,s=math.cos(-math.pi/4),math.sin(-math.pi/4)
    hand=np.array([[c,-s,0,0],[s,c,0,0],[0,0,1,0],[0,0,0,1.]])
    result['panda_hand']=t@link8@hand
    tcp=np.diag([-1.,-1.,1.,1.]);tcp[2,3]=.1
    result['right_gripper']=result['panda_hand']@tcp
    return result


def quat(r):
    # Test input uses independent scipy conversion, not production wxyz code.
    from scipy.spatial.transform import Rotation
    q=Rotation.from_matrix(r).as_quat();return [q[3],q[0],q[1],q[2]]


@pytest.mark.parametrize('q',[Q,[0,-math.pi/4,0,-math.pi/2,0,math.pi/2,math.pi/4],[-.8,.22,-.45,-2.41,-.27,2.3,.7]])
def test_numeric_FK_agrees_with_independent_modified_DH_for_nontrivial_poses(q):
    actual=kin.forward_local(q,kin.load_model());reference=mdh(q)
    for name in (*kin.FRAMES,'right_gripper'):
        np.testing.assert_allclose(actual[name],reference[name],atol=3e-11,rtol=0)


def test_world_anchor_and_noncommuting_orientation_preserve_own_link_frames():
    from scipy.spatial.transform import Rotation
    base=np.eye(4);base[:3,:3]=Rotation.from_euler('zyx',[.48,-.31,.27]).as_matrix();base[:3,3]=[.4,-.2,.77]
    ref=mdh(Q);tcp=base@ref['right_gripper']
    value=kin.derive_robot_self_state(Q,dict(position_m=tcp[:3,3].tolist(),quaternion_wxyz=quat(tcp[:3,:3])),
        episode_id='test',observation_id='test:5',simulation_time=.2)
    for name in kin.FRAMES:
        expected=base@ref[name];row=value['frames'][name]
        np.testing.assert_allclose(row['position_m'],expected[:3,3],atol=6e-9,rtol=0)
        np.testing.assert_allclose(kin._quat_matrix(row['quaternion_wxyz']),expected[:3,:3],atol=2e-8,rtol=0)
    assert value['hand_to_TCP']==dict(translation_m=[0,0,.1],quaternion_wxyz=[0,0,0,1])
    assert value['obstacle_or_held_object_state_included'] is False and value['cooked_shape_verified'] is False


@pytest.mark.parametrize('bad',[None,[0]*6,[0]*8,[True,*Q[1:]],[float('nan'),*Q[1:]],[float('inf'),*Q[1:]],[99,*Q[1:]]])
def test_invalid_or_unbounded_public_joint_vector_fails_closed(bad):
    with pytest.raises((ValueError,TypeError)):
        kin.derive_robot_self_state(bad,dict(position_m=[0,0,1],quaternion_wxyz=[1,0,0,0]),episode_id='e',observation_id='e:0',simulation_time=0)


@pytest.mark.parametrize('bad',[[2,0,0,0],[0,0,0,0],[float('nan'),0,0,0],[True,0,0,0]])
def test_nonunit_or_invalid_quaternion_is_not_silently_used(bad):
    with pytest.raises(ValueError):kin.derive_robot_self_state(Q,dict(position_m=[0,0,1],quaternion_wxyz=bad),episode_id='e',observation_id='e:0',simulation_time=0)


def test_regeneration_is_byte_identical_and_runtime_needs_no_URDF_or_USD(tmp_path,monkeypatch):
    fixture=ROOT/'tests/fixtures/lab_cuvette_project_v1_1/robot_self'
    value=kin.generate_numeric_model(fixture/'lula_franka_gen.source.xml',fixture/'robot_local_boxes.source.json')
    raw=(json.dumps(value,indent=2,allow_nan=False)+'\n').encode()
    assert hashlib.sha256(raw).hexdigest()==kin.MODEL_SHA256
    portable=tmp_path/'model.json';portable.write_bytes(raw)
    monkeypatch.setattr(kin.ET,'fromstring',lambda *a,**k:pytest.fail('Runtime attempted URDF parse'))
    model=kin.load_model(portable)
    assert kin.derive_robot_self_state(Q,dict(position_m=[0,0,1],quaternion_wxyz=[1,0,0,0]),
        episode_id='e',observation_id='e:0',simulation_time=0,model=model)['frames']
    model['joints'][0]['origin_xyz_m'][0]=.1
    with pytest.raises(ValueError,match='content mismatch'):
        kin.derive_robot_self_state(Q,dict(position_m=[0,0,1],quaternion_wxyz=[1,0,0,0]),episode_id='e',observation_id='e:0',simulation_time=0,model=model)


class Environment(helpers.Environment):
    def observe(self):
        value=super().observe();value['joint_positions']=Q+[.0053,.0053]
        return value


def run_fake(profile,output,monkeypatch,runner=public_runner):
    env=Environment();cfg=load_config(profile)
    replies=[helpers.helpers.helpers.reply('wait',helpers.helpers.helpers.args(env),0),helpers.helpers.helpers.reply('finish',
        dict(episode_id='e1',observation_id='e1:60',reason='CPU stop'),1)]
    opener=helpers.helpers.helpers._Opener(replies);monkeypatch.setenv('CUBENCE_API_KEY','CPU-only-placeholder')
    ledger=BudgetLedger(output.with_name(output.name+'_budget.json'),cfg);client=CubenceClient(cfg,ledger,opener=opener,sleeper=lambda _:None)
    result=runner(env,client,output,max_calls=2)
    return env,opener,ledger,result,json.loads((output/'controller.json').read_text())


def test_profile_only_adds_selfstate_and_caps_old_modules_stay_frozen():
    cfg=load_config(PROFILE);base=load_config(helpers.PROFILE)
    assert cfg.pop('robot_self_state')==selfstate.ROBOT_SELF_STATE and cfg==base
    assert inspect.signature(selfstate.run_episode).parameters['max_calls'].default==160
    for file,digest in [('policy/backends/cubence_project_v1_1_active_view.py','bc726756a1873eaf0da22f575d2c6b0f5bd7f1976ae183670746750caeec5843'),
        ('policy/backends/cubence_project_v1_1_side_detail.py','4f1b481fb3e724252beeb9c8453f20914e744ecfa94aeb9054c85110c4596061'),
        (str(helpers.PROFILE.relative_to(ROOT)),'3679ae68f23f52fc53f4306d3896be6ad1492bb3a3a276d73a5700334b01bd92')]:
        assert hashlib.sha256((ROOT/file).read_bytes()).hexdigest()==digest


@pytest.mark.parametrize('bad',[None,False,{},dict(selfstate.ROBOT_SELF_STATE,enabled=False),dict(selfstate.ROBOT_SELF_STATE,object_truth=True)])
def test_optin_is_strict_and_before_any_provider_call_or_action(bad,tmp_path):
    base=helpers.helpers.Client();base.cfg=load_config(PROFILE);base.cfg['robot_self_state']=bad
    with pytest.raises(ProviderError,match='INVALID_ROBOT_SELF_STATE_CONFIG'):selfstate.run_episode(object(),base,tmp_path/'bad')
    assert not base.calls and not (tmp_path/'bad').exists()


def test_actual_fake_wire_adds_only_current_robot_text_and_generic_prompt(monkeypatch,tmp_path):
    _,old,_,_,_=run_fake(helpers.PROFILE,tmp_path/'P8',monkeypatch)
    env,new,ledger,result,controller=run_fake(PROFILE,tmp_path/'P9',monkeypatch)
    assert len(new.bodies)==ledger.summary()['total_network_attempts']==2 and len(env.executions)==1
    for prior,body in zip(old.bodies,new.bodies):
        prior=copy.deepcopy(prior);body=copy.deepcopy(body)
        assert body.pop('instructions')==selfstate.SYSTEM_PROMPT+'\nAction limits: '+json.dumps(load_config(PROFILE)['action_limits'])
        prior.pop('instructions')
        group=body['input'].pop(-2);assert group['content'][0]['text'].startswith('CURRENT ROBOT SELF-STATE\n')
        value=json.loads(group['content'][0]['text'].split('\n',1)[1]);assert set(value['frames'])==set(kin.FRAMES)
        assert body==prior
        assert 'PRIVILEGED_SENTINEL' not in json.dumps(body) and 'object_position_m' not in json.dumps(value)
    extension=controller['controller_extension'];assert extension['prompt_version']=='Project_v1_1.public_tools.v9_robot_self_state'
    assert extension['actual_request_instructions_SHA256']==hashlib.sha256(new.bodies[0]['instructions'].encode()).hexdigest()
    manifest=tmp_path/'P9/temporal_visual_context/decision_000001/input_items_manifest.json';record=json.loads(manifest.read_text())
    assert record['current_user_item_index']==len(new.bodies[1]['input'])-1
    assert record['total_image_count']==4 and record['robot_self_user_item_index']==len(new.bodies[1]['input'])-2
    assert reconstruct_input_items(manifest)==new.bodies[1]['input']
    assert record['pre_robot_self_manifest']['sha256']==hashlib.sha256((manifest.parent/'pre_robot_self_input_items_manifest.json').read_bytes()).hexdigest()


@pytest.mark.parametrize('profile,runner',[('P8',active.run_episode),('P7',detail.run_episode)])
def test_old_public_dispatch_wire_matches_unchanged_direct_runners(profile,runner,monkeypatch,tmp_path):
    path=helpers.PROFILE if profile=='P8' else detail.DEFAULT_PROFILE
    _,a,_,_,_=run_fake(path,tmp_path/'public',monkeypatch)
    _,b,_,_,_=run_fake(path,tmp_path/'direct',monkeypatch,runner=runner)
    assert a.bodies==b.bodies


def test_prompt_never_supplies_task_route_and_retains_contact_slip_rules():
    assert selfstate.SYSTEM_PROMPT.startswith(active.SYSTEM_PROMPT)
    for text in ('Missing support before contact is expected','incrementally','Do not release before actual support','no evidenced safe local action'):
        assert text in selfstate.SELF_STATE_PROMPT
    for text in ('SourceMesh','candidate_far_hinge','world +','world -','safe height','waypoint','move_ee(','.04','0.1 mm','teacher'):
        assert text not in selfstate.SELF_STATE_PROMPT
    assert set(selfstate.ProjectV11RobotSelfStateTools.__dict__)-{'__module__','__doc__','controller_metadata'}==set()


def send_direct(client,output,index,*,episode='e',step=None,forces=(.2,.2),history=(),bad_q=False):
    step=index if step is None else step
    obs=Environment().observe();obs.update(episode_id=episode,observation_id=f'{episode}:{step}',step_index=step,
        simulation_time=step/60,finger_contact_N=list(forces),object_position_m='POISON_OBJECT',
        teacher_phase='POISON_TEACHER',scorer={'depth':'POISON_SCORE'})
    if bad_q:obs['joint_positions'][0]=float('inf')
    contents=observation_content(obs,image_config=client.cfg['images'])
    label=f'CPU:{episode}:decision{index}';save_observation_artifacts(contents,output,index,label)
    items=[*copy.deepcopy(history),dict(role='user',content=contents)]
    before=copy.deepcopy(items)
    client.responses(items,instructions='CPU',label=label,deadline_monotonic=123.)
    assert items==before
    folder=output/'temporal_visual_context'/f'decision_{index:06d}'
    return json.loads((folder/'input_items_manifest.json').read_text()),folder,items


def test_public_only_poison_is_not_read_and_private_memory_is_redacted_not_removed_from_live(tmp_path):
    base=helpers.helpers.Client();base.cfg=load_config(PROFILE);client=selfstate.PublicRobotSelfStateClient(base,tmp_path)
    private=dict(type='reasoning',id='private',summary=[dict(type='summary_text',text='DO_NOT_PERSIST_PRIVATE')])
    packet,folder,items=send_direct(client,tmp_path,0,history=[private])
    assert base.calls[0][0][0]==private and base.calls[0][1]['deadline_monotonic']==123.
    assert packet['private_provider_items_redacted'][0]['input_item_index']==0
    assert packet['exact_full_input_reconstructable'] is False
    assert canonical_hash(base.calls[0][0])==packet['full_wire_input_canonical_sha256']
    saved=''.join(p.read_text() for p in folder.glob('*.json'))
    for poison in ('DO_NOT_PERSIST_PRIVATE','POISON_OBJECT','POISON_TEACHER','POISON_SCORE'):
        assert poison not in saved
    with pytest.raises(ValueError,match='Hidden/opaque'):reconstruct_input_items(folder/'input_items_manifest.json')


def test_repeated_observation_and_new_episode_keep_current_ids_and_reset_history(tmp_path):
    base=helpers.helpers.Client();base.cfg=load_config(PROFILE);client=selfstate.PublicRobotSelfStateClient(base,tmp_path)
    first,_,_=send_direct(client,tmp_path,0,forces=(0.,0.))
    second,_,_=send_direct(client,tmp_path,1,step=0,forces=(0.,0.))
    third,_,_=send_direct(client,tmp_path,2,step=1)
    reset,folder,_=send_direct(client,tmp_path,3,episode='new',step=0,forces=(0.,0.))
    assert second['current_observation_is_duplicate_id'] is True
    assert reset['historical_references']==[] and reset['previous'] is None
    assert reset['total_image_count']==3 and len(base.calls)==4
    current=json.loads(base.calls[-1][0][-2]['content'][0]['text'].split('\n',1)[1])
    assert current['episode_id']=='new' and current['observation_id']=='new:0'
    assert len(base.calls[-1][0][-1]['content'])==5


def test_local_selfstate_text_is_in_original_budget_reservation_before_one_HTTP(monkeypatch,tmp_path):
    env,opener,ledger,_,_=run_fake(PROFILE,tmp_path/'budget',monkeypatch)
    entries=json.loads(ledger.path.read_text())['attempts']
    for body,entry in zip(opener.bodies,entries):
        assert entry['reservation_input_tokens']==input_token_bound(body,80000)
        without=copy.deepcopy(body);without['input'].pop(-2)
        assert entry['reservation_input_tokens']>input_token_bound(without,80000)
    assert len(entries)==len(opener.bodies)==2 and len(env.executions)==1


def test_P9_context_bound_failure_is_before_HTTP_and_does_not_execute(monkeypatch,tmp_path):
    env=Environment();cfg=load_config(PROFILE);cfg['max_context_input_tokens']=1000
    opener=helpers.helpers.helpers._Opener([]);monkeypatch.setenv('CUBENCE_API_KEY','CPU-only-placeholder')
    ledger=BudgetLedger(tmp_path/'bound_budget.json',cfg);client=CubenceClient(cfg,ledger,opener=opener,sleeper=lambda _:None)
    result=public_runner(env,client,tmp_path/'bounded',max_calls=2)
    assert not opener.bodies and not env.executions
    assert result['backend_error_code']=='LOCAL_CONTEXT_TOKEN_BOUND_EXCEEDED'
    assert result['backend_failure_type']=='INPUT_CONTRACT_ERROR'
    record=json.loads((tmp_path/'bounded/temporal_visual_context/decision_000000/input_items_manifest.json').read_text())
    assert record['robot_self_state']['model_SHA256']==kin.MODEL_SHA256
