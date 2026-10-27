"""CPU regression checks for offline asset retrieval and source dependencies."""

import hashlib
import io
import json
import xml.etree.ElementTree as ET
import zipfile

import pytest

from utils import cell_assets


def test_cache_location_is_project_local_with_explicit_overrides(tmp_path, monkeypatch):
    monkeypatch.delenv("LABSIM_ASSET_CACHE", raising=False)
    monkeypatch.chdir(tmp_path)
    expected = cell_assets.CATALOG_PATH.parents[2] / "local_assets"
    assert cell_assets.asset_cache() == expected
    monkeypatch.setenv("LABSIM_ASSET_CACHE", str(tmp_path / "environment-cache"))
    assert cell_assets.asset_cache() == tmp_path / "environment-cache"
    assert cell_assets.asset_cache(tmp_path / "explicit-cache") == tmp_path / "explicit-cache"


@pytest.fixture
def cached_asset(tmp_path, monkeypatch):
    root = tmp_path / "cache" / "test" / ("a" * 40)
    folder = root / "device"
    folder.mkdir(parents=True)
    (folder / "mesh.obj").write_text("v 0 0 0\n")
    entry = folder / "model.urdf"
    entry.write_text(
        '<robot name="test"><link name="base"><visual><geometry>'
        '<mesh filename="mesh.obj"/></geometry></visual></link></robot>'
    )
    (root / "LICENSE").write_text("Test fixture license")
    catalog = tmp_path / "catalog.json"
    catalog.write_text(json.dumps({
        "sources": {"test": {"revision": "a" * 40, "notice_files": ["LICENSE"]}},
        "assets": [{"asset_id": "test", "source": "test", "source_directory": "device",
                    "entry_file": "model.urdf",
                    "entry_sha256": hashlib.sha256(entry.read_bytes()).hexdigest()}],
    }))
    monkeypatch.setattr(cell_assets, "CATALOG_PATH", catalog)
    return tmp_path / "cache", entry


def test_offline_fetch_without_network(cached_asset):
    cache, entry = cached_asset
    assert cell_assets.fetch_asset("test", cache, offline=True) == entry


@pytest.mark.parametrize("damage", ["entry", "mesh", "license", "lfs"])
def test_incomplete_or_changed_sources_are_rejected(cached_asset, damage):
    cache, entry = cached_asset
    if damage == "entry":
        entry.write_text("changed")
    elif damage == "mesh":
        (entry.parent / "mesh.obj").unlink()
    elif damage == "license":
        (entry.parent.parent / "LICENSE").unlink()
    else:
        (entry.parent / "mesh.obj").write_text("version https://git-lfs.github.com/spec/v1\n")
    with pytest.raises((ValueError, FileNotFoundError)):
        cell_assets.fetch_asset("test", cache, offline=True)


def test_urdf_cannot_reference_outside_its_asset(cached_asset):
    _, entry = cached_asset
    entry.write_text(entry.read_text().replace('filename="mesh.obj"', 'filename="../LICENSE"'))
    with pytest.raises(ValueError, match="escapes"):
        cell_assets.validate_urdf_files(entry)


@pytest.mark.parametrize("body, message", [
    ('<link name="base"/><link name="base"/>', "unique"),
    ('<link name="base"/><link name="orphan"/>', "one root"),
    ('<link name="base"/><joint name="j" type="fixed">'
     '<parent link="base"/><child link="missing"/></joint>', "invalid links"),
    ('<link name="root"/><link name="a"/><link name="b"/>'
     '<joint name="ab" type="fixed"><parent link="a"/><child link="b"/></joint>'
     '<joint name="ba" type="fixed"><parent link="b"/><child link="a"/></joint>',
     "cycle"),
    ('<link name="base"/><link name="arm"/>'
     '<joint name="a" type="fixed"><parent link="base"/><child link="arm"/></joint>'
     '<joint name="b" type="fixed"><parent link="base"/><child link="arm"/></joint>',
     "multiple parents"),
])
def test_broken_joint_trees_are_rejected(body, message):
    document = ET.fromstring(f'<robot name="invalid">{body}</robot>')
    with pytest.raises(ValueError, match=message):
        cell_assets._validate_urdf_topology(document)


