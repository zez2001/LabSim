"""Synthetic physical-state unit fixtures, never demonstration/policy data."""
import copy
import json
import math

import numpy as np
import pytest

from demos.lab_cuvette_progress_v1 import ProgressEvaluator, STAGES, resolve_config
from demos.lab_cuvette_progress_v1.geometry import measured_geometry


def configuration():
    task = dict(physics=dict(hz=20), vessel=dict(asset_id='synthetic_fixture', outer_xy_m=[.01, .01]),
        geometry=dict(target_depth_m=.027), robot=dict(grasp_above_bottom_m=.053, gripper_yaw_deg=0),
        control=dict(alignment_budget_m=.0001, tilt_budget_deg=.15, yaw_budget_deg=.2),
        env=dict(scene_layout_module='demos.lab_cuvette_size_v1.scene'))
    metadata = dict(episode_id='SYNTHETIC_UNIT_ONLY', sample_interval_s=.05,
        vessel_body_local_bounds_m=[[-.005, -.005, 0], [.005, .005, .0675]],
        layout=dict(source_floor=[0., 0., 0.], source_rim_z=.025, rack_rotation=np.eye(3),
            source_inner_m=.016, target_floor=[.3, 0., .12], seat_original_floor=[.29935, -.000001, .12],
            instrument_rotation=np.eye(3), target_inner_m=.0126, target_depth_m=.027))
    return resolve_config(task, metadata), metadata


class Trace:
    def __init__(self):
        self.rows = []

    def add(self, p=(0., 0., .00002), *, held=True, support=0., clearance=0., inside=None, n=1, **extra):
        p = np.asarray(p, float)
        for _ in range(n):
            near = abs(p[0]-.3) < .003
            contains = bool(near and p[2] <= .147) if inside is None else inside
            row = dict(t=len(self.rows)*.05, physics_step=len(self.rows),
                object_position_m=p.tolist(), object_quaternion_wxyz=[1., 0., 0., 0.],
                object_bottom_world_z_m=float(p[2]),
                actual_tcp_position_m=(p+[0., 0., .053]).tolist(), actual_tcp_quaternion_wxyz=[0., 1., 0., 0.],
                cup_in_hand_position_m=[0., 0., -.053], cup_in_hand_quaternion_wxyz=[0., 1., 0., 0.],
                finger_contact_N=[1., 1.] if held else [0., 0.],
                finger_joint_positions_m=[.005, .005] if held else [.04, .04],
                source_bottom_gap_m=float(p[2]), source_reference_inside=bool(np.linalg.norm(p[:2]) < .006 and p[2] < .025),
                depth_m=float(.147-p[2]), xy_error_target_m=(p[:2]-[.3, 0.]).tolist(),
                tilt_deg=0., yaw_error_deg=0., target_bottom_gap_m=float(p[2]-.12) if near else None,
                target_bottom_support_N=support, target_region_contains_object=contains,
                input_geometry_overlap_observed_m=0., gripper_object_clearance_m=clearance,
                phase='MISLEADING_TEACHER_SUCCESS_IGNORED')
            row.update(extra)
            self.rows.append(row)
        return self

    def held_route(self):
        return self.add(n=4).add((0., 0., .1)).add((.1, 0., .2)).add((.3, 0., .149))

    def seated(self):
        return self.held_route().add((.3, 0., .12)).add((.3, 0., .12), support=.2)

    def released(self, *, clearance=.05):
        return self.seated().add((.3, 0., .12), held=False, support=.2, clearance=clearance, n=3)

    def success(self):
        return self.released().add((.3, 0., .12), held=False, support=.2, clearance=.05, n=62)


def evaluate(rows, *, cfg=None):
    config, metadata = configuration()
    evaluator = ProgressEvaluator(cfg or config).reset(metadata)
    snapshots = [evaluator.update(row) for row in rows]
    return evaluator, snapshots


def test_complete_task_requires_physical_chain_and_causal_three_second_confirmation():
    evaluator, snapshots = evaluate(Trace().success().rows)
    result = evaluator.finalize({'termination_reason': 'TASK_SUCCESS'})
    assert result['progress_complete'] is True
    assert result['unfinished_requirement'] is None
    assert all(result['milestones'][stage]['ever_achieved'] for stage in STAGES)
    confirm = result['milestones']['stable_complete']['first_confirmed_t']
    candidate = result['last_snapshot']['stable_window']['candidate_start_t']
    assert confirm-candidate >= 3.-1e-9
    assert all(s['stages']['stable_complete']['ever_achieved'] is False for s in snapshots if s['t'] < confirm)
    assert result['failure_observation'] == []


def test_vessel_left_in_source_never_stable_complete_even_with_success_phase():
    evaluator, snapshots = evaluate(Trace().add(n=85).rows)
    result = evaluator.finalize({'termination_reason': 'TIMEOUT'})
    assert result['termination_domain'] == 'timeout'
    assert result['unfinished_requirement']['code'] == 'EXTRACTION_NOT_COMPLETED'
    assert snapshots[-1]['hold_state'] == 'gripper_held'
    assert result['stages']['stable_complete']['terminal_status'] == 'not_reached'
    assert result['failure_observation'] == []


