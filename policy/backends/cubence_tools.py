"""Generic bounded robot tools and a genuine image/robot-state GPT closed loop.

There are no grasp, extraction, alignment or insertion macros. The policy cannot
access the teacher, object ground truth, privileged scorer state or debug camera
metadata. Physics advances only inside a validated synchronous robot action.
"""
from __future__ import annotations

import base64
import copy
import io
import json
import math
from pathlib import Path
import time
from typing import Any
import uuid

from .cubence import BudgetExceeded, CubenceClient, ProviderError, canonical_hash, response_text, response_tools


PUBLIC_FIELDS = frozenset(("episode_id", "observation_id", "step_index", "simulation_time", "simulation_time_s",
    "joint_positions", "joint_velocities", "TCPpose", "tcp_pose", "gripper_opening_m", "gripper_effort_limit_N",
    "task_language", "source_slot_id", "target_seat_id", "camera_meta", "camera_calibration", "images",
    "finger_contact_forces_N", "finger_contact_N"))
CAMERA_FIELDS = frozenset(("name", "physical_parent", "mounting", "local_pose_position_m", "local_pose_quaternion_wxyz",
    "world_pose_position_m", "world_pose_quaternion_wxyz", "world_from_camera_usd", "camera_cv_from_world",
    "extrinsic_translation_unit", "meters_per_stage_unit", "optical_conventions", "intrinsic_matrix_native",
    "intrinsic_matrix_policy_256", "resolution_wh", "channels", "focal_length_cm", "horizontal_aperture_mm",
    "vertical_aperture_mm", "requested_fps", "sensor_rendering_time_s", "sensor_timestamp_clock", "source"))


def json_safe(value):
    if hasattr(value, "tolist"):
        return value.tolist()
    if isinstance(value, dict):
        return {str(k):json_safe(v) for k,v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(x) for x in value]
    return value


def public_observation(observation: dict) -> dict:
    result={k:copy.deepcopy(v) for k,v in observation.items() if k in PUBLIC_FIELDS}
    if 'images' in result:
        result['images']={k:v for k,v in result['images'].items() if k in ('side_camera','wrist_camera')}
    for name in ('TCPpose','tcp_pose'):
        if name in result:
            result[name]={k:v for k,v in result[name].items() if k in ('position_m','quaternion_wxyz')}
    for name in ("camera_meta", "camera_calibration"):
        if name in result:
            result[name]={cam:{k:v for k,v in meta.items() if k in CAMERA_FIELDS} for cam,meta in result[name].items() if cam in ('side_camera','wrist_camera')}
            for metadata in result[name].values():
                conventions=metadata.get('optical_conventions')
                if isinstance(conventions,dict):
                    metadata['optical_conventions']={k:v for k,v in conventions.items() if k in ('usd','opencv','world','quaternion') and isinstance(v,str)}
    for name in ("joint_positions", "joint_velocities"):
        if name in result:
            values=json_safe(result[name])
            if len(values)!=9 or not all(math.isfinite(float(x)) for x in values):
                raise ProviderError("PHYSICS_INVALID_NONFINITE_ROBOT_STATE")
    return result


def _identity_schema():
    return {"episode_id":{"type":"string"}, "observation_id":{"type":"string"}}