@pytest.mark.parametrize("axis, lower, upper, origin, valid", [
    ("0 1 0", "-0.2", "0.2", "0 0 0", True),
    ("0 0 0", "0", "1", "0 0 0", False),
    ("0 nan 0", "0", "1", "0 0 0", False),
    ("0 1 0", "1", "0", "0 0 0", False),
    ("0 1 0", "0", "inf", "0 0 0", False),
    ("0 1 0", "0", "1", "0 nan 0", False),
])
def test_joint_frames_axes_and_limits(axis, lower, upper, origin, valid):
    document = ET.fromstring(
        '<robot name="slider"><link name="base"/><link name="carriage"/>'
        '<joint name="slide" type="prismatic"><parent link="base"/>'
        f'<child link="carriage"/><origin xyz="{origin}"/><axis xyz="{axis}"/>'
        f'<limit lower="{lower}" upper="{upper}" effort="0" velocity="0"/>'
        '</joint></robot>'
    )
    if valid:
        cell_assets._validate_urdf_topology(document)
    else:
        with pytest.raises(ValueError):
            cell_assets._validate_urdf_topology(document)


def test_unknown_asset_is_rejected():
    with pytest.raises(KeyError, match="Unknown"):
        cell_assets.fetch_asset("missing", offline=True)


def test_github_download_pins_revision_and_quotes_paths(tmp_path, monkeypatch):
    payload = b"source file bytes"
    filename = "One Part/model.stl"
    source = {
        "repo_id": "example/asset", "revision": "a" * 40,
        "files_sha256": {filename: hashlib.sha256(payload).hexdigest()},
    }
    requests = []

    def respond(request, timeout):
        requests.append(request.full_url)
        return io.BytesIO(payload)

    monkeypatch.setattr(cell_assets, "urlopen", respond)
    cell_assets._fetch_pinned_files(source, tmp_path)
    assert requests == [
        "https://raw.githubusercontent.com/example/asset/" + "a" * 40 + "/One%20Part/model.stl"
    ]
    assert (tmp_path / filename).read_bytes() == payload
    cell_assets._fetch_pinned_files(source, tmp_path)
    assert len(requests) == 1  # A verified cached file must not be fetched again.


def test_bad_download_does_not_replace_existing_source(tmp_path, monkeypatch):
    target = tmp_path / "model.stl"
    target.write_bytes(b"existing source")
    source = {
        "repo_id": "example/asset", "revision": "a" * 40,
        "files_sha256": {"model.stl": hashlib.sha256(b"expected bytes").hexdigest()},
    }
    monkeypatch.setattr(cell_assets, "urlopen", lambda *a, **k: io.BytesIO(b"wrong response"))
    with pytest.raises(ValueError, match="pinned hash"):
        cell_assets._fetch_pinned_files(source, tmp_path)
    assert target.read_bytes() == b"existing source"
    assert not list(tmp_path.glob("*.part"))


def test_download_supports_pinned_upstream_reference_url(tmp_path, monkeypatch):
    payload = b"upstream CAD source archive"
    url = "https://gitlab.example/project/archive.zip?sha=" + "b" * 40
    source = {
        "repo_id": "example/asset", "revision": "a" * 40,
        "files_sha256": {"reference.zip": hashlib.sha256(payload).hexdigest()},
        "file_urls": {"reference.zip": url},
    }
    requests = []

    def respond(request, timeout):
        requests.append(request.full_url)
        return io.BytesIO(payload)

    monkeypatch.setattr(cell_assets, "urlopen", respond)
    cell_assets._fetch_pinned_files(source, tmp_path)
    assert requests == [url]
    assert (tmp_path / "reference.zip").read_bytes() == payload


def test_missing_contract_is_not_invented(cached_asset):
    cache, _ = cached_asset
    with pytest.raises(FileNotFoundError, match="does not provide an instrument contract"):
        cell_assets.read_contract("test", cache)


