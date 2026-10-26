"""Project_v1_1 receipt adapter over the existing bounded Cubence provider.

There is no HTTP client, credential store, task macro, or privileged observation
path here. The injected runner reuses the existing provider and budget ledger.
Historical Project_v1 GenericRobotTools remain the default of the shared runner.
"""
from __future__ import annotations

import copy
import hashlib
import math
from pathlib import Path

from .cubence import ProviderError
from .cubence_tools import (GenericRobotTools, SYSTEM_PROMPT as PREVIOUS_PROMPT,
                            backend_failure_class, json_safe,
                            run_episode as _run_episode)


SYSTEM_PROMPT = PREVIOUS_PROMPT + """
Project_v1_1 execution contract:
accepted means the command passed preflight, not that motion occurred or the target was reached.
execution_finished means its execution interval ended. target_reached is a separate measurement of the actual endpoint.
completed is a compatibility alias for interval completion; never interpret it alone as reaching the requested pose.
A CONTROL_PLAN_REJECTED receipt means a continuous local IK path could not be verified. Rejection executes zero ticks and leaves the current observation valid. Reduce the requested move or choose another visually supported direction; never assume it moved. Do not repeatedly send the same rejected path with a new ID.
Read requested versus actual endpoint, final and maximum tracking errors, executed duration/ticks, stop_reason, safety_stopped and partial_execution.
If an action partially executed or safety stopped, do not replay it as though nothing moved. Use its successor observation and actual receipt; the backend may end the episode to preserve the safety evidence.
An execution_finished command with target_reached=false is not a successful move. Observe the fresh images/state before deciding on a smaller correction.
The force cap is an upper limit, not a measured contact force. move and wait preserve the previous gripper request; only the explicit gripper tool changes opening/effort. Use the public bilateral finger contact readings to assess contact, and fresh images to assess retention.
Both cameras are synchronized at each decision. The side camera covers the rack, arm and instrument; the wrist camera moves with the hand. Use their actual supplied mounting, intrinsics, extrinsics, image transformation and timestamps. Do not assume an old wrist mounting or invent object poses from a task ID.
Use the static robot calibration in task_language to distinguish the TCP frame from the panda_hand/palm frame when interpreting images and camera mounting. Apply the stated parent/child transform and quaternion convention; do not assume the frames share an origin or orientation. The frame-origin offset is robot geometry, not a complete hand/finger collision envelope or an obstacle-pose oracle.
Plan clearance for the whole hand and the held vessel, not only the TCP or the vessel bottom. After extraction, inspect the side image and lift sufficiently above intervening rack walls and instrument housing before lateral transport. Leaving the source slot does not prove that the fingers, palm or arm clear the instrument. Use fresh images to choose a clear route and to check clearance again before descent; no obstacle coordinates or safe-height oracle are provided.
If an intervening housing edge or whole-hand clearance cannot be judged from the current images, obtain fresh dual views and establish visually supported clearance before horizontal transport. Do not continue laterally solely because the TCP or vessel appears outside the source slot; if clearance remains uncertain, observe or stop rather than assume a safe route.
Perspective alignment: overlap or centering in one image does not establish coaxial alignment. Cross-check the vessel long axis and the intended aperture in both views using the supplied calibration; do not assume equal image pixels imply equal world positions.
Once visually near the seat or uncertain contact, command insertion/descent at no more than0.001m/s. Split it into short bounded increments and inspect fresh dual-view images, robot state and bilateral finger contact after each increment. This instruction does not add a hidden contact detector or automatic insertion macro.
If the hand descends while the vessel moves upward relative to the fingers, or one side of finger contact is lost, stop descending. Use only a visually supported safe backoff and realignment before trying again; do not keep pressing with the same downward command or release to bypass the obstruction.
Do not open the fingers before sufficient nominal loading depth and actual support have been established from the allowed observations. Compare the visible exposed vessel length with the static task goal while accounting for perspective and occlusion. A TCP endpoint reached, a tool interval finished, or a vessel tip or mouth overlapping a seat rim is not evidence of bottom support. If depth or support remains uncertain, stop and reassess rather than opening early.
These controls remain generic move, gripper, wait, observe and finish. No expert stage controller, object ground truth or hidden recovery action is available.
"""


