from __future__ import annotations

import math
from dataclasses import dataclass

from OCP.BRep import BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepGProp import BRepGProp
from OCP.Bnd import Bnd_Box
from OCP.GProp import GProp_GProps
from OCP.GeomAbs import GeomAbs_Circle, GeomAbs_Cone, GeomAbs_Cylinder, GeomAbs_Line, GeomAbs_Plane, GeomAbs_Sphere, GeomAbs_Torus
from OCP.TopAbs import TopAbs_EDGE, TopAbs_REVERSED, TopAbs_VERTEX
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS

from manufacturing_pipeline.core.decision_variables import HOLE_DETECTION_DECISION_VARIABLES


@dataclass
class HoleFeature:
    diameter: float
    depth: float
    position: tuple[float, float, float]
    axis: tuple[float, float, float]
    type: str = "unknown"
    id: str | None = None


def precompute_face_properties(cq_object):
    """Pre-compute primitive face data in one pass."""
    all_faces = cq_object.faces().vals()
    face_data = []

    type_map = {
        GeomAbs_Cylinder: "cylinder",
        GeomAbs_Plane: "plane",
        GeomAbs_Cone: "cone",
        GeomAbs_Sphere: "sphere",
        GeomAbs_Torus: "torus",
    }

    for face in all_faces:
        surf = BRepAdaptor_Surface(face.wrapped, True)
        stype = surf.GetType()

        props = GProp_GProps()
        BRepGProp.SurfaceProperties_s(face.wrapped, props)
        area = props.Mass()
        center = props.CentreOfMass()

        entry = {
            "face": face,
            "type": type_map.get(stype, "other"),
            "area": area,
            "center": (center.X(), center.Y(), center.Z()),
            "orientation": face.wrapped.Orientation(),
        }

        if stype == GeomAbs_Cylinder:
            cyl = surf.Cylinder()
            loc = cyl.Location()
            axis = cyl.Axis().Direction()
            entry["radius"] = cyl.Radius()
            entry["axis"] = (axis.X(), axis.Y(), axis.Z())
            entry["axis_origin"] = (loc.X(), loc.Y(), loc.Z())
            entry["u_min"] = surf.FirstUParameter()
            entry["u_max"] = surf.LastUParameter()
        elif stype == GeomAbs_Plane:
            pln = surf.Plane()
            axis = pln.Axis().Direction()
            loc = pln.Location()
            entry["normal"] = (axis.X(), axis.Y(), axis.Z())
            entry["plane_location"] = (loc.X(), loc.Y(), loc.Z())
            entry["plane_d"] = -(axis.X() * loc.X() + axis.Y() * loc.Y() + axis.Z() * loc.Z())

        face_data.append(entry)

    return face_data


