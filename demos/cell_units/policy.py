"""Explicit user-supplied GPT endpoint, shared transport/budget/robot tools."""

import json
import math
import os
from urllib.parse import urlsplit

from policy.backends.cubence import BudgetLedger, CubenceClient

PROMPT = """You control a simulated Franka for the task stated in task_language.
Use only current side/wrist RGB, camera calibration, joint/TCP state and finger contacts.
There is no object pose oracle, teacher primitive or automatic task completion.
Use the generic move_ee, gripper, wait, observe and finish tools, one call at a time.
Translations are metres, rotations radians, quaternions wxyz. Opening is TOTAL finger separation.
Each action requires the current episode_id, observation_id and a unique action_id.
Maximum translation norm is .04 m per action at .02 m/s; rotation .15 rad at .15 rad/s.
Duration is at most 3 seconds. Infer geometry from the images, approach cautiously and avoid collision.
Finish requests independent scoring; it cannot assert task success. Execute the stated instrument task.
"""


def validate_provider(cfg):
    endpoint = urlsplit(cfg["base_url"])
    if (
        endpoint.scheme != "https"
        or not endpoint.hostname
        or endpoint.username
        or endpoint.password
        or endpoint.query
        or endpoint.fragment
    ):
        raise ValueError("Use an explicit HTTPS provider endpoint without embedded credentials")
    if (
        cfg["model"] != "gpt-6-astra"
        or cfg["credential_env"] != "LABSIM_UNIT_API_KEY"
        or cfg["endpoint"] != "responses"
    ):
        raise ValueError("Unit GPT uses explicit gpt-6-astra / Responses / LABSIM_UNIT_API_KEY")
    for name in (
        "max_requests",
        "max_estimated_usd",
        "request_timeout_s",
        "episode_timeout_s",
        "max_output_tokens",
        "max_context_input_tokens",
    ):
        if not math.isfinite(float(cfg[name])) or cfg[name] <= 0:
            raise ValueError("Invalid provider budget: " + name)
    if cfg["max_requests"] > 1500 or cfg["max_estimated_usd"] > 30:
        raise ValueError("Do not exceed the shared LabSim budget limits")
    return cfg


def make_client(config_path, ledger_path):
    if config_path is None:
        raise ValueError(
            "gpt6 requires --provider-config; credentials come only from LABSIM_UNIT_API_KEY"
        )
    if not os.environ.get("LABSIM_UNIT_API_KEY"):
        raise ValueError("Set LABSIM_UNIT_API_KEY in the process environment")
    cfg = validate_provider(json.loads(config_path.read_text()))
    return CubenceClient(cfg, BudgetLedger(ledger_path, cfg), config_validator=validate_provider)
