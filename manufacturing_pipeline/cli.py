#!/usr/bin/env python3
"""
Manufacturing Pipeline - Unified CLI

Modes:
    - Quick mode (default): Fast analysis with simple reports
  - Batch mode (--batch): Process multiple files (parallel or sequential)
"""
import sys
import os
import argparse
import json
from types import SimpleNamespace
from concurrent.futures import ProcessPoolExecutor, as_completed
from multiprocessing import cpu_count
from datetime import datetime

from manufacturing_pipeline.core.paths import PROJECT_ROOT, DATA_DIR, DB_DIR, PARTS_DIR, OUTPUT_DIR
from manufacturing_pipeline.core.config import diagnose_freecad_setup
from manufacturing_pipeline.core.file_utils import find_step_files, select_step_file, get_output_dir, process_single_file
from manufacturing_pipeline.core.runtime_unfold import run_unfold_to_step
from manufacturing_pipeline.core.cache import get_file_hash, load_cache, save_cache, cache_result, CACHE_FILE
from manufacturing_pipeline.core.python_dependencies import (
    auto_install_python_dependencies_enabled,
    ensure_host_python_dependencies,
)

# ---------------------------------------------------------------------------
# Quick-mode single-file runner
# ---------------------------------------------------------------------------

def run_quick(step_file, args):
    """Run quick analysis on a single STEP file (or each solid in an assembly)."""
    import shutil
    from manufacturing_pipeline.analysis.io.step_file_io import extract_solids_to_temp_files
    from manufacturing_pipeline.core.runtime_analysis import run_analysis

    output_dir, part_name = get_output_dir(step_file)

    print(f"\n{'=' * 60}")
    print(f"QUICK ANALYSIS: {part_name}")
    print(f"{'=' * 60}")
    print(f"Input:  {step_file}")
    print(f"Output: {output_dir}/")
    print("Mode:   Quick")

    # Detect assembly (multiple solids) and process each separately
    solids = extract_solids_to_temp_files(step_file)
    if solids:
        print(f"\nAssembly gedetecteerd: {len(solids)} onderdelen")
        print("Elk onderdeel wordt afzonderlijk geanalyseerd.")

        tmp_dir = solids[0]["tmp_dir"]
        errors = []
        try:
            for solid_info in solids:
                solid_name = solid_info["name"]
                solid_step = solid_info["path"]
                safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in solid_name)
                solid_output_dir = os.path.join(output_dir, safe_name or f"part_{solid_info['index'] + 1:03d}")
                os.makedirs(solid_output_dir, exist_ok=True)

                print(f"\n{'─' * 60}")
                print(f"Onderdeel {solid_info['index'] + 1}/{len(solids)}: {solid_name}")

                try:
                    run_analysis(solid_step, solid_output_dir, args)
                except Exception as exc:
                    errors.append((solid_name, exc))
                    print(f"  Fout: {exc}")
                    if args.verbose:
                        import traceback
                        traceback.print_exc()
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

        print(f"\n{'=' * 60}")
        ok = len(solids) - len(errors)
        print(f"COMPLETE — {ok}/{len(solids)} onderdelen verwerkt")
        if errors:
            for name, exc in errors:
                print(f"  FOUT '{name}': {exc}")
        print(f"{'=' * 60}")
        print(f"Output: {output_dir}/")
        if errors:
            sys.exit(1)
        return

    # Single-solid path
    try:
        run_analysis(step_file, output_dir, args)

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


