"""API route definitions."""

import csv
import collections
import hashlib
import json
import io
import logging
import math
import os
import shutil
import uuid
import zipfile
from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse, Response

from manufacturing_pipeline.api.config import ALLOWED_EXTENSIONS, DISABLE_STAGES, MAX_FILE_SIZE_MB, UPLOAD_DIR, VALID_STAGE_KEYS
from manufacturing_pipeline.api.schemas import (
    AnalysisResult,
    BulkJobActionResult,
    HealthResponse,
    JobCreated,
    JobListItem,
    JobListResponse,
    JobStats,
    JobStatus,
    JobTimelineResponse,
    TimelineEvent,
    TimelineSummary,
    UnfoldStatus,
    UnfoldResult,
)
from manufacturing_pipeline.api.job_manager import jobs
from manufacturing_pipeline.api.analysis_service import _build_sheet_metrics, run_step_analysis
from manufacturing_pipeline.core.runtime_unfold import canonicalize_unfold_payload, run_unfold_to_step
from manufacturing_pipeline.analysis.io.step_file_io import extract_solids_to_temp_files
from manufacturing_pipeline.reporting.xml_exporter import export_to_xml
from pathlib import Path
import tempfile

router = APIRouter(prefix="/api/v1")

# In-memory ring buffer for recent log lines (last 500)
_LOG_BUFFER: collections.deque = collections.deque(maxlen=500)


class _BufferHandler(logging.Handler):
    def emit(self, record):
        _LOG_BUFFER.append(self.format(record))


_buf_handler = _BufferHandler()
_buf_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
logging.getLogger().addHandler(_buf_handler)
DEFAULT_VIEWER_STEP = Path(__file__).resolve().parents[2] / "data" / "testfile" / "nieuwmodel.step"


def _build_fold_detail_from_group(group: dict, segments: list[dict], index: int) -> dict | None:
    member_indexes = [int(value) for value in (group.get("segment_indices") or []) if isinstance(value, (int, float))]
    members = []
    for member_index in member_indexes:
        for fallback_index, segment in enumerate(segments):
            segment_index = segment.get("index", fallback_index)
            try:
                segment_index = int(segment_index)
            except Exception:
                segment_index = fallback_index
            if segment_index == member_index:
                members.append(segment)
                break
    if not members:
        return None

    first = members[0]
    center = first.get("center") or [0.0, 0.0, 0.0]
    fixed_x = float(center[0]) if len(center) > 0 else 0.0
    fixed_y = float(center[1]) if len(center) > 1 else 0.0
    fixed_z = float(center[2]) if len(center) > 2 else 0.0
    axis = str(group.get("axis") or first.get("axis") or "Y").upper()
    span_values = []
    for segment in members:
        axis_span = segment.get("axis_span") or []
        if len(axis_span) >= 2:
          span_values.extend([float(axis_span[0]), float(axis_span[1])])
    if not span_values:
        return None

    if axis == "X":
        start = [min(span_values), fixed_y, fixed_z]
        end = [max(span_values), fixed_y, fixed_z]
    else:
        start = [fixed_x, min(span_values), fixed_z]
        end = [fixed_x, max(span_values), fixed_z]

    return {
        "id": int(group.get("id") or (index + 1)),
        "axis": axis.lower(),
        "center": [
            (float(start[0]) + float(end[0])) / 2.0,
            (float(start[1]) + float(end[1])) / 2.0,
            (float(start[2]) + float(end[2])) / 2.0,
        ],
        "start": start,
        "end": end,
        "length": abs(float(end[0]) - float(start[0])) + abs(float(end[1]) - float(start[1])),
        "segment_indices": [member_index + 1 for member_index in member_indexes],
    }


def _normalize_unfold_payload(result: dict | None) -> dict:
    return canonicalize_unfold_payload(result)


def _resolve_job_timeline(job) -> tuple[list, dict | None]:
    """Single source of truth for reading timeline events from a job.

    For completed jobs: reads from result['timeline'], falls back to
    _rebuild_timeline_from_result_dict when timeline was never stored
    (e.g. old cached jobs).  For in-progress jobs: reads live
    progress_events from memory.
    """
    if job.status == "completed":
        timeline_raw = (job.result or {}).get("timeline") or []
        summary_raw = (job.result or {}).get("timeline_summary")
        if not timeline_raw and job.result:
            timeline_raw, summary_raw = _rebuild_timeline_from_result_dict(job.result)
    else:
        timeline_raw = getattr(job, "progress_events", None) or []
        summary_raw = _refresh_live_summary(getattr(job, "progress_summary", None))
    return timeline_raw or [], summary_raw


def _refresh_live_summary(summary_raw: dict | None) -> dict | None:
    if not summary_raw:
        return None

    summary = dict(summary_raw)
    now = datetime.now(timezone.utc)

    analysis_started_at = summary.get("analysis_started_at")
    if analysis_started_at:
        try:
            started_dt = datetime.fromisoformat(analysis_started_at)
            summary["total_elapsed_seconds"] = round(max((now - started_dt).total_seconds(), 0.0), 4)
        except ValueError:
            pass

    active_stage_started_at = summary.get("active_stage_started_at")
    if summary.get("active_stage") and active_stage_started_at:
        try:
            active_dt = datetime.fromisoformat(active_stage_started_at)
            summary["active_stage_elapsed_seconds"] = round(max((now - active_dt).total_seconds(), 0.0), 4)
        except ValueError:
            pass

    return summary


def _run_analysis_job(job_id: str, step_path: str, use_aag: bool, disable_stages: set[str] | None = None):
    """Background task that runs the analysis and updates job state."""
    job = jobs.get(job_id)
    if job and job.status == "cancelled":
        return
    jobs.mark_processing(job_id)
    try:
        result = run_step_analysis(
            step_path,
            use_aag=use_aag,
            progress_callback=lambda event, summary: jobs.record_progress(job_id, event, summary),
            disable_stages=disable_stages,
        )
        # Don't overwrite a job that was cancelled while analysis was running
        job = jobs.get(job_id)
        if job and job.status == "cancelled":
            return
        jobs.mark_completed(job_id, result)
    except Exception as e:
        job = jobs.get(job_id)
        if job and job.status == "cancelled":
            return
        jobs.mark_failed(job_id, str(e))


