from __future__ import annotations

from typing import Any, Dict, Optional

from manufacturing_pipeline.analysis.classification_core.result_types import Step0Result, _result


def _check_hollow_tube_consistency(solid, axis, vertices, core_sec) -> Dict[str, Any]:
    """Check if a hollow round tube is geometrically constant along its length."""
    import numpy as np
    from shapely.geometry import Polygon as ShapelyPolygon

    OD_VAR_MAX = 0.15
    WALL_VAR_MAX = 0.25
    HOLLOW_TUBE_MIN_LENGTH_RATIO = 1.5

    result: Dict[str, Any] = {
        "is_machined": False,
        "reason": "n.v.t.",
        "details": {},
    }

    if core_sec is None or axis is None or vertices is None:
        return result

    try:
        from manufacturing_pipeline.analysis.step0_section_tools import (
            section_plane_positions_from_vertices,
            slice_solid_to_section,
        )
        projection = np.asarray(vertices, dtype=float) @ axis.direction
        axis_length = float(np.max(projection) - np.min(projection))
    except Exception:
        return result

    if axis_length <= 0:
        return result

    minx, miny, maxx, maxy = core_sec.polygon.bounds
    dmax_ref = float(max(maxx - minx, maxy - miny))
    if dmax_ref <= 0:
        return result

    if axis_length / dmax_ref < HOLLOW_TUBE_MIN_LENGTH_RATIO:
        return result

    fracs = (0.05, 0.25, 0.75, 0.95)
    try:
        positions = section_plane_positions_from_vertices(vertices, axis.direction, fracs)
    except Exception:
        return result

    ods: list[float] = []
    wall_thicknesses: list[float] = []

    for pos in positions:
        try:
            sec = slice_solid_to_section(
                solid,
                plane_origin=axis.direction * pos,
                plane_normal=axis.direction,
                section_position=pos,
            )
        except Exception:
            continue

        if sec is None or sec.polygon.area <= 0:
            continue

        sx0, sy0, sx1, sy1 = sec.polygon.bounds
        od = float(max(sx1 - sx0, sy1 - sy0))
        if od <= 0:
            continue
        ods.append(od)

        inner_poly = None
        if sec.polygon.interiors:
            try:
                inner_poly = ShapelyPolygon(list(sec.polygon.interiors[0].coords))
            except Exception:
                inner_poly = None

        if inner_poly is None:
            wire_polys = [
                poly
                for poly in getattr(sec, "wire_polygons", ())
                if poly is not None and not poly.is_empty and poly.area > 0
            ]
            if len(wire_polys) >= 2:
                wire_polys.sort(key=lambda poly: poly.area, reverse=True)
                inner_poly = wire_polys[1]

        if inner_poly is not None and not inner_poly.is_empty and inner_poly.area > 0:
            ix0, iy0, ix1, iy1 = inner_poly.bounds
            inner_d = float(max(ix1 - ix0, iy1 - iy0))
            wall_t = (od - inner_d) / 2.0
            if wall_t > 0:
                wall_thicknesses.append(wall_t)

    result["details"]["ods"] = [round(v, 2) for v in ods]
    result["details"]["wall_thicknesses"] = [round(v, 2) for v in wall_thicknesses]

    if len(ods) >= 2:
        od_max, od_min = max(ods), min(ods)
        od_var = (od_max - od_min) / max(od_max, 1e-9)
        result["details"]["od_variation"] = round(od_var, 4)
        if od_var > OD_VAR_MAX:
            result["is_machined"] = True
            result["reason"] = (
                f"buitendiameter niet constant (variatie {od_var:.1%} > {OD_VAR_MAX:.0%}): "
                f"min={od_min:.1f}, max={od_max:.1f}"
            )
            return result

    if len(wall_thicknesses) >= 2:
        wt_max, wt_min = max(wall_thicknesses), min(wall_thicknesses)
        wt_var = (wt_max - wt_min) / max(wt_max, 1e-9)
        result["details"]["wall_variation"] = round(wt_var, 4)
        if wt_var > WALL_VAR_MAX:
            result["is_machined"] = True
            result["reason"] = (
                f"wanddikte niet constant (variatie {wt_var:.1%} > {WALL_VAR_MAX:.0%}): "
                f"min={wt_min:.1f}, max={wt_max:.1f}"
            )

    return result


