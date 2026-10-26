"""CPU diagnostic sequencing; these stubs make no physical success claims."""
import copy
import json
from types import SimpleNamespace

import numpy as np

from demos.lab_cuvette_project_v1_1 import probes


def test_original_prefix_preserves_arguments_but_refreshes_command_identity(tmp_path, monkeypatch):
    monkeypatch.setattr(probes, "ROOT", tmp_path)
    source = tmp_path / "outputs/lab_cuvette_loading/Project_v1/gpt_formal5_01/attempt_0001/episode_0000/gpt_control/policy_trace.jsonl"
    source.parent.mkdir(parents=True)
    original = dict(episode_id="historic", observation_id="historic:9", action_id="historic-action",
        mode="ee_delta", values=[.001, 0, 0, 0, 0, 0], frame="world", duration_s=.3)
    events = [dict(tool_call=dict(name="move_ee", arguments=json.dumps(original))),
        dict(model_tool_calls=[dict(name="wait", arguments=dict(duration_s=.5))]),
        dict(tool_call=dict(name="wait", arguments=dict(duration_s=1.)))]
    source.write_text("\n".join(json.dumps(event) for event in events) + "\n")
    destination = tmp_path / "new_episode"
    destination.mkdir()
    calls = []
    def call(name, **arguments):
        calls.append((name, arguments))
        return len(calls) < 2  # The failed second action prevents a third.
    probe = SimpleNamespace(task=SimpleNamespace(episode_dir=destination), call=call)
    probes.original_prefix(probe, 1)
    assert calls == [("move_ee", {key: value for key, value in original.items()
        if key not in ("episode_id", "observation_id", "action_id")}), ("wait", dict(duration_s=.5))]
    evidence = json.loads((destination / "replay_source.json").read_text())
    assert evidence["diagnostic_not_GPT_run"] is True
    assert evidence["action_prefix_preserved"] is True
    assert len(evidence["sha256"]) == 64


def test_free_space_signed_axes_reset_to_fixed_anchor_without_accumulating_residuals():
    anchors, snapshots, tool_calls = [], [], []
    task = SimpleNamespace(ended=False)
    pose = dict(position_m=[.1, .2, .3], quaternion_wxyz=[1., 0, 0, 0])
    probe = SimpleNamespace(task=task, records=[], tools=SimpleNamespace(observe=lambda: dict(TCPpose=copy.deepcopy(pose))))
    probe.snapshot = snapshots.append
    probe.to_position = lambda target: anchors.append(copy.deepcopy(target)) or True
    def delta(xyz, **kwargs):
        probe.records.append(dict(delta=list(xyz), options=kwargs))
        return True
    probe.delta = delta
    probe.call = lambda name, **kwargs: tool_calls.append((name, kwargs)) or True
    probes.free_space(probe)
    definitions = [record["probe_definition"] for record in probe.records if "probe_definition" in record]
    assert len(definitions) == 72
    assert all(np.allclose(anchor, pose["position_m"]) for anchor in anchors)
    for pose_index in (0, 1):
        for amplitude in (.001, .005, .02, .04):
            selected = [item for item in definitions if item["pose_index"] == pose_index
                and np.isclose(abs(item["amplitude_m"]), amplitude)]
            assert sum(item["amplitude_m"] for item in selected) == 0
    assert snapshots == ["free_pose_0", "free_pose_1"]
    assert [call[0] for call in tool_calls] == ["wait", "gripper", "gripper", "wait", "gripper", "gripper"]


def test_run_probe_labels_diagnostic_without_teacher_or_gpt_calls(tmp_path, monkeypatch):
    resets = []
    task = SimpleNamespace(ended=False, release_contract=dict(frozen_scene_sha256="a" * 64))
    def finalize(reason, failure_type):
        task.ended = True
        task._result = dict(termination_reason=reason, failure_type=failure_type)
    task.finalize_episode = finalize
    facade = SimpleNamespace(task=task, reset=lambda seed, options: resets.append((seed, options)))
    monkeypatch.setattr(probes, "ManualProbe", lambda env: SimpleNamespace(task=task, records=[]))
    monkeypatch.setattr(probes, "free_space", lambda probe: None)
    assert probes.run_probes(facade, "free-space", [1, 2], tmp_path) == 0
    assert len(resets) == 1
    assert resets[0][1]["teacher"] is False
    assert resets[0][1]["policy_id"] == "deterministic_control_diagnostic"
    manifest = json.loads((tmp_path / "run_manifest.json").read_text())
    assert manifest["model_calls"] == 0 and manifest["diagnostic_not_GPT_demonstration"] is True
    assert manifest["episodes_completed"] == 1
