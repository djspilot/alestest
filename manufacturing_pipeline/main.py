#!/usr/bin/env python3
"""
Manufacturing Pipeline - Full Analysis Mode

NOTE: This is the legacy entry point. Consider using the unified entry point:
    python run.py -f mypart.step --full

This script is maintained for backward compatibility.
"""
import sys
import os
import argparse

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

try:
    from src.step_processing import (
        load_step_file, detect_holes, is_turned_part, get_geometric_properties,
        analyze_faces, get_topology_stats, classify_components, analyze_components_detailed,
        detect_threads, detect_shafts, analyze_chamfers_and_fillets,
        analyze_manufacturing_requirements, calculate_mass_properties,
        analyze_holes_with_fits, generate_manufacturing_summary, generate_werkvoorbereiding,
        analyze_sheetmetal, analyze_assembly_bom
    )
    from src.pdf_processing import extract_dimensions_from_pdf
    from src.correlation import correlate_hole_dimension
    from src.database import DatabaseManager
    from src.report_generator import PDFReportGenerator
    from src import iso_standards
    from src.cache_manager import CacheManager, PipelineRunner, PipelineStage
    from src.config import (
        PipelineConfig, ModuleConfig, apply_module_toggles,
        print_module_status, MODULE_GROUPS, MODULE_NAMES
    )
    from src.werkvoorbereiding import generate_simple_cost_table, generate_production_info_table
except ImportError as e:
    print(f"Error importing modules: {e}")
    print("Please ensure all requirements are installed.")
    sys.exit(1)

import json
from dataclasses import asdict


def save_to_json(filename, part_name, holes, matches, is_turned, geom_props=None,
                 face_analysis=None, topology_stats=None, component_classification=None,
                 detailed_parts=None, manufacturing_data=None, verbose=True):
    """Save analysis results to a JSON file."""
    data = {
        "part_name": part_name,
        "is_turned_part": is_turned,
        "geometric_properties": geom_props,
        "face_analysis": face_analysis,
        "topology_stats": topology_stats,
        "component_classification": component_classification,
        "detailed_parts": detailed_parts,
        "holes": [asdict(h) for h in holes],
        "matches": [
            {
                "step_value": m.step_value,
                "pdf_value": m.pdf_value,
                "tolerance_upper": m.tolerance_upper,
                "tolerance_lower": m.tolerance_lower,
                "confidence": m.confidence,
                "status": m.status.value
            } for m in matches
        ],
        # New manufacturing data per Dutch/ISO standards
        "manufacturing_analysis": manufacturing_data,
    }

    with open(filename, 'w') as f:
        json.dump(data, f, indent=2)
    if verbose:
        print(f"Results saved to {filename}")


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Manufacturing Pipeline - Analyze STEP files with caching support",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                          # Run with default file and caching
  python main.py -f mypart.step           # Analyze specific STEP file
  python main.py --no-cache               # Run without using cache
  python main.py --status                 # Show cache status
  python main.py --clear-cache            # Clear all cached data
  python main.py --from geometry_analysis # Re-run from specific stage
  python main.py --list-stages            # List all pipeline stages

Module Control:
  python main.py --disable cost_estimation        # Disable cost module
  python main.py --disable werkvoorbereiding      # Disable all werkvoorbereiding
  python main.py --enable iso --disable cost_estimation
  python main.py --list-modules                   # Show all modules

