"""API route definitions."""

import csv
import hashlib
import io
import os
import uuid
import shutil
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

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
)
from manufacturing_pipeline.api.job_manager import jobs
from manufacturing_pipeline.api.analysis_service import run_step_analysis
from manufacturing_pipeline.reporting.xml_exporter import export_to_xml
from pathlib import Path
import tempfile

router = APIRouter(prefix="/api/v1")
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
    finally:
        # Cleanup uploaded file
        upload_dir = os.path.dirname(step_path)
        shutil.rmtree(upload_dir, ignore_errors=True)


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

    # Save file to upload directory
    job_id = str(uuid.uuid4())
    job_dir = os.path.join(UPLOAD_DIR, job_id)
    os.makedirs(job_dir, exist_ok=True)

    step_path = os.path.join(job_dir, file.filename or "upload.step")
    with open(step_path, "wb") as f:
        f.write(content)

    # Create job and queue analysis
    file_hash = hashlib.md5(content).hexdigest()
    job = jobs.create(job_id, step_path,
                      file_name=file.filename or "upload.step",
                      file_hash=file_hash,
                      file_size_bytes=len(content))
    background_tasks.add_task(_run_analysis_job, job_id, step_path, aag, merged_disable_stages)

    return JobCreated(job_id=job_id, created_at=job.created_at)


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
        return _result_to_xml(job.result)


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
        timeline_summary=TimelineSummary(**summary_raw) if summary_raw else None,
        timeline_events=[TimelineEvent(**e) for e in timeline_raw],
        error=job.error,
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


@router.get("/health", response_model=HealthResponse)
async def health():
    """Health check endpoint."""
    return HealthResponse()


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
    from fastapi.responses import Response

    # Create temporary file for XML export
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.xml') as tmp:
        tmp_path = Path(tmp.name)

    try:
        # Export to XML using the exporter module
        export_to_xml(result, tmp_path)

        # Read the XML content
        xml_content = tmp_path.read_text(encoding='utf-8')

        # Clean up temp file
        tmp_path.unlink()

        # Return as XML response
        filename = Path(result.get('file', 'result')).stem
        return Response(
            content=xml_content,
            media_type="application/xml",
            headers={"Content-Disposition": f"attachment; filename={filename}.xml"},
        )

    except Exception as e:
        # Clean up temp file on error
        if tmp_path.exists():
            tmp_path.unlink()
        raise HTTPException(status_code=500, detail=f"XML export failed: {str(e)}")
