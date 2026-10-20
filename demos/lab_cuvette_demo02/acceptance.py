"""Derive static acceptance from fresh source audit evidence, never nominal labels."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT/'docs/lab_cuvette_loading/V0_demo02'


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--output', type=Path, default=DOC/'acceptance.json')
    args = p.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    cp = args.output.with_name('scene_contract.json')
    if cp.exists():
        raise FileExistsError(cp)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    audit = DOC/'source_audit'
    inventory = json.loads((audit/'delivery_inventory.json').read_text())
    sections = json.loads((audit/'candidate_fit_and_chamber_sections.json').read_text())
    scene_path = ROOT/'assets/lab_cuvette_loading/V0_demo02/video_pose_verified/manifest.json'
    scene = json.loads(scene_path.read_text())
    per_candidate = []
    for c in sections['candidates']:
        per_candidate.append(dict(source_prim=c['source_prim'],
                                  observed_intersecting_sections=len(c['actual_mesh_boundary_intersection_witnesses']),
                                  top_centerline_spacing_m=c['observed_top_centerline_boundary_spacing_m'],
                                  proof='actual original triangle section boundary intersections in declared upright centred pose; not a full arbitrary-path search'))
    rack_found = bool(inventory['rack_source_found'])
    overlap = any(c['observed_intersecting_sections'] for c in per_candidate)
    # Identity remains evidence-qualified even though video supports a candidate.
    identity_confirmed = bool(scene['target_identity_confirmed'])
    blockers = []
    if not rack_found:
        blockers.append('COMPLETE_SOURCE_RACK_ASSET_NOT_FOUND: no CAD dimensions, collision slot IDs or supported source initial state')
    if not identity_confirmed:
        blockers.append('INTERNAL_SEAT_AND_MATCHED_MODEL_UNCONFIRMED: video far-hinge A mapping is provisional; other seat role unresolved')
    if overlap:
        blockers.append('NATIVE_VESSEL_SEAT_GEOMETRY_INTERSECTS: actual mesh sections cross in both declared upright centred candidate poses; no dimension edits allowed')
    result = dict(version='V0_demo02', status='BLOCKED_STATIC_ACCEPTANCE' if blockers else 'REQUIRES_OPERATION_VALIDATION',
                  blockers=blockers, complete_rack_asset_found=rack_found,
                  target_identity_confirmed=identity_confirmed,
                  declared_pose_geometry_passed=not overlap, candidates=per_candidate,
                  scene_correspondence_accepted=False, workflow_executed=False,
                  workflow_success=False, native_pair_executed=False, native_pair_success=False,
                  real_calibrated=False, data_eligible=False,
                  new_physical_trajectory=None, successful_training_batch=None,
                  post_retreat_window=dict(available=False, status='unavailable', reason='new workflow not executed'),
                  stable_after_retreat=None, terminal_window=None,
                  standard=dict(requested=5, executed=0, result=None),
                  random=dict(requested_minimum=10, executed=0, result=None),
                  source_rack_video_count=dict(rows=6, columns=6, basis='two-view manual image count, not CAD or dimensional measurement'),
                  lid_pose=scene['lid_pose'],
                  scene_manifest_sha256=hashlib.sha256(scene_path.read_bytes()).hexdigest(),
                  measured_evidence=[str((audit/x).relative_to(ROOT)) for x in ['delivery_inventory.json', 'candidate_fit_and_chamber_sections.json', 'source_geometry.json']],
                  inherited_release_logic='demos/lab_cuvette_demo01/run.py remains available; new complete executor has not been adapted or physically validated without accepted geometry',
                  limits='static local geometry and composition checks do not prove whole-hand/whole-arm clearance or actual cooked collision dimensions')
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    contract = dict(version='V0_demo02', scene_version='V0_demo02', asset_manifest_sha256=result['scene_manifest_sha256'],
                    scene_correspondence=dict(accepted=False, complete_source_rack_present=False,
                                              evidence=['reference_review/role_correspondence.json', 'source_audit/delivery_inventory.json']),
                    source_slot=dict(id=None, rack_id=None, pose=None, support=None),
                    target_seat=dict(id=None, provisional_id='candidate_far_hinge',
                                     inside_sample_chamber=True, identity_confirmed=False),
                    geometry_audit=dict(accepted=False, evidence=result['measured_evidence']),
                    native_pair_verified=False,
                    real_calibrated=False, data_scope='lab_cuvette_loading_V0_demo02_simulation',
                    runtime_integrity=dict(verified=False, physical_episode_executed=False),
                    physical_episode_executed=False,
                    limits='provisional chamber frames are not accepted target or rack slot geometry')
    with cp.open('x') as f:
        json.dump(contract, f, ensure_ascii=False, indent=2); f.write('\n')
    print(result['status'], 'candidate section witnesses:', [c['observed_intersecting_sections'] for c in per_candidate])


if __name__ == '__main__':
    main()
