"""Release-only orderly teardown of the installed Isaac 5.1 menu callbacks.

No installed code or callback is patched. All writers close first, then the
official extension manager unloads menu owners while USD is still alive. The
SDK owns final application cleanup; no preceding post_quit races that cleanup.
"""
from __future__ import annotations

import json
from pathlib import Path
import time


class ReleaseShutdownError(RuntimeError):
    pass


def close_release_application(app, *, environment=None, report_path=None,
                              kit_app=None, context_provider=None):
    """Close owned resources in order and retain any cleanup failure.

    Optional providers permit CPU protocol tests; they are never used as native
    validation. No app.update/world.step or logging suppression is performed.
    """
    started = time.perf_counter()
    report = dict(schema="labsim.Project_release_v1.application_shutdown.v1",
                  version="menu_callback_owner_order.v1", steps=[], errors=[],
                  application_close_returned=False, native_warning_absence_verified=False)

    def step(name, operation):
        start = time.perf_counter()
        row = dict(step=name)
        try:
            details = operation()
            if isinstance(details, dict):
                row.update(details)
            row["ok"] = True
        except BaseException as error:
            row.update(ok=False, error_type=type(error).__name__, error=str(error))
            report["errors"].append(dict(row))
        finally:
            row["wall_seconds"] = time.perf_counter() - start
            report["steps"].append(row)

    if environment is not None:
        step("close_environment_writers_and_world", environment.close)

    def unload_menu_owners():
        nonlocal kit_app, context_provider
        if kit_app is None:
            from omni.kit.app import get_app
            kit_app = get_app()
        if context_provider is None:
            import omni.usd
            context_provider = omni.usd.get_context
        manager = kit_app.get_extension_manager()
        before = context_provider() is not None
        rows = []
        if not before:
            raise RuntimeError("USD context already unavailable before menu-owner teardown")
        for name in ("isaacsim.gui.menu", "omni.kit.menu.utils"):
            begin = time.perf_counter()
            enabled_before = bool(manager.get_enabled_extension_id(name))
            result = None
            if enabled_before:
                result = manager.set_extension_enabled_immediate(name, False)
            enabled_after = bool(manager.get_enabled_extension_id(name))
            row = dict(extension=name, enabled_before=enabled_before, enabled_after=enabled_after,
                       API_return=None if result is None else bool(result),
                       USD_context_available=context_provider() is not None,
                       wall_seconds=time.perf_counter() - begin)
            rows.append(row)
            # Save partial details even when a later extension fails.
            report["menu_extensions"] = rows
            if enabled_after:
                raise RuntimeError("Menu owner remained enabled after official unload: " + name)
            if not row["USD_context_available"]:
                raise RuntimeError("USD context disappeared during menu-owner teardown")
        return dict(USD_context_available_before=before, menu_extensions=rows,
                    API="ExtensionManager.set_extension_enabled_immediate(name, False)")

    step("unload_menu_owners_before_USD", unload_menu_owners)

    def close_app():
        app.close(wait_for_replicator=True, skip_cleanup=False)
        report["application_close_returned"] = True

    step("SimulationApp.close_full_cleanup", close_app)
    report["wall_seconds"] = time.perf_counter() - started
    report["successful_cleanup_calls"] = not report["errors"]
    if report_path is not None:
        Path(report_path).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    if report["errors"]:
        raise ReleaseShutdownError("Release cleanup failed; inspect application_shutdown.json: " +
                                   "; ".join(row["step"] + ": " + row["error"] for row in report["errors"]))
    return report
