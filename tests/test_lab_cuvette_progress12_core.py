"""Progress v1.2 causal semantics; synthetic values are never rollout evidence."""
import copy
import json
import math
from pathlib import Path

import pytest

from demos.lab_cuvette_progress_v1.config import PARAMETERS, SCHEMA_VERSION, resolve_config
from demos.lab_cuvette_progress_v1.core import smooth_quality
from test_lab_cuvette_progress_core import Trace, configuration, evaluate


def test_known_source_bound_raw_projection_is_not_insertion_progress():
    rows = Trace().add(held=False, n=5, depth_m=.171,
        xy_error_target_m=[-.298, 0.], target_region_contains_object=False).rows
    evaluator, snapshots = evaluate(rows)
    for sample in snapshots:
        assert sample['stages']['insert']['continuous'] == 1.  # legacy diagnostic
        assert sample['raw_axial_depth_m'] == .171
        assert sample['raw_depth_fraction'] > 6.
        assert sample['valid_insertion_progress'] == 0.
        assert sample['stages']['insert']['effective_continuous'] == 0.
        assert sample['insertion_progress_applicable'] is False
        assert 'outside_correct_target_region' in sample['insertion_gate_details']['not_applicable_reasons']
    assert not evaluator.finalize()['milestones']['insert']['ever_achieved']


def test_missing_required_containment_after_valid_route_stays_unknown():
    _, snapshots = evaluate(Trace().held_route().add((.3, 0., .135),
        target_region_contains_object=None).rows)
    last = snapshots[-1]
    assert last['insertion_progress_applicable'] is None
    assert last['valid_insertion_progress'] is None
    assert last['metrics']['valid_insertion_progress']['available'] is False
    assert 'missing_correct_target_evidence' in last['insertion_gate_details']['unknown_reasons']


def test_signed_unclipped_projection_survives_entrance_region_exclusion():
    _, snapshots = evaluate(Trace().held_route().add((.3, 0., .2), depth_m=-.053).rows)
    last = snapshots[-1]
    assert last['raw_axial_depth_m'] == -.053
    assert last['raw_depth_fraction'] < 0.
    assert last['metrics']['depth_ratio']['value'] == 0.
    assert last['valid_insertion_progress'] == 0.


def test_valid_depth_and_transferred_release_keep_effective_progress_without_grasp():
    trace = Trace().held_route().add((.3, 0., .135))
    _, mid = evaluate(trace.rows)
    assert mid[-1]['valid_insertion_progress'] == pytest.approx(.012/.027)
    trace.add((.3, 0., .12), support=.2)
    trace.add((.3, 0., .12), held=False, support=.2, clearance=.05, n=4, tilt_deg=.5)
    _, snapshots = evaluate(trace.rows)
    last = snapshots[-1]
    assert last['hold_evidence']['gripper_held'] is False
    assert last['hold_state'] == 'target_supported'
    assert last['stages']['align']['current_satisfied'] is False
    assert last['valid_insertion_progress'] == pytest.approx(1.)
    assert last['insertion_progress_applicable'] is True


def test_approach_quality_improves_monotonically_with_distance_and_rotation():
    cfg, _ = configuration()
    base = Trace().add(held=False).rows[0]
    def one(distance, angle):
        row = copy.deepcopy(base)
        row['actual_tcp_position_m'] = [distance, 0., .05302]
        row['actual_tcp_quaternion_wxyz'] = [0., math.cos(angle/2), math.sin(angle/2), 0.]
        return evaluate([row], cfg=cfg)[1][0]
    far, near = one(.272, .3), one(.224, .3)
    assert 0 < far['metrics']['approach_position_quality']['value'] < near['metrics']['approach_position_quality']['value'] < 1.
    assert far['stages']['approach_grasp']['effective_continuous'] < near['stages']['approach_grasp']['effective_continuous']
    wrong, good = one(.224, .5), one(.224, .1)
    assert wrong['metrics']['approach_orientation_quality']['value'] < good['metrics']['approach_orientation_quality']['value']
    assert wrong['stages']['approach_grasp']['effective_continuous'] < good['stages']['approach_grasp']['effective_continuous']
    assert smooth_quality(None, .1) is None
    row = copy.deepcopy(base); row['actual_tcp_position_m'] = None
    sample = evaluate([row], cfg=cfg)[1][0]
    assert sample['metrics']['approach_position_quality']['value'] is None
    assert sample['stages']['approach_grasp']['effective_continuous'] is None


