from __future__ import annotations

import traceback


class UnfoldException(Exception):
    pass


class BendException(Exception):
    pass


class TreeException(Exception):
    pass


class SMLogger:
    @staticmethod
    def _emit(level: str, *parts) -> None:  # type: ignore[no-untyped-def]
        try:
            message = " ".join(str(part) for part in parts)
        except Exception:
            message = " ".join(repr(part) for part in parts)
        print(f"[SheetMetal:{level}] {message}")

    @staticmethod
    def error(*parts) -> None:  # type: ignore[no-untyped-def]
        SMLogger._emit("error", *parts)

    @staticmethod
    def warning(*parts) -> None:  # type: ignore[no-untyped-def]
        SMLogger._emit("warning", *parts)

    @staticmethod
    def log(*parts) -> None:  # type: ignore[no-untyped-def]
        SMLogger._emit("log", *parts)

    @staticmethod
    def debug(*parts) -> None:  # type: ignore[no-untyped-def]
        SMLogger._emit("debug", *parts)

    @staticmethod
    def exception(*parts) -> None:  # type: ignore[no-untyped-def]
        SMLogger._emit("exception", *parts)
        tb = traceback.format_exc().strip()
        if tb and tb != "NoneType: None":
            print(tb)
