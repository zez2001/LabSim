"""CPU-only small handoff guards; no refresh, live HDF5 or GPU lock."""
from copy import deepcopy
import unittest

from scripts.refresh_lab_cuvette_size_v1_handoff import compact_asset, final_audit_evidence


class HandoffEvidenceTests(unittest.TestCase):
    def audit(self):
        event = dict(qualified=True, actual_event_count=1,
            actual_event=dict(t=1.0, actual_depth_m=.001), actual_depth_m=.001,
            checks=dict(event_matches_actual_successor_time=True,
                        event_depth_matches_saved_physical_state=True),
            source_sidecar_sha256=dict(events="source-hash"))
        readers = [dict(sample_filter="failure", policy_type=policy,
            train_episode_ids=["failure-episode"], validation_episode_ids=[],
            episode_split_disjoint=True, train_and_validation_same_frozen_standard_scene=True,
            scene_randomization_enabled=False,
            checks=[dict(exact_executed_actions=True, exact_saved_RGB=True)],
            optimizer_or_training_executed=False) for policy in ("act", "dp")]
        return dict(qualified_success_count=0, qualified_failure_count=1,
            episodes=[dict(failure=True,
                labels=dict(condition_group="deterministic_action_deviation", episode_id="failure-episode"),
                controlled_deviation_event_evidence=event)], reader_validation=readers)

    def test_compact_asset_preserves_physics_and_removes_only_geometry_noise(self):
        source = dict(asset_id="test", mass_kg=.02,
            material_attributes=[dict(attributes={"physics:dynamicFriction": ".5"})],
            root_rigid_body_attributes={"physics:mass": ".02"},
            collision_input_shapes=[dict(prim="/Asset/Collision/wall", approximation="convexHull",
                contact_offset_m=.00005, rest_offset_m=0, bounds_m=[[0, 0, 0], [1, 1, 1]],
                configuration_attributes_excluding_vertex_arrays={
                    "physics:collisionEnabled": "True", "physxConvexHullCollision:hullVertexLimit": "256",
                    "visibility": "invisible", "points": "large-array"})])
        result = compact_asset(source)
        self.assertEqual(result["material_attributes"], source["material_attributes"])
        self.assertEqual(result["root_rigid_body_attributes"], source["root_rigid_body_attributes"])
        shape = result["collision_input_shapes"][0]
        self.assertEqual(shape["contact_offset_m"], .00005)
        self.assertEqual(shape["physical_configuration_attributes"], {
            "physics:collisionEnabled": "True", "physxConvexHullCollision:hullVertexLimit": "256"})

    def test_actual_event_and_normal_readers_pass_without_mutating_source(self):
        audit = self.audit()
        before = deepcopy(audit)
        evidence = final_audit_evidence(audit)
        self.assertEqual(audit, before)
        self.assertEqual(len(evidence["controlled_failure_actual_events"]), 1)
        self.assertEqual(len(evidence["normal_readers_and_whole_episode_splits"]), 2)
        self.assertFalse(evidence["training_executed"])

    def test_old_configuration_only_audit_cannot_become_final_snapshot(self):
        audit = self.audit()
        audit["episodes"][0].pop("controlled_deviation_event_evidence")
        with self.assertRaisesRegex(ValueError, "actual teacher-event"):
            final_audit_evidence(audit)

    def test_missing_DP_or_unsaved_RGB_proof_rejected(self):
        audit = self.audit()
        audit["reader_validation"].pop()
        with self.assertRaisesRegex(ValueError, "ACT/DP"):
            final_audit_evidence(audit)
        audit = self.audit()
        audit["reader_validation"][0]["checks"][0]["exact_saved_RGB"] = False
        with self.assertRaisesRegex(ValueError, "saved-action/RGB"):
            final_audit_evidence(audit)

    def test_whole_episode_leak_and_scene_randomization_rejected(self):
        audit = self.audit()
        audit["reader_validation"][0]["validation_episode_ids"] = ["failure-episode"]
        with self.assertRaisesRegex(ValueError, "whole-episode"):
            final_audit_evidence(audit)
        audit = self.audit()
        audit["reader_validation"][0]["scene_randomization_enabled"] = True
        with self.assertRaisesRegex(ValueError, "frozen-standard"):
            final_audit_evidence(audit)


if __name__ == "__main__":
    unittest.main()
