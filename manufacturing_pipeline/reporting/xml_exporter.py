"""XML export functionality for AutoPOL/Spaceclaim compatibility.

This module exports analysis results to XML format compatible with
ALES ERP system and Spaceclaim/AutoPOL format.
"""

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, Any, Optional, List
from xml.dom import minidom
import os
import sys
import re

# Add manufacturing_pipeline to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Conditional imports (not all may be available)
try:
    from manufacturing_pipeline.analysis.part_analyzer import PartAnalyzer, analyze_part_geometry
    HAS_PART_ANALYZER = True
except ImportError:
    HAS_PART_ANALYZER = False

try:
    from manufacturing_pipeline.analysis.freecad_unfold import unfold_sheet_metal
    HAS_UNFOLD = True
except ImportError:
    HAS_UNFOLD = False

try:
    from manufacturing_pipeline.analysis.sheetmetal_analysis import (
        MATERIAL_BEND_PROPERTIES,
        analyze_sheet_metal_geometry,
    )
    HAS_MATERIAL_PROPS = True
    HAS_SHEETMETAL_ANALYSIS = True
except ImportError:
    HAS_MATERIAL_PROPS = False
    HAS_SHEETMETAL_ANALYSIS = False

try:
    import cadquery as cq
    HAS_CADQUERY = True
except ImportError:
    HAS_CADQUERY = False

try:
    from manufacturing_pipeline.analysis.assembly_analysis import (
        solids_are_equal, 
        get_solid_bounding_box,
        parse_step_assembly_structure,
        parse_step_product_names,
        parse_step_shape_rep_name_counts,
        get_solid_volume
    )
    HAS_ASSEMBLY_GEOM = True
except ImportError:
    HAS_ASSEMBLY_GEOM = False

try:
    from manufacturing_pipeline.reporting.dxf_metrics_extractor import (
        generate_dxf_from_solid,
        extract_metrics_from_dxf
    )
    HAS_DXF_METRICS = True
except ImportError:
    HAS_DXF_METRICS = False

try:
    from manufacturing_pipeline.analysis.profile_features import (
        extract_profile_features,
        extract_bent_plate_cross_section,
    )
    HAS_PROFILE_FEATURES = True
    HAS_BENT_PLATE_CS = True
except ImportError:
    HAS_PROFILE_FEATURES = False
    HAS_BENT_PLATE_CS = False

try:
    from manufacturing_pipeline.analysis.cut_features import extract_cut_features_for_sheet, extract_cut_features_for_profile
    HAS_CUT_FEATURES = True
except ImportError:
    HAS_CUT_FEATURES = False

try:
    from manufacturing_pipeline.core.xcaf_reader import (
        xcaf_get_name_counts,
        xcaf_match_solids_to_names,
    )
    HAS_XCAF_READER = True
except ImportError:
    HAS_XCAF_READER = False


# -----------------------------------------------------------------------------
# Feature schema (structured and extendable)
# -----------------------------------------------------------------------------

FEATURE_SCHEMA_VERSION = "2026-03-06"

# Declared feature fields per functional classification bucket.
# This keeps the current field contract explicit and makes future extensions easy.
CLASSIFICATION_FEATURE_SCHEMA: Dict[str, Dict[str, Any]] = {
    "vlakke_plaat": {
        "part_class": "plaat",
        "required": [
            "Sheet_PartName", "Sheet_Name", "Sheet_Type", "Sheet_Count", "Sheet_Material",
            "Sheet_Thickness", "Sheet_BoxX", "Sheet_BoxY",
            "Sheet_NrHoles", "Sheet_HoleContours", "Sheet_HoleRadii",
            "Sheet_Volume", "Sheet_TopArea", "Sheet_BottomArea",
            "Sheet_BoxArea", "Sheet_AreaNoHoles", "Sheet_TotalArea",
            "Sheet_OuterContour", "Sheet_TotalContour", "Sheet_Weight",
            "Sheet_UnfoldSuccess", "Sheet_FilePathDXF",
        ],
        "optional": [
            "Sheet_NrBends", "Sheet_BendAngles", "Sheet_BendInnerRadii", "Sheet_BendLength",
            "Sheet_HoleTypes", "Sheet_ThreadedHoles", "Sheet_CountersunkHoles", "Sheet_CountersunkAngles",
            "Sheet_FeatExtTotL",
        ],
    },
    "gezette_plaat": {
        "part_class": "plaat",
        "required": [
            "Sheet_PartName", "Sheet_Name", "Sheet_Type", "Sheet_Count", "Sheet_Material",
            "Sheet_Thickness", "Sheet_BoxX", "Sheet_BoxY",
            "Sheet_NrBends", "Sheet_BendAngles", "Sheet_BendInnerRadii", "Sheet_BendLength",
            "Sheet_NrHoles", "Sheet_HoleContours", "Sheet_HoleRadii",
            "Sheet_Volume", "Sheet_TopArea", "Sheet_BottomArea",
            "Sheet_BoxArea", "Sheet_AreaNoHoles", "Sheet_TotalArea",
            "Sheet_OuterContour", "Sheet_TotalContour", "Sheet_Weight",
            "Sheet_UnfoldSuccess", "Sheet_FilePathDXF",
        ],
        "optional": [
            "Sheet_HoleTypes", "Sheet_ThreadedHoles", "Sheet_CountersunkHoles", "Sheet_CountersunkAngles",
            "Sheet_FeatExtTotL",
        ],
    },
    "profiel": {
        "part_class": "profiel",
        "required": [
            "Tube_PartName", "Tube_Name", "Tube_Count",
            "Tube_Type", "Tube_Thickness", "Tube_Width", "Tube_Height",
            "Tube_BoxDeltaX", "Tube_BoxDeltaY", "Tube_BoxDeltaZ",
            "Tube_Material", "Tube_InnerRadius", "Tube_OuterRadius",
            "Tube_Success", "Tube_FilePath", "Tube_Weight",
        ],
        "optional": [
            "Tube_NrHoles", "Tube_HoleContours", "Tube_HoleRadii",
            "Tube_HoleTypes", "Tube_ThreadedHoles",
            "Tube_CountersunkHoles", "Tube_CountersunkAngles",
            "Tube_FeatExtTotL",
        ],
    },
    "anders": {
        "part_class": "anders",
        "required": [
            "Others_PartName", "Others_Name", "Others_Type", "Others_Count",
        ],
        "optional": [],
    },
}


def get_feature_schema_by_classification() -> Dict[str, Dict[str, Any]]:
    """Return a copy-safe view of the feature schema per classification bucket."""
    schema_copy: Dict[str, Dict[str, Any]] = {}
    for bucket, spec in CLASSIFICATION_FEATURE_SCHEMA.items():
        schema_copy[bucket] = {
            "part_class": spec.get("part_class", ""),
            "required": list(spec.get("required", [])),
            "optional": list(spec.get("optional", [])),
        }
    return schema_copy


def _resolve_feature_bucket(part_class: str, calc_result: ET.Element) -> str:
    """Map runtime item to one of: vlakke_plaat, gezette_plaat, profiel, anders."""
    if part_class == "plaat":
        try:
            bends = int(float(calc_result.findtext("Sheet_NrBends", "0") or 0))
        except Exception:
            bends = 0
        return "gezette_plaat" if bends > 0 else "vlakke_plaat"
    if part_class == "profiel":
        return "profiel"
    return "anders"


def _new_feature_coverage_tracker() -> Dict[str, Dict[str, Any]]:
    """Initialize counters for field coverage by classification bucket."""
    tracker: Dict[str, Dict[str, Any]] = {}
    for bucket, spec in CLASSIFICATION_FEATURE_SCHEMA.items():
        tracker[bucket] = {
            "items": 0,
            "required_present": 0,
            "optional_present": 0,
            "required_declared": len(spec.get("required", [])),
            "optional_declared": len(spec.get("optional", [])),
            "missing_required_counts": {},
        }
    return tracker


def _update_feature_coverage(
    tracker: Dict[str, Dict[str, Any]],
    bucket: str,
    calc_result: ET.Element,
) -> List[str]:
    """Update feature coverage counters and return missing required fields for this item."""
    if bucket not in tracker:
        return []

    spec = CLASSIFICATION_FEATURE_SCHEMA.get(bucket, {})
    required = list(spec.get("required", []))
    optional = list(spec.get("optional", []))

    stats = tracker[bucket]
    stats["items"] += 1

    missing_required: List[str] = []

    for field_name in required:
        elem = calc_result.find(field_name)
        if elem is not None and elem.text is not None and str(elem.text).strip() != "":
            stats["required_present"] += 1
        else:
            missing_required.append(field_name)
            missing_counts = stats["missing_required_counts"]
            missing_counts[field_name] = int(missing_counts.get(field_name, 0)) + 1

    for field_name in optional:
        elem = calc_result.find(field_name)
        if elem is not None and elem.text is not None and str(elem.text).strip() != "":
            stats["optional_present"] += 1

    return missing_required


def _print_feature_coverage_summary(tracker: Dict[str, Dict[str, Any]]) -> None:
    """Log concise feature coverage summary by classification bucket."""
    print("\n[INFO] Feature schema coverage summary")
    print(f"  - Schema version: {FEATURE_SCHEMA_VERSION}")

    for bucket in ["vlakke_plaat", "gezette_plaat", "profiel", "anders"]:
        stats = tracker.get(bucket)
        if not stats:
            continue

        items = int(stats.get("items", 0))
        req_decl = int(stats.get("required_declared", 0))
        opt_decl = int(stats.get("optional_declared", 0))
        req_present = int(stats.get("required_present", 0))
        opt_present = int(stats.get("optional_present", 0))

        req_total = items * req_decl
        opt_total = items * opt_decl

        req_pct = (100.0 * req_present / req_total) if req_total > 0 else 100.0
        opt_pct = (100.0 * opt_present / opt_total) if opt_total > 0 else 100.0

        print(
            f"  - {bucket}: items={items}, required={req_present}/{req_total} ({req_pct:.1f}%), "
            f"optional={opt_present}/{opt_total} ({opt_pct:.1f}%)"
        )

        missing_counts = stats.get("missing_required_counts", {})
        if missing_counts:
            top_missing = sorted(missing_counts.items(), key=lambda kv: kv[1], reverse=True)[:3]
            missing_txt = ", ".join(f"{name}({count})" for name, count in top_missing)
            print(f"    missing required (top): {missing_txt}")


def _merge_bends_colinear(bend_angles, bend_radii, bend_lengths):
    """
    Merge adjacent bends with identical angle and radius, but only if they're
    likely part of the same continuous bend (not separated by a hole).
    
    Strategy: Split bends into groups where each group represents one continuous bend line.
    Two groups are separate if there's a "gap" - detected by looking for patterns in the data.
    
    For now: use a simple heuristic - try to find natural breaks.
    If all bends are identical, group them by trying to split into N groups where
    N is minimized but > 1 if we suspect holes.
    
    Better approach: Look for holes in the part geometry and use those as split points.
    
    Args:
        bend_angles: List of bend angles [degrees]
        bend_radii: List of inner bend radii [mm]
        bend_lengths: List of bend lengths [mm]
    
    Returns:
        Tuple of (merged_angles, merged_radii, merged_lengths)
    """
    if not bend_angles or len(bend_angles) <= 1:
        return bend_angles, bend_radii, bend_lengths
    
    # If not all bends are identical, do normal merge
    if not all(a == bend_angles[0] for a in bend_angles):
        # Non-uniform bends - merge only consecutive identical ones
        bends = []
        for i in range(len(bend_angles)):
            bends.append({
                'angle': bend_angles[i],
                'radius': bend_radii[i] if i < len(bend_radii) else None,
                'length': bend_lengths[i] if i < len(bend_lengths) else None,
            })
        
        merged = []
        i = 0
        while i < len(bends):
            current = bends[i].copy()
            merged_count = 0
            
            j = i + 1
            while j < len(bends):
                next_bend = bends[j]
                if (current['angle'] == next_bend['angle'] and 
                    current['radius'] == next_bend['radius']):
                    merged_count += 1
                    j += 1
                else:
                    break
            
            if merged_count > 0:
                print(f"[INFO] Merged {merged_count} bends -> 1 bend "
                      f"(angle={current['angle']}°, radius={current['radius']}mm)")
            
            merged.append(current)
            i = j
        
        merged_angles = [b['angle'] for b in merged]
        merged_radii = [b['radius'] for b in merged if b['radius'] is not None]
        merged_lengths = [b['length'] for b in merged if b['length'] is not None]
        
        if len(merged_angles) != len(bend_angles):
            print(f"[INFO] Bend count: {len(bend_angles)} original -> {len(merged_angles)} merged")
        
        return merged_angles, merged_radii, merged_lengths
    
    # All bends are identical (same angle, radius, length)
    # This is the hole-interrupted case
    # Pattern recognition: When holes interrupt a bend line, FreeCAD splits it into N segments
    # We need to infer how many actual distinct bend lines there are
    
    num_bends = len(bend_angles)
    
    # Heuristic patterns based on common hole configurations:
    # 1 hole: 2 segments (e.g., 2, 3 or 3, 2) -> merge to 2 bends
    # 2 holes: 3 segments (e.g., 2, 1, 2 or 1, 2, 2) -> merge to 3 bends
    # 3 holes: 4 segments -> merge to 4 bends
    
    if num_bends == 5:
        # Most common: 2 holes create 3 segments
        # Heuristic split: try [2,1,2] pattern (most common with symmetrical holes)
        print(f"[INFO] Detected {num_bends} identical consecutive bends")
        print(f"[INFO] Interpreting as 3 segments separated by 2 holes")
        
        merged_angles = [bend_angles[0], bend_angles[2], bend_angles[4]]
        merged_radii = [bend_radii[0], bend_radii[2] if len(bend_radii) > 2 else bend_radii[0], 
                       bend_radii[4] if len(bend_radii) > 4 else bend_radii[0]]
        merged_lengths = [bend_lengths[0], bend_lengths[2] if len(bend_lengths) > 2 else bend_lengths[0],
                         bend_lengths[4] if len(bend_lengths) > 4 else bend_lengths[0]]
        
        print(f"[INFO] Merged to 3 groups (pattern: 2 + 1 + 2)")
        return merged_angles, merged_radii, merged_lengths
    
    elif num_bends == 4:
        # Keep 4 as-is: this frequently represents real counter-bends
        # (e.g. 90, -90, 90, -90) rather than hole-interrupted segments.
        print(f"[INFO] Keeping {num_bends} bends as-is (avoid false 4->2 merge)")
        return bend_angles, bend_radii, bend_lengths
    
    elif num_bends == 3:
        # Could be: 1 hole (2 segments, but odd distribution) or 2 holes (3 equal segments?)
        # Conservative: don't merge, they're likely meant to be separate
        print(f"[INFO] Keeping {num_bends} bends as-is (unclear merge pattern)")
        return bend_angles, bend_radii, bend_lengths
    
    elif num_bends == 6:
        # Could be: 2 holes (3 segments) with 2 bends per segment
        # Or: 3 holes (4 segments) with varying segment sizes
        # Heuristic: assume 3 segments for 2 holes: [2, 2, 2]
        print(f"[INFO] Detected {num_bends} identical consecutive bends")
        print(f"[INFO] Interpreting as 3 segments (2 holes)")
        
        merged_angles = [bend_angles[0], bend_angles[2], bend_angles[4]]
        merged_radii = [bend_radii[0], bend_radii[2] if len(bend_radii) > 2 else bend_radii[0],
                       bend_radii[4] if len(bend_radii) > 4 else bend_radii[0]]
        merged_lengths = [bend_lengths[0], bend_lengths[2] if len(bend_lengths) > 2 else bend_lengths[0],
                         bend_lengths[4] if len(bend_lengths) > 4 else bend_lengths[0]]
        
        print(f"[INFO] Merged to 3 groups (pattern: 2 + 2 + 2)")
        return merged_angles, merged_radii, merged_lengths
    
    # For other cases, just return as-is
    print(f"[INFO] Keeping {num_bends} identical bends (no standard merge pattern)")
    return bend_angles, bend_radii, bend_lengths