def _build_unfold_result(job_id: str, result: dict | None, error: str | None = None) -> dict | None:
    if not result and not error:
        return None

    payload = _normalize_unfold_payload(result)
    payload.setdefault("success", False)
    payload["error"] = error or payload.get("error")
    payload["flat_step_url"] = (
        f"/api/v1/jobs/{job_id}/unfold/artifacts/flat-step"
        if payload.get("flat_step_path") and os.path.exists(payload["flat_step_path"])
        else None
    )
    dxf_path = payload.get("dxf_path") or payload.get("output_dxf")
    payload["dxf_url"] = (
        f"/api/v1/jobs/{job_id}/unfold/artifacts/dxf"
        if dxf_path and os.path.exists(dxf_path)
        else None
    )
    # Pass through debug/timing fields from the unfold result
    for key in (
        "unfold_timings_ms",
        "route",
        "error_details",
        "theoretical",
        "attempts",
        "simplified_faces",
        "selected_strategy",
        "skip_sheet_tree_reason",
        "complexity_score",
        "geometry_diagnostics",
    ):
        if result and key in result and key not in payload:
            payload[key] = result[key]
    return payload


def _build_unfold_status(job) -> UnfoldStatus:
    unfold_payload = _build_unfold_result(job.job_id, getattr(job, "unfold_result", None), getattr(job, "unfold_error", None))
    unfold_status = getattr(job, "unfold_status", "idle") or "idle"
    unfold_started_at = getattr(job, "unfold_started_at", None)
    elapsed_seconds = None
    if unfold_status == "processing" and unfold_started_at is not None:
        elapsed_seconds = round(max((datetime.now(timezone.utc) - unfold_started_at).total_seconds(), 0.0), 1)
    return UnfoldStatus(
        status=unfold_status,
        requested_at=getattr(job, "unfold_requested_at", None),
        started_at=unfold_started_at,
        completed_at=getattr(job, "unfold_completed_at", None),
        error=getattr(job, "unfold_error", None),
        result=UnfoldResult(**unfold_payload) if unfold_payload else None,
        phase=getattr(job, "unfold_phase", None) if isinstance(getattr(job, "unfold_phase", None), str) else None,
        elapsed_seconds=elapsed_seconds,
    )


def _triangle_area(point_a: tuple[float, float, float], point_b: tuple[float, float, float], point_c: tuple[float, float, float]) -> float:
    ab = (point_b[0] - point_a[0], point_b[1] - point_a[1], point_b[2] - point_a[2])
    ac = (point_c[0] - point_a[0], point_c[1] - point_a[1], point_c[2] - point_a[2])
    cross = (
        ab[1] * ac[2] - ab[2] * ac[1],
        ab[2] * ac[0] - ab[0] * ac[2],
        ab[0] * ac[1] - ab[1] * ac[0],
    )
    return 0.5 * math.sqrt(cross[0] * cross[0] + cross[1] * cross[1] + cross[2] * cross[2])


def _mesh_surface_area(mesh: dict | None) -> float:
    if not isinstance(mesh, dict):
        return 0.0
    vertices = mesh.get("vertices") or []
    indices = mesh.get("indices") or []
    if len(vertices) < 9 or len(indices) < 3:
        return 0.0

    def _point(index: int) -> tuple[float, float, float]:
        offset = index * 3
        return (
            float(vertices[offset]),
            float(vertices[offset + 1]),
            float(vertices[offset + 2]),
        )

    total = 0.0
    for i in range(0, len(indices) - 2, 3):
        try:
            p0 = _point(int(indices[i]))
            p1 = _point(int(indices[i + 1]))
            p2 = _point(int(indices[i + 2]))
        except Exception:
            continue
        total += _triangle_area(p0, p1, p2)
    return total


def _mesh_volume(mesh: dict | None) -> float:
    if not isinstance(mesh, dict):
        return 0.0
    vertices = mesh.get("vertices") or []
    indices = mesh.get("indices") or []
    if len(vertices) < 9 or len(indices) < 3:
        return 0.0

    def _point(index: int) -> tuple[float, float, float]:
        offset = index * 3
        return (
            float(vertices[offset]),
            float(vertices[offset + 1]),
            float(vertices[offset + 2]),
        )

    total = 0.0
    for i in range(0, len(indices) - 2, 3):
        try:
            p0 = _point(int(indices[i]))
            p1 = _point(int(indices[i + 1]))
            p2 = _point(int(indices[i + 2]))
        except Exception:
            continue
        total += (
            p0[0] * (p1[1] * p2[2] - p1[2] * p2[1])
            - p0[1] * (p1[0] * p2[2] - p1[2] * p2[0])
            + p0[2] * (p1[0] * p2[1] - p1[1] * p2[0])
        )
    return abs(total) / 6.0


def _has_nonzero_sheet_metrics(metrics: dict | None) -> bool:
    if not isinstance(metrics, dict):
        return False
    for key in ("volume", "top_area", "area_no_holes", "total_area", "outer_contour", "total_contour"):
        try:
            if abs(float(metrics.get(key) or 0.0)) > 1e-6:
                return True
        except Exception:
            continue
    return False


def _has_meaningful_bend_geometry(bends: list[dict] | None) -> bool:
    for bend in bends or []:
        try:
            angle = bend.get("angle")
            radius = bend.get("radius")
            if angle is not None and abs(float(angle)) > 1e-6:
                return True
            if radius is not None and abs(float(radius)) > 1e-6:
                return True
        except Exception:
            continue
    return False


def _meaningful_bend_candidates(unfold_visuals: dict | None) -> list[dict]:
    candidates = []
    for bend in (unfold_visuals or {}).get("bends_logical") or []:
        try:
            angle = bend.get("angle")
            radius = bend.get("radius")
            if (angle is not None and abs(float(angle)) > 1e-6) or (radius is not None and abs(float(radius)) > 1e-6):
                candidates.append(bend)
        except Exception:
            continue
    return candidates


