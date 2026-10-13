import unittest
import numpy as np
from demos.minimal_precision_insertion.geometry import cylinder_mesh, overlap_metrics


class GeometryCheck(unittest.TestCase):
    def setUp(self):
        self.v,self.f=cylinder_mesh(.005,.05,96)
        self.e=np.unique(np.sort(np.concatenate([self.f[:,[0,1]],self.f[:,[1,2]],self.f[:,[2,0]]]),axis=1),axis=0)

    def measure(self,x,z,q=(1.,0,0,0)):
        return overlap_metrics(np.array([x,0,z]),q,self.v,self.e,np.zeros(2),0.)

    def test_clearance_interference_and_depth(self):
        center=self.measure(0.,.035)
        self.assertAlmostEqual(center['depth_m'],.01)
        self.assertEqual(center['overlap_m'],0.)
        interference=self.measure(.0005,.035)
        self.assertGreater(interference['wall_overlap_m'],.00019)

    def test_shallow_rim_contact_is_not_full_lateral_penetration(self):
        m=self.measure(.0008,.044999)
        self.assertGreater(m['wall_radial_intrusion_m'],.00049)
        self.assertLess(m['wall_overlap_m'],.00000101)

    def test_base_and_pose_are_considered(self):
        m=self.measure(0.,.0245)
        self.assertAlmostEqual(m['base_overlap_m'],.0005)
        tilted=self.measure(0.,.035,(np.cos(.025),0,np.sin(.025),0))
        self.assertGreater(tilted['wall_overlap_m'],0.)

    def test_outside_module_cannot_be_scored_as_contained(self):
        m=self.measure(.015,.035)
        self.assertGreater(m['containment_error_m'],.014)


if __name__=='__main__':
    unittest.main()
