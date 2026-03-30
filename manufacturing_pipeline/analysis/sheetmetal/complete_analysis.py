from __future__ import annotations

from typing import Any, Dict

from manufacturing_pipeline.analysis.sheetmetal import geometry_analysis as _sheetmetal_geometry_analysis
from manufacturing_pipeline.analysis.sheetmetal import standards as _sheetmetal_standards


def analyze_sheetmetal_complete(
    solid,
    thickness: float,
    material: str = "steel_s235",
    quantity: int = 1,
) -> Dict[str, Any]:
    mat_props = _sheetmetal_standards.MATERIAL_BEND_PROPERTIES.get(
        material,
        _sheetmetal_standards.MATERIAL_BEND_PROPERTIES["steel_s235"],
    )

    try:
        if hasattr(solid, "val"):
            actual_solid = solid.val().wrapped
        elif hasattr(solid, "wrapped"):
            actual_solid = solid.wrapped
        else:
            actual_solid = solid

        geom_analysis = _sheetmetal_geometry_analysis.analyze_sheet_metal_geometry(actual_solid, thickness)
    except Exception as exc:
        geom_analysis = {"error": str(exc), "bends": [], "bend_count": 0}

    v_size, v_tool = _sheetmetal_standards.recommend_v_opening(thickness)
    min_radius = _sheetmetal_standards.get_minimum_bend_radius(thickness, material.split("_")[0])

    k_factor = mat_props.get("k_factor", 0.44)
    sample_ba = _sheetmetal_standards.calculate_bend_allowance(thickness, 90, min_radius, k_factor)
    bend_force_per_m = _sheetmetal_standards.calculate_bend_force(
        thickness,
        1000,
        v_size,
        mat_props.get("tensile_strength", 400),
    )

    is_standard_thickness = any(
        abs(thickness - std) < 0.05 for std in _sheetmetal_standards.STANDARD_THICKNESSES
    )

    result = {
        "is_sheet_metal": True,
        "thickness": {
            "value": thickness,
            "is_standard": is_standard_thickness,
            "nearest_standard": min(
                _sheetmetal_standards.STANDARD_THICKNESSES,
                key=lambda value: abs(value - thickness),
            ),
            "standard": "EN 10131" if is_standard_thickness else None,
        },
        "material": {
            "code": material,
            "name": mat_props.get("name", material),
            "tensile_strength": mat_props.get("tensile_strength"),
            "yield_strength": mat_props.get("yield_strength"),
            "k_factor": k_factor,
            "springback": f"{(mat_props.get('springback_factor', 1.0) - 1) * 100:.1f}%",
        },
        "bending": {
            "bend_count": geom_analysis.get("bend_count", 0),
            "total_bend_length_mm": geom_analysis.get("total_bend_length", 0),
            "min_inner_radius": min_radius,
            "bend_allowance_90deg": round(sample_ba, 2),
            "bends": [
                {
                    "id": bend.bend_id,
                    "angle": bend.angle,
                    "radius": bend.inner_radius,
                    "length": round(bend.bend_length, 1),
                    "standard_angle": bend.is_standard_angle,
                    "standard_radius": bend.is_standard_radius,
                }
                for bend in geom_analysis.get("bends", [])
            ]
            if geom_analysis.get("bends")
            else [],
        },
        "tooling": {
            "recommended_v_die": f"V{v_size}",
            "v_opening_mm": v_size,
            "punch_radius_mm": v_tool.punch_radius,
            "min_flange_mm": v_tool.min_flange,
            "max_thickness_mm": v_tool.max_thickness,
            "bend_force_kN_per_m": round(bend_force_per_m, 1),
            "tonnage_per_m": v_tool.tonnage_per_m,
        },
        "flat_pattern": {
            "note": "Uitslag berekening beschikbaar per buiging",
            "k_factor_used": k_factor,
            "calculation_method": "DIN 6935",
        },
        "production": {
            "quantity": quantity,
            "estimated_bends_total": geom_analysis.get("bend_count", 0) * quantity,
            "machine_requirement": _recommend_machine(thickness, geom_analysis.get("total_bend_length", 0)),
        },
        "warnings": [],
    }

    if not is_standard_thickness:
        result["warnings"].append(
            f"Niet-standaard plaatdikte ({thickness}mm). "
            f"Overweeg {result['thickness']['nearest_standard']}mm"
        )

    for bend in geom_analysis.get("bends", []):
        if bend.inner_radius < min_radius:
            result["warnings"].append(
                f"Buiging {bend.bend_id}: radius {bend.inner_radius}mm < minimum {min_radius}mm - risico op scheuren"
            )

    return result


def _recommend_machine(thickness: float, total_bend_length: float) -> str:
    if thickness <= 3 and total_bend_length < 2000:
        return "Kleine kantbank (≤50 ton)"
    if thickness <= 6 and total_bend_length < 3000:
        return "Middelgrote kantbank (50-150 ton)"
    if thickness <= 10:
        return "Grote kantbank (150-300 ton)"
    return "Zware kantbank (>300 ton)"
