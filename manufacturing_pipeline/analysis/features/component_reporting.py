from __future__ import annotations

import math
import os
import uuid

from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepGProp import BRepGProp
from OCP.Bnd import Bnd_Box
from OCP.GProp import GProp_GProps
from OCP.GeomAbs import (
    GeomAbs_BezierSurface,
    GeomAbs_BSplineSurface,
    GeomAbs_Cone,
    GeomAbs_Cylinder,
    GeomAbs_Plane,
    GeomAbs_Sphere,
    GeomAbs_Torus,
)
from OCP.TopAbs import (
    TopAbs_EDGE,
    TopAbs_FACE,
    TopAbs_REVERSED,
    TopAbs_SHELL,
    TopAbs_SOLID,
    TopAbs_VERTEX,
)
from OCP.TopExp import TopExp_Explorer


def _analyze_part_manufacturing(cq_part, volume, part_holes, *, iso_provider):
    manufacturing = {
        "holes_with_fits": [],
        "threads": [],
        "chamfers_fillets": None,
        "mass_estimates": None,
    }

    if part_holes:
        diameter_groups = {}
        for hole in part_holes:
            d_rounded = round(hole.diameter, 1)
            diameter_groups.setdefault(d_rounded, []).append(hole)

        for diameter, hole_list in diameter_groups.items():
            fit_analysis = iso_provider.analyze_hole_fit(diameter)
            thread_matches = iso_provider.identify_thread_from_diameter(diameter, 0.15)
            thread_info = None
            if thread_matches:
                best = thread_matches[0]
                thread_info = {
                    "designation": best.designation,
                    "pitch": best.pitch,
                    "tap_drill": iso_provider.get_tap_drill_size(best.designation),
                }
                manufacturing["threads"].append(
                    {
                        "diameter": diameter,
                        "thread_designation": best.designation,
                        "pitch": best.pitch,
                        "tap_drill": iso_provider.get_tap_drill_size(best.designation),
                        "count": len(hole_list),
                    }
                )

            manufacturing["holes_with_fits"].append(
                {
                    "diameter": diameter,
                    "count": len(hole_list),
                    "fit_recommendation": fit_analysis["primary_recommendation"],
                    "tolerances": fit_analysis["tolerances"],
                    "possible_thread": thread_info,
                }
            )

        manufacturing["holes_with_fits"].sort(key=lambda item: item["diameter"])

    try:
        all_faces = cq_part.faces().vals()
        chamfers = []
        fillets = []
        for face in all_faces:
            surf = BRepAdaptor_Surface(face.wrapped, True)
            stype = surf.GetType()

            if stype == GeomAbs_Cone:
                cone = surf.Cone()
                angle_deg = math.degrees(cone.SemiAngle())
                if 40 <= angle_deg <= 50:
                    chamfers.append(round(cone.RefRadius() * 0.3, 2))
            elif stype == GeomAbs_Torus:
                torus = surf.Torus()
                minor_radius = torus.MinorRadius()
                major_radius = torus.MajorRadius()
                if minor_radius < major_radius * 0.5 and minor_radius < 20:
                    fillets.append(round(minor_radius, 2))

        avg_chamfer = sum(chamfers) / len(chamfers) if chamfers else 0
        avg_fillet = sum(fillets) / len(fillets) if fillets else 0
        manufacturing["chamfers_fillets"] = {
            "chamfer_count": len(chamfers),
            "chamfer_avg": round(avg_chamfer, 2),
            "fillet_count": len(fillets),
            "fillet_avg": round(avg_fillet, 2),
        }
    except Exception:
        manufacturing["chamfers_fillets"] = {
            "chamfer_count": 0,
            "chamfer_avg": 0,
            "fillet_count": 0,
            "fillet_avg": 0,
        }

    volume_m3 = volume / 1e9
    manufacturing["mass_estimates"] = {
        "steel_s235": round(volume_m3 * 7850, 3),
        "alu_6061": round(volume_m3 * 2700, 3),
    }
    return manufacturing


