"""
Profiler for timing manufacturing pipeline analysis steps.

Usage:
    profiler = AnalysisProfiler("mypart.step", 6.1)
    with profiler.step("Load STEP", 1, 7):
        shape = load_step(path)
    with profiler.step("Detect holes", 2, 7):
        with profiler.sub_step("Cylindrical"):
            cyl_holes = detect_cylindrical(shape)
        profiler.set_sub_count("Cylindrical", len(cyl_holes))
        with profiler.sub_step("Shaped", count=len(shaped)):
            shaped = detect_shaped(shape)
    profiler.count("faces", 1234)
    profiler.count("holes", 57)
    profiler.print_summary()
    profiler.save_json("output/")
"""

import json
import os
import time
from contextlib import contextmanager
from datetime import datetime, timezone


class AnalysisProfiler:
    """Times manufacturing pipeline analysis steps and produces summary reports."""

    def __init__(self, part_name: str, file_size_mb: float, event_callback=None):
        self.part_name = part_name
        self.file_size_mb = file_size_mb
        self.event_callback = event_callback
        self.steps: list[dict] = []
        self.counts: dict[str, int] = {}
        self._current_step: dict | None = None
        self._first_start: float | None = None
        self._first_start_at_iso: str | None = None
        self._last_end: float | None = None
        self._events: list[dict] = []

    def _utc_now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _current_elapsed(self, now: float | None = None) -> float:
        if self._first_start is None:
            return 0.0
        current = now if now is not None else (self._last_end if self._last_end is not None else time.perf_counter())
        return max(current - self._first_start, 0.0)

    def _build_live_summary(self, now: float | None = None) -> dict:
        current_step = self._current_step
        active_stage = None
        active_stage_started_at = None
        active_stage_elapsed_seconds = None
        if current_step is not None and not current_step.get("_finished"):
            active_stage = current_step.get("name")
            active_stage_started_at = current_step.get("_started_at_iso")
            active_stage_elapsed_seconds = round(
                max((now if now is not None else time.perf_counter()) - current_step.get("_start_perf", 0.0), 0.0),
                4,
            )

        total_steps_hint = max(
            (step.get("total") or 0 for step in self.steps),
            default=len(self.steps),
        ) or len(self.steps)

        return {
            "total_elapsed_seconds": round(self._current_elapsed(now), 4),
            "event_count": len(self._events),
            "step_count": len(self.steps),
            "part_name": self.part_name,
            "analysis_started_at": self._first_start_at_iso,
            "active_stage": active_stage,
            "active_stage_started_at": active_stage_started_at,
            "active_stage_elapsed_seconds": active_stage_elapsed_seconds,
            "completed_step_count": sum(1 for step in self.steps if step.get("_finished")),
            "total_steps_hint": total_steps_hint,
        }

    def _emit_event(self, event: dict, now: float | None = None):
        self._events.append(event)
        if self.event_callback:
            self.event_callback(event, self._build_live_summary(now))

    def emit(self, event_type: str, stage: str, payload: dict | None = None, status: str = "OK"):
        now = time.perf_counter()
        self._emit_event(
            {
                "type": event_type,
                "stage": stage,
                "timestamp_ms": int(round(self._current_elapsed(now) * 1000)),
                "status": status,
                "payload": payload or {},
            },
            now,
        )

    @contextmanager
    def step(self, name: str, step_num: int = None, total_steps: int = None):
        """Context manager that times a top-level analysis step."""
        entry = {
            "name": name,
            "num": step_num,
            "total": total_steps,
            "elapsed": 0.0,
            "status": "OK",
            "sub_steps": [],
            "error": None,
            "_start_perf": 0.0,
            "_started_at_iso": None,
            "_finished": False,
        }
        self.steps.append(entry)
        prev_step = self._current_step
        self._current_step = entry

        start = time.perf_counter()
        started_at_iso = self._utc_now_iso()
        entry["_start_perf"] = start
        entry["_started_at_iso"] = started_at_iso
        if self._first_start is None:
            self._first_start = start
            self._first_start_at_iso = started_at_iso

        self._emit_event(
            {
                "type": "stage_start",
                "stage": name,
                "timestamp_ms": int(round(self._current_elapsed(start) * 1000)),
                "status": "START",
                "payload": {
                    "num": step_num,
                    "total": total_steps,
                },
            },
            start,
        )

        try:
            yield entry
        except Exception as exc:
            end = time.perf_counter()
            entry["status"] = "FAIL"
            entry["error"] = str(exc)
            entry["elapsed"] = end - start
            entry["_finished"] = True
            self._last_end = end
            self._emit_event(
                {
                    "type": "stage_failed",
                    "stage": name,
                    "timestamp_ms": int(round(self._current_elapsed(end) * 1000)),
                    "status": "FAIL",
                    "payload": {
                        "elapsed_seconds": round(entry["elapsed"], 4),
                        "error": entry["error"],
                    },
                },
                end,
            )
            raise
        else:
            end = time.perf_counter()
            entry["elapsed"] = end - start
            entry["_finished"] = True
            self._last_end = end
            status = (entry.get("status") or "OK").upper()
            event_type = "stage_skipped" if status == "SKIP" else "stage_end"
            self._emit_event(
                {
                    "type": event_type,
                    "stage": name,
                    "timestamp_ms": int(round(self._current_elapsed(end) * 1000)),
                    "status": status,
                    "payload": {
                        "elapsed_seconds": round(entry["elapsed"], 4),
                        "error": entry["error"],
                    },
                },
                end,
            )
        finally:
            self._current_step = prev_step

    @contextmanager
    def sub_step(self, name: str, count: int = None):
        """Context manager for a sub-step within the current step."""
        sub = {
            "name": name,
            "elapsed": 0.0,
            "count": count,
        }
        if self._current_step is not None:
            self._current_step["sub_steps"].append(sub)

        start = time.perf_counter()
        try:
            yield sub
        finally:
            sub["elapsed"] = time.perf_counter() - start

    def set_sub_count(self, name: str, count: int):
        """Set the count for a sub-step by name (most recent match in current step)."""
        if self._current_step is None:
            return
        for sub in reversed(self._current_step["sub_steps"]):
            if sub["name"] == name:
                sub["count"] = count
                return

    def count(self, key: str, value: int):
        """Record a count (faces, solids, holes, etc.)."""
        self.counts[key] = value

    @staticmethod
    def _fmt_time(seconds: float) -> str:
        """Format elapsed time for display."""
        if seconds < 60:
            return f"{seconds:.2f}s"
        minutes = int(seconds // 60)
        secs = seconds - minutes * 60
        return f"{minutes}m {secs:02.0f}s"

    def print_summary(self):
        """Print a box-drawing summary table of all timed steps."""
        W = 60  # inner width

        def line(left, fill, right):
            return f"{left}{fill * W}{right}"

        def pad(text):
            return f"║ {text}{' ' * (W - 2 - len(text))}║"

        header = f"{self.part_name} ({self.file_size_mb:.1f} MB)"

        rows = []
        rows.append(line("╔", "═", "╗"))
        rows.append(pad(header))
        rows.append(line("╠", "═", "╣"))

        for step in self.steps:
            num = step["num"]
            total = step["total"]
            if num is not None and total is not None:
                prefix = f"[{num}/{total}]"
            elif num is not None:
                prefix = f"[{num}]"
            else:
                prefix = "   "

            t = self._fmt_time(step["elapsed"])
            label = f"{prefix} {step['name']}"
            status = step["status"]
            content = f"{label:<30} {t:>7}   {status}"
            rows.append(pad(content))

            subs = step["sub_steps"]
            for i, sub in enumerate(subs):
                is_last = i == len(subs) - 1
                branch = "└─" if is_last else "├─"
                st = self._fmt_time(sub["elapsed"])
                count_str = f"  ({sub['count']:,} found)" if sub["count"] is not None else ""
                sub_content = f"      {branch} {sub['name']:<22} {st:>7}{count_str}"
                rows.append(pad(sub_content))

        # Total
        if self._first_start is not None and self._last_end is not None:
            total_elapsed = self._last_end - self._first_start
        else:
            total_elapsed = sum(s["elapsed"] for s in self.steps)

        rows.append(line("╠", "═", "╣"))
        total_line = f"{'TOTAL':<30} {self._fmt_time(total_elapsed):>7}"
        rows.append(pad(total_line))

        if self.counts:
            parts = []
            for key, val in self.counts.items():
                parts.append(f"{key.capitalize()}: {val:,}")
            counts_line = "  ".join(parts)
            rows.append(pad(counts_line))

        rows.append(line("╚", "═", "╝"))

        print("\n".join(rows))

    def save_json(self, output_dir: str):
        """Save timing data as JSON to output_dir/{part_name}_timing.json."""
        if self._first_start is not None and self._last_end is not None:
            total_elapsed = self._last_end - self._first_start
        else:
            total_elapsed = sum(s["elapsed"] for s in self.steps)

        # Strip extension from part_name for the filename
        base = os.path.splitext(self.part_name)[0]

        data = {
            "part_name": self.part_name,
            "file_size_mb": self.file_size_mb,
            "total_elapsed": round(total_elapsed, 4),
            "counts": self.counts,
            "steps": [
                {
                    "name": s["name"],
                    "num": s["num"],
                    "total": s["total"],
                    "elapsed": round(s["elapsed"], 4),
                    "status": s["status"],
                    "error": s["error"],
                    "sub_steps": [
                        {
                            "name": sub["name"],
                            "elapsed": round(sub["elapsed"], 4),
                            "count": sub["count"],
                        }
                        for sub in s["sub_steps"]
                    ],
                }
                for s in self.steps
            ],
        }

        os.makedirs(output_dir, exist_ok=True)
        path = os.path.join(output_dir, f"{base}_timing.json")
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        return path
