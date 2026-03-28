"""
Pipeline stage runner functions.

Groups related pipeline stages into logical units for cleaner orchestration.
"""
import os
from typing import Dict, Any, Optional, List, Tuple

from manufacturing_pipeline.data.cache_manager import PipelineRunner, PipelineStage
from manufacturing_pipeline.analysis.step_processing import (
    load_step_file, detect_holes, is_turned_part, get_geometric_properties,
    analyze_faces, get_topology_stats, classify_components, analyze_components_detailed,
    detect_threads, detect_shafts, analyze_chamfers_and_fillets,
    analyze_manufacturing_requirements, calculate_mass_properties,
    analyze_holes_with_fits, analyze_sheetmetal, analyze_assembly_bom,
    generate_werkvoorbereiding
)
from manufacturing_pipeline.analysis.werkvoorbereiding import generate_simple_cost_table


class _IsoStandardsFallback:
    @staticmethod
    def get_tap_drill_size(_designation):
        return None

    @staticmethod
    def get_all_materials_by_category():
        return {"steel": ["steel_s235"], "aluminum": ["alu_6061"]}


iso_standards = _IsoStandardsFallback()
from manufacturing_pipeline.reporting.cli_output import (
    print_section_header, print_holes_summary, print_geometry_summary,
    print_iso2768_summary, print_iso286_summary, print_threads_summary,
    print_surface_finish_summary, print_edge_analysis_summary, print_mass_summary,
    print_manufacturing_process_summary, print_werkvoorbereiding_summary,
    print_sheetmetal_summary, print_assembly_summary, print_simple_cost_table_preview,
    print_production_info_table
)


def run_geometry_and_topology_stages(
    runner: PipelineRunner,
    step_file: str,
    production_only: bool = False
) -> Dict[str, Any]:
    """
    Run geometry and topology analysis stages (1-6).
    
    Returns dict with: shape, is_turned, geom_props, face_analysis, topology_stats,
                       component_classification, detailed_parts, images_dir
    """
    # Stage 1: Load STEP file
    shape = runner.get_or_run(
        PipelineStage.LOAD_STEP,
        load_step_file,
        step_file
    )
    if not production_only:
        xcaf_names = getattr(shape, "_xcaf_solid_names", None)
        if xcaf_names:
            print(f"STEP file loaded successfully (XCAF, {len(xcaf_names)} named solids).")
        else:
            print("STEP file loaded successfully.")

    # Stage 2: Detect holes
    holes = runner.get_or_run(
        PipelineStage.DETECT_HOLES,
        detect_holes,
        shape
    )
    print_holes_summary(holes, production_only)

    # Stage 3: Geometry Analysis
    geom_props = runner.get_or_run(
        PipelineStage.GEOMETRY_ANALYSIS,
        get_geometric_properties,
        shape
    )
    print_geometry_summary(geom_props, production_only)

    # Stage 4: Face Analysis
    face_analysis = runner.get_or_run(
        PipelineStage.FACE_ANALYSIS,
        analyze_faces,
        shape
    )
    if not production_only:
        print("Face Analysis:", face_analysis)

    # Turned part check (lightweight, no separate cache)
    is_turned = is_turned_part(shape)
    if not production_only:
        print(f"Turned Part Classification: {'Yes' if is_turned else 'No'}")

    # Stage 5: Topology
    topology_stats = runner.get_or_run(
        PipelineStage.TOPOLOGY,
        get_topology_stats,
        shape
    )
    if not production_only:
        print("Topology Stats:", topology_stats)

    # Stage 6: Component Classification
    component_classification = runner.get_or_run(
        PipelineStage.COMPONENT_CLASSIFICATION,
        classify_components,
        shape
    )
    if not production_only:
        print("Component Classification:", component_classification)

    # Stage 7: Detailed Parts Analysis
    if not production_only:
        print("Generating detailed component analysis and images...")
    images_dir = os.path.join(os.path.dirname(step_file) if os.path.dirname(step_file) else ".", "part_images")
    detailed_parts = runner.get_or_run(
        PipelineStage.DETAILED_PARTS,
        analyze_components_detailed,
        shape, images_dir
    )
    if not production_only:
        print(f"Found {len(detailed_parts)} unique parts.")

    return {
        "shape": shape,
        "holes": holes,
        "is_turned": is_turned,
        "geom_props": geom_props,
        "face_analysis": face_analysis,
        "topology_stats": topology_stats,
        "component_classification": component_classification,
        "detailed_parts": detailed_parts,
        "images_dir": images_dir,
    }


