from __future__ import annotations

import itertools
import math
from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, Sequence

import numpy as np
from shapely import affinity
from shapely.geometry import MultiPolygon, Point, Polygon, LinearRing

from manufacturing_pipeline.analysis.classification_variables import STEP0_CLUSTER_RATIO_MIN
from manufacturing_pipeline.analysis.geometry import profile_sections as shared_profile_sections

try:
    from OCP.BRep import BRep_Tool
    from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Section
    from OCP.BRepGProp import BRepGProp
    from OCP.BRepTools import BRepTools_WireExplorer
    from OCP.GProp import GProp_GProps
    from OCP.GeomAbs import (
        GeomAbs_BSplineCurve,
        GeomAbs_BezierCurve,
        GeomAbs_Circle,
        GeomAbs_Ellipse,
        GeomAbs_Line,
        GeomAbs_Plane,
    )
    from OCP.ShapeAnalysis import ShapeAnalysis_FreeBounds
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_VERTEX, TopAbs_WIRE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopTools import TopTools_HSequenceOfShape
    from OCP.TopoDS import TopoDS
    from OCP.gp import gp_Dir, gp_Pln, gp_Pnt

    _HAS_OCP = True
except ImportError:
    _HAS_OCP = False


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


def _require_ocp() -> None:
    if not _HAS_OCP:
        raise RuntimeError("OCP is required for Step 0 section tools")


def _as_ocp_shape(shape: Any) -> Any:
    """Return underlying OCP shape when a CadQuery wrapper is provided."""
    return shape.wrapped if hasattr(shape, "wrapped") else shape


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


def solid_vertices_np(solid_shape: Any, tol: float = 1e-8) -> np.ndarray:
    _require_ocp()
    solid_shape = _as_ocp_shape(solid_shape)
    pts: list[list[float]] = []
    explorer = TopExp_Explorer(solid_shape, TopAbs_VERTEX)
    while explorer.More():
        vertex = TopoDS.Vertex_s(explorer.Current())
        point = BRep_Tool.Pnt_s(vertex)
        pts.append([point.X(), point.Y(), point.Z()])
        explorer.Next()
    arr = np.asarray(pts, dtype=float)
    return unique_rows_rounded(arr, tol=tol)


def planar_face_normal_candidates(solid_shape: Any, angle_tol_deg: float = 1.0) -> list[np.ndarray]:
    _require_ocp()
    solid_shape = _as_ocp_shape(solid_shape)
    raw: list[tuple[np.ndarray, float]] = []
    explorer = TopExp_Explorer(solid_shape, TopAbs_FACE)
    while explorer.More():
        face = TopoDS.Face_s(explorer.Current())
        surf = BRepAdaptor_Surface(face, True)
        if surf.GetType() == GeomAbs_Plane:
            plane = surf.Plane()
            direction = plane.Axis().Direction()
            normal = normalize([direction.X(), direction.Y(), direction.Z()])
            props = GProp_GProps()
            BRepGProp.SurfaceProperties_s(face, props)
            area = float(props.Mass())
            raw.append((normal, area))
            raw.append((-normal, area))
        explorer.Next()

    if not raw:
        return []

    cos_tol = math.cos(math.radians(angle_tol_deg))
    clusters: list[dict[str, Any]] = []
    for direction, area in raw:
        matched = False
        for cluster in clusters:
            if float(np.dot(direction, cluster["dir"])) >= cos_tol:
                cluster["sum"] += direction * area
                cluster["weight"] += area
                cluster["dir"] = normalize(cluster["sum"])
                matched = True
                break
        if not matched:
            clusters.append({"dir": direction.copy(), "sum": direction * area, "weight": area})

    clusters.sort(key=lambda item: item["weight"], reverse=True)
    return [item["dir"] for item in clusters[:8]]


def pca_axis_candidate(points_3d: np.ndarray) -> np.ndarray:
    pts = np.asarray(points_3d, dtype=float)
    if len(pts) < 3:
        raise ValueError("Need at least 3 points for PCA")
    centered = pts - pts.mean(axis=0, keepdims=True)
    cov = np.cov(centered, rowvar=False)
    evals, evecs = np.linalg.eigh(cov)
    axis = evecs[:, int(np.argmax(evals))]
    return normalize(axis)


