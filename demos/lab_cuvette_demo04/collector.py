"""V0_demo04 native-nominal aligned collector with explicit auxiliary controls.

Previous collectors and raw episodes are untouched. Failed/unknown episodes
close for diagnostic use; only independently bound physical success qualifies
for the learning-success index. Native pairing requires that same complete
workflow and the geometry gate. Real calibration is never claimed here.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import h5py
import numpy as np
from omegaconf import OmegaConf

from demos.lab_cuvette_demo03.analyze import PHASES, json_safe, load_json, sha256
from demos.lab_cuvette_demo03.collector import Demo03Collector

PHASE_NAMES = tuple(PHASES) + ("GATE_RETRACT", "DIAGNOSTIC_HOLD", "JAM_RETRACT")


def canonical_schedule(cfg, controller_file=None):
    config = OmegaConf.to_container(cfg, resolve=True) if OmegaConf.is_config(cfg) else dict(cfg)
    names = list(config.get("control", {}).get("phases_s", {}))
    if not names:
        names = list(PHASE_NAMES if config.get("version") == "V0_demo04" else PHASES)
    payload = dict(schema="labsim.V0_demo04.control_schedule.v1", configuration=json_safe(config),
        phase_names=names, schedule_encoder_source_sha256=sha256(__file__),
        auxiliary_action_semantics="per-control symmetric effort cap_N, raw requested finger target_m, full9joint applied position command",
        controller_source_sha256=sha256(controller_file) if controller_file and Path(controller_file).is_file() else None)
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return text, hashlib.sha256(text.encode()).hexdigest()


def collector_metadata(contract, schedule_json, schedule_sha256):
    contract = dict(contract or {})
    source, target = contract.get("source_slot", {}), contract.get("target_seat", {})
    instrument_count = contract.get("instrument_count", contract.get("scene_correspondence", {}).get("instrument_count"))
    values = dict(schema_version="labsim.lab_cuvette_loading.V0_demo04.v1", scene_version="V0_demo04",
        task="lab_cuvette_loading_V0_demo04", scene_mode="native_nominal",
        data_scope="lab_cuvette_loading_V0_demo04_native_nominal",
        source_slot_known=bool(source.get("id")), target_seat_known=bool(target.get("id")),
        scene_correspondence_accepted=(contract.get("version") == "V0_demo04"
            and contract.get("scene_mode") == "native_nominal"
            and contract.get("scene_correspondence", {}).get("accepted") is True),
        action_semantics="absolute_7_arm_rad_and_symmetric_finger_metre",
        observation_alignment="obs_before_action; next_state_after_explicit_substeps",
        phase_names_json=json.dumps(list(PHASE_NAMES)), real_calibrated=False, native_pair_success=False,
        cad_pair_verified=False, success=False, complete=False, workflow_success=False,
        data_eligible=False, full_task_eligible=False, full_success=False,
        diagnostic_read_eligible=False, control_schedule_json=schedule_json,
        control_schedule_sha256=schedule_sha256, control_auxiliary_alignment="same post-action endpoint as next_timestamp",
        control_auxiliary_units="command_q:7arm_rad+2finger_m; gripper_effort_limit_N:N per finger; gripper_target_m:m requested before command limiting")
    for key,value in (("source_slot_id", source.get("id")), ("target_seat_id", target.get("id")),
        ("target_is_internal_chamber", target.get("inside_sample_chamber")),
        ("asset_manifest_sha256", contract.get("asset_manifest_sha256")), ("instrument_count", instrument_count)):
        if value is not None:
            values[key] = value
    text = json.dumps(json_safe(contract), ensure_ascii=False, sort_keys=True, allow_nan=False)
    values.update(scene_contract_json=text, scene_contract_canonical_sha256=hashlib.sha256(text.encode()).hexdigest())
    return values


def qualification_reasons(metadata, score, output, frames, final_timestamp, observed_phases):
    checks = dict(new_score_schema=score.get("schema") == "labsim.V0_demo04.independent.v1",
        new_score_scene=score.get("scene_version") == "V0_demo04",
        native_nominal_scope=score.get("scene_mode") == metadata.get("scene_mode") == "native_nominal",
        single_instrument_bound=metadata.get("instrument_count") == 1,
        independently_accepted_geometry=score.get("geometry_gate_passed") is True,
        independently_successful_workflow=score.get("workflow_success") is True,
        independently_eligible=score.get("data_eligible") is True,
        independently_accepted_scene=score.get("scene_correspondence_accepted") is True,
        collector_accepted_scene=metadata.get("scene_correspondence_accepted") is True,
        no_real_calibration_claim=score.get("real_calibrated") is False,
        same_episode=bool(score.get("source_episode")) and Path(score["source_episode"]).resolve() == Path(output).resolve(),
        same_asset_manifest=bool(metadata.get("asset_manifest_sha256")) and metadata.get("asset_manifest_sha256") == score.get("asset_manifest_sha256"),
        same_source_slot=bool(metadata.get("source_slot_id")) and metadata.get("source_slot_id") == score.get("source_slot_id"),
        same_internal_target=metadata.get("target_is_internal_chamber") is True and bool(metadata.get("target_seat_id"))
            and metadata.get("target_seat_id") == score.get("target_seat_id"),
        actual_transitions_present=frames > 0,
        complete_workflow_observed=list(observed_phases) == list(PHASES),
        same_terminal_state=bool(final_timestamp is not None and score.get("trajectory_end_time_s") is not None
            and abs(float(final_timestamp)-float(score["trajectory_end_time_s"])) <= 1e-6),
        saved_physics_hash_present=bool(score.get("physics_records_sha256")),
        saved_events_hash_present=bool(score.get("events_sha256")))
    return [key for key,value in checks.items() if value is not True]


class Demo04Collector(Demo03Collector):
    def __init__(self, cfg, output_dir, save_video=True, *, scene_contract=None):
        super().__init__(cfg, output_dir, save_video, scene_contract=scene_contract)
        # Keep the historical eleven workflow codes stable and append diagnostic
        # phases. They are observable, but cannot qualify as the full workflow.
        self.cfg.control.phases_s = {phase: 0.0 for phase in PHASE_NAMES}
        controller = Path(__file__).with_name("run.py")
        schedule, digest = canonical_schedule(cfg, controller)
        self.metadata = collector_metadata(scene_contract, schedule, digest)

    def begin_episode(self, index, initial_position):
        super().begin_episode(index, initial_position)
        self.file.attrs.update(self.metadata)
        self.file.attrs["control_auxiliary_unknown"] = "NaN and available=false; never zero-filled"

    def cache_transition(self, state, action, next_state, result):
        super().cache_transition(state, action, next_state, result)
        auxiliary = next_state.get("control_aux", {})
        q = auxiliary.get("command_q")
        q = np.asarray(q, float) if q is not None and np.shape(q) == (9,) else np.full(9, np.nan)
        effort = auxiliary.get("gripper_effort_limit_N")
        target = auxiliary.get("gripper_target_m")
        effort = float(effort) if effort is not None else np.nan
        target = float(target) if target is not None else np.nan
        self.count -= 1
        self._append("control_auxiliary/command_q", q)
        self._append("control_auxiliary/gripper_effort_limit_N", np.float64(effort))
        self._append("control_auxiliary/gripper_target_m", np.float64(target))
        self._append("control_auxiliary/available", np.bool_(np.isfinite(q).all() and np.isfinite([effort, target]).all()))
        self.count += 1

    def finish_episode(self, result, independent_score=None):
        if self.file is None:
            raise RuntimeError("No open V0_demo04 episode")
        self.file.flush()
        evidence, source_hash, rejection = None, None, ["independent_score_not_provided"]
        if independent_score is not None and Path(independent_score).is_file():
            path = Path(independent_score)
            evidence, source_hash = load_json(path), sha256(path)
            last = float(self.file["next_timestamp"][-1]) if self.count else None
            codes = self.file["phase_code"][:] if self.count else []
            phase_names = json.loads(self.file.attrs["phase_names_json"])
            observed = list(dict.fromkeys(phase_names[int(code)] for code in codes if 0 <= int(code) < len(phase_names)))
            rejection = qualification_reasons(self.metadata, evidence, self.output, self.count, last, observed)
            for key,name in (("physics_records_sha256", "physics_records.json"), ("events_sha256", "events.json")):
                raw = self.output / name
                if not raw.is_file() or evidence.get(key) != sha256(raw):
                    rejection.append("independent_score_does_not_match_" + name)
            if not self.count or "control_auxiliary/available" not in self.file or not self.file["control_auxiliary/available"][:].all():
                rejection.append("auxiliary_control_not_fully_measured")
        elif independent_score is not None:
            rejection = ["independent_score_file_missing"]
        eligible = not rejection
        geometry_pass = bool(evidence and evidence.get("geometry_gate_passed") is True)
        native = bool(eligible and geometry_pass and evidence.get("native_pair_success") is True)
        diagnostic = bool(self.count > 0)
        workflow_verdict = evidence.get("workflow_success") if evidence else None
        terminal_verdict = "SUCCESS" if eligible else ("FAILED_OR_BLOCKED" if workflow_verdict is False else "UNADJUDICATED")
        self.file.attrs.update(complete=True, frames=self.count, success=eligible, workflow_success=eligible,
            full_success=eligible, full_task_eligible=eligible, data_eligible=eligible,
            native_pair_success=native, cad_pair_verified=native, real_calibrated=False,
            geometry_gate_passed=geometry_pass, diagnostic_read_eligible=diagnostic,
            independent_adjudication_available=evidence is not None,
            terminal_verdict=terminal_verdict, workflow_verdict_json=json.dumps(workflow_verdict),
            status=result.get("status", "UNKNOWN"), reason=result.get("reason", result.get("status", "UNKNOWN")),
            qualification_rejection_json=json.dumps(rejection), independent_score_sha256=source_hash or "unavailable")
        if self.count:
            if "done" in self.file:
                self.file["done"][-1] = True
            if "reward" in self.file:
                self.file["reward"][-1] = np.float32(eligible)
        adjudication = dict(workflow_success=eligible, geometry_gate_passed=geometry_pass,
            native_pair_success=native, real_calibrated=False, data_eligible=eligible,
            diagnostic_read_eligible=diagnostic, rejection_reasons=rejection,
            workflow_verdict=workflow_verdict,
            score_sha256=source_hash, score_source=str(independent_score) if independent_score else None)
        properties = dict(result, independent_adjudication=adjudication)
        if evidence is not None:
            self.file.create_dataset("independent_score_json", data=json.dumps(json_safe(evidence), ensure_ascii=False), dtype=h5py.string_dtype())
        self.file.create_dataset("task_properties", data=json.dumps(json_safe(properties), ensure_ascii=False), dtype=h5py.string_dtype())
        self.close()
        with (self.output / (self.name + "_result.json")).open("x", encoding="utf-8") as stream:
            json.dump(json_safe(properties), stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
        with (self.output / "dataset/meta/episode.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(json_safe(dict(episode_index=self.index, length=self.count,
                tasks=[self.cfg.task.instruction], task_properties=properties)), ensure_ascii=False) + "\n")
        self.episode_count += 1
        return adjudication
