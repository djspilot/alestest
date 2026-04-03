"""Pydantic models for API request/response schemas."""

from datetime import datetime
from typing import Optional, Literal
from pydantic import BaseModel, Field


class Dimensions(BaseModel):
    length: float = 0.0
    width: float = 0.0
    height: float = 0.0


class FlatDimensions(BaseModel):
    length: float = 0.0
    width: float = 0.0


class Production(BaseModel):
    holes_total: int = 0
    bends_total: int = 0
    bends_up: int = 0
    bends_down: int = 0


class HoleDetail(BaseModel):
    type: str
    diameter: Optional[float] = None
    perimeter: Optional[float] = None
    isoperimetric_quotient: Optional[float] = None


class BendDetail(BaseModel):
    type: str
    angle: Optional[float] = None
    radius: Optional[float] = None
    length: Optional[float] = None
    k_factor: Optional[float] = None
    bend_allowance: Optional[float] = None
    bend_deduction: Optional[float] = None


class AAGDetails(BaseModel):
    cut_length: Optional[float] = None
    total_cut_length: Optional[float] = None
    pierce_count: Optional[int] = None
    estimated_cut_time_seconds: Optional[float] = None
    face_count: Optional[int] = None
    edge_count: Optional[int] = None
    hole_details: list[HoleDetail] = []
    bend_details: list[BendDetail] = []


class RouteDetails(BaseModel):
    category: Optional[str] = None
    profile_label: Optional[str] = None
    confidence: Optional[float] = None
    method: Optional[str] = None
    variant: Optional[str] = None
    reasoning: Optional[str] = None


class TimelineEvent(BaseModel):
    type: str
    stage: str
    timestamp_ms: int = 0
    status: Optional[str] = None
    payload: dict = Field(default_factory=dict)


class TimelineSummary(BaseModel):
    total_elapsed_seconds: float = 0.0
    event_count: int = 0
    step_count: int = 0
    part_name: Optional[str] = None
    analysis_started_at: Optional[datetime] = None
    active_stage: Optional[str] = None
    active_stage_started_at: Optional[datetime] = None
    active_stage_elapsed_seconds: Optional[float] = None
    completed_step_count: int = 0
    total_steps_hint: int = 0


class MeshData(BaseModel):
    vertices: list[float] = []   # flat [x,y,z, x,y,z, ...]
    indices: list[int] = []      # flat [i0,i1,i2, ...]
    normals: list[float] = []    # flat [nx,ny,nz, ...]
    display_edges: list[float] = []  # flat [x1,y1,z1, x2,y2,z2, ...]


class AnalysisResult(BaseModel):
    file: str
    success: bool
    category: Optional[str] = None
    part_type: Optional[str] = None
    thickness: Optional[float] = None
    dimensions: Optional[Dimensions] = None
    flat_dimensions: Optional[FlatDimensions] = None
    production: Optional[Production] = None
    aag_details: Optional[AAGDetails] = None
    route: Optional[RouteDetails] = None
    timeline_summary: Optional[TimelineSummary] = None
    mesh: Optional[MeshData] = None
    visuals: Optional[dict] = None
    error: Optional[str] = None


class UnfoldResult(BaseModel):
    success: bool
    error: Optional[str] = None
    flat_length: Optional[float] = None
    flat_width: Optional[float] = None
    fold_lines: int = 0
    raw_fold_lines: Optional[int] = None
    bend_line_groups: list[dict] = Field(default_factory=list)
    flat_step_url: Optional[str] = None
    dxf_url: Optional[str] = None


class UnfoldStatus(BaseModel):
    status: Literal["idle", "queued", "processing", "completed", "failed"] = "idle"
    requested_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    result: Optional[UnfoldResult] = None


class JobCreated(BaseModel):
    job_id: str
    status: Literal["queued"] = "queued"
    created_at: datetime


class JobStatus(BaseModel):
    job_id: str
    status: Literal["queued", "processing", "completed", "failed"]
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    timeline_summary: Optional[TimelineSummary] = None
    timeline_events: list[TimelineEvent] = Field(default_factory=list)
    result: Optional[AnalysisResult] = None
    error: Optional[str] = None
    unfold: Optional[UnfoldStatus] = None


class JobTimelineResponse(BaseModel):
    job_id: str
    status: Literal["queued", "processing", "completed", "failed"]
    summary: Optional[TimelineSummary] = None
    events: list[TimelineEvent] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "1.0.0"


class ResultSummary(BaseModel):
    """Compact result summary for job list view."""
    category: Optional[str] = None
    part_type: Optional[str] = None
    thickness: Optional[float] = None
    dimensions: Optional[dict] = None
    production: Optional[dict] = None


class JobListItem(BaseModel):
    """Lightweight job summary for list view (no full result blob)."""
    job_id: str
    file_name: str
    file_hash: Optional[str] = None
    file_size_bytes: Optional[int] = None
    status: str
    created_at: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error: Optional[str] = None
    result: Optional[ResultSummary] = None
    unfold: Optional[UnfoldStatus] = None


class JobListResponse(BaseModel):
    """Paginated job list response."""
    items: list[JobListItem]
    total: int
    limit: int
    offset: int


class JobStats(BaseModel):
    """Aggregated job statistics."""
    total_jobs: int = 0
    jobs_completed: int = 0
    jobs_failed: int = 0
    jobs_queued: int = 0
    jobs_processing: int = 0
    jobs_last_24h: int = 0
