"""Pydantic models for API request/response schemas."""

from datetime import datetime
from typing import Optional, Literal
from pydantic import BaseModel


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
    error: Optional[str] = None


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
    result: Optional[AnalysisResult] = None
    error: Optional[str] = None


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "1.0.0"
