from __future__ import annotations

from typing import Any, Dict, List, Optional

import math

from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_Circle, GeomAbs_Cone
from OCP.TopAbs import TopAbs_EDGE
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS


def _detect_countersunk_holes(cq_object, cylindrical_holes, *, collect_conical_faces, normalize_vector, as_point_tuple, dot, distance_point_to_axis, signed_axis_distance) -> Dict[int, float]:
    if not cylindrical_holes:
        return {}

    conical_faces = collect_conical_faces(cq_object)
    if not conical_faces:
        return {}

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
            if axis_dot < 0.97:
                continue

            radial_dist = distance_point_to_axis(hole_axis_origin, cone["origin"], cone["axis"])
            if radial_dist > max(1.0, hole_radius * 1.25):
                continue

            axial_dist = abs(signed_axis_distance(hole_axis_origin, cone["origin"], cone["axis"]))
            if axial_dist > max(25.0, hole_radius * 6.0):
                continue

            included_angle = cone["included_angle"]
            if included_angle < 55.0 or included_angle > 150.0:
                continue

            score = radial_dist + (1.0 - axis_dot) * 10.0 + axial_dist * 0.05
            if best_score is None or score < best_score:
                best_score = score
                best_angle = included_angle

        if best_angle is not None:
            matches[idx] = round(best_angle, 2)

    return matches


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
        radial_limit = max(1.0, min(candidate_inner_radius, hole_radius) * 0.8)
        if radial_dist > radial_limit:
            continue

        axial_dist = abs(signed_axis_distance(hole_axis_origin, candidate_origin, candidate_axis))
        if axial_dist > max(40.0, hole_radius * 8.0):
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
        if included_angle < 55.0 or included_angle > 150.0:
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
