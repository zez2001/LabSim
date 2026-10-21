"""CPU workflow/label contracts with synthetic evidence, never physical results.

The fixtures exercise the existing state-event scorer and the new declared
input-material criterion. They do not establish that an actual loading occurred.
"""
import copy
import importlib.util
from pathlib import Path
import unittest

import numpy as np
from scipy.spatial.transform import Rotation

from demos.lab_cuvette_size_v1.scorer import Scorer
from tasks.lab_cuvette_loading_env_v1_scorer import CuvetteLoadingEnvV1Scorer


ROOT=Path(__file__).resolve().parents[1]


def _load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_fixture=_load('size_v1_existing_synthetic_scorer_fixture',ROOT/'tests/test_lab_cuvette_env_v1_scorer.py')
_teacher=_load('size_v1_teacher_contract_math',ROOT/'controllers/lab_cuvette_env_v1_controller.py')


class SizeScorerWorkflowContract(unittest.TestCase):
    def setUp(self):
        self.cfg=copy.deepcopy(_fixture.CFG)
        self.cfg['vessel'].update(asset_id='synthetic_size_contract_only',outer_xy_m=[.010,.010])
        self.cfg['experiment']=dict(condition_group='standard_natural')
        self.layout=copy.deepcopy(_fixture.LAYOUT)

    def rows(self):
        rows=_fixture.fixture_rows(overlap=None)
        for row in rows:
            row.update(input_geometry_overlap_observed_m=0.,
                input_geometry_sample_time_s=row['t'],input_geometry_cache_age_s=0.,
                input_method='Explicit synthetic unit fixture, not actual mesh measurement',
                forbidden_robot_environment_contact=False)
        return rows

    def score(self,rows,**kwargs):
        scorer=Scorer(self.cfg,self.layout,dict(geometry_valid=True))
        for row in rows:scorer.update(row)
        return scorer.finalize('synthetic-unit-only','loading',**kwargs)

    def test_variant_success_does_not_rewrite_original_nominal_pair(self):
        result=self.score(self.rows())
        self.assertTrue(result['task_success'])
        self.assertTrue(result['variant_pair_success'])
        self.assertIsNone(result['native_pair_success'])
        self.assertTrue(result['original_12_5mm_native_pair_verdict_unchanged'])
        self.assertTrue(result['eligible_for_success_bc'])
        self.assertFalse(result['real_calibrated'])

    def test_input_check_is_explicit_and_unknown_cooked_geometry_remains_flagged(self):
        result=self.score(self.rows())
        criteria=result['post_retreat_window']['criteria']
        self.assertTrue(criteria['observed_input_material_overlap_within_limit'])
        self.assertNotIn('native_overlap_within_limit',criteria)
        self.assertIn('NATIVE_TARGET_OVERLAP_UNAVAILABLE',result['physics_quality_flags'])
        self.assertIn('not calibrated cooked geometry',result['acceptance_geometry_scope'])

    def test_missing_input_measurement_cannot_create_success_or_fake_failure(self):
        rows=self.rows()
        for row in rows:row['input_geometry_overlap_observed_m']=None
        result=self.score(rows)
        self.assertIsNone(result['task_success'])
        self.assertTrue(result['record_valid'])
        self.assertFalse(result['eligible_for_success_bc'])
        self.assertFalse(result['eligible_for_failure_analysis'])

    def test_missing_retreat_keeps_post_window_unavailable(self):
        rows=self.rows()
        rows=[r for r in rows if r['gripper_object_clearance_m']<.04]
        result=self.score(rows)
        self.assertFalse(result['retreat_observed'])
        self.assertEqual(result['post_retreat_window']['status'],'unavailable')
        self.assertIsNone(result['stable_after_retreat'])
        self.assertIsNone(result['post_retreat_window']['stable'])
        self.assertIn('terminal_window',result)
        self.assertFalse(result['eligible_for_success_bc'])

    def test_two_seconds_after_retreat_does_not_satisfy_three_seconds(self):
        rows=self.rows()
        first=next(r['t'] for r in rows if r['gripper_object_clearance_m']>=.04)
        result=self.score([r for r in rows if r['t']<=first+2.])
        self.assertTrue(result['retreat_observed'])
        self.assertEqual(result['post_retreat_window']['status'],'incomplete')
        self.assertIsNone(result['stable_after_retreat'])
        self.assertFalse(result['task_success'])

    def test_robot_instrument_contact_is_hard_failure_not_loading_success(self):
        scorer=Scorer(self.cfg,self.layout,dict(geometry_valid=True))
        row=self.rows()[0]
        row['forbidden_robot_environment_contact']=True
        outcome=scorer.update(row)
        self.assertTrue(outcome['terminate'])
        self.assertEqual(outcome['termination_reason'],'ROBOT_ENVIRONMENT_COLLISION')
        self.assertEqual(outcome['failure_type'],'PHYSICS_INVALID')
        result=scorer.finalize('synthetic-forbidden-contact','loading')
        self.assertFalse(result['record_valid'])
        self.assertFalse(result['eligible_for_success_bc'])
        self.assertFalse(result['eligible_for_failure_analysis'])

    def test_observed_input_penetration_hard_stops_with_original_limit(self):
        scorer=Scorer(self.cfg,self.layout,dict(geometry_valid=True))
        rows=self.rows()[:2]
        scorer.update(rows[0])
        rows[1]['input_geometry_overlap_observed_m']=.000051
        outcome=scorer.update(rows[1])
        self.assertTrue(outcome['terminate'])
        self.assertEqual(outcome['termination_reason'],'INPUT_MATERIAL_PENETRATION')
        self.assertEqual(outcome['failure_type'],'PHYSICS_INVALID')
        # Follow the actual environment's propagation of the stop outcome.
        result=scorer.finalize('synthetic-overlap','loading',
            outcome['termination_reason'],outcome['failure_type'])
        self.assertFalse(result['record_valid'])
        self.assertIn('observed_input_material_overlap_above_declared_limit',result['invalid_state_reasons'])
        self.assertFalse(result['eligible_for_failure_analysis'])

    def test_whole_seat_force_cannot_replace_classified_bottom_support(self):
        rows=self.rows()
        for row in rows:
            row['target_bottom_support_N']=None
            row['target_whole_seat_net_vertical_N']=5.
        result=self.score(rows)
        self.assertIsNone(result['task_success'])
        self.assertIsNone(result['post_retreat_window']['criteria']['target_support'])
        self.assertFalse(result['eligible_for_success_bc'])

    def test_input_penetration_failure_persists_for_independent_offline_finalize(self):
        scorer=Scorer(self.cfg,self.layout,dict(geometry_valid=True))
        rows=self.rows()[:2]
        scorer.update(rows[0])
        rows[1]['input_geometry_overlap_observed_m']=.0001
        scorer.update(rows[1])
        result=scorer.finalize('synthetic-offline-overlap','loading')
        self.assertEqual(result['failure_type'],'PHYSICS_INVALID')
        self.assertFalse(result['record_valid'])

    def test_initial_support_invalid_is_not_physical_failure_quota(self):
        result=self.score(self.rows(),termination_reason='INITIAL_SUPPORT_INVALID',
                          failure_type='INITIAL_SUPPORT_INVALID')
        self.assertEqual(result['failure_type'],'INITIALIZATION_INVALID')
        self.assertFalse(result['record_valid'])
        self.assertIsNone(result['task_success'])
        self.assertFalse(result['eligible_for_failure_analysis'])

    def test_original_env_scorer_keeps_its_unknown_cooked_geometry_contract(self):
        old=CuvetteLoadingEnvV1Scorer(self.cfg,self.layout,dict(geometry_valid=True))
        for row in self.rows():old.update(row)
        result=old.finalize('synthetic-old-env-unchanged','loading')
        self.assertIsNone(result['task_success'])
        self.assertIsNone(result['post_retreat_window']['stable'])


