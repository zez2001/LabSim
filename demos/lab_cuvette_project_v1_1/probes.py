"""Explicit deterministic diagnostics using the same public robot executor.

These scripts are not GPT policies. Scene-design coordinates are disclosed for
the manual grasp probe; object truth is recorded for analysis, never fed back.
"""
from __future__ import annotations

import copy
import hashlib
import json
import time
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation

from demos.lab_cuvette_project_v1.runtime import ROOT
from policy.backends.cubence_tools import observation_content, save_observation_artifacts


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


class ManualProbe:
    def __init__(self, facade):
        from policy.backends.cubence_project_v1_1_tools import ProjectV11RobotTools as GenericRobotTools
        self.env = facade
        self.task = facade.task
        limits = json.loads((ROOT/'config/lab_cuvette_loading/Project_v1/policies/cubence_gpt6.json').read_text())['action_limits']
        self.tools = GenericRobotTools(facade, limits)
        self.records = []
        self.snapshot_index = 0

    def snapshot(self, stage):
        # Same encoder as real model transport. No crop, no object truth.
        content = observation_content(self.tools.observe(), image_config=dict(max_side_px=512, jpeg_quality=60, detail='low'))
        files = save_observation_artifacts(content, self.task.episode_dir/'model_input_preview', self.snapshot_index, stage)
        self.snapshot_index += 1
        return files

    def call(self, name, **values):
        obs = self.tools.observe()
        args = dict(episode_id=obs['episode_id'], observation_id=obs['observation_id'],
                    action_id=f'diagnostic-{len(self.records):05d}', **values)
        start = time.perf_counter()
        record = dict(tool=name, arguments=args, start_TCP=copy.deepcopy(obs['TCPpose']))
        try:
            record['receipt'] = self.tools.execute(name, args)
        except Exception as error:
            record.update(error_type=type(error).__name__, error=str(error), receipt=self.tools.execution_receipt(args))
        record.update(wall_seconds=time.perf_counter()-start,
                      actual_endpoint_TCP=copy.deepcopy(self.tools.observe()['TCPpose']))
        self.records.append(record)
        write(self.task.episode_dir/'probe_actions.json', self.records)
        receipt = record.get('receipt') or {}
        print('PROBE_ACTION', len(self.records)-1, name, receipt.get('accepted'),
              receipt.get('target_reached'), receipt.get('stop_reason'),
              receipt.get('final_position_error_m'), flush=True)
        return bool(receipt.get('accepted') and receipt.get('target_reached') and not self.task.ended)

    def delta(self, xyz, *, frame='world', rotation=(0., 0., 0.), duration=None):
        distance = float(np.linalg.norm(xyz))
        angle = float(np.linalg.norm(rotation))
        duration = duration or np.ceil(max(.3, distance/.015, angle/.1)*60)/60
        return self.call('move_ee', mode='ee_delta', values=list(xyz)+list(rotation),
                         frame=frame, duration_s=float(duration))

    def to_position(self, target):
        # Every increment remains relative to its fixed observed start.
        for _ in range(100):
            p = np.asarray(self.tools.observe()['TCPpose']['position_m'])
            delta = np.asarray(target)-p
            length = np.linalg.norm(delta)
            if length < .00075:
                return True
            if length > .025:
                delta *= .025/length
            if not self.delta(delta):
                return False
        return False


def original_prefix(probe, attempt):
    source = ROOT/'outputs/lab_cuvette_loading/Project_v1/gpt_formal5_01'/f'attempt_{attempt:04d}'/'episode_0000/gpt_control/policy_trace.jsonl'
    events = [json.loads(line) for line in source.read_text().splitlines()]
    write(probe.task.episode_dir/'replay_source.json', dict(original_attempt=attempt,
        path=str(source.relative_to(ROOT)), sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        action_prefix_preserved=True, diagnostic_not_GPT_run=True))
    for event in events:
        call = event.get('tool_call')
        if call is None:
            calls = event.get('model_tool_calls', [])
            if len(calls) != 1:
                raise ValueError('Original record lacks one action')
            call = calls[0]
        arguments = copy.deepcopy(call['arguments'])
        if isinstance(arguments, str):
            arguments = json.loads(arguments)
        for key in ('episode_id', 'observation_id', 'action_id'):
            arguments.pop(key, None)
        if not probe.call(call['name'], **arguments):
            break