def tool_definitions() -> list[dict]:
    def tool(name, description, properties, required):
        return dict(type="function", name=name, description=description, strict=True,
            parameters=dict(type="object", properties=properties, required=required, additionalProperties=False))
    identity=_identity_schema()
    return [
        tool("observe", "Read the current synchronized side/wrist images and robot state. Physics remains paused.", {}, []),
        tool("move_ee", "Execute one bounded generic Cartesian command via IK/interpolation. No task macro. Units metres/radians, world frame or TCP delta, quaternion wxyz.",
            dict(**identity, action_id={"type":"string"}, mode={"type":"string","enum":["ee_pose","ee_delta"]},
                values={"type":"array","items":{"type":"number"}}, frame={"type":"string","enum":["world","tcp"]},
                duration_s={"type":"number"}), [*identity,"action_id","mode","values","frame","duration_s"]),
        tool("gripper", "Symmetric two-finger total opening in metres and explicit per-finger force cap in newtons; arm holds its current pose. No object binding.",
            dict(**identity, action_id={"type":"string"}, opening_m={"type":"number"}, effort_limit_N={"type":"number"}, duration_s={"type":"number"}),
            [*identity,"action_id","opening_m","effort_limit_N","duration_s"]),
        tool("wait", "Advance a bounded simulation interval while holding the current robot and gripper command.",
            dict(**identity, action_id={"type":"string"}, duration_s={"type":"number"}), [*identity,"action_id","duration_s"]),
        tool("finish", "Request independent scoring and finish. This cannot assert success or bypass release/retreat/stability checks.",
            dict(**identity, reason={"type":"string"}), [*identity,"reason"]),
    ]


SYSTEM_PROMPT = """You directly control a simulated Franka for the task in task_language.
Use only the synchronized side and wrist RGB, robot joint/TCP state, provided camera calibration, task text and tool receipts.
There is no object-pose oracle and no expert motion primitive. Infer locations from images and calibration. Do not request debug or ground truth.
All translations are metres; rotations radians; ee_pose quaternion order wxyz. Gripper opening is total finger separation, not each finger's position.
Call one tool at a time. Every motion needs the current episode_id, observation_id, and a unique action_id. A receipt acknowledges executed motion; never replay an acknowledged action.
Use larger bounded moves in free space and small, slower actions near contact. Model requests pause simulation; duration_s advances simulation only during tool execution.
Follow the full task: approach the designated light cuvette in the white rack, physical grasp, extraction, transport, internal-seat insertion, support transfer, symmetric release, retreat, then at least3seconds stable observation.
Do not declare success from your own assessment: finish only requests the same independent physical scorer used for every backend.
Avoid pushing after stalled insertion, dropping, collisions, and joint limits. If unsure, observe. You may reduce the gripper force cap during an image/state-confirmed support handoff, but cannot change physics or task thresholds.
Return a tool call rather than a long explanation. No task-specific macro, teacher takeover or hidden plan execution is available.
"""


