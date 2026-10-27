"""P8 CPU/fake transport; no model, task-success or geometry claims."""
import copy
import hashlib
import importlib.util
import inspect
import json
from pathlib import Path

import numpy as np
import pytest

from policy.backends import cubence_project_v1_1_active_view as active
from policy.backends import cubence_project_v1_1_side_detail as detail
from policy.backends.cubence import BudgetLedger,CubenceClient,ProviderError,load_config
from policy.backends.cubence_tools import tool_definitions
from policy.backends.cubence_project_v1_1_tools import run_episode as public_runner

ROOT=Path(__file__).resolve().parents[1]
PROFILE=ROOT/'config/lab_cuvette_loading/Project_v1_1/policies/cubence_gpt6_context2_640high_temporal_detail_active_view.json'
spec=importlib.util.spec_from_file_location('active_view_helpers',ROOT/'tests/test_lab_cuvette_project_v1_1_side_detail.py')
helpers=importlib.util.module_from_spec(spec);spec.loader.exec_module(helpers)


class Environment(helpers.helpers.ReceiptEnvironment):
    def observe(self):
        value=super().observe()
        value['images']={name:np.zeros((480,640,3),dtype=np.uint8) for name in ('side_camera','wrist_camera')}
        camera=dict(physical_parent='/World',
            local_pose_position_m=detail.FIXED_SIDE_DETAIL['expected_local_position_m'],
            local_pose_quaternion_wxyz=detail.FIXED_SIDE_DETAIL['expected_local_quaternion_wxyz'],
            intrinsic_matrix_native=[[500.,0.,320.],[0.,500.,240.],[0.,0.,1.]])
        value['camera_meta']={name:camera for name in ('side_camera','wrist_camera')}
        return value


def run_fake(profile,output,monkeypatch,runner=public_runner,prompt=None):
    env=Environment();cfg=load_config(profile)
    replies=[helpers.helpers.reply('wait',helpers.helpers.args(env),0),helpers.helpers.reply('finish',
        dict(episode_id='e1',observation_id='e1:60',reason='CPU stop'),1)]
    opener=helpers.helpers._Opener(replies)
    monkeypatch.setenv('CUBENCE_API_KEY','CPU-active-view-placeholder')
    ledger=BudgetLedger(output.with_name(output.name+'_budget.json'),cfg)
    client=CubenceClient(cfg,ledger,opener=opener,sleeper=lambda _:None)
    kwargs={} if prompt is None else {'prompt':prompt}
    result=runner(env,client,output,max_calls=2,**kwargs)
    return env,opener,ledger,result,json.loads((output/'controller.json').read_text())


def test_P8_profile_only_adds_explicit_prompt_policy_and_retains_all_limits():
    cfg=load_config(PROFILE);base=load_config(detail.DEFAULT_PROFILE)
    assert cfg.pop('active_view_control')==active.ACTIVE_VIEW_CONTROL
    assert cfg==base
    assert cfg['max_requests']==1500 and cfg['max_estimated_usd']==30
    assert cfg['max_output_tokens']==1024 and cfg['reasoning_effort']=='low'
    assert cfg['max_context_messages']==2 and cfg['max_context_input_tokens']==80000
    assert inspect.signature(active.run_episode).parameters['max_calls'].default==160
    assert hashlib.sha256((ROOT/'policy/backends/cubence_project_v1_1_side_detail.py').read_bytes()).hexdigest()=='4f1b481fb3e724252beeb9c8453f20914e744ecfa94aeb9054c85110c4596061'
    assert hashlib.sha256(detail.DEFAULT_PROFILE.read_bytes()).hexdigest()=='559e5fdd10383c810728c90a34426e807695a9fdca32dcf8f6c8b57e51f93318'


@pytest.mark.parametrize('bad',[None,False,{},dict(active.ACTIVE_VIEW_CONTROL,enabled=False),
    dict(active.ACTIVE_VIEW_CONTROL,hidden_route=True),dict(active.ACTIVE_VIEW_CONTROL,scope='automatic_action')])
def test_invalid_optin_fails_before_client_or_execution(bad,tmp_path):
    base=helpers.Client();base.cfg=load_config(PROFILE);base.cfg['active_view_control']=bad
    with pytest.raises(ProviderError,match='INVALID_ACTIVE_VIEW_CONTROL'):
        active.run_episode(object(),base,tmp_path/'episode')
    assert not base.calls and not (tmp_path/'episode').exists()


