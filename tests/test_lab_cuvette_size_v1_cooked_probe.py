"""Pure CPU geometry checks for the runtime probe; no Isaac process launched."""
import unittest

import numpy as np

from demos.lab_cuvette_size_v1.cooked_probe import _json_hit, point_to_triangles, surface_comparison, triangulate


class CookedProbeTests(unittest.TestCase):
    def test_point_face_distance_is_not_nearest_vertex(self):
        triangle = np.array([[[0, 0, 0], [1, 0, 0], [0, 1, 0]]], float)
        self.assertAlmostEqual(point_to_triangles([.2, .2, .01], triangle)[0], .01)
        self.assertAlmostEqual(point_to_triangles([.5, -.1, 0], triangle)[0], .1)
        self.assertAlmostEqual(point_to_triangles([2, 0, 0], triangle)[0], 1.)

    def test_polygon_indices_have_consistent_faces(self):
        self.assertTrue(np.array_equal(triangulate([4, 3], [0, 1, 2, 3, 4, 5, 6]),
            [[0, 1, 2], [0, 2, 3], [4, 5, 6]]))

    def test_pybind_callback_uses_snake_case_face_index(self):
        class Hit:
            collision = "/seat"
            rigid_body = "/instrument"
            face_index = 7
            position = [.1, .2, .3]
            normal = [0., 0., 1.]
            distance = .01
        value = _json_hit(Hit())
        self.assertEqual(value["faceIndex"], 7)
        self.assertEqual(value["rigidBody"], "/instrument")

    def test_mm_local_coordinates_full_scale_and_translation_applied(self):
        source = np.array([[0, 0, 0], [1000, 0, 0], [0, 1000, 0]], float)
        cooked = source + [0, 0, .02]
        matrix = np.diag([.001, .001, .001, 1.])
        matrix[3, :3] = [1., 2., 3.]
        result = surface_comparison(source, [[0, 1, 2]], cooked, [[0, 1, 2]], matrix, 1.)
        self.assertAlmostEqual(result["max_observed_cooked_to_input_surface_distance_m"], .00002)
        self.assertAlmostEqual(result["max_observed_input_to_cooked_surface_distance_m"], .00002)
        self.assertEqual(result["input_world_bounds_m"], [[1., 2., 3.], [2., 3., 3.]])
        self.assertEqual(result["cooked_to_input_sample_count"], 4)


if __name__ == "__main__":
    unittest.main()