def run_iso_standards_stages(
    runner: PipelineRunner,
    shape,
    face_analysis: Dict,
    production_only: bool = False
) -> Dict[str, Any]:
    """
    Run ISO standards analysis stages (8-12).
    
    Returns dict with: mfg_requirements, holes_with_fits, threads, thread_summary,
                       edge_analysis, mass_steel, mass_alu
    """
    if not production_only:
        print_section_header("DUTCH/ISO MANUFACTURING STANDARDS ANALYSIS")

    # Stage 8: Manufacturing Requirements (ISO 2768)
    if not production_only:
        print("\n[ISO 2768] Tolerance Analysis...")
    mfg_requirements = runner.get_or_run(
        PipelineStage.MANUFACTURING_REQUIREMENTS,
        analyze_manufacturing_requirements,
        shape, face_analysis
    )
    print_iso2768_summary(mfg_requirements, production_only)

    # Stage 9: Holes with Fits (ISO 286)
    if not production_only:
        print("\n[ISO 286] Hole & Fit Analysis...")
    holes_with_fits = runner.get_or_run(
        PipelineStage.HOLES_WITH_FITS,
        analyze_holes_with_fits,
        shape
    )
    print_iso286_summary(holes_with_fits, production_only)

    # Stage 10: Thread Detection (ISO 68-1 / ISO 261)
    if not production_only:
        print("\n[ISO 68-1] Thread Detection...")
    threads = runner.get_or_run(
        PipelineStage.THREADS,
        detect_threads,
        shape
    )
    
    # Calculate thread summary
    thread_summary = {}
    for t in threads:
        des = t["thread_designation"]
        if des not in thread_summary:
            thread_summary[des] = 0
        thread_summary[des] += 1
    
    print_threads_summary(threads, thread_summary, iso_standards, production_only)

    # ISO 1302 Surface Finish (from mfg_requirements)
    print_surface_finish_summary(mfg_requirements, production_only)

    # Stage 11: Chamfers & Fillets (ISO 13715)
    if not production_only:
        print("\n[ISO 13715] Chamfers & Fillets...")
    edge_analysis = runner.get_or_run(
        PipelineStage.CHAMFERS_FILLETS,
        analyze_chamfers_and_fillets,
        shape
    )
    print_edge_analysis_summary(edge_analysis, production_only)

    # Stage 12: Mass Properties (EN Standards)
    if not production_only:
        print("\n[EN 10025/573] Mass Estimation...")
    mass_steel = runner.get_or_run(
        PipelineStage.MASS_PROPERTIES,
        calculate_mass_properties,
        shape, "steel_s235"
    )
    # Also calculate aluminum (lightweight, doesn't need separate caching)
    mass_alu = calculate_mass_properties(shape, "alu_6061")
    print_mass_summary(mass_steel, mass_alu, production_only)

    # Manufacturing Process
    print_manufacturing_process_summary(mfg_requirements, production_only)

    return {
        "mfg_requirements": mfg_requirements,
        "holes_with_fits": holes_with_fits,
        "threads": threads,
        "thread_summary": thread_summary,
        "edge_analysis": edge_analysis,
        "mass_steel": mass_steel,
        "mass_alu": mass_alu,
    }


def run_werkvoorbereiding_stage(
    runner: PipelineRunner,
    shape,
    config,
    production_only: bool = False
) -> Optional[Dict[str, Any]]:
    """
    Run werkvoorbereiding (manufacturing preparation) stage.
    
    Returns werkvoorbereiding_data dict or None if all modules disabled.
    """
    modules = config.modules
    wv_enabled = any([
        modules.cost_estimation,
        modules.tool_list,
        modules.outsourcing,
        modules.surface_treatment,
        modules.purchase_spec
    ])

    if not wv_enabled:
        if not production_only:
            print("\n[Werkvoorbereiding] - ALLE MODULES UITGESCHAKELD")
        return None

    if not production_only:
        print_section_header("WERKVOORBEREIDING / MANUFACTURING PREPARATION")

    werkvoorbereiding_data = runner.get_or_run(
        PipelineStage.WERKVOORBEREIDING,
        generate_werkvoorbereiding,
        shape, config.material, config.quantity, None,
        config.hourly_rates.to_dict(),
        config.material_prices.to_dict()
    )

    print_werkvoorbereiding_summary(werkvoorbereiding_data, modules, production_only)

    if not production_only:
        print("\n" + "="*60)

    return werkvoorbereiding_data


def is_sheetmetal_candidate(dimensions: List[float]) -> bool:
    """Check if dimensions suggest sheet metal (thin relative to size)."""
    min_dim = min(dimensions)
    max_dim = max(dimensions)
    return min_dim < max_dim * 0.1 and min_dim < 25


