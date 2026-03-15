"""Dataclasses for pipeline output — JSON-serializable."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class SectionResult:
    """One cross-section at a specific position along the extrusion axis."""
    position_frac: float
    position_abs: float
    plane_origin: list[float]
    plane_normal: list[float]
    polygon: dict | None = None       # {"outer": [[x,y],...], "holes": [...]}
    features: dict | None = None      # SectionFeatures as dict
    is_valid: bool = False


@dataclass
class ClassificationResult:
    """Profile classification output."""
    label: str                         # e.g. "ROND_STAAL", "I_FAMILY", "ANDERS"
    method: str                        # "rule", "template", "template-fallback"
    variant: str | None = None         # e.g. "i-b0.55-tw0.08-tf0.14"
    top_matches: list[dict] | None = None


@dataclass
class SolidResult:
    """Complete analysis result for one solid."""
    name: str
    instance_id: str
    units: str | None

    # Geometry
    axis_direction: list[float]
    axis_origin: list[float]
    axis_source: str
    axis_score: float
    bounding_box_min: list[float]
    bounding_box_max: list[float]

    # Classification
    classification: ClassificationResult

    # Sections
    sections: list[SectionResult] = field(default_factory=list)
    core_section: SectionResult | None = None
    cluster_size: int = 0
    sections_total: int = 0

    # Optional 3D vertices
    vertices_3d: list[list[float]] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to a plain dict for JSON serialization."""
        d = asdict(self)
        # Remove None values for cleaner output
        return {k: v for k, v in d.items() if v is not None}
