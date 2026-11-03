"""Boundary tests for unit scoring, closed data and the shared release API."""

import copy
import json
import numpy as np
import pytest

from demos.cell_units.registry import get_unit, list_units
from demos.cell_units.scorer import score
from demos.cell_units.recording import Recorder, check_dataset
from demos.cell_units.run import main
from demos.cell_units.policy import validate_provider


def cap_rows():
    row = dict(
        time_s=1.0,
        joint_actual=[0] * 7 + [0.04, 0.04],
        cap_position_m=[0, 0, 0],
        cap_orientation_wxyz=[1, 0, 0, 0],
        end_effector_m=[0, 0, 0.2],
        finger_force_n=[0, 0],
        robot_device_force_n=0.0,
        robot_table_force_n=0.0,
    )
    held = copy.deepcopy(row)
    held.update(cap_position_m=[0, 0, 0.1], finger_force_n=[0.2, 0.2])
    return [held] + [copy.deepcopy(row) for _ in range(360)]


def test_independent_cap_score_rejects_false_success():
    unit, rows = get_unit("diynafluor_uncap"), cap_rows()
    targets = {"closed": np.zeros(3), "parked": np.zeros(3)}
    assert score(unit, rows, targets, np.zeros(3), 1 / 120)["task_success"]
    for field, value in [
        ("finger_force_n", [0.2, 0.2]),
        ("cap_position_m", [0.1, 0, 0]),
        ("robot_device_force_n", 2.0),
        ("end_effector_m", [0, 0, 0.01]),
    ]:
        invalid = copy.deepcopy(rows)
        invalid[-1][field] = value
        assert not score(unit, invalid, targets, np.zeros(3), 1 / 120)["task_success"]
    assert not score(unit, rows[:10], targets, np.zeros(3), 1 / 120)["task_success"]


