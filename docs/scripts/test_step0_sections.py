#!/usr/bin/env python3
"""
Test script om dwarsdoorsneden (cross-sections) van een solid uit te extraheren
voor STEP 0 classificatie-debugging.
"""
import sys
import os
import cadquery as cq
from manufacturing_pipeline.analysis.classification import classify_step0, _get_bbox_sorted

# Import section tools
try:
    from manufacturing_pipeline.analysis.profile_classifier import (
        find_extrusion_axis,
        solid_vertices_np,
        section_plane_positions_from_vertices,
        slice_solid_to_section,
        dominant_section_cluster,
        normalize_section_polygon,
        extract_section_features,
    )
    HAS_SECTION_TOOLS = True
except ImportError as e:
    print(f"⚠️  Section tools niet beschikbaar: {e}")
    HAS_SECTION_TOOLS = False


def extract_and_report_sections(step_file: str):
    """Laad STEP-bestand en rapporteer dwarsdoorsneden."""
    
    print(f"\n{'='*70}")
    print(f"STEP 0 Section Analysis: {os.path.basename(step_file)}")
    print(f"{'='*70}\n")
    
    # Load STEP
    try:
        assembly = cq.importers.importStep(step_file)
        solid = assembly.val().wrapped
    except Exception as e:
        print(f"❌ Fout bij laden STEP-bestand: {e}")
        return
    
    # Get geometry basics
    dims = _get_bbox_sorted(solid)
    print(f"Bounding box (sorted): {dims[0]:.1f} × {dims[1]:.1f} × {dims[2]:.1f} mm")
    
    # Run STEP 0 classification
    print(f"\nStep 0 classificatie...")
    try:
        result = classify_step0(solid)
        print(f"  Label: {result.get('label', '?')}")
        print(f"  Step:  {result.get('step', '?')}")
        print(f"  Method: {result.get('method', '?')}")
        print(f"  Confidence: {result.get('confidence', 0):.2%}")
        print(f"  Fallthrough: {result.get('fallthrough', False)}")
        if result.get('reason'):
            print(f"  Reason: {result.get('reason')}")
    except Exception as e:
        print(f"  ❌ Fout: {e}")
        return
    
    # Extract sections if tools available
    if not HAS_SECTION_TOOLS:
        print(f"\n⚠️  Section-extractie niet beschikbaar (profile_classifier import fout)")
        return
    
    print(f"\n{'='*70}")
    print(f"Section Analysis (STEP 0.1 — Slice Validation)")
    print(f"{'='*70}\n")
    
    # Find extrusion axis
    try:
        axis = find_extrusion_axis(solid)
        if axis is None:
            print(f"❌ Geen stabiele extrusie-as gevonden")
            return
        
        print(f"✓ Extrusion axis gevonden: {axis.direction}")
    except Exception as e:
        print(f"❌ Fout bij find_extrusion_axis: {e}")
        return
    
    # Extract vertices and positions
    try:
        vertices = solid_vertices_np(solid)
        print(f"✓ Vertices: {len(vertices)} punten")
        
        positions = section_plane_positions_from_vertices(
            vertices, axis.direction, (0.20, 0.40, 0.60, 0.80)
        )
        print(f"✓ Section positions: {positions}")
    except Exception as e:
        print(f"❌ Fout bij vertex/position extractie: {e}")
        return
    
    # Extract sections
    print(f"\n{'─'*70}")
    print(f"{'pos':<6} {'area':<10} {'holes':<6} {'corners':<10} {'status':<15}")
    print(f"{'─'*70}")
    
    sections = []
    for s in positions:
        try:
            sec = slice_solid_to_section(
                solid,
                plane_origin=axis.direction * s,
                plane_normal=axis.direction,
                section_position=s,
            )
            
            if sec is None:
                print(f"{s:<6.2f} {'—':<10} {'—':<6} {'—':<10} {'No section':<15}")
                continue
            
            poly = sec.polygon
            if poly.area <= 0:
                print(f"{s:<6.2f} {'—':<10} {'—':<6} {'—':<10} {'Empty area':<15}")
                continue
            
            # Extract features
            try:
                features = extract_section_features(poly)
                holes = features.get("holes", 0)
                corners = features.get("corners", 0)
            except:
                holes = "?"
                corners = "?"
            
            print(f"{s:<6.2f} {poly.area:<10.1f} {str(holes):<6} {str(corners):<10} {'✓ OK':<15}")
            sections.append(sec)
        except Exception as e:
            print(f"{s:<6.2f} — error: {str(e)[:30]}")
    
    # Dominant section clustering
    if sections:
        print(f"\n{'─'*70}")
        try:
            cluster = dominant_section_cluster(sections)
            cluster_ratio = len(cluster) / max(len(sections), 1)
            print(f"✓ Dominant cluster: {len(cluster)}/{len(sections)} sections ({cluster_ratio:.1%})")
            if cluster_ratio >= 0.60:
                print(f"  ✓ POORT GEHAALD (cluster_ratio >= 0.60)")
            else:
                print(f"  ❌ POORT FAALT (cluster_ratio < 0.60)")
        except Exception as e:
            print(f"❌ Fout bij clustering: {e}")
    else:
        print(f"\n❌ Geen geldige sections gevonden")
    
    print(f"\n{'='*70}\n")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Gebruik: python test_step0_sections.py <step_bestand.step>")
        sys.exit(1)
    
    step_file = sys.argv[1]
    extract_and_report_sections(step_file)
