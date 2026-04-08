from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import tempfile
from typing import Any, Dict


def _kill_process_tree(proc, grace_seconds=5):
    """Kill a subprocess and its children reliably."""
    if proc.poll() is not None:
        return
    if os.name == "posix":
        try:
            pgid = os.getpgid(proc.pid)
            os.killpg(pgid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            proc.terminate()
        try:
            proc.wait(timeout=grace_seconds)
            return
        except subprocess.TimeoutExpired:
            pass
        try:
            pgid = os.getpgid(proc.pid)
            os.killpg(pgid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            proc.kill()
        try:
            proc.wait(timeout=grace_seconds)
        except subprocess.TimeoutExpired:
            pass
    else:
        proc.terminate()
        try:
            proc.wait(timeout=grace_seconds)
        except subprocess.TimeoutExpired:
            proc.kill()
            try:
                proc.wait(timeout=grace_seconds)
            except subprocess.TimeoutExpired:
                pass


def run_freecadcmd_script(freecadcmd: str, script: str, timeout_seconds: int = 300) -> Dict[str, Any]:
    tmp_file = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", suffix="_freecad_unfold.py", delete=False, encoding="utf-8"
        ) as handle:
            handle.write(script)
            tmp_file = handle.name

        popen_kwargs: Dict[str, Any] = {
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "text": True,
        }
        if os.name == "posix":
            popen_kwargs["start_new_session"] = True

        proc = subprocess.Popen([freecadcmd, tmp_file], **popen_kwargs)
        timed_out = False
        try:
            stdout, stderr = proc.communicate(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            _kill_process_tree(proc)
            stdout, stderr = proc.communicate()
            timed_out = True

        if timed_out:
            return {
                "success": False,
                "error": f"Timeout (>{timeout_seconds}s)",
                "timeout": True,
                "timeout_seconds": timeout_seconds,
                "attempts": 0,
                "error_details": [],
            }

        output_lines = [line.strip() for line in (stdout or "").splitlines() if line.strip()]
        for line in output_lines:
            if not (line.startswith("{") and line.endswith("}")) and "[DEBUG]" in line:
                print(line)

        for line in reversed(output_lines):
            if line.startswith("{") and line.endswith("}"):
                try:
                    data = json.loads(line)
                    data.setdefault("error_details", [])
                    data.setdefault("attempts", 0)
                    return data
                except Exception:
                    continue

        stderr_str = (stderr or "").strip()
        return {
            "success": False,
            "error": f"FreeCADCmd uitvoer niet parsebaar (code {proc.returncode}): {stderr_str[:300]}",
            "attempts": 0,
            "error_details": [],
        }
    except Exception as exc:
        return {
            "success": False,
            "error": f"FreeCADCmd fallback error: {exc}",
            "attempts": 0,
            "error_details": [],
        }
    finally:
        if tmp_file and os.path.exists(tmp_file):
            try:
                os.remove(tmp_file)
            except Exception:
                pass
