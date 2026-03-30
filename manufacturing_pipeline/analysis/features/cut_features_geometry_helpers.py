from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepGProp import BRepGProp
from OCP.BRepTools import BRepTools
from OCP.GProp import GProp_GProps
from OCP.GeomAbs import GeomAbs_Plane
from OCP.TopoDS import TopoDS_Shape


def _normalize_vector(vector: Tuple[float, float, float]) -> Optional[Tuple[float, float, float]]:
    try:
        x, y, z = float(vector[0]), float(vector[1]), float(vector[2])
        norm = math.sqrt(x * x + y * y + z * z)
        if norm <= 1e-9:
            return None
        return (x / norm, y / norm, z / norm)
    except Exception:
        return None


def _as_point_tuple(value: Any) -> Optional[Tuple[float, float, float]]:
    try:
        if value is None:
            return None
        return (float(value[0]), float(value[1]), float(value[2]))
    except Exception:
        return None


def _dot(a: Tuple[float, float, float], b: Tuple[float, float, float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _distance_point_to_axis(
    point: Tuple[float, float, float],
    axis_origin: Tuple[float, float, float],
    axis_dir: Tuple[float, float, float],
) -> float:
    vx = point[0] - axis_origin[0]
    vy = point[1] - axis_origin[1]
    vz = point[2] - axis_origin[2]

    cx = vy * axis_dir[2] - vz * axis_dir[1]
    cy = vz * axis_dir[0] - vx * axis_dir[2]
    cz = vx * axis_dir[1] - vy * axis_dir[0]

    return math.sqrt(cx * cx + cy * cy + cz * cz)


def _signed_axis_distance(
    point: Tuple[float, float, float],
    axis_origin: Tuple[float, float, float],
    axis_dir: Tuple[float, float, float],
) -> float:
    return (
        (point[0] - axis_origin[0]) * axis_dir[0]
        + (point[1] - axis_origin[1]) * axis_dir[1]
        + (point[2] - axis_origin[2]) * axis_dir[2]
    )


def _get_outer_contour_length(shape: TopoDS_Shape, *, logger) -> float:
    try:
        from OCP.TopAbs import TopAbs_FACE
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopoDS import TopoDS

        planar_faces = []
        exp = TopExp_Explorer(shape, TopAbs_FACE)
        while exp.More():
            face = TopoDS.Face_s(exp.Current())
            surf = BRepAdaptor_Surface(face)
            if surf.GetType() == GeomAbs_Plane:
                props = GProp_GProps()
                BRepGProp.SurfaceProperties_s(face, props)
                planar_faces.append((face, props.Mass()))
            exp.Next()

        if not planar_faces:
            logger.warning("[CutFeatures] Geen planaire faces gevonden voor outer contour")
            return 0.0

        planar_faces.sort(key=lambda item: item[1], reverse=True)
        largest_face = planar_faces[0][0]
        outer_wire = BRepTools.OuterWire_s(largest_face)

        props = GProp_GProps()
        BRepGProp.LinearProperties_s(outer_wire, props)
        return props.Mass()
    except Exception as exc:
        logger.error(f"[CutFeatures] Fout bij outer contour berekening: {exc}")
        return 0.0


def _label_contours_from_holes(
    closed_contours: List[Dict[str, Any]],
    cylindrical_holes,
    countersink_matches: Dict[int, float],
    *,
    iso_standards,
    as_point_tuple,
    inferred_countersunk: Optional[set] = None,
    is_profile: bool = False,
) -> List[Dict[str, Any]]:
    if inferred_countersunk is None:
        inferred_countersunk = set()
    results: List[Dict[str, Any]] = []
    used_hole_indices: set = set()
    match_tol = 10.0

    for contour in closed_contours:
        center_cc = contour.get("center")
        best_idx: Optional[int] = None
        best_dist = float("inf")

        if center_cc is not None:
            for idx, hole in enumerate(cylindrical_holes):
                if idx in used_hole_indices:
                    continue
                pos = as_point_tuple(getattr(hole, "position", None))
                if pos is None:
                    pos = as_point_tuple(getattr(hole, "axis_origin", None))
                if pos is None:
                    continue
                dx = center_cc[0] - pos[0]
                dy = center_cc[1] - pos[1]
                dz = center_cc[2] - pos[2]
                dist = math.sqrt(dx * dx + dy * dy + dz * dz)
                if dist < best_dist:
                    best_dist = dist
                    best_idx = idx

        label = "hole"
        radius: Optional[float] = None
        cs_angle: Optional[float] = None

        if best_idx is not None and best_dist <= match_tol:
            used_hole_indices.add(best_idx)
            hole = cylindrical_holes[best_idx]
            radius = hole.diameter / 2.0
            cs_angle_val = countersink_matches.get(best_idx)
            if cs_angle_val is not None or best_idx in inferred_countersunk:
                label = "countersunk"
                cs_angle = cs_angle_val
            else:
                thread_matches = iso_standards.identify_thread_from_diameter(hole.diameter, 0.20)
                tapped_matches = [m for m in thread_matches if "tapped" in m.designation.lower()]
                major_matches = [m for m in thread_matches if "tapped" not in m.designation.lower()]
                hole_depth = float(getattr(hole, "depth", 0.0) or 0.0)

                if is_profile:
                    if tapped_matches and not major_matches:
                        label = "thread"
                    elif tapped_matches and major_matches:
                        if hole.diameter <= 6.0 and hole_depth <= max(6.0, hole.diameter * 1.5):
                            for match in tapped_matches:
                                delta = float(getattr(match, "major_diameter", 0.0) or 0.0) - float(hole.diameter)
                                if 0.8 <= delta <= 1.4:
                                    label = "thread"
                                    break
                else:
                    if tapped_matches and major_matches:
                        tapped_matches = []
                    if tapped_matches and hole_depth > 0:
                        plausible = [
                            m
                            for m in tapped_matches
                            if float(getattr(m, "major_diameter", 0.0) or 0.0) <= hole_depth * 1.35
                        ]
                        tapped_matches = plausible if plausible else []
                    if tapped_matches:
                        label = "thread"

        results.append({"label": label, "radius": radius, "cs_angle": cs_angle})

    return results


def _detect_closed_inner_contours(
    shape: TopoDS_Shape,
    *,
    logger,
    as_point_tuple,
    normalize_vector,
    dot,
) -> List[Dict[str, Any]]:
    try:
        from collections import defaultdict
        from OCP.Bnd import Bnd_Box
        from OCP.BRepBndLib import BRepBndLib
        from OCP.TopAbs import TopAbs_FACE, TopAbs_WIRE
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopoDS import TopoDS

        contour_candidates: List[Dict[str, Any]] = []
        exp = TopExp_Explorer(shape, TopAbs_FACE)
        while exp.More():
            face = TopoDS.Face_s(exp.Current())
            surf = BRepAdaptor_Surface(face, True)

            normal = None
            if surf.GetType() == GeomAbs_Plane:
                axis = surf.Plane().Axis().Direction()
                normal = (axis.X(), axis.Y(), axis.Z())

            outer_wire = BRepTools.OuterWire_s(face)
            wire_exp = TopExp_Explorer(face, TopAbs_WIRE)
            while wire_exp.More():
                wire = TopoDS.Wire_s(wire_exp.Current())
                wire_exp.Next()

                if wire.IsSame(outer_wire):
                    continue

                props = GProp_GProps()
                BRepGProp.LinearProperties_s(wire, props)
                perimeter = float(props.Mass())
                if perimeter <= 1e-6:
                    continue

                center = props.CentreOfMass()
                bbox = Bnd_Box()
                BRepBndLib.Add_s(wire, bbox)
                xmin, ymin, zmin, xmax, ymax, zmax = bbox.Get()
                dims = sorted(
                    [
                        float(xmax - xmin),
                        float(ymax - ymin),
                        float(zmax - zmin),
                    ],
                    reverse=True,
                )
                major = dims[0] if dims else 0.0
                minor = dims[1] if len(dims) > 1 else 0.0

                contour_candidates.append(
                    {
                        "perimeter": perimeter,
                        "center": (center.X(), center.Y(), center.Z()),
                        "normal": normal,
                        "dim": f"{major:.1f}x{minor:.1f}",
                    }
                )

            exp.Next()

        if not contour_candidates:
            return []

        buckets = defaultdict(list)
        for idx, contour in enumerate(contour_candidates):
            buckets[(round(float(contour["perimeter"]), 2), contour["dim"])].append((idx, contour))

        unique_contours: List[Dict[str, Any]] = []
        processed_indices = set()
        for bucket in buckets.values():
            for i, contour_a in bucket:
                if i in processed_indices:
                    continue

                processed_indices.add(i)
                unique_contours.append(contour_a)

                center_a = as_point_tuple(contour_a.get("center"))
                normal_a = normalize_vector(as_point_tuple(contour_a.get("normal")))
                if center_a is None:
                    continue

                for j, contour_b in bucket:
                    if j in processed_indices or i == j:
                        continue

                    center_b = as_point_tuple(contour_b.get("center"))
                    if center_b is None:
                        continue

                    dx = center_b[0] - center_a[0]
                    dy = center_b[1] - center_a[1]
                    dz = center_b[2] - center_a[2]
                    dist_sq = dx * dx + dy * dy + dz * dz
                    if dist_sq < 0.01:
                        processed_indices.add(j)
                        continue

                    if normal_a is None:
                        continue

                    dist = math.sqrt(dist_sq)
                    if dist <= 1e-9:
                        processed_indices.add(j)
                        continue

                    direction = (dx / dist, dy / dist, dz / dist)
                    if abs(dot(direction, normal_a)) > 0.9:
                        processed_indices.add(j)

        return unique_contours
    except Exception as exc:
        logger.debug(f"[CutFeatures] Closed contour detectie mislukt: {exc}")
        return []
