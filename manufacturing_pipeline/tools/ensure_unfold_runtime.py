from __future__ import annotations

import argparse
import json
import sys

from manufacturing_pipeline.core import freecad_runtime


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ensure a managed headless FreeCAD runtime for sheet-metal unfolding.",
    )
    parser.add_argument(
        "--no-install",
        action="store_true",
        help="Only verify the configured runtime; do not install if missing.",
    )
    parser.add_argument(
        "--update-sheetmetal",
        action="store_true",
        help="Pull the SheetMetal source if it already exists.",
    )
    parser.add_argument(
        "--package-manager",
        help="Override package manager path or command (micromamba/conda).",
    )
    parser.add_argument(
        "--sheetmetal-repo",
        default=freecad_runtime.DEFAULT_SHEETMETAL_REPO,
        help="Git repository to install as the SheetMetal workbench.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = freecad_runtime.ensure_managed_runtime(
        install_if_missing=not args.no_install,
        package_manager=args.package_manager,
        sheetmetal_repo=args.sheetmetal_repo,
        update_sheetmetal=args.update_sheetmetal,
    )

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    elif result.get("success"):
        runtime = result.get("runtime") or {}
        action = "installed" if result.get("installed") else "verified"
        print(f"Managed FreeCAD runtime {action}.")
        print(f"  root: {runtime.get('runtime_root')}")
        print(f"  cmd:  {runtime.get('freecad_cmd')}")
        print(f"  mod:  {runtime.get('freecad_mod')}")
        print("Use this runtime via the normal pipeline; config is persisted automatically.")
    else:
        print(result.get("error") or "Managed FreeCAD runtime check failed.", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