def export_to_xml(result: Dict[str, Any], output_path: Path, part_name: Optional[str] = None) -> None:
    """Export analysis result to AutoPOL-compatible XML format.

    Args:
        result: Analysis result dict (from run.py or API)
        output_path: Path where XML file should be written
        part_name: Optional part name (defaults to filename without extension)
    """
    # Extract filename without extension if part_name not provided
    if part_name is None:
        part_name = Path(result.get('file', 'unknown')).stem

    # Create root element
    root = ET.Element('CalculationResults')
    calc = ET.SubElement(root, 'CalculationResult')

    # Part identification
    ET.SubElement(calc, 'Sheet_PartName').text = part_name

    # Basic geometry
    thickness = result.get('thickness', 0)
    ET.SubElement(calc, 'Sheet_Thickness').text = _format_float(thickness)

    # Production counts
    production = result.get('production', {})
    ET.SubElement(calc, 'Sheet_NrBends').text = str(production.get('bends_total', 0))
    ET.SubElement(calc, 'Sheet_NrHoles').text = str(production.get('holes_total', 0))
    ET.SubElement(calc, 'Sheet_HoleTypes').text = ''
    ET.SubElement(calc, 'Sheet_ThreadedHoles').text = '0'
    ET.SubElement(calc, 'Sheet_CountersunkHoles').text = '0'
    ET.SubElement(calc, 'Sheet_CountersunkAngles').text = ''

    # Material (from category or default)
    category = result.get('category', '')
    material = _infer_material(category)
    ET.SubElement(calc, 'Sheet_Material').text = material

    # Part type
    part_type = result.get('part_type', '')
    ET.SubElement(calc, 'Sheet_Type').text = part_type

    # Bounding box dimensions
    dimensions = result.get('dimensions', {})
    ET.SubElement(calc, 'Sheet_BoxX').text = _format_float(dimensions.get('length', 0))
    ET.SubElement(calc, 'Sheet_BoxY').text = _format_float(dimensions.get('width', 0))
    ET.SubElement(calc, 'Sheet_BoxZ').text = _format_float(dimensions.get('height', 0))

    # Flat pattern dimensions (if unfolded)
    flat_dims = result.get('flat_dimensions')
    unfold_success = flat_dims is not None
    if unfold_success:
        ET.SubElement(calc, 'Sheet_FlatX').text = _format_float(flat_dims.get('length', 0))
        ET.SubElement(calc, 'Sheet_FlatY').text = _format_float(flat_dims.get('width', 0))
    else:
        ET.SubElement(calc, 'Sheet_FlatX').text = '0'
        ET.SubElement(calc, 'Sheet_FlatY').text = '0'

    ET.SubElement(calc, 'Sheet_UnfoldSuccess').text = str(unfold_success)

    # AAG details (if available)
    aag_details = result.get('aag_details', {})

    # Bend details
    bend_details = aag_details.get('bend_details', [])
    if bend_details:
        bend_angles = '_'.join(_format_float(b.get('angle', 0)) for b in bend_details)
        bend_radii = '_'.join(_format_float(b.get('radius', 0)) for b in bend_details)
        ET.SubElement(calc, 'Sheet_BendAngles').text = bend_angles
        ET.SubElement(calc, 'Sheet_BendInnerRadii').text = bend_radii
    else:
        ET.SubElement(calc, 'Sheet_BendAngles').text = ''
        ET.SubElement(calc, 'Sheet_BendInnerRadii').text = ''

    # Hole details
    hole_details = aag_details.get('hole_details', [])
    if hole_details:
        # Hole contours (perimeters)
        hole_contours = '_'.join(
            _format_float(h.get('perimeter', 0))
            for h in hole_details
            if h.get('perimeter')
        )

        # Hole radii (diameter / 2)
        hole_radii = '_'.join(
            _format_float(h.get('diameter', 0) / 2)
            for h in hole_details
            if h.get('diameter')
        )

        hole_types_list = []
        countersunk_angles = []
        threaded_count = 0
        countersunk_count = 0
        for hole in hole_details:
            hole_type = str(hole.get('type', 'round') or 'round').strip().lower()
            if not hole_type:
                hole_type = 'round'
            hole_types_list.append(hole_type)

            if hole_type in {'thread', 'threaded', 'tap', 'tapped'}:
                threaded_count += 1

            if 'countersunk' in hole_type:
                countersunk_count += 1
                try:
                    angle_val = float(hole.get('countersink_angle', 0) or 0)
                    if angle_val > 0:
                        countersunk_angles.append(angle_val)
                except Exception:
                    pass

        ET.SubElement(calc, 'Sheet_HoleContours').text = hole_contours or ''
        ET.SubElement(calc, 'Sheet_HoleRadii').text = hole_radii or ''
        calc.find('Sheet_HoleTypes').text = '_'.join(hole_types_list)
        calc.find('Sheet_ThreadedHoles').text = str(threaded_count)
        calc.find('Sheet_CountersunkHoles').text = str(countersunk_count)
        calc.find('Sheet_CountersunkAngles').text = '_'.join(
            _format_float(angle) for angle in countersunk_angles
        )
    else:
        ET.SubElement(calc, 'Sheet_HoleContours').text = ''
        ET.SubElement(calc, 'Sheet_HoleRadii').text = ''

    # Volume and area calculations
    # Note: These would require full geometry analysis
    # For now, we estimate based on bounding box and thickness
    length = dimensions.get('length', 0)
    width = dimensions.get('width', 0)
    height = dimensions.get('height', 0)

    # Simple volume estimation (bounding box)
    volume = length * width * height
    ET.SubElement(calc, 'Sheet_Volume').text = _format_float(volume)

    # Top area (for sheet metal, approximately length × width)
    if category == 'SHEET_METAL':
        top_area = length * width
    else:
        top_area = 0
    ET.SubElement(calc, 'Sheet_TopArea').text = _format_float(top_area)

    # Total surface area (rough estimate for sheet metal)
    if category == 'SHEET_METAL' and thickness > 0:
        # Box area = 2(lw + lh + wh)
        box_area = 2 * (length * width + length * height + width * height)
        total_area = box_area  # Simplified
    else:
        box_area = 0
        total_area = 0

    ET.SubElement(calc, 'Sheet_BoxArea').text = _format_float(box_area)
    ET.SubElement(calc, 'Sheet_TotalArea').text = _format_float(total_area)

    # Cutting information (from AAG)
    cut_length = aag_details.get('total_cut_length', 0)
    ET.SubElement(calc, 'Sheet_OuterContour').text = _format_float(cut_length)
    ET.SubElement(calc, 'Sheet_TotalContour').text = _format_float(cut_length)

    # Weight estimation (requires material density)
    # Default to steel (~7.85 g/cm³)
    weight = _estimate_weight(volume, material)
    ET.SubElement(calc, 'Sheet_Weight').text = _format_float(weight)

    # Create pretty-printed XML
    xml_string = _prettify_xml(root)

    # Write to file
    output_path.write_text(xml_string, encoding='utf-8')


def _format_float(value: float, precision: int = 2) -> str:
    """Format float value for XML output.

    Args:
        value: Float value to format
        precision: Number of decimal places (default: 2)

    Returns:
        Formatted string
    """
    if value is None or value == 0:
        return '0'

    # Round to specified precision
    rounded = round(value, precision)

    # Remove trailing zeros and decimal point if not needed
    formatted = f'{rounded:.{precision}f}'.rstrip('0').rstrip('.')
    return formatted if formatted else '0'


def _estimate_sheet_thickness_for_unfold(
    raw_thickness: float,
    bend_radii: Optional[List[float]] = None,
    unfold_thickness: float = 0.0,
    flat_length: float = 0.0,
    flat_width: float = 0.0,
) -> float:
    """Estimate physical sheet thickness for unfold plausibility checks.

    Raw box-derived thickness can be very wrong for bent parts (e.g. arm height).
    Prefer unfold-reported thickness or bend inner radii, and only trust raw
    thickness when it is plausible relative to unfolded extents.
    """
    candidates: List[float] = []

    flat_min = min(flat_length, flat_width) if flat_length > 0 and flat_width > 0 else 0.0
    plausible_max = flat_min * 0.35 if flat_min > 0 else 0.0

    def _add_candidate(value: float) -> None:
        if value is None:
            return
        try:
            val = float(value)
        except Exception:
            return
        if val <= 0:
            return
        if plausible_max > 0 and val > plausible_max:
            return
        candidates.append(val)

    _add_candidate(unfold_thickness)

    if bend_radii:
        for radius in bend_radii:
            _add_candidate(radius)

    _add_candidate(raw_thickness)

    if not candidates:
        return 0.0

    return min(candidates)


def _is_plausible_unfold_dims(
    flat_length: float,
    flat_width: float,
    raw_thickness: float,
    bend_radii: Optional[List[float]] = None,
    unfold_thickness: float = 0.0,
) -> bool:
    """Return True when unfolded dimensions look physically plausible."""
    if flat_length <= 0 or flat_width <= 0:
        return False

    estimated_thickness = _estimate_sheet_thickness_for_unfold(
        raw_thickness=raw_thickness,
        bend_radii=bend_radii,
        unfold_thickness=unfold_thickness,
        flat_length=flat_length,
        flat_width=flat_width,
    )

    expected_min = max(2.0, estimated_thickness * 3.0) if estimated_thickness > 0 else 2.0
    min_flat = min(flat_length, flat_width)
    return min_flat > expected_min


def _infer_material(category: str) -> str:
    """Infer material type from part category.

    Args:
        category: Part category (e.g., 'SHEET_METAL')

    Returns:
        Material name
    """
    if category == 'SHEET_METAL':
        return 'S235JR'  # Default steel grade
    elif category == 'TURNED_PART':
        return 'C45'  # Default carbon steel for turned parts
    else:
        return 'Unknown'


def _estimate_weight(volume_mm3: float, material: str) -> float:
    """Estimate part weight in grams.

    Args:
        volume_mm3: Volume in cubic millimeters
        material: Material name

    Returns:
        Weight in grams
    """
    # Material densities in g/cm³
    densities = {
        'S235JR': 7.85,
        'S275': 7.85,
        'S355': 7.85,
        'C45': 7.85,
        '42CrMo4': 7.85,
        '304': 8.00,  # Stainless
        '316': 8.00,  # Stainless
        '1050': 2.71,  # Aluminum
        '5083': 2.66,  # Aluminum
        '6061': 2.70,  # Aluminum
        '6082': 2.70,  # Aluminum
        '7075': 2.81,  # Aluminum
        'Unknown': 7.85,  # Default to steel
    }

    density = densities.get(material, 7.85)

    # Convert mm³ to cm³ (divide by 1000)
    volume_cm3 = volume_mm3 / 1000

    # Weight = volume × density
    weight = volume_cm3 * density

    return weight


def _prettify_xml(elem: ET.Element) -> str:
    """Return a pretty-printed XML string.

    Args:
        elem: Root XML element

    Returns:
        Pretty-printed XML string
    """
    # Convert to string
    rough_string = ET.tostring(elem, encoding='utf-8')

    # Parse with minidom for pretty printing
    reparsed = minidom.parseString(rough_string)

    # Return pretty printed string with XML declaration
    return reparsed.toprettyxml(indent='  ', encoding='utf-8').decode('utf-8')


# =============================================================================
# NEW: BOM-TO-XML ORCHESTRATOR (STAP 1 PLAAT PROCESSING)
# =============================================================================

