"""Scorer logic tests with explicitly synthetic state fixtures, not simulations.

Actual geometry remains blocked. A geometry=True fixture only verifies that the
scorer can recognize evidence instead of containing a hardcodedFalse outcome.
"""
import unittest

import numpy as np

from tasks.lab_cuvette_loading_env_v1_scorer import CuvetteLoadingEnvV1Scorer


CFG = {'scene': {'table_top_m': .74}, 'vessel': {'outer_xy_m': [.0125, .0125]},
       'geometry': {'depth_m': .027}, 'calibrated': False}
LAYOUT = {'source_rim_z': .768, 'target_rim_z': .914, 'target_depth_m': .027}


def fixture_rows(*, overlap=0.0, diagnostic=False):
    rows = []
    position = np.array([-.1, -.2, .743])

    def add(position_, force=(1., 1.), fingers=(.0065, .0065), support=0., clearance=0.):
        p = np.asarray(position_)
        near = np.linalg.norm(p[:2]-[.36, -.03]) < 1e-8
        rows.append(dict(t=len(rows)/240, physics_step=len(rows), phase='MISLEADING_PHASE_UNUSED',
            object_position_m=p.tolist(), object_quaternion_wxyz=[1., 0., 0., 0.],
            object_bottom_world_z_m=float(p[2]), depth_m=.914-float(p[2]),
            target_bottom_gap_m=float(p[2]-.887), xy_error_target_m=(p[:2]-[.36, -.03]).tolist(),
            tilt_deg=0., yaw_error_deg=0., finger_contact_N=list(force),
            finger_joint_positions_m=list(fingers), cup_in_hand_position_m=[0., 0., -.053],
            cup_in_hand_quaternion_wxyz=[1., 0., 0., 0.],
            target_bottom_support_N=support, target_region_contains_object=near,
            native_target_overlap_m=overlap, source_rack_penetration_m=0.,
            gripper_object_clearance_m=clearance))

    def move(end, n):
        nonlocal position
        for point in np.linspace(position, end, n+1)[1:]:
            add(point)
        position = np.array(end)

    for _ in range(40):
        add(position)
    move([-.1, -.2, .95], 150)
    move([.36, -.03, .95], 400)
    move([.36, -.03, .915], 100)
    if diagnostic:
        move([.36, -.03, .925], 100)
        for _ in range(260):
            add(position)
    else:
        move([.36, -.03, .887], 100)
        for _ in range(30):
            add(position, support=.1962)
        for i in range(60):
            add(position, force=(1-i/59, 1-i/59), fingers=(.0065+.0335*i/59,)*2,
                support=.1962)
        for _ in range(30):
            add(position, force=(0., 0.), fingers=(.04, .04), support=.1962)
        for clearance in np.linspace(0, .05, 30):
            add(position, force=(0., 0.), fingers=(.04, .04), support=.1962, clearance=clearance)
        for _ in range(750):
            add(position, force=(0., 0.), fingers=(.04, .04), support=.1962, clearance=.05)
    return rows


def score(rows, kind='loading', geometry=True):
    scorer = CuvetteLoadingEnvV1Scorer(CFG, LAYOUT, {'geometry_valid': geometry})
    for row in rows:
        scorer.update(row)
    return scorer.finalize('synthetic_unit_fixture', kind)


def test_evidence_can_produce_success_without_teacher_stage_flags():
    result = score(fixture_rows())
    assert result['task_success'] is True
    assert result['full_success'] is True
    assert result['eligible_for_success_bc'] is True
    assert result['post_retreat_window']['stable'] is True
    assert result['stage_labels_used_as_success_proof'] is False


def test_unknown_native_overlap_is_not_zero_or_a_physical_failure_label():
    result = score(fixture_rows(overlap=None))
    assert result['task_success'] is None
    assert result['record_valid'] is True
    assert result['eligible_for_success_bc'] is False
    assert result['eligible_for_failure_analysis'] is False
    assert result['post_retreat_window']['stable'] is None


def test_diagnostic_is_independent_and_never_full_loading_success():
    result = score(fixture_rows(diagnostic=True), 'preinsert_diagnostic', geometry=False)
    assert result['task_success'] is True
    assert result['full_success'] is None
    assert result['geometry_valid'] is False
    assert result['eligible_for_success_bc'] is False
    assert result['post_retreat_window']['status'] == 'unavailable'
    assert result['stable_after_retreat'] is None


def test_misleading_teacher_success_does_not_create_loading_or_retreat():
    rows = fixture_rows(diagnostic=True)
    for row in rows:
        row['phase'] = 'SUCCESS'
    result = score(rows)
    assert result['task_success'] is False
    assert result['post_retreat_window']['status'] == 'unavailable'
    assert result['post_retreat_window']['stable'] is None
    assert result['terminal_window']['status'] == 'complete'


def test_nonphysical_preflight_block_is_not_valid_physical_failure():
    scorer = CuvetteLoadingEnvV1Scorer(CFG, LAYOUT, {'geometry_valid': False})
    result = scorer.finalize('preflight', 'loading', 'GEOMETRY_PRECHECK_BLOCKED',
                             'GEOMETRY_PRECHECK_BLOCKED')
    assert result['record_valid'] is False
    assert result['task_success'] is None
    assert result['eligible_for_failure_analysis'] is False


