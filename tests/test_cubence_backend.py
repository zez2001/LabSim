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

from policy.backends.cubence import BudgetExceeded, BudgetLedger, CubenceClient, ProviderError, input_token_bound, load_config, response_tools
from policy.backends.cubence_tools import GenericRobotTools, public_observation, tool_definitions


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
        self.executions=[];self.saved={};self.step=0
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
    def finish(self,reason):return dict(task_success=False,termination_reason=reason)


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


if __name__=="__main__":unittest.main()
