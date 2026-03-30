from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from typing import Any, Dict, Tuple

from manufacturing_pipeline.analysis.sheetmetal import standards as _sheetmetal_standards

try:
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Cylinder, GeomAbs_Plane
    from OCP.GProp import GProp_GProps
    from OCP.BRepGProp import BRepGProp
    from OCP.TopAbs import TopAbs_FACE
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopoDS import TopoDS
    from OCP.gp import gp_Vec, gp_Pnt

    HAS_OCP = True
except ImportError:
    HAS_OCP = False


@dataclass
class DetectedBend:
    """Gedetecteerde buiging in geometrie"""

    bend_id: int
    angle: float
    inner_radius: float
    bend_length: float
    flange1_length: float
    flange2_length: float
    position: Tuple[float, float, float]
    bend_axis: Tuple[float, float, float]
    is_standard_angle: bool
    is_standard_radius: bool


def analyze_sheet_metal_geometry(solid, thickness: float = None) -> Dict[str, Any]:
    if not HAS_OCP:
        return {"error": "OCP library not available"}

    result = {
        "is_sheet_metal": False,
        "thickness": thickness,
        "bends": [],
        "bend_count": 0,
        "total_bend_length": 0,
        "flat_pattern": None,
        "tooling_recommendations": [],
    }

    faces = []
    exp = TopExp_Explorer(solid, TopAbs_FACE)
    while exp.More():
        faces.append(TopoDS.Face_s(exp.Current()))
        exp.Next()

    cylindrical_faces = []
    planar_faces = []

    for face in faces:
        surf = BRepAdaptor_Surface(face, True)
        stype = surf.GetType()

        props = GProp_GProps()
        BRepGProp.SurfaceProperties_s(face, props)
        area = props.Mass()

        if stype == GeomAbs_Cylinder:
            cyl = surf.Cylinder()
            radius = cyl.Radius()
            axis = cyl.Axis()
            location = cyl.Location()

            u_min = surf.FirstUParameter()
            u_max = surf.LastUParameter()
            angle_deg = math.degrees(abs(u_max - u_min))
            arc_length = radius * abs(u_max - u_min)
            bend_length = area / arc_length if arc_length > 0 else 0

            cylindrical_faces.append(
                {
                    "face": face,
                    "radius": radius,
                    "axis": (axis.Direction().X(), axis.Direction().Y(), axis.Direction().Z()),
                    "location": (location.X(), location.Y(), location.Z()),
                    "area": area,
                    "bend_length": bend_length,
                    "angle": angle_deg,
                }
            )
        elif stype == GeomAbs_Plane:
            pln = surf.Plane()
            normal = pln.Axis().Direction()
            planar_faces.append(
                {
                    "face": face,
                    "normal": (normal.X(), normal.Y(), normal.Z()),
                    "area": area,
                }
            )

    reference_normal = None
    reference_center = None
    if planar_faces:
        largest_face = max(planar_faces, key=lambda x: x["area"])
        reference_normal = largest_face["normal"]

        props = GProp_GProps()
        BRepGProp.SurfaceProperties_s(largest_face["face"], props)
        cm = props.CentreOfMass()
        reference_center = (cm.X(), cm.Y(), cm.Z())

    grouped_bends = []
    processed_indices = set()
    for i, c1 in enumerate(cylindrical_faces):
        if i in processed_indices:
            continue
        if c1["angle"] > 270:
            continue

        current_group = [c1]
        processed_indices.add(i)

        for j, c2 in enumerate(cylindrical_faces):
            if j in processed_indices:
                continue
            if c2["angle"] > 270:
                continue

            dot = (
                c1["axis"][0] * c2["axis"][0]
                + c1["axis"][1] * c2["axis"][1]
                + c1["axis"][2] * c2["axis"][2]
            )
            if abs(abs(dot) - 1.0) > 0.01:
                continue

            dx = c2["location"][0] - c1["location"][0]
            dy = c2["location"][1] - c1["location"][1]
            dz = c2["location"][2] - c1["location"][2]
            cx = dy * c1["axis"][2] - dz * c1["axis"][1]
            cy = dz * c1["axis"][0] - dx * c1["axis"][2]
            cz = dx * c1["axis"][1] - dy * c1["axis"][0]
            dist = math.sqrt(cx * cx + cy * cy + cz * cz)

            if dist < 0.1:
                current_group.append(c2)
                processed_indices.add(j)

        grouped_bends.append(current_group)

    bends = []
    detected_thicknesses = []

    for i, group in enumerate(grouped_bends):
        by_radius = {}
        for face in group:
            radius_key = round(face["radius"], 2)
            if radius_key not in by_radius:
                by_radius[radius_key] = []
            by_radius[radius_key].append(face)

        is_hole = False
        for faces_at_radius in by_radius.values():
            total_angle = sum(f["angle"] for f in faces_at_radius)
            if total_angle > 270:
                is_hole = True
                break
        if is_hole:
            continue

        group.sort(key=lambda x: x["radius"])
        radii = sorted(list(by_radius.keys()))
        if len(radii) >= 2:
            thickness_delta = radii[-1] - radii[0]
            if 0.1 < thickness_delta < 25.0:
                detected_thicknesses.append(thickness_delta)

        inner = group[0]
        inner_radius = round(inner["radius"], 2)
        inner_faces = by_radius.get(inner_radius, [inner])
        total_angle = sum(f["angle"] for f in inner_faces)

        is_valid_bend = True
        bend_length = inner["bend_length"]
        if bend_length < 20.0:
            is_valid_bend = False
        if inner["radius"] > 15.0:
            is_valid_bend = False
        if total_angle < 30.0:
            is_valid_bend = False

        if 0.5 <= inner["radius"] <= 50 and is_valid_bend:
            direction = 0
            if reference_normal and reference_center:
                try:
                    ax_loc = inner["location"]
                    dx = ax_loc[0] - reference_center[0]
                    dy = ax_loc[1] - reference_center[1]
                    dz = ax_loc[2] - reference_center[2]
                    h = dx * reference_normal[0] + dy * reference_normal[1] + dz * reference_normal[2]

                    if h > 0.1:
                        direction = 1
                    elif h < -0.1:
                        direction = -1

                    if direction == 0:
                        surf = BRepAdaptor_Surface(inner["face"], True)
                        u_mid = (surf.FirstUParameter() + surf.LastUParameter()) / 2.0
                        v_mid = (surf.FirstVParameter() + surf.LastVParameter()) / 2.0
                        point = gp_Pnt()
                        d1u = gp_Vec()
                        d1v = gp_Vec()
                        surf.D1(u_mid, v_mid, point, d1u, d1v)
                        normal = d1u.Crossed(d1v)
                        normal.Normalize()
                        dot = (
                            normal.X() * reference_normal[0]
                            + normal.Y() * reference_normal[1]
                            + normal.Z() * reference_normal[2]
                        )
                        if dot > 0.1:
                            direction = 1
                        elif dot < -0.1:
                            direction = -1
                except Exception:
                    pass

            bend = DetectedBend(
                bend_id=i + 1,
                angle=round(total_angle, 1),
                inner_radius=inner["radius"],
                bend_length=inner["bend_length"],
                flange1_length=0,
                flange2_length=0,
                position=inner["location"],
                bend_axis=inner["axis"],
                is_standard_angle=any(
                    abs(total_angle - angle) < 5 for angle in _sheetmetal_standards.STANDARD_BEND_ANGLES
                ),
                is_standard_radius=any(
                    abs(inner["radius"] - radius) < 0.1
                    for radius in [0.5, 1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10]
                ),
            )
            bend.direction = direction
            bends.append(bend)

    if thickness is None and detected_thicknesses:
        thickness = Counter(detected_thicknesses).most_common(1)[0][0]
        result["thickness"] = thickness

    up_bends = sum(1 for bend in bends if getattr(bend, "direction", 0) == 1)
    down_bends = sum(1 for bend in bends if getattr(bend, "direction", 0) == -1)
    counter_bend_count = min(up_bends, down_bends) if (up_bends + down_bends) > 0 else 0

    is_closed_profile = False
    is_stock_profile = False
    if len(bends) >= 4:
        total_bend_angle = sum(bend.angle for bend in bends)
        if 350 <= total_bend_angle <= 370:
            is_closed_profile = True
            is_stock_profile = True

    if not is_stock_profile and 1 <= len(bends) <= 3 and bends:
        lengths = [bend.bend_length for bend in bends]
        avg_len = sum(lengths) / len(lengths)
        if all(abs(length - avg_len) < avg_len * 0.1 for length in lengths) and avg_len > 100:
            is_stock_profile = True

    result["bends"] = bends
    result["bend_count"] = len(bends)
    result["counter_bend_count"] = counter_bend_count
    result["is_sheet_metal"] = len(bends) > 0
    result["is_closed_profile"] = is_closed_profile
    result["is_stock_profile"] = is_stock_profile
    result["total_bend_length"] = sum(bend.bend_length for bend in bends)
    result["bend_count_for_erp"] = 0 if is_stock_profile else len(bends)
    return result