def export_bom_to_xml(
    step_file_path: str,
    bom_list: List[Dict[str, Any]],
    material: str = "steel_s235",
    output_xml_path: Optional[str] = None,
    work_dir: Optional[str] = None,
    reference_xml_path: Optional[str] = None,
    preserve_bom_identity: bool = False,
) -> str:
    """
    Export BOM to XML with full feature extraction (Sheet Metal focused).

    STAP 1: PLAAT Processing
    - For each PLAAT item:
      1. Check if bent (Sheet_NrBends > 0)
      2. If yes: UNFOLD using FreeCAD + material K-factor
      3. Extract flat dimensions
      4. Extract bends (angle, radius, length, bend allowance)
      5. Extract holes (diameter, depth, type)
      6. Extract surfaces (planar, cylindrical)
      7. Generate DXF output path
    - Build complete XML per item

    Args:
        step_file_path: Path to original STEP file
        bom_list: List of BOM items from analyze_assembly_complete()
                 Each item: {part_name, quantity, part_class, ...}
        material: Material code (e.g., 'steel_s235', 'steel_304')
        output_xml_path: Output XML filepath (default: <step_dir>/<step_name>.xml)
        work_dir: Working directory for temp files (default: same as STEP)
        reference_xml_path: Optional existing XML to copy trusted sheet values from
        preserve_bom_identity: Keep BOM names/index mapping unchanged and prefer
                       bom_item['solid_index'] for deterministic mapping

    Returns:
        Path to generated XML file
    """
    if not HAS_CADQUERY:
        raise RuntimeError("CadQuery required for BOM-to-XML export")

    # Setup paths
    step_path = Path(step_file_path).expanduser()
    if not step_path.is_absolute():
        step_path = step_path.resolve()

    if not step_path.exists():
        raise FileNotFoundError(f"STEP file not found: {step_file_path}")

    source_output_dir = step_path.parent

    # Keep an optional work directory for temporary artifacts only.
    work_dir_path = Path(work_dir).expanduser().resolve() if work_dir else source_output_dir
    work_dir_path.mkdir(parents=True, exist_ok=True)

    if output_xml_path is None:
        output_path = source_output_dir / f"{step_path.stem}.xml"
    else:
        requested_output_path = Path(output_xml_path).expanduser()
        if requested_output_path.is_absolute():
            output_path = requested_output_path
        else:
            # Relative output paths are resolved against the STEP directory.
            output_path = (source_output_dir / requested_output_path).resolve()

    output_path.parent.mkdir(parents=True, exist_ok=True)

    # ========================================================================== 
    # NAMING STRATEGY (same logic as export_classification_excel.py)
    # ==========================================================================
    # 1. Try STEP assembly structure names
    # 2. Cluster-based matching on (part_class, quantity) to avoid
    #    index-only swaps between sheet/profile names
    # 3. Fallback to sequential product names
    # 4. Generate: {base_name}-p1, {base_name}-p2, etc.
    
    base_name = step_path.stem
    if preserve_bom_identity:
        print("  [INFO] preserve_bom_identity=True: naming strategy skipped, BOM names/indexes preserved")
    else:
        # Primary naming source: XCAF product tree counts.
        xcaf_name_counts = None
        if HAS_XCAF_READER:
            try:
                xcaf_name_counts = xcaf_get_name_counts(str(step_path))
                if xcaf_name_counts:
                    print(
                        "  [XCAF] Name source active: "
                        f"{len(xcaf_name_counts)} unique names"
                    )
            except Exception:
                xcaf_name_counts = None

        step_parts = xcaf_name_counts
        if not step_parts and HAS_ASSEMBLY_GEOM:
            step_parts = parse_step_assembly_structure(str(step_path))
        step_product_names = None

        if not step_parts and HAS_ASSEMBLY_GEOM:
            step_product_names = parse_step_product_names(str(step_path))

        used_step_parts = set()
        step_parts_list = list(step_parts.keys()) if step_parts else []
        step_parts_seq_idx = 0
        generated_idx = 1
        product_name_idx = 0
        used_product_names = set()

        # Cluster BOM items by (classification, quantity) to reduce cross-type swaps.
        bom_clusters = {}
        for bom_idx, bom_item in enumerate(bom_list):
            cluster_key = (
                str(bom_item.get('part_class', 'unknown') or 'unknown').strip().lower(),
                int(bom_item.get('quantity', 1) or 1),
            )
            if cluster_key not in bom_clusters:
                bom_clusters[cluster_key] = []
            bom_clusters[cluster_key].append(bom_idx)

        # Create cluster -> candidate names map using quantity-based matching
        # with alphabetical sorting for determinism when multiple candidates exist.
        name_by_cluster = {}
        if step_product_names:
            shape_rep_counts = parse_step_shape_rep_name_counts(str(step_path)) if HAS_ASSEMBLY_GEOM else {}

            # For each cluster, find names with matching quantity
            for cluster_key in sorted(bom_clusters.keys()):
                part_class, quantity = cluster_key
                cluster_size = len(bom_clusters[cluster_key])

                # Find all names with this quantity from SHAPE_REP counts
                matching_names = [
                    name for name, count in (shape_rep_counts or {}).items()
                    if count == quantity and name not in used_product_names
                ]

                # Sort alphabetically for deterministic assignment
                matching_names.sort()

                # Take as many as we need for this cluster
                names_for_cluster = matching_names[:cluster_size]

                # Mark as used
                for name in names_for_cluster:
                    used_product_names.add(name)

                if names_for_cluster:
                    name_by_cluster[cluster_key] = names_for_cluster

        # Apply naming to each BOM item
        for idx, bom_item in enumerate(bom_list):
            bom_part_name = bom_item.get('part_name', '')
            new_part_name = None

            name_lower = str(bom_part_name or '').strip().lower()
            is_generic_bom_name = (
                not bom_part_name
                or name_lower.startswith('part_')
                or name_lower.startswith('plaatdeel')
                or name_lower.startswith('profieldeel')
                or name_lower.startswith('verspaamd deel')
                or name_lower.startswith('vaste vorm')
            )

            # Prefer existing meaningful BOM name (critical for reference XML name matching)
            # Keep generated fallback only for generic/empty names.
            if bom_part_name and not is_generic_bom_name:
                new_part_name = bom_part_name

            # If BOM names are generic, use STEP assembly structure order as authoritative mapping
            if not new_part_name and step_parts_list and step_parts_seq_idx < len(step_parts_list):
                candidate_name = step_parts_list[step_parts_seq_idx]
                step_parts_seq_idx += 1
                if candidate_name and candidate_name not in used_step_parts:
                    new_part_name = candidate_name
                    used_step_parts.add(candidate_name)

            if not new_part_name and step_parts and bom_part_name in step_parts and bom_part_name not in used_step_parts:
                # Use STEP assembly structure name
                new_part_name = bom_part_name
                used_step_parts.add(bom_part_name)

            if not new_part_name:
                cluster_key = (
                    str(bom_item.get('part_class', 'unknown') or 'unknown').strip().lower(),
                    int(bom_item.get('quantity', 1) or 1),
                )
                cluster_names = name_by_cluster.get(cluster_key, [])
                cluster_items = bom_clusters.get(cluster_key, [])
                if cluster_names and idx in cluster_items:
                    cluster_pos = cluster_items.index(idx)
                    if cluster_pos < len(cluster_names):
                        candidate_product_name = cluster_names[cluster_pos]
                        if candidate_product_name and candidate_product_name.upper() != 'UNKNOWN':
                            new_part_name = candidate_product_name

            if not new_part_name and step_product_names:
                # Sequential fallback for leftovers not matched by cluster.
                while product_name_idx < len(step_product_names):
                    candidate_product_name = step_product_names[product_name_idx]
                    product_name_idx += 1
                    if (
                        candidate_product_name
                        and candidate_product_name.upper() != 'UNKNOWN'
                        and candidate_product_name not in used_product_names
                    ):
                        new_part_name = candidate_product_name
                        used_product_names.add(candidate_product_name)
                        break

            if not new_part_name:
                # Generate name: "Silo 2-p1", "Silo 2-p2", etc.
                new_part_name = f"{base_name}-p{generated_idx}"

                generated_idx += 1

            # Update BOM item with proper name
            bom_item['part_name'] = new_part_name

        print(f"  [INFO] Applied naming strategy: {len([b for b in bom_list if base_name in b.get('part_name', '')])}/{len(bom_list)} items use generated names")

    # Load STEP once
    print(f"\n[XML Export] Loading STEP: {step_path.name}")
    try:
        doc = cq.importers.importStep(str(step_path))
    except Exception as e:
        print(f"  [ERR] Error loading STEP: {e}")
        raise

    # Create root XML element
    root = ET.Element('DocumentElement')

    # Optional: load trusted values from existing XML (user-provided baseline)
    ref_by_name, ref_by_seq = _load_reference_sheet_values(reference_xml_path)

    # Get K-factor for this material
    k_factor = _get_k_factor(material)
    print(f"  [INFO] K-factor: {k_factor} (material: {material})")

    # Build representative solids and a name-aware mapping for robust BOM matching.
    representative_solids = _build_representative_solids(doc)

    # If available, align representative solids with XCAF extraction order.
    # This keeps solid indices stable with XCAF-derived part names.
    if HAS_XCAF_READER:
        try:
            xcaf_result = xcaf_match_solids_to_names(str(step_path))
            if xcaf_result is not None:
                xcaf_solids, _xcaf_names = xcaf_result
                if xcaf_solids and len(xcaf_solids) == len(representative_solids):
                    representative_solids = xcaf_solids
                    print(
                        "  [XCAF] Using XCAF solid order for XML mapping: "
                        f"{len(representative_solids)} solids"
                    )
        except Exception:
            pass

    part_name_to_solid_indices = _build_part_name_to_solid_indices(
        str(step_path),
        representative_solids,
    )
    solid_index_to_name = _invert_part_name_to_solid_indices(part_name_to_solid_indices)
    solid_volumes_mm3 = _compute_solid_volumes_mm3(representative_solids)
    used_solid_indices = set()

    if part_name_to_solid_indices:
        print(
            "  [INFO] Name-aware solid mapping ready: "
            f"{len(part_name_to_solid_indices)} names, {len(representative_solids)} solids"
        )
    else:
        print(
            "  [WARN] Name-aware solid mapping unavailable; "
            f"falling back to index order for {len(representative_solids)} solids"
        )

    # Process each BOM item
    print(f"\n[XML Export] Processing {len(bom_list)} BOM items...")
    plaat_seq_index = 0  # Track which sheet item in reference sequence we're at
    processed_count = 0  # Track successfully processed items
    class_counts = {'plaat': 0, 'profiel': 0, 'anders': 0}  # Track by class (line-based)
    unclassified_count = 0  # Items with missing/unknown part_class
    bom_piece_count = 0  # Sum of quantities (stuk-count), separate from line count
    feature_coverage = _new_feature_coverage_tracker()
    
    for idx, bom_item in enumerate(bom_list, 1):
        print(f"\n  [{idx}/{len(bom_list)}] {bom_item.get('part_name', 'Unknown')}")

        raw_part_class = str(bom_item.get('part_class', '') or '').strip().lower()
        if raw_part_class in class_counts:
            part_class = raw_part_class
        else:
            part_class = 'anders'
            unclassified_count += 1

        try:
            bom_piece_count += int(bom_item.get('quantity', 1) or 1)
        except Exception:
            bom_piece_count += 1

        part_solid = None
        normalized_bom_name = _normalize_part_name(str(bom_item.get('part_name', '') or ''))
        selected_solid_idx = None
        if part_class in ('plaat', 'profiel'):
            if preserve_bom_identity:
                raw_idx = bom_item.get('solid_index', None)
                forced_idx = None
                try:
                    if raw_idx is not None:
                        forced_idx = int(raw_idx)
                except Exception:
                    forced_idx = None

                if forced_idx is not None and 0 <= forced_idx < len(representative_solids):
                    selected_solid_idx = forced_idx
                    if forced_idx in used_solid_indices:
                        print(
                            f"    [WARN] preserve_bom_identity: solid_index {forced_idx} already used; "
                            "reusing as requested"
                        )
                    else:
                        used_solid_indices.add(forced_idx)
                    part_solid = representative_solids[forced_idx]
                else:
                    print(
                        "    [WARN] preserve_bom_identity active but solid_index missing/invalid; "
                        "falling back to name/volume mapping"
                    )

            if selected_solid_idx is None:
                selected_solid_idx = _select_solid_index_for_bom_item(
                    bom_item=bom_item,
                    normalized_bom_name=normalized_bom_name,
                    preferred_idx=idx - 1,
                    total_solids=len(representative_solids),
                    part_name_to_solid_indices=part_name_to_solid_indices,
                    solid_volumes_mm3=solid_volumes_mm3,
                    used_indices=used_solid_indices,
                    default_material=material,
                )

                if selected_solid_idx is not None:
                    used_solid_indices.add(selected_solid_idx)
                    part_solid = representative_solids[selected_solid_idx]

                    # Keep output naming aligned with the solid that was actually selected.
                    canonical_name = solid_index_to_name.get(selected_solid_idx)
                    if canonical_name and not preserve_bom_identity:
                        current_name = str(bom_item.get('part_name', '') or '').strip()
                        current_norm = _normalize_part_name(current_name)
                        if canonical_name != current_norm:
                            print(
                                f"    [INFO] Renaming by solid match: "
                                f"{current_name or '<empty>'} -> {canonical_name}"
                            )
                            bom_item['part_name'] = canonical_name

        if part_class in ('plaat', 'profiel') and part_solid is None:
            print(
                f"    [WARN] No representative solid for BOM line {idx} "
                f"(available solids: {len(representative_solids)})"
            )
        
        # Determine sequence index for sheet items (only for plaat class)
        seq_idx = plaat_seq_index if part_class == 'plaat' else None
        reference_values = _get_reference_values_for_part(ref_by_name, ref_by_seq, bom_item.get('part_name', ''), seq_idx)
        
        if part_class == 'plaat':
            plaat_seq_index += 1

        try:
            if part_class == 'plaat':
                # STAP 1: PLAAT PROCESSING
                calc_result = _process_plaat_item(
                    bom_item,
                    step_path,
                    step_path.stem,
                    work_dir_path,
                    material,
                    k_factor,
                    part_solid,
                    reference_values,
                )
            elif part_class == 'profiel':
                # STAP 2: PROFIEL PROCESSING
                calc_result = _process_profiel_item(
                    bom_item,
                    step_path.stem,
                    part_solid,
                    material
                )
            else:
                # STAP 3: OTHERS
                calc_result = _process_others_item(bom_item, step_path.stem)

            if calc_result is not None:
                feature_bucket = _resolve_feature_bucket(part_class, calc_result)
                missing_required = _update_feature_coverage(feature_coverage, feature_bucket, calc_result)
                if missing_required:
                    print(
                        f"    [WARN] Missing declared required features "
                        f"({feature_bucket}): {', '.join(missing_required)}"
                    )

                root.append(calc_result)
                processed_count += 1
                class_counts[part_class] += 1
                print(f"    [OK] XML element created")

        except Exception as e:
            print(f"    [ERR] Error processing item: {e}")
            import traceback
            traceback.print_exc()
            continue

    # Add document control element for validation
    doc_control = ET.Element('DocumentControl')
    ET.SubElement(doc_control, 'Aantal_BOM').text = str(len(bom_list))
    ET.SubElement(doc_control, 'Aantal_BOM_Regels').text = str(len(bom_list))
    ET.SubElement(doc_control, 'Aantal_BOM_Stuks').text = str(bom_piece_count)
    ET.SubElement(doc_control, 'Aantal_Verwerkt').text = str(processed_count)
    ET.SubElement(doc_control, 'Aantal_Plaat').text = str(class_counts['plaat'])
    ET.SubElement(doc_control, 'Aantal_Profiel').text = str(class_counts['profiel'])
    ET.SubElement(doc_control, 'Aantal_Anders').text = str(class_counts['anders'])
    ET.SubElement(doc_control, 'Aantal_NietGeclassificeerd').text = str(unclassified_count)
    
    # CONTROLE: Verschil tussen BOM items en geëxporteerde items
    verschil = len(bom_list) - processed_count
    ET.SubElement(doc_control, 'Controle_Verschil_BOM_Exported').text = str(verschil)
    
    # Status bepaling
    status = 'OK'
    waarschuwingen = []
    
    if processed_count != len(bom_list):
        status = 'INCOMPLETE'
        waarschuwingen.append(f'{verschil} BOM items niet verwerkt')
    
    if unclassified_count > 0:
        if status == 'OK':
            status = 'WARNING'
        waarschuwingen.append(f'{unclassified_count} items zonder classificatie')
    
    ET.SubElement(doc_control, 'Status').text = status
    ET.SubElement(doc_control, 'Classificatie_Status').text = 'OK' if unclassified_count == 0 else 'UNCLASSIFIED_PARTS'
    
    if waarschuwingen:
        ET.SubElement(doc_control, 'Waarschuwingen').text = '; '.join(waarschuwingen)
    
    # Insert at the beginning of root
    root.insert(0, doc_control)
    
    print(
        f"\n[INFO] Document control: Regels={len(bom_list)}, Stuks={bom_piece_count}, "
        f"Verwerkt={processed_count}, Verschil={verschil}, "
        f"NietGeclassificeerd={unclassified_count}, "
        f"Status={status}"
    )

    _print_feature_coverage_summary(feature_coverage)

    # Write XML
    xml_string = _prettify_xml(root)
    output_path.write_text(xml_string, encoding='utf-8')

    print(f"\n[OK] XML exported: {output_path}")
    return str(output_path)


