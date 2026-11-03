"""Explicit owner-authorized funding for the restored historical profile only.

The historical $30 ledger is never edited or reset. An approved experiment
ledger retains every historical attempt and adds only the authorized allowance.
No authorization is inferred from the presence of a credential or a profile.
"""
from __future__ import annotations

import copy
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile


SCHEMA = 'labsim.gpt_debug04.budget_authorization.v1'
PROFILE = 'gpt_debug04_v1'


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text())


def inspect_authorization(path, *, template, original_ledger):
    """Validate a concrete human grant before any credential or model access."""
    if path is None or not Path(path).is_file():
        raise PermissionError('BUDGET_AUTHORIZATION_REQUIRED: historical analysis is free; new API calls require the owner-approved allowance')
    value = read_json(path)
    if (value.get('schema') != SCHEMA or value.get('approved') is not True
            or value.get('profile_id') != PROFILE
            or not str(value.get('authorization_evidence', '')).strip()):
        raise PermissionError('Explicit owner budget authorization is missing')
    if value.get('protocol_template_sha256') != sha256(template):
        raise ValueError('Authorization is for a different frozen policy protocol')
    original = read_json(original_ledger)
    if value.get('original_ledger_sha256') != sha256(original_ledger):
        raise ValueError('Original cumulative ledger changed; reassess the proposal before starting')
    attempts = original['attempts']
    if any(row.get('status') == 'RESERVED' for row in attempts):
        raise ValueError('Unsettled historical network attempt; do not create another budget')
    count, spent = len(attempts), sum(row['charged_estimate_usd'] for row in attempts)
    if (value.get('base_attempt_count') != count
            or abs(float(value.get('base_estimated_usd', -1)) - spent) > 1e-8):
        raise ValueError('Authorization does not preserve the actual historical expense prefix')
    allowance = float(value['additional_estimated_usd'])
    requests = value['additional_network_attempts']
    episodes = value['maximum_formal_episodes']
    if (not math.isfinite(allowance) or allowance <= 0
            or not isinstance(requests, int) or isinstance(requests, bool) or requests < 1
            or not isinstance(episodes, int) or isinstance(episodes, bool)
            or episodes not in (1, 10)):
        raise ValueError('Invalid finite authorized cost/request/episode allowance')
    authorized_ledger = Path(value.get('authorized_ledger_path', ''))
    if not authorized_ledger.is_absolute() or authorized_ledger.resolve() == Path(original_ledger).resolve():
        raise ValueError('Authorization must bind one distinct absolute cumulative ledger path')
    return dict(authorization=value, authorization_sha256=sha256(path),
                original=original, original_sha256=sha256(original_ledger),
                authorized_ledger_path=str(authorized_ledger.resolve()),
                cumulative_usd=spent + allowance, cumulative_requests=count + requests,
                base_count=count, base_spent=spent)


def authorized_configuration(original_config, funding):
    """Change financial guards only; native policy/action configuration is exact."""
    cfg = copy.deepcopy(original_config)
    cfg['max_estimated_usd'] = funding['cumulative_usd']
    cfg['max_requests'] = funding['cumulative_requests']
    return cfg


def prepare_ledger(path, funding, *, create=False):
    path = Path(path).resolve()
    if str(path) != funding['authorized_ledger_path']:
        raise PermissionError('AUTHORIZATION_LEDGER_PATH_MISMATCH: one grant cannot fund several fresh ledgers')
    if not path.exists():
        if not create:
            raise ValueError('Authorized cumulative ledger has not been initialized')
        value = copy.deepcopy(funding['original'])
        value.update(max_estimated_usd=funding['cumulative_usd'],
                     max_requests=funding['cumulative_requests'],
                     restored_profile_authorization_sha256=funding['authorization_sha256'],
                     historical_ledger_sha256=funding['original_sha256'])
        path.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive creation prevents replacing any existing experiment ledger.
        with path.open('x') as stream:
            json.dump(value, stream, indent=2, allow_nan=False)
            stream.write('\n')
    value = read_json(path)
    base = funding['original']['attempts']
    if (value.get('attempts', [])[:len(base)] != base
            or value.get('restored_profile_authorization_sha256') != funding['authorization_sha256']
            or value.get('historical_ledger_sha256') != funding['original_sha256']
            or value.get('max_requests') != funding['cumulative_requests']
            or abs(float(value.get('max_estimated_usd', -1)) - funding['cumulative_usd']) > 1e-8):
        raise ValueError('Authorized ledger prefix, identity or financial caps differ')
    return value


def require_start_allowance(ledger, *, minimum_usd, maximum_new_network_attempts):
    used = sum(row['charged_estimate_usd'] for row in ledger['attempts'])
    if ledger['max_estimated_usd'] - used + 1e-9 < minimum_usd:
        raise PermissionError('INSUFFICIENT_FULL_OPPORTUNITY_ALLOWANCE: do not start a predictably short budget-censored trial')
    if ledger['max_requests'] - len(ledger['attempts']) < maximum_new_network_attempts:
        raise PermissionError('INSUFFICIENT_FULL_OPPORTUNITY_REQUEST_ALLOWANCE')


def claim_trial(path, trial_id, *, output, runtime_commit, minimum_usd,
                maximum_new_network_attempts):
    """A planned trial ID is used once, including startup/recording failures."""
    path = Path(path)
    with path.with_suffix(path.suffix+'.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        value = read_json(path)
        require_start_allowance(value, minimum_usd=minimum_usd,
            maximum_new_network_attempts=maximum_new_network_attempts)
        trials = value.setdefault('restored_formal_trials', {})
        if trial_id in trials:
            raise ValueError('Formal trial ID already claimed; retain the original result instead of silently rerunning it')
        trials[trial_id] = dict(output=str(Path(output).resolve()),
            runtime_commit=runtime_commit, status='claimed_before_environment_start',
            source='predeclared frozen plan; startup/closed result determines actual started status')
        descriptor, temporary = tempfile.mkstemp(prefix=path.name+'.',dir=path.parent)
        try:
            with os.fdopen(descriptor,'w') as stream:
                json.dump(value,stream,indent=2,allow_nan=False)
                stream.write('\n')
            os.replace(temporary,path)
        finally:
            if Path(temporary).exists():Path(temporary).unlink()


def create_client(provider_config, ledger_path, funding):
    """Use the exact historical transport with an explicit financial overlay."""
    from .vendor.cubence import BudgetLedger, CubenceClient, load_config
    original = load_config(provider_config)  # Original provider/model/$30 validation.
    executed = authorized_configuration(original, funding)
    ledger = BudgetLedger(ledger_path, executed)
    # The original constructor validates the exact original policy configuration.
    # Only after it succeeds are the authorized accounting caps installed. All
    # request, retry, usage, reservation, prompt and action logic remains vendor.
    client = CubenceClient(original, ledger)
    client.cfg = executed
    return client
