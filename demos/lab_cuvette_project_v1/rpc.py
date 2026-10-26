"""Loopback RPent wire compatibility; all actions use ProjectEnvironment.

The synchronous HTTP owner thread is the Isaac launcher thread. Waiting for a
request never calls app.update, render or world.step. No teacher/debug method is
registered. This is an optional adapter, not a second simulation implementation.
"""
from __future__ import annotations
import base64
import copy
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import threading
import time
import numpy as np


def encode(value):
    if isinstance(value,np.ndarray):
        if value.dtype.hasobject:raise TypeError('Object arrays cannot cross RPC')
        return {'__ndarray__':base64.b64encode(value.tobytes()).decode('ascii'),'dtype':str(value.dtype),'shape':list(value.shape)}
    if isinstance(value,np.generic):return value.item()
    raise TypeError('Unsupported RPC value type')


def decode(value):
    if isinstance(value,dict):
        if '__ndarray__' in value:
            if set(value)!={'__ndarray__','dtype','shape'}:raise ValueError('Malformed ndarray envelope')
            dtype=np.dtype(value['dtype'])
            if dtype.hasobject:raise ValueError('Object arrays cannot cross RPC')
            shape=value['shape']
            if not isinstance(shape,list) or len(shape)>8 or any(not isinstance(x,int) or x<0 for x in shape):
                raise ValueError('Invalid ndarray shape')
            raw=base64.b64decode(value['__ndarray__'],validate=True)
            count=int(np.prod(shape,dtype=np.int64))
            if count<0 or count*dtype.itemsize!=len(raw):raise ValueError('ndarray byte count differs from shape')
            return np.frombuffer(raw,dtype=dtype).reshape(shape).copy()
        return {key:decode(item) for key,item in value.items()}
    if isinstance(value,list):return [decode(item) for item in value]
    return value


