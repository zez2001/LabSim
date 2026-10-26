"""CPU-only transport/safety contracts. These are not physical task validation."""
import copy
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
import numpy as np

from policy.backends.cubence import BudgetExceeded, BudgetLedger, CubenceClient, ProviderError, input_token_bound, load_config, response_tools
from policy.backends.cubence_tools import GenericRobotTools, observation_content, public_observation, run_episode, tool_definitions


CONFIG=Path(__file__).resolve().parents[1]/"config/lab_cuvette_loading/Project_v1/policies/cubence_gpt6.json"


class Response(io.BytesIO):
    status=200
    def __enter__(self):return self
    def __exit__(self,*args):self.close()


class Opener:
    def __init__(self, results):self.results=list(results);self.calls=[]
    def open(self,request,timeout):
        self.calls.append((request,timeout))
        value=self.results.pop(0)
        if isinstance(value,Exception):raise value
        return Response(json.dumps(value).encode())


class Environment:
    """A protocol fake; does not claim simulation or success."""
    def __init__(self):
        self.executions=[];self.saved={};self.step=0;self.ended=False;self.result=None
    def observe(self):
        return dict(episode_id="e1",observation_id="o"+str(self.step),joint_positions=[0.]*7+[.04,.04],
            joint_velocities=[0.]*9,TCPpose=dict(position_m=[0.,0.,1.],quaternion_wxyz=[1.,0.,0.,0.]),
            gripper_opening_m=.08,simulation_time=self.step/60,object_position_m=[9,9,9],phase="SECRET")
    def receipt(self,action_id):return self.saved.get(action_id)
    def execute(self,action):
        self.executions.append(action);self.step+=1
        receipt=dict(action_id=action["action_id"],status="EXECUTED",observation_id="o"+str(self.step))
        self.saved[action["action_id"]]=receipt
        return receipt
    def status(self):return dict(terminated=self.ended)
    def finish(self,reason,*,failure_type=None):
        if not self.ended:
            self.result=dict(task_success=False,termination_reason=reason,failure_type=failure_type,record_valid=failure_type is None)
            self.ended=True
        return self.result


