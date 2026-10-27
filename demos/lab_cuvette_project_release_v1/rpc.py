"""Release-only RPC identity, failure forwarding and whole-chunk idempotency."""
from __future__ import annotations

import copy
import hashlib
import json
from http.server import HTTPServer
from pathlib import Path
import threading

from demos.lab_cuvette_project_v1.rpc import Handler, ProjectRPC as Previous, encode


class ProjectRPC(Previous):
    FAILURE_TYPES = frozenset(("MODEL_SERVICE_ERROR", "INPUT_CONTRACT_ERROR", "PROCESS_INTERRUPTED",
                              "PHYSICS_INVALID", "EXECUTOR_FAILURE", "SIMULATION_FAILURE", "SAFETY_FAILURE"))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._chunks = {}

    def metadata(self):
        value = super().metadata()
        value.update(schema="labsim.Project_release_v1.rpent_environment.v1", version="Project_release_v1",
                     chunk_retry_semantics="same canonical chunk returns cached original result; interrupted chunk never resumes",
                     physical_baseline="Project_v1_1")
        task = self.environment.task
        cfg = task.cfg if hasattr(task, "cfg") else task.base_cfg
        release = cfg.get("release", {}) if hasattr(cfg, "get") else {}
        value["record_mode"] = release.get("record_mode", "diagnostic")
        return value

    def reset(self, seed=None, options=None):
        options = dict(options or {})
        unexpected = set(options) - {"mode", "subtask", "policy_id", "truth_visible", "teacher"}
        if unexpected:
            raise ValueError("Public standard reset cannot override scene/target/private options: " + repr(sorted(unexpected)))
        result = super().reset(seed, options)
        self._chunks.clear()
        return result

    def chunk(self, actions, return_all_frames=False, chunk_id=None):
        if not isinstance(actions, list) or not 1 <= len(actions) <= 32 or any(not isinstance(a, dict) for a in actions):
            raise ValueError("chunk needs 1..32 typed actions")
        original = copy.deepcopy(actions)
        canonical = json.dumps(original, sort_keys=True, allow_nan=False, default=encode)
        digest = hashlib.sha256(canonical.encode()).hexdigest()
        key = str(chunk_id) if chunk_id is not None else "canonical:" + digest
        if not key or len(key) > 128:
            raise ValueError("chunk_id must contain 1..128 characters")
        current = self.environment.observe()
        episode = current["episode_id"]
        if any(action.get("episode_id") != episode for action in original):
            raise ValueError("Stale chunk episode")
        if key in self._chunks:
            cached = self._chunks[key]
            if cached["digest"] != digest or cached["episode_id"] != episode:
                raise ValueError("chunk_id was reused with a different request or episode")
            if not cached["finished"]:
                raise RuntimeError("Previous chunk interrupted; inspect action receipts, do not replay/resume it")
            return self._chunk_result(cached, return_all_frames, replayed=True)
        if original[0].get("observation_step") != current["step_index"]:
            raise ValueError("Stale chunk origin")
        cached = dict(digest=digest, episode_id=episode, finished=False, results=[])
        # Reserve before the first interval. An exception cannot turn a retry
        # into another physical execution, even if its HTTP response was lost.
        self._chunks[key] = cached
        for index, original_action in enumerate(original):
            action = copy.deepcopy(original_action)
            current = self.environment.observe()
            action["observation_step"] = int(current["step_index"])
            # Child IDs belong to this canonical whole request, never to a
            # newly rebased copy of the chunk received on retry.
            action["action_id"] = "chunk:" + hashlib.sha256(key.encode()).hexdigest() + ":" + str(index)
            result = self.step(action)
            cached["results"].append(copy.deepcopy(result))
            receipt = result[4].get("action_receipt", {})
            if result[2] or result[3] or receipt.get("accepted") is False or receipt.get("partial_execution") is True or receipt.get("successor_observation_available") is False:
                break
        cached["finished"] = True
        episode_dir = getattr(self.environment.task, "episode_dir", None)
        if episode_dir is not None:
            record = dict(schema="labsim.Project_release_v1.chunk_receipt.v1", episode_id=episode,
                chunk_id=key, canonical_request_sha256=digest, original_actions=original,
                requested_actions=len(original), returned_actions=len(cached["results"]),
                child_receipts=[row[4].get("action_receipt") for row in cached["results"]],
                finished=True, unexecuted_remainder_discarded=len(cached["results"]) < len(original))
            with (Path(episode_dir) / "chunk_receipts.jsonl").open("a") as stream:
                stream.write(json.dumps(record, default=encode, allow_nan=False) + "\n")
        return self._chunk_result(cached, return_all_frames, replayed=False)

    @staticmethod
    def _chunk_result(cached, return_all_frames, *, replayed):
        rows = copy.deepcopy(cached["results"])
        last = list(rows[-1])
        last[4] = dict(last[4], chunk_request_sha256=cached["digest"], chunk_replayed=replayed,
                       chunk_actions_returned=len(rows))
        if return_all_frames:
            last[0] = [row[0] for row in rows]
        return tuple(last)

    def finalize(self, termination_reason="POLICY_BUDGET", failure_type=None, episode_id=None):
        status = self.environment.status()
        if episode_id is not None and episode_id != status["episode_id"]:
            raise ValueError("Stale finalization episode")
        normalized = None if failure_type is None else str(failure_type).upper()
        if normalized is not None and normalized not in self.FAILURE_TYPES:
            raise ValueError("Unsupported backend failure classification")
        # The facade preserves an already scored safety/physical terminal
        # result; a backend cannot replace it with a service error or success.
        return self.environment.finish(reason=str(termination_reason), failure_type=normalized)

    def dispatch(self, method, args=(), kwargs=None):
        result = super().dispatch(method, args, kwargs)
        if method == "healthz":
            return dict(result, version="Project_release_v1")
        return result


def serve_environment(environment, host="127.0.0.1", port=8097, *, ready_path=None):
    if host not in ("127.0.0.1", "localhost"):
        raise ValueError("Unauthenticated policy RPC is loopback only")
    if threading.current_thread() is not threading.main_thread():
        raise RuntimeError("Isaac RPC must run on main thread")
    server = HTTPServer((host, int(port)), Handler)
    server.timeout = .1
    ready = Path(ready_path) if ready_path else None
    server.facade = ProjectRPC(environment, request_log=ready.with_suffix(".rpc.jsonl") if ready else None)
    meta = server.facade.metadata()
    meta["endpoint"] = f"http://{host}:{server.server_address[1]}"
    if ready:
        ready.write_text(json.dumps(meta, indent=2) + "\n")
    print("PROJECT_RPC_READY", meta["endpoint"], "Project_release_v1", flush=True)
    try:
        while not server.facade.closed:
            server.handle_request()
    finally:
        server.server_close()
        environment.close()
    return meta