def _merge_bends_logical(existing_unfold: dict, incoming_unfold: dict) -> list[dict]:
    incoming_bends = list(incoming_unfold.get("bends_logical") or [])
    if _has_meaningful_bend_geometry(incoming_bends):
        return incoming_bends

    meaningful_existing = _meaningful_bend_candidates(existing_unfold)
    if not incoming_bends:
        return meaningful_existing or list(existing_unfold.get("bends_logical") or [])

    if not meaningful_existing:
        return incoming_bends or list(existing_unfold.get("bends_logical") or [])

    merged = []
    for index, bend in enumerate(incoming_bends):
        fallback = meaningful_existing[index] if index < len(meaningful_existing) else meaningful_existing[-1]
        merged.append({
            **fallback,
            **bend,
            "angle": fallback.get("angle") if bend.get("angle") in (None, 0, 0.0, "0", "0.0") else bend.get("angle"),
            "radius": fallback.get("radius") if bend.get("radius") in (None, 0, 0.0, "0", "0.0") else bend.get("radius"),
            "type": bend.get("type") or fallback.get("type"),
            "id": bend.get("id") or fallback.get("id") or (index + 1),
        })
    return merged


def _merge_unfold_visuals(existing_unfold: dict | None, incoming_unfold: dict | None) -> dict:
    existing = dict(existing_unfold or {})
    incoming = dict(incoming_unfold or {})
    if not incoming:
        return existing

    merged = {**existing, **incoming}
    merged_bends = _merge_bends_logical(existing, incoming)
    if merged_bends:
        merged["bends_logical"] = merged_bends
        merged["bend_angles_erp"] = [
            float(bend["angle"])
            for bend in merged_bends
            if bend.get("angle") not in (None, "")
        ]
    elif existing.get("bend_angles_erp"):
        merged["bend_angles_erp"] = list(existing.get("bend_angles_erp") or [])

    if not merged.get("bend_angles_raw") and existing.get("bend_angles_raw"):
        merged["bend_angles_raw"] = list(existing.get("bend_angles_raw") or [])
    return merged


def _effective_result_dict(job) -> dict:
    base_result = getattr(job, "result", None) or {}
    if not base_result:
        return {}

    result = deepcopy(base_result)
    visuals = dict(result.get("visuals") or {})
    merged_unfold = _merge_unfold_visuals(
        visuals.get("unfold") or {},
        _build_unfold_result(job.job_id, getattr(job, "unfold_result", None), getattr(job, "unfold_error", None)),
    )
    if merged_unfold:
        visuals["unfold"] = merged_unfold
        result["visuals"] = visuals

        production = dict(result.get("production") or {})
        if merged_unfold.get("success"):
            fold_lines = int(merged_unfold.get("fold_lines") or production.get("bends_total") or 0)
            production["bends_total"] = fold_lines
            bends_logical = merged_unfold.get("bends_logical") or []
            production["bends_up"] = sum(1 for bend in bends_logical if str(bend.get("type") or "").lower() == "up")
            production["bends_down"] = sum(1 for bend in bends_logical if str(bend.get("type") or "").lower() == "down")
            result["production"] = production

            flat_length = merged_unfold.get("flat_length")
            flat_width = merged_unfold.get("flat_width")
            if flat_length or flat_width:
                result["flat_dimensions"] = {
                    "length": flat_length,
                    "width": flat_width,
                }

    category = str(result.get("category") or "").upper()
    if category in {"PLAAT (VLAK)", "GEBOGEN PLAATWERK", "SHEET_METAL"} and not _has_nonzero_sheet_metrics(result.get("sheet_metrics")):
        mesh = result.get("mesh") or {}
        volume = _mesh_volume(mesh)
        surface_area = _mesh_surface_area(mesh)
        if volume <= 0:
            dimensions = result.get("dimensions") or {}
            volume = float(dimensions.get("length") or 0.0) * float(dimensions.get("width") or 0.0) * float(dimensions.get("height") or 0.0)
        if volume > 0:
            result["sheet_metrics"] = _build_sheet_metrics(
                result,
                SimpleNamespace(volume=volume, surface_area=surface_area),
            )

    return result


def _source_step_available(job) -> bool:
    return bool(getattr(job, "file_path", None)) and os.path.exists(job.file_path)


def _rebuild_timeline_from_result_dict(result: dict) -> tuple[list, dict | None]:
    """Reconstruct minimal timeline events from a completed result dict.

    Used when result['timeline'] is empty (e.g. old cached job where timing_data
    was unavailable at analysis time).  Does not require the analysis object —
    only the stored result/visuals data.  Stages get synthetic stage_end events
    so the viewer's stage list is selectable.
    """
    from manufacturing_pipeline.api.analysis_service import _synthetic_stage_end

    events = []
    current_ms = 0
    visuals = result.get("visuals") or {}
    production = result.get("production") or {}

    route = result.get("route") or {}
    if route:
        events.append(_synthetic_stage_end("Profile Router", current_ms))
        events.append({
            "type": "classification_decision",
            "stage": "Profile Router",
            "timestamp_ms": 0,
            "status": "OK",
            "payload": {k: v for k, v in route.items() if k != "debug"},
        })

    classification = visuals.get("classification") or {}
    if classification or result.get("category"):
        events.append(_synthetic_stage_end("Classify geometry", current_ms))
        events.append({
            "type": "geometry_classified",
            "stage": "Classify geometry",
            "timestamp_ms": current_ms,
            "status": "OK",
            "payload": {
                **classification,
                "category": result.get("category"),
                "part_type": result.get("part_type"),
                "bends_total": production.get("bends_total", 0),
            },
        })

    holes_pre_unfold = visuals.get("holes_pre_unfold") or {}
    if holes_pre_unfold.get("items"):
        events.append(_synthetic_stage_end("Detect holes (pre-unfold)", current_ms))
        events.append({
            "type": "holes_detected_pre_unfold",
            "stage": "Detect holes (pre-unfold)",
            "timestamp_ms": current_ms,
            "status": "OK",
            "payload": {k: v for k, v in holes_pre_unfold.items() if k != "flat_mesh"},
        })

    holes = visuals.get("holes") or {}
    events.append(_synthetic_stage_end("Detect holes", current_ms))
    events.append({
        "type": "holes_detected",
        "stage": "Detect holes",
        "timestamp_ms": current_ms,
        "status": "OK",
        "payload": {"total": holes.get("total", 0)},
    })
    events.append({
        "type": "bends_detected",
        "stage": "Classify geometry",
        "timestamp_ms": current_ms,
        "status": "OK",
        "payload": {
            "total": production.get("bends_total", 0),
            "up": production.get("bends_up", 0),
            "down": production.get("bends_down", 0),
        },
    })

    unfold = visuals.get("unfold") or {}
    if unfold:
        success = bool(unfold.get("success"))
        events.append(_synthetic_stage_end("Unfold", current_ms, "OK" if success else "FAIL"))
        events.append({
            "type": "unfold_result",
            "stage": "Unfold",
            "timestamp_ms": current_ms,
            "status": "OK" if success else "FAIL",
            "payload": {k: v for k, v in unfold.items() if k not in {"flat_mesh", "bends_3d"}},
        })

    if not events:
        return [], None
    summary = {
        "total_elapsed_seconds": 0.0,
        "event_count": len(events),
        "step_count": 0,
        "part_name": result.get("file"),
        "analysis_started_at": None,
        "active_stage": None,
        "active_stage_started_at": None,
        "active_stage_elapsed_seconds": None,
        "completed_step_count": 0,
        "total_steps_hint": 0,
    }
    return events, summary


