from __future__ import annotations

import contextlib
import json
import os
import sys
import traceback
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
PIPELINE_ROOT = str(REPO_ROOT)
VENDOR_ROOT = str(REPO_ROOT / "manufacturing_pipeline" / "vendor" / "freecad_sheetmetal")


def _install_runtime_paths() -> None:
    for path in (
        os.environ.get("FREECAD_LIB", ""),
        os.environ.get("FREECAD_MOD", ""),
        os.path.expanduser("~/Library/Application Support/FreeCAD/Mod") if sys.platform == "darwin" else (os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "FreeCAD", "Mod") if sys.platform == "win32" else os.path.expanduser("~/.local/share/FreeCAD/Mod")),
        VENDOR_ROOT,
        PIPELINE_ROOT,
    ):
        if path and os.path.isdir(path) and path not in sys.path:
            sys.path.insert(0, path)


def _install_headless_gui_mock() -> None:
    class _MockObject:
        Refine = True

    class _MockSelection:
        _selection = [_MockObject()]

        @staticmethod
        def getSelection() -> list[Any]:
            return _MockSelection._selection

        @staticmethod
        def addSelection(*args: Any) -> None:
            return None

    class _MockGui:
        Selection = _MockSelection()

    sys.modules["FreeCADGui"] = _MockGui()


_install_runtime_paths()
_install_headless_gui_mock()

import FreeCAD  # type: ignore  # noqa: E402
import Part  # type: ignore  # noqa: E402

from manufacturing_pipeline.analysis import freecad_unfold  # noqa: E402

# Sync already-imported FreeCAD/Part into freecad_environment so that
# unfold_sheet_metal() skips the _ensure_freecad_imported() bootstrap and
# goes straight to the direct-import path. Without this, the environment
# module sees FreeCAD=None and tries _run_subprocess_fallback, returning 0 attempts.
_env = freecad_unfold._freecad_environment
_env.FreeCAD = FreeCAD
_env.Part = Part
freecad_unfold.FreeCAD = FreeCAD
freecad_unfold.Part = Part


def _serializable_error_details(error_details: Any) -> list[dict[str, Any]]:
    if not isinstance(error_details, list):
        return []
    normalized = []
    for item in error_details:
        if isinstance(item, dict):
            normalized.append(item)
    return normalized


