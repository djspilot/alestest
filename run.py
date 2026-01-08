#!/usr/bin/env python3
"""
Manufacturing Pipeline Runner

Unified entry point for examining STEP files and running the manufacturing analysis pipeline.
"""

import sys
import os
import argparse
import json
import logging
from pathlib import Path

# Add src to python path if needed (although imports should work relatively)
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

try:
    from src.step_processing import (
        load_step_file, detect_holes, detect_shaped_holes, 
        deduplicate_holes
    )
    from src.part_analyzer import PartType, analyze_part_geometry
    from src.aag_analyzer import run_aag_analysis, AAGAnalyzer
    # from src.freecad_unfold import run_unfold_to_step # Removed: calling as subprocess
    from src.report_generator import format_analysis_report
    from src.config import PipelineConfig, INPUT_DIR, OUTPUT_DIR
except ImportError as e:
    # If run from root without installation, try direct imports
    try:
        from src.step_processing import (
            load_step_file, detect_holes, detect_shaped_holes, 
            deduplicate_holes
        )
        from src.part_analyzer import PartType, analyze_part_geometry
        from src.aag_analyzer import analyze_with_aag as run_aag_analysis, AAGAnalyzer
        # from src.freecad_unfold import run_unfold_to_step
        from src.report_generator import format_analysis_report
        from src.config import PipelineConfig, INPUT_DIR, OUTPUT_DIR
    except ImportError:
        print(f"Error importing modules: {e}")
        print("Please ensure you are running from the project root.")
        sys.exit(1)



def run_unfold_to_step(step_file, output_dir, part_name, analysis):
    """
    Wrapper to run the FreeCAD unfolding script.
    """
    script_path = os.path.join(os.path.dirname(__file__), 'src', 'freecad_unfold.py')
    output_dxf = os.path.join(output_dir, f"{part_name}_flat.dxf")
    
    cmd = [script_path, step_file, "-o", output_dxf]
    
    try:
        import subprocess
        # Make sure the script is executable
        try:
            os.chmod(script_path, 0o755)
        except:
            pass
            
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            logging.error(f"FreeCAD Unfold failed: {result.stderr}")
            return {'success': False}

        # Parse output for dimensions
        length = 0
        width = 0
        for line in result.stdout.split('\n'):
            if "Uitslag:" in line:
                # Expected format: "  Uitslag: 123.4 x 56.7 mm"
                try:
                    parts = line.split(':')[1].strip().split('x')
                    if len(parts) >= 2:
                        length = float(parts[0].replace('mm','').strip())
                        width = float(parts[1].replace('mm','').strip())
                except:
                    pass
        
        return {
            'success': True,
            'flat_length': length,
            'flat_width': width,
            'flat_step_path': output_dxf 
        }
    except Exception as e:
        print(f"Unfold execution failed: {e}")
        return {'success': False}


def find_step_files(directory=None):
    """Find all STEP files in the given directory."""
    search_dir = directory or INPUT_DIR
    if not os.path.exists(search_dir):
        # Fallback to current dir if input dir doesn't exist
        search_dir = "."
        
    step_files = []
    import glob
    for pattern in ["*.step", "*.STEP", "*.stp", "*.STP"]:
        step_files.extend(glob.glob(os.path.join(search_dir, pattern)))
        # Also search subdirectories
        step_files.extend(glob.glob(os.path.join(search_dir, "**", pattern), recursive=True))
    return sorted(set(step_files))


def select_step_file(step_files):
    """Interactive file selector."""
    if not step_files:
        return None

    if len(step_files) == 1:
        print(f"Found: {os.path.basename(step_files[0])}")
        return step_files[0]

    print("\nSTEP files found:")
    print("-" * 60)
    for i, f in enumerate(step_files, 1):
        rel_path = os.path.relpath(f, os.getcwd())
        size_kb = os.path.getsize(f) / 1024
        print(f"  [{i:2d}] {rel_path:<45} ({size_kb:.0f} KB)")
    print("-" * 60)

    while True:
        try:
            choice = input(f"Select file [1-{len(step_files)}] or 'q' to quit: ").strip()
            if choice.lower() == 'q':
                return None
            idx = int(choice) - 1
            if 0 <= idx < len(step_files):
                return step_files[idx]
            print(f"Invalid choice. Enter 1-{len(step_files)}")
        except ValueError:
            print("Enter a valid number.")


