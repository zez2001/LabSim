"""Export two real samples via the existing loader; never train or rewrite H5."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

import h5py
import numpy as np

from demos.lab_cuvette_demo03.analyze import PHASES, json_safe, load_json, sha256, write_new
from policy.dataset.minimal_pick_dataset import MinimalPickDataset


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episode", type=Path, required=True)
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    episode, index, output = args.episode.resolve(), args.index.resolve(), args.output.resolve()
    required = ("independent_score.json", "adjudication.json", "execution_summary.json")
    assert all((episode / f).is_file() for f in required), "Never open an in-progress episode"
    score = load_json(episode / "independent_score.json")
    assert score["workflow_success"] is True and score["data_eligible"] is True
    output.mkdir(parents=True, exist_ok=False)
    raw = episode / "dataset/episode_0000.h5"
    before = sha256(raw)
    shape_meta = {"obs": {"camera_1_rgb": {"type": "rgb", "shape": [3, 256, 256]},
                          "camera_2_rgb": {"type": "rgb", "shape": [3, 256, 256]},
                          "agent_pose": {"type": "low_dim", "shape": [8]}}, "action": {"shape": [8]}}
    dataset = MinimalPickDataset(shape_meta, str(index), horizon=16, n_obs_steps=1, val_ratio=0, policy_type="act")
    assert len(dataset.episode_ids) == 1, "This sample export binds a single real episode"
    with h5py.File(index, "r") as indexed:
        group = indexed[dataset.episode_ids[0]]
        assert group.attrs["independent_score_sha256"] == sha256(episode / "independent_score.json")
        assert Path(group["actions"].file.filename).resolve() == raw
    with h5py.File(raw, "r") as h:
        codes = h["phase_code"][:]
        phases = ["EXTRACT", "INSERT"]
        offsets = [30, 60]
        indices = [int(np.flatnonzero(codes == PHASES.index(phase))[0]) + offset for phase,offset in zip(phases, offsets)]
        assert all(codes[i] == PHASES.index(phase) for i,phase in zip(indices, phases))
        assert all(dataset.sequences[i] == (dataset.episode_ids[0], i) for i in indices)
        batch = dataset.collate_fn([dataset[i] for i in indices])
        arrays = {"obs_camera_1_rgb": batch["obs"]["camera_1_rgb"].numpy(),
                  "obs_camera_2_rgb": batch["obs"]["camera_2_rgb"].numpy(),
                  "obs_agent_pose": batch["obs"]["agent_pose"].numpy(),
                  "action": batch["action"].numpy(), "is_pad": batch["is_pad"].numpy(),
                  "source_control_indices": np.array(indices), "source_timestamps_s": h["timestamp"][indices],
                  "source_phases": np.array(phases)}
        for j,i in enumerate(indices):
            assert np.array_equal(arrays["action"][j], h["actions"][i:i+16])
            assert np.array_equal(arrays["obs_agent_pose"][j], h["agent_pose"][i])
            for key in ("camera_1_rgb", "camera_2_rgb"):
                reconstructed = np.rint(arrays["obs_" + key][j] * 255).astype(np.uint8)
                assert np.array_equal(reconstructed, h[key][i])
        assert not arrays["is_pad"].any() and np.isfinite(arrays["action"]).all()
        attrs = {key: h.attrs[key] for key in ("scene_version", "scene_mode", "data_scope", "source_slot_id",
            "target_seat_id", "asset_manifest_sha256", "native_pair_success", "real_calibrated", "data_eligible")}
    movie = episode / "main.mp4"
    metadata = json_safe(dict(schema="labsim.V0_demo03.actual_batch_sample.v1", source_episode=str(episode),
        raw_h5_path=str(raw), raw_h5_sha256=before, independent_score_sha256=sha256(episode / "independent_score.json"),
        index_path=str(index), loader="policy.dataset.minimal_pick_dataset.MinimalPickDataset",
        control_indices=indices, timestamps_s=arrays["source_timestamps_s"], phases=phases,
        **attrs, main_video_same_episode=str(movie), main_video_sha256=sha256(movie),
        action_semantics="7 absolute arm joint targets(rad) plus1 symmetric finger target(m),16future commands per sample",
        policy_inputs="dual normalized RGB and8joint agent_pose only; privileged geometry is not policy input",
        optimizer_or_training_executed=False, full_episode_included=False,
        scope="two real samples from the same continuous episode as the final main movie; not a complete episode"))
    arrays["metadata_json"] = np.array(json.dumps(metadata, ensure_ascii=False))
    destination = output / "batch_sample.npz"
    with destination.open("xb") as stream:
        np.savez_compressed(stream, **arrays)
    with np.load(destination, allow_pickle=False) as loaded:
        assert all(np.array_equal(loaded[k], value) for k,value in arrays.items())
    metadata.update(saved_sample_path=str(destination), saved_sample_sha256=sha256(destination),
        saved_sample_bytes=destination.stat().st_size, raw_h5_unchanged=sha256(raw) == before,
        exact_source_actions_verified=True, exact_source_agent_pose_verified=True,
        exact_source_RGB_reconstruction_verified=True, sample_reload_allow_pickle_false_passed=True,
        batch_shapes={k: list(v.shape) for k,v in arrays.items()}, export_script_sha256=sha256(__file__))
    assert metadata["raw_h5_unchanged"] is True
    write_new(output / "verification.json", metadata)
    write_new(output / "manifest.json", dict(schema="labsim.V0_demo03.readable_batch_sample.v1",
        source_episode=str(episode), sha256=sha256(destination), bytes=destination.stat().st_size,
        source_h5_sha256=before, same_episode_as_final_main_movie=True, full_episode_included=False))
    print(json.dumps(dict(output=str(output), control_indices=indices, source_phases=phases,
                         samples=2, unchanged=True), ensure_ascii=False))


if __name__ == "__main__":
    main()
