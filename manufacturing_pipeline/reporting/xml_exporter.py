"""XML export functionality for AutoPOL/Spaceclaim compatibility.

This module exports analysis results to XML format compatible with
ALES ERP system and Spaceclaim/AutoPOL format.
"""

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, Any, Optional
from xml.dom import minidom


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
