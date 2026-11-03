"""Run one declared evaluation trial through unchanged release entry points.

No policy implementation, action transformation, task scoring or asset edits.
The caller freezes a protocol, uses a clean source checkout and keeps the
shared paid-provider ledger. Outputs are exclusive and never reused.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.request


SECRETS = ('CUBENCE_API_KEY', 'OPENAI_API_KEY', 'HF_TOKEN',
           'HUGGING_FACE_HUB_TOKEN', 'HUGGINGFACEHUB_API_TOKEN', 'CODEX_API_KEY')


def utc():
    return datetime.now(timezone.utc).isoformat()


def write(path, value):
    path = Path(path)
    temp = path.with_name('.' + path.name + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    temp.replace(path)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(8 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def rpc(port, method):
    body = json.dumps(dict(method=method, args=[], kwargs={}, session_id=None)).encode()
    req = urllib.request.Request(f'http://127.0.0.1:{port}/call', data=body,
                                 headers={'Content-Type': 'application/json'})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(req, timeout=5) as response:
        result = json.loads(response.read())
    if result.get('ok') is not True:
        raise RuntimeError('Local RPC rejected ' + method)
    return result['result']


def wait_ready(child, port, method, timeout=420):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if child.poll() is not None:
            raise RuntimeError('Service exited before readiness')
        try:
            return rpc(port, method)
        except (OSError, ValueError, RuntimeError):
            time.sleep(2)
    raise TimeoutError('Local service readiness deadline')


def gpt_command(common, common_options, root, protocol, output, diagnostic):
    """Explicit single episode: legacy eval defaults to five repeats."""
    return common + ['eval', '--backend', 'gpt6', '--episodes', '1', *common_options,
        '--provider-config', str(root/protocol['gpt6']['provider_config']),
        '--budget-ledger', protocol['budget']['ledger'], '--max-calls',
        str(1 if diagnostic else protocol['gpt6']['max_calls']),
        '--output', str(output/'environment')]


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--protocol', type=Path, required=True)
    p.add_argument('--checkout', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--group', choices=('gpt6', 'pi05'), required=True)
    p.add_argument('--phase', choices=('diagnostic', 'formal'), required=True)
    p.add_argument('--trial-id', required=True)
    p.add_argument('--check-only', action='store_true',
                   help='Validate immutable protocol/source and print identity; no output or model start')
    p.add_argument('--credential-file', type=Path,
                   default=Path.home()/'.local/share/labsim/credentials/cubence.key')
    args = p.parse_args(argv)
    protocol = json.loads(args.protocol.read_text())
    if args.phase == 'formal' and (protocol.get('status') != 'frozen' or
            protocol.get('preflight_passed') is not True):
        raise ValueError('Formal trials require the frozen, preflight-passed protocol')
    root = args.checkout.resolve()
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
    if head != protocol['environment']['runtime_commit']:
        raise ValueError('Runtime commit differs from protocol')
    if subprocess.check_output(['git', 'status', '--porcelain'], cwd=root).strip():
        raise ValueError('Use a clean runtime checkout')
    for name, expected in protocol['locked_source_files'].items():
        if digest(root/name) != expected:
            raise ValueError('Frozen source differs: ' + name)
    if args.check_only:
        print(json.dumps(dict(valid=True, runtime_commit=head,
            protocol_sha256=digest(args.protocol), group=args.group, phase=args.phase,
            actual_models_started=False, output_created=False), indent=2))
        return 0
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    env = dict(os.environ)
    for name in SECRETS:
        env.pop(name, None)
    env.update(LABSIM_ASSET_ROOT=protocol['environment']['asset_root'],
               OMNI_KIT_ACCEPT_EULA='YES', PYTHONHASHSEED='0',
               HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1',
               TOKENIZERS_PARALLELISM='false')
    status = dict(schema='labsim.policy_eval.supervisor.v1', phase=args.phase,
                  group=args.group, trial_id=args.trial_id, started_utc=utc(),
                  runtime_commit=head, protocol_sha256=digest(args.protocol),
                  supervisor_sha256=digest(__file__), children=[], status='starting',
                  credential_contents_saved=False)
    started = time.perf_counter()
    children = []
    handles = []

    def update(**fields):
        status.update(fields, updated_utc=utc(), wall_seconds=time.perf_counter()-started)
        write(output/'supervisor.json', status)

    def start(name, command, child_env=env):
        handle = (output/(name+'.native.log')).open('x')
        handles.append(handle)
        child = subprocess.Popen(command, cwd=root, env=child_env, stdout=handle,
                                 stderr=subprocess.STDOUT)
        item = dict(name=name, pid=child.pid, command=command, started_utc=utc(),
                    credentials_in_child=name=='gpt_environment')
        children.append((child, item)); status['children'].append(item)
        update(status='running', active_child=name)
        return child

    def wait(child, deadline):
        while child.poll() is None:
            if time.perf_counter()-started > deadline:
                raise TimeoutError('Declared supervisor wall-clock protection')
            update(status='running')
            time.sleep(5)
        return child.wait()

    isaac = protocol['environment']['isaac_python']
    policy_python = protocol['pi05']['python']
    purpose = 'lifecycle_diagnostic' if args.phase=='diagnostic' else 'policy_evaluation'
    common = [isaac, str(root/'scripts/labsim_cli.py')]
    common_options = ['--project-version', 'Project_release_v1', '--headless',
                      '--record-mode', 'eval', '--record-purpose', purpose, '--progress']
    try:
        if args.group == 'gpt6':
            child_env = dict(env)
            credential = args.credential_file
            if credential.stat().st_mode & 0o077:
                raise ValueError('Credential file must be private to its owner')
            child_env['CUBENCE_API_KEY'] = credential.read_text().strip()
            if not child_env['CUBENCE_API_KEY']:
                raise ValueError('Credential unavailable')
            command = gpt_command(common, common_options, root, protocol, output,
                                  args.phase=='diagnostic')
            child = start('gpt_environment', command, child_env)
            code = wait(child, protocol['execution']['supervisor_wall_s'])
            child_env.pop('CUBENCE_API_KEY', None)
            update(policy_exit_code=code)
        else:
            for port in (8097,8098):
                with socket.socket() as sock:
                    sock.settimeout(.2)
                    if sock.connect_ex(('127.0.0.1',port)) == 0:
                        raise RuntimeError('Required RPC port already in use')
            environment = start('environment', common + ['serve', *common_options,
                '--port', '8097', '--output', str(output/'environment')])
            ready = wait_ready(environment, 8097, 'env.get_env_meta')
            update(environment_metadata=ready)
            model = start('model', [policy_python, '-m',
                'policy_backends.lab_cuvette_env_v1.pi05_server', '--model-path',
                protocol['pi05']['checkpoint'], '--output', str(output/'model'),
                '--host','127.0.0.1','--port','8098','--seed','0'])
            update(model_metadata=wait_ready(model,8098,'vla.get_metadata'))
            diagnostic = args.phase=='diagnostic'
            policy = start('policy', [policy_python,'-m','policy.backends.rpent_compat',
                '--backend','pi05','--policy-config',str(root/protocol['pi05']['policy_config']),
                '--env-endpoint','http://127.0.0.1:8097',
                '--vla-endpoint','http://127.0.0.1:8098','--output',str(output/'policy'),
                '--max-simulation-s',str(.25 if diagnostic else protocol['environment']['simulation_limit_s']),
                '--max-model-requests',str(1 if diagnostic else protocol['pi05']['max_model_requests']),
                '--max-actions',str(5 if diagnostic else protocol['pi05']['max_actions']),
                '--seed','0'])
            code=wait(policy,protocol['execution']['supervisor_wall_s'])
            update(policy_exit_code=code)
            rpc(8097,'shutdown'); wait(environment,protocol['execution']['supervisor_wall_s'])
            rpc(8098,'shutdown'); wait(model,protocol['execution']['supervisor_wall_s'])
        update(status='closed', finished_utc=utc())
    except BaseException as error:
        update(status='supervisor_error', error_type=type(error).__name__,
               error=str(error), automatic_retry=False)
        for port in (8097,8098):
            try: rpc(port,'shutdown')
            except Exception: pass
        raise
    finally:
        for child,item in reversed(children):
            if child.poll() is None:
                child.terminate()
                try:child.wait(timeout=60)
                except subprocess.TimeoutExpired:child.kill();child.wait()
            item.update(exit_code=child.returncode,process_exited=True,
                        native_pid_gone=not Path('/proc',str(child.pid)).exists())
        for handle in handles:handle.close()
        update()
        if (output/'environment').exists():
            write(output/'environment'/'process_exit.json', dict(status,
                process_exited=True, exit_code=next((i['exit_code'] for _,i in children
                    if i['name'] in ('gpt_environment','environment')),None),
                completion_evidence='Parent Popen.wait completed; native PID absent'))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
