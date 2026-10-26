"""Versioned release labels over the unchanged independent physical criteria."""
from demos.lab_cuvette_size_v1.scorer import Scorer as SizeScorer


class Scorer(SizeScorer):
    def finalize(self, *args, **kwargs):
        result = super().finalize(*args, **kwargs)
        result.update(schema='labsim.Project_v1.independent.v1', scene_version='Project_v1',
                      scorer_version='Project_v1.independent.v1', real_calibrated=False)
        return result
