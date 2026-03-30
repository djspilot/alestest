from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from manufacturing_pipeline.analysis.classification_core.result_types import Step0Result, _result
from manufacturing_pipeline.analysis.classification_variables import (
    ROUND_SHAFT_AXIAL_AREA_RATIO_MIN,
    ROUND_SHAFT_CORE_BBOX_RATIO_MIN,
    ROUND_SHAFT_CORE_COMPACTNESS_MIN,
    ROUND_SHAFT_MIN_LENGTH_RATIO,
    STEP0_CLUSTER_RATIO_MIN,
)

logger = logging.getLogger("ales.classification_step0")


def _evaluate_round_shaft_axial_slice(
    *,
    solid,
    axis,
    vertices,
    core_sec,
    core_features,
    slice_solid_to_section_fn,
) -> Dict[str, Any]:
    """Check round solid shaft machining via longitudinal slice area ratio."""
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

    dmax = 0.0
    try:
        from manufacturing_pipeline.analysis.step0_section_tools import section_plane_positions_from_vertices

        end_fracs = (0.02, 0.05, 0.10, 0.20, 0.35, 0.50, 0.65, 0.80, 0.90, 0.95, 0.98)
        end_positions = section_plane_positions_from_vertices(vertices, axis.direction, end_fracs)
        for pos in end_positions:
            sec = slice_solid_to_section_fn(
                solid,
                plane_origin=axis.direction * pos,
                plane_normal=axis.direction,
                section_position=pos,
            )
            if sec is None or sec.polygon.area <= 0:
                continue
            minx, miny, maxx, maxy = sec.polygon.bounds
            dim = float(max(maxx - minx, maxy - miny))
            if dim > dmax:
                dmax = dim
    except Exception as exc:
        logger.debug("Dmax sampling fout: %s", exc)

    if dmax <= 0:
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
        break

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


def _step_0_1_slice_validation(solid) -> Optional[Step0Result]:
    """Poort: controleer of stabiele extrusie-as en consistente doorsneden bestaan."""
    try:
        from manufacturing_pipeline.analysis.step0_section_tools import (
            dominant_section_cluster,
            extract_section_features,
            find_extrusion_axis,
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
        return _result(
            label="ANDERS",
            step="0.1",
            method="rule",
            confidence=0.40,
            fallthrough=True,
            reason="geen stabiele extrusie-as gevonden; doorval naar Step 1",
        )

    try:
        vertices = solid_vertices_np(solid)
        positions = section_plane_positions_from_vertices(vertices, axis.direction, (0.20, 0.35, 0.50, 0.65, 0.80))
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
    except Exception as exc:
        logger.debug("Slice-validatie fout: %s", exc)
        return None

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

    try:
        import numpy as np

        normalized = [normalize_section_polygon(sec.polygon) for sec in cluster]
        dsum = [sum(section_distance(a, b) for j, b in enumerate(normalized) if j != i) for i, a in enumerate(normalized)]
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
    except Exception as exc:
        logger.debug("Ronde-as axial slice check overgeslagen: %s", exc)

    return None
