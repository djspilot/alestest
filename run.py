#!/usr/bin/env python3
"""
Manufacturing Pipeline Runner - Unified Entry Point

Modes:
  - Quick mode (default): Fast AAG-based analysis with simple reports
  - Full mode (--full): Complete ISO pipeline with database storage

STEP files are read from ./resources/input/ and output goes to ./resources/output/
"""

import os
import sys
import argparse
import json
from concurrent.futures import ProcessPoolExecutor, as_completed
from multiprocessing import cpu_count
from datetime import datetime

# Import all utilities from manufacturing_pipeline
from manufacturing_pipeline.utils import (
    PROJECT_ROOT, PARTS_DIR, OUTPUT_DIR, CACHE_FILE,
    find_step_files, select_step_file, get_output_dir,
    run_analysis, run_aag_analysis, run_debug, generate_simple_pdf, generate_compact_pdf,
    # Cache functions
    load_cache, save_cache, cache_result, process_single_file
)


# =============================================================================
# Argument Parsing
# =============================================================================

def create_argument_parser():
    """Create and configure the argument parser."""
    parser = argparse.ArgumentParser(
        description="Manufacturing Pipeline - Unified Entry Point",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Modes:
  Quick (default)   Fast AAG-based analysis
  Full (--full)     Complete ISO pipeline with database

Examples:
  python run.py                              Interactive file selection
  python run.py -f mypart.step               Analyze specific file
  python run.py -f ./folder --batch -p 4     Parallel batch (4 workers)
  python run.py -f mypart.step --full        Full ISO pipeline
        """
    )

    # File selection
    parser.add_argument("-f", "--file", help="STEP file or folder path")
    
    # Mode selection
    parser.add_argument("--full", action="store_true", 
                        help="Run full ISO pipeline with database")
    
    # Quick mode options
    parser.add_argument("--analyze", action="store_true", help="Show detailed analysis")
    parser.add_argument("--aag", action="store_true", help="Run AAG analysis")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--debug", action="store_true", help="Debug hole detection")
    parser.add_argument("--no-unfold", action="store_true", help="Skip unfolding")
    parser.add_argument("--no-pdf", action="store_true", help="Skip PDF generation")
    
    # Batch options
    parser.add_argument("--batch", action="store_true", help="Process all STEP files")
    parser.add_argument("--parallel", "-p", type=int, default=1, metavar="N",
                        help="Parallel workers (0=auto)")
    parser.add_argument("--json", action="store_true", help="JSON output")
    
    # Cache options
    parser.add_argument("--no-cache", action="store_true", help="Skip cache")
    parser.add_argument("--clear-cache", action="store_true", help="Clear cache and exit")
    
    # Full mode options
    parser.add_argument("--production-info", action="store_true", help="Show production table")
    parser.add_argument("--material", default="steel_s235", help="Material for cost")
    parser.add_argument("--quantity", type=int, default=1, help="Quantity")
    
    # Utility options
    parser.add_argument("--list", action="store_true", help="List STEP files")

    return parser


# =============================================================================
# Full Pipeline (imports from cli module)
# =============================================================================

def run_full_pipeline(step_file, args):
    """Run the full manufacturing pipeline with ISO standards and database."""
    try:
        from manufacturing_pipeline.step_processing import load_step_file
        from manufacturing_pipeline.database import DatabaseManager
        from manufacturing_pipeline.report_generator import PDFReportGenerator
        from manufacturing_pipeline.cache_manager import PipelineRunner, PipelineStage
    except ImportError as e:
        print(f"Error: Full pipeline requires manufacturing_pipeline modules: {e}")
        return None

    part_name = os.path.splitext(os.path.basename(step_file))[0]
    pipeline_dir = os.path.join(PROJECT_ROOT, "manufacturing_pipeline")
    cache_dir = os.path.join(pipeline_dir, ".pipeline_cache")
    db_path = os.path.join(pipeline_dir, "manufacturing_data.db")
    schema_path = os.path.join(pipeline_dir, "sql", "schema.sql")
    
    runner = PipelineRunner(
        step_file=step_file,
        cache_dir=cache_dir,
        no_cache=args.no_cache,
        verbose=True
    )
    
    print(f"\n{'='*60}")
    print(f"FULL PIPELINE: {part_name}")
    print(f"{'='*60}")
    
    # Run stages
    from manufacturing_pipeline.step_processing import (
        load_step_file, detect_holes, is_turned_part, get_geometric_properties,
        analyze_faces, get_topology_stats, classify_components
    )
    
    print("\n[1/5] Loading STEP file...")
    shape = runner.get_or_run(PipelineStage.LOAD_STEP, load_step_file, step_file)
    if shape is None:
        print("  ✗ Failed to load STEP file")
        return None
    
    print("[2/5] Detecting holes...")
    holes = runner.get_or_run(PipelineStage.DETECT_HOLES, detect_holes, shape)
    print(f"  Found {len(holes)} holes")
    
    print("[3/5] Analyzing geometry...")
    geom_props = runner.get_or_run(PipelineStage.GEOMETRY_ANALYSIS, get_geometric_properties, shape)
    is_turned = is_turned_part(shape)
    
    print("[4/5] Topology analysis...")
    topology_stats = runner.get_or_run(PipelineStage.TOPOLOGY, get_topology_stats, shape)
    
    print("[5/5] Component classification...")
    component_classification = runner.get_or_run(
        PipelineStage.COMPONENT_CLASSIFICATION, classify_components, shape
    )
    
    # Save results
    result = {
        'part_name': part_name,
        'holes': len(holes),
        'is_turned': is_turned,
        'geometry': geom_props,
        'topology': topology_stats,
        'components': component_classification,
    }
    
    json_path = os.path.join(OUTPUT_DIR, part_name, f"{part_name}_full_results.json")
    os.makedirs(os.path.dirname(json_path), exist_ok=True)
    
    with open(json_path, 'w') as f:
        json.dump(result, f, indent=2, default=str)
    
    # Generate PDF
    if not args.no_pdf:
        try:
            report_gen = PDFReportGenerator(json_path)
            pdf_path = os.path.join(OUTPUT_DIR, part_name, f"{part_name}_full_report.pdf")
            report_gen.generate_report(pdf_path)
            print(f"\n  PDF Report: {pdf_path}")
        except Exception as e:
            print(f"  ⚠ PDF generation failed: {e}")
    
    # Save to database
    try:
        db = DatabaseManager(db_path)
        db.initialize_schema(schema_path)
        db.save_analysis_results(part_name, holes, [], is_turned)
    except Exception as e:
        print(f"  ⚠ Database save failed: {e}")
    
    print(f"\n{'='*60}")
    print(f"FULL PIPELINE COMPLETE")
    print(f"  JSON: {json_path}")
    print(f"{'='*60}")
    
    return result


# =============================================================================
# Batch Processing
# =============================================================================

def run_batch_mode(step_files, args, cache):
    """Run batch processing on multiple STEP files."""
    # Try to import tqdm for progress bar
    try:
        from tqdm import tqdm
        has_tqdm = True
    except ImportError:
        has_tqdm = False

    num_workers = args.parallel if args.parallel > 0 else max(1, cpu_count() - 1)
    
    args_dict = {
        'analyze': args.analyze, 'aag': args.aag, 'verbose': args.verbose,
        'debug': args.debug, 'no_unfold': args.no_unfold,
        'no_pdf': args.no_pdf, 'no_cache': args.no_cache,
    }

    results, completed, failed, cached_count = [], 0, 0, 0

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
                futures_iter = tqdm(futures_iter, total=len(step_files), 
                                   desc="Processing", unit="file")
            
            for future in futures_iter:
                result = future.result()
                results.append(result)
                
                if result['success']:
                    completed += 1
                    if result.get('cached'):
                        cached_count += 1
                    if not result.get('cached') and result.get('filepath'):
                        cache_result(result['filepath'], result, cache)
                else:
                    failed += 1
    else:
        if not args.json:
            print(f"\nBatch processing {len(step_files)} files...")
        
        files_iter = tqdm(step_files, desc="Processing") if has_tqdm and not args.json else step_files
        
        for step_file in files_iter:
            result = process_single_file(step_file, args_dict, cache)
            results.append(result)
            
            if result['success']:
                completed += 1
                if result.get('cached'):
                    cached_count += 1
                if not result.get('cached') and result.get('filepath'):
                    cache_result(result['filepath'], result, cache)
            else:
                failed += 1
    
    # Save updated cache
    if not args.no_cache:
        save_cache(cache)
    
    # Output results
    _print_batch_results(results, completed, failed, cached_count, args)


def _print_batch_results(results, completed, failed, cached_count, args):
    """Print batch processing results."""
    if args.json:
        output = {
            "summary": {
                "total": len(results),
                "succeeded": completed,
                "failed": failed,
                "cached": cached_count,
                "timestamp": datetime.now().isoformat()
            },
            "results": sorted(results, key=lambda x: x['file'])
        }
        print(json.dumps(output, indent=2, default=str))
    else:
        print(f"\n{'='*60}")
        cache_msg = f" ({cached_count} from cache)" if cached_count > 0 else ""
        print(f"Batch complete: {completed} succeeded{cache_msg}, {failed} failed")
        print(f"Output in: {OUTPUT_DIR}/")
        
        if results:
            print(f"\n{'='*60}")
            print(f"{'File':<35} {'Category':<20} {'Holes':>6} {'Bends':>6}")
            print(f"{'-'*35} {'-'*20} {'-'*6} {'-'*6}")
            for r in sorted(results, key=lambda x: x['file']):
                if r['success']:
                    print(f"{r['file']:<35} {r['category']:<20} {r['holes']:>6} {r['bends']:>6}")


# =============================================================================
# Single File Quick Analysis
# =============================================================================

def run_quick_analysis(step_file, args):
    """Run quick analysis on a single STEP file."""
    output_dir, part_name = get_output_dir(step_file)

    print(f"\n{'='*60}")
    print(f"QUICK ANALYSIS: {part_name}")
    print(f"{'='*60}")
    print(f"Input:  {step_file}")
    print(f"Output: {output_dir}/")
    print(f"Mode:   Quick (use --full for complete ISO pipeline)")

    try:
        analysis, total_holes = run_analysis(step_file, output_dir, args)

        # Run AAG analysis if requested
        if args.aag:
            _run_and_print_aag(step_file, output_dir, part_name, args)

        if not args.no_pdf:
            print("\nGenerating PDF report...")
            generate_compact_pdf(step_file, output_dir, part_name, analysis, total_holes)

        print(f"\n{'='*60}")
        print(f"COMPLETE")
        print(f"{'='*60}")
        print(f"Output files in: {output_dir}/")
        for f in sorted(os.listdir(output_dir)):
            if os.path.isfile(os.path.join(output_dir, f)):
                print(f"  - {f}")

    except Exception as e:
        print(f"\n✗ Error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


def _run_and_print_aag(step_file, output_dir, part_name, args):
    """Run AAG analysis and print results."""
    print("\n[AAG] Running Attributed Adjacency Graph analysis...")
    aag_result = run_aag_analysis(step_file)

    if aag_result.get('success'):
        print(f"\n--- AAG Analyse Resultaat ---")
        print(f"Type:             {aag_result.get('part_type', 'ONBEKEND')}")
        print(f"Gaten (AAG):      {aag_result['hole_count']}")
        print(f"Zettingen:        {aag_result['bend_count']}")
        print(f"Dikte (AAG):      {aag_result['thickness']:.2f} mm")
        print(f"Snijlengte:       {aag_result['total_cut_length']:.0f} mm")

        # Save AAG results to JSON
        aag_json_path = os.path.join(output_dir, f"{part_name}_aag.json")
        with open(aag_json_path, 'w') as f:
            json.dump(aag_result, f, indent=2)
        print(f"\n  AAG JSON: {aag_json_path}")
    else:
        print(f"  ⚠ AAG analyse gefaald: {aag_result.get('error', 'Unknown error')}")


# =============================================================================
# Main Entry Point
# =============================================================================

def main():
    parser = create_argument_parser()
    args = parser.parse_args()

    # Handle clear-cache
    if args.clear_cache:
        if os.path.exists(CACHE_FILE):
            os.remove(CACHE_FILE)
            print(f"Cache cleared: {CACHE_FILE}")
        else:
            print("No cache file found.")
        return

    # Ensure directories exist
    os.makedirs(PARTS_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Load cache
    cache = load_cache() if not args.no_cache else {}

    # Determine search directory
    search_dir = args.file if args.file and os.path.isdir(args.file) else None
    step_files = find_step_files(search_dir)

    # List files
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

    # Batch mode
    if args.batch:
        if not step_files:
            print(f"No STEP files found in {search_dir or PARTS_DIR}")
            return
        run_batch_mode(step_files, args, cache)
        return

    # Single file mode - resolve file path
    if args.file:
        step_file = _resolve_file_path(args.file, step_files)
        if step_file is None:
            return
    else:
        if not step_files:
            print("No STEP files found. Place files in ./resources/input/")
            return
        step_file = select_step_file(step_files)
        if not step_file:
            print("No file selected.")
            return

    # Debug mode
    if args.debug:
        run_debug(step_file)
        return

    # Full pipeline mode
    if args.full:
        result = run_full_pipeline(step_file, args)
        if result is None:
            sys.exit(1)
        return

    # Quick analysis (default)
    run_quick_analysis(step_file, args)


def _resolve_file_path(file_arg, step_files):
    """Resolve file path from argument."""
    if os.path.exists(file_arg):
        return file_arg
    
    full_path = os.path.join(PARTS_DIR, file_arg)
    if os.path.exists(full_path):
        return full_path
    
    # Try to find in subdirectories
    matches = [f for f in step_files if file_arg in f]
    if len(matches) == 1:
        return matches[0]
    elif len(matches) > 1:
        print(f"Multiple matches for '{file_arg}':")
        for m in matches:
            print(f"  - {os.path.relpath(m, PROJECT_ROOT)}")
        return None
    else:
        print(f"File not found: {file_arg}")
        return None


if __name__ == "__main__":
    main()
