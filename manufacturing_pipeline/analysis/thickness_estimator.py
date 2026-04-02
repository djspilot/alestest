from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence


def _bucket_thickness(value_mm: float, resolution_mm: float = 0.5) -> float:
    return round(float(value_mm) / resolution_mm) * resolution_mm


def _normalize(vector: Sequence[float]) -> tuple[float, float, float]:
    x, y, z = (float(vector[0]), float(vector[1]), float(vector[2]))
    norm = math.sqrt(x * x + y * y + z * z)
    if norm <= 1e-12:
        raise ValueError("cannot normalize near-zero vector")
    return (x / norm, y / norm, z / norm)


def _canonical_axis(direction: Sequence[float]) -> tuple[float, float, float]:
    nx, ny, nz = _normalize(direction)
    if nx < -1e-9 or (abs(nx) <= 1e-9 and ny < -1e-9) or (abs(nx) <= 1e-9 and abs(ny) <= 1e-9 and nz < -1e-9):
        return (-nx, -ny, -nz)
    return (nx, ny, nz)


def _dot(a: Sequence[float], b: Sequence[float]) -> float:
    return float(a[0] * b[0] + a[1] * b[1] + a[2] * b[2])


def _cross(a: Sequence[float], b: Sequence[float]) -> tuple[float, float, float]:
    return (
        float(a[1] * b[2] - a[2] * b[1]),
        float(a[2] * b[0] - a[0] * b[2]),
        float(a[0] * b[1] - a[1] * b[0]),
    )


def _norm(vector: Sequence[float]) -> float:
    return math.sqrt(float(vector[0] * vector[0] + vector[1] * vector[1] + vector[2] * vector[2]))


def _axis_line_distance(point_a: Sequence[float], direction: Sequence[float], point_b: Sequence[float]) -> float:
    delta = (
        float(point_b[0] - point_a[0]),
        float(point_b[1] - point_a[1]),
        float(point_b[2] - point_a[2]),
    )
    return _norm(_cross(delta, direction))


@dataclass(frozen=True, slots=True)
class ThicknessCandidate:
    method: str
    thickness_mm: float
    confidence: float
    vote_weight: float
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ThicknessEstimate:
    thickness_mm: float
    method: str
    confidence: float
    candidates: tuple[ThicknessCandidate, ...] = field(default_factory=tuple)
    bucket_votes: dict[float, float] = field(default_factory=dict)

    def should_override(self, current_mm: float, tolerance_mm: float = 0.25, ratio_threshold: float = 1.35) -> bool:
        current_mm = float(current_mm or 0.0)
        if self.thickness_mm <= 0:
            return False
        if current_mm <= 0:
            return True
        if abs(self.thickness_mm - current_mm) <= tolerance_mm:
            return False
        if self.confidence >= 0.75 and self.thickness_mm >= current_mm * ratio_threshold:
            return True
        return self.confidence >= 0.9


def select_best_thickness_candidate(
    candidates: Iterable[ThicknessCandidate],
    resolution_mm: float = 0.5,
) -> tuple[float, ThicknessCandidate | None, dict[float, float]]:
    candidate_list = [candidate for candidate in candidates if candidate.thickness_mm > 0]
    if not candidate_list:
        return 0.0, None, {}

    bucket_votes: dict[float, float] = defaultdict(float)
    for candidate in candidate_list:
        bucket = _bucket_thickness(candidate.thickness_mm, resolution_mm)
        bucket_votes[bucket] += float(candidate.vote_weight)

    best_bucket = max(bucket_votes.items(), key=lambda item: (item[1], item[0]))[0]
    bucket_candidates = [
        candidate
        for candidate in candidate_list
        if abs(_bucket_thickness(candidate.thickness_mm, resolution_mm) - best_bucket) <= 1e-9
    ]
    best_candidate = max(
        bucket_candidates,
        key=lambda candidate: (
            candidate.confidence,
            candidate.vote_weight,
            -abs(candidate.thickness_mm - best_bucket),
        ),
    )
    return best_bucket, best_candidate, dict(bucket_votes)


def _estimate_planar_opposites(planar_faces: Sequence[tuple[Any, float]], total_area: float) -> ThicknessCandidate | None:
    if len(planar_faces) < 2:
        return None

    from OCP.BRepAdaptor import BRepAdaptor_Surface

    plane_props = []
    for face, area in planar_faces:
        surf = BRepAdaptor_Surface(face, True)
        plane = surf.Plane()
        direction = plane.Axis().Direction()
        location = plane.Location()
        nx, ny, nz = _canonical_axis((direction.X(), direction.Y(), direction.Z()))
        d = -(nx * location.X() + ny * location.Y() + nz * location.Z())
        plane_props.append((nx, ny, nz, d, float(area)))

    support_by_thickness: dict[float, float] = defaultdict(float)
    for index, (n1x, n1y, n1z, d1, area1) in enumerate(plane_props):
        for n2x, n2y, n2z, d2, area2 in plane_props[index + 1 :]:
            if abs(_dot((n1x, n1y, n1z), (n2x, n2y, n2z)) + 1.0) > 0.01:
                continue
            thickness = abs(d1 + d2)
            if 0.1 < thickness < 25.0:
                support_by_thickness[_bucket_thickness(thickness, 0.1)] += min(area1, area2)

    if not support_by_thickness:
        return None

    thickness_mm, support_area = max(support_by_thickness.items(), key=lambda item: (item[1], item[0]))
    support_ratio = (support_area * 2.0 / total_area) if total_area > 0 else 0.0
    confidence = min(0.88, 0.55 + min(0.28, support_ratio * 2.5))
    vote_weight = 0.7 + support_ratio * 4.0
    return ThicknessCandidate(
        method="planar_opposites",
        thickness_mm=float(thickness_mm),
        confidence=float(confidence),
        vote_weight=float(vote_weight),
        details={"support_area": support_area, "support_ratio": support_ratio},
    )


