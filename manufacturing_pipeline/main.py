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
    from src.step_processing import load_step_file
    from src.pdf_processing import extract_dimensions_from_pdf
    from src.correlation import correlate_hole_dimension
    from src.database import DatabaseManager
    from src.report_generator import PDFReportGenerator
    from src import iso_standards
    from src.cache_manager import CacheManager, PipelineRunner, PipelineStage
    from src.config import PipelineConfig
    from src.pipeline_init import (
        normalize_args, resolve_input_paths, resolve_db_paths,
        load_or_init_pipeline_config, handle_module_listing, handle_stage_listing,
        handle_config_display_and_save, handle_cache_commands, parse_force_from_stage
    )
    from src.pipeline_stages import (
        run_geometry_and_topology_stages, run_iso_standards_stages,
        run_werkvoorbereiding_stage, run_sheetmetal_stage, run_assembly_bom_stage,
        run_simple_cost_table_stage, compile_manufacturing_data
    )
    from src.cli_output import print_section_header, print_production_info_table
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


def run_full_pipeline(step_file, pdf_file, db_path, schema_path, args, config, cache, force_from):
    """Run the full manufacturing analysis pipeline."""
    production_only = args.production_only

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

    if not production_only:
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
        verbose=not production_only
    )

    try:
        # Stages 1-7: Geometry and Topology
        geo_results = run_geometry_and_topology_stages(runner, step_file, production_only)
        
        shape = geo_results["shape"]
        holes = geo_results["holes"]
        is_turned = geo_results["is_turned"]
        geom_props = geo_results["geom_props"]
        face_analysis = geo_results["face_analysis"]
        topology_stats = geo_results["topology_stats"]
        component_classification = geo_results["component_classification"]
        detailed_parts = geo_results["detailed_parts"]

        # Production info table
        if args.production_info and detailed_parts:
            print_production_info_table(detailed_parts)

        # Stages 8-12: ISO Standards Analysis
        iso_results = run_iso_standards_stages(runner, shape, face_analysis, production_only)
        
        mfg_requirements = iso_results["mfg_requirements"]
        holes_with_fits = iso_results["holes_with_fits"]
        threads = iso_results["threads"]
        thread_summary = iso_results["thread_summary"]
        edge_analysis = iso_results["edge_analysis"]
        mass_steel = iso_results["mass_steel"]
        mass_alu = iso_results["mass_alu"]

        # Stage 13: Werkvoorbereiding
        werkvoorbereiding_data = run_werkvoorbereiding_stage(runner, shape, config, production_only)

        # Stage 14: Sheet Metal Analysis
        sheetmetal_data = run_sheetmetal_stage(runner, shape, geom_props, config, production_only)

        # Stage 15: Assembly/BOM Analysis
        assembly_data = run_assembly_bom_stage(runner, shape, topology_stats, step_file, config, production_only)

        # Stage 16: Simple Cost Table
        simple_cost_table_data = run_simple_cost_table_stage(detailed_parts, config, production_only)

        # Compile all manufacturing data
        manufacturing_data = compile_manufacturing_data(
            mfg_requirements, holes_with_fits, threads, thread_summary,
            edge_analysis, mass_steel, mass_alu, werkvoorbereiding_data,
            sheetmetal_data, assembly_data, simple_cost_table_data, config
        )

        if not production_only:
            print("\n" + "="*60)

        # Stage 17: PDF Correlation
        if not production_only:
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

        # Save Results
        if not production_only:
            print("\nSaving results...")
        part_name = os.path.splitext(os.path.basename(step_file))[0]

        # Save to Database
        db.save_analysis_results(part_name, holes, matches, is_turned)

        # Save to JSON
        json_file = f"{part_name}_results.json"
        save_to_json(
            json_file, part_name, holes, matches, is_turned,
            geom_props, face_analysis, topology_stats, component_classification,
            detailed_parts, manufacturing_data, verbose=not production_only
        )

        # Generate PDF Report
        if not args.no_report:
            output_pdf = f"{part_name}_report.pdf"
            if not production_only:
                print(f"Generating PDF report: {output_pdf}")
            report_gen = PDFReportGenerator(json_file)
            report_gen.generate_report(output_pdf)

        # Mark pipeline complete
        if not args.no_cache:
            runner.cache.save_stage(PipelineStage.COMPLETE, True, step_file)

        if not production_only:
            print("\n" + "="*60)
            print("ANALYSIS COMPLETE")
            print(f"  JSON: {json_file}")
            if not args.no_report:
                print(f"  PDF:  {output_pdf}")
            print("="*60)

        # Show cache status
        if not production_only:
            print("\n" + runner.status())

    except Exception as e:
        import traceback
        print(f"An error occurred during analysis: {e}")
        traceback.print_exc()
        print("\nTip: Use --status to see which stages completed successfully.")
        print("     Use --from <stage> to resume from a specific stage.")


def main():
    args = parse_args()

    # Normalize arguments (handle implications like --production-only)
    normalize_args(args)

    # Resolve paths
    step_file, pdf_file = resolve_input_paths(args.file, args.pdf)
    db_path, schema_path = resolve_db_paths(os.path.dirname(__file__))

    # Handle early-exit commands
    if handle_module_listing(args):
        return

    if handle_stage_listing(args):
        return

    # Load configuration
    config = load_or_init_pipeline_config(args, step_file, os.path.dirname(__file__))

    if handle_config_display_and_save(args, config):
        return

    # Initialize cache manager
    cache = CacheManager(args.cache_dir)

    if handle_cache_commands(args, cache):
        return

    # Parse --from stage
    force_from = parse_force_from_stage(args.from_stage)
    if args.from_stage and force_from is None:
        return  # Error already printed

    # Show active configuration if modules were toggled
    if (args.enable or args.disable) and not args.production_only:
        from src.config import print_module_status
        print_module_status(config.modules)

    # Run the pipeline
    run_full_pipeline(step_file, pdf_file, db_path, schema_path, args, config, cache, force_from)


if __name__ == "__main__":
    main()
