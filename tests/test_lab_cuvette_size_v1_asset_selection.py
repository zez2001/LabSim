"""Registry selection never retunes the original seat, physics or target path."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import yaml
from demos.lab_cuvette_size_v1 import asset_selection

ROOT = Path(__file__).resolve().parents[1]


class AssetSelectionTests(unittest.TestCase):
    def setUp(self):
        self.cfg = yaml.safe_load((ROOT / 'config/lab_cuvette_loading/Size_v1/standard.yaml').read_text())

    def test_standard_resolution_is_idempotent_and_does_not_mutate_input(self):
        original = copy.deepcopy(self.cfg)
        resolved = asset_selection.resolve_asset_config(self.cfg)
        self.assertEqual(self.cfg, original)
        self.assertEqual(resolved, asset_selection.resolve_asset_config(resolved))
        for key in ('physics', 'geometry', 'rack', 'adapter', 'robot', 'cameras', 'scene'):
            self.assertEqual(resolved[key], original[key])
        self.assertEqual(resolved['asset_directory'], original['asset_directory'])

    def test_only_top_asset_id_change_replaces_all_cup_references(self):
        self.cfg['asset_id'] = 'cuvette_xy_1050'
        resolved = asset_selection.resolve_asset_config(self.cfg)
        self.assertEqual(resolved['vessel']['asset_id'], 'cuvette_xy_1050')
        self.assertEqual(resolved['collision_scheme'], 'cuvette_xy_1050')
        self.assertEqual(resolved['vessel']['outer_xy_m'], [.0105, .0105])
        self.assertEqual(resolved['vessel']['mass_kg'], .020)
        self.assertEqual(resolved['source']['vessel'], resolved['source']['vessel_collision'])
        self.assertTrue(resolved['source']['vessel'].endswith('/cuvette_xy_1050.usda'))
        self.assertEqual(resolved['geometry'], self.cfg['geometry'])
        self.assertEqual(resolved['physics'], self.cfg['physics'])

    def test_explicit_asset_argument_wins_and_unknown_is_rejected(self):
        resolved = asset_selection.resolve_asset_config(self.cfg, 'cuvette_xy_0950')
        self.assertEqual(resolved['asset_id'], 'cuvette_xy_0950')
        with self.assertRaisesRegex(ValueError, 'Unknown registered'):
            asset_selection.resolve_asset_config(self.cfg, 'not_registered')

    def test_replacing_original_instrument_directory_is_rejected(self):
        self.cfg['asset_directory'] = 'assets/lab_cuvette_loading/V0_demo03'
        with self.assertRaisesRegex(ValueError, 'original'):
            asset_selection.resolve_asset_config(self.cfg)

    def test_asset_content_tampering_is_detected_without_touching_real_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            registry = json.loads((ROOT / asset_selection.REGISTRY).read_text())
            registry['assets'] = {k: registry['assets'][k] for k in ('cuvette_xy_1000', 'cuvette_xy_1250')}
            path = root / asset_selection.REGISTRY
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps(registry))
            for record in registry['assets'].values():
                for name in (record['asset_path'], record['source']['path']):
                    target = root / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes((ROOT / name).read_bytes())
                (root / record['asset_path']).with_suffix('.json').write_text(json.dumps(record))
            bad = root / registry['assets']['cuvette_xy_1000']['asset_path']
            bad.write_bytes(bad.read_bytes() + b'\n#changed\n')
            with patch.object(asset_selection, 'ROOT', root):
                with self.assertRaisesRegex(ValueError, 'asset SHA256 differs'):
                    asset_selection.resolve_asset_config(self.cfg)

    def test_omegaconf_type_and_values_are_preserved(self):
        try:
            from omegaconf import OmegaConf
        except ImportError:
            self.skipTest('Existing OmegaConf not available in this Python')
        cfg = OmegaConf.create(self.cfg)
        resolved = asset_selection.resolve_asset_config(cfg)
        self.assertTrue(OmegaConf.is_config(resolved))
        self.assertEqual(OmegaConf.to_container(resolved.physics), self.cfg['physics'])
        self.assertEqual(OmegaConf.to_container(resolved),
                         OmegaConf.to_container(asset_selection.resolve_asset_config(resolved)))


if __name__ == '__main__':
    unittest.main()
