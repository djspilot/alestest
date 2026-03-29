from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Sequence

import numpy as np
from shapely import affinity
from shapely.geometry import MultiPolygon, Point, Polygon


@dataclass(slots=True)
class AxisCandidate:
    direction: np.ndarray
    origin: np.ndarray
    source: str
    score: float = float("-inf")
    metrics: dict[str, float] = field(default_factory=dict)


@dataclass(slots=True)
class Section2D:
    polygon: Polygon
    origin_3d: np.ndarray
    normal_3d: np.ndarray
    basis_u: np.ndarray
    basis_v: np.ndarray
    source_position: float
    line_length_fraction: float
    curve_length_fraction: float
    wire_polygons: tuple[Polygon, ...] = field(default_factory=tuple)


@dataclass(slots=True)
class SectionFeatures:
    area: float
    perimeter: float
    compactness: float
    convexity: float
    bbox_ratio: float
    bbox_fill: float
    holes: int
    symmetry_angles_deg: tuple[float, ...]
    symmetry_scores: tuple[float, ...]
    reentrant_corners: int
    line_length_fraction: float
    curve_length_fraction: float


@dataclass(slots=True)
class TemplateMatch:
    family: str
    variant: str
    score: float
    details: dict[str, float] = field(default_factory=dict)


@dataclass(slots=True)
class ProfileTemplate:
    family: str
    variant: str
    polygon: Polygon
    meta: dict[str, float] = field(default_factory=dict)


def normalize(v: Sequence[float], eps: float = 1e-12) -> np.ndarray:
    arr = np.asarray(v, dtype=float)
    norm = float(np.linalg.norm(arr))
    if norm < eps:
        raise ValueError("cannot normalize near-zero vector")
    return arr / norm


def unique_rows_rounded(points: np.ndarray, tol: float = 1e-8) -> np.ndarray:
    if len(points) == 0:
        return points
    scale = max(tol, 1e-12)
    quantized = np.round(points / scale).astype(np.int64)
    _, idx = np.unique(quantized, axis=0, return_index=True)
    return points[np.sort(idx)]


