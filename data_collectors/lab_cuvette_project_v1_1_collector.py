"""New-version qualification axes on the unchanged streaming H5 representation."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import h5py

from data_collectors.lab_cuvette_env_v1_collector import LabCuvetteEnvV1Collector, _known_bool, json_text


class LabCuvetteProjectV11Collector(LabCuvetteEnvV1Collector):
    """Only H5 files created by this instance can receive the new fields."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.configuration.get("version") != "Project_v1_1":
            raise ValueError("Project_v1_1 collector requires its independent version config")
        self._fresh_episode_paths = set()

    def begin_episode(self, *args, **kwargs):
        super().begin_episode(*args, **kwargs)
        self._fresh_episode_paths.add(self.path.resolve())
        self.file.attrs.update(schema_version="labsim.lab_cuvette_loading.Project_v1_1.v1",
            qualification_schema="labsim.Project_v1_1.qualifications.v1",
            record_integrity_valid="unknown", physics_trustworthy="unknown",
            success_bc_eligible=False, trajectory_analysis_eligible=False)

    def finish_episode(self, result, independent_score=None):
        path = self.path.resolve()
        if path not in self._fresh_episode_paths or self.file is None:
            raise RuntimeError("Qualification append is restricted to this instance's newly created open episode")
        if isinstance(independent_score, (str, Path)):
            evidence = json.loads(Path(independent_score).read_text(encoding="utf-8"))
        else:
            evidence = dict(independent_score or {})
        labels = super().finish_episode(result, independent_score)
        legacy_labels = copy.deepcopy(labels)
        integrity_errors = list(self._integrity_errors) + list(evidence.get("record_integrity_errors", []))
        if _known_bool(evidence.get("record_integrity_valid")) is False and not integrity_errors:
            integrity_errors.append("independent_score_declared_record_integrity_invalid")
        integrity = not integrity_errors
        physics = _known_bool(evidence.get("physics_trustworthy"))
        domain = str(evidence.get("failure_domain", "unknown"))
        valid = bool(labels["record_valid"] and integrity and physics is True and domain in {"none", "task", "safety", "budget"})
        success_bc = bool(valid and labels["eligible_for_success_bc"] and evidence.get("success_bc_eligible") is True)
        failure_analysis = bool(valid and labels["eligible_for_failure_analysis"] and domain in {"task", "safety", "budget"})
        task_result = copy.deepcopy(evidence.get("task_result", dict(success=labels["task_success"], status="unknown")))
        qualification = dict(schema="labsim.Project_v1_1.qualifications.v1",
            task_result=task_result, record_integrity_valid=integrity,
            record_integrity_source="streaming_collector_checks_at_flush_close",
            record_integrity_errors=integrity_errors, physics_trustworthy=physics,
            physics_trust_scope=evidence.get("physics_trust_scope", "unavailable"),
            failure_domain=domain, success_bc_eligible=success_bc,
            trajectory_analysis_eligible=bool(integrity and self.count > 0),
            eligibility_pending_collector_integrity=False, legacy_collector_labels=legacy_labels)
        labels.update(record_valid=valid, eligible_for_success_bc=success_bc,
                      eligible_for_failure_analysis=failure_analysis,
                      qualification_schema=qualification["schema"],
                      **{key: value for key, value in qualification.items() if key != "schema"})
        # The inherited writer has now flushed and closed this new file. Never
        # open a historic H5 or change the original independent-score dataset.
        with h5py.File(path, "r+") as output:
            for key in ("record_integrity_valid", "record_integrity_source", "physics_trustworthy", "success_bc_eligible",
                        "trajectory_analysis_eligible", "failure_domain", "eligibility_pending_collector_integrity",
                        "record_valid", "eligible_for_success_bc", "eligible_for_failure_analysis"):
                value = labels[key]
                output.attrs[key] = "unknown" if value is None else value
            output.attrs["success"] = success_bc
            output.create_dataset("qualification_json", data=json_text(qualification), dtype=h5py.string_dtype())
            output.create_dataset("task_result_json", data=json_text(task_result), dtype=h5py.string_dtype())
            properties = json.loads(output["task_properties"].asstr()[()])
            properties["labels"].update(labels)
            output["task_properties"][()] = json_text(properties)
        summary = self.output / (self.name + "_result.json")
        properties = json.loads(summary.read_text(encoding="utf-8"))
        properties["labels"].update(labels)
        summary.write_text(json.dumps(properties, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        index = self.output / "dataset/meta/episode.jsonl"
        lines = index.read_text(encoding="utf-8").splitlines()
        last = json.loads(lines[-1])
        if last["episode_id"] != self.episode_id:
            raise RuntimeError("Fresh collection index changed during finalization")
        last["labels"].update(labels)
        lines[-1] = json_text(last)
        index.write_text("\n".join(lines) + "\n", encoding="utf-8")
        self._fresh_episode_paths.remove(path)
        return labels
