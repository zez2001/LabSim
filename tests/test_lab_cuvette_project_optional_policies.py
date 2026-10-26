"""Optional policy-entry contracts; no RPent, checkpoint or GPU required."""
import math
from pathlib import Path
import unittest
import yaml
from policy.backends.rpent_compat import prepare_arguments


class OptionalPolicyEntryContracts(unittest.TestCase):
    def test_pi05_defaults_to_portable_project_transfer(self):
        argv=prepare_arguments(['--backend','pi05','--env-endpoint','http://127.0.0.1:8097','--output','new'])
        config=Path(argv[argv.index('--policy-config')+1])
        self.assertEqual(config.name,'pi05_libero.yaml')
        self.assertEqual(config.parent.parent.name,'Project_v1')
        source=config.read_text()
        self.assertNotIn('/home/',source)
        self.assertNotIn('auth.json',source)
    def test_random_or_preinsert_cannot_replace_fixed_loading(self):
        for extra in (['--layout-mode','random'],['--subtask','preinsert_diagnostic']):
            with self.assertRaises(ValueError):prepare_arguments(['--backend','pi05',*extra])
    def test_pi05_transfer_respects_shared_norm_speed_bounds(self):
        config=Path(__file__).resolve().parents[1]/'config/lab_cuvette_loading/Project_v1/policies/pi05_libero.yaml'
        c=yaml.safe_load(config.read_text());duration=1/c['policy_action_hz']
        self.assertLessEqual(math.sqrt(3)*c['execution_translation_cap_m']/duration,.02)
        self.assertLessEqual(math.sqrt(3)*c['execution_rotation_cap_rad']/duration,.15)
        self.assertEqual(c['expected_weights_sha256'],'4d9089c941793f170b625c2ed0ac7a3aa09b6f103e52dbbc82e67301529d6683')
    def test_harness_retains_explicit_existing_codex_without_global_config(self):
        argv=prepare_arguments(['--backend','harness','--codex-bin','/declared/existing/codex'])
        self.assertEqual(argv[argv.index('--codex-bin')+1],'/declared/existing/codex')


if __name__=='__main__':unittest.main()
