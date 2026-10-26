"""Full-pose, per-episode free-space diagnostics over public robot tools."""
from __future__ import annotations
import copy
from pathlib import Path
import numpy as np
from scipy.spatial.transform import Rotation
from .free_space_plan import build_free_space_plan, anchor_return_commands, anchor_pose_error
from .probes import ManualProbe, write


def run_checked_free_space(facade, output):
    options=dict(mode='standard', teacher=False, policy_id='deterministic_control_diagnostic',
                 demonstrator_id='ManualGenericInterfaceProbe')
    facade.reset(0, options)
    initial=copy.deepcopy(facade.observe()['TCPpose'])
    rotated=copy.deepcopy(initial)
    rotated['position_m']=(np.asarray(initial['position_m'])+[0.,0.,.03]).tolist()
    R=Rotation.from_rotvec([0.,0.,.1])*Rotation.from_quat(np.roll(initial['quaternion_wxyz'],-1))
    rotated['quaternion_wxyz']=np.roll(R.as_quat(),1).tolist()
    plan=build_free_space_plan(initial,rotated)
    write(Path(output)/'free_space_plan.json',plan)
    results=[]
    for index, group in enumerate(plan['episodes']):
        if index:facade.reset(0, options)
        probe=ManualProbe(facade);checks=[];completed=0;failure=None
        anchor=group['anchor_pose']
        def return_anchor():
            for action in anchor_return_commands(probe.tools.observe()['TCPpose'],anchor):
                if not probe.call(action['tool'],**action['arguments']):return False
            check=anchor_pose_error(probe.tools.observe()['TCPpose'],anchor)
            checks.append(check)
            return check['reached']
        for definition in group['probes']:
            if not return_anchor():failure='FULL_POSE_ANCHOR_NOT_REACHED';break
            if completed==0:probe.snapshot(group['episode_id']+'_anchor')
            actual_start=copy.deepcopy(probe.tools.observe()['TCPpose'])
            action=definition['action'];ok=probe.call(action['tool'],**action['arguments'])
            probe.records[-1]['probe_definition']=dict(definition,actual_start=actual_start,
                anchor_start_check=checks[-1],pose_index=0 if group['pose_id']=='pose0' else 1,
                signed_axis=('X','Y','Z').index(definition['axis']),
                signed_amplitude_m=definition['sign']*definition['amplitude_m'],free_space_intent=True)
            write(probe.task.episode_dir/'probe_actions.json',probe.records)
            if not ok:failure='SIGNED_PROBE_NOT_COMPLETED';break
            completed+=1
        if failure is None:
            for action in group['epilogue']:
                ok=return_anchor() if action['kind']=='return_anchor' else probe.call(action['tool'],**action['arguments'])
                if not ok:failure='EPILOGUE_NOT_COMPLETED';break
        probe.snapshot(group['episode_id']+'_terminal')
        if not facade.task.ended:facade.task.finalize_episode('CONTROL_DIAGNOSTIC_COMPLETE','POLICY_BUDGET')
        results.append(dict(group=group['episode_id'],signed_probes_completed=completed,
            full_diagnostic_passed=completed==24 and failure is None,failure=failure,
            anchor_checks=checks,actions=probe.records,result=facade.task._result))
        write(Path(output)/'diagnostic_summary.json',results)
    write(Path(output)/'run_manifest.json',dict(schema='labsim.Project_v1_1.diagnostic.v1',
        mode='free-space-checked',episodes_completed=len(results),model_calls=0,
        diagnostic_not_GPT_demonstration=True,sequential_single_GPU=True,
        full_pose_anchor=True,independent_group_reset=True,
        frozen_scene_sha256=facade.task.release_contract['frozen_scene_sha256']))
    return 0
