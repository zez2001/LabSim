"""Report content validation without Word authoring or a document marker."""
import importlib.util
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1] / 'docs/lab_cuvette_loading/Size_v1/report/generate_report.py'
spec = importlib.util.spec_from_file_location('size_report', SOURCE)
report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(report)


class ReportTests(unittest.TestCase):
    def test_report_date_uses_created_at_in_Shanghai(self):
        self.assertEqual(report.report_date('2026-10-21T17:10:00+00:00'), '2026年10月22日')
        self.assertEqual(report.report_date('2026-10-22T01:10:00+08:00'), '2026年10月22日')
        self.assertEqual(report.report_date(None), '日期未知')

    def test_reproduction_summary_includes_actual_verification_and_audit(self):
        data = {'root': '/repo', 'summary': {'root': '/repo/outputs/Size_v1', 'standard5': {
            'selection': {'explicit_run_prefixes': ['verify5_actual_batch']}}},
            'quota': {'qualification_evidence': {'path': '/repo/docs/final_actual/collection_audit.json'}}}
        command = report.reproduction_commands(data, 'cuvette_xy_1000')
        self.assertIn('../labutopia-env/bin/python scripts/summarize_lab_cuvette_size_v1.py', command)
        self.assertIn('--verification-run-prefix verify5_actual_batch', command)
        self.assertIn('--collection-audit docs/final_actual/collection_audit.json', command)
        self.assertIn('--root outputs/Size_v1', command)
        self.assertNotIn('/repo/', command)

    def test_depth_groups_require_actual_admitted_events_not_configuration_only(self):
        def event_row(depth, actual=True):
            return {'failure': True, 'labels': {'condition_group': 'deterministic_action_deviation'},
                'controlled_deviation_event_evidence': {'qualified': True, 'actual_event_count': 1,
                    'checks': {'actual_event_matches_state': True}, 'configuration_spec': {'stop_insertion_at_depth_m': .099},
                    'actual_event': {'spec': {'stage': 'INSERT', 'unit': 'm',
                        'stop_insertion_at_depth_m': depth}} if actual else {}}}
        text = report.failure_depth_distribution({'episodes': [event_row(.001), event_row(.001), event_row(.005), event_row(.099, False)]})
        self.assertIn('1mm 2条、5mm 1条', text)
        self.assertIn('另有1条事件核验不足', text)
        self.assertNotIn('99mm', text)

    def test_reader_split_counts_are_actual_and_RGB_scope_stays_sampled(self):
        rows = [{'sample_filter': selection, 'policy_type': policy,
            'train_episode_ids': ['train0', 'train1'], 'validation_episode_ids': ['val0'],
            'episode_split_disjoint': True, 'train_and_validation_same_frozen_standard_scene': True}
            for selection in ('success', 'failure') for policy in ('act', 'dp')]
        audit = {'reader_validation': rows, 'episodes': [{'admission_errors': []}]}
        self.assertIn('成功2/1、失败2/1', report.reader_split_summary(audit))
        scope = report.reader_check_scope(audit)
        self.assertIn('全时间轴及8D动作映射', scope)
        self.assertIn('选样核对RGB', scope)
        self.assertIn('不是全量逐帧图像核验', scope)
        rows[-1]['episode_split_disjoint'] = False
        self.assertIn('失败未知', report.reader_split_summary(audit))

    def test_compact_provenance_is_relative_small_and_does_not_mutate_authoring_data(self):
        with tempfile.TemporaryDirectory() as d:
            parent = Path(d)
            (parent / 'data').mkdir(); (parent / 'media').mkdir()
            audit = parent / 'data' / 'audit.json'; audit.write_text('{"actual_count":21}\n')
            clip = parent / 'media' / 'main.mp4'; clip.write_bytes(b'closed-video-fixture')
            large = 'DO_NOT_DUPLICATE_FULL_CONFIG_OR_REGISTRY' * 1500
            full = {'created_at': 'actual_time', 'root': '/original/workspace', 'branch': 'codex/test',
                'authoring_head': 'commit-sha', 'registry': {'assets': {
                    'asset_' + str(i): {'full_metadata': large} for i in range(35)}},
                'summary': {'standard5': {'all_five_successful': True}, 'runs': [
                    {'config_snapshot': {'full_config': large}, 'physics_quality_flags': ['MEASURED_WARNING']}
                    for _ in range(40)]},
                'quota': {'qualified_success_count': 20, 'qualified_failure_count': 1,
                    'qualification_evidence': {'reader_validation': [large] * 40}},
                'primary': {'episode_id': 'actual-UUID', 'asset_id': 'asset_0', 'config_snapshot': large},
                'primary_result': {'task_success': True, 'physics_quality_flags': ['MEASURED_WARNING']},
                'collection_audit': {'episodes': [large] * 40},
                'sources': {'registry.json': {'path': 'registry.json', 'bytes': 123, 'sha256': 'source-sha'}},
                'evidence_files': [{'path': str(audit), 'label': '数据资格与正常读取验证',
                    'source_provenance_path': '/original/audit.json'}],
                'figures': [], 'media': [{'path': str(clip), 'kind': 'video', 'label': '主录像',
                    'source': '/original/main.mp4', 'source_sha256': 'original-video-sha',
                    'continuous_same_episode': True, 'command': [large]}]}
            original = copy.deepcopy(full)
            compact = report.compact_provenance_manifest(full, parent)
            encoded = json.dumps(compact, ensure_ascii=False).encode()
            self.assertEqual(full, original)
            self.assertLess(len(encoded), 500_000)
            self.assertNotIn('DO_NOT_DUPLICATE_FULL_CONFIG_OR_REGISTRY', encoded.decode())
            self.assertEqual(compact['schema'], 'labsim.Size_v1.report_provenance_compact.v2')
            self.assertEqual(compact['collection_counts']['qualified_success_count'], 20)
            self.assertEqual(compact['primary']['episode_id'], 'actual-UUID')
            self.assertTrue(compact['primary_result']['task_success'])
            audit_ref = compact['collection_counts']['full_audit_file']
            self.assertEqual(audit_ref['path'], 'data/audit.json')
            self.assertEqual(audit_ref['sha256'], hashlib.sha256(audit.read_bytes()).hexdigest())
            self.assertEqual(compact['media'][0]['path'], 'media/main.mp4')
            self.assertTrue(compact['media'][0]['metadata']['continuous_same_episode'])
            self.assertEqual(compact['sources'][0]['sha256'], 'source-sha')

    def test_display_statuses_are_precise_and_do_not_infer_unknown(self):
        self.assertEqual(report.outcome_label('SUCCESS_OBSERVED'), '已观察完整成功')
        self.assertEqual(report.outcome_label('FAILURE_OBSERVED'), '已观察任务失败')
        self.assertEqual(report.outcome_label(None), '未知或未执行')
        self.assertEqual(report.termination_label('CONTROLLER_WORKFLOW_COMPLETE'), '流程执行结束')
        self.assertEqual(report.standard_label({'selected_episode_count': 5, 'closed_record_count': 5,
            'independently_scored_success_count': 5, 'independently_scored_failure_count': 0,
            'outcome_unknown_count': 0}), '5/5完整成功')

    def test_representatives_include_sizes_and_controlled_failure_not_preview(self):
        def row(ident, asset, group='natural', excluded=False):
            return {'episode_id': ident, 'asset_id': asset, 'complete': True,
                'task_type': 'loading', 'condition_group': group, 'task_success': group == 'natural',
                'qualification_exclusions': ['preview_or_interface_diagnostic'] if excluded else []}
        primary = row('main', 'cuvette_xy_1000')
        rows = [row('preview', 'cuvette_xy_1030', excluded=True), primary,
            row('medium', 'cuvette_xy_1030'), row('failure', 'cuvette_xy_1050'),
            row('controlled', 'cuvette_xy_1000', 'deterministic_action_deviation')]
        chosen = report.representative_runs({'runs': rows}, primary)
        self.assertEqual([x['episode_id'] for x in chosen], ['main', 'medium', 'failure', 'controlled'])

    def test_camera_association_requires_matching_episode_UUID(self):
        sync = {'episode_id': 'correct', 'cameras': {name: {'samples': 7,
            'same_observation_matches_current_USD_within_1e_8_m': 7}
            for name in ('side_camera', 'wrist_camera')}}
        self.assertIn('侧视7/7、腕视7/7', report.camera_association(sync, {}, 'correct'))
        self.assertIn('结果未知', report.camera_association(sync, {}, 'other'))
        self.assertNotIn('7/7', report.camera_association(sync, {}, 'other'))

    def test_final_progress_uses_actual_quota_completion(self):
        complete = report.final_progress({'qualified_success_count': 4, 'qualified_failure_count': 3,
            'success_target': 4, 'failure_target': 3, 'success_missing': 0, 'failure_missing': 0})
        self.assertIn('已达到本轮', complete)
        self.assertIn('成功4条、有效失败3条', complete)
        self.assertNotIn('20条', complete)
        self.assertIn('尚缺成功未知条', report.final_progress({}))

    def test_docx_grid_and_columns_match_deliberate_widths(self):
        from docx import Document
        from docx.shared import Cm
        with tempfile.TemporaryDirectory() as d:
            target = Path(d) / 'table_widths.docx'
            report.write_docx([[report.table(['A', 'B'], [['x', 'y']], [3.0, 10.0])]], target)
            table = Document(target).tables[0]
            self.assertEqual([column.width.twips for column in table.columns], [Cm(3).twips, Cm(10).twips])
            self.assertEqual([grid.w.twips for grid in table._tbl.tblGrid.gridCol_lst], [Cm(3).twips, Cm(10).twips])

    def test_standard_episode_labels_keep_uuid_and_episode_suffix(self):
        labels = [report.episode_label({'episode_id': f'uuid-{index}-unique',
            'episode_directory': f'collection_standard/runs/verify5_long_shared_prefix/episode_{index:04d}'})
            for index in range(5)]
        self.assertEqual(len(set(labels)), 5)
        self.assertIn('uuid-0-unique', labels[0])
        self.assertTrue(labels[0].endswith('episode_0000'))

    def test_audited_controlled_stops_do_not_become_natural_failures(self):
        summary = {'collection20_success20_failure': {'condition_groups': {
            'natural': {'qualified_failure': 0},
            'deterministic_action_deviation': {'qualified_failure': 2}}},
            'runs': [{'qualified_failure': True,
                'condition_group': 'deterministic_action_deviation',
                'failure_type': 'CONTROLLED_EARLY_STOP'} for _ in range(2)]}
        text = report.controlled_failure_paragraph(summary)
        self.assertIn('自然控制0条', text)
        self.assertIn('确定性动作偏差2条', text)
        self.assertIn('全部为CONTROLLED_EARLY_STOP', text)
        self.assertIn('不是自然受阻或碰撞失败样本', text)
        self.assertNotIn('20条', text)

    def test_mixed_or_unknown_controlled_types_are_not_inferred_as_early_stops(self):
        summary = {'collection20_success20_failure': {'condition_groups': {
            'deterministic_action_deviation': {'qualified_failure': 1}}},
            'runs': [{'qualified_failure': True,
                'condition_group': 'deterministic_action_deviation', 'failure_type': None}]}
        text = report.controlled_failure_paragraph(summary)
        self.assertIn('自然控制未知条', text)
        self.assertIn('类型为未知', text)
        self.assertNotIn('全部为CONTROLLED_EARLY_STOP', text)

    def test_unknown_is_not_reported_as_false_or_zero(self):
        self.assertEqual(report.state(None), '未知或未执行')
        self.assertEqual(report.num(None), '未知')
        self.assertEqual(report.state(False), '未通过')

    def test_relative_media_links_are_inside_report_folder(self):
        with tempfile.TemporaryDirectory() as d:
            parent = Path(d)
            image = parent / 'media' / 'clip.mp4'
            self.assertEqual(report.relative_target({'path': str(image)}, parent), 'media/clip.mp4')
            with self.assertRaises(ValueError):
                report.relative_target({'path': '/outside/clip.mp4'}, parent)

    def test_failure_text_uses_audited_values_and_keeps_task_exit_separate(self):
        audit = {'maximum_position_gate_observation': {'t_s': 2.5,
            'origin_drift_um': 321.5, 'relative_rotation_change_deg': .25,
            'configured_grasp_anchor_drift_um': 45.25, 'rotation_lever_component_um': 322.},
            'grip_thresholds': {'origin_drift_um': 201.},
            'support_stage_additional_gate': {'xy_um_range': [101.25, 102.5], 'samples': 17,
                'aligned_supported_samples': 0}, 'alignment_thresholds': {'xy_um': 100.},
            'original_independent_verdict': {'task_success': False, 'failure_type': 'GRASP_SLIP',
                'release_observed': True, 'retreat_observed': True,
                'post_retreat_window': {'stable': True}},
            'process_status': {'exit_code': 9}}
        text = '\n'.join(report.failure1050_paragraphs(audit))
        self.assertIn('321.500µm', text)
        self.assertIn('45.250µm', text)
        self.assertIn('101.250至102.500µm', text)
        self.assertIn('完整任务仍为未通过', text)
        self.assertIn('进程实际退出码9单独保留', text)
        self.assertNotIn('616.042', text)

    def test_optional_physics_metadata_and_code_declaration_have_distinct_provenance(self):
        actual = report.backend_snapshot({'runtime_physics': {'physics_backend': 'PhysX',
            'gpu_dynamics_enabled': False, 'enableCCD': True}}, {'physics': {'ccd': False}})
        self.assertEqual(actual['backend_source'], 'runtime_metadata')
        self.assertIs(actual['gpu_dynamics'], False)
        self.assertIs(actual['ccd'], True)
        declaration = report.backend_snapshot({}, {'physics': {'ccd': True}},
            "CreateEnableGPUDynamicsAttr(False);CreateBroadphaseTypeAttr('MBP')")
        self.assertEqual(declaration['backend_source'], 'shared_builder_code_declaration')
        self.assertEqual(declaration['ccd_source'], 'saved_configuration')
        self.assertEqual(declaration['broadphase'], 'MBP')

    def test_missing_failure_measurements_remain_unknown(self):
        text = '\n'.join(report.failure1050_paragraphs({'original_independent_verdict': {}}))
        self.assertIn('未知', text)
        self.assertNotIn('漂移0.', text)
        self.assertNotIn('退出码0', text)

if __name__ == '__main__':
    unittest.main()
