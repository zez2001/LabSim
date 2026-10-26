"""Generic bounded robot tools and a genuine image/robot-state GPT closed loop.

There are no grasp, extraction, alignment or insertion macros. The policy cannot
access the teacher, object ground truth, privileged scorer state or debug camera
metadata. Physics advances only inside a validated synchronous robot action.
"""
from __future__ import annotations

import base64
import copy
import hashlib
import io
import json
import math
from pathlib import Path
import time

from .cubence import CubenceClient, ProviderError, canonical_hash, response_tools


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


def finite_number(value, code):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):
        raise ProviderError(code)
    return float(value)


def backend_failure_class(code):
    """Backend errors cannot be admitted as valid physical task failures."""
    if code in ('COST_BUDGET_EXHAUSTED','REQUEST_BUDGET_EXHAUSTED','POLICY_BUDGET'):
        return None
    if code.startswith('PROTOCOL') or code=='LOCAL_CONTEXT_TOKEN_BOUND_EXCEEDED':
        return 'INPUT_CONTRACT_ERROR'
    if code.startswith('PHYSICS') or code=='ACTION_EXECUTION_UNKNOWN_CHECK_RECEIPT':
        return 'PHYSICS_INVALID'
    return 'MODEL_SERVICE_ERROR'


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
            try:valid=len(values)==9 and all(math.isfinite(float(x)) for x in values)
            except (TypeError,ValueError,OverflowError):valid=False
            if not valid:
                raise ProviderError("PHYSICS_INVALID_NONFINITE_ROBOT_STATE")
    return result


