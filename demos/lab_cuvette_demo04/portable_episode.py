"""Self-contained copy of one real completed episode, including auxiliary control.

All source datasets/labels are retained. Failed or unknown task outcomes remain
failed/unknown; diagnostic reads reuse existing loader methods without promoting
any H5 success attribute. No simulation, inference or training is performed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile

import h5py
import numpy as np
from omegaconf import OmegaConf

from demos.lab_cuvette_demo03.analyze import json_safe, load_json, sha256, write_new
from demos.lab_cuvette_demo04.collector import canonical_schedule


def iter_records(path):
    decoder = json.JSONDecoder()
    with Path(path).open(encoding="utf-8") as stream:
        buffer, position, started = "", 0, False
        while True:
            while position < len(buffer) and (buffer[position].isspace() or buffer[position] == ","):
                position += 1
            if position == len(buffer):
                chunk = stream.read(1024 * 1024)
                if not chunk:
                    raise ValueError("Incomplete physics JSON array")
                buffer, position = chunk, 0
                continue
            if not started:
                if buffer[position] != "[":
                    raise ValueError("Expected physics JSON array")
                started, position = True, position + 1
                continue
            if buffer[position] == "]":
                return
            try:
                row, end = decoder.raw_decode(buffer, position)
            except json.JSONDecodeError:
                chunk = stream.read(1024 * 1024)
                if not chunk:
                    raise ValueError("Incomplete physics JSON record")
                buffer, position = buffer[position:] + chunk, 0
                continue
            position = end
            if not isinstance(row, dict):
                raise ValueError("Physics row is not an object")
            yield row


def dataset_digest(dataset):
    """Hash all logical values, including variable-length UTF-8, with bounded RAM."""
    digest = hashlib.sha256()
    if dataset.shape == ():
        blocks = [dataset[()]]
    else:
        blocks = (dataset[start:start+16] for start in range(0, len(dataset), 16))
    for block in blocks:
        data = np.asarray(block)
        if data.dtype.kind in "OUS":
            for item in data.reshape(-1):
                encoded = item if isinstance(item, bytes) else str(item).encode()
                digest.update(len(encoded).to_bytes(8, "little"))
                digest.update(encoded)
        else:
            digest.update(np.ascontiguousarray(data).tobytes())
    return digest.hexdigest()


def auxiliary_from_physics(raw, physics):
    times, hz = raw["next_timestamp"][:], float(raw.attrs["physics_hz"])
    wanted = {int(round(t*hz)): i for i,t in enumerate(times)}
    n = len(times)
    q, effort, grip = np.full((n, 9), np.nan), np.full(n, np.nan), np.full(n, np.nan)
    matched, phase_match, time_match = np.zeros(n, bool), True, True
    names = json.loads(raw.attrs["phase_names_json"])
    phases = raw["phase_code"][:]
    for step,row in enumerate(iter_records(physics)):
        if step not in wanted:
            continue
        i = wanted[step]
        time_match &= bool(row.get("physics_step") == step and abs(float(row["t"]) - times[i]) < 1e-8)
        phase_match &= row.get("phase") == names[int(phases[i])]
        if np.shape(row.get("command_q")) == (9,):
            q[i] = row["command_q"]
        if row.get("gripper_effort_limit_N") is not None:
            effort[i] = row["gripper_effort_limit_N"]
        if row.get("gripper_target_m") is not None:
            grip[i] = row["gripper_target_m"]
        matched[i] = True
    available = matched & np.isfinite(q).all(1) & np.isfinite(effort) & np.isfinite(grip)
    actions_equal = bool(np.array_equal(q[:,:8].astype(np.float32), raw["actions"][:]))
    checks = dict(all_control_endpoints_found=bool(matched.all()), same_physics_step_time=bool(time_match),
        same_action_phase=bool(phase_match), all_auxiliary_measured=bool(available.all()),
        exact_float32_action_match=actions_equal,
        command_fingers_symmetric=bool(np.allclose(q[:,7], q[:,8], atol=1e-9, rtol=0)))
    values = dict(command_q=q, gripper_effort_limit_N=effort, gripper_target_m=grip, available=available)
    if "control_auxiliary" in raw:
        checks["runtime_auxiliary_matches_saved_physics"] = all(
            key in raw["control_auxiliary"] and np.array_equal(raw["control_auxiliary"][key][:], value, equal_nan=True)
            for key,value in values.items())
    return values, checks


def no_external_links(group):
    links = []
    def visit(current, prefix=""):
        for key in current:
            name = prefix + key
            link = current.get(key, getlink=True)
            if not isinstance(link, h5py.HardLink):
                links.append(dict(path=name, link_type=type(link).__name__))
            elif isinstance(current[key], h5py.Group):
                visit(current[key], name + "/")
    visit(group)
    return links


def read_batch(portable, output):
    """Try the normal success filter, then an explicit non-training diagnostic view."""
    from policy.dataset.minimal_pick_dataset import MinimalPickDataset
    cameras = ["camera_1_rgb", "camera_2_rgb"]
    shape_meta = {"obs": {**{key: {"type": "rgb", "shape": [3,256,256]} for key in cameras},
        "agent_pose": {"type": "low_dim", "shape": [8]}}, "action": {"shape": [8]}}
    try:
        dataset = MinimalPickDataset(shape_meta, str(portable), horizon=16, n_obs_steps=1, val_ratio=0, policy_type="act")
        batch = dataset.collate_fn([dataset[0]])
        mode, rejection = "existing_normal_success_filtered_loader", None
    except ValueError as exc:
        if "no complete successful episodes" not in str(exc):
            raise
        rejection = str(exc)
        # The temporary index deliberately retains the original false success
        # label. A diagnostic view invokes the existing __getitem__/collate code;
        # it is not a trained dataset and never changes raw/index success=true.
        with tempfile.TemporaryDirectory(prefix="labsim_diagnostic_read_") as temporary:
            index = Path(temporary) / "diagnostic_read_index.h5"
            with h5py.File(index, "x") as h:
                h.attrs.update(scope="diagnostic_read_only_not_learning_success_index", training_eligible=False)
                h["episode_0000"] = h5py.ExternalLink(str(portable), "/episode_0000")
            view = SimpleNamespace(path=index, horizon=16, n_obs_steps=1, policy_type="act", camera_names=cameras,
                lengths={"episode_0000": 0}, sequences=[("episode_0000", 0)])
            with h5py.File(portable, "r") as h:
                view.lengths["episode_0000"] = len(h["episode_0000/actions"])
                assert not bool(h["episode_0000"].attrs.get("success", False))
            sample = MinimalPickDataset.__getitem__(view, 0)
            batch = MinimalPickDataset.collate_fn([sample])
        mode = "diagnostic_read_only_existing_getitem_and_collate; normal_success_filter_rejected"
    arrays = {"obs_" + k: v.numpy() for k,v in batch["obs"].items()}
    arrays.update(action=batch["action"].numpy(), is_pad=batch["is_pad"].numpy())
    # Validate against the same raw group; constructor chooses one episode only.
    with h5py.File(portable, "r") as h:
        group = h["episode_0000"]
        n = len(group["actions"])
        expected = group["actions"][np.clip(np.arange(16), 0, n-1)] if n >= 16 else np.stack([group["actions"][min(i,n-1)] for i in range(16)])
        assert np.array_equal(arrays["action"][0], expected)
        assert np.array_equal(arrays["obs_agent_pose"][0], group["agent_pose"][0])
        for key in cameras:
            assert np.array_equal(np.rint(arrays["obs_"+key][0]*255).astype(np.uint8), group[key][0])
        outcome = {key: json_safe(group.attrs.get(key)) for key in ("success", "workflow_success", "data_eligible", "native_pair_success", "real_calibrated")}
    with (output / "read_batch.npz").open("xb") as stream:
        np.savez_compressed(stream, **arrays)
    with np.load(output / "read_batch.npz", allow_pickle=False) as saved:
        assert all(np.array_equal(saved[k], v) for k,v in arrays.items())
    return dict(mode=mode, normal_loader_rejection=rejection, original_outcome_labels=outcome,
        batch_read_executed=True, optimizer_or_training_executed=False,
        training_success_index_eligible=bool(outcome.get("success") and outcome.get("data_eligible")),
        raw_success_labels_unchanged=True, arrays={k:list(v.shape) for k,v in arrays.items()},
        exact_source_actions_state_and_RGB_verified=True, sample_sha256=sha256(output / "read_batch.npz"))


def export_episode(episode, output):
    episode, output = Path(episode).resolve(), Path(output).resolve()
    for marker in ("adjudication.json", "execution_summary.json"):
        if not (episode / marker).is_file():
            raise ValueError("Episode not confirmed closed: missing " + marker)
    raw_files = list((episode / "dataset").glob("episode_*.h5"))
    if len(raw_files) != 1:
        raise ValueError("Expected exactly one raw episode H5")
    raw_path, physics_path = raw_files[0], episode / "physics_records.json"
    protected = [raw_path, physics_path, episode / "config.yaml", episode / "events.json"]
    before = {str(p): sha256(p) for p in protected}
    output.mkdir(parents=True, exist_ok=False)
    destination = output / "episode_data.hdf5"
    with h5py.File(raw_path, "r") as raw:
        if not bool(raw.attrs.get("complete", False)) or not len(raw["actions"]):
            raise ValueError("Raw episode must be closed, complete and nonempty")
        auxiliary, alignment = auxiliary_from_physics(raw, physics_path)
        if not all(alignment.values()):
            raise ValueError("Saved command/physics/auxiliary alignment failed: " + str(alignment))
        if raw.attrs.get("control_schedule_json"):
            schedule = str(raw.attrs["control_schedule_json"])
            schedule_hash = hashlib.sha256(schedule.encode()).hexdigest()
            if raw.attrs.get("control_schedule_sha256") != schedule_hash:
                raise ValueError("Runtime schedule hash mismatch")
            schedule_origin = "runtime collector metadata"
        else:
            config = OmegaConf.load(episode / "config.yaml")
            snapshots = list((episode.parent / "source_snapshot/demos").glob("*/run.py"))
            schedule, schedule_hash = canonical_schedule(config, snapshots[0] if len(snapshots)==1 else None)
            schedule_origin = "derived from preserved config/controller snapshot for historical-tool validation; not a new run"
        with h5py.File(destination, "x") as portable:
            portable.attrs.update(schema="labsim.portable_real_episode.v1", format_version="V0_demo04",
                self_contained=True, source_H5_sha256=before[str(raw_path)], original_labels_preserved=True,
                source_scene_version=str(raw.attrs.get("scene_version", "unknown")), source_episode_provenance=str(episode),
                portability_scope="all datasets copied; provenance absolute paths are strings only, never live external data links")
            group = portable.create_group("episode_0000")
            group.attrs.update(dict(raw.attrs))
            for key in raw:
                raw.copy(key, group, name=key, expand_external=True, expand_soft=True, expand_refs=True)
            if "control_auxiliary" not in group:
                aux_group = group.create_group("control_auxiliary")
                for key,value in auxiliary.items():
                    aux_group.create_dataset(key, data=value, compression="lzf")
            group.attrs.update(control_schedule_json=schedule, control_schedule_sha256=schedule_hash,
                portable_auxiliary_origin="exact original physics-step endpoint join; runtime auxiliary compared when present")
            portable.create_dataset("control_schedule_json", data=schedule, dtype=h5py.string_dtype())
        copy_checks = {}
        with h5py.File(destination, "r") as portable:
            group = portable["episode_0000"]
            def verify(name,obj):
                if isinstance(obj, h5py.Dataset):
                    copied = group[name]
                    copy_checks[name] = dict(shape_equal=obj.shape==copied.shape, dtype_equal=obj.dtype==copied.dtype,
                        full_value_sha256=dataset_digest(obj), copied_full_value_sha256=dataset_digest(copied))
            raw.visititems(verify)
            assert all(v["shape_equal"] and v["dtype_equal"] and v["full_value_sha256"]==v["copied_full_value_sha256"] for v in copy_checks.values())
            links = no_external_links(portable)
            assert not links
            labels = {key: json_safe(raw.attrs.get(key)) for key in ("success", "workflow_success", "data_eligible", "native_pair_success", "real_calibrated")}
            assert all(json_safe(group.attrs.get(k)) == value for k,value in labels.items())
            frames = len(group["actions"])
    batch = read_batch(destination, output)
    unchanged = {str(p): sha256(p)==digest for p,digest in ((Path(k),v) for k,v in before.items())}
    assert all(unchanged.values())
    result = dict(schema="labsim.V0_demo04.portable_episode_audit.v1", source_episode=str(episode),
        source_scene_version=str(OmegaConf.load(episode / "config.yaml").get("version", "unknown")),
        portable_file=str(destination), portable_sha256=sha256(destination), portable_bytes=destination.stat().st_size,
        complete_frames=frames, original_outcome_labels=labels, source_files_sha256=before,
        source_files_unchanged=unchanged, copied_dataset_count=len(copy_checks), all_source_dataset_values_verified=True,
        dataset_copy_checks=copy_checks, external_or_soft_links=links, all_data_self_contained=True,
        auxiliary_endpoint_checks=alignment, control_schedule_sha256=schedule_hash, control_schedule_origin=schedule_origin,
        config_source_sha256=before[str(episode / "config.yaml")], loader=batch,
        runtime_executed_by_export=False, optimizer_or_training_executed=False,
        source_version_not_relabelled=True, tool_source_sha256=sha256(__file__))
    write_new(output / "portable_audit.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episode", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="new directory")
    args = parser.parse_args()
    result = export_episode(args.episode, args.output)
    print(json.dumps({k:result[k] for k in ("portable_file", "complete_frames", "portable_bytes", "all_data_self_contained", "loader")}))


if __name__ == "__main__":
    main()