def _run_new_unfolder(step_path: str, output_dir: str, part_name: str, k_factor: float) -> dict[str, Any]:
    import SheetMetalNewUnfolder  # type: ignore
    from SheetMetalNewUnfolder import BendAllowanceCalculator  # type: ignore
    import importDXF  # type: ignore

    shape = Part.Shape()
    shape.read(step_path)
    solid = shape.Solids[0] if getattr(shape, "Solids", None) else shape
    candidates = freecad_unfold.find_all_base_face_candidates(solid)
    if not candidates:
        return {
            "success": False,
            "error": "Geen vlakke oppervlakken gevonden",
            "attempts": 0,
            "error_details": [],
            "used_face_idx": None,
            "unfolder_variant": "new",
        }

    error_details = []
    bac = BendAllowanceCalculator.from_single_value(float(k_factor), "ansi")

    for attempt, candidate in enumerate(candidates[:10], start=1):
        face_idx = int(candidate["index"])
        doc = FreeCAD.newDocument("PersistentUnfoldDoc")
        try:
            obj = doc.addObject("Part::Feature", "SheetPart")
            obj.Shape = solid
            doc.recompute()

            selected_face, unfolded_shape, bend_lines_compound, root_normal, bend_infos = SheetMetalNewUnfolder.getUnfold(
                bac,
                obj,
                f"Face{face_idx + 1}",
            )
            if unfolded_shape is None:
                raise RuntimeError("New unfolder returned no unfolded shape")

            os.makedirs(output_dir, exist_ok=True)
            flat_step_path = os.path.join(output_dir, f"{part_name}_flat.step")
            dxf_path = os.path.join(output_dir, f"{part_name}_flat.dxf")
            unfolded_shape.exportStep(flat_step_path)
            importDXF.export([unfolded_shape], dxf_path)

            fold_edges = bend_lines_compound.Edges if bend_lines_compound else []
            bend_line_segments = freecad_unfold._extract_fold_line_segments_from_edges(fold_edges, unfolded_shape)

            bend_angles = []
            bend_radii = []
            bend_lengths = []
            for info in bend_infos or []:
                angle = round(float(getattr(info, "angle", 0.0)), 2)
                radius = round(float(getattr(info, "radius", 0.0)), 2)
                bend_angles.append(angle)
                bend_radii.append(radius)
                line = getattr(info, "line", None)
                if line is not None:
                    bend_lengths.append(round(float(getattr(line, "Length", 0.0)), 2))

            merged_angles, merged_radii, merged_lengths, bend_line_groups = freecad_unfold._merge_bends_by_collinear_segments(
                bend_angles,
                bend_radii,
                bend_lengths,
                bend_line_segments,
            )
            dims = freecad_unfold._measure_flat_pattern_dimensions(unfolded_shape)

            # Build fold_details and bends_logical from merged groups for viewer
            fold_details = []
            bends_logical = []
            for grp in bend_line_groups:
                gid = grp.get("id", len(fold_details) + 1)
                members = grp.get("segment_indices", [])
                axis = str(grp.get("axis", "X")).lower()
                # Compute merged span from segments
                span_min = None
                span_max = None
                center_x, center_y = 0.0, 0.0
                n_segs = 0
                for seg in bend_line_segments:
                    if seg.get("index") in members:
                        s_span = seg.get("axis_span")
                        if s_span and len(s_span) >= 2:
                            lo, hi = float(min(s_span[0], s_span[1])), float(max(s_span[0], s_span[1]))
                            if span_min is None or lo < span_min:
                                span_min = lo
                            if span_max is None or hi > span_max:
                                span_max = hi
                        c = seg.get("center")
                        if c and len(c) >= 2:
                            center_x += float(c[0])
                            center_y += float(c[1])
                            n_segs += 1
                if span_min is None:
                    span_min = 0.0
                if span_max is None:
                    span_max = 0.0
                if n_segs > 0:
                    center_x /= n_segs
                    center_y /= n_segs

                # Calculate merged line length
                if axis == "x":
                    start = (span_min, center_y, 0.0)
                    end = (span_max, center_y, 0.0)
                else:
                    start = (center_x, span_min, 0.0)
                    end = (center_x, span_max, 0.0)
                import math as _math
                line_length = _math.dist(start, end)
                center = ((start[0] + end[0]) / 2.0, (start[1] + end[1]) / 2.0, 0.0)

                fold_details.append({
                    "id": gid,
                    "length": round(line_length, 2),
                    "center": center,
                    "axis": axis,
                    "axis_span": (span_min, span_max),
                    "start": start,
                    "end": end,
                    "segment_indices": [idx + 1 for idx in members],
                })

                # Merged angles/radii are indexed by group number, not by segment index
                group_idx = gid - 1  # gid is 1-based
                angle = float(bend_angles[group_idx]) if group_idx >= 0 and group_idx < len(bend_angles) else None
                radius = float(bend_radii[group_idx]) if group_idx >= 0 and group_idx < len(bend_radii) else None
                bends_logical.append({
                    "id": gid,
                    "type": "up" if angle is not None and angle >= 0 else "down",
                    "angle": abs(angle) if angle is not None else None,
                    "radius": radius,
                })

            fold_lines_count = len(bend_line_groups) if bend_line_groups else len(fold_edges)

            return {
                "success": True,
                "error": None,
                "attempts": attempt,
                "error_details": error_details,
                "flat_length": dims.get("flat_length", 0.0),
                "flat_width": dims.get("flat_width", 0.0),
                "bend_angles": merged_angles,
                "bend_radii": merged_radii,
                "bend_lengths": merged_lengths,
                "bend_count": len(merged_angles),
                "bend_line_segments": bend_line_segments,
                "bend_line_groups": bend_line_groups,
                "raw_fold_lines": len(fold_edges),
                "fold_lines": fold_lines_count,
                "fold_details": fold_details,
                "bends_logical": bends_logical,
                "used_face_idx": face_idx,
                "flat_step_path": flat_step_path,
                "unfolder_variant": "new",
                "sheetmetal_source": getattr(SheetMetalNewUnfolder, "__file__", ""),
            }
        except Exception as exc:
            error_details.append(
                {
                    "face_idx": face_idx,
                    "stage": "new_unfolder",
                    "error_code": -3,
                    "message": str(exc),
                    "traceback": traceback.format_exc(),
                }
            )
        finally:
            try:
                FreeCAD.closeDocument("PersistentUnfoldDoc")
            except Exception:
                pass

    return {
        "success": False,
        "error": error_details[-1]["message"] if error_details else "New unfolder failed",
        "attempts": len(error_details),
        "error_details": error_details,
        "used_face_idx": None,
        "unfolder_variant": "new",
    }