def detect_holes(
    cq_object,
    filter_bores=True,
    is_flat_pattern=False,
    is_turned=None,
    face_data=None,
    return_debug=False,
    turned_part_detector=None,
):
    """Extract cylindrical holes from geometry."""
    candidates = []
    debug_items = []
    candidate_counter = 0

    def make_criterion(name, value=None, threshold=None, passed=True, note=None):
        return {
            "name": name,
            "value": value,
            "threshold": threshold,
            "passed": bool(passed),
            "note": note,
        }

    def make_hole_debug_item(item_id, status, reason, criteria, payload):
        return {
            "id": item_id,
            "status": status,
            "type": "cylindrical",
            "label": f"Ø{float(payload.get('diameter') or 0.0):.1f} mm",
            "reason": reason,
            "criteria": criteria,
            **payload,
        }

    part_dims = None
    if filter_bores:
        try:
            shape = cq_object.val().wrapped
            bbox = Bnd_Box()
            BRepBndLib.Add_s(shape, bbox)
            xmin, ymin, zmin, xmax, ymax, zmax = bbox.Get()
            part_dims = sorted([xmax - xmin, ymax - ymin, zmax - zmin])
        except Exception:
            part_dims = None

    thickness_ref = part_dims[0] if part_dims and part_dims[0] > 0 else None

    if is_turned is None:
        if filter_bores and turned_part_detector is not None:
            is_turned = turned_part_detector(cq_object)
        else:
            is_turned = False

    if face_data is not None:
        for fd in face_data:
            if fd["type"] != "cylinder":
                continue
            if not is_flat_pattern and fd["orientation"] != TopAbs_REVERSED:
                continue

            radius = fd["radius"]
            u_min = fd["u_min"]
            u_max = fd["u_max"]
            angle_deg = math.degrees(abs(u_max - u_min))
            arc_length = radius * abs(u_max - u_min)
            depth = fd["area"] / arc_length if arc_length > 0 else 0

            if is_flat_pattern and radius * 2 > HOLE_DETECTION_DECISION_VARIABLES["flat_artifact_filter"]["diameter_min_mm"] and thickness_ref is not None:
                threshold = max(
                    HOLE_DETECTION_DECISION_VARIABLES["flat_artifact_filter"]["depth_abs_min_mm"],
                    thickness_ref * HOLE_DETECTION_DECISION_VARIABLES["flat_artifact_filter"]["depth_thickness_factor"],
                )
                if depth > threshold:
                    item_id = f"hole-cyl-{candidate_counter}"
                    candidate_counter += 1
                    debug_items.append(make_hole_debug_item(
                        item_id,
                        "rejected",
                        "Afgewezen als flat-pattern buigartefact",
                        [
                            make_criterion("flat_artifact_filter", round(depth, 3), round(threshold, 3), False, "Diepte te groot voor uitslaggat"),
                            make_criterion("flat_pattern_source", "flat", None, True, None),
                        ],
                        {
                            "diameter": radius * 2,
                            "depth": depth,
                            "position": fd["center"],
                            "axis": fd["axis"],
                            "source": "flat" if is_flat_pattern else "3d",
                        },
                    ))
                    continue

            candidates.append({
                "id": f"hole-cyl-{candidate_counter}",
                "diameter": radius * 2,
                "depth": depth,
                "position": fd["center"],
                "axis_origin": fd["axis_origin"],
                "axis": fd["axis"],
                "angle": angle_deg,
            })
            candidate_counter += 1
    else:
        all_faces = cq_object.faces().vals()
        for face in all_faces:
            surf = BRepAdaptor_Surface(face.wrapped, True)
            if surf.GetType() != GeomAbs_Cylinder:
                continue
            if not is_flat_pattern and face.wrapped.Orientation() != TopAbs_REVERSED:
                continue

            cylinder = surf.Cylinder()
            radius = cylinder.Radius()
            location = cylinder.Location()
            axis = cylinder.Axis().Direction()
            u_min = surf.FirstUParameter()
            u_max = surf.LastUParameter()
            angle_deg = math.degrees(abs(u_max - u_min))

            props = GProp_GProps()
            BRepGProp.SurfaceProperties_s(face.wrapped, props)
            area = props.Mass()
            center = props.CentreOfMass()
            arc_length = radius * abs(u_max - u_min)
            depth = area / arc_length if arc_length > 0 else 0

            if is_flat_pattern and radius * 2 > HOLE_DETECTION_DECISION_VARIABLES["flat_artifact_filter"]["diameter_min_mm"] and thickness_ref is not None:
                threshold = max(
                    HOLE_DETECTION_DECISION_VARIABLES["flat_artifact_filter"]["depth_abs_min_mm"],
                    thickness_ref * HOLE_DETECTION_DECISION_VARIABLES["flat_artifact_filter"]["depth_thickness_factor"],
                )
                if depth > threshold:
                    item_id = f"hole-cyl-{candidate_counter}"
                    candidate_counter += 1
                    debug_items.append(make_hole_debug_item(
                        item_id,
                        "rejected",
                        "Afgewezen als flat-pattern buigartefact",
                        [
                            make_criterion("flat_artifact_filter", round(depth, 3), round(threshold, 3), False, "Diepte te groot voor uitslaggat"),
                            make_criterion("flat_pattern_source", "flat", None, True, None),
                        ],
                        {
                            "diameter": radius * 2,
                            "depth": depth,
                            "position": (center.X(), center.Y(), center.Z()),
                            "axis": (axis.X(), axis.Y(), axis.Z()),
                            "source": "flat" if is_flat_pattern else "3d",
                        },
                    ))
                    continue

            candidates.append({
                "id": f"hole-cyl-{candidate_counter}",
                "diameter": radius * 2,
                "depth": depth,
                "position": (center.X(), center.Y(), center.Z()),
                "axis_origin": (location.X(), location.Y(), location.Z()),
                "axis": (axis.X(), axis.Y(), axis.Z()),
                "angle": angle_deg,
            })
            candidate_counter += 1

    from collections import defaultdict

    diameter_buckets = defaultdict(list)
    for idx, candidate in enumerate(candidates):
        diameter_buckets[round(candidate["diameter"], 2)].append((idx, candidate))

    grouped_holes = []
    processed_indices = set()

    for bucket_key in diameter_buckets:
        nearby = []
        for adj_key in [bucket_key - 0.01, bucket_key, bucket_key + 0.01]:
            if adj_key in diameter_buckets:
                nearby.extend(diameter_buckets[adj_key])

        for i, c1 in nearby:
            if i in processed_indices:
                continue

            current_group = [c1]
            processed_indices.add(i)

            for j, c2 in nearby:
                if j in processed_indices:
                    continue
                if abs(c1["diameter"] - c2["diameter"]) > 0.01:
                    continue

                dot = c1["axis"][0] * c2["axis"][0] + c1["axis"][1] * c2["axis"][1] + c1["axis"][2] * c2["axis"][2]
                if abs(abs(dot) - 1.0) > 0.01:
                    continue

                dx = c2["axis_origin"][0] - c1["axis_origin"][0]
                dy = c2["axis_origin"][1] - c1["axis_origin"][1]
                dz = c2["axis_origin"][2] - c1["axis_origin"][2]

                cx = dy * c1["axis"][2] - dz * c1["axis"][1]
                cy = dz * c1["axis"][0] - dx * c1["axis"][2]
                cz = dx * c1["axis"][1] - dy * c1["axis"][0]
                dist_sq = cx * cx + cy * cy + cz * cz

                if dist_sq < 0.01:
                    t1 = c1["position"][0] * c1["axis"][0] + c1["position"][1] * c1["axis"][1] + c1["position"][2] * c1["axis"][2]
                    t2 = c2["position"][0] * c1["axis"][0] + c2["position"][1] * c1["axis"][1] + c2["position"][2] * c1["axis"][2]
                    if abs(t1 - t2) < 5.0:
                        current_group.append(c2)
                        processed_indices.add(j)

            grouped_holes.append(current_group)

    holes = []
    for group in grouped_holes:
        total_angle = sum(c["angle"] for c in group)
        min_angle = 160 if is_flat_pattern else 270
        group_diameter = group[0]["diameter"] if group else 0.0
        if is_flat_pattern and group_diameter > 100:
            min_angle = 300

        if total_angle > min_angle:
            max_depth = max(c["depth"] for c in group)
            first = group[0]
            diameter = first["diameter"]
            hole_axis = first["axis"]

            skip_hole = False
            min_dim = None
            if filter_bores and is_turned and part_dims:
                min_dim = part_dims[0]
                if max_depth > min_dim * 0.5:
                    skip_hole = True

            criteria = [
                make_criterion("angle_coverage", round(total_angle, 3), round(min_angle, 3), total_angle > min_angle, "Totale cilindrische dekking"),
                make_criterion("bore_filter", round(max_depth, 3), round(min_dim * 0.5, 3) if filter_bores and is_turned and part_dims else None, not skip_hole, "Bore-filter voor draaistukken"),
            ]

            if not skip_hole:
                holes.append(HoleFeature(
                    diameter=diameter,
                    depth=max_depth,
                    position=first["position"],
                    axis=hole_axis,
                    id=first["id"],
                ))
                debug_items.append(make_hole_debug_item(
                    first["id"],
                    "accepted",
                    "Geaccepteerd als cilindrisch gat",
                    criteria,
                    {
                        "diameter": diameter,
                        "depth": max_depth,
                        "position": first["position"],
                        "axis": hole_axis,
                        "source": "flat" if is_flat_pattern else "3d",
                    },
                ))
            else:
                debug_items.append(make_hole_debug_item(
                    first["id"],
                    "rejected",
                    "Afgewezen als boring in draaideel",
                    criteria,
                    {
                        "diameter": diameter,
                        "depth": max_depth,
                        "position": first["position"],
                        "axis": hole_axis,
                        "source": "flat" if is_flat_pattern else "3d",
                    },
                ))
        else:
            first = group[0]
            debug_items.append(make_hole_debug_item(
                first["id"],
                "rejected",
                "Afgewezen op onvoldoende cilindrische dekking",
                [make_criterion("angle_coverage", round(total_angle, 3), round(min_angle, 3), False, "Totale cilindrische dekking te laag")],
                {
                    "diameter": first["diameter"],
                    "depth": max(c["depth"] for c in group),
                    "position": first["position"],
                    "axis": first["axis"],
                    "source": "flat" if is_flat_pattern else "3d",
                },
            ))

    if return_debug:
        return holes, debug_items
    return holes


