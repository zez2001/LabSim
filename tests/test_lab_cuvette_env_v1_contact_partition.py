"""Pure contact-sign/region math, not a substitute for PhysX API verification."""
import unittest
import numpy as np
from demos.lab_cuvette_env_v1.physics_capture import resolve_contact_sign,classify_seat_point,rigid_following_bottom

class ContactPartitionTest(unittest.TestCase):
    def test_signed_point_sum_is_bound_to_pair_aggregate(self):
        raw=np.array([[0,0,-.12],[0,0,-.08]])
        result=resolve_contact_sign(raw,[0,0,.2])
        self.assertTrue(result['resolved']);self.assertEqual(result['sign'],-1)
        self.assertAlmostEqual(result['residual_N'],0)

    def test_inconsistent_buffers_remain_unknown(self):
        result=resolve_contact_sign([[1,0,0]],[0,1,0])
        self.assertFalse(result['resolved']);self.assertIsNone(result['sign'])

    def test_bottom_wall_and_top_are_independent(self):
        R=np.eye(3);origin=[.1,.2,.887]
        kind,_,_=classify_seat_point([.101,.201,.88701],[0,0,.196],origin,R,.027)
        self.assertEqual(kind,'bottom')
        kind,_,_=classify_seat_point([.1063,.2,.88701],[1,0,.01],origin,R,.027)
        self.assertEqual(kind,'wall_or_other')
        kind,_,_=classify_seat_point([.1063,.2,.914],[1,0,.01],origin,R,.027)
        self.assertEqual(kind,'entrance_or_top_feature')

    def test_commanded_bottom_uses_actual_outline_and_relative_transform(self):
        from scipy.spatial.transform import Rotation
        vertices=np.array([[-.01,-.02,0],[.01,.02,.0675]])
        value=rigid_following_bottom(vertices,[0,0,.1],Rotation.identity(),[0,0,1.],Rotation.from_euler('x',180,degrees=True))
        self.assertAlmostEqual(value,.8325)
        self.assertNotAlmostEqual(value,1.-.1-.0675/2)  # The object origin/centre is not its lowest outline point.

    def test_net_seat_z_does_not_make_top_contact_bottom_support(self):
        kind,_,force=classify_seat_point([0,0,.027],[0,0,5.],[0,0,0],np.eye(3),.027)
        self.assertNotEqual(kind,'bottom');self.assertEqual(force[2],5.)

if __name__=='__main__':unittest.main()
