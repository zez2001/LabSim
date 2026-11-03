"""Run the frozen restored debug04 profile on the current standard environment.

--check-only never imports Isaac, reads credentials, creates a ledger or calls a
model. Paid execution requires a separately recorded, explicit owner grant.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

from policy.backends.gpt_debug04_v1 import budget


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TEMPLATE = ROOT / 'config/lab_cuvette_loading/Gpt_debug04_v1/protocol_template.json'


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--protocol', type=Path, default=DEFAULT_TEMPLATE)
    p.add_argument('--authorization', type=Path)
    p.add_argument('--ledger', type=Path)
    p.add_argument('--trial-id', default='debug04_01')
    p.add_argument('--output', type=Path)
    p.add_argument('--check-only', action='store_true')
    p.add_argument('--headless', action='store_true')
    p.add_argument('--credential-file', type=Path,
                   default=Path.home()/'.local/share/labsim/credentials/cubence.key')
    return p


def validate_profile(protocol):
    for name, expected in protocol['locked_source_files'].items():
        if budget.sha256(ROOT/name) != expected:
            raise ValueError('Frozen source differs: ' + name)
    from policy.backends.gpt_debug04_v1.vendor import cubence_project_v1_1_tools as tools
    from policy.backends.gpt_debug04_v1.vendor.cubence_tools import tool_definitions
    if hashlib.sha256(tools.SYSTEM_PROMPT.encode()).hexdigest() != protocol['prompt_sha256']:
        raise ValueError('Historical prompt changed')
    schema_sha = hashlib.sha256(json.dumps(tool_definitions(),sort_keys=True,separators=(',',':')).encode()).hexdigest()
    if schema_sha != protocol['tool_schema_canonical_sha256']:
        raise ValueError('Historical tool schema changed')


def main(argv=None):
    args = parser().parse_args(argv)
    protocol = budget.read_json(args.protocol)
    validate_profile(protocol)
    plan = {row['trial_id']:row for row in protocol['trials']}
    if args.trial_id not in plan:
        raise ValueError('Trial is not in the declared ten-episode plan')
    original_ledger = ROOT/protocol['original_budget_ledger']
    if args.check_only:
        print(json.dumps(dict(valid=True, profile_id=protocol['profile_id'],
            historical_episode_id=protocol['historical_episode_id'],
            template_sha256=budget.sha256(args.protocol), trial_id=args.trial_id,
            model_calls=0, credential_read=False, ledger_created=False,
            authorization_required=True, current_environment=protocol['environment']),indent=2))
        return 0
    funding = budget.inspect_authorization(args.authorization, template=args.protocol,
                                          original_ledger=original_ledger)
    trial_number = int(args.trial_id.rsplit('_',1)[-1])
    if trial_number > funding['authorization']['maximum_formal_episodes']:
        raise PermissionError('This trial exceeds the explicitly authorized episode count')
    if args.output is None or args.ledger is None:
        raise ValueError('Paid execution requires new --output and dedicated --ledger paths')
    output, ledger = args.output.resolve(), args.ledger.resolve()
    if output.exists() or ledger == original_ledger.resolve():
        raise ValueError('Never overwrite an output or reuse the protected historical ledger')
    if subprocess.check_output(['git','status','--porcelain'],cwd=ROOT).strip():
        raise ValueError('Commit the frozen implementation before a formal trial')
    head = subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    value = budget.prepare_ledger(ledger, funding, create=True)
    budget.require_start_allowance(value, minimum_usd=protocol['minimum_start_allowance_usd'],
        maximum_new_network_attempts=protocol['maximum_network_attempts_per_episode'])
    credential = args.credential_file
    if credential.stat().st_mode & 0o077:
        raise PermissionError('Credential file must be private to its owner')
    key = credential.read_text().strip()
    if not key:
        raise ValueError('Credential unavailable')
    budget.claim_trial(ledger,args.trial_id,output=output,runtime_commit=head,
        minimum_usd=protocol['minimum_start_allowance_usd'],
        maximum_new_network_attempts=protocol['maximum_network_attempts_per_episode'])
    frozen = dict(protocol, schema='labsim.gpt_debug04.executed_protocol.v1',status='frozen',
        runtime_commit=head, protocol_template_sha256=budget.sha256(args.protocol),
        authorization_sha256=funding['authorization_sha256'],
        historical_ledger_sha256=funding['original_sha256'],
        actual_trial_id=args.trial_id, ledger=str(ledger))
    # This receipt is written before the first model access. The launcher's
    # exclusive output creation remains the owner of the episode directory.
    receipt = output.with_name(output.name+'.frozen_protocol.json')
    receipt.parent.mkdir(parents=True,exist_ok=True)
    with receipt.open('x') as stream:json.dump(frozen,stream,indent=2);stream.write('\n')
    from policy.backends.gpt_debug04_v1.vendor.cubence_project_v1_1_tools import run_episode
    os.environ.update(LABSIM_ASSET_ROOT=protocol['environment']['asset_root'],
        OMNI_KIT_ACCEPT_EULA='YES',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',
        TOKENIZERS_PARALLELISM='false',PYTHONHASHSEED='0')
    from demos.lab_cuvette_project_release_v1.launch import main as launch
    command = ['--backend','gpt6','--config',str(ROOT/protocol['environment']['configuration']),
        '--layout-mode','standard','--episodes','1','--seed','0',
        '--execution-purpose','eval','--record-mode','eval','--record-purpose','policy_evaluation',
        '--progress','--max-calls',str(protocol['max_calls']),
        '--provider-config',str(ROOT/protocol['provider_config']),
        '--budget-ledger',str(ledger),'--output',str(output)]
    if args.headless:command.append('--headless')
    previous = os.environ.get('CUBENCE_API_KEY')
    os.environ['CUBENCE_API_KEY'] = key
    try:
        return launch(command,
            gpt_client_factory=lambda config,path:budget.create_client(config,path,funding),
            gpt_episode_runner=run_episode,
            gpt_profile_identity=dict(profile_id=protocol['profile_id'],
                original_episode_id=protocol['historical_episode_id'],
                original_source_commit=protocol['historical_source_commit'],
                protocol_sha256=budget.sha256(receipt),trial_id=args.trial_id,
                financial_overlay_only=True))
    finally:
        if previous is None:os.environ.pop('CUBENCE_API_KEY',None)
        else:os.environ['CUBENCE_API_KEY']=previous


if __name__ == '__main__':
    # Match the existing release launcher after its explicit writer/app close.
    # Avoid a second native-finalizer teardown while preserving failed exits.
    import sys
    try:
        code = main()
    except SystemExit as error:
        code = int(error.code or 0)
    except BaseException:
        import traceback
        traceback.print_exc()
        code = 1
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(code)
