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
    parser.add_argument(
        "--doctor",
        action="store_true",
        help="Print runtime diagnostics instead of installing or verifying.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.doctor:
        result = freecad_runtime.doctor_runtime(sheetmetal_repo=args.sheetmetal_repo)
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print("FreeCAD unfold runtime doctor")
            print(f"  platform: {result['platform']}")
            print(f"  runtime_root: {result['runtime_root']}")
            print(f"  auto_install_enabled: {result['auto_install_enabled']}")
            print(f"  auto_bootstrap_package_manager_enabled: {result['auto_bootstrap_package_manager_enabled']}")
            pkg = result["package_manager"]
            print(f"  package_manager: {pkg.get('chosen') or '(none)'}")
            verify = result["verify"]
            print(f"  verify_success: {verify.get('success')}")
            if verify.get("error"):
                print(f"  verify_error: {verify['error']}")
        return 0

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
        if result.get("actions"):
            print(f"  actions: {', '.join(result['actions'])}")
        print("Use this runtime via the normal pipeline; config is persisted automatically.")
    else:
        print(result.get("error") or "Managed FreeCAD runtime check failed.", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
