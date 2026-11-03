"""Behavioral checks for explicit funding and preserving historical expenses."""
import copy
import json

import pytest

from policy.backends.gpt_debug04_v1 import budget


def fixture(tmp_path):
    template=tmp_path/'protocol.json';template.write_text('{"profile":"restored"}')
    original=tmp_path/'old.json'
    original.write_text(json.dumps(dict(attempts=[dict(request_id='old',status='COMPLETED',charged_estimate_usd=29.2)],
        max_requests=1500,max_estimated_usd=30.,pricing={})))
    authorization=tmp_path/'grant.json'
    value=dict(schema=budget.SCHEMA,approved=True,profile_id=budget.PROFILE,
        authorization_evidence='explicit test fixture; not a real funding approval',
        protocol_template_sha256=budget.sha256(template),original_ledger_sha256=budget.sha256(original),
        base_attempt_count=1,base_estimated_usd=29.2,additional_estimated_usd=20.,
        additional_network_attempts=480,maximum_formal_episodes=1,
        authorized_ledger_path=str(tmp_path/'new.json'))
    authorization.write_text(json.dumps(value))
    return template,original,authorization,value


def test_missing_or_pending_authorization_never_creates_ledger(tmp_path):
    template,old,auth,value=fixture(tmp_path)
    with pytest.raises(PermissionError):
        budget.inspect_authorization(None,template=template,original_ledger=old)
    value['approved']=False;auth.write_text(json.dumps(value))
    with pytest.raises(PermissionError):
        budget.inspect_authorization(auth,template=template,original_ledger=old)
    assert not (tmp_path/'new.json').exists()


def test_explicit_allowance_preserves_full_expense_prefix_and_original_file(tmp_path):
    template,old,auth,_=fixture(tmp_path);before=old.read_bytes()
    funding=budget.inspect_authorization(auth,template=template,original_ledger=old)
    ledger=tmp_path/'new.json';value=budget.prepare_ledger(ledger,funding,create=True)
    assert old.read_bytes()==before
    assert value['attempts']==json.loads(before)['attempts']
    assert value['max_estimated_usd']==pytest.approx(49.2)
    assert value['max_requests']==481
    value['attempts'].append(dict(request_id='new',status='COMPLETED',charged_estimate_usd=.2))
    ledger.write_text(json.dumps(value))
    assert len(budget.prepare_ledger(ledger,funding)['attempts'])==2
    assert old.read_bytes()==before


def test_tampered_history_and_grant_are_rejected(tmp_path):
    template,old,auth,_=fixture(tmp_path)
    funding=budget.inspect_authorization(auth,template=template,original_ledger=old)
    ledger=tmp_path/'new.json';value=budget.prepare_ledger(ledger,funding,create=True)
    value['attempts'][0]['charged_estimate_usd']=0;ledger.write_text(json.dumps(value))
    with pytest.raises(ValueError,match='prefix'):budget.prepare_ledger(ledger,funding)
    old.write_text(old.read_text()+'\n')
    with pytest.raises(ValueError,match='ledger changed'):
        budget.inspect_authorization(auth,template=template,original_ledger=old)


def test_trial_claim_is_exclusive_and_low_allowance_does_not_start(tmp_path):
    template,old,auth,_=fixture(tmp_path)
    funding=budget.inspect_authorization(auth,template=template,original_ledger=old)
    ledger=tmp_path/'new.json';budget.prepare_ledger(ledger,funding,create=True)
    options=dict(output=tmp_path/'trial',runtime_commit='commit',minimum_usd=15.,maximum_new_network_attempts=480)
    budget.claim_trial(ledger,'debug04_01',**options)
    with pytest.raises(ValueError,match='already claimed'):budget.claim_trial(ledger,'debug04_01',**options)
    value=budget.read_json(ledger);value['attempts'].append(dict(charged_estimate_usd=19.,status='COMPLETED'))
    ledger.write_text(json.dumps(value));before=ledger.read_bytes()
    with pytest.raises(PermissionError,match='INSUFFICIENT_FULL_OPPORTUNITY'):
        budget.claim_trial(ledger,'debug04_02',**options)
    assert ledger.read_bytes()==before


def test_one_grant_cannot_create_multiple_ledgers(tmp_path):
    template,old,auth,_=fixture(tmp_path)
    funding=budget.inspect_authorization(auth,template=template,original_ledger=old)
    first=tmp_path/'new.json';budget.prepare_ledger(first,funding,create=True)
    with pytest.raises(PermissionError,match='LEDGER_PATH_MISMATCH'):
        budget.prepare_ledger(tmp_path/'another.json',funding,create=True)
    assert not (tmp_path/'another.json').exists()


@pytest.mark.parametrize('episode_count',[True,1.0])
def test_episode_allowance_is_an_explicit_integer(tmp_path,episode_count):
    template,old,auth,value=fixture(tmp_path)
    value['maximum_formal_episodes']=episode_count;auth.write_text(json.dumps(value))
    with pytest.raises(ValueError,match='allowance'):
        budget.inspect_authorization(auth,template=template,original_ledger=old)


def test_financial_overlay_changes_no_policy_or_action_field():
    config=dict(max_estimated_usd=30.,max_requests=1500,prompt='unchanged',
        images=dict(detail='high'),action_limits=dict(max_translation_m=.04))
    saved=copy.deepcopy(config)
    result=budget.authorized_configuration(config,dict(cumulative_usd=49.2,cumulative_requests=857))
    assert config==saved
    assert {k:v for k,v in result.items() if k not in ('max_estimated_usd','max_requests')} == {
        k:v for k,v in saved.items() if k not in ('max_estimated_usd','max_requests')}