class SizeTeacherWorkflowContract(unittest.TestCase):
    def setUp(self):
        self.cfg=dict(env=dict(task_type='loading'),
            physics=dict(control_hz=60,dynamic_friction=.5,finger_dynamic_friction=.8),
            vessel=dict(mass_kg=.02,yaw_deg=0),robot=dict(finger_kp=2000),
            gripper=dict(contact_safety_factor=2),control=dict(timeout_s=200.))
        self.layout=dict(source_floor=[-.085,-.175,.743],
            target_floor=[.21237,-.1499,.887],instrument_rotation=np.eye(3),
            target_rim_z=.914,source_rim_z=.768)
        self.hand=Rotation.from_euler('x',180,degrees=True)
        self.debug=dict(actual_tcp_position_m=[.21237,-.1499,1.028],
            actual_tcp_quaternion_wxyz=_teacher.wxyz(self.hand),
            object_position_m=[.21237,-.1499,.975],object_quaternion_wxyz=[1,0,0,0],
            finger_contact_N=[.2,.2],finger_joint_positions_m=[.0051,.0051],
            source_bottom_z_m=.975,tilt_deg=0.,xy_error_target_m=[0.,0.],
            target_bottom_gap_m=.088,target_bottom_support_N=0.,
            native_target_overlap_m=None,depth_m=-.061)

    def controller(self,**control):
        cfg=copy.deepcopy(self.cfg);cfg['control'].update(control)
        teacher=_teacher.LabCuvetteTeacher(cfg,self.layout)
        teacher.act(dict(simulation_time=0.,episode_id='unit'),self.debug)
        teacher.latch_opening=.0099;teacher.contact_opening=.0102
        teacher.latch_time=0.;teacher.grasp_reference=teacher._relative(self.debug)
        teacher.phase_start=0.
        return teacher

    def act(self,teacher,t,debug=None):
        return teacher.act(dict(simulation_time=t,episode_id='unit'),debug or self.debug)

    def test_preapproach_absent_preserves_original_env_transition(self):
        teacher=self.controller();teacher.phase='ALIGN'
        target=teacher.target.copy()
        self.act(teacher,3.)
        self.assertEqual(teacher.phase,'INSERT')
        np.testing.assert_array_equal(teacher.target,target)

    def test_explicit_preapproach_descends_to_safe_rim_before_insert(self):
        teacher=self.controller(loading_preapproach=True,
            preinsert_bottom_above_rim_m=.002,preapproach_speed_m_s=.005)
        teacher.phase='ALIGN';before=teacher.target[2]
        self.act(teacher,3.)
        self.assertEqual(teacher.phase,'ALIGN')
        self.assertAlmostEqual(before-teacher.target[2],.005/60)
        near=copy.deepcopy(self.debug)
        near['source_bottom_z_m']=.91601
        near['object_position_m'][2]=.91601
        near['actual_tcp_position_m'][2]=.96901
        self.act(teacher,3.1,near)
        self.assertEqual(teacher.phase,'INSERT')

    def test_insert_default_still_times_out_at_original_thirty_five_seconds(self):
        teacher=self.controller();teacher.phase='INSERT'
        self.act(teacher,36.)
        self.assertEqual(teacher.phase,'JAM_RETRACT')

    def test_explicit_insert_budget_does_not_relax_any_support_gate(self):
        teacher=self.controller(insert_timeout_s=100.);teacher.phase='INSERT'
        before=teacher.target[2]
        self.act(teacher,36.)
        self.assertEqual(teacher.phase,'INSERT')
        self.assertLess(teacher.target[2],before)
        self.assertFalse(teacher._supported(self.debug))

    def test_at_floor_without_support_stops_descent_and_never_opens(self):
        teacher=self.controller(allow_geometric_support_transfer=True)
        teacher.phase='INSERT'
        debug=copy.deepcopy(self.debug)
        debug.update(source_bottom_z_m=.887,target_bottom_gap_m=0.,depth_m=.027)
        debug['object_position_m'][2]=.887
        debug['actual_tcp_position_m'][2]=.940
        teacher.target=np.asarray(debug['actual_tcp_position_m']).copy()
        teacher.grasp_reference=teacher._relative(debug)
        # Independent stable physical pose history, with zero classified support.
        for t in np.arange(.0,.301,1/60):
            teacher.history.append(dict(t=float(t),position=np.array(debug['object_position_m']),
                quaternion=np.array(debug['object_quaternion_wxyz']),bottom=.887,
                target_z=.940,wall_force=0.))
        before=teacher.target.copy()
        self.act(teacher,.32,debug)
        self.assertEqual(teacher.phase,'SUPPORT_TRANSFER')
        np.testing.assert_array_equal(teacher.target,before)
        self.assertTrue(teacher.events[-2]['support_not_yet_claimed'])
        for t in np.arange(.34,3.5,1/60):self.act(teacher,float(t),debug)
        self.assertEqual(teacher.phase,'SUPPORT_TRANSFER')
        self.assertFalse(teacher.finished)
        self.assertIsNone(teacher.open_target)
        self.assertNotIn('OPEN',[event.get('target') for event in teacher.events])
        np.testing.assert_array_equal(teacher.target,before)


if __name__=='__main__':
    unittest.main()
