from __future__ import annotations

from typing import Any, Dict, List, Optional

import math

from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_Circle, GeomAbs_Cone
from OCP.TopAbs import TopAbs_EDGE
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS

from manufacturing_pipeline.core.decision_variables import SHEET_FEATURE_DECISION_VARIABLES


def _detect_countersunk_by_coaxial_pairs(cylindrical_holes, matches, *, normalize_vector, as_point_tuple, dot, distance_point_to_axis, signed_axis_distance) -> Dict[int, float]:
    """Fallback: infer countersinks from coaxial large/small cylindrical pairs.

    This is used when conical faces are missing in STEP export or when cone matching
    does not cover all holes. The larger diameter member of the pair gets the
    countersunk label.
    """
    if not cylindrical_holes:
        return matches

    used_indices = set(matches.keys())
    for idx in range(len(cylindrical_holes)):
        if idx in used_indices:
            continue

        h1 = cylindrical_holes[idx]
        axis1 = normalize_vector(h1.axis)
        origin1 = as_point_tuple(getattr(h1, "axis_origin", None)) or as_point_tuple(h1.position)
        if axis1 is None or origin1 is None:
            continue

        best_candidate = None
        best_score = None

        for jdx in range(idx + 1, len(cylindrical_holes)):
            if jdx in used_indices:
                continue

            h2 = cylindrical_holes[jdx]
            axis2 = normalize_vector(h2.axis)
            origin2 = as_point_tuple(getattr(h2, "axis_origin", None)) or as_point_tuple(h2.position)
            if axis2 is None or origin2 is None:
                continue

            axis_dot = abs(dot(axis1, axis2))
            if axis_dot < 0.995:
                continue

            radial_dist = distance_point_to_axis(origin2, origin1, axis1)
            if radial_dist > SHEET_FEATURE_DECISION_VARIABLES["countersink_pairing"]["coaxial_radial_dist_max_mm"]:
                continue

            axial_dist = abs(signed_axis_distance(origin2, origin1, axis1))
            if axial_dist > SHEET_FEATURE_DECISION_VARIABLES["countersink_pairing"]["coaxial_axial_dist_max_mm"]:
                continue

            d1 = float(getattr(h1, "diameter", 0.0) or 0.0)
            d2 = float(getattr(h2, "diameter", 0.0) or 0.0)
            if d1 <= 0.0 or d2 <= 0.0:
                continue

            d_large = max(d1, d2)
            d_small = min(d1, d2)
            ratio = d_large / d_small if d_small > 0.0 else 0.0

            # Countersink-like diameter step (e.g. 17 -> 8.5 gives ratio 2.0)
            if ratio < SHEET_FEATURE_DECISION_VARIABLES["countersink_pairing"]["diameter_ratio_min"] or ratio > SHEET_FEATURE_DECISION_VARIABLES["countersink_pairing"]["diameter_ratio_max"]:
                continue

            depth1 = float(getattr(h1, "depth", 0.0) or 0.0)
            depth2 = float(getattr(h2, "depth", 0.0) or 0.0)
            depth_large = depth1 if d1 >= d2 else depth2
            depth_small = depth2 if d1 >= d2 else depth1

            # Large diameter should be relatively shallow; small one continues deeper.
            if depth_large > max(
                SHEET_FEATURE_DECISION_VARIABLES["countersink_pairing"]["depth_large_abs_max_mm"],
                d_large * SHEET_FEATURE_DECISION_VARIABLES["countersink_pairing"]["depth_large_rel_max_factor"],
            ):
                continue
            if depth_small + 1e-6 < depth_large:
                continue

            score = radial_dist + axial_dist * 0.1 + abs(ratio - 2.0)
            if best_score is None or score < best_score:
                best_score = score
                best_candidate = jdx

        if best_candidate is None:
            continue

        h2 = cylindrical_holes[best_candidate]
        d1 = float(getattr(h1, "diameter", 0.0) or 0.0)
        d2 = float(getattr(h2, "diameter", 0.0) or 0.0)
        large_idx = idx if d1 >= d2 else best_candidate

        # Fallback angle when cone geometry is absent.
        matches[large_idx] = 90.0
        used_indices.add(idx)
        used_indices.add(best_candidate)

    return matches


