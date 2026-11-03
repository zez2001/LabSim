"""Bounded, credential-safe Cubence Responses transport (stdlib only).

No SDK globals, Codex authentication, teacher controller or simulation imports.
All network attempts, including retries and ambiguous timeouts, consume a shared
on-disk budget before sending. Unknown usage retains the conservative reservation.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any


class ProviderError(RuntimeError):
    def __init__(self, code: str, *, status: int | None = None, retryable: bool = False, details: dict | None = None):
        super().__init__(code)
        self.code, self.status, self.retryable = code, status, retryable
        self.details = details


class BudgetExceeded(ProviderError):
    pass


def load_config(path: str | Path) -> dict:
    cfg = json.loads(Path(path).read_text())
    return validate_config(cfg)


def validate_config(cfg: dict) -> dict:
    if cfg.get("provider") != "cubence":
        raise ValueError("Provider must be explicitly cubence")
    if cfg.get("model") != "gpt-6-astra":
        raise ValueError("This evaluation is pinned to gpt-6-astra; no model substitution")
    url = urllib.parse.urlsplit(cfg["base_url"])
    if url.scheme != "https" or url.hostname not in {
        "api.cubence.ai", "api-lb.cubence.ai", "api.cubence.com"
    } or url.username or url.password or url.query or url.fragment or url.path.rstrip("/") != "/v1":
        raise ValueError("Use an official HTTPS Cubence /v1 endpoint without credentials or query")
    if cfg.get("credential_env") != "CUBENCE_API_KEY":
        raise ValueError("Only the process environment CUBENCE_API_KEY is accepted")
    if cfg.get("endpoint", "responses") not in {"responses", "chat/completions"}:
        raise ValueError("Unknown API endpoint")
    for name in ("request_timeout_s", "episode_timeout_s", "max_output_tokens", "max_requests", "max_estimated_usd", "max_context_input_tokens"):
        if not math.isfinite(float(cfg[name])) or float(cfg[name]) <= 0:
            raise ValueError(f"Invalid positive limit: {name}")
    if int(cfg["max_requests"]) > 1500 or float(cfg["max_estimated_usd"]) > 30:
        raise ValueError("User-authorized cap is $30 estimated and 1500 network attempts")
    return cfg


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


class BudgetLedger:
    """Sequential-process ledger; Linux advisory locking prevents overlapping runs."""
    def __init__(self, path: str | Path, cfg: dict):
        self.path, self.cfg = Path(path), cfg
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _locked(self, update):
        import fcntl
        lock_path = self.path.with_suffix(self.path.suffix + ".lock")
        with lock_path.open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            data = json.loads(self.path.read_text()) if self.path.exists() else {
                "schema": "labsim.cubence_budget.v1", "attempts": [],
                "max_estimated_usd": min(30., float(self.cfg["max_estimated_usd"])),
                "max_requests": min(1500, int(self.cfg["max_requests"])),
                "pricing": self.cfg["pricing"],
            }
            result = update(data)
            tmp = self.path.with_name(self.path.name + "." + uuid.uuid4().hex + ".tmp")
            tmp.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n")
            tmp.replace(self.path)
            return result

    def reserve(self, *, label: str, endpoint: str, input_tokens_bound: int, output_tokens_bound: int) -> str:
        price = self.cfg["pricing"]
        bound = (input_tokens_bound * price["input_usd_per_million"] + output_tokens_bound * price["output_usd_per_million"]) / 1e6
        def update(data):
            used = sum(x["charged_estimate_usd"] for x in data["attempts"])
            if len(data["attempts"]) >= min(data["max_requests"], int(self.cfg["max_requests"])):
                raise BudgetExceeded("REQUEST_BUDGET_EXHAUSTED")
            if used + bound > min(data["max_estimated_usd"], float(self.cfg["max_estimated_usd"])) + 1e-12:
                raise BudgetExceeded("COST_BUDGET_EXHAUSTED")
            request_id = str(uuid.uuid4())
            data["attempts"].append(dict(request_id=request_id, label=label, endpoint=endpoint,
                requested_model=self.cfg["model"], reservation_input_tokens=input_tokens_bound,
                reservation_output_tokens=output_tokens_bound, reserved_usd=bound,
                charged_estimate_usd=bound, status="RESERVED", created_unix_s=time.time()))
            return request_id
        return self._locked(update)

    def complete(self, request_id: str, *, status: str, usage: dict | None = None, **metadata):
        def update(data):
            item = next(x for x in data["attempts"] if x["request_id"] == request_id)
            item.update(status=status, **metadata)
            if usage is not None:
                price = self.cfg["pricing"]
                inp = int(usage.get("input_tokens", usage.get("prompt_tokens", 0)))
                out = int(usage.get("output_tokens", usage.get("completion_tokens", 0)))
                details = usage.get("input_tokens_details", usage.get("prompt_tokens_details", {})) or {}
                cached = min(inp, int(details.get("cached_tokens", 0)))
                if min(inp, out, cached) < 0:
                    raise ValueError("Negative usage refused")
                item["usage"] = usage
                item["charged_estimate_usd"] = ((inp - cached) * price["input_usd_per_million"] + cached * price["cached_input_usd_per_million"] + out * price["output_usd_per_million"]) / 1e6
                item["cost_basis"] = "returned usage times configured public rates; billing multiplier unknown"
            else:
                item["cost_basis"] = "unknown usage: conservative reservation retained"
            data["total_network_attempts"] = len(data["attempts"])
            data["total_estimated_usd"] = sum(x["charged_estimate_usd"] for x in data["attempts"])
            return dict(item)
        return self._locked(update)

    def summary(self) -> dict:
        if not self.path.exists():
            return {"total_network_attempts": 0, "total_estimated_usd": 0.}
        data = json.loads(self.path.read_text())
        return {"total_network_attempts": len(data["attempts"]),
                "total_estimated_usd": sum(x["charged_estimate_usd"] for x in data["attempts"]),
                "path": str(self.path)}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def input_token_bound(payload: dict, limit: int) -> int:
    """Conservative local estimate, not a tokenizer or image precision claim.

    Images <=640x480 are reserved at8192 tokens each; text at one token/UTF8 byte.
    Unknown image sizes must be resized by the observation adapter first.
    """
    def replace_images(value):
        if isinstance(value, dict):
            if value.get("type") in ("input_image", "image_url"):
                return " " * 8192
            return {k: replace_images(v) for k, v in value.items()}
        if isinstance(value, list):
            return [replace_images(v) for v in value]
        return value
    bound = len(json.dumps(replace_images(payload), ensure_ascii=False).encode()) + 1024
    if bound > int(limit):
        raise ProviderError("LOCAL_CONTEXT_TOKEN_BOUND_EXCEEDED")
    return bound


class CubenceClient:
    def __init__(self, config: dict, ledger: BudgetLedger, *, opener=None, sleeper=time.sleep):
        self.cfg, self.ledger, self.sleeper = validate_config(config), ledger, sleeper
        self.opener = opener or urllib.request.build_opener(_NoRedirect)
        self.key = os.environ.get(config["credential_env"], "").strip()
        if not self.key:
            raise ProviderError("MISSING_CUBENCE_API_KEY")
        self.endpoint = config.get("endpoint", "responses")
        if self.endpoint != "responses":
            proof = config.get("fallback_capability_evidence")
            if not proof or not Path(proof).is_file():
                raise ProviderError("CHAT_FALLBACK_REQUIRES_RECORDED_RESPONSES_PROBE")
            evidence = json.loads(Path(proof).read_text())
            if evidence.get("requested_model") != config["model"] or evidence.get("responses_supported") is not False or evidence.get("chat_supported") is not True:
                raise ProviderError("INVALID_CHAT_FALLBACK_EVIDENCE")

    def request(self, payload: dict, *, label: str, endpoint: str | None = None, allow_retry=True, deadline_monotonic: float | None = None) -> tuple[dict, dict]:
        endpoint = endpoint or self.endpoint
        if endpoint not in {"responses", "chat/completions"}:
            raise ValueError("Unsupported endpoint")
        # Models are pinned here even when a caller constructs the payload.
        if payload.get("model") != self.cfg["model"]:
            raise ProviderError("MODEL_SUBSTITUTION_REFUSED")
        body = json.dumps(payload, allow_nan=False).encode()
        bound = input_token_bound(payload, int(self.cfg["max_context_input_tokens"]))
        output_bound = int(payload.get("max_output_tokens", payload.get("max_completion_tokens", self.cfg["max_output_tokens"])))
        if output_bound < 1 or output_bound > int(self.cfg["max_output_tokens"]):
            raise ProviderError("OUTPUT_TOKEN_LIMIT_REFUSED")
        attempts = 1 + (int(self.cfg.get("max_retries", 0)) if allow_retry else 0)
        for retry in range(attempts):
            remaining=None if deadline_monotonic is None else deadline_monotonic-time.monotonic()
            if remaining is not None and remaining<=0:
                raise ProviderError("PROVIDER_EPISODE_WALL_TIMEOUT")
            request_id = self.ledger.reserve(label=label, endpoint=endpoint, input_tokens_bound=bound, output_tokens_bound=output_bound)
            started = time.monotonic()
            request = urllib.request.Request(self.cfg["base_url"].rstrip("/") + "/" + endpoint, data=body,
                headers={"Authorization": "Bearer " + self.key, "Content-Type": "application/json", "Accept": "application/json", "User-Agent": "LabSim-Project-v1/1.0"}, method="POST")
            try:
                timeout=float(self.cfg["request_timeout_s"])
                if remaining is not None:timeout=min(timeout,max(.001,remaining))
                with self.opener.open(request, timeout=timeout) as response:
                    content = response.read(16 * 1024 * 1024)
                    if len(content) >= 16 * 1024 * 1024:
                        raise ProviderError("PROVIDER_RESPONSE_TOO_LARGE")
                    try:
                        parsed = json.loads(content)
                    except (ValueError, UnicodeError):
                        raise ProviderError("PROVIDER_INVALID_JSON") from None
                    if not isinstance(parsed, dict):
                        raise ProviderError("PROVIDER_INVALID_ENVELOPE")
                    if parsed.get("error"):
                        raise ProviderError("PROVIDER_ERROR_ENVELOPE")
                    returned_model=parsed.get('model')
                    identity_error=('RETURNED_MODEL_MISSING' if returned_model is None or returned_model=='' else
                        'RETURNED_MODEL_MISMATCH' if returned_model!=self.cfg['model'] else None)
                    try:
                        meta = self.ledger.complete(request_id, status=identity_error or "OK", usage=parsed.get("usage"),
                            returned_model=returned_model, response_id=parsed.get("id"), wall_seconds=time.monotonic()-started,
                            http_status=int(getattr(response, "status", 200)), retry_index=retry)
                    except (ValueError,TypeError,AttributeError,OverflowError):
                        raise ProviderError("PROVIDER_INVALID_USAGE") from None
                    if identity_error:
                        raise ProviderError(identity_error)
                    return parsed, meta
            except urllib.error.HTTPError as error:
                status = int(error.code)
                code = "PROVIDER_RATE_LIMIT" if status == 429 else "PROVIDER_HTTP_ERROR"
                retryable = status == 429 or status >= 500
                # Never serialize provider error bodies, request objects or headers.
                self.ledger.complete(request_id, status=code, http_status=status, retry_index=retry, wall_seconds=time.monotonic()-started)
                failure = ProviderError(code, status=status, retryable=retryable)
            except (urllib.error.URLError, socket.timeout, TimeoutError) as error:
                code = "PROVIDER_TIMEOUT" if isinstance(error, (socket.timeout, TimeoutError)) or isinstance(getattr(error, "reason", None), (socket.timeout, TimeoutError)) else "PROVIDER_NETWORK_ERROR"
                self.ledger.complete(request_id, status=code, retry_index=retry, wall_seconds=time.monotonic()-started)
                failure = ProviderError(code, retryable=True)
            except ProviderError as error:
                if error.code not in ("RETURNED_MODEL_MISSING","RETURNED_MODEL_MISMATCH"):
                    self.ledger.complete(request_id, status=error.code, retry_index=retry, wall_seconds=time.monotonic()-started)
                raise
            if not failure.retryable or retry + 1 >= attempts:
                raise failure from None
            delay=min(10., float(self.cfg.get("retry_delay_s", 1.)) * 2 ** retry)
            if deadline_monotonic is not None:delay=min(delay,max(0.,deadline_monotonic-time.monotonic()))
            self.sleeper(delay)
        raise ProviderError("PROVIDER_RETRY_EXHAUSTED")

    def responses(self, input_items: list, *, instructions: str, tools: list | None = None, label="policy", deadline_monotonic=None, **extra):
        payload = dict(model=self.cfg["model"], input=input_items, instructions=instructions,
            max_output_tokens=int(self.cfg["max_output_tokens"]), store=False)
        if self.cfg.get("reasoning_effort"):
            payload["reasoning"] = {"effort": self.cfg["reasoning_effort"]}
        if tools:
            payload.update(tools=tools, parallel_tool_calls=False)
        payload.update(extra)
        if tools:
            # Policy tools are a serial robot-control protocol. A caller cannot
            # accidentally enable parallel physical actions through extra kwargs.
            payload["parallel_tool_calls"] = False
        return self.request(payload, label=label, endpoint="responses", deadline_monotonic=deadline_monotonic)


def response_text(response: dict) -> str:
    chunks=[]
    for item in response.get("output", []):
        if item.get("type") == "message":
            chunks.extend(str(c.get("text", "")) for c in item.get("content", []) if c.get("type") == "output_text")
    return "".join(chunks)


def response_tools(response: dict) -> list[dict]:
    tools=[]
    output=response.get("output", [])
    if not isinstance(output,list):raise ProviderError("PROTOCOL_INVALID_RESPONSE_OUTPUT")
    for item in output:
        if not isinstance(item,dict):raise ProviderError("PROTOCOL_INVALID_RESPONSE_ITEM")
        if item.get("type") == "function_call":
            try:
                arguments = json.loads(item.get("arguments", ""))
            except (ValueError, TypeError):
                raise ProviderError("PROTOCOL_INVALID_TOOL_JSON") from None
            if not isinstance(arguments, dict):
                raise ProviderError("PROTOCOL_TOOL_ARGUMENTS_NOT_OBJECT")
            tools.append({"name": item.get("name"), "arguments": arguments, "call_id": item.get("call_id")})
    if len(tools) > 1:
        raise ProviderError("PROTOCOL_MULTIPLE_ACTIONS_REFUSED")
    if tools and (not isinstance(tools[0]['name'],str) or not tools[0]['name']):
        raise ProviderError("PROTOCOL_UNKNOWN_TOOL")
    if tools and (not isinstance(tools[0]['call_id'],str) or not tools[0]['call_id']):
        raise ProviderError("PROTOCOL_CALL_ID_MISSING")
    return tools
