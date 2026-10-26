"""CPU transport/facade compatibility checks; no physical simulation is mocked as evidence."""
import copy
import json
from types import SimpleNamespace
import unittest
import numpy as np
from demos.lab_cuvette_project_v1.rpc import ProjectRPC,decode,encode


class Facade:
    def __init__(self):
        self.step=0;self.actions={};self.called=[]
        self.task=SimpleNamespace(base_cfg=SimpleNamespace(robot=Config(base_m=[0,0,.74]),physics=SimpleNamespace(hz=240,control_hz=60)),ACTION_SPECS={})
    def reset(self,seed=0,options=None):self.step=0;self.actions={};return self.observe()
    def observe(self):
        return dict(episode_id='e',observation_id=f'e:{self.step}',step_index=self.step,simulation_time=self.step/60,
            task_language='Task',images={'side_camera':np.zeros((2,3,3),np.uint8),'wrist_camera':np.ones((2,3,3),np.uint8)},
            camera_meta={'side_camera':{'name':'side_camera'}},joint_positions=np.zeros(9))
    def execute(self,action):
        key=action['action_id']
        if key in self.actions:return self.actions[key]
        if action['observation_id']!=self.observe()['observation_id']:raise ValueError('stale')
        self.called.append(action);self.step+=3;self.actions[key]={'action_id':key,'accepted':True,'completed':True}
        return self.actions[key]
    def status(self):return dict(episode_id='e',simulation_time=self.step/60,terminated=False,task_success=None)
    def finish(self,reason):return dict(task_success=False,termination_reason=reason)
    def close(self):pass


class Config(SimpleNamespace):
    def get(self,key,default=None):return getattr(self,key,default)


class ProjectRPCContracts(unittest.TestCase):
    def setUp(self):self.env=Facade();self.rpc=ProjectRPC(self.env)
    def command(self):return dict(type='ee_delta',values=[0,0,.0005,0,0,0],duration_s=.05,episode_id='e',observation_step=0)
    def test_legacy_step_routes_through_same_bounded_facade_with_stable_id(self):
        result=self.rpc.dispatch('env.step',[self.command()]);self.rpc.dispatch('env.step',[self.command()])
        self.assertEqual(len(self.env.called),1)
        self.assertEqual(result[0]['step_index'],3);self.assertEqual(len(result),5)
        self.assertEqual(self.env.called[0]['observation_id'],'e:0')
        self.assertEqual(self.env.called[0]['raw_model_action'],self.command())
    def test_ndarray_action_values_can_be_hashed_and_executed(self):
        action=self.command();action['values']=np.asarray(action['values'])
        self.rpc.step(action);self.rpc.step(action)
        self.assertEqual(len(self.env.called),1)
    def test_standard_reset_rejects_teacher_and_random(self):
        for options in [dict(teacher=True),dict(mode='random'),dict(subtask='preinsert_diagnostic'),dict(truth_visible=True)]:
            with self.assertRaises(ValueError):self.rpc.reset(options=options)
        obs,info=self.rpc.reset(seed=2,options=dict(mode='standard',subtask='loading',truth_visible=False))
        self.assertEqual(obs['episode_id'],'e');self.assertIsNone(info['task_success'])
    def test_no_private_or_teacher_rpc_method(self):
        for name in ['env.get_debug_observation','teacher.act','env.scorer','project.task']:
            with self.assertRaises(ValueError):self.rpc.dispatch(name)
    def test_metadata_declares_native_version_and_timing(self):
        meta=self.rpc.dispatch('env.get_env_meta')
        self.assertEqual(meta['version'],'Project_v1');self.assertEqual(meta['physics_steps_per_control'],4)
        self.assertFalse(meta['observation_debug_exposed'])
    def test_finalization_cannot_submit_success_or_score_failure_override(self):
        result=self.rpc.finalize(termination_reason='POLICY_BUDGET',failure_type='invented',episode_id='e')
        self.assertFalse(result['task_success']);self.assertNotIn('invented',json.dumps(result))
        with self.assertRaises(ValueError):self.rpc.finalize(episode_id='old')
    def test_ndarray_wire_matches_rpent_without_pickle(self):
        image=np.arange(18,dtype=np.uint8).reshape(2,3,3)
        decoded=decode(json.loads(json.dumps({'image':image},default=encode)))
        np.testing.assert_array_equal(decoded['image'],image)
        with self.assertRaises(TypeError):encode(np.array([{}],dtype=object))
        with self.assertRaises(ValueError):decode({'__ndarray__':'AA==','dtype':'float64','shape':[1000]})
    def test_duplicate_chunk_ids_are_explicit_and_each_action_has_fresh_origin(self):
        action=self.command();result=self.rpc.chunk([copy.deepcopy(action),copy.deepcopy(action)],return_all_frames=True)
        self.assertEqual([x['observation_id'] for x in self.env.called],['e:0','e:3'])
        self.assertEqual(len(result[0]),2)


if __name__=='__main__':unittest.main()
