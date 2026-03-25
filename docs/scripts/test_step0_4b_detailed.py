#!/usr/bin/env python3
"""
STEP 0.4b Gedetailleerde Analyse - Gezette plaat vs Profiel
===

Dit script voert een uitgebreide analyse uit van STEP 0.4b criteria:
- holes == 0
- reentrant_corners > 0
- dikteConstant == true
- _is_bent_sheet_geometry (7 sub-criteria)
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
    _HAS_OCP,
)

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
except ImportError:
    HAS_SECTION_TOOLS = False


def analyze_step_0_4b(step_file: str):
    """Voer STEP 0.4b analyse uit met alle criteria."""
    
    print(f"\n{'='*100}")
    print(f"STEP 0.4b GEDETAILLEERDE ANALYSE: {os.path.basename(step_file)}")
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
    print(f"  Aspect ratio (longest/smallest): {dims[2]/dims[0] if dims[0] > 0 else 0:.2f}")
    print()
    
    print(f"{'='*100}")
    print(f"PRIMAIRE CRITERIA CHECK (Prerequisites voor 0.4b)")
    print(f"{'='*100}\n")
    
    # Check 0.4b prerequisites
    criterion_1_pass = False  # holes == 0
    criterion_2_pass = False  # reentrant_corners > 0
    criterion_3_pass = False  # dikteConstant == true
    
    # Criterion 1: holes == 0
    print(f"[CRITERION 1] holes == 0")
    print(f"  Betekenis: 2D-doorsnede bevat GEEN interne lussen (open profiel, niet hol)\n")
    
    if not HAS_SECTION_TOOLS:
        print(f"  ⚠️  Section tools niet beschikbaar, kan niet checken")
        print()
    else:
        try:
            axis = find_extrusion_axis(solid)
            if axis is None:
                print(f"  ⚠️  Geen stabiele extrusieas gevonden, kan niet controleren")
                print()
            else:
                try:
                    vertices = solid_vertices_np(solid)
                    positions = section_plane_positions_from_vertices(
                        vertices, axis.direction, (0.20, 0.40, 0.60, 0.80)
                    )
                    sections = []
                    for s in positions:
                        sec = slice_solid_to_section(
                            solid,
                            plane_origin=axis.direction * s,
                            plane_normal=axis.direction,
                            section_position=s,
                        )
                        if sec is not None and sec.polygon.area > 0:
                            sections.append(sec)
                    
                    if sections:
                        cluster = dominant_section_cluster(sections)
                        if cluster:
                            core_sec = cluster[0]
                            features = extract_section_features(core_sec)
                            holes = features.get("holes", 0)
                            
                            if holes == 0:
                                print(f"  ✓ holes = {holes} → CRITERION 1 PASS")
                                criterion_1_pass = True
                            else:
                                print(f"  ✗ holes = {holes} (verwacht: 0) → CRITERION 1 FAIL")
                                print(f"    (Dit duidt op holle doorsnede; zou in 0.2 verwerkt moeten zijn)")
                        else:
                            print(f"  ⚠️  Geen stabiel section cluster, kan niet controleren")
                    else:
                        print(f"  ⚠️  Geen geldige sections, kan niet controleren")
                except Exception as e:
                    print(f"  ⚠️  Fout bij section extractie: {e}")
                print()
        except Exception as e:
            print(f"  ⚠️  Fout: {e}")
            print()
    
    # Criterion 2: reentrant_corners > 0
    print(f"[CRITERION 2] reentrant_corners > 0")
    print(f"  Betekenis: 2D-doorsnede heeft INWENDIGE (concave) hoeken → open profiel\n")
    
    if not HAS_SECTION_TOOLS:
        print(f"  ⚠️  Section tools niet beschikbaar, kan niet checken")
        print()
    else:
        try:
            axis = find_extrusion_axis(solid)
            if axis is None:
                print(f"  ⚠️  Geen stabiele extrusieas gevonden")
                print()
            else:
                try:
                    vertices = solid_vertices_np(solid)
                    positions = section_plane_positions_from_vertices(
                        vertices, axis.direction, (0.20, 0.40, 0.60, 0.80)
                    )
                    sections = []
                    for s in positions:
                        sec = slice_solid_to_section(
                            solid,
                            plane_origin=axis.direction * s,
                            plane_normal=axis.direction,
                            section_position=s,
                        )
                        if sec is not None and sec.polygon.area > 0:
                            sections.append(sec)
                    
                    if sections:
                        cluster = dominant_section_cluster(sections)
                        if cluster:
                            core_sec = cluster[0]
                            features = extract_section_features(core_sec)
                            reentrant = features.get("reentrant_corners", 0)
                            
                            if reentrant > 0:
                                print(f"  ✓ reentrant_corners = {reentrant} (> 0) → CRITERION 2 PASS")
                                criterion_2_pass = True
                            else:
                                print(f"  ✗ reentrant_corners = {reentrant} (verwacht: > 0) → CRITERION 2 FAIL")
                                print(f"    (Dit duidt op vlakke of massieve vorm, geen open profiel)")
                        else:
                            print(f"  ⚠️  Geen stabiel section cluster")
                    else:
                        print(f"  ⚠️  Geen geldige sections")
                except Exception as e:
                    print(f"  ⚠️  Fout bij section extractie: {e}")
                print()
        except Exception as e:
            print(f"  ⚠️  Fout: {e}")
            print()
    
    # Criterion 3: dikteConstant == true
    print(f"[CRITERION 3] dikteConstant == true")
    print(f"  Betekenis: Wanddikte is ONGEVEER CONSTANT (niet variabel zoals I-beam/UNP)\n")
    
    try:
        is_constant = _is_constant_thickness(solid)
        if is_constant:
            print(f"  ✓ dikteConstant = true → CRITERION 3 PASS")
            criterion_3_pass = True
        else:
            print(f"  ✗ dikteConstant = false → CRITERION 3 FAIL")
            print(f"    (Twee grootste vlakken hebben >20% oppervlak-verschil)")
    except Exception as e:
        print(f"  ⚠️  Fout bij dikteConstant check: {e}")
    print()
    
    # Summary of prerequisites
    print(f"{'─'*100}")
    print(f"PREREQUISITE SUMMARY:")
    all_pass = criterion_1_pass and criterion_2_pass and criterion_3_pass
    
    status_1 = "✓ PASS" if criterion_1_pass else "✗ FAIL" if not HAS_SECTION_TOOLS else "✗ FAIL"
    status_2 = "✓ PASS" if criterion_2_pass else "✗ FAIL" if not HAS_SECTION_TOOLS else "✗ FAIL"
    status_3 = "✓ PASS" if criterion_3_pass else "✗ FAIL"
    
    print(f"  Criterion 1 (holes==0):            {status_1}")
    print(f"  Criterion 2 (reentrant>0):         {status_2}")
    print(f"  Criterion 3 (dikteConstant==true): {status_3}")
    print()
    
    if not all_pass:
        print(f"⚠️  NIET ALLE CRITERIA BEREIKT → FALLTHROUGH naar volgende stap (0.5)")
        print(f"{'='*100}\n")
        return
    
    print(f"✓ ALLE PRIMAIRE CRITERIA BEREIKT → Bepaal GEZETTE_PLAAT vs PROFIEL\n")
    
    # Now check _is_bent_sheet_geometry
    print(f"{'='*100}")
    print(f"SECONDAIRE CRITERIA (_is_bent_sheet_geometry) - 7 Sub-criteria")
    print(f"{'='*100}\n")
    
    smallest, middle, longest = dims
    bbox_volume = smallest * middle * longest
    volume_ratio = volume / bbox_volume if bbox_volume > 0 else 0.0
    edge_count, large_radius_count = _count_edges_and_large_radius(solid)
    top2_pct = _get_top2_face_percent(solid)
    aspect_ratio = longest / smallest if smallest > 0 else 0.0
    cross_ratio = smallest / middle if middle > 0 else 0.0
    
    print(f"EXTRACTED FEATURES:")
    print(f"  Volume: {volume:.1f} mm³")
    print(f"  Bbox volume: {bbox_volume:.1f} mm³")
    print(f"  Volume-ratio: {volume_ratio:.3f}")
    print(f"  Edge count: {edge_count}")
    print(f"  Large radius edges: {large_radius_count}")
    print(f"  Top2 face %: {top2_pct:.1f}%")
    print(f"  Aspect ratio: {aspect_ratio:.2f}")
    print(f"  Cross-ratio (smallest/middle): {cross_ratio:.2f}")
    print()
    
    # Import thresholds
    from manufacturing_pipeline.analysis.classification_variables import (
        BENT_SHEET_THICKNESS_MAX_MM,
        BENT_SHEET_MIN_EDGE_COUNT,
        BENT_SHEET_VOLUME_RATIO_MIN,
        BENT_SHEET_VOLUME_RATIO_MAX,
        BENT_SHEET_TOP2_FACES_MAX_PCT,
        BENT_SHEET_ASPECT_RATIO_MIN,
        PLATE_THICK_MAX_MM,
        PROFILE_LENGTH_RATIO_MIN,
        PROFILE_CROSS_RATIO_MIN,
        PROFILE_CROSS_RATIO_MAX,
        STANDARD_TUBE_VOLUME_RATIO_MAX,
    )
    
    checks = {}
    
    # Check 1: Thin material
    check1 = smallest <= BENT_SHEET_THICKNESS_MAX_MM
    checks["1_thin"] = (check1, f"smallest ({smallest:.1f}) <= {BENT_SHEET_THICKNESS_MAX_MM}")
    
    # Check 2: Enough edges
    check2 = edge_count >= BENT_SHEET_MIN_EDGE_COUNT
    checks["2_edges"] = (check2, f"edge_count ({edge_count}) >= {BENT_SHEET_MIN_EDGE_COUNT}")
    
    # Check 3: Volume ratio
    check3 = BENT_SHEET_VOLUME_RATIO_MIN <= volume_ratio <= BENT_SHEET_VOLUME_RATIO_MAX
    checks["3_volume"] = (check3, f"vol_ratio ({volume_ratio:.3f}) in [{BENT_SHEET_VOLUME_RATIO_MIN}, {BENT_SHEET_VOLUME_RATIO_MAX}]")
    
    # Check 4: Top2 faces
    check4 = top2_pct <= BENT_SHEET_TOP2_FACES_MAX_PCT
    checks["4_top2"] = (check4, f"top2_pct ({top2_pct:.1f}) <= {BENT_SHEET_TOP2_FACES_MAX_PCT}")
    
    # Check 5: Aspect ratio
    check5 = aspect_ratio >= BENT_SHEET_ASPECT_RATIO_MIN
    checks["5_aspect"] = (check5, f"aspect ({aspect_ratio:.2f}) >= {BENT_SHEET_ASPECT_RATIO_MIN}")
    
    # Check 6: Exclusion — tube-like
    check6 = not (smallest >= PLATE_THICK_MAX_MM and (longest / middle) >= PROFILE_LENGTH_RATIO_MIN 
                  and PROFILE_CROSS_RATIO_MIN <= (middle / smallest) <= PROFILE_CROSS_RATIO_MAX 
                  and volume_ratio <= STANDARD_TUBE_VOLUME_RATIO_MAX)
    checks["6_excl_tube"] = (check6, f"NOT a tube-like profile (length_ratio={longest/middle:.2f})")
    
    # Check 7: Exclusion — perfect square
    check7 = not (abs(cross_ratio - 1.0) < 0.05)
    checks["7_excl_square"] = (check7, f"NOT a perfect square/circle (cross_ratio={cross_ratio:.2f})")
    
    print(f"CRITERION CHECKS:")
    print(f"{'─'*100}")
    for key, (passed, detail) in checks.items():
        status = "✓" if passed else "✗"
        print(f"  {status} {detail}")
    print()
    
    # Overall decision
    all_checks_pass = all(passed for passed, _ in checks.values())
    
    print(f"{'─'*100}")
    print(f"DECISION:")
    print()
    
    if all_checks_pass:
        print(f"✓ ALLE 7 CRITERIA PASS → _is_bent_sheet_geometry = TRUE")
        print(f"\n  → CLASSIFICATIE: **GEZETTE_PLAAT** (confidence 88%)")
        print(f"\n  Betekenis: Dit onderdeel is een gebogen/gezet stalen profiel (U-kanaal, tray, etc.)")
        print(f"             Met dunne wanden en veel zettingen/bochten.")
    else:
        failing = [k for k, (p, _) in checks.items() if not p]
        print(f"✗ NIET ALLE 7 CRITERIA PASS → _is_bent_sheet_geometry = FALSE")
        print(f"  Failende criteria: {', '.join(failing)}")
        print(f"\n  → CLASSIFICATIE: **PROFIEL** (confidence 82%)")
        print(f"\n  Betekenis: Dit onderdeel is een massief extrusieprofiel (L-beam, U-beam, etc.)")
        print(f"             Met constante dikke of meer volle structuur.")
    
    print(f"\n{'='*100}\n")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Gebruik: python test_step0_4b_detailed.py <step_bestand.step>")
        sys.exit(1)
    
    step_file = sys.argv[1]
    analyze_step_0_4b(step_file)
