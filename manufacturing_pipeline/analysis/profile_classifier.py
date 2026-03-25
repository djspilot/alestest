from __future__ import annotations

"""
STEP steel profile classifier pipeline.

This module is designed for pythonocc-core + Shapely + NumPy/SciPy.
The OpenCASCADE-dependent parts are imported lazily so the file can be
syntax-checked on machines where pythonocc-core is not installed.

Focus:
- STEP/XDE import independent of CAD-exported names
- flattening assemblies to individual solids
- extrusion-axis hypothesis generation and validation
- slicing a solid into a 2D cross-section
- extracting robust 2D features from the cross-section
- rule-based family classification + template matching hooks

Authoring note:
The OCC-specific code is written against the current pythonocc/OpenCASCADE
API shape documented in the official docs and pythonocc demos, but cannot be
executed in this environment because pythonocc-core is not installed here.
The pure-2D parts (Shapely/NumPy/SciPy) are executable and tested separately.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator, Sequence
import itertools
import math
import os
import platform
import sys
import uuid

import numpy as np
from shapely import affinity
from shapely.geometry import LineString, LinearRing, Point, Polygon, MultiPolygon
from shapely.ops import unary_union
from scipy.spatial.distance import cdist
from scipy.cluster.hierarchy import linkage, fcluster


# -----------------------------------------------------------------------------
# Small data objects
# -----------------------------------------------------------------------------


@dataclass(slots=True)
class SolidInstance:
    """A single located solid extracted from a STEP file."""

    shape: Any
    instance_id: str
    label_path: tuple[str, ...] = ()
    debug_name: str | None = None
    units: str | None = None


@dataclass(slots=True)
class AxisCandidate:
    direction: np.ndarray  # shape (3,), unit vector
    origin: np.ndarray     # shape (3,)
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


# -----------------------------------------------------------------------------
# Generic math helpers
# -----------------------------------------------------------------------------


def normalize(v: Sequence[float], eps: float = 1e-12) -> np.ndarray:
    arr = np.asarray(v, dtype=float)
    n = float(np.linalg.norm(arr))
    if n < eps:
        raise ValueError("cannot normalize near-zero vector")
    return arr / n



def unique_rows_rounded(points: np.ndarray, tol: float = 1e-8) -> np.ndarray:
    if len(points) == 0:
        return points
    scale = max(tol, 1e-12)
    q = np.round(points / scale).astype(np.int64)
    _, idx = np.unique(q, axis=0, return_index=True)
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



def polygon_centroid_xy(coords: np.ndarray) -> np.ndarray:
    poly = Polygon(coords)
    c = poly.centroid
    return np.array([c.x, c.y], dtype=float)



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


# -----------------------------------------------------------------------------
# STEP / XDE import
# -----------------------------------------------------------------------------


class MissingPythonOCC(RuntimeError):
    pass



def _require_occ() -> None:
    # Accepteer zowel oud 'OCC' (pythonocc-core) als nieuw 'OCP' (cadquery/OCP),
    # inclusief de occ_compat-shim die OCC.Core.* naar OCP.* mapt.
    try:
        import OCC  # noqa: F401
        return
    except ModuleNotFoundError:
        pass
    try:
        import OCP  # noqa: F401
        return
    except ModuleNotFoundError as exc:
        raise MissingPythonOCC(
            "Noch 'OCC' (pythonocc-core) noch 'OCP' (cadquery/OCP) is beschikbaar."
        ) from exc


# ---------------------------------------------------------------------------
# OCC.Core.* → OCP.* compatibility shim
#
# Als OCC (oud pythonocc-core) niet beschikbaar is maar OCP (nieuw) wel,
# maak dan fake `OCC.Core.<module>` entries in sys.modules die wijzen naar
# de equivalente `OCP.<module>`.  Vervolgens werken alle `from OCC.Core.X
# import Y`-statements in de functies hieronder automatisch.
#
# Extra: topods-adapter (API-verschil: topods.Vertex(s) → TopoDS.Vertex_s(s))
#        en brepgprop_SurfaceProperties-adapter.
# ---------------------------------------------------------------------------
def _install_occ_ocp_shim() -> None:
    """Installeer OCC.Core.* → OCP.* shim in sys.modules (eenmalig)."""
    import sys
    import types

    try:
        import OCC  # noqa: F401
        return  # OCC al beschikbaar, shim niet nodig
    except ImportError:
        pass

    try:
        import OCP  # noqa: F401
    except ImportError:
        return  # ook OCP niet beschikbaar, niets te doen

    # Maak top-level OCC package aan als dat nog niet bestaat
    if "OCC" not in sys.modules:
        occ_pkg = types.ModuleType("OCC")
        sys.modules["OCC"] = occ_pkg
    else:
        occ_pkg = sys.modules["OCC"]

    if "OCC.Core" not in sys.modules:
        occ_core = types.ModuleType("OCC.Core")
        sys.modules["OCC.Core"] = occ_core
        occ_pkg.Core = occ_core  # type: ignore[attr-defined]
    else:
        occ_core = sys.modules["OCC.Core"]

    # Alle OCC.Core submodules mappen naar OCP.*
    _ocp_modules = [
        "BRep", "BRepAdaptor", "BRepAlgoAPI", "BRepGProp", "BRepTools",
        "GProp", "GeomAbs", "IFSelect", "Interface", "STEPCAFControl",
        "STEPControl", "ShapeAnalysis", "TColStd", "TCollection",
        "TDF", "TDocStd", "TopAbs", "TopExp", "TopLoc", "TopTools",
        "TopoDS", "XCAFDoc", "gp",
    ]
    for mod_name in _ocp_modules:
        occ_key = f"OCC.Core.{mod_name}"
        if occ_key not in sys.modules:
            try:
                ocp_mod = __import__(f"OCP.{mod_name}", fromlist=[mod_name])
                sys.modules[occ_key] = ocp_mod
                setattr(occ_core, mod_name, ocp_mod)
            except ImportError:
                pass

    # topods-adapter: OCC gebruikt topods.Vertex(s), OCP gebruikt TopoDS.Vertex_s(s)
    try:
        from OCP.TopoDS import TopoDS as _TopoDS
        _topods = types.SimpleNamespace(
            Vertex=lambda s: _TopoDS.Vertex_s(s),
            Face=lambda s: _TopoDS.Face_s(s),
            Edge=lambda s: _TopoDS.Edge_s(s),
            Wire=lambda s: _TopoDS.Wire_s(s),
            Solid=lambda s: _TopoDS.Solid_s(s),
            Shell=lambda s: _TopoDS.Shell_s(s),
            Compound=lambda s: _TopoDS.Compound_s(s),
        )
        if "OCC.Core.TopoDS" in sys.modules:
            sys.modules["OCC.Core.TopoDS"].topods = _topods  # type: ignore[attr-defined]
    except Exception:
        pass

    # brepgprop-adapter: OCC gebruikt brepgprop_SurfaceProperties(shape, props)
    # OCP gebruikt BRepGProp.SurfaceProperties_s(shape, props)
    try:
        from OCP.BRepGProp import BRepGProp as _BRepGProp
        if "OCC.Core.BRepGProp" in sys.modules:
            sys.modules["OCC.Core.BRepGProp"].brepgprop_SurfaceProperties = (  # type: ignore[attr-defined]
                lambda shape, props: _BRepGProp.SurfaceProperties_s(shape, props)
            )
            sys.modules["OCC.Core.BRepGProp"].brepgprop_VolumeProperties = (  # type: ignore[attr-defined]
                lambda shape, props: _BRepGProp.VolumeProperties_s(shape, props)
            )
            sys.modules["OCC.Core.BRepGProp"].brepgprop_LinearProperties = (  # type: ignore[attr-defined]
                lambda shape, props: _BRepGProp.LinearProperties_s(shape, props)
            )
    except Exception:
        pass


_install_occ_ocp_shim()



def read_step_solids(step_path: str | Path) -> list[SolidInstance]:
    """
    Assembly-aware STEP reader.

    Uses STEPCAFControl_Reader + XCAFDoc_ShapeTool so AP203/AP214/AP242/XDE
    assembly structure is handled by OCCT instead of manual ISO-10303-21 parsing.

    Returns flattened, located solids.
    """
    _require_occ()

    # On some macOS ARM pythonocc/OCCT builds, constructing TDocStd_Document
    # can abort the process in native code (not catchable in Python). Prefer
    # the flat STEP reader there unless explicitly overridden.
    if (
        sys.platform == "darwin"
        and platform.machine().lower() in {"arm64", "aarch64"}
        and os.environ.get("SPC_FORCE_XDE", "0") != "1"
    ):
        return read_step_solids_flat(step_path)

    from OCC.Core.IFSelect import IFSelect_RetDone
    from OCC.Core.STEPCAFControl import STEPCAFControl_Reader
    from OCC.Core.TCollection import TCollection_ExtendedString
    from OCC.Core.TDocStd import TDocStd_Document
    from OCC.Core.TDF import TDF_LabelSequence
    from OCC.Core.TopAbs import TopAbs_SOLID
    from OCC.Core.TopExp import TopExp_Explorer
    from OCC.Core.XCAFDoc import XCAFDoc_DocumentTool
    from OCC.Core.STEPControl import STEPControl_Reader

    # Optional translation parameters. Keep them best-effort because wrappers
    # differ slightly across pythonocc releases.
    try:
        from OCC.Core.Interface import Interface_Static
        Interface_Static.SetIVal_("read.step.product.mode", 1)
        Interface_Static.SetIVal_("read.step.assembly.level", 1)
        Interface_Static.SetIVal_("read.step.shape.relationship", 1)
        Interface_Static.SetIVal_("read.step.shape.repr", 1)
    except Exception:
        pass

    path = str(step_path)

    # Read with XDE/CAF to preserve assembly and instances.
    doc = TDocStd_Document(TCollection_ExtendedString("pythonocc-xde"))
    shape_tool = XCAFDoc_DocumentTool.ShapeTool(doc.Main())

    reader = STEPCAFControl_Reader()
    reader.SetColorMode(True)
    reader.SetLayerMode(True)
    reader.SetNameMode(True)
    reader.SetPropsMode(True)
    try:
        reader.SetMatMode(True)
    except Exception:
        pass

    status = reader.ReadFile(path)
    if status != IFSelect_RetDone:
        raise RuntimeError(f"Could not read STEP file: {path}")
    ok = reader.Transfer(doc)
    if not ok:
        raise RuntimeError(f"Could not transfer STEP file into XDE doc: {path}")

    # Try to retrieve original file units for later catalog matching.
    units = None
    try:
        raw_reader = STEPControl_Reader()
        raw_reader.ReadFile(path)
        from OCC.Core.TColStd import TColStd_SequenceOfAsciiString
        l_units = TColStd_SequenceOfAsciiString()
        a_units = TColStd_SequenceOfAsciiString()
        s_units = TColStd_SequenceOfAsciiString()
        raw_reader.FileUnits(l_units, a_units, s_units)
        if l_units.Length() > 0:
            units = str(l_units.Value(1))
    except Exception:
        pass

    labels = TDF_LabelSequence()
    shape_tool.GetFreeShapes(labels)

    solids: list[SolidInstance] = []

    def flatten_solids(occ_shape: Any, path_parts: tuple[str, ...]) -> None:
        explorer = TopExp_Explorer(occ_shape, TopAbs_SOLID)
        count = 0
        while explorer.More():
            count += 1
            solid = explorer.Current()
            solids.append(
                SolidInstance(
                    shape=solid,
                    instance_id=str(uuid.uuid4()),
                    label_path=path_parts,
                    debug_name="/".join(path_parts) if path_parts else None,
                    units=units,
                )
            )
            explorer.Next()
        # Some files contain a single solid directly as the free shape.
        if count == 0:
            try:
                # ShapeType == TopAbs_SOLID would need TopAbs import. The explorer
                # above is usually enough, so just keep this as a no-op fallback.
                pass
            except Exception:
                pass

    def walk_label(label: Any, path_parts: tuple[str, ...]) -> None:
        # For components, GetShape(label) already returns the located instance.
        if shape_tool.IsAssembly(label):
            children = TDF_LabelSequence()
            shape_tool.GetComponents(label, children, False)
            for i in range(1, children.Length() + 1):
                child = children.Value(i)
                child_path = path_parts + (f"component_{i}",)
                walk_label(child, child_path)
            return

        shape = shape_tool.GetShape(label)
        flatten_solids(shape, path_parts)

    for i in range(1, labels.Length() + 1):
        top_label = labels.Value(i)
        walk_label(top_label, (f"root_{i}",))

    if solids:
        return solids

    # Flat fallback: ignore assembly semantics and just iterate all solids in
    # the translated root shape.
    return read_step_solids_flat(step_path)



def read_step_solids_flat(step_path: str | Path) -> list[SolidInstance]:
    _require_occ()
    from OCC.Core.IFSelect import IFSelect_RetDone
    from OCC.Core.STEPControl import STEPControl_Reader
    from OCC.Core.TopAbs import TopAbs_SOLID
    from OCC.Core.TopExp import TopExp_Explorer

    reader = STEPControl_Reader()
    status = reader.ReadFile(str(step_path))
    if status != IFSelect_RetDone:
        raise RuntimeError(f"Could not read STEP file: {step_path}")
    reader.TransferRoots()
    shape = reader.OneShape()

    solids: list[SolidInstance] = []
    explorer = TopExp_Explorer(shape, TopAbs_SOLID)
    idx = 1
    while explorer.More():
        solids.append(SolidInstance(shape=explorer.Current(), instance_id=f"flat_{idx}", label_path=("flat", str(idx))))
        idx += 1
        explorer.Next()
    return solids


# -----------------------------------------------------------------------------
# Axis detection
# -----------------------------------------------------------------------------



def solid_vertices_np(solid_shape: Any, tol: float = 1e-8) -> np.ndarray:
    _require_occ()
    from OCC.Core.BRep import BRep_Tool
    from OCC.Core.TopAbs import TopAbs_VERTEX
    from OCC.Core.TopExp import TopExp_Explorer
    from OCC.Core.TopoDS import topods

    pts: list[list[float]] = []
    explorer = TopExp_Explorer(solid_shape, TopAbs_VERTEX)
    while explorer.More():
        v = topods.Vertex(explorer.Current())
        p = BRep_Tool.Pnt(v)
        pts.append([p.X(), p.Y(), p.Z()])
        explorer.Next()
    arr = np.asarray(pts, dtype=float)
    return unique_rows_rounded(arr, tol=tol)



def planar_face_normal_candidates(solid_shape: Any, angle_tol_deg: float = 1.0) -> list[np.ndarray]:
    """
    Collect unique normals of planar faces.

    We intentionally keep several candidate normals instead of trying to decide
    which planar pair are the true end caps up front. The later section-consistency
    score selects the actual extrusion axis.
    """
    _require_occ()
    from OCC.Core.BRepAdaptor import BRepAdaptor_Surface
    from OCC.Core.BRepGProp import brepgprop_SurfaceProperties
    from OCC.Core.GProp import GProp_GProps
    from OCC.Core.GeomAbs import GeomAbs_Plane
    from OCC.Core.TopAbs import TopAbs_FACE
    from OCC.Core.TopExp import TopExp_Explorer
    from OCC.Core.TopoDS import topods

    raw: list[tuple[np.ndarray, float]] = []
    explorer = TopExp_Explorer(solid_shape, TopAbs_FACE)
    while explorer.More():
        face = topods.Face(explorer.Current())
        surf = BRepAdaptor_Surface(face)
        if surf.GetType() == GeomAbs_Plane:
            plane = surf.Plane()
            d = plane.Axis().Direction()
            n = normalize([d.X(), d.Y(), d.Z()])
            props = GProp_GProps()
            brepgprop_SurfaceProperties(face, props)
            area = float(props.Mass())
            raw.append((n, area))
            raw.append((-n, area))
        explorer.Next()

    if not raw:
        return []

    cos_tol = math.cos(math.radians(angle_tol_deg))
    clusters: list[dict[str, Any]] = []
    for n, area in raw:
        matched = False
        for c in clusters:
            if float(np.dot(n, c["dir"])) >= cos_tol:
                c["sum"] += n * area
                c["weight"] += area
                c["dir"] = normalize(c["sum"])
                matched = True
                break
        if not matched:
            clusters.append({"dir": n.copy(), "sum": n * area, "weight": area})

    clusters.sort(key=lambda c: c["weight"], reverse=True)
    return [c["dir"] for c in clusters[:8]]



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
    s = np.asarray(vertices) @ normalize(axis)
    smin, smax = float(np.min(s)), float(np.max(s))
    length = smax - smin
    return [smin + float(f) * length for f in interior_fracs]



def find_extrusion_axis(
    solid_shape: Any,
    interior_fracs: Sequence[float] = (0.20, 0.35, 0.50, 0.65, 0.80),
    min_successful_sections: int = 3,
) -> AxisCandidate | None:
    """
    Robust axis detection:
    1. generate candidate axes from planar-face normals + PCA;
    2. score each candidate by section stability across multiple interior slices;
    3. keep the best candidate only if it behaves prismatic enough.
    """
    vertices = solid_vertices_np(solid_shape)
    if len(vertices) < 8:
        return None

    origin = vertices.mean(axis=0)
    candidates: list[AxisCandidate] = []

    # Candidate 1..N: normals of planar faces
    for d in planar_face_normal_candidates(solid_shape):
        candidates.append(AxisCandidate(direction=normalize(d), origin=origin, source="planar-face-normal"))

    # Candidate fallback: PCA major axis
    try:
        pca_axis = pca_axis_candidate(vertices)
        candidates.append(AxisCandidate(direction=pca_axis, origin=origin, source="vertex-pca"))
    except Exception:
        pass

    if not candidates:
        return None

    # Deduplicate candidate directions up to sign.
    uniq: list[AxisCandidate] = []
    for cand in candidates:
        keep = True
        for prev in uniq:
            if abs(float(np.dot(cand.direction, prev.direction))) > 0.999:
                keep = False
                break
        if keep:
            uniq.append(cand)
    candidates = uniq

    best: AxisCandidate | None = None
    positions_cache: dict[tuple[float, float, float], list[float]] = {}

    for cand in candidates:
        key = tuple(np.round(cand.direction, 9))
        if key not in positions_cache:
            positions_cache[key] = section_plane_positions_from_vertices(vertices, cand.direction, interior_fracs)
        positions = positions_cache[key]

        sections: list[Section2D] = []
        for s in positions:
            p = cand.direction * s
            try:
                sec = slice_solid_to_section(solid_shape, plane_origin=p, plane_normal=cand.direction, section_position=s)
            except Exception:
                sec = None
            if sec is not None and not sec.polygon.is_empty and sec.polygon.area > 0:
                sections.append(sec)

        if len(sections) < min_successful_sections:
            cand.score = -1e9
            cand.metrics = {"success": float(len(sections))}
            continue

        # Normalize sections and compare pairwise.
        normalized = [normalize_section_polygon(sec.polygon) for sec in sections]
        areas = np.array([sec.polygon.area for sec in sections], dtype=float)
        perims = np.array([sec.polygon.length for sec in sections], dtype=float)
        dists = []
        for a, b in itertools.combinations(normalized, 2):
            dists.append(section_distance(a, b))
        mean_dist = float(np.mean(dists)) if dists else 0.0
        area_cv = float(np.std(areas) / max(np.mean(areas), 1e-12))
        perim_cv = float(np.std(perims) / max(np.mean(perims), 1e-12))

        # Larger is better.
        cand.score = (
            4.0 * len(sections)
            - 50.0 * mean_dist
            - 20.0 * area_cv
            - 10.0 * perim_cv
        )
        cand.metrics = {
            "success": float(len(sections)),
            "mean_section_distance": mean_dist,
            "area_cv": area_cv,
            "perimeter_cv": perim_cv,
        }
        if best is None or cand.score > best.score:
            best = cand

    if best is None:
        return None

    # Prismatic sanity gate.
    if best.metrics.get("success", 0.0) < min_successful_sections:
        return None
    if best.metrics.get("mean_section_distance", 1.0) > 0.10:
        return None
    if best.metrics.get("area_cv", 1.0) > 0.12:
        return None
    return best


# -----------------------------------------------------------------------------
# Sectioning and wire reconstruction
# -----------------------------------------------------------------------------



def _iter_occ_edges(shape: Any) -> Iterator[Any]:
    _require_occ()
    from OCC.Core.TopAbs import TopAbs_EDGE
    from OCC.Core.TopExp import TopExp_Explorer
    from OCC.Core.TopoDS import topods

    explorer = TopExp_Explorer(shape, TopAbs_EDGE)
    while explorer.More():
        yield topods.Edge(explorer.Current())
        explorer.Next()



def _edge_points_3d(edge: Any, n_samples_curve: int = 12) -> np.ndarray:
    _require_occ()
    from OCC.Core.BRepAdaptor import BRepAdaptor_Curve
    from OCC.Core.GeomAbs import GeomAbs_Line, GeomAbs_Circle, GeomAbs_Ellipse

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

    pts: list[list[float]] = []
    for t in params:
        p = adaptor.Value(float(t))
        pts.append([p.X(), p.Y(), p.Z()])
    return np.asarray(pts, dtype=float)



def _edge_curve_type(edge: Any) -> str:
    _require_occ()
    from OCC.Core.BRepAdaptor import BRepAdaptor_Curve
    from OCC.Core.GeomAbs import (
        GeomAbs_Line,
        GeomAbs_Circle,
        GeomAbs_Ellipse,
        GeomAbs_BSplineCurve,
        GeomAbs_BezierCurve,
    )

    ctype = BRepAdaptor_Curve(edge).GetType()
    if ctype == GeomAbs_Line:
        return "line"
    if ctype in (GeomAbs_Circle, GeomAbs_Ellipse):
        return "arc"
    if ctype in (GeomAbs_BSplineCurve, GeomAbs_BezierCurve):
        return "spline"
    return "other"



def _wire_to_ring2d_points(wire: Any, origin: np.ndarray, u: np.ndarray, v: np.ndarray) -> tuple[np.ndarray, float, float]:
    _require_occ()
    from OCC.Core.BRepTools import BRepTools_WireExplorer

    explorer = BRepTools_WireExplorer(wire)
    pts_2d: list[np.ndarray] = []
    total_line = 0.0
    total_curve = 0.0
    while explorer.More():
        edge = explorer.Current()
        curve_type = _edge_curve_type(edge)
        pts_3d = _edge_points_3d(edge)
        pts_2 = project_points_to_plane(pts_3d, origin, u, v)
        if pts_2d:
            pts_2 = pts_2[1:]
        for row in pts_2:
            pts_2d.append(row)
        seg_len = float(np.sum(np.linalg.norm(np.diff(pts_2, axis=0), axis=1))) if len(pts_2) > 1 else 0.0
        if curve_type == "line":
            total_line += seg_len
        else:
            total_curve += seg_len
        explorer.Next()

    arr = np.asarray(pts_2d, dtype=float)
    if len(arr) == 0:
        return arr, 0.0, 0.0
    if np.linalg.norm(arr[0] - arr[-1]) > 1e-8:
        arr = np.vstack([arr, arr[0]])
    return arr, total_line, total_curve



def _build_section_polygon_from_wires(wires: list[Any], origin: np.ndarray, u: np.ndarray, v: np.ndarray) -> tuple[Polygon | None, float, float]:
    rings: list[tuple[Polygon, float, float]] = []
    for wire in wires:
        pts, line_len, curve_len = _wire_to_ring2d_points(wire, origin, u, v)
        if len(pts) < 4:
            continue
        try:
            ring = LinearRing(pts)
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
        return None, 0.0, 0.0

    # One connected section with optional holes is expected.
    rings.sort(key=lambda item: item[0].area, reverse=True)
    outer, line_len, curve_len = rings[0]
    holes: list[Sequence[tuple[float, float]]] = []
    for poly, l2, c2 in rings[1:]:
        if outer.contains(poly.representative_point()):
            holes.append(list(poly.exterior.coords))
            line_len += l2
            curve_len += c2
        else:
            # Disconnected section -> not a single profile contour.
            return None, 0.0, 0.0

    result = Polygon(outer.exterior.coords, holes=holes)
    if not result.is_valid:
        result = result.buffer(0)
        if isinstance(result, MultiPolygon):
            result = max(result.geoms, key=lambda g: g.area)
    return result, line_len, curve_len



def slice_solid_to_section(
    solid_shape: Any,
    plane_origin: Sequence[float],
    plane_normal: Sequence[float],
    section_position: float = 0.5,
    connect_tol: float = 1e-5,
) -> Section2D | None:
    """
    Slice solid by a plane and rebuild closed 2D contour(s).

    Returns a single connected Polygon with optional holes.
    Multiple disconnected outer rings are treated as invalid for profile
    classification because standard rolled sections should cut into one connected
    region (possibly hollow).
    """
    _require_occ()
    from OCC.Core.BRepAlgoAPI import BRepAlgoAPI_Section
    from OCC.Core.ShapeAnalysis import ShapeAnalysis_FreeBounds
    from OCC.Core.TopTools import TopTools_HSequenceOfShape
    from OCC.Core.TopLoc import TopLoc_Location
    from OCC.Core.gp import gp_Dir, gp_Pln, gp_Pnt
    from OCC.Core.TopoDS import topods
    from OCC.Core.TopAbs import TopAbs_WIRE
    from OCC.Core.TopExp import TopExp_Explorer

    n, u, v = orthonormal_basis_from_normal(plane_normal)
    po = np.asarray(plane_origin, dtype=float)
    plane = gp_Pln(gp_Pnt(*po.tolist()), gp_Dir(*n.tolist()))

    section = BRepAlgoAPI_Section(solid_shape, plane, False)
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

    # 1) collect loose edges
    edge_seq = TopTools_HSequenceOfShape()
    for edge in _iter_occ_edges(result_shape):
        edge_seq.Append(edge)
    if edge_seq.Length() == 0:
        return None

    # 2) connect edges into wires
    wire_seq = TopTools_HSequenceOfShape()
    ShapeAnalysis_FreeBounds.ConnectEdgesToWires(edge_seq, connect_tol, False, wire_seq)

    wires: list[Any] = []
    for i in range(1, wire_seq.Length() + 1):
        wires.append(topods.Wire(wire_seq.Value(i)))

    if not wires:
        # Fallback if wrapper returns existing wires directly in the shape.
        explorer = TopExp_Explorer(result_shape, TopAbs_WIRE)
        while explorer.More():
            wires.append(topods.Wire(explorer.Current()))
            explorer.Next()
    if not wires:
        return None

    poly, line_len, curve_len = _build_section_polygon_from_wires(wires, po, u, v)
    if poly is None or poly.is_empty or poly.area <= 0:
        return None

    total = line_len + curve_len
    line_frac = line_len / total if total > 0 else 0.0
    curve_frac = curve_len / total if total > 0 else 0.0
    return Section2D(
        polygon=poly,
        origin_3d=po,
        normal_3d=n,
        basis_u=u,
        basis_v=v,
        source_position=float(section_position),
        line_length_fraction=float(line_frac),
        curve_length_fraction=float(curve_frac),
    )


# -----------------------------------------------------------------------------
# Cross-section normalization, comparison, clustering
# -----------------------------------------------------------------------------



def normalize_section_polygon(poly: Polygon) -> Polygon:
    poly = poly.buffer(0) if not poly.is_valid else poly
    if isinstance(poly, MultiPolygon):
        poly = max(poly.geoms, key=lambda g: g.area)

    # translate centroid to origin
    c = poly.centroid
    p = affinity.translate(poly, xoff=-c.x, yoff=-c.y)

    # rotate by principal axis of exterior coordinates
    xy = np.asarray(p.exterior.coords[:-1], dtype=float)
    if len(xy) >= 3:
        cov = np.cov(xy, rowvar=False)
        evals, evecs = np.linalg.eigh(cov)
        axis = evecs[:, int(np.argmax(evals))]
        angle = math.degrees(math.atan2(axis[1], axis[0]))
        p = affinity.rotate(p, -angle, origin=(0, 0))

    # deterministic mirror choice
    px = affinity.scale(p, xfact=-1, yfact=1, origin=(0, 0))
    if px.bounds < p.bounds:
        p = px

    # scale to unit area
    if p.area <= 0:
        return p
    scale = math.sqrt(p.area)
    p = affinity.scale(p, xfact=1.0 / scale, yfact=1.0 / scale, origin=(0, 0))
    return p



def section_distance(a: Polygon, b: Polygon) -> float:
    """
    Distance in normalized space.

    Small is good. Combination of Hausdorff distance and symmetric-difference area.
    """
    a = normalize_section_polygon(a)
    b = normalize_section_polygon(b)
    hd = float(a.hausdorff_distance(b))
    sdiff = float(a.symmetric_difference(b).area)
    return 0.7 * hd + 0.3 * sdiff



def dominant_section_cluster(sections: Sequence[Section2D], distance_threshold: float = 0.08) -> list[Section2D]:
    if len(sections) <= 1:
        return list(sections)
    polys = [normalize_section_polygon(sec.polygon) for sec in sections]
    dmat = np.zeros((len(polys), len(polys)), dtype=float)
    for i in range(len(polys)):
        for j in range(i + 1, len(polys)):
            d = section_distance(polys[i], polys[j])
            dmat[i, j] = dmat[j, i] = d
    condensed = dmat[np.triu_indices(len(polys), 1)]
    z = linkage(condensed, method="average")
    labels = fcluster(z, t=distance_threshold, criterion="distance")
    best_label = max(set(labels.tolist()), key=lambda lab: int(np.sum(labels == lab)))
    return [sec for sec, lab in zip(sections, labels) if lab == best_label]


# -----------------------------------------------------------------------------
# 2D feature extraction and symmetry
# -----------------------------------------------------------------------------



def count_reentrant_corners(poly: Polygon, rel_tol: float = 0.004) -> int:
    p = simplify_relative(poly, rel_tol=rel_tol)
    ring = np.asarray(p.exterior.coords[:-1], dtype=float)
    if len(ring) < 4:
        return 0

    # Ensure CCW orientation for the outer ring.
    if polygon_signed_area(ring) < 0:
        ring = ring[::-1]

    count = 0
    for i in range(len(ring)):
        a = ring[i - 1]
        b = ring[i]
        c = ring[(i + 1) % len(ring)]
        v1 = a - b
        v2 = c - b
        cross = float(np.cross(v1, v2))
        if cross > 0:
            count += 1
    return count



def reflect_polygon_about_axis(poly: Polygon, angle_deg: float) -> Polygon:
    centered = affinity.translate(poly, xoff=-poly.centroid.x, yoff=-poly.centroid.y)
    r = affinity.rotate(centered, -angle_deg, origin=(0, 0))
    rr = affinity.scale(r, xfact=1.0, yfact=-1.0, origin=(0, 0))
    out = affinity.rotate(rr, angle_deg, origin=(0, 0))
    return out



def symmetry_score(poly: Polygon, axis_angle_deg: float) -> float:
    reflected = reflect_polygon_about_axis(poly, axis_angle_deg)
    union = poly.union(reflected)
    inter = poly.intersection(reflected)
    if union.area <= 0:
        return 0.0
    return float(inter.area / union.area)



def detect_symmetry_axes(
    poly: Polygon,
    angle_step_deg: float = 2.5,
    min_score: float = 0.985,
) -> tuple[tuple[float, ...], tuple[float, ...]]:
    """
    Reflection symmetry by IoU after mirroring around an axis through centroid.

    Returns deduplicated axis angles in degrees in [0, 180).
    """
    p = normalize_section_polygon(poly)
    angles = np.arange(0.0, 180.0, angle_step_deg)
    scored = [(float(a), symmetry_score(p, float(a))) for a in angles]
    passed = [(a, s) for a, s in scored if s >= min_score]
    if not passed:
        # Still return the best 2 for diagnostics.
        best = sorted(scored, key=lambda t: t[1], reverse=True)[:2]
        return tuple(a for a, _ in best), tuple(s for _, s in best)

    # Cluster neighboring angles because a symmetric shape usually yields a small
    # band of equivalent angles around the true axis after discretization.
    merged: list[tuple[float, float]] = []
    current: list[tuple[float, float]] = [passed[0]]
    for item in passed[1:]:
        if item[0] - current[-1][0] <= 1.5 * angle_step_deg:
            current.append(item)
        else:
            merged.append((float(np.mean([a for a, _ in current])), float(max(s for _, s in current))))
            current = [item]
    merged.append((float(np.mean([a for a, _ in current])), float(max(s for _, s in current))))
    return tuple(a for a, _ in merged), tuple(s for _, s in merged)



def extract_section_features(section: Section2D) -> SectionFeatures:
    poly = section.polygon
    area = float(poly.area)
    perim = float(poly.length)
    compactness = float(4.0 * math.pi * area / max(perim * perim, 1e-12))
    convexity = float(area / max(poly.convex_hull.area, 1e-12))

    mrr = poly.minimum_rotated_rectangle
    mrr_xy = np.asarray(mrr.exterior.coords[:-1], dtype=float)
    edges = np.linalg.norm(np.diff(np.vstack([mrr_xy, mrr_xy[0]]), axis=0), axis=1)
    # For rectangles we get [w, h, w, h]. Use min/max instead of the two largest.
    h = float(np.max(edges)) if len(edges) else 0.0
    w = float(np.min(edges)) if len(edges) else h
    bbox_ratio = min(h, w) / max(h, w, 1e-12)
    bbox_fill = float(area / max(mrr.area, 1e-12))

    sym_angles, sym_scores = detect_symmetry_axes(poly)
    reentrant = count_reentrant_corners(poly)

    return SectionFeatures(
        area=area,
        perimeter=perim,
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


# -----------------------------------------------------------------------------
# Template generators and matching
# -----------------------------------------------------------------------------



def _center_scale_polygon(poly: Polygon) -> Polygon:
    return normalize_section_polygon(poly)



def make_round_bar(radius: float = 0.5, resolution: int = 64) -> Polygon:
    return _center_scale_polygon(Point(0, 0).buffer(radius, resolution=resolution))



def make_pipe(outer_radius: float = 0.5, thickness: float = 0.1, resolution: int = 64) -> Polygon:
    outer = Point(0, 0).buffer(outer_radius, resolution=resolution)
    inner = Point(0, 0).buffer(max(outer_radius - thickness, 1e-6), resolution=resolution)
    return _center_scale_polygon(outer.difference(inner))



def make_flat_bar(width: float = 1.0, thickness: float = 0.2) -> Polygon:
    hw, ht = width / 2.0, thickness / 2.0
    return _center_scale_polygon(Polygon([(-hw, -ht), (hw, -ht), (hw, ht), (-hw, ht)]))



def make_rectangular_tube(width: float = 1.0, height: float = 0.6, thickness: float = 0.08) -> Polygon:
    ow, oh = width / 2.0, height / 2.0
    iw, ih = max(ow - thickness, 1e-6), max(oh - thickness, 1e-6)
    outer = Polygon([(-ow, -oh), (ow, -oh), (ow, oh), (-ow, oh)])
    inner = Polygon([(-iw, -ih), (iw, -ih), (iw, ih), (-iw, ih)])
    return _center_scale_polygon(outer.difference(inner))



def make_i_section(h: float = 1.0, b: float = 0.55, tw: float = 0.08, tf: float = 0.12) -> Polygon:
    hh, hb = h / 2.0, b / 2.0
    hw, hf = tw / 2.0, tf
    coords = [
        (-hb, hh), (hb, hh), (hb, hh - hf), (hw, hh - hf), (hw, -hh + hf),
        (hb, -hh + hf), (hb, -hh), (-hb, -hh), (-hb, -hh + hf), (-hw, -hh + hf),
        (-hw, hh - hf), (-hb, hh - hf),
    ]
    return _center_scale_polygon(Polygon(coords))



def make_u_section(h: float = 1.0, b: float = 0.45, tw: float = 0.08, tf: float = 0.12) -> Polygon:
    hh, hb = h / 2.0, b / 2.0
    coords = [
        (-hb, hh), (hb, hh), (hb, hh - tf), (-hb + tw, hh - tf),
        (-hb + tw, -hh + tf), (hb, -hh + tf), (hb, -hh), (-hb, -hh),
    ]
    return _center_scale_polygon(Polygon(coords))



def make_l_section(a: float = 1.0, b: float = 0.7, t: float = 0.12) -> Polygon:
    coords = [
        (0, 0), (a, 0), (a, t), (t, t), (t, b), (0, b),
    ]
    poly = Polygon(coords)
    poly = affinity.translate(poly, xoff=-poly.centroid.x, yoff=-poly.centroid.y)
    return _center_scale_polygon(poly)



def make_t_section(h: float = 1.0, b: float = 0.7, tw: float = 0.10, tf: float = 0.16) -> Polygon:
    hh, hb = h / 2.0, b / 2.0
    hw = tw / 2.0
    coords = [
        (-hb, hh), (hb, hh), (hb, hh - tf), (hw, hh - tf),
        (hw, -hh), (-hw, -hh), (-hw, hh - tf), (-hb, hh - tf),
    ]
    return _center_scale_polygon(Polygon(coords))


@dataclass(slots=True)
class ProfileTemplate:
    family: str
    variant: str
    polygon: Polygon
    meta: dict[str, float] = field(default_factory=dict)


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

        # Generic families: coarse but useful. For exact IPE/HEA/HEB/UNP size
        # matching, feed a real standards CSV into the registry.
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
    q = normalize_section_polygon(poly)
    variants: list[TemplateMatch] = []
    for tpl in registry.templates:
        best = float("inf")
        for rot in (0.0, 90.0, 180.0, 270.0):
            t = affinity.rotate(tpl.polygon, rot, origin=(0, 0))
            d = section_distance(q, t)
            best = min(best, d)
            tm = affinity.scale(t, xfact=-1.0, yfact=1.0, origin=(0, 0))
            d2 = section_distance(q, tm)
            best = min(best, d2)
        variants.append(TemplateMatch(family=tpl.family, variant=tpl.variant, score=best, details=dict(tpl.meta)))
    variants.sort(key=lambda m: m.score)
    return variants[:top_k]


# -----------------------------------------------------------------------------
# Rule-based family classification
# -----------------------------------------------------------------------------



def _is_nearly_circle(poly: Polygon, compactness_min: float = 0.92, bbox_ratio_min: float = 0.95) -> bool:
    sec = Section2D(poly, np.zeros(3), np.array([0, 0, 1.0]), np.array([1.0, 0, 0]), np.array([0, 1.0, 0]), 0.0, 0.0, 1.0)
    f = extract_section_features(sec)
    return f.compactness >= compactness_min and f.bbox_ratio >= bbox_ratio_min



def _is_nearly_rectangle(poly: Polygon, bbox_fill_min: float = 0.95, convexity_min: float = 0.98, rel_tol: float = 0.004) -> bool:
    p = simplify_relative(poly, rel_tol=rel_tol)
    f = extract_section_features(Section2D(p, np.zeros(3), np.array([0, 0, 1.0]), np.array([1.0, 0, 0]), np.array([0, 1.0, 0]), 0.0, 1.0, 0.0))
    coords = np.asarray(p.exterior.coords[:-1], dtype=float)
    return len(coords) == 4 and f.bbox_fill >= bbox_fill_min and f.convexity >= convexity_min



def classify_section(
    section: Section2D,
    registry: ProfileRegistry | None = None,
    template_accept_threshold: float = 0.12,
) -> dict[str, Any]:
    """
    Hybrid classifier.

    Strategy:
    1. hard rules for circles / pipes / flat bars / rectangular hollow sections;
    2. coarse family template matching for I/U/L/T;
    3. return ANDERS when the best template is still too far.
    """
    poly = section.polygon.buffer(0) if not section.polygon.is_valid else section.polygon
    if isinstance(poly, MultiPolygon):
        poly = max(poly.geoms, key=lambda g: g.area)

    features = extract_section_features(section)
    registry = registry or ProfileRegistry().extend_generic_defaults()

    # 1) circular families
    if features.holes == 0 and _is_nearly_circle(poly):
        return {
            "label": "ROND_STAAL",
            "confidence": 0.99,
            "method": "rule",
            "features": features,
        }

    if features.holes == 1:
        outer = Polygon(poly.exterior.coords)
        inner = Polygon(list(poly.interiors[0].coords))
        if _is_nearly_circle(outer, 0.90, 0.94) and _is_nearly_circle(inner, 0.90, 0.94):
            return {
                "label": "RONDE_BUIS",
                "confidence": 0.99,
                "method": "rule",
                "features": features,
            }
        if _is_nearly_rectangle(outer) and _is_nearly_rectangle(inner):
            return {
                "label": "RECHTHOEKIGE_KOKER",
                "confidence": 0.98,
                "method": "rule",
                "features": features,
            }

    # 2) flat bar / rectangular solid bar
    if features.holes == 0 and _is_nearly_rectangle(poly):
        if features.bbox_ratio <= 0.30:
            return {
                "label": "PLAT_STAAL",
                "confidence": 0.98,
                "method": "rule",
                "features": features,
            }
        # ontology gap: solid square/rectangular bar is not in the requested list.
        return {
            "label": "ANDERS",
            "confidence": 0.85,
            "method": "rule",
            "reason": "rechthoekige massieve doorsnede valt niet in de opgegeven profielset",
            "features": features,
        }

    # 3) open concave families: I/U/L/T via templates
    matches = match_templates(poly, registry, top_k=5)
    best = matches[0] if matches else None
    if best and best.score <= template_accept_threshold:
        return {
            "label": best.family,
            "variant": best.variant,
            "confidence": max(0.50, 1.0 - min(best.score / template_accept_threshold, 1.0)),
            "method": "template",
            "features": features,
            "top_matches": matches,
        }

    return {
        "label": "ANDERS",
        "confidence": 0.60 if best is None else max(0.30, 1.0 - min(best.score, 1.0)),
        "method": "template-fallback",
        "features": features,
        "top_matches": matches,
    }


# -----------------------------------------------------------------------------
# End-to-end convenience function
# -----------------------------------------------------------------------------

# Fractions along the extrusion axis to sample: 0.03 and 0.97 give start/end sections.
_CLASSIFY_SECTION_FRACS = (0.03, 0.20, 0.35, 0.50, 0.65, 0.80, 0.97)


def _serialize_section_entry(sec: "Section2D", pos_to_frac: dict) -> dict:
    """Serialize a Section2D to a JSON-safe dict including exact 2D polygon coordinates."""
    ext_coords = [[float(c[0]), float(c[1])] for c in list(sec.polygon.exterior.coords)[:-1]]
    int_coords = [
        [[float(c[0]), float(c[1])] for c in list(ring.coords)[:-1]]
        for ring in sec.polygon.interiors
    ]
    frac = float(pos_to_frac.get(sec.source_position, 0.5))
    return {
        "position": float(sec.source_position),
        "fraction": frac,
        "is_start": frac <= 0.10,
        "is_end": frac >= 0.90,
        "origin_3d": sec.origin_3d.tolist(),
        "normal_3d": sec.normal_3d.tolist(),
        "basis_u": sec.basis_u.tolist(),
        "basis_v": sec.basis_v.tolist(),
        "area": float(sec.polygon.area),
        "holes": len(sec.polygon.interiors),
        "line_length_fraction": float(sec.line_length_fraction),
        "curve_length_fraction": float(sec.curve_length_fraction),
        "polygon_exterior": ext_coords,
        "polygon_interiors": int_coords,
    }


def classify_solid_profile(solid_shape: Any, registry: ProfileRegistry | None = None) -> dict[str, Any]:
    axis = find_extrusion_axis(solid_shape)
    if axis is None:
        return {
            "label": "ANDERS",
            "confidence": 0.4,
            "reason": "geen stabiele extrusie-as gevonden",
        }

    vertices = solid_vertices_np(solid_shape)
    fracs = _CLASSIFY_SECTION_FRACS
    positions = section_plane_positions_from_vertices(vertices, axis.direction, fracs)
    pos_to_frac = dict(zip(positions, fracs))
    sections: list[Section2D] = []
    for s in positions:
        sec = slice_solid_to_section(solid_shape, plane_origin=axis.direction * s, plane_normal=axis.direction, section_position=s)
        if sec is not None and sec.polygon.area > 0:
            sections.append(sec)

    if len(sections) < 3:
        return {
            "label": "ANDERS",
            "confidence": 0.45,
            "reason": "te weinig geldige doorsneden",
            "axis": axis,
            "section_positions": [float(p) for p in positions],
            "sampled_sections": [_serialize_section_entry(sec, pos_to_frac) for sec in sections],
        }

    cluster = dominant_section_cluster(sections)
    if len(cluster) / max(len(sections), 1) < 0.60:
        return {
            "label": "ANDERS",
            "confidence": 0.50,
            "reason": "doorsneden zijn niet stabiel genoeg langs de lengte",
            "axis": axis,
            "section_positions": [float(p) for p in positions],
            "sampled_sections": [_serialize_section_entry(sec, pos_to_frac) for sec in sections],
        }

    # medoid of dominant cluster
    normalized = [normalize_section_polygon(sec.polygon) for sec in cluster]
    dsum = []
    for i, a in enumerate(normalized):
        s = 0.0
        for j, b in enumerate(normalized):
            if i != j:
                s += section_distance(a, b)
        dsum.append(s)
    core = cluster[int(np.argmin(dsum))]

    result = classify_section(core, registry=registry)
    result.update(
        {
            "axis": axis,
            "cluster_size": len(cluster),
            "sections_total": len(sections),
            "section_positions": [float(p) for p in positions],
            "sampled_sections": [_serialize_section_entry(sec, pos_to_frac) for sec in sections],
        }
    )
    return result


# -----------------------------------------------------------------------------
# Registry extension hook from JSON-like specs
# -----------------------------------------------------------------------------


TEMPLATE_BUILDERS: dict[str, Callable[..., Polygon]] = {
    "round_bar": make_round_bar,
    "pipe": make_pipe,
    "flat_bar": make_flat_bar,
    "rect_tube": make_rectangular_tube,
    "i_section": make_i_section,
    "u_section": make_u_section,
    "l_section": make_l_section,
    "t_section": make_t_section,
}



def add_template_from_spec(registry: ProfileRegistry, spec: dict[str, Any]) -> None:
    builder_name = str(spec["shape"])
    family = str(spec["family"])
    variant = str(spec.get("variant", family))
    params = dict(spec.get("params", {}))
    if builder_name not in TEMPLATE_BUILDERS:
        raise KeyError(f"Unknown template builder: {builder_name}")
    polygon = TEMPLATE_BUILDERS[builder_name](**params)
    registry.add(family, variant, polygon, **{k: float(v) for k, v in params.items() if isinstance(v, (int, float))})


if __name__ == "__main__":
    print("step_profile_classifier.py loaded successfully.")
