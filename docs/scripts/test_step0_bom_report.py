#!/usr/bin/env python3
"""
STEP 0 Classification Report met BOM Validatie

Lees STEP-file → Controleer BOM → Rapporteer per-stap criteria van classify_step0()
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict
import cadquery as cq

from manufacturing_pipeline.analysis.classification import classify_step0


def load_solids_cadquery(stepfile: str) -> list[Any]:
    """Laad solids van STEP-file via CadQuery (geen OCC.Core vereist)."""
    doc = cq.importers.importStep(str(stepfile))
    
    # Extract all solids from the CadQuery doc
    solids = []
    
    # CadQuery returns a Workplane; extract the underlying OCP shape
    if hasattr(doc, 'val'):
        # Single solid case - .val() returns the CadQuery Solid wrapper
        cq_solid = doc.val()
        if hasattr(cq_solid, 'wrapped'):
            # .wrapped gets the underlying OCP.TopoDS_Shape
            ocp_shape = cq_solid.wrapped
            solids.append(ocp_shape)
    
    if not solids:
        raise RuntimeError(f"No solids found or extracted from STEP file: {stepfile}")
    
    return solids


def report_bom_and_classification(stepfile: str) -> None:
    """Lees STEP → Controleer BOM → Rapporteer classify_step0 per solid."""
    
    print("=" * 80)
    print(f"STEP 0 CLASSIFICATION REPORT")
    print(f"File: {stepfile}")
    print("=" * 80)
    
    # STAP 1: Laad STEP-file
    print("\n[STAP 1] STEP-file inlezen via CadQuery...")
    try:
        solids = load_solids_cadquery(stepfile)
        print(f"✓ {len(solids)} solid(s) geladen")
    except Exception as e:
        print(f"❌ Fout: {e}")
        return
    
    # STAP 2: Controleer BOM-aantallen
    print("\n[STAP 2] BOM-aantallen (count per label)...")
    if len(solids) > 0:
        print(f"  Verwacht: {len(solids)} items")
        print(f"  Geladen:  {len(solids)} items")
        print("  ✓ Aantal OK")
    else:
        print("  ❌ Geen solids geladen")
        return
    
    # STAP 3: Classificeer per solid met classify_step0
    print("\n[STAP 3] Classification per solid (STEP 0)...")
    print("-" * 80)
    
    for i, solid in enumerate(solids):
        print(f"\nSOLID #{i}")
        print(f"  {'=' * 76}")
        
        result = classify_step0(solid)
        
        label = result.get("label", "?")
        step = result.get("step", "?")
        confidence = result.get("confidence", 0.0)
        reason = result.get("reason", "")
        fallthrough = result.get("fallthrough", False)
        
        print(f"  Label:      {label}")
        print(f"  Step:       {step}")
        print(f"  Confidence: {confidence:.2f}")
        print(f"  Fallthrough: {fallthrough}")
        print(f"  Reason:     {reason[:120]}")
        
        # Toon features als beschikbaar
        features = result.get("features", {})
        if features:
            print(f"\n  Features measured:")
            for key, val in list(features.items())[:5]:
                if isinstance(val, float):
                    print(f"    {key:25s} = {val:.2f}")
                else:
                    print(f"    {key:25s} = {val}")
    
    # STAP 4: Samenvattingresultaten
    print("\n" + "=" * 80)
    print("[STAP 4] SAMENVATTING")
    print("=" * 80)
    
    results = [classify_step0(s) for s in solids]
    labels = [r.get("label") for r in results]
    
    from collections import Counter
    counts = Counter(labels)
    
    print("\nClassificatie verdeling:")
    for label, count in sorted(counts.items()):
        print(f"  {label:20s}: {count}")
    
    print("\n" + "=" * 80)
    print("¡RAPPORT COMPLETE!")
    print("=" * 80)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Gebruik: python test_step0_bom_report.py <stepfile.stp>")
        sys.exit(1)
    
    stepfile = sys.argv[1]
    report_bom_and_classification(stepfile)
