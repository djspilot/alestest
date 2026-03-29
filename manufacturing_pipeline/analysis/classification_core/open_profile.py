from __future__ import annotations

from typing import Optional, Tuple

from manufacturing_pipeline.analysis.classification_variables import (
    BENT_SHEET_ASPECT_RATIO_MIN,
    BENT_SHEET_MIN_EDGE_COUNT,
    BENT_SHEET_THICKNESS_MAX_MM,
    BENT_SHEET_TOP2_FACES_MAX_PCT,
    BENT_SHEET_VOLUME_RATIO_MAX,
    BENT_SHEET_VOLUME_RATIO_MIN,
    PLATE_THICK_MAX_MM,
    PROFILE_CROSS_RATIO_MAX,
    PROFILE_CROSS_RATIO_MIN,
    PROFILE_LENGTH_RATIO_MIN,
    STANDARD_TUBE_VOLUME_RATIO_MAX,
)
from manufacturing_pipeline.analysis.classification_core.geometry_metrics import (
    _count_edges_and_large_radius,
    _get_top2_face_percent,
    _get_volume,
)
from manufacturing_pipeline.analysis.classification_core.result_types import Step0Result, _result

try:
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopAbs import TopAbs_EDGE

    _HAS_OCP = True
except ImportError:
    _HAS_OCP = False


def _is_bent_sheet_geometry(solid, volume: float, dims: Tuple[float, float, float]) -> bool:
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

    profile_cross_ratio = middle / smallest if smallest > 0 else 0.0
    profile_length_ratio = longest / middle if middle > 0 else 0.0
    if (
        smallest >= PLATE_THICK_MAX_MM
        and profile_length_ratio >= PROFILE_LENGTH_RATIO_MIN
        and PROFILE_CROSS_RATIO_MIN <= profile_cross_ratio <= PROFILE_CROSS_RATIO_MAX
        and volume_ratio <= STANDARD_TUBE_VOLUME_RATIO_MAX
    ):
        return False

    bent_cross_ratio = smallest / middle if middle > 0 else 0.0
    if abs(bent_cross_ratio - 1.0) < 0.05:
        return False

    return True


def _step_0_3_open_profile(solid, dims: Tuple[float, float, float]) -> Optional[Step0Result]:
    try:
        from manufacturing_pipeline.analysis.step0_section_tools import (
            ProfileRegistry,
            dominant_section_cluster,
            extract_section_features,
            find_extrusion_axis,
            match_templates,
            normalize_section_polygon,
            section_distance,
            section_plane_positions_from_vertices,
            slice_solid_to_section,
            solid_vertices_np,
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
    dsum = [
        sum(section_distance(a, b) for j, b in enumerate(normalized) if j != i)
        for i, a in enumerate(normalized)
    ]
    core_idx = int(np.argmin(dsum))
    core_sec = cluster[core_idx]
    core_poly = core_sec.polygon

    features = extract_section_features(core_sec)

    if features.holes != 0 or features.reentrant_corners == 0:
        return None

    volume = _get_volume(solid)
    if _is_bent_sheet_geometry(solid, volume, dims):
        return None

    registry = ProfileRegistry().extend_generic_defaults()
    matches = match_templates(core_poly, registry, top_k=5)
    best = matches[0] if matches else None

    open_families = {"I_FAMILY", "U_FAMILY", "L_FAMILY", "T_FAMILY"}
    if best and best.score <= 0.12 and best.family in open_families:
        confidence = max(0.50, 1.0 - min(best.score / 0.12, 1.0))
        return _result(
            label="PROFIEL",
            step="0.3",
            method="template",
            confidence=confidence,
            fallthrough=False,
            reason=f"open profiel family={best.family} score={best.score:.3f}",
            features={
                "template_family": best.family,
                "template_score": best.score,
                "reentrant_corners": features.reentrant_corners,
            },
        )

    return None