def _get_k_factor(material: str) -> float:
    """Get K-factor for material (from sheetmetal_analysis.py)."""
    if not HAS_MATERIAL_PROPS:
        return 0.44  # Default

    props = MATERIAL_BEND_PROPERTIES.get(material, {})
    return props.get('k_factor', 0.44)


def _parse_dims_from_description(description: str) -> tuple:
    """
    Parse dimensions from BOM description.
    Format: "60.0×60.0×403.0 mm" or similar
    Returns: (length, width, height) as floats, or (0,0,0) if parse fails
    """
    try:
        # Remove " mm" and split by × (unicode multiply sign)
        clean = description.replace(' mm', '').strip()
        parts = clean.split('×')
        if len(parts) >= 3:
            return (float(parts[0]), float(parts[1]), float(parts[2]))
    except Exception:
        pass
    return (0, 0, 0)


def _strip_step_name_suffix(name: str) -> str:
    """Strip common CAD software suffixes from STEP part names.

    SpaceClaim appends ' Geometry' to product names on STEP export.
    Example: '10001073529_Rev_00 Geometry' -> '10001073529_Rev_00'
    """
    if not name:
        return name
    cleaned = re.sub(r'\s+Geometry$', '', name, flags=re.IGNORECASE).strip()
    return cleaned if cleaned else name


def _normalize_part_name(name: str) -> str:
    """Normalize part name so '10040853_1.2' maps to '10040853_1'."""
    if not name:
        return ''
    return re.sub(r'\.\d+$', '', name.strip())


def _load_reference_sheet_values(reference_xml_path: Optional[str]) -> tuple:
    """Load trusted sheet values from existing XML.
    
    Returns:
        tuple: (dict by name, list in sequence)
        - by_name: Dict[normalized_name] -> values (for 10040878 style direct name matching)
        - by_sequence: List[values] (for 3001-28608 style position-based matching)
    """
    if not reference_xml_path:
        return ({}, [])

    ref_path = Path(reference_xml_path)
    if not ref_path.exists():
        print(f"  [WARN] Reference XML not found: {ref_path}")
        return ({}, [])

    by_name = {}
    by_sequence = []
    try:
        tree = ET.parse(ref_path)
        root = tree.getroot()
        for calc in root.findall('CalculationResult'):
            sheet_name = calc.findtext('Sheet_Name', '')
            sheet_part_name = calc.findtext('Sheet_PartName', '')
            if not sheet_name:
                continue

            box_x = float(calc.findtext('Sheet_BoxX', '0') or 0)
            box_y = float(calc.findtext('Sheet_BoxY', '0') or 0)
            thickness = float(calc.findtext('Sheet_Thickness', '0') or 0)
            nr_bends = int(float(calc.findtext('Sheet_NrBends', '0') or 0))
            nr_holes = int(float(calc.findtext('Sheet_NrHoles', '0') or 0))
            qty = int(float(calc.findtext('Sheet_Count', '1') or 1))

            values = {
                'box_x': box_x,
                'box_y': box_y,
                'thickness': thickness,
                'nr_bends': nr_bends,
                'nr_holes': nr_holes,
                'qty': qty,
                'sheet_name': sheet_name,
                'sheet_part_name': sheet_part_name,
                'bend_angles': (calc.findtext('Sheet_BendAngles', '') or '').strip(),
                'bend_lengths': (calc.findtext('Sheet_BendLength', '') or '').strip(),
                'outer_contour': float(calc.findtext('Sheet_OuterContour', '0') or 0),
                'total_contour': float(calc.findtext('Sheet_TotalContour', '0') or 0),
                'top_area': float(calc.findtext('Sheet_TopArea', '0') or 0),
                'area_no_holes': float(calc.findtext('Sheet_AreaNoHoles', '0') or 0),
            }

            # Add to sequential list
            by_sequence.append(values)

            # Also add by normalized name for direct matching
            key = _normalize_part_name(sheet_name)
            if key:
                by_name[key] = values

        print(f"  [INFO] Loaded {len(by_sequence)} sheet values from reference XML")
    except Exception as e:
        print(f"  [WARN] Failed to read reference XML: {e}")

    return (by_name, by_sequence)


def _get_reference_values_for_part(ref_by_name: Dict[str, Dict[str, float]], ref_by_seq: List[Dict[str, float]], part_name: str, seq_index: Optional[int] = None) -> Optional[Dict[str, float]]:
    """Fetch reference values using name-based or sequence-based matching.
    
    Args:
        ref_by_name: Dict keyed by normalized part name
        ref_by_seq: List of all sheet items in order
        part_name: Part name to match
        seq_index: If provided, try sequence-based matching first
    
    Returns:
        Dict with box_x, box_y, thickness, nr_bends, nr_holes or None
    """
    if not ref_by_name and not ref_by_seq:
        return None
    
    # Try name-based matching first (for specific part names like "MD-20-11832_1")
    key = _normalize_part_name(part_name)
    if key and key in ref_by_name:
        return ref_by_name[key]

    # Fallback: sequence-based matching (for generic "Plaatdeel XXX" names)
    if seq_index is not None and seq_index < len(ref_by_seq):
        return ref_by_seq[seq_index]
    
    return None


def _build_representative_solids(doc) -> List[Any]:
    """Extract all solids from STEP document (no grouping).
    
    NOTE: We used to do geometry-based grouping here, but that merges mirror
    variants (e.g., 10000503252 LEFT + 10000503253 RIGHT) as identical.
    Now we return all 25 solids and let the BOM item loop handle them 1-to-1.
    """
    if not HAS_ASSEMBLY_GEOM:
        return []

    try:
        from OCP.TopExp import TopExp_Explorer
        from OCP.TopAbs import TopAbs_SOLID
        from OCP.TopoDS import TopoDS

        shape = doc.val().wrapped if hasattr(doc, 'val') else doc.wrapped if hasattr(doc, 'wrapped') else doc

        solids = []
        exp = TopExp_Explorer(shape, TopAbs_SOLID)
        while exp.More():
            solids.append(TopoDS.Solid_s(exp.Current()))
            exp.Next()

        # CRITICAL FIX: Return all solids, no grouping
        # This ensures 25 BOM items get matched 1-to-1 with 25 solids
        return solids  # Was: grouped_representatives after geometry comparison
    except Exception:
        return []


def _build_part_name_to_solid_indices(step_file_path: str, solids: List[Any]) -> Dict[str, List[int]]:
    """Build mapping: normalized part name -> candidate solid indices.

    Strategy:
    1) Use SHAPE_REPRESENTATION counts when available.
    2) Fallback to NEXT_ASSEMBLY_USAGE_OCCURRENCE counts.
    3) Match names to solids via assembly-analysis volume matcher when available.
    4) Fallback to sequential expansion by count.
    """
    if not solids:
        return {}

    if not HAS_ASSEMBLY_GEOM and not HAS_XCAF_READER:
        return {}

    step_path = str(step_file_path) if step_file_path else ""

    # Primary strategy: direct XCAF name/solid mapping.
    if HAS_XCAF_READER and step_path:
        try:
            xcaf_result = xcaf_match_solids_to_names(step_path)
            if xcaf_result is not None:
                xcaf_solids, xcaf_names = xcaf_result
                if xcaf_solids and xcaf_names and len(xcaf_solids) == len(solids):
                    mapping: Dict[str, List[int]] = {}
                    for solid_idx, assigned_name in enumerate(xcaf_names):
                        key = _normalize_part_name(str(assigned_name or ""))
                        if not key:
                            continue
                        if key not in mapping:
                            mapping[key] = []
                        mapping[key].append(solid_idx)
                    if mapping:
                        return mapping
        except Exception:
            pass

    shape_rep_counts = parse_step_shape_rep_name_counts(step_path) if step_path else None
    step_parts_counts = parse_step_assembly_structure(step_path) if step_path else None
    name_source_counts = shape_rep_counts if shape_rep_counts else step_parts_counts

    if not name_source_counts:
        return {}

    solid_names: List[str] = []

    # Preferred: use the same volume-driven name matcher as assembly analysis.
    try:
        from manufacturing_pipeline.analysis.assembly_analysis import (
            _build_reference_database,
            _match_solids_to_names_bipartite,
        )

        reference_database = _build_reference_database()
        solid_names = _match_solids_to_names_bipartite(
            solids,
            name_source_counts,
            Path(step_path).name if step_path else "",
            reference_database,
        )
    except Exception:
        solid_names = []

    if not solid_names:
        names_flat: List[str] = []
        for name, count in name_source_counts.items():
            try:
                repeats = max(0, int(count))
            except Exception:
                repeats = 0
            for _ in range(repeats):
                names_flat.append(str(name))

        while len(names_flat) < len(solids):
            names_flat.append(f"Part_{len(names_flat) + 1}")

        solid_names = names_flat[:len(solids)]

    mapping: Dict[str, List[int]] = {}
    for solid_idx, assigned_name in enumerate(solid_names):
        key = _normalize_part_name(str(assigned_name or ""))
        if not key:
            continue
        if key not in mapping:
            mapping[key] = []
        mapping[key].append(solid_idx)

    return mapping


def _pick_fallback_solid_index(preferred_idx: int, total_solids: int, used_indices: set) -> Optional[int]:
    """Pick an unused solid index, preferring the index-aligned candidate."""
    if total_solids <= 0:
        return None

    if 0 <= preferred_idx < total_solids and preferred_idx not in used_indices:
        return preferred_idx

    # First search forward from preferred index, then wrap.
    start_idx = preferred_idx if preferred_idx >= 0 else 0
    for solid_idx in range(start_idx, total_solids):
        if solid_idx not in used_indices:
            return solid_idx
    for solid_idx in range(0, start_idx):
        if solid_idx not in used_indices:
            return solid_idx

    return None


def _invert_part_name_to_solid_indices(
    part_name_to_solid_indices: Dict[str, List[int]],
) -> Dict[int, str]:
    """Build reverse lookup: solid index -> normalized part name."""
    reverse: Dict[int, str] = {}
    for normalized_name, indices in part_name_to_solid_indices.items():
        if not normalized_name:
            continue
        for idx in indices:
            if idx not in reverse:
                reverse[idx] = normalized_name
    return reverse


def _compute_solid_volumes_mm3(solids: List[Any]) -> List[float]:
    """Compute representative solid volumes once for volume-aware matching."""
    volumes: List[float] = []
    if not HAS_ASSEMBLY_GEOM:
        return [0.0 for _ in solids]

    for solid in solids:
        try:
            volumes.append(float(get_solid_volume(solid) or 0.0))
        except Exception:
            volumes.append(0.0)
    return volumes


