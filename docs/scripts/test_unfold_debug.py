#!/usr/bin/env python
"""Detailed debugging of why FreeCAD unfold fails on solid 10001073529."""

import sys, json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from manufacturing_pipeline.core.xcaf_reader import xcaf_match_solids_to_names
from manufacturing_pipeline.analysis.freecad_unfold import unfold_sheet_metal

STEP_FILE = Path(__file__).parent / "data/stepfile/10001073426_Rev_00-aangepast.stp"

print("=" * 80)
print("DETAILED DEBUG: Why FreeCAD Unfold Fails on 10001073529")
print("=" * 80)

# Load solid
xcaf_result = xcaf_match_solids_to_names(str(STEP_FILE))
solids, names = xcaf_result
solid_0 = solids[0]
name_0 = names[0]

print(f"\nSolid: {name_0}")
print("-" * 80)

# Try unfold with high verbosity
dxf_output = str(STEP_FILE.parent / f"{name_0}_unfold_debug.dxf")
unfold_result = unfold_sheet_metal(
    solid_object=solid_0,
    output_dxf=dxf_output,
    k_factor=0.3,
    max_attempts=5,
    max_bends=None
)

print("\nUNFOLD RESULT:")
print("-" * 80)
for key, value in unfold_result.items():
    if key == 'error_details' and value:
        print(f"\n{key}:")
        for i, err in enumerate(value):
            print(f"  [{i}] {json.dumps(err, indent=4)}")
    elif key != 'flat_shape':  # Skip the Shape object
        print(f"{key}: {value}")

print("\n" + "=" * 80)
if unfold_result.get('error_details'):
    print("ERROR ANALYSIS:")
    print("-" * 80)
    for err in unfold_result['error_details']:
        print(f"\nFace {err['face_idx']}: {err['stage']}")
        print(f"  Error code: {err.get('error_code')} → {err.get('message')}")
        
    # Count errors by stage
    by_stage = {}
    for err in unfold_result['error_details']:
        stage = err['stage']
        code = err.get('error_code')
        key = (stage, code)
        by_stage[key] = by_stage.get(key, 0) + 1
    
    print("\nError frequency:")
    for (stage, code), count in sorted(by_stage.items()):
        print(f"  {stage} (code {code}): {count}x")
