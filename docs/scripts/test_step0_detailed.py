#!/usr/bin/env python3
"""
Uitgebreid STEP 0 rapport: alle stappen 0.1–0.5 met alle beslissingen.
"""
import sys
import os
import json
import cadquery as cq
from manufacturing_pipeline.analysis.classification import (
    classify_step0,
    _get_bbox_sorted,
    _get_volume,
    _step_0_1_slice_validation,
    _step_0_2_hollow_closed,
    _step_0_3_open_profile,
    _step_0_4a_flat_plate,
    _step_0_4b_constant_thickness_open,
    _step_0_5_solid_profile_fallback,
)


def format_result(result, step_name):
    """Formatteer een Step0Result als leesbare regel."""
    if result is None:
        return f"  {step_name}: ✓ DOORLOOPT (geen match)"
    
    label = result.get("label", "?")
    confidence = result.get("confidence", 0)
    reason = result.get("reason", "")
    method = result.get("method", "")
    fallthrough = result.get("fallthrough", False)
    
    status = "✗ STOP" if not fallthrough else "↓ FALLTHROUGH"
    
    return f"  {step_name}: {status:12} | {label:20} | {method:15} | conf={confidence:5.1%}\n           Reason: {reason}"


def run_detailed_step0_analysis(step_file: str):
    """Voer STEP 0 uit met uitgebreide rapportage per stap."""
    
    print(f"\n{'='*100}")
    print(f"STEP 0 GEDETAILLEERDE ANALYSE: {os.path.basename(step_file)}")
    print(f"{'='*100}\n")
    
    # Load STEP
    try:
        assembly = cq.importers.importStep(step_file)
        solid = assembly.val().wrapped
        print(f"✓ STEP-bestand geladen\n")
    except Exception as e:
        print(f"❌ Fout bij laden STEP-bestand: {e}")
        return
    
    # Get geometry basics
    dims = _get_bbox_sorted(solid)
    volume = _get_volume(solid)
    
    print(f"GEOMETRY BASICS:")
    print(f"  Bounding box (sorted): {dims[0]:.1f} × {dims[1]:.1f} × {dims[2]:.1f} mm")
    print(f"  Volume: {volume:.1f} mm³")
    print(f"  Aspect ratio: {dims[2]/dims[0] if dims[0] > 0 else 0:.2f}")
    print()
    
    # Run stap voor stap
    print(f"{'='*100}")
    print(f"STAP-PER-STAP ANALYSE")
    print(f"{'='*100}\n")
    
    results_log = []
    
    # STEP 0.1
    print(f"[STAP 0.1] SLICE VALIDATION (Poort)")
    print(f"  Controleer: stabiele extrusie-as + minimaal 3 geldige doorsneden\n")
    try:
        result = _step_0_1_slice_validation(solid)
        if result is None:
            print(f"  ✓ POORT GEHAALD — doorloopt naar 0.2")
            results_log.append(("0.1", "PASS", "Slice validation OK"))
        else:
            print(format_result(result, "0.1"))
            results_log.append(("0.1", "STOP", result.get("label", "?")))
    except Exception as e:
        print(f"  ⚠️  Fout: {e}")
        results_log.append(("0.1", "ERROR", str(e)[:50]))
    print()
    
    # STEP 0.2
    print(f"[STAP 0.2] GESLOTEN-HOL (Buis/Koker)")
    print(f"  Controleer: holes==1 + (ronde buis OF rechthoekige koker)\n")
    try:
        result = _step_0_2_hollow_closed(solid)
        if result is None:
            print(f"  ✗ GEEN MATCH — doorloopt naar 0.3")
            results_log.append(("0.2", "NO_MATCH", "Not a hollow closed"))
        else:
            print(format_result(result, "0.2"))
            results_log.append(("0.2", "STOP", result.get("label", "?")))
    except Exception as e:
        print(f"  ⚠️  Fout: {e}")
        results_log.append(("0.2", "ERROR", str(e)[:50]))
    print()
    
    # STEP 0.3
    print(f"[STAP 0.3] OPEN PROFIEL (L/U/I/T)")
    print(f"  Controleer: holes==0 + reentrant_corners>0 + template match (I/U/L/T)\n")
    try:
        result = _step_0_3_open_profile(solid, dims)
        if result is None:
            print(f"  ✗ GEEN MATCH — doorloopt naar 0.4a")
            results_log.append(("0.3", "NO_MATCH", "Not an open profile"))
        else:
            print(format_result(result, "0.3"))
            results_log.append(("0.3", "STOP", result.get("label", "?")))
    except Exception as e:
        print(f"  ⚠️  Fout: {e}")
        results_log.append(("0.3", "ERROR", str(e)[:50]))
    print()
    
    # STEP 0.4a
    print(f"[STAP 0.4a] VLAKKE PLAAT (High Confidence)")
    print(f"  Controleer: holes==0 + near-rectangle + bbox_ratio<=0.30\n")
    try:
        result = _step_0_4a_flat_plate(solid)
        if result is None:
            print(f"  ✗ GEEN HIGH CONFIDENCE MATCH — doorloopt naar 0.4b")
            results_log.append(("0.4a", "NO_MATCH", "Not a flat plate (high conf)"))
        else:
            print(format_result(result, "0.4a"))
            results_log.append(("0.4a", "STOP", result.get("label", "?")))
    except Exception as e:
        print(f"  ⚠️  Fout: {e}")
        results_log.append(("0.4a", "ERROR", str(e)[:50]))
    print()
    
    # STEP 0.4b
    print(f"[STAP 0.4b] CONSTANT-DIKTE OPEN SECTIE (Gezette plaat vs Profiel)")
    print(f"  Controleer: holes==0 + reentrant_corners>0 + dikteConstant==true")
    print(f"  → Als bent_sheet: GEZETTE_PLAAT, anders: PROFIEL\n")
    try:
        result = _step_0_4b_constant_thickness_open(solid, dims)
        if result is None:
            print(f"  ✗ GEEN MATCH — doorloopt naar 0.5")
            results_log.append(("0.4b", "NO_MATCH", "Not constant-thickness open"))
        else:
            print(format_result(result, "0.4b"))
            results_log.append(("0.4b", "STOP", result.get("label", "?")))
    except Exception as e:
        print(f"  ⚠️  Fout: {e}")
        results_log.append(("0.4b", "ERROR", str(e)[:50]))
    print()
    
    # STEP 0.5
    print(f"[STAP 0.5] MASSIEF PROFIEL FALLBACK")
    print(f"  Controleer: length_ratio >= 5.0 + cross_ratio geschikte waarde + volume_ratio\n")
    try:
        result = _step_0_5_solid_profile_fallback(solid, dims, volume)
        if result is None:
            print(f"  ✗ FALLBACK FAALT (shouldn't happen)")
            results_log.append(("0.5", "FALLBACK_FAIL", "Fallback failed"))
        else:
            print(format_result(result, "0.5"))
            results_log.append(("0.5", "STOP", result.get("label", "?")))
    except Exception as e:
        print(f"  ⚠️  Fout: {e}")
        results_log.append(("0.5", "ERROR", str(e)[:50]))
    print()
    
    # SAMENVATTING
    print(f"{'='*100}")
    print(f"EINDRAPPORT")
    print(f"{'='*100}\n")
    
    # Roep ook classify_step0 aan voor vergelijking
    try:
        final_result = classify_step0(solid)
        print(f"FINAL RESULT (via classify_step0):")
        print(f"  Label:       {final_result.get('label', '?')}")
        print(f"  Step:        {final_result.get('step', '?')}")
        print(f"  Method:      {final_result.get('method', '?')}")
        print(f"  Confidence:  {final_result.get('confidence', 0):.1%}")
        print(f"  Fallthrough: {final_result.get('fallthrough', False)}")
        if final_result.get('reason'):
            print(f"  Reason:      {final_result.get('reason')[:100]}")
    except Exception as e:
        print(f"❌ Fout bij classify_step0: {e}")
    
    print(f"\nSTAP-SEQUENTIE LOGBOEK:")
    for step, status, detail in results_log:
        print(f"  {step}: {status:15} {detail}")
    
    print(f"\n{'='*100}\n")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Gebruik: python test_step0_detailed.py <step_bestand.step>")
        sys.exit(1)
    
    step_file = sys.argv[1]
    run_detailed_step0_analysis(step_file)