def test_zip_extracts_only_pinned_members_and_checks_offline_cache(tmp_path):
    payload = b"pinned CAD bytes"
    with zipfile.ZipFile(tmp_path / "source.zip", "w") as archive:
        archive.writestr("models/part.stl", payload)
        archive.writestr("unlisted.txt", b"not requested")
    source = {"zip_members_sha256": {"source.zip": {
        "models/part.stl": hashlib.sha256(payload).hexdigest(),
    }}}
    cell_assets._extract_source_members(source, tmp_path, offline=False)
    assert (tmp_path / "models/part.stl").read_bytes() == payload
    assert not (tmp_path / "unlisted.txt").exists()
    cell_assets._extract_source_members(source, tmp_path, offline=True)
    (tmp_path / "models/part.stl").write_bytes(b"changed")
    with pytest.raises(ValueError, match="changed extracted"):
        cell_assets._extract_source_members(source, tmp_path, offline=True)
    assert (tmp_path / "models/part.stl").read_bytes() == b"changed"


def test_fetch_extracts_archived_license_before_attribution_check(tmp_path, monkeypatch):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("LICENSE", b"Test source license")
    payload = buffer.getvalue()
    digest = hashlib.sha256(payload).hexdigest()
    catalog = tmp_path / "catalog.json"
    catalog.write_text(json.dumps({
        "sources": {"test": {
            "provider": "github", "repo_id": "example/test", "revision": "a" * 40,
            "files_sha256": {"source.zip": digest}, "notice_files": ["LICENSE"],
            "zip_members_sha256": {"source.zip": {
                "LICENSE": hashlib.sha256(b"Test source license").hexdigest(),
            }},
        }},
        "assets": [{"asset_id": "test", "source": "test", "source_directory": "",
                    "entry_file": "source.zip", "entry_sha256": digest,
                    "format": "stl_assembly"}],
    }))
    monkeypatch.setattr(cell_assets, "CATALOG_PATH", catalog)
    monkeypatch.setattr(cell_assets, "urlopen", lambda *a, **k: io.BytesIO(payload))
    entry = cell_assets.fetch_asset("test", tmp_path / "cache")
    assert (entry.parent / "LICENSE").read_bytes() == b"Test source license"
    assert cell_assets.fetch_asset("test", tmp_path / "cache", offline=True) == entry


@pytest.mark.parametrize("member", ["../escaped.stl", "part.stl"])
def test_zip_rejects_escape_and_wrong_member_hash(tmp_path, member):
    with zipfile.ZipFile(tmp_path / "source.zip", "w") as archive:
        archive.writestr(member, b"unexpected content")
    source = {"zip_members_sha256": {"source.zip": {member: "0" * 64}}}
    with pytest.raises(ValueError, match="escapes|pinned hash"):
        cell_assets._extract_source_members(source, tmp_path, offline=False)
    assert not list(tmp_path.rglob("*.stl"))


def test_assembly_preserves_source_faces_and_relative_placement(tmp_path):
    import numpy as np
    import trimesh

    entry = tmp_path / "source.zip"
    path = tmp_path / "part.stl"
    path.write_bytes(trimesh.creation.box(extents=[2, 4, 6]).export(file_type="stl"))
    original = path.read_bytes()
    mesh = trimesh.load_mesh(path, process=False)
    asset = {"meters_per_unit": 0.001, "parts": [
        {"name": "First", "file": "part.stl"},
        {"name": "Second", "file": "part.stl",
         "rotation": [[-1, 0, 0], [0, 1, 0], [0, 0, -1]],
         "translation_source_units": [10, 20, 30]},
    ]}
    first, second = cell_assets._read_static_parts(entry, asset)
    assert np.array_equal(first[1].faces, mesh.faces)
    assert np.array_equal(second[1].faces, mesh.faces)
    assert np.allclose(first[2], mesh.vertices * .001)
    assert np.allclose(second[2], (mesh.vertices * [-1, 1, -1] + [10, 20, 30]) * .001)
    assert path.read_bytes() == original
    asset["parts"][1]["rotation"][0][0] = -2
    with pytest.raises(ValueError, match="must be rigid"):
        cell_assets._read_static_parts(entry, asset)


