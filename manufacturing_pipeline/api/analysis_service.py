"""Bridge between the API and the existing manufacturing pipeline.

Wraps process_single_file() and enriches the result with AAG details.
"""

import os
import shutil
import json

from manufacturing_pipeline.core.utils import (
    run_analysis,
    get_output_dir,
)


def _load_timing_json(output_dir: str, step_file: str) -> dict | None:
    """Load profiler timing JSON from output dir when available."""
    stem = os.path.splitext(os.path.basename(step_file))[0]
    timing_path = os.path.join(output_dir, f"{stem}_timing.json")
    if not os.path.exists(timing_path):
        return None

    try:
        with open(timing_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _build_timeline(result: dict, analysis, total_holes: int, timing_data: dict | None) -> tuple[list[dict], dict | None]:
    """Build replay timeline events and a compact summary."""
    if not timing_data:
        return [], None

    events: list[dict] = []
    current_ms = 0
    steps = timing_data.get("steps", [])

    for step in steps:
        step_name = step.get("name", "Unknown")
        step_status = (step.get("status") or "OK").upper()
        elapsed = float(step.get("elapsed") or 0.0)
        step_ms = int(round(elapsed * 1000))

        events.append(
            {
                "type": "stage_start",
                "stage": step_name,
                "timestamp_ms": current_ms,
                "status": "START",
                "payload": {
                    "num": step.get("num"),
                    "total": step.get("total"),
                },
            }
        )

        for sub in step.get("sub_steps", []):
            sub_elapsed = float(sub.get("elapsed") or 0.0)
            sub_ms = int(round(sub_elapsed * 1000))
            events.append(
                {
                    "type": "sub_step",
                    "stage": step_name,
                    "timestamp_ms": current_ms,
                    "status": "OK",
                    "payload": {
                        "name": sub.get("name"),
                        "elapsed_seconds": round(sub_elapsed, 4),
                        "count": sub.get("count"),
                    },
                }
            )
            current_ms += sub_ms

        if step_status == "SKIP":
            end_type = "stage_skipped"
        elif step_status == "FAIL":
            end_type = "stage_failed"
        else:
            end_type = "stage_end"

        current_ms = max(current_ms, 0) + max(step_ms - sum(int(round(float(s.get("elapsed") or 0.0) * 1000)) for s in step.get("sub_steps", [])), 0)

        events.append(
            {
                "type": end_type,
                "stage": step_name,
                "timestamp_ms": current_ms,
                "status": step_status,
                "payload": {
                    "elapsed_seconds": round(elapsed, 4),
                    "error": step.get("error"),
                },
            }
        )

    route_result = getattr(analysis, "route_result", None)
    if route_result is not None:
        events.append(
            {
                "type": "classification_decision",
                "stage": "Profile Router",
                "timestamp_ms": 0,
                "status": "OK",
                "payload": {
                    "category": getattr(route_result.category, "value", None),
                    "profile_label": route_result.profile_label,
                    "confidence": route_result.confidence,
                    "method": route_result.method,
                    "variant": route_result.variant,
                    "reasoning": route_result.reasoning,
                },
            }
        )

    events.append(
        {
            "type": "holes_detected",
            "stage": "Detect holes",
            "timestamp_ms": current_ms,
            "status": "OK",
            "payload": {
                "total": total_holes,
            },
        }
    )

    events.append(
        {
            "type": "bends_detected",
            "stage": "Classify geometry",
            "timestamp_ms": current_ms,
            "status": "OK",
            "payload": {
                "total": result.get("production", {}).get("bends_total", 0),
                "up": result.get("production", {}).get("bends_up", 0),
                "down": result.get("production", {}).get("bends_down", 0),
            },
        }
    )

    unfold_result = getattr(analysis, "unfold_result", None)
    if unfold_result:
        success = bool(unfold_result.get("success"))
        events.append(
            {
                "type": "unfold_succeeded" if success else "unfold_failed",
                "stage": "Unfold",
                "timestamp_ms": current_ms,
                "status": "OK" if success else "FAIL",
                "payload": {
                    "flat_length": unfold_result.get("flat_length"),
                    "flat_width": unfold_result.get("flat_width"),
                    "fold_lines": unfold_result.get("fold_lines"),
                    "error": unfold_result.get("error"),
                    "error_details": unfold_result.get("error_details"),
                },
            }
        )

    total_elapsed = float(timing_data.get("total_elapsed") or 0.0)
    summary = {
        "total_elapsed_seconds": round(total_elapsed, 4),
        "event_count": len(events),
        "step_count": len(steps),
        "part_name": timing_data.get("part_name") or result.get("file"),
        "analysis_started_at": None,
        "active_stage": None,
        "active_stage_started_at": None,
        "active_stage_elapsed_seconds": None,
        "completed_step_count": len(steps),
        "total_steps_hint": max((step.get("total") or 0 for step in steps), default=len(steps)) or len(steps),
    }
    return events, summary


def _serialize_analysis_reasoning(analysis) -> list[dict]:
    serialized = []
    for item in getattr(analysis, "reasoning", []) or []:
        serialized.append(
            {
                "step": getattr(item, "step", ""),
                "observation": getattr(item, "observation", ""),
                "conclusion": getattr(item, "conclusion", ""),
                "details": getattr(item, "details", {}) or {},
            }
        )
    return serialized


def run_step_analysis(step_file: str, use_aag: bool = True, progress_callback=None) -> dict:
    """Run the manufacturing analysis pipeline on a STEP file.

    Args:
        step_file: Absolute path to the STEP file.
        use_aag: Whether to run AAG topology-based feature recognition.

    Returns:
        Enriched result dict with analysis data, AAG details, and production info.
    """

    class Args:
        def __init__(self):
            self.analyze = False
            self.aag = use_aag
            self.aag_fallback = use_aag
            self.verbose = False
            self.debug = False
            self.no_unfold = False
            self.no_pdf = True  # No PDF generation for API
            self.no_cache = True

    args = Args()
    part_name = os.path.basename(step_file)

    try:
        output_dir, _ = get_output_dir(step_file)
        analysis, total_holes = run_analysis(
            step_file,
            output_dir,
            args,
            progress_callback=progress_callback,
        )
        timing_data = _load_timing_json(output_dir, step_file)

        # Build base result
        result = {
            "file": part_name,
            "success": True,
            "category": getattr(analysis, "part_category", "UNKNOWN"),
            "part_type": None,
            "thickness": getattr(analysis, "thickness", 0),
            "dimensions": {
                "length": getattr(analysis, "length", 0),
                "width": getattr(analysis, "width", 0),
                "height": getattr(analysis, "height", 0),
            },
            "flat_dimensions": None,
            "production": {
                "holes_total": total_holes,
                "bends_total": getattr(analysis, "bend_count_erp", 0),
                "bends_up": 0,
                "bends_down": 0,
            },
            "aag_details": None,
        }

        # Convert part_type enum to string
        pt = getattr(analysis, "part_type", None)
        if pt is not None:
            result["part_type"] = pt.value if hasattr(pt, "value") else str(pt)

        # Add flat dimensions if unfold was successful
        flat_length = getattr(analysis, "flat_length", 0)
        flat_width = getattr(analysis, "flat_width", 0)
        if flat_length > 0 and flat_width > 0:
            result["flat_dimensions"] = {
                "length": flat_length,
                "width": flat_width,
            }

        # Extract up/down bend counts from unfold result
        unfold_result = getattr(analysis, "unfold_result", None)
        if unfold_result and unfold_result.get("success"):
            bends_logical = unfold_result.get("bends_logical", [])
            result["production"]["bends_up"] = sum(
                1 for b in bends_logical if b.get("type") == "up"
            )
            result["production"]["bends_down"] = sum(
                1 for b in bends_logical if b.get("type") == "down"
            )

        # Add AAG details if available
        aag_data = getattr(analysis, "aag_result", None)
        if aag_data and aag_data.get("success"):
            result["aag_details"] = {
                "cut_length": aag_data.get("cut_length"),
                "total_cut_length": aag_data.get("total_cut_length"),
                "pierce_count": aag_data.get("pierce_count"),
                "estimated_cut_time_seconds": aag_data.get("estimated_cut_time"),
                "face_count": aag_data.get("face_count"),
                "edge_count": aag_data.get("edge_count"),
                "hole_details": aag_data.get("holes_detail", []),
                "bend_details": aag_data.get("bends_detail", []),
            }

        # Add route details when available
        route_result = getattr(analysis, "route_result", None)
        if route_result is not None:
            result["route"] = {
                "category": getattr(route_result.category, "value", None),
                "profile_label": route_result.profile_label,
                "confidence": route_result.confidence,
                "method": route_result.method,
                "variant": route_result.variant,
                "reasoning": route_result.reasoning,
            }

        result["visuals"] = {
            "router": {
                **(result.get("route") or {}),
                **(getattr(route_result, "debug", None) or {}),
            } if route_result is not None else None,
            "classification": {
                **(getattr(analysis, "classification_visuals", None) or {}),
                "part_category": result.get("category"),
                "part_type": result.get("part_type"),
                "thickness": result.get("thickness"),
                "dimensions": result.get("dimensions"),
                "trace": getattr(analysis, "classification_trace", {}) or {},
                "rules": list((getattr(analysis, "classification_trace", {}) or {}).get("rules") or []),
                "criteria": getattr(analysis, "classification_criteria", []) or [],
                "matrix_doc": "docs/CLASSIFICATION_THRESHOLDS_MATRIX.md",
                "reasoning": _serialize_analysis_reasoning(analysis),
            },
            "holes": {
                "total": total_holes,
                **(getattr(analysis, "detected_hole_visuals", None) or {"items": []}),
            },
            "unfold": {
                "success": bool(unfold_result and unfold_result.get("success")),
                "flat_length": unfold_result.get("flat_length") if unfold_result else None,
                "flat_width": unfold_result.get("flat_width") if unfold_result else None,
                "fold_lines": unfold_result.get("fold_lines") if unfold_result else 0,
                "fold_details": unfold_result.get("fold_details", []) if unfold_result else [],
                "bends_logical": unfold_result.get("bends_logical", []) if unfold_result else [],
            },
        }

        # Build replay timeline from profiler + analysis outputs
        timeline_events, timeline_summary = _build_timeline(result, analysis, total_holes, timing_data)
        result["timeline"] = timeline_events
        result["timeline_summary"] = timeline_summary

        # Tessellate STEP geometry for 3D viewer
        try:
            from manufacturing_pipeline.analysis.step_processing import (
                extract_display_edges,
                load_step_file,
                tessellate_shape,
            )

            def _rounded_mesh(path: str):
                shape = load_step_file(path)
                mesh_data = tessellate_shape(shape, deflection=0.8, angular_deflection=0.7)
                if not mesh_data or len(mesh_data.get("vertices", [])) == 0:
                    return None
                mesh_data["display_edges"] = extract_display_edges(mesh_data)
                mesh_data["vertices"] = [round(v, 2) for v in mesh_data["vertices"]]
                mesh_data["normals"] = [round(n, 4) for n in mesh_data["normals"]]
                mesh_data["display_edges"] = [round(v, 2) for v in mesh_data.get("display_edges", [])]
                return mesh_data

            mesh_data = _rounded_mesh(step_file)
            if mesh_data:
                result["mesh"] = mesh_data

            flat_step_path = unfold_result.get("flat_step_path") if unfold_result else None
            if flat_step_path and os.path.exists(flat_step_path):
                flat_mesh_data = _rounded_mesh(flat_step_path)
                if flat_mesh_data:
                    result.setdefault("visuals", {}).setdefault("unfold", {})["flat_mesh"] = flat_mesh_data
        except Exception:
            pass  # Mesh is optional, don't fail the analysis

        # Cleanup output dir (we don't need generated files for API mode)
        try:
            shutil.rmtree(output_dir, ignore_errors=True)
        except Exception:
            pass

        return result

    except Exception as e:
        return {
            "file": part_name,
            "success": False,
            "error": str(e),
        }
