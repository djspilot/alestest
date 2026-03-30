from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Dict, List, Optional

from manufacturing_pipeline.core.paths import PROJECT_ROOT

MANAGED_RUNTIME_DIR = os.path.join(PROJECT_ROOT, ".runtime", "freecad")
MANAGED_RUNTIME_METADATA = os.path.join(PROJECT_ROOT, ".runtime", "freecad_runtime.json")
DEFAULT_SHEETMETAL_REPO = "https://github.com/shaise/FreeCAD_SheetMetal.git"


def managed_runtime_root(project_root: Optional[str] = None) -> str:
    root = project_root or PROJECT_ROOT
    return os.path.join(root, ".runtime", "freecad")


def managed_runtime_metadata_path(project_root: Optional[str] = None) -> str:
    root = project_root or PROJECT_ROOT
    return os.path.join(root, ".runtime", "freecad_runtime.json")


def _dedupe(items: List[str]) -> List[str]:
    seen = set()
    ordered: List[str] = []
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


def _candidate_paths(runtime_root: str, platform: Optional[str] = None) -> Dict[str, List[str]]:
    platform = platform or sys.platform
    if platform.startswith("win"):
        return {
            "freecad_cmd": [
                os.path.join(runtime_root, "Library", "bin", "FreeCADCmd.exe"),
                os.path.join(runtime_root, "Library", "bin", "freecadcmd.exe"),
                os.path.join(runtime_root, "bin", "FreeCADCmd.exe"),
                os.path.join(runtime_root, "bin", "freecadcmd.exe"),
            ],
            "freecad_python": [
                os.path.join(runtime_root, "python.exe"),
                os.path.join(runtime_root, "Library", "bin", "python.exe"),
                os.path.join(runtime_root, "bin", "python.exe"),
            ],
            "freecad_lib": [
                os.path.join(runtime_root, "Library", "bin"),
                os.path.join(runtime_root, "Library", "lib"),
                os.path.join(runtime_root, "Lib", "site-packages"),
                os.path.join(runtime_root, "bin"),
            ],
            "freecad_mod": [
                os.path.join(runtime_root, "Mod"),
                os.path.join(runtime_root, "Library", "Mod"),
            ],
        }

    return {
        "freecad_cmd": [
            os.path.join(runtime_root, "bin", "FreeCADCmd"),
            os.path.join(runtime_root, "bin", "freecadcmd"),
        ],
        "freecad_python": [
            os.path.join(runtime_root, "bin", "python"),
            os.path.join(runtime_root, "bin", "python3"),
        ],
        "freecad_lib": [
            os.path.join(runtime_root, "lib"),
            os.path.join(runtime_root, "lib", "python3", "site-packages"),
        ],
        "freecad_mod": [
            os.path.join(runtime_root, "Mod"),
            os.path.join(runtime_root, "share", "freecad", "Mod"),
            os.path.join(runtime_root, "share", "FreeCAD", "Mod"),
        ],
    }


def detect_runtime_layout(runtime_root: str, platform: Optional[str] = None) -> Dict[str, str]:
    candidates = _candidate_paths(runtime_root, platform=platform)
    resolved = {
        "runtime_root": runtime_root,
        "freecad_path": runtime_root,
    }
    for key, values in candidates.items():
        existing = next((value for value in values if os.path.exists(value)), "")
        resolved[key] = existing or (values[0] if values else "")
    return resolved


def load_runtime_metadata(metadata_path: Optional[str] = None) -> Dict[str, Any]:
    path = metadata_path or MANAGED_RUNTIME_METADATA
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, dict):
            return data
    except Exception:
        return {}
    return {}


def save_runtime_metadata(data: Dict[str, Any], metadata_path: Optional[str] = None) -> str:
    path = metadata_path or MANAGED_RUNTIME_METADATA
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, sort_keys=True)
    return path


def configured_runtime(project_root: Optional[str] = None) -> Dict[str, Any]:
    metadata = load_runtime_metadata(managed_runtime_metadata_path(project_root))
    runtime_root = str(metadata.get("runtime_root") or "")
    if not runtime_root:
        return {}
    detected = detect_runtime_layout(runtime_root, platform=metadata.get("platform"))
    merged = {**detected, **metadata}
    merged["runtime_root"] = runtime_root
    merged["available"] = bool(merged.get("freecad_cmd") and os.path.exists(merged["freecad_cmd"]))
    return merged


def runtime_root_candidates(project_root: Optional[str] = None) -> List[str]:
    candidates: List[str] = []
    env_runtime_root = os.environ.get("FREECAD_RUNTIME_ROOT")
    if env_runtime_root:
        candidates.append(env_runtime_root)
    metadata = configured_runtime(project_root)
    if metadata.get("runtime_root"):
        candidates.append(str(metadata["runtime_root"]))
    candidates.append(managed_runtime_root(project_root))
    return _dedupe(candidates)


def choose_package_manager() -> str:
    env_value = os.environ.get("FREECAD_PACKAGE_MANAGER")
    if env_value:
        return env_value
    for candidate in ("micromamba", "conda"):
        path = shutil.which(candidate)
        if path:
            return path
    return ""