@pytest.mark.parametrize("hz", [120, 480])
def test_h5_exact_transition_and_closed_gate(tmp_path, hz):
    rec = Recorder(
        tmp_path,
        dict(
            scene_version="SingleCellUnit_v1",
            backend="teacher",
            record_purpose="demonstration",
            physics_hz=hz,
        ),
    )

    def obs(t):
        return dict(
            simulation_time=t,
            joint_positions=np.zeros(9),
            joint_velocities=np.zeros(9),
            TCPpose=dict(position_m=[0, 0, 0], quaternion_wxyz=[1, 0, 0, 0]),
            images={k: np.ones((8, 8, 3), np.uint8) for k in ("side_camera", "wrist_camera")},
        )

    rec.observation(obs(0))
    rec.physics(dict(time_s=1 / hz, joint_target=[0] * 9))
    rec.transition(obs(1 / hz))
    rec.close(dict(task_success=False, termination_reason="POLICY_BUDGET"))
    report = check_dataset(tmp_path)
    assert report["physics_steps"] == report["transitions"] == 1
    assert report["batch_shape"] == [1, hz // 30, 9]
    assert report["duration_s"] == 1 / hz
    assert not report["task_success"]
    import h5py

    with h5py.File(rec.path, "r+") as f:
        f.attrs["closed"] = False
    with pytest.raises(ValueError, match="closed"):
        check_dataset(tmp_path)


def test_registry_and_cpu_entry(tmp_path):
    assert len(list_units()) == 5
    assert (
        main(["demo", "--unit", "ika_open", "--output", str(tmp_path / "not-created"), "--dry-run"])
        == 0
    )
    assert not (tmp_path / "not-created").exists()


@pytest.mark.parametrize(
    "child_code,worker_code,expected", [(0, 0, 0), (0, 1, 1), (-11, 0, 139), (0, None, 1)]
)
def test_launcher_preserves_worker_failure(
    tmp_path, monkeypatch, child_code, worker_code, expected
):
    """Fast Isaac exit must not turn an exception or missing result into success."""
    from types import SimpleNamespace

    output = tmp_path / "run"

    def child(command):
        assert command[-1] == "--worker"
        output.mkdir()
        if worker_code is not None:
            (output / "worker_status.json").write_text(json.dumps({"exit_code": worker_code}))
        return SimpleNamespace(returncode=child_code)

    monkeypatch.setattr("demos.cell_units.run.subprocess.run", child)
    assert main(["eval", "--unit", "ika_open", "--output", str(output)]) == expected
    assert json.loads((output / "process_exit.json").read_text())["child_returncode"] == child_code


def test_submillimetre_ik_changes_joints_and_rejects_unreachable():
    from scipy.spatial.transform import Rotation
    from demos.cell_units.kinematics import solve_step

    forward = lambda q: (q[:3], Rotation.from_rotvec(q[3:6]).as_matrix())
    q = np.zeros(7)
    position = np.array([0.0005, -0.0003, 0.0001])
    solved, ok, detail = solve_step(
        forward, q, position, Rotation.identity(), -np.ones(7), np.ones(7), np.ones(7) * 0.01
    )
    assert ok and np.linalg.norm(solved[:3] - position) < 1e-5
    assert np.linalg.norm(solved - q) > 0.0001
    _, ok, _ = solve_step(
        forward,
        q,
        np.array([0.1, 0, 0]),
        Rotation.identity(),
        -np.ones(7),
        np.ones(7),
        np.ones(7) * 0.01,
    )
    assert not ok


def test_pcr_pocket_has_open_throat_and_closed_floor():
    from demos.cell_units.pcr import CONFIG, pocket_mesh

    cfg = json.loads(CONFIG.read_text())
    mesh = pocket_mesh(cfg)
    assert mesh.is_watertight and mesh.volume > 0
    hits, _, _ = mesh.ray.intersects_location([[0, 0, 0.01]], [[0, 0, -1]])
    assert np.isclose(hits[:, 2].max(), -cfg["hole_depth_m"])
    hits, _, _ = mesh.ray.intersects_location([[0.004, 0, 0.01]], [[0, 0, -1]])
    assert np.isclose(hits[:, 2].max(), 0)


def test_pcr_score_requires_insertion_and_physical_support():
    unit = get_unit("pcr_insert")
    row = dict(
        position_m=[0, 0, 0],
        orientation_wxyz=[1, 0, 0, 0],
        joint_actual=[0] * 7 + [0.04, 0.04],
        end_effector_m=[0, 0, 0.2],
        finger_force_n=[0, 0],
        robot_device_force_n=0,
        robot_table_force_n=0,
        payload_device_force_n=0.006,
        insertion_depth_m=0.0126,
    )
    held = dict(row, position_m=[0, 0, 0.1], finger_force_n=[0.1, 0.1])
    rows = [held] + [copy.deepcopy(row) for _ in range(1440)]
    targets = dict(loaded=np.zeros(3), returned=np.zeros(3), hole_top=[0, 0, 0.0126])
    assert score(unit, rows, targets, np.array([0, 0, 0.03]), 1 / 480)["task_success"]
    for field, value in [
        ("insertion_depth_m", 0),
        ("insertion_depth_m", 0.2),
        ("payload_device_force_n", 0),
        ("position_m", [0.001, 0, 0]),
        ("finger_force_n", [0.1, 0.1]),
    ]:
        invalid = copy.deepcopy(rows)
        invalid[-1][field] = value
        assert not score(unit, invalid, targets, np.array([0, 0, 0.03]), 1 / 480)["task_success"]

    displaced = copy.deepcopy(rows)
    for row in displaced:
        row["position_m"] = [0.1, 0.1, -0.2]
        row["insertion_depth_m"] = 0.2
    assert not score(unit, displaced, targets, np.zeros(3), 1 / 480)["checks"][
        "inserted_at_least_10mm"
    ]


def test_placement_score_rejects_dropping_before_support():
    unit = dict(
        get_unit("magsep_transfer"), initial_state="placement-ready", initial_grasp_contact_N=[1, 1]
    )
    released = dict(
        position_m=[0, 0, 0],
        orientation_wxyz=[1, 0, 0, 0],
        joint_actual=[0] * 7 + [0.04, 0.04],
        end_effector_m=[0, 0, 0.2],
        finger_force_n=[0, 0],
        robot_device_force_n=0,
        robot_table_force_n=0,
        payload_table_force_n=1.0,
    )
    supported = dict(released, joint_actual=[0] * 7 + [0.025, 0.025], finger_force_n=[1, 1])
    targets = dict(loaded=np.zeros(3), returned=np.zeros(3))
    rows = [supported] + [copy.deepcopy(released) for _ in range(360)]
    assert score(unit, rows, targets, np.zeros(3), 1 / 120)["task_success"]
    # Landing in the target after opening in the air is not a controlled placement.
    rows[0] = dict(supported, position_m=[0, 0, 0.06], payload_table_force_n=0)
    assert not score(unit, rows, targets, np.zeros(3), 1 / 120)["task_success"]
    unit["initial_grasp_contact_N"] = [0, 0]
    rows[0] = supported
    assert not score(unit, rows, targets, np.zeros(3), 1 / 120)["task_success"]


@pytest.mark.parametrize(
    "arguments,message",
    [
        (["dataset-check"], "--path"),
        (["eval", "--unit", "ika_open", "--backend", "pi05"], "--checkpoint"),
        (["eval", "--unit", "ika_open", "--max-actions", "0"], "positive"),
    ],
)
def test_cli_rejects_missing_inputs_before_gpu(tmp_path, capsys, arguments, message):
    with pytest.raises(SystemExit) as error:
        main(arguments + ["--output", str(tmp_path / "new"), "--dry-run"])
    assert error.value.code == 2
    assert message in capsys.readouterr().err
    assert not (tmp_path / "new").exists()


def test_external_rpc_does_not_require_local_checkpoint(tmp_path):
    assert (
        main(
            [
                "serve",
                "--unit",
                "magsep_transfer",
                "--backend",
                "pi05",
                "--initial-state",
                "placement-ready",
                "--output",
                str(tmp_path / "new"),
                "--dry-run",
            ]
        )
        == 0
    )


def test_close_partial_initialization_keeps_h5_incomplete(tmp_path):
    from unittest.mock import Mock
    from demos.cell_units.environment import UnitTask
    import h5py

    task = UnitTask("ika_open", tmp_path / "run")
    task.video = Mock()
    task.recorder = Recorder(task.output, dict(scene_version="SingleCellUnit_v2"))
    task.close()
    task.video.close.assert_called_once()
    with h5py.File(task.output / "episode.h5") as f:
        assert not f.attrs["closed"]
    assert not (task.output / "complete.json").exists()


@pytest.mark.parametrize("corruption", ["late_nan", "shape", "end_time"])
def test_dataset_checks_beyond_the_preview_batch(tmp_path, corruption):
    import h5py

    rec = Recorder(
        tmp_path,
        dict(
            scene_version="SingleCellUnit_v2",
            backend="teacher",
            record_purpose="demonstration",
            physics_hz=120,
        ),
    )

    def obs(t):
        return dict(
            simulation_time=t,
            joint_positions=np.zeros(9),
            joint_velocities=np.zeros(9),
            TCPpose=dict(position_m=[0, 0, 0], quaternion_wxyz=[1, 0, 0, 0]),
            images={k: np.ones((8, 8, 3), np.uint8) for k in ("side_camera", "wrist_camera")},
        )

    rec.observation(obs(0))
    for i in range(10):
        rec.physics(dict(time_s=(i + 1) / 120, joint_target=[0] * 9))
        rec.transition(obs((i + 1) / 120))
    rec.close(dict(task_success=False, termination_reason="POLICY_BUDGET"))
    assert check_dataset(tmp_path)["validated_action_blocks"] == 10
    with h5py.File(rec.path, "r+") as f:
        if corruption == "late_nan":
            f["actions/joint_targets"][-1, 0, 0] = np.nan
        elif corruption == "end_time":
            f["actions/time_end_s"][-1] = 100
        else:
            del f["actions/joint_targets"]
            f["actions/joint_targets"] = np.zeros((10, 4, 8))
    with pytest.raises(ValueError):
        check_dataset(tmp_path)


def test_hood_requires_withdrawal_for_the_whole_stable_window():
    row = dict(
        joint_actual=[0] * 7 + [0.04, 0.04],
        end_effector_m=[0, 0, 0.2],
        handle_force_n=[0, 0],
        unintended_robot_device_force_n=0,
        robot_environment_force_n=0,
        hood_angle_rad=1.3,
    )
    grasp = dict(
        row, joint_actual=[0] * 7 + [0.02, 0.02], end_effector_m=[0, 0, 0], handle_force_n=[1, 1]
    )
    rows = [grasp] + [copy.deepcopy(row) for _ in range(360)]
    targets = dict(initial_angle_rad=0)
    assert score(get_unit("ika_open"), rows, targets, np.zeros(3), 1 / 120)["task_success"]
    rows[-2]["end_effector_m"] = [0, 0, 0.05]
    assert not score(get_unit("ika_open"), rows, targets, np.zeros(3), 1 / 120)["checks"][
        "withdrawn_12cm"
    ]


def test_public_unit_constructor_reports_invalid_inputs_without_output(tmp_path):
    from demos.cell_units.environment import UnitTask
    for unit_id, initial in [('unknown','default'),('ika_open','typo'),('ika_open','placement-ready')]:
        with pytest.raises(ValueError):
            UnitTask(unit_id,tmp_path/'new',backend='external',initial_state=initial)
        assert not (tmp_path/'new').exists()
