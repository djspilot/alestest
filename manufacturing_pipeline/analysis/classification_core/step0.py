"""
STEP 0 Classificatie — definitieve beslisboom voor solid geometrie.

Dit module implementeert de STEP 0 beslisboom zoals vastgelegd in
classification_step_review.md. De functie `classify_step0` is het
centrale entrypoint.

Beslisboom volgorde (met exit-gedrag):
  0.1  Slice-validatie (poort)        → ANDERS als niet stabiel
  0.2  Gesloten-hol (buis/koker)      → direct stop bij match
  0.3  Open profiel (L/U/I/T)         → direct stop bij match
  0.4a Vlakke plaat (high confidence) → stop of doorval naar Step 1
    0.4b Constant-dikte open sectie     → GEZETTE_PLAAT en stop
  0.5  Massief profiel fallback       → PROFIEL of ANDERS

Uitvoer van classify_step0():
    {
        "label":      str,      # RONDE_BUIS|RECHTHOEKIGE_KOKER|PROFIEL|
                                #  PLAAT|GEZETTE_PLAAT|ANDERS
        "step":       str,      # "0.1"|"0.2"|"0.3"|"0.4a"|"0.4b"|"0.5"
        "method":     str,      # "rule"|"template"|"fallback"
        "confidence": float,    # 0.0–1.0
        "fallthrough":bool,     # True = door naar Step 1 nodig
        "reason":     str,      # vrije tekst, debuginfo
        "features":   dict,     # gemeten waarden
    }

Integratie met assembly_analysis.py:
  classify_solid() roept classify_step0() als eerste check aan.
  Indien fallthrough=False wordt het resultaat direct teruggegeven.
  Indien fallthrough=True gaat classify_solid() verder met Step 1-4.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("ales.classification_step0")

# ---------------------------------------------------------------------------
# Lazy OCP import guard
# ---------------------------------------------------------------------------
try:
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopAbs import TopAbs_FACE, TopAbs_EDGE
    from OCP.TopoDS import TopoDS
    from OCP.GProp import GProp_GProps
    from OCP.BRepGProp import BRepGProp
    _HAS_OCP = True
except ImportError:
    _HAS_OCP = False


# ---------------------------------------------------------------------------
# Geïmporteerde bouwstenen
# ---------------------------------------------------------------------------
from manufacturing_pipeline.analysis.classification_variables import (
    BENT_SHEET_LARGE_RADIUS_MIN_MM,
    BENT_SHEET_MIN_EDGE_COUNT,
    BENT_SHEET_THICKNESS_MAX_MM,
    BENT_SHEET_VOLUME_RATIO_MIN,
    BENT_SHEET_VOLUME_RATIO_MAX,
    BENT_SHEET_TOP2_FACES_MAX_PCT,
    BENT_SHEET_ASPECT_RATIO_MIN,
    PLATE_THICK_MAX_MM,
    PROFILE_LENGTH_RATIO_MIN,
    PROFILE_CROSS_RATIO_MIN,
    PROFILE_CROSS_RATIO_MAX,
    ROUND_SHAFT_AXIAL_AREA_RATIO_MIN,
    ROUND_SHAFT_CORE_BBOX_RATIO_MIN,
    ROUND_SHAFT_CORE_COMPACTNESS_MIN,
    ROUND_SHAFT_MIN_LENGTH_RATIO,
    STANDARD_TUBE_VOLUME_RATIO_MAX,
    STEP0_CLUSTER_RATIO_MIN,
)
from manufacturing_pipeline.analysis.classification_core import geometry_metrics as _geometry_metrics
from manufacturing_pipeline.analysis.classification_core import hollow_closed as _hollow_closed
from manufacturing_pipeline.analysis.classification_core import open_profile as _open_profile
from manufacturing_pipeline.analysis.classification_core import plate_rules as _plate_rules
from manufacturing_pipeline.analysis.classification_core.result_types import Step0Result, _result
from manufacturing_pipeline.analysis.classification_core import solid_profile_fallback as _solid_profile_fallback
from manufacturing_pipeline.analysis.classification_core import validation as _validation

# ===========================================================================
# Privé helpers — drempelwaarde logica
# ===========================================================================

def _is_bent_sheet_geometry(solid, volume: float, dims: Tuple[float, float, float]) -> bool:
    return _open_profile._is_bent_sheet_geometry(solid, volume, dims)


def _is_constant_thickness(solid) -> bool:
    return _plate_rules._is_constant_thickness(solid)


# ===========================================================================
# Stap 0.3 — Open profiel (L/U/I/T)
# ===========================================================================

def _step_0_3_open_profile(solid, dims: Tuple[float, float, float]) -> Optional[Step0Result]:
    return _open_profile._step_0_3_open_profile(solid, dims)


# ===========================================================================
# Stap 0.4a — Vlakke plaat (high confidence)
# ===========================================================================

def _step_0_4a_flat_plate(solid) -> Optional[Step0Result]:
    return _plate_rules._step_0_4a_flat_plate(solid)


def _select_step_0_4b_features(solid) -> Optional[Dict[str, Any]]:
    return _plate_rules._select_step_0_4b_features(solid)


# ===========================================================================
# Stap 0.4b — Constant-dikte open sectie
# ===========================================================================

def _step_0_4b_constant_thickness_open(
    solid, dims: Tuple[float, float, float]
) -> Optional[Step0Result]:
    return _plate_rules._step_0_4b_constant_thickness_open(solid, dims)


# ===========================================================================
# Stap 0.5 — Massief profiel fallback
# ===========================================================================

def _step_0_5_solid_profile_fallback(
    solid, dims: Tuple[float, float, float], volume: float
) -> Step0Result:
    return _solid_profile_fallback._step_0_5_solid_profile_fallback(solid, dims, volume)


# ===========================================================================
# Publiek entrypoint
# ===========================================================================

def classify_step0(solid) -> Step0Result:
    """Voer de complete STEP 0 beslisboom uit op een OCC solid.

    Volgorde met exit-gedrag:
      0.1 → 0.2 → 0.3 → 0.4a → 0.4b → 0.5

    Args:
        solid: OCC TopoDS_Shape of vergelijkbaar solid object.

    Returns:
        Step0Result dict (zie module-docstring voor schema).
    """
    dims = _get_bbox_sorted(solid)
    volume = _get_volume(solid)

    dependency_errors: list[str] = []

    # 0.1 Slice-validatie (poort)
    try:
        gate = _step_0_1_slice_validation(solid)
        if gate is not None:
            return gate
    except Exception as e:
        dependency_errors.append(f"0.1: {e}")

    # 0.2 Gesloten-hol → stop bij match
    try:
        result = _step_0_2_hollow_closed(solid)
        if result is not None:
            return result
    except Exception as e:
        dependency_errors.append(f"0.2: {e}")

    # 0.3 Open profiel → stop bij match
    try:
        result = _step_0_3_open_profile(solid, dims)
        if result is not None:
            return result
    except Exception as e:
        dependency_errors.append(f"0.3: {e}")

    # 0.4a Vlakke plaat (stop bij high confidence; fallthrough bij lage confidence)
    try:
        result = _step_0_4a_flat_plate(solid)
        if result is not None:
            return result
    except Exception as e:
        dependency_errors.append(f"0.4a: {e}")

    # 0.4b Constant-dikte open sectie → GEZETTE_PLAAT
    try:
        result = _step_0_4b_constant_thickness_open(solid, dims)
        if result is not None:
            return result
    except Exception as e:
        dependency_errors.append(f"0.4b: {e}")

    # Als kernafhankelijkheden ontbreken (bv. pythonocc-core), val expliciet
    # door naar Step 1 in de legacy-classifier in plaats van hard te falen.
    if dependency_errors:
        joined = " | ".join(dependency_errors)
        return _result(
            label="ANDERS",
            step="0.x",
            method="fallback",
            confidence=0.0,
            fallthrough=True,
            reason=f"STEP0 afhankelijkheden niet beschikbaar: {joined[:220]}",
            features={"step0_dependency_errors": dependency_errors[:5]},
        )

    # 0.5 Massief profiel fallback
    return _step_0_5_solid_profile_fallback(solid, dims, volume)


# ===========================================================================
# GEDETAILLEERDE TRACE — alle stappen met hun criteria
# ===========================================================================

def classify_step0_detailed_trace(solid) -> Dict[str, Any]:
    """Bouw een volledige trace van alle stappen 0.1 t/m 0.5.

    De trace volgt dezelfde beslisvolgorde als classify_step0() en rapporteert
    per stap de individuele criteria met hun actuele meetwaarden.
    """
    dims = _get_bbox_sorted(solid)
    volume = _get_volume(solid)
    smallest, middle, longest = dims
    bbox_volume = smallest * middle * longest
    volume_ratio = volume / bbox_volume if bbox_volume > 0 else 0.0

    steps_trace: list[Dict[str, Any]] = []

    has_section_tools = False
    section_tools_error = ""
    section_context: Optional[Dict[str, Any]] = None

    try:
        from manufacturing_pipeline.analysis.step0_section_tools import (
            find_extrusion_axis,
            solid_vertices_np,
            section_plane_positions_from_vertices,
            slice_solid_to_section,
            dominant_section_cluster,
            normalize_section_polygon,
            extract_section_features,
            section_distance,
            _is_nearly_circle,
            _is_nearly_rectangle,
            match_templates,
            ProfileRegistry,
        )
        import numpy as np
        from shapely.geometry import Polygon as ShapelyPolygon

        has_section_tools = True
    except Exception as exc:
        section_tools_error = str(exc)

    def _build_section_context() -> Dict[str, Any]:
        """Compute axis, sections, dominant cluster and core section once."""
        if not has_section_tools:
            return {"ok": False, "reason": "section tools niet beschikbaar"}

        try:
            axis = find_extrusion_axis(solid)
            if axis is None:
                return {
                    "ok": False,
                    "axis": None,
                    "sections": [],
                    "cluster": [],
                    "cluster_ratio": 0.0,
                    "reason": "geen stabiele extrusieas gevonden",
                }

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

            if len(sections) < 1:
                return {
                    "ok": False,
                    "axis": axis,
                    "sections": sections,
                    "cluster": [],
                    "cluster_ratio": 0.0,
                    "reason": "geen geldige doorsneden",
                }

            cluster = dominant_section_cluster(sections)
            cluster_ratio = len(cluster) / max(len(sections), 1)
            if not cluster:
                return {
                    "ok": False,
                    "axis": axis,
                    "sections": sections,
                    "cluster": cluster,
                    "cluster_ratio": cluster_ratio,
                    "reason": "geen dominant section cluster",
                }

            normalized = [normalize_section_polygon(sec.polygon) for sec in cluster]
            dsum = [
                sum(section_distance(a, b) for j, b in enumerate(normalized) if j != i)
                for i, a in enumerate(normalized)
            ]
            core_sec = cluster[int(np.argmin(dsum))]
            core_features = extract_section_features(core_sec)

            return {
                "ok": True,
                "axis": axis,
                "vertices": vertices,
                "sections": sections,
                "cluster": cluster,
                "cluster_ratio": cluster_ratio,
                "core_section": core_sec,
                "core_features": core_features,
                "core_polygon": core_sec.polygon,
                "reason": "ok",
            }
        except Exception as exc:
            return {
                "ok": False,
                "axis": None,
                "sections": [],
                "cluster": [],
                "cluster_ratio": 0.0,
                "reason": f"section extractie fout: {str(exc)[:120]}",
            }

    # =======================================================================
    # STAP 0.1: Slice-validatie (poort)
    # =======================================================================
    step_01_info = {"step": "0.1", "name": "Slice-validatie", "criteria": []}

    if not has_section_tools:
        step_01_info["criteria"].append(
            {
                "name": "section tools beschikbaar",
                "value": False,
                "expected": True,
                "pass": None,
            }
        )
        step_01_info["verdict"] = "SKIP"
        step_01_info["next"] = "0.2"
        step_01_info["note"] = f"trace zonder section tools: {section_tools_error[:120]}"
        steps_trace.append(step_01_info)
    else:
        section_context = _build_section_context()

        axis_ok = section_context.get("axis") is not None
        sections_count = len(section_context.get("sections", []))
        cluster_ratio = float(section_context.get("cluster_ratio", 0.0))
        core_sec = section_context.get("core_section")
        core_features = section_context.get("core_features")
        vertices_ctx = section_context.get("vertices")

        step_01_info["criteria"].append(
            {
                "name": "stabiele extrusieas gedetecteerd",
                "value": axis_ok,
                "expected": True,
                "pass": axis_ok,
            }
        )
        step_01_info["criteria"].append(
            {
                "name": "minimaal 3 geldige doorsneden",
                "value": sections_count,
                "expected": ">=3",
                "pass": sections_count >= 3,
            }
        )
        step_01_info["criteria"].append(
            {
                "name": f"dominant cluster >= {int(STEP0_CLUSTER_RATIO_MIN*100)}%",
                "value": f"{cluster_ratio:.1%}",
                "expected": f">={STEP0_CLUSTER_RATIO_MIN}",
                "pass": cluster_ratio >= STEP0_CLUSTER_RATIO_MIN,
            }
        )

        round_shaft_check = _evaluate_round_shaft_axial_slice(
            solid=solid,
            axis=section_context.get("axis"),
            vertices=vertices_ctx,
            core_sec=core_sec,
            core_features=core_features,
            slice_solid_to_section_fn=slice_solid_to_section,
        )

        if round_shaft_check.get("applicable"):
            ratio = round_shaft_check.get("ratio")
            threshold = round_shaft_check.get("threshold")
            step_01_info["criteria"].append(
                {
                    "name": "ronde massieve as: axiale area_ratio >= d*L ratio-min",
                    "value": (
                        f"{ratio:.3f} "
                        f"(ax={round_shaft_check.get('axial_area', 0.0):.2f}, "
                        f"exp={round_shaft_check.get('expected_area', 0.0):.2f})"
                    )
                    if ratio is not None
                    else "n.v.t.",
                    "expected": f">={threshold:.3f}",
                    "pass": round_shaft_check.get("passed"),
                }
            )
        else:
            step_01_info["criteria"].append(
                {
                    "name": "ronde massieve as-check",
                    "value": round_shaft_check.get("reason", "n.v.t."),
                    "expected": "alleen van toepassing op ronde assen",
                    "pass": None,
                }
            )

        if not axis_ok:
            step_01_info["verdict"] = "FAIL"
            step_01_info["next"] = "0.2"
            step_01_info["note"] = "geen stabiele extrusieas; section-gedreven Step0-regels niet beslissend, doorval naar 0.2"
            steps_trace.append(step_01_info)

        elif sections_count < 3:
            step_01_info["verdict"] = "FAIL"
            step_01_info["result"] = "ANDERS"
            steps_trace.append(step_01_info)
            return {
                "final_result": _result(
                    label="ANDERS",
                    step="0.1",
                    method="rule",
                    confidence=0.45,
                    fallthrough=False,
                    reason="te weinig geldige doorsneden",
                    features=step_01_info,
                ),
                "steps": steps_trace,
            }

        elif cluster_ratio < STEP0_CLUSTER_RATIO_MIN:
            step_01_info["verdict"] = "FAIL"
            step_01_info["result"] = "ANDERS"
            steps_trace.append(step_01_info)
            return {
                "final_result": _result(
                    label="ANDERS",
                    step="0.1",
                    method="rule",
                    confidence=0.50,
                    fallthrough=False,
                    reason=f"doorsneden niet stabiel langs lengte (cluster {cluster_ratio:.2f})",
                    features=step_01_info,
                ),
                "steps": steps_trace,
            }

        elif round_shaft_check.get("applicable") and round_shaft_check.get("passed") is False:
            ratio = round_shaft_check.get("ratio")
            threshold = round_shaft_check.get("threshold")
            step_01_info["verdict"] = "FAIL"
            step_01_info["result"] = "ANDERS"
            steps_trace.append(step_01_info)
            return {
                "final_result": _result(
                    label="ANDERS",
                    step="0.1",
                    method="rule",
                    confidence=0.65,
                    fallthrough=False,
                    reason=(
                        "ronde massieve as met axiale diameterafname "
                        f"(area_ratio={ratio:.3f} < {threshold:.3f})"
                    ),
                    features={
                        "axial_area_ratio": ratio,
                        "axial_area_ratio_min": threshold,
                        "axis_length": round_shaft_check.get("axis_length"),
                        "diameter_ref": round_shaft_check.get("diameter_ref"),
                    },
                ),
                "steps": steps_trace,
            }

        elif axis_ok:
            step_01_info["verdict"] = "PASS"
            step_01_info["next"] = "0.2"
            steps_trace.append(step_01_info)

    # =======================================================================
    # STAP 0.2: Gesloten-hol (koker/buis)
    # =======================================================================
    step_02_info = {"step": "0.2", "name": "Gesloten-hol (koker/buis)", "criteria": []}

    if not has_section_tools:
        step_02_info["criteria"].append(
            {
                "name": "section tools beschikbaar",
                "value": False,
                "expected": True,
                "pass": None,
            }
        )
        step_02_info["verdict"] = "SKIP"
        step_02_info["next"] = "0.3"
        steps_trace.append(step_02_info)
    else:
        if section_context is None:
            section_context = _build_section_context()

        core_features = section_context.get("core_features")
        core_poly = section_context.get("core_polygon")

        holes = core_features.holes if core_features is not None else None
        effective_holes = holes
        core_sec = section_context.get("core_section")
        outer = None
        inner = None
        used_wire_fallback = False

        if core_poly is not None and len(core_poly.interiors) >= 1:
            outer = ShapelyPolygon(core_poly.exterior.coords)
            inner = ShapelyPolygon(list(core_poly.interiors[0].coords))
        elif core_sec is not None:
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
                    if effective_holes is None:
                        effective_holes = 1
                    else:
                        effective_holes = max(int(effective_holes), 1)
                    used_wire_fallback = True

        step_02_info["criteria"].append(
            {
                "name": "holes == 1",
                "value": effective_holes,
                "expected": 1,
                "pass": (effective_holes == 1) if effective_holes is not None else None,
            }
        )

        is_round = False
        is_rect = False
        is_rect_strict = False
        is_rect_rounded = False
        if effective_holes == 1 and outer is not None and inner is not None:
            is_round = _is_nearly_circle(outer, 0.90, 0.94) and _is_nearly_circle(inner, 0.90, 0.94)
            is_rect_strict = _is_nearly_rectangle(outer) and _is_nearly_rectangle(inner)
            # Afgeronde hoeken (standaard RHS/EN 10219): convexity=1.0 maar bbox_fill < 0.95
            is_rect_rounded = (
                _is_nearly_rectangle(outer, bbox_fill_min=0.85, convexity_min=0.98, rel_tol=0.05)
                and _is_nearly_rectangle(inner, bbox_fill_min=0.88, convexity_min=0.98, rel_tol=0.05)
            )
            if used_wire_fallback and not is_rect_rounded:
                is_rect_rounded = (
                    _is_nearly_rectangle(outer, bbox_fill_min=0.80, convexity_min=0.95, rel_tol=0.08)
                    and _is_nearly_rectangle(inner, bbox_fill_min=0.80, convexity_min=0.95, rel_tol=0.08)
                )
            is_rect = is_rect_strict or is_rect_rounded

        step_02_info["criteria"].append(
            {
                "name": "outer+inner near-circle",
                "value": is_round,
                "expected": True,
                "pass": is_round,
            }
        )
        step_02_info["criteria"].append(
            {
                "name": "outer+inner near-rectangle",
                "value": is_rect,
                "expected": True,
                "pass": is_rect,
            }
        )
        if used_wire_fallback:
            step_02_info["note"] = "wire-loop fallback gebruikt voor hole-detectie"

        if is_round:
            # For round hollow tubes: check if diameter is constant and ends not machined
            machined_check = _check_hollow_tube_consistency(
                solid=solid,
                axis=section_context.get("axis"),
                vertices=section_context.get("vertices"),
                core_sec=core_sec,
            )
            
            if machined_check.get("is_machined"):
                # Stepped/machined ends or high diameter variation → ANDERS
                step_02_info["verdict"] = "MATCH"
                step_02_info["result"] = "ANDERS"
                step_02_info["reason"] = machined_check.get("reason")
                steps_trace.append(step_02_info)
                return {
                    "final_result": _result(
                        label="ANDERS",
                        step="0.2",
                        method="rule",
                        confidence=0.88,
                        fallthrough=False,
                        reason=machined_check.get("reason", "gemaakte uiteinden of variabele diameter"),
                        features={"holes": effective_holes, **machined_check.get("details", {})},
                    ),
                    "steps": steps_trace,
                }

            step_02_info["verdict"] = "MATCH"
            step_02_info["result"] = "RONDE_BUIS"
            steps_trace.append(step_02_info)
            return {
                "final_result": _result(
                    label="RONDE_BUIS",
                    step="0.2",
                    method="rule",
                    confidence=0.99,
                    fallthrough=False,
                    reason="holes==1 + outer/inner near-circle + constante diameter",
                    features={"holes": effective_holes},
                ),
                "steps": steps_trace,
            }

        if is_rect:
            step_02_info["verdict"] = "MATCH"
            step_02_info["result"] = "RECHTHOEKIGE_KOKER"
            steps_trace.append(step_02_info)
            rect_reason = "holes==1 + outer/inner near-rectangle"
            if not is_rect_strict and is_rect_rounded:
                rect_reason = "holes==1 + outer/inner near-rectangle (rounded tolerance)"
            return {
                "final_result": _result(
                    label="RECHTHOEKIGE_KOKER",
                    step="0.2",
                    method="rule",
                    confidence=0.98,
                    fallthrough=False,
                    reason=rect_reason,
                    features={"holes": effective_holes},
                ),
                "steps": steps_trace,
            }

        step_02_info["verdict"] = "FAIL"
        step_02_info["next"] = "0.3"
        steps_trace.append(step_02_info)

    # =======================================================================
    # STAP 0.3: Open profiel (L/U/I/T)
    # =======================================================================
    step_03_info = {"step": "0.3", "name": "Open profiel (L/U/I/T)", "criteria": []}

    if not has_section_tools:
        step_03_info["criteria"].append(
            {
                "name": "section tools beschikbaar",
                "value": False,
                "expected": True,
                "pass": None,
            }
        )
        step_03_info["verdict"] = "SKIP"
        step_03_info["next"] = "0.4a"
        steps_trace.append(step_03_info)
    else:
        if section_context is None:
            section_context = _build_section_context()

        core_features = section_context.get("core_features")
        core_poly = section_context.get("core_polygon")

        holes = core_features.holes if core_features is not None else None
        reentrant = core_features.reentrant_corners if core_features is not None else None
        bent_sheet = _is_bent_sheet_geometry(solid, volume, dims)

        step_03_info["criteria"].append(
            {
                "name": "holes == 0",
                "value": holes,
                "expected": 0,
                "pass": (holes == 0) if holes is not None else None,
            }
        )
        step_03_info["criteria"].append(
            {
                "name": "reentrant_corners > 0",
                "value": reentrant,
                "expected": ">0",
                "pass": (reentrant > 0) if reentrant is not None else None,
            }
        )
        step_03_info["criteria"].append(
            {
                "name": "bent-sheet veto (must be False)",
                "value": bent_sheet,
                "expected": False,
                "pass": not bent_sheet,
            }
        )

        best_family = None
        best_score = None
        template_pass = False
        if core_poly is not None:
            registry = ProfileRegistry().extend_generic_defaults()
            matches = match_templates(core_poly, registry, top_k=5)
            best = matches[0] if matches else None
            if best is not None:
                best_family = best.family
                best_score = best.score
                open_families = {"I_FAMILY", "U_FAMILY", "L_FAMILY", "T_FAMILY"}
                template_pass = best.score <= 0.12 and best.family in open_families

        template_value = (
            f"family={best_family}, score={best_score:.3f}" if best_score is not None else "geen match"
        )
        step_03_info["criteria"].append(
            {
                "name": "template score <= 0.12 in I/U/L/T families",
                "value": template_value,
                "expected": True,
                "pass": template_pass,
            }
        )

        real_03 = _step_0_3_open_profile(solid, dims)
        if real_03 is not None:
            step_03_info["verdict"] = "MATCH"
            step_03_info["result"] = real_03.get("label")
            steps_trace.append(step_03_info)
            return {"final_result": real_03, "steps": steps_trace}

        step_03_info["verdict"] = "FAIL"
        step_03_info["next"] = "0.4a"
        steps_trace.append(step_03_info)

    # =======================================================================
    # STAP 0.4a: Vlakke plaat (high confidence)
    # =======================================================================
    step_04a_info = {"step": "0.4a", "name": "Vlakke plaat (high confidence)", "criteria": []}

    if not has_section_tools:
        step_04a_info["criteria"].append(
            {
                "name": "section tools beschikbaar",
                "value": False,
                "expected": True,
                "pass": None,
            }
        )
        step_04a_info["verdict"] = "SKIP"
        step_04a_info["next"] = "0.4b"
        steps_trace.append(step_04a_info)
    else:
        if section_context is None:
            section_context = _build_section_context()

        core_features = section_context.get("core_features")
        core_poly = section_context.get("core_polygon")

        holes = core_features.holes if core_features is not None else None
        reentrant = core_features.reentrant_corners if core_features is not None else None
        bbox_ratio = core_features.bbox_ratio if core_features is not None else None
        near_rectangle = _is_nearly_rectangle(core_poly) if core_poly is not None else False
        dikte_constant = _is_constant_thickness(solid)

        step_04a_info["criteria"].append(
            {
                "name": "holes == 0",
                "value": holes,
                "expected": 0,
                "pass": (holes == 0) if holes is not None else None,
            }
        )
        step_04a_info["criteria"].append(
            {
                "name": "reentrant_corners == 0",
                "value": reentrant,
                "expected": 0,
                "pass": (reentrant == 0) if reentrant is not None else None,
            }
        )
        step_04a_info["criteria"].append(
            {
                "name": "dikteConstant == true",
                "value": dikte_constant,
                "expected": True,
                "pass": dikte_constant,
            }
        )
        step_04a_info["criteria"].append(
            {
                "name": "near-rectangle (high-confidence gate)",
                "value": near_rectangle,
                "expected": "optioneel",
                "pass": near_rectangle,
            }
        )
        step_04a_info["criteria"].append(
            {
                "name": "bbox_ratio <= 0.30 (high confidence)",
                "value": f"{bbox_ratio:.3f}" if bbox_ratio is not None else None,
                "expected": "<=0.30",
                "pass": (bbox_ratio <= 0.30) if bbox_ratio is not None else None,
            }
        )

        real_04a = _step_0_4a_flat_plate(solid)
        if real_04a is not None:
            step_04a_info["verdict"] = "MATCH"
            step_04a_info["result"] = real_04a.get("label")
            if real_04a.get("fallthrough"):
                step_04a_info["note"] = "lage confidence plaat; classify_step0 markeert fallthrough=True"
            steps_trace.append(step_04a_info)
            return {"final_result": real_04a, "steps": steps_trace}

        step_04a_info["verdict"] = "FAIL"
        step_04a_info["next"] = "0.4b"
        steps_trace.append(step_04a_info)

    # =======================================================================
    # STAP 0.4b: Gezette plaat (constant-dikte open sectie)
    # =======================================================================
    step_04b_info = {"step": "0.4b", "name": "Gezette plaat (constant-dikte open sectie)", "criteria": []}

    holes_04b = None
    reentrant_04b = None
    axis_source_04b = None
    used_alt_axis_04b = False

    if has_section_tools:
        step_04b_eval = _select_step_0_4b_features(solid)
        if step_04b_eval is not None:
            selected_features = step_04b_eval.get("selected_features")
            if selected_features is not None:
                holes_04b = selected_features.holes
                reentrant_04b = selected_features.reentrant_corners
            axis_source_04b = step_04b_eval.get("selected_axis_source")
            used_alt_axis_04b = bool(step_04b_eval.get("used_alternate_axis"))

    dikte_constant = _is_constant_thickness(solid)

    step_04b_info["criteria"].append(
        {
            "name": "holes == 0 (geen gaten in doorsnede)",
            "value": holes_04b,
            "expected": 0,
            "pass": (holes_04b == 0) if holes_04b is not None else None,
        }
    )
    step_04b_info["criteria"].append(
        {
            "name": "reentrant_corners > 0 (concave hoeken)",
            "value": reentrant_04b,
            "expected": ">0",
            "pass": (reentrant_04b > 0) if reentrant_04b is not None else None,
        }
    )
    step_04b_info["criteria"].append(
        {
            "name": "dikteConstant == true",
            "value": dikte_constant,
            "expected": True,
            "pass": dikte_constant,
        }
    )

    real_04b = _step_0_4b_constant_thickness_open(solid, dims)
    if real_04b is not None:
        step_04b_info["verdict"] = "MATCH"
        step_04b_info["result"] = real_04b.get("label")
        if used_alt_axis_04b:
            step_04b_info["note"] = (
                f"alternatieve doorsnede-as gebruikt ({axis_source_04b})"
                if axis_source_04b
                else "alternatieve doorsnede-as gebruikt"
            )
        steps_trace.append(step_04b_info)
        return {"final_result": real_04b, "steps": steps_trace}

    step_04b_info["verdict"] = "FAIL"
    step_04b_info["next"] = "0.5"
    steps_trace.append(step_04b_info)

    # =======================================================================
    # STAP 0.5: Massief profiel fallback
    # =======================================================================
    from manufacturing_pipeline.analysis.classification_variables import (
        PROFILE_SMALLEST_MIN_MM,
        PROFILE_LENGTH_RATIO_MIN,
        PROFILE_CROSS_RATIO_MIN,
        PROFILE_CROSS_RATIO_MAX,
        PROFILE_VOLUME_RATIO_STRONG_MIN,
        PROFILE_VOLUME_RATIO_WEAK_MIN,
        PROFILE_SA_V_RATIO_MAX,
    )

    step_05_info = {"step": "0.5", "name": "Massief profiel fallback", "criteria": []}
    length_ratio = longest / middle if middle > 0 else 0.0
    cross_ratio = middle / smallest if smallest > 0 else 0.0

    step_05_info["criteria"].append(
        {
            "name": "smallest >= PROFILE_SMALLEST_MIN_MM",
            "value": f"{smallest:.2f}",
            "expected": f">={PROFILE_SMALLEST_MIN_MM}",
            "pass": smallest >= PROFILE_SMALLEST_MIN_MM,
        }
    )
    step_05_info["criteria"].append(
        {
            "name": "length_ratio >= PROFILE_LENGTH_RATIO_MIN",
            "value": f"{length_ratio:.3f}",
            "expected": f">={PROFILE_LENGTH_RATIO_MIN}",
            "pass": length_ratio >= PROFILE_LENGTH_RATIO_MIN,
        }
    )
    step_05_info["criteria"].append(
        {
            "name": "PROFILE_CROSS_RATIO_MIN <= cross_ratio <= PROFILE_CROSS_RATIO_MAX",
            "value": f"{cross_ratio:.3f}",
            "expected": f"[{PROFILE_CROSS_RATIO_MIN}, {PROFILE_CROSS_RATIO_MAX}]",
            "pass": PROFILE_CROSS_RATIO_MIN <= cross_ratio <= PROFILE_CROSS_RATIO_MAX,
        }
    )
    step_05_info["criteria"].append(
        {
            "name": "volume_ratio > PROFILE_VOLUME_RATIO_STRONG_MIN",
            "value": f"{volume_ratio:.3f}",
            "expected": f">{PROFILE_VOLUME_RATIO_STRONG_MIN}",
            "pass": volume_ratio > PROFILE_VOLUME_RATIO_STRONG_MIN,
        }
    )
    step_05_info["criteria"].append(
        {
            "name": "volume_ratio >= PROFILE_VOLUME_RATIO_WEAK_MIN",
            "value": f"{volume_ratio:.3f}",
            "expected": f">={PROFILE_VOLUME_RATIO_WEAK_MIN}",
            "pass": volume_ratio >= PROFILE_VOLUME_RATIO_WEAK_MIN,
        }
    )

    sa_v_ratio = None
    if _HAS_OCP and volume > 0:
        try:
            ocp_solid = solid.wrapped if hasattr(solid, "wrapped") else solid
            props = GProp_GProps()
            BRepGProp.SurfaceProperties_s(ocp_solid, props)
            surface_area = float(props.Mass())
            if surface_area > 0:
                sa_v_ratio = surface_area / volume
        except Exception:
            sa_v_ratio = None

    if sa_v_ratio is not None:
        step_05_info["criteria"].append(
            {
                "name": "SA/V < PROFILE_SA_V_RATIO_MAX",
                "value": f"{sa_v_ratio:.3f}",
                "expected": f"<{PROFILE_SA_V_RATIO_MAX}",
                "pass": sa_v_ratio < PROFILE_SA_V_RATIO_MAX,
            }
        )

    final_result = _step_0_5_solid_profile_fallback(solid, dims, volume)
    step_05_info["verdict"] = "MATCH"
    step_05_info["result"] = final_result.get("label")
    steps_trace.append(step_05_info)

    return {"final_result": final_result, "steps": steps_trace}


_get_volume = _geometry_metrics._get_volume
_get_bbox_sorted = _geometry_metrics._get_bbox_sorted
_get_face_areas = _geometry_metrics._get_face_areas
_get_top2_face_percent = _geometry_metrics._get_top2_face_percent
_count_edges_and_large_radius = _geometry_metrics._count_edges_and_large_radius
_count_edges = _geometry_metrics._count_edges
_evaluate_round_shaft_axial_slice = _validation._evaluate_round_shaft_axial_slice
_step_0_1_slice_validation = _validation._step_0_1_slice_validation
_check_hollow_tube_consistency = _hollow_closed._check_hollow_tube_consistency
_step_0_2_hollow_closed = _hollow_closed._step_0_2_hollow_closed
_step_0_3_open_profile = _open_profile._step_0_3_open_profile
_step_0_4a_flat_plate = _plate_rules._step_0_4a_flat_plate
_select_step_0_4b_features = _plate_rules._select_step_0_4b_features
_step_0_4b_constant_thickness_open = _plate_rules._step_0_4b_constant_thickness_open
_step_0_5_solid_profile_fallback = _solid_profile_fallback._step_0_5_solid_profile_fallback


# Compatibility assertions: underscore-prefixed helpers are part of de-facto public surface.
assert _step_0_3_open_profile is _open_profile._step_0_3_open_profile
assert _step_0_4a_flat_plate is _plate_rules._step_0_4a_flat_plate
assert _select_step_0_4b_features is _plate_rules._select_step_0_4b_features
assert _step_0_4b_constant_thickness_open is _plate_rules._step_0_4b_constant_thickness_open
assert _step_0_5_solid_profile_fallback is _solid_profile_fallback._step_0_5_solid_profile_fallback
