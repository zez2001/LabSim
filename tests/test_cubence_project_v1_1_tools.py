"""CPU protocol fakes only: no API, GPU, physics, or fabricated task success."""
import copy
import io
import json
from pathlib import Path

import numpy as np
import pytest

from policy.backends.cubence import BudgetLedger, CubenceClient, ProviderError, load_config
from policy.backends.cubence_project_v1_1_tools import ProjectV11RobotTools, SYSTEM_PROMPT, run_episode


CONFIG=Path(__file__).resolve().parents[1]/'config/lab_cuvette_loading/Project_v1/policies/cubence_gpt6.json'


class ReceiptEnvironment:
    """Synchronous receipt fake; counter movement is not simulation validation."""
    def __init__(self,modes=('ok',)):
        self.modes=list(modes);self.step=0;self.executions=[];self.saved={};self.ended=False;self.result=None

    def observe(self):
        return dict(episode_id='e1',observation_id='e1:'+str(self.step),step_index=self.step,
            simulation_time=self.step/60,joint_positions=[0.]*7+[.0053,.0053],joint_velocities=[0.]*9,
            TCPpose=dict(position_m=[.1,.2,1.05],quaternion_wxyz=[1.,0.,0.,0.]),gripper_opening_m=.0106,
            gripper_effort_limit_N=.05,finger_contact_N=[.2,.21],task_language='A generic public task',
            source_slot_id='A1',target_seat_id='candidate_far_hinge',
            images={'side_camera':np.zeros((8,12,3),np.uint8),'wrist_camera':np.ones((8,12,3),np.uint8)},
            object_position_m=[9,9,9],phase='PRIVILEGED_SENTINEL',scorer={'success':True})

    def status(self):
        return dict(episode_id='e1',terminated=self.ended,simulation_time=self.step/60)

    def receipt(self,action_id):
        return copy.deepcopy(self.saved.get(action_id))

    def execute(self,action):
        assert action['action_id'] not in self.saved,'adapter replayed an executed action'
        self.executions.append(copy.deepcopy(action));mode=self.modes.pop(0) if self.modes else 'ok'
        before=self.step;requested=round(action['duration_s']*60)
        ticks=0 if mode=='reject' else min(5,requested) if mode in ('partial','safety','slip') else requested
        self.step+=ticks
        receipt=dict(action_id=action['action_id'],episode_id='e1',observation_id=action['observation_id'],
            accepted=mode!='reject',execution_finished=True,target_reached=mode=='ok',safety_stopped=mode in ('partial','safety','slip'),
            completed=True,partial_execution=0<ticks<requested,executed_control_ticks=ticks,
            simulation_time_before=before/60,simulation_time_after=self.step/60,executed_duration_s=ticks/60,
            observation_id_after='e1:'+str(self.step),stop_reason={'reject':'CONTROL_PLAN_REJECTED',
                'partial':'EXECUTOR_TRACKING_ERROR','safety':'ROBOT_ENVIRONMENT_COLLISION','slip':'GRASP_SLIP'}.get(mode,'INTERVAL_FINISHED'),
            gripper_opening_m=.0106,status='REJECTED' if mode=='reject' else 'EXECUTED',
            requested_target_TCP=self.observe()['TCPpose'],actual_endpoint_TCP=self.observe()['TCPpose'])
        if mode=='reject':
            receipt['planning_failure']=dict(reference_tick=19,reason='LOCAL_BOUNDARY_UNREACHABLE',
                IK={'position_error_m':.0008,'orientation_error_rad':.003,'reason':'LOCAL_BOUNDARY_UNREACHABLE'},
                robot_state_only=True,object_position_m=[9,9,9])
        if mode=='slip':
            self.ended=True;self.result=dict(task_success=False,failure_type='GRASP_SLIP',record_valid=True)
        self.saved[action['action_id']]=copy.deepcopy(receipt)
        return receipt

    def finish(self,reason,*,failure_type=None):
        if not self.ended:
            self.ended=True;self.result=dict(task_success=None,failure_type=failure_type,termination_reason=reason)
        return copy.deepcopy(self.result)


@pytest.fixture
def cfg():return load_config(CONFIG)


def args(env,**values):
    return dict(episode_id='e1',observation_id='e1:'+str(env.step),action_id='a1',duration_s=1.,**values)


