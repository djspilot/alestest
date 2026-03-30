from __future__ import annotations

import importlib.util
import subprocess
import sys
from typing import Any, Dict, List


HOST_DEPENDENCIES = [
    {
        "label": "cadquery",
        "module": "cadquery",
        "pip": "cadquery>=2.4.0",
    },
    {
        "label": "cadquery-ocp",
        "module": "OCP",
        "pip": "cadquery-ocp",
    },
    {
        "label": "shapely",
        "module": "shapely",
        "pip": "shapely",
    },
]


def auto_install_python_dependencies_enabled() -> bool:
    value = str(__import__("os").environ.get("PIPELINE_AUTO_INSTALL_PY_DEPS", "0")).strip().lower()
    return value in {"1", "true", "yes", "on"}


def missing_host_dependencies() -> List[Dict[str, str]]:
    missing = []
    for dep in HOST_DEPENDENCIES:
        if importlib.util.find_spec(dep["module"]) is None:
            missing.append(dep)
    return missing


def install_command_for_missing_dependencies(missing: List[Dict[str, str]]) -> List[str]:
    packages = [dep["pip"] for dep in missing]
    return [sys.executable, "-m", "pip", "install", *packages]


def ensure_host_python_dependencies(install_if_missing: bool = False) -> Dict[str, Any]:
    missing = missing_host_dependencies()
    if not missing:
        return {
            "success": True,
            "installed": False,
            "missing": [],
            "command": [],
        }

    command = install_command_for_missing_dependencies(missing)
    if not install_if_missing:
        return {
            "success": False,
            "installed": False,
            "missing": [dep["label"] for dep in missing],
            "error": "Ontbrekende host Python dependencies: " + ", ".join(dep["label"] for dep in missing),
            "command": command,
        }

    try:
        subprocess.run(command, check=True)
    except Exception as exc:
        return {
            "success": False,
            "installed": False,
            "missing": [dep["label"] for dep in missing],
            "error": f"Installatie van host Python dependencies gefaald: {exc}",
            "command": command,
        }

    remaining = missing_host_dependencies()
    if remaining:
        return {
            "success": False,
            "installed": True,
            "missing": [dep["label"] for dep in remaining],
            "error": "Dependencies nog steeds niet importeerbaar na installatie",
            "command": install_command_for_missing_dependencies(remaining),
        }

    return {
        "success": True,
        "installed": True,
        "missing": [],
        "command": command,
    }


def doctor_host_python_dependencies() -> Dict[str, Any]:
    missing = missing_host_dependencies()
    return {
        "python": sys.executable,
        "missing": [dep["label"] for dep in missing],
        "auto_install_enabled": auto_install_python_dependencies_enabled(),
        "command": install_command_for_missing_dependencies(missing) if missing else [],
        "success": not missing,
    }