def test_print_layout_selection_preserves_triangles_and_rejects_cut(tmp_path):
    import numpy as np
    import trimesh

    left = trimesh.creation.box()
    right = left.copy()
    right.apply_translation([10, 0, 0])
    path = tmp_path / "layout.stl"
    path.write_bytes(trimesh.util.concatenate([left, right]).export(file_type="stl"))
    original = trimesh.load_mesh(path, process=False)
    asset = {"meters_per_unit": .001, "parts": [{
        "name": "Left", "file": path.name,
        "selection_bounds_source_units": [[-1, -1, -1], [1, 1, 1]],
    }]}
    part, mesh, vertices = cell_assets._read_static_parts(tmp_path / "source.zip", asset)[0]
    expected = original.triangles[original.triangles_center[:, 0] < 1]
    assert np.array_equal(mesh.triangles, expected)
    assert np.allclose(vertices[mesh.faces], expected * .001)
    part["selection_bounds_source_units"][1][0] = 0
    with pytest.raises(ValueError, match="whole source triangles"):
        cell_assets._read_static_parts(tmp_path / "source.zip", asset)


def test_preview_help_does_not_require_isaac(capsys, monkeypatch):
    from demos.cell_assets import preview

    monkeypatch.setattr("sys.argv", ["preview", "--help"])
    with pytest.raises(SystemExit) as error:
        preview.main()
    assert error.value.code == 0
    assert "--asset-id" in capsys.readouterr().out


def test_glass_binding_reaches_instance_mesh_without_changing_source(tmp_path):
    """A parent binding must override an instanced mesh's imported material."""
    Usd = pytest.importorskip("pxr.Usd")
    from pxr import UsdGeom, UsdPhysics, UsdShade

    source_path = tmp_path / "source.usda"
    source = Usd.Stage.CreateNew(str(source_path))
    source_root = UsdGeom.Xform.Define(source, "/Part").GetPrim()
    source.SetDefaultPrim(source_root)
    mesh = UsdGeom.Mesh.Define(source, "/Part/Mesh")
    mesh.CreatePointsAttr([(0, 0, 0), (1, 0, 0), (0, 1, 0)])
    mesh.CreateFaceVertexCountsAttr([3])
    mesh.CreateFaceVertexIndicesAttr([0, 1, 2])
    UsdPhysics.CollisionAPI.Apply(mesh.GetPrim())
    old_material = UsdShade.Material.Define(source, "/Part/ImportedMaterial")
    UsdShade.MaterialBindingAPI.Apply(mesh.GetPrim()).Bind(old_material)
    source.GetRootLayer().Save()
    original_bytes = source_path.read_bytes()

    stage = Usd.Stage.CreateInMemory()
    root = UsdGeom.Xform.Define(stage, "/Device").GetPrim()
    stage.SetDefaultPrim(root)
    instance = stage.DefinePrim("/Device/Pane/visuals/Instance", "Xform")
    instance.GetReferences().AddReference(str(source_path))
    instance.SetInstanceable(True)
    instance_mesh = stage.GetPrimAtPath(instance.GetPath().AppendChild("Mesh"))
    assert instance_mesh.IsInstanceProxy()
    points = UsdGeom.Mesh(instance_mesh).GetPointsAttr().Get()
    asset = {"glass_display": {
        "links": ["Pane"], "color": [.8, .9, .95], "ior": 1.49,
        "roughness": .05, "absorption_depth_m": .02,
    }}
    cell_assets._apply_glass_display(stage, asset)
    bound, _ = UsdShade.MaterialBindingAPI(instance_mesh).ComputeBoundMaterial()
    assert bound.GetPath() == "/Device/Looks/HoodGlass"
    assert instance_mesh.IsInstanceProxy()
    assert instance_mesh.HasAPI(UsdPhysics.CollisionAPI)
    assert UsdGeom.Mesh(instance_mesh).GetPointsAttr().Get() == points
    assert source_path.read_bytes() == original_bytes


def test_gas_strut_retains_insertion_and_rejects_disconnected_rod():
    from utils.ika_gas_springs import mount_geometry, read_config

    config = read_config()
    minimum, maximum = mount_geometry(config, [0, .160437, .517426])
    values = config["assumptions"]
    assert minimum > values["rod_length_m"]
    assert values["barrel_length_m"] + values["rod_length_m"] - maximum >= .01
    values["rod_length_m"] = .14
    with pytest.raises(ValueError, match="insertion"):
        mount_geometry(config, [0, .160437, .517426])