def _detect_countersunk_holes(cq_object, cylindrical_holes, *, collect_conical_faces, normalize_vector, as_point_tuple, dot, distance_point_to_axis, signed_axis_distance) -> Dict[int, float]:
    if not cylindrical_holes:
        return {}

    conical_faces = collect_conical_faces(cq_object)
    if not conical_faces:
        return _detect_countersunk_by_coaxial_pairs(
            cylindrical_holes,
            {},
            normalize_vector=normalize_vector,
            as_point_tuple=as_point_tuple,
            dot=dot,
            distance_point_to_axis=distance_point_to_axis,
            signed_axis_distance=signed_axis_distance,
        )

    matches: Dict[int, float] = {}

    for idx, hole in enumerate(cylindrical_holes):
        hole_axis = normalize_vector(hole.axis)
        if hole_axis is None:
            continue

        hole_radius = max(float(hole.diameter) * 0.5, 0.0)
        hole_pos = hole.position
        hole_axis_origin = as_point_tuple(getattr(hole, "axis_origin", None)) or as_point_tuple(hole_pos)
        if hole_axis_origin is None:
            continue

        best_angle: Optional[float] = None
        best_score: Optional[float] = None

        for cone in conical_faces:
            axis_dot = abs(dot(hole_axis, cone["axis"]))
            if axis_dot < SHEET_FEATURE_DECISION_VARIABLES["conical_matching"]["axis_alignment_min"]:
                continue

            radial_dist = distance_point_to_axis(hole_axis_origin, cone["origin"], cone["axis"])
            if radial_dist > max(
                SHEET_FEATURE_DECISION_VARIABLES["conical_matching"]["radial_dist_base_max_mm"],
                hole_radius * SHEET_FEATURE_DECISION_VARIABLES["conical_matching"]["radial_dist_radius_factor"],
            ):
                continue

            axial_dist = abs(signed_axis_distance(hole_axis_origin, cone["origin"], cone["axis"]))
            if axial_dist > max(
                SHEET_FEATURE_DECISION_VARIABLES["conical_matching"]["axial_dist_base_max_mm"],
                hole_radius * SHEET_FEATURE_DECISION_VARIABLES["conical_matching"]["axial_dist_radius_factor"],
            ):
                continue

            included_angle = cone["included_angle"]
            if included_angle < SHEET_FEATURE_DECISION_VARIABLES["conical_matching"]["included_angle_min_deg"] or included_angle > SHEET_FEATURE_DECISION_VARIABLES["conical_matching"]["included_angle_max_deg"]:
                continue

            score = radial_dist + (1.0 - axis_dot) * 10.0 + axial_dist * 0.05
            if best_score is None or score < best_score:
                best_score = score
                best_angle = included_angle

        if best_angle is not None:
            matches[idx] = round(best_angle, 2)

    return _detect_countersunk_by_coaxial_pairs(
        cylindrical_holes,
        matches,
        normalize_vector=normalize_vector,
        as_point_tuple=as_point_tuple,
        dot=dot,
        distance_point_to_axis=distance_point_to_axis,
        signed_axis_distance=signed_axis_distance,
    )


def _group_conical_countersink_faces(conical_faces: List[Dict[str, Any]], *, dot, distance_point_to_axis, signed_axis_distance) -> List[Dict[str, Any]]:
    groups: List[Dict[str, Any]] = []

    for cone in conical_faces:
        placed = False
        for group in groups:
            axis_dot = abs(dot(group["axis"], cone["axis"]))
            if axis_dot < 0.999:
                continue

            radial_dist = distance_point_to_axis(cone["origin"], group["origin"], group["axis"])
            axial_dist = abs(signed_axis_distance(cone["origin"], group["origin"], group["axis"]))
            if radial_dist > 0.2 or axial_dist > 1.0:
                continue

            if abs(float(group["included_angle"]) - float(cone["included_angle"])) > 1.0:
                continue

            if abs(float(group["inner_radius"]) - float(cone.get("inner_radius", 0.0))) > 0.3:
                continue

            group["count"] += 1
            placed = True
            break

        if not placed:
            groups.append(
                {
                    "axis": cone["axis"],
                    "origin": cone["origin"],
                    "included_angle": float(cone["included_angle"]),
                    "inner_radius": float(cone.get("inner_radius", 0.0) or 0.0),
                    "outer_radius": float(cone.get("outer_radius", 0.0) or 0.0),
                    "count": 1,
                }
            )

    return groups


