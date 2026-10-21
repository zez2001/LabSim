"""CPU contracts for retained size hypotheses and conservative geometry gates."""
import hashlib
import json
from pathlib import Path
import unittest
import numpy as np
from demos.lab_cuvette_size_v1.geometry_audit import _clip_above

ROOT = Path(__file__).resolve().parents[1]


class SizeFamilyTests(unittest.TestCase):
    def test_all_registered_assets_exist_and_are_independent(self):
        registry = json.loads((ROOT / 'assets/lab_cuvette_loading/Size_v1/registry.json').read_text())
        self.assertGreaterEqual(len(registry['assets']), 17)
        paths = []
        for ident, record in registry['assets'].items():
            p = ROOT / record['asset_path']
            self.assertTrue(p.is_file())
            self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(), record['asset_sha256'])
            self.assertEqual(ident, record['asset_id'])
            self.assertTrue(all(record['checks'].values()))
            self.assertEqual(record['axis_scale'][2], 1.0)
            self.assertEqual(record['nominal_outer_xy_mm'][0], record['nominal_outer_xy_mm'][1])
            self.assertEqual(record['mass_kg'], .020)
            self.assertEqual(len(record['collision_input_shapes']), 28)
            self.assertIsNone(record['physics_validation'])
            self.assertIsNone(record['complete_task_result'])
            self.assertEqual(len(record['inner_cavity_sections']), 3)
            self.assertGreaterEqual(len(record['material_attributes']), 2)
            paths.append(str(p))
        self.assertEqual(len(paths), len(set(paths)))

    def test_original_source_control_is_unchanged(self):
        p = ROOT / 'assets/lab_cuvette_loading/V0_demo04/vessel_125_mm.usda'
        self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(),
            '8d52757227303edd4f38918ee04763481f08846fdd8daa6803295c8fc77c689d')
        p = ROOT / 'assets/lab_cuvette_loading/V0_demo04/instrument_native.usda'
        self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(),
            'b7145d71ca9668630466648a6144c26de9d555ca228259e22ecb3bf4e02a3a4e')

    def test_clipping_does_not_drop_vertical_walls(self):
        triangle = np.array([[1., 0., 0.], [1., 2., 0.], [1., 0., 2.]])
        clipped = _clip_above(triangle, .5)
        self.assertGreaterEqual(len(clipped), 3)
        self.assertTrue(np.all(clipped[:, 2] >= .5))
        self.assertTrue(np.all(clipped[:, 0] == 1))
        self.assertGreater(np.ptp(clipped[:, 1]), 0)

    def test_clipping_keeps_crossing_edges_and_rejects_below(self):
        triangle = np.array([[0., 0., 0.], [2., 0., 0.], [0., 2., 2.]])
        clipped = _clip_above(triangle, 1.)
        self.assertTrue(np.any(np.all(np.isclose(clipped, [0., 1., 1.]), axis=1)))
        self.assertEqual(len(_clip_above(triangle, 3)), 0)


if __name__ == '__main__':
    unittest.main()