def test_gas_strut_passive_force_and_closed_open_balance():
    import numpy as np
    from utils.ika_gas_springs import axial_force, mount_geometry, read_config

    config = read_config()
    values = config["assumptions"]
    origin = np.array([0, .160437, .517426])
    minimum, maximum = mount_geometry(config, origin)
    assert axial_force(values, minimum, 0, minimum, maximum) == pytest.approx(48)
    assert axial_force(values, maximum, 0, minimum, maximum) == pytest.approx(40)
    assert axial_force(values, maximum, 10, minimum, maximum) == 0
    assert axial_force(values, minimum, -10, minimum, maximum) == 80
    base = np.array([0, *values["base_mount_yz_m"]])
    pin = np.array([0, *values["hood_mount_yz_m"]])
    # Gravity from the source hood assembly's mass-weighted COM.
    torques = []
    for angle in (0, values["maximum_hood_angle_rad"]):
        c, s = np.cos(angle), np.sin(angle)
        lever = np.array([[1, 0, 0], [0, c, s], [0, -s, c]]) @ pin
        delta = origin + lever - base
        length = np.linalg.norm(delta)
        force = axial_force(values, length, 0, minimum, maximum)
        spring_torque = -2 * np.cross(lever, force * delta / length)[0]
        gravity = 9.81 * (-.74400188 * c - .4203287 * s)
        torques.append(spring_torque + gravity)
    assert torques[0] < 0  # Remains shut without a robot.
    assert torques[1] > 0  # Supports the open hood against the stroke limit.


def _loading_acceptance_records():
    import copy

    placed = {
        "phase": "loaded_settle", "beaker_position_m": [.1, .365, .8727],
        "beaker_orientation_wxyz": [1, 0, 0, 0], "beaker_force_n": [0, 0],
        "joint_actual": [0] * 7 + [.04, .04], "end_effector_m": [.1, .365, 1.0527],
        "hood_angle_rad": 1.3,
    }
    records = [copy.deepcopy(placed) for _ in range(3)]
    for _ in range(3):
        final = copy.deepcopy(placed)
        final.update(phase="closed_settle", hood_angle_rad=0)
        records.append(final)
    held = copy.deepcopy(placed)
    held.update(phase="lift_beaker", beaker_position_m=[.2, 0, .92],
                end_effector_m=[.2, 0, .9596], beaker_force_n=[20, 20])
    return [held] + records


def test_loading_acceptance_requires_actual_placement_and_final_retention():
    from demos.cell_assets.loading import evaluate_loading

    result = evaluate_loading(_loading_acceptance_records(), [.2, 0, .74],
                              [.1, .365, .8737], .8727, 1., .0396)
    assert all(result.values())


@pytest.mark.parametrize("failure,key", [
    ("retained_grasp", "loaded_no_finger_contact"),
    ("blocked_jaws", "loaded_gripper_open"),
    ("cup_above_platform", "loaded_on_platform_within_1cm"),
    ("lost_during_closing", "final_target_xy_within_2cm"),
    ("incomplete_run", "final_stable_window_3s"),
    ("hood_fell", "hood_remains_open_through_loading"),
])
def test_loading_acceptance_rejects_partial_success(failure, key):
    from demos.cell_assets.loading import evaluate_loading

    records = _loading_acceptance_records()
    if failure == "retained_grasp":
        records[1]["beaker_force_n"] = [10, 10]
    elif failure == "blocked_jaws":
        records[1]["joint_actual"][-2:] = [.02, .02]
    elif failure == "cup_above_platform":
        records[1]["beaker_position_m"][2] += .14
    elif failure == "lost_during_closing":
        records[-1]["beaker_position_m"][0] += .2
    elif failure == "incomplete_run":
        records.pop()
    elif failure == "hood_fell":
        records[0]["hood_angle_rad"] = .7
    result = evaluate_loading(records, [.2, 0, .74], [.1, .365, .8737], .8727, 1., .0396)
    assert result[key] is False
    assert not all(result.values())


def test_full_cycle_help_does_not_start_isaac(monkeypatch, capsys):
    from demos.cell_assets import hood_open

    monkeypatch.setattr("sys.argv", ["hood_open", "--help"])
    with pytest.raises(SystemExit) as error:
        hood_open.main()
    assert error.value.code == 0
    assert "--load-test" in capsys.readouterr().out


