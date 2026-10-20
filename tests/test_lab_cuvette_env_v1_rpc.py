"""Real RPent HTTP transport + fixture env; explicitly NOT a physics test."""
from pathlib import Path
import json
import subprocess
import sys
import time

import numpy as np
import unittest
try:
    import pytest
except ImportError as exc:
    raise unittest.SkipTest("This pytest suite runs in the deployed RPent .venv; Isaac Python has no pytest and is not modified") from exc


_SERVER = r'''
import json,threading
import numpy as np
from pathlib import Path
from demos.lab_cuvette_env_v1.rpc import serve_environment
class FixtureEnvironment:
    ACTION_SPECS={'joint_position':{'values':'7 rad plus total opening metres'}}
    def __init__(self):
        self.closed=False;self.owner=threading.get_ident();self.steps=0;self.t=0.;self.episode_id=None
        self.base_cfg={'version':'Env_v1','env':{'task_type':'preinsert_diagnostic'},'physics':{'hz':240,'control_hz':60},'robot':{'base_m':[-.3,0,.74]}}
    def check(self):
        assert threading.get_ident()==self.owner,'fixture called outside main thread'
    def reset(self,seed=None,options=None):
        self.check();self.steps=0;self.t=0.;self.episode_id='fixture-'+str(seed)
        return self.get_observation(),{'fixture_only':True}
    def get_observation(self):
        self.check();return {'episode_id':self.episode_id,'steps':self.steps,'simulation_time':self.t,'owner_thread':self.owner,'image':np.arange(60,dtype=np.uint8).reshape(4,5,3)}
    def step(self,action):
        self.check()
        if action['episode_id']!=self.episode_id:raise ValueError('stale episode refused')
        assert isinstance(action['values'],np.ndarray)
        self.steps+=12;self.t+=.05
        return self.get_observation(),0.,False,False,{'fixture_only':True,'task_success':None}
    def chunk_step(self,actions,return_all_frames=False):
        self.check();results=[self.step(a) for a in actions]
        final=results[-1]
        if return_all_frames:return (*final[:4],dict(final[4],all_frames=[x[0] for x in results]))
        return final
    def render_camera(self,camera_name,**kwargs):
        self.check();return self.get_observation()['image']
    def get_camera_meta(self,camera_name,**kwargs):
        self.check();return {'name':camera_name,'fixture_only':True}
    def get_task_language(self):
        self.check();return 'transport contract fixture only'
    def finalize_episode(self,termination_reason='POLICY_BUDGET',failure_type=None):
        self.check();return {'task_success':None,'fixture_only':True,'termination_reason':termination_reason}
    def close(self):
        self.check();self.closed=True
serve_environment(FixtureEnvironment(),port=0,ready_path=Path(__import__('sys').argv[1]))
'''


def test_real_rpent_wire_main_thread_and_paused_wait(tmp_path):
    pytest.importorskip('rpent')
    from rpent.utils.rpc.http_rpc import HttpRpcClient
    from rpent.utils.rpc.rpc_client import RpcError
    ready = tmp_path / 'ready.json'
    process = subprocess.Popen([sys.executable, '-u', '-c', _SERVER, str(ready)],
                               cwd=Path(__file__).resolve().parents[1],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        deadline = time.monotonic() + 10
        while not ready.exists() and time.monotonic() < deadline and process.poll() is None:
            time.sleep(.02)
        assert ready.exists(), process.communicate(timeout=1)
        meta = json.loads(ready.read_text())
        assert meta['framework_contract'] == 'deployed_rpent.BaseEnvFacade'
        assert meta['physics_steps_per_control'] == 4
        client = HttpRpcClient(meta['endpoint'])
        assert client.call('healthz') == {'status':'ok'}
        obs, info = client.call('env.reset', kwargs={'seed':7,'options':{}})
        np.testing.assert_array_equal(obs['image'], np.arange(60,dtype=np.uint8).reshape(4,5,3))
        before = client.call('env.get_observation')
        time.sleep(.25)
        after = client.call('env.get_observation')
        assert before['steps'] == after['steps'] == 0
        assert before['simulation_time'] == after['simulation_time'] == 0
        result = client.call('env.step', args=({'episode_id':obs['episode_id'],'values':np.zeros(7)},))
        assert result[0]['steps'] == 12 and result[0]['simulation_time'] == .05
        assert result[4]['task_success'] is None
        with pytest.raises(RpcError, match='not public'):
            client.call('env.get_debug_observation')
        with pytest.raises(RpcError, match='not public'):
            client.call('teacher.run_complete_loading')
        with pytest.raises(RpcError, match='stale'):
            client.call('env.step', args=({'episode_id':'old','values':np.zeros(7)},))
        assert client.call('env.get_observation')['steps'] == 12
        chunk = client.call('env.chunk_step', args=([{'episode_id':obs['episode_id'],'values':np.zeros(7)}] * 2,), kwargs={'return_all_frames':True})
        assert isinstance(chunk[0],list) and len(chunk[0]) == 2
        assert [frame['steps'] for frame in chunk[0]] == [24,36]
        with pytest.raises(RpcError, match='stale'):
            client.call('env.finalize_episode', kwargs={'termination_reason':'POLICY_BUDGET','episode_id':'old'})
        final = client.call('env.finalize_episode', kwargs={'termination_reason':'POLICY_BUDGET','episode_id':obs['episode_id']})
        assert final['task_success'] is None
        assert client.call('env.close') == {'closed':True}
        assert process.wait(timeout=5) == 0
        events = [json.loads(row) for row in ready.with_suffix('.rpc.jsonl').read_text().splitlines()]
        assert len({row['thread_id'] for row in events}) == 1
        for row in events:
            if row['method'] in {'env.get_observation','env.get_env_meta','healthz'}:
                assert row['physics_steps_before'] == row['physics_steps_after']
    finally:
        if process.poll() is None:
            process.terminate()
        process.communicate(timeout=5)
