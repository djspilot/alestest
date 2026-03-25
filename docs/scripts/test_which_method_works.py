#!/usr/bin/env python
"""Test which detection method succeeds: FreeCAD unfold vs cross-section."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from manufacturing_pipeline.core.xcaf_reader import xcaf_match_solids_to_names
from manufacturing_pipeline.analysis.profile_features import extract_bent_plate_cross_section
from manufacturing_pipeline.analysis.freecad_unfold import unfold_sheet_metal

STEP_FILE = Path(__file__).parent / "data/stepfile/10001073426_Rev_00-aangepast.stp"

print("=" * 80)
print("Testing DETECTION METHODS for solid 0: 10001073529_Rev_00")
print("=" * 80)

# Load solid
xcaf_result = xcaf_match_solids_to_names(str(STEP_FILE))
solids, names = xcaf_result
solid_0 = solids[0]
name_0 = names[0]

print(f"\nSolid: {name_0}")
print("-" * 80)

# TEST 1: Cross-section only
print("\n[TEST 1] CROSS-SECTION METHOD ONLY")
print("-" * 80)
cs_result = extract_bent_plate_cross_section(solid_0)
if cs_result:
    print("✓ Cross-section SUCCEEDED:")
    print(f"  - nr_bends: {cs_result.get('nr_bends')}")
    print(f"  - bend_angles: {cs_result.get('bend_angles')}")
    print(f"  - inner_radii: {cs_result.get('inner_radii')}")
    print(f"  - thickness: {cs_result.get('thickness')} mm")
    print(f"  - bend_line_length: {cs_result.get('bend_line_length')} mm")
    print(f"  - flat_width: {cs_result.get('flat_width')} mm")
else:
    print("✗ Cross-section FAILED (returned None)")

# TEST 2: FreeCAD unfold only
print("\n[TEST 2] FREECAD UNFOLD METHOD ONLY")
print("-" * 80)
try:
    dxf_output = str(STEP_FILE.parent / f"{name_0}_test_unfold.dxf")
    unfold_result = unfold_sheet_metal(
        solid_object=solid_0,
        output_dxf=dxf_output,
        k_factor=0.3,
        max_attempts=3,
        max_bends=None
    )
    
    if unfold_result and unfold_result.get('success'):
        print("✓ FreeCAD Unfold SUCCEEDED:")
        print(f"  - nr_bends: {unfold_result.get('nr_bends')}")
        print(f"  - bend_angles: {unfold_result.get('bend_angles')}")
        print(f"  - bend_radii: {unfold_result.get('bend_radii')}")
        print(f"  - thickness: {unfold_result.get('thickness')} mm")
        print(f"  - flat_length: {unfold_result.get('flat_length')} mm")
        print(f"  - flat_width: {unfold_result.get('flat_width')} mm")
        print(f"  - DXF: {unfold_result.get('dxf_output')}")
    else:
        err = unfold_result.get('error', 'Unknown error') if unfold_result else 'No result'
        print(f"✗ FreeCAD Unfold FAILED: {err}")
except Exception as e:
    print(f"✗ FreeCAD Unfold ERROR: {e}")

print("\n" + "=" * 80)
print("VERDICT")
print("=" * 80)
print("\nCross-section works:  " + ("✓ YES" if cs_result else "✗ NO"))
try:
    unfold_ok = unfold_result and unfold_result.get('success')
    print("FreeCAD unfold works: " + ("✓ YES" if unfold_ok else "✗ NO"))
except:
    print("FreeCAD unfold works: ✗ NO")

print("\n→ So the FIX is via:", end=" ")
if cs_result and not unfold_ok:
    print("CROSS-SECTION (unfold was broken)")
elif unfold_ok and not cs_result:
    print("FREECAD UNFOLD (cross-section didn't detect)")
elif cs_result and unfold_ok:
    print("BOTH WORK - cross-section is primary fallback")
else:
    print("NEITHER WORKS (should investigate)")
