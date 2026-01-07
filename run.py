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

# Import functions and constants from scripts/pipeline_functions.py
from scripts.pipeline_functions import (
    PROJECT_ROOT, PARTS_DIR, OUTPUT_DIR,
    find_step_files, select_step_file, get_output_dir,
    run_analysis, run_aag_analysis, run_debug, generate_simple_pdf, generate_compact_pdf
)

def main():
    parser = argparse.ArgumentParser(
        description="Manufacturing Pipeline - Analyze STEP files with detailed reasoning",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run.py                    Analyze STEP file (interactive)
  python run.py -f mypart.step     Analyze specific file
  python run.py --analyze          Show detailed analysis reasoning
  python run.py --aag              Run AAG topology-based feature recognition
  python run.py --debug            Debug hole detection
  python run.py --no-unfold        Skip automatic unfolding
  python run.py --batch            Process all files in ./parts/
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
    parser.add_argument("--list", action="store_true", help="List available STEP files")

    args = parser.parse_args()

    # Ensure directories exist
    os.makedirs(PARTS_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # List files
    step_files = find_step_files()

    if args.list:
        if step_files:
            print("\nSTEP files:")
            for f in step_files:
                rel = os.path.relpath(f, PROJECT_ROOT)
                size_kb = os.path.getsize(f) / 1024
                print(f"  - {rel} ({size_kb:.0f} KB)")
        else:
            print("No STEP files found in ./parts/")
        return

    # Batch mode
    if args.batch:
        if not step_files:
            print("No STEP files found in ./parts/")
            return

        print(f"\nBatch processing {len(step_files)} files...")
        for i, step_file in enumerate(step_files, 1):
            print(f"\n{'='*60}")
            print(f"[{i}/{len(step_files)}] {os.path.basename(step_file)}")
            print(f"{'='*60}")

            output_dir, part_name = get_output_dir(step_file)

            try:
                analysis, total_holes = run_analysis(step_file, output_dir, args)
                if not args.no_pdf:
                    generate_simple_pdf(step_file, output_dir, part_name, analysis, total_holes)
            except Exception as e:
                print(f"  ✗ Error: {e}")

        print(f"\n{'='*60}")
        print(f"Batch complete. Output in ./output/")
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
                print(f"Gaten (AAG):      {aag_result['hole_count']}")
                print(f"Slots (AAG):      {aag_result['slot_count']}")
                print(f"Zettingen (AAG):  {aag_result['bend_count']}")
                print(f"Dikte (AAG):      {aag_result['thickness']:.2f} mm")
                print(f"Snijlengte:       {aag_result['total_cut_length']:.0f} mm")
                print(f"Pierces:          {aag_result['pierce_count']}")
                print(f"Laser snijtijd:   {aag_result['laser_cut_time']:.1f} sec")
                print(f"Faces/Edges:      {aag_result['face_count']}/{aag_result['edge_count']}")
                print(f"Skin/Thickness:   {aag_result['skin_faces']}/{aag_result['thickness_faces']}")

                # Show hole details if verbose
                if args.verbose and aag_result.get('holes_detail'):
                    print(f"\n--- Gaten Detail (AAG) ---")
                    for h in aag_result['holes_detail'][:10]:
                        q_str = f"Q={h['isoperimetric_quotient']:.2f}" if h.get('isoperimetric_quotient') else ""
                        print(f"  {h['type']}: Ø{h.get('diameter', 0):.1f}mm, P={h['perimeter']:.0f}mm {q_str}")

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
