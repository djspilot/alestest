"""API route definitions."""

import csv
import collections
import hashlib
import json
import io
import logging
import os
import uuid
import zipfile
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse, Response

from manufacturing_pipeline.api.config import ALLOWED_EXTENSIONS, DISABLE_STAGES, MAX_FILE_SIZE_MB, UPLOAD_DIR, VALID_STAGE_KEYS
from manufacturing_pipeline.api.schemas import (
    AnalysisResult,
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
from manufacturing_pipeline.api.analysis_service import run_step_analysis
from manufacturing_pipeline.core.runtime_unfold import run_unfold_to_step
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
    jobs.mark_processing(job_id)
    try:
        result = run_step_analysis(
            step_path,
            use_aag=use_aag,
            progress_callback=lambda event, summary: jobs.record_progress(job_id, event, summary),
            disable_stages=disable_stages,
        )
        jobs.mark_completed(job_id, result)
    except Exception as e:
        jobs.mark_failed(job_id, str(e))


def _build_unfold_result(job_id: str, result: dict | None, error: str | None = None) -> dict | None:
    if not result and not error:
        return None

    payload = dict(result or {})
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
    return payload


def _build_unfold_status(job) -> UnfoldStatus:
    unfold_payload = _build_unfold_result(job.job_id, getattr(job, "unfold_result", None), getattr(job, "unfold_error", None))
    return UnfoldStatus(
        status=getattr(job, "unfold_status", "idle") or "idle",
        requested_at=getattr(job, "unfold_requested_at", None),
        started_at=getattr(job, "unfold_started_at", None),
        completed_at=getattr(job, "unfold_completed_at", None),
        error=getattr(job, "unfold_error", None),
        result=UnfoldResult(**unfold_payload) if unfold_payload else None,
    )


def _source_step_available(job) -> bool:
    return bool(getattr(job, "file_path", None)) and os.path.exists(job.file_path)


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
    result = getattr(job, "result", None) or {}
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
    reusable_job = jobs.find_reusable_job(request_fingerprint)
    if reusable_job:
        return JobCreated(
            job_id=reusable_job.job_id,
            status=reusable_job.status,
            reused_existing=True,
            created_at=reusable_job.created_at,
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

    return JobCreated(job_id=job_id, status=job.status, created_at=job.created_at)


@router.get("/jobs", response_model=JobListResponse)
async def list_jobs(
    limit: int = Query(20, ge=1, le=100, description="Items per page"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    status: str = Query(None, description="Filter by status: queued, processing, completed, failed"),
):
    """List all analysis jobs (paginated)."""
    items, total = jobs.list_jobs(limit=limit, offset=offset, status=status)
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
        return _result_to_csv(job.result)

    if format == "xml" and job.status == "completed" and job.result:
        return _build_xml_response(job.result)


    if job.status == "completed":
        timeline_raw = (job.result or {}).get("timeline") or []
        summary_raw = (job.result or {}).get("timeline_summary")
    else:
        timeline_raw = getattr(job, "progress_events", None) or []
        summary_raw = _refresh_live_summary(getattr(job, "progress_summary", None))

    response = JobStatus(
        job_id=job.job_id,
        status=job.status,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        source_step_available=_source_step_available(job),
        timeline_summary=TimelineSummary(**summary_raw) if summary_raw else None,
        timeline_events=[TimelineEvent(**e) for e in timeline_raw],
        error=job.error,
        unfold=_build_unfold_status(job),
    )

    if job.status == "completed" and job.result:
        response.result = AnalysisResult(**job.result)

    return response


@router.get("/jobs/{job_id}/timeline", response_model=JobTimelineResponse)
async def get_job_timeline(job_id: str):
    """Get replay timeline events for a completed job."""
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.status == "completed":
        timeline_raw = (job.result or {}).get("timeline") or []
        summary_raw = (job.result or {}).get("timeline_summary")
    else:
        timeline_raw = getattr(job, "progress_events", None) or []
        summary_raw = _refresh_live_summary(getattr(job, "progress_summary", None))

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
        return _build_xml_response(job.result)
    if bundle_name == "part-xmls":
        return _build_part_xml_zip(job)
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