def free_space(probe):
    # Two robot poses in the existing scene, reached by the same public path.
    # Actual forbidden-contact guards remain active; preflight is kinematic only.
    for pose_index in range(2):
        probe.snapshot(f'free_pose_{pose_index}')
        if pose_index and not probe.delta([0., 0., .03]):
            return
        if pose_index and not probe.delta([0., 0., 0.], rotation=[0., 0., .1]):
            return
        anchor=copy.deepcopy(probe.tools.observe()['TCPpose'])
        for amplitude in (.001, .005, .02, .04):
            for frame in (('world',) if pose_index == 0 else ('world', 'tcp')):
                for axis in range(3):
                    for sign in (1., -1.):
                        d = np.zeros(3);d[axis] = sign*amplitude
                        # Each signed probe starts at the same observed pose;
                        # tracking residuals cannot accumulate into the next.
                        if not probe.to_position(anchor['position_m']):return
                        probe.delta(d, frame=frame)
                        probe.records[-1]['probe_definition']=dict(pose_index=pose_index,frame=frame,
                            signed_axis=axis,amplitude_m=sign*amplitude,free_space_intent=True)
                        if probe.task.ended:return
        if not probe.to_position(anchor['position_m']):return
        if not probe.call('wait', duration_s=1.):
            return
        if not probe.call('gripper', opening_m=.06, effort_limit_N=5., duration_s=1.):
            return
        if not probe.call('gripper', opening_m=.08, effort_limit_N=5., duration_s=1.):
            return


def grasp_transport(probe):
    # Nominal hand-specified pose in this fixed design. This is NOT a GPT result,
    # and it does not use the current object pose to correct the target.
    source = np.asarray(probe.task.ctx['fixtures']['source_floor'])
    grasp = source + [0., 0., .053]
    write(probe.task.episode_dir/'manual_diagnostic_plan.json', dict(
        nominal_grasp_TCP_world_m=grasp.tolist(), source='fixed scene design coordinates',
        online_object_truth_feedback=False, teacher_used=False, no_full_task_macro_exposed=True,
        sequence=['settle', 'approach', 'close', 'lift', 'hold', 'short transport']))
    probe.snapshot('initial')
    if not probe.call('wait', duration_s=3.):return
    if not probe.to_position(grasp + [0., 0., .03]):return
    probe.snapshot('above_source')
    if not probe.to_position(grasp):return
    probe.snapshot('before_close')
    if not probe.call('gripper', opening_m=.009, effort_limit_N=5., duration_s=3.):return
    probe.snapshot('closed')
    if not probe.delta([0., 0., .04], duration=3.):return
    if not probe.delta([0., 0., .04], duration=3.):return
    probe.snapshot('extracted')
    if not probe.call('wait', duration_s=2.):return
    if not probe.delta([.02, 0., .02], duration=2.):return
    probe.snapshot('short_transport')
    probe.call('wait', duration_s=2.)


def pose_hold(probe):
    # Public robot pose measured in closed free_space_02, action58. This is a
    # manual free-space probe, not a target/object pose or a task primitive.
    p=[-.08589575538213295,-.17337017742961916,1.0505144070640076]
    q=[-.007534587183567482,.7470404534418813,-.6644407602178849,-.019805733472933462]
    write(probe.task.episode_dir/'manual_diagnostic_plan.json',dict(
        source='free_space_02 public robot state before action58',reference_TCP=dict(position_m=p,quaternion_wxyz=q),
        purpose='Complete the pose1 wait/gripper checks after original170s timeout; do not relabel the timeout run'))
    if not probe.call('move_ee',mode='ee_pose',values=p+q,frame='world',duration_s=3.):return
    probe.snapshot('safe_rotated_pose')
    if not probe.call('wait',duration_s=1.):return
    if not probe.call('gripper',opening_m=.06,effort_limit_N=5.,duration_s=1.):return
    if not probe.call('gripper',opening_m=.08,effort_limit_N=5.,duration_s=1.):return
    if not probe.call('move_ee',mode='ee_pose',values=p+q,frame='world',duration_s=3.):return
    probe.call('wait',duration_s=3.)