def _run_old_unfolder(step_path: str, output_dir: str, part_name: str, k_factor: float) -> dict[str, Any]:
    os.makedirs(output_dir, exist_ok=True)
    dxf_path = os.path.join(output_dir, f"{part_name}_flat.dxf")
    with contextlib.redirect_stdout(sys.stderr):
        result = freecad_unfold.unfold_sheet_metal(
            step_path=step_path,
            output_dxf=dxf_path,
            k_factor=float(k_factor),
        )

    payload = {
        "success": bool(result.get("success")),
        "error": result.get("error"),
        "attempts": result.get("attempts"),
        "error_details": _serializable_error_details(result.get("error_details")),
        "flat_length": result.get("flat_length"),
        "flat_width": result.get("flat_width"),
        "bend_angles": result.get("bend_angles", []),
        "bend_radii": result.get("bend_radii", []),
        "bend_lengths": result.get("bend_lengths", []),
        "bend_count": result.get("bend_count"),
        "bend_line_segments": result.get("bend_line_segments", []),
        "bend_line_groups": result.get("bend_line_groups", []),
        "raw_fold_lines": result.get("raw_fold_lines"),
        "used_face_idx": result.get("used_face_idx"),
        "unfolder_variant": "old",
        "sheetmetal_source": result.get("sheetmetal_source"),
    }

    # Build fold_details and bends_logical from old unfolder results for viewer
    old_groups = result.get("bend_line_groups", [])
    old_angles = result.get("bend_angles", [])
    old_radii = result.get("bend_radii", [])
    old_segments = result.get("bend_line_segments", [])
    if old_groups:
        fold_details = []
        bends_logical = []
        for grp in old_groups:
            gid = grp.get("id", len(fold_details) + 1)
            members = grp.get("segment_indices", [])
            axis = str(grp.get("axis", "X")).lower()
            # Compute merged span from segments
            span_min = None
            span_max = None
            center_x, center_y = 0.0, 0.0
            n_segs = 0
            for seg in old_segments:
                if seg.get("index") in members:
                    s_span = seg.get("axis_span")
                    if s_span and len(s_span) >= 2:
                        lo, hi = float(min(s_span[0], s_span[1])), float(max(s_span[0], s_span[1]))
                        if span_min is None or lo < span_min:
                            span_min = lo
                        if span_max is None or hi > span_max:
                            span_max = hi
                    c = seg.get("center")
                    if c and len(c) >= 2:
                        center_x += float(c[0])
                        center_y += float(c[1])
                        n_segs += 1
            if span_min is None:
                span_min = 0.0
            if span_max is None:
                span_max = 0.0
            if n_segs > 0:
                center_x /= n_segs
                center_y /= n_segs

            if axis == "x":
                start = (span_min, center_y, 0.0)
                end = (span_max, center_y, 0.0)
            else:
                start = (center_x, span_min, 0.0)
                end = (center_x, span_max, 0.0)
            import math as _math
            line_length = _math.dist(start, end)
            center = ((start[0] + end[0]) / 2.0, (start[1] + end[1]) / 2.0, 0.0)

            fold_details.append({
                "id": gid,
                "length": round(line_length, 2),
                "center": center,
                "axis": axis,
                "axis_span": (span_min, span_max),
                "start": start,
                "end": end,
                "segment_indices": [idx + 1 for idx in members],
            })

            # Merged angles/radii are indexed by group number, not by segment index
            group_idx = gid - 1  # gid is 1-based
            angle = float(old_angles[group_idx]) if group_idx >= 0 and group_idx < len(old_angles) else None
            radius = float(old_radii[group_idx]) if group_idx >= 0 and group_idx < len(old_radii) else None
            bends_logical.append({
                "id": gid,
                "type": "up" if angle is not None and angle >= 0 else "down",
                "angle": abs(angle) if angle is not None else None,
                "radius": radius,
            })

        payload["fold_lines"] = len(old_groups)
        payload["fold_details"] = fold_details
        payload["bends_logical"] = bends_logical
    elif result.get("success") and old_angles:
        # No groups but have angles — use raw bend count
        payload["fold_lines"] = len(old_angles)
        payload["bends_logical"] = [
            {"id": i + 1, "type": "up" if a >= 0 else "down", "angle": abs(a), "radius": old_radii[i] if i < len(old_radii) else None}
            for i, a in enumerate(old_angles)
        ]

    flat_shape = result.get("flat_shape")
    if result.get("success") and flat_shape is not None:
        flat_step_path = os.path.join(output_dir, f"{part_name}_flat.step")
        flat_shape.exportStep(flat_step_path)
        payload["flat_step_path"] = flat_step_path
    else:
        payload["flat_step_path"] = None

    return payload