def section_plane_positions_from_vertices(vertices: np.ndarray, axis: np.ndarray, interior_fracs: Sequence[float]) -> list[float]:
    projection = np.asarray(vertices) @ normalize(axis)
    smin, smax = float(np.min(projection)), float(np.max(projection))
    length = smax - smin
    return [smin + float(frac) * length for frac in interior_fracs]


def _iter_edges(shape: Any) -> Iterator[Any]:
    _require_ocp()
    shape = _as_ocp_shape(shape)
    explorer = TopExp_Explorer(shape, TopAbs_EDGE)
    while explorer.More():
        yield TopoDS.Edge_s(explorer.Current())
        explorer.Next()


def _edge_points_3d(edge: Any, n_samples_curve: int = 12) -> np.ndarray:
    adaptor = BRepAdaptor_Curve(edge)
    u0 = float(adaptor.FirstParameter())
    u1 = float(adaptor.LastParameter())
    ctype = adaptor.GetType()

    if ctype == GeomAbs_Line:
        params = np.array([u0, u1], dtype=float)
    elif ctype in (GeomAbs_Circle, GeomAbs_Ellipse):
        params = np.linspace(u0, u1, max(n_samples_curve, 16))
    else:
        params = np.linspace(u0, u1, n_samples_curve)

    points: list[list[float]] = []
    for param in params:
        point = adaptor.Value(float(param))
        points.append([point.X(), point.Y(), point.Z()])
    return np.asarray(points, dtype=float)


def _edge_curve_type(edge: Any) -> str:
    ctype = BRepAdaptor_Curve(edge).GetType()
    if ctype == GeomAbs_Line:
        return "line"
    if ctype in (GeomAbs_Circle, GeomAbs_Ellipse):
        return "arc"
    if ctype in (GeomAbs_BSplineCurve, GeomAbs_BezierCurve):
        return "spline"
    return "other"


def _wire_to_ring2d_points(wire: Any, origin: np.ndarray, u: np.ndarray, v: np.ndarray) -> tuple[np.ndarray, float, float]:
    explorer = BRepTools_WireExplorer(wire)
    points_2d: list[np.ndarray] = []
    total_line = 0.0
    total_curve = 0.0

    while explorer.More():
        edge = explorer.Current()
        curve_type = _edge_curve_type(edge)
        pts_3d = _edge_points_3d(edge)
        pts_2d = project_points_to_plane(pts_3d, origin, u, v)
        if points_2d:
            pts_2d = pts_2d[1:]
        for row in pts_2d:
            points_2d.append(row)
        seg_len = float(np.sum(np.linalg.norm(np.diff(pts_2d, axis=0), axis=1))) if len(pts_2d) > 1 else 0.0
        if curve_type == "line":
            total_line += seg_len
        else:
            total_curve += seg_len
        explorer.Next()

    arr = np.asarray(points_2d, dtype=float)
    if len(arr) == 0:
        return arr, 0.0, 0.0
    if np.linalg.norm(arr[0] - arr[-1]) > 1e-8:
        arr = np.vstack([arr, arr[0]])
    return arr, total_line, total_curve


def _build_section_polygon_from_wires(
    wires: list[Any],
    origin: np.ndarray,
    u: np.ndarray,
    v: np.ndarray,
) -> tuple[Polygon | None, float, float, tuple[Polygon, ...]]:
    rings: list[tuple[Polygon, float, float]] = []
    for wire in wires:
        points, line_len, curve_len = _wire_to_ring2d_points(wire, origin, u, v)
        if len(points) < 4:
            continue
        try:
            ring = LinearRing(points)
            poly = Polygon(ring)
            if poly.area <= 0:
                continue
            if not poly.is_valid:
                poly = poly.buffer(0)
            if isinstance(poly, MultiPolygon):
                poly = max(poly.geoms, key=lambda g: g.area)
            rings.append((poly, line_len, curve_len))
        except Exception:
            continue

    if not rings:
        return None, 0.0, 0.0, tuple()

    rings.sort(key=lambda item: item[0].area, reverse=True)
    ring_polygons = tuple(item[0] for item in rings)
    outer, line_len, curve_len = rings[0]
    holes: list[Sequence[tuple[float, float]]] = []
    for poly, line_add, curve_add in rings[1:]:
        if outer.contains(poly.representative_point()):
            holes.append(list(poly.exterior.coords))
            line_len += line_add
            curve_len += curve_add
        else:
            return None, 0.0, 0.0, ring_polygons

    result = Polygon(outer.exterior.coords, holes=holes)
    if not result.is_valid:
        fixed = result.buffer(0)
        if isinstance(fixed, Polygon):
            result = fixed
        elif isinstance(fixed, MultiPolygon):
            # Avoid collapsing to a tiny fragment; keep the dominant outer loop.
            result = outer
        else:
            result = outer
    return result, line_len, curve_len, ring_polygons