@pytest.mark.parametrize("reachable,jump", [(False, 0), (True, 1)])
def test_shared_cartesian_preflight_rejects_invalid_path(reachable, jump):
    import numpy as np
    from demos.cell_assets.motion import cartesian_joint_path

    class Solver:
        def compute_inverse_kinematics(self, frame, position, rotation, seed):
            return seed + jump, reachable

    with pytest.raises(RuntimeError, match="Unreachable or discontinuous"):
        cartesian_joint_path(Solver(), "tcp", np.zeros(3), np.array([1., 0, 0, 0]),
                             np.ones(3), np.array([1., 0, 0, 0]), np.zeros(7), 1)


def test_video_recorder_closes_partial_encoders(tmp_path, monkeypatch):
    import sys
    from types import SimpleNamespace
    from demos.cell_assets.cameras import VideoRecorder

    closed = []
    count = []

    def open_writer(*args):
        index = len(count)
        count.append(index)
        return SimpleNamespace(isOpened=lambda: index == 0,
                               release=lambda: closed.append(index))

    monkeypatch.setitem(sys.modules, "cv2", SimpleNamespace(
        VideoWriter=open_writer, VideoWriter_fourcc=lambda *args: 0))
    with pytest.raises(RuntimeError, match="side"):
        VideoRecorder(tmp_path, {"front": object(), "side": object()})
    assert closed == [0, 1]


def cap_cycle_records():
    """Ideal contact/release evidence for exercising rejection conditions."""
    import numpy as np

    dt = 1 / 120
    offset = np.array([0, 0, 0.016])
    targets = {"closed": np.array([0.2, 0.096, 0.789]),
               "parked": np.array([0.2, 0.055, 0.789])}
    records = []
    for phase, target, count, held in (
        ("uncap", "closed", 2, True),
        ("transfer_to_park", "parked", 2, True),
        ("parked_settle", "parked", 360, False),
        ("lift_from_park", "parked", 2, True),
        ("transfer_to_sample", "closed", 2, True),
        ("closed_settle", "closed", 360, False),
    ):
        for _ in range(count):
            position = targets[target] + [0, 0, 0.12 if held else 0]
            ee = position + offset + [0, 0, 0 if held else 0.16]
            records.append({
                "time_s": (len(records) + 1) * dt, "phase": phase,
                "cap_position_m": position.tolist(), "cap_orientation_wxyz": [1, 0, 0, 0],
                "end_effector_m": ee.tolist(), "joint_actual": [0] * 7 + [0.018 if held else 0.04] * 2,
                "finger_force_n": [1, 1] if held else [0, 0],
                "robot_device_force_n": 0, "robot_table_force_n": 0,
            })
    return records, targets, dt, len(records), offset


def test_cap_cycle_requires_complete_released_contact_evidence():
    from demos.cell_assets.cap_cycle import evaluate_cycle

    data = cap_cycle_records()
    assert all(evaluate_cycle(*data).values())
    shortened = (data[0][:-1], *data[1:])
    checks = evaluate_cycle(*shortened)
    assert not checks["complete_record_count"]
    assert not checks["closed_stable_3s"]


@pytest.mark.parametrize("fault,failed_check", [
    ("held_release", "parked_no_finger_contact"),
    ("wrong_seat", "closed_xy_within_1mm"),
    ("tilted_carry", "opening_upright_during_carry_5deg"),
    ("slip", "opening_tracks_gripper_3mm"),
    ("collision", "no_robot_device_collision_above_1N"),
    ("missing_contact", "closing_bilateral_contact"),
])
def test_cap_cycle_rejects_false_success(fault, failed_check):
    import numpy as np
    from demos.cell_assets.cap_cycle import evaluate_cycle

    data = cap_cycle_records()
    rows = data[0]
    if fault == "held_release":
        next(r for r in rows if r["phase"] == "parked_settle")["finger_force_n"] = [0.1, 0.1]
    elif fault == "wrong_seat":
        next(r for r in rows if r["phase"] == "closed_settle")["cap_position_m"][0] += 0.002
    elif fault == "tilted_carry":
        rows[0]["cap_orientation_wxyz"] = [np.cos(np.deg2rad(10)), np.sin(np.deg2rad(10)), 0, 0]
    elif fault == "slip":
        rows[0]["cap_position_m"][1] += 0.004
    elif fault == "collision":
        rows[0]["robot_device_force_n"] = 2
    elif fault == "missing_contact":
        next(r for r in rows if r["phase"] == "lift_from_park")["finger_force_n"] = [0, 1]
    assert not evaluate_cycle(*data)[failed_check]