def test_rejected_gripper_plan_keeps_previous_request_and_simulation_time(cfg):
    env=ReceiptEnvironment(('ok','reject','ok'));tools=ProjectV11RobotTools(env,cfg['action_limits'])
    tools.execute('gripper',args(env,opening_m=.009,effort_limit_N=2.))
    previous=(tools.commanded_opening_m,tools.commanded_effort_N,env.step)
    rejected=args(env,opening_m=.04,effort_limit_N=8.);rejected['action_id']='bad'
    with pytest.raises(ProviderError,match='PROTOCOL_CONTROL_PLAN_REJECTED'):
        tools.execute('gripper',rejected)
    assert (tools.commanded_opening_m,tools.commanded_effort_N,env.step)==previous
    move=args(env,mode='ee_delta',values=[.005,0,0,0,0,0],frame='world');move['action_id']='move'
    tools.execute('move_ee',move)
    assert env.executions[-1]['gripper_opening_m']==.009
    assert env.executions[-1]['gripper_effort_limit_N']==2.


def test_partial_execution_is_retained_and_never_replayed(cfg):
    env=ReceiptEnvironment(('partial',));tools=ProjectV11RobotTools(env,cfg['action_limits'])
    command=args(env)
    for _ in range(2):
        with pytest.raises(ProviderError,match='EXECUTOR_ACTION_PARTIAL'):
            tools.execute('wait',command)
    assert len(env.executions)==1 and env.step==5
    receipt=tools.execution_receipt(command)
    assert receipt['partial_execution'] and receipt['executed_control_ticks']==5


def test_completed_interval_does_not_imply_target_reached(cfg):
    env=ReceiptEnvironment(('not_reached',));tools=ProjectV11RobotTools(env,cfg['action_limits'])
    result=tools.execute('wait',args(env))
    assert result['accepted'] and result['execution_finished'] and result['completed']
    assert result['target_reached'] is False and result['status']=='TARGET_NOT_REACHED'


def test_scope_validity_and_applied_gripper_fields_reach_public_receipt(cfg):
    env=ReceiptEnvironment();original=env.execute
    extra=dict(successor_observation_available=True,actual_endpoint_valid=True,
        tracking_error_coverage_complete=True,tracking_error_sampling='every physics step',
        target_reached_scope='TCP pose; gripper contact may prevent requested opening',
        requested_gripper_opening_m=.009,applied_gripper_opening_m=.0103,
        requested_effort_limit_N=5.,applied_effort_limit_N=5.,stop_domain='none')
    def execute(action):
        result=original(action);result.update(extra);env.saved[action['action_id']]=copy.deepcopy(result)
        return result
    env.execute=execute
    tools=ProjectV11RobotTools(env,cfg['action_limits'])
    result=tools.execute('wait',args(env))
    for key,value in extra.items():assert result[key]==value


def test_safety_stop_is_not_automatically_classified_as_physics_invalid(cfg):
    env=ReceiptEnvironment(('safety',));tools=ProjectV11RobotTools(env,cfg['action_limits'])
    with pytest.raises(ProviderError) as raised:
        tools.execute('wait',args(env))
    assert raised.value.code=='SAFETY_ACTION_STOPPED'
    assert tools.failure_class(raised.value.code)=='SAFETY_FAILURE'
    assert tools.failure_class('EXECUTOR_ACTION_PARTIAL')=='EXECUTOR_FAILURE'
    assert tools.failure_class('SIMULATION_STATE_STOPPED')=='SIMULATION_FAILURE'


def test_already_scored_ordinary_task_failure_remains_task_failure(cfg):
    env=ReceiptEnvironment(('slip',));tools=ProjectV11RobotTools(env,cfg['action_limits'])
    result=tools.execute('wait',args(env))
    assert result['partial_execution'] and result['safety_stopped']
    assert env.finish('ENVIRONMENT_TERMINATED',failure_type=None)['failure_type']=='GRASP_SLIP'


def test_reused_id_with_changed_payload_cannot_be_misread_as_previous_success(cfg):
    env=ReceiptEnvironment();tools=ProjectV11RobotTools(env,cfg['action_limits']);command=args(env)
    tools.execute('wait',command)
    changed=dict(command,duration_s=.5)
    with pytest.raises(ProviderError,match='PROTOCOL_ACTION_ID_REUSED'):
        tools.execute('wait',changed)
    assert len(env.executions)==1


