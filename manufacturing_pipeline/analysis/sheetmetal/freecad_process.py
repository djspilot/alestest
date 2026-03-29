from __future__ import annotations

import json
import os
import subprocess
import tempfile
from typing import Any, Dict


def run_freecadcmd_script(freecadcmd: str, script: str, timeout_seconds: int = 300) -> Dict[str, Any]:
    tmp_file = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", suffix="_freecad_unfold.py", delete=False, encoding="utf-8"
        ) as handle:
            handle.write(script)
            tmp_file = handle.name

        proc = subprocess.run(
            [freecadcmd, tmp_file],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )

        output_lines = [line.strip() for line in (proc.stdout or "").splitlines() if line.strip()]
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

        stderr = (proc.stderr or "").strip()
        return {
            "success": False,
            "error": f"FreeCADCmd uitvoer niet parsebaar (code {proc.returncode}): {stderr[:300]}",
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
