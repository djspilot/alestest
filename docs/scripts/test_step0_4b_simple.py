#!/usr/bin/env python3
"""
Simpel STEP 0.4b test - gewoon classify_step0() aanroepen.
Geen dependencies op OCC.Core nodig.
"""
import sys
import os
import cadquery as cq
from manufacturing_pipeline.analysis.classification import classify_step0


def test_step0_4b(step_file: str):
    """Call classify_step0() and show result."""
    
    print(f"\n{'='*80}")
    print(f"STEP 0.4b Analyse (via classify_step0): {os.path.basename(step_file)}")
    print(f"{'='*80}\n")
    
    try:
        assembly = cq.importers.importStep(step_file)
        solid = assembly.val().wrapped
    except Exception as e:
        print(f"❌ STEP load error: {e}")
        return
    
    # Call classify_step0
    try:
        result = classify_step0(solid)
    except Exception as e:
        print(f"❌ classify_step0 error: {e}")
        return
    
    label = result.get("label", "?")
    step = result.get("step", "?")
    method = result.get("method", "?")
    confidence = result.get("confidence", 0)
    reason = result.get("reason", "")
    
    print(f"RESULT:")
    print(f"  Label:      {label}")
    print(f"  Step:       {step}")
    print(f"  Method:     {method}")
    print(f"  Confidence: {confidence:.1%}")
    if reason:
        print(f"  Reason:     {reason[:100]}")
    print()
    
    # Interpret if 0.4b
    if step == "0.4b":
        print(f"STEP 0.4b RESULT:")
        if label == "GEZETTE_PLAAT":
            print(f"  ✓ GEZETTE_PLAAT (bent sheet metal)")
            print(f"    → Open form + dunne wanden + veel bochten")
        elif label == "PROFIEL":
            print(f"  ✓ PROFIEL (solid profile)")
            print(f"    → Open form + massief extrusieprofiel")
    else:
        print(f"NOTE: Stap 0.4b niet bereikt (stopte bij {step})")
    
    print(f"\n{'='*80}\n")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Gebruik: python test_step0_simple.py <step.step>")
        sys.exit(1)
    test_step0_4b(sys.argv[1])
