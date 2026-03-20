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

# ---------------------------------------------------------------------------
# Type alias
# ---------------------------------------------------------------------------
Step0Result = Dict[str, Any]


# ===========================================================================
# Privé helpers — geometrische metingen
# ===========================================================================

def _get_volume(solid) -> float:
    """Volume in mm³ via OCP mass properties."""
    if not _HAS_OCP:
        return 0.0
    try:
        # Convert CadQuery solid to OCP shape if needed
        ocp_solid = solid.wrapped if hasattr(solid, 'wrapped') else solid
        props = GProp_GProps()
        BRepGProp.VolumeProperties_s(ocp_solid, props)
        return float(props.Mass())
    except Exception:
        return 0.0


def _get_bbox_sorted(solid) -> Tuple[float, float, float]:
    """Gesorteerde bounding box [kleinste, midden, grootste] in mm."""
    if not _HAS_OCP:
        return (0.0, 0.0, 0.0)
    try:
        from OCP.BRep import BRep_Builder
        from OCP.Bnd import Bnd_Box
        from OCP.BRepBndLib import BRepBndLib
        
        # Convert CadQuery solid to OCP shape if needed
        ocp_solid = solid.wrapped if hasattr(solid, 'wrapped') else solid
        box = Bnd_Box()
        BRepBndLib.Add_s(ocp_solid, box)
        xmin, ymin, zmin, xmax, ymax, zmax = box.Get()
        dims = sorted([abs(xmax - xmin), abs(ymax - ymin), abs(zmax - zmin)])
        return (dims[0], dims[1], dims[2])
    except Exception:
        return (0.0, 0.0, 0.0)


def _get_face_areas(solid) -> list[float]:
    """Lijst van vlakoppervlaktes voor alle faces (mm²)."""
    areas: list[float] = []
    if not _HAS_OCP:
        return areas
    try:
        # Convert CadQuery solid to OCP shape if needed
        ocp_solid = solid.wrapped if hasattr(solid, 'wrapped') else solid
        exp = TopExp_Explorer(ocp_solid, TopAbs_FACE)
        while exp.More():
            face = TopoDS.Face_s(exp.Current())
            props = GProp_GProps()
            BRepGProp.SurfaceProperties_s(face, props)
            areas.append(float(props.Mass()))
            exp.Next()
    except Exception:
        pass
    return areas


def _get_top2_face_percent(solid) -> float:
    """Percentage oppervlak gedekt door de twee grootste faces."""
    areas = _get_face_areas(solid)
    if not areas:
        return 0.0
    total = sum(areas)
    if total == 0:
        return 0.0
    top2 = sum(sorted(areas, reverse=True)[:2])
    return 100.0 * top2 / total


def _count_edges_and_large_radius(solid) -> Tuple[int, int]:
    """Tel edges en edges met grote boogstraal (buiging >= BENT_SHEET_LARGE_RADIUS_MIN_MM).

    Returns:
        (edge_count, large_radius_count)
    """
    if not _HAS_OCP:
        return (0, 0)
    try:
        from OCP.BRepAdaptor import BRepAdaptor_Curve
        from OCP.GeomAbs import GeomAbs_Circle
        
        # Convert CadQuery solid to OCP shape if needed
        ocp_solid = solid.wrapped if hasattr(solid, 'wrapped') else solid
        edge_count = 0
        large_radius_count = 0
        exp = TopExp_Explorer(ocp_solid, TopAbs_EDGE)
        while exp.More():
            edge_count += 1
            edge = TopoDS.Edge_s(exp.Current())
            adapter = BRepAdaptor_Curve(edge)
            if adapter.GetType() == GeomAbs_Circle:
                radius = adapter.Circle().Radius()
                if radius >= BENT_SHEET_LARGE_RADIUS_MIN_MM:
                    large_radius_count += 1
            exp.Next()
        return edge_count, large_radius_count
    except Exception:
        return (0, 0)


def _count_edges(solid) -> int:
    """Tel alleen het aantal edges in het solid."""
    if not _HAS_OCP:
        return 0
    try:
        # Convert CadQuery solid to OCP shape if needed
        ocp_solid = solid.wrapped if hasattr(solid, 'wrapped') else solid
        edge_count = 0
        exp = TopExp_Explorer(ocp_solid, TopAbs_EDGE)
        while exp.More():
            edge_count += 1
            exp.Next()
        return edge_count
    except Exception:
        return 0


