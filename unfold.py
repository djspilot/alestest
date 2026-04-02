from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent


def _venv_python() -> Path:
    if os.name == "nt":
        return REPO_ROOT / ".venv" / "Scripts" / "python.exe"
    return REPO_ROOT / ".venv" / "bin" / "python"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Direct STEP unfold runner for this repo.",
    )
    parser.add_argument("step_file", help="Path to the STEP file to unfold.")
    parser.add_argument(
        "--variant",
        choices=("auto", "new", "old"),
        default="auto",
        help="SheetMetal unfolder variant selection. Default: auto.",
    )
    parser.add_argument(
        "--no-json",
        action="store_true",
        help="Print normal CLI output instead of JSON.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    python_exe = _venv_python()
    if not python_exe.exists():
        python_exe = Path(sys.executable)

    env = os.environ.copy()
    env["FREECAD_UNFOLD_MODE"] = "direct-python"
    env["FREECAD_UNFOLDER_VARIANT"] = args.variant

    command = [
        str(python_exe),
        "-m",
        "manufacturing_pipeline",
        "--unfold-only",
        "-f",
        str(Path(args.step_file)),
    ]
    if not args.no_json:
        command.append("--json")

    print(">>>", " ".join(command))
    print(f">>> FREECAD_UNFOLD_MODE={env['FREECAD_UNFOLD_MODE']}")
    print(f">>> FREECAD_UNFOLDER_VARIANT={env['FREECAD_UNFOLDER_VARIANT']}")
    completed = subprocess.run(command, cwd=REPO_ROOT, env=env)
    return int(completed.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