def analyze_components_detailed(
    cq_object,
    output_dir,
    *,
    cq_module,
    detect_holes_fn,
    detect_shaped_holes_fn,
    analyze_sheet_metal_fn,
    analyze_part_manufacturing_fn,
):
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    shape = cq_object.val().wrapped
    unique_parts = {}

    exp = TopExp_Explorer(shape, TopAbs_SOLID)
    while exp.More():
        solid = exp.Current()
        props = GProp_GProps()
        BRepGProp.VolumeProperties_s(solid, props)
        volume = props.Mass()

        bbox = Bnd_Box()
        BRepBndLib.Add_s(solid, bbox)
        xmin, ymin, zmin, xmax, ymax, zmax = bbox.Get()
        dims = sorted([xmax - xmin, ymax - ymin, zmax - zmin])
        sig = (round(volume, 2), round(dims[0], 2), round(dims[1], 2), round(dims[2], 2))

        if sig not in unique_parts:
            part_id = str(uuid.uuid4())[:8]
            image_filename = f"part_{part_id}.svg"
            image_path = os.path.join(output_dir, image_filename)
            cq_solid = cq_module.Shape.cast(solid)
            cq_wp = cq_module.Workplane(obj=cq_solid)
            part_holes = detect_holes_fn(cq_wp)
            hole_summary = "None"
            if part_holes:
                from collections import Counter

                diams = [round(h.diameter, 1) for h in part_holes]
                counts = Counter(diams)
                hole_summary = ", ".join(f"{c}x Ø{d}mm" for d, c in counts.items())

            sm_data = analyze_sheet_metal_fn(solid)

            try:
                cq_module.exporters.export(
                    cq_wp,
                    image_path,
                    opt={
                        "width": 200,
                        "height": 200,
                        "marginLeft": 5,
                        "marginTop": 5,
                        "showAxes": False,
                        "projectionDir": (1, 1, 1),
                        "strokeWidth": 0.5,
                        "strokeColor": (0, 0, 0),
                        "hiddenColor": (100, 100, 100),
                        "showHidden": True,
                    },
                )
            except Exception:
                image_path = None

            classification = "Unknown"
            bbox_vol = dims[0] * dims[1] * dims[2] if dims[0] > 0 else 1.0
            if sm_data["is_sheet_metal"]:
                classification = "Sheet Metal"
                if sm_data["bend_count"] > 0:
                    classification += " (Bent)"
            elif volume < 1000:
                if dims[2] / dims[1] > 3:
                    classification = "Fastener (Bolt/Screw/Pin)"
                elif dims[0] < dims[1] * 0.2:
                    classification = "Washer/Spacer"
                else:
                    classification = "Small Component"
            else:
                aspect_ratio = dims[2] / dims[1]
                flatness = dims[0] / dims[1]
                if flatness < 0.1:
                    classification = "Plate/Sheet"
                elif aspect_ratio > 5:
                    classification = "Shaft/Bar"
                elif volume / bbox_vol > 0.5:
                    classification = "Block/Housing"
                else:
                    classification = "Complex Part"

            part_holes = detect_holes_fn(cq_wp)
            shaped_holes = detect_shaped_holes_fn(cq_wp)
            part_manufacturing = analyze_part_manufacturing_fn(cq_wp, volume, part_holes)

            length = dims[2]
            width = dims[1]
            thickness = dims[0]
            if sm_data["is_sheet_metal"]:
                thickness = sm_data["thickness"]
                form = "Plaat"
            elif "Shaft" in classification or "Bar" in classification:
                form = "Profiel"
            else:
                form = "Overig"

            production_data = {
                "CalcID": part_id,
                "ArtikelNr": f"ART-{part_id}",
                "Aantal": 1,
                "Vorm": form,
                "Lengte": round(length, 2),
                "Breedte": round(width, 2),
                "Dikte": round(thickness, 2),
                "Hoogte": round(dims[0], 2),
                "Snijgaten": len(part_holes) + len(shaped_holes),
                "DiaSnijgat": sorted(
                    [round(h.diameter, 1) for h in part_holes] + [h["dim"] for h in shaped_holes],
                    key=lambda value: str(value),
                ),
                "ZetAantal": sm_data["bend_count"],
                "Aantaltegenzet": sm_data.get("counter_bend_count", 0),
            }

            unique_parts[sig] = {
                "id": part_id,
                "count": 1,
                "volume": volume,
                "dimensions": dims,
                "classification": classification,
                "image_path": image_path,
                "hole_summary": hole_summary,
                "holes": [{"diameter": h.diameter, "depth": h.depth} for h in part_holes],
                "sheet_metal": sm_data,
                "manufacturing": part_manufacturing,
                "production_data": production_data,
            }
        else:
            unique_parts[sig]["count"] += 1
            unique_parts[sig]["production_data"]["Aantal"] += 1

        exp.Next()

    return list(unique_parts.values())


def get_topology_stats(cq_object):
    shape = cq_object.val().wrapped
    stats = {"solids": 0, "shells": 0, "faces": 0, "edges": 0, "vertices": 0}
    for entity_type, key in [
        (TopAbs_SOLID, "solids"),
        (TopAbs_SHELL, "shells"),
        (TopAbs_FACE, "faces"),
        (TopAbs_EDGE, "edges"),
        (TopAbs_VERTEX, "vertices"),
    ]:
        exp = TopExp_Explorer(shape, entity_type)
        while exp.More():
            stats[key] += 1
            exp.Next()
    return stats