def _estimate_cylindrical_pairs(cylindrical_faces: Sequence[tuple[Any, float, Any]], total_area: float) -> ThicknessCandidate | None:
    if len(cylindrical_faces) < 2:
        return None

    cylinders = []
    for face, area, surf in cylindrical_faces:
        cylinder = surf.Cylinder()
        axis = cylinder.Axis()
        direction = _canonical_axis((axis.Direction().X(), axis.Direction().Y(), axis.Direction().Z()))
        location = axis.Location()
        cylinders.append(
            {
                "direction": direction,
                "point": (float(location.X()), float(location.Y()), float(location.Z())),
                "radius": float(cylinder.Radius()),
                "area": float(area),
            }
        )

    support_by_thickness: dict[float, float] = defaultdict(float)
    for index, first in enumerate(cylinders):
        for second in cylinders[index + 1 :]:
            if _dot(first["direction"], second["direction"]) < 0.995:
                continue
            if _axis_line_distance(first["point"], first["direction"], second["point"]) > 0.5:
                continue
            delta_radius = abs(first["radius"] - second["radius"])
            if 0.3 < delta_radius < 25.0:
                support_by_thickness[_bucket_thickness(delta_radius, 0.1)] += min(first["area"], second["area"])

    if not support_by_thickness:
        return None

    thickness_mm, support_area = max(support_by_thickness.items(), key=lambda item: (item[1], item[0]))
    support_ratio = (support_area * 2.0 / total_area) if total_area > 0 else 0.0
    confidence = min(0.94, 0.72 + min(0.18, support_ratio * 3.0))
    vote_weight = 1.2 + support_ratio * 5.0
    return ThicknessCandidate(
        method="cylindrical_pairs",
        thickness_mm=float(thickness_mm),
        confidence=float(confidence),
        vote_weight=float(vote_weight),
        details={"support_area": support_area, "support_ratio": support_ratio},
    )


def _estimate_volume_planar_area(solid: Any, planar_faces: Sequence[tuple[Any, float]]) -> ThicknessCandidate | None:
    if not planar_faces:
        return None

    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(solid, props)
    volume = float(props.Mass())
    top_area = max(float(area) for _, area in planar_faces)
    if volume <= 0 or top_area <= 0:
        return None

    estimated = volume / top_area
    if not 0.3 <= estimated <= 25.0:
        return None

    thickness_mm = _bucket_thickness(estimated, 0.5)
    return ThicknessCandidate(
        method="volume_planar_area",
        thickness_mm=float(thickness_mm),
        confidence=0.28,
        vote_weight=0.25,
        details={"volume": volume, "top_area": top_area, "estimated": estimated},
    )


def _estimate_bbox_min_dim(bbox_dims: Sequence[float], cylindrical_area: float) -> ThicknessCandidate | None:
    if not bbox_dims:
        return None
    smallest = float(min(bbox_dims))
    if not 0.3 <= smallest <= 25.0:
        return None
    confidence = 0.42 if cylindrical_area > 0 else 0.22
    vote_weight = 0.45 if cylindrical_area > 0 else 0.2
    return ThicknessCandidate(
        method="bbox_min_dim",
        thickness_mm=smallest,
        confidence=confidence,
        vote_weight=vote_weight,
        details={"smallest_dimension": smallest},
    )


def estimate_sheet_thickness(
    solid: Any,
    *,
    planar_faces: Sequence[tuple[Any, float]] | None = None,
    cylindrical_faces: Sequence[tuple[Any, float, Any]] | None = None,
    bbox_dims: Sequence[float] | None = None,
    total_area: float | None = None,
) -> ThicknessEstimate:
    candidates: list[ThicknessCandidate] = []

    planar_faces = list(planar_faces or [])
    cylindrical_faces = list(cylindrical_faces or [])

    if total_area is None:
        total_area = 0.0
        for _, area in planar_faces:
            total_area += float(area)
        for _, area, _ in cylindrical_faces:
            total_area += float(area)

    planar_candidate = _estimate_planar_opposites(planar_faces, float(total_area))
    if planar_candidate is not None:
        candidates.append(planar_candidate)

    cylinder_candidate = _estimate_cylindrical_pairs(cylindrical_faces, float(total_area))
    if cylinder_candidate is not None:
        candidates.append(cylinder_candidate)

    volume_candidate = _estimate_volume_planar_area(solid, planar_faces)
    if volume_candidate is not None:
        candidates.append(volume_candidate)

    if bbox_dims:
        bbox_candidate = _estimate_bbox_min_dim(bbox_dims, sum(float(area) for _, area, _ in cylindrical_faces))
        if bbox_candidate is not None:
            candidates.append(bbox_candidate)

    bucket_mm, selected_candidate, bucket_votes = select_best_thickness_candidate(candidates)
    if selected_candidate is None:
        return ThicknessEstimate(thickness_mm=0.0, method="none", confidence=0.0, candidates=tuple(), bucket_votes={})

    return ThicknessEstimate(
        thickness_mm=float(bucket_mm),
        method=selected_candidate.method,
        confidence=float(selected_candidate.confidence),
        candidates=tuple(candidates),
        bucket_votes=bucket_votes,
    )