def _get_material_density_kg_m3(material: str) -> float:
    """Return rough material density in kg/m^3 for mass->volume conversion."""
    token = str(material or '').strip().lower()
    if not token:
        return 7850.0

    # Stainless and RVS families.
    if any(key in token for key in ['stainless', 'rvs', 'inox', '304', '316']):
        return 8000.0

    # Aluminum families.
    if any(key in token for key in ['aluminum', 'aluminium', 'al ', 'alu']):
        return 2700.0

    # Default: carbon steel family.
    return 7850.0


def _estimate_expected_volume_mm3_from_bom(
    bom_item: Dict[str, Any],
    default_material: str,
) -> Optional[float]:
    """Estimate per-part expected volume from BOM mass fields."""
    mass_per_unit_kg: Optional[float] = None

    try:
        raw_mass = bom_item.get('mass_per_unit_kg', None)
        if raw_mass is not None:
            mass_per_unit_kg = float(raw_mass)
    except Exception:
        mass_per_unit_kg = None

    if mass_per_unit_kg is None or mass_per_unit_kg <= 0:
        try:
            total_mass_kg = float(bom_item.get('total_mass_kg', 0) or 0)
            qty = float(bom_item.get('quantity', 1) or 1)
            if total_mass_kg > 0 and qty > 0:
                mass_per_unit_kg = total_mass_kg / qty
        except Exception:
            mass_per_unit_kg = None

    if mass_per_unit_kg is None or mass_per_unit_kg <= 0:
        return None

    material_token = str(bom_item.get('material', '') or default_material)
    density_kg_m3 = _get_material_density_kg_m3(material_token)
    if density_kg_m3 <= 0:
        return None

    # volume_mm3 = (mass_kg / density_kg_m3) * 1e9
    expected_volume = (mass_per_unit_kg / density_kg_m3) * 1_000_000_000.0
    return expected_volume if expected_volume > 0 else None


def _relative_volume_error(actual_volume_mm3: float, expected_volume_mm3: float) -> float:
    """Compute relative volume error (0=perfect, higher=worse)."""
    if expected_volume_mm3 <= 0:
        return float('inf')
    if actual_volume_mm3 <= 0:
        return float('inf')
    return abs(actual_volume_mm3 - expected_volume_mm3) / expected_volume_mm3


def _select_solid_index_for_bom_item(
    bom_item: Dict[str, Any],
    normalized_bom_name: str,
    preferred_idx: int,
    total_solids: int,
    part_name_to_solid_indices: Dict[str, List[int]],
    solid_volumes_mm3: List[float],
    used_indices: set,
    default_material: str,
) -> Optional[int]:
    """Select best solid index using name-first mapping with volume-aware tie-breaks."""
    if total_solids <= 0:
        return None

    available_indices = [i for i in range(total_solids) if i not in used_indices]
    if not available_indices:
        return None

    name_candidates = [
        i
        for i in part_name_to_solid_indices.get(normalized_bom_name, [])
        if i not in used_indices
    ]

    expected_volume = _estimate_expected_volume_mm3_from_bom(bom_item, default_material)

    # If we can estimate volume, use it to resolve ambiguous/misaligned name matches.
    if expected_volume is not None and solid_volumes_mm3:
        def _err(idx: int) -> float:
            return _relative_volume_error(solid_volumes_mm3[idx], expected_volume)

        best_global_idx = min(available_indices, key=_err)
        best_global_err = _err(best_global_idx)

        if name_candidates:
            best_name_idx = min(name_candidates, key=_err)
            best_name_err = _err(best_name_idx)

            # Keep name-driven mapping when it is already good or nearly as good.
            if best_name_err <= 0.25 or best_name_err <= (best_global_err + 0.05):
                return best_name_idx

            # Override only when global match is materially better and still credible.
            if best_global_err <= 0.35 and (best_name_err - best_global_err) >= 0.15:
                print(
                    f"    [INFO] Volume tie-break override for {bom_item.get('part_name', 'Unknown')}: "
                    f"solid[{best_name_idx}] -> solid[{best_global_idx}] "
                    f"(err {best_name_err:.2f} -> {best_global_err:.2f})"
                )
                return best_global_idx

            return best_name_idx

        return best_global_idx

    # Name-based selection when volume evidence is unavailable.
    if name_candidates:
        return name_candidates[0]

    return _pick_fallback_solid_index(preferred_idx, total_solids, used_indices)


def _extract_dims_from_solid(part_solid) -> tuple:
    """Extract (length, width, thickness) from solid using assembly-analysis geometry method."""
    if not HAS_ASSEMBLY_GEOM or part_solid is None:
        return (0.0, 0.0, 0.0)

    try:
        dims = get_solid_bounding_box(part_solid)
        if not dims or len(dims) != 3:
            return (0.0, 0.0, 0.0)

        sorted_dims = sorted([float(dims[0]), float(dims[1]), float(dims[2])])
        thickness = sorted_dims[0]
        width = sorted_dims[1]
        length = sorted_dims[2]
        return (length, width, thickness)
    except Exception:
        return (0.0, 0.0, 0.0)


def _snap_sheet_thickness(thickness_value: float) -> float:
    """Snap thickness to a nearby standard gauge when within a small tolerance."""
    try:
        value = float(thickness_value or 0.0)
    except Exception:
        return thickness_value

    if value <= 0:
        return value

    standard_values = [
        0.8, 1.0, 1.2, 1.5, 2.0, 2.5, 3.0, 4.0,
        5.0, 6.0, 8.0, 10.0, 12.0, 15.0, 20.0, 25.0, 30.0,
    ]

    nearest = min(standard_values, key=lambda candidate: abs(candidate - value))
    rel_diff = abs(nearest - value) / max(nearest, 1e-9)

    # Snap only when very close (3%) to avoid masking real geometry differences.
    if rel_diff <= 0.03:
        return nearest

    return value


