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


def auto_install_enabled() -> bool:
    value = os.environ.get("FREECAD_AUTO_INSTALL", "1").strip().lower()
    return value not in {"0", "false", "no", "off"}


def auto_bootstrap_package_manager_enabled() -> bool:
    value = os.environ.get("FREECAD_BOOTSTRAP_PACKAGE_MANAGER", "0").strip().lower()
    return value in {"1", "true", "yes", "on"}


def choose_package_manager() -> str:
    env_value = os.environ.get("FREECAD_PACKAGE_MANAGER")
    if env_value:
        return env_value
    for candidate in ("micromamba", "conda"):
        path = shutil.which(candidate)
        if path:
            return path
    # Check known install locations not yet on PATH
    if sys.platform.startswith("win"):
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        if local_app_data:
            candidate = os.path.join(local_app_data, "micromamba", "micromamba.exe")
            if os.path.exists(candidate):
                return candidate
    return ""


def _run_command(command: List[str], capture_output: bool = False, text: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=True, capture_output=capture_output, text=text)


def diagnose_package_manager() -> Dict[str, Any]:
    discovered = []
    for candidate in ("micromamba", "conda"):
        discovered.append({
            "name": candidate,
            "path": shutil.which(candidate) or "",
        })
    chosen = choose_package_manager()
    return {
        "chosen": chosen,
        "discovered": discovered,
        "auto_bootstrap_enabled": auto_bootstrap_package_manager_enabled(),
    }


def _package_manager_bootstrap_command() -> List[str]:
    if sys.platform.startswith("win"):
        return [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-NoProfile",
            "-Command",
            "iwr -useb https://micro.mamba.pm/install.ps1 | iex",
        ]
    return [
        "bash",
        "-lc",
        "curl -Ls https://micro.mamba.pm/install.sh | bash",
    ]


def bootstrap_package_manager() -> Dict[str, Any]:
    if not auto_bootstrap_package_manager_enabled():
        return {
            "success": False,
            "error": "Geen package manager gevonden. Zet FREECAD_BOOTSTRAP_PACKAGE_MANAGER=1 om micromamba automatisch te bootstrapen.",
            "command": _package_manager_bootstrap_command(),
        }

    command = _package_manager_bootstrap_command()
    try:
        _run_command(command)
    except Exception as exc:
        return {
            "success": False,
            "error": f"Bootstrap van micromamba gefaald: {exc}",
            "command": command,
        }

    chosen = choose_package_manager()
    if not chosen:
        return {
            "success": False,
            "error": "Bootstrap voltooid zonder bruikbare package manager in PATH.",
            "command": command,
        }

    return {
        "success": True,
        "package_manager": chosen,
        "command": command,
    }


def _sheetmetal_destination(runtime_info: Dict[str, Any]) -> str:
    mod_root = str(runtime_info.get("freecad_mod") or "")
    if not mod_root:
        mod_root = os.path.join(str(runtime_info.get("runtime_root") or ""), "Mod")
    return os.path.join(mod_root, "SheetMetal")


def _install_sheetmetal_source(
    runtime_info: Dict[str, Any],
    sheetmetal_repo: str,
    update_sheetmetal: bool,
) -> Dict[str, Any]:
    git_executable = shutil.which("git")
    if not git_executable:
        return {
            "success": False,
            "error": "Git niet gevonden. Installeer git om de SheetMetal broncode op te halen.",
        }

    mod_root = str(runtime_info.get("freecad_mod") or "")
    if not mod_root:
        mod_root = os.path.join(str(runtime_info.get("runtime_root") or ""), "Mod")
        runtime_info["freecad_mod"] = mod_root
    os.makedirs(mod_root, exist_ok=True)
    sheetmetal_dest = _sheetmetal_destination(runtime_info)

    try:
        if os.path.isdir(sheetmetal_dest):
            if update_sheetmetal:
                _run_command([git_executable, "-C", sheetmetal_dest, "pull", "--ff-only"])
        else:
            _run_command([git_executable, "clone", "--depth", "1", sheetmetal_repo, sheetmetal_dest])
    except Exception as exc:
        return {
            "success": False,
            "error": f"SheetMetal broncode installatie gefaald: {exc}",
        }

    return {
        "success": True,
        "sheetmetal_dest": sheetmetal_dest,
    }


def _persist_runtime(runtime_info: Dict[str, Any], sheetmetal_repo: str, manager: str) -> Dict[str, Any]:
    metadata = {
        **runtime_info,
        "platform": sys.platform,
        "sheetmetal_repo": sheetmetal_repo,
        "manager": manager,
    }
    save_runtime_metadata(metadata)
    return metadata