def _classify_shaped_inner_wire(edge_count, lines, circles, radii, lengths, bbox_dims):
    dims = sorted(abs(value) for value in bbox_dims)
    dim_str = f"{dims[2]:.1f}x{dims[1]:.1f}"

    if lines == 2 and circles == 2:
        radius = sum(radii) / len(radii) if radii else 0
        line_length = max(lengths) if lengths else 0
        width = 2 * radius
        total_length = line_length + (2 * radius)
        return "Slot", f"{total_length:.1f}x{width:.1f}", "slot_like"
    if lines >= 4 and circles >= 4:
        return "Rect (R)", dim_str, "rounded_rect_like"
    if lines >= 3 and circles == 0:
        return ("Rect" if lines == 4 else "Poly"), dim_str, "polygonal"
    if edge_count >= 2:
        return "Closed contour", dim_str, "closed_contour"
    return "unknown", dim_str, "unknown"


def _sample_edge_points(edge, reverse=False):
    try:
        curve = BRepAdaptor_Curve(TopoDS.Edge_s(edge))
        c_type = curve.GetType()
        if c_type == GeomAbs_Circle:
            segments = 18
        elif c_type == GeomAbs_Line:
            segments = 2
        else:
            segments = 8

        u_start = curve.FirstParameter()
        u_end = curve.LastParameter()
        if reverse:
            u_start, u_end = u_end, u_start

        points = []
        for idx in range(segments):
            t = u_start if segments == 1 else u_start + (u_end - u_start) * (idx / (segments - 1))
            point = curve.Value(t)
            points.append((point.X(), point.Y(), point.Z()))
        return points
    except Exception:
        return []