_RECEIPT_FIELDS = frozenset((
    'action_id', 'model_action_id', 'execution_action_id', 'episode_id', 'observation_id',
    'status', 'accepted', 'execution_finished', 'target_reached', 'safety_stopped',
    'completed', 'completed_semantics', 'partial_execution', 'executed_control_ticks',
    'executed_physics_steps', 'incomplete_control_interval',
    'requested_duration_s', 'quantized_requested_duration_s', 'executed_duration_s',
    'executed_duration_source', 'simulation_time_before', 'simulation_time_after',
    'observation_id_after', 'requested_start_TCP', 'requested_target_TCP',
    'actual_endpoint_TCP', 'TCPpose', 'maximum_position_tracking_error_m',
    'maximum_orientation_tracking_error_rad', 'final_position_error_m',
    'final_orientation_error_rad', 'endpoint_tolerances', 'stop_reason',
    'successor_observation_available', 'actual_endpoint_valid',
    'tracking_error_coverage_complete', 'tracking_error_sampling', 'target_reached_scope',
    'requested_gripper_opening_m', 'applied_gripper_opening_m',
    'requested_effort_limit_N', 'applied_effort_limit_N', 'stop_domain',
    'terminated', 'gripper_opening_m', 'wall_seconds', 'idempotent_replay',
    'executor_error_type', 'error_type'))


def _public_receipt(receipt):
    value={key:copy.deepcopy(item) for key,item in receipt.items() if key in _RECEIPT_FIELDS}
    plan=receipt.get('plan')
    if isinstance(plan,dict):
        value['plan']={key:item for key,item in plan.items() if key in (
            'planned_ticks','requested_ticks','wall_seconds','maximum_FK_position_error_m',
            'maximum_FK_orientation_error_rad','maximum_joint_step_rad','scope')}
    failure=receipt.get('planning_failure')
    if isinstance(failure,dict):
        value['planning_failure']={key:item for key,item in failure.items()
            if key in ('reference_tick','reason','robot_state_only')}
        detail=failure.get('IK')
        if isinstance(detail,dict):
            value['planning_failure']['IK']={key:item for key,item in detail.items() if key in (
                'success','position_error_m','orientation_error_rad','iterations','fk_evaluations','reason')}
    return json_safe(value)