def test_prompt_is_generic_local_information_gathering_without_forced_motion():
    text=active.ACTIVE_VIEW_PROMPT
    assert active.SYSTEM_PROMPT.startswith(detail.SYSTEM_PROMPT)
    for fact in ('whole moving arm','conservative reversible','stationary observe',
            'no safe local action','safety stop/anomaly','without release'):
        assert fact in text
    for forbidden in ('SourceMesh','candidate_far_hinge','0.04','0.005','safe height',
            'world +','world -','seat_position','object_position','teacher','step 1','three moves'):
        assert forbidden not in text
    assert 'execute' not in active.PublicActiveViewClient.__dict__
    assert set(active.ProjectV11ActiveViewRobotTools.__dict__)-{'__module__','__doc__','controller_metadata'}==set()


def test_P8_client_image_history_projection_is_identical_to_P7(tmp_path):
    bodies=[]
    for cls,profile,name in ((detail.PublicFixedSideDetailClient,detail.DEFAULT_PROFILE,'P7'),
                            (active.PublicActiveViewClient,PROFILE,'P8')):
        base=helpers.Client();base.cfg=load_config(profile);client=cls(base,tmp_path/name)
        for i,forces in enumerate(((0.,0.),(.2,.2),(.2,.2),(.2,.2))):
            packet,_,_=helpers.send(client,tmp_path/name,i,forces=forces)
        assert packet['total_image_count']==4 and packet['historical_images_inserted']==1
        bodies.append(base.calls)
    assert bodies[0]==bodies[1]


def test_public_runner_uses_P8_once_and_saves_actual_prompt_identity(monkeypatch,tmp_path):
    env,opener,ledger,result,controller=run_fake(PROFILE,tmp_path/'P8',monkeypatch)
    assert len(opener.bodies)==ledger.summary()['total_network_attempts']==2
    assert len(env.executions)==1 and result['task_result']['task_success'] is None
    extension=controller['controller_extension']
    assert extension['prompt_version']=='Project_v1_1.public_tools.v8_active_view'
    assert extension['active_view_control']==active.ACTIVE_VIEW_CONTROL
    assert controller['prompt']==active.SYSTEM_PROMPT
    assert extension['actual_system_prompt_SHA256']==hashlib.sha256(controller['prompt'].encode()).hexdigest()
    assert extension['actual_request_instructions_SHA256']==hashlib.sha256(opener.bodies[0]['instructions'].encode()).hexdigest()
    assert opener.bodies[0]['instructions'].startswith(active.SYSTEM_PROMPT)
    assert opener.bodies[0]['tools']==tool_definitions()
    assert json.loads(opener.bodies[-1]['input'][-1]['content'][0]['text'])['observation_id']=='e1:60'
    assert 'PRIVILEGED_SENTINEL' not in json.dumps(opener.bodies)


def test_P8_wire_differs_from_P7_only_in_instructions(monkeypatch,tmp_path):
    _,old,_,_,_=run_fake(detail.DEFAULT_PROFILE,tmp_path/'P7',monkeypatch)
    _,new,_,_,_=run_fake(PROFILE,tmp_path/'P8',monkeypatch)
    for old_body,new_body in zip(old.bodies,new.bodies):
        old_body=copy.deepcopy(old_body);new_body=copy.deepcopy(new_body)
        assert old_body.pop('instructions')!=new_body.pop('instructions')
        assert old_body==new_body


def test_P7_public_dispatch_matches_frozen_direct_runner(monkeypatch,tmp_path):
    _,old,_,_,_=run_fake(detail.DEFAULT_PROFILE,tmp_path/'P7direct',monkeypatch,runner=detail.run_episode)
    _,new,_,_,_=run_fake(detail.DEFAULT_PROFILE,tmp_path/'P7public',monkeypatch)
    assert old.bodies==new.bodies


def test_custom_prompt_metadata_hash_tracks_actual_instruction_text(monkeypatch,tmp_path):
    _,opener,_,_,controller=run_fake(PROFILE,tmp_path/'custom',monkeypatch,prompt='CPU custom generic task')
    extension=controller['controller_extension']
    assert extension['actual_system_prompt_SHA256']==hashlib.sha256(controller['prompt'].encode()).hexdigest()
    assert extension['actual_request_instructions_SHA256']==hashlib.sha256(opener.bodies[0]['instructions'].encode()).hexdigest()
    assert extension['actual_system_prompt_SHA256']!=extension['default_system_prompt_SHA256']