Module Groups: basic, iso, manufacturing, werkvoorbereiding, all
        """
    )
    # File arguments
    parser.add_argument("-f", "--file", default="core_one_assembly.step",
                        help="STEP file to analyze (default: core_one_assembly.step)")
    parser.add_argument("--pdf", default=None,
                        help="PDF file for dimension correlation (default: same name as STEP)")
    parser.add_argument("--production-info", action="store_true",
                        help="Show detailed production information table")
    parser.add_argument("--production-only", action="store_true",
                        help="Show ONLY production information table (implies --production-info, --no-report)")
    parser.add_argument("--no-report", action="store_true",
                        help="Skip PDF report generation")

    # Cache arguments
    parser.add_argument("--no-cache", action="store_true",
                        help="Disable caching, run all stages fresh")
    parser.add_argument("--clear-cache", action="store_true",
                        help="Clear all cached data and exit")
    parser.add_argument("--status", action="store_true",
                        help="Show cache status and exit")
    parser.add_argument("--from", dest="from_stage", metavar="STAGE",
                        help="Re-run from specific stage (clears cache from that point)")
    parser.add_argument("--list-stages", action="store_true",
                        help="List all pipeline stages")
    parser.add_argument("--cache-dir", default=".pipeline_cache",
                        help="Cache directory (default: .pipeline_cache)")

    # Module control arguments
    parser.add_argument("--enable", action="append", default=[],
                        metavar="MODULE",
                        help="Enable specific module or group (can be used multiple times)")
    parser.add_argument("--disable", action="append", default=[],
                        metavar="MODULE",
                        help="Disable specific module or group (can be used multiple times)")
    parser.add_argument("--list-modules", action="store_true",
                        help="List all available modules and exit")
    parser.add_argument("--show-config", action="store_true",
                        help="Show current module configuration")
    parser.add_argument("--config", metavar="FILE",
                        help="Load module configuration from JSON file")
    parser.add_argument("--save-config", metavar="FILE",
                        help="Save current configuration to JSON file")

    # Manufacturing parameters
    parser.add_argument("--material", default="steel_s235",
                        help="Material for cost estimation (default: steel_s235)")
    parser.add_argument("--quantity", type=int, default=1,
                        help="Quantity for cost estimation (default: 1)")

    return parser.parse_args()


def main():
    args = parse_args()

    # Handle --production-only
    if args.production_only:
        args.production_info = True
        args.no_report = True

    step_file = args.file
    pdf_file = args.pdf or step_file.replace(".step", ".pdf").replace(".STEP", ".pdf")
    db_path = "manufacturing_data.db"
    schema_path = os.path.join(os.path.dirname(__file__), 'sql', 'schema.sql')

    # Handle --list-modules
    if args.list_modules:
        print("\nBeschikbare Modules / Available Modules:")
        print("=" * 55)
        for group_name, modules in MODULE_GROUPS.items():
            if modules is None:
                continue
            print(f"\n[{group_name.upper()}]")
            for module in modules:
                name = MODULE_NAMES.get(module, module)
                print(f"  {module:25s} - {name}")
        print("\n" + "=" * 55)
        print("Gebruik / Usage:")
        print("  --enable <module|group>   Enable module or group")
        print("  --disable <module|group>  Disable module or group")
        return

    # Initialize module configuration
    # Check for config file: CLI arg > pipeline_config.json > default
    default_config_path = os.path.join(os.path.dirname(__file__), "pipeline_config.json")
    config_path = args.config or (default_config_path if os.path.exists(default_config_path) else None)

    if config_path and os.path.exists(config_path):
        config = PipelineConfig.load(config_path)
        if not args.production_only:
            print(f"✓ Configuratie geladen uit: {config_path}")
    else:
        config = PipelineConfig(step_file=step_file)
        if not args.production_only:
            print("  (Geen config bestand gevonden, standaard instellingen gebruikt)")

    # Apply enable/disable toggles
    if args.enable or args.disable:
        apply_module_toggles(config.modules, args.enable, args.disable)

    # Update config with CLI args
    config.material = args.material
    config.quantity = args.quantity

    # Handle --show-config
    if args.show_config:
        print_module_status(config.modules)
        return

    # Handle --save-config
    if args.save_config:
        config.save(args.save_config)
        print(f"Configuration saved to {args.save_config}")
        return

    # Handle --list-stages
    if args.list_stages:
        print("Pipeline Stages:")
        print("-" * 40)
        for stage in PipelineStage:
            print(f"  {stage.value}")
        return

    # Initialize cache manager for status/clear operations
    cache = CacheManager(args.cache_dir)

    # Handle --status
    if args.status:
        print(cache.get_status_report())
        return

    # Handle --clear-cache
    if args.clear_cache:
        cache.clear_cache()
        print("Cache cleared.")
        return

    # Parse --from stage if provided
    force_from = None
    if args.from_stage:
        try:
            force_from = PipelineStage(args.from_stage)
            print(f"Will re-run from stage: {force_from.value}")
        except ValueError:
            print(f"Error: Unknown stage '{args.from_stage}'")
            print("Use --list-stages to see available stages.")
            return

    # Show active configuration if modules were toggled
    if (args.enable or args.disable) and not args.production_only:
        print_module_status(config.modules)

    # Initialize Database
    db = DatabaseManager(db_path)
    try:
        db.initialize_schema(schema_path)
    except Exception as e:
        print(f"Warning: Could not initialize database schema: {e}")

    if not os.path.exists(step_file):
        print(f"STEP file not found: {step_file}")
        print("Place a STEP file in the root directory to run the analysis.")
        return

    if not args.production_only:
        print(f"Analyzing {step_file}...")
        print(f"Cache directory: {args.cache_dir}")
        if args.no_cache:
            print("Caching disabled - running all stages fresh")
        print()

    # Initialize pipeline runner with caching
    runner = PipelineRunner(
        step_file=step_file,
        cache_dir=args.cache_dir,
        force_from=force_from,
        no_cache=args.no_cache,
        verbose=not args.production_only
    )

    try:
        # Stage 1: Load STEP file
        shape = runner.get_or_run(
            PipelineStage.LOAD_STEP,
            load_step_file,
            step_file
        )
        if not args.production_only:
            print("STEP file loaded successfully.")

        # Stage 2: Detect holes
        holes = runner.get_or_run(
            PipelineStage.DETECT_HOLES,
            detect_holes,
            shape
        )
        if not args.production_only:
            print(f"Detected {len(holes)} holes.")
            for i, hole in enumerate(holes[:10]):
                print(f"  Hole {i+1}: Diameter={hole.diameter:.2f}, Depth={hole.depth:.2f}")
            if len(holes) > 10:
                print(f"  ... and {len(holes) - 10} more holes")

        # Stage 3: Geometry Analysis
        geom_props = runner.get_or_run(
            PipelineStage.GEOMETRY_ANALYSIS,
            get_geometric_properties,
            shape
        )
        if not args.production_only:
            print(f"Volume: {geom_props['volume']:.2f} mm³, Surface Area: {geom_props['surface_area']:.2f} mm²")

        # Stage 4: Face Analysis
        face_analysis = runner.get_or_run(
            PipelineStage.FACE_ANALYSIS,
            analyze_faces,
            shape
        )
        if not args.production_only:
            print("Face Analysis:", face_analysis)

        # Turned part check (lightweight, no separate cache)
        is_turned = is_turned_part(shape)
        if not args.production_only:
            print(f"Turned Part Classification: {'Yes' if is_turned else 'No'}")

        # Stage 5: Topology
        topology_stats = runner.get_or_run(
            PipelineStage.TOPOLOGY,
            get_topology_stats,
            shape
        )
        if not args.production_only:
            print("Topology Stats:", topology_stats)

        # Stage 6: Component Classification
        component_classification = runner.get_or_run(
            PipelineStage.COMPONENT_CLASSIFICATION,
            classify_components,
            shape
        )
        if not args.production_only:
            print("Component Classification:", component_classification)

        # Stage 7: Detailed Parts Analysis
        if not args.production_only:
            print("Generating detailed component analysis and images...")
        images_dir = os.path.join(os.path.dirname(step_file) if os.path.dirname(step_file) else ".", "part_images")
        detailed_parts = runner.get_or_run(
            PipelineStage.DETAILED_PARTS,
            analyze_components_detailed,
            shape, images_dir
        )
        if not args.production_only:
            print(f"Found {len(detailed_parts)} unique parts.")

        if args.production_info and detailed_parts:
            print("\n" + "="*100)
            print("PRODUCTIE INFORMATIE / PRODUCTION DATA")
            print("="*100)
            # Print header
            headers = ["CalcID", "ArtikelNr", "Aantal", "Vorm", "Dikte", "L x B", "Gaten", "Dia", "Zet", "TegenZet"]
            print(f"{headers[0]:<8} {headers[1]:<12} {headers[2]:<6} {headers[3]:<8} {headers[4]:<6} {headers[5]:<15} {headers[6]:<6} {headers[7]:<12} {headers[8]:<4} {headers[9]:<8}")
            print("-" * 100)
            
            for part in detailed_parts:
                pd = part.get("production_data", {})
                l_x_b = f"{pd.get('Lengte',0)}x{pd.get('Breedte',0)}"
                dia = str(pd.get('DiaSnijgat', []))
                if len(dia) > 12: dia = dia[:9] + "..."
                
                print(f"{pd.get('CalcID', '')[:8]:<8} {pd.get('ArtikelNr', '')[:12]:<12} {pd.get('Aantal', 0):<6} {pd.get('Vorm', '')[:8]:<8} {pd.get('Dikte', 0):<6} {l_x_b:<15} {pd.get('Snijgaten', 0):<6} {dia:<12} {pd.get('ZetAantal', 0):<4} {pd.get('Aantaltegenzet', 0):<8}")
            print("="*100 + "\n")

        # =====================================================================
        # Dutch/ISO Manufacturing Standards Analysis
        # =====================================================================
        if not args.production_only:
            print("\n" + "="*60)
            print("DUTCH/ISO MANUFACTURING STANDARDS ANALYSIS")
            print("="*60)

        # Stage 8: Manufacturing Requirements (ISO 2768)
        if not args.production_only:
            print("\n[ISO 2768] Tolerance Analysis...")
        mfg_requirements = runner.get_or_run(
            PipelineStage.MANUFACTURING_REQUIREMENTS,
            analyze_manufacturing_requirements,
            shape, face_analysis
        )
        if not args.production_only:
            iso_rec = mfg_requirements["iso2768_recommendation"]
            print(f"  Recommended: {iso_rec['designation']}")
            print(f"  Tolerance Table:")
            for tol in iso_rec["tolerance_table"]:
                print(f"    {tol['dimension']:.1f}mm: {tol['tolerance']}")

        # Stage 9: Holes with Fits (ISO 286)
        if not args.production_only:
            print("\n[ISO 286] Hole & Fit Analysis...")
        holes_with_fits = runner.get_or_run(
            PipelineStage.HOLES_WITH_FITS,
            analyze_holes_with_fits,
            shape
        )
        if not args.production_only:
            print(f"  Analyzed {len(holes_with_fits)} unique hole diameters:")
            for h in holes_with_fits[:5]:
                fit = h["fit_recommendation"]
                print(f"    Ø{h['diameter']:.1f}mm (×{h['count']}): {fit['fit']} - {fit['description']}")
                if h["possible_thread"]:
                    print(f"      Possible thread: {h['possible_thread']['designation']}")
            if len(holes_with_fits) > 5:
                print(f"    ... and {len(holes_with_fits) - 5} more diameters")

        # Stage 10: Thread Detection (ISO 68-1 / ISO 261)
        if not args.production_only:
            print("\n[ISO 68-1] Thread Detection...")
        threads = runner.get_or_run(
            PipelineStage.THREADS,
            detect_threads,
            shape
        )
        
        # Calculate thread summary (needed for manufacturing_data)
        thread_summary = {}
        for t in threads:
            des = t["thread_designation"]
            if des not in thread_summary:
                thread_summary[des] = 0
            thread_summary[des] += 1

        if not args.production_only:
            print(f"  Detected {len(threads)} potential threaded holes:")
            for des, count in sorted(thread_summary.items()):
                print(f"    {des}: {count}× (tap drill: {iso_standards.get_tap_drill_size(des)}mm)")

        # ISO 1302 Surface Finish (from mfg_requirements, already cached)
        if not args.production_only:
            print("\n[ISO 1302] Surface Finish Requirements...")
            surface_finish = mfg_requirements["surface_finish"]
            print(f"  Default Ra: {surface_finish['default_ra']} μm")
            print(f"  Recommendation: {surface_finish['general_recommendation']}")
            for sf in surface_finish.get("by_face_type", [])[:3]:
                print(f"    {sf['face_type']}: Ra {sf['recommended_ra']} μm ({sf['typical_process']})")

        # Stage 11: Chamfers & Fillets (ISO 13715)
        if not args.production_only:
            print("\n[ISO 13715] Chamfers & Fillets...")
        edge_analysis = runner.get_or_run(
            PipelineStage.CHAMFERS_FILLETS,
            analyze_chamfers_and_fillets,
            shape
        )
        if not args.production_only:
            print(f"  Chamfers: {edge_analysis['chamfers']['count']} (avg: {edge_analysis['chamfers']['average_size']}mm)")
            print(f"  Fillets: {edge_analysis['fillets']['count']} (avg radius: {edge_analysis['fillets']['average_radius']}mm)")
            print(f"  Note: {edge_analysis['edge_note']}")

        # Stage 12: Mass Properties (EN Standards)
        if not args.production_only:
            print("\n[EN 10025/573] Mass Estimation...")
        mass_steel = runner.get_or_run(
            PipelineStage.MASS_PROPERTIES,
            calculate_mass_properties,
            shape, "steel_s235"
        )
        # Also calculate aluminum (lightweight, doesn't need separate caching)
        mass_alu = calculate_mass_properties(shape, "alu_6061")
        if not args.production_only:
            if mass_steel:
                print(f"  Steel S235JR: {mass_steel['primary']['mass_kg']:.2f} kg")
            if mass_alu:
                print(f"  Aluminum 6061: {mass_alu['primary']['mass_kg']:.2f} kg")

        # Manufacturing Process (from mfg_requirements, already cached)
        if not args.production_only:
            print("\n[Manufacturing Process]")
            mfg_proc = mfg_requirements["manufacturing_process"]
            print(f"  Primary: {mfg_proc['primary']}")
            print(f"  Secondary: {', '.join(mfg_proc['secondary'])}")
            print(f"  Complexity: {mfg_proc['complexity']}")

        # Stage 13: Werkvoorbereiding (Manufacturing Preparation)
        # Check if any werkvoorbereiding module is enabled
        wv_modules = config.modules
        wv_enabled = any([
            wv_modules.cost_estimation,
            wv_modules.tool_list,
            wv_modules.outsourcing,
            wv_modules.surface_treatment,
            wv_modules.purchase_spec
        ])

        werkvoorbereiding_data = None
        if wv_enabled:
            if not args.production_only:
                print("\n" + "="*60)
                print("WERKVOORBEREIDING / MANUFACTURING PREPARATION")
                print("="*60)

            werkvoorbereiding_data = runner.get_or_run(
                PipelineStage.WERKVOORBEREIDING,
                generate_werkvoorbereiding,
                shape, config.material, config.quantity, None,
                config.hourly_rates.to_dict(),
                config.material_prices.to_dict()
            )

            # Cost Estimate
            if wv_modules.cost_estimation and not args.production_only:
                cost = werkvoorbereiding_data["cost_estimate"]
                print(f"\n[Kostprijsberekening]")
                print(f"  Kostprijs per stuk: €{cost['cost_per_piece']:.2f}")
                print(f"  Materiaalkosten: €{cost['breakdown']['material']:.2f}")
                print(f"  Bewerkingskosten: €{cost['breakdown']['machining']:.2f}")
                print(f"  Bewerkingstijd: {cost['time_estimate']['total_time_hours']:.2f} uur")
                print(f"  Uurtarief: €{cost['hourly_rate']:.2f}/uur")
            elif not args.production_only:
                print("\n[Kostprijsberekening] - UITGESCHAKELD")

            # Tool List
            if wv_modules.tool_list and not args.production_only:
                tools = werkvoorbereiding_data["tool_list"]
                print(f"\n[Gereedschapslijst] ({len(tools)} gereedschappen)")
                for tool in tools[:5]:
                    print(f"  - {tool['designation']}: €{tool['estimated_cost']:.2f}")
                if len(tools) > 5:
                    print(f"  ... en {len(tools) - 5} meer")
            elif not args.production_only:
                print("\n[Gereedschapslijst] - UITGESCHAKELD")

            # Outsourcing
            if wv_modules.outsourcing and not args.production_only:
                outsource = werkvoorbereiding_data["outsourcing"]
                print(f"\n[Uitbesteding]")
                print(f"  Categorie: {outsource['primary_category']}")
                print(f"  Doorlooptijd: {outsource['estimated_lead_time_days']} werkdagen")
                print(f"  Aanbeveling: {outsource['recommendation']}")
            elif not args.production_only:
                print("\n[Uitbesteding] - UITGESCHAKELD")

            # Surface Treatment
            if wv_modules.surface_treatment and not args.production_only:
                treatments = werkvoorbereiding_data["surface_treatment_options"]
                if treatments and isinstance(treatments, list) and len(treatments) > 0:
                    if isinstance(treatments[0], dict) and "warning" not in treatments[0]:
                        print(f"\n[Oppervlaktebehandeling Opties]")
                        for t in treatments[:3]:
                            print(f"  - {t['name']} ({t['standard']})")
            elif not args.production_only:
                print("\n[Oppervlaktebehandeling] - UITGESCHAKELD")

            # Purchase Spec
            if wv_modules.purchase_spec and not args.production_only:
                purchase = werkvoorbereiding_data["purchase_specification"]
                print(f"\n[Inkoop Specificatie]")
                print(f"  Materiaal: {purchase['material']['name']}")
                print(f"  Ruw formaat: {purchase['raw_material']['dimensions']}")
                print(f"  Ruw gewicht: {purchase['raw_material']['mass_per_piece_kg']:.2f} kg")
                print(f"  Certificaat: {purchase['certification']}")
            elif not args.production_only:
                print("\n[Inkoop Specificatie] - UITGESCHAKELD")

            if not args.production_only:
                print("\n" + "="*60)
        elif not args.production_only:
            print("\n[Werkvoorbereiding] - ALLE MODULES UITGESCHAKELD")

        # Stage 14: Sheet Metal / Plaatwerk Analysis
        sheetmetal_data = None
        sm_enabled = any([
            wv_modules.sheetmetal_analysis,
            wv_modules.bend_detection,
            wv_modules.kantbank_tooling,
            wv_modules.flat_pattern
        ])

        if sm_enabled:
            if not args.production_only:
                print("\n" + "="*60)
                print("PLAATWERK ANALYSE / SHEET METAL ANALYSIS")
                print("="*60)

            # Detect sheet metal thickness from geometry
            dims = geom_props["bounding_box"]["dimensions"]
            min_dim = min(dims)

            # Only run if part appears to be sheet metal (thin relative to size)
            max_dim = max(dims)
            if min_dim < max_dim * 0.1 and min_dim < 25:  # Likely sheet metal
                sheetmetal_data = runner.get_or_run(
                    PipelineStage.SHEETMETAL,
                    analyze_sheetmetal,
                    shape, min_dim, config.material
                )

                if sheetmetal_data and not sheetmetal_data.get("error"):
                    if wv_modules.sheetmetal_analysis and not args.production_only:
                        print(f"\n[Plaatwerk Detectie]")
                        print(f"  Plaatdikte: {sheetmetal_data['thickness']['value']:.1f}mm")
                        std_text = "(standaard)" if sheetmetal_data['thickness']['is_standard'] else "(niet-standaard)"
                        print(f"  Status: {std_text}")

                    if wv_modules.bend_detection and not args.production_only:
                        bending = sheetmetal_data.get('bending', {})
                        print(f"\n[Buiging Detectie]")
                        print(f"  Aantal buigingen: {bending.get('bend_count', 0)}")
                        print(f"  Min. binnenradius: {bending.get('min_inner_radius', 0):.1f}mm")
                        if bending.get('bends'):
                            for b in bending['bends'][:3]:
                                print(f"    Buiging {b['id']}: {b['angle']}° R{b['radius']}mm")

                    if wv_modules.kantbank_tooling and not args.production_only:
                        tooling = sheetmetal_data.get('tooling', {})
                        print(f"\n[Kantbank Gereedschap]")
                        print(f"  Aanbevolen V-matrijs: {tooling.get('recommended_v_die', 'N/A')}")
                        print(f"  V-opening: {tooling.get('v_opening_mm', 0)}mm")
                        print(f"  Buigkracht: {tooling.get('bend_force_kN_per_m', 0):.1f} kN/m")

                    if wv_modules.flat_pattern and not args.production_only:
                        flat = sheetmetal_data.get('flat_pattern', {})
                        print(f"\n[Uitslag Berekening]")
                        print(f"  K-factor: {flat.get('k_factor_used', 0):.2f}")
                        print(f"  Methode: {flat.get('calculation_method', 'DIN 6935')}")

                    # Warnings
                    warnings = sheetmetal_data.get('warnings', [])
                    if warnings and not args.production_only:
                        print(f"\n[Waarschuwingen]")
                        for w in warnings:
                            print(f"  ⚠ {w}")
                elif not args.production_only:
                    print("  Geen plaatwerk detectie mogelijk (geometrie niet geschikt)")
            elif not args.production_only:
                print("\n[Plaatwerk] Onderdeel lijkt geen plaatwerk te zijn")
                print(f"  (min. dimensie {min_dim:.1f}mm > 10% van max {max_dim:.1f}mm)")

            if not args.production_only:
                print("\n" + "="*60)
        elif not args.production_only:
            print("\n[Plaatwerk] - ALLE MODULES UITGESCHAKELD")

        # Stage 15: Assembly / BOM Analysis
        # Only run if multiple solids detected (assembly)
        assembly_data = None
        if topology_stats.get("solids", 0) > 1:
            if not args.production_only:
                print("\n" + "="*60)
                print("ASSEMBLAGE ANALYSE / ASSEMBLY ANALYSIS (BOM)")
                print("="*60)

            part_name_for_bom = os.path.splitext(os.path.basename(step_file))[0]
            assembly_data = runner.get_or_run(
                PipelineStage.ASSEMBLY_BOM,
                analyze_assembly_bom,
                shape, part_name_for_bom, config.material
            )

            if assembly_data and not assembly_data.get("error") and not args.production_only:
                summary = assembly_data.get("summary", {})
                print(f"\n[Stuklijst / Bill of Materials]")
                print(f"  Totaal onderdelen: {assembly_data.get('total_parts', 0)}")
                print(f"  Unieke onderdelen: {assembly_data.get('unique_parts', 0)}")
                print(f"  Bevestigingsmiddelen: {assembly_data.get('total_fasteners', 0)}")
                print(f"  Te vervaardigen: {summary.get('manufactured_parts', 0)}")
                print(f"  Inkoop onderdelen: {summary.get('purchased_parts', 0)}")

                print(f"\n[Massa & Kosten]")
                print(f"  Totale massa: {assembly_data.get('total_mass_kg', 0):.3f} kg")
                print(f"  Geschatte montage tijd: {assembly_data.get('estimated_assembly_time_hours', 0):.2f} uur")
                print(f"  Geschatte totale kosten: €{assembly_data.get('estimated_total_cost', 0):.2f}")

                # Fastener summary
                fasteners = assembly_data.get("fastener_summary", {})
                if fasteners:
                    print(f"\n[Bevestigingsmiddelen Overzicht]")
                    for desc, count in fasteners.items():
                        print(f"  {count}× {desc}")

                # BOM Preview (first 5 items)
                flat_bom = assembly_data.get("flat_bom", [])
                if flat_bom:
                    print(f"\n[Stuklijst Preview (eerste 5)]")
                    print(f"  {'Item':<6} {'Naam':<25} {'Aantal':<8} {'Massa (kg)':<12}")
                    print(f"  {'-'*6} {'-'*25} {'-'*8} {'-'*12}")
                    for item in flat_bom[:5]:
                        print(f"  {item.get('item_number', ''):<6} {item.get('part_name', '')[:25]:<25} {item.get('quantity', 0):<8} {item.get('total_mass_kg', 0):.3f}")
                    if len(flat_bom) > 5:
                        print(f"  ... en {len(flat_bom) - 5} meer onderdelen")

            if not args.production_only:
                print("\n" + "="*60)

        # Stage 16: Simple Cost Table (if enabled)
        simple_cost_table_data = None
        if config.modules.simple_cost_report and detailed_parts and not args.production_only:
            print("\n" + "="*60)
            print("EENVOUDIG KOSTENOVERZICHT / SIMPLE COST TABLE")
            print("="*60)

            # Get enabled columns from config
            enabled_columns = config.cost_columns.get_enabled_columns()

            simple_cost_table_data = generate_simple_cost_table(
                parts=detailed_parts,
                material=config.material,
                quantity=config.quantity,
                hourly_rates_config=config.hourly_rates.to_dict(),
                material_prices_config=config.material_prices.to_dict(),
                enabled_columns=enabled_columns
            )

            # Print table preview
            headers = simple_cost_table_data.get('headers', [])
            rows = simple_cost_table_data.get('rows', [])

            print(f"\n[Kostentabel] ({len(rows)} onderdelen)")
            print(f"  Kolommen: {', '.join(headers)}")
            print(f"  Totaal: €{simple_cost_table_data.get('grand_total', 0):.2f}")

            # Show first few rows
            for row in rows[:5]:
                artikel = row.get('artikel', '')[:20]
                totaal = row.get('totaal', 0)
                print(f"    {artikel:<20} €{totaal:.2f}")
            if len(rows) > 5:
                print(f"    ... en {len(rows) - 5} meer onderdelen")

            print("\n" + "="*60)

        # Compile all manufacturing data with module config
        manufacturing_data = {
            "iso2768": mfg_requirements["iso2768_recommendation"] if wv_modules.iso2768_tolerances else None,
            "surface_finish": mfg_requirements["surface_finish"] if wv_modules.iso1302_surface else None,
            "manufacturing_process": mfg_requirements["manufacturing_process"],
            "holes_with_fits": holes_with_fits if wv_modules.iso286_fits else None,
            "threads": {
                "detected": threads,
                "summary": thread_summary,
            } if wv_modules.iso68_threads else None,
            "edges": edge_analysis if wv_modules.iso13715_edges else None,
            "mass_estimates": {
                "steel_s235": mass_steel["primary"] if mass_steel else None,
                "steel_s355": mass_steel["alternatives"].get("steel_s355") if mass_steel else None,
                "alu_6061": mass_alu["primary"] if mass_alu else None,
                "alu_7075": mass_alu["alternatives"].get("alu_7075") if mass_alu else None,
            } if wv_modules.mass_estimation else None,
            "material_options": list(iso_standards.get_all_materials_by_category().keys()),
            "werkvoorbereiding": werkvoorbereiding_data,
            "sheetmetal": sheetmetal_data,
            "assembly": assembly_data,
            # Simple cost table for simplified reports
            "simple_cost_table": simple_cost_table_data,
            # Store module configuration for PDF report
            "module_config": config.modules.to_dict(),
            # Store cost columns configuration
            "cost_columns_config": config.cost_columns.to_dict(),
        }

        if not args.production_only:
            print("\n" + "="*60)

        # Stage 13: PDF Correlation
        if not args.production_only:
            print("\nCorrelating Data...")
        pdf_dims = extract_dimensions_from_pdf(pdf_file)

        def correlate_all_holes(holes_list, dims):
            matches = []
            for hole in holes_list:
                match = correlate_hole_dimension(hole, dims)
                if match:
                    matches.append(match)
            return matches

        matches = runner.get_or_run(
            PipelineStage.PDF_CORRELATION,
            correlate_all_holes,
            holes, pdf_dims
        )

        # Save Results (always run, not cached)
        if not args.production_only:
            print("\nSaving results...")
        part_name = os.path.splitext(os.path.basename(step_file))[0]

        # Save to Database
        db.save_analysis_results(part_name, holes, matches, is_turned)

        # Save to JSON (with new manufacturing data)
        json_file = f"{part_name}_results.json"
        save_to_json(
            json_file, part_name, holes, matches, is_turned,
            geom_props, face_analysis, topology_stats, component_classification,
            detailed_parts, manufacturing_data, verbose=not args.production_only
        )

        # Generate PDF Report
        if not args.no_report:
            output_pdf = f"{part_name}_report.pdf"
            if not args.production_only:
                print(f"Generating PDF report: {output_pdf}")
            report_gen = PDFReportGenerator(json_file)
            report_gen.generate_report(output_pdf)

        # Mark pipeline complete
        if not args.no_cache:
            runner.cache.save_stage(PipelineStage.COMPLETE, True, step_file)

        if not args.production_only:
            print("\n" + "="*60)
            print("ANALYSIS COMPLETE")
            print(f"  JSON: {json_file}")
            if not args.no_report:
                print(f"  PDF:  {output_pdf}")
            print("="*60)

        # Show cache status
        if not args.production_only:
            print("\n" + runner.status())

    except Exception as e:
        import traceback
        print(f"An error occurred during analysis: {e}")
        traceback.print_exc()
        print("\nTip: Use --status to see which stages completed successfully.")
        print("     Use --from <stage> to resume from a specific stage.")


if __name__ == "__main__":
    main()
