"""Review current public joint semantics using actual facade/task conversion.

The robot/FK/physics parent are explicit CPU stubs. This is a software counter-
example, not Franka motion, a physical run, or a historical H5 relabelling.
"""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import numpy as np
import pytest
from scipy.spatial.transform import Rotation

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path(__file__).with_suffix('.json'))
    args = parser.parse_args()
    helper_path = ROOT / 'tests/test_lab_cuvette_project_v1_1_tracking_integration.py'
    spec = importlib.util.spec_from_file_location('joint_semantics_cpu_helpers', helper_path)
    helper = importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
    from demos.lab_cuvette_project_v1_1.environment import ProjectEnvironment
    from policy.backends.action_adapters import act_dp_joint_action
    cases = []
    with pytest.MonkeyPatch.context() as patch:
        make_task = helper.task_factory.__wrapped__(patch)
        def ideal_robot_step(task, action):
            q, opening, effort, _, conversion = task._convert_action(action)
            task.low_actions.append(copy.deepcopy(action));task.conversions.append(conversion)
            task.qcmd, task.actual_q = q.copy(), q.copy()
            task.grip, task.effort = opening, effort
            task.applied_count += 1;task.control_steps += 1;task.steps += 4;task.t += 1 / 60
            position, matrix = task.forward(q[:7])
            task.debug['actual_tcp_position_m'] = position.tolist()
            task.debug['actual_tcp_quaternion_wxyz'] = np.roll(Rotation.from_matrix(matrix).as_quat(), 1).tolist()
            return ({}, 0., False, False, {})
        patch.setattr(helper.CPUParent, 'step', ideal_robot_step)
        for kind, enabled in [('joint_position', True), ('joint_velocity', True),
                ('joint_position', False), ('ee_delta', True), ('direct_joint_position', True)]:
            task = make_task(enabled=enabled)
            task.low_actions, task.conversions = [], []
            task._result = None
            task.get_observation = lambda: dict(episode_id=task.episode_id,
                observation_id=f'{task.episode_id}:{task.control_steps}',
                TCPpose=dict(position_m=list(task.debug['actual_tcp_position_m']),
                    quaternion_wxyz=list(task.debug['actual_tcp_quaternion_wxyz'])),
                joint_positions=task.actual_q.copy(), gripper_opening_m=task.grip, images={})
            requested_q = np.array([.0001, 0, 0, 0, 0, 0, .001])
            public = act_dp_joint_action(np.r_[requested_q, .005], task.get_observation(), action_id='cpu_one')
            public['type'] = kind
            if kind == 'joint_velocity':
                public['values'] = (requested_q * 60).tolist()
            if kind == 'ee_delta':
                public['values'] = [.0001, 0, 0, 0, 0, 0];public['frame'] = 'world'
            if kind == 'direct_joint_position':
                public['type'] = 'joint_position'
                low = dict(public, observation_step=task.control_steps)
                task.step(low);receipt = None
            else:
                receipt = ProjectEnvironment(task).execute(public)
            applied = task.qcmd[:7]
            low = task.low_actions[0]
            conversion = task.conversions[0]
            cases.append(dict(request_type=kind, cartesian_tracking_enabled=enabled,
                requested_arm_q7_rad=requested_q.tolist() if kind != 'ee_delta' else None,
                executed_arm_command_q7_rad=applied.tolist(),
                maximum_arm_target_change_rad=float(np.max(abs(applied - requested_q))) if kind != 'ee_delta' else None,
                redundant_coordinate_requested_rad=float(requested_q[6]) if kind != 'ee_delta' else None,
                redundant_coordinate_executed_rad=float(applied[6]),
                low_level_type=low['type'], preserved_raw_public_type=low.get('raw_model_action', {}).get('type'),
                conversion_input_type=conversion['input_type'],cartesian_bias_applied=conversion.get('robot_tracking') is not None,
                previous_command_FK_minus_actual_m=None if conversion.get('robot_tracking') is None else conversion['robot_tracking']['raw_position_error_m'],
                requested_qplan=low.get('_executor_q7'), applied_gripper_total_opening_m=task.grip,
                nominal_TCP_reference=conversion['target_pose'],effective_IK_goal=conversion.get('effective_IK_goal_TCP'),
                receipt_target_reached=None if receipt is None else receipt['target_reached'],
                receipt_final_TCP_error_m=None if receipt is None else receipt['final_position_error_m'],
                receipt_target_scope=None if receipt is None else receipt['target_reached_scope'],
                all_runtime_stops=[json.loads(line).get('runtime_stop') for line in
                    (task.episode_dir / 'execution_trace.jsonl').read_text().splitlines()]))
    sources = ['demos/lab_cuvette_project_v1_1/environment.py', 'tasks/lab_cuvette_loading_project_v1_1.py',
        'policy/backends/action_adapters.py', 'data_collectors/lab_cuvette_env_v1_collector.py']
    value = dict(schema='labsim.Project_v1_1.public_joint_semantics_review.v1',
        scope='Actual facade and actual task conversion AST with explicit redundant FK and ideal drive stubs; no Isaac, API or H5.',
        toy_FK='q0..q2 map to position, q3..q5 to rotation vector, q6 is redundant. This is not a Franka kinematic model.',
        runtime_source_SHA256={name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in sources},
        current_public_joint_targets_changed=any(c['maximum_arm_target_change_rad'] > 1e-12 for c in cases
            if c['request_type'] in ('joint_position', 'joint_velocity') and c['cartesian_tracking_enabled']),
        cases=cases, runtime_modified=False, active_simulation_touched=False, HDF5_opened=False)
    with args.output.open('x') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False);stream.write('\n')
    print(json.dumps(value, ensure_ascii=False))


if __name__ == '__main__':
    main()
