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
    from manufacturing_pipeline.analysis.sheetmetal_analysis import MATERIAL_BEND_PROPERTIES
    HAS_MATERIAL_PROPS = True
except ImportError:
    HAS_MATERIAL_PROPS = False

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
        parse_step_product_names
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


# Configuration for DXF output path - can be overridden
DXF_OUTPUT_BASE_PATH = None  # Default: use same directory as STEP file


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

        ET.SubElement(calc, 'Sheet_HoleContours').text = hole_contours or ''
        ET.SubElement(calc, 'Sheet_HoleRadii').text = hole_radii or ''
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
    reference_xml_path: Optional[str] = None
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
        output_xml_path: Output XML filepath (default: input_file.xml)
        work_dir: Working directory for temp files (default: same as STEP)
        reference_xml_path: Optional existing XML to copy trusted sheet values from

    Returns:
        Path to generated XML file
    """
    if not HAS_CADQUERY:
        raise RuntimeError("CadQuery required for BOM-to-XML export")

    # Setup paths
    step_path = Path(step_file_path)
    if not step_path.exists():
        raise FileNotFoundError(f"STEP file not found: {step_file_path}")

    work_dir = Path(work_dir or step_path.parent)
    work_dir.mkdir(parents=True, exist_ok=True)

    if output_xml_path is None:
        output_xml_path = str(work_dir / f"{step_path.stem}.xml")

    # ==========================================================================
    # NAMING STRATEGY (same logic as export_classification_excel.py)
    # ==========================================================================
    # 1. Try STEP assembly structure names
    # 2. Try PRODUCT_DEFINITION names (deduplicated)
    # 3. Generate: {base_name}-p1, {base_name}-p2, etc.
    
    step_parts = parse_step_assembly_structure(str(step_path)) if HAS_ASSEMBLY_GEOM else None
    step_product_names = None
    
    if not step_parts and HAS_ASSEMBLY_GEOM:
        step_product_names = parse_step_product_names(str(step_path))
        
        # Deduplicate product names: remove _1, _2, _3 suffixes
        if step_product_names:
            unique_names = []
            seen_bases = set()
            for name in step_product_names:
                base_name = re.sub(r'_\d+$', '', name)
                if base_name not in seen_bases:
                    unique_names.append(base_name)
                    seen_bases.add(base_name)
            step_product_names = unique_names
    
    # Base name for generated part names
    base_name = step_path.stem
    used_step_parts = set()
    step_parts_list = list(step_parts.keys()) if step_parts else []
    step_parts_seq_idx = 0
    generated_idx = 1
    product_name_idx = 0
    
    # Apply naming to each BOM item
    for bom_item in bom_list:
        bom_part_name = bom_item.get('part_name', '')
        new_part_name = None

        name_lower = str(bom_part_name or '').strip().lower()
        is_generic_bom_name = (
            not bom_part_name
            or name_lower.startswith('part_')
            or name_lower.startswith('plaatdeel')
            or name_lower.startswith('profieldeel')
            or name_lower.startswith('verspaamd deel')
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
        elif not new_part_name and step_product_names and product_name_idx < len(step_product_names):
            # Use next PRODUCT_DEFINITION name
            new_part_name = step_product_names[product_name_idx]
            product_name_idx += 1
        
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

    # Build representative solids in the same grouping style as assembly analysis
    representative_solids = _build_representative_solids(doc)

    # Process each BOM item
    print(f"\n[XML Export] Processing {len(bom_list)} BOM items...")
    plaat_seq_index = 0  # Track which sheet item in reference sequence we're at
    for idx, bom_item in enumerate(bom_list, 1):
        print(f"\n  [{idx}/{len(bom_list)}] {bom_item.get('part_name', 'Unknown')}")

        part_class = bom_item.get('part_class', 'anders').lower()
        part_solid = representative_solids[idx - 1] if (idx - 1) < len(representative_solids) else None
        
        # Determine sequence index for sheet items (only for plaat class)
        seq_idx = plaat_seq_index if part_class == 'plaat' else None
        reference_values = _get_reference_values_for_part(ref_by_name, ref_by_seq, bom_item.get('part_name', ''), seq_idx)
        
        if part_class == 'plaat':
            plaat_seq_index += 1

        # If baseline XML says this is a sheet item, follow that classification
        if reference_values is not None and part_class != 'plaat':
            print("    [INFO] Override class to 'plaat' from reference XML")
            part_class = 'plaat'

        try:
            if part_class == 'plaat':
                # STAP 1: PLAAT PROCESSING
                calc_result = _process_plaat_item(
                    bom_item,
                    step_path,
                    step_path.stem,
                    work_dir,
                    material,
                    k_factor,
                    part_solid,
                    reference_values,
                )
            elif part_class == 'profiel':
                # STAP 2: PROFIEL PROCESSING (TODO)
                calc_result = _process_profiel_item(bom_item, step_path.stem)
            else:
                # STAP 3: OTHERS
                calc_result = _process_others_item(bom_item)

            if calc_result is not None:
                root.append(calc_result)
                print(f"    [OK] XML element created")

        except Exception as e:
            print(f"    [ERR] Error processing item: {e}")
            import traceback
            traceback.print_exc()
            continue

    # Write XML
    xml_string = _prettify_xml(root)
    output_path = Path(output_xml_path)
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
    """Build representative solids by grouping equal solids (assembly-analysis style)."""
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

        grouped_representatives = []
        for solid in solids:
            found = False
            for rep in grouped_representatives:
                if solids_are_equal(solid, rep):
                    found = True
                    break
            if not found:
                grouped_representatives.append(solid)

        return grouped_representatives
    except Exception:
        return []


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
    output_sheet_name = part_name

    if reference_values is not None:
        ref_sheet_name = str(reference_values.get('sheet_name', '') or '').strip()
        ref_qty = int(float(reference_values.get('qty', quantity) or quantity))

        if ref_sheet_name:
            output_sheet_name = ref_sheet_name
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
    ET.SubElement(calc_result, 'Sheet_HoleRadii').text = ''
    ET.SubElement(calc_result, 'Sheet_UnfoldSuccess').text = 'False'

    # PROACTIVE UNFOLD: Try unfold for all sheet metal parts to detect bends
    # This catches bent sheets that classify as "plaat" via shell detection
    # but don't get flagged as bent by part_analyzer
    early_unfold_attempted = False
    if HAS_UNFOLD and part_solid is not None:
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
                    
                    nr_bends = len(bend_angles) if bend_angles else 0
                    if nr_bends > 0:
                        print(f"    [OK] Unfold: {nr_bends} bends detected")
                        print(f"        Angles: {bend_angles}")
                        print(f"        Radii: {bend_radii}")
                        print(f"        Flat: {unfold_result.get('flat_length', 0):.1f} x {unfold_result.get('flat_width', 0):.1f} mm")
                        
                        calc_result.find('Sheet_NrBends').text = str(nr_bends)
                        calc_result.find('Sheet_BendAngles').text = '_'.join(_format_float(a) for a in bend_angles)
                        calc_result.find('Sheet_BendInnerRadii').text = '_'.join(_format_float(r) for r in bend_radii)
                        calc_result.find('Sheet_BendLength').text = '_'.join(_format_float(l) for l in bend_lengths)
                        flat_length = float(unfold_result.get('flat_length', 0) or 0)
                        flat_width = float(unfold_result.get('flat_width', 0) or 0)
                        min_flat = min(flat_length, flat_width)
                        expected_min = max(2.0, thickness * 3.0) if thickness > 0 else 2.0
                        # Reject clearly implausible unfold dimensions (e.g., one axis collapsing to thickness)
                        if flat_length > 0 and flat_width > 0 and min_flat > expected_min:
                            calc_result.find('Sheet_BoxX').text = _format_float(flat_length)
                            calc_result.find('Sheet_BoxY').text = _format_float(flat_width)
                            length = flat_length
                            width = flat_width
                        else:
                            print(f"    [WARN] Ignoring implausible unfold dims: {flat_length:.1f} x {flat_width:.1f} mm")
                        calc_result.find('Sheet_UnfoldSuccess').text = 'True'
                        
                        # Update thickness from unfold if available
                        if unfold_result.get('thickness'):
                            calc_result.find('Sheet_Thickness').text = _format_float(unfold_result['thickness'])
        except Exception as e:
            print(f"    [WARN] Proactive unfold failed: {str(e)[:60]}")

    # Try to extract detailed features from part geometry via part_analyzer
    # Skip bend detection if already done by proactive unfold
    if HAS_PART_ANALYZER:
        try:
            if part_solid is not None:
                # Analyze geometry for this specific part solid
                analysis = analyze_part_geometry(part_solid, part_name)

                # Check if bent (but skip if already unfolded proactively)
                if not early_unfold_attempted and hasattr(analysis, 'bends') and len(analysis.bends) > 0:
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
                        min_flat = min(flat_length, flat_width)
                        expected_min = max(2.0, thickness * 3.0) if thickness > 0 else 2.0
                        if flat_length > 0 and flat_width > 0 and min_flat > expected_min:
                            print(f"    [OK] Unfold: {flat_length:.1f} x {flat_width:.1f} mm")
                            calc_result.find('Sheet_BoxX').text = _format_float(flat_length)
                            calc_result.find('Sheet_BoxY').text = _format_float(flat_width)
                            length = flat_length
                            width = flat_width
                        else:
                            print(f"    [WARN] Ignoring implausible unfold dims: {flat_length:.1f} x {flat_width:.1f} mm")
                        calc_result.find('Sheet_UnfoldSuccess').text = 'True'
                        
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

            min_flat = min(flat_length, flat_width)
            expected_min = max(2.0, thickness * 3.0) if thickness > 0 else 2.0
            if flat_length > 0 and flat_width > 0:
                if min_flat > expected_min:
                    print(f"    [OK] Unfold (fallback): {flat_length:.1f} x {flat_width:.1f} mm")
                    calc_result.find('Sheet_BoxX').text = _format_float(flat_length)
                    calc_result.find('Sheet_BoxY').text = _format_float(flat_width)
                    length = flat_length
                    width = flat_width
                else:
                    print(f"    [WARN] Ignoring implausible fallback unfold dims: {flat_length:.1f} x {flat_width:.1f} mm")
                calc_result.find('Sheet_UnfoldSuccess').text = 'True'
                
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
    if HAS_DXF_METRICS and part_solid is not None and nr_bends_value == 0:
        # Flat plate - generate DXF from 2D projection
        try:
            # Determine DXF output path (use STEP directory or configured base path)
            if DXF_OUTPUT_BASE_PATH:
                dxf_dir = Path(DXF_OUTPUT_BASE_PATH)
            else:
                dxf_dir = step_path.parent
            
            dxf_name = f"{step_path.stem}_{part_name}_flat.dxf"
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
                    calc_result.find('Sheet_NrHoles').text = str(nr_holes)
                    calc_result.find('Sheet_HoleContours').text = hole_contours
                    
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
                    
        except Exception as e:
            print(f"    [WARN] DXF processing failed: {str(e)[:80]}")
    
    elif HAS_DXF_METRICS and part_solid is not None and nr_bends_value > 0 and calc_result.findtext('Sheet_UnfoldSuccess', 'False') == 'True':
        # Unfolded plate - generate DXF from unfolded state
        try:
            # Use same DXF generation for unfolded (no FreeCAD unfold output available here)
            # This is for future use if we capture unfolded solids
            pass
        except Exception as e:
            print(f"    [WARN] Unfolded DXF processing failed: {str(e)[:80]}")

    # ========== GEOMETRY AND AREA CALCULATIONS ==========
    # Volume and area calculations based on bounding box dimensions
    volume = length * width * thickness
    ET.SubElement(calc_result, 'Sheet_Volume').text = _format_float(volume)

    # Top area (flat surface for sheet metal)
    top_area = dxf_metric_overrides['top_area'] if dxf_metric_overrides['top_area'] is not None else (length * width)
    ET.SubElement(calc_result, 'Sheet_TopArea').text = _format_float(top_area)

    # Bottom area (same as top for sheet metal)
    bottom_area = top_area
    ET.SubElement(calc_result, 'Sheet_BottomArea').text = _format_float(bottom_area)

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
    outer_contour = dxf_metric_overrides['outer_contour'] if dxf_metric_overrides['outer_contour'] is not None else (2 * (length + width))
    ET.SubElement(calc_result, 'Sheet_OuterContour').text = _format_float(outer_contour)

    # Total contour (including internal cuts if any)
    total_contour = dxf_metric_overrides['total_contour'] if dxf_metric_overrides['total_contour'] is not None else outer_contour
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
        work_dir: Working directory
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
        dxf_output = str(work_dir / f"{part_name}_flat.dxf")

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


def _process_profiel_item(bom_item: Dict[str, Any], source_step_name: str = '') -> Optional[ET.Element]:
    """
    Process PROFIEL item: Extract dimensions and features.
    TODO: Implement in STAP 2
    """
    calc_result = ET.Element('CalculationResult')
    part_name = bom_item.get('part_name', 'Unknown')
    output_part_name = source_step_name if source_step_name else part_name
    ET.SubElement(calc_result, 'Tube_PartName').text = output_part_name
    ET.SubElement(calc_result, 'Tube_Name').text = part_name
    ET.SubElement(calc_result, 'Tube_Type').text = 'Profile'
    ET.SubElement(calc_result, 'Tube_Count').text = str(bom_item.get('quantity', 1))
    # TODO: Add more fields
    return calc_result


def _process_others_item(bom_item: Dict[str, Any]) -> Optional[ET.Element]:
    """
    Process OTHERS/COMPONENT item: Basic info only.
    """
    calc_result = ET.Element('CalculationResult')
    ET.SubElement(calc_result, 'Others_PartName').text = bom_item.get('part_name', 'Unknown')
    ET.SubElement(calc_result, 'Others_Name').text = bom_item.get('part_name', 'Unknown')
    ET.SubElement(calc_result, 'Others_Type').text = 'Other'
    ET.SubElement(calc_result, 'Others_Count').text = str(bom_item.get('quantity', 1))
    return calc_result