def _run_command(command: List[str]) -> None:
    subprocess.run(command, check=True)


def _verify_runtime(runtime_info: Dict[str, Any]) -> Dict[str, Any]:
    freecad_cmd = str(runtime_info.get("freecad_cmd") or "")
    freecad_mod = str(runtime_info.get("freecad_mod") or "")
    if not freecad_cmd or not os.path.exists(freecad_cmd):
        return {
            "success": False,
            "error": "FreeCADCmd niet gevonden na installatie",
        }

    script = (
        "import json, os, sys\n"
        f"mod_path = {json.dumps(freecad_mod)}\n"
        "if mod_path and os.path.isdir(mod_path) and mod_path not in sys.path:\n"
        "    sys.path.insert(0, mod_path)\n"
        "import FreeCAD\n"
        "import Part\n"
        "import SheetMetalUnfolder\n"
        "print(json.dumps({'success': True}))\n"
    )

    tmp_file = None
    try:
        with tempfile.NamedTemporaryFile("w", suffix="_verify_freecad.py", delete=False, encoding="utf-8") as handle:
            handle.write(script)
            tmp_file = handle.name
        proc = subprocess.run(
            [freecad_cmd, tmp_file],
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
    except Exception as exc:
        return {
            "success": False,
            "error": f"Runtime verificatie gefaald: {exc}",
        }
    finally:
        if tmp_file and os.path.exists(tmp_file):
            try:
                os.remove(tmp_file)
            except OSError:
                pass

    for line in reversed((proc.stdout or "").splitlines()):
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            payload = json.loads(line)
        except Exception:
            continue
        if payload.get("success"):
            return {"success": True}

    return {
        "success": False,
        "error": (proc.stderr or proc.stdout or "Runtime verificatie gaf geen geldig resultaat").strip(),
    }


def ensure_managed_runtime(
    install_if_missing: bool = True,
    runtime_root: Optional[str] = None,
    package_manager: Optional[str] = None,
    sheetmetal_repo: str = DEFAULT_SHEETMETAL_REPO,
    update_sheetmetal: bool = False,
) -> Dict[str, Any]:
    runtime_root = runtime_root or managed_runtime_root()
    runtime_info = detect_runtime_layout(runtime_root)

    if os.path.exists(runtime_info["freecad_cmd"]):
        verify_result = _verify_runtime(runtime_info)
        if verify_result.get("success"):
            metadata = {
                **runtime_info,
                "platform": sys.platform,
                "sheetmetal_repo": sheetmetal_repo,
                "manager": "existing",
            }
            save_runtime_metadata(metadata)
            return {
                "success": True,
                "installed": False,
                "runtime": metadata,
            }
        if not install_if_missing:
            return {
                "success": False,
                "installed": False,
                "error": verify_result.get("error") or "Bestaande runtime verificatie gefaald",
            }

    if not install_if_missing:
        return {
            "success": False,
            "installed": False,
            "error": "Geen beheerde FreeCAD runtime gevonden",
        }

    manager = package_manager or choose_package_manager()
    if not manager:
        return {
            "success": False,
            "installed": False,
            "error": "Geen package manager gevonden. Installeer micromamba of conda.",
        }

    git_executable = shutil.which("git")
    if not git_executable:
        return {
            "success": False,
            "installed": False,
            "error": "Git niet gevonden. Installeer git om de SheetMetal broncode op te halen.",
        }

    os.makedirs(runtime_root, exist_ok=True)
    create_cmd = [
        manager,
        "create",
        "-y",
        "-p",
        runtime_root,
        "-c",
        "conda-forge",
        "freecad",
        "git",
    ]
    try:
        _run_command(create_cmd)
    except Exception as exc:
        return {
            "success": False,
            "installed": False,
            "error": f"Runtime installatie gefaald: {exc}",
            "command": create_cmd,
        }

    runtime_info = detect_runtime_layout(runtime_root)
    mod_root = runtime_info["freecad_mod"] or os.path.join(runtime_root, "Mod")
    os.makedirs(mod_root, exist_ok=True)
    sheetmetal_dest = os.path.join(mod_root, "SheetMetal")

    try:
        if os.path.isdir(sheetmetal_dest):
            if update_sheetmetal:
                _run_command([git_executable, "-C", sheetmetal_dest, "pull", "--ff-only"])
        else:
            _run_command([git_executable, "clone", "--depth", "1", sheetmetal_repo, sheetmetal_dest])
    except Exception as exc:
        return {
            "success": False,
            "installed": False,
            "error": f"SheetMetal broncode installatie gefaald: {exc}",
        }

    verify_result = _verify_runtime(runtime_info)
    if not verify_result.get("success"):
        return {
            "success": False,
            "installed": True,
            "error": verify_result.get("error") or "Runtime verificatie gefaald",
        }

    metadata = {
        **runtime_info,
        "platform": sys.platform,
        "sheetmetal_repo": sheetmetal_repo,
        "manager": os.path.basename(manager),
    }
    save_runtime_metadata(metadata)
    return {
        "success": True,
        "installed": True,
        "runtime": metadata,
    }