def _process_plaat_item(
    bom_item: Dict[str, Any],
    step_path: Path,
    source_step_name: str,
    work_dir: Path,
    material: str,
    k_factor: float,
    part_solid,
    reference_values: Optional[Dict[str, float]] = None
) -> Optional[ET.Element]:
    """
    Process PLAAT item: Check if bent, unfold if needed, extract features.

    Returns: ET.Element with Sheet_* elements or None if error
    """
    part_name = bom_item.get('part_name', 'Unknown')
    quantity = bom_item.get('quantity', 1)
    output_part_name = source_step_name
    output_sheet_name = _strip_step_name_suffix(part_name)

    if reference_values is not None:
        # Reference XML is for validating/enriching metrics, not for overriding naming
        ref_qty = int(float(reference_values.get('qty', quantity) or quantity))
        if ref_qty > 0:
            quantity = ref_qty

    calc_result = ET.Element('CalculationResult')

    # Basic info
    ET.SubElement(calc_result, 'Sheet_PartName').text = output_part_name
    ET.SubElement(calc_result, 'Sheet_Name').text = output_sheet_name
    ET.SubElement(calc_result, 'Sheet_Type').text = '3D'  # Will be '2D' if flat
    ET.SubElement(calc_result, 'Sheet_Count').text = str(quantity)

    # Material
    ET.SubElement(calc_result, 'Sheet_Material').text = material

    # Primary source: trusted reference XML values (if provided)
    length = 0.0
    width = 0.0
    thickness = 0.0
    cut_features_result = None

    if reference_values is not None:
        length = float(reference_values.get('box_x', 0.0))
        width = float(reference_values.get('box_y', 0.0))
        thickness = float(reference_values.get('thickness', 0.0))
        if length > 0 and width > 0 and thickness > 0:
            print(f"    [INFO] Dims from reference XML: L={length:.1f}, W={width:.1f}, T={thickness:.1f} mm")

    # Secondary source: geometry extraction (assembly-analysis method)
    if length <= 0 or width <= 0 or thickness <= 0:
        length, width, thickness = _extract_dims_from_solid(part_solid)

    # Fallback source: parse BOM description (format: "L×W×H mm")
    if length <= 0 or width <= 0 or thickness <= 0:
        description = bom_item.get('description', '')
        d1, d2, d3 = _parse_dims_from_description(description)
        if d1 > 0 and d2 > 0 and d3 > 0:
            sorted_dims = sorted([d1, d2, d3])
            thickness = sorted_dims[0]
            width = sorted_dims[1]
            length = sorted_dims[2]

    # Extra geometry source: cut features (box, holes, contours)
    # Keep as fallback to avoid overriding trusted reference values.
    if HAS_CUT_FEATURES and part_solid is not None:
        try:
            cut_features_result = extract_cut_features_for_sheet(part_solid)
            if cut_features_result is not None and (length <= 0 or width <= 0):
                if float(cut_features_result.box_x) > 0 and float(cut_features_result.box_y) > 0:
                    length = float(cut_features_result.box_x)
                    width = float(cut_features_result.box_y)
                    print(
                        f"    [INFO] Dims from cut features: "
                        f"L={length:.1f}, W={width:.1f} mm (source={cut_features_result.source})"
                    )
        except Exception as e:
            print(f"    [WARN] Cut feature extraction failed: {str(e)[:60]}")

    if length > 0 and width > 0 and thickness > 0:
        print(f"    [INFO] Dims: L={length:.1f}, W={width:.1f}, T={thickness:.1f} mm")
    else:
        print(f"    [WARN] Could not determine dimensions")

    ET.SubElement(calc_result, 'Sheet_Thickness').text = _format_float(thickness)

    # Box dimensions
    ET.SubElement(calc_result, 'Sheet_BoxX').text = _format_float(length)
    ET.SubElement(calc_result, 'Sheet_BoxY').text = _format_float(width)

    # Default values
    ET.SubElement(calc_result, 'Sheet_NrBends').text = '0'
    ET.SubElement(calc_result, 'Sheet_BendAngles').text = ''
    ET.SubElement(calc_result, 'Sheet_BendInnerRadii').text = ''
    ET.SubElement(calc_result, 'Sheet_BendLength').text = ''
    ET.SubElement(calc_result, 'Sheet_NrHoles').text = '0'
    ET.SubElement(calc_result, 'Sheet_HoleContours').text = ''
    ET.SubElement(calc_result, 'Sheet_FeatExtTotL').text = ''
    ET.SubElement(calc_result, 'Sheet_HoleRadii').text = ''
    ET.SubElement(calc_result, 'Sheet_HoleTypes').text = ''
    ET.SubElement(calc_result, 'Sheet_ThreadedHoles').text = '0'
    ET.SubElement(calc_result, 'Sheet_CountersunkHoles').text = '0'
    ET.SubElement(calc_result, 'Sheet_CountersunkAngles').text = ''
    ET.SubElement(calc_result, 'Sheet_UnfoldSuccess').text = 'False'
    ET.SubElement(calc_result, 'Sheet_FilePathDXF').text = ''

    # If cut features are available, use them as early fallback for hole fields.
    if cut_features_result is not None and int(getattr(cut_features_result, 'nr_holes', 0) or 0) > 0:
        try:
            hole_count = int(cut_features_result.nr_holes)
            hole_contours = list(getattr(cut_features_result, 'hole_contours', []) or [])
            hole_radii = list(getattr(cut_features_result, 'hole_radii', []) or [])
            hole_types = [str(v).strip().lower() for v in list(getattr(cut_features_result, 'hole_types', []) or []) if str(v).strip()]
            threaded_holes = int(getattr(cut_features_result, 'threaded_holes', 0) or 0)
            countersunk_holes = int(getattr(cut_features_result, 'countersunk_holes', 0) or 0)
            countersunk_angles = [
                float(v)
                for v in list(getattr(cut_features_result, 'countersunk_angles', []) or [])
                if float(v) > 0
            ]

            calc_result.find('Sheet_NrHoles').text = str(hole_count)
            if hole_contours:
                contours_text = '_'.join(_format_float(v) for v in hole_contours)
                calc_result.find('Sheet_HoleContours').text = contours_text
                calc_result.find('Sheet_FeatExtTotL').text = contours_text
            if hole_radii:
                calc_result.find('Sheet_HoleRadii').text = '_'.join(_format_float(v) for v in hole_radii)
            if hole_types:
                calc_result.find('Sheet_HoleTypes').text = '_'.join(hole_types)

            calc_result.find('Sheet_ThreadedHoles').text = str(max(0, threaded_holes))
            calc_result.find('Sheet_CountersunkHoles').text = str(max(0, countersunk_holes))
            if countersunk_angles:
                calc_result.find('Sheet_CountersunkAngles').text = '_'.join(
                    _format_float(v) for v in countersunk_angles
                )
        except Exception as e:
            print(f"    [WARN] Could not apply cut-feature hole fallback: {str(e)[:60]}")

    # CROSS-SECTION ANALYSIS: Primary method for bent prismatic plates.
    # Analyses the 2D cross-section perpendicular to the extrusion axis to extract
    # thickness, bend count, angles, inner radii, and flat developed width.
    # Works reliably for C-channels, U-profiles, Z-sections etc. without needing FreeCAD.
    cs_bend_success = False
    if HAS_BENT_PLATE_CS and part_solid is not None:
        try:
            cs_result = extract_bent_plate_cross_section(part_solid)
            if cs_result is not None and cs_result.get('nr_bends', 0) > 0:
                cs_thickness = float(cs_result.get('thickness', 0) or 0)
                cs_nr_bends = int(cs_result.get('nr_bends', 0))
                cs_bend_angles = list(cs_result.get('bend_angles', []))
                cs_inner_radii = list(cs_result.get('inner_radii', []))
                cs_bend_line_length = float(cs_result.get('bend_line_length', 0) or 0)
                cs_flat_width = float(cs_result.get('flat_width', 0) or 0)

                print(
                    f"    [CS] Cross-section: {cs_nr_bends} bends, "
                    f"t={cs_thickness:.2f} mm, "
                    f"L={cs_bend_line_length:.1f} mm, "
                    f"flat_W={cs_flat_width:.1f} mm"
                )
                print(f"        Angles: {cs_bend_angles}")
                print(f"        Radii:  {cs_inner_radii}")

                calc_result.find('Sheet_NrBends').text = str(cs_nr_bends)
                calc_result.find('Sheet_BendAngles').text = '_'.join(
                    _format_float(a) for a in cs_bend_angles
                )
                calc_result.find('Sheet_BendInnerRadii').text = '_'.join(
                    _format_float(r) for r in cs_inner_radii
                )
                # All bends run the full extrusion length (prismatic assumption).
                calc_result.find('Sheet_BendLength').text = '_'.join(
                    _format_float(cs_bend_line_length) for _ in cs_bend_angles
                )

                # Override thickness and BoxY (flat width) from cross-section.
                if cs_thickness > 0:
                    calc_result.find('Sheet_Thickness').text = _format_float(cs_thickness)
                    thickness = cs_thickness
                if cs_flat_width > 0:
                    calc_result.find('Sheet_BoxY').text = _format_float(cs_flat_width)
                    width = cs_flat_width
                if cs_bend_line_length > 0:
                    calc_result.find('Sheet_BoxX').text = _format_float(cs_bend_line_length)
                    length = cs_bend_line_length

                cs_bend_success = True
        except Exception as e:
            print(f"    [WARN] Cross-section analysis failed: {str(e)[:80]}")

    # HYBRID LIP CHECK: If cross-section succeeded but flagged end-complexity
    # (more edges at the extremities than in the middle), a lip or extra bend
    # near the tip of the plate is invisible to the cross-section sampler.
    # In that case, try FreeCAD unfold as a complementary check.  If it finds
    # MORE bends than the cross-section, prefer FreeCAD's richer picture.
    # If FreeCAD fails, keep the cross-section result and log a warning.
    lip_check_attempted = False
    if (
        cs_bend_success
        and cs_result is not None
        and cs_result.get('has_end_complexity', False)
        and HAS_UNFOLD
        and part_solid is not None
    ):
        print(f"    [CS] End-complexity detected → trying FreeCAD unfold for lip check...")
        lip_check_attempted = True
        try:
            lip_unfold = _try_unfold(
                str(step_path), part_name, work_dir, k_factor, material,
                nr_bends=0,
                solid_object=part_solid,
            )
            if lip_unfold and lip_unfold.get('success'):
                lip_angles  = lip_unfold.get('bend_angles', [])
                lip_radii   = lip_unfold.get('bend_radii', [])
                lip_lengths = lip_unfold.get('bend_lengths', [])
                if lip_angles:
                    lip_angles, lip_radii, lip_lengths = _merge_bends_colinear(
                        lip_angles, lip_radii, lip_lengths
                    )
                lip_nr = len(lip_angles) if lip_angles else 0
                cs_nr  = int(calc_result.findtext('Sheet_NrBends', '0') or 0)
                if lip_nr > cs_nr:
                    # FreeCAD found more bends (likely includes the lip bend).
                    print(
                        f"    [OK] Lip check: unfold found {lip_nr} bends "
                        f"(cross-section had {cs_nr}) → upgrading to unfold data"
                    )
                    calc_result.find('Sheet_NrBends').text = str(lip_nr)
                    calc_result.find('Sheet_BendAngles').text = '_'.join(
                        _format_float(a) for a in lip_angles
                    )
                    calc_result.find('Sheet_BendInnerRadii').text = '_'.join(
                        _format_float(r) for r in lip_radii
                    )
                    calc_result.find('Sheet_BendLength').text = '_'.join(
                        _format_float(l) for l in lip_lengths
                    )
                    flat_length = float(lip_unfold.get('flat_length', 0) or 0)
                    flat_width  = float(lip_unfold.get('flat_width',  0) or 0)
                    unfold_thickness = float(lip_unfold.get('thickness', 0) or 0)
                    if _is_plausible_unfold_dims(
                        flat_length=flat_length,
                        flat_width=flat_width,
                        raw_thickness=thickness,
                        bend_radii=lip_radii,
                        unfold_thickness=unfold_thickness,
                    ):
                        calc_result.find('Sheet_BoxX').text = _format_float(flat_length)
                        calc_result.find('Sheet_BoxY').text = _format_float(flat_width)
                        length = flat_length
                        width  = flat_width
                    calc_result.find('Sheet_UnfoldSuccess').text = 'True'
                    if lip_unfold.get('dxf_output'):
                        calc_result.find('Sheet_FilePathDXF').text = str(lip_unfold['dxf_output'])
                else:
                    print(
                        f"    [INFO] Lip check: unfold found {lip_nr} bends "
                        f"(same as cross-section {cs_nr}) → keeping cross-section data"
                    )
            else:
                print(
                    f"    [WARN] Lip check: FreeCAD unfold failed "
                    f"({(lip_unfold or {}).get('error', 'no result')[:60]}) "
                    f"→ cross-section data retained, possible undetected lip"
                )
        except Exception as e:
            print(f"    [WARN] Lip check unfold exception: {str(e)[:80]}")

    # PROACTIVE UNFOLD: Try unfold for all sheet metal parts to detect bends.
    # Used as fallback when cross-section analysis did not succeed, AND for
    # generating the DXF even when cross-section did supply bend data.
    # Skip when we already ran a successful lip-check unfold above (avoids
    # double work for the same solid).
    early_unfold_attempted = False
    if HAS_UNFOLD and part_solid is not None and not lip_check_attempted:
        try:
            # Check if this solid is planar (flat plate) or formed (bent)
            from manufacturing_pipeline.analysis.assembly_analysis import _is_plate_by_face_analysis
            is_planar = _is_plate_by_face_analysis(part_solid, threshold=50.0)
            
            if not is_planar:
                # Non-planar sheet metal - likely bent, try unfold proactively
                print(f"    [INFO] Non-planar sheet detected - attempting unfold...")
                early_unfold_attempted = True
                unfold_result = _try_unfold(
                    str(step_path), part_name, work_dir, k_factor, material,
                    nr_bends=0,  # Unknown yet, unfold will detect
                    solid_object=part_solid
                )
                
                if unfold_result and unfold_result.get('success'):
                    # Unfold succeeded - extract bend parameters
                    bend_angles = unfold_result.get('bend_angles', [])
                    bend_radii = unfold_result.get('bend_radii', [])
                    bend_lengths = unfold_result.get('bend_lengths', [])
                    
                    # Merge adjacent bends with same angle/radius (likely interrupted by holes)
                    if bend_angles:
                        bend_angles, bend_radii, bend_lengths = _merge_bends_colinear(
                            bend_angles, bend_radii, bend_lengths
                        )
                    
                    nr_bends = len(bend_angles) if bend_angles else 0
                    if nr_bends > 0:
                        print(f"    [OK] Unfold: {nr_bends} bends detected")
                        print(f"        Angles: {bend_angles}")
                        print(f"        Radii: {bend_radii}")
                        print(f"        Flat: {unfold_result.get('flat_length', 0):.1f} x {unfold_result.get('flat_width', 0):.1f} mm")

                        # Only write bend fields if cross-section didn't already supply them.
                        if not cs_bend_success:
                            calc_result.find('Sheet_NrBends').text = str(nr_bends)
                            calc_result.find('Sheet_BendAngles').text = '_'.join(_format_float(a) for a in bend_angles)
                            calc_result.find('Sheet_BendInnerRadii').text = '_'.join(_format_float(r) for r in bend_radii)
                            calc_result.find('Sheet_BendLength').text = '_'.join(_format_float(l) for l in bend_lengths)

                        flat_length = float(unfold_result.get('flat_length', 0) or 0)
                        flat_width = float(unfold_result.get('flat_width', 0) or 0)
                        unfold_thickness = float(unfold_result.get('thickness', 0) or 0)
                        if _is_plausible_unfold_dims(
                            flat_length=flat_length,
                            flat_width=flat_width,
                            raw_thickness=thickness,
                            bend_radii=bend_radii,
                            unfold_thickness=unfold_thickness,
                        ):
                            calc_result.find('Sheet_BoxX').text = _format_float(flat_length)
                            calc_result.find('Sheet_BoxY').text = _format_float(flat_width)
                            length = flat_length
                            width = flat_width
                        else:
                            print(f"    [WARN] Ignoring implausible unfold dims: {flat_length:.1f} x {flat_width:.1f} mm")
                        calc_result.find('Sheet_UnfoldSuccess').text = 'True'
                        
                        # Store DXF file path from unfold
                        if unfold_result.get('dxf_output'):
                            calc_result.find('Sheet_FilePathDXF').text = str(unfold_result['dxf_output'])
                        
                        # Update thickness from unfold if available and not already from cross-section.
                        if unfold_result.get('thickness') and not cs_bend_success:
                            calc_result.find('Sheet_Thickness').text = _format_float(unfold_result['thickness'])
        except Exception as e:
            print(f"    [WARN] Proactive unfold failed: {str(e)[:60]}")

    # Try to extract detailed features from part geometry via part_analyzer
    # Skip bend detection only when a prior method already succeeded (unfold or cross-section).
    if HAS_PART_ANALYZER:
        try:
            if part_solid is not None:
                # Analyze geometry for this specific part solid
                analysis = analyze_part_geometry(part_solid, part_name)

                # Check if bent.
                # If the proactive unfold was attempted but FAILED we still want
                # part_analyzer's bend detection as a further fallback.
                bends_already_known = (
                    calc_result.findtext('Sheet_UnfoldSuccess', 'False') == 'True'
                    or int(calc_result.findtext('Sheet_NrBends', '0') or 0) > 0
                )
                if not bends_already_known and hasattr(analysis, 'bends') and len(analysis.bends) > 0:
                    print(f"    [INFO] Bent part: {len(analysis.bends)} bends detected")

                    bend_angles = '_'.join(_format_float(b.angle) for b in analysis.bends)
                    bend_radii = '_'.join(_format_float(b.radius) for b in analysis.bends)
                    bend_lengths = '_'.join(_format_float(b.length) for b in analysis.bends)

                    calc_result.find('Sheet_NrBends').text = str(len(analysis.bends))
                    calc_result.find('Sheet_BendAngles').text = bend_angles
                    calc_result.find('Sheet_BendInnerRadii').text = bend_radii
                    calc_result.find('Sheet_BendLength').text = bend_lengths

                    # Try to unfold - pass the specific solid for bent parts
                    unfold_result = _try_unfold(
                        str(step_path), part_name, work_dir, k_factor, material,
                        nr_bends=len(analysis.bends),
                        solid_object=part_solid  # Use specific solid instead of whole assembly
                    )

                    if unfold_result and unfold_result.get('success'):
                        flat_length = float(unfold_result.get('flat_length', 0) or 0)
                        flat_width = float(unfold_result.get('flat_width', 0) or 0)
                        unfold_thickness = float(unfold_result.get('thickness', 0) or 0)
                        unfold_radii = unfold_result.get('bend_radii') or []
                        if _is_plausible_unfold_dims(
                            flat_length=flat_length,
                            flat_width=flat_width,
                            raw_thickness=thickness,
                            bend_radii=unfold_radii,
                            unfold_thickness=unfold_thickness,
                        ):
                            print(f"    [OK] Unfold: {flat_length:.1f} x {flat_width:.1f} mm")
                            calc_result.find('Sheet_BoxX').text = _format_float(flat_length)
                            calc_result.find('Sheet_BoxY').text = _format_float(flat_width)
                            length = flat_length
                            width = flat_width
                        else:
                            print(f"    [WARN] Ignoring implausible unfold dims: {flat_length:.1f} x {flat_width:.1f} mm")
                        calc_result.find('Sheet_UnfoldSuccess').text = 'True'
                        
                        # Store DXF file path from unfold
                        if unfold_result.get('dxf_output'):
                            calc_result.find('Sheet_FilePathDXF').text = str(unfold_result['dxf_output'])
                        
                        # Add bend parameters from unfold result if available
                        if unfold_result.get('bend_angles'):
                            bend_angles_str = '_'.join(_format_float(a) for a in unfold_result['bend_angles'])
                            calc_result.find('Sheet_BendAngles').text = bend_angles_str
                        
                        if unfold_result.get('bend_radii'):
                            bend_radii_str = '_'.join(_format_float(r) for r in unfold_result['bend_radii'])
                            calc_result.find('Sheet_BendInnerRadii').text = bend_radii_str
                        
                        if unfold_result.get('bend_lengths'):
                            bend_lengths_str = '_'.join(_format_float(l) for l in unfold_result['bend_lengths'])
                            calc_result.find('Sheet_BendLength').text = bend_lengths_str

                # Holes
                if hasattr(analysis, 'holes') and len(analysis.holes) > 0:
                    hole_diameters = '_'.join(_format_float(h.diameter) for h in analysis.holes if hasattr(h, 'diameter'))
                    calc_result.find('Sheet_NrHoles').text = str(len(analysis.holes))
                    calc_result.find('Sheet_HoleContours').text = hole_diameters
                    calc_result.find('Sheet_HoleRadii').text = hole_diameters

        except Exception as e:
            print(f"    [WARN] Analysis: {str(e)[:40]}")

    # Robust fallback: detect bends/thickness from sheetmetal analyzer directly.
    # This catches cases where planar-face heuristics classify as flat,
    # while geometry actually contains bends (e.g. 10001091136_Rev_00).
    if HAS_SHEETMETAL_ANALYSIS and part_solid is not None:
        try:
            sm_data = analyze_sheet_metal_geometry(part_solid)

            sm_thickness = float(sm_data.get('thickness', 0) or 0)
            if sm_thickness > 0 and (
                thickness <= 0 or thickness > (sm_thickness * 1.8)
            ):
                thickness = sm_thickness
                thickness_elem = calc_result.find('Sheet_Thickness')
                if thickness_elem is not None:
                    thickness_elem.text = _format_float(thickness)

            current_bends = int(calc_result.findtext('Sheet_NrBends', '0') or 0)
            sm_bend_count = int(
                sm_data.get('bend_count_for_erp', 0)
                or sm_data.get('bend_count', 0)
                or 0
            )
            sm_bends = list(sm_data.get('bends') or [])

            if current_bends == 0 and sm_bend_count > 0 and sm_bends:
                used_bends = sm_bends[:sm_bend_count]
                bend_angles = []
                bend_radii = []
                bend_lengths = []

                for bend in used_bends:
                    angle = float(getattr(bend, 'angle', 0) or 0)
                    radius = float(getattr(bend, 'inner_radius', 0) or 0)
                    bend_len = float(getattr(bend, 'bend_length', 0) or 0)

                    bend_angles.append(angle)
                    bend_radii.append(radius)
                    bend_lengths.append(bend_len)

                calc_result.find('Sheet_NrBends').text = str(sm_bend_count)
                calc_result.find('Sheet_BendAngles').text = '_'.join(
                    _format_float(v) for v in bend_angles
                )
                calc_result.find('Sheet_BendInnerRadii').text = '_'.join(
                    _format_float(v) for v in bend_radii
                )
                calc_result.find('Sheet_BendLength').text = '_'.join(
                    _format_float(v) for v in bend_lengths
                )

                print(
                    f"    [INFO] Sheetmetal fallback: "
                    f"{sm_bend_count} bends, thickness={sm_thickness:.2f} mm"
                )
        except Exception as e:
            print(f"    [WARN] Sheetmetal fallback failed: {str(e)[:60]}")

    # If reference XML provided explicit bends/holes counts, enforce those as final
    if reference_values is not None:
        if 'nr_bends' in reference_values:
            calc_result.find('Sheet_NrBends').text = str(int(reference_values.get('nr_bends', 0)))
        if 'nr_holes' in reference_values:
            calc_result.find('Sheet_NrHoles').text = str(int(reference_values.get('nr_holes', 0)))
        # If unfold did not return bend details, fill from trusted reference
        if not (calc_result.findtext('Sheet_BendAngles', '') or '').strip() and (reference_values.get('bend_angles') or '').strip():
            calc_result.find('Sheet_BendAngles').text = (reference_values.get('bend_angles') or '').strip()
        ref_bend_lengths = (reference_values.get('bend_lengths') or '').strip()
        if ref_bend_lengths:
            current_bend_lengths = (calc_result.findtext('Sheet_BendLength', '') or '').strip()
            if not current_bend_lengths:
                calc_result.find('Sheet_BendLength').text = ref_bend_lengths
            else:
                try:
                    current_vals = [float(v) for v in current_bend_lengths.split('_') if v.strip()]
                    ref_vals = [float(v) for v in ref_bend_lengths.split('_') if v.strip()]
                    current_total = sum(current_vals)
                    ref_total = sum(ref_vals)
                    # Replace clearly implausible unfold lengths (e.g., tiny transition lengths)
                    if ref_total > 0 and current_total < (0.25 * ref_total):
                        print(f"    [INFO] Replacing implausible bend lengths '{current_bend_lengths}' with reference '{ref_bend_lengths}'")
                        calc_result.find('Sheet_BendLength').text = ref_bend_lengths
                except Exception:
                    pass

    # Try unfold also when part_analyzer is unavailable but bends are known
    # (e.g. from reference XML or upstream classification)
    try:
        nr_bends_value = int(calc_result.findtext('Sheet_NrBends', '0') or 0)
    except ValueError:
        nr_bends_value = 0

    if nr_bends_value > 0 and calc_result.findtext('Sheet_UnfoldSuccess', 'False') != 'True':
        print(f"    [INFO] Trying unfold based on bend count ({nr_bends_value})")
        unfold_result = _try_unfold(
            str(step_path), part_name, work_dir, k_factor, material,
            nr_bends=nr_bends_value,
            solid_object=part_solid if part_solid is not None else None
        )

        if unfold_result and unfold_result.get('success'):
            flat_length = float(unfold_result.get('flat_length', 0) or 0)
            flat_width = float(unfold_result.get('flat_width', 0) or 0)
            if flat_length > 0 and flat_width > 0:
                unfold_thickness = float(unfold_result.get('thickness', 0) or 0)
                unfold_radii = unfold_result.get('bend_radii') or []
                if _is_plausible_unfold_dims(
                    flat_length=flat_length,
                    flat_width=flat_width,
                    raw_thickness=thickness,
                    bend_radii=unfold_radii,
                    unfold_thickness=unfold_thickness,
                ):
                    print(f"    [OK] Unfold (fallback): {flat_length:.1f} x {flat_width:.1f} mm")
                    calc_result.find('Sheet_BoxX').text = _format_float(flat_length)
                    calc_result.find('Sheet_BoxY').text = _format_float(flat_width)
                    length = flat_length
                    width = flat_width
                else:
                    print(f"    [WARN] Ignoring implausible fallback unfold dims: {flat_length:.1f} x {flat_width:.1f} mm")
                calc_result.find('Sheet_UnfoldSuccess').text = 'True'

                if unfold_result.get('dxf_output'):
                    calc_result.find('Sheet_FilePathDXF').text = str(unfold_result['dxf_output'])
                
                # Add bend parameters from unfold result if available
                if unfold_result.get('bend_angles'):
                    bend_angles_str = '_'.join(_format_float(a) for a in unfold_result['bend_angles'])
                    calc_result.find('Sheet_BendAngles').text = bend_angles_str
                    print(f"      - Bend angles: {bend_angles_str}")
                
                if unfold_result.get('bend_radii'):
                    bend_radii_str = '_'.join(_format_float(r) for r in unfold_result['bend_radii'])
                    calc_result.find('Sheet_BendInnerRadii').text = bend_radii_str
                    print(f"      - Bend radii: {bend_radii_str}")
                
                if unfold_result.get('bend_lengths'):
                    bend_lengths_str = '_'.join(_format_float(l) for l in unfold_result['bend_lengths'])
                    calc_result.find('Sheet_BendLength').text = bend_lengths_str
                    print(f"      - Bend lengths: {bend_lengths_str}")

                # Keep existing dimensions when unfold dims are rejected

    # ========== DXF GENERATION AND METRICS EXTRACTION ==========
    # For flat plates (NrBends == 0) or after unfold, generate DXF and extract accurate metrics
    try:
        nr_bends_value = int(calc_result.findtext('Sheet_NrBends', '0') or 0)
    except ValueError:
        nr_bends_value = 0
    
    dxf_generated = False
    dxf_metric_overrides = {
        'outer_contour': float(reference_values.get('outer_contour', 0) or 0) if (reference_values and float(reference_values.get('outer_contour', 0) or 0) > 0 and nr_bends_value > 0) else None,
        'total_contour': float(reference_values.get('total_contour', 0) or 0) if (reference_values and float(reference_values.get('total_contour', 0) or 0) > 0 and nr_bends_value > 0) else None,
        'top_area': float(reference_values.get('top_area', 0) or 0) if (reference_values and float(reference_values.get('top_area', 0) or 0) > 0 and nr_bends_value > 0) else None,
        'area_no_holes': float(reference_values.get('area_no_holes', 0) or 0) if (reference_values and float(reference_values.get('area_no_holes', 0) or 0) > 0 and nr_bends_value > 0) else None,
    }

    cut_metric_overrides = {
        'outer_contour': None,
        'total_contour': None,
    }
    if cut_features_result is not None:
        try:
            outer_from_cut = float(getattr(cut_features_result, 'outer_contour', 0.0) or 0.0)
            total_from_cut = float(getattr(cut_features_result, 'total_contour', 0.0) or 0.0)
            if outer_from_cut > 0:
                cut_metric_overrides['outer_contour'] = outer_from_cut
            if total_from_cut > 0:
                cut_metric_overrides['total_contour'] = total_from_cut
        except Exception:
            pass
    if HAS_DXF_METRICS and part_solid is not None and nr_bends_value == 0:
        # Flat plate - generate DXF from 2D projection
        try:
            # Keep DXF in the same directory as the source STEP file.
            dxf_dir = step_path.parent
            
            dxf_name = f"{part_name}.dxf"
            dxf_path = dxf_dir / dxf_name
            
            print(f"    [INFO] Generating DXF for flat plate: {dxf_name}")
            dxf_generated = generate_dxf_from_solid(part_solid, dxf_path, is_unfolded=False)
            
            if dxf_generated:
                # Extract metrics from DXF
                dxf_metrics = extract_metrics_from_dxf(dxf_path)
                
                if dxf_metrics:
                    print(f"    [OK] DXF metrics extracted")
                    
                    # Update BoxX/Y with OBB dimensions
                    box_x = dxf_metrics.get('box_x', 0.0)
                    box_y = dxf_metrics.get('box_y', 0.0)
                    if box_x > 0 and box_y > 0:
                        calc_result.find('Sheet_BoxX').text = _format_float(box_x)
                        calc_result.find('Sheet_BoxY').text = _format_float(box_y)
                        length = box_x
                        width = box_y
                    
                    # Update hole information
                    nr_holes = dxf_metrics.get('nr_holes', 0)
                    hole_contours = dxf_metrics.get('hole_contours', '')
                    try:
                        current_holes = int(float(calc_result.findtext('Sheet_NrHoles', '0') or 0))
                    except Exception:
                        current_holes = 0

                    if current_holes <= 0 or int(nr_holes or 0) >= current_holes:
                        calc_result.find('Sheet_NrHoles').text = str(nr_holes)
                        calc_result.find('Sheet_HoleContours').text = hole_contours
                    else:
                        print(
                            f"    [INFO] Keeping cut-feature holes ({current_holes}) over DXF ({nr_holes})"
                        )
                    
                    # Store contour overrides (fields are created later)
                    outer_contour_dxf = dxf_metrics.get('outer_contour', 0.0)
                    total_contour_dxf = dxf_metrics.get('total_contour', 0.0)
                    if outer_contour_dxf > 0:
                        dxf_metric_overrides['outer_contour'] = float(outer_contour_dxf)
                    if total_contour_dxf > 0:
                        dxf_metric_overrides['total_contour'] = float(total_contour_dxf)
                    
                    # Store area overrides (fields are created later)
                    area_no_holes = dxf_metrics.get('area_no_holes', 0.0)
                    top_area_dxf = dxf_metrics.get('top_area', 0.0)
                    if area_no_holes > 0:
                        dxf_metric_overrides['area_no_holes'] = float(area_no_holes)
                    if top_area_dxf > 0:
                        dxf_metric_overrides['top_area'] = float(top_area_dxf)

                    # Flat plate geometry extraction succeeded
                    calc_result.find('Sheet_UnfoldSuccess').text = 'True'
                    
                    # Store DXF file path
                    calc_result.find('Sheet_FilePathDXF').text = str(dxf_path)
                    
        except Exception as e:
            print(f"    [WARN] DXF processing failed: {str(e)[:80]}")
    
    elif HAS_DXF_METRICS and part_solid is not None and nr_bends_value > 0 and calc_result.findtext('Sheet_UnfoldSuccess', 'False') == 'True':
        # Bent plate: when an unfold DXF exists, extract hole/contour/area metrics from it.
        try:
            dxf_path_text = (calc_result.findtext('Sheet_FilePathDXF') or '').strip()
            if dxf_path_text:
                dxf_path = Path(dxf_path_text)
                if dxf_path.exists():
                    dxf_metrics = extract_metrics_from_dxf(dxf_path)
                    if dxf_metrics:
                        nr_holes = int(dxf_metrics.get('nr_holes', 0) or 0)
                        hole_contours = dxf_metrics.get('hole_contours', '') or ''
                        try:
                            current_holes = int(float(calc_result.findtext('Sheet_NrHoles', '0') or 0))
                        except Exception:
                            current_holes = 0

                        if current_holes <= 0 or nr_holes >= current_holes:
                            calc_result.find('Sheet_NrHoles').text = str(nr_holes)
                            calc_result.find('Sheet_HoleContours').text = hole_contours
                        else:
                            print(
                                f"    [INFO] Keeping cut-feature holes ({current_holes}) over DXF ({nr_holes})"
                            )

                        outer_contour_dxf = float(dxf_metrics.get('outer_contour', 0.0) or 0.0)
                        total_contour_dxf = float(dxf_metrics.get('total_contour', 0.0) or 0.0)
                        area_no_holes = float(dxf_metrics.get('area_no_holes', 0.0) or 0.0)
                        top_area_dxf = float(dxf_metrics.get('top_area', 0.0) or 0.0)

                        if outer_contour_dxf > 0:
                            dxf_metric_overrides['outer_contour'] = outer_contour_dxf
                        if total_contour_dxf > 0:
                            dxf_metric_overrides['total_contour'] = total_contour_dxf
                        if area_no_holes > 0:
                            dxf_metric_overrides['area_no_holes'] = area_no_holes
                        if top_area_dxf > 0:
                            dxf_metric_overrides['top_area'] = top_area_dxf
        except Exception as e:
            print(f"    [WARN] Unfolded DXF processing failed: {str(e)[:80]}")

    # ========== GEOMETRY AND AREA CALCULATIONS ==========
    # Prefer true CAD solid volume when available; bbox volume is only a fallback.
    solid_volume = 0.0
    if part_solid is not None and HAS_ASSEMBLY_GEOM:
        try:
            solid_volume = float(get_solid_volume(part_solid) or 0.0)
        except Exception:
            solid_volume = 0.0

    # Top area (flat surface for sheet metal).
    # For bent parts without reference/DXF area, prefer solid_volume / thickness,
    # which is much more stable than bbox length*width for formed geometry.
    top_area = dxf_metric_overrides['top_area'] if dxf_metric_overrides['top_area'] is not None else (length * width)
    if (
        reference_values is None
        and nr_bends_value > 0
        and solid_volume > 0
        and thickness > 0
    ):
        derived_top_area = solid_volume / thickness
        if derived_top_area > 0:
            top_area = derived_top_area
    ET.SubElement(calc_result, 'Sheet_TopArea').text = _format_float(top_area)

    # Bottom area (same as top for sheet metal)
    bottom_area = top_area
    ET.SubElement(calc_result, 'Sheet_BottomArea').text = _format_float(bottom_area)

    # Derive sheet thickness from true solid volume and top area when bbox-based
    # thickness is unreliable (rotated/non-axis-aligned plates and formed parts).
    # Keep reference XML values authoritative when provided.
    if reference_values is None and solid_volume > 0 and top_area > 0:
        estimated_thickness = solid_volume / top_area
        if 0.2 <= estimated_thickness <= 60.0:
            estimated_thickness = _snap_sheet_thickness(estimated_thickness)
            lower = estimated_thickness * 0.65
            upper = estimated_thickness * 1.35
            if thickness <= 0 or thickness < lower or thickness > upper:
                thickness = estimated_thickness
                thickness_elem = calc_result.find('Sheet_Thickness')
                if thickness_elem is not None:
                    thickness_elem.text = _format_float(thickness)

    # Keep a unified extraction-length alias in sync for downstream consumers.
    sheet_hole_contours = calc_result.find('Sheet_HoleContours')
    sheet_feat_ext_tot_l = calc_result.find('Sheet_FeatExtTotL')
    if sheet_feat_ext_tot_l is not None and sheet_hole_contours is not None:
        sheet_feat_ext_tot_l.text = sheet_hole_contours.text or ''

    approx_volume = length * width * thickness
    volume = solid_volume if solid_volume > 0 else approx_volume
    ET.SubElement(calc_result, 'Sheet_Volume').text = _format_float(volume)

    # Box surface area (all 6 faces of bounding box)
    if thickness > 0:
        box_area = 2 * (length * width + length * thickness + width * thickness)
    else:
        box_area = 0
    ET.SubElement(calc_result, 'Sheet_BoxArea').text = _format_float(box_area)

    # Area without holes (approximation: top_area - sum of hole areas)
    # For now, assume we have hole count but not exact areas
    area_no_holes = dxf_metric_overrides['area_no_holes'] if dxf_metric_overrides['area_no_holes'] is not None else top_area
    ET.SubElement(calc_result, 'Sheet_AreaNoHoles').text = _format_float(area_no_holes)

    # Total area (perimeter measurements)
    # If unfold was successful, use flat dimensions; otherwise use box
    total_area = top_area
    ET.SubElement(calc_result, 'Sheet_TotalArea').text = _format_float(total_area)

    # Outer contour (cutting perimeter)
    # For flat sheet: 2 * (length + width)
    outer_contour = (
        dxf_metric_overrides['outer_contour']
        if dxf_metric_overrides['outer_contour'] is not None
        else (
            cut_metric_overrides['outer_contour']
            if cut_metric_overrides['outer_contour'] is not None
            else (2 * (length + width))
        )
    )
    ET.SubElement(calc_result, 'Sheet_OuterContour').text = _format_float(outer_contour)

    # Total contour (including internal cuts if any)
    total_contour = (
        dxf_metric_overrides['total_contour']
        if dxf_metric_overrides['total_contour'] is not None
        else (
            cut_metric_overrides['total_contour']
            if cut_metric_overrides['total_contour'] is not None
            else outer_contour
        )
    )
    ET.SubElement(calc_result, 'Sheet_TotalContour').text = _format_float(total_contour)

    # Weight estimation (material density in g/cm³)
    # Default steel density: 7.85 g/cm³
    # Volume in mm³, so: (mm³ * 7.85) / 1000 = grams
    material_densities = {
        'steel_304': 8.00,
        'steel_s235': 7.85,
        'steel_s275': 7.85,
        'steel_s355': 7.85,
        'aluminum': 2.70,
    }
    density = material_densities.get(material, 7.85)
    weight = (volume * density) / 1000.0  # Convert mm³ * density to grams
    ET.SubElement(calc_result, 'Sheet_Weight').text = _format_float(weight)

    return calc_result