# ===========================================================================
# Privé helpers — drempelwaarde logica
# ===========================================================================

def _is_bent_sheet_geometry(solid, volume: float, dims: Tuple[float, float, float]) -> bool:
    """Detecteer gezette / gevouwen plaat (niet massief, niet buisachtig).

    Criteria (conform _detect_bent_sheet in assembly_analysis.py):
      1. Dunne material (smallest <= BENT_SHEET_THICKNESS_MAX_MM)
      2. Voldoende edges (edge_count >= BENT_SHEET_MIN_EDGE_COUNT)
      3. Volume-ratio in correct bereik
      4. Top2-faces niet te dominant
      5. Gebogen aspect (elongated)
      6. Exclusie: lange koker-achtige secties
      7. Exclusie: perfecte cirkelronde/vierkante doorsnede
    """
    if not _HAS_OCP:
        return False
    smallest, middle, longest = dims
    if smallest > BENT_SHEET_THICKNESS_MAX_MM:
        return False

    edge_count, _ = _count_edges_and_large_radius(solid)
    if edge_count < BENT_SHEET_MIN_EDGE_COUNT:
        return False

    bbox_volume = smallest * middle * longest
    volume_ratio = volume / bbox_volume if bbox_volume > 0 else 0.0
    if not (BENT_SHEET_VOLUME_RATIO_MIN <= volume_ratio <= BENT_SHEET_VOLUME_RATIO_MAX):
        return False

    top2_pct = _get_top2_face_percent(solid)
    if top2_pct > BENT_SHEET_TOP2_FACES_MAX_PCT:
        return False

    aspect_ratio = longest / smallest if smallest > 0 else 0.0
    if aspect_ratio < BENT_SHEET_ASPECT_RATIO_MIN:
        return False

    # Exclusie: kokerachtige lange rechthoekige secties
    profile_cross_ratio = middle / smallest if smallest > 0 else 0.0
    profile_length_ratio = longest / middle if middle > 0 else 0.0
    if (
        smallest >= PLATE_THICK_MAX_MM
        and profile_length_ratio >= PROFILE_LENGTH_RATIO_MIN
        and PROFILE_CROSS_RATIO_MIN <= profile_cross_ratio <= PROFILE_CROSS_RATIO_MAX
        and volume_ratio <= STANDARD_TUBE_VOLUME_RATIO_MAX
    ):
        return False

    # Exclusie: perfecte vierkante/ronde doorsnede
    bent_cross_ratio = smallest / middle if middle > 0 else 0.0
    if abs(bent_cross_ratio - 1.0) < 0.05:
        return False

    return True


def _is_constant_thickness(solid) -> bool:
    """Proxy voor dikteConstant.

    Constant = niet variabele wanddikte.
    Anders gezegd: de twee grootste vlakken van het solid hebben NIET
    een significant verschil in oppervlak.

    Gebaseerd op _detect_variable_thickness (assembly_analysis.py:690–748).
    """
    if not _HAS_OCP:
        return True  # conservatief: aanname constant
    areas = sorted(_get_face_areas(solid), reverse=True)
    if len(areas) < 2:
        return True
    top_area = areas[0]
    if top_area == 0:
        return True
    from manufacturing_pipeline.analysis.classification_variables import (
        STANDARD_PROFILE_FACE_AREA_TOLERANCE,
    )
    area_diff = abs(top_area - areas[1]) / top_area
    return area_diff <= STANDARD_PROFILE_FACE_AREA_TOLERANCE