def test_empty_hand_near_target_does_not_prove_held_transport_or_insertion():
    evaluator, snapshots = evaluate(Trace().add(held=False, n=3).add((.3, 0., .12), held=False, support=.2, clearance=.05, n=70).rows)
    result = evaluator.finalize()
    assert not result['milestones']['transport']['ever_achieved']
    assert not result['milestones']['insert']['ever_achieved']
    assert not result['milestones']['stable_complete']['ever_achieved']
    assert snapshots[-1]['metrics']['depth_ratio']['value'] == pytest.approx(1.)
    assert result['unfinished_requirement']['code'] == 'GRASP_NOT_ESTABLISHED'


def test_bilateral_contact_while_source_supported_is_candidate_not_extraction():
    evaluator, snapshots = evaluate(Trace().add(n=8).rows)
    assert snapshots[-1]['milestones']['grasp']['ever_achieved']
    assert snapshots[-1]['metrics']['grasp_off_source_verified']['value'] is False
    assert not evaluator.finalize()['milestones']['extract']['ever_achieved']


def test_unsupported_grasp_loss_preserves_history_and_current_state_regresses():
    trace = Trace().held_route().add((.15, 0., .15), held=False, n=7)
    evaluator, snapshots = evaluate(trace.rows)
    result = evaluator.finalize()
    assert result['milestones']['extract']['ever_achieved']
    assert snapshots[-1]['stages']['extract']['current_satisfied'] is False
    assert snapshots[-1]['hold_state'] == 'unsupported_or_lost'
    assert result['attempts'][0]['outcome'] == 'failure'
    assert result['failure_observation'][0]['code'] == 'GRASP_LOST_DURING_TRANSPORT'


def test_depth_complete_and_target_support_are_distinct():
    evaluator, snapshots = evaluate(Trace().held_route().add((.3, 0., .12), n=7).rows)
    assert snapshots[-1]['stages']['insert']['current_satisfied'] is True
    assert snapshots[-1]['stages']['support_transfer']['current_satisfied'] is False
    assert evaluator.finalize()['unfinished_requirement']['code'] == 'SUPPORT_TRANSFER_NOT_COMPLETED'


def test_legal_supported_release_is_not_grasp_loss_and_allows_retreat():
    evaluator, snapshots = evaluate(Trace().released().rows)
    result = evaluator.finalize()
    assert snapshots[-1]['hold_state'] == 'target_supported'
    assert snapshots[-1]['milestones']['released']['ever_achieved']
    assert snapshots[-1]['milestones']['retreated']['ever_achieved']
    assert result['failure_observation'] == []
    assert result['attempts'][0]['ended_by'] == 'legal_target_support_release'


def test_post_release_drift_interrupts_window_and_requires_new_full_window():
    trace = Trace().released().add((.3, 0., .12), held=False, support=.2, clearance=.05, n=20)
    first_prefix_len = len(trace.rows)
    trace.add((.3003, 0., .12), held=False, support=.2, clearance=.05, n=20)
    evaluator, snapshots = evaluate(trace.rows)
    result = evaluator.finalize()
    assert snapshots[first_prefix_len-1]['stable_window']['continuous_duration_s'] > .8
    assert snapshots[first_prefix_len]['stable_window']['continuous_duration_s'] == 0.
    assert not result['milestones']['stable_complete']['ever_achieved']
    assert any(e['name'] == 'stable_window_interrupted' for e in evaluator.events)
    assert any(e['code'] == 'POST_RELEASE_UNSTABLE' for e in result['failure_observation'])


def test_insufficient_actual_gripper_clearance_cannot_be_replaced_by_tcp_distance():
    trace = Trace().released(clearance=.02).add((.3, 0., .12), held=False, support=.2, clearance=.02, n=70,
        actual_tcp_position_m=[.8, 0., .12])
    evaluator, snapshots = evaluate(trace.rows)
    result = evaluator.finalize()
    assert snapshots[-1]['metrics']['tcp_object_distance_m']['value'] > .4
    assert result['unfinished_requirement']['code'] == 'RETREAT_NOT_COMPLETED'
    assert not result['milestones']['stable_complete']['ever_achieved']


def test_retry_has_new_relative_reference_and_preserves_failed_attempt():
    trace = Trace().held_route().add((.15, 0., .15), held=False, n=7)
    trace.add((0., 0., .00002), held=False, n=2)
    trace.success()
    evaluator, snapshots = evaluate(trace.rows)
    result = evaluator.finalize()
    assert result['progress_complete'] is True
    assert [a['outcome'] for a in result['attempts']] == ['failure', 'success']
    assert result['attempts'][1]['recovered_from_attempt_id'] == 1
    assert result['attempts'][0]['next_attempt_id'] == 2
    assert result['retry_count'] == 1
    assert len(result['failure_observation']) == 1