def _verify_runtime(runtime_info: Dict[str, Any]) -> Dict[str, Any]:
    freecad_cmd = str(runtime_info.get("freecad_cmd") or "")
    freecad_python = str(runtime_info.get("freecad_python") or "")
    freecad_lib = str(runtime_info.get("freecad_lib") or "")
    freecad_mod = str(runtime_info.get("freecad_mod") or "")

    # On Windows conda, FreeCAD.pyd lives in Library/bin which is not on sys.path
    freecad_lib_bin = os.path.join(str(runtime_info.get("runtime_root") or ""), "Library", "bin")

    script = (
        "import json, os, sys\n"
        "\n"
        "# Mock FreeCADGui BEFORE adding Library/bin to sys.path\n"
        "# so the real FreeCADGui.pyd (which needs Qt/GUI) is never loaded\n"
        "class _MockObj:\n"
        "    Refine = True\n"
        "class _MockSel:\n"
        "    _s = [_MockObj()]\n"
        "    @staticmethod\n"
        "    def getSelection():\n"
        "        return _MockSel._s\n"
        "    @staticmethod\n"
        "    def addSelection(*a):\n"
        "        pass\n"
        "class _MockGui:\n"
        "    Selection = _MockSel()\n"
        "sys.modules['FreeCADGui'] = _MockGui()\n"
        "\n"
        f"lib_bin = {json.dumps(freecad_lib_bin)}\n"
        "if lib_bin and os.path.isdir(lib_bin) and lib_bin not in sys.path:\n"
        "    sys.path.insert(0, lib_bin)\n"
        f"mod_path = {json.dumps(freecad_mod)}\n"
        "if mod_path and os.path.isdir(mod_path) and mod_path not in sys.path:\n"
        "    sys.path.insert(0, mod_path)\n"
        "\n"
        "import FreeCAD\n"
        "import Part\n"
        "import SheetMetalUnfolder\n"
        "print(json.dumps({'success': True}))\n"
    )

    # Build PATH so conda-managed FreeCAD can find its DLLs
    extra_path_parts = []
    runtime_root = str(runtime_info.get("runtime_root") or "")
    for candidate in (
        os.path.join(runtime_root, "Library", "bin"),
        os.path.join(runtime_root, "Library", "mingw-w64", "bin"),
        os.path.join(runtime_root, "bin"),
        freecad_lib,
    ):
        if candidate and os.path.isdir(candidate) and candidate not in extra_path_parts:
            extra_path_parts.append(candidate)

    env = os.environ.copy()
    if extra_path_parts:
        path_sep = ";" if sys.platform.startswith("win") else ":"
        existing = env.get("PATH", "")
        env["PATH"] = path_sep.join(extra_path_parts) + path_sep + existing

    # Prefer python.exe over FreeCADCmd.exe — it resolves DLLs correctly
    # within conda environments where FreeCADCmd may fail due to PATH issues.
    executables_to_try: List[str] = []
    if freecad_python and os.path.exists(freecad_python):
        executables_to_try.append(freecad_python)
    if freecad_cmd and os.path.exists(freecad_cmd):
        executables_to_try.append(freecad_cmd)
    if not executables_to_try:
        return {
            "success": False,
            "error": "FreeCAD executable niet gevonden (python of FreeCADCmd)",
            "stage": "resolve_freecadcmd",
        }

    tmp_file = None
    last_error = ""
    for executable in executables_to_try:
        try:
            with tempfile.NamedTemporaryFile("w", suffix="_verify_freecad.py", delete=False, encoding="utf-8") as handle:
                handle.write(script)
                tmp_file = handle.name
            proc = subprocess.run(
                [executable, tmp_file],
                capture_output=True,
                text=True,
                check=False,
                timeout=120,
                env=env,
            )
        except Exception as exc:
            last_error = f"Runtime verificatie gefaald ({os.path.basename(executable)}): {exc}"
            continue
        finally:
            if tmp_file and os.path.exists(tmp_file):
                try:
                    os.remove(tmp_file)
                except OSError:
                    pass
                tmp_file = None

        for line in reversed((proc.stdout or "").splitlines()):
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                payload = json.loads(line)
            except Exception:
                continue
            if payload.get("success"):
                return {"success": True, "stage": "verified"}

        last_error = (proc.stderr or proc.stdout or "Runtime verificatie gaf geen geldig resultaat").strip()

    return {
        "success": False,
        "error": last_error,
        "stage": "verify_imports",
        "stdout": "",
        "stderr": last_error[:2000],
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
    actions: List[str] = []

    if os.path.exists(runtime_info["freecad_cmd"]):
        actions.append("found_existing_runtime")
        verify_result = _verify_runtime(runtime_info)
        if verify_result.get("success"):
            metadata = _persist_runtime(runtime_info, sheetmetal_repo, "existing")
            return {
                "success": True,
                "installed": False,
                "runtime": metadata,
                "actions": actions + ["verified_existing_runtime"],
            }

        repair_result = _install_sheetmetal_source(
            runtime_info,
            sheetmetal_repo=sheetmetal_repo,
            update_sheetmetal=True,
        )
        if repair_result.get("success"):
            actions.append("repaired_sheetmetal_source")
            verify_result = _verify_runtime(runtime_info)
            if verify_result.get("success"):
                metadata = _persist_runtime(runtime_info, sheetmetal_repo, "existing")
                return {
                    "success": True,
                    "installed": False,
                    "runtime": metadata,
                    "actions": actions + ["verified_existing_runtime"],
                }
        if not install_if_missing:
            return {
                "success": False,
                "installed": False,
                "error": (
                    repair_result.get("error")
                    or verify_result.get("error")
                    or "Bestaande runtime verificatie gefaald"
                ),
                "actions": actions,
                "verify": verify_result,
            }

    if not install_if_missing:
        return {
            "success": False,
            "installed": False,
            "error": "Geen beheerde FreeCAD runtime gevonden",
            "actions": actions,
        }

    manager = package_manager or choose_package_manager()
    if not manager:
        bootstrap_result = bootstrap_package_manager()
        if bootstrap_result.get("success"):
            manager = str(bootstrap_result["package_manager"])
            actions.append("bootstrapped_package_manager")
        else:
            return {
                "success": False,
                "installed": False,
                "error": bootstrap_result.get("error") or "Geen package manager gevonden.",
                "actions": actions,
                "bootstrap": bootstrap_result,
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
        actions.append("created_runtime")
    except Exception as exc:
        return {
            "success": False,
            "installed": False,
            "error": f"Runtime installatie gefaald: {exc}",
            "command": create_cmd,
            "actions": actions,
        }

    runtime_info = detect_runtime_layout(runtime_root)
    sheetmetal_result = _install_sheetmetal_source(
        runtime_info,
        sheetmetal_repo=sheetmetal_repo,
        update_sheetmetal=update_sheetmetal,
    )
    if not sheetmetal_result.get("success"):
        return {
            "success": False,
            "installed": False,
            "error": sheetmetal_result.get("error") or "SheetMetal broncode installatie gefaald",
            "actions": actions,
        }
    actions.append("installed_sheetmetal_source")

    verify_result = _verify_runtime(runtime_info)
    if not verify_result.get("success"):
        return {
            "success": False,
            "installed": True,
            "error": verify_result.get("error") or "Runtime verificatie gefaald",
            "actions": actions,
            "verify": verify_result,
        }

    metadata = _persist_runtime(runtime_info, sheetmetal_repo, os.path.basename(manager))
    return {
        "success": True,
        "installed": True,
        "runtime": metadata,
        "actions": actions + ["verified_new_runtime"],
    }


def doctor_runtime(
    runtime_root: Optional[str] = None,
    sheetmetal_repo: str = DEFAULT_SHEETMETAL_REPO,
) -> Dict[str, Any]:
    runtime_root = runtime_root or managed_runtime_root()
    runtime_info = detect_runtime_layout(runtime_root)
    configured = configured_runtime()
    verify = _verify_runtime(runtime_info) if os.path.exists(runtime_info.get("freecad_cmd") or "") else {
        "success": False,
        "stage": "resolve_freecadcmd",
        "error": "FreeCADCmd niet gevonden",
    }

    return {
        "platform": sys.platform,
        "runtime_root": runtime_root,
        "auto_install_enabled": auto_install_enabled(),
        "auto_bootstrap_package_manager_enabled": auto_bootstrap_package_manager_enabled(),
        "package_manager": diagnose_package_manager(),
        "configured_runtime": configured,
        "detected_runtime": {
            **runtime_info,
            "sheetmetal_dest": _sheetmetal_destination(runtime_info),
            "sheetmetal_repo": sheetmetal_repo,
        },
        "verify": verify,
        "bootstrap_command": _package_manager_bootstrap_command(),
    }