def _build_request_fingerprint(file_hash: str, use_aag: bool, disable_stages: set[str]) -> str:
    payload = {
        "file_hash": file_hash,
        "aag": bool(use_aag),
        "disable_stages": sorted(disable_stages),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _safe_download_stem(value: str | None, fallback: str = "result") -> str:
    stem = Path(value or fallback).stem.strip() or fallback
    cleaned = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "_" for ch in stem)
    return cleaned or fallback


def _build_xml_bytes(result: dict) -> bytes:
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".xml") as tmp:
        tmp_path = Path(tmp.name)

    try:
        export_to_xml(result, tmp_path)
        return tmp_path.read_bytes()
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def _build_xml_response(result: dict) -> Response:
    filename = f"{_safe_download_stem(result.get('file'))}.xml"
    return Response(
        content=_build_xml_bytes(result),
        media_type="application/xml",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _part_results_for_download(job) -> list[tuple[str, dict]]:
    result = _effective_result_dict(job)
    parts = result.get("parts") or []
    if result.get("is_assembly") and parts:
        part_results: list[tuple[str, dict]] = []
        for index, part in enumerate(parts, start=1):
            part_copy = dict(part)
            part_name = (
                part_copy.get("solid_name")
                or part_copy.get("file")
                or f"part_{index:02d}"
            )
            part_copy["file"] = part_name
            part_results.append((part_name, part_copy))
        return part_results

    if result:
        single = dict(result)
        single_name = single.get("file") or getattr(job, "file_name", None) or job.job_id
        single["file"] = single_name
        return [(single_name, single)]

    return []


def _build_part_xml_zip(job) -> Response:
    parts = _part_results_for_download(job)
    if not parts:
        raise HTTPException(status_code=404, detail="Geen analyse-resultaten beschikbaar voor losse XML-bestanden")

    bundle = io.BytesIO()
    base_name = _safe_download_stem(getattr(job, "file_name", None) or job.job_id, fallback=job.job_id)
    folder_name = f"{base_name}_xml"
    with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for index, (part_name, part_result) in enumerate(parts, start=1):
            filename = f"{index:02d}_{_safe_download_stem(part_name, fallback=f'part_{index:02d}')}.xml"
            archive.writestr(f"{folder_name}/{filename}", _build_xml_bytes(part_result))

    return Response(
        content=bundle.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{folder_name}.zip"'},
    )


def _assembly_parts(job) -> list[dict]:
    result = getattr(job, "result", None) or {}
    if not result.get("is_assembly"):
        return []
    return result.get("parts") or []


def _get_job_part(job, part_index: int) -> dict:
    parts = _assembly_parts(job)
    for fallback_index, part in enumerate(parts):
        solid_index = part.get("solid_index", fallback_index)
        try:
            solid_index = int(solid_index)
        except Exception:
            solid_index = fallback_index
        if solid_index == part_index:
            return part
    raise HTTPException(status_code=404, detail="Assembly onderdeel niet gevonden")


def _part_storage_dir(job_id: str, part_index: int) -> str:
    return os.path.join(UPLOAD_DIR, job_id, "parts", f"part_{part_index:03d}")


def _part_step_filename(part: dict, part_index: int) -> str:
    part_name = (
        part.get("solid_name")
        or part.get("file")
        or f"part_{part_index + 1:02d}"
    )
    return f"{part_index + 1:02d}_{_safe_download_stem(part_name, fallback=f'part_{part_index + 1:02d}')}.step"


def _part_download_stem(part: dict, part_index: int) -> str:
    return Path(_part_step_filename(part, part_index)).stem


def _ensure_part_step_file(job, part_index: int) -> tuple[dict, str]:
    if not job.file_path or not os.path.exists(job.file_path):
        raise HTTPException(status_code=404, detail="Bron STEP bestand is niet meer beschikbaar")

    part = _get_job_part(job, part_index)
    part_dir = _part_storage_dir(job.job_id, part_index)
    os.makedirs(part_dir, exist_ok=True)
    cached_path = os.path.join(part_dir, _part_step_filename(part, part_index))
    if os.path.exists(cached_path):
        return part, cached_path

    extracted = extract_solids_to_temp_files(job.file_path)
    if not extracted:
        raise HTTPException(status_code=404, detail="Losse onderdeel STEP kon niet uit de samenstelling worden gehaald")

    tmp_dir = extracted[0].get("tmp_dir")
    try:
        selected = None
        representative_occurrence_index = int(
            part.get("representative_occurrence_index", part.get("solid_index", part_index))
        )
        for item in extracted:
            if int(item.get("index", -1)) == representative_occurrence_index:
                selected = item
                break
        if not selected:
            raise HTTPException(status_code=404, detail="Assembly onderdeel STEP niet gevonden")
        shutil.copyfile(selected["path"], cached_path)
        return part, cached_path
    finally:
        if tmp_dir:
            shutil.rmtree(tmp_dir, ignore_errors=True)


def _build_part_unfold_result(job, part_index: int, result: dict | None, error: str | None = None) -> dict | None:
    payload = _build_unfold_result(job.job_id, result, error)
    if not payload:
        return None
    payload["flat_step_url"] = (
        f"/api/v1/jobs/{job.job_id}/parts/{part_index}/unfold/artifacts/flat-step"
        if payload.get("flat_step_path") and os.path.exists(payload["flat_step_path"])
        else None
    )
    dxf_path = payload.get("dxf_path") or payload.get("output_dxf")
    payload["dxf_url"] = (
        f"/api/v1/jobs/{job.job_id}/parts/{part_index}/unfold/artifacts/dxf"
        if dxf_path and os.path.exists(dxf_path)
        else None
    )
    return payload


def _part_unfold_result_path(job_id: str, part_index: int) -> str:
    return os.path.join(_part_storage_dir(job_id, part_index), "unfold", "result.json")


def _load_cached_part_unfold_result(job, part_index: int) -> dict | None:
    result_path = _part_unfold_result_path(job.job_id, part_index)
    if not os.path.exists(result_path):
        return None
    try:
        payload = json.loads(Path(result_path).read_text(encoding="utf-8"))
    except Exception:
        return None
    return _build_part_unfold_result(job, part_index, payload)


def _ensure_part_unfold_result(job, part_index: int) -> dict:
    cached = _load_cached_part_unfold_result(job, part_index)
    if cached:
        return cached

    part, part_step_path = _ensure_part_step_file(job, part_index)
    output_dir = os.path.join(_part_storage_dir(job.job_id, part_index), "unfold")
    os.makedirs(output_dir, exist_ok=True)
    part_name = _part_download_stem(part, part_index)
    from types import SimpleNamespace

    analysis_stub = SimpleNamespace(
        bend_count_erp=(part or {}).get("production", {}).get("bends_total", 0),
        thickness=(part or {}).get("thickness") or 0.0,
        is_sheet_metal=True,
    )

    try:
        result = run_unfold_to_step(part_step_path, output_dir, part_name, analysis_stub)
        result["dxf_path"] = os.path.join(output_dir, f"{part_name}_flat.dxf")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    payload = _build_part_unfold_result(job, part_index, result) or {"success": False, "error": "Unfold-resultaat ontbreekt"}
    result_path = _part_unfold_result_path(job.job_id, part_index)
    Path(result_path).parent.mkdir(parents=True, exist_ok=True)
    Path(result_path).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return payload


def _build_part_step_zip(job) -> Response:
    parts = _assembly_parts(job)
    if not parts:
        raise HTTPException(status_code=404, detail="Geen assembly onderdelen beschikbaar")

    bundle = io.BytesIO()
    base_name = _safe_download_stem(getattr(job, "file_name", None) or job.job_id, fallback=job.job_id)
    folder_name = f"{base_name}_parts_step"
    with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for fallback_index, part in enumerate(parts):
            part_index = int(part.get("solid_index", fallback_index))
            resolved_part, step_path = _ensure_part_step_file(job, part_index)
            archive.write(step_path, arcname=f"{folder_name}/{_part_step_filename(resolved_part, part_index)}")

    return Response(
        content=bundle.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{folder_name}.zip"'},
    )


def _build_part_unfold_zip(job) -> Response:
    parts = _assembly_parts(job)
    if not parts:
        raise HTTPException(status_code=404, detail="Geen assembly onderdelen beschikbaar")

    bundle = io.BytesIO()
    base_name = _safe_download_stem(getattr(job, "file_name", None) or job.job_id, fallback=job.job_id)
    folder_name = f"{base_name}_parts_unfold"
    written = 0
    with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for fallback_index, part in enumerate(parts):
            part_index = int(part.get("solid_index", fallback_index))
            payload = _ensure_part_unfold_result(job, part_index)
            artifacts = [
                (payload.get("flat_step_path"), f"{folder_name}/{_part_download_stem(part, part_index)}_flat.step"),
                (payload.get("dxf_path") or payload.get("output_dxf"), f"{folder_name}/{_part_download_stem(part, part_index)}_flat.dxf"),
            ]
            for artifact_path, archive_name in artifacts:
                if artifact_path and os.path.exists(artifact_path):
                    archive.write(artifact_path, arcname=archive_name)
                    written += 1

    if not written:
        raise HTTPException(status_code=404, detail="Geen losse unfold-bestanden gevonden")

    return Response(
        content=bundle.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{folder_name}.zip"'},
    )


def _build_unfold_zip(job) -> Response:
    unfold_result = getattr(job, "unfold_result", None) or {}
    if getattr(job, "unfold_status", "idle") != "completed" or not unfold_result:
        raise HTTPException(status_code=404, detail="Unfold-bestanden zijn nog niet beschikbaar")

    artifact_specs = [
        (
            unfold_result.get("flat_step_path"),
            f"{_safe_download_stem(getattr(job, 'file_name', None) or 'part')}_flat.step",
        ),
        (
            unfold_result.get("dxf_path") or unfold_result.get("output_dxf"),
            f"{_safe_download_stem(getattr(job, 'file_name', None) or 'part')}_flat.dxf",
        ),
    ]
    existing_specs = [(path, name) for path, name in artifact_specs if path and os.path.exists(path)]
    if not existing_specs:
        raise HTTPException(status_code=404, detail="Geen unfold-artifacts gevonden")

    bundle = io.BytesIO()
    base_name = _safe_download_stem(getattr(job, "file_name", None) or job.job_id, fallback=job.job_id)
    folder_name = f"{base_name}_unfold"
    with zipfile.ZipFile(bundle, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for artifact_path, archive_name in existing_specs:
            archive.write(artifact_path, arcname=f"{folder_name}/{archive_name}")

    return Response(
        content=bundle.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{folder_name}.zip"'},
    )


def _run_unfold_job(job_id: str):
    jobs.mark_unfold_processing(job_id)
    job = jobs.get(job_id)
    if not job:
        return
    if not job.file_path or not os.path.exists(job.file_path):
        jobs.mark_unfold_failed(job_id, "Bron STEP bestand niet meer beschikbaar")
        return

    output_dir = os.path.join(UPLOAD_DIR, job_id, "unfold")
    os.makedirs(output_dir, exist_ok=True)
    part_name = Path(job.file_name).stem or "part"
    from types import SimpleNamespace

    try:
        analysis_stub = SimpleNamespace(
            bend_count_erp=(job.result or {}).get("production", {}).get("bends_total", 0),
            thickness=(job.result or {}).get("thickness") or 0.0,
            is_sheet_metal=True,
        )
        jobs.set_unfold_phase(job_id, "FreeCAD subprocess gestart...")
        result = run_unfold_to_step(job.file_path, output_dir, part_name, analysis_stub)
        result["dxf_path"] = os.path.join(output_dir, f"{part_name}_flat.dxf")
        jobs.mark_unfold_completed(job_id, _build_unfold_result(job_id, result) or result)
    except Exception as exc:
        jobs.mark_unfold_failed(job_id, str(exc))


@router.post("/analyze", response_model=JobCreated, status_code=202)
async def analyze(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    aag: bool = Query(True, description="Run AAG topology-based feature recognition"),
    disable_stages: str = Query("", description="Comma-separated stage keys to disable: classify_geometry, profile_router, detect_holes_pre_unfold, unfold, detect_holes, aag"),
    force: bool = Query(False, description="Skip deduplication and always create a new job"),
):
    """Upload a STEP file for manufacturing analysis.

    Returns a job_id that can be polled via GET /jobs/{job_id}.
    """
    # Parse and validate disable_stages
    request_disabled = {s.strip() for s in disable_stages.split(",") if s.strip()}
    invalid_keys = request_disabled - VALID_STAGE_KEYS
    if invalid_keys:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid disable_stages keys: {', '.join(sorted(invalid_keys))}. Valid: {', '.join(sorted(VALID_STAGE_KEYS))}",
        )
    merged_disable_stages = DISABLE_STAGES | request_disabled

    # Validate file extension
    _, ext = os.path.splitext(file.filename or "")
    if ext.lower() not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type '{ext}'. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    # Read and validate file size
    content = await file.read()
    if len(content) > MAX_FILE_SIZE_MB * 1024 * 1024:
        raise HTTPException(
            status_code=413, detail=f"File too large. Maximum: {MAX_FILE_SIZE_MB}MB"
        )

    file_hash = hashlib.md5(content).hexdigest()
    request_fingerprint = _build_request_fingerprint(file_hash, aag, merged_disable_stages)

    if not force:
        reusable_job = jobs.find_reusable_job(request_fingerprint)
        if reusable_job is not None:
            return JobCreated(
                job_id=reusable_job.job_id,
                status=reusable_job.status,
                reused_existing=True,
                created_at=reusable_job.created_at,
                archived=bool(getattr(reusable_job, "archived", False)),
                archived_at=getattr(reusable_job, "archived_at", None),
            )

    # Save file to upload directory
    job_id = str(uuid.uuid4())
    job_dir = os.path.join(UPLOAD_DIR, job_id)
    os.makedirs(job_dir, exist_ok=True)

    step_path = os.path.join(job_dir, file.filename or "upload.step")
    with open(step_path, "wb") as f:
        f.write(content)

    # Create job and queue analysis
    job = jobs.create(job_id, step_path,
                      file_name=file.filename or "upload.step",
                      file_hash=file_hash,
                      request_fingerprint=request_fingerprint,
                      file_size_bytes=len(content))
    background_tasks.add_task(_run_analysis_job, job_id, step_path, aag, merged_disable_stages)

    return JobCreated(
        job_id=job_id,
        status=job.status,
        created_at=job.created_at,
        archived=bool(getattr(job, "archived", False)),
        archived_at=getattr(job, "archived_at", None),
    )


@router.get("/jobs", response_model=JobListResponse)
async def list_jobs(
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    status: str = Query(None, description="Filter by status: queued, processing, completed, failed"),
    include_archived: bool = Query(False, description="Include archived jobs in the result"),
    archived_only: bool = Query(False, description="Only return archived jobs"),
):
    """List all analysis jobs (paginated)."""
    items, total = jobs.list_jobs(
        limit=limit,
        offset=offset,
        status=status,
        include_archived=include_archived,
        archived_only=archived_only,
    )
    return JobListResponse(
        items=[JobListItem(**item) for item in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/jobs/{job_id}", response_model=JobStatus)
async def get_job(
    job_id: str,
    format: str = Query("json", description="Response format: json, csv, or xml"),
):
    """Get the status and result of an analysis job."""
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if format == "csv" and job.status == "completed" and job.result:
        return _result_to_csv(_effective_result_dict(job))

    if format == "xml" and job.status == "completed" and job.result:
        return _build_xml_response(_effective_result_dict(job))


    timeline_raw, summary_raw = _resolve_job_timeline(job)

    response = JobStatus(
        job_id=job.job_id,
        status=job.status,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        archived=bool(getattr(job, "archived", False)),
        archived_at=getattr(job, "archived_at", None),
        source_step_available=_source_step_available(job),
        timeline_summary=TimelineSummary(**summary_raw) if summary_raw else None,
        timeline_events=[TimelineEvent(**e) for e in timeline_raw],
        error=job.error,
        unfold=_build_unfold_status(job),
    )

    if job.status == "completed" and job.result:
        response.result = AnalysisResult(**_effective_result_dict(job))

    return response


@router.post("/jobs/{job_id}/cancel", response_model=JobStatus)
async def cancel_job(job_id: str):
    """Cancel a queued or processing job."""
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    cancelled = jobs.mark_cancelled(job_id)
    if not cancelled:
        raise HTTPException(
            status_code=409,
            detail=f"Job cannot be cancelled (status: {job.status})",
        )
    job = jobs.get(job_id)
    timeline_raw, summary_raw = _resolve_job_timeline(job)
    return JobStatus(
        job_id=job.job_id,
        status=job.status,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        archived=bool(getattr(job, "archived", False)),
        archived_at=getattr(job, "archived_at", None),
        source_step_available=_source_step_available(job),
        timeline_summary=TimelineSummary(**summary_raw) if summary_raw else None,
        timeline_events=[TimelineEvent(**e) for e in timeline_raw],
        error="Geannuleerd door gebruiker",
    )


@router.post("/jobs/{job_id}/archive", response_model=JobStatus)
async def archive_job(job_id: str):
    """Archive a job so it disappears from the default jobs list."""
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    updated = jobs.set_archived(job_id, True)
    if not updated:
        raise HTTPException(status_code=404, detail="Job not found")
    timeline_raw, summary_raw = _resolve_job_timeline(updated)
    response = JobStatus(
        job_id=updated.job_id,
        status=updated.status,
        created_at=updated.created_at,
        started_at=updated.started_at,
        completed_at=updated.completed_at,
        archived=bool(getattr(updated, "archived", False)),
        archived_at=getattr(updated, "archived_at", None),
        source_step_available=_source_step_available(updated),
        timeline_summary=TimelineSummary(**summary_raw) if summary_raw else None,
        timeline_events=[TimelineEvent(**e) for e in timeline_raw],
        error=updated.error,
        unfold=_build_unfold_status(updated),
        result=AnalysisResult(**_effective_result_dict(updated)) if updated.status == "completed" and updated.result else None,
    )
    return response


@router.post("/jobs/{job_id}/restore", response_model=JobStatus)
async def restore_job(job_id: str):
    """Restore an archived job back into the default jobs list."""
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    updated = jobs.set_archived(job_id, False)
    if not updated:
        raise HTTPException(status_code=404, detail="Job not found")
    timeline_raw, summary_raw = _resolve_job_timeline(updated)
    response = JobStatus(
        job_id=updated.job_id,
        status=updated.status,
        created_at=updated.created_at,
        started_at=updated.started_at,
        completed_at=updated.completed_at,
        archived=bool(getattr(updated, "archived", False)),
        archived_at=getattr(updated, "archived_at", None),
        source_step_available=_source_step_available(updated),
        timeline_summary=TimelineSummary(**summary_raw) if summary_raw else None,
        timeline_events=[TimelineEvent(**e) for e in timeline_raw],
        error=updated.error,
        unfold=_build_unfold_status(updated),
        result=AnalysisResult(**_effective_result_dict(updated)) if updated.status == "completed" and updated.result else None,
    )
    return response


@router.post("/jobs/{job_id}/reanalyze", response_model=JobCreated, status_code=202)
async def reanalyze_job(
    job_id: str,
    background_tasks: BackgroundTasks,
    aag: bool = Query(True, description="Run AAG topology-based feature recognition"),
    disable_stages: str = Query("", description="Comma-separated stage keys to disable"),
):
    """Create a new analysis job from an existing job's stored STEP file."""
    original = jobs.get(job_id)
    if not original:
        raise HTTPException(status_code=404, detail="Job not found")
    if not _source_step_available(original):
        raise HTTPException(status_code=409, detail="Source STEP file is no longer available for this job")

    request_disabled = {s.strip() for s in disable_stages.split(",") if s.strip()}
    invalid_keys = request_disabled - VALID_STAGE_KEYS
    if invalid_keys:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid disable_stages keys: {', '.join(sorted(invalid_keys))}. Valid: {', '.join(sorted(VALID_STAGE_KEYS))}",
        )
    merged_disable_stages = DISABLE_STAGES | request_disabled

    new_job_id = str(uuid.uuid4())
    new_job_dir = os.path.join(UPLOAD_DIR, new_job_id)
    os.makedirs(new_job_dir, exist_ok=True)
    file_name = original.file_name or os.path.basename(original.file_path)
    new_step_path = os.path.join(new_job_dir, file_name)
    shutil.copy2(original.file_path, new_step_path)

    with open(new_step_path, "rb") as f:
        file_hash = hashlib.md5(f.read()).hexdigest()
    request_fingerprint = _build_request_fingerprint(file_hash, aag, merged_disable_stages)
    file_size_bytes = os.path.getsize(new_step_path)

    new_job = jobs.create(new_job_id, new_step_path,
                          file_name=file_name,
                          file_hash=file_hash,
                          request_fingerprint=request_fingerprint,
                          file_size_bytes=file_size_bytes)
    background_tasks.add_task(_run_analysis_job, new_job_id, new_step_path, aag, merged_disable_stages)

    return JobCreated(
        job_id=new_job_id,
        status=new_job.status,
        created_at=new_job.created_at,
        archived=False,
        archived_at=None,
    )


@router.post("/jobs/archive-all", response_model=BulkJobActionResult)
async def archive_all_jobs():
    """Archive all jobs."""
    affected = jobs.archive_all()
    return BulkJobActionResult(affected=affected)


@router.get("/jobs/{job_id}/timeline", response_model=JobTimelineResponse)
async def get_job_timeline(job_id: str):
    """Get replay timeline events for a completed job."""
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    timeline_raw, summary_raw = _resolve_job_timeline(job)

    summary = TimelineSummary(**summary_raw) if summary_raw else None
    events = [TimelineEvent(**e) for e in timeline_raw]

    return JobTimelineResponse(
        job_id=job.job_id,
        status=job.status,
        summary=summary,
        events=events,
    )


@router.post("/jobs/{job_id}/unfold", response_model=UnfoldStatus, status_code=202)
async def request_unfold(job_id: str, background_tasks: BackgroundTasks):
    """Queue a server-side unfold job for a completed analysis."""
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != "completed":
        raise HTTPException(status_code=409, detail="Analysis job is not completed yet")
    if not job.file_path or not os.path.exists(job.file_path):
        raise HTTPException(status_code=404, detail="Source STEP file is no longer available")

    current_status = getattr(job, "unfold_status", "idle") or "idle"
    if current_status in {"queued", "processing"}:
        return _build_unfold_status(job)

    jobs.queue_unfold(job_id)
    background_tasks.add_task(_run_unfold_job, job_id)
    return _build_unfold_status(jobs.get(job_id))


@router.get("/jobs/{job_id}/unfold", response_model=UnfoldStatus)
async def get_unfold_status(job_id: str):
    """Get the unfold status and artifact links for a job."""
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return _build_unfold_status(job)


@router.get("/jobs/{job_id}/unfold/artifacts/{artifact_name}")
async def get_unfold_artifact(job_id: str, artifact_name: str):
    """Download unfold artifacts for a completed unfold job."""
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    unfold_result = getattr(job, "unfold_result", None) or {}
    if getattr(job, "unfold_status", "idle") != "completed" or not unfold_result:
        raise HTTPException(status_code=404, detail="Unfold artifact not available")

    artifact_map = {
        "flat-step": (
            unfold_result.get("flat_step_path"),
            f"{Path(job.file_name).stem or 'part'}_flat.step",
            "application/step",
        ),
        "dxf": (
            unfold_result.get("dxf_path") or unfold_result.get("output_dxf"),
            f"{Path(job.file_name).stem or 'part'}_flat.dxf",
            "application/dxf",
        ),
    }
    if artifact_name not in artifact_map:
        raise HTTPException(status_code=404, detail="Unknown artifact")

    artifact_path, download_name, media_type = artifact_map[artifact_name]
    if not artifact_path or not os.path.exists(artifact_path):
        raise HTTPException(status_code=404, detail="Artifact file not found")
    return FileResponse(artifact_path, filename=download_name, media_type=media_type)


@router.get("/jobs/{job_id}/downloads/{bundle_name}")
async def download_job_bundle(job_id: str, bundle_name: str):
    """Download bundled job outputs as a zip or file."""
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != "completed" or not getattr(job, "result", None):
        raise HTTPException(status_code=409, detail="Analysis job is not completed yet")

    if bundle_name == "total-xml":
        return _build_xml_response(_effective_result_dict(job))
    if bundle_name == "part-xmls":
        return _build_part_xml_zip(job)
    if bundle_name == "part-steps":
        return _build_part_step_zip(job)
    if bundle_name == "part-unfolds":
        return _build_part_unfold_zip(job)
    if bundle_name == "unfold-files":
        return _build_unfold_zip(job)

    raise HTTPException(status_code=404, detail="Unknown download bundle")


@router.get("/jobs/{job_id}/step")
async def get_job_step_file(job_id: str):
    """Download the original uploaded STEP file for a job."""
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if not job.file_path or not os.path.exists(job.file_path):
        raise HTTPException(status_code=404, detail="Source STEP file is no longer available")
    return FileResponse(
        job.file_path,
        filename=job.file_name or f"{job_id}.step",
        media_type="application/step",
    )


@router.get("/jobs/{job_id}/parts/{part_index}")
async def get_job_part(job_id: str, part_index: int):
    """Get a single embedded assembly part result."""
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != "completed" or not getattr(job, "result", None):
        raise HTTPException(status_code=409, detail="Analysis job is not completed yet")
    part = _get_job_part(job, part_index)
    return {
        "job_id": job.job_id,
        "part_index": part_index,
        "source_step_available": bool(job.file_path and os.path.exists(job.file_path)),
        "result": part,
    }


@router.get("/jobs/{job_id}/parts/{part_index}/step")
async def get_job_part_step_file(job_id: str, part_index: int):
    """Download a single part STEP extracted from an assembly job."""
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != "completed" or not getattr(job, "result", None):
        raise HTTPException(status_code=409, detail="Analysis job is not completed yet")
    part, step_path = _ensure_part_step_file(job, part_index)
    return FileResponse(
        step_path,
        filename=_part_step_filename(part, part_index),
        media_type="application/step",
    )


@router.get("/jobs/{job_id}/parts/{part_index}/unfold", response_model=UnfoldStatus)
async def get_job_part_unfold_status(job_id: str, part_index: int):
    """Build or return unfold results for a single assembly part."""
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != "completed" or not getattr(job, "result", None):
        raise HTTPException(status_code=409, detail="Analysis job is not completed yet")

    payload = _ensure_part_unfold_result(job, part_index)
    return UnfoldStatus(status="completed", result=UnfoldResult(**payload))


@router.get("/jobs/{job_id}/parts/{part_index}/unfold/artifacts/{artifact_name}")
async def get_job_part_unfold_artifact(job_id: str, part_index: int, artifact_name: str):
    """Download unfold artifacts for a single assembly part."""
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != "completed" or not getattr(job, "result", None):
        raise HTTPException(status_code=409, detail="Analysis job is not completed yet")

    payload = _ensure_part_unfold_result(job, part_index)
    artifact_map = {
        "flat-step": (
            payload.get("flat_step_path"),
            f"{_part_download_stem(_get_job_part(job, part_index), part_index)}_flat.step",
            "application/step",
        ),
        "dxf": (
            payload.get("dxf_path") or payload.get("output_dxf"),
            f"{_part_download_stem(_get_job_part(job, part_index), part_index)}_flat.dxf",
            "application/dxf",
        ),
    }
    if artifact_name not in artifact_map:
        raise HTTPException(status_code=404, detail="Unknown artifact")
    artifact_path, download_name, media_type = artifact_map[artifact_name]
    if not artifact_path or not os.path.exists(artifact_path):
        raise HTTPException(status_code=404, detail="Artifact file not found")
    return FileResponse(artifact_path, filename=download_name, media_type=media_type)


@router.get("/health", response_model=HealthResponse)
async def health():
    """Health check endpoint."""
    return HealthResponse()


@router.get("/debug/logs", response_class=PlainTextResponse)
async def debug_logs(n: int = Query(200, ge=1, le=500)):
    """Return the last N server log lines. Requires API key."""
    lines = list(_LOG_BUFFER)[-n:]
    return "\n".join(lines) if lines else "(no logs yet)"


@router.get("/viewer/default-step")
async def get_viewer_default_step():
    """Serve a repo-relative default STEP file for the viewer demo button."""
    if not DEFAULT_VIEWER_STEP.exists():
        raise HTTPException(status_code=404, detail="Default viewer STEP file not found")
    return FileResponse(
        DEFAULT_VIEWER_STEP,
        filename=DEFAULT_VIEWER_STEP.name,
        media_type="application/step",
    )


@router.get("/stats", response_model=JobStats)
async def stats():
    """Get aggregated job statistics."""
    data = jobs.get_stats()
    return JobStats(**data)


def _result_to_csv(result: dict) -> str:
    """Convert analysis result dict to CSV string response."""
    from fastapi.responses import Response

    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")

    dims = result.get("dimensions", {})
    flat = result.get("flat_dimensions") or {}
    prod = result.get("production", {})

    # Header
    writer.writerow([
        "file", "success", "category", "part_type", "thickness",
        "length", "width", "height",
        "flat_length", "flat_width",
        "holes_total", "bends_total", "bends_up", "bends_down",
    ])

    # Data
    writer.writerow([
        result.get("file", ""),
        result.get("success", False),
        result.get("category", ""),
        result.get("part_type", ""),
        result.get("thickness", ""),
        dims.get("length", ""),
        dims.get("width", ""),
        dims.get("height", ""),
        flat.get("length", ""),
        flat.get("width", ""),
        prod.get("holes_total", ""),
        prod.get("bends_total", ""),
        prod.get("bends_up", ""),
        prod.get("bends_down", ""),
    ])

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={result.get('file', 'result')}.csv"},
    )


def _result_to_xml(result: dict) -> str:
    """Convert analysis result dict to XML string response."""
    return _build_xml_response(result)