def test_bilateral_contact_with_large_measured_relative_slip_fails():
    rows = fixture_rows(diagnostic=True)
    for i, row in enumerate(rows):
        if i > 200:
            row['cup_in_hand_position_m'] = [.001, 0., -.053]
    result = score(rows, 'preinsert_diagnostic', geometry=False)
    assert result['task_success'] is False
    assert result['failure_type'] == 'GRASP_SLIP'
    assert result['grasp_relative_pose']['maximum_position_drift_m'] == .001


def test_unknown_bottom_support_stays_unknown_instead_of_whole_seat_force():
    rows = fixture_rows()
    for row in rows:
        row['target_bottom_support_N'] = None
        row['target_whole_seat_net_vertical_N'] = 5.0
    result = score(rows)
    assert result['task_success'] is None
    assert result['eligible_for_failure_analysis'] is False
    assert result['post_retreat_window']['criteria']['target_support'] is None


def test_explicit_physical_regrasp_can_recover_without_erasing_failed_attempt():
    prefix = fixture_rows()[:40]
    for row in prefix[30:]:
        row['cup_in_hand_position_m'] = [.001, 0., -.053]
    for _ in range(60):
        row = dict(prefix[-1])
        row.update(t=len(prefix)/240, physics_step=len(prefix),
                   finger_contact_N=[0., 0.], finger_joint_positions_m=[.04, .04])
        prefix.append(row)
    tail = fixture_rows()
    offset = len(prefix)
    for index, row in enumerate(tail):
        row.update(t=(offset+index)/240, physics_step=offset+index)
    result = score(prefix+tail)
    assert result['task_success'] is True
    assert result['retry_count'] == 1
    assert result['grasp_attempts'][0]['maximum_position_drift_m'] == .001


def grasp_hold_rows():
    template = fixture_rows()[0]
    return [dict(template, t=i/240, physics_step=i, source_reference_inside=True)
            for i in range(810)]


def test_grasp_hold_has_own_three_second_in_rack_goal_without_extraction():
    result = score(grasp_hold_rows(), 'grasp_hold', geometry=False)
    assert result['task_success'] is True
    assert result['source_slot_cleared'] is False
    assert result['full_success'] is None
    assert result['eligible_for_success_bc'] is False
    assert result['diagnostic_hold_window']['required_duration_s'] == 3.0


def test_grasp_hold_does_not_invent_unknown_source_occupancy():
    rows = grasp_hold_rows()
    for row in rows:
        row['source_reference_inside'] = None
    result = score(rows, 'grasp_hold', geometry=False)
    assert result['task_success'] is None
    assert result['diagnostic_hold_window']['criteria']['source_rack_occupancy'] is None


def test_extract_transport_can_pass_without_preinsert_or_release():
    rows = fixture_rows(diagnostic=True)[:590]
    for _ in range(760):
        rows.append(dict(rows[-1], t=len(rows)/240, physics_step=len(rows)))
    result = score(rows, 'extract_transport', geometry=False)
    assert result['task_success'] is True
    assert result['source_slot_cleared'] is True
    assert 'safe_preinsert_observed' not in result['observed_events']
    assert result['full_success'] is None
    assert result['eligible_for_success_bc'] is False
    assert result['diagnostic_hold_window']['required_duration_s'] == 3.0


def test_preflight_alias_is_excluded_from_physical_failures():
    scorer = CuvetteLoadingEnvV1Scorer(CFG, LAYOUT, {'geometry_valid': False})
    result = scorer.finalize('preflight', 'loading', 'GEOMETRY_PREFLIGHT_BLOCKED',
                             'GEOMETRY_PREFLIGHT_BLOCKED')
    assert result['record_valid'] is False
    assert result['task_success'] is None
    assert result['eligible_for_failure_analysis'] is False


def test_anchor_is_recorded_without_relaxing_bottom_origin_acceptance():
    rows = grasp_hold_rows()
    theta = np.deg2rad(.5)
    quaternion = [np.cos(theta/2), 0., np.sin(theta/2), 0.]
    height = .053
    for row in rows[100:]:
        row['cup_in_hand_quaternion_wxyz'] = quaternion
        row['cup_in_hand_position_m'] = [-height*np.sin(theta), 0., -height*np.cos(theta)]
    result = score(rows, 'grasp_hold', geometry=False)
    assert result['task_success'] is False
    assert result['grasp_relative_pose']['maximum_position_drift_m'] > .0002
    assert result['grasp_relative_pose']['maximum_configured_grasp_anchor_drift_m'] < 1e-12


def load_tests(loader, tests, pattern):
    """Run with stdlib unittest; Isaac's environment need not install pytest."""
    return unittest.TestSuite(unittest.FunctionTestCase(value)
        for name, value in sorted(globals().items()) if name.startswith('test_') and callable(value))


if __name__ == '__main__':
    unittest.main()