def _evaluate_round_shaft_axial_slice(
    *,
    solid,
    axis,
    vertices,
    core_sec,
    core_features,
    slice_solid_to_section_fn,
) -> Dict[str, Any]:
    """Check round solid shaft machining via longitudinal slice area ratio.

    Only applicable to round (circular) core cross-sections.

    Dmax is determined by sampling cross-sections including near-end positions
    (0%/100%) to capture shoulders and diameter steps caused by turning.

    The criterion is:
        A_axial / (Dmax × L) >= ROUND_SHAFT_AXIAL_AREA_RATIO_MIN

    A significantly lower ratio indicates machined/stepped geometry → ANDERS.
    Both basis_u and basis_v are tried for the axial slice; the larger valid
    area is used.
    """
    result: Dict[str, Any] = {
        "applicable": False,
        "passed": None,
        "ratio": None,
        "threshold": ROUND_SHAFT_AXIAL_AREA_RATIO_MIN,
        "reason": "n.v.t.",
    }

    if core_sec is None or core_features is None or axis is None or vertices is None:
        return result

    if core_features.holes != 0 or core_features.reentrant_corners != 0:
        result["reason"] = "geen massieve ronde kernsectie"
        return result

    # Only applicable to round (circular) core cross-sections
    if core_features.compactness < ROUND_SHAFT_CORE_COMPACTNESS_MIN:
        result["reason"] = "kernsectie onvoldoende rond (compactness)"
        return result

    if core_features.bbox_ratio < ROUND_SHAFT_CORE_BBOX_RATIO_MIN:
        result["reason"] = "kernsectie onvoldoende rond (bbox_ratio)"
        return result

    try:
        import numpy as np

        projection = np.asarray(vertices, dtype=float) @ axis.direction
        axis_length = float(np.max(projection) - np.min(projection))
    except Exception:
        result["reason"] = "lengteprojectie niet beschikbaar"
        return result

    if axis_length <= 0:
        result["reason"] = "ongeldige lengte"
        return result

    # --- Dmax: sample cross-sections including near-end positions (0%/100%) ---
    # This detects shoulders and diameter steps at turned ends.
    dmax = 0.0
    try:
        from manufacturing_pipeline.analysis.step0_section_tools import (
            section_plane_positions_from_vertices,
        )

        # Fractions from near-0% to near-100% — captures end-zone geometry
        end_fracs = (0.02, 0.05, 0.10, 0.20, 0.35, 0.50, 0.65, 0.80, 0.90, 0.95, 0.98)
        end_positions = section_plane_positions_from_vertices(
            vertices, axis.direction, end_fracs
        )
        for pos in end_positions:
            sec = slice_solid_to_section_fn(
                solid,
                plane_origin=axis.direction * pos,
                plane_normal=axis.direction,
                section_position=pos,
            )
            if sec is None or sec.polygon.area <= 0:
                continue
            # Use outer bounding-box dimension — unaffected by holes/threads
            minx, miny, maxx, maxy = sec.polygon.bounds
            dim = float(max(maxx - minx, maxy - miny))
            if dim > dmax:
                dmax = dim
    except Exception as exc:
        logger.debug("Dmax sampling fout: %s", exc)

    if dmax <= 0:
        # Fallback to core cross-section bounds
        minx, miny, maxx, maxy = core_sec.polygon.bounds
        dmax = float(max(maxx - minx, maxy - miny))

    if dmax <= 0:
        result["reason"] = "ongeldige diameter"
        return result

    length_ratio = axis_length / dmax
    if length_ratio < ROUND_SHAFT_MIN_LENGTH_RATIO:
        result["reason"] = "niet lang genoeg voor as-check"
        return result

    result["applicable"] = True

    # --- Axial slice: try basis_u first, fall back to basis_v if None ---
    # We do NOT take the maximum — basis_u is the primary direction for consistency.
    # basis_v is only used when basis_u gives no usable section.
    axial_area: Optional[float] = None
    for normal_vec in (core_sec.basis_u, core_sec.basis_v):
        try:
            axial_sec = slice_solid_to_section_fn(
                solid,
                plane_origin=axis.origin,
                plane_normal=normal_vec,
                section_position=0.0,
            )
        except Exception as exc:
            logger.debug("Axiale slice fout: %s", exc)
            continue
        if axial_sec is None or axial_sec.polygon.area <= 0:
            continue
        axial_area = float(axial_sec.polygon.area)
        break  # use first valid result (basis_u preferred)

    if axial_area is None:
        result["reason"] = "geen geldige axiale doorsnede (basis_u en basis_v beiden mislukt)"
        return result

    expected_area = float(dmax * axis_length)
    ratio = axial_area / max(expected_area, 1e-9)
    passed = ratio >= ROUND_SHAFT_AXIAL_AREA_RATIO_MIN

    result.update(
        {
            "passed": passed,
            "ratio": ratio,
            "axial_area": axial_area,
            "expected_area": expected_area,
            "axis_length": axis_length,
            "diameter_ref": dmax,
            "length_ratio": length_ratio,
            "reason": "ok" if passed else "axiale doorsnede te klein voor onbewerkte ronde as",
        }
    )
    return result