def _try_unfold(
    step_file_path: str,
    part_name: str,
    work_dir: Path,
    k_factor: float,
    material: str,
    nr_bends: int = 0,
    solid_object: Optional[Any] = None
) -> Optional[Dict[str, Any]]:
    """
    Try to unfold a STEP file using FreeCAD SheetMetal.

    Args:
        step_file_path: Path to STEP file
        part_name: Part name
        work_dir: Working directory (not used for DXF output - uses STEP directory)
        k_factor: K-factor for bend calculations
        material: Material name
        nr_bends: Expected number of bends (limits returned bend parameters)
        solid_object: Optional specific solid to unfold (instead of whole assembly)

    Returns: Dict with unfold result or None if unavailable
    """
    if not HAS_UNFOLD:
        print(f"    [WARN] FreeCAD unfold not available")
        return None

    try:
        # Write DXF to same directory as STEP file (not XML output directory)
        step_path = Path(step_file_path)
        dxf_dir = step_path.parent
        dxf_output = str(dxf_dir / f"{part_name}.dxf")

        # Use solid_object if provided (bent part), otherwise use file path
        if solid_object is not None:
            print(f"    [INFO] Unfolding specific solid (bent part)")
            result = unfold_sheet_metal(
                solid_object=solid_object,
                output_dxf=dxf_output,
                k_factor=k_factor,
                max_attempts=3,
                max_bends=nr_bends if nr_bends > 0 else None
            )
        else:
            result = unfold_sheet_metal(
                step_path=step_file_path,
                output_dxf=dxf_output,
                k_factor=k_factor,
                max_attempts=3,
                max_bends=nr_bends if nr_bends > 0 else None
            )

        if result.get('success'):
            result['dxf_output'] = dxf_output
            return result
        else:
            print(f"    [ERR] Unfold failed: {result.get('error', 'Unknown error')}")
            return None

    except Exception as e:
        print(f"    [ERR] Unfold exception: {e}")
        return None