def classify_components(cq_object):
    shape = cq_object.val().wrapped
    classification = {
        "Fastener (Bolt/Screw/Pin)": 0,
        "Washer/Spacer": 0,
        "Plate/Sheet": 0,
        "Shaft/Bar": 0,
        "Block/Housing": 0,
        "Complex/Other": 0,
    }

    exp = TopExp_Explorer(shape, TopAbs_SOLID)
    while exp.More():
        solid = exp.Current()
        props = GProp_GProps()
        BRepGProp.VolumeProperties_s(solid, props)
        volume = props.Mass()

        bbox = Bnd_Box()
        BRepBndLib.Add_s(solid, bbox)
        xmin, ymin, zmin, xmax, ymax, zmax = bbox.Get()
        dims = sorted([xmax - xmin, ymax - ymin, zmax - zmin])
        bbox_vol = dims[0] * dims[1] * dims[2] if dims[0] > 0 else 1.0

        if volume < 1000:
            if dims[2] / dims[1] > 3:
                classification["Fastener (Bolt/Screw/Pin)"] += 1
            elif dims[0] < dims[1] * 0.2:
                classification["Washer/Spacer"] += 1
            else:
                classification["Fastener (Bolt/Screw/Pin)"] += 1
        else:
            aspect_ratio = dims[2] / dims[1]
            flatness = dims[0] / dims[1]
            if flatness < 0.1:
                classification["Plate/Sheet"] += 1
            elif aspect_ratio > 5:
                classification["Shaft/Bar"] += 1
            elif volume / bbox_vol > 0.5:
                classification["Block/Housing"] += 1
            else:
                classification["Complex/Other"] += 1
        exp.Next()

    return classification


def get_geometric_properties(cq_object):
    shape = cq_object.val().wrapped
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, props)
    volume = props.Mass()
    center_of_mass = props.CentreOfMass()

    BRepGProp.SurfaceProperties_s(shape, props)
    surface_area = props.Mass()

    bbox = Bnd_Box()
    BRepBndLib.Add_s(shape, bbox)
    xmin, ymin, zmin, xmax, ymax, zmax = bbox.Get()
    return {
        "volume": volume,
        "surface_area": surface_area,
        "center_of_mass": (center_of_mass.X(), center_of_mass.Y(), center_of_mass.Z()),
        "bounding_box": {
            "min": (xmin, ymin, zmin),
            "max": (xmax, ymax, zmax),
            "dimensions": (xmax - xmin, ymax - ymin, zmax - zmin),
        },
    }


def analyze_faces(cq_object):
    counts = {
        "Plane": 0,
        "Cylinder": 0,
        "Cone": 0,
        "Sphere": 0,
        "Torus": 0,
        "Bezier": 0,
        "BSpline": 0,
        "Other": 0,
    }

    for face in cq_object.faces().vals():
        surf = BRepAdaptor_Surface(face.wrapped, True)
        stype = surf.GetType()
        if stype == GeomAbs_Plane:
            counts["Plane"] += 1
        elif stype == GeomAbs_Cylinder:
            counts["Cylinder"] += 1
        elif stype == GeomAbs_Cone:
            counts["Cone"] += 1
        elif stype == GeomAbs_Sphere:
            counts["Sphere"] += 1
        elif stype == GeomAbs_Torus:
            counts["Torus"] += 1
        elif stype == GeomAbs_BezierSurface:
            counts["Bezier"] += 1
        elif stype == GeomAbs_BSplineSurface:
            counts["BSpline"] += 1
        else:
            counts["Other"] += 1
    return counts


def debug_hole_detection(cq_object, *, detect_holes_fn):
    debug_info = {
        "total_faces": 0,
        "cylindrical_faces": [],
        "rejected_faces": [],
        "candidates": [],
        "final_holes": [],
    }

    all_faces = cq_object.faces().vals()
    debug_info["total_faces"] = len(all_faces)
    for i, face in enumerate(all_faces):
        surf = BRepAdaptor_Surface(face.wrapped, True)
        if surf.GetType() != GeomAbs_Cylinder:
            continue

        cylinder = surf.Cylinder()
        radius = cylinder.Radius()
        orientation = face.wrapped.Orientation()
        u_min = surf.FirstUParameter()
        u_max = surf.LastUParameter()
        angle_deg = math.degrees(abs(u_max - u_min))

        face_info = {
            "face_index": i,
            "diameter": round(radius * 2, 2),
            "orientation": "REVERSED" if orientation == TopAbs_REVERSED else "FORWARD",
            "angle_deg": round(angle_deg, 1),
            "is_internal": orientation == TopAbs_REVERSED,
        }
        debug_info["cylindrical_faces"].append(face_info)

        if orientation != TopAbs_REVERSED:
            debug_info["rejected_faces"].append(
                {**face_info, "reason": "Not REVERSED orientation (external cylinder/boss)"}
            )
        else:
            debug_info["candidates"].append(face_info)

    holes = detect_holes_fn(cq_object)
    debug_info["final_holes"] = [
        {"diameter": hole.diameter, "depth": hole.depth, "position": hole.position}
        for hole in holes
    ]
    return debug_info