def test_cap_cycle_help_does_not_start_isaac(monkeypatch, capsys):
    from demos.cell_assets import cap_cycle

    monkeypatch.setattr("sys.argv", ["cap_cycle", "--help"])
    with pytest.raises(SystemExit) as error:
        cap_cycle.main()
    assert error.value.code == 0
    assert "--offline" in capsys.readouterr().out


def handling_records():
    """Independent ideal evidence, including two released stable windows."""
    import numpy as np
    from demos.cell_assets.motion import Motion

    dt, offset = 0.1, np.array([0, 0, 0.02])
    targets = {"loaded": np.array([0.05, 0.27, 0.9087]),
               "returned": np.array([0.05, -0.05, 0.74])}
    rows, motions = [], []
    for phase, target, seconds, held in (
        ("lift", "returned", 1, True), ("transfer", "loaded", 1, True),
        ("enter", "loaded", 1, True), ("loaded_settle", "loaded", 3, False),
        ("retrieve", "loaded", 1, True), ("return_enter", "loaded", 1, True),
        ("return_transfer", "returned", 1, True), ("returned_settle", "returned", 3, False),
    ):
        motions.append(Motion(phase, seconds, np.zeros((2, 7)), 0 if held else 0.04))
        for _ in range(round(seconds / dt)):
            pos = targets[target] + [0, 0, 0.15 if held else 0]
            rows.append({"time_s": (len(rows) + 1) * dt, "phase": phase,
                         "position_m": pos.tolist(), "orientation_wxyz": [1, 0, 0, 0],
                         "end_effector_m": (pos + offset + [0, 0, 0 if held else 0.15]).tolist(),
                         "joint_actual": [0] * 7 + [0.02 if held else 0.04] * 2,
                         "finger_force_n": [1, 1] if held else [0, 0],
                         "payload_device_force_n": 1 if phase == "loaded_settle" else 0,
                         "payload_table_force_n": 1 if phase == "returned_settle" else 0,
                         "robot_device_force_n": 0, "robot_table_force_n": 0})
    return rows, targets, offset, dt, motions


def test_handling_requires_completed_load_and_unload():
    from demos.cell_assets.handling import evaluate_handling

    data = handling_records()
    assert all(evaluate_handling(*data).values())
    checks = evaluate_handling(data[0][:-1], *data[1:])
    assert not checks["all_phases_completed"]
    assert not checks["returned_stable_3s"]


@pytest.mark.parametrize("fault,check", [
    ("contact", "loading_bilateral_contact"), ("slip", "loading_tracks_gripper_3mm"),
    ("tilt", "loading_orientation_within_5deg"), ("collision", "no_robot_device_collision_above_1N"),
    ("held", "loaded_no_finger_contact"), ("seat", "loaded_position_within_2mm"),
    ("unsupported", "loaded_supported_after_release"),
])
def test_handling_rejects_false_success(fault, check):
    from demos.cell_assets.handling import evaluate_handling

    data = handling_records()
    row = data[0][0]
    if fault in {"held", "seat"}:
        row = next(r for r in data[0] if r["phase"] == "loaded_settle")
    if fault == "contact":
        row["finger_force_n"] = [0, 1]
    elif fault == "slip":
        row["position_m"][0] += 0.004
    elif fault == "tilt":
        row["orientation_wxyz"] = [0.984807753, 0.173648178, 0, 0]
    elif fault == "collision":
        row["robot_device_force_n"] = 2
    elif fault == "held":
        row["finger_force_n"] = [0.1, 0.1]
    elif fault == "seat":
        row["position_m"][2] += 0.003
    elif fault == "unsupported":
        next(r for r in data[0] if r["phase"] == "loaded_settle")["payload_device_force_n"] = 0
    assert not evaluate_handling(*data)[check]


def test_handling_help_does_not_start_isaac(monkeypatch, capsys):
    from demos.cell_assets import handling

    monkeypatch.setattr("sys.argv", ["handling", "--help"])
    with pytest.raises(SystemExit) as error:
        handling.main()
    assert error.value.code == 0
    assert "--offline" in capsys.readouterr().out
