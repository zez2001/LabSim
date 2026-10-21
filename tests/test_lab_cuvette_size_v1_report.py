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

if __name__ == '__main__':
    unittest.main()
