"""Opt-in P9: robot-own FK facts, no scene queries or automatic motion."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from .cubence import ProviderError,canonical_hash
from .cubence_tools import run_episode as _run_episode
from .cubence_project_v1_1_active_view import (
    PublicActiveViewClient,ProjectV11ActiveViewRobotTools,
    SYSTEM_PROMPT as P8_PROMPT,ACTIVE_VIEW_PROMPT,validate_active_view)
from .cubence_project_v1_1_side_detail import SYSTEM_PROMPT as P7_PROMPT,DETAIL_PROMPT
from .cubence_project_v1_1_tools import SYSTEM_PROMPT as P4_PROMPT,TEMPORAL_SYSTEM_PROMPT as P6_PROMPT,TEMPORAL_VISUAL_PROMPT
from .cubence_project_v1_1_visual_context import _json_bytes
from policy.robot_self_kinematics import derive_robot_self_state,MODEL_SHA256,VERSION as MODEL_VERSION

VERSION='Project_v1_1.public_robot_self_state_packet.v1'
ROBOT_SELF_STATE=dict(enabled=True,version=MODEL_VERSION,model_SHA256=MODEL_SHA256,
    frames=['panda_link6','panda_link7','panda_hand'],scope='robot_only_nominal_fk_authored_local_input_boxes')
SELF_STATE_PROMPT="""
P9 supplies CURRENT robot-only nominal link frames/local input boxes from measured joints and the public actual TCP. These are not obstacle, seat or held-object state, cooked shapes, swept volume, clearance or support. The hand box excludes fingers and the held vessel; inspect both images for those and scene relationships. Use CURRENT identities. Missing support before contact is expected, not alone a reason to finish: if visual alignment and the next local clearance are supported, seek allowed task contact incrementally and observe again under the existing insertion/slip rules. Do not release before actual support. Stop on real safety/anomaly or when no evidenced safe local action exists. No automatic motion or route is supplied.
"""
SYSTEM_PROMPT=P8_PROMPT+SELF_STATE_PROMPT
DEFAULT_PROFILE=Path(__file__).resolve().parents[2]/'config/lab_cuvette_loading/Project_v1_1/policies/cubence_gpt6_context2_640high_temporal_detail_active_view_self_state.json'


def validate_robot_self_state(config):
    validate_active_view(config)
    value=config.get('robot_self_state')
    if not isinstance(value,dict) or value!=ROBOT_SELF_STATE or value.get('enabled') is not True:
        raise ProviderError('PROTOCOL_INVALID_ROBOT_SELF_STATE_CONFIG')
    return copy.deepcopy(value)


class PublicRobotSelfStateClient(PublicActiveViewClient):
    """One extra current text group before unchanged final current JSON/RGB."""
    def __init__(self,client,output):
        validate_robot_self_state(client.cfg)
        super().__init__(client,output)

    def _save_packet(self,augmented,current,previous,reference,candidates,
                     duplicate,selected_contact,request_label,expanded):
        state=current['state']
        try:
            self_state=derive_robot_self_state(state['joint_positions'][:7],state['TCPpose'],
                episode_id=state['episode_id'],observation_id=state['observation_id'],simulation_time=state['simulation_time'])
        except (ValueError,TypeError,KeyError,IndexError,OverflowError):
            raise ProviderError('PROTOCOL_INVALID_PUBLIC_ROBOT_SELF_STATE') from None
        packet=super()._save_packet(augmented,current,previous,reference,candidates,
            duplicate,selected_contact,request_label,expanded)
        path=packet/'input_items_manifest.json';before=path.read_bytes();record=json.loads(before)
        with (packet/'pre_robot_self_input_items_manifest.json').open('xb') as stream:stream.write(before)
        (packet/'pre_robot_self_preparation.json').write_bytes(_json_bytes(dict(
            schema=VERSION,status='intermediate_preparation_not_actual_input',API_sent=False,
            pre_robot_self_manifest_SHA256=hashlib.sha256(before).hexdigest())))
        raw=_json_bytes(self_state)
        with (packet/'current_robot_self_state.json').open('xb') as stream:stream.write(raw)
        text='CURRENT ROBOT SELF-STATE\n'+json.dumps(self_state,ensure_ascii=False,separators=(',',':'),allow_nan=False)
        group=dict(role='user',content=[dict(type='input_text',text=text)])
        index=len(augmented)-1;augmented.insert(index,group)
        assert augmented[-1]['content']==current['source_contents']
        projection=record['input_items_public_projection'];projection.insert(index,copy.deepcopy(group))
        redactions=copy.deepcopy(record['private_provider_items_redacted'])
        for row in redactions:
            if row['input_item_index']>=index:row['input_item_index']+=1
        record.update(schema=VERSION,base_fixed_side_detail_schema=record['schema'],
            pre_robot_self_manifest=dict(path='pre_robot_self_input_items_manifest.json',sha256=hashlib.sha256(before).hexdigest(),scope='Intermediate preparation; never delegated alone'),
            robot_self_state=dict(path='current_robot_self_state.json',sha256=hashlib.sha256(raw).hexdigest(),
                model_SHA256=MODEL_SHA256,source='Current public q7/actual TCP and locked numeric robot model only'),
            robot_self_user_item_index=index,current_user_item_index=len(augmented)-1,
            current_user_item_preserved=True,input_items_public_projection=projection,
            public_projection_canonical_sha256=canonical_hash(projection),full_wire_input_canonical_sha256=canonical_hash(augmented),
            private_provider_items_redacted=redactions,
            budget_scope='All unchanged P8 images/history plus robot-only text delegated once before unchanged client bounds/reserves the same ledger; no extra API call',
            source_scope='Public RGB/proprio/calibration/tactile plus nominal own-robot FK/INPUT boxes; no scene/object/seat/obstacle truth or collision query')
        path.write_bytes(_json_bytes(record))
        return packet


class ProjectV11RobotSelfStateTools(ProjectV11ActiveViewRobotTools):
    @staticmethod
    def controller_metadata():
        value=ProjectV11ActiveViewRobotTools.controller_metadata()
        value.update(tools_class='ProjectV11RobotSelfStateTools',prompt_version='Project_v1_1.public_tools.v9_robot_self_state',
            robot_self_state=copy.deepcopy(ROBOT_SELF_STATE),
            default_system_prompt_SHA256=hashlib.sha256(SYSTEM_PROMPT.encode()).hexdigest())
        value['implementation_sha256'][Path(__file__).name]=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        library=Path(__file__).resolve().parents[1]/'robot_self_kinematics.py'
        value['implementation_sha256']['robot_self_kinematics.py']=hashlib.sha256(library.read_bytes()).hexdigest()
        return value


def run_episode(environment,client,output,*,max_calls=160,prompt=None):
    validate_robot_self_state(client.cfg)
    if prompt is None or prompt in (P4_PROMPT,P6_PROMPT,P7_PROMPT,P8_PROMPT,SYSTEM_PROMPT):actual_prompt=SYSTEM_PROMPT
    else:actual_prompt=prompt+TEMPORAL_VISUAL_PROMPT+DETAIL_PROMPT+ACTIVE_VIEW_PROMPT+SELF_STATE_PROMPT
    class EpisodeTools(ProjectV11RobotSelfStateTools):
        @staticmethod
        def controller_metadata():
            value=ProjectV11RobotSelfStateTools.controller_metadata()
            value['actual_system_prompt_SHA256']=hashlib.sha256(actual_prompt.encode()).hexdigest()
            instructions=actual_prompt+'\nAction limits: '+json.dumps(client.cfg['action_limits'])
            value['actual_request_instructions_SHA256']=hashlib.sha256(instructions.encode()).hexdigest()
            return value
    return _run_episode(environment,PublicRobotSelfStateClient(client,output),output,
        max_calls=max_calls,prompt=actual_prompt,tools_class=EpisodeTools)
