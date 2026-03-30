from __future__ import annotations

from typing import Any, Dict


def analyze_manufacturing_requirements(
    cq_object,
    *,
    analyze_faces_fn,
    get_geometric_properties_fn,
    is_turned_part_fn,
    iso_provider,
    face_analysis=None,
):
    if face_analysis is None:
        face_analysis = analyze_faces_fn(cq_object)

    geom_props = get_geometric_properties_fn(cq_object)
    is_turned = is_turned_part_fn(cq_object)

    dims = geom_props["bounding_box"]["dimensions"]
    max_dim = max(dims)
    min_dim = min(dims)

    total_faces = sum(face_analysis.values())
    bspline_ratio = face_analysis.get("BSpline", 0) / total_faces if total_faces > 0 else 0
    torus_count = face_analysis.get("Torus", 0)

    if bspline_ratio > 0.3:
        complexity = "high"
    elif torus_count > 10 or total_faces > 500:
        complexity = "medium"
    else:
        complexity = "low"

    if is_turned:
        part_type = "Shaft/Bar"
    elif min_dim < max_dim * 0.1:
        part_type = "Plate/Sheet"
    else:
        part_type = "Block/Housing"

    linear_class, geo_class = iso_provider.recommend_iso2768_class(part_type, complexity)

    tolerance_table = []
    for dim in dims:
        tol = iso_provider.get_iso2768_linear_tolerance(dim, linear_class)
        if tol:
            tolerance_table.append(
                {
                    "dimension": round(dim, 2),
                    "tolerance": f"±{tol}",
                    "class": linear_class,
                }
            )

    surface_analysis = iso_provider.analyze_surface_requirements(face_analysis)

    if is_turned:
        primary_process = "CNC Turning"
        secondary_processes = ["Milling (for features)", "Grinding (if Ra < 0.8)"]
    elif bspline_ratio > 0.2:
        primary_process = "5-Axis CNC Milling"
        secondary_processes = ["3-Axis roughing", "Finishing passes"]
    elif min_dim < max_dim * 0.05:
        primary_process = "Sheet Metal (Laser/Plasma + Bending)"
        secondary_processes = ["Deburring", "Surface treatment"]
    else:
        primary_process = "3-Axis CNC Milling"
        secondary_processes = ["Drilling", "Tapping", "Deburring"]

    return {
        "iso2768_recommendation": {
            "linear_class": linear_class,
            "geometric_class": geo_class,
            "designation": f"ISO 2768-{linear_class}{geo_class}",
            "tolerance_table": tolerance_table,
        },
        "surface_finish": surface_analysis,
        "manufacturing_process": {
            "primary": primary_process,
            "secondary": secondary_processes,
            "complexity": complexity,
        },
        "part_characteristics": {
            "is_turned_part": is_turned,
            "part_type": part_type,
            "max_dimension": round(max_dim, 2),
            "volume": round(geom_props["volume"], 2),
        },
    }


def calculate_mass_properties(cq_object, *, get_geometric_properties_fn, iso_provider, material_key="steel_s235"):
    geom_props = get_geometric_properties_fn(cq_object)
    volume = geom_props["volume"]
    mass_data = iso_provider.calculate_mass(volume, material_key)
    if not mass_data:
        return None

    alternatives = {}
    for alt_key in ["steel_s355", "steel_304", "alu_6061", "alu_7075"]:
        if alt_key != material_key:
            alt_mass = iso_provider.calculate_mass(volume, alt_key)
            if alt_mass:
                alternatives[alt_key] = {
                    "material": alt_mass["material"],
                    "mass_kg": alt_mass["mass_kg"],
                }

    return {
        "primary": mass_data,
        "alternatives": alternatives,
        "volume_mm3": volume,
        "volume_cm3": volume / 1000,
    }


def analyze_holes_with_fits(cq_object, *, detect_holes_fn, iso_provider):
    holes = detect_holes_fn(cq_object)
    analyzed_holes = []
    diameter_groups = {}
    for hole in holes:
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

        analyzed_holes.append(
            {
                "diameter": diameter,
                "count": len(hole_list),
                "depths": [round(h.depth, 2) for h in hole_list],
                "fit_recommendation": fit_analysis["primary_recommendation"],
                "alternative_fit": fit_analysis["alternative_recommendation"],
                "tolerances": fit_analysis["tolerances"],
                "possible_thread": thread_info,
            }
        )

    analyzed_holes.sort(key=lambda item: item["diameter"])
    return analyzed_holes


def generate_manufacturing_summary(
    cq_object,
    *,
    analyze_faces_fn,
    get_geometric_properties_fn,
    get_topology_stats_fn,
    analyze_manufacturing_requirements_fn,
    analyze_holes_with_fits_fn,
    detect_threads_fn,
    analyze_chamfers_and_fillets_fn,
    calculate_mass_properties_fn,
    output_dir=None,
):
    face_analysis = analyze_faces_fn(cq_object)
    geom_props = get_geometric_properties_fn(cq_object)
    topology = get_topology_stats_fn(cq_object)

    mfg_requirements = analyze_manufacturing_requirements_fn(cq_object, face_analysis)
    holes_analysis = analyze_holes_with_fits_fn(cq_object)
    threads = detect_threads_fn(cq_object)
    chamfers_fillets = analyze_chamfers_and_fillets_fn(cq_object)

    mass_steel = calculate_mass_properties_fn(cq_object, "steel_s235")
    mass_alu = calculate_mass_properties_fn(cq_object, "alu_6061")

    return {
        "geometry": {
            "volume_mm3": geom_props["volume"],
            "surface_area_mm2": geom_props["surface_area"],
            "bounding_box": geom_props["bounding_box"],
            "center_of_mass": geom_props["center_of_mass"],
        },
        "topology": topology,
        "face_analysis": face_analysis,
        "manufacturing": mfg_requirements,
        "holes": {
            "summary": holes_analysis,
            "total_count": sum(h["count"] for h in holes_analysis),
        },
        "threads": {
            "detected": threads,
            "count": len(threads),
        },
        "edges": chamfers_fillets,
        "mass_estimates": {
            "steel_s235": mass_steel["primary"] if mass_steel else None,
            "alu_6061": mass_alu["primary"] if mass_alu else None,
        },
    }


