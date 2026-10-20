"""Read-only reanalysis of an actual demo04 trace; never a new simulation."""
from pathlib import Path
import argparse
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from omegaconf import OmegaConf
from demos.lab_cuvette_demo04.scene import layout
from tasks.lab_cuvette_loading_env_v1_scorer import CuvetteLoadingEnvV1Scorer


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--audit', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    cfg = OmegaConf.load(args.source / 'config.yaml')
    lay = layout(cfg)
    audit = json.loads(args.audit.read_text())
    scorer = CuvetteLoadingEnvV1Scorer(cfg, lay, audit)
    records = json.loads((args.source / 'physics_records.json').read_text())
    automatic = []
    for r in records:
        row = dict(t=r['t'], physics_step=r['physics_step'], phase=r['phase'],
            object_position_m=r['position'], object_quaternion_wxyz=r['quaternion'],
            object_bottom_world_z_m=r['source_bottom_z_m'],
            source_bottom_z_m=r['source_bottom_z_m'],
            depth_m=lay['target_rim_z']-r['source_bottom_z_m'],
            target_bottom_gap_m=r['target_bottom_signed_gap_m'],
            xy_error_target_m=r['xy_error_m'], tilt_deg=r['tilt_deg'], yaw_error_deg=None,
            finger_contact_N=r['finger_force_N'], finger_joint_positions_m=r['joints'][7:9],
            cup_in_hand_position_m=r['cup_in_hand_position_m'],
            cup_in_hand_quaternion_wxyz=r['cup_in_hand_quaternion'],
            actual_tcp_position_m=r['actual_tcp'], joints9=r['joints'],
            target_bottom_support_N=None, wall_contact_N=None,
            source_rack_penetration_m=r['source_penetration_m'], native_target_overlap_m=None,
            native_linear_velocity_m_s=r['linear_velocity'],
            native_angular_velocity_rad_s=r['angular_velocity'],
            fd_linear_velocity_m_s=r['fd_com_velocity'], target_region_contains_object=None,
            gripper_object_clearance_m=r['independent_geometry']['robot_to_vessel_clearance_m'],
            commanded_bottom_z_m=r['target_tcp'][2]-float(cfg.robot.grasp_above_bottom_m))
        response = scorer.update(row)
        if response['terminate']:
            automatic.append((r['t'], response['failure_type']))
    result = dict(scope='Actual historical demo04 diagnostic03 trace reanalysis; no new simulation and no historical edit.',
        source_records=str(args.source / 'physics_records.json'),
        source_sha256=sha(args.source / 'physics_records.json'), source_rows=len(records),
        scorer_source_sha256=sha(ROOT / 'tasks/lab_cuvette_loading_env_v1_scorer.py'),
        analysis_implementation_sha256=sha(__file__),
        geometry_audit_source=str(args.audit), geometry_audit_sha256=sha(args.audit),
        canonical_mapping=dict(depth_m='Actual target rim worldZ minus recorded actual visual minimum worldZ; not command depth.',
            target_bottom_support_N=None, wall_contact_N=None, native_target_overlap_m=None,
            target_region_contains_object=None,
            gripper_object_clearance_m='Historical independent_geometry.robot_to_vessel_clearance_m; not proof of retreat without prior physical release.'),
        automatic_failure_observations=automatic,
        score=scorer.finalize('historical_demo04_diagnostic03', 'preinsert_diagnostic', 'HISTORICAL_TRACE_REANALYSIS'))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({k: result['score'][k] for k in ('record_valid', 'task_success', 'failure_type', 'grasp_relative_pose', 'measured_grasp_segments')}, indent=2))


if __name__ == '__main__':
    main()
