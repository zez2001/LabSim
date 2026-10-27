"""Opt-in P8 prompt policy; the P7 public-image and robot tools stay unchanged."""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

from .cubence import ProviderError
from .cubence_tools import run_episode as _run_episode
from .cubence_project_v1_1_side_detail import (
    PublicFixedSideDetailClient, ProjectV11FixedSideDetailTools,
    SYSTEM_PROMPT as P7_PROMPT, DETAIL_PROMPT, validate_fixed_side_detail)
from .cubence_project_v1_1_tools import (
    SYSTEM_PROMPT as P4_PROMPT, TEMPORAL_SYSTEM_PROMPT as P6_PROMPT,
    TEMPORAL_VISUAL_PROMPT)

VERSION='Project_v1_1.active_view_prompt.v1'
ACTIVE_VIEW_CONTROL=dict(enabled=True,version=VERSION,scope='prompt_only_no_automatic_action')
ACTIVE_VIEW_PROMPT="""
P8 active-view clarification: uncertainty about an entire route is not itself evidence that no safe local action exists. Distinguish a visible obstruction or imminent contact from missing depth information. If the current views support that the next local motion is free for the whole moving arm, hand and held vessel, choose a conservative reversible translation or rotation within the existing tool limits to gain a different view, then inspect fresh images and tactile readings before proceeding. Account for how wrist rotation also moves the fingers and held vessel. A stationary observe does not change the camera viewpoint; repeated lifting without new useful visibility is not evidence of a route. Do not require certainty about the whole route before a supported local observation move. If no safe local action is supported, or an actual safety stop/anomaly occurs, stop and finish without release. All insertion, contact, support, release and current-identity requirements remain.
"""
SYSTEM_PROMPT=P7_PROMPT+ACTIVE_VIEW_PROMPT


def validate_active_view(config):
    validate_fixed_side_detail(config)
    value=config.get('active_view_control')
    if not isinstance(value,dict) or value!=ACTIVE_VIEW_CONTROL or value.get('enabled') is not True:
        raise ProviderError('PROTOCOL_INVALID_ACTIVE_VIEW_CONTROL')
    return copy.deepcopy(value)


class PublicActiveViewClient(PublicFixedSideDetailClient):
    """Validation only; inherited P7 image/history/recording/delegation is exact."""
    def __init__(self,client,output):
        validate_active_view(client.cfg)
        super().__init__(client,output)


class ProjectV11ActiveViewRobotTools(ProjectV11FixedSideDetailTools):
    """Metadata only: no action, observation, limit or stopping override."""
    @staticmethod
    def controller_metadata():
        value=ProjectV11FixedSideDetailTools.controller_metadata()
        value.update(tools_class='ProjectV11ActiveViewRobotTools',
            prompt_version='Project_v1_1.public_tools.v8_active_view',
            active_view_control=copy.deepcopy(ACTIVE_VIEW_CONTROL),
            active_view_scope='Generic prompt guidance only; no coordinates, route, automatic action, perception oracle or altered safety gate',
            default_system_prompt_SHA256=hashlib.sha256(SYSTEM_PROMPT.encode()).hexdigest())
        value['implementation_sha256'][Path(__file__).name]=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        return value


def run_episode(environment,client,output,*,max_calls=160,prompt=None):
    validate_active_view(client.cfg)
    if prompt is None or prompt in (P4_PROMPT,P6_PROMPT,P7_PROMPT,SYSTEM_PROMPT):
        actual_prompt=SYSTEM_PROMPT
    else:
        actual_prompt=prompt+TEMPORAL_VISUAL_PROMPT+DETAIL_PROMPT+ACTIVE_VIEW_PROMPT

    class EpisodeTools(ProjectV11ActiveViewRobotTools):
        @staticmethod
        def controller_metadata():
            value=ProjectV11ActiveViewRobotTools.controller_metadata()
            value['actual_system_prompt_SHA256']=hashlib.sha256(actual_prompt.encode()).hexdigest()
            instructions=actual_prompt+'\nAction limits: '+json.dumps(client.cfg['action_limits'])
            value['actual_request_instructions_SHA256']=hashlib.sha256(instructions.encode()).hexdigest()
            return value

    return _run_episode(environment,PublicActiveViewClient(client,output),output,
        max_calls=max_calls,prompt=actual_prompt,tools_class=EpisodeTools)
