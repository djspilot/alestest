#!/usr/bin/env python3
"""
STEP 0.4b Analyse (Fallback versie - zonder OCC.Core dependency)
===

Dit script voert 0.4b analyse uit met beschikbare OCP tools.
"""
import sys
import os
import cadquery as cq
from manufacturing_pipeline.analysis.classification import (
    _get_bbox_sorted,
    _get_volume,
    _is_constant_thickness,
    _is_bent_sheet_geometry,
    _get_top2_face_percent,
    _count_edges_and_large_radius,
)


def analyze_step_0_4b_fallback(step_file: str):
    """Voer STEP 0.4b analyse uit met OCP tools (geen OCC.Core)."""
    
    print(f"\n{'='*100}")
    print(f"STEP 0.4b ANALYSE (Fallback - OCP-only): {os.path.basename(step_file)}")
    print(f"{'='*100}\n")
    
    try:
        assembly = cq.importers.importStep(step_file)
        solid = assembly.val().wrapped
        print(f"✓ STEP-bestand geladen via CadQuery/OCP\n")
    except Exception as e:
        print(f"❌ Fout bij laden STEP-bestand: {e}")
        return
    
    dims = _get_bbox_sorted(solid)
    volume = _get_volume(solid)
    smallest, middle, longest = dims
    
    print(f"GEOMETRY BASICS:")
    print(f"  Bounding box (sorted): {dims[0]:.1f} × {dims[1]:.1f} × {dims[2]:.1f} mm")
    print(f"  Volume: {volume:.1f} mm³")
    print(f"  Aspect: {dims[2]/dims[0] if dims[0] > 0 else 0:.2f}")
    print()
    
    print(f"{'='*100}")
    print(f"STAP 0.4b ROUTE (Geometry-based fallback)")
    print(f"{'='*100}\n")
    
    print(f"NOTA: Volledig 0.4b vereist STEP-sectie analyse (holes, reentrant_corners)")
    print(f"      Deze tools vereisen OCC.Core die niet beschikbaar is.")
    print(f"      We gebruiken alternatief: _is_bent_sheet_geometry (OCP-based)")
    print()
    
    # Criterion 3: dikteConstant
    print(f"[CRITERIUM 3] dikteConstant == true")
    print(f"  (Meting via 3D face-area asymmetrie, niet 2D-sectie)\n")
    
    is_constant = _is_constant_thickness(solid)
    if is_constant:
        print(f"  ✓ PASS: dikteConstant = true")
        print(f"    → Wanddikte is CONSTANT (twee grootste vlakken verschil < 20%)")
    else:
        print(f"  ✗ FAIL: dikteConstant = false")
        print(f"    → Variable dikte (I-beam, UNP type)")
        print(f"    → Zou door 0.4b fallthrough gaan naar 0.5")
        print()
        return
    print()
    
    # Fallback: Determine via _is_bent_sheet_geometry
    print(f"{'='*100}")
    print(f"BENT_SHEET_GEOMETRY CHECK (7 OCP-based criteria)")
    print(f"{'='*100}\n")
    
    bbox_volume = smallest * middle * longest
    volume_ratio = volume / bbox_volume if bbox_volume > 0 else 0.0
    edge_count, large_radius = _count_edges_and_large_radius(solid)
    top2_pct = _get_top2_face_percent(solid)
    aspect_ratio = longest / smallest if smallest > 0 else 0.0
    
    print(f"FEATURES:")
    print(f"  smallest:       {smallest:.1f} mm")
    print(f"  middle:         {middle:.1f} mm")
    print(f"  longest:        {longest:.1f} mm")
    print(f"  volume_ratio:   {volume_ratio:.3f}")
    print(f"  edge_count:     {edge_count}")
    print(f"  large_radius_edges: {large_radius}")
    print(f"  top2_face_pct:  {top2_pct:.1f}%")
    print(f"  aspect_ratio:   {aspect_ratio:.2f}")
    print()
    
    # Call _is_bent_sheet_geometry
    is_bent_sheet = _is_bent_sheet_geometry(solid, volume, dims)
    
    print(f"{'─'*100}")
    print(f"DECISION:")
    print(f"{'─'*100}\n")
    
    if is_bent_sheet:
        print(f"  _is_bent_sheet_geometry() → TRUE")
        print(f"\n  ✓ CLASSIFICATIE: **GEZETTE_PLAAT** (confidence 88%)")
        print(f"\n  Dit onderdeel matcht het bent-sheet profiel:")
        print(f"    - Dunne wandeling (<= 5mm)")
        print(f"    - Voldoende edges voor zettingen (>= 8)")
        print(f"    - Volume-ratio in sheet-range (0.15-0.5)")
        print(f"    - Top2-faces niet dominant (<= 60%)")
        print(f"    - Redelijke elongation (aspect >= 2.0)")
        print(f"    - GEEN tube, GEEN perfect square")
    else:
        print(f"  _is_bent_sheet_geometry() → FALSE")
        print(f"\n  ✓ CLASSIFICATIE: **PROFIEL** (confidence 82%)")
        print(f"\n  Dit onderdeel is een massief extrusieprofiel:")
        print(f"    - Dikkere materiaal (> 5mm)")
        print(f"    - Minder edges dan bent-sheet")
        print(f"    - Hogere volume-ratio")
        print(f"    - Meer dominant top2-faces")
        print(f"    - Of volume_ratio buiten het 0.15-0.5 bereik")
    
    print(f"\n{'='*100}\n")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Gebruik: python test_step0_4b_fallback.py <step_bestand.step>")
        sys.exit(1)
    
    step_file = sys.argv[1]
    analyze_step_0_4b_fallback(step_file)
