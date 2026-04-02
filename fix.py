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


def _run(command: list[str]) -> int:
    print(">>>", " ".join(command))
    completed = subprocess.run(command, cwd=REPO_ROOT)
    return int(completed.returncode)


def _run_windows_fix(force_reinstall: bool, skip_viewer: bool, doctor_only: bool) -> int:
    bootstrap = REPO_ROOT / "scripts" / "bootstrap-windows.ps1"
    doctor = REPO_ROOT / "scripts" / "freecad-windows-doctor.ps1"

    if not bootstrap.exists():
        print(f"Bootstrap script niet gevonden: {bootstrap}", file=sys.stderr)
        return 1

    bootstrap_cmd = [
        "powershell",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(bootstrap),
    ]
    if doctor_only:
        bootstrap_cmd.append("-DoctorOnly")
    else:
        bootstrap_cmd.append("-SkipSystemDeps")
        if skip_viewer:
            bootstrap_cmd.append("-SkipViewer")
        if force_reinstall:
            bootstrap_cmd.append("-ForceFreeCADReinstall")

    rc = _run(bootstrap_cmd)
    if rc != 0:
        return rc

    if doctor_only:
        return 0

    if doctor.exists():
        return _run([
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(doctor),
        ])

    python_exe = _venv_python()
    if not python_exe.exists():
        print(f"Venv Python niet gevonden: {python_exe}", file=sys.stderr)
        return 1

    return _run([
        str(python_exe),
        "-m",
        "manufacturing_pipeline.tools.ensure_unfold_runtime",
        "--doctor",
    ])


def _run_non_windows_doctor() -> int:
    python_exe = _venv_python()
    if not python_exe.exists():
        python_exe = Path(sys.executable)
    return _run([
        str(python_exe),
        "-m",
        "manufacturing_pipeline.tools.ensure_unfold_runtime",
        "--doctor",
    ])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Repo-root fixer for FreeCAD runtime/bootstrap issues.",
    )
    parser.add_argument(
        "--doctor-only",
        action="store_true",
        help="Only run the existing doctor flow.",
    )
    parser.add_argument(
        "--no-force-reinstall",
        action="store_true",
        help="Do not pass -ForceFreeCADReinstall to the Windows bootstrapper.",
    )
    parser.add_argument(
        "--with-viewer",
        action="store_true",
        help="Also allow the Windows bootstrapper to install viewer dependencies.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if os.name == "nt":
        return _run_windows_fix(
            force_reinstall=not args.no_force_reinstall,
            skip_viewer=not args.with_viewer,
            doctor_only=args.doctor_only,
        )

    return _run_non_windows_doctor()


if __name__ == "__main__":
    raise SystemExit(main())
