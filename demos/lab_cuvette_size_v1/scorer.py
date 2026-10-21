"""Size-series scoring, preserving actual cooked-geometry unknowns separately.

Engineering acceptance uses the declared input-material geometry check, physical
bottom contacts, actual finger detachment, retreat and the same3-second gates.
It does not claim a global bound for PhysX cooked surfaces or real calibration.
"""
import numpy as np
from tasks.lab_cuvette_loading_env_v1_scorer import CuvetteLoadingEnvV1Scorer,_number,_get,_vector

class Scorer(CuvetteLoadingEnvV1Scorer):
    def update(self,row):
        outcome=super().update(row)
        if row.get('forbidden_robot_environment_contact'):
            self.invalid_reasons.add('robot_contact_with_original_instrument_or_rack')
            self._automatic_failure='PHYSICS_INVALID'
            return dict(terminate=True,termination_reason='ROBOT_ENVIRONMENT_COLLISION',failure_type='PHYSICS_INVALID')
        penetration=_number(row,'input_geometry_overlap_observed_m')
        if penetration is not None and penetration>self.tolerance_m:
            self.invalid_reasons.add('observed_input_material_overlap_above_declared_limit')
            self._automatic_failure='PHYSICS_INVALID'
            return dict(terminate=True,termination_reason='INPUT_MATERIAL_PENETRATION',failure_type='PHYSICS_INVALID')
        return outcome

    def _window(self,rows,required_s,*,supported=False):
        result=super()._window(rows,required_s,supported=False)
        if not supported or result['status']!='complete':return result
        support=[_number(r,'target_bottom_support_N') for r in rows]
        gaps=[_number(r,'target_bottom_gap_m') for r in rows]
        overlaps=[_number(r,'input_geometry_overlap_observed_m') for r in rows]
        inside=[r.get('target_region_contains_object') for r in rows]
        forces=[_vector(r,'finger_contact_N',2) for r in rows]
        depths=[_number(r,'depth_m') for r in rows]
        tilts=[_number(r,'tilt_deg') for r in rows]
        known=lambda a: all(v is not None for v in a)
        criteria=dict(position_stable=result['stable'],
            target_support=all(v>=float(_get(self.cfg,'demo_release.min_support_N',.1)) for v in support) and all(abs(v)<=float(_get(self.cfg,'demo_release.bottom_distance_m',.00005)) for v in gaps) if known(support+gaps) else None,
            target_contains=all(v is True for v in inside) if known(inside) else None,
            observed_input_material_overlap_within_limit=all(v<=self.tolerance_m for v in overlaps) if known(overlaps) else None,
            no_finger_contact=all(np.all(v<.01) for v in forces) if known(forces) else None,
            upright=all(abs(v)<=float(_get(self.cfg,'acceptance.upright_after_release_deg',1)) for v in tilts) if known(tilts) else None,
            retained_loading_depth=all(v>=float(_get(self.cfg,'geometry.target_depth_m',.027))-self.tolerance_m for v in depths) if known(depths) else None)
        result['criteria']=criteria
        result['geometry_scope']='Independent actual-pose input-material samples/intersection checks; actual cooked surface global error remains unknown'
        result['stable']=False if any(v is False for v in criteria.values()) else None if any(v is None for v in criteria.values()) else True
        return result

    def finalize(self,episode_id,task_type,termination_reason=None,failure_type=None):
        preview=termination_reason=='PREVIEW_COMPLETE'
        if failure_type in ('INITIAL_SUPPORT_INVALID','INITIALIZATION_INVALID'):
            failure_type='INITIALIZATION_INVALID'
        result=super().finalize(episode_id,task_type,termination_reason,failure_type)
        if preview:
            result.update(task_type='scene_preview',task_success=None,workflow_success=None,full_success=None,
                eligible_for_success_bc=False,eligible_for_failure_analysis=False)
        result.update(schema='labsim.Size_v1.independent_physical.v1',
            asset_id=_get(self.cfg,'vessel.asset_id'),scene_version='Size_v1',
            condition_group=_get(self.cfg,'experiment.condition_group','development'),
            variant_pair_success=result['full_success'],native_pair_success=None,
            original_12_5mm_native_pair_verdict_unchanged=True,
            acceptance_geometry_scope='Declared input material geometry checks plus actual physical contact and motion, not calibrated cooked geometry or real accuracy')
        return result
