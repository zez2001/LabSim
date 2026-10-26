"""Measured-force preload state machine; CPU evidence, not grasp physics."""
import inspect

import pytest

from demos.lab_cuvette_project_v1_1.gripper_hold import GenericContactHold


def make():
    return GenericContactHold(control_hz=60, mass_kg=.02, dynamic_friction=.5,
        finger_dynamic_friction=.8, finger_kp_N_per_m=2000, contact_safety_factor=2,
        maximum_compression_m=.0003, contact_threshold_N=.03, contact_persist_s=.1,
        contact_approach_speed_m_s=.002)


def step(h, t, previous=.010418463, **kw):
    values=dict(t=t, logical_requested_opening_m=.010418463, ramped_opening_m=.010418463,
        previous_applied_opening_m=previous, measured_finger_positions_m=[.00536434]*2,
        finger_contact_N=[.208, .389], effort_limit_N=8.)
    values.update(kw)
    return h.update(**values)


def test_recorded_underload_closes_only_at_declared_speed_after_persistence():
    h=make(); p, _=step(h, 0.)
    assert h.minimum_hold_normal_force_N == pytest.approx(.310219438462518)
    for n in range(1, 6):
        q, d=step(h,n/60,p)
        assert q==p and not d['force_hold_applied']
        p=q
    q,d=step(h,.1,p)
    assert p-q==pytest.approx(.002/60)
    assert d['confirmed'] and d['force_hold_applied']
    assert d['decision']=='low_measured_normal_force_slow_close'
    assert d['effort_limit_N']==8. and d['force_cap_modified'] is False
    assert d['task_phase_or_object_pose_used'] is False


def test_measured_adequate_force_stops_closure_and_never_reopens():
    h=make();p,_=step(h,0.);p,_=step(h,.1,p)
    for n in range(7,20):
        q,d=step(h,n/60,p,finger_contact_N=[.31,.32])
        assert q==p and not d['force_hold_applied']
        p=q


def test_repeated_same_sample_cannot_close_again():
    h=make();p,_=step(h,0.);p,_=step(h,.1,p)
    q,d=step(h,.1,p)
    assert q==p and not d['force_hold_applied']


@pytest.mark.parametrize('effort',[0.,.05,.3,None])
def test_explicit_low_effort_unload_or_legacy_caller_disables_preload(effort):
    h=make();p,_=step(h,0.)
    q,d=step(h,.1,p,effort_limit_N=effort)
    assert q==p and not d['force_hold_enabled'] and not d['force_hold_applied']


def test_slow_symmetric_opening_has_priority_over_force_maintenance():
    h=make();p,_=step(h,0.);p,_=step(h,.1,p)
    q,d=step(h,.12,p,logical_requested_opening_m=.02,ramped_opening_m=.011)
    assert p<q<=.011 and q-p==pytest.approx(.011-.010418463)
    assert d['decision']=='explicit_opening_ramp'
    assert not d['force_hold_enabled'] and not d['force_hold_applied']


def test_one_contact_lost_does_not_use_bilateral_force_rule():
    h=make();p,_=step(h,0.);p,_=step(h,.1,p)
    q,d=step(h,.12,p,finger_contact_N=[0.,.2])
    assert not d['force_hold_applied']
    assert d['decision']=='contact_loss_slow_close' and q<=p


def test_lower_opening_bound_remains_enforced():
    h=make();p,_=step(h,0.,previous=.002)
    q,d=step(h,.1,p)
    assert q==.002 and not d['force_hold_applied']


@pytest.mark.parametrize('opening',[0.,.001,.00199])
def test_low_prior_command_is_never_automatically_opened(opening):
    h=make();p,_=step(h,0.,previous=opening)
    q,d=step(h,.1,p)
    assert q<=p and q==opening and not d['force_hold_applied']


def test_persistent_low_sensor_force_cannot_integrate_to_minimum_opening():
    h=make();p,_=step(h,0.);initial=p
    for n in range(1,601):p,d=step(h,n/60,p)
    assert initial-p==pytest.approx(2*h.maximum_compression_m)
    assert p>.009 and not d['force_hold_applied']


def test_teacher_stale_logical_unload_preserves_small_scheduled_increment():
    h=make();p,_=step(h,0.)
    for n in range(1,8):p,_=step(h,n/60,p)
    before=p;increment=.000001723
    q,d=step(h,.1+2/60,p,logical_requested_opening_m=.010418463+increment,
        ramped_opening_m=.010418463+increment)
    assert q-before==pytest.approx(increment)
    assert d['decision']=='explicit_opening_ramp' and not d['force_hold_applied']
    # Finish the requested ramp; bounded catch-up reaches the final request.
    final=.010418463+increment
    for n in range(3,80):
        q,d=step(h,.1+n/60,q,logical_requested_opening_m=final,ramped_opening_m=final,
            finger_contact_N=[0.,0.],effort_limit_N=.05)
        if not d['explicit_opening_ramp_active']:break
    assert q==pytest.approx(final) and not d['explicit_opening_ramp_active']


def test_old_caller_without_preload_keeps_original_opening_behavior():
    h=make();p,_=step(h,0.,effort_limit_N=None)
    q,d=step(h,.1,p,effort_limit_N=None,logical_requested_opening_m=.02,ramped_opening_m=.011)
    assert q==.011 and not d['release_slew_active']


def test_identical_release_sample_is_idempotent_and_cannot_revert_target():
    h=make();p,_=step(h,0.)
    for n in range(1,8):p,_=step(h,n/60,p)
    kw=dict(logical_requested_opening_m=.02,ramped_opening_m=.01042)
    result=step(h,8/60,p,**kw)
    for _ in range(100):assert step(h,8/60,p,**kw)==result


def test_paused_intermediate_ramp_cannot_catch_up_to_unrequested_final_goal():
    h=make();p,_=step(h,0.)
    for n in range(1,8):p,_=step(h,n/60,p)
    for n in range(8,200):
        p,d=step(h,n/60,p,logical_requested_opening_m=.08,ramped_opening_m=.011)
        assert p<=.011
    assert p==pytest.approx(.011) and d['explicit_opening_ramp_active']


def test_explicit_closing_reversal_exits_force_corrected_release_mode():
    h=make();p,_=step(h,0.)
    for n in range(1,8):p,_=step(h,n/60,p)
    p,_=step(h,8/60,p,logical_requested_opening_m=.02,ramped_opening_m=.01042)
    p,d=step(h,9/60,p,logical_requested_opening_m=.009,ramped_opening_m=.0103)
    assert d['closing_reversal'] and not d['release_slew_active'] and not d['explicit_opening_ramp_active']


def test_loss_recontact_does_not_reset_additional_feedback_closure_budget():
    h=make();p,_=step(h,0.);initial=p
    for n in range(1,50):p,_=step(h,n/60,p)
    assert initial-p==pytest.approx(.0006)
    p,_=step(h,50/60,p,finger_contact_N=[0.,0.])
    for n in range(51,90):p,d=step(h,n/60,p)
    assert initial-p==pytest.approx(.0006)
    assert d['force_hold_reference_opening_m']==initial


@pytest.mark.parametrize('effort',[-1.,float('nan'),float('inf')])
def test_bad_effort_is_rejected(effort):
    with pytest.raises(ValueError):step(make(),0.,effort_limit_N=effort)


def test_preload_accepts_only_declared_robot_signals():
    names=set(inspect.signature(GenericContactHold.update).parameters)
    assert names=={'self','t','logical_requested_opening_m','ramped_opening_m',
        'previous_applied_opening_m','measured_finger_positions_m','finger_contact_N','effort_limit_N'}