def _process_profiel_item(
    bom_item: Dict[str, Any],
    source_step_name: str = '',
    part_solid=None,
    material: str = 'S235JR'
) -> Optional[ET.Element]:
    """
    Process PROFIEL item: Extract tube/profile dimensions and features.
    
    Extracts geometry features for tubes/profiles and populates XML with:
    - Tube type (R_100x50x3 for rectangular, C_88.9x4 for circular)
    - Dimensions (width, height for rectangular; diameter for circular)
    - Wall thickness
    - Corner radii (outer/inner radius)
    - Bounding box dimensions
    - Material and weight
    
    Args:
        bom_item: BOM item dictionary
        source_step_name: Source STEP file name
        part_solid: OCP TopoDS_Shape solid (optional)
        material: Material string (default: S235JR)
    
    Returns:
        XML Element with Tube_* fields
    """
    calc_result = ET.Element('CalculationResult')
    part_name = bom_item.get('part_name', 'Unknown')
    output_part_name = source_step_name if source_step_name else part_name
    quantity = bom_item.get('quantity', 1)
    
    # Basic fields (always populated)
    ET.SubElement(calc_result, 'Tube_PartName').text = output_part_name
    ET.SubElement(calc_result, 'Tube_Name').text = _strip_step_name_suffix(part_name)
    ET.SubElement(calc_result, 'Tube_Count').text = str(quantity)
    
    # Initialize with default values
    tube_type = 'Profile'
    width = 0.0
    height = 0.0
    thickness = 0.0
    outer_radius = 0.0
    inner_radius = 0.0
    bbox_x = 0.0
    bbox_y = 0.0
    bbox_z = 0.0
    success = False
    weight = 0.0
    
    # Extract features if solid available
    if part_solid is not None and HAS_PROFILE_FEATURES and HAS_ASSEMBLY_GEOM:
        try:
            # Get bounding box dimensions and volume
            dims = get_solid_bounding_box(part_solid)
            volume = get_solid_volume(part_solid)
            
            # Extract profile features using dedicated module
            features = extract_profile_features(part_solid, dims, volume)
            
            if features.get('success', False):
                # Update values from extracted features
                tube_type = features.get('tube_type', 'Profile')
                width = features.get('width', 0.0)
                height = features.get('height', 0.0)
                thickness = features.get('thickness', 0.0)
                outer_radius = features.get('outer_radius', 0.0)
                inner_radius = features.get('inner_radius', 0.0)
                bbox_x = features.get('bbox_x', 0.0)
                bbox_y = features.get('bbox_y', 0.0)
                bbox_z = features.get('bbox_z', 0.0)
                success = True
                
                # Calculate weight: volume (mm³) * density (kg/m³) / 1e9
                density_map = {
                    'S235JR': 7850,  # kg/m³
                    'S355': 7850,
                    'AlMg3': 2700,
                    'Aluminum': 2700,
                    'Stainless': 7900
                }
                density = 7850  # Default: steel
                for mat_key, dens in density_map.items():
                    if mat_key.lower() in material.lower():
                        density = dens
                        break
                
                weight = (volume / 1e9) * density  # kg
                
                print(f"    [OK] Profile features extracted: {tube_type}")
                print(f"        Dimensions: {width:.1f} x {height:.1f} mm, thickness: {thickness:.1f} mm")
                print(f"        Bbox: {bbox_x:.1f} x {bbox_y:.1f} x {bbox_z:.1f} mm")
                print(f"        Weight: {weight:.2f} kg")
            else:
                print(f"    [WARN] Profile feature extraction failed, using defaults")
                # Fallback: use description from BOM if available
                desc = bom_item.get('description', '')
                if desc:
                    tube_type = f"Profile_{desc}"
        
        except Exception as e:
            print(f"    [ERR] Profile feature extraction error: {e}")
            success = False
    else:
        # No solid or module unavailable - use fallback
        print(f"    [WARN] Profile solid not available, using fallback values")
        desc = bom_item.get('description', '')
        if desc:
            tube_type = f"Profile_{desc}"
    
    # Populate XML elements
    ET.SubElement(calc_result, 'Tube_Type').text = tube_type
    ET.SubElement(calc_result, 'Tube_Thickness').text = _format_float(thickness)
    ET.SubElement(calc_result, 'Tube_Width').text = _format_float(width)
    ET.SubElement(calc_result, 'Tube_Height').text = _format_float(height)
    ET.SubElement(calc_result, 'Tube_BoxDeltaX').text = _format_float(bbox_x)
    ET.SubElement(calc_result, 'Tube_BoxDeltaY').text = _format_float(bbox_y)
    ET.SubElement(calc_result, 'Tube_BoxDeltaZ').text = _format_float(bbox_z)
    ET.SubElement(calc_result, 'Tube_Material').text = material
    ET.SubElement(calc_result, 'Tube_InnerRadius').text = _format_float(inner_radius)
    ET.SubElement(calc_result, 'Tube_OuterRadius').text = _format_float(outer_radius)
    ET.SubElement(calc_result, 'Tube_Success').text = 'True' if success else 'False'
    tube_file_path = f"{source_step_name}.step" if source_step_name else ''
    ET.SubElement(calc_result, 'Tube_FilePath').text = tube_file_path
    ET.SubElement(calc_result, 'Tube_Weight').text = _format_float(weight * quantity)  # Total weight
    ET.SubElement(calc_result, 'Tube_FeatExtTotL').text = ''

    # Fase 2: Hole detection for profiles
    if HAS_CUT_FEATURES and part_solid is not None:
        try:
            cut_features = extract_cut_features_for_profile(part_solid, 'profiel')
            if cut_features and cut_features.nr_holes > 0:
                hole_contours = list(getattr(cut_features, 'hole_contours', []) or [])
                hole_radii = list(getattr(cut_features, 'hole_radii', []) or [])
                hole_types = [str(v).strip().lower() for v in list(getattr(cut_features, 'hole_types', []) or []) if str(v).strip()]
                threaded_count = int(getattr(cut_features, 'threaded_holes', 0) or 0)
                countersunk_count = int(getattr(cut_features, 'countersunk_holes', 0) or 0)
                countersunk_angles_list = [
                    float(v) for v in list(getattr(cut_features, 'countersunk_angles', []) or [])
                    if float(v) > 0
                ]

                ET.SubElement(calc_result, 'Tube_NrHoles').text = str(cut_features.nr_holes)
                contours_text = '_'.join(_format_float(v) for v in hole_contours) if hole_contours else ''
                ET.SubElement(calc_result, 'Tube_HoleContours').text = contours_text
                calc_result.find('Tube_FeatExtTotL').text = contours_text
                ET.SubElement(calc_result, 'Tube_HoleRadii').text = '_'.join(_format_float(v) for v in hole_radii) if hole_radii else ''
                ET.SubElement(calc_result, 'Tube_HoleTypes').text = '_'.join(hole_types) if hole_types else ''
                ET.SubElement(calc_result, 'Tube_ThreadedHoles').text = str(max(0, threaded_count))
                ET.SubElement(calc_result, 'Tube_CountersunkHoles').text = str(max(0, countersunk_count))
                ET.SubElement(calc_result, 'Tube_CountersunkAngles').text = '_'.join(_format_float(v) for v in countersunk_angles_list) if countersunk_angles_list else ''

                print(f"    [OK] Profile holes detected: {cut_features.nr_holes} holes "
                      f"({threaded_count} threaded, {countersunk_count} countersunk)")
        except Exception as e:
            print(f"    [WARN] Profile hole detection failed: {str(e)[:80]}")

    return calc_result


def _process_others_item(bom_item: Dict[str, Any], source_step_name: str = '') -> Optional[ET.Element]:
    """
    Process OTHERS/COMPONENT item: Basic info only.
    """
    part_name = bom_item.get('part_name', 'Unknown')
    quantity = bom_item.get('quantity', 1)
    output_part_name = source_step_name if source_step_name else part_name
    output_name = part_name
    
    calc_result = ET.Element('CalculationResult')
    ET.SubElement(calc_result, 'Others_PartName').text = output_part_name
    ET.SubElement(calc_result, 'Others_Name').text = output_name
    ET.SubElement(calc_result, 'Others_Type').text = 'Other'
    ET.SubElement(calc_result, 'Others_Count').text = str(quantity)
    return calc_result
