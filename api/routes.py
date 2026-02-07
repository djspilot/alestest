"""API route definitions."""

import csv
import io
import os
import uuid
import shutil

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, Query, UploadFile

from api.config import ALLOWED_EXTENSIONS, MAX_FILE_SIZE_MB, UPLOAD_DIR
from api.schemas import (
    AnalysisResult,
    HealthResponse,
    JobCreated,
    JobStatus,
)
from api.job_manager import jobs
from api.analysis_service import run_step_analysis

router = APIRouter(prefix="/api/v1")


def _run_analysis_job(job_id: str, step_path: str, use_aag: bool):
    """Background task that runs the analysis and updates job state."""
    jobs.mark_processing(job_id)
    try:
        result = run_step_analysis(step_path, use_aag=use_aag)
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
):
    """Upload a STEP file for manufacturing analysis.

    Returns a job_id that can be polled via GET /jobs/{job_id}.
    """
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
    job = jobs.create(job_id, step_path)
    background_tasks.add_task(_run_analysis_job, job_id, step_path, aag)

    return JobCreated(job_id=job_id, created_at=job.created_at)


@router.get("/jobs/{job_id}")
async def get_job(
    job_id: str,
    format: str = Query("json", description="Response format: json or csv"),
):
    """Get the status and result of an analysis job."""
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if format == "csv" and job.status == "completed" and job.result:
        return _result_to_csv(job.result)

    response = JobStatus(
        job_id=job.job_id,
        status=job.status,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        error=job.error,
    )

    if job.status == "completed" and job.result:
        response.result = AnalysisResult(**job.result)

    return response


@router.get("/health", response_model=HealthResponse)
async def health():
    """Health check endpoint."""
    return HealthResponse()


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