def test_new_tools_do_not_add_ground_truth_or_task_macros(cfg):
    tools=ProjectV11RobotTools(ReceiptEnvironment(),cfg['action_limits']);public=tools.observe()
    assert 'object_position_m' not in public and 'phase' not in public and 'scorer' not in public
    with pytest.raises(ProviderError,match='PROTOCOL_UNKNOWN_TOOL'):
        tools.execute('grasp',args(tools.env))
    assert tools.env.executions==[]
    assert 'execution_finished' in SYSTEM_PROMPT and 'target_reached' in SYSTEM_PROMPT


class _Response(io.BytesIO):
    status=200
    def __enter__(self):return self
    def __exit__(self,*_):self.close()


class _Opener:
    def __init__(self,replies):self.replies=list(replies);self.bodies=[]
    def open(self,request,timeout):
        self.bodies.append(json.loads(request.data))
        return _Response(json.dumps(self.replies.pop(0)).encode())


def reply(name,arguments,index=0):
    return dict(model='gpt-6-astra',id='r'+str(index),usage=dict(input_tokens=10,output_tokens=5),
        output=[dict(type='function_call',name=name,arguments=json.dumps(arguments),call_id='call'+str(index))])


def test_runner_reuses_provider_ledger_and_exposes_new_rejection_contract(tmp_path,monkeypatch,cfg):
    ledger=BudgetLedger(tmp_path/'budget.json',cfg)
    prior=ledger.reserve(label='prior-version',endpoint='responses',input_tokens_bound=10,output_tokens_bound=5)
    ledger.complete(prior,status='OK',usage=dict(input_tokens=10,output_tokens=5),returned_model='gpt-6-astra')
    env=ReceiptEnvironment(('reject',));command=args(env,opening_m=.02,effort_limit_N=3.)
    opener=_Opener([reply('gripper',command),reply('finish',dict(episode_id='e1',observation_id='e1:0',reason='diagnostic complete'),1)])
    monkeypatch.setenv('CUBENCE_API_KEY','cpu-test-placeholder')
    client=CubenceClient(cfg,ledger,opener=opener,sleeper=lambda _:None)
    output=tmp_path/'episode';summary=run_episode(env,client,output,max_calls=3)
    assert summary['network_attempts_this_episode']==2
    assert ledger.summary()['total_network_attempts']==3
    assert env.step==0 and len(env.executions)==1
    trace=[json.loads(line) for line in (output/'policy_trace.jsonl').read_text().splitlines()]
    rejected=trace[0]['receipt']
    assert rejected['status']=='REJECTED' and rejected['accepted'] is False
    assert rejected['execution_finished'] is True and rejected['target_reached'] is False
    assert rejected['physics_advanced'] is False and rejected['executed_control_ticks']==0
    assert 'object_position_m' not in json.dumps(rejected)
    controller=json.loads((output/'controller.json').read_text())
    assert controller['controller_extension']['version']=='Project_v1_1'
    assert controller['prompt']==SYSTEM_PROMPT
    assert [tool['name'] for tool in controller['tool_schema']]==['observe','move_ee','gripper','wait','finish']
    saved=''.join(p.read_text() for p in output.rglob('*.json'))+(output/'policy_trace.jsonl').read_text()
    assert 'PRIVILEGED_SENTINEL' not in saved and 'cpu-test-placeholder' not in saved and 'Authorization' not in saved


def test_runner_stops_after_partial_motion_without_another_model_decision(tmp_path,monkeypatch,cfg):
    env=ReceiptEnvironment(('partial',));ledger=BudgetLedger(tmp_path/'budget.json',cfg)
    opener=_Opener([reply('wait',args(env))]);monkeypatch.setenv('CUBENCE_API_KEY','cpu-test-placeholder')
    client=CubenceClient(cfg,ledger,opener=opener,sleeper=lambda _:None)
    output=tmp_path/'episode';summary=run_episode(env,client,output,max_calls=3)
    assert len(opener.bodies)==1 and len(env.executions)==1 and env.step==5
    assert summary['backend_failure_type']=='EXECUTOR_FAILURE'
    assert summary['backend_error_code']=='EXECUTOR_ACTION_PARTIAL'
    record=json.loads((output/'policy_trace.jsonl').read_text())
    assert record['action_receipt']['executed_control_ticks']==5
    assert record['action_receipt']['partial_execution'] is True
