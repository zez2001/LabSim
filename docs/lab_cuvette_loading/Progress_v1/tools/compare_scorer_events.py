"""Compare real original scorer evidence with Progress without relabeling either."""
import argparse
import gzip
import json
from pathlib import Path

MAPPING=[
 ('bilateral_grasp_observed','grasp','Same physical bilateral hold; Progress allows 1e-9s numerical comparison tolerance, original literal >=0.1s may confirm one physical step later.'),
 ('source_slot_cleared','extract','Actual held minimum envelope above source rim; same nominal 2mm clearance.'),
 ('held_transport_observed','transport','Different facts: original confirms held XY displacement; Progress also requires fixed preinsert-region arrival.'),
 ('safe_preinsert_observed','align','Different facts: original includes a signed-depth safety band; Progress alignment uses target-frame errors with current-attempt arrival lineage.'),
 ('loaded_pose_candidate','insert','Original candidate includes bottom gap; Progress separates effective full insertion, measured target containment and target support.'),
 ('correct_target_supported','support_transfer','Both bind selected-seat bottom force and geometry; Progress current support also retains sampled input-material overlap evidence.'),
 ('both_fingers_open_and_detached','released','Same measured open/no-contact hold; 1e-9s numerical comparison tolerance can shift first confirmation one physics step.'),
 ('actual_gripper_retreat','retreated','Same actual gripper-input-geometry lower-bound clearance requirement; TCP is not proof.')]


def compare(episode, progress_directory, output):
    episode,progress_directory,output=map(Path,(episode,progress_directory,output))
    if output.exists():raise FileExistsError(output)
    original=json.loads((episode/'result.json').read_text());progress=json.loads((progress_directory/'progress_summary.json').read_text())
    rows=[];wanted=set()
    for old,new,scope in MAPPING:
        t0=original.get('observed_events',{}).get(old,{}).get('t')
        t1=progress.get('milestones',{}).get(new,{}).get('first_confirmed_t')
        for t in (t0,t1):
            if t is not None:wanted.add(float(t))
        rows.append(dict(original_event=old,progress_milestone=new,original_t_s=t0,progress_t_s=t1,
            progress_minus_original_s=t1-t0 if t0 is not None and t1 is not None else None,criterion_comparison=scope))
    fields=['t','physics_step','finger_contact_N','finger_joint_positions_m','cup_in_hand_position_m','source_clearance_m','depth_m','xy_error_target_m','tilt_deg','yaw_error_deg','target_bottom_gap_m','target_bottom_support_N','target_region_contains_object','input_geometry_overlap_observed_m','gripper_object_clearance_m']
    samples=[]
    with gzip.open(episode/'physics_records.jsonl.gz','rt') as stream:
        for line in stream:
            row=json.loads(line)
            if any(abs(row['t']-t)<1e-9 for t in wanted):samples.append({key:row.get(key) for key in fields})
    value=dict(schema='labsim.Progress_v1.original_scorer_comparison.v1',episode_id=original['episode_id'],original_result=str(episode/'result.json'),progress_summary=str(progress_directory/'progress_summary.json'),
        original_task_success=original.get('task_success'),progress_complete=progress.get('progress_complete'),comparisons=rows,actual_samples_at_different_confirmation_times=samples,
        original_labels_modified=False,progress_online_offline_equality_is_a_separate_check=True,
        interpretation='Timing differences are explicit, not automatic changes to original grades. Event names alone are not semantic equivalence.')
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(value,indent=2)+'\n');return value

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('episode',type=Path);p.add_argument('progress_directory',type=Path);p.add_argument('--output',required=True,type=Path);a=p.parse_args();v=compare(a.episode,a.progress_directory,a.output);print(a.output)