def run_sheetmetal_stage(
    runner: PipelineRunner,
    shape,
    geom_props: Dict,
    config,
    production_only: bool = False
) -> Optional[Dict[str, Any]]:
    """
    Run sheet metal analysis stage.
    
    Returns sheetmetal_data dict or None if not applicable.
    """
    modules = config.modules
    sm_enabled = any([
        modules.sheetmetal_analysis,
        modules.bend_detection,
        modules.kantbank_tooling,
        modules.flat_pattern
    ])

    if not sm_enabled:
        if not production_only:
            print("\n[Plaatwerk] - ALLE MODULES UITGESCHAKELD")
        return None

    if not production_only:
        print_section_header("PLAATWERK ANALYSE / SHEET METAL ANALYSIS")

    dims = geom_props["bounding_box"]["dimensions"]
    
    if not is_sheetmetal_candidate(dims):
        if not production_only:
            min_dim = min(dims)
            max_dim = max(dims)
            print("\n[Plaatwerk] Onderdeel lijkt geen plaatwerk te zijn")
            print(f"  (min. dimensie {min_dim:.1f}mm > 10% van max {max_dim:.1f}mm)")
        return None

    min_dim = min(dims)
    sheetmetal_data = runner.get_or_run(
        PipelineStage.SHEETMETAL,
        analyze_sheetmetal,
        shape, min_dim, config.material
    )

    print_sheetmetal_summary(sheetmetal_data, modules, production_only)

    if not production_only:
        print("\n" + "="*60)

    return sheetmetal_data


def run_assembly_bom_stage(
    runner: PipelineRunner,
    shape,
    topology_stats: Dict,
    step_file: str,
    config,
    production_only: bool = False
) -> Optional[Dict[str, Any]]:
    """
    Run assembly/BOM analysis stage.
    
    Returns assembly_data dict or None if not an assembly.
    """
    if topology_stats.get("solids", 0) <= 1:
        return None

    if not production_only:
        print_section_header("ASSEMBLAGE ANALYSE / ASSEMBLY ANALYSIS (BOM)")

    part_name_for_bom = os.path.splitext(os.path.basename(step_file))[0]
    assembly_data = runner.get_or_run(
        PipelineStage.ASSEMBLY_BOM,
        analyze_assembly_bom,
        shape, part_name_for_bom, config.material, step_file
    )

    print_assembly_summary(assembly_data, production_only)

    if not production_only:
        print("\n" + "="*60)

    return assembly_data


def run_simple_cost_table_stage(
    detailed_parts: List[Dict],
    config,
    production_only: bool = False
) -> Optional[Dict[str, Any]]:
    """
    Run simple cost table generation stage.
    
    Returns simple_cost_table_data dict or None.
    """
    if not (config.modules.simple_cost_report and detailed_parts and not production_only):
        return None

    print_section_header("EENVOUDIG KOSTENOVERZICHT / SIMPLE COST TABLE")

    enabled_columns = config.cost_columns.get_enabled_columns()

    simple_cost_table_data = generate_simple_cost_table(
        parts=detailed_parts,
        material=config.material,
        quantity=config.quantity,
        hourly_rates_config=config.hourly_rates.to_dict(),
        material_prices_config=config.material_prices.to_dict(),
        enabled_columns=enabled_columns
    )

    print_simple_cost_table_preview(simple_cost_table_data, production_only)

    print("\n" + "="*60)

    return simple_cost_table_data


def compile_manufacturing_data(
    mfg_requirements: Dict,
    holes_with_fits: List[Dict],
    threads: List[Dict],
    thread_summary: Dict,
    edge_analysis: Dict,
    mass_steel: Optional[Dict],
    mass_alu: Optional[Dict],
    werkvoorbereiding_data: Optional[Dict],
    sheetmetal_data: Optional[Dict],
    assembly_data: Optional[Dict],
    simple_cost_table_data: Optional[Dict],
    config
) -> Dict[str, Any]:
    """Compile all manufacturing data into a single dictionary."""
    modules = config.modules
    
    return {
        "iso2768": mfg_requirements["iso2768_recommendation"] if modules.iso2768_tolerances else None,
        "surface_finish": mfg_requirements["surface_finish"] if modules.iso1302_surface else None,
        "manufacturing_process": mfg_requirements["manufacturing_process"],
        "holes_with_fits": holes_with_fits if modules.iso286_fits else None,
        "threads": {
            "detected": threads,
            "summary": thread_summary,
        } if modules.iso68_threads else None,
        "edges": edge_analysis if modules.iso13715_edges else None,
        "mass_estimates": {
            "steel_s235": mass_steel["primary"] if mass_steel else None,
            "steel_s355": mass_steel["alternatives"].get("steel_s355") if mass_steel else None,
            "alu_6061": mass_alu["primary"] if mass_alu else None,
            "alu_7075": mass_alu["alternatives"].get("alu_7075") if mass_alu else None,
        } if modules.mass_estimation else None,
        "material_options": list(iso_standards.get_all_materials_by_category().keys()),
        "werkvoorbereiding": werkvoorbereiding_data,
        "sheetmetal": sheetmetal_data,
        "assembly": assembly_data,
        "simple_cost_table": simple_cost_table_data,
        "module_config": config.modules.to_dict(),
        "cost_columns_config": config.cost_columns.to_dict(),
    }
