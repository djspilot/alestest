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


class AnalysisProfiler:
    """Times manufacturing pipeline analysis steps and produces summary reports."""

    def __init__(self, part_name: str, file_size_mb: float):
        self.part_name = part_name
        self.file_size_mb = file_size_mb
        self.steps: list[dict] = []
        self.counts: dict[str, int] = {}
        self._current_step: dict | None = None
        self._first_start: float | None = None
        self._last_end: float | None = None

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
        }
        self.steps.append(entry)
        prev_step = self._current_step
        self._current_step = entry

        start = time.perf_counter()
        if self._first_start is None:
            self._first_start = start

        try:
            yield entry
        except Exception as exc:
            entry["status"] = "FAIL"
            entry["error"] = str(exc)
            entry["elapsed"] = time.perf_counter() - start
            self._last_end = time.perf_counter()
            self._current_step = prev_step
            raise
        else:
            entry["elapsed"] = time.perf_counter() - start
            self._last_end = time.perf_counter()
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