class GenericRobotTools:
    def __init__(self, environment, limits: dict):
        self.env=environment
        self.limits=dict(limits)
        self.last_observation=None
        self.receipts={}
        self.commanded_opening_m=None
        self.commanded_effort_N=None

    def observe(self):
        self.last_observation=public_observation(self.env.observe())
        if not self.last_observation.get("episode_id") or not self.last_observation.get("observation_id"):
            raise ProviderError("PROTOCOL_OBSERVATION_ID_MISSING")
        if self.commanded_opening_m is None:
            self.commanded_opening_m=float(self.last_observation.get("gripper_opening_m",sum(json_safe(self.last_observation["joint_positions"])[-2:])))
        if self.commanded_effort_N is None:
            self.commanded_effort_N=float(self.last_observation.get("gripper_effort_limit_N",self.limits["gripper_effort_limit_N"]))
        return copy.deepcopy(self.last_observation)

    def _validate_identity(self, arguments):
        if self.last_observation is None:self.observe()
        for name in ("episode_id", "observation_id"):
            if arguments.get(name) != self.last_observation[name]:
                raise ProviderError("PROTOCOL_STALE_"+name.upper())

    def _duration(self, value):
        d=float(value)
        if not math.isfinite(d) or d<float(self.limits["min_duration_s"])-1e-9 or d>float(self.limits["max_duration_s"])+1e-9:
            raise ProviderError("PROTOCOL_ACTION_DURATION_LIMIT")
        hz=int(self.limits["control_hz"])
        # Quantization is declared in the receipt, never silently adds unbounded time.
        ticks=round(d*hz)
        if ticks<1:raise ProviderError("PROTOCOL_ACTION_DURATION_LIMIT")
        return ticks/hz

    def _pose(self):
        pose=self.last_observation.get("TCPpose", self.last_observation.get("tcp_pose"))
        if not isinstance(pose, dict):raise ProviderError("PROTOCOL_TCP_POSE_UNAVAILABLE")
        return [float(x) for x in pose["position_m"]], [float(x) for x in pose["quaternion_wxyz"]]

    def execute(self, name: str, arguments: dict) -> dict:
        if name=="observe":
            obs=self.observe()
            return {"status":"OBSERVED", "episode_id":obs["episode_id"], "observation_id":obs["observation_id"]}
        if name not in {"move_ee", "gripper", "wait", "finish"}:
            raise ProviderError("PROTOCOL_UNKNOWN_TOOL")
        # Idempotency check comes before stale-observation rejection: an acknowledged
        # action can be queried again without moving the robot a second time.
        action_id=arguments.get("action_id")
        if name!="finish":
            if not isinstance(action_id,str) or not 1<=len(action_id)<=128:
                raise ProviderError("PROTOCOL_ACTION_ID_MISSING")
            prior=self.env.receipt(action_id)
            if prior is not None:
                expected=self.receipts.get(action_id)
                if expected is None or expected[0]!=canonical_hash({"name":name,"arguments":arguments}):
                    raise ProviderError("PROTOCOL_ACTION_ID_REUSED")
                return {**json_safe(prior),"idempotent_replay":True}
        self._validate_identity(arguments)
        if name=="finish":
            result=self.env.finish(reason="POLICY_FINISH_REQUEST")
            return dict(status="FINISH_REQUESTED", result=json_safe(result))
        duration=self._duration(arguments.get("duration_s"))
        p,q=self._pose()
        # Hold the previous requested command, not the measured opening: resetting
        # the target to the contact-deformed opening would unintentionally unload
        # the grasp. Likewise a move/wait must not silently restore8N after unload.
        opening=self.commanded_opening_m
        effort=self.commanded_effort_N
        action=dict(action_id=action_id,episode_id=arguments["episode_id"],observation_id=arguments["observation_id"],
            type="ee_delta", values=[0.]*6, frame="world", duration_s=duration,
            gripper_opening_m=opening, gripper_effort_limit_N=effort)
        if name=="move_ee":
            mode=arguments.get("mode");v=arguments.get("values")
            if mode not in {"ee_pose","ee_delta"} or not isinstance(v,list) or len(v)!=(7 if mode=="ee_pose" else 6):
                raise ProviderError("PROTOCOL_ACTION_SHAPE")
            if not all(isinstance(x,(int,float)) and math.isfinite(x) for x in v):
                raise ProviderError("PROTOCOL_NONFINITE_ACTION")
            if arguments.get("frame") not in {"world","tcp"} or mode=="ee_pose" and arguments.get("frame")!="world":
                raise ProviderError("PROTOCOL_ACTION_FRAME")
            delta=[v[i]-p[i] for i in range(3)] if mode=="ee_pose" else v[:3]
            distance=math.sqrt(sum(x*x for x in delta))
            if distance>float(self.limits["max_translation_m"])+1e-9 or distance/duration>float(self.limits["max_linear_speed_m_s"])+1e-9:
                raise ProviderError("PROTOCOL_TRANSLATION_SPEED_LIMIT")
            if mode=="ee_delta":angle=math.sqrt(sum(x*x for x in v[3:]))
            else:
                norm=math.sqrt(sum(x*x for x in v[3:]));normq=math.sqrt(sum(x*x for x in q))
                if abs(norm-1)>1e-3:raise ProviderError("PROTOCOL_QUATERNION_NOT_UNIT")
                angle=2*math.acos(min(1.,abs(sum(v[i+3]*q[i] for i in range(4))/(norm*normq))))
            if angle>float(self.limits["max_rotation_rad"])+1e-9 or angle/duration>float(self.limits["max_angular_speed_rad_s"])+1e-9:
                raise ProviderError("PROTOCOL_ROTATION_SPEED_LIMIT")
            action.update(type=mode,values=v,frame=arguments["frame"])
        elif name=="gripper":
            opening=float(arguments.get("opening_m"));effort=float(arguments.get("effort_limit_N"))
            if not math.isfinite(opening) or not 0<=opening<=float(self.limits["max_gripper_opening_m"]):
                raise ProviderError("PROTOCOL_GRIPPER_OPENING_LIMIT")
            if not math.isfinite(effort) or not 0<=effort<=float(self.limits["gripper_effort_limit_N"]):
                raise ProviderError("PROTOCOL_GRIPPER_EFFORT_LIMIT")
            action.update(gripper_opening_m=opening,gripper_effort_limit_N=effort)
        identity_hash=canonical_hash({"name":name,"arguments":arguments})
        # Record intent before calling. An exception must query the receipt before
        # any caller considers a retry; this adapter never blindly replays motion.
        self.receipts[action_id]=(identity_hash,None)
        try:
            receipt=self.env.execute(action)
        except Exception:
            receipt=self.env.receipt(action_id)
            if receipt is None:raise ProviderError("ACTION_EXECUTION_UNKNOWN_CHECK_RECEIPT") from None
        self.receipts[action_id]=(identity_hash,json_safe(receipt))
        self.commanded_opening_m=action["gripper_opening_m"]
        self.commanded_effort_N=action["gripper_effort_limit_N"]
        self.observe()
        return {**json_safe(receipt),"requested_duration_s":arguments["duration_s"],"executed_duration_s":duration}