def _step_0_2_hollow_closed(solid) -> Optional[Step0Result]:
    """Detecteer ronde buis of rechthoekige koker via section holes==1."""
    try:
        from manufacturing_pipeline.analysis.step0_section_tools import (
            _is_nearly_circle,
            _is_nearly_rectangle,
            dominant_section_cluster,
            extract_section_features,
            find_extrusion_axis,
            normalize_section_polygon,
            section_distance,
            section_plane_positions_from_vertices,
            slice_solid_to_section,
            solid_vertices_np,
        )
        from shapely.geometry import Polygon as ShapelyPolygon
    except ImportError:
        return None

    axis = find_extrusion_axis(solid)
    if axis is None:
        return None

    try:
        vertices = solid_vertices_np(solid)
        positions = section_plane_positions_from_vertices(
            vertices, axis.direction, (0.20, 0.35, 0.50, 0.65, 0.80)
        )
        sections = []
        for pos in positions:
            sec = slice_solid_to_section(
                solid,
                plane_origin=axis.direction * pos,
                plane_normal=axis.direction,
                section_position=pos,
            )
            if sec is not None and sec.polygon.area > 0:
                sections.append(sec)
    except Exception:
        return None

    if not sections:
        return None

    cluster = dominant_section_cluster(sections)
    if not cluster:
        return None

    import numpy as np

    normalized = [normalize_section_polygon(sec.polygon) for sec in cluster]
    dsum = [sum(section_distance(a, b) for j, b in enumerate(normalized) if j != i) for i, a in enumerate(normalized)]
    core_sec = cluster[int(np.argmin(dsum))]
    core_poly = core_sec.polygon

    features = extract_section_features(core_sec)
    effective_holes = features.holes
    outer = None
    inner = None
    used_wire_fallback = False

    if core_poly is not None and len(core_poly.interiors) >= 1:
        outer = ShapelyPolygon(core_poly.exterior.coords)
        inner = ShapelyPolygon(list(core_poly.interiors[0].coords))
    else:
        wire_polys = [
            poly
            for poly in getattr(core_sec, "wire_polygons", ())
            if poly is not None and not poly.is_empty and poly.area > 0
        ]
        if len(wire_polys) >= 2:
            wire_polys.sort(key=lambda poly: poly.area, reverse=True)
            outer = wire_polys[0]
            inner = wire_polys[1]
            overlap_ratio = outer.intersection(inner).area / max(inner.area, 1e-9)
            if overlap_ratio >= 0.90:
                effective_holes = max(effective_holes, 1)
                used_wire_fallback = True

    if effective_holes != 1 or outer is None or inner is None:
        return None

    if _is_nearly_circle(outer, 0.90, 0.94) and _is_nearly_circle(inner, 0.90, 0.94):
        machined_check = _check_hollow_tube_consistency(
            solid=solid,
            axis=axis,
            vertices=vertices,
            core_sec=core_sec,
        )
        if machined_check.get("is_machined"):
            return _result(
                label="ANDERS",
                step="0.2",
                method="rule",
                confidence=0.88,
                fallthrough=False,
                reason=machined_check.get("reason", "gemaakte uiteinden of variabele diameter"),
                features={"holes": effective_holes, **machined_check.get("details", {})},
            )

        return _result(
            label="RONDE_BUIS",
            step="0.2",
            method="rule",
            confidence=0.99,
            fallthrough=False,
            reason="holes==1 + outer/inner near-circle + constante diameter",
            features={"holes": effective_holes},
        )

    is_rect_strict = _is_nearly_rectangle(outer) and _is_nearly_rectangle(inner)
    is_rect_rounded = (
        _is_nearly_rectangle(outer, bbox_fill_min=0.85, convexity_min=0.98, rel_tol=0.05)
        and _is_nearly_rectangle(inner, bbox_fill_min=0.88, convexity_min=0.98, rel_tol=0.05)
    )
    if used_wire_fallback and not is_rect_rounded:
        is_rect_rounded = (
            _is_nearly_rectangle(outer, bbox_fill_min=0.80, convexity_min=0.95, rel_tol=0.08)
            and _is_nearly_rectangle(inner, bbox_fill_min=0.80, convexity_min=0.95, rel_tol=0.08)
        )

    if is_rect_strict or is_rect_rounded:
        rect_reason = "holes==1 + outer/inner near-rectangle"
        if not is_rect_strict and is_rect_rounded:
            rect_reason = "holes==1 + outer/inner near-rectangle (afgeronde hoeken)"
        return _result(
            label="RECHTHOEKIGE_KOKER",
            step="0.2",
            method="rule",
            confidence=0.98,
            fallthrough=False,
            reason=rect_reason,
            features={"holes": effective_holes},
        )

    return None
