"""Report content validation without Word authoring or a document marker."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1] / 'docs/lab_cuvette_loading/Size_v1/report/generate_report.py'
spec = importlib.util.spec_from_file_location('size_report', SOURCE)
report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(report)


class ReportTests(unittest.TestCase):
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
