from __future__ import annotations

from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.GeomAbs import GeomAbs_Cylinder, GeomAbs_Plane
from OCP.GProp import GProp_GProps
from OCP.BRepGProp import BRepGProp
from OCP.TopAbs import TopAbs_FACE
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS

from manufacturing_pipeline.analysis import sheetmetal_analysis


def analyze_sheet_metal(solid):
    exp = TopExp_Explorer(solid, TopAbs_FACE)
    faces = []
    while exp.More():
        faces.append(TopoDS.Face_s(exp.Current()))
        exp.Next()

    planar_faces = []
    total_area = 0.0

    for face in faces:
        props = GProp_GProps()
        BRepGProp.SurfaceProperties_s(face, props)
        area = props.Mass()
        total_area += area

        surf = BRepAdaptor_Surface(face, True)
        stype = surf.GetType()
        if stype == GeomAbs_Plane:
            planar_faces.append((face, area))

    thickness_counts = {}
    planes = []
    for face, area in planar_faces:
        surf = BRepAdaptor_Surface(face, True)
        pln = surf.Plane()
        ax = pln.Axis().Direction()
        normal = (ax.X(), ax.Y(), ax.Z())
        loc = pln.Location()
        d_val = -(normal[0] * loc.X() + normal[1] * loc.Y() + normal[2] * loc.Z())
        planes.append({"normal": normal, "d": d_val, "area": area})

    for i in range(len(planes)):
        for j in range(i + 1, len(planes)):
            p1 = planes[i]
            p2 = planes[j]
            dot = (
                p1["normal"][0] * p2["normal"][0]
                + p1["normal"][1] * p2["normal"][1]
                + p1["normal"][2] * p2["normal"][2]
            )
            if abs(dot + 1.0) >= 0.01:
                continue
            dist = abs(p1["d"] + p2["d"])
            if dist <= 0.1:
                continue
            t_val = round(dist, 2)
            if t_val not in thickness_counts:
                thickness_counts[t_val] = 0
            thickness_counts[t_val] += min(p1["area"], p2["area"])

    detected_thickness = 0.0
    is_sheet = False

    if thickness_counts:
        sheet_candidates = {t: area for t, area in thickness_counts.items() if t < 25.0}
        best_t = max(sheet_candidates, key=sheet_candidates.get) if sheet_candidates else max(
            thickness_counts, key=thickness_counts.get
        )
        coverage = thickness_counts[best_t] * 2
        if total_area > 0 and (coverage / total_area > 0.1):
            detected_thickness = best_t
            is_sheet = True

    is_closed_profile = False
    counter_bend_count = 0
    bend_count = 0

    try:
        t_arg = detected_thickness if detected_thickness > 0 else None
        sm_result = sheetmetal_analysis.analyze_sheet_metal_geometry(solid, thickness=t_arg)

        bend_count = sm_result.get("bend_count_for_erp", sm_result.get("bend_count", 0))
        is_closed_profile = sm_result.get("is_closed_profile", False)
        counter_bend_count = sm_result.get("counter_bend_count", 0)

        if detected_thickness == 0.0 and sm_result.get("thickness"):
            detected_thickness = sm_result.get("thickness")
            is_sheet = True
    except Exception:
        bend_count = 0

    iso_thicknesses = [0.5, 0.6, 0.8, 1.0, 1.2, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0, 12.0, 15.0, 20.0]
    is_standard = False
    if is_sheet:
        for iso_t in iso_thicknesses:
            if abs(detected_thickness - iso_t) < 0.05:
                is_standard = True
                break

    return {
        "is_sheet_metal": is_sheet,
        "thickness": detected_thickness,
        "bend_count": bend_count,
        "counter_bend_count": counter_bend_count,
        "is_closed_profile": is_closed_profile,
        "is_standard": is_standard,
    }
