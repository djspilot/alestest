from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from manufacturing_pipeline.analysis.classification_variables import STEP0_CLUSTER_RATIO_MIN
from manufacturing_pipeline.analysis.classification_core.geometry_metrics import _get_face_areas
from manufacturing_pipeline.analysis.classification_core.result_types import Step0Result, _result


def _is_constant_thickness(solid) -> bool:
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


def _step_0_4a_flat_plate(solid) -> Optional[Step0Result]:
    try:
        from manufacturing_pipeline.analysis.step0_section_tools import (
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
    core_sec = cluster[int(np.argmin(dsum))]
    core_poly = core_sec.polygon
    features = extract_section_features(core_sec)

    if features.holes != 0:
        return None
    if features.reentrant_corners > 0:
        return None

    dikte_constant = _is_constant_thickness(solid)
    if not dikte_constant:
        return None

    near_rectangle = _is_nearly_rectangle(core_poly)

    if near_rectangle and features.bbox_ratio <= 0.30:
        return _result(
            label="PLAAT",
            step="0.4a",
            method="rule",
            confidence=0.98,
            fallthrough=False,
            reason=f"vlakke plaat high confidence (bbox_ratio={features.bbox_ratio:.3f})",
            features={
                "bbox_ratio": features.bbox_ratio,
                "holes": 0,
                "reentrant_corners": 0,
                "near_rectangle": near_rectangle,
                "dikte_constant": dikte_constant,
            },
        )

    reason = (
        f"vlakke plaat lage confidence (near_rectangle=False, bbox_ratio={features.bbox_ratio:.3f}) -> Step 1"
        if not near_rectangle
        else f"vlakke plaat lage confidence (bbox_ratio={features.bbox_ratio:.3f}) -> Step 1"
    )
    return _result(
        label="PLAAT",
        step="0.4a",
        method="rule",
        confidence=0.65,
        fallthrough=True,
        reason=reason,
        features={
            "bbox_ratio": features.bbox_ratio,
            "holes": 0,
            "reentrant_corners": 0,
            "near_rectangle": near_rectangle,
            "dikte_constant": dikte_constant,
        },
    )


def _select_step_0_4b_features(solid) -> Optional[Dict[str, Any]]:
    try:
        from manufacturing_pipeline.analysis.step0_section_tools import (
            dominant_section_cluster,
            extract_section_features,
            find_extrusion_axis,
            normalize_section_polygon,
            pca_axis_candidate,
            planar_face_normal_candidates,
            section_distance,
            section_plane_positions_from_vertices,
            slice_solid_to_section,
            solid_vertices_np,
        )
    except ImportError:
        return None

    import numpy as np

    axis = find_extrusion_axis(solid)
    if axis is None:
        return None

    try:
        vertices = solid_vertices_np(solid)
    except Exception:
        return None

    def _evaluate_direction(direction: Any, source: str) -> Optional[Dict[str, Any]]:
        try:
            direction_vec = np.asarray(direction, dtype=float)
            norm = float(np.linalg.norm(direction_vec))
            if norm <= 1e-9:
                return None
            direction_vec = direction_vec / norm

            positions = section_plane_positions_from_vertices(
                vertices, direction_vec, (0.20, 0.35, 0.50, 0.65, 0.80)
            )

            sections = []
            for pos in positions:
                sec = slice_solid_to_section(
                    solid,
                    plane_origin=direction_vec * pos,
                    plane_normal=direction_vec,
                    section_position=pos,
                )
                if sec is not None and sec.polygon.area > 0:
                    sections.append(sec)
        except Exception:
            return None

        if len(sections) < 3:
            return None

        cluster = dominant_section_cluster(sections)
        if not cluster:
            return None

        cluster_ratio = len(cluster) / max(len(sections), 1)
        if cluster_ratio < STEP0_CLUSTER_RATIO_MIN:
            return None

        normalized = [normalize_section_polygon(sec.polygon) for sec in cluster]
        dsum = [
            sum(section_distance(a, b) for j, b in enumerate(normalized) if j != i)
            for i, a in enumerate(normalized)
        ]
        core_sec = cluster[int(np.argmin(dsum))]
        features = extract_section_features(core_sec)

        return {
            "features": features,
            "source": source,
            "direction": direction_vec,
            "cluster_ratio": cluster_ratio,
        }

    primary_source = getattr(axis, "source", "find_extrusion_axis")
    primary_eval = _evaluate_direction(axis.direction, primary_source)
    if primary_eval is None:
        return None

    selected_eval = primary_eval
    used_alternate_axis = False

    primary_features = primary_eval["features"]
    if primary_features.holes == 0 and primary_features.reentrant_corners == 0:
        alternative_candidates: list[tuple[str, Any]] = []
        for direction in planar_face_normal_candidates(solid):
            alternative_candidates.append(("planar-face-normal", direction))
        try:
            alternative_candidates.append(("vertex-pca", pca_axis_candidate(vertices)))
        except Exception:
            pass

        unique_candidates: list[tuple[str, Any]] = []
        primary_dir = primary_eval["direction"]
        for source, direction in alternative_candidates:
            direction_vec = np.asarray(direction, dtype=float)
            norm = float(np.linalg.norm(direction_vec))
            if norm <= 1e-9:
                continue
            direction_vec = direction_vec / norm

            if abs(float(np.dot(direction_vec, primary_dir))) > 0.999:
                continue
            duplicate = any(
                abs(float(np.dot(direction_vec, np.asarray(prev_dir, dtype=float)))) > 0.999
                for _, prev_dir in unique_candidates
            )
            if duplicate:
                continue
            unique_candidates.append((source, direction_vec))

        best_alt: Optional[Dict[str, Any]] = None
        for source, direction_vec in unique_candidates:
            candidate_eval = _evaluate_direction(direction_vec, source)
            if candidate_eval is None:
                continue

            candidate_features = candidate_eval["features"]
            if candidate_features.holes != 0:
                continue

            if best_alt is None:
                best_alt = candidate_eval
                continue

            best_features = best_alt["features"]
            if candidate_features.reentrant_corners > best_features.reentrant_corners:
                best_alt = candidate_eval
                continue
            if (
                candidate_features.reentrant_corners == best_features.reentrant_corners
                and candidate_features.convexity < best_features.convexity
            ):
                best_alt = candidate_eval

        if best_alt is not None and best_alt["features"].reentrant_corners > 0:
            selected_eval = best_alt
            used_alternate_axis = True

    return {
        "selected_features": selected_eval["features"],
        "selected_axis_source": selected_eval["source"],
        "used_alternate_axis": used_alternate_axis,
        "primary_features": primary_features,
    }


def _step_0_4b_constant_thickness_open(
    solid, dims: Tuple[float, float, float]
) -> Optional[Step0Result]:
    section_eval = _select_step_0_4b_features(solid)
    if section_eval is None:
        return None

    features = section_eval.get("selected_features")
    if features is None:
        return None

    if features.holes != 0 or features.reentrant_corners == 0:
        return None

    if not _is_constant_thickness(solid):
        return None

    smallest, middle, longest = dims
    reason = "holes==0 + reentrant_corners>0 + dikteConstant"
    if section_eval.get("used_alternate_axis"):
        reason = f"{reason} + alternatieve doorsnede-as"

    feature_payload: Dict[str, Any] = {
        "holes": features.holes,
        "reentrant_corners": features.reentrant_corners,
        "axis_source": section_eval.get("selected_axis_source"),
        "smallest": smallest,
        "middle": middle,
        "longest": longest,
    }
    if section_eval.get("used_alternate_axis") and section_eval.get("primary_features") is not None:
        primary_features = section_eval["primary_features"]
        feature_payload["primary_reentrant_corners"] = primary_features.reentrant_corners

    return _result(
        label="GEZETTE_PLAAT",
        step="0.4b",
        method="rule",
        confidence=0.88,
        fallthrough=False,
        reason=reason,
        features=feature_payload,
    )