class CubenceBackendContracts(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory();self.addCleanup(self.directory.cleanup)
        self.cfg=load_config(CONFIG);self.ledger=BudgetLedger(Path(self.directory.name)/"budget.json",self.cfg)
    def client(self,results):
        opener=Opener(results)
        with patch.dict(os.environ,{"CUBENCE_API_KEY":"private-test-value"}):
            return CubenceClient(self.cfg,self.ledger,opener=opener,sleeper=lambda _:None),opener

    def test_official_endpoint_and_model_are_pinned(self):
        cfg=copy.deepcopy(self.cfg);cfg["base_url"]="https://api.cubence.ai.evil.example/v1"
        path=Path(self.directory.name)/"bad.json";path.write_text(json.dumps(cfg))
        with self.assertRaisesRegex(ValueError,"official HTTPS"):load_config(path)
        cfg["base_url"]=self.cfg["base_url"];cfg["model"]="different-model";path.write_text(json.dumps(cfg))
        with self.assertRaisesRegex(ValueError,"pinned"):load_config(path)

    def test_usage_pricing_and_secret_not_in_ledger(self):
        reply=dict(id="r",model="gpt-6-astra",usage=dict(input_tokens=1000,output_tokens=100,input_tokens_details=dict(cached_tokens=200)),output=[])
        client,opener=self.client([reply]);_,meta=client.responses([dict(role="user",content="hello")],instructions="test")
        self.assertAlmostEqual(meta["charged_estimate_usd"],.0132)
        ledger=self.ledger.path.read_text()
        self.assertNotIn("private-test-value",ledger);self.assertNotIn("Authorization",ledger)
        self.assertEqual(opener.calls[0][0].get_header("Authorization"),"Bearer private-test-value")
        self.assertEqual(self.ledger.summary()["total_network_attempts"],1)

    def test_http_errors_are_sanitized_and_retries_count(self):
        error=urllib.error.HTTPError("https://api.cubence.ai/v1/responses",429,"secret-body",{},io.BytesIO(b"Authorization: private-test-value"))
        reply=dict(model="gpt-6-astra",id="retry",usage=dict(input_tokens=10,output_tokens=1),output=[])
        client,_=self.client([error,reply]);client.responses([],instructions="test")
        ledger=json.loads(self.ledger.path.read_text())
        self.assertEqual(len(ledger["attempts"]),2)
        self.assertEqual(ledger["attempts"][0]["status"],"PROVIDER_RATE_LIMIT")
        self.assertGreater(ledger["attempts"][0]["charged_estimate_usd"],0)
        self.assertNotIn("secret-body",self.ledger.path.read_text())

    def test_ambiguous_timeout_keeps_reservation_and_finite_retries(self):
        client,opener=self.client([TimeoutError(),TimeoutError(),TimeoutError()])
        with self.assertRaisesRegex(ProviderError,"PROVIDER_TIMEOUT"):client.responses([],instructions="test")
        self.assertEqual(len(opener.calls),3)
        data=json.loads(self.ledger.path.read_text())
        self.assertTrue(all(x["charged_estimate_usd"]==x["reserved_usd"] for x in data["attempts"]))

    def test_shared_ledger_enforces_request_budget_before_network(self):
        self.cfg["max_requests"]=1
        client,opener=self.client([dict(model="gpt-6-astra",output=[],usage=dict(input_tokens=1,output_tokens=1))])
        client.responses([],instructions="test")
        second=BudgetLedger(self.ledger.path,self.cfg)
        with self.assertRaises(BudgetExceeded):second.reserve(label="second",endpoint="responses",input_tokens_bound=1,output_tokens_bound=1)
        self.assertEqual(len(opener.calls),1)

    def test_cost_cap_checks_reservation_before_call(self):
        self.cfg["max_estimated_usd"]=.001
        client,opener=self.client([])
        with self.assertRaises(BudgetExceeded):client.responses([],instructions="test")
        self.assertEqual(opener.calls,[])

    def test_returned_model_mismatch_is_recorded_and_refused(self):
        client,_=self.client([dict(model="another-model",output=[],usage=dict(input_tokens=1,output_tokens=1))])
        with self.assertRaisesRegex(ProviderError,"RETURNED_MODEL_MISMATCH"):client.responses([],instructions="test")
        self.assertEqual(json.loads(self.ledger.path.read_text())["attempts"][0]["returned_model"],"another-model")

    def test_multiple_or_invalid_tool_calls_never_execute(self):
        with self.assertRaisesRegex(ProviderError,"MULTIPLE_ACTIONS"):
            response_tools({"output":[dict(type="function_call",arguments="{}")]*2})
        with self.assertRaisesRegex(ProviderError,"INVALID_TOOL_JSON"):
            response_tools({"output":[dict(type="function_call",arguments="oops")]})

    def test_image_bound_does_not_charge_base64_as_text(self):
        bound=input_token_bound({"input":[dict(type="input_image",image_url="data:image/png;base64,"+"a"*1_000_000)]},24000)
        self.assertLess(bound,10000)

    def test_declared_image_resize_preserves_native_data_and_calibration_mapping(self):
        observation=Environment().observe();image=np.full((480,640,3),120,np.uint8)
        observation['images']={'side_camera':image.copy(),'wrist_camera':image.copy()}
        observation['camera_meta']={name:dict(intrinsic_matrix_native=[[500.,0.,319.5],[0.,500.,239.5],[0.,0.,1.]]) for name in observation['images']}
        content=observation_content(observation,image_config={'max_side_px':256,'jpeg_quality':60})
        data=json.loads(content[0]['text']);meta=data['model_image_transforms']['side_camera']
        self.assertEqual(meta['native_resolution_wh'],[640,480]);self.assertEqual(meta['transmitted_resolution_wh'],[256,192])
        np.testing.assert_allclose(meta['intrinsic_matrix_transmitted'],[[200.,0.,127.5],[0.,200.,95.5],[0.,0.,1.]],rtol=0,atol=1e-12)
        self.assertFalse(meta['native_recording_changed']);self.assertEqual(observation['images']['side_camera'].shape,(480,640,3))
        self.assertTrue(content[2]['image_url'].startswith('data:image/jpeg;base64,'))

    def test_model_camera_payload_is_compact_without_changing_public_calibration(self):
        observation=Environment().observe();image=np.zeros((48,64,3),np.uint8)
        metadata=dict(name='side_camera',intrinsic_matrix_native=[[10.,0.,31.5],[0.,10.,23.5],[0.,0.,1.]],
            camera_cv_from_world=np.eye(4).tolist(),world_pose_position_m=[1.,2.,3.],world_pose_quaternion_wxyz=[1.,0.,0.,0.],
            resolution_wh=[64,48],sensor_rendering_time_s=.1,source='verbose source narrative',
            optical_conventions={'opencv':'verbose optical narrative'},world_from_camera_usd=np.eye(4).tolist(),focal_length_cm=2.)
        observation['images']={'side_camera':image,'wrist_camera':image}
        observation['camera_meta']={'side_camera':copy.deepcopy(metadata),'wrist_camera':copy.deepcopy(metadata)}
        content=observation_content(observation)
        model=json.loads(content[0]['text'])['camera_meta']['side_camera']
        self.assertIn('intrinsic_matrix_native',model);self.assertIn('camera_cv_from_world',model)
        self.assertIn('world_pose_position_m',model);self.assertIn('sensor_rendering_time_s',model)
        self.assertNotIn('source',model);self.assertNotIn('optical_conventions',model);self.assertNotIn('world_from_camera_usd',model)
        self.assertEqual(public_observation(observation)['camera_meta']['side_camera']['source'],'verbose source narrative')
        self.assertEqual(observation['camera_meta']['side_camera'],metadata)

    def test_public_observation_denies_truth_and_camera_debug(self):
        observation=Environment().observe();observation["camera_meta"]={"side_camera":dict(intrinsic_matrix_native=[[1]],object_depth_m=9,renderer_debug={"private":1})}
        public=public_observation(observation)
        self.assertNotIn("object_position_m",public);self.assertNotIn("phase",public)
        self.assertEqual(public["camera_meta"],{"side_camera":{"intrinsic_matrix_native":[[1]]}})

    def test_nested_public_containers_do_not_forward_unknown_truth(self):
        observation=Environment().observe()
        observation['TCPpose']['object_position_m']=[9,9,9]
        observation['camera_meta']={'side_camera':{'optical_conventions':{'usd':'-Z forward','object_depth_m':9}},'object_debug_camera':{'name':'secret'}}
        observation['images']={'side_camera':'rgb','wrist_camera':'rgb','depth':'private'}
        observation['tactile']={'object_pose':[9,9,9]}
        public=public_observation(observation)
        self.assertEqual(set(public['TCPpose']),{'position_m','quaternion_wxyz'})
        self.assertEqual(public['camera_meta'],{'side_camera':{'optical_conventions':{'usd':'-Z forward'}}})
        self.assertEqual(set(public['images']),{'side_camera','wrist_camera'})
        self.assertNotIn('tactile',public)

    def test_malformed_usage_is_classified_without_losing_reserved_cost(self):
        client,_=self.client([dict(model='gpt-6-astra',usage={'input_tokens':'invalid'},output=[])])
        with self.assertRaisesRegex(ProviderError,'PROVIDER_INVALID_USAGE'):client.responses([],instructions='test')
        item=json.loads(self.ledger.path.read_text())['attempts'][0]
        self.assertEqual(item['status'],'PROVIDER_INVALID_USAGE')
        self.assertEqual(item['charged_estimate_usd'],item['reserved_usd'])

    def action(self,**updates):
        value=dict(episode_id="e1",observation_id="o0",action_id="a1",mode="ee_delta",values=[0.,0.,.001,0.,0.,0.],frame="world",duration_s=.1)
        value.update(updates);return value

    def test_receipt_prevents_duplicate_motion_and_conflicting_reuse(self):
        env=Environment();tools=GenericRobotTools(env,self.cfg["action_limits"]);tools.observe()
        tools.execute("move_ee",self.action());retry=tools.execute("move_ee",self.action())
        self.assertEqual(len(env.executions),1);self.assertTrue(retry["idempotent_replay"])
        with self.assertRaisesRegex(ProviderError,"ACTION_ID_REUSED"):tools.execute("move_ee",self.action(values=[0,0,.002,0,0,0]))

    def test_stale_or_too_fast_actions_are_rejected_without_step(self):
        env=Environment();tools=GenericRobotTools(env,self.cfg["action_limits"]);tools.observe()
        with self.assertRaisesRegex(ProviderError,"STALE_OBSERVATION_ID"):tools.execute("move_ee",self.action(observation_id="old"))
        with self.assertRaisesRegex(ProviderError,"TRANSLATION_SPEED_LIMIT"):tools.execute("move_ee",self.action(values=[0,0,.04,0,0,0]))
        self.assertEqual(env.executions,[])

    def test_norm_limit_rejection_reports_numeric_violation_and_preserves_state(self):
        env=Environment();tools=GenericRobotTools(env,self.cfg['action_limits']);tools.observe()
        with self.assertRaises(ProviderError) as caught:
            tools.execute('move_ee',self.action(values=[0.,-.04,-.04,0.,0.,0.],duration_s=3.))
        details=caught.exception.details
        self.assertAlmostEqual(details['translation_norm_m'],.0565685424949238)
        self.assertEqual(details['max_translation_norm_m'],.04)
        self.assertEqual(details['violations'],['translation_norm'])
        self.assertLess(details['linear_speed_m_s'],details['max_linear_speed_m_s'])
        self.assertEqual(env.executions,[])

    def test_unknown_execution_queries_receipt_instead_of_replaying(self):
        env=Environment();execute=env.execute
        def ack_lost(action):execute(action);raise TimeoutError()
        env.execute=ack_lost
        tools=GenericRobotTools(env,self.cfg["action_limits"]);tools.observe()
        receipt=tools.execute("move_ee",self.action())
        self.assertEqual(receipt["status"],"EXECUTED");self.assertEqual(len(env.executions),1)

    def test_move_holds_requested_grip_and_unload_effort_not_measured_width(self):
        env=Environment();tools=GenericRobotTools(env,self.cfg["action_limits"]);tools.observe()
        tools.execute("gripper",dict(episode_id="e1",observation_id="o0",action_id="close",opening_m=.002,effort_limit_N=.05,duration_s=.1))
        tools.execute("move_ee",self.action(observation_id="o1",action_id="move"))
        self.assertEqual(env.executions[-1]["gripper_opening_m"],.002)
        self.assertEqual(env.executions[-1]["gripper_effort_limit_N"],.05)

    def test_tool_schema_has_no_task_or_truth_primitive(self):
        names=[x["name"] for x in tool_definitions()]
        self.assertEqual(names,["observe","move_ee","gripper","wait","finish"])
        self.assertTrue(all(t["parameters"]["additionalProperties"] is False for t in tool_definitions()))

    def test_parallel_function_calls_cannot_be_enabled_by_extra_kwargs(self):
        client,opener=self.client([dict(model='gpt-6-astra',output=[],usage=dict(input_tokens=1,output_tokens=1))])
        client.responses([],instructions='test',tools=tool_definitions(),parallel_tool_calls=True)
        self.assertIs(json.loads(opener.calls[0][0].data)['parallel_tool_calls'],False)

    def test_malformed_gripper_numbers_are_protocol_errors_before_motion(self):
        for field in ('opening_m','effort_limit_N','duration_s'):
            for invalid in (None,'0.01',{},[],True,float('nan')):
                env=Environment();tools=GenericRobotTools(env,self.cfg['action_limits']);tools.observe()
                args=dict(episode_id='e1',observation_id='o0',action_id='bad',opening_m=.01,effort_limit_N=8.,duration_s=.1)
                args[field]=invalid
                with self.assertRaises(ProviderError,msg=(field,invalid)):tools.execute('gripper',args)
                self.assertEqual(env.executions,[])

    def episode(self,env,client,*,max_calls=1):
        output=Path(self.directory.name)/'episode'
        with patch('policy.backends.cubence_tools.observation_content',lambda obs,**kwargs:[dict(type='input_text',text='CPU fixture robot observation')]):
            summary=run_episode(env,client,output,max_calls=max_calls)
        return summary,output

    def tool_reply(self,name='move_ee',arguments=None):
        return dict(model='gpt-6-astra',id='fixture-response',usage=dict(input_tokens=1,output_tokens=1),
            output=[dict(type='function_call',name=name,call_id='call-fixture',arguments=json.dumps(arguments or self.action()))])

    def test_provider_http_failure_flushes_attempt_with_nonphysical_label(self):
        error=urllib.error.HTTPError('https://api.cubence.ai/v1/responses',401,'private-error-body',{},None)
        client,_=self.client([error]);env=Environment();summary,output=self.episode(env,client)
        self.assertEqual(summary['backend_failure_type'],'MODEL_SERVICE_ERROR')
        self.assertEqual(summary['backend_error_code'],'PROVIDER_HTTP_ERROR')
        self.assertEqual(summary['network_attempts_this_episode'],1)
        self.assertEqual(summary['api_decisions'],0)
        self.assertFalse(summary['task_result']['record_valid'])
        self.assertEqual(env.executions,[])
        self.assertEqual(json.loads((output/'summary.json').read_text()),summary)

    def test_local_context_guard_is_input_contract_error_without_http_attempt(self):
        self.cfg['max_context_input_tokens']=100
        client,opener=self.client([]);env=Environment();summary,_=self.episode(env,client)
        self.assertEqual(summary['backend_failure_type'],'INPUT_CONTRACT_ERROR')
        self.assertEqual(summary['backend_error_code'],'LOCAL_CONTEXT_TOKEN_BOUND_EXCEEDED')
        self.assertEqual(summary['network_attempts_this_episode'],0)
        self.assertEqual(opener.calls,[]);self.assertEqual(env.executions,[])

    def test_multiple_model_calls_abort_before_either_motion_and_preserve_calls(self):
        reply=self.tool_reply();reply['output']*=2
        client,_=self.client([reply]);env=Environment();summary,output=self.episode(env,client)
        self.assertEqual(summary['backend_failure_type'],'INPUT_CONTRACT_ERROR')
        self.assertEqual(summary['backend_error_code'],'PROTOCOL_MULTIPLE_ACTIONS_REFUSED')
        self.assertEqual(env.executions,[])
        error=json.loads((output/'policy_trace.jsonl').read_text().splitlines()[-1])
        self.assertEqual(len(error['model_tool_calls']),2)
        self.assertFalse(summary['task_result']['record_valid'])

    def test_repeated_malformed_gripper_outputs_do_not_become_task_failures(self):
        args=dict(episode_id='e1',observation_id='o0',action_id='bad',opening_m=None,effort_limit_N=8.,duration_s=.1)
        client,_=self.client([self.tool_reply('gripper',args) for _ in range(8)])
        env=Environment();summary,_=self.episode(env,client,max_calls=8)
        self.assertEqual(summary['protocol_rejections'],8)
        self.assertEqual(summary['backend_error_code'],'PROTOCOL_ERROR_LIMIT')
        self.assertEqual(summary['task_result']['failure_type'],'INPUT_CONTRACT_ERROR')
        self.assertEqual(env.executions,[])

    def test_partial_execution_failure_preserves_actual_receipt_without_replay(self):
        env=Environment();execute=env.execute
        def partial(action):
            result=execute(action);result.update(completed=False,error_type='RuntimeError',error='CONTROL_OR_IK_FAILURE');raise RuntimeError('CONTROL_OR_IK_FAILURE')
        env.execute=partial
        client,_=self.client([self.tool_reply()]);summary,output=self.episode(env,client)
        self.assertEqual(summary['backend_failure_type'],'PHYSICS_INVALID')
        self.assertEqual(len(env.executions),1)
        error=json.loads((output/'policy_trace.jsonl').read_text().splitlines()[-1])
        self.assertEqual(error['action_receipt']['error'],'CONTROL_OR_IK_FAILURE')

    def test_normal_policy_budget_retains_independent_physical_admission(self):
        env=Environment();client,_=self.client([self.tool_reply()]);summary,_=self.episode(env,client)
        self.assertEqual(summary['termination_reason'],'POLICY_BUDGET')
        self.assertIsNone(summary['backend_failure_type'])
        self.assertIsNone(summary['backend_error_code'])
        self.assertTrue(summary['task_result']['record_valid'])
        self.assertEqual(len(env.executions),1)

    def test_already_ended_physical_verdict_is_not_rewritten(self):
        env=Environment();env.ended=True;env.result=dict(task_success=False,record_valid=True,failure_type='GRASP_SLIP')
        client,_=self.client([]);summary,_=self.episode(env,client)
        self.assertEqual(summary['task_result']['failure_type'],'GRASP_SLIP')
        self.assertEqual(summary['api_decisions'],0)


if __name__=="__main__":unittest.main()