def compact_camera_metadata(metadata: dict) -> dict:
    """GPT transport view; complete public calibration stays in API and H5.

    Keep one CV extrinsic, the native K, camera pose/mount and frame time. Drop
    duplicate USD matrices, optical prose, lens derivations and source narratives.
    """
    fields=('name','physical_parent','local_pose_position_m','local_pose_quaternion_wxyz',
        'world_pose_position_m','world_pose_quaternion_wxyz','camera_cv_from_world',
        'intrinsic_matrix_native','resolution_wh','sensor_rendering_time_s')
    result={key:json_safe(metadata[key]) for key in fields if key in metadata}
    result['frames']='world metres Z-up; camera CV x-right y-down z-forward; quaternion wxyz'
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
Translation and rotation limits apply to the Euclidean vector norm. For example, delta[.02,.02,0] has length.028284m and needs at least1.415s at.02m/s. A longer duration cannot make a vector longer than.04m legal; split it into smaller commands. Read numeric rejection details and correct the next command.
Follow the full task: approach the designated light cuvette in the white rack, physical grasp, extraction, transport, internal-seat insertion, support transfer, symmetric release, retreat, then at least3seconds stable observation.
Public fixed-scene task prior: the light cuvette in slot A1 is at the rack corner closest to the robot. The blue cuvette in opposite corner F6 is a distractor to leave in place. The selected light cuvette's nominal outer dimensions are10x10x67.5mm. These are nominal task facts; infer current poses from the images and calibration.
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
        previous_episode=self.last_observation.get('episode_id') if self.last_observation else None
        self.last_observation=public_observation(self.env.observe())
        if not self.last_observation.get("episode_id") or not self.last_observation.get("observation_id"):
            raise ProviderError("PROTOCOL_OBSERVATION_ID_MISSING")
        if previous_episode is not None and previous_episode!=self.last_observation['episode_id']:
            self.commanded_opening_m=None
            self.commanded_effort_N=None
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
        d=finite_number(value,"PROTOCOL_ACTION_DURATION_LIMIT")
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
        try:
            p=[float(x) for x in pose["position_m"]];q=[float(x) for x in pose["quaternion_wxyz"]]
        except (TypeError,ValueError,KeyError):
            raise ProviderError("PHYSICS_INVALID_TCP_POSE") from None
        if len(p)!=3 or len(q)!=4 or not all(math.isfinite(x) for x in p+q) or sum(x*x for x in q)<.25:
            raise ProviderError("PHYSICS_INVALID_TCP_POSE")
        return p,q

    @staticmethod
    def execution_id(episode_id,model_action_id):
        payload=json.dumps([episode_id,model_action_id],ensure_ascii=False,separators=(',',':'))
        return 'gpt:'+hashlib.sha256(payload.encode()).hexdigest()

    def execution_id_for(self,arguments):
        if not isinstance(arguments,dict):return None
        model_id=arguments.get('action_id')
        if not isinstance(model_id,str) or not 1<=len(model_id)<=128:return None
        if self.last_observation is None:self.observe()
        current=self.env.status().get('episode_id') or self.last_observation['episode_id']
        if arguments.get('episode_id')!=current:return None
        return self.execution_id(current,model_id)

    def execution_receipt(self,arguments):
        execution_id=self.execution_id_for(arguments)
        return self.env.receipt(execution_id) if execution_id else None

    def _timed_receipt(self,receipt,arguments):
        result=json_safe(receipt)
        actual=None;source='unavailable'
        before=result.get('simulation_time_before');after=result.get('simulation_time_after')
        if isinstance(before,(int,float)) and isinstance(after,(int,float)) and math.isfinite(before) and math.isfinite(after) and after>=before:
            actual=float(after-before);source='simulation_time_after_minus_before'
        else:
            ticks=result.get('executed_control_ticks')
            if isinstance(ticks,int) and not isinstance(ticks,bool) and ticks>=0:
                actual=ticks/float(self.limits['control_hz']);source='executed_control_ticks_divided_by_control_hz'
        result.update(requested_duration_s=arguments['duration_s'],
            quantized_requested_duration_s=self._duration(arguments['duration_s']),
            executed_duration_s=actual,executed_duration_source=source,
            action_id=arguments['action_id'],model_action_id=arguments['action_id'],
            execution_action_id=self.execution_id(arguments['episode_id'],arguments['action_id']))
        return result

    def execute(self, name: str, arguments: dict) -> dict:
        if not isinstance(arguments,dict):raise ProviderError("PROTOCOL_TOOL_ARGUMENTS_NOT_OBJECT")
        if not isinstance(name,str):raise ProviderError("PROTOCOL_UNKNOWN_TOOL")
        if name=="observe":
            obs=self.observe()
            return {"status":"OBSERVED", "episode_id":obs["episode_id"], "observation_id":obs["observation_id"]}
        if name not in {"move_ee", "gripper", "wait", "finish"}:
            raise ProviderError("PROTOCOL_UNKNOWN_TOOL")
        if self.last_observation is None:self.observe()
        current_episode=self.env.status().get('episode_id') or self.last_observation['episode_id']
        if arguments.get('episode_id')!=current_episode:
            raise ProviderError('PROTOCOL_STALE_EPISODE_ID')
        if self.last_observation['episode_id']!=current_episode:self.observe()
        # Idempotency check comes before stale-observation rejection: an acknowledged
        # action can be queried again without moving the robot a second time.
        action_id=arguments.get("action_id")
        execution_action_id=None
        if name!="finish":
            if not isinstance(action_id,str) or not 1<=len(action_id)<=128:
                raise ProviderError("PROTOCOL_ACTION_ID_MISSING")
            execution_action_id=self.execution_id(current_episode,action_id)
            prior=self.env.receipt(execution_action_id)
            if prior is not None:
                expected=self.receipts.get(execution_action_id)
                if expected is None or expected[0]!=canonical_hash({"name":name,"arguments":arguments}):
                    raise ProviderError("PROTOCOL_ACTION_ID_REUSED")
                return {**self._timed_receipt(prior,arguments),"idempotent_replay":True}
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
        action=dict(action_id=execution_action_id,model_action_id=action_id,execution_action_id=execution_action_id,
            episode_id=arguments["episode_id"],observation_id=arguments["observation_id"],
            type="ee_delta", values=[0.]*6, frame="world", duration_s=duration,
            gripper_opening_m=opening, gripper_effort_limit_N=effort)
        if name=="move_ee":
            mode=arguments.get("mode");v=arguments.get("values")
            if mode not in {"ee_pose","ee_delta"} or not isinstance(v,list) or len(v)!=(7 if mode=="ee_pose" else 6):
                raise ProviderError("PROTOCOL_ACTION_SHAPE")
            if not all(not isinstance(x,bool) and isinstance(x,(int,float)) and math.isfinite(x) for x in v):
                raise ProviderError("PROTOCOL_NONFINITE_ACTION")
            if arguments.get("frame") not in {"world","tcp"} or mode=="ee_pose" and arguments.get("frame")!="world":
                raise ProviderError("PROTOCOL_ACTION_FRAME")
            delta=[v[i]-p[i] for i in range(3)] if mode=="ee_pose" else v[:3]
            distance=math.sqrt(sum(x*x for x in delta))
            if distance>float(self.limits["max_translation_m"])+1e-9 or distance/duration>float(self.limits["max_linear_speed_m_s"])+1e-9:
                raise ProviderError("PROTOCOL_TRANSLATION_SPEED_LIMIT",details=dict(translation_norm_m=distance,
                    duration_s=duration,linear_speed_m_s=distance/duration,max_translation_norm_m=float(self.limits['max_translation_m']),
                    max_linear_speed_m_s=float(self.limits['max_linear_speed_m_s']),
                    violations=[name for name,invalid in [('translation_norm',distance>float(self.limits['max_translation_m'])+1e-9),
                        ('linear_speed',distance/duration>float(self.limits['max_linear_speed_m_s'])+1e-9)] if invalid],
                    repair='Reduce the translation vector norm or split the move; choose duration >= norm/max_linear_speed within the duration limit.'))
            if mode=="ee_delta":angle=math.sqrt(sum(x*x for x in v[3:]))
            else:
                norm=math.sqrt(sum(x*x for x in v[3:]));normq=math.sqrt(sum(x*x for x in q))
                if abs(norm-1)>1e-3:raise ProviderError("PROTOCOL_QUATERNION_NOT_UNIT")
                angle=2*math.acos(min(1.,abs(sum(v[i+3]*q[i] for i in range(4))/(norm*normq))))
            if angle>float(self.limits["max_rotation_rad"])+1e-9 or angle/duration>float(self.limits["max_angular_speed_rad_s"])+1e-9:
                raise ProviderError("PROTOCOL_ROTATION_SPEED_LIMIT",details=dict(rotation_norm_rad=angle,duration_s=duration,
                    angular_speed_rad_s=angle/duration,max_rotation_norm_rad=float(self.limits['max_rotation_rad']),
                    max_angular_speed_rad_s=float(self.limits['max_angular_speed_rad_s'])))
            action.update(type=mode,values=v,frame=arguments["frame"])
        elif name=="gripper":
            opening=finite_number(arguments.get("opening_m"),"PROTOCOL_GRIPPER_OPENING_LIMIT")
            effort=finite_number(arguments.get("effort_limit_N"),"PROTOCOL_GRIPPER_EFFORT_LIMIT")
            if not math.isfinite(opening) or not 0<=opening<=float(self.limits["max_gripper_opening_m"]):
                raise ProviderError("PROTOCOL_GRIPPER_OPENING_LIMIT")
            if not math.isfinite(effort) or not 0<=effort<=float(self.limits["gripper_effort_limit_N"]):
                raise ProviderError("PROTOCOL_GRIPPER_EFFORT_LIMIT")
            action.update(gripper_opening_m=opening,gripper_effort_limit_N=effort)
        identity_hash=canonical_hash({"name":name,"arguments":arguments})
        # Record intent before calling. An exception must query the receipt before
        # any caller considers a retry; this adapter never blindly replays motion.
        self.receipts[execution_action_id]=(identity_hash,None)
        try:
            receipt=self.env.execute(action)
        except Exception as error:
            receipt=self.env.receipt(execution_action_id)
            if receipt is None:
                if isinstance(error,(ValueError,TypeError)):raise ProviderError("PROTOCOL_ENVIRONMENT_ACTION_REJECTED") from None
                raise ProviderError("ACTION_EXECUTION_UNKNOWN_CHECK_RECEIPT") from None
        self.receipts[execution_action_id]=(identity_hash,json_safe(receipt))
        if receipt.get('completed') is False or receipt.get('error_type'):
            raise ProviderError("PHYSICS_ACTION_EXECUTION_FAILURE")
        self.commanded_opening_m=action["gripper_opening_m"]
        self.commanded_effort_N=action["gripper_effort_limit_N"]
        self.observe()
        return self._timed_receipt(receipt,arguments)