class ProjectRPC:
    METHODS=frozenset(('healthz','shutdown','env.reset','env.step','env.chunk_step','env.get_observation',
        'env.render_camera','env.get_camera_meta','env.get_task_language','env.get_env_meta',
        'env.finalize_episode','env.close','project.observe','project.execute','project.receipt','project.status','project.finish'))
    def __init__(self,environment,*,request_log=None):
        self.environment=environment
        self.owner=threading.get_ident()
        self.closed=False
        self.request_log=Path(request_log) if request_log else None

    def metadata(self):
        task=self.environment.task;cfg=task.cfg if hasattr(task,'cfg') else task.base_cfg
        return dict(schema='labsim.Project_v1.rpent_environment.v1',task='lab_cuvette_loading',version='Project_v1',
            task_type='loading',scene_mode='standard',robot_base_position_m=list(cfg.robot.base_m),
            robot_base_quaternion_xyzw=list(cfg.robot.get('base_quaternion_xyzw',[0.,0.,0.,1.])),
            physics_hz=int(cfg.physics.hz),control_hz=int(cfg.physics.control_hz),
            physics_steps_per_control=int(cfg.physics.hz//cfg.physics.control_hz),camera_names=['side_camera','wrist_camera'],
            action_specs=copy.deepcopy(task.ACTION_SPECS),observation_debug_exposed=False,
            execution='same ProjectEnvironment bounds, generic IK/interpolation and independent scorer',
            physics_while_waiting_for_rpc='paused; no app.update/world.step/render',
            dispatch_thread='main',wire_format='RPent POST /call JSON __ndarray__ base64/dtype/shape',
            optional_models_started=False)

    def _status(self):
        try:return self.environment.status()
        except AttributeError:return dict(episode_id=None,simulation_time=None,terminated=True,initialization='reset_required')

    def reset(self,seed=None,options=None):
        options=dict(options or {})
        if options.get('mode','standard')!='standard' or options.get('subtask','loading')!='loading':
            raise ValueError('Project release RPC supports standard/loading only')
        if options.get('teacher') or options.get('truth_visible'):
            raise ValueError('Public RPC cannot request teacher or privileged observations')
        obs=self.environment.reset(seed=int(seed or 0),options=dict(options,mode='standard',teacher=False))
        return obs,self.environment.status()

    def step(self,action):
        if not isinstance(action,dict):raise ValueError('Typed action envelope required')
        obs=self.environment.observe()
        if action.get('episode_id')!=obs['episode_id']:
            raise ValueError('Stale episode_id')
        step=action.get('observation_step')
        if not isinstance(step,int):raise ValueError('observation_step integer required')
        # A deterministic ID makes an identical legacy request replay safe after a
        # lost HTTP response. Never rebase a stale request to the current state.
        payload=json.dumps(action,sort_keys=True,allow_nan=False,default=encode)
        action_id=action.get('action_id') or 'legacy:'+hashlib.sha256(payload.encode()).hexdigest()
        forwarded={key:copy.deepcopy(action[key]) for key in ('type','values','frame','duration_s','gripper_opening_m','gripper_effort_limit_N') if key in action}
        forwarded.update(action_id=action_id,episode_id=action['episode_id'],observation_id=f"{action['episode_id']}:{step}",
            raw_model_action=copy.deepcopy(action))
        if action.get('metadata'):raise ValueError('Public RPC cannot select private phases')
        receipt=self.environment.execute(forwarded)
        successor=self.environment.observe();status=self.environment.status()
        info=dict(status,action_receipt=receipt)
        return successor,float(status.get('task_success') is True),bool(status['terminated']),False,info

    def chunk(self,actions,return_all_frames=False):
        if not isinstance(actions,list) or not 1<=len(actions)<=32:raise ValueError('chunk needs1..32 typed actions')
        origin=self.environment.observe();frames=[];last=None
        for index,action in enumerate(actions):
            if action.get('episode_id')!=origin['episode_id']:raise ValueError('Stale chunk episode')
            if index==0 and action.get('observation_step')!=origin['step_index']:raise ValueError('Stale chunk origin')
            action=copy.deepcopy(action);current=self.environment.observe();action['observation_step']=int(current['step_index'])
            action.setdefault('action_id','chunk:'+hashlib.sha256(json.dumps(actions,sort_keys=True,allow_nan=False,default=encode).encode()).hexdigest()+':'+str(index))
            last=self.step(action);frames.append(last[0])
            if last[2] or last[3]:break
        return (frames,*last[1:]) if return_all_frames else last

    def finalize(self,termination_reason='POLICY_BUDGET',failure_type=None,episode_id=None):
        if episode_id is not None and episode_id!=self.environment.status()['episode_id']:
            raise ValueError('Stale finalization episode')
        # Backend/service classification belongs to policy evidence. The caller
        # cannot overwrite a physical scorer failure or submit a success flag.
        return self.environment.finish(reason=str(termination_reason))

    def dispatch(self,method,args=(),kwargs=None):
        if threading.get_ident()!=self.owner:raise RuntimeError('RPC dispatched outside owner thread')
        if method not in self.METHODS:raise ValueError('RPC method is not public')
        kwargs=dict(kwargs or {});before=self._status();started=time.perf_counter()
        try:
            if method=='healthz':result={'status':'ok','version':'Project_v1'}
            elif method=='shutdown':self.closed=True;result={'ok':True}
            elif method=='env.reset':result=self.reset(*args,**kwargs)
            elif method=='env.step':result=self.step(*args,**kwargs)
            elif method=='env.chunk_step':result=self.chunk(*args,**kwargs)
            elif method in ('env.get_observation','project.observe'):result=self.environment.observe()
            elif method=='env.get_env_meta':result=self.metadata()
            elif method=='env.get_task_language':result=self.environment.observe()['task_language']
            elif method=='env.get_camera_meta':
                name=args[0] if args else kwargs.get('camera_name')
                if set(kwargs)-{'camera_name'}:raise ValueError('No debug camera metadata')
                result=self.environment.observe()['camera_meta'][name]
            elif method=='env.render_camera':
                name=args[0] if args else kwargs.get('camera_name')
                if set(kwargs)-{'camera_name'}:raise ValueError('No extra camera channels')
                result=self.environment.observe()['images'][name]
            elif method=='env.finalize_episode':result=self.finalize(*args,**kwargs)
            elif method=='env.close':self.closed=True;self.environment.close();result={'closed':True}
            elif method=='project.execute':result=self.environment.execute(*args,**kwargs)
            elif method=='project.receipt':result=self.environment.receipt(*args,**kwargs)
            elif method=='project.status':result=self.environment.status()
            elif method=='project.finish':result=self.environment.finish(*args,**kwargs)
            ok=True;return result
        except Exception:
            ok=False;raise
        finally:
            if self.request_log:
                row=dict(method=method,ok=ok,thread_id=self.owner,wall_seconds=time.perf_counter()-started,
                    simulation_time_before=before.get('simulation_time'),simulation_time_after=self._status().get('simulation_time'))
                with self.request_log.open('a') as stream:stream.write(json.dumps(row,allow_nan=False)+'\n')


class Handler(BaseHTTPRequestHandler):
    timeout=10.
    def log_message(self,*args):pass
    def do_POST(self):
        if self.path!='/call':self.send_error(404);return
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=32*1024*1024:raise ValueError('Invalid RPC body length')
            raw=self.rfile.read(length)
            if len(raw)!=length:raise ValueError('Incomplete RPC request')
            request=decode(json.loads(raw))
            if not isinstance(request,dict) or not isinstance(request.get('method'),str):raise ValueError('RPC method required')
            if request.get('session_id') is not None:raise ValueError('Use episode_id; sessions unsupported')
            result=self.server.facade.dispatch(request['method'],request.get('args',[]),request.get('kwargs',{}))
            body=json.dumps({'ok':True,'result':result},default=encode,allow_nan=False).encode()
        except Exception as error:
            body=json.dumps({'ok':False,'error':str(error),'error_type':type(error).__name__}).encode()
        self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers()
        try:self.wfile.write(body)
        except (BrokenPipeError,ConnectionResetError):pass # Action receipts remain queryable.


def serve_environment(environment,host='127.0.0.1',port=8097,*,ready_path=None):
    if host not in ('127.0.0.1','localhost'):raise ValueError('Unauthenticated policy RPC is loopback only')
    if threading.current_thread() is not threading.main_thread():raise RuntimeError('Isaac RPC must run on main thread')
    server=HTTPServer((host,int(port)),Handler);server.timeout=.1
    ready=Path(ready_path) if ready_path else None
    server.facade=ProjectRPC(environment,request_log=ready.with_suffix('.rpc.jsonl') if ready else None)
    meta=server.facade.metadata();meta['endpoint']=f'http://{host}:{server.server_address[1]}'
    if ready:ready.write_text(json.dumps(meta,indent=2)+'\n')
    print('PROJECT_RPC_READY',meta['endpoint'],flush=True)
    try:
        while not server.facade.closed:server.handle_request()
    finally:
        server.server_close();environment.close()
    return meta
