"""Expose the local LabSim extension to the installed RPent CLI registry.

Only this process's namespace search path is extended. No installed RPent files,
robot registry, global configuration or user memory are modified.
"""
from pathlib import Path
import sys
import os


def register_extension():
    import robots
    from rpent.utils.config import get_repo_root
    installed_root = str(get_repo_root() / "robots")
    if installed_root not in robots.__path__:
        robots.__path__.append(installed_root)
    extension_root = str(Path(__file__).resolve().parent / "robots")
    if extension_root not in robots.__path__:
        robots.__path__.append(extension_root)


def main():
    register_extension()
    if "--memory-profile" not in sys.argv:
        sys.argv.extend(["--memory-profile", "local"])
    if "labsim_cuvette" in sys.argv:
        # Match policy_runner's evaluation boundary, including native Codex
        # built-ins outside the MCP Toolkit. This modifies only this process.
        from .policy_runner import RestrictedLabSimCodexPlanner
        import rpent.planner.codex as codex_backend
        codex_backend.CodexPlanner = RestrictedLabSimCodexPlanner
        os.environ.setdefault("CODEX_BIN", "/usr/lib/chatgpt/resources/codex")
        if "--planner" not in sys.argv:
            sys.argv.extend(["--planner", "codex"])
        if "--model" not in sys.argv:
            sys.argv.extend(["--model", "gpt-6-astra"])
        if "--reasoning-effort" not in sys.argv:
            sys.argv.extend(["--reasoning-effort", "medium"])
    from rpent.cli.main import main as rpent_main
    rpent_main()


if __name__ == "__main__":
    main()