def test_unheld_geometric_position_does_not_complete_other_effective_stages():
    _, snapshots = evaluate(Trace().add((.3, 0., .12), held=False, support=.2, n=5).rows)
    last = snapshots[-1]
    assert last['stages']['align']['continuous'] == 1.
    for stage in ('extract', 'transport', 'align', 'insert', 'support_transfer'):
        assert last['stages'][stage]['effective_continuous'] == 0.


def test_normal_physical_successors_do_not_display_as_grasp_or_transport_failure():
    _, snapshots = evaluate(Trace().released().rows)
    last = snapshots[-1]
    assert last['stages']['grasp']['current_satisfied'] is False
    assert last['stages']['extract']['current_satisfied'] is False
    assert last['stages']['transport']['current_satisfied'] is False
    for name in ('grasp', 'extract', 'transport'):
        assert last['stages'][name]['user_status'] == 'completed_followed'
    assert last['actual_grasp_loss_observed'] is False


def test_unconfirmed_support_and_actual_grasp_loss_are_separate_facts():
    trace = Trace().held_route().add((.15, 0., .15), held=False, n=7)
    _, snapshots = evaluate(trace.rows)
    assert snapshots[-7]['hold_state_user'] == 'support_unconfirmed'
    assert snapshots[-7]['actual_grasp_loss_observed'] is False
    assert snapshots[-1]['hold_state_user'] == 'unsupported_with_observed_loss'
    assert snapshots[-1]['actual_grasp_loss_observed'] is True
    assert snapshots[-1]['stages']['extract']['user_status'] == 'evidenced_failure'


def test_first_confirmation_is_immutable_and_reconfirmation_is_separately_counted():
    trace = Trace().held_route().add((.3, 0., .135), yaw_error_deg=2.)
    trace.add((.3, 0., .135), n=2)
    evaluator, snapshots = evaluate(trace.rows)
    result = evaluator.finalize()
    stage = result['stages']['align']
    assert stage['confirmation_count'] == 2
    assert stage['first_confirmed_t'] < stage['last_confirmed_t']
    attempt = result['attempts'][0]
    assert attempt['completed_stages']['align'] == stage['first_confirmed_t']
    assert attempt['stage_timing']['align']['last_confirmed_t'] == stage['last_confirmed_t']
    assert result['event_statistics']['operational_attempt_count'] == 1
    assert result['event_statistics']['repeated_confirmation_count'] >= 1


def test_current_state_and_prior_snapshots_are_not_backfilled_by_success():
    trace = Trace().success()
    evaluator, snapshots = evaluate(trace.rows)
    prefix = copy.deepcopy(snapshots[:8])
    evaluator.finalize({'task_success': True})
    assert snapshots[:8] == prefix
    assert all(sample['valid_insertion_progress'] == 0. for sample in prefix[:6])
    _, short = evaluate(trace.rows[:8])
    assert short == prefix


def test_new_parameters_are_explicitly_versioned_without_discrete_threshold_change():
    root = Path(__file__).resolve().parents[1]
    old = json.loads((root/'config/lab_cuvette_loading/Progress_v1/progress.json').read_text())
    new = json.loads(PARAMETERS.read_text())
    assert new['version'] == 'Progress_v1.2'
    assert new['thresholds'] == old['thresholds']
    assert SCHEMA_VERSION == 'labsim.Progress_v1_2.v1'
    cfg, _ = configuration()
    cfg['progress_schema_version'] = 'labsim.Progress_v1.v1'
    with pytest.raises(ValueError, match='original task config'):
        resolve_config(cfg)


@pytest.mark.parametrize('extra', [{'target_bottom_gap_m': .001}, {'input_geometry_overlap_observed_m': .001}])
def test_support_force_is_not_effective_transfer_without_legal_support_geometry(extra):
    _, snapshots = evaluate(Trace().held_route().add((.3, 0., .12), support=1., **extra).rows)
    last = snapshots[-1]
    assert last['stages']['support_transfer']['continuous'] == 1.
    assert last['stages']['support_transfer']['effective_continuous'] == 0.
    assert last['stages']['support_transfer']['current_satisfied'] is False


def test_original_axial_measurement_remains_readable_when_pose_channel_is_missing():
    trace = Trace().held_route().add((.3, 0., .135), depth_m=.012,
        object_quaternion_wxyz=None, target_region_contains_object=True)
    _, snapshots = evaluate(trace.rows)
    last = snapshots[-1]
    assert last['metrics']['raw_depth_m']['value'] is None  # legacy behavior preserved
    assert last['raw_axial_depth_m'] == .012
    assert last['raw_depth_fraction'] == pytest.approx(.012/.027)
    assert last['metrics']['raw_axial_depth_m']['available'] is True
    assert last['valid_insertion_progress'] is None
    assert last['insertion_progress_applicable'] is None