def _handle_request(request: dict[str, Any]) -> dict[str, Any]:
    step_path = str(request.get("step_file") or "")
    output_dir = str(request.get("output_dir") or "")
    part_name = str(request.get("part_name") or "part")
    variant = str(request.get("variant") or "auto").strip().lower()
    k_factor = float(request.get("k_factor") or 0.44)

    if not step_path:
        return {"success": False, "error": "Missing step_file"}

    if variant in {"auto", "new"}:
        try:
            with contextlib.redirect_stdout(sys.stderr):
                new_result = _run_new_unfolder(step_path, output_dir, part_name, k_factor)
            if new_result.get("success") or variant == "new":
                return new_result
            new_errors = _serializable_error_details(new_result.get("error_details"))
        except Exception as exc:
            new_errors = [{
                "face_idx": -1,
                "stage": "new_unfolder",
                "error_code": -3,
                "message": str(exc),
                "traceback": traceback.format_exc(),
            }]
            if variant == "new":
                return {
                    "success": False,
                    "error": str(exc),
                    "attempts": 1,
                    "error_details": new_errors,
                    "unfolder_variant": "new",
                }
    else:
        new_errors = []

    old_result = _run_old_unfolder(step_path, output_dir, part_name, k_factor)
    if new_errors:
        old_result["error_details"] = new_errors + _serializable_error_details(old_result.get("error_details"))
        if not old_result.get("success") and not old_result.get("error"):
            old_result["error"] = new_errors[0]["message"]
    return old_result


def main() -> int:
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)

    ready = {
        "type": "ready",
        "pid": os.getpid(),
        "python": sys.executable,
        "freecad_version": getattr(FreeCAD, "Version", lambda: [])(),
    }
    print(json.dumps(ready), flush=True)

    for raw_line in sys.stdin:
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        try:
            request = json.loads(raw_line)
            request_id = request.get("id")
        except Exception:
            print(json.dumps({"id": None, "payload": {"success": False, "error": "Invalid worker request"}}), flush=True)
            continue

        try:
            payload = _handle_request(request)
        except Exception as exc:
            payload = {
                "success": False,
                "error": str(exc),
                "error_details": [{
                    "face_idx": -1,
                    "stage": "worker_exception",
                    "error_code": -9,
                    "message": str(exc),
                    "traceback": traceback.format_exc(),
                }],
            }

        print(json.dumps({"id": request_id, "payload": payload}), flush=True)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