@pytest.mark.parametrize('missing', ['finger_contact_N', 'cup_in_hand_position_m', 'object_quaternion_wxyz'])
def test_missing_contact_or_pose_remains_unknown(missing):
    rows = Trace().add(n=8).rows
    for row in rows:
        row[missing] = None
    evaluator, snapshots = evaluate(rows)
    assert snapshots[-1]['stages']['grasp']['current_satisfied'] is None
    assert not evaluator.finalize()['milestones']['grasp']['ever_achieved']
    if missing == 'finger_contact_N':
        assert snapshots[-1]['metrics']['finger_contact_N']['value'] is None
        assert snapshots[-1]['metrics']['finger_contact_N']['available'] is False


def test_reset_isolates_first_times_attempts_and_finalize_is_idempotent():
    evaluator, _ = evaluate(Trace().success().rows)
    first = evaluator.finalize({'termination_reason': 'DONE'})
    assert evaluator.finalize({'termination_reason': 'CHANGED'}) == first
    with pytest.raises(RuntimeError, match='reset'):
        evaluator.update(Trace().rows)
    evaluator.reset({'episode_id': 'SECOND'})
    evaluator.update(Trace().add(held=False).rows[0])
    result = evaluator.finalize()
    assert result['episode_id'] == 'SECOND'
    assert result['attempts'] == []
    assert not any(v['ever_achieved'] for name, v in result['milestones'].items() if name != 'approach_grasp')
    assert first['progress_complete'] is True


def test_prefix_and_online_offline_same_raw_inputs_are_identical():
    rows = Trace().success().rows
    online, online_snapshots = evaluate(rows)
    offline, offline_snapshots = evaluate(json.loads(json.dumps(rows)))
    assert online_snapshots == offline_snapshots
    assert online.finalize() == offline.finalize()
    for length in [1, 5, 9, len(rows)-1]:
        _, prefix = evaluate(rows[:length])
        assert prefix == online_snapshots[:length]


def test_evidence_gap_breaks_stability_instead_of_counting_unobserved_time():
    trace = Trace().released().add((.3, 0., .12), held=False, support=.2, clearance=.05, n=3)
    row = copy.deepcopy(trace.rows[-1]); row['t'] += 4.
    trace.rows.append(row)
    evaluator, snapshots = evaluate(trace.rows)
    assert snapshots[-1]['stable_window']['continuous_duration_s'] == 0.
    assert evaluator.finalize()['evidence_gap_count'] == 1
    assert not snapshots[-1]['stages']['stable_complete']['ever_achieved']


def test_tilted_bottom_envelope_does_not_clear_rim_using_body_origin_height():
    cfg, _ = configuration()
    row = dict(object_position_m=[0., 0., .03],
        object_quaternion_wxyz=[math.cos(math.pi/8), 0., math.sin(math.pi/8), 0.])
    measured = measured_geometry(row, cfg['geometry'])
    assert measured['bottom'] < .03-.003
    assert measured['bottom_source'] == 'conservative_transformed_body_AABB_envelope'


def test_square_yaw_is_not_automatically_reduced_modulo_ninety_degrees():
    trace = Trace().held_route().add((.3, 0., .12), support=.2, yaw_error_deg=90., n=10)
    evaluator, snapshots = evaluate(trace.rows)
    assert snapshots[-1]['metrics']['target_yaw_error_rad']['value'] == pytest.approx(math.pi/2)
    assert not evaluator.finalize()['milestones']['insert']['ever_achieved']


def test_post_transfer_upright_gate_is_original_release_gate_not_alignment_budget():
    trace = Trace().released().add((.3, 0., .12), held=False, support=.2, clearance=.05,
        tilt_deg=.5, n=62)
    evaluator, snapshots = evaluate(trace.rows)
    assert snapshots[-1]['stages']['align']['current_satisfied'] is False
    assert snapshots[-1]['hold_state'] == 'target_supported'
    assert evaluator.finalize()['progress_complete'] is True


def test_depth_stall_without_executed_intent_is_unknown_not_jam():
    trace = Trace().held_route().add((.3, 0., .135), n=20, commanded_bottom_z_m=.13, wall_contact_N=1.)
    evaluator, snapshots = evaluate(trace.rows)
    assert snapshots[-1]['metrics']['insertion_depth_change_window_m']['value'] == 0.
    assert snapshots[-1]['metrics']['contact_stall_observed']['available'] is False
    assert not any(o['code'] == 'CONTACT_STALL_OBSERVED' for o in evaluator.finalize()['failure_observation'])


def test_no_geometry_or_contact_does_not_crash_or_invent_bounds():
    evaluator = ProgressEvaluator(resolve_config({}))
    snapshot = evaluator.update({'t': 0.})
    assert snapshot['hold_state'] == 'unknown'
    assert snapshot['metrics']['raw_depth_m']['available'] is False
    assert snapshot['metrics']['grasp_relative_translation_m']['value'] is None


def test_reject_nonfinite_and_nonmonotonic_time():
    evaluator, _ = evaluate(Trace().add(n=1).rows)
    with pytest.raises(ValueError, match='strictly increase'):
        evaluator.update({'t': 0.})
    with pytest.raises(ValueError, match='finite'):
        evaluator.update({'t': float('nan')})