def _edge_end_keys(edge, tolerance):
    exp = TopExp_Explorer(edge, TopAbs_VERTEX)
    vertices = []
    while exp.More():
        vertices.append(TopoDS.Vertex_s(exp.Current()))
        exp.Next()

    if len(vertices) < 2:
        return None

    start = BRep_Tool.Pnt_s(vertices[0])
    end = BRep_Tool.Pnt_s(vertices[-1])
    start_point = (float(start.X()), float(start.Y()), float(start.Z()))
    end_point = (float(end.X()), float(end.Y()), float(end.Z()))

    def _key(point):
        return (round(point[0] / tolerance), round(point[1] / tolerance), round(point[2] / tolerance))

    return _key(start_point), _key(end_point), start_point, end_point


def _recover_contours_from_bucket(bucket_entries, tolerance=0.05):
    if not bucket_entries:
        return [], []

    from collections import defaultdict

    edge_records = []
    adjacency = defaultdict(list)

    for entry in bucket_entries:
        for edge in entry.get("edges") or []:
            end_info = _edge_end_keys(edge, tolerance)
            if end_info is None:
                continue
            start_key, end_key, start_point, end_point = end_info
            rec = {
                "edge": edge,
                "start_key": start_key,
                "end_key": end_key,
                "start_point": start_point,
                "end_point": end_point,
                "normal": entry.get("normal"),
                "source": entry.get("source", "3d"),
            }
            edge_index = len(edge_records)
            edge_records.append(rec)
            adjacency[start_key].append((edge_index, False))
            adjacency[end_key].append((edge_index, True))

    if not edge_records:
        return [], []

    used_edges = set()
    recovered = []
    debug_items = []

    for edge_index, edge_record in enumerate(edge_records):
        if edge_index in used_edges:
            continue

        chain = [(edge_index, False)]
        used_edges.add(edge_index)
        start_key = edge_record["start_key"]
        current_key = edge_record["end_key"]
        max_steps = max(32, len(edge_records) * 2)
        closed = False

        while max_steps > 0:
            max_steps -= 1
            if current_key == start_key and len(chain) >= 3:
                closed = True
                break

            next_choice = None
            for candidate_index, reverse in adjacency.get(current_key, []):
                if candidate_index in used_edges:
                    continue
                next_choice = (candidate_index, reverse)
                break

            if next_choice is None:
                break

            candidate_index, reverse = next_choice
            chain.append((candidate_index, reverse))
            used_edges.add(candidate_index)
            candidate = edge_records[candidate_index]
            current_key = candidate["start_key"] if reverse else candidate["end_key"]

        if not closed:
            continue

        contour_points = []
        edge_lengths = []
        lines = 0
        circles = 0
        radii = []
        line_lengths = []

        for chain_index, (candidate_index, reverse) in enumerate(chain):
            rec = edge_records[candidate_index]
            edge = rec["edge"]
            sampled = _sample_edge_points(edge, reverse=reverse)
            if not sampled:
                continue
            if chain_index > 0 and contour_points:
                sampled = sampled[1:]
            contour_points.extend(sampled)

            edge_props = GProp_GProps()
            BRepGProp.LinearProperties_s(edge, edge_props)
            edge_length = float(edge_props.Mass())
            edge_lengths.append(edge_length)

            curve = BRepAdaptor_Curve(TopoDS.Edge_s(edge))
            c_type = curve.GetType()
            if c_type == GeomAbs_Line:
                lines += 1
                line_lengths.append(edge_length)
            elif c_type == GeomAbs_Circle:
                circles += 1
                try:
                    radii.append(float(curve.Circle().Radius()))
                except Exception:
                    pass

        if len(contour_points) < 4:
            continue

        first_point = contour_points[0]
        last_point = contour_points[-1]
        close_dist = math.sqrt((first_point[0] - last_point[0]) ** 2 + (first_point[1] - last_point[1]) ** 2 + (first_point[2] - last_point[2]) ** 2)
        if close_dist > max(0.25, tolerance * 6.0):
            continue
        if edge_lengths and sum(edge_lengths) <= 1e-3:
            continue

        xs = [pt[0] for pt in contour_points]
        ys = [pt[1] for pt in contour_points]
        zs = [pt[2] for pt in contour_points]
        dx = max(xs) - min(xs)
        dy = max(ys) - min(ys)
        dz = max(zs) - min(zs)

        shape_type, dim_str, shape_family = _classify_shaped_inner_wire(len(chain), lines, circles, radii, line_lengths, (dx, dy, dz))
        if shape_type == "unknown":
            shape_type = "Recovered contour"
            shape_family = "recovered_mixed"

        center = (sum(xs) / len(xs), sum(ys) / len(ys), sum(zs) / len(zs))
        perimeter = float(sum(edge_lengths))
        normal = next((edge_records[idx]["normal"] for idx, _ in chain if edge_records[idx].get("normal") is not None), (0.0, 0.0, 1.0))
        source = next((edge_records[idx]["source"] for idx, _ in chain if edge_records[idx].get("source") is not None), "3d")

        item_id = f"hole-recovered-{len(recovered)}"
        recovered.append({
            "id": item_id,
            "type": shape_type,
            "dim": dim_str,
            "center": center,
            "normal": normal,
            "perimeter": perimeter,
            "contour_points": contour_points,
            "method": "recovery_bucket_fallback",
        })
        debug_items.append({
            "id": item_id,
            "status": "accepted",
            "type": str(shape_type).lower().replace(" ", "_"),
            "label": dim_str or shape_type,
            "reason": "Geaccepteerd via recovery bucket (gemengde contour line/arc)",
            "method": "recovery_bucket_fallback",
            "criteria": [
                {"name": "method_order", "value": "fallback", "threshold": "face_boundary_primary_first", "passed": True, "note": "Pas gebruikt nadat Face Boundary geen herkenbare vorm gaf"},
                {"name": "recovery_bucket", "value": True, "threshold": True, "passed": True, "note": "Wire walking op afgewezen contour-fragmenten"},
                {"name": "edge_count", "value": len(chain), "threshold": 3, "passed": len(chain) >= 3, "note": "Minimale gesloten lus"},
                {"name": "closed_loop", "value": round(close_dist, 4), "threshold": round(max(0.25, tolerance * 6.0), 4), "passed": True, "note": "Begin/eind binnen closure tolerance"},
                {"name": "shape_family", "value": shape_family, "threshold": "slot/rect/poly/recovered_mixed", "passed": True, "note": "Recovered contour classificatie"},
            ],
            "position": center,
            "normal": normal,
            "size": dim_str,
            "perimeter": perimeter,
            "contour_points": contour_points,
            "source": source,
        })

    return recovered, debug_items


