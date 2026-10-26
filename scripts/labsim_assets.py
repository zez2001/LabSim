"""Standalone standard-library asset command; also used by ./labsim assets."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from demos.lab_cuvette_project_v1.assets import (
    AssetError, DEFAULT_LOCK, check_assets, download_assets, load_lock,
    materialize_assets, selected_files)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("list", "download", "install", "check"))
    parser.add_argument("--lock", type=Path, default=DEFAULT_LOCK)
    parser.add_argument("--task", default="lab_cuvette_loading")
    parser.add_argument("--cache", type=Path)
    parser.add_argument("--asset-root", type=Path, help="Portable asset tree, preserving assets/... layout")
    parser.add_argument("--private-root", type=Path, help="Authorized local-only model tree; never uploaded")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--public-only", action="store_true", help="Install only publicly released dependencies")
    args = parser.parse_args(argv)
    try:
        if args.command == "list":
            lock = load_lock(args.lock)
            result = {"repository": lock["repository"], "revision": lock["revision"],
                      "files": selected_files(lock, args.task, include_local=True),
                      "assets": lock.get("assets", [])}
        elif args.command == "download":
            result = download_assets(args.lock, task=args.task, cache=args.cache, offline=args.offline)
        elif args.command == "install":
            if not args.asset_root:
                parser.error("install requires --asset-root")
            result = materialize_assets(args.asset_root, args.lock, task=args.task,
                cache=args.cache, private_root=args.private_root, offline=args.offline,
                include_local=not args.public_only)
        else:
            if not args.asset_root:
                parser.error("check requires --asset-root")
            result = check_assets(args.asset_root, args.lock, task=args.task)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0 if result.get("all_files_verified", True) else 2
    except (AssetError, OSError, ValueError) as error:
        print("ASSET_ERROR: " + str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
