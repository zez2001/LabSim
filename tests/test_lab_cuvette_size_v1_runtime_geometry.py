"""Analytic material/contact cases, not simulator-generated success fixtures."""
import unittest

import numpy as np
import trimesh
from scipy.spatial.transform import Rotation

from demos.lab_cuvette_size_v1.runtime_geometry import SeatMaterialGeometry, _segment_crossings


class RuntimeMaterialCheckTests(unittest.TestCase):
    def setUp(self):
        # Closed8mm square solid resting on a finite20mm square base plate.
        # These independent analytic bodies expose signed penetration units.
        vessel=trimesh.creation.box([.008,.008,.020])
        vessel.apply_translation([0,0,.010])
        target=trimesh.creation.box([.020,.020,.002])
        target.apply_translation([0,0,-.001])
        self.geometry=SeatMaterialGeometry(vessel.vertices,vessel.faces,
            target.vertices,target.faces,target_floor_m=[0,0,0],
            instrument_rotation=np.eye(3),target_depth_m=.020)

    def test_known_submillimetre_floor_penetration_uses_surface_distance(self):
        result=self.geometry.measure([0,0,-.0001],[1,0,0,0],1.)
        self.assertAlmostEqual(result['input_geometry_overlap_observed_m'],.0001,places=9)
        self.assertFalse(result['target_region_contains_object'])
        self.assertGreater(result['input_geometry_surface_crossing_count'],0)
        self.assertIsNone(result['native_target_overlap_m'])

    def test_declared_fifty_micron_gate_allows_observed_ten_micron_contact(self):
        result=self.geometry.measure([0,0,-.00001],[1,0,0,0],1.)
        self.assertAlmostEqual(result['input_geometry_overlap_observed_m'],.00001,places=9)
        self.assertTrue(result['target_region_contains_object'])

    def test_true_six_degree_pose_exposes_tilted_bottom_intersection(self):
        q=Rotation.from_euler('x',2,degrees=True).as_quat()
        result=self.geometry.measure([0,0,0],np.r_[q[3],q[:3]],1.)
        self.assertGreater(result['input_geometry_overlap_observed_m'],.0001)
        self.assertFalse(result['target_region_contains_object'])

    def test_cache_exposes_original_sample_time_and_age(self):
        self.geometry.measure([0,0,0],[1,0,0,0],1.)
        result=self.geometry.measure([0,0,-.001],[1,0,0,0],1.004)
        self.assertEqual(self.geometry.computations,1)
        self.assertAlmostEqual(result['input_geometry_cache_age_s'],.004)
        result=self.geometry.measure([0,0,-.001],[1,0,0,0],1.020)
        self.assertEqual(self.geometry.computations,2)
        self.assertGreater(result['input_geometry_overlap_observed_m'],.0005)

    def test_remote_measurement_stays_unknown(self):
        result=self.geometry.measure([.5,0,0],[1,0,0,0],0.)
        self.assertIsNone(result['input_geometry_overlap_observed_m'])
        self.assertIsNone(result['target_region_contains_object'])

    def test_finite_segments_do_not_count_infinite_ray_hits(self):
        mesh=trimesh.creation.box([2,2,2])
        result=_segment_crossings(np.array([[0.,0.,2.],[0,0,2]]),
            np.array([[0.,0.,1.5],[0,0,-2.]]),mesh)
        self.assertEqual(result['count'],2)
        self.assertEqual(result['tested_segments'],2)

    def test_metadata_does_not_claim_global_or_cooked_accuracy(self):
        metadata=self.geometry.metadata()
        self.assertFalse(metadata['sample_spacing_is_global_error_bound'])
        self.assertFalse(metadata['native_target_overlap_measured'])
        self.assertEqual(metadata['target_boundary_edge_count'],0)
        self.assertEqual(metadata['target_face_count'],12)


if __name__=='__main__':
    unittest.main()
