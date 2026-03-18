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
  0.4b Constant-dikte open sectie     → GEZETTE_PLAAT of PROFIEL en stop
  0.5  Massief profiel fallback       → PROFIEL of ANDERS

Uitvoer van classify_step0():
    {
        "label":      str,      # RONDE_BUIS|RECHTHOEKIGE_KOKER|PROFIEL|
                                #  PLAAT|GEZETTE_PLAAT|ANDERS
        "step":       str,      # "0.1"|"0.2"|"0.3"|"0.4a"|"0.4b"|"0.5"
        "method":     str,      # "rule"|"template"|"bent_sheet"|"fallback"
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
    STANDARD_TUBE_VOLUME_RATIO_MAX,
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
        props = GProp_GProps()
        BRepGProp.VolumeProperties_s(solid, props)
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
        box = Bnd_Box()
        BRepBndLib.Add_s(solid, box)
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
        exp = TopExp_Explorer(solid, TopAbs_FACE)
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
        edge_count = 0
        large_radius_count = 0
        exp = TopExp_Explorer(solid, TopAbs_EDGE)
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


# ===========================================================================
# Stap 0.1 — Slice-validatie (poort)
# ===========================================================================

def _step_0_1_slice_validation(solid) -> Optional[Step0Result]:
    """Poort: controleer of stabiele extrusie-as en consistente doorsneden bestaan.

    Returns None als OK (doorloopt), Step0Result(ANDERS) als poort faalt.
    """
    try:
        from manufacturing_pipeline.analysis.profile_classifier import (
            find_extrusion_axis,
            solid_vertices_np,
            section_plane_positions_from_vertices,
            slice_solid_to_section,
            dominant_section_cluster,
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
            vertices, axis.direction, (0.20, 0.40, 0.60, 0.80)
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
    if cluster_ratio < 0.60:
        return _result(
            label="ANDERS",
            step="0.1",
            method="rule",
            confidence=0.50,
            fallthrough=False,
            reason=f"doorsneden niet stabiel langs lengte (cluster {cluster_ratio:.2f})",
            features={"cluster_ratio": cluster_ratio},
        )

    # OK — doorloopt
    return None


# ===========================================================================
# Stap 0.2 — Gesloten-hol (buis/koker)
# ===========================================================================

def _step_0_2_hollow_closed(solid) -> Optional[Step0Result]:
    """Detecteer ronde buis of rechthoekige koker via section holes==1."""
    try:
        from manufacturing_pipeline.analysis.profile_classifier import (
            find_extrusion_axis,
            solid_vertices_np,
            section_plane_positions_from_vertices,
            slice_solid_to_section,
            dominant_section_cluster,
            normalize_section_polygon,
            extract_section_features,
            _is_nearly_circle,
            _is_nearly_rectangle,
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
            vertices, axis.direction, (0.20, 0.40, 0.60, 0.80)
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
    from manufacturing_pipeline.analysis.profile_classifier import section_distance
    import numpy as np
    normalized = [normalize_section_polygon(sec.polygon) for sec in cluster]
    dsum = [sum(section_distance(a, b) for j, b in enumerate(normalized) if j != i)
            for i, a in enumerate(normalized)]
    core_poly = cluster[int(np.argmin(dsum))].polygon

    features = extract_section_features(cluster[int(np.argmin(dsum))])
    if features.holes != 1:
        return None

    outer = ShapelyPolygon(core_poly.exterior.coords)
    inner = ShapelyPolygon(list(core_poly.interiors[0].coords))

    if _is_nearly_circle(outer, 0.90, 0.94) and _is_nearly_circle(inner, 0.90, 0.94):
        return _result(
            label="RONDE_BUIS",
            step="0.2",
            method="rule",
            confidence=0.99,
            fallthrough=False,
            reason="holes==1 + outer/inner near-circle",
            features={"holes": 1},
        )

    if _is_nearly_rectangle(outer) and _is_nearly_rectangle(inner):
        return _result(
            label="RECHTHOEKIGE_KOKER",
            step="0.2",
            method="rule",
            confidence=0.98,
            fallthrough=False,
            reason="holes==1 + outer/inner near-rectangle",
            features={"holes": 1},
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
        from manufacturing_pipeline.analysis.profile_classifier import (
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
            vertices, axis.direction, (0.20, 0.40, 0.60, 0.80)
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
        from manufacturing_pipeline.analysis.profile_classifier import (
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
            vertices, axis.direction, (0.20, 0.40, 0.60, 0.80)
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
    """Scheidt constant-dikte open secties in GEZETTE_PLAAT of PROFIEL.

    Criteria:
      holes == 0, reentrant_corners > 0, dikteConstant == True

    Beslissing: _is_bent_sheet_geometry
      True  → GEZETTE_PLAAT
      False → PROFIEL
    """
    try:
        from manufacturing_pipeline.analysis.profile_classifier import (
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
            vertices, axis.direction, (0.20, 0.40, 0.60, 0.80)
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

    # Selectie-criteria voor 0.4b
    if features.holes != 0 or features.reentrant_corners == 0:
        return None
    if not _is_constant_thickness(solid):
        return None

    volume = _get_volume(solid)
    if _is_bent_sheet_geometry(solid, volume, dims):
        return _result(
            label="GEZETTE_PLAAT",
            step="0.4b",
            method="bent_sheet",
            confidence=0.88,
            fallthrough=False,
            reason="constant-dikte open sectie + bent_sheet positief → GEZETTE_PLAAT",
            features={"reentrant_corners": features.reentrant_corners},
        )
    else:
        return _result(
            label="PROFIEL",
            step="0.4b",
            method="rule",
            confidence=0.82,
            fallthrough=False,
            reason="constant-dikte open sectie + bent_sheet negatief → PROFIEL",
            features={"reentrant_corners": features.reentrant_corners},
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
                features={"volume_ratio": volume_ratio, "length_ratio": length_ratio},
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

    # 0.1 Slice-validatie (poort)
    gate = _step_0_1_slice_validation(solid)
    if gate is not None:
        return gate

    # 0.2 Gesloten-hol → stop bij match
    result = _step_0_2_hollow_closed(solid)
    if result is not None:
        return result

    # 0.3 Open profiel → stop bij match
    result = _step_0_3_open_profile(solid, dims)
    if result is not None:
        return result

    # 0.4a Vlakke plaat (stop bij high confidence; fallthrough bij lage confidence)
    result = _step_0_4a_flat_plate(solid)
    if result is not None:
        return result

    # 0.4b Constant-dikte open sectie → GEZETTE_PLAAT of PROFIEL
    result = _step_0_4b_constant_thickness_open(solid, dims)
    if result is not None:
        return result

    # 0.5 Massief profiel fallback
    return _step_0_5_solid_profile_fallback(solid, dims, volume)