def observation_content(observation: dict, *, image_config=None) -> list[dict]:
    from PIL import Image
    obs=public_observation(observation)
    images=obs.pop("images",{})
    settings=dict(max_side_px=640,jpeg_quality=80,detail='low',resize_interpolation='lanczos')
    settings.update(image_config or {})
    if not isinstance(settings['max_side_px'],int) or not 64<=settings['max_side_px']<=640 or not isinstance(settings['jpeg_quality'],int) or not 30<=settings['jpeg_quality']<=95 or settings['detail'] not in ('low','high','auto') or settings['resize_interpolation']!='lanczos':
        raise ProviderError('PROTOCOL_INVALID_IMAGE_TRANSFORM_CONFIG')
    content=[];provenance={}
    for name in ("side_camera","wrist_camera"):
        if name not in images:raise ProviderError("PROTOCOL_REQUIRED_RGB_MISSING")
        value=images[name]
        try:image=Image.fromarray(value).convert("RGB")
        except (ValueError,TypeError,AttributeError):raise ProviderError('PROTOCOL_REQUIRED_RGB_INVALID') from None
        original=image.size
        image.thumbnail((settings['max_side_px'],settings['max_side_px']),Image.Resampling.LANCZOS)
        buffer=io.BytesIO();image.save(buffer,format="JPEG",quality=settings['jpeg_quality']);transmitted=buffer.getvalue()
        sx=image.size[0]/original[0];sy=image.size[1]/original[1]
        pixel_transform=[[sx,0.,(sx-1)/2],[0.,sy,(sy-1)/2],[0.,0.,1.]]
        camera=obs.get('camera_meta',obs.get('camera_calibration',{})).get(name,{})
        intrinsic=json_safe(camera.get('intrinsic_matrix_native'))
        transformed=None
        if isinstance(intrinsic,list) and len(intrinsic)==3 and all(isinstance(row,list) and len(row)==3 for row in intrinsic):
            transformed=[[sum(pixel_transform[i][k]*intrinsic[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
        provenance[name]=dict(native_resolution_wh=list(original),transmitted_resolution_wh=list(image.size),scale_xy=[sx,sy],
            native_rgb_sha256=hashlib.sha256(value.tobytes()).hexdigest(),transmitted_jpeg_sha256=hashlib.sha256(transmitted).hexdigest(),
            transmitted_bytes=len(transmitted),jpeg_quality=settings['jpeg_quality'],detail=settings['detail'],
            resize_interpolation='Pillow LANCZOS',crop=None,rotation_deg=0,color_space='RGB',
            transmitted_pixel_from_native_pixel=pixel_transform,intrinsic_matrix_transmitted=transformed,
            pixel_convention='zero-based pixel-centre indices: dst=(src+.5)*scale-.5',native_recording_changed=False)
        content.extend([dict(type="input_text",text="Synchronized RGB: "+name),dict(type="input_image",image_url="data:image/jpeg;base64,"+base64.b64encode(transmitted).decode(),detail=settings['detail'])])
    obs['model_image_transforms']=provenance
    for field in ('camera_meta','camera_calibration'):
        if field in obs:obs[field]={name:compact_camera_metadata(camera) for name,camera in obs[field].items()}
    try:encoded=json.dumps(json_safe(obs),ensure_ascii=False,allow_nan=False)
    except (ValueError,TypeError):raise ProviderError('PHYSICS_INVALID_OBSERVATION') from None
    return [dict(type='input_text',text=encoded)]+content


def save_observation_artifacts(contents,output,decision_index,request_label):
    """Persist exactly the already-encoded wire JPEGs and public state text.

    No image is re-encoded here. The saved public JSON is the first input_text
    passed to the provider; headers, credentials and hidden reasoning are absent.
    """
    try:
        if not isinstance(contents,list) or len(contents)!=5 or contents[0].get('type')!='input_text':
            raise ValueError('Expected public state and two named RGB inputs')
        state_text=contents[0]['text'];state=json.loads(state_text)
        allowed=(PUBLIC_FIELDS-{'images'})|{'model_image_transforms'}
        if not isinstance(state,dict) or set(state)-allowed:raise ValueError('Unexpected public-state field')
        if not isinstance(state.get('episode_id'),str) or not isinstance(state.get('observation_id'),str):raise ValueError('Missing observation identity')
        image_rows=[]
        for index,name in enumerate(('side_camera','wrist_camera')):
            label=contents[1+2*index];block=contents[2+2*index]
            if label!={'type':'input_text','text':'Synchronized RGB: '+name} or block.get('type')!='input_image':
                raise ValueError('Unexpected image ordering or name')
            url=block.get('image_url','');prefix='data:image/jpeg;base64,'
            if not isinstance(url,str) or not url.startswith(prefix):raise ValueError('Only declared JPEG data URLs may be saved')
            jpeg=base64.b64decode(url[len(prefix):],validate=True)
            sha=hashlib.sha256(jpeg).hexdigest()
            if not jpeg.startswith(b'\xff\xd8') or state['model_image_transforms'][name]['transmitted_jpeg_sha256']!=sha:
                raise ValueError('Wire image differs from declared provenance')
            image_rows.append((name,jpeg,sha))
    except (ValueError,TypeError,KeyError,AttributeError) as error:
        raise ProviderError('PROTOCOL_OBSERVATION_ARTIFACT_INVALID') from None
    root=Path(output);folder=root/'observations'/f'decision_{decision_index:06d}'
    folder.mkdir(parents=True,exist_ok=False)
    public_bytes=state_text.encode('utf-8')
    public_path=folder/'public_observation.json';public_path.write_bytes(public_bytes)
    manifest=dict(schema='labsim.provider_observation_files.v1',decision_index=decision_index,request_label=request_label,
        episode_id=state['episode_id'],observation_id=state['observation_id'],simulation_time_s=state.get('simulation_time',state.get('simulation_time_s')),
        public_observation=dict(path=str(public_path.relative_to(root)),sha256=hashlib.sha256(public_bytes).hexdigest(),bytes=len(public_bytes)),images=[])
    for name,jpeg,sha in image_rows:
        path=folder/(name+'.jpg');path.write_bytes(jpeg)
        manifest['images'].append(dict(camera_name=name,path=str(path.relative_to(root)),sha256=sha,bytes=len(jpeg),
            content_type='image/jpeg',resolution_wh=state['model_image_transforms'][name]['transmitted_resolution_wh']))
    manifest_path=folder/'manifest.json';manifest_bytes=(json.dumps(manifest,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode()
    manifest_path.write_bytes(manifest_bytes)
    return dict(manifest_path=str(manifest_path.relative_to(root)),manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
        public_observation=manifest['public_observation'],images=manifest['images'])


def run_episode(environment, client: CubenceClient, output: str | Path, *, max_calls=160, prompt=SYSTEM_PROMPT) -> dict:
    """Run policy on an already-reset facade. The caller owns reset and close."""
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    cfg=client.cfg;tools=GenericRobotTools(environment,cfg["action_limits"])
    schema=tool_definitions()
    frozen=dict(schema="labsim.gpt_controller.v1",provider_config=cfg,prompt=prompt,tool_schema=schema,
        object_truth_used=False,teacher_used=False,physics_paused_during_inference=True,
        implementation_sha256={name:hashlib.sha256((Path(__file__).parent/name).read_bytes()).hexdigest() for name in ('cubence.py','cubence_tools.py')},
        action_meaning="generic EE pose/delta, symmetric gripper or wait; facade performs only IK, interpolation and bounds")
    (output/"controller.json").write_text(json.dumps(frozen,indent=2,ensure_ascii=False)+"\n")
    controller_sha=canonical_hash(frozen)
    started=time.monotonic();calls=0;errors=0;history=[];termination="POLICY_BUDGET";failure=None;backend_error_code=None
    budget_before=client.ledger.summary()
    trace=(output/"policy_trace.jsonl").open("x")
    obs=None;observations_saved=0;observation_artifacts=None;request_label=None;decision_index=None
    try:
        while calls<int(max_calls):
            status=environment.status()
            if status.get("terminated") or status.get("ended"):
                termination="ENVIRONMENT_TERMINATED";break
            if time.monotonic()-started>float(cfg["episode_timeout_s"]):
                termination="POLICY_EPISODE_WALL_TIMEOUT";backend_error_code=termination;failure='MODEL_SERVICE_ERROR';break
            observation_artifacts=None;request_label=None;decision_index=observations_saved
            obs=tools.observe()
            contents=observation_content(obs,image_config=cfg.get('images'))
            try:image_provenance=json.loads(contents[0]['text']).get('model_image_transforms')
            except (ValueError,TypeError,KeyError):image_provenance=None
            request_label=f"policy:{obs['episode_id']}:{obs.get('step_index',obs['observation_id'])}:decision{decision_index}"
            observation_artifacts=save_observation_artifacts(contents,output,decision_index,request_label)
            observations_saved+=1
            # Fresh images every decision; earlier turns preserve only generic
            # tool calls/receipts, never repeated base64 images or privileged state.
            recent_turns=history[-max(1,int(cfg.get("max_context_messages",12))//2):]
            conversation=[item for turn in recent_turns for item in turn]
            input_items=[dict(role="user",content="Task: "+str(obs.get("task_language","")))]+conversation+[dict(role="user",content=contents)]
            before=float(obs.get("simulation_time",obs.get("simulation_time_s",0.)))
            response=None
            meta=None
            call=None
            try:
                response,meta=client.responses(input_items,instructions=prompt+"\nAction limits: "+json.dumps(cfg["action_limits"]),tools=schema,label=request_label,deadline_monotonic=started+float(cfg["episode_timeout_s"]))
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
                    if not error.code.startswith('PROTOCOL'):raise
                    errors+=1
                    receipt={"status":"REJECTED","error":error.code,"details":error.details,
                        "episode_id":obs["episode_id"],"observation_id":obs["observation_id"],"physics_advanced":False,
                        "model_action_id":call['arguments'].get('action_id'),"execution_action_id":tools.execution_id_for(call['arguments'])}
                # Preserve complete response-item groups in memory. Some reasoning
                # models require the reasoning item that accompanies a function call.
                # The trace stores only the observable action, never hidden reasoning.
                history.append(response.get("output",[])+[dict(type="function_call_output",call_id=call["call_id"],output=json.dumps(receipt,allow_nan=False))])
                record=dict(event="decision",episode_id=obs["episode_id"],observation_id=obs["observation_id"],simulation_time_s=before,
                    requested_model=cfg["model"],returned_model=response.get("model"),request_id=meta["request_id"],response_id=response.get("id"),
                    inference_wall_seconds=meta["wall_seconds"],usage=response.get("usage"),tool_call=call,receipt=receipt,controller_sha256=controller_sha,
                    model_action_id=call['arguments'].get('action_id'),execution_action_id=receipt.get('execution_action_id'),
                    decision_index=decision_index,request_label=request_label,observation_artifacts=observation_artifacts,
                    image_channels=["side_camera","wrist_camera"],model_image_transforms=image_provenance,truth_exposed=False)
                trace.write(json.dumps(json_safe(record),ensure_ascii=False,allow_nan=False)+"\n");trace.flush()
                if call["name"]=="finish" and receipt.get("status")!="REJECTED":termination="POLICY_FINISH_REQUEST";break
                if errors>=8:termination="PROTOCOL_ERROR_LIMIT";backend_error_code=termination;failure='INPUT_CONTRACT_ERROR';break
            except ProviderError as error:
                failure=backend_failure_class(error.code)
                termination=error.code
                backend_error_code=error.code
                invalid_calls=[]
                if isinstance(response,dict) and isinstance(response.get('output'),list):
                    invalid_calls=[{k:item.get(k) for k in ('name','arguments','call_id')} for item in response['output'] if isinstance(item,dict) and item.get('type')=='function_call']
                partial_receipt=tools.execution_receipt(call['arguments']) if call and call.get('arguments',{}).get('action_id') else None
                trace.write(json.dumps(dict(event="error",code=error.code,http_status=error.status,episode_id=obs["episode_id"],observation_id=obs["observation_id"],simulation_time_s=before,
                    model_tool_calls=invalid_calls,action_receipt=json_safe(partial_receipt),response_id=response.get('id') if response else None,request_id=meta.get('request_id') if meta else None,
                    decision_index=decision_index,request_label=request_label,observation_artifacts=observation_artifacts))+"\n");trace.flush()
                break
    except ProviderError as error:
        # Observation/context validation can fail before any API request. It must
        # still flush the physical attempt and retain an explicit nonphysical tag.
        backend_error_code=termination=error.code;failure=backend_failure_class(error.code)
        trace.write(json.dumps(dict(event='error',code=error.code,http_status=error.status,
            episode_id=obs.get('episode_id') if obs else None,observation_id=obs.get('observation_id') if obs else None,
            decision_index=decision_index,request_label=request_label,observation_artifacts=observation_artifacts))+"\n");trace.flush()
    finally:
        trace.close()
    result=environment.finish(reason=termination,failure_type=failure)
    budget_after=client.ledger.summary()
    summary=dict(schema="labsim.cubence_episode.v1",controller_sha256=controller_sha,provider=cfg["provider"],requested_model=cfg["model"],
        endpoint=cfg["endpoint"],api_decisions=calls,protocol_rejections=errors,wall_seconds=time.monotonic()-started,
        termination_reason=termination,backend_failure_type=failure,backend_error_code=backend_error_code,
        task_result=json_safe(result),budget=budget_after,
        network_attempts_this_episode=budget_after.get('total_network_attempts',0)-budget_before.get('total_network_attempts',0),
        estimated_usd_this_episode=budget_after.get('total_estimated_usd',0)-budget_before.get('total_estimated_usd',0),
        observation_decisions_recorded=observations_saved,observation_directory='observations',
        object_truth_used=False,teacher_used=False,physics_paused_during_inference=True)
    (output/"summary.json").write_text(json.dumps(summary,indent=2,ensure_ascii=False,allow_nan=False)+"\n")
    return summary
