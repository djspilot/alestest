#!/usr/bin/env python3
"""
Test script to compare detected holes and bends from STEP files
against expected values from Excel.
"""

import os
import sys
import pandas as pd

# Add pipeline to path
SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPTS_DIR)
PIPELINE_DIR = os.path.join(PROJECT_ROOT, "manufacturing_pipeline")
sys.path.insert(0, PIPELINE_DIR)

from src.step_processing import load_step_file, detect_holes, detect_shaped_holes, analyze_sheet_metal
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_SOLID
from OCP.TopoDS import TopoDS

# Paths
EXCEL_FILE = os.path.join(PROJECT_ROOT, "data", "wonr20253515.xlsx")
PARTS_DIR = os.path.join(PROJECT_ROOT, "parts", "fwofferte20253515bestanden")


def analyze_step_file(step_path):
    """Analyze a STEP file and return holes and bend count."""
    try:
        shape = load_step_file(step_path)

        # Detect circular holes
        holes = detect_holes(shape)

        # Detect shaped holes (slots, rectangles)
        shaped_holes = detect_shaped_holes(shape)

        # Total hole count includes both circular and shaped holes
        hole_count = len(holes) + len(shaped_holes)

        # Get max hole diameter (for circular holes only)
        max_diameter = max([h.diameter for h in holes]) if holes else 0

        # Analyze sheet metal for bends
        # Get the first solid
        solid = shape.val().wrapped
        sm_data = analyze_sheet_metal(solid)

        bend_count = sm_data.get("bend_count", 0)
        counter_bend = sm_data.get("counter_bend_count", 0)
        is_sheet_metal = sm_data.get("is_sheet_metal", False)
        is_closed_profile = sm_data.get("is_closed_profile", False)
        thickness = sm_data.get("thickness", 0)

        # Determine form type
        if is_closed_profile:
            form_type = "koker"
        elif bend_count == 0 and is_sheet_metal:
            form_type = "plaat"
        elif bend_count == 1:
            form_type = "hoekprofiel"
        elif bend_count == 2:
            form_type = "U-profiel"
        elif bend_count >= 3:
            form_type = "complex"
        else:
            form_type = "overig"

        return {
            "holes": hole_count,
            "max_diameter": round(max_diameter, 2),
            "bends": bend_count,
            "counter_bends": counter_bend,
            "is_sheet_metal": is_sheet_metal,
            "is_closed_profile": is_closed_profile,
            "form_type": form_type,
            "thickness": round(thickness, 2),
            "error": None
        }
    except Exception as e:
        return {
            "holes": 0,
            "max_diameter": 0,
            "bends": 0,
            "counter_bends": 0,
            "is_sheet_metal": False,
            "is_closed_profile": False,
            "form_type": "error",
            "thickness": 0,
            "error": str(e)
        }


def main():
    # Load Excel data
    print(f"Loading Excel: {EXCEL_FILE}")
    df = pd.read_excel(EXCEL_FILE)

    print(f"\nFound {len(df)} parts in Excel")
    print(f"Parts directory: {PARTS_DIR}\n")

    # Results table
    results = []

    print("="*140)
    print(f"{'ArtikelNr':<25} | {'Vorm':<10} | {'Expected':^24} | {'Detected':^24} | {'Match':^14}")
    print(f"{'':25} | {'':10} | {'Gaten':>6} {'Zet':>6} {'Dia':>8} | {'Gaten':>6} {'Zet':>6} {'Dia':>8} | {'Gaten':^6} {'Zet':^6}")
    print("="*140)

    total_parts = 0
    holes_match = 0
    bends_match = 0

    for idx, row in df.iterrows():
        artikel_nr = row['ArtikelNr']
        expected_holes = int(row['Snijgaten']) if pd.notna(row['Snijgaten']) else 0
        expected_bends = int(row['ZetAantal']) if pd.notna(row['ZetAantal']) else 0
        expected_counter = int(row['Aantaltegenzet']) if pd.notna(row['Aantaltegenzet']) else 0
        expected_dia = float(row['DiaSnijgat']) if pd.notna(row['DiaSnijgat']) else 0
        expected_dikte = float(row['Dikte']) if pd.notna(row['Dikte']) else 0

        # Find STEP file
        step_file = None
        for ext in ['.step', '.STEP', '.stp', '.STP']:
            test_path = os.path.join(PARTS_DIR, f"{artikel_nr}{ext}")
            if os.path.exists(test_path):
                step_file = test_path
                break

        if not step_file:
            print(f"{artikel_nr:<25} | {'FILE NOT FOUND':^30} |")
            continue

        # Analyze
        result = analyze_step_file(step_file)

        if result["error"]:
            print(f"{artikel_nr:<25} | ERROR: {result['error'][:50]}")
            continue

        total_parts += 1

        # Compare
        holes_ok = result["holes"] == expected_holes
        bends_ok = result["bends"] == expected_bends
        dikte_ok = abs(result["thickness"] - expected_dikte) < 0.5 if expected_dikte > 0 else True

        if holes_ok:
            holes_match += 1
        if bends_ok:
            bends_match += 1

        holes_status = "✓" if holes_ok else "✗"
        bends_status = "✓" if bends_ok else "✗"
        dikte_status = "✓" if dikte_ok else "✗"

        form_type = result.get('form_type', 'overig')
        print(f"{artikel_nr:<25} | {form_type:<10} | {expected_holes:>6} {expected_bends:>6} {expected_dia:>8.1f} | "
              f"{result['holes']:>6} {result['bends']:>6} {result['max_diameter']:>8.1f} | "
              f"{holes_status:^6} {bends_status:^6}")

        results.append({
            "artikel_nr": artikel_nr,
            "expected_holes": expected_holes,
            "detected_holes": result["holes"],
            "expected_bends": expected_bends,
            "detected_bends": result["bends"],
            "expected_dikte": expected_dikte,
            "detected_dikte": result["thickness"],
            "holes_match": holes_ok,
            "bends_match": bends_ok,
        })

    # Summary
    print("="*120)
    print(f"\nSUMMARY:")
    print(f"  Total parts analyzed: {total_parts}")
    print(f"  Holes match:  {holes_match}/{total_parts} ({100*holes_match/total_parts:.0f}%)" if total_parts > 0 else "  No parts analyzed")
    print(f"  Bends match:  {bends_match}/{total_parts} ({100*bends_match/total_parts:.0f}%)" if total_parts > 0 else "")

    # Show mismatches
    mismatches = [r for r in results if not r["holes_match"] or not r["bends_match"]]
    if mismatches:
        print(f"\nMISMATCHES ({len(mismatches)}):")
        for m in mismatches:
            issues = []
            if not m["holes_match"]:
                issues.append(f"Holes: expected {m['expected_holes']}, got {m['detected_holes']}")
            if not m["bends_match"]:
                issues.append(f"Bends: expected {m['expected_bends']}, got {m['detected_bends']}")
            print(f"  {m['artikel_nr']}: {', '.join(issues)}")


if __name__ == "__main__":
    main()