def slice_solid_to_section(
    solid_shape: Any,
    plane_origin: Sequence[float],
    plane_normal: Sequence[float],
    section_position: float = 0.5,
    connect_tol: float = 1e-5,
) -> Section2D | None:
    _require_ocp()
    solid_shape = _as_ocp_shape(solid_shape)
    n, u, v = orthonormal_basis_from_normal(plane_normal)
    origin = np.asarray(plane_origin, dtype=float)
    plane = gp_Pln(gp_Pnt(*origin.tolist()), gp_Dir(*n.tolist()))

    try:
        section = BRepAlgoAPI_Section(solid_shape, plane, False)
    except TypeError:
        section = BRepAlgoAPI_Section(solid_shape, plane)
    try:
        section.Approximation(True)
    except Exception:
        pass
    try:
        section.ComputePCurveOn1(True)
        section.ComputePCurveOn2(True)
    except Exception:
        pass
    section.Build()
    result_shape = section.Shape()

    edge_seq = TopTools_HSequenceOfShape()
    for edge in _iter_edges(result_shape):
        edge_seq.Append(edge)
    if edge_seq.Length() == 0:
        return None

    wire_seq = TopTools_HSequenceOfShape()
    connect_edges = getattr(ShapeAnalysis_FreeBounds, "ConnectEdgesToWires_s", None)
    if connect_edges is None:
        connect_edges = ShapeAnalysis_FreeBounds.ConnectEdgesToWires
    connect_edges(edge_seq, connect_tol, False, wire_seq)

    wires: list[Any] = []
    for idx in range(1, wire_seq.Length() + 1):
        wires.append(TopoDS.Wire_s(wire_seq.Value(idx)))

    if not wires:
        explorer = TopExp_Explorer(result_shape, TopAbs_WIRE)
        while explorer.More():
            wires.append(TopoDS.Wire_s(explorer.Current()))
            explorer.Next()
    if not wires:
        return None

    poly, line_len, curve_len, ring_polys = _build_section_polygon_from_wires(wires, origin, u, v)
    if poly is None or poly.is_empty or poly.area <= 0:
        return None

    total = line_len + curve_len
    line_frac = line_len / total if total > 0 else 0.0
    curve_frac = curve_len / total if total > 0 else 0.0
    return Section2D(
        polygon=poly,
        origin_3d=origin,
        normal_3d=n,
        basis_u=u,
        basis_v=v,
        source_position=float(section_position),
        line_length_fraction=float(line_frac),
        curve_length_fraction=float(curve_frac),
        wire_polygons=ring_polys,
    )


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
    sdiff = float(a.symmetric_difference(b).area)
    return 0.7 * hausdorff + 0.3 * sdiff


def dominant_section_cluster(sections: Sequence[Section2D], distance_threshold: float = 0.45) -> list[Section2D]:
    if len(sections) <= 1:
        return list(sections)

    polys = [normalize_section_polygon(section.polygon) for section in sections]
    adjacency = {idx: {idx} for idx in range(len(polys))}

    for i in range(len(polys)):
        for j in range(i + 1, len(polys)):
            distance = section_distance(polys[i], polys[j])
            if distance <= distance_threshold:
                adjacency[i].add(j)
                adjacency[j].add(i)

    visited: set[int] = set()
    clusters: list[list[int]] = []
    for start in range(len(polys)):
        if start in visited:
            continue
        stack = [start]
        component: list[int] = []
        while stack:
            node = stack.pop()
            if node in visited:
                continue
            visited.add(node)
            component.append(node)
            stack.extend(neigh for neigh in adjacency[node] if neigh not in visited)
        clusters.append(component)

    best = max(clusters, key=lambda comp: (len(comp), -min(comp)))
    return [sections[idx] for idx in sorted(best)]


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
        # 2D scalar cross product to avoid NumPy 2.0 deprecation on np.cross(2d, 2d)
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
        inter = poly.intersection(reflected)
    except Exception:
        return 0.0
    if union.area <= 0:
        return 0.0
    return float(inter.area / union.area)


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


