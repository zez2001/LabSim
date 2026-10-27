"""CPU cleanup-order fixtures only, not proof about native GUI warnings."""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from demos.lab_cuvette_project_release_v1.shutdown import ReleaseShutdownError, close_release_application


class ReleaseShutdownContracts(unittest.TestCase):
    def fixtures(self, *, environment_error=False, reject_extension=False, app_error=False):
        calls = []
        enabled = {"isaacsim.gui.menu": True, "omni.kit.menu.utils": True}
        class Environment:
            def close(self):
                calls.append("environment.close")
                if environment_error:
                    raise OSError("fixture writer close failure")
        class Manager:
            def get_enabled_extension_id(self, name):
                return name if enabled[name] else ""
            def set_extension_enabled_immediate(self, name, value):
                calls.append("disable:" + name)
                if reject_extension:
                    return False
                enabled[name] = value
                return True
        class App:
            def close(self, **kwargs):
                calls.append(("app.close", kwargs))
                if app_error:
                    raise RuntimeError("fixture app close failure")
        return calls, Environment(), SimpleNamespace(get_extension_manager=lambda: Manager()), App()

    def test_writers_then_menu_owners_then_sdk_full_cleanup(self):
        calls, env, kit, app = self.fixtures()
        result = close_release_application(app, environment=env, kit_app=kit, context_provider=lambda: object())
        self.assertEqual(calls[:3], ["environment.close", "disable:isaacsim.gui.menu", "disable:omni.kit.menu.utils"])
        self.assertEqual(calls[3], ("app.close", dict(wait_for_replicator=True, skip_cleanup=False)))
        self.assertTrue(result["application_close_returned"])
        self.assertFalse(result["native_warning_absence_verified"])

    def test_environment_close_failure_still_closes_application_and_is_reported(self):
        calls, env, kit, app = self.fixtures(environment_error=True)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "shutdown.json"
            with self.assertRaisesRegex(ReleaseShutdownError, "writer close failure"):
                close_release_application(app, environment=env, kit_app=kit,
                    context_provider=lambda: object(), report_path=path)
            result = json.loads(path.read_text())
            self.assertTrue(result["application_close_returned"])
            self.assertFalse(result["successful_cleanup_calls"])
        self.assertEqual(calls[-1][0], "app.close")

    def test_refused_extension_unload_or_missing_context_does_not_skip_app_close(self):
        for missing_context in (False, True):
            calls, env, kit, app = self.fixtures(reject_extension=not missing_context)
            with self.assertRaises(ReleaseShutdownError):
                close_release_application(app, environment=env, kit_app=kit,
                    context_provider=(lambda: None) if missing_context else (lambda: object()))
            self.assertEqual(calls[-1][0], "app.close")

    def test_sdk_failure_is_never_swallowed(self):
        calls, env, kit, app = self.fixtures(app_error=True)
        with self.assertRaisesRegex(ReleaseShutdownError, "app close failure"):
            close_release_application(app, environment=env, kit_app=kit, context_provider=lambda: object())


if __name__ == "__main__":
    unittest.main()