def analyze_file(step_file, args):
    """Run analysis on a single file."""
    part_name = os.path.splitext(os.path.basename(step_file))[0]
    output_dir = os.path.join(OUTPUT_DIR, part_name)
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(os.path.join(output_dir, "images"), exist_ok=True)

    print(f"\nAnalyzing: {part_name}")
    print(f"Output: {output_dir}")

    # [1/6] Loading
    print("\n[1/6] Loading STEP file...")
    try:
        shape = load_step_file(step_file)
    except Exception as e:
        print(f"Error loading file: {e}")
        return

    # [2/6] AAG Analysis (Optional/Default)
    aag_result = None
    if args.aag or True: # enable by default as it's useful
        print("[2/6] Running AAG Feature Recognition...")
        # Use simple wrapper for now
        # run_aag_analysis expects file path
        try:
             # Run via subprocess wrapper in aag_analyzer
             aag_data = run_aag_analysis(step_file)
             
             class AAGResultStub:
                def __init__(self, data):
                    self.success = data.get('success', False)
                    self.thickness = data.get('thickness', 0.0)
                    self.bend_count = data.get('bend_count', 0)
                    self.hole_count = data.get('hole_count', 0)
                    self.data = data
             
             aag_result = AAGResultStub(aag_data)
             if aag_result.success:
                 print(f"  ✓ AAG Success: {aag_result.bend_count} bends, t={aag_result.thickness:.2f}mm")
             else:
                 print("  ⚠ AAG Analysis failed/skipped")
        except Exception as e:
            print(f"  ⚠ AAG Error: {e}")

    # [3/6] Standard Geometry
    print("[3/6] Analyzing dimensions & geometry...")
    analysis = analyze_part_geometry(shape, part_name)
    
    # [4/6] Classification & Unfold decision
    # Merge AAG results
    if aag_result and aag_result.success:
        if aag_result.thickness > 0 and analysis.thickness == 0:
            analysis.thickness = aag_result.thickness
        if aag_result.bend_count > 0:
            analysis.is_sheet_metal = True
            analysis.bend_count_erp = aag_result.bend_count
            analysis.part_type = PartType.COMPLEX
    
    part_category = "ONBEKEND"
    if analysis.is_profile:
        part_category = "PROFIEL (ingekocht)"
    elif analysis.bend_count_erp > 0 or (aag_result and aag_result.bend_count > 0):
        part_category = "GEBOGEN PLAATWERK"
    elif analysis.is_sheet_metal or (analysis.thickness > 0 and analysis.thickness < 20):
        part_category = "PLAAT (vlak)"
    elif analysis.is_turned:
        part_category = "DRAAISTUK"
        
    print(f"\n--- Classificatie ---")
    print(f"Categorie:   {part_category}")
    print(f"Afmetingen:  {analysis.length:.0f} x {analysis.width:.0f} x {analysis.height:.0f} mm")
    print(f"Dikte:       {analysis.thickness:.2f} mm")
    
    # [5/6] Unfold
    unfold_result = None
    flat_shape = None
    
    should_unfold = (part_category == "GEBOGEN PLAATWERK") and not args.no_unfold
    if should_unfold:
        print("\n[4/6] Unfolding sheet metal...")
        # Need to fix imports in run_unfold_to_step to point to new src location? 
        # Actually run_unfold_to_step generates a script that imports from src.
        # We might need to ensure src is in path for the subprocess.
        unfold_result = run_unfold_to_step(step_file, output_dir, part_name, analysis)
        
        if unfold_result and unfold_result.get('success'):
             print(f"  ✓ Unfold geslaagd: {unfold_result.get('flat_length', 0):.0f} x {unfold_result.get('flat_width', 0):.0f} mm")
             if unfold_result.get('flat_step_path'):
                 try:
                    flat_shape = load_step_file(unfold_result['flat_step_path'])
                 except:
                     pass
        else:
            print("  ⚠ Unfold niet gelukt")
    else:
        print(f"\n[4/6] Unfold: Niet nodig ({part_category})")

    # [6/6] Hole Detection
    print("\n[5/6] Detecting holes...")
    target_shape = flat_shape if flat_shape else shape
    is_flat_mode = (flat_shape is not None)
    
    circular_holes = detect_holes(target_shape, is_flat_pattern=is_flat_mode)
    shaped_holes = detect_shaped_holes(target_shape)
    circular_holes = deduplicate_holes(circular_holes, shaped_holes)
    
    print(f"  Cilindrische gaten: {len(circular_holes)}")
    print(f"  Shaped holes: {len(shaped_holes)}")
    
    # [7/6] Save Results
    print("\n[6/6] Saving results...")
    
    report_path = os.path.join(output_dir, f"{part_name}_analysis.txt")
    with open(report_path, 'w') as f:
        f.write(format_analysis_report(analysis))
        f.write(f"\nCategorie: {part_category}\n")
        f.write(f"Gaten: {len(circular_holes) + len(shaped_holes)}\n")
    
    print(f"  Report saved: {report_path}")


def main():
    parser = argparse.ArgumentParser(description="Manufacturing Pipeline Runner")
    parser.add_argument("-f", "--file", help="STEP file to analyze")
    parser.add_argument("--batch", action="store_true", help="Process all files in input/")
    parser.add_argument("--list", action="store_true", help="List available files")
    parser.add_argument("--no-unfold", action="store_true", help="Skip unfold")
    parser.add_argument("--aag", action="store_true", help="Run AAG analysis")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    
    args = parser.parse_args()

    # Ensure directories
    os.makedirs(INPUT_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    if args.list:
        find_step_files()
        return

    if args.batch:
        files = find_step_files()
        print(f"Found {len(files)} files for batch processing.")
        for f in files:
            analyze_file(f, args)
        return

    step_file = args.file
    if not step_file:
        files = find_step_files()
        step_file = select_step_file(files)
    
    if step_file:
        analyze_file(step_file, args)
    else:
        if not args.list:
            print("No file selected.")

if __name__ == "__main__":
    main()