def fine_preinsert(probe):
    # Empty gripper in the designed pre-insertion free space. Manual design
    # coordinates are disclosed; none are provided to a GPT policy.
    target=np.asarray(probe.task.ctx['fixtures']['target_floor'])+[0.,0.,.13]
    initial=probe.tools.observe()['TCPpose'];q=initial['quaternion_wxyz']
    write(probe.task.episode_dir/'manual_diagnostic_plan.json',dict(
        source='fixed scene target fixture design, not online object pose',
        nominal_TCP_world_m=target.tolist(),quaternion_wxyz=q,
        held_object=False,original_seat_unchanged=True,precision_goal_m=.0001))
    def absolute(p,duration):
        return probe.call('move_ee',mode='ee_pose',values=list(p)+q,frame='world',duration_s=duration)
    # The same upright fixed quaternion is held across the transit and probes.
    for waypoint in ([initial['position_m'][0],initial['position_m'][1],1.05],
                     [target[0],target[1],1.05],target):
        for _ in range(50):
            p=np.asarray(probe.tools.observe()['TCPpose']['position_m']);d=np.asarray(waypoint)-p
            length=np.linalg.norm(d)
            if length<.00075:break
            if length>.025:d*=.025/length
            if not absolute(p+d,float(np.ceil(max(.5,np.linalg.norm(d)/.015)*60)/60)):return
        else:return
    probe.snapshot('empty_preinsert_free_pose')
    if not absolute(target,3.):return
    for amplitude in (.0001,.0005,.001,.002):
        for axis in range(3):
            for sign in (1.,-1.):
                if not absolute(target,1.):return
                current=np.asarray(probe.tools.observe()['TCPpose']['position_m']);delta=np.zeros(3);delta[axis]=sign*amplitude
                completed=absolute(current+delta,max(1.,amplitude/.001))
                probe.records[-1]['probe_definition']=dict(near_preinsert=True,frame='world',signed_axis=axis,
                    amplitude_m=sign*amplitude,frozen_orientation_reference_wxyz=q,
                    comparison='actual displacement from fixed observed start AND actual endpoint minus requested target')
                if not completed:return
    if not absolute(target,3.):return
    probe.call('wait',duration_s=3.)


def run_probes(facade, mode, attempts, output):
    results = []
    for attempt in (attempts if mode == 'fixed-replay' else [0]):
        facade.reset(0, dict(mode='standard', teacher=False,
            policy_id='deterministic_control_diagnostic', demonstrator_id='ManualGenericInterfaceProbe'))
        probe = ManualProbe(facade)
        if mode == 'fixed-replay':original_prefix(probe, attempt)
        elif mode == 'free-space':free_space(probe)
        elif mode == 'pose-hold':pose_hold(probe)
        elif mode == 'fine-preinsert':fine_preinsert(probe)
        elif mode == 'grasp-transport':grasp_transport(probe)
        else:raise ValueError('Unknown probe')
        if not facade.task.ended:facade.task.finalize_episode('CONTROL_DIAGNOSTIC_COMPLETE', 'POLICY_BUDGET')
        results.append(dict(mode=mode, original_attempt=attempt if mode=='fixed-replay' else None,
            actions=probe.records, result=facade.task._result))
        write(Path(output)/'diagnostic_summary.json', results)
    write(Path(output)/'run_manifest.json', dict(schema='labsim.Project_v1_1.diagnostic.v1',
        mode=mode, episodes_completed=len(results), model_calls=0,
        diagnostic_not_GPT_demonstration=True, sequential_single_GPU=True,
        frozen_scene_sha256=facade.task.release_contract['frozen_scene_sha256']))
    return 0