def orthonormal_basis_from_normal(n: Sequence[float]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    n = normalize(n)
    ref = np.array([1.0, 0.0, 0.0]) if abs(float(np.dot(n, [1.0, 0.0, 0.0]))) < 0.9 else np.array([0.0, 1.0, 0.0])
    u = normalize(np.cross(n, ref))
    v = normalize(np.cross(n, u))
    return n, u, v


def project_points_to_plane(points_3d: np.ndarray, origin: np.ndarray, u: np.ndarray, v: np.ndarray) -> np.ndarray:
    rel = np.asarray(points_3d, dtype=float) - origin[None, :]
    x = rel @ u
    y = rel @ v
    return np.column_stack([x, y])


def polygon_signed_area(coords: np.ndarray) -> float:
    xy = np.asarray(coords, dtype=float)
    x0 = xy[:, 0]
    y0 = xy[:, 1]
    x1 = np.roll(x0, -1)
    y1 = np.roll(y0, -1)
    return 0.5 * float(np.sum(x0 * y1 - x1 * y0))


def simplify_relative(poly: Polygon, rel_tol: float = 0.003) -> Polygon:
    if poly.is_empty:
        return poly
    minx, miny, maxx, maxy = poly.bounds
    scale = max(maxx - minx, maxy - miny)
    tol = max(rel_tol * scale, 1e-9)
    out = poly.simplify(tol, preserve_topology=True)
    if not out.is_valid:
        out = out.buffer(0)
    if isinstance(out, MultiPolygon):
        out = max(out.geoms, key=lambda g: g.area)
    return out


def normalize_section_polygon(poly: Polygon) -> Polygon:
    poly = poly.buffer(0) if not poly.is_valid else poly
    if isinstance(poly, MultiPolygon):
        poly = max(poly.geoms, key=lambda g: g.area)

    centroid = poly.centroid
    normalized = affinity.translate(poly, xoff=-centroid.x, yoff=-centroid.y)

    xy = np.asarray(normalized.exterior.coords[:-1], dtype=float)
    if len(xy) >= 3:
        cov = np.cov(xy, rowvar=False)
        evals, evecs = np.linalg.eigh(cov)
        axis = evecs[:, int(np.argmax(evals))]
        angle = math.degrees(math.atan2(axis[1], axis[0]))
        normalized = affinity.rotate(normalized, -angle, origin=(0, 0))

    mirrored = affinity.scale(normalized, xfact=-1, yfact=1, origin=(0, 0))
    if mirrored.bounds < normalized.bounds:
        normalized = mirrored

    if normalized.area <= 0:
        return normalized
    scale = math.sqrt(normalized.area)
    normalized = affinity.scale(normalized, xfact=1.0 / scale, yfact=1.0 / scale, origin=(0, 0))
    return normalized


def section_distance(a: Polygon, b: Polygon) -> float:
    a = normalize_section_polygon(a)
    b = normalize_section_polygon(b)
    hausdorff = float(a.hausdorff_distance(b))
    symmetric_diff = float(a.symmetric_difference(b).area)
    return 0.7 * hausdorff + 0.3 * symmetric_diff


def count_reentrant_corners(poly: Polygon, rel_tol: float = 0.004) -> int:
    simplified = simplify_relative(poly, rel_tol=rel_tol)
    ring = np.asarray(simplified.exterior.coords[:-1], dtype=float)
    if len(ring) < 4:
        return 0

    if polygon_signed_area(ring) < 0:
        ring = ring[::-1]

    count = 0
    for idx in range(len(ring)):
        a = ring[idx - 1]
        b = ring[idx]
        c = ring[(idx + 1) % len(ring)]
        v1 = a - b
        v2 = c - b
        cross = float((v1[0] * v2[1]) - (v1[1] * v2[0]))
        if cross > 0:
            count += 1
    return count


def reflect_polygon_about_axis(poly: Polygon, angle_deg: float) -> Polygon:
    centered = affinity.translate(poly, xoff=-poly.centroid.x, yoff=-poly.centroid.y)
    rotated = affinity.rotate(centered, -angle_deg, origin=(0, 0))
    reflected = affinity.scale(rotated, xfact=1.0, yfact=-1.0, origin=(0, 0))
    return affinity.rotate(reflected, angle_deg, origin=(0, 0))


def symmetry_score(poly: Polygon, axis_angle_deg: float) -> float:
    reflected = reflect_polygon_about_axis(poly, axis_angle_deg)
    try:
        union = poly.union(reflected)
        intersection = poly.intersection(reflected)
    except Exception:
        return 0.0
    if union.area <= 0:
        return 0.0
    return float(intersection.area / union.area)


def detect_symmetry_axes(poly: Polygon, angle_step_deg: float = 2.5, min_score: float = 0.985) -> tuple[tuple[float, ...], tuple[float, ...]]:
    normalized = normalize_section_polygon(poly)
    angles = np.arange(0.0, 180.0, angle_step_deg)
    scored = [(float(angle), symmetry_score(normalized, float(angle))) for angle in angles]
    passed = [(angle, score) for angle, score in scored if score >= min_score]
    if not passed:
        best = sorted(scored, key=lambda item: item[1], reverse=True)[:2]
        return tuple(angle for angle, _ in best), tuple(score for _, score in best)

    merged: list[tuple[float, float]] = []
    current: list[tuple[float, float]] = [passed[0]]
    for item in passed[1:]:
        if item[0] - current[-1][0] <= 1.5 * angle_step_deg:
            current.append(item)
        else:
            merged.append((float(np.mean([angle for angle, _ in current])), float(max(score for _, score in current))))
            current = [item]
    merged.append((float(np.mean([angle for angle, _ in current])), float(max(score for _, score in current))))
    return tuple(angle for angle, _ in merged), tuple(score for _, score in merged)


def extract_section_features(section: Section2D) -> SectionFeatures:
    poly = section.polygon
    area = float(poly.area)
    perimeter = float(poly.length)
    compactness = float(4.0 * math.pi * area / max(perimeter * perimeter, 1e-12))
    convexity = float(area / max(poly.convex_hull.area, 1e-12))

    mrr = poly.minimum_rotated_rectangle
    mrr_xy = np.asarray(mrr.exterior.coords[:-1], dtype=float)
    edges = np.linalg.norm(np.diff(np.vstack([mrr_xy, mrr_xy[0]]), axis=0), axis=1)
    height = float(np.max(edges)) if len(edges) else 0.0
    width = float(np.min(edges)) if len(edges) else height
    bbox_ratio = min(height, width) / max(height, width, 1e-12)
    bbox_fill = float(area / max(mrr.area, 1e-12))

    sym_angles, sym_scores = detect_symmetry_axes(poly)
    reentrant = count_reentrant_corners(poly)

    return SectionFeatures(
        area=area,
        perimeter=perimeter,
        compactness=compactness,
        convexity=convexity,
        bbox_ratio=bbox_ratio,
        bbox_fill=bbox_fill,
        holes=len(poly.interiors),
        symmetry_angles_deg=sym_angles,
        symmetry_scores=sym_scores,
        reentrant_corners=reentrant,
        line_length_fraction=section.line_length_fraction,
        curve_length_fraction=section.curve_length_fraction,
    )


def _center_scale_polygon(poly: Polygon) -> Polygon:
    return normalize_section_polygon(poly)


def make_round_bar(radius: float = 0.5, resolution: int = 64) -> Polygon:
    return _center_scale_polygon(Point(0, 0).buffer(radius, resolution=resolution))


def make_pipe(outer_radius: float = 0.5, thickness: float = 0.1, resolution: int = 64) -> Polygon:
    outer = Point(0, 0).buffer(outer_radius, resolution=resolution)
    inner = Point(0, 0).buffer(max(outer_radius - thickness, 1e-6), resolution=resolution)
    return _center_scale_polygon(outer.difference(inner))


def make_flat_bar(width: float = 1.0, thickness: float = 0.2) -> Polygon:
    half_width, half_thickness = width / 2.0, thickness / 2.0
    return _center_scale_polygon(Polygon([(-half_width, -half_thickness), (half_width, -half_thickness), (half_width, half_thickness), (-half_width, half_thickness)]))


def make_rectangular_tube(width: float = 1.0, height: float = 0.6, thickness: float = 0.08) -> Polygon:
    outer_width, outer_height = width / 2.0, height / 2.0
    inner_width = max(outer_width - thickness, 1e-6)
    inner_height = max(outer_height - thickness, 1e-6)
    outer = Polygon([(-outer_width, -outer_height), (outer_width, -outer_height), (outer_width, outer_height), (-outer_width, outer_height)])
    inner = Polygon([(-inner_width, -inner_height), (inner_width, -inner_height), (inner_width, inner_height), (-inner_width, inner_height)])
    return _center_scale_polygon(outer.difference(inner))


def make_i_section(h: float = 1.0, b: float = 0.55, tw: float = 0.08, tf: float = 0.12) -> Polygon:
    half_height, half_width = h / 2.0, b / 2.0
    half_web, flange = tw / 2.0, tf
    coords = [
        (-half_width, half_height), (half_width, half_height), (half_width, half_height - flange), (half_web, half_height - flange),
        (half_web, -half_height + flange), (half_width, -half_height + flange), (half_width, -half_height), (-half_width, -half_height),
        (-half_width, -half_height + flange), (-half_web, -half_height + flange), (-half_web, half_height - flange), (-half_width, half_height - flange),
    ]
    return _center_scale_polygon(Polygon(coords))


def make_u_section(h: float = 1.0, b: float = 0.45, tw: float = 0.08, tf: float = 0.12) -> Polygon:
    half_height, half_width = h / 2.0, b / 2.0
    coords = [
        (-half_width, half_height), (half_width, half_height), (half_width, half_height - tf), (-half_width + tw, half_height - tf),
        (-half_width + tw, -half_height + tf), (half_width, -half_height + tf), (half_width, -half_height), (-half_width, -half_height),
    ]
    return _center_scale_polygon(Polygon(coords))


def make_l_section(a: float = 1.0, b: float = 0.7, t: float = 0.12) -> Polygon:
    poly = Polygon([(0, 0), (a, 0), (a, t), (t, t), (t, b), (0, b)])
    centered = affinity.translate(poly, xoff=-poly.centroid.x, yoff=-poly.centroid.y)
    return _center_scale_polygon(centered)


def make_t_section(h: float = 1.0, b: float = 0.7, tw: float = 0.10, tf: float = 0.16) -> Polygon:
    half_height, half_width = h / 2.0, b / 2.0
    half_web = tw / 2.0
    coords = [
        (-half_width, half_height), (half_width, half_height), (half_width, half_height - tf), (half_web, half_height - tf),
        (half_web, -half_height), (-half_web, -half_height), (-half_web, half_height - tf), (-half_width, half_height - tf),
    ]
    return _center_scale_polygon(Polygon(coords))


class ProfileRegistry:
    def __init__(self) -> None:
        self.templates: list[ProfileTemplate] = []

    def add(self, family: str, variant: str, polygon: Polygon, **meta: float) -> None:
        self.templates.append(ProfileTemplate(family=family, variant=variant, polygon=normalize_section_polygon(polygon), meta=meta))

    def extend_generic_defaults(self) -> "ProfileRegistry":
        self.add("ROUND_BAR", "round-bar", make_round_bar())
        self.add("PIPE", "pipe-t0.1", make_pipe(thickness=0.10))
        self.add("PIPE", "pipe-t0.2", make_pipe(thickness=0.20))
        self.add("FLAT_BAR", "flat-5x1", make_flat_bar(1.0, 0.20))
        self.add("FLAT_BAR", "flat-4x1", make_flat_bar(1.0, 0.25))
        self.add("RECT_TUBE", "rhs-1", make_rectangular_tube(1.0, 0.60, 0.08))
        self.add("RECT_TUBE", "rhs-2", make_rectangular_tube(1.0, 0.80, 0.10))

        for b in (0.45, 0.55, 0.75):
            for tw in (0.06, 0.08, 0.10):
                for tf in (0.10, 0.14, 0.18):
                    self.add("I_FAMILY", f"i-b{b:.2f}-tw{tw:.2f}-tf{tf:.2f}", make_i_section(1.0, b, tw, tf), b=b, tw=tw, tf=tf)
        for b in (0.35, 0.45, 0.60):
            for tw in (0.06, 0.08, 0.10):
                for tf in (0.10, 0.14, 0.18):
                    self.add("U_FAMILY", f"u-b{b:.2f}-tw{tw:.2f}-tf{tf:.2f}", make_u_section(1.0, b, tw, tf), b=b, tw=tw, tf=tf)
        for b in (0.5, 0.7, 1.0):
            for t in (0.08, 0.12, 0.18):
                self.add("L_FAMILY", f"l-b{b:.2f}-t{t:.2f}", make_l_section(1.0, b, t), b=b, t=t)
        for b in (0.45, 0.70, 1.0):
            for tw in (0.06, 0.10, 0.14):
                for tf in (0.10, 0.16, 0.22):
                    self.add("T_FAMILY", f"t-b{b:.2f}-tw{tw:.2f}-tf{tf:.2f}", make_t_section(1.0, b, tw, tf), b=b, tw=tw, tf=tf)
        return self


def match_templates(poly: Polygon, registry: ProfileRegistry, top_k: int = 5) -> list[TemplateMatch]:
    query = normalize_section_polygon(poly)
    variants: list[TemplateMatch] = []
    for template in registry.templates:
        best = float("inf")
        for rotation in (0.0, 90.0, 180.0, 270.0):
            rotated = affinity.rotate(template.polygon, rotation, origin=(0, 0))
            best = min(best, section_distance(query, rotated))
            mirrored = affinity.scale(rotated, xfact=-1.0, yfact=1.0, origin=(0, 0))
            best = min(best, section_distance(query, mirrored))
        variants.append(TemplateMatch(family=template.family, variant=template.variant, score=best, details=dict(template.meta)))
    variants.sort(key=lambda item: item.score)
    return variants[:top_k]
