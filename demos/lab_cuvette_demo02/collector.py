"""Existing aligned collector with conservative V0_demo02 identity/label gates.

Call ``finish_episode(result, independent_score=NEW_SCORE_PATH)`` only after the
new saved-state analysis has run on this episode. Missing/failed score keeps raw
success and data eligibility false. This class is not applied to historical H5.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import h5py
import numpy as np
from omegaconf import OmegaConf

from demos.lab_cuvette_demo01.collector import DemoCollector
from demos.lab_cuvette_demo02.analyze import CHECK_NAMES, PHASES, json_safe, load_json, sha256
from demos.lab_cuvette_demo02.data_check import ACTION_SEMANTICS, OBSERVATION_ALIGNMENT


def collector_metadata(contract):
    """Pure metadata interface: unknown IDs remain absent, with null in JSON."""
    contract = dict(contract or {})
    source, target = contract.get("source_slot", {}), contract.get("target_seat", {})
    result = dict(schema_version="labsim.lab_cuvette_loading.V0_demo02.v1",
                  scene_version="V0_demo02", task="lab_cuvette_loading_V0_demo02",
                  data_scope="lab_cuvette_loading_V0_demo02_simulation",
                  action_semantics=ACTION_SEMANTICS, observation_alignment=OBSERVATION_ALIGNMENT,
                  phase_names_json=json.dumps(list(PHASES)),
                  source_slot_known=bool(source.get("id")), target_seat_known=bool(target.get("id")),
                  scene_correspondence_accepted=contract.get("scene_correspondence", {}).get("accepted") is True,
                  cad_pair_verified=contract.get("native_pair_verified") is True,
                  real_calibrated=contract.get("real_calibrated") is True,
                  success=False, complete=False, data_eligible=False, full_task_eligible=False,
                  workflow_success=False, native_pair_success=False, full_success=False)
    for name, value in (("source_slot_id", source.get("id")),
                        ("target_seat_id", target.get("id")),
                        ("asset_manifest_sha256", contract.get("asset_manifest_sha256")),
                        ("target_is_internal_chamber", target.get("inside_sample_chamber"))):
        if value is not None:
            result[name] = value
    serialized = json.dumps(json_safe(contract), ensure_ascii=False, sort_keys=True, allow_nan=False)
    result["scene_contract_json"] = serialized
    result["scene_contract_canonical_sha256"] = hashlib.sha256(serialized.encode()).hexdigest()
    return result


def qualification_reasons(metadata, score, output, frames, final_timestamp):
    """A controller status alone is deliberately absent from this gate."""
    checks = dict(
        new_score_schema=score.get("schema") == "labsim.V0_demo02.independent.v2",
        not_historical=score.get("historical_semantics_only") is False,
        new_score_scene=score.get("scene_version") == "V0_demo02",
        independently_accepted_scene=score.get("scene_correspondence_accepted") is True,
        collector_accepted_scene=metadata.get("scene_correspondence_accepted") is True,
        independently_successful_workflow=score.get("workflow_success") is True,
        independently_eligible=score.get("data_eligible") is True,
        all_independent_checks_pass=(set(score.get("checks", {})) == set(CHECK_NAMES)
                                     and all(v is True for v in score.get("checks", {}).values())),
        same_episode=score.get("source_episode") is not None and
                     Path(score["source_episode"]).resolve() == Path(output).resolve(),
        same_asset_manifest=bool(metadata.get("asset_manifest_sha256")) and
                            metadata.get("asset_manifest_sha256") == score.get("asset_manifest_sha256"),
        same_source_slot=bool(metadata.get("source_slot_id")) and
                         metadata.get("source_slot_id") == score.get("source_slot_id"),
        same_internal_target=metadata.get("target_is_internal_chamber") is True and
                             bool(metadata.get("target_seat_id")) and
                             metadata.get("target_seat_id") == score.get("target_seat_id"),
        actual_transitions_present=frames > 0,
        same_terminal_state=bool(final_timestamp is not None and
            score.get("trajectory_end_time_s") is not None and
            abs(float(final_timestamp)-float(score["trajectory_end_time_s"])) <= 1e-6),
        saved_physics_hash_present=bool(score.get("physics_records_sha256")),
        saved_events_hash_present=bool(score.get("events_sha256")))
    return [key for key, value in checks.items() if value is not True]


class Demo02Collector(DemoCollector):
    def __init__(self, cfg, output_dir, save_video=True, *, scene_contract=None):
        # The native-scene audit config uses task as a name string. The inherited
        # writer expects task.instruction/control_hz. Normalize a private copy;
        # do not change the experiment config or any earlier collector.
        data = OmegaConf.to_container(cfg, resolve=True) if OmegaConf.is_config(cfg) else dict(cfg)
        data = json.loads(json.dumps(data))
        physics = data.setdefault("physics", {})
        physics.setdefault("control_hz", 60)
        physics.setdefault("hz", 240)
        task = data.get("task")
        if not isinstance(task, dict):
            task = {}
        task.setdefault("instruction", "Take the vessel from the designated rack slot and load the verified internal sample-chamber seat.")
        task.setdefault("control_hz", physics["control_hz"])
        data["task"] = task
        data.setdefault("collector", {}).setdefault("compression", "lzf")
        data.setdefault("control", {})["phases_s"] = {phase: 0.0 for phase in PHASES}
        super().__init__(OmegaConf.create(data), output_dir, save_video)
        self.scene_contract = dict(scene_contract or {})
        self.metadata = collector_metadata(self.scene_contract)

    def begin_episode(self, index, initial_position):
        super().begin_episode(index, initial_position)
        self.file.attrs.update(self.metadata)
        self.file.attrs["progress_columns"] = "support_valid,grasp_success,extract_success,transport_success,loaded,released,retreated,stable"

    def finish_episode(self, result, independent_score=None):
        if self.file is None:
            raise RuntimeError("No open new episode")
        self.file.flush()
        evidence, rejection, source_hash = None, ["independent_score_not_provided"], None
        if independent_score is not None:
            path = Path(independent_score)
            if not path.is_file():
                rejection = ["independent_score_file_missing"]
            else:
                evidence, source_hash = load_json(path), sha256(path)
                last = float(self.file["next_timestamp"][-1]) if self.count and "next_timestamp" in self.file else None
                rejection = qualification_reasons(self.metadata, evidence, self.output, self.count, last)
                for key, name in (("physics_records_sha256", "physics_records.json"),
                                  ("events_sha256", "events.json")):
                    raw = self.output/name
                    if not raw.is_file() or evidence.get(key) != sha256(raw):
                        rejection.append("independent_score_does_not_match_"+name)
        eligible = not rejection
        workflow = bool(eligible)
        native = bool(eligible and evidence.get("native_pair_success") is True)
        self.file.attrs.update(success=eligible, complete=True, frames=self.count,
            status=result.get("status", "UNKNOWN"), reason=result.get("reason", result.get("status", "UNKNOWN")),
            workflow_success=workflow, full_success=workflow, native_pair_success=native,
            data_eligible=eligible, full_task_eligible=eligible,
            independent_adjudication_available=evidence is not None,
            qualification_rejection_json=json.dumps(rejection),
            independent_score_sha256=source_hash or "unavailable")
        if self.count:
            if "done" in self.file:
                self.file["done"][-1] = True
            if "reward" in self.file:
                self.file["reward"][-1] = np.float32(workflow)
        properties = dict(result)
        properties["independent_adjudication"] = dict(workflow_success=workflow,
            native_pair_success=native, data_eligible=eligible, rejection_reasons=rejection,
            score_sha256=source_hash, score_source=str(independent_score) if independent_score else None)
        if evidence is not None:
            self.file.create_dataset("independent_score_json", data=json.dumps(json_safe(evidence), ensure_ascii=False),
                                     dtype=h5py.string_dtype())
        self.file.create_dataset("task_properties", data=json.dumps(json_safe(properties), ensure_ascii=False),
                                 dtype=h5py.string_dtype())
        self.close()
        with (self.output/(self.name+"_result.json")).open("x", encoding="utf-8") as stream:
            json.dump(json_safe(properties), stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
        with (self.output/"dataset/meta/episode.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(json_safe(dict(episode_index=self.index, length=self.count,
                tasks=[self.cfg.task.instruction], task_properties=properties)), ensure_ascii=False)+"\n")
        self.episode_count += 1
        return properties["independent_adjudication"]


DemoCollectorV0Demo02 = Demo02Collector
