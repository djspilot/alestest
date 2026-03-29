from __future__ import annotations

import os
import sys

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


def _should_prefer_freecadcmd() -> bool:
    mode = os.getenv("FREECAD_UNFOLD_MODE", "auto").strip().lower()
    if mode == "subprocess":
        return True
    if mode == "direct":
        return False
    return sys.platform.startswith("win")


def _ensure_freecad_imported() -> bool:
    global FreeCAD, Part, _FREECAD_IMPORT_ERROR

    if FreeCAD is not None and Part is not None:
        return True

    for path in _candidate_freecad_paths():
        if path and os.path.isdir(path) and path not in sys.path:
            sys.path.insert(0, path)

    try:
        import FreeCAD as _FreeCAD
        import Part as _Part

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
        return False


def _find_freecadcmd_executable() -> str:
    env_path = os.getenv("FREECAD_CMD")
    if env_path and os.path.exists(env_path):
        return env_path

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

    return ""
