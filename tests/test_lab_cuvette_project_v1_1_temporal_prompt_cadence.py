"""Real generic-tool protocol over CPU receipt fakes; no physical claim."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

from policy.backends.cubence import BudgetLedger, CubenceClient, ProviderError, load_config
from policy.backends.cubence_project_v1_1_tools import (
    SYSTEM_PROMPT, TEMPORAL_SYSTEM_PROMPT, ProjectV11RobotTools,
    ProjectV11TemporalRobotTools, run_episode)

ROOT=Path(__file__).resolve().parents[1]
PROFILE=ROOT/'config/lab_cuvette_loading/Project_v1_1/policies/cubence_gpt6_context4_640high_temporal.json'
spec=importlib.util.spec_from_file_location('cadence_receipt_helpers',ROOT/'tests/test_cubence_project_v1_1_tools.py')
helpers=importlib.util.module_from_spec(spec);spec.loader.exec_module(helpers)
P4_SHA256='ac9ac4d33b2e329dfe684bfcd8461b4962274ac5b57659c94194da2af0ce2ddf'


class CallbackEnvironment(helpers.ReceiptEnvironment):
    """Inspect delegation, ticks and reference frames, not IK/contact physics."""
    def __init__(self):
        super().__init__();self.position=np.array([.1,.2,1.05]);self.callback=[]
    def observe(self):
        result=super().observe()
        # +90deg about X: local down is world +Y, not world down.
        result['TCPpose']=dict(position_m=self.position.tolist(),quaternion_wxyz=[2**-.5,2**-.5,0.,0.])
        return result
    def execute(self,action):
        result=super().execute(action)
        delta=np.array(action['values'][:3])
        if action['frame']=='tcp':delta=np.array([delta[0],-delta[2],delta[1]])
        for tick in range(result['executed_control_ticks']):
            self.callback.append(dict(action_id=action['action_id'],tick=tick,
                frame=action['frame'],position=(self.position+delta*(tick+1)/result['executed_control_ticks']).tolist()))
        self.position+=delta
        result['actual_endpoint_TCP']=self.observe()['TCPpose']
        self.saved[action['action_id']]=copy.deepcopy(result)
        return result


def test_default_p4_prompt_and_metadata_remain_frozen():
    assert hashlib.sha256(SYSTEM_PROMPT.encode()).hexdigest()==P4_SHA256
    assert ProjectV11RobotTools.controller_metadata()['prompt_version']=='Project_v1_1.public_tools.v4'


def test_explicit_profile_changes_memory_only_not_actions_or_budget():
    temporal=load_config(PROFILE);baseline=load_config(PROFILE.with_name('cubence_gpt6_context4_640high.json'))
    assert temporal.pop('visual_context')['enabled'] is True
    assert temporal==baseline


@pytest.mark.parametrize('frame,expected_delta',[('world',[0.,0.,-.0001]),('tcp',[0.,.0001,0.])])
def test_100_micrometre_request_delegates_six_ticks_with_current_ids_and_preserved_frame(frame,expected_delta):
    env=CallbackEnvironment();tools=ProjectV11TemporalRobotTools(env,load_config(PROFILE)['action_limits'])
    start=env.position.copy();arguments=helpers.args(env,mode='ee_delta',values=[0.,0.,-.0001,0.,0.,0.],frame=frame)
    arguments['duration_s']=.1
    receipt=tools.execute('move_ee',arguments)
    assert receipt['executed_control_ticks']==6 and receipt['quantized_requested_duration_s']==.1
    assert receipt['simulation_time_after']-receipt['simulation_time_before']==pytest.approx(.1)
    assert len(env.callback)==6 and all(row['frame']==frame for row in env.callback)
    assert env.executions[0]['observation_id']=='e1:0'
    assert env.executions[0]['values']==arguments['values'] and env.executions[0]['frame']==frame
    assert env.position-start==pytest.approx(expected_delta)
    stale=dict(arguments,action_id='stale',observation_id='e1:0')
    tools.observe()
    with pytest.raises(ProviderError,match='PROTOCOL_STALE_OBSERVATION_ID'):tools.execute('move_ee',stale)
    assert len(env.executions)==1 and len(env.callback)==6


def test_three_millimetres_three_seconds_still_legal_prompt_is_not_an_automatic_stage_guard():
    env=CallbackEnvironment();tools=ProjectV11TemporalRobotTools(env,load_config(PROFILE)['action_limits'])
    request=helpers.args(env,mode='ee_delta',values=[0.,0.,-.003,0.,0.,0.],frame='world')
    request['duration_s']=3.
    receipt=tools.execute('move_ee',request)
    assert receipt['accepted'] and receipt['executed_control_ticks']==180
    assert len(env.callback)==180 and env.position[2]==pytest.approx(1.047)


def test_opt_in_actual_runner_sends_p6_instructions_and_metadata_to_cpu_transport(tmp_path,monkeypatch):
    cfg=load_config(PROFILE);env=CallbackEnvironment();ledger=BudgetLedger(tmp_path/'budget.json',cfg)
    command=helpers.args(env,mode='ee_delta',values=[0.,0.,-.0001,0.,0.,0.],frame='world');command['duration_s']=.1
    opener=helpers._Opener([helpers.reply('move_ee',command),
        helpers.reply('finish',dict(episode_id='e1',observation_id='e1:6',reason='CPU protocol end'),1)])
    monkeypatch.setenv('CUBENCE_API_KEY','cpu-cadence-placeholder')
    client=CubenceClient(cfg,ledger,opener=opener,sleeper=lambda _:None)
    result=run_episode(env,client,tmp_path/'episode',max_calls=2)
    assert len(opener.bodies)==2 and result['network_attempts_this_episode']==2
    expected=TEMPORAL_SYSTEM_PROMPT+'\nAction limits: '+json.dumps(cfg['action_limits'])
    assert all(body['instructions']==expected for body in opener.bodies)
    assert len(env.callback)==6 and env.executions[0]['observation_id']=='e1:0'
    controller=json.loads((tmp_path/'episode/controller.json').read_text())
    assert controller['controller_extension']['prompt_version']=='Project_v1_1.public_tools.v6_temporal'
    assert controller['prompt']==TEMPORAL_SYSTEM_PROMPT