def _is_nearly_circle(poly: Polygon, compactness_min: float = 0.92, bbox_ratio_min: float = 0.95) -> bool:
    section = Section2D(poly, np.zeros(3), np.array([0, 0, 1.0]), np.array([1.0, 0, 0]), np.array([0, 1.0, 0]), 0.0, 0.0, 1.0)
    features = extract_section_features(section)
    return features.compactness >= compactness_min and features.bbox_ratio >= bbox_ratio_min


def _is_nearly_rectangle(poly: Polygon, bbox_fill_min: float = 0.95, convexity_min: float = 0.98, rel_tol: float = 0.03) -> bool:
    simplified = simplify_relative(poly, rel_tol=rel_tol)
    features = extract_section_features(Section2D(simplified, np.zeros(3), np.array([0, 0, 1.0]), np.array([1.0, 0, 0]), np.array([0, 1.0, 0]), 0.0, 1.0, 0.0))
    coords = np.asarray(simplified.exterior.coords[:-1], dtype=float)
    return len(coords) <= 8 and features.bbox_fill >= bbox_fill_min and features.convexity >= convexity_min


def find_extrusion_axis(
    solid_shape: Any,
    interior_fracs: Sequence[float] = (0.20, 0.35, 0.50, 0.65, 0.80),
    min_successful_sections: int = 3,
) -> AxisCandidate | None:
    vertices = solid_vertices_np(solid_shape)
    if len(vertices) < 8:
        return None

    origin = vertices.mean(axis=0)
    candidates: list[AxisCandidate] = []
    for direction in planar_face_normal_candidates(solid_shape):
        candidates.append(AxisCandidate(direction=normalize(direction), origin=origin, source="planar-face-normal"))

    try:
        candidates.append(AxisCandidate(direction=pca_axis_candidate(vertices), origin=origin, source="vertex-pca"))
    except Exception:
        pass

    if not candidates:
        return None

    unique_candidates: list[AxisCandidate] = []
    for cand in candidates:
        keep = True
        for prev in unique_candidates:
            if abs(float(np.dot(cand.direction, prev.direction))) > 0.999:
                keep = False
                break
        if keep:
            unique_candidates.append(cand)
    candidates = unique_candidates

    axis_extents: dict[tuple[float, float, float], float] = {}
    max_extent = 0.0
    for cand in candidates:
        key = tuple(np.round(cand.direction, 9))
        projection = vertices @ cand.direction
        extent = float(np.max(projection) - np.min(projection))
        axis_extents[key] = extent
        max_extent = max(max_extent, extent)

    positions_cache: dict[tuple[float, float, float], list[float]] = {}
    extent_prefilter_ratio = 0.60

    def _evaluate_candidate(cand: AxisCandidate) -> None:
        key = tuple(np.round(cand.direction, 9))
        axis_extent = axis_extents[key]
        if key not in positions_cache:
            positions_cache[key] = section_plane_positions_from_vertices(vertices, cand.direction, interior_fracs)
        positions = positions_cache[key]

        sections: list[Section2D] = []
        for position in positions:
            plane_origin = cand.direction * position
            try:
                section = slice_solid_to_section(
                    solid_shape,
                    plane_origin=plane_origin,
                    plane_normal=cand.direction,
                    section_position=position,
                )
            except Exception:
                section = None
            if section is not None and not section.polygon.is_empty and section.polygon.area > 0:
                sections.append(section)

        if len(sections) < min_successful_sections:
            cand.score = -1e9
            cand.metrics = {
                "success": float(len(sections)),
                "axis_extent": axis_extent,
                "extent_prefilter_pass": axis_extent >= extent_prefilter_ratio * max_extent if max_extent > 0 else True,
            }
            return

        cluster = dominant_section_cluster(sections)
        cluster_ratio = len(cluster) / max(len(sections), 1)
        normalized = [normalize_section_polygon(section.polygon) for section in cluster]
        areas = np.array([section.polygon.area for section in cluster], dtype=float)
        perimeters = np.array([section.polygon.length for section in cluster], dtype=float)
        distances = [section_distance(a, b) for a, b in itertools.combinations(normalized, 2)]
        mean_distance = float(np.mean(distances)) if distances else 0.0
        area_cv = float(np.std(areas) / max(np.mean(areas), 1e-12))
        perimeter_cv = float(np.std(perimeters) / max(np.mean(perimeters), 1e-12))

        cand.score = (
            15.0 * len(cluster)
            + 0.15 * axis_extent
            + 10.0 * cluster_ratio
            - 20.0 * mean_distance
            - 10.0 * area_cv
            - 5.0 * perimeter_cv
        )
        cand.metrics = {
            "success": float(len(sections)),
            "cluster_size": float(len(cluster)),
            "cluster_ratio": cluster_ratio,
            "mean_section_distance": mean_distance,
            "area_cv": area_cv,
            "perimeter_cv": perimeter_cv,
            "axis_extent": axis_extent,
            "extent_prefilter_pass": axis_extent >= extent_prefilter_ratio * max_extent if max_extent > 0 else True,
        }

    def _passes_quality_gates(cand: AxisCandidate) -> bool:
        return (
            cand.metrics.get("success", 0.0) >= min_successful_sections
            and cand.metrics.get("cluster_ratio", 0.0) >= STEP0_CLUSTER_RATIO_MIN
            and cand.metrics.get("mean_section_distance", 1.0) <= 0.50
            and cand.metrics.get("area_cv", 1.0) <= 0.25
        )

    for cand in candidates:
        _evaluate_candidate(cand)

    preferred: list[AxisCandidate] = []
    fallback: list[AxisCandidate] = []
    for cand in candidates:
        key = tuple(np.round(cand.direction, 9))
        axis_extent = axis_extents[key]
        if max_extent > 0 and axis_extent >= extent_prefilter_ratio * max_extent:
            preferred.append(cand)
        else:
            fallback.append(cand)

    preferred_valid = [cand for cand in preferred if _passes_quality_gates(cand)]
    if preferred_valid:
        return max(preferred_valid, key=lambda c: c.score)

    fallback_valid = [cand for cand in fallback if _passes_quality_gates(cand)]
    if fallback_valid:
        return max(fallback_valid, key=lambda c: c.score)

    return None


