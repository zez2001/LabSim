"""Launch one fixed instrument unit through teacher, GPT or public RPC."""

import argparse
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import traceback

from demos.cell_units.registry import ROOT, list_units


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("command", choices=("list", "demo", "collect", "eval", "serve", "dataset-check"))
    p.add_argument("--unit", choices=tuple(u["id"] for u in list_units()))
    p.add_argument("--output", type=Path)
    p.add_argument("--path", type=Path, help="Closed unit episode H5 or directory")
    p.add_argument("--backend", choices=("teacher", "gpt6", "pi05"), default="teacher")
    p.add_argument("--initial-state", choices=("default", "placement-ready"), default="default")
    p.add_argument("--episodes", type=int, default=1)
    p.add_argument("--headless", action="store_true")
    p.add_argument("--cache", type=Path, default=ROOT / "local_assets")
    p.add_argument("--provider-config", type=Path)
    p.add_argument(
        "--budget-ledger", type=Path, default=ROOT / "local_setup/cell_units_budget.json"
    )
    p.add_argument(
        "--max-calls", type=int, help="Default: GPT 8; pi05 120 (up to 30 simulated seconds)"
    )
    p.add_argument("--max-actions", type=int, default=600)
    p.add_argument("--checkpoint", type=Path)
    p.add_argument("--port", type=int, default=8097)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    return p


def main(argv=None):
    p = parser()
    args = p.parse_args(argv)
    if args.max_calls is None:
        args.max_calls = 120 if args.backend == "pi05" else 8
    if args.command == "list":
        print((ROOT / "config/cell_units/units.json").read_text())
        return 0
    if args.command == "dataset-check":
        from demos.cell_units.recording import check_dataset

        if args.path is None:
            p.error("dataset-check requires --path")
        result = check_dataset(args.path)
        if args.output:
            with args.output.open("x") as f:
                json.dump(result, f, indent=2)
        print(json.dumps(result))
        return 0
    if not args.unit or not args.output:
        p.error("A run requires --unit and a new --output directory")
    if not 1 <= args.episodes <= 20 or args.max_calls < 1 or args.max_actions < 1:
        p.error("Use 1..20 episodes and positive call/action budgets")
    local_pi05 = args.command != "serve" and args.backend == "pi05"
    if local_pi05 and args.checkpoint is None:
        p.error("pi05 requires --checkpoint")
    if args.output.exists():
        p.error("Output exists; select a new directory")
    if args.command == "collect" and args.backend != "teacher":
        p.error("collect records expert demonstrations; use eval for policies")
    if args.initial_state == "placement-ready" and (
        args.unit not in ("flex_load", "magsep_transfer")
        or args.command not in ("eval", "serve")
        or (args.command == "eval" and args.backend == "teacher")
    ):
        p.error("placement-ready is a policy test for flex_load or magsep_transfer")
    if args.dry_run:
        print(
            json.dumps(
                dict(
                    unit=args.unit,
                    command=args.command,
                    backend=args.backend,
                    output=str(args.output),
                    gpu_started=False,
                )
            )
        )
        return 0
    if not args.worker:
        command = [
            sys.executable,
            "-m",
            "demos.cell_units.run",
            *(sys.argv[1:] if argv is None else argv),
            "--worker",
        ]
        result = subprocess.run(command)
        worker_status = args.output / "worker_status.json"
        worker_code = (
            json.loads(worker_status.read_text())["exit_code"] if worker_status.exists() else 1
        )
        if args.output.is_dir():
            (args.output / "process_exit.json").write_text(
                json.dumps(
                    dict(
                        child_returncode=result.returncode,
                        worker_exit_code=worker_code,
                        shutdown_mode="Isaac Sim fast_shutdown",
                        full_native_cleanup_verified=False,
                    ),
                    indent=2,
                )
                + "\n"
            )
        return (
            result.returncode if result.returncode >= 0 else 128 - result.returncode
        ) or worker_code
    client = None
    if args.backend == "gpt6" and args.command != "serve":
        from demos.cell_units.policy import make_client

        client = make_client(args.provider_config, args.budget_ledger)
    lock = open("/tmp/labsim-V0_ext01-gpu.lock", "a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    os.environ["OMNI_KIT_ACCEPT_EULA"] = "YES"
    if local_pi05:
        os.environ["JAX_PLATFORMS"] = "cpu"
        os.environ["TORCHDYNAMO_DISABLE"] = "1"
        os.environ.setdefault("OPENPI_DATA_HOME", str(ROOT / "local_assets/policies/openpi-cache"))
    from isaacsim import SimulationApp

    app = SimulationApp(
        dict(
            headless=args.headless,
            renderer="RayTracedLighting",
            limit_cpu_threads=8,
            multi_gpu=False,
            fast_shutdown=True,
        )
    )
    task = None
    code = 0
    try:
        from demos.cell_units.environment import UnitTask
        from demos.lab_cuvette_project_release_v1.environment import ProjectEnvironment

        backend = "external" if args.command == "serve" else args.backend
        task = UnitTask(args.unit, args.output, args.cache, backend, args.initial_state)
        facade = ProjectEnvironment(task)
        model = None
        if local_pi05:
            from demos.cell_units.pi05 import OpenPiModel

            model = OpenPiModel(args.checkpoint, args.output / "model")
        if args.command == "serve":
            from demos.cell_units.rpc import serve

            serve(facade, args.port)
        else:
            results = []
            for _ in range(args.episodes):
                facade.reset()
                if args.backend == "teacher":
                    task.run_teacher()
                elif args.backend == "pi05":
                    from demos.cell_units.pi05 import run as run_pi05

                    run_pi05(
                        facade, model, task.episode_dir / "pi05", args.max_calls, args.max_actions
                    )
                else:
                    from policy.backends.cubence_project_v1_1_tools import run_episode
                    from demos.cell_units.policy import PROMPT

                    run_episode(
                        facade,
                        client,
                        task.episode_dir / "gpt",
                        max_calls=args.max_calls,
                        prompt=PROMPT,
                    )
                results.append(task._result)
            task._write(args.output / "summary.json", dict(unit_id=args.unit, results=results))
            print("UNIT_RESULTS", json.dumps(results), flush=True)
            if args.backend == "teacher" and not all(result["task_success"] for result in results):
                code = 1
    except BaseException:
        code = 1
        traceback.print_exc()
        raise
    finally:
        # The parent records the real exit: Isaac's supported fast shutdown
        # terminates Python inside app.close. Writers must close beforehand.
        if task is not None:
            task.close()
        if args.output.is_dir():
            (args.output / "worker_status.json").write_text(
                json.dumps(dict(exit_code=code, writers_closed=True)) + "\n"
            )
        lock.close()
        app.close()
    return code


if __name__ == "__main__":
    raise SystemExit(main())
