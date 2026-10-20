"""RPent HTTP/JSON facade executing every Isaac operation on the main thread.

The installed RPent BaseEnvFacade is used when importable. Only the transport
loop is replaced: upstream RPent normally serves requests on a worker thread,
whereas Isaac USD/physics/render operations must remain on the owner thread.
No app.update(), world.step() or render call happens while awaiting a request.
"""
from __future__ import annotations

import base64
import copy
import hashlib
import json
import os
import sys
import threading
import traceback
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import numpy as np


# LabSim's robots directory is a namespace package, while RPent's robots is
# a regular package. Preload/retain the LabSim namespace before adding RPent's
# source path so the latter cannot hide robots.franka during later reset.
try:
    import robots as _robot_namespace
    _lab_robot_path = str(Path(__file__).resolve().parents[2] / 'robots')
    if _lab_robot_path not in _robot_namespace.__path__:
        _robot_namespace.__path__.append(_lab_robot_path)
except ImportError:
    _robot_namespace = None

_RPENT_IMPORT_ERROR = None
try:
    from rpent.robots.components.env_facade_base import BaseEnvFacade as _BaseEnvFacade
except ModuleNotFoundError:
    # Source-only import: never add the model .venv/site-packages or replace
    # Isaac's installed numpy/torch. This checkout is already deployed locally.
    candidate = Path(os.environ.get('RPENT_REPO_ROOT', Path(__file__).resolve().parents[3] / 'rpent')).expanduser()
    if (candidate / 'rpent' / 'robots' / 'components' / 'env_facade_base.py').is_file():
        sys.path.append(str(candidate))
    try:
        from rpent.robots.components.env_facade_base import BaseEnvFacade as _BaseEnvFacade
    except (ImportError, ModuleNotFoundError) as exc:
        _RPENT_IMPORT_ERROR = f'{type(exc).__name__}: {exc}'

        class _BaseEnvFacade:
            """Explicit compatible fallback; not claimed as deployed RPent code."""
            def __init__(self):
                self._rpc = {}
                self._readonly_methods = set()
                self._shutdown_event = threading.Event()
                self._register_rpc()

            def _register_rpc(self):
                pass

            def _dispatch(self, method, args=(), kwargs=None):
                if method == 'healthz':
                    return {'status': 'ok'}
                if method == 'shutdown':
                    self._shutdown_event.set()
                    return {'ok': True}
                if method not in self._rpc:
                    raise ValueError(f'unknown RPC method: {method}')
                return self._rpc[method](*args, **(kwargs or {}))


USING_DEPLOYED_RPENT_FACADE = _RPENT_IMPORT_ERROR is None


def _encode(value):
    if isinstance(value, np.ndarray):
        if value.dtype.hasobject:
            raise TypeError('object-dtype arrays cannot cross the RPC boundary')
        return {'__ndarray__': base64.b64encode(value.tobytes()).decode('ascii'),
                'dtype': str(value.dtype), 'shape': list(value.shape)}
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f'not JSON serializable: {type(value).__name__}')