class ProjectV11RobotTools(GenericRobotTools):
    """Keep ID/idempotency validation, and interpret the new measured receipts."""

    @staticmethod
    def controller_metadata():
        return dict(version='Project_v1_1',tools_class='ProjectV11RobotTools',
            prompt_version='Project_v1_1.public_tools.v4',
            receipt_contract='accepted/execution_finished/target_reached/safety_stopped/partial_execution',
            implementation_sha256={Path(__file__).name:hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
            observation_scope='Same public RGB/robot/calibration/tactile whitelist as Project_v1; no object truth')

    @staticmethod
    def failure_class(code):
        if code.startswith('EXECUTOR_'):
            return 'EXECUTOR_FAILURE'
        if code.startswith('SAFETY_'):
            return 'SAFETY_FAILURE'
        if code.startswith('SIMULATION_') or code.startswith('PHYSICS_INVALID'):
            return 'SIMULATION_FAILURE'
        return backend_failure_class(code)

    def rejection_receipt(self,error,base,arguments):
        # A reused/stale ID may resolve to an earlier successful receipt. It is
        # evidence about that earlier command, not about this rejected request.
        native=self.execution_receipt(arguments) if error.code=='PROTOCOL_CONTROL_PLAN_REJECTED' else None
        result=dict(base)
        if native is not None:
            result.update(_public_receipt(native))
        else:
            now=self.last_observation.get('simulation_time',self.last_observation.get('simulation_time_s'))
            result.update(simulation_time_before=now,simulation_time_after=now,
                          observation_id_after=self.last_observation['observation_id'])
        result.update(status='REJECTED',error=error.code,details=error.details,
            accepted=False,execution_finished=True,target_reached=False,safety_stopped=False,
            partial_execution=False,physics_advanced=False,executed_control_ticks=0,
            executed_physics_steps=0,incomplete_control_interval=False,
            executed_duration_s=0.,model_action_id=arguments.get('action_id'),
            execution_action_id=self.execution_id_for(arguments))
        return result

    def execute(self,name,arguments):
        # Initialization reads public state only. Preserve these commands across
        # rejected gripper/EE plans, even if the compatibility parent tentatively
        # acknowledges completed=true (which means only interval completion).
        if self.last_observation is None:
            self.observe()
        opening,effort=self.commanded_opening_m,self.commanded_effort_N
        before=self.last_observation.get('simulation_time',self.last_observation.get('simulation_time_s'))
        try:
            receipt=super().execute(name,arguments)
        except ProviderError as error:
            if error.code not in ('PHYSICS_ACTION_EXECUTION_FAILURE','ACTION_EXECUTION_UNKNOWN_CHECK_RECEIPT'):
                raise
            native=self.execution_receipt(arguments) if isinstance(arguments,dict) else None
            if native is None:
                raise
            receipt=self._timed_receipt(native,arguments)
        if name in ('observe','finish'):
            return receipt
        fields=('accepted','execution_finished','target_reached','safety_stopped')
        ticks=receipt.get('executed_control_ticks')
        valid=(all(isinstance(receipt.get(key),bool) for key in fields)
            and isinstance(ticks,int) and not isinstance(ticks,bool) and ticks>=0
            and isinstance(receipt.get('partial_execution'),bool))
        if not valid:
            raise ProviderError('EXECUTOR_RECEIPT_CONTRACT_ERROR')
        public=_public_receipt(receipt)
        if not receipt['accepted']:
            self.commanded_opening_m,self.commanded_effort_N=opening,effort
            if ticks or receipt['partial_execution'] or receipt['safety_stopped']:
                raise ProviderError('EXECUTOR_REJECTION_EXECUTED_MOTION',details=public)
            elapsed=receipt.get('executed_duration_s')
            if not isinstance(elapsed,(int,float)) or not math.isfinite(elapsed) or abs(elapsed)>1e-9:
                raise ProviderError('EXECUTOR_REJECTION_ADVANCED_TIME',details=public)
            after=self.env.status().get('simulation_time')
            if after is None:
                observed=self.env.observe()
                after=observed.get('simulation_time',observed.get('simulation_time_s'))
            if not isinstance(before,(int,float)) or not isinstance(after,(int,float)) or abs(after-before)>1e-9:
                raise ProviderError('EXECUTOR_REJECTION_ADVANCED_TIME',details=public)
            raise ProviderError('PROTOCOL_CONTROL_PLAN_REJECTED',details=public)
        # Partial execution is never automatically retried. The original native
        # receipt remains queryable under its episode-bound execution ID.
        reason=str(receipt.get('stop_reason',''))
        if not receipt['execution_finished']:
            raise ProviderError('EXECUTOR_INTERVAL_UNFINISHED',details=public)
        if receipt.get('executor_error_type') or receipt.get('error_type') or reason.startswith('EXECUTOR'):
            raise ProviderError('EXECUTOR_ACTION_PARTIAL' if receipt['partial_execution'] else 'EXECUTOR_ACTION_STOPPED',details=public)
        if reason!='SIMULATION_TIMEOUT' and reason.startswith(('NONFINITE','SIMULATION','PHYSICS_INVALID','OBJECT_POSE_JUMP')):
            raise ProviderError('SIMULATION_STATE_STOPPED',details=public)
        if receipt['safety_stopped']:
            # Independent task verdicts already ended by grasp/drop/timeout are
            # preserved by the environment; do not relabel them as solver faults.
            task_end=bool(self.env.status().get('terminated'))
            ordinary_task_end=reason.startswith(('GRASP_SLIP','DROPPED','TIMEOUT','SIMULATION_TIMEOUT',
                'POLICY_FINISH','TASK_','SUCCESS','UNSTABLE_AFTER_RELEASE'))
            if not (task_end and ordinary_task_end):
                raise ProviderError('SAFETY_ACTION_STOPPED',details=public)
        if receipt['partial_execution'] and not self.env.status().get('terminated'):
            raise ProviderError('EXECUTOR_ACTION_PARTIAL',details=public)
        if not receipt['target_reached'] and not receipt['safety_stopped']:
            public['status']='TARGET_NOT_REACHED'
        return public


def run_episode(environment,client,output,*,max_calls=160,prompt=SYSTEM_PROMPT):
    """Use the existing client/ledger with Project_v1_1 measured tool semantics."""
    return _run_episode(environment,client,output,max_calls=max_calls,prompt=prompt,
                        tools_class=ProjectV11RobotTools)
