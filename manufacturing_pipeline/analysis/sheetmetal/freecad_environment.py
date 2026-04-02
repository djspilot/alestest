from __future__ import annotations

import os
import sys

from manufacturing_pipeline.core import freecad_runtime
from manufacturing_pipeline.core.freecad_vendor import ensure_vendor_sheetmetal_on_sys_path

FreeCAD = None
Part = None
_FREECAD_IMPORT_ERROR = None


class MockFreeCADGui:
    class Selection:
        @staticmethod
        def getSelection():
            return []


def _candidate_freecad_paths():
    candidates = []

    runtime_info = freecad_runtime.configured_runtime()
    candidates.extend(
        [
            str(runtime_info.get("freecad_path") or ""),
            str(runtime_info.get("freecad_lib") or ""),
            str(runtime_info.get("freecad_mod") or ""),
            str(runtime_info.get("runtime_root") or ""),
        ]
    )

    freecad_path = os.getenv("FREECAD_PATH")
    if freecad_path:
        candidates.append(freecad_path)
        candidates.append(os.path.join(freecad_path, "bin"))
        candidates.append(os.path.join(freecad_path, "lib"))
        candidates.append(os.path.join(freecad_path, "Mod"))

    program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
    program_files_x86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    for base in [program_files, program_files_x86]:
        if base:
            candidates.extend(
                [
                    os.path.join(base, "FreeCAD 1.0", "bin"),
                    os.path.join(base, "FreeCAD 1.0", "Mod"),
                    os.path.join(base, "FreeCAD", "bin"),
                    os.path.join(base, "FreeCAD", "Mod"),
                    os.path.join(base, "FreeCAD 0.21", "bin"),
                    os.path.join(base, "FreeCAD 0.21", "Mod"),
                ]
            )

    appdata = os.environ.get("APPDATA")
    if appdata:
        candidates.append(os.path.join(appdata, "FreeCAD", "Mod"))

    mac_app = "/Applications/FreeCAD.app/Contents/Resources"
    brew_app = "/opt/homebrew/Caskroom/freecad/1.0.2/FreeCAD.app/Contents/Resources"
    for path in [mac_app, brew_app]:
        candidates.extend([os.path.join(path, "lib"), os.path.join(path, "Mod")])
    candidates.append(os.path.expanduser("~/Library/Application Support/FreeCAD/Mod"))

    candidates.extend(
        [
            "/usr/lib/freecad/lib",
            "/usr/share/freecad/Mod",
            "/usr/lib/freecad/Mod",
            "/snap/freecad/current/usr/lib/freecad/lib",
            "/snap/freecad/current/usr/share/freecad/Mod",
            os.path.expanduser("~/.local/share/FreeCAD/Mod"),
        ]
    )

    return candidates


def _ensure_managed_runtime_available() -> bool:
    if not freecad_runtime.auto_install_enabled():
        return False
    result = freecad_runtime.ensure_managed_runtime(install_if_missing=True)
    return bool(result.get("success"))


def _should_prefer_freecadcmd() -> bool:
    mode = os.getenv("FREECAD_UNFOLD_MODE", "auto").strip().lower()
    if mode == "subprocess":
        return True
    if mode == "direct":
        return False
    return False


def _ensure_freecad_imported() -> bool:
    global FreeCAD, Part, _FREECAD_IMPORT_ERROR

    if FreeCAD is not None and Part is not None:
        return True

    ensure_vendor_sheetmetal_on_sys_path()
    for path in _candidate_freecad_paths():
        if path and os.path.isdir(path) and path not in sys.path:
            sys.path.insert(0, path)
    for mod_name in ("SheetMetalLogger", "SheetMetalUnfolder", "SheetMetalTools", "lookup"):
        sys.modules.pop(mod_name, None)

    try:
        import FreeCAD as _FreeCAD
        import Part as _Part
        import SheetMetalUnfolder  # noqa: F401

        FreeCAD = _FreeCAD
        Part = _Part

        try:
            import FreeCADGui as _FreeCADGui

            _FreeCADGui.Selection.getSelection()
        except (ImportError, AttributeError):
            sys.modules["FreeCADGui"] = MockFreeCADGui()

        return True
    except Exception as exc:
        _FREECAD_IMPORT_ERROR = str(exc)
        if _ensure_managed_runtime_available():
            ensure_vendor_sheetmetal_on_sys_path()
            for path in _candidate_freecad_paths():
                if path and os.path.isdir(path) and path not in sys.path:
                    sys.path.insert(0, path)
            for mod_name in ("SheetMetalLogger", "SheetMetalUnfolder", "SheetMetalTools", "lookup"):
                sys.modules.pop(mod_name, None)
            try:
                import FreeCAD as _FreeCAD
                import Part as _Part
                import SheetMetalUnfolder  # noqa: F401

                FreeCAD = _FreeCAD
                Part = _Part

                try:
                    import FreeCADGui as _FreeCADGui

                    _FreeCADGui.Selection.getSelection()
                except (ImportError, AttributeError):
                    sys.modules["FreeCADGui"] = MockFreeCADGui()

                _FREECAD_IMPORT_ERROR = None
                return True
            except Exception as retry_exc:
                _FREECAD_IMPORT_ERROR = str(retry_exc)
        return False


def _find_freecadcmd_executable() -> str:
    env_path = os.getenv("FREECAD_CMD")
    if env_path and os.path.exists(env_path):
        return env_path

    runtime_info = freecad_runtime.configured_runtime()
    managed_cmd = str(runtime_info.get("freecad_cmd") or "")
    if managed_cmd and os.path.exists(managed_cmd):
        return managed_cmd

    candidates = [
        r"C:\Program Files\FreeCAD 1.0\bin\freecadcmd.exe",
        r"C:\Program Files\FreeCAD\bin\freecadcmd.exe",
        r"C:\Program Files\FreeCAD 0.21\bin\freecadcmd.exe",
        r"C:\Program Files (x86)\FreeCAD\bin\freecadcmd.exe",
        "/usr/bin/freecadcmd",
        "/usr/local/bin/freecadcmd",
        "/Applications/FreeCAD.app/Contents/MacOS/FreeCADCmd",
    ]
    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate

    if _ensure_managed_runtime_available():
        runtime_info = freecad_runtime.configured_runtime()
        managed_cmd = str(runtime_info.get("freecad_cmd") or "")
        if managed_cmd and os.path.exists(managed_cmd):
            return managed_cmd

    return ""