# ===========================================================================
# Stap 0.1 — Slice-validatie (poort)
# ===========================================================================

def _step_0_1_slice_validation(solid) -> Optional[Step0Result]:
    """Poort: controleer of stabiele extrusie-as en consistente doorsneden bestaan.

    Returns None als OK (doorloopt), Step0Result(ANDERS) als poort faalt.
    """
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
        )
    except ImportError:
        # profile_classifier niet beschikbaar; poort overslaan
        return None

    axis = find_extrusion_axis(solid)
    if axis is None:
        return _result(
            label="ANDERS",
            step="0.1",
            method="rule",
            confidence=0.40,
            fallthrough=False,
            reason="geen stabiele extrusie-as gevonden",
        )

    try:
        vertices = solid_vertices_np(solid)
        positions = section_plane_positions_from_vertices(
            vertices, axis.direction, (0.20, 0.35, 0.50, 0.65, 0.80)
        )
        sections = []
        for s in positions:
            sec = slice_solid_to_section(
                solid,
                plane_origin=axis.direction * s,
                plane_normal=axis.direction,
                section_position=s,
            )
            if sec is not None and sec.polygon.area > 0:
                sections.append(sec)
    except Exception as e:
        logger.debug("Slice-validatie fout: %s", e)
        return None  # poort overslaan bij onverwachte fout

    if len(sections) < 3:
        return _result(
            label="ANDERS",
            step="0.1",
            method="rule",
            confidence=0.45,
            fallthrough=False,
            reason="te weinig geldige doorsneden",
        )

    cluster = dominant_section_cluster(sections)
    cluster_ratio = len(cluster) / max(len(sections), 1)
    if cluster_ratio < STEP0_CLUSTER_RATIO_MIN:
        return _result(
            label="ANDERS",
            step="0.1",
            method="rule",
            confidence=0.50,
            fallthrough=False,
            reason=f"doorsneden niet stabiel langs lengte (cluster {cluster_ratio:.2f})",
            features={"cluster_ratio": cluster_ratio},
        )

    # Extra poort voor ronde massieve assen:
    # detecteer diameterafname (afgedraaide/bewerkte einden) via axiale slice.
    try:
        import numpy as np

        normalized = [normalize_section_polygon(sec.polygon) for sec in cluster]
        dsum = [
            sum(section_distance(a, b) for j, b in enumerate(normalized) if j != i)
            for i, a in enumerate(normalized)
        ]
        core_sec = cluster[int(np.argmin(dsum))]
        core_features = extract_section_features(core_sec)

        round_shaft_check = _evaluate_round_shaft_axial_slice(
            solid=solid,
            axis=axis,
            vertices=vertices,
            core_sec=core_sec,
            core_features=core_features,
            slice_solid_to_section_fn=slice_solid_to_section,
        )

        if round_shaft_check.get("applicable") and round_shaft_check.get("passed") is False:
            ratio = round_shaft_check.get("ratio")
            threshold = round_shaft_check.get("threshold")
            return _result(
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
            )
    except Exception as e:
        logger.debug("Ronde-as axial slice check overgeslagen: %s", e)

    # OK — doorloopt
    return None


# ===========================================================================
# Stap 0.2 — Gesloten-hol (buis/koker)
# ===========================================================================

