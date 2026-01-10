#!/usr/bin/env python3
"""
Manufacturing Pipeline Runner

Simple entry point to run the manufacturing analysis pipeline.
STEP files are read from ./resources/parts/ and output goes to ./resources/output/
"""

import os
import sys
import argparse
import json
import hashlib
from concurrent.futures import ProcessPoolExecutor, as_completed
from multiprocessing import cpu_count
from datetime import datetime

# Import functions and constants from scripts/pipeline_functions.py
from scripts.pipeline_functions import (
    PROJECT_ROOT, PARTS_DIR, OUTPUT_DIR,
    find_step_files, select_step_file, get_output_dir,
    run_analysis, run_aag_analysis, run_debug, generate_simple_pdf, generate_compact_pdf
)

# Cache file location
CACHE_FILE = os.path.join(PROJECT_ROOT, ".pipeline_cache.json")


def get_file_hash(filepath):
    """Calculate MD5 hash of a file."""
    hasher = hashlib.md5()
    with open(filepath, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            hasher.update(chunk)
    return hasher.hexdigest()


def load_cache():
    """Load cache from disk."""
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}
    return {}


def save_cache(cache):
    """Save cache to disk."""
    with open(CACHE_FILE, 'w') as f:
        json.dump(cache, f, indent=2)


def get_cached_result(filepath, cache):
    """Get cached result if file hasn't changed."""
    file_hash = get_file_hash(filepath)
    cache_key = os.path.abspath(filepath)
    
    if cache_key in cache:
        cached = cache[cache_key]
        if cached.get('hash') == file_hash:
            return cached.get('result')
    return None


def cache_result(filepath, result, cache):
    """Cache a result for a file."""
    file_hash = get_file_hash(filepath)
    cache_key = os.path.abspath(filepath)
    
    cache[cache_key] = {
        'hash': file_hash,
        'result': result,
        'cached_at': datetime.now().isoformat()
    }
    return cache


def process_single_file(step_file, args_dict, cache_data=None):
    """Worker function to process a single STEP file (for parallel processing)."""
    import sys
    import os
    import hashlib
    
    # Re-import in subprocess
    from scripts.pipeline_functions import (
        get_output_dir, run_analysis, generate_simple_pdf
    )
    
    # Convert args dict back to namespace
    class Args:
        def __init__(self, d):
            for k, v in d.items():
                setattr(self, k, v)
    
    args = Args(args_dict)
    part_name = os.path.basename(step_file)
    
    # Check cache if provided and not disabled
    if cache_data is not None and not args_dict.get('no_cache', False):
        file_key = os.path.abspath(step_file)
        if file_key in cache_data:
            # Calculate current hash
            hasher = hashlib.md5()
            with open(step_file, 'rb') as f:
                for chunk in iter(lambda: f.read(65536), b''):
                    hasher.update(chunk)
            current_hash = hasher.hexdigest()
            
            cached = cache_data[file_key]
            if cached.get('hash') == current_hash:
                result = cached.get('result', {}).copy()
                result['cached'] = True
                return result
    
    try:
        output_dir, part_name_clean = get_output_dir(step_file)
        analysis, total_holes = run_analysis(step_file, output_dir, args)
        
        if not args.no_pdf:
            generate_simple_pdf(step_file, output_dir, part_name_clean, analysis, total_holes)
        
        result = {
            'file': part_name,
            'filepath': step_file,
            'success': True,
            'cached': False,
            'category': getattr(analysis, 'part_category', 'UNKNOWN'),
            'part_type': getattr(analysis, 'part_type', None),
            'holes': total_holes,
            'thickness': getattr(analysis, 'thickness', 0),
            'bends': getattr(analysis, 'bend_count_erp', 0),
            'dimensions': {
                'length': getattr(analysis, 'length', 0),
                'width': getattr(analysis, 'width', 0),
                'height': getattr(analysis, 'height', 0)
            }
        }
        # Convert part_type enum to string for JSON serialization
        if result['part_type'] is not None:
            result['part_type'] = str(result['part_type'].value) if hasattr(result['part_type'], 'value') else str(result['part_type'])
        
        return result
    except Exception as e:
        return {
            'file': part_name,
            'filepath': step_file,
            'success': False,
            'cached': False,
            'error': str(e)
        }

