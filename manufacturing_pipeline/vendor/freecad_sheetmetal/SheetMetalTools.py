"""Minimal SheetMetalTools compatibility layer for direct unfold imports.

This intentionally implements only the tiny subset used by the vendored
``SheetMetalUnfolder.py``. The full upstream workbench contains substantial
GUI/export functionality that is not required for the pipeline's direct
unfold path.
"""

from __future__ import annotations

import math

import FreeCAD


def isGuiLoaded() -> bool:
    return bool(getattr(FreeCAD, "GuiUp", False))


def smIsEqualAngle(angle_a: float, angle_b: float, precision: int = 5) -> bool:
    try:
        return round(float(angle_a) - float(angle_b), precision) == 0
    except Exception:
        return False


class _Logger:
    @staticmethod
    def _print(method_name: str, message: str) -> None:
        console = getattr(FreeCAD, "Console", None)
        if console is None:
            return
        method = getattr(console, method_name, None)
        if method is None:
            return
        if not message.endswith("\n"):
            message += "\n"
        method(message)

    @classmethod
    def warning(cls, message: str) -> None:
        cls._print("PrintWarning", message)

    @classmethod
    def error(cls, message: str) -> None:
        cls._print("PrintError", message)

    @classmethod
    def log(cls, message: str) -> None:
        cls._print("PrintLog", message)


SMLogger = _Logger()