def run_unfold_only(step_file, args):
    """Run only the unfold pipeline through the external FreeCAD runtime."""
    output_dir, part_name = get_output_dir(step_file)
    dxf_output = os.path.join(output_dir, f"{part_name}_flat.dxf")
    flat_step_output = os.path.join(output_dir, f"{part_name}_flat.step")

    print(f"\n{'=' * 60}")
    print(f"UNFOLD ONLY: {part_name}")
    print(f"{'=' * 60}")
    print(f"Input:  {step_file}")
    print(f"Output: {output_dir}/")
    print("Mode:   Unfold only")

    try:
        analysis = SimpleNamespace(bend_count_erp=0, thickness=0.0, is_sheet_metal=True)
        result = run_unfold_to_step(step_file, output_dir, part_name, analysis)
    except Exception as e:
        print(f"\nError: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)

    if args.json:
        bend_count = result.get("bend_count")
        if bend_count is None:
            bend_count = result.get("fold_lines")
        payload = {
            "success": bool(result.get("success")),
            "error": result.get("error"),
            "flat_length": result.get("flat_length"),
            "flat_width": result.get("flat_width"),
            "bend_count": bend_count,
            "bend_angles": result.get("bend_angles", []),
            "bend_radii": result.get("bend_radii", []),
            "bend_lengths": result.get("bend_lengths", []),
            "bend_line_segments": result.get("bend_line_segments", []),
            "bend_line_groups": result.get("bend_line_groups", []),
            "used_face_idx": result.get("used_face_idx"),
            "selected_strategy": result.get("selected_strategy"),
            "skip_sheet_tree_reason": result.get("skip_sheet_tree_reason"),
            "complexity_score": result.get("complexity_score"),
            "geometry_diagnostics": result.get("geometry_diagnostics"),
            "output_dxf": dxf_output if os.path.exists(dxf_output) else None,
            "flat_step_path": flat_step_output if os.path.exists(flat_step_output) else result.get("flat_step_path"),
            "raw_fold_lines": result.get("raw_fold_lines"),
        }
        print(json.dumps(payload, indent=2))
        return

    if result.get("success"):
        bend_count = result.get("bend_count")
        if bend_count is None:
            bend_count = result.get("fold_lines", 0)
        print("\nUNFOLD COMPLETE")
        print(f"Flat pattern: {result.get('flat_length', 0):.1f} x {result.get('flat_width', 0):.1f} mm")
        print(f"Bends:        {bend_count}")
        if result.get("bend_angles"):
            print(f"Angles:       {result.get('bend_angles')}")
        if result.get("bend_radii"):
            print(f"Radii:        {result.get('bend_radii')}")
        if result.get("bend_lengths"):
            print(f"Lengths:      {result.get('bend_lengths')}")
        if result.get("raw_fold_lines") is not None:
            print(f"Raw folds:    {result.get('raw_fold_lines')}")
        groups = result.get("bend_line_groups") or []
        if groups:
            print("Bend groups:")
            for group in groups:
                print(
                    f"  - #{group.get('id')}: axis={group.get('axis')} "
                    f"segments={group.get('segment_indices')} count={group.get('segment_count')}"
                )
        if os.path.exists(dxf_output):
            print(f"DXF:          {dxf_output}")
        if os.path.exists(flat_step_output):
            print(f"Flat STEP:    {flat_step_output}")
        return

    print(f"\nUNFOLD FAILED: {result.get('error') or 'unknown error'}")
    print_freecad_setup_check()
    sys.exit(1)


def print_freecad_setup_check(json_output: bool = False):
    """Print a compact FreeCAD runtime diagnostic."""
    info = diagnose_freecad_setup()
    if json_output:
        print(json.dumps(info, indent=2))
        return

    print("\nFREECAD SETUP CHECK")
    print(f"Path:    {info.get('freecad_path') or '(empty)'}")
    print(f"  valid: {info.get('freecad_path_valid')}")
    print(f"Python:  {info.get('freecad_python') or '(empty)'}")
    print(f"  exists: {info.get('freecad_python_exists')}")
    print(f"Cmd:     {info.get('freecad_cmd') or '(empty)'}")
    print(f"  exists: {info.get('freecad_cmd_exists')}")
    if info.get("candidates"):
        print("Candidates:")
        for candidate in info["candidates"]:
            print(f"  - {candidate}")
    if info.get("recommendations"):
        print("Hints:")
        for recommendation in info["recommendations"]:
            print(f"  - {recommendation}")


# ---------------------------------------------------------------------------
# Batch processing
# ---------------------------------------------------------------------------

def run_batch(step_files, args, cache):
    """Run batch processing over multiple STEP files."""
    try:
        import importlib
        tqdm = importlib.import_module("tqdm").tqdm
        has_tqdm = True
    except ImportError:
        has_tqdm = False

    num_workers = args.parallel
    if num_workers == 0:
        num_workers = max(1, cpu_count() - 1)

    args_dict = {
        "analyze": args.analyze,
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
    Quick (default)   Fast analysis
  Batch (--batch)   Process multiple files (optionally parallel)

Examples - Quick Mode:
  python run.py                              Interactive file selection
  python run.py -f mypart.step               Analyze specific file
    python run.py -f mypart.step -v            Verbose output

Examples - Batch Mode:
  python run.py -f ./folder --batch -p 4     Parallel batch (4 workers)
  python run.py -f ./folder --batch --json   JSON output for ERP

        """,
    )

    # File selection
    parser.add_argument("-f", "--file", help="STEP file or folder path")

    # Quick mode options
    parser.add_argument("--analyze", action="store_true", help="Show detailed analysis with reasoning")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--debug", action="store_true", help="Debug hole detection")
    parser.add_argument("--no-unfold", action="store_true", help="Skip automatic unfolding")
    parser.add_argument("--no-pdf", action="store_true", help="Skip PDF generation")
    parser.add_argument("--unfold-only", action="store_true", help="Run only unfold and bend-line detection")
    parser.add_argument("--check-freecad", action="store_true", help="Print FreeCAD runtime diagnostics and exit")

    # Batch options
    parser.add_argument("--batch", action="store_true", help="Process all STEP files in folder")
    parser.add_argument("--parallel", "-p", type=int, default=1, metavar="N",
                        help="Number of parallel workers (default: 1, use 0 for auto)")
    parser.add_argument("--json", action="store_true", help="Output results as JSON")

    # Cache options
    parser.add_argument("--no-cache", action="store_true", help="Skip cache, force re-analysis")
    parser.add_argument("--clear-cache", action="store_true", help="Clear cache and exit")

    # Utility
    parser.add_argument("--list", action="store_true", help="List available STEP files")

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

    # --- Quick cache clear ---
    if args.clear_cache:
        # CACHE_FILE already imported at module level
        if os.path.exists(CACHE_FILE):
            os.remove(CACHE_FILE)
            print(f"Cache cleared: {CACHE_FILE}")
        else:
            print("No cache file found.")
        return

    if args.check_freecad:
        print_freecad_setup_check(json_output=args.json)
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
        dep_result = ensure_host_python_dependencies(
            install_if_missing=auto_install_python_dependencies_enabled(),
        )
        if not dep_result.get("success"):
            command = dep_result.get("command") or []
            if command:
                print(f"Missing Python dependencies. Install with: {' '.join(command)}")
            else:
                print(dep_result.get("error") or "Missing Python dependencies.")
            return
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

    dep_result = ensure_host_python_dependencies(
        install_if_missing=auto_install_python_dependencies_enabled(),
    )
    if not dep_result.get("success"):
        command = dep_result.get("command") or []
        if command:
            print(f"Missing Python dependencies. Install with: {' '.join(command)}")
        else:
            print(dep_result.get("error") or "Missing Python dependencies.")
        return

    if args.debug:
        from manufacturing_pipeline.core.runtime_reporting import run_debug
        run_debug(step_file)
        return

    if args.unfold_only:
        run_unfold_only(step_file, args)
        return

    run_quick(step_file, args)


if __name__ == "__main__":
    main()
