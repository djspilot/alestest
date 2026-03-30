from __future__ import annotations

import argparse
import json
import sys

from manufacturing_pipeline.core import python_dependencies


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ensure host Python dependencies such as cadquery are available.",
    )
    parser.add_argument(
        "--doctor",
        action="store_true",
        help="Show dependency diagnostics instead of installing.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON.",
    )
    parser.add_argument(
        "--no-install",
        action="store_true",
        help="Only verify dependencies; do not install if missing.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.doctor:
        result = python_dependencies.doctor_host_python_dependencies()
    else:
        result = python_dependencies.ensure_host_python_dependencies(
            install_if_missing=not args.no_install,
        )

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    elif result.get("success"):
        action = "installed" if result.get("installed") else "verified"
        print(f"Host Python dependencies {action}.")
        if result.get("command"):
            print(f"  command: {' '.join(result['command'])}")
    else:
        print(result.get("error") or "Host Python dependency check failed.", file=sys.stderr)
        if result.get("command"):
            print(f"Install with: {' '.join(result['command'])}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
