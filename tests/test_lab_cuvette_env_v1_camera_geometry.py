"""CPU camera-axis math; rendered visibility still requires real Isaac checks."""
import unittest
import numpy as np
from demos.lab_cuvette_env_v1.cameras import look_at_usd, pose_matrix, policy_image, normalized_camera_spec, DEFAULT_CAMERA_CONFIG

class CameraAxisTest(unittest.TestCase):
    def test_optical_axis_points_at_target_and_up_is_projected_correctly(self):
        eye,target,up = [1,2,3],[0,0,0],[0,0,1]
        R,q = look_at_usd(eye,target,up)
        direction=np.asarray(target)-eye;direction=direction/np.linalg.norm(direction)
        np.testing.assert_allclose(R@np.array([0,0,-1]), direction, atol=1e-12)
        self.assertGreater(np.dot(R[:,1],up),0)
        np.testing.assert_allclose(pose_matrix(eye,q)[:3,:3],R,atol=1e-12)
        self.assertAlmostEqual(np.linalg.det(R),1)

    def test_wrist_vessel_vertical_projects_to_image_up(self):
        s=DEFAULT_CAMERA_CONFIG['wrist_camera']
        R,_=look_at_usd(s['localeye_m'],s['localtarget_m'],s['localup'])
        # A downward hand maps upright world cup +Z to hand-local -Z.
        cup_up_in_camera=R.T@np.array([0.,0.,-1.])
        self.assertGreater(cup_up_in_camera[1],.4)
        self.assertAlmostEqual(cup_up_in_camera[0],0,places=10)

    def test_formal_config_aliases_are_respected_and_json_serializable(self):
        import json
        from omegaconf import OmegaConf
        supplied=OmegaConf.create(dict(local_eye_m=[.1,.2,.3],local_target_m=[0,0,.12],
            local_up=[0,0,-1],prim_path='/World/Franka/panda_hand/WristCameraV1',policy_resolution=[256,256]))
        spec=normalized_camera_spec('wrist_camera',supplied)
        self.assertEqual(spec['localeye_m'],[.1,.2,.3])
        self.assertEqual(spec['prim_path'],'/World/Franka/panda_hand/WristCameraV1')
        json.dumps(spec,allow_nan=False)

    def test_bad_axis_is_not_silently_replaced(self):
        with self.assertRaises(ValueError):look_at_usd([0,0,0],[0,0,0],[0,0,1])
        with self.assertRaises(ValueError):look_at_usd([0,0,1],[0,0,0],[0,0,1])

    def test_policy_transform_is_explicit_chw_without_rotation(self):
        source=np.zeros((480,640,3),np.uint8);source[:,:,0]=127;source[:,:,2]=31
        out=policy_image(source)
        self.assertEqual(out.shape,(3,256,256));self.assertTrue((out[0]==127).all());self.assertTrue((out[2]==31).all())

if __name__=='__main__':unittest.main()
