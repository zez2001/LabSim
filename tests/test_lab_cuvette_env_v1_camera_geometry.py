"""CPU camera-axis math; rendered visibility still requires real Isaac checks."""
import unittest
import numpy as np
from demos.lab_cuvette_env_v1.cameras import look_at_usd, pose_matrix, policy_image, normalized_camera_spec, CameraRig, DEFAULT_CAMERA_CONFIG,depth_summary,diagnostic_json

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

    def test_cleanup_continues_after_vendor_detach_error_and_is_idempotent(self):
        class BrokenAnnotator:
            def detach(self,paths):raise TypeError('Invalid NodeObj object in Py_Node in getAttributes')
        class Product:
            def __init__(self):self.destroyed=False
            def destroy(self):self.destroyed=True
        class Sensor:
            def __init__(self):
                self._custom_annotators={'rgb':BrokenAnnotator()};self._fabric_time_annotator=None
                self._render_product_path='/Render/product';self._render_product=Product();self._current_frame={}
            def pause(self):pass
        sensors={name:Sensor() for name in ('side_camera','wrist_camera')}
        products=[s._render_product for s in sensors.values()]
        rig=CameraRig({},sensors,{},1.)
        result=rig.close()
        self.assertTrue(result['cleanup_errors_observed']);self.assertTrue(rig.closed)
        self.assertTrue(all(p.destroyed for p in products))
        self.assertTrue(all(not s._custom_annotators and s._render_product is None for s in sensors.values()))
        self.assertIsNone(rig.close())

    def test_bad_axis_is_not_silently_replaced(self):
        with self.assertRaises(ValueError):look_at_usd([0,0,0],[0,0,0],[0,0,1])
        with self.assertRaises(ValueError):look_at_usd([0,0,1],[0,0,0],[0,0,1])

    def test_policy_transform_is_explicit_chw_without_rotation(self):
        source=np.zeros((480,640,3),np.uint8);source[:,:,0]=127;source[:,:,2]=31
        out=policy_image(source)
        self.assertEqual(out.shape,(3,256,256));self.assertTrue((out[0]==127).all());self.assertTrue((out[2]==31).all())

    def test_debug_depth_nonfinite_values_are_not_zero_filled_or_policy_images(self):
        import json
        values=np.array([[np.inf,0],[.25,np.nan]])
        result=depth_summary(values)
        self.assertEqual(result['finite_positive_fraction'],.25)
        self.assertEqual(result['min_m'],.25);self.assertIsNone(result['center_m'])
        encoded=json.dumps(diagnostic_json(dict(depth=result,raw_matrix=np.eye(4))),allow_nan=False)
        self.assertIn('null',encoded)

if __name__=='__main__':unittest.main()