def _step_0_2_hollow_closed(solid) -> Optional[Step0Result]:
    """Detecteer ronde buis of rechthoekige koker via section holes==1."""
    try:
        from manufacturing_pipeline.analysis.step0_section_tools import (
            find_extrusion_axis,
            solid_vertices_np,
            section_plane_positions_from_vertices,
            slice_solid_to_section,
            dominant_section_cluster,
            normalize_section_polygon,
            extract_section_features,
            _is_nearly_circle,
            _is_nearly_rectangle,
            section_distance,
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
        for s in positions:
            sec = slice_solid_to_section(
                solid,
                plane_origin=axis.direction * s,
                plane_normal=axis.direction,
                section_position=s,
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

    # Gebruik mediatoon van het cluster als representatieve doorsnede
    import numpy as np
    normalized = [normalize_section_polygon(sec.polygon) for sec in cluster]
    dsum = [
        sum(section_distance(a, b) for j, b in enumerate(normalized) if j != i)
        for i, a in enumerate(normalized)
    ]
    core_sec = cluster[int(np.argmin(dsum))]
    core_poly = core_sec.polygon

    features = extract_section_features(core_sec)
    effective_holes = features.holes
    outer = None
    inner = None
    used_wire_fallback = False

    # Primaire pad: hole zit correct in de samengestelde polygon.
    if core_poly is not None and len(core_poly.interiors) >= 1:
        outer = ShapelyPolygon(core_poly.exterior.coords)
        inner = ShapelyPolygon(list(core_poly.interiors[0].coords))
    else:
        # Fallback: gebruik de ruwe wire-loops wanneer polygon-hole reconstructie
        # faalt op afgeronde kokers (self-intersecting shell artefacten).
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
        return _result(
            label="RONDE_BUIS",
            step="0.2",
            method="rule",
            confidence=0.99,
            fallthrough=False,
            reason="holes==1 + outer/inner near-circle",
            features={"holes": effective_holes},
        )

    is_rect_strict = _is_nearly_rectangle(outer) and _is_nearly_rectangle(inner)
    is_rect_rounded = False
    if used_wire_fallback:
        is_rect_rounded = (
            _is_nearly_rectangle(outer, bbox_fill_min=0.85, convexity_min=0.95, rel_tol=0.05)
            and _is_nearly_rectangle(inner, bbox_fill_min=0.85, convexity_min=0.95, rel_tol=0.05)
        )

    if is_rect_strict or is_rect_rounded:
        rect_reason = "holes==1 + outer/inner near-rectangle"
        if not is_rect_strict and is_rect_rounded:
            rect_reason = "holes==1 + outer/inner near-rectangle (rounded tolerance)"
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


# ===========================================================================
# Stap 0.3 — Open profiel (L/U/I/T)
# ===========================================================================

def _step_0_3_open_profile(solid, dims: Tuple[float, float, float]) -> Optional[Step0Result]:
    """Detecteer open concave profielen (I/U/L/T) via template-matching.

    Veto: _is_bent_sheet_geometry sluit gezette plaat uit.
    """
    try:
        from manufacturing_pipeline.analysis.step0_section_tools import (
            find_extrusion_axis,
            solid_vertices_np,
            section_plane_positions_from_vertices,
            slice_solid_to_section,
            dominant_section_cluster,
            normalize_section_polygon,
            extract_section_features,
            count_reentrant_corners,
            section_distance,
            match_templates,
            ProfileRegistry,
        )
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
        for s in positions:
            sec = slice_solid_to_section(
                solid,
                plane_origin=axis.direction * s,
                plane_normal=axis.direction,
                section_position=s,
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
    dsum = [sum(section_distance(a, b) for j, b in enumerate(normalized) if j != i)
            for i, a in enumerate(normalized)]
    core_idx = int(np.argmin(dsum))
    core_sec = cluster[core_idx]
    core_poly = core_sec.polygon

    features = extract_section_features(core_sec)

    # Primaire criteria: geen gat, wél reentrant corners
    if features.holes != 0 or features.reentrant_corners == 0:
        return None

    # Bent-sheet veto
    volume = _get_volume(solid)
    if _is_bent_sheet_geometry(solid, volume, dims):
        return None

    # Template matching (I/U/L/T families)
    registry = ProfileRegistry().extend_generic_defaults()
    matches = match_templates(core_poly, registry, top_k=5)
    best = matches[0] if matches else None

    _OPEN_FAMILIES = {"I_FAMILY", "U_FAMILY", "L_FAMILY", "T_FAMILY"}
    if best and best.score <= 0.12 and best.family in _OPEN_FAMILIES:
        confidence = max(0.50, 1.0 - min(best.score / 0.12, 1.0))
        return _result(
            label="PROFIEL",
            step="0.3",
            method="template",
            confidence=confidence,
            fallthrough=False,
            reason=f"open profiel family={best.family} score={best.score:.3f}",
            features={"template_family": best.family, "template_score": best.score,
                      "reentrant_corners": features.reentrant_corners},
        )

    return None


# ===========================================================================
# Stap 0.4a — Vlakke plaat (high confidence)
# ===========================================================================

def _step_0_4a_flat_plate(solid) -> Optional[Step0Result]:
    """Detecteer vlakke plaat via holes==0, near-rectangle, bbox_ratio.

    High confidence path: stopt direct.
    Lage confidence: geeft fallthrough=True zodat Step 1 verder kan.
    """
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
            _is_nearly_rectangle,
        )
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
        for s in positions:
            sec = slice_solid_to_section(
                solid,
                plane_origin=axis.direction * s,
                plane_normal=axis.direction,
                section_position=s,
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
    dsum = [sum(section_distance(a, b) for j, b in enumerate(normalized) if j != i)
            for i, a in enumerate(normalized)]
    core_sec = cluster[int(np.argmin(dsum))]
    core_poly = core_sec.polygon
    features = extract_section_features(core_sec)

    if features.holes != 0:
        return None

    if not _is_nearly_rectangle(core_poly):
        return None

    # High confidence: near-rectangle + bbox_ratio <= 0.30
    if features.bbox_ratio <= 0.30:
        return _result(
            label="PLAAT",
            step="0.4a",
            method="rule",
            confidence=0.98,
            fallthrough=False,
            reason=f"vlakke plaat high confidence (bbox_ratio={features.bbox_ratio:.3f})",
            features={"bbox_ratio": features.bbox_ratio, "holes": 0},
        )

    # Lagere confidence: near-rectangle maar dikkere sectie → door naar Step 1
    return _result(
        label="PLAAT",
        step="0.4a",
        method="rule",
        confidence=0.65,
        fallthrough=True,
        reason=f"vlakke plaat lage confidence (bbox_ratio={features.bbox_ratio:.3f}) → Step 1",
        features={"bbox_ratio": features.bbox_ratio, "holes": 0},
    )


# ===========================================================================
# Stap 0.4b — Constant-dikte open sectie
# ===========================================================================

def _step_0_4b_constant_thickness_open(
    solid, dims: Tuple[float, float, float]
) -> Optional[Step0Result]:
    """Classificeert constant-dikte open secties als GEZETTE_PLAAT.

    Criteria:
      holes == 0, reentrant_corners > 0, dikteConstant == True
    
    Note: gebruikt OCP-native section tools, niet profile_classifier.py.
    """
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
        )
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
        for s in positions:
            sec = slice_solid_to_section(
                solid,
                plane_origin=axis.direction * s,
                plane_normal=axis.direction,
                section_position=s,
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
    dsum = [sum(section_distance(a, b) for j, b in enumerate(normalized) if j != i)
            for i, a in enumerate(normalized)]
    core_sec = cluster[int(np.argmin(dsum))]
    features = extract_section_features(core_sec)

    if features.holes != 0 or features.reentrant_corners == 0:
        return None

    if not _is_constant_thickness(solid):
        return None

    smallest, middle, longest = dims
    return _result(
        label="GEZETTE_PLAAT",
        step="0.4b",
        method="rule",
        confidence=0.88,
        fallthrough=False,
        reason="holes==0 + reentrant_corners>0 + dikteConstant",
        features={
            "holes": features.holes,
            "reentrant_corners": features.reentrant_corners,
            "smallest": smallest,
            "middle": middle,
            "longest": longest,
        },
    )


# ===========================================================================
# Stap 0.5 — Massief profiel fallback
# ===========================================================================

def _step_0_5_solid_profile_fallback(
    solid, dims: Tuple[float, float, float], volume: float
) -> Step0Result:
    """Massief rechthoekig balk/profiel via dimensie-eigenschappen.

    Gebaseerd op Step 2 in classify_solid (assembly_analysis.py:1398-1408).
    """
    from manufacturing_pipeline.analysis.classification_variables import (
        PROFILE_SMALLEST_MIN_MM,
        PROFILE_LENGTH_RATIO_MIN,
        PROFILE_CROSS_RATIO_MIN,
        PROFILE_CROSS_RATIO_MAX,
        PROFILE_VOLUME_RATIO_STRONG_MIN,
        PROFILE_VOLUME_RATIO_WEAK_MIN,
        PROFILE_SA_V_RATIO_MAX,
    )

    smallest, middle, longest = dims
    bbox_volume = smallest * middle * longest
    volume_ratio = volume / bbox_volume if bbox_volume > 0 else 0.0
    length_ratio = longest / middle if middle > 0 else 0.0
    cross_ratio = middle / smallest if smallest > 0 else 0.0

    if (
        smallest >= PROFILE_SMALLEST_MIN_MM
        and length_ratio >= PROFILE_LENGTH_RATIO_MIN
        and PROFILE_CROSS_RATIO_MIN <= cross_ratio <= PROFILE_CROSS_RATIO_MAX
    ):
        if volume_ratio > PROFILE_VOLUME_RATIO_STRONG_MIN:
            return _result(
                label="PROFIEL",
                step="0.5",
                method="fallback",
                confidence=0.78,
                fallthrough=False,
                reason=f"massief profiel fallback (vol_ratio={volume_ratio:.3f} sterk)",
        # section tools niet beschikbaar; poort overslaan
            )

        # Zwakke match: bevestig met SA/V tiebreaker
        if volume_ratio >= PROFILE_VOLUME_RATIO_WEAK_MIN:
            try:
                if _HAS_OCP:
                    props = GProp_GProps()
                    BRepGProp.SurfaceProperties_s(solid, props)
                    surface_area = float(props.Mass())
                    if surface_area > 0 and volume > 0:
                        sa_v_ratio = surface_area / volume
                        if sa_v_ratio < PROFILE_SA_V_RATIO_MAX:
                            return _result(
                                label="PROFIEL",
                                step="0.5",
                                method="fallback",
                                confidence=0.70,
                                fallthrough=False,
                                reason=f"massief profiel SA/V tiebreaker ({sa_v_ratio:.3f})",
                                features={
                                    "volume_ratio": volume_ratio,
                                    "sa_v_ratio": sa_v_ratio,
                                },
                            )
            except Exception:
                pass

    return _result(
        label="ANDERS",
        step="0.5",
        method="fallback",
        confidence=0.55,
        fallthrough=False,
        reason="geen classificatie gevonden in STEP 0",
    )


# ===========================================================================
# Helper: bouw resultaat-dict
# ===========================================================================

def _result(
    *,
    label: str,
    step: str,
    method: str,
    confidence: float,
    fallthrough: bool,
    reason: str,
    features: Optional[Dict[str, Any]] = None,
) -> Step0Result:
    return {
        "label": label,
        "step": step,
        "method": method,
        "confidence": confidence,
        "fallthrough": fallthrough,
        "reason": reason,
        "features": features or {},
    }


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
            step_01_info["result"] = "ANDERS"
            steps_trace.append(step_01_info)
            return {
                "final_result": _result(
                    label="ANDERS",
                    step="0.1",
                    method="rule",
                    confidence=0.40,
                    fallthrough=False,
                    reason="geen stabiele extrusieas gevonden",
                    features=step_01_info,
                ),
                "steps": steps_trace,
            }

        if sections_count < 3:
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

        if cluster_ratio < STEP0_CLUSTER_RATIO_MIN:
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

        if round_shaft_check.get("applicable") and round_shaft_check.get("passed") is False:
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
            if used_wire_fallback:
                is_rect_rounded = (
                    _is_nearly_rectangle(outer, bbox_fill_min=0.85, convexity_min=0.95, rel_tol=0.05)
                    and _is_nearly_rectangle(inner, bbox_fill_min=0.85, convexity_min=0.95, rel_tol=0.05)
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
                    reason="holes==1 + outer/inner near-circle",
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
        bbox_ratio = core_features.bbox_ratio if core_features is not None else None
        near_rectangle = _is_nearly_rectangle(core_poly) if core_poly is not None else False

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
                "name": "near-rectangle",
                "value": near_rectangle,
                "expected": True,
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
    if has_section_tools:
        if section_context is None:
            section_context = _build_section_context()
        core_features = section_context.get("core_features")
        if core_features is not None:
            holes_04b = core_features.holes
            reentrant_04b = core_features.reentrant_corners

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