def generate_werkvoorbereiding(
    cq_object,
    *,
    get_geometric_properties_fn,
    analyze_faces_fn,
    detect_holes_fn,
    detect_threads_fn,
    analyze_chamfers_and_fillets_fn,
    is_turned_part_fn,
    werkvoorbereiding_provider,
    material: str = "steel_s235",
    quantity: int = 1,
    surface_treatment: str = None,
    hourly_rates_config: dict = None,
    material_prices_config: dict = None,
):
    geom_props = get_geometric_properties_fn(cq_object)
    face_analysis = analyze_faces_fn(cq_object)
    holes = detect_holes_fn(cq_object)
    threads = detect_threads_fn(cq_object)
    chamfers_fillets = analyze_chamfers_and_fillets_fn(cq_object)
    is_turned = is_turned_part_fn(cq_object)

    total_faces = sum(face_analysis.values())
    bspline_ratio = face_analysis.get("BSpline", 0) / total_faces if total_faces > 0 else 0
    if bspline_ratio > 0.3:
        complexity = "high"
    elif face_analysis.get("Torus", 0) > 10 or total_faces > 500:
        complexity = "medium"
    else:
        complexity = "low"

    dims = geom_props["bounding_box"]["dimensions"]
    min_dim = min(dims)
    max_dim = max(dims)
    if is_turned:
        process_type = "cnc_draaien"
    elif min_dim < max_dim * 0.05:
        process_type = "plaatwerk"
    elif bspline_ratio > 0.2 or complexity == "high":
        process_type = "cnc_frezen_5as"
    else:
        process_type = "cnc_frezen_3as"

    volume = geom_props["volume"]
    density = 7850 if "steel" in material else 2700 if "alu" in material else 7850
    mass_kg = (volume / 1e9) * density

    holes_data = [{"diameter": hole.diameter, "depth": hole.depth} for hole in holes]
    threads_data = [
        {"thread_designation": item["thread_designation"], "tap_drill": item.get("tap_drill")}
        for item in threads
    ]

    cost_estimate = werkvoorbereiding_provider.calculate_cost_estimate(
        volume_mm3=volume,
        surface_area_mm2=geom_props["surface_area"],
        mass_kg=mass_kg,
        hole_count=len(holes),
        thread_count=len(threads),
        complexity=complexity,
        process_type=process_type,
        material=material,
        quantity=quantity,
        surface_treatment=surface_treatment,
        hourly_rates_config=hourly_rates_config,
        material_prices_config=material_prices_config,
    )
    tool_list = werkvoorbereiding_provider.generate_tool_list(
        holes=holes_data,
        threads=threads_data,
        chamfers_fillets=chamfers_fillets,
        is_turned=is_turned,
        material=material,
    )
    outsourcing = werkvoorbereiding_provider.classify_outsourcing(
        classification=process_type,
        complexity=complexity,
        is_turned=is_turned,
        is_sheet_metal=(process_type == "plaatwerk"),
        volume_mm3=volume,
        has_5axis_features=(process_type == "cnc_frezen_5as"),
        needs_surface_treatment=(surface_treatment is not None),
    )
    surface_recommendations = werkvoorbereiding_provider.recommend_surface_treatment(
        material=material,
        corrosion_resistance="normal",
    )
    purchase_spec = werkvoorbereiding_provider.generate_purchase_spec(
        part_id="PART-001",
        material=material,
        mass_kg=mass_kg,
        dimensions=dims,
        quantity=quantity,
    )

    return {
        "cost_estimate": cost_estimate,
        "tool_list": tool_list,
        "outsourcing": outsourcing,
        "surface_treatment_options": surface_recommendations,
        "purchase_specification": purchase_spec,
        "process_info": {
            "process_type": process_type,
            "complexity": complexity,
            "is_turned": is_turned,
            "material": material,
            "quantity": quantity,
        },
    }


def analyze_sheetmetal(cq_object, *, analyze_sheet_metal_fn, sheetmetal_analysis_module, thickness: float = None, material: str = "steel_s235"):
    try:
        if hasattr(cq_object, "val"):
            solid = cq_object.val().wrapped
        elif hasattr(cq_object, "wrapped"):
            solid = cq_object.wrapped
        else:
            solid = cq_object
    except Exception:
        return {"error": "Could not access geometry"}

    if thickness is None:
        from OCP.TopAbs import TopAbs_SOLID
        from OCP.TopExp import TopExp_Explorer

        exp = TopExp_Explorer(solid, TopAbs_SOLID)
        if exp.More():
            first_solid = exp.Current()
            sm_data = analyze_sheet_metal_fn(first_solid)
            if sm_data.get("is_sheet_metal"):
                thickness = sm_data.get("thickness", 2.0)
            else:
                thickness = 2.0

    return sheetmetal_analysis_module.analyze_sheetmetal_complete(solid, thickness, material)


def analyze_assembly_bom(cq_object, *, assembly_analysis_module, assembly_name: str = "Assembly", material: str = "steel_s235", step_file_path: str = None):
    return assembly_analysis_module.analyze_assembly_complete(
        cq_object,
        assembly_name=assembly_name,
        material=material,
        step_file_path=step_file_path,
    )