def observation_content(observation: dict) -> list[dict]:
    from PIL import Image
    obs=public_observation(observation)
    images=obs.pop("images",{})
    content=[dict(type="input_text",text=json.dumps(json_safe(obs),ensure_ascii=False,allow_nan=False))]
    for name in ("side_camera","wrist_camera"):
        if name not in images:raise ProviderError("PROTOCOL_REQUIRED_RGB_MISSING")
        value=images[name]
        image=Image.fromarray(value).convert("RGB")
        image.thumbnail((640,480))
        buffer=io.BytesIO();image.save(buffer,format="JPEG",quality=80)
        content.extend([dict(type="input_text",text="Synchronized RGB: "+name),dict(type="input_image",image_url="data:image/jpeg;base64,"+base64.b64encode(buffer.getvalue()).decode(),detail="low")])
    return content


def run_episode(environment, client: CubenceClient, output: str | Path, *, max_calls=160, prompt=SYSTEM_PROMPT) -> dict:
    """Run policy on an already-reset facade. The caller owns reset and close."""
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    cfg=client.cfg;tools=GenericRobotTools(environment,cfg["action_limits"])
    schema=tool_definitions()
    frozen=dict(schema="labsim.gpt_controller.v1",provider_config=cfg,prompt=prompt,tool_schema=schema,
        object_truth_used=False,teacher_used=False,physics_paused_during_inference=True,
        action_meaning="generic EE pose/delta, symmetric gripper or wait; facade performs only IK, interpolation and bounds")
    (output/"controller.json").write_text(json.dumps(frozen,indent=2,ensure_ascii=False)+"\n")
    controller_sha=canonical_hash(frozen)
    started=time.monotonic();calls=0;errors=0;history=[];termination="POLICY_BUDGET";failure=None
    trace=(output/"policy_trace.jsonl").open("x")
    try:
        while calls<int(max_calls):
            status=environment.status()
            if status.get("terminated") or status.get("ended"):
                termination="ENVIRONMENT_TERMINATED";break
            if time.monotonic()-started>float(cfg["episode_timeout_s"]):
                termination="POLICY_EPISODE_WALL_TIMEOUT";failure="PROVIDER_TIMEOUT";break
            obs=tools.observe()
            contents=observation_content(obs)
            # Fresh images every decision; earlier turns preserve only generic
            # tool calls/receipts, never repeated base64 images or privileged state.
            recent_turns=history[-max(1,int(cfg.get("max_context_messages",12))//2):]
            conversation=[item for turn in recent_turns for item in turn]
            input_items=[dict(role="user",content="Task: "+str(obs.get("task_language","")))]+conversation+[dict(role="user",content=contents)]
            before=float(obs.get("simulation_time",obs.get("simulation_time_s",0.)))
            try:
                response,meta=client.responses(input_items,instructions=prompt+"\nAction limits: "+json.dumps(cfg["action_limits"]),tools=schema,label="policy:"+str(obs["episode_id"]),deadline_monotonic=started+float(cfg["episode_timeout_s"]))
                calls+=1
                after=tools.observe()
                if abs(float(after.get("simulation_time",after.get("simulation_time_s",0.)))-before)>1e-9:
                    raise ProviderError("PHYSICS_ADVANCED_DURING_INFERENCE")
                function_calls=response_tools(response)
                if not function_calls:raise ProviderError("PROTOCOL_TOOL_CALL_REQUIRED")
                call=function_calls[0]
                if not call.get("call_id"):raise ProviderError("PROTOCOL_CALL_ID_MISSING")
                try:
                    receipt=tools.execute(call["name"],call["arguments"])
                except ProviderError as error:
                    errors+=1
                    receipt={"status":"REJECTED","error":error.code,"episode_id":obs["episode_id"],"observation_id":obs["observation_id"],"physics_advanced":False}
                # Preserve complete response-item groups in memory. Some reasoning
                # models require the reasoning item that accompanies a function call.
                # The trace stores only the observable action, never hidden reasoning.
                history.append(response.get("output",[])+[dict(type="function_call_output",call_id=call["call_id"],output=json.dumps(receipt,allow_nan=False))])
                record=dict(event="decision",episode_id=obs["episode_id"],observation_id=obs["observation_id"],simulation_time_s=before,
                    requested_model=cfg["model"],returned_model=response.get("model"),request_id=meta["request_id"],response_id=response.get("id"),
                    inference_wall_seconds=meta["wall_seconds"],usage=response.get("usage"),tool_call=call,receipt=receipt,controller_sha256=controller_sha,
                    image_channels=["side_camera","wrist_camera"],truth_exposed=False)
                trace.write(json.dumps(json_safe(record),ensure_ascii=False,allow_nan=False)+"\n");trace.flush()
                if call["name"]=="finish" and receipt.get("status")!="REJECTED":termination="POLICY_FINISH_REQUEST";break
                if errors>=8:termination="PROTOCOL_ERROR_LIMIT";failure="PROTOCOL_ERROR";break
            except ProviderError as error:
                failure="PROVIDER_FAILURE" if not error.code.startswith("PROTOCOL") else "PROTOCOL_ERROR"
                termination=error.code
                trace.write(json.dumps(dict(event="error",code=error.code,http_status=error.status,episode_id=obs["episode_id"],observation_id=obs["observation_id"],simulation_time_s=before))+"\n");trace.flush()
                break
        result=environment.finish(reason=termination)
        summary=dict(schema="labsim.cubence_episode.v1",controller_sha256=controller_sha,provider=cfg["provider"],requested_model=cfg["model"],
            endpoint=cfg["endpoint"],api_decisions=calls,protocol_rejections=errors,wall_seconds=time.monotonic()-started,
            termination_reason=termination,backend_failure_type=failure,task_result=json_safe(result),budget=client.ledger.summary(),
            object_truth_used=False,teacher_used=False,physics_paused_during_inference=True)
        (output/"summary.json").write_text(json.dumps(summary,indent=2,ensure_ascii=False,allow_nan=False)+"\n")
        return summary
    finally:
        trace.close()
