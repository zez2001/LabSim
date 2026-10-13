"""Meaningful independent geometry, scoring and import contract checks."""
import unittest,sys,json,copy
from pathlib import Path
import numpy as np
from omegaconf import OmegaConf
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from demos.lab_cuvette_loading.model import box_overlap,rz,sample_layout,slots
from demos.lab_cuvette_loading.scoring import Scorer
from demos.lab_cuvette_loading.real_import import normalize_record,patch_config,JOINTS
class Checks(unittest.TestCase):
 def setUp(self):self.cfg=OmegaConf.load(ROOT/'config/lab_cuvette_loading/V0.yaml')
 def test_rotated_sat(self):
  I=np.eye(3);half=np.ones(3)*.005
  self.assertEqual(box_overlap(np.zeros(3),I,half,[.02,0,0],rz(45),half),0)
  self.assertGreater(box_overlap(np.zeros(3),I,half,[.005,0,0],rz(45),half),0)
 def test_seeds_and_whole_rack(self):
  a=sample_layout(self.cfg,'random',2000);b=sample_layout(self.cfg,'random',2000);self.assertEqual(a,b)
  canonical=sample_layout(self.cfg,'standard',0);self.assertNotEqual(a['rack_xy_m'],canonical['rack_xy_m'])
  allslots=slots(self.cfg,a);self.assertAlmostEqual(np.linalg.norm(allslots['r0c1']-allslots['r0c0']),self.cfg.rack.pitch_m)
 def test_phase_cannot_fake_success(self):
  source=np.array([0,0,.744]);target=np.array([.2,0,.8]);layout=sample_layout(self.cfg,'standard',0);initial={'objects':{'target':{'position':(source+[0,0,.0225]).tolist()}},'target_object_id':self.cfg.cuvette.target_id,'source_slot_id':'r0c0'}
  score=Scorer(self.cfg,dict(source=source,target=target,boxes=[]),layout,initial)
  m=score.measure(source+[0,0,.0225],[1,0,0,0],[0,0,1.],[0]*7+[.04,.04],[0,0],0);m['phase']='VERIFY'
  self.assertEqual(score.update(28,m)[0],'GRASP_FAILURE')
  # Depth alone cannot substitute for extraction, physical grasp or release.
  m=score.measure(target+[0,0,.0225],[1,0,0,0],[.2,0,1.],[0]*7+[.04,.04],[0,0],0)
  self.assertNotEqual(score.update(1,m)[0],'SUCCESS')
 def test_cross_robot_rejected(self):
  with self.assertRaisesRegex(ValueError,'Cross-robot'):normalize_record(dict(purpose='calibration',robot_type='neo_unconfirmed'))
 def test_holdout_cannot_tune(self):
  with self.assertRaisesRegex(ValueError,'final validation'):patch_config(ROOT/'config/lab_cuvette_loading/V0.yaml',dict(version='V1',purpose='final_validation',parameters=[]))
if __name__=='__main__':unittest.main()
