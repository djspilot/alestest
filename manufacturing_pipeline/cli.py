#!/usr/bin/env python3
"""
Manufacturing Pipeline - Unified CLI

Modes:
  - Quick mode (default): Fast AAG-based analysis with simple reports
  - Full mode (--full):   Complete ISO pipeline with database storage
  - Batch mode (--batch): Process multiple files (parallel or sequential)
"""
import sys
import os
import argparse
import json
import hashlib
from concurrent.futures import ProcessPoolExecutor, as_completed
from multiprocessing import cpu_count
from datetime import datetime

from manufacturing_pipeline.core.utils import (
    PROJECT_ROOT, DATA_DIR, DB_DIR, PARTS_DIR, OUTPUT_DIR,
    find_step_files, select_step_file, get_output_dir,
    run_analysis, run_aag_analysis, run_debug,
    generate_simple_pdf, generate_compact_pdf,
    process_single_file,
    get_file_hash, load_cache, save_cache, cache_result,
)


# ---------------------------------------------------------------------------
# Full-pipeline helpers (lazy imports to keep quick mode fast)
# ---------------------------------------------------------------------------

def _import_full_pipeline():
    """Lazy import of full pipeline modules (only needed for --full mode)."""
    from manufacturing_pipeline.analysis.step_processing import load_step_file
    from manufacturing_pipeline.reporting.pdf_processing import extract_dimensions_from_pdf
    from manufacturing_pipeline.analysis.correlation import correlate_hole_dimension
    from manufacturing_pipeline.data.database import DatabaseManager
    from manufacturing_pipeline.reporting.report_generator import PDFReportGenerator
    from manufacturing_pipeline.analysis import iso_standards  # noqa: F841
    from manufacturing_pipeline.data.cache_manager import CacheManager, PipelineRunner, PipelineStage
    from manufacturing_pipeline.core.config import PipelineConfig
    from manufacturing_pipeline.core.pipeline_init import (
        normalize_args, resolve_input_paths, resolve_db_paths,
        load_or_init_pipeline_config, handle_module_listing, handle_stage_listing,
        handle_config_display_and_save, handle_cache_commands, parse_force_from_stage,
    )
    from manufacturing_pipeline.analysis.pipeline_stages import (
        run_geometry_and_topology_stages, run_iso_standards_stages,
        run_werkvoorbereiding_stage, run_sheetmetal_stage, run_assembly_bom_stage,
        run_simple_cost_table_stage, compile_manufacturing_data,
    )
    from manufacturing_pipeline.reporting.cli_output import print_section_header, print_production_info_table
    from dataclasses import asdict

    # Return everything as a namespace dict so the caller can pick what it needs.
    return {k: v for k, v in locals().items()}