# Canonical shared ownership for duplicated 2D/profile helpers now lives in
# analysis.geometry.profile_sections. Keep the legacy names here for
# compatibility while later refactors trim the duplicated local bodies.
AxisCandidate = shared_profile_sections.AxisCandidate
Section2D = shared_profile_sections.Section2D
SectionFeatures = shared_profile_sections.SectionFeatures
TemplateMatch = shared_profile_sections.TemplateMatch
ProfileTemplate = shared_profile_sections.ProfileTemplate
ProfileRegistry = shared_profile_sections.ProfileRegistry
normalize = shared_profile_sections.normalize
unique_rows_rounded = shared_profile_sections.unique_rows_rounded
orthonormal_basis_from_normal = shared_profile_sections.orthonormal_basis_from_normal
project_points_to_plane = shared_profile_sections.project_points_to_plane
polygon_signed_area = shared_profile_sections.polygon_signed_area
simplify_relative = shared_profile_sections.simplify_relative
normalize_section_polygon = shared_profile_sections.normalize_section_polygon
section_distance = shared_profile_sections.section_distance
count_reentrant_corners = shared_profile_sections.count_reentrant_corners
reflect_polygon_about_axis = shared_profile_sections.reflect_polygon_about_axis
symmetry_score = shared_profile_sections.symmetry_score
detect_symmetry_axes = shared_profile_sections.detect_symmetry_axes
extract_section_features = shared_profile_sections.extract_section_features
make_round_bar = shared_profile_sections.make_round_bar
make_pipe = shared_profile_sections.make_pipe
make_flat_bar = shared_profile_sections.make_flat_bar
make_rectangular_tube = shared_profile_sections.make_rectangular_tube
make_i_section = shared_profile_sections.make_i_section
make_u_section = shared_profile_sections.make_u_section
make_l_section = shared_profile_sections.make_l_section
make_t_section = shared_profile_sections.make_t_section
match_templates = shared_profile_sections.match_templates