def main():
    parser = argparse.ArgumentParser(
        description="Manufacturing Pipeline - Analyze STEP files with detailed reasoning",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run.py                    Analyze STEP file (interactive)
  python run.py -f mypart.step     Analyze specific file
  python run.py -f ./folder --batch            Batch process folder
  python run.py -f ./folder --batch -p 4       Parallel batch (4 workers)
  python run.py -f ./folder --batch -p 0       Parallel batch (auto workers)
  python run.py -f ./folder --batch --json     Output results as JSON
  python run.py -f ./folder --batch --no-cache Force re-analysis (skip cache)
  python run.py --analyze          Show detailed analysis reasoning
  python run.py --aag              Run AAG topology-based feature recognition
  python run.py --debug            Debug hole detection
  python run.py --no-unfold        Skip automatic unfolding
        """
    )

    parser.add_argument("-f", "--file", help="STEP file path or name in ./resources/parts/")
    parser.add_argument("--analyze", action="store_true", help="Show detailed analysis with reasoning")
    parser.add_argument("--aag", action="store_true", help="Run AAG (Attributed Adjacency Graph) analysis")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--debug", action="store_true", help="Debug hole detection")
    parser.add_argument("--no-unfold", action="store_true", help="Skip automatic unfolding")
    parser.add_argument("--no-pdf", action="store_true", help="Skip PDF generation")
    parser.add_argument("--batch", action="store_true", help="Process all STEP files")
    parser.add_argument("--parallel", "-p", type=int, default=1, metavar="N",
                        help="Number of parallel workers for batch processing (default: 1, use 0 for auto)")
    parser.add_argument("--json", action="store_true", help="Output results as JSON (machine-readable)")
    parser.add_argument("--no-cache", action="store_true", help="Skip cache, force re-analysis of all files")
    parser.add_argument("--clear-cache", action="store_true", help="Clear the cache file and exit")
    parser.add_argument("--list", action="store_true", help="List available STEP files")

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

    # Determine search directory: use -f if it's a directory, otherwise default PARTS_DIR
    search_dir = None
    if args.file and os.path.isdir(args.file):
        search_dir = args.file

    # List files
    step_files = find_step_files(search_dir)

    if args.list:
        if step_files:
            print("\nSTEP files:")
            for f in step_files:
                rel = os.path.relpath(f, PROJECT_ROOT)
                size_kb = os.path.getsize(f) / 1024
                print(f"  - {rel} ({size_kb:.0f} KB)")
        else:
            search_loc = search_dir or "./parts/"
            print(f"No STEP files found in {search_loc}")
        return

    # Batch mode
    if args.batch:
        if not step_files:
            search_loc = search_dir or "./parts/"
            if not args.json:
                print(f"No STEP files found in {search_loc}")
            else:
                print(json.dumps({"error": f"No STEP files found in {search_loc}", "results": []}))
            return

        # Try to import tqdm for progress bar
        try:
            from tqdm import tqdm
            has_tqdm = True
        except ImportError:
            has_tqdm = False

        # Determine number of workers
        num_workers = args.parallel
        if num_workers == 0:
            num_workers = max(1, cpu_count() - 1)  # Leave 1 core free
        
        # Convert args to dict for pickling
        args_dict = {
            'analyze': args.analyze,
            'aag': args.aag,
            'verbose': args.verbose,
            'debug': args.debug,
            'no_unfold': args.no_unfold,
            'no_pdf': args.no_pdf,
            'no_cache': args.no_cache,
        }

        results = []
        completed = 0
        failed = 0
        cached_count = 0

        if num_workers > 1:
            # Parallel processing
            if not args.json:
                print(f"\nBatch processing {len(step_files)} files with {num_workers} workers...")
            
            with ProcessPoolExecutor(max_workers=num_workers) as executor:
                # Submit all jobs with cache data
                future_to_file = {
                    executor.submit(process_single_file, sf, args_dict, cache): sf 
                    for sf in step_files
                }
                
                # Use tqdm if available and not JSON mode
                futures_iter = as_completed(future_to_file)
                if has_tqdm and not args.json:
                    futures_iter = tqdm(futures_iter, total=len(step_files), 
                                       desc="Processing", unit="file",
                                       bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]")
                
                # Process results as they complete
                for future in futures_iter:
                    result = future.result()
                    results.append(result)
                    
                    if result['success']:
                        completed += 1
                        if result.get('cached'):
                            cached_count += 1
                        
                        # Update cache with new result
                        if not result.get('cached') and result.get('filepath'):
                            cache = cache_result(result['filepath'], result, cache)
                        
                        if not args.json and not has_tqdm:
                            cache_tag = " (cached)" if result.get('cached') else ""
                            print(f"  ✓ [{completed + failed}/{len(step_files)}] {result['file']} - {result['category']}, {result['holes']} holes{cache_tag}")
                    else:
                        failed += 1
                        if not args.json and not has_tqdm:
                            print(f"  ✗ [{completed + failed}/{len(step_files)}] {result['file']} - Error: {result['error']}")
        else:
            # Sequential processing
            if not args.json:
                print(f"\nBatch processing {len(step_files)} files...")
            
            # Use tqdm if available and not JSON mode
            files_iter = step_files
            if has_tqdm and not args.json:
                files_iter = tqdm(step_files, desc="Processing", unit="file",
                                 bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]")
            
            for step_file in files_iter:
                result = process_single_file(step_file, args_dict, cache)
                results.append(result)
                
                if result['success']:
                    completed += 1
                    if result.get('cached'):
                        cached_count += 1
                    
                    # Update cache with new result
                    if not result.get('cached') and result.get('filepath'):
                        cache = cache_result(result['filepath'], result, cache)
                    
                    if not args.json and not has_tqdm:
                        cache_tag = " (cached)" if result.get('cached') else ""
                        print(f"  ✓ {result['file']} - {result['category']}, {result['holes']} holes{cache_tag}")
                else:
                    failed += 1
                    if not args.json and not has_tqdm:
                        print(f"  ✗ {result['file']} - Error: {result['error']}")
        
        # Save updated cache
        if not args.no_cache:
            save_cache(cache)
        
        # Output results
        if args.json:
            # JSON output mode
            output = {
                "summary": {
                    "total": len(step_files),
                    "succeeded": completed,
                    "failed": failed,
                    "cached": cached_count,
                    "timestamp": datetime.now().isoformat()
                },
                "results": sorted(results, key=lambda x: x['file'])
            }
            print(json.dumps(output, indent=2, default=str))
        else:
            # Human-readable output
            print(f"\n{'='*60}")
            cache_msg = f" ({cached_count} from cache)" if cached_count > 0 else ""
            print(f"Batch complete: {completed} succeeded{cache_msg}, {failed} failed")
            print(f"Output in: {OUTPUT_DIR}/")
            
            # Print summary table
            if results:
                print(f"\n{'='*60}")
                print(f"{'File':<35} {'Category':<20} {'Holes':>6} {'Bends':>6} {'Cache':>6}")
                print(f"{'-'*35} {'-'*20} {'-'*6} {'-'*6} {'-'*6}")
                for r in sorted(results, key=lambda x: x['file']):
                    if r['success']:
                        cache_mark = "✓" if r.get('cached') else ""
                        print(f"{r['file']:<35} {r['category']:<20} {r['holes']:>6} {r['bends']:>6} {cache_mark:>6}")
        return

    # Single file mode
    if args.file:
        if os.path.exists(args.file):
            step_file = args.file
        else:
            step_file = os.path.join(PARTS_DIR, args.file)
            if not os.path.exists(step_file):
                # Try to find in subdirectories
                matches = [f for f in step_files if args.file in f]
                if len(matches) == 1:
                    step_file = matches[0]
                elif len(matches) > 1:
                    print(f"Multiple matches for '{args.file}':")
                    for m in matches:
                        print(f"  - {os.path.relpath(m, PROJECT_ROOT)}")
                    return
                else:
                    print(f"File not found: {args.file}")
                    return
    else:
        if not step_files:
            print("No STEP files found in ./parts/")
            print("Place your STEP files in the ./parts/ folder")
            return

        step_file = select_step_file(step_files)
        if not step_file:
            print("No file selected.")
            return

    # Debug mode
    if args.debug:
        run_debug(step_file)
        return

    # Normal analysis
    output_dir, part_name = get_output_dir(step_file)

    print(f"\n{'='*60}")
    print(f"MANUFACTURING ANALYSIS: {part_name}")
    print(f"{'='*60}")
    print(f"Input:  {step_file}")
    print(f"Output: {output_dir}/")

    try:
        analysis, total_holes = run_analysis(step_file, output_dir, args)

        # Run AAG analysis if requested
        aag_result = None
        if args.aag:
            print("\n[AAG] Running Attributed Adjacency Graph analysis...")
            aag_result = run_aag_analysis(step_file)

            if aag_result.get('success'):
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

                # Show hole details if verbose
                if args.verbose and aag_result.get('holes_detail'):
                    print(f"\n--- Gaten Detail (AAG) ---")
                    for h in aag_result['holes_detail'][:10]:
                        q_str = f"Q={h['isoperimetric_quotient']:.2f}" if h.get('isoperimetric_quotient') else ""
                        diam = h.get('diameter') or 0
                        print(f"  {h['type']}: Ø{diam:.1f}mm, P={h['perimeter']:.0f}mm {q_str}")

                # Show bend details if verbose
                if args.verbose and aag_result.get('bends_detail'):
                    print(f"\n--- Zettingen Detail (AAG) ---")
                    for b in aag_result['bends_detail'][:10]:
                        print(f"  {b['type']}: {b['angle']:.0f}°, R={b['radius']:.1f}mm, L={b['length']:.0f}mm, K={b['k_factor']:.2f}")

                # Save AAG results to JSON
                aag_json_path = os.path.join(output_dir, f"{part_name}_aag.json")
                with open(aag_json_path, 'w') as f:
                    json.dump(aag_result, f, indent=2)
                print(f"\n  AAG JSON: {aag_json_path}")
            else:
                print(f"  ⚠ AAG analyse gefaald: {aag_result.get('error', 'Unknown error')}")

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


if __name__ == "__main__":
    main()