def _decode(value):
    if isinstance(value, dict):
        if '__ndarray__' in value and set(value) <= {'__ndarray__', 'dtype', 'shape'}:
            dtype = np.dtype(value['dtype'])
            if dtype.hasobject:
                raise ValueError('object-dtype arrays are forbidden')
            shape = tuple(value.get('shape', [-1]))
            data = base64.b64decode(value['__ndarray__'], validate=True)
            return np.frombuffer(data, dtype=dtype).reshape(shape).copy()
        return {key: _decode(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_decode(item) for item in value]
    return value


def _plain(value):
    try:
        from omegaconf import OmegaConf
        if OmegaConf.is_config(value):
            return OmegaConf.to_container(value, resolve=True)
    except ImportError:
        pass
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    return value


def _lookup(mapping, *keys, default=None):
    current = mapping
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return current


def environment_metadata(env, *, host='127.0.0.1', port=8097):
    """Freeze launch identity; moving wrist extrinsics use get_camera_meta RPC."""
    config = _plain(getattr(env, 'base_cfg', {}))
    physics_hz = _lookup(config, 'physics', 'hz')
    control_hz = _lookup(config, 'physics', 'control_hz')
    ratio = None
    if physics_hz is not None and control_hz is not None:
        ratio = float(physics_hz) / float(control_hz)
        if abs(ratio - round(ratio)) > 1e-9:
            raise ValueError('physics/control frequency ratio must be an integer')
        ratio = int(round(ratio))
    config_json = json.dumps(config, sort_keys=True, ensure_ascii=False, default=_encode)
    return {
        'schema': 'labsim.Env_v1.rpent_environment.v1',
        'task': 'lab_cuvette_loading', 'version': _lookup(config, 'version', default='Env_v1'),
        'task_type': _lookup(config, 'env', 'task_type'),
        'scene_mode': _lookup(config, 'scene_mode'),
        'configuration_sha256': hashlib.sha256(config_json.encode()).hexdigest(),
        'robot_base_position_m': _lookup(config, 'robot', 'base_m'),
        'robot_base_quaternion_xyzw': _lookup(config, 'robot', 'base_quaternion_xyzw', default=[0., 0., 0., 1.]),
        'robot_base_orientation_basis': 'explicit config value; identity when original Franka assembly has no authored base rotation',
        'physics_hz': physics_hz, 'control_hz': control_hz,
        'physics_steps_per_control': ratio,
        'action_specs': copy.deepcopy(getattr(env, 'ACTION_SPECS', {})),
        'camera_names': ['side_camera', 'wrist_camera'],
        'cameras': {
            'side_camera': {'mounting': 'fixed_world', 'live_metadata_rpc': 'env.get_camera_meta'},
            'wrist_camera': {'mounting': 'robot_hand_link', 'live_metadata_rpc': 'env.get_camera_meta'},
        },
        'camera_configuration': _lookup(config, 'cameras', default={}),
        'observation_debug_exposed': False,
        'physics_while_waiting_for_rpc': 'paused; no app.update/world.step/render',
        'dispatch_thread': 'main',
        'framework_contract': 'deployed_rpent.BaseEnvFacade' if USING_DEPLOYED_RPENT_FACADE else 'explicit_compatible_fallback',
        'fallback_reason': _RPENT_IMPORT_ERROR,
        'transport': 'http', 'wire_format': 'RPent POST /call JSON with __ndarray__ base64/dtype/shape',
        'endpoint': f'http://{host}:{port}',
    }


class LabSimMainThreadFacade(_BaseEnvFacade):
    """Real BaseEnvFacade with a fixed RPC allowlist and main-thread dispatch."""
    ALLOWED_METHODS = frozenset({
        'healthz', 'shutdown', 'env.reset', 'env.step', 'env.chunk_step',
        'env.get_observation', 'env.render_camera', 'env.get_camera_meta',
        'env.get_task_language', 'env.get_env_meta', 'env.finalize_episode', 'env.close',
    })

    def __init__(self, env, *, metadata):
        self.env = env
        self.metadata = copy.deepcopy(metadata)
        self.owner_thread_id = threading.get_ident()
        self.request_log = []
        self.request_log_path = None
        super().__init__()

    def _register_rpc(self):
        # Register explicitly. This both implements the RPent base contract and
        # prevents future/debug/teacher methods from entering the public RPC.
        self._rpc.update({
            'env.reset': self.reset, 'env.step': self.step, 'env.chunk_step': self.chunk_step,
            'env.get_observation': self.get_observation,
            'env.render_camera': self.render_camera, 'env.get_camera_meta': self.get_camera_meta,
            'env.get_task_language': self.get_task_language, 'env.get_env_meta': self.get_env_meta,
            'env.finalize_episode': self.finalize_episode, 'env.close': self.close,
        })

    def dispatch(self, method, args=(), kwargs=None):
        if threading.get_ident() != self.owner_thread_id:
            raise RuntimeError('environment RPC dispatched outside its main owner thread')
        if method not in self.ALLOWED_METHODS:
            raise ValueError(f'RPC method is not public: {method}')
        event = {'method': method, 'thread_id': threading.get_ident(),
                 'started_wall_unix_s': time.time(), 'episode_id_before': getattr(self.env, 'episode_id', None),
                 'physics_steps_before': getattr(self.env, 'steps', None),
                 'simulation_time_before': getattr(self.env, 't', None)}
        started = time.perf_counter()
        try:
            result = super()._dispatch(method, tuple(args), kwargs or {})
            event['ok'] = True
            return result
        except Exception as exc:
            event.update(ok=False, error_type=type(exc).__name__, error=str(exc))
            raise
        finally:
            event.update(wall_time_s=time.perf_counter()-started,
                         episode_id_after=getattr(self.env, 'episode_id', None),
                         physics_steps_after=getattr(self.env, 'steps', None),
                         simulation_time_after=getattr(self.env, 't', None))
            self.request_log.append(event)
            if self.request_log_path:
                with self.request_log_path.open('a') as f:
                    f.write(json.dumps(event, default=_encode, allow_nan=False)+'\n')

    def get_env_meta(self):
        return copy.deepcopy(self.metadata)

    def reset(self, seed=None, options=None):
        return self.env.reset(seed=seed, options=options)

    def step(self, action):
        return self.env.step(action)

    def chunk_step(self, actions, return_all_frames=False):
        result = self.env.chunk_step(actions, return_all_frames=return_all_frames)
        if return_all_frames and not isinstance(result[0], list):
            info = dict(result[4])
            frames = info.pop('all_frames', None)
            if frames is None:
                raise RuntimeError('environment did not return requested per-action observations')
            # RPent BaseEnvClient requires obs_list in the first tuple field.
            result = (frames, result[1], result[2], result[3], info)
        return result

    def get_observation(self):
        return self.env.get_observation()

    def render_camera(self, camera_name, **kwargs):
        return self.env.render_camera(camera_name, **kwargs)

    def get_camera_meta(self, camera_name, **kwargs):
        return self.env.get_camera_meta(camera_name, **kwargs)

    def get_task_language(self):
        return self.env.get_task_language()

    def finalize_episode(self, termination_reason='POLICY_BUDGET', failure_type=None, episode_id=None):
        if episode_id is not None and episode_id != getattr(self.env, 'episode_id', None):
            raise ValueError('stale episode finalization refused')
        return self.env.finalize_episode(termination_reason=termination_reason, failure_type=failure_type)

    def close(self):
        self.env.close()
        self._shutdown_event.set()
        return {'closed': True}


class _Handler(BaseHTTPRequestHandler):
    # Accepted connection reads are bounded, including malformed partial clients.
    timeout = 10.0
    max_body_bytes = 64 * 1024 * 1024

    def log_message(self, format, *args):
        pass

    def do_POST(self):
        if self.path != '/call':
            self.send_error(404)
            return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= self.max_body_bytes:
                raise ValueError('invalid RPC Content-Length')
            request = _decode(json.loads(self.rfile.read(length)))
            if not isinstance(request, dict) or not isinstance(request.get('method'), str):
                raise ValueError('RPC request must contain a string method')
            if request.get('session_id') is not None:
                raise ValueError('environment transport is session-unaware; use episode_id in actions')
            result = self.server.facade.dispatch(request['method'], request.get('args', []), request.get('kwargs', {}))
            response = {'ok': True, 'result': result}
        except Exception as exc:
            response = {'ok': False, 'error': str(exc), 'traceback': traceback.format_exc()}
        try:
            body = json.dumps(response, default=_encode, ensure_ascii=False, allow_nan=False).encode()
        except Exception as exc:
            body = json.dumps({'ok': False, 'error': f'RPC response serialization failed: {exc}',
                               'traceback': traceback.format_exc()}).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            # The operation already ran; do not retry it automatically.
            pass


def serve_environment(env, host='127.0.0.1', port=8097, *, ready_path=None, launch_meta=None):
    """Block in the calling main thread; every environment call stays there.

    A ready JSON file can be used by a launcher instead of parsing stdout.
    RPC shutdown closes this loop; normal launcher cleanup still owns app.close.
    """
    if threading.current_thread() is not threading.main_thread():
        raise RuntimeError('serve_environment must be called on the main thread')
    server = HTTPServer((host, int(port)), _Handler)
    server.timeout = .1
    actual_port = int(server.server_address[1])
    meta = environment_metadata(env, host=host, port=actual_port)
    if launch_meta:
        meta['launcher_metadata'] = _plain(launch_meta)
    facade = LabSimMainThreadFacade(env, metadata=meta)
    server.facade = facade
    if ready_path:
        facade.request_log_path = Path(ready_path).with_suffix(".rpc.jsonl")
        facade.request_log_path.parent.mkdir(parents=True, exist_ok=True)
    if ready_path:
        target = Path(ready_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(meta, indent=2, ensure_ascii=False, default=_encode) + '\n')
    print(f'LabSim environment RPC listening on http://{host}:{actual_port} (main thread; synchronous physics)', flush=True)
    try:
        while not facade._shutdown_event.is_set() and not getattr(env, 'closed', False):
            # Do not pump SimulationApp or advance timeline while waiting.
            server.handle_request()
    finally:
        server.server_close()
        env.close()
    return meta
