from __future__ import annotations

import math

from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_Cone, GeomAbs_Cylinder, GeomAbs_Torus
from OCP.GProp import GProp_GProps
from OCP.BRepGProp import BRepGProp


def detect_threads(cq_object, detect_holes_fn, iso_provider, tolerance=0.15):
    holes = detect_holes_fn(cq_object)
    thread_candidates = []

    for hole in holes:
        diameter = hole.diameter
        matches = iso_provider.identify_thread_from_diameter(diameter, tolerance)
        if not matches:
            continue

        coarse_matches = [m for m in matches if getattr(m, "is_coarse", False)]
        best_match = coarse_matches[0] if coarse_matches else matches[0]

        thread_candidates.append(
            {
                "diameter": diameter,
                "depth": hole.depth,
                "position": hole.position,
                "thread_designation": best_match.designation,
                "pitch": best_match.pitch,
                "is_coarse": getattr(best_match, "is_coarse", False),
                "minor_diameter": getattr(best_match, "minor_diameter", 0.0),
                "tap_drill": iso_provider.get_tap_drill_size(best_match.designation),
                "all_matches": [m.designation for m in matches[:3]],
            }
        )

    return thread_candidates


def detect_shafts(cq_object, iso_provider):
    shafts = []
    all_faces = cq_object.faces().vals()
    cylinder_data = []

    for face in all_faces:
        surf = BRepAdaptor_Surface(face.wrapped, True)
        if surf.GetType() != GeomAbs_Cylinder:
            continue

        cylinder = surf.Cylinder()
        radius = cylinder.Radius()
        location = cylinder.Location()

        props = GProp_GProps()
        BRepGProp.SurfaceProperties_s(face.wrapped, props)
        area = props.Mass()
        circumference = 2 * math.pi * radius
        length = area / circumference if circumference > 0 else 0.0

        cylinder_data.append(
            {
                "diameter": radius * 2,
                "length": length,
                "position": (location.X(), location.Y(), location.Z()),
            }
        )

    if cylinder_data:
        cylinder_data.sort(key=lambda x: x["diameter"], reverse=True)
        seen_diameters = set()
        for cyl in cylinder_data:
            d = round(cyl["diameter"], 1)
            if d in seen_diameters or d <= 3.0:
                continue
            seen_diameters.add(d)
            fit_analysis = iso_provider.analyze_hole_fit(cyl["diameter"])
            shafts.append(
                {
                    "diameter": cyl["diameter"],
                    "length": cyl["length"],
                    "position": cyl["position"],
                    "fit_recommendation": fit_analysis["primary_recommendation"],
                }
            )

    return shafts


def analyze_chamfers_and_fillets(cq_object, iso_provider):
    chamfers = []
    fillets = []

    all_faces = cq_object.faces().vals()
    for face in all_faces:
        surf = BRepAdaptor_Surface(face.wrapped, True)
        stype = surf.GetType()

        props = GProp_GProps()
        BRepGProp.SurfaceProperties_s(face.wrapped, props)
        area = props.Mass()

        if stype == GeomAbs_Cone:
            cone = surf.Cone()
            half_angle = cone.SemiAngle()
            angle_deg = math.degrees(half_angle)
            if 40 <= angle_deg <= 50:
                ref_radius = cone.RefRadius()
                chamfers.append(
                    {
                        "angle": round(angle_deg, 1),
                        "estimated_size": round(ref_radius * 0.3, 2),
                        "area": area,
                    }
                )

        elif stype == GeomAbs_Torus:
            torus = surf.Torus()
            minor_radius = torus.MinorRadius()
            major_radius = torus.MajorRadius()
            if minor_radius < major_radius * 0.5 and minor_radius < 20:
                fillets.append(
                    {
                        "radius": round(minor_radius, 2),
                        "area": area,
                        "standard_radius": iso_provider.get_nearest_standard_fillet(minor_radius),
                    }
                )

    chamfer_sizes = [c["estimated_size"] for c in chamfers]
    fillet_radii = [f["radius"] for f in fillets]

    avg_chamfer = sum(chamfer_sizes) / len(chamfer_sizes) if chamfer_sizes else 1.0
    avg_fillet = sum(fillet_radii) / len(fillet_radii) if fillet_radii else 2.0

    return {
        "chamfers": {
            "count": len(chamfers),
            "sizes": list(set(round(s, 1) for s in chamfer_sizes)),
            "average_size": round(avg_chamfer, 2),
            "recommended_standard": iso_provider.get_nearest_standard_chamfer(avg_chamfer),
        },
        "fillets": {
            "count": len(fillets),
            "radii": list(set(round(r, 1) for r in fillet_radii)),
            "average_radius": round(avg_fillet, 2),
            "recommended_standard": iso_provider.get_nearest_standard_fillet(avg_fillet),
        },
        "edge_note": "All edges to be deburred and broken 0.2-0.5mm unless otherwise specified (ISO 13715)",
    }