def detect_shaped_holes(shape, face_data=None, is_flat_pattern=False, return_debug=False):
    """Detect non-circular holes (slots, rectangles, generic contours)."""
    all_shaped_holes = []
    debug_items = []
    recovery_bucket = []
    candidate_counter = 0

    def make_criterion(name, value=None, threshold=None, passed=True, note=None):
        return {
            "name": name,
            "value": value,
            "threshold": threshold,
            "passed": bool(passed),
            "note": note,
        }

    if face_data is not None:
        planar_faces = [(fd["face"], fd["normal"]) for fd in face_data if fd["type"] == "plane"]
    else:
        faces = shape.faces().vals()
        planar_faces = []
        for face in faces:
            surf = BRepAdaptor_Surface(face.wrapped, True)
            if surf.GetType() == GeomAbs_Plane:
                pln = surf.Plane()
                axis = pln.Axis().Direction()
                planar_faces.append((face, (axis.X(), axis.Y(), axis.Z())))

    source = "flat" if is_flat_pattern else "3d"
    if not planar_faces:
        return ([], []) if return_debug else []

    for face, normal in planar_faces:
        wires = face.Wires()
        sorted_wires = []
        for wire in wires:
            bbox = Bnd_Box()
            BRepBndLib.Add_s(wire.wrapped, bbox)
            xmin, ymin, zmin, xmax, ymax, zmax = bbox.Get()
            diag = math.sqrt((xmax - xmin) ** 2 + (ymax - ymin) ** 2 + (zmax - zmin) ** 2)
            sorted_wires.append((wire, diag))

        sorted_wires.sort(key=lambda item: item[1], reverse=True)
        if len(sorted_wires) <= 1:
            continue

        inner_wires = [wire_info[0] for wire_info in sorted_wires[1:]]
        for wire in inner_wires:
            edges = []
            iterator = TopExp_Explorer(wire.wrapped, TopAbs_EDGE)
            while iterator.More():
                edges.append(iterator.Current())
                iterator.Next()
            if not edges:
                continue

            is_circle = False
            if len(edges) == 1:
                curve = BRepAdaptor_Curve(TopoDS.Edge_s(edges[0]))
                if curve.GetType() == GeomAbs_Circle:
                    is_circle = True
            elif len(edges) == 2:
                c1 = BRepAdaptor_Curve(TopoDS.Edge_s(edges[0]))
                c2 = BRepAdaptor_Curve(TopoDS.Edge_s(edges[1]))
                if c1.GetType() == GeomAbs_Circle and c2.GetType() == GeomAbs_Circle:
                    is_circle = True
            if is_circle:
                continue

            lines = 0
            circles = 0
            radii = []
            lengths = []
            for edge in edges:
                curve = BRepAdaptor_Curve(TopoDS.Edge_s(edge))
                c_type = curve.GetType()
                if c_type == GeomAbs_Line:
                    lines += 1
                    p1 = curve.Value(curve.FirstParameter())
                    p2 = curve.Value(curve.LastParameter())
                    lengths.append(p1.Distance(p2))
                elif c_type == GeomAbs_Circle:
                    circles += 1
                    radii.append(curve.Circle().Radius())

            bbox = Bnd_Box()
            BRepBndLib.Add_s(wire.wrapped, bbox)
            xmin, ymin, zmin, xmax, ymax, zmax = bbox.Get()
            dx = xmax - xmin
            dy = ymax - ymin
            dz = zmax - zmin
            shape_type, dim_str, shape_family = _classify_shaped_inner_wire(len(edges), lines, circles, radii, lengths, (dx, dy, dz))

            wire_props = GProp_GProps()
            BRepGProp.LinearProperties_s(wire.wrapped, wire_props)
            center_mass = wire_props.CentreOfMass()
            center = (center_mass.X(), center_mass.Y(), center_mass.Z())
            perimeter = float(wire_props.Mass())
            contour_points = []
            for edge in edges:
                contour_points.extend(_sample_edge_points(edge))
            if contour_points and contour_points[0] != contour_points[-1]:
                contour_points.append(contour_points[0])

            item_id = f"hole-shaped-{candidate_counter}"
            candidate_counter += 1

            if shape_type == "unknown":
                candidate = {
                    "id": item_id,
                    "type": "Irregular contour",
                    "dim": dim_str,
                    "center": center,
                    "normal": normal,
                    "perimeter": perimeter,
                    "contour_points": contour_points,
                    "method": "face_boundary_primary",
                }
                debug_items.append({
                    "id": item_id,
                    "status": "accepted",
                    "type": "irregular_contour",
                    "label": dim_str or "Irregular contour",
                    "reason": "Geaccepteerd als irregulaire gesloten contour via Face Boundary",
                    "method": "face_boundary_primary",
                    "criteria": [
                        make_criterion("method_order", "primary", "face_boundary_primary_first", True, "Eerst geprobeerd via inner wires van face"),
                        make_criterion("face_boundary", True, True, True, "Inner wire kandidaat vanuit face boundaries"),
                        make_criterion("recognized_shape", "unknown", "known", True, f"{lines} lijnen / {circles} bogen"),
                        make_criterion("irregular_contour_policy", True, True, True, "Onbekende gesloten contour toch als gat teruggeven"),
                    ],
                    "position": center,
                    "normal": normal,
                    "size": dim_str,
                    "perimeter": perimeter,
                    "contour_points": contour_points,
                    "source": source,
                })
            else:
                candidate = {
                    "id": item_id,
                    "type": shape_type,
                    "dim": dim_str,
                    "center": center,
                    "normal": normal,
                    "perimeter": perimeter,
                    "contour_points": contour_points,
                    "method": "face_boundary_primary",
                }
                debug_items.append({
                    "id": item_id,
                    "status": "accepted",
                    "type": str(shape_type).lower().replace(" ", "_"),
                    "label": dim_str or shape_type,
                    "reason": "Geaccepteerd als generieke gesloten contour" if shape_type == "Closed contour" else f"Geaccepteerd als {shape_type}",
                    "method": "face_boundary_primary",
                    "criteria": [
                        make_criterion("method_order", "primary", "face_boundary_primary_first", True, "Eerst geprobeerd via inner wires van face"),
                        make_criterion("face_boundary", True, True, True, "Outer wire uitgesloten; inner wires als hole-kandidaten"),
                        make_criterion("recognized_shape", shape_type, "known", True, f"{lines} lijnen / {circles} bogen"),
                        make_criterion("shape_family", shape_family, "slot/rect/poly/closed_contour", True, "Inner wire op planar face"),
                        make_criterion("closed_inner_wire", True, True, True, "Inner wire van planar face wordt als gesloten contour behandeld"),
                        make_criterion("is_circle", False, False, True, "Niet door de cilindrische detector afgehandeld"),
                    ],
                    "position": center,
                    "normal": normal,
                    "size": dim_str,
                    "perimeter": perimeter,
                    "contour_points": contour_points,
                    "source": source,
                })

            all_shaped_holes.append(candidate)

    recovered_holes, recovered_debug = _recover_contours_from_bucket(recovery_bucket)
    if recovered_holes:
        all_shaped_holes.extend(recovered_holes)
        debug_items.extend(recovered_debug)

    from collections import defaultdict

    type_dim_buckets = defaultdict(list)
    for idx, hole in enumerate(all_shaped_holes):
        type_dim_buckets[(hole["type"], hole["dim"])].append((idx, hole))

    unique_holes = []
    processed_indices = set()

    for bucket in type_dim_buckets.values():
        for i, h1 in bucket:
            if i in processed_indices:
                continue

            for j, h2 in bucket:
                if i == j or j in processed_indices:
                    continue
                dx = h2["center"][0] - h1["center"][0]
                dy = h2["center"][1] - h1["center"][1]
                dz = h2["center"][2] - h1["center"][2]
                dist_sq = dx * dx + dy * dy + dz * dz

                if dist_sq < 0.01:
                    processed_indices.add(j)
                else:
                    dist = math.sqrt(dist_sq)
                    if dist > 0:
                        vx, vy, vz = dx / dist, dy / dist, dz / dist
                        nx, ny, nz = h1["normal"]
                        dot = abs(vx * nx + vy * ny + vz * nz)
                        if dot > 0.9:
                            processed_indices.add(j)

                if j in processed_indices:
                    rejected_id = h2.get("id")
                    for item in debug_items:
                        if item.get("id") == rejected_id:
                            item["status"] = "rejected"
                            item["reason"] = "Afgewezen als duplicaat van een shaped hole op hetzelfde vlak"
                            item["criteria"].append(make_criterion("deduplicate", True, False, False, "Duplicaat op zelfde vlak"))

            unique_holes.append(h1)
            processed_indices.add(i)

    if return_debug:
        return unique_holes, debug_items
    return unique_holes