def _candidate_matches_cylindrical_hole(candidate: Dict[str, Any], cylindrical_holes, *, normalize_vector, as_point_tuple, dot, distance_point_to_axis, signed_axis_distance) -> bool:
    candidate_axis = normalize_vector(candidate.get("axis"))
    candidate_origin = as_point_tuple(candidate.get("origin"))
    candidate_inner_radius = float(candidate.get("inner_radius", 0.0) or 0.0)

    if candidate_axis is None or candidate_origin is None:
        return False

    for hole in cylindrical_holes:
        hole_axis = normalize_vector(hole.axis)
        if hole_axis is None:
            continue

        axis_dot = abs(dot(hole_axis, candidate_axis))
        if axis_dot < 0.97:
            continue

        hole_axis_origin = as_point_tuple(getattr(hole, "axis_origin", None)) or as_point_tuple(hole.position)
        if hole_axis_origin is None:
            continue

        radial_dist = distance_point_to_axis(hole_axis_origin, candidate_origin, candidate_axis)
        hole_radius = max(float(hole.diameter) * 0.5, 0.0)
        radial_limit = max(
            SHEET_FEATURE_DECISION_VARIABLES["standalone_conical_matching"]["radial_limit_base_mm"],
            min(candidate_inner_radius, hole_radius) * SHEET_FEATURE_DECISION_VARIABLES["standalone_conical_matching"]["radial_limit_inner_factor"],
        )
        if radial_dist > radial_limit:
            continue

        axial_dist = abs(signed_axis_distance(hole_axis_origin, candidate_origin, candidate_axis))
        if axial_dist > max(
            SHEET_FEATURE_DECISION_VARIABLES["standalone_conical_matching"]["axial_limit_base_mm"],
            hole_radius * SHEET_FEATURE_DECISION_VARIABLES["standalone_conical_matching"]["axial_limit_radius_factor"],
        ):
            continue

        return True

    return False


def _detect_standalone_countersunk_holes(cq_object, cylindrical_holes, *, collect_conical_faces, group_conical_countersink_faces, candidate_matches_cylindrical_hole) -> List[Dict[str, float]]:
    conical_faces = collect_conical_faces(cq_object)
    if not conical_faces:
        return []

    grouped = group_conical_countersink_faces(conical_faces)
    standalone: List[Dict[str, float]] = []

    for candidate in grouped:
        inner_radius = float(candidate.get("inner_radius", 0.0) or 0.0)
        included_angle = float(candidate.get("included_angle", 0.0) or 0.0)

        if inner_radius <= 0:
            continue
        if included_angle < SHEET_FEATURE_DECISION_VARIABLES["standalone_conical_matching"]["included_angle_min_deg"] or included_angle > SHEET_FEATURE_DECISION_VARIABLES["standalone_conical_matching"]["included_angle_max_deg"]:
            continue
        if candidate_matches_cylindrical_hole(candidate, cylindrical_holes):
            continue

        standalone.append(
            {
                "inner_radius": inner_radius,
                "included_angle": included_angle,
                "origin": candidate["origin"],
            }
        )

    return standalone


def _collect_conical_faces(cq_object, *, normalize_vector) -> List[Dict[str, Any]]:
    conical_faces: List[Dict[str, Any]] = []

    for face in cq_object.faces().vals():
        surf = BRepAdaptor_Surface(face.wrapped, True)
        if surf.GetType() != GeomAbs_Cone:
            continue

        cone = surf.Cone()
        axis_dir = cone.Axis().Direction()
        axis = normalize_vector((axis_dir.X(), axis_dir.Y(), axis_dir.Z()))
        if axis is None:
            continue

        origin = cone.Location()
        included_angle = abs(math.degrees(float(cone.SemiAngle()))) * 2.0
        if included_angle <= 0:
            continue

        circle_radii: List[float] = []
        exp = TopExp_Explorer(face.wrapped, TopAbs_EDGE)
        while exp.More():
            edge = TopoDS.Edge_s(exp.Current())
            curve = BRepAdaptor_Curve(edge)
            if curve.GetType() == GeomAbs_Circle:
                try:
                    radius = float(curve.Circle().Radius())
                    if radius > 0:
                        circle_radii.append(radius)
                except Exception:
                    pass
            exp.Next()

        if circle_radii:
            inner_radius = min(circle_radii)
            outer_radius = max(circle_radii)
        else:
            ref_radius = float(cone.RefRadius())
            inner_radius = 0.0
            outer_radius = ref_radius if ref_radius > 0 else 0.0

        conical_faces.append(
            {
                "axis": axis,
                "origin": (origin.X(), origin.Y(), origin.Z()),
                "included_angle": included_angle,
                "inner_radius": inner_radius,
                "outer_radius": outer_radius,
            }
        )

    return conical_faces