def save_to_json(filename, part_name, holes, matches, is_turned, geom_props=None,
                 face_analysis=None, topology_stats=None, component_classification=None,
                 detailed_parts=None, manufacturing_data=None, route_result=None, verbose=True):
    """Save full-pipeline analysis results to a JSON file."""
    from dataclasses import asdict

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
                "status": m.status.value,
            }
            for m in matches
        ],
        "manufacturing_analysis": manufacturing_data,
    }

    if route_result is not None:
        data["route"] = {
            "category": route_result.category.value,
            "profile_label": route_result.profile_label,
            "confidence": route_result.confidence,
            "reasoning": route_result.reasoning,
            "variant": route_result.variant,
            "method": route_result.method,
        }

    with open(filename, "w", encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    if verbose:
        print(f"Results saved to {filename}")


# ---------------------------------------------------------------------------
# Full pipeline runner
# ---------------------------------------------------------------------------

def run_full_pipeline(step_file, pdf_file, db_path, schema_path, args, config, cache, force_from):
    """Run the full manufacturing analysis pipeline with ISO standards."""
    mods = _import_full_pipeline()
    DatabaseManager = mods["DatabaseManager"]
    PipelineRunner = mods["PipelineRunner"]
    PipelineStage = mods["PipelineStage"]
    PDFReportGenerator = mods["PDFReportGenerator"]
    extract_dimensions_from_pdf = mods["extract_dimensions_from_pdf"]
    correlate_hole_dimension = mods["correlate_hole_dimension"]
    run_geometry_and_topology_stages = mods["run_geometry_and_topology_stages"]
    run_iso_standards_stages = mods["run_iso_standards_stages"]
    run_werkvoorbereiding_stage = mods["run_werkvoorbereiding_stage"]
    run_sheetmetal_stage = mods["run_sheetmetal_stage"]
    run_assembly_bom_stage = mods["run_assembly_bom_stage"]
    run_simple_cost_table_stage = mods["run_simple_cost_table_stage"]
    compile_manufacturing_data = mods["compile_manufacturing_data"]
    print_production_info_table = mods["print_production_info_table"]

    production_only = getattr(args, "production_only", False)

    # Initialize Database
    db = DatabaseManager(db_path)
    try:
        db.initialize_schema(schema_path)
    except Exception as e:
        print(f"Warning: Could not initialize database schema: {e}")

    if not os.path.exists(step_file):
        print(f"STEP file not found: {step_file}")
        return

    if not production_only:
        print(f"Analyzing {step_file}...")
        print(f"Cache directory: {args.cache_dir}")
        if args.no_cache:
            print("Caching disabled - running all stages fresh")
        print()

    runner = PipelineRunner(
        step_file=step_file,
        cache_dir=args.cache_dir,
        force_from=force_from,
        no_cache=args.no_cache,
        verbose=not production_only,
    )

    # === Pre-routing ===
    if not production_only:
        print("Running profile router...")
    try:
        from manufacturing_pipeline.analysis.router import route_step_file as _route_step_file
        route_result = _route_step_file(step_file)
        if not production_only:
            print(f"  Route: {route_result.category.value.upper()} "
                  f"(profiel: {route_result.profile_label}, "
                  f"confidence: {route_result.confidence:.0%})")
            print(f"  {route_result.reasoning}\n")
    except Exception as e:
        if not production_only:
            print(f"  Warning: Router failed ({e}), continuing without routing\n")
        route_result = None

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

        if getattr(args, "production_info", False) and detailed_parts:
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

        manufacturing_data = compile_manufacturing_data(
            mfg_requirements, holes_with_fits, threads, thread_summary,
            edge_analysis, mass_steel, mass_alu, werkvoorbereiding_data,
            sheetmetal_data, assembly_data, simple_cost_table_data, config,
        )

        if not production_only:
            print("\n" + "=" * 60)

        # Stage 17: PDF Correlation
        if not production_only:
            print("\nCorrelating Data...")
        pdf_dims = extract_dimensions_from_pdf(pdf_file)

        def correlate_all_holes(holes_list, dims):
            return [m for h in holes_list if (m := correlate_hole_dimension(h, dims))]

        matches = runner.get_or_run(PipelineStage.PDF_CORRELATION, correlate_all_holes, holes, pdf_dims)

        # Save Results
        if not production_only:
            print("\nSaving results...")
        part_name = os.path.splitext(os.path.basename(step_file))[0]

        db.save_analysis_results(part_name, holes, matches, is_turned)

        json_file = f"{part_name}_results.json"
        save_to_json(
            json_file, part_name, holes, matches, is_turned,
            geom_props, face_analysis, topology_stats, component_classification,
            detailed_parts, manufacturing_data, route_result=route_result,
            verbose=not production_only,
        )

        if not getattr(args, "no_report", False):
            output_pdf = f"{part_name}_report.pdf"
            if not production_only:
                print(f"Generating PDF report: {output_pdf}")
            report_gen = PDFReportGenerator(json_file)
            report_gen.generate_report(output_pdf)

        if not args.no_cache:
            runner.cache.save_stage(PipelineStage.COMPLETE, True, step_file)

        if not production_only:
            print("\n" + "=" * 60)
            print("ANALYSIS COMPLETE")
            print(f"  JSON: {json_file}")
            if not getattr(args, "no_report", False):
                print(f"  PDF:  {output_pdf}")
            print("=" * 60)
            print("\n" + runner.status())

    except Exception as e:
        import traceback
        print(f"An error occurred during analysis: {e}")
        traceback.print_exc()
        print("\nTip: Use --status to see which stages completed successfully.")
        print("     Use --from <stage> to resume from a specific stage.")


# ---------------------------------------------------------------------------
# Quick-mode single-file runner
# ---------------------------------------------------------------------------

def run_quick(step_file, args):
    """Run quick AAG-based analysis on a single STEP file."""
    output_dir, part_name = get_output_dir(step_file)

    print(f"\n{'=' * 60}")
    print(f"QUICK ANALYSIS: {part_name}")
    print(f"{'=' * 60}")
    print(f"Input:  {step_file}")
    print(f"Output: {output_dir}/")
    print(f"Mode:   Quick (use --full for complete ISO pipeline)")

    try:
        analysis, total_holes = run_analysis(step_file, output_dir, args)

        # Run AAG analysis if requested
        if args.aag:
            print("\n[AAG] Running Attributed Adjacency Graph analysis...")
            aag_result = run_aag_analysis(step_file)

            if aag_result.get("success"):
                print(f"\n--- AAG Analyse Resultaat ---")
                print(f"Type:             {aag_result.get('part_type', 'ONBEKEND')}")
                print(f"Gaten (AAG):      {aag_result['hole_count']}")
                print(f"Slots (AAG):      {aag_result['slot_count']}")
                print(f"Zettingen:        {aag_result['bend_count']}")
                print(f"Tegenzettingen:   {aag_result.get('counter_bend_count', 0)}")
                print(f"Dikte (AAG):      {aag_result['thickness']:.2f} mm")
                print(f"Snijlengte:       {aag_result['total_cut_length']:.0f} mm")
                print(f"Pierces:          {aag_result['pierce_count']}")
                if args.verbose:
                    print(f"Faces/Edges:      {aag_result['face_count']}/{aag_result['edge_count']}")
                    print(f"Skin/Thickness:   {aag_result['skin_faces']}/{aag_result['thickness_faces']}")
                    print(f"Raw bends/Prod:   {aag_result.get('all_bend_count', '?')}/{aag_result.get('production_bend_count', '?')}")
                if args.verbose and aag_result.get("holes_detail"):
                    print(f"\n--- Gaten Detail (AAG) ---")
                    for h in aag_result["holes_detail"][:10]:
                        q_str = f"Q={h['isoperimetric_quotient']:.2f}" if h.get("isoperimetric_quotient") else ""
                        diam = h.get("diameter") or 0
                        print(f"  {h['type']}: \u00d8{diam:.1f}mm, P={h['perimeter']:.0f}mm {q_str}")
                if args.verbose and aag_result.get("bends_detail"):
                    print(f"\n--- Zettingen Detail (AAG) ---")
                    for b in aag_result["bends_detail"][:10]:
                        print(f"  {b['type']}: {b['angle']:.0f}\u00b0, R={b['radius']:.1f}mm, L={b['length']:.0f}mm, K={b['k_factor']:.2f}")

                aag_json_path = os.path.join(output_dir, f"{part_name}_aag.json")
                with open(aag_json_path, "w") as f:
                    json.dump(aag_result, f, indent=2)
                print(f"\n  AAG JSON: {aag_json_path}")
            else:
                print(f"  AAG analyse gefaald: {aag_result.get('error', 'Unknown error')}")

        if not args.no_pdf:
            print("\nGenerating PDF report...")
            generate_compact_pdf(step_file, output_dir, part_name, analysis, total_holes)

        # Excel export (SpaceClaim format)
        if args.excel:
            from pathlib import Path
            from manufacturing_pipeline.reporting.excel_exporter import export_to_excel

            # Build enriched result dict
            result_dict = {
                "file": os.path.basename(step_file),
                "success": True,
                "category": getattr(analysis, "part_category", "UNKNOWN"),
                "part_type": str(getattr(analysis, "part_type", "").value)
                    if hasattr(getattr(analysis, "part_type", None), "value")
                    else str(getattr(analysis, "part_type", "")),
                "thickness": getattr(analysis, "thickness", 0),
                "dimensions": {
                    "length": getattr(analysis, "length", 0),
                    "width": getattr(analysis, "width", 0),
                    "height": getattr(analysis, "height", 0),
                },
                "flat_dimensions": None,
                "production": {
                    "holes_total": total_holes,
                    "bends_total": getattr(analysis, "bend_count_erp", 0),
                    "bends_up": 0,
                    "bends_down": 0,
                },
                "aag_details": {},
            }

            # Add flat dimensions if available
            flat_l = getattr(analysis, "flat_length", 0)
            flat_w = getattr(analysis, "flat_width", 0)
            if flat_l > 0 and flat_w > 0:
                result_dict["flat_dimensions"] = {"length": flat_l, "width": flat_w}

            # Add AAG details if available
            if args.aag and aag_result and aag_result.get("success"):
                result_dict["aag_details"] = {
                    "total_cut_length": aag_result.get("total_cut_length", 0),
                    "counter_bend_count": aag_result.get("counter_bend_count", 0),
                }

            excel_path = Path(output_dir) / f"{part_name}.xlsx"
            ref_path = Path(args.reference) if args.reference else None
            export_to_excel([result_dict], excel_path, reference_path=ref_path)
            print(f"\n  Excel: {excel_path}")

        print(f"\n{'=' * 60}")
        print(f"COMPLETE")
        print(f"{'=' * 60}")
        print(f"Output files in: {output_dir}/")
        for fname in sorted(os.listdir(output_dir)):
            if os.path.isfile(os.path.join(output_dir, fname)):
                print(f"  - {fname}")

    except Exception as e:
        print(f"\nError: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


# ---------------------------------------------------------------------------
# Batch processing
# ---------------------------------------------------------------------------

def run_batch(step_files, args, cache):
    """Run batch processing over multiple STEP files."""
    try:
        from tqdm import tqdm
        has_tqdm = True
    except ImportError:
        has_tqdm = False

    num_workers = args.parallel
    if num_workers == 0:
        num_workers = max(1, cpu_count() - 1)

    args_dict = {
        "analyze": args.analyze,
        "aag": args.aag,
        "verbose": args.verbose,
        "debug": args.debug,
        "no_unfold": args.no_unfold,
        "no_pdf": args.no_pdf,
        "no_cache": args.no_cache,
    }

    results = []
    completed = 0
    failed = 0
    cached_count = 0

    def _handle_result(result):
        nonlocal completed, failed, cached_count, cache
        if result["success"]:
            completed += 1
            if result.get("cached"):
                cached_count += 1
            if not result.get("cached") and result.get("filepath"):
                cache = cache_result(result["filepath"], result, cache)
        else:
            failed += 1
        results.append(result)
        return result

    if num_workers > 1:
        if not args.json:
            print(f"\nBatch processing {len(step_files)} files with {num_workers} workers...")
        with ProcessPoolExecutor(max_workers=num_workers) as executor:
            future_to_file = {
                executor.submit(process_single_file, sf, args_dict, cache): sf
                for sf in step_files
            }
            futures_iter = as_completed(future_to_file)
            if has_tqdm and not args.json:
                futures_iter = tqdm(
                    futures_iter, total=len(step_files),
                    desc="Processing", unit="file",
                    bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]",
                )
            for future in futures_iter:
                r = _handle_result(future.result())
                if not args.json and not has_tqdm:
                    total_done = completed + failed
                    if r["success"]:
                        tag = " (cached)" if r.get("cached") else ""
                        print(f"  [{total_done}/{len(step_files)}] {r['file']} - {r['category']}, {r['holes']} holes{tag}")
                    else:
                        print(f"  [{total_done}/{len(step_files)}] {r['file']} - Error: {r['error']}")
    else:
        if not args.json:
            print(f"\nBatch processing {len(step_files)} files...")
        files_iter = step_files
        if has_tqdm and not args.json:
            files_iter = tqdm(
                step_files, desc="Processing", unit="file",
                bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]",
            )
        for step_file in files_iter:
            r = _handle_result(process_single_file(step_file, args_dict, cache))
            if not args.json and not has_tqdm:
                if r["success"]:
                    tag = " (cached)" if r.get("cached") else ""
                    print(f"  {r['file']} - {r['category']}, {r['holes']} holes{tag}")
                else:
                    print(f"  {r['file']} - Error: {r['error']}")

    # Save updated cache
    if not args.no_cache:
        save_cache(cache)

    # Output results
    if args.json:
        output = {
            "summary": {
                "total": len(step_files),
                "succeeded": completed,
                "failed": failed,
                "cached": cached_count,
                "timestamp": datetime.now().isoformat(),
            },
            "results": sorted(results, key=lambda x: x["file"]),
        }
        print(json.dumps(output, indent=2, default=str))
    else:
        print(f"\n{'=' * 60}")
        cache_msg = f" ({cached_count} from cache)" if cached_count > 0 else ""
        print(f"Batch complete: {completed} succeeded{cache_msg}, {failed} failed")
        print(f"Output in: {OUTPUT_DIR}/")
        if results:
            print(f"\n{'=' * 60}")
            print(f"{'File':<35} {'Category':<20} {'Holes':>6} {'Bends':>6} {'Cache':>6}")
            print(f"{'-' * 35} {'-' * 20} {'-' * 6} {'-' * 6} {'-' * 6}")
            for r in sorted(results, key=lambda x: x["file"]):
                if r["success"]:
                    cache_mark = "\u2713" if r.get("cached") else ""
                    print(f"{r['file']:<35} {r['category']:<20} {r['holes']:>6} {r['bends']:>6} {cache_mark:>6}")

    # Excel export for batch (one combined Excel with all results)
    if args.excel and results:
        from pathlib import Path
        from manufacturing_pipeline.reporting.excel_exporter import export_to_excel

        successful = [r for r in results if r.get("success")]
        if successful:
            excel_path = Path(OUTPUT_DIR) / "batch_results.xlsx"
            ref_path = Path(args.reference) if args.reference else None
            export_to_excel(successful, excel_path, reference_path=ref_path)
            print(f"\n  Excel: {excel_path}")


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def parse_args():
    """Parse command line arguments for all modes."""
    parser = argparse.ArgumentParser(
        description="Manufacturing Pipeline - Analyze STEP files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Modes:
  Quick (default)   Fast AAG-based analysis
  Full (--full)     Complete ISO pipeline with database
  Batch (--batch)   Process multiple files (optionally parallel)

Examples - Quick Mode:
  python run.py                              Interactive file selection
  python run.py -f mypart.step               Analyze specific file
  python run.py -f mypart.step --aag         With AAG topology analysis
  python run.py -f mypart.step --aag -v      AAG with verbose details

Examples - Batch Mode:
  python run.py -f ./folder --batch -p 4     Parallel batch (4 workers)
  python run.py -f ./folder --batch --json   JSON output for ERP

Examples - Full Mode:
  python run.py -f mypart.step --full        Full ISO pipeline
  python run.py --full --production-info     With production table

Full Mode - Cache Management:
  python run.py --full --status              Show cache status
  python run.py --full --clear-cache         Clear cached data
  python run.py --full --from threads        Resume from specific stage
  python run.py --full --list-stages         List pipeline stages

Full Mode - Module Control:
  python run.py --full --list-modules        List available modules
  python run.py --full --disable cost_estimation
        """,
    )

    # File selection
    parser.add_argument("-f", "--file", help="STEP file or folder path")

    # Mode selection
    parser.add_argument("--full", action="store_true",
                        help="Run full ISO pipeline with database (slower, more detailed)")

    # Quick mode options
    parser.add_argument("--analyze", action="store_true", help="Show detailed analysis with reasoning")
    parser.add_argument("--aag", action="store_true", help="Run AAG (Attributed Adjacency Graph) analysis")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--debug", action="store_true", help="Debug hole detection")
    parser.add_argument("--no-unfold", action="store_true", help="Skip automatic unfolding")
    parser.add_argument("--no-pdf", action="store_true", help="Skip PDF generation")

    # Batch options
    parser.add_argument("--batch", action="store_true", help="Process all STEP files in folder")
    parser.add_argument("--parallel", "-p", type=int, default=1, metavar="N",
                        help="Number of parallel workers (default: 1, use 0 for auto)")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")

    # Cache options (shared between quick batch cache and full pipeline cache)
    parser.add_argument("--no-cache", action="store_true", help="Skip cache, force re-analysis")
    parser.add_argument("--clear-cache", action="store_true", help="Clear cache and exit")

    # Full mode options
    parser.add_argument("--pdf", default=None,
                        help="PDF file for dimension correlation (full mode)")
    parser.add_argument("--production-info", action="store_true",
                        help="Show production information table (full mode)")
    parser.add_argument("--production-only", action="store_true",
                        help="Show ONLY production table (full mode, implies --production-info, --no-report)")
    parser.add_argument("--no-report", action="store_true",
                        help="Skip PDF report generation (full mode)")
    parser.add_argument("--status", action="store_true",
                        help="Show full pipeline cache status and exit")
    parser.add_argument("--from", dest="from_stage", metavar="STAGE",
                        help="Re-run full pipeline from specific stage")
    parser.add_argument("--list-stages", action="store_true",
                        help="List all full pipeline stages")
    parser.add_argument("--cache-dir", default=".pipeline_cache",
                        help="Full pipeline cache directory (default: .pipeline_cache)")

    # Full mode - module control
    parser.add_argument("--enable", action="append", default=[], metavar="MODULE",
                        help="Enable specific module or group (full mode)")
    parser.add_argument("--disable", action="append", default=[], metavar="MODULE",
                        help="Disable specific module or group (full mode)")
    parser.add_argument("--list-modules", action="store_true",
                        help="List all available modules (full mode)")
    parser.add_argument("--show-config", action="store_true",
                        help="Show current module configuration (full mode)")
    parser.add_argument("--config", metavar="FILE",
                        help="Load module configuration from JSON file (full mode)")
    parser.add_argument("--save-config", metavar="FILE",
                        help="Save current configuration to JSON file (full mode)")

    # Manufacturing parameters
    parser.add_argument("--material", default="steel_s235",
                        help="Material for cost estimation (default: steel_s235)")
    parser.add_argument("--quantity", type=int, default=1,
                        help="Quantity for cost estimation (default: 1)")

    # Utility
    parser.add_argument("--list", action="store_true", help="List available STEP files")

    # Export options
    parser.add_argument("--excel", action="store_true",
                        help="Export results to Excel in SpaceClaim column format")
    parser.add_argument("--reference", metavar="FILE",
                        help="SpaceClaim reference file (.xlsx/.xml) for comparison sheet")

    return parser.parse_args()


# ---------------------------------------------------------------------------
# File resolution helpers
# ---------------------------------------------------------------------------

def resolve_step_file(args, step_files):
    """Resolve a single STEP file from args and available files."""
    if args.file:
        if os.path.exists(args.file):
            return args.file
        candidate = os.path.join(PARTS_DIR, args.file)
        if os.path.exists(candidate):
            return candidate
        # Fuzzy match in discovered files
        matches = [f for f in step_files if args.file in f]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            print(f"Multiple matches for '{args.file}':")
            for m in matches:
                print(f"  - {os.path.relpath(m, PROJECT_ROOT)}")
            return None
        print(f"File not found: {args.file}")
        return None

    if not step_files:
        print(f"No STEP files found in {PARTS_DIR}")
        print("Place your STEP files in the data/input/ folder")
        return None

    return select_step_file(step_files)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main():
    args = parse_args()

    # Ensure data directories exist
    os.makedirs(PARTS_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(DB_DIR, exist_ok=True)

    # --- Full mode early-exit commands (don't need a file) ---
    if args.full or args.list_stages or args.list_modules or args.show_config or args.status:
        return _main_full(args)

    # --- Quick cache clear ---
    if args.clear_cache and not args.full:
        from manufacturing_pipeline.core.utils import CACHE_FILE
        if os.path.exists(CACHE_FILE):
            os.remove(CACHE_FILE)
            print(f"Cache cleared: {CACHE_FILE}")
        else:
            print("No cache file found.")
        return

    # Determine search directory
    search_dir = None
    if args.file and os.path.isdir(args.file):
        search_dir = args.file

    step_files = find_step_files(search_dir)

    # --- List mode ---
    if args.list:
        if step_files:
            print("\nSTEP files:")
            for f in step_files:
                rel = os.path.relpath(f, PROJECT_ROOT)
                size_kb = os.path.getsize(f) / 1024
                print(f"  - {rel} ({size_kb:.0f} KB)")
        else:
            print(f"No STEP files found in {search_dir or PARTS_DIR}")
        return

    # --- Batch mode ---
    if args.batch:
        if not step_files:
            loc = search_dir or PARTS_DIR
            if args.json:
                print(json.dumps({"error": f"No STEP files found in {loc}", "results": []}))
            else:
                print(f"No STEP files found in {loc}")
            return
        cache = load_cache() if not args.no_cache else {}
        run_batch(step_files, args, cache)
        return

    # --- Single file mode ---
    step_file = resolve_step_file(args, step_files)
    if not step_file:
        return

    if args.debug:
        run_debug(step_file)
        return

    run_quick(step_file, args)


def _main_full(args):
    """Handle full-pipeline mode (--full) and its early-exit commands."""
    mods = _import_full_pipeline()
    normalize_args = mods["normalize_args"]
    resolve_input_paths = mods["resolve_input_paths"]
    resolve_db_paths = mods["resolve_db_paths"]
    load_or_init_pipeline_config = mods["load_or_init_pipeline_config"]
    handle_module_listing = mods["handle_module_listing"]
    handle_stage_listing = mods["handle_stage_listing"]
    handle_config_display_and_save = mods["handle_config_display_and_save"]
    handle_cache_commands = mods["handle_cache_commands"]
    parse_force_from_stage = mods["parse_force_from_stage"]
    CacheManager = mods["CacheManager"]

    normalize_args(args)

    # For full mode, -f defaults to a sample file
    file_arg = args.file or "core_one_assembly.step"
    step_file, pdf_file = resolve_input_paths(file_arg, args.pdf)
    pkg_dir = os.path.dirname(__file__)
    db_path, schema_path = resolve_db_paths(pkg_dir)

    if handle_module_listing(args):
        return
    if handle_stage_listing(args):
        return

    config = load_or_init_pipeline_config(args, step_file, pkg_dir)
    if handle_config_display_and_save(args, config):
        return

    cache = CacheManager(args.cache_dir)
    if handle_cache_commands(args, cache):
        return

    force_from = parse_force_from_stage(args.from_stage)
    if args.from_stage and force_from is None:
        return

    if (args.enable or args.disable) and not getattr(args, "production_only", False):
        from manufacturing_pipeline.core.config import print_module_status
        print_module_status(config.modules)

    run_full_pipeline(step_file, pdf_file, db_path, schema_path, args, config, cache, force_from)


if __name__ == "__main__":
    main()