def deduplicate_holes(circular_holes, shaped_holes, return_debug=False):
    """Remove circular holes that are part of a shaped hole."""
    if not shaped_holes:
        return (circular_holes, []) if return_debug else circular_holes

    filtered_circular = []
    rejected = []

    for circ in circular_holes:
        is_duplicate = False
        c_pos = circ.position
        for shaped in shaped_holes:
            s_pos = shaped["center"]

            if shaped.get("method") in {"face_boundary_round_contour_fallback", "face_boundary_circular_wire_fallback"}:
                continue

            shaped_normal = shaped.get("normal")
            if shaped_normal and hasattr(circ, "axis") and circ.axis:
                dot = abs(circ.axis[0] * shaped_normal[0] + circ.axis[1] * shaped_normal[1] + circ.axis[2] * shaped_normal[2])
                if dot < 0.7:
                    continue

            dx = c_pos[0] - s_pos[0]
            dy = c_pos[1] - s_pos[1]
            dz = c_pos[2] - s_pos[2]
            dist = math.sqrt(dx * dx + dy * dy + dz * dz)

            try:
                dims = [float(x) for x in shaped["dim"].split("x")]
                max_dim = max(dims)
            except Exception:
                max_dim = 20.0

            min_dim = min(dims) if "dims" in locals() and len(dims) >= 2 else max_dim
            circ_diam = circ.diameter
            if circ_diam < min_dim * 0.25:
                continue

            if dist < (max_dim * 0.8):
                is_duplicate = True
                rejected.append({
                    "id": getattr(circ, "id", None),
                    "reason": "Afgewezen als onderdeel van een shaped hole",
                    "overlap_with": {
                        "id": shaped.get("id"),
                        "method": shaped.get("method"),
                        "type": shaped.get("type"),
                        "label": shaped.get("dim") or shaped.get("type"),
                        "position": shaped.get("center"),
                        "distance": round(dist, 3),
                    },
                    "criteria": [
                        {
                            "name": "duplicate_of_shaped_hole",
                            "value": round(dist, 3),
                            "threshold": round(max_dim * 0.8, 3),
                            "passed": False,
                            "note": f"Nabij shaped hole {shaped.get('dim', shaped.get('type', 'unknown'))}",
                        }
                    ],
                })
                break

        if not is_duplicate:
            filtered_circular.append(circ)

    if return_debug:
        return filtered_circular, rejected
    return filtered_circular
