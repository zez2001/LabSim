"""Independent CPU counterexamples; never runs a simulator or provider."""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[5]
HERE = Path(__file__).resolve().parent
SOURCE = ROOT / 'demos/lab_cuvette_project_v1_1/gripper_hold.py'


def main():
    output = HERE / 'review_revised_snapshot.json'
    if output.exists():
        raise FileExistsError('Refusing to replace prior audit evidence')
    source = SOURCE.read_bytes()
    namespace = {}
    exec(compile(source, 'snapshot:gripper_hold.py', 'exec'), namespace)
    cls = namespace['GenericContactHold']

    def make():
        return cls(control_hz=60, mass_kg=.02, dynamic_friction=.5,
            finger_dynamic_friction=.8, finger_kp_N_per_m=2000,
            contact_safety_factor=2, maximum_compression_m=.0003,
            contact_threshold_N=.03, contact_persist_s=.1,
            contact_approach_speed_m_s=.002)

    latch = .010418463

    def step(h, t, previous=latch, **kw):
        values = dict(t=t, logical_requested_opening_m=latch,
            ramped_opening_m=latch, previous_applied_opening_m=previous,
            measured_finger_positions_m=[.00536434]*2,
            finger_contact_N=[.208, .389], effort_limit_N=8.)
        values.update(kw)
        return h.update(**values)

    result = dict(schema='labsim.force_hold_v2_independent_review.revised.v1',
        scope='Synthetic controls and robot sensors exercised on captured Python source bytes; no physical success claim.',
        source='demos/lab_cuvette_project_v1_1/gripper_hold.py',
        source_SHA256=hashlib.sha256(source).hexdigest(),
        Git_HEAD=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        source_git_differs_from_HEAD=bool(subprocess.check_output(
            ['git', 'diff', 'HEAD', '--', 'demos/lab_cuvette_project_v1_1/gripper_hold.py'], cwd=ROOT)),
        never_open_boundary_examples=[])
    for previous in (0., .001, .00199, .002):
        h=make(); first,_=step(h, 0., previous)
        after,d=step(h, .1, first)
        assert first == previous and after == previous
        result['never_open_boundary_examples'].append(dict(
            prior_command_m=previous, after_persistence_m=after,
            increase_m=after-previous, force_hold_applied=d['force_hold_applied']))

    h=make(); p,_=step(h,0.); initial=p
    max_step=0.
    for n in range(1,601):
        q,d=step(h,n/60,p)
        max_step=max(max_step,p-q)
        assert q <= p+1e-15
        assert p-q <= .002/60+1e-14
        p=q
    assert abs(initial-p-.0006)<1e-12
    reference=d['force_hold_reference_opening_m']
    p,_=step(h,601/60,p,finger_contact_N=[0.,0.])
    for n in range(602,701):
        p,d=step(h,n/60,p)
    assert reference==d['force_hold_reference_opening_m']
    assert abs(initial-p-.0006)<1e-12
    result['persistent_underload_and_loss_recontact']=dict(
        first_freeze_m=initial, final_target_m=p, additional_feedback_closure_m=initial-p,
        maximum_single_regular_tick_close_m=max_step,
        reference_before_loss_m=reference,
        reference_after_recontact_m=d['force_hold_reference_opening_m'],
        material_compression_or_geometry_bound_claimed=False)

    h=make();p,_=step(h,0.)
    for n in range(1,8):p,_=step(h,n/60,p)
    tightened=p; increment=.000001723427777777
    final=latch+increment
    p,d=step(h,8/60,p,logical_requested_opening_m=final,ramped_opening_m=final)
    first=p
    assert abs((p-tightened)-increment)<1e-12
    for n in range(9,200):
        p,d=step(h,n/60,p,logical_requested_opening_m=final,ramped_opening_m=final,
            finger_contact_N=[0.,0.],effort_limit_N=.05)
        if not d['explicit_opening_ramp_active']:
            break
    assert abs(p-final)<1e-12 and not d['explicit_opening_ramp_active']
    result['teacher_stale_latch_release']=dict(
        tightened_target_m=tightened, teacher_old_latch_m=latch,
        teacher_first_scheduled_increment_m=increment,
        actual_first_opening_increment_m=first-tightened,
        final_logical_goal_m=final, actual_finished_target_m=p,
        finished_only_after_actual_target_arrival=not d['explicit_opening_ramp_active'])

    h=make();p,_=step(h,0.)
    for n in range(1,8):p,_=step(h,n/60,p)
    kwargs=dict(logical_requested_opening_m=.08,ramped_opening_m=.011)
    previous=p; frozen=step(h,8/60,previous,**kwargs)
    for _ in range(100):
        assert step(h,8/60,previous,**kwargs)==frozen
    p,d=frozen
    largest=p
    for n in range(9,600):
        p,d=step(h,n/60,p,**kwargs)
        largest=max(largest,p)
        assert p<=.011
    assert p==.011 and d['explicit_opening_ramp_active']
    result['paused_ramp_and_duplicate_sample']=dict(
        logical_goal_m=.08, current_ramped_target_m=.011,
        maximum_applied_target_m=largest, release_still_active=d['explicit_opening_ramp_active'],
        identical_sample_100_calls_equal=True)
    p,d=step(h,600/60,p,logical_requested_opening_m=.009,ramped_opening_m=.0103)
    assert d['closing_reversal'] and not d['release_slew_active'] and not d['explicit_opening_ramp_active']
    result['closing_reversal_exits_release']=True

    result['legacy_without_actual_force_adjustment']=[]
    for effort, forces in ((None,[.208,.389]),(8.,[.31,.32])):
        h=make();p,_=step(h,0.,effort_limit_N=effort,finger_contact_N=forces)
        p,_=step(h,.1,p,effort_limit_N=effort,finger_contact_N=forces)
        p,d=step(h,.12,p,effort_limit_N=effort,finger_contact_N=forces,
            logical_requested_opening_m=.02,ramped_opening_m=.011)
        assert p==.011 and not d['release_slew_active']
        result['legacy_without_actual_force_adjustment'].append(dict(
            effort_limit_N=effort, sensor_forces_N=forces, applied_m=p,
            original_ramped_target_m=.011, slew_not_applied=not d['release_slew_active']))

    result.update(source_unchanged_during_proof=SOURCE.read_bytes()==source,
        previous_draft_evidence_preserved=(HERE/'review_snapshot.json').exists(),
        CPU_counterexamples_passed=True, runtime_modified_by_reviewer=False,
        GPU_used=False, API_calls=0, actual_force_hold_physical_effect_not_verified=True)
    assert result['source_unchanged_during_proof']
    output.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps(dict(passed=True,source_SHA256=result['source_SHA256'],output=output.name)))


if __name__=='__main__':
    main()
