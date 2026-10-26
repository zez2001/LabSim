"""Export a complete Project_v1 episode with smaller RGB, never shorter time.

All transitions, raw/executed actions, states, timestamps, events, labels and
terminal observations are retained. Both policy RGB streams are resized with
OpenCV INTER_AREA. Other values are losslessly recompressed; author filesystem
paths in metadata become logical references with a public sanitization ledger.
The source HDF5 is read-only and its content hash is rechecked after export.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if not (__name__ == "__main__" and any(arg in sys.argv[1:] for arg in ("-h", "--help"))):
    try:
        import cv2
        import h5py
        import numpy as np
        from utils.episode_selection import episode_matches_filter
    except ModuleNotFoundError as error:
        raise SystemExit("Missing data dependency " + str(error.name) + ". Run this command with "
            "the declared LabSim Python selected by ./labsim doctor (LABSIM_PYTHON). "
            "This exporter does not install or modify the Isaac/model environments.") from None

CAMERAS = ("side_camera_rgb", "wrist_camera_rgb")
SECRET = re.compile(r"(?:sk-user-|hf_)[A-Za-z0-9]{20,}")
AUTHOR_PATH = re.compile(r"/(?:home|Users|tmp|media|mnt|private)/[^\s\"'<>\[\]{},;]+")
SCHEMA = "labsim.Project_v1.compact_public_episode.v1"


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def plain(value):
    if isinstance(value, dict):
        return {str(k): plain(v) for k, v in value.items()}
    if isinstance(value, np.ndarray):
        return plain(value.tolist())
    if isinstance(value, (tuple, list)):
        return [plain(v) for v in value]
    if isinstance(value, np.generic):
        return plain(value.item())
    if isinstance(value, bytes):
        return value.decode("utf-8")
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def logical_path(value):
    # These are provenance strings, not runtime remapping of task geometry.
    if "/assets/" in value:
        return "asset://" + value.split("/assets/", 1)[1]
    if "/LabSim/" in value:
        return "repo://" + value.split("/LabSim/", 1)[1]
    if "/site-packages/" in value:
        return "runtime://python-site/" + value.split("/site-packages/", 1)[1]
    name = value.rstrip("/").rsplit("/", 1)[-1]
    if name in ("python", "python3", "python3.11"):
        return "runtime://isaac-python"
    identifier = hashlib.sha256(value.encode()).hexdigest()[:16]
    return "provenance://path/" + identifier + "/" + name


def sanitized_text(value):
    """Sanitize filesystem provenance only; USD prim paths stay unchanged."""
    if SECRET.search(value):
        raise ValueError("Credential-like content found in source metadata; publication aborted")
    aliases = []
    def replace(match):
        logical = logical_path(match.group(0))
        aliases.append(logical)
        return logical
    result = AUTHOR_PATH.sub(replace, value)
    return result, aliases


class Sanitizer:
    def __init__(self):
        self.ledger = {}

    def value(self, value, context):
        if isinstance(value, str):
            transformed, aliases = sanitized_text(value)
            if transformed != value:
                entry = self.ledger.setdefault(context, dict(
                    field=context, values_changed=0, path_occurrences_replaced=0,
                    transformation="Replace author/cache filesystem provenance strings with logical IDs; numeric values unchanged",
                    logical_aliases=set()))
                entry["values_changed"] += 1
                entry["path_occurrences_replaced"] += len(aliases)
                entry["logical_aliases"].update(aliases)
            return transformed
        if isinstance(value, bytes):
            return self.value(value.decode("utf-8"), context).encode("utf-8")
        if isinstance(value, np.ndarray) and value.dtype.kind in "OUS":
            converted = [self.value(v, context) for v in value.reshape(-1)]
            # Let HDF5 choose storage for the (usually scalar) string attrs.
            return np.asarray(converted, dtype=object).reshape(value.shape)
        return value

    def entries(self):
        return [{**entry, "logical_aliases": sorted(entry["logical_aliases"])}
                for _, entry in sorted(self.ledger.items())]


def object_id(obj):
    return h5py.h5o.get_info(obj.id).addr


def inspect_links(group, seen=None):
    seen = set() if seen is None else seen
    if object_id(group) in seen:
        return []
    seen.add(object_id(group))
    bad = []
    for key in group:
        link = group.get(key, getlink=True)
        path = group.name.rstrip("/") + "/" + key
        if not isinstance(link, h5py.HardLink):
            bad.append(dict(path=path, type=type(link).__name__))
            continue
        obj = group[key]
        if isinstance(obj, h5py.Group):
            bad.extend(inspect_links(obj, seen))
        elif obj.is_virtual or obj.external:
            bad.append(dict(path=path, type="virtual_or_external_storage"))
        elif h5py.check_ref_dtype(obj.dtype) is not None:
            bad.append(dict(path=path, type="HDF5_object_reference_dtype"))
    return bad


def chunks(shape, itemsize):
    tail = max(1, int(np.prod(shape[1:])))
    batch = max(1, min(shape[0], (1 << 20) // max(1, itemsize * tail), 64))
    return (batch, *shape[1:])


def copy_attrs(source, destination, sanitizer):
    for key, value in source.attrs.items():
        destination.attrs[key] = sanitizer.value(value, source.name + "@" + key)


def text_values(dataset, start=None, stop=None):
    values = dataset.asstr()[()] if start is None else dataset.asstr()[start:stop]
    return values


def copy_dataset(source, parent, name, image_ids, image_size, sanitizer, compression_level):
    shape, dtype = source.shape, source.dtype
    is_image = object_id(source) in image_ids
    string = h5py.check_string_dtype(dtype)
    if is_image:
        if shape[-3] != 3 or dtype != np.dtype("uint8") or len(shape) not in (3, 4):
            raise ValueError("Expected uint8 CHW RGB: " + source.name)
        target_shape = (*shape[:-2], image_size, image_size)
        kw = dict(shape=target_shape, dtype=np.uint8, compression="gzip",
                  compression_opts=compression_level, shuffle=True)
        kw["chunks"] = chunks(target_shape, 1) if len(shape) == 4 else target_shape
        target = parent.create_dataset(name, **kw)
        if len(shape) == 3:
            image = np.transpose(source[()], (1, 2, 0))
            target[...] = np.transpose(cv2.resize(image, (image_size, image_size), interpolation=cv2.INTER_AREA), (2, 0, 1))
        else:
            for start in range(0, shape[0], 32):
                frames = source[start:start + 32]
                out = np.stack([np.transpose(cv2.resize(np.transpose(frame, (1, 2, 0)),
                    (image_size, image_size), interpolation=cv2.INTER_AREA), (2, 0, 1)) for frame in frames])
                target[start:start + len(out)] = out
    elif string and len(shape) > 0:
        # HDF5 gzip does not compress the heap behind VLEN strings. Fixed-width
        # UTF8 storage compresses the same logical values, including full JSON.
        maximum = 1
        for start in range(0, shape[0], 64):
            for value in np.asarray(text_values(source, start, start + 64)).reshape(-1):
                transformed, _ = sanitized_text(value)
                maximum = max(maximum, len(transformed.encode("utf-8")))
        target = parent.create_dataset(name, shape=shape,
            dtype=h5py.string_dtype("utf-8", length=maximum),
            chunks=chunks(shape, maximum), compression="gzip", compression_opts=compression_level,
            shuffle=True)
        for start in range(0, shape[0], 64):
            values = np.asarray(text_values(source, start, start + 64))
            transformed = [sanitizer.value(v, source.name) for v in values.reshape(-1)]
            encoded = np.asarray([v.encode("utf-8") for v in transformed], dtype=target.dtype).reshape(values.shape)
            target[start:start + len(values)] = encoded
    elif string:
        value = sanitizer.value(text_values(source), source.name)
        target = parent.create_dataset(name, data=value, dtype=h5py.string_dtype("utf-8"))
    else:
        if h5py.check_vlen_dtype(dtype) is not None:
            raise ValueError("Unsupported non-string variable-length data: " + source.name)
        kw = dict(shape=shape, dtype=dtype)
        if shape and all(shape):
            kw.update(chunks=chunks(shape, dtype.itemsize), compression="gzip",
                      compression_opts=compression_level, shuffle=True)
        target = parent.create_dataset(name, **kw)
        if not shape:
            target[()] = source[()]
        elif shape[0]:
            for start in range(0, shape[0], 64):
                target[start:start + 64] = source[start:start + 64]
    copy_attrs(source, target, sanitizer)
    return target


def copy_tree(source, target, image_ids, image_size, sanitizer, compression_level, seen=None):
    seen = {} if seen is None else seen
    seen[object_id(source)] = target.name
    copy_attrs(source, target, sanitizer)
    for name in source:
        obj = source[name]
        address = object_id(obj)
        if address in seen:
            target[name] = target.file[seen[address]]
            continue
        if isinstance(obj, h5py.Group):
            child = target.create_group(name, track_order=True)
            copy_tree(obj, child, image_ids, image_size, sanitizer, compression_level, seen)
        else:
            child = copy_dataset(obj, target, name, image_ids, image_size, sanitizer, compression_level)
            seen[address] = child.name


def equal_values(first, second):
    if first.dtype.kind in "fc":
        return bool(np.array_equal(first, second, equal_nan=True))
    return bool(np.array_equal(first, second))


def verify_export(source, target, image_ids, image_size):
    checked, changed_text, checked_images, checked_attrs = [], [], [], []
    dataset_aliases = {}
    def verify_group(a, b, seen=None):
        seen = set() if seen is None else seen
        if object_id(a) in seen:
            return
        seen.add(object_id(a))
        for key, value in a.attrs.items():
            expected = Sanitizer().value(value, a.name + "@" + key)
            left, right = np.asarray(expected), np.asarray(b.attrs[key])
            if left.dtype.kind in "OUS" and right.dtype.kind in "OUS":
                same = np.array_equal(plain(left), plain(right))
            else:
                same = equal_values(left, right)
            if not same:
                raise AssertionError("Attribute changed beyond declared metadata sanitation: " + a.name + "@" + key)
            checked_attrs.append(a.name + "@" + key)
        for name in a:
            x, y = a[name], b[name]
            if isinstance(x, h5py.Group):
                verify_group(x, y, seen)
                continue
            if object_id(x) in dataset_aliases:
                if object_id(y) != dataset_aliases[object_id(x)]:
                    raise AssertionError("Source hard-link alias lost: " + x.name)
                continue
            dataset_aliases[object_id(x)] = object_id(y)
            if object_id(x) in image_ids:
                expected = (*x.shape[:-2], image_size, image_size)
                if y.shape != expected:
                    raise AssertionError("Resized RGB shape differs: " + x.name)
                frames = [(x[()], y[()])] if len(x.shape) == 3 else (
                    (x[i], y[i]) for i in range(x.shape[0]))
                for original, exported in frames:
                    expected_rgb = np.transpose(cv2.resize(np.transpose(original, (1, 2, 0)),
                        (image_size, image_size), interpolation=cv2.INTER_AREA), (2, 0, 1))
                    if not np.array_equal(expected_rgb, exported):
                        raise AssertionError("Exported RGB differs from declared spatial resize: " + x.name)
                checked_images.append(x.name)
                continue
            if x.shape != y.shape:
                raise AssertionError("Non-RGB shape changed: " + x.name)
            text = h5py.check_string_dtype(x.dtype)
            if not text and x.dtype != y.dtype:
                raise AssertionError("Non-RGB numeric dtype changed: " + x.name)
            ranges = [(None, None)] if not x.shape else [(i, i + 64) for i in range(0, x.shape[0], 64)]
            for start, stop in ranges:
                if text:
                    a_values = np.asarray(text_values(x, start, stop))
                    b_values = np.asarray(text_values(y, start, stop))
                    expected = np.asarray([sanitized_text(v)[0] for v in a_values.reshape(-1)]).reshape(a_values.shape)
                    same = np.array_equal(expected, b_values)
                    if not np.array_equal(a_values, b_values) and x.name not in changed_text:
                        changed_text.append(x.name)
                else:
                    a_values = np.asarray(x[()] if start is None else x[start:stop])
                    b_values = np.asarray(y[()] if start is None else y[start:stop])
                    same = equal_values(a_values, b_values)
                if not same:
                    raise AssertionError("Dataset values changed beyond declared metadata sanitation: " + x.name)
            checked.append(x.name)
    verify_group(source, target)
    if inspect_links(target):
        raise AssertionError("Export has nonportable HDF5 links")
    if not np.array_equal(source["timestamp"][:], target["timestamp"][:]) or \
            not np.array_equal(source["next_timestamp"][:], target["next_timestamp"][:]):
        raise AssertionError("Time sequence was altered")
    return dict(non_RGB_dataset_values_verified=checked, sanitized_text_datasets=changed_text,
                source_attributes_verified=checked_attrs, resized_RGB_datasets_all_frames_verified=checked_images,
                all_transitions_retained=True, timestamps_exactly_retained=True,
                non_RGB_numeric_values_exactly_retained=True, external_or_virtual_dependencies=[])


def normal_reader_check(path, image_size, sample_filter="success"):
    import torch
    from torch.utils.data import DataLoader
    from policy.dataset.lab_cuvette_project_v1_dataset import LabCuvetteProjectV1Dataset
    shape = dict(obs={camera: dict(shape=[3, image_size, image_size], type="rgb") for camera in CAMERAS},
                 action=dict(shape=[8]))
    shape["obs"]["agent_pose"] = dict(shape=[8], type="low_dim")
    results = []
    def describe(value):
        if isinstance(value, dict):
            return {k: describe(v) for k, v in value.items()}
        if torch.is_tensor(value):
            return dict(shape=list(value.shape), dtype=str(value.dtype), finite=bool(torch.isfinite(value).all()))
        return plain(value)
    for policy, n_obs in (("act", 1), ("dp", 3)):
        dataset = LabCuvetteProjectV1Dataset(shape_meta=shape, dataset_path=path,
            horizon=16, n_obs_steps=n_obs, policy_type=policy, sample_filter=sample_filter, val_ratio=0)
        batch = next(iter(DataLoader(dataset, batch_size=min(3, len(dataset)), num_workers=0)))
        results.append(dict(policy_type=policy, scene_fingerprint=dataset.scene_fingerprint,
            episodes=list(dataset.group_paths), transitions=len(dataset), batch=describe(batch),
            normal_reader="policy.dataset.lab_cuvette_project_v1_dataset.LabCuvetteProjectV1Dataset",
            model_or_optimizer_executed=False))
    return results


def export_sample(source_h5, output, *, image_size=96, sample_filter="success",
                  verify_reader=True, max_bytes=250_000_000, compression_level=6):
    source_h5, output = Path(source_h5).resolve(), Path(output).resolve()
    if output == source_h5 or output.is_relative_to(source_h5.parent.parent):
        raise ValueError("Public sample must use a new directory outside the source episode")
    if not 32 <= image_size <= 256 or not 1 <= compression_level <= 9:
        raise ValueError("Image size must be32..256; gzip compression must be1..9")
    if output.exists():
        raise FileExistsError(output)
    source_sha = sha256(source_h5)
    started = time.monotonic()
    sanitizer = Sanitizer()
    with h5py.File(source_h5, "r") as source:
        if source.attrs.get("scene_version") != "Project_v1":
            raise ValueError("A new Project_v1 episode is required, not a historical Size_v1 alias")
        accepted, reason = episode_matches_filter(source.attrs, sample_filter)
        if not accepted or source.attrs.get("task_type") != "loading":
            raise ValueError("Source is not a closed eligible full-loading record: " + reason)
        bad = inspect_links(source)
        if bad:
            raise ValueError("Source has nonportable HDF5 dependencies: " + json.dumps(bad))
        n = len(source["actions"])
        if not n:
            raise ValueError("Source contains no task transitions")
        image_ids, dimensions = set(), {}
        for camera in CAMERAS:
            dataset = source[camera]
            if dataset.shape != (n, 3, 256, 256):
                raise ValueError("Expected full256×256 source policy RGB: " + camera)
            image_ids.add(object_id(dataset)); dimensions[camera] = list(dataset.shape)
            if "terminal_observation/" + camera in source:
                image_ids.add(object_id(source["terminal_observation/" + camera]))
        labels = {key: plain(source.attrs.get(key)) for key in (
            "episode_id", "scene_version", "scene_mode", "task_type", "condition_group", "asset_id",
            "source_slot_id", "target_seat_id", "complete", "record_valid", "task_success", "failure_type",
            "termination_reason", "eligible_for_success_bc", "eligible_for_failure_analysis", "real_calibrated",
            "frozen_scene_sha256", "control_config_sha256", "code_commit")}
        first, last = float(source["timestamp"][0]), float(source["next_timestamp"][-1])
        output.mkdir(parents=True, exist_ok=False)
        target_h5 = output / "episode.h5"
        with h5py.File(target_h5, "x", libver="latest", track_order=True) as target:
            copy_tree(source, target, image_ids, image_size, sanitizer, compression_level)
            verification = verify_export(source, target, image_ids, image_size)
            target.attrs["public_sample_schema"] = SCHEMA
            target.attrs["public_sample_source_sha256"] = source_sha
            target.attrs["public_sample_RGB_resolution_wh"] = [image_size, image_size]
            target.attrs["public_sample_temporal_subsampling"] = False
            target.attrs["public_sample_original_camera_metadata_retained"] = True
        original_camera_metadata = plain(source.attrs.get("camera_meta_json"))
    if sha256(source_h5) != source_sha:
        raise RuntimeError("Source changed while exporting; this derivative must not be published")
    reader = normal_reader_check(target_h5, image_size, sample_filter) if verify_reader else []
    scale = image_size / 256
    manifest = dict(schema=SCHEMA, source_episode_id=labels["episode_id"],
        source_hdf5_sha256=source_sha, source_hdf5_size_bytes=source_h5.stat().st_size,
        source_scope="Complete original HDF5 sequence and all its fields; separate high-rate physics JSONL/media sidecars are not bundled",
        source_path_recorded=False, exported_hdf5="episode.h5", exported_hdf5_sha256=sha256(target_h5),
        exported_hdf5_size_bytes=target_h5.stat().st_size, source_labels=labels, transitions=n,
        first_observation_time_s=first, final_next_state_time_s=last, full_simulation_duration_s=last - first,
        source_RGB_shapes=dimensions, exported_RGB_shape_per_camera=[n, 3, image_size, image_size],
        image_derivation=dict(method="OpenCV INTER_AREA spatial resize only", opencv_version=cv2.__version__,
            from_resolution_wh=[256, 256], to_resolution_wh=[image_size, image_size],
            source_to_export_pixel_center_homography=[[scale, 0, (scale - 1) / 2], [0, scale, (scale - 1) / 2], [0, 0, 1]],
            camera_count=2, every_source_frame_retained=True, terminal_RGB_retained=True,
            source_capture_camera_metadata_preserved=True,
            original_camera_metadata_sha256=hashlib.sha256((original_camera_metadata or "").encode()).hexdigest(),
            calibration_note="Original capture metadata retains its original resolution/intrinsics;96px images are a spatial derivative of256px policy images. Apply the native-to-policy preprocessing then this resize transform; no new optical calibration is claimed."),
        storage=dict(compression="gzip", gzip_level=compression_level,
            JSON_text="Losslessly recompressed as fixed-width UTF8 values; same logical text except declared filesystem provenance replacements",
            camera_alias_hardlinks_preserved=True),
        physical_action_state_event_values_and_outcome_labels_changed=False,
        temporal_subsampling=False, successful_short_excerpt_claimed=False,
        metadata_sanitization=sanitizer.entries(), verification=verification,
        source_modified=False, normal_reader_validation=reader,
        normal_reader_shape_meta=dict(obs={camera: dict(shape=[3, image_size, image_size], type="rgb") for camera in CAMERAS},
                                      action=dict(shape=[8])),
        export_script_sha256=sha256(__file__), wall_seconds=time.monotonic() - started)
    manifest["normal_reader_shape_meta"]["obs"]["agent_pose"] = dict(shape=[8], type="low_dim")
    manifest["within_requested_size_budget"] = manifest["exported_hdf5_size_bytes"] <= max_bytes
    (output / "sample_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    (output / "shape_meta.json").write_text(json.dumps(manifest["normal_reader_shape_meta"], indent=2) + "\n")
    (output / "README.md").write_text(
        "# Complete Project_v1 simulation episode — compact RGB derivative\n\n"
        f"Episode ID: `{labels['episode_id']}`. Recorded task outcome: `{labels['task_success']}`. "
        f"All {n} control transitions and both complete RGB sequences are retained, spanning "
        f"{last - first:.6f} simulation seconds. This is not a temporally truncated excerpt.\n\n"
        f"Only image resolution changes: both policy RGB streams and terminal RGB are spatially resized "
        f"from 256×256 to {image_size}×{image_size} with OpenCV INTER_AREA. Raw and executed actions, "
        "robot/object states, contacts present in the record, timestamps, events, source outcome labels and "
        "original camera calibration metadata remain available. Nonoperative author filesystem paths in metadata "
        "are replaced by logical IDs, with a sanitization ledger. Original capture intrinsics retain their original "
        "resolution; see the manifest's resize transform before interpreting them for the smaller images.\n\n"
        "The HDF5 has no external links, virtual datasets or external storage. JSON is losslessly recompressed "
        "as fixed-width UTF8; original source HDF5 bytes remain unchanged. Privileged state is evaluator/debug "
        "data and is excluded by the default visual policy reader. This is synthetic simulation data, not "
        "real-world calibration.\n\n"
        "From a LabSim checkout using its declared Python environment:\n\n"
        "```bash\npython scripts/export_lab_cuvette_public_sample.py "
        f"--read-existing /path/to/this-sample --image-size {image_size} --sample-filter {sample_filter}\n```\n\n"
        "This invokes the existing `LabCuvetteProjectV1Dataset` for real ACT and DP batches; no model or "
        "optimizer is run. `shape_meta.json` gives the matching image sizes for direct dataset construction.\n\n"
        f"Source HDF5 SHA256: `{source_sha}`. Exported HDF5 SHA256: `{manifest['exported_hdf5_sha256']}`. "
        "See `sample_manifest.json` for full timing, source labels, exact transformations and reader checks.\n",
        encoding="utf-8")
    if not manifest["within_requested_size_budget"]:
        raise ValueError("Complete derivative exceeds the requested byte budget; preserved output for inspection, never truncated")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-h5", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--read-existing", type=Path, help="Read an exported sample with the normal Project_v1 ACT/DP dataset")
    parser.add_argument("--image-size", type=int, default=96)
    parser.add_argument("--sample-filter", choices=("success", "failure", "all_valid"), default="success")
    parser.add_argument("--skip-reader-check", action="store_true")
    parser.add_argument("--max-bytes", type=int, default=250_000_000)
    args = parser.parse_args()
    if args.read_existing:
        result = normal_reader_check(args.read_existing / "episode.h5", args.image_size, args.sample_filter)
    else:
        if not args.source_h5 or not args.output:
            parser.error("export requires --source-h5 and --output")
        result = export_sample(args.source_h5, args.output, image_size=args.image_size,
            sample_filter=args.sample_filter, verify_reader=not args.skip_reader_check, max_bytes=args.max_bytes)
        result = {k: result[k] for k in ("source_episode_id", "transitions", "full_simulation_duration_s",
            "exported_hdf5_size_bytes", "exported_hdf5_sha256", "within_requested_size_budget")}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
