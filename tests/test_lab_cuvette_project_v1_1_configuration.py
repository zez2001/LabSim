"""Static release wiring checks; no Isaac app, assets, or model API is started."""
import ast
from pathlib import Path
import unittest

from omegaconf import OmegaConf


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config/lab_cuvette_loading/Project_v1_1/standard.yaml"
PREVIOUS = ROOT / "config/lab_cuvette_loading/Project_v1/standard.yaml"


def registrations(path, function):
    tree = ast.parse(path.read_text())
    found = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == function:
            if node.args and isinstance(node.args[0], ast.Constant):
                name = node.args[0].value
                if name in found:
                    raise AssertionError("Duplicate factory name: " + name)
                found[name] = node.args[1].id
    return found


class ProjectV11ConfigurationTest(unittest.TestCase):
    def setUp(self):
        self.current = OmegaConf.to_container(OmegaConf.load(CONFIG), resolve=True)
        self.previous = OmegaConf.to_container(OmegaConf.load(PREVIOUS), resolve=True)

    def test_new_version_has_independent_paths_and_existing_teacher(self):
        c = self.current
        self.assertEqual(c["version"], "Project_v1_1")
        self.assertEqual(c["task_type"], "lab_cuvette_project_v1_1")
        self.assertEqual(c["collector_type"], "lab_cuvette_project_v1_1")
        self.assertEqual(c["controller_type"], "lab_cuvette_project_v1_teacher")
        self.assertEqual(c["output_root"], "outputs/lab_cuvette_loading/Project_v1_1")
        self.assertEqual(c["env"]["geometry_audit_cache"], c["output_root"] + "/geometry_cache")
        self.assertEqual(c["env"]["scorer_module"], "demos.lab_cuvette_project_v1_1.scorer")
        self.assertEqual(c["project"]["action_interface_version"], "Project_v1_1.actions.v1")
        self.assertEqual(c["project"]["scorer_version"], "Project_v1_1.independent.v1")
        self.assertNotEqual(c["env"]["geometry_audit_cache"], self.previous["env"]["geometry_audit_cache"])

    def test_assets_physics_and_physical_task_gates_are_identical(self):
        for key in ("physics", "acceptance", "control", "demo_release", "gripper", "robot", "scene",
                    "rack", "adapter", "vessel", "source", "geometry", "randomization", "video",
                    "asset_directory", "derived_directory", "asset_registry", "asset_id", "asset_selection",
                    "collection", "training_scene"):
            self.assertEqual(self.current[key], self.previous[key], key)
        self.assertEqual(self.current["env"], dict(self.previous["env"],
            scorer_module="demos.lab_cuvette_project_v1_1.scorer",
            geometry_audit_cache="outputs/lab_cuvette_loading/Project_v1_1/geometry_cache"))

    def test_wrist_changes_fixed_aim_only_and_keeps_global_side_view(self):
        self.assertEqual(self.current["cameras"]["side_camera"], self.previous["cameras"]["side_camera"])
        before = self.previous["cameras"]["wrist_camera"]
        after = self.current["cameras"]["wrist_camera"]
        self.assertEqual(before["localtarget_m"], [0, 0, .35])
        self.assertEqual(after, dict(before, localeye_m=[.075,0,.04], localtarget_m=[0, 0, .12],
            prim_path="/World/Franka/panda_hand/WristCameraV11"))

    def test_executor_fields_match_the_new_tasks_actual_consumers(self):
        expected = dict(maximum_position_tracking_error_m=.005,
            maximum_orientation_tracking_error_deg=2., maximum_actual_TCP_speed_m_s=.05,
            maximum_actual_joint_speed_factor=1.25, ik_position_tolerance_m=2e-6,
            ik_orientation_tolerance_rad=2e-5, ik_iterations=35)
        self.assertEqual(self.current["executor"], expected)
        tree = ast.parse((ROOT / "tasks/lab_cuvette_loading_project_v1_1.py").read_text())
        consumed = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)
            and isinstance(n.value, ast.Attribute) and n.value.attr == "executor"
            and isinstance(n.value.value, ast.Attribute) and n.value.value.attr == "cfg"}
        self.assertEqual(consumed, set(expected))

    def test_new_factories_preserve_existing_native_and_minimal_names(self):
        tasks = registrations(ROOT / "factories/task_factory.py", "register_task")
        collectors = registrations(ROOT / "factories/collector_factory.py", "register_collector")
        self.assertEqual(tasks["lab_cuvette_project_v1_1"], "LabCuvetteProjectV11")
        self.assertEqual(collectors["lab_cuvette_project_v1_1"], "LabCuvetteProjectV11Collector")
        self.assertEqual(tasks["lab_cuvette_project_v1"], "LabCuvetteProjectV1")
        self.assertEqual(tasks["lab_cuvette_env_v1"], "LabCuvetteLoadingEnvV1")
        self.assertEqual(tasks["minimal_pick"], "MinimalPickTask")
        self.assertEqual(collectors["lab_cuvette_project_v1"], "LabCuvetteEnvV1Collector")
        self.assertEqual(collectors["minimal_pick"], "MinimalPickCollector")


if __name__ == "__main__":
    unittest.main()
