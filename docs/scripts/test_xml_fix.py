#!/usr/bin/env python
"""Quick test of the fixes: Geometry suffix stripping and cross-section bent-plate extraction."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from manufacturing_pipeline.core.xcaf_reader import xcaf_match_solids_to_names
from manufacturing_pipeline.reporting.xml_exporter import _strip_step_name_suffix
from manufacturing_pipeline.analysis.profile_features import extract_bent_plate_cross_section

# Configuration
STEP_FILE = Path(__file__).parent / "data/stepfile/10001073426_Rev_00-aangepast.stp"

print("=" * 80)
print("TEST 1: Geometry suffix stripping (_strip_step_name_suffix)")
print("=" * 80)

names_to_test = [
    "10001073529_Rev_00 Geometry",
    "10001073530_Rev_00 Geometry",
    "10001073414_Rev_00",
    "PlateAssembly Geometry",
]
for name in names_to_test:
    stripped = _strip_step_name_suffix(name)
    status = "✓" if " Geometry" not in stripped and "Geometry" not in stripped else "✗"
    print(f"  {status} '{name}' → '{stripped}'")

print("\n" + "=" * 80)
print("TEST 2: Cross-section detection on bent plates")
print("=" * 80)

print(f"\nLoading STEP: {STEP_FILE.name}")
xcaf_result = xcaf_match_solids_to_names(str(STEP_FILE))
if xcaf_result:
    solids, names = xcaf_result
    print(f"✓ Loaded {len(solids)} solids from XCAF")
    
    for i in [0, 2]:
        if i < len(solids):
            solid, name = solids[i], names[i]
            print(f"\n  Solid {i}: {_strip_step_name_suffix(name)}")
            cs = extract_bent_plate_cross_section(solid)
            if cs:
                print(f"    ✓ Cross-section analysis succeeded:")
                print(f"      - thickness: {cs.get('thickness')} mm")
                print(f"      - nr_bends: {cs.get('nr_bends')}")
                print(f"      - bend_angles: {cs.get('bend_angles')}")
                print(f"      - inner_radii: {cs.get('inner_radii')}")
                print(f"      - bend_line_length: {cs.get('bend_line_length')} mm")
                print(f"      - flat_width: {cs.get('flat_width')} mm")
                print(f"      - method: {cs.get('method')}")
            else:
                print(f"    ✗ No bent prismatic geometry detected (expected for this part)")
else:
    print("✗ Failed to load STEP with XCAF")

print("\n" + "=" * 80)
print("All tests complete!")
print("=" * 80)

