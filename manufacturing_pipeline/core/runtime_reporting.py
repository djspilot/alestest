"""Extracted runtime functions from runtime_functions.py."""

import os
import sys
import math
import json
import subprocess

from manufacturing_pipeline.core.config import SystemConfig

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
CONFIG_DIR = os.path.join(DATA_DIR, "config")
DB_DIR = os.path.join(DATA_DIR, "db")
PARTS_DIR = os.path.join(DATA_DIR, "input")
OUTPUT_DIR = os.path.join(DATA_DIR, "output")
PIPELINE_DIR = os.path.join(PROJECT_ROOT, "manufacturing_pipeline")
SCRIPTS_DIR = os.path.join(PIPELINE_DIR, "scripts")

FREECAD_PYTHON = SystemConfig.from_env().freecad_python
HOST_PYTHON = sys.executable

if PIPELINE_DIR not in sys.path:
    sys.path.insert(0, PIPELINE_DIR)
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

def run_aag_analysis(step_file):
    """Run AAG (Attributed Adjacency Graph) analysis via FreeCAD subprocess.

    Returns dict with AAG analysis results including:
    - hole_count, bend_count, slot_count
    - thickness detection
    - cut length and laser cut time estimation
    - isoperimetric quotients for hole classification
    """
    # Get system config for paths
    sys_config = SystemConfig.from_env()
    fc_lib = sys_config.freecad_lib
    fc_mod = sys_config.freecad_mod

    # Build the analysis script
    aag_script = f'''
import sys
import os
import platform
import json

# FreeCAD paths
freecad_lib = "{fc_lib}"
freecad_mod = "{fc_mod}"

if platform.system() == "Darwin":
    freecad_user_mod = os.path.expanduser("~/Library/Application Support/FreeCAD/Mod")
else:
    freecad_user_mod = os.path.expanduser("~/.local/share/FreeCAD/Mod")

sys.path.insert(0, freecad_lib)
sys.path.insert(0, freecad_mod)
sys.path.insert(0, freecad_user_mod)
sys.path.insert(0, "{SCRIPTS_DIR}")

import FreeCAD
import Part

# Import AAG analyzer
from aag_analyzer import AAGAnalyzer

# Load STEP file
shape = Part.Shape()
shape.read("{step_file}")

# Run AAG analysis
analyzer = AAGAnalyzer()
result = analyzer.analyze(shape)

# Convert to JSON-serializable dict
output = {{
    "success": True,
    "part_type": result.part_type,
    "hole_count": result.hole_count,
    "bend_count": result.bend_count,
    "counter_bend_count": result.counter_bend_count,
    "slot_count": result.slot_count,
    "thickness": result.thickness,
    "cut_length": result.cut_length,
    "total_cut_length": result.total_cut_length,
    "pierce_count": result.pierce_count,
    "face_count": result.face_count,
    "edge_count": result.edge_count,
    "skin_faces": result.skin_faces,
    "thickness_faces": result.thickness_faces,
    "production_bend_count": len(result.production_bends),
    "all_bend_count": len(result.bends),
    "holes_detail": [],
    "bends_detail": [],
}}

# Add hole details
for h in result.holes[:20]:  # Limit to 20
    output["holes_detail"].append({{
        "type": h.hole_type.value if hasattr(h.hole_type, 'value') else str(h.hole_type),
        "diameter": h.diameter,
        "perimeter": h.perimeter,
        "isoperimetric_quotient": h.isoperimetric_quotient,
    }})

# Add bend details (only production bends)
for b in result.production_bends[:20]:  # Limit to 20
    output["bends_detail"].append({{
        "type": b.bend_type.value if hasattr(b.bend_type, 'value') else str(b.bend_type),
        "angle": b.bend_angle,
        "radius": b.bend_radius,
        "length": b.bend_length,
        "k_factor": b.k_factor,
        "bend_allowance": b.bend_allowance,
        "bend_deduction": b.bend_deduction,
    }})

print("AAG_RESULT:" + json.dumps(output))
'''

    try:
        result = subprocess.run(
            [FREECAD_PYTHON, "-c", aag_script],
            capture_output=True,
            text=True,
            timeout=300
        )

        # Parse result
        for line in result.stdout.split('\n'):
            if line.startswith('AAG_RESULT:'):
                json_str = line[len('AAG_RESULT:'):]
                return json.loads(json_str)

        # Check for errors
        if result.returncode != 0:
            return {"success": False, "error": "AAG analysis failed", "details": result.stderr[-500:] if result.stderr else ""}

        return {"success": False, "error": "No result returned"}

    except subprocess.TimeoutExpired:
        return {"success": False, "error": "AAG analysis timeout (>300s)"}
    except Exception as e:
        return {"success": False, "error": str(e)}



def run_debug(step_file):
    """Debug mode - detailed hole detection analysis."""
    from manufacturing_pipeline.analysis.step_processing import load_step_file, debug_hole_detection

    print(f"\n{'='*60}")
    print(f"DEBUG: HOLE DETECTION ANALYSIS")
    print(f"{'='*60}")
    print(f"File: {step_file}\n")

    print("Loading STEP file...")
    shape = load_step_file(step_file)
    print("Analyzing cylindrical faces...\n")

    debug = debug_hole_detection(shape)

    print(f"Total faces in model: {debug['total_faces']}")
    print(f"Cylindrical faces found: {len(debug['cylindrical_faces'])}")
    print(f"Internal (hole candidates): {len(debug['candidates'])}")
    print(f"External (rejected): {len(debug['rejected_faces'])}")
    print(f"Final holes detected: {len(debug['final_holes'])}")

    if debug['cylindrical_faces']:
        print(f"\n{'='*60}")
        print("ALL CYLINDRICAL FACES:")
        print(f"{'='*60}")
        for f in debug['cylindrical_faces']:
            status = "HOLE CANDIDATE" if f['is_internal'] else "REJECTED (external)"
            print(f"  Face {f['face_index']:3d}: Ø{f['diameter']:8.2f}mm | {f['orientation']:8s} | {f['angle_deg']:6.1f}° | {status}")

    if debug['rejected_faces']:
        print(f"\n{'='*60}")
        print("REJECTED FACES:")
        print(f"{'='*60}")
        for f in debug['rejected_faces']:
            print(f"  Ø{f['diameter']:.2f}mm - {f['reason']}")

    if debug['final_holes']:
        print(f"\n{'='*60}")
        print("DETECTED HOLES:")
        print(f"{'='*60}")
        for h in debug['final_holes']:
            print(f"  Ø{h['diameter']:.2f}mm, depth={h['depth']:.2f}mm")
    else:
        print(f"\n{'='*60}")
        print("NO HOLES DETECTED!")
        print(f"{'='*60}")
        if not debug['cylindrical_faces']:
            print("  -> No cylindrical faces in model")
        elif not debug['candidates']:
            print("  -> All cylinders are external (FORWARD orientation)")
        else:
            print("  -> Candidates filtered out (angle < 270°)")



def generate_compact_pdf(step_file, output_dir, part_name, analysis, total_holes, unfold_result=None):
    """Generate a compact 1-page A4 PDF report."""
    # Fallback: try to get unfold_result from analysis object if not provided
    if unfold_result is None:
        unfold_result = getattr(analysis, 'unfold_result', None)

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, HRFlowable
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    import datetime
    from svglib.svglib import svg2rlg
    from manufacturing_pipeline.analysis.step_processing import load_step_file
    import cadquery as cq

    # Prepare images
    image_dir = os.path.join(output_dir, "images")
    os.makedirs(image_dir, exist_ok=True)
    
    svg_path = os.path.join(image_dir, f"{part_name}.svg")
    flat_svg_path = os.path.join(image_dir, f"{part_name}_flat.svg")

    # Generate 3D SVG
    try:
        shape = load_step_file(step_file)
        cq.exporters.export(
            shape,
            svg_path,
            opt={
                "width": 300,
                "height": 300,
                "marginLeft": 10,
                "marginTop": 10,
                "showAxes": False,
                "projectionDir": (1, 1, 1),
                "strokeWidth": 0.5,
            }
        )
    except Exception as e:
        print(f"  Warning: Could not generate 3D SVG: {e}")

    # Generate Flat Pattern SVG
    flat_step_path = getattr(analysis, 'flat_step_path', None)
    if flat_step_path and os.path.exists(flat_step_path):
        try:
            flat_shape = load_step_file(flat_step_path)
            
            # Determine optimal projection direction (largest face normal)
            proj_dir = (0, 0, 1) # Default
            try:
                faces = flat_shape.faces().vals()
                if faces:
                    largest_face = max(faces, key=lambda f: f.Area())
                    normal = largest_face.normalAt(largest_face.Center())
                    proj_dir = (normal.x, normal.y, normal.z)
            except Exception as e:
                print(f"  Warning: Could not determine flat face normal: {e}")

            cq.exporters.export(
                flat_shape,
                flat_svg_path,
                opt={
                    "width": 300,
                    "height": 300,
                    "marginLeft": 10,
                    "marginTop": 10,
                    "showAxes": False,
                    "projectionDir": proj_dir,
                    "strokeWidth": 0.5,
                }
            )
            print(f"  Generated flat pattern SVG: {flat_svg_path}")
        except Exception as e:
            print(f"  Warning: Could not generate flat SVG: {e}")
    
    # PDF Setup
    pdf_path = os.path.join(output_dir, f"{part_name}_report.pdf")
    doc = SimpleDocTemplate(pdf_path, pagesize=A4,
                           leftMargin=10*mm, rightMargin=10*mm,
                           topMargin=10*mm, bottomMargin=10*mm)

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=16, alignment=TA_CENTER, spaceAfter=2)
    subtitle_style = ParagraphStyle('Subtitle', parent=styles['Normal'], fontSize=10, alignment=TA_CENTER, textColor=colors.grey)
    header_style = ParagraphStyle('Header', parent=styles['Heading3'], fontSize=10, textColor=colors.HexColor('#2c3e50'), spaceBefore=5, spaceAfter=2)
    normal_style = ParagraphStyle('Normal', parent=styles['Normal'], fontSize=9, leading=11)
    small_style = ParagraphStyle('Small', parent=styles['Normal'], fontSize=8, leading=10)
    
    elements = []
    
    # --- Header ---
    date_str = datetime.datetime.now().strftime("%d-%m-%Y %H:%M")
    elements.append(Paragraph(f"PRODUCTIE ANALYSE: {part_name}", title_style))
    elements.append(Paragraph(f"Datum: {date_str} | Bestand: {os.path.basename(step_file)}", subtitle_style))
    elements.append(Spacer(1, 3*mm))
    elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#3498db')))
    elements.append(Spacer(1, 5*mm))

    # --- Main Layout (2 Columns) ---
    
    # 1. Classification Data
    part_category = getattr(analysis, 'part_category', "ONBEKEND")
    if not part_category:
        if analysis.is_profile: part_category = "PROFIEL"
        elif analysis.bend_count_erp > 0: part_category = "GEBOGEN PLAATWERK"
        else: part_category = "PLAAT (vlak)"

    class_data = [
        ["CLASSIFICATIE", ""],
        ["Categorie", part_category],
        ["Type", analysis.part_type.value.upper()],
        ["Materiaal", "Staal (aanname)"],
        ["Dikte", f"{analysis.thickness:.2f} mm"]
    ]
    
    # 2. Dimensions Data
    dim_data = [
        ["AFMETINGEN", ""],
        ["Bounding Box", f"{analysis.length:.1f} x {analysis.width:.1f} x {analysis.height:.1f} mm"],
    ]
    if analysis.flat_length > 0:
        dim_data.append(["Uitslag (Flat)", f"{analysis.flat_length:.1f} x {analysis.flat_width:.1f} mm"])
    
    # 3. Production Data
    prod_data = [
        ["PRODUCTIE DATA", ""],
        ["Totaal Gaten", str(total_holes)],
        ["Zettingen (Totaal)", str(analysis.bend_count_erp)]
    ]
    
    # Add Up/Down counts if available
    if unfold_result and unfold_result.get('bends_logical'):
        bends = unfold_result.get('bends_logical')
        up_count = sum(1 for b in bends if b['type'] == 'up')
        down_count = sum(1 for b in bends if b['type'] == 'down')
        prod_data.append(["  - Zettingen (Up)", str(up_count)])
        prod_data.append(["  - Tegenzettingen (Down)", str(down_count)])

    def create_info_table(data):
        t = Table(data, colWidths=[50*mm, 40*mm])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#34495e')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#bdc3c7')),
            ('BACKGROUND', (0, 1), (0, -1), colors.HexColor('#ecf0f1')),
            ('SPAN', (0, 0), (-1, 0)),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]))
        return t

    t_class = create_info_table(class_data)
    t_dims = create_info_table(dim_data)
    t_prod = create_info_table(prod_data)
    
    # Left Column Content
    left_table_data = [
        [t_class],
        [Spacer(1, 3*mm)],
        [t_dims],
        [Spacer(1, 3*mm)],
        [t_prod]
    ]
    left_col_table = Table(left_table_data, colWidths=[90*mm])
    left_col_table.setStyle(TableStyle([('LEFTPADDING', (0,0), (-1,-1), 0)]))
    
    # Right Column Content (Images)
    right_table_data = []
    
    # 3D Image
    if os.path.exists(svg_path):
        try:
            drawing = svg2rlg(svg_path)
            if drawing:
                scale = min(85*mm / drawing.width, 60*mm / drawing.height)
                drawing.width *= scale
                drawing.height *= scale
                drawing.scale(scale, scale)
                right_table_data.append([Paragraph("3D Weergave", header_style)])
                right_table_data.append([drawing])
                right_table_data.append([Spacer(1, 5*mm)])
        except Exception as e:
            print(f"Error loading 3D SVG: {e}")

    # Flat Image
    if os.path.exists(flat_svg_path):
        try:
            drawing_flat = svg2rlg(flat_svg_path)
            if drawing_flat:
                scale = min(85*mm / drawing_flat.width, 80*mm / drawing_flat.height)
                drawing_flat.width *= scale
                drawing_flat.height *= scale
                drawing_flat.scale(scale, scale)
                right_table_data.append([Paragraph("Uitslag (Flat Pattern)", header_style)])
                right_table_data.append([drawing_flat])
        except Exception as e:
            print(f"Error loading Flat SVG: {e}")

    if not right_table_data:
        right_table_data = [[Paragraph("Geen afbeeldingen beschikbaar", normal_style)]]
        
    right_col_table = Table(right_table_data, colWidths=[90*mm])
    right_col_table.setStyle(TableStyle([
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('LEFTPADDING', (0,0), (-1,-1), 0)
    ]))
    
    # Master Table
    master_table = Table([[left_col_table, right_col_table]], colWidths=[95*mm, 95*mm])
    master_table.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
    ]))
    elements.append(master_table)
    elements.append(Spacer(1, 5*mm))
    
    # --- Bottom Section: Details ---
    
    # Bend Sequence Table (Compact)
    if unfold_result and unfold_result.get('bends_logical'):
        elements.append(Paragraph("Buigvolgorde & Details", header_style))
        bends = unfold_result.get('bends_logical')
        
        # Create a multi-column list if many bends
        # We want 2 columns of bends: # Type Angle Radius | # Type Angle Radius
        bend_data = [["#", "Type", "Hoek", "Radius", "#", "Type", "Hoek", "Radius"]]
        
        row = []
        for i, b in enumerate(bends, 1):
            row.extend([str(i), b['type'].upper(), f"{b['angle']:.0f}°", f"R{b['radius']:.1f}"])
            if len(row) == 8:
                bend_data.append(row)
                row = []
        if row:
            while len(row) < 8:
                row.append("")
            bend_data.append(row)
            
        t_bends = Table(bend_data, colWidths=[10*mm, 15*mm, 15*mm, 15*mm]*2)
        t_bends.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#34495e')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 7),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#bdc3c7')),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
        ]))
        elements.append(t_bends)

    # Footer
    elements.append(Spacer(1, 10*mm))
    elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.grey))
    elements.append(Paragraph("Gegenereerd door Manufacturing Pipeline", small_style))

    doc.build(elements)
    print(f"  PDF (Compact): {pdf_path}")
    return pdf_path



def generate_simple_pdf(step_file, output_dir, part_name, analysis, total_holes, unfold_result=None):
    """Generate comprehensive PDF report with detailed analysis and reasoning.

    Includes BOTH original 3D view AND flat pattern view when available.
    """
    # Fallback: try to get unfold_result from analysis object if not provided
    if unfold_result is None:
        unfold_result = getattr(analysis, 'unfold_result', None)

    from manufacturing_pipeline.analysis.step_processing import load_step_file
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak, HRFlowable, Image
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm, cm
    from reportlab.lib.enums import TA_LEFT, TA_CENTER

    shape = load_step_file(step_file)

    # Generate SVG image for ORIGINAL 3D view
    image_dir = os.path.join(output_dir, "images")
    svg_path = None
    flat_svg_path = None

    try:
        import cadquery as cq
        svg_path = os.path.join(image_dir, f"{part_name}_3d.svg")
        cq.exporters.export(
            shape,
            svg_path,
            opt={
                "width": 300,
                "height": 300,
                "marginLeft": 10,
                "marginTop": 10,
                "showAxes": False,
                "projectionDir": (1, 1, 1),
                "strokeWidth": 0.5,
            }
        )
    except Exception as e:
        print(f"  Warning: Could not generate 3D SVG: {e}")

    # Generate SVG for FLAT PATTERN if available
    flat_step_path = getattr(analysis, 'flat_step_path', None)
    if flat_step_path and os.path.exists(flat_step_path):
        try:
            import cadquery as cq
            flat_shape = load_step_file(flat_step_path)
            flat_svg_path = os.path.join(image_dir, f"{part_name}_flat.svg")
            cq.exporters.export(
                flat_shape,
                flat_svg_path,
                opt={
                    "width": 300,
                    "height": 300,
                    "marginLeft": 10,
                    "marginTop": 10,
                    "showAxes": False,
                    "projectionDir": (0, 0, 1),  # Top view for flat pattern
                    "strokeWidth": 0.5,
                }
            )
            print(f"  Generated flat pattern SVG: {flat_svg_path}")
        except Exception as e:
            print(f"  Warning: Could not generate flat SVG: {e}")

    # Create PDF
    pdf_path = os.path.join(output_dir, f"{part_name}_report.pdf")
    doc = SimpleDocTemplate(pdf_path, pagesize=A4,
                           leftMargin=15*mm, rightMargin=15*mm,
                           topMargin=15*mm, bottomMargin=15*mm)

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('Title', parent=styles['Title'], fontSize=18, spaceAfter=10, alignment=TA_CENTER)
    heading_style = ParagraphStyle('Heading', parent=styles['Heading2'], fontSize=14, spaceAfter=5, spaceBefore=10,
                                   textColor=colors.HexColor('#2c3e50'))
    subheading_style = ParagraphStyle('SubHeading', parent=styles['Heading3'], fontSize=11, spaceAfter=3, spaceBefore=5,
                                      textColor=colors.HexColor('#34495e'))
    normal_style = ParagraphStyle('Normal', parent=styles['Normal'], fontSize=10, leading=14)
    small_style = ParagraphStyle('Small', parent=styles['Normal'], fontSize=9, leading=12, textColor=colors.grey)
    success_style = ParagraphStyle('Success', parent=styles['Normal'], fontSize=10, textColor=colors.HexColor('#27ae60'))
    warning_style = ParagraphStyle('Warning', parent=styles['Normal'], fontSize=10, textColor=colors.HexColor('#e67e22'))
    error_style = ParagraphStyle('Error', parent=styles['Normal'], fontSize=10, textColor=colors.HexColor('#c0392b'))

    elements = []

    # ==================== PAGE 1: SUMMARY ====================
    elements.append(Paragraph(f"Productie Analyse Rapport", title_style))
    elements.append(Paragraph(f"<b>{part_name}</b>", ParagraphStyle('Subtitle', parent=title_style, fontSize=14)))
    elements.append(Spacer(1, 3*mm))
    elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#3498db')))
    elements.append(Spacer(1, 5*mm))

    # Classification box
    type_color = colors.HexColor('#27ae60') if analysis.is_sheet_metal else colors.HexColor('#95a5a6')
    classification_data = [
        ["CLASSIFICATIE", ""],
        ["Type onderdeel", analysis.part_type.value.upper()],
        ["Sheet metal", "JA" if analysis.is_sheet_metal else "NEE"],
        ["Profiel (ingekocht)", "JA" if analysis.is_profile else "NEE"],
        ["Draaistuk", "JA" if analysis.is_turned else "NEE"],
    ]

    class_table = Table(classification_data, colWidths=[60*mm, 60*mm])
    class_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#3498db')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('SPAN', (0, 0), (-1, 0)),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('BACKGROUND', (0, 1), (0, -1), colors.HexColor('#ecf0f1')),
        ('FONTNAME', (0, 1), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#bdc3c7')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))

    # Calculate up/down for summary
    up_count = 0
    down_count = 0
    if unfold_result and unfold_result.get('success'):
        bends = unfold_result.get('bends_logical', [])
        up_count = sum(1 for b in bends if b['type'] == 'up')
        down_count = sum(1 for b in bends if b['type'] == 'down')

    # Production data box
    prod_data = [
        ["PRODUCTIE DATA (ERP)", ""],
        ["Totaal zettingen", str(analysis.bend_count_erp)],
    ]
    
    if up_count > 0 or down_count > 0:
        prod_data.append(["  - Zettingen", str(up_count)])
        prod_data.append(["  - Tegenzettingen", str(down_count)])
        
    prod_data.extend([
        ["Snijgaten", str(total_holes)],
        ["Max gat diameter", f"{analysis.max_hole_diameter:.1f} mm" if analysis.max_hole_diameter > 0 else "-"],
        ["Plaatdikte", f"{analysis.thickness:.1f} mm" if analysis.thickness > 0 else "-"],
    ])

    prod_table = Table(prod_data, colWidths=[60*mm, 60*mm])
    prod_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e74c3c')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('SPAN', (0, 0), (-1, 0)),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('BACKGROUND', (0, 1), (0, -1), colors.HexColor('#ecf0f1')),
        ('FONTNAME', (0, 1), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#bdc3c7')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))

    # Side by side tables
    combined = Table([[class_table, Spacer(5*mm, 1), prod_table]], colWidths=[125*mm, 5*mm, 125*mm])
    elements.append(combined)
    elements.append(Spacer(1, 8*mm))

    # Dimensions
    elements.append(Paragraph("Afmetingen", heading_style))
    dim_data = [
        ["Bounding Box", f"{analysis.length:.1f} × {analysis.width:.1f} × {analysis.height:.1f} mm"],
    ]
    if analysis.flat_length > 0 and analysis.flat_width > 0:
        dim_data.append(["Uitslag (flat)", f"{analysis.flat_length:.1f} × {analysis.flat_width:.1f} mm"])

    dim_table = Table(dim_data, colWidths=[50*mm, 100*mm])
    dim_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#ecf0f1')),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#bdc3c7')),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    elements.append(dim_table)
    elements.append(Spacer(1, 5*mm))

    # ==================== IMAGES SECTION ====================
    # Determine part category for display logic
    part_category = getattr(analysis, 'part_category', None)
    if not part_category:
        if analysis.is_profile:
            part_category = "PROFIEL (ingekocht)"
        elif analysis.bend_count_erp == 0:
            part_category = "PLAAT (vlak)"
        elif analysis.bend_count_erp > 0:
            part_category = "GEBOGEN PLAATWERK"
        else:
            part_category = "ONBEKEND"

    # For GEBOGEN PLAATWERK: show BOTH original and flat view
    # For PLAAT/PROFIEL: show only original view
    is_gebogen = "GEBOGEN" in part_category

    if is_gebogen and flat_svg_path and os.path.exists(flat_svg_path):
        # Show both images side by side for gebogen plaatwerk
        elements.append(Paragraph("Visualisatie: Origineel vs Uitslag", heading_style))
        elements.append(Spacer(1, 3*mm))

        try:
            from svglib.svglib import svg2rlg

            # Load both drawings
            drawing_3d = svg2rlg(svg_path) if svg_path and os.path.exists(svg_path) else None
            drawing_flat = svg2rlg(flat_svg_path)

            img_cells = []
            img_labels = []

            if drawing_3d:
                scale = min(80*mm / drawing_3d.width, 60*mm / drawing_3d.height)
                drawing_3d.width *= scale
                drawing_3d.height *= scale
                drawing_3d.scale(scale, scale)
                img_cells.append(drawing_3d)
                img_labels.append("ORIGINEEL (3D)")
            else:
                img_cells.append(Paragraph("(geen 3D afbeelding)", small_style))
                img_labels.append("")

            if drawing_flat:
                scale = min(80*mm / drawing_flat.width, 60*mm / drawing_flat.height)
                drawing_flat.width *= scale
                drawing_flat.height *= scale
                drawing_flat.scale(scale, scale)
                img_cells.append(drawing_flat)
                img_labels.append("UITSLAG (flat)")
            else:
                img_cells.append(Paragraph("(geen flat afbeelding)", small_style))
                img_labels.append("")

            # Create side-by-side table
            img_table = Table([img_cells, img_labels], colWidths=[90*mm, 90*mm])
            img_table.setStyle(TableStyle([
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('FONTNAME', (0, 1), (-1, 1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 1), (-1, 1), 10),
                ('TEXTCOLOR', (0, 1), (-1, 1), colors.HexColor('#2c3e50')),
                ('TOPPADDING', (0, 0), (-1, -1), 5),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ]))
            elements.append(img_table)
            elements.append(Spacer(1, 5*mm))

        except Exception as e:
            # Fallback to single image
            if svg_path and os.path.exists(svg_path):
                try:
                    from svglib.svglib import svg2rlg
                    drawing = svg2rlg(svg_path)
                    if drawing:
                        scale = min(120*mm / drawing.width, 80*mm / drawing.height)
                        drawing.width *= scale
                        drawing.height *= scale
                        drawing.scale(scale, scale)
                        elements.append(drawing)
                        elements.append(Spacer(1, 5*mm))
                except Exception:
                    pass
    else:
        # PLAAT or PROFIEL: show only original image
        if svg_path and os.path.exists(svg_path):
            elements.append(Paragraph("Visualisatie", heading_style))
            try:
                from svglib.svglib import svg2rlg
                drawing = svg2rlg(svg_path)
                if drawing:
                    scale = min(120*mm / drawing.width, 80*mm / drawing.height)
                    drawing.width *= scale
                    drawing.height *= scale
                    drawing.scale(scale, scale)
                    elements.append(drawing)
                    elements.append(Spacer(1, 5*mm))
            except Exception:
                pass

    # ==================== UNFOLD STATUS SECTION ====================
    # Only show unfold status for gebogen plaatwerk (not for plaat or profiel)
    if is_gebogen:
        elements.append(Paragraph("Unfold Status", heading_style))

        if analysis.can_unfold:
            if analysis.flat_length > 0:
                elements.append(Paragraph(f"[OK] Unfold geslaagd: {analysis.flat_length:.1f} x {analysis.flat_width:.1f} mm", success_style))
                elements.append(Paragraph(f"  Reden: {analysis.unfold_reason}", normal_style))
                
                # Add detailed bend info if available
                if unfold_result and unfold_result.get('success'):
                    elements.append(Spacer(1, 3*mm))
                    elements.append(Paragraph("Zettingen Analyse (Verified)", subheading_style))
                    
                    # Zettingen vs Tegenzettingen
                    bends_logical = unfold_result.get('bends_logical', [])
                    if bends_logical:
                        up_count = sum(1 for b in bends_logical if b['type'] == 'up')
                        down_count = sum(1 for b in bends_logical if b['type'] == 'down')
                        
                        zt_data = [
                            ["Type", "Aantal"],
                            ["Zettingen (Up)", str(up_count)],
                            ["Tegenzettingen (Down)", str(down_count)]
                        ]
                        zt_table = Table(zt_data, colWidths=[60*mm, 30*mm])
                        zt_table.setStyle(TableStyle([
                            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#34495e')),
                            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#bdc3c7')),
                            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                        ]))
                        elements.append(zt_table)
                        elements.append(Spacer(1, 3*mm))
                        
                        # Detailed sequence
                        elements.append(Paragraph("Buigvolgorde:", small_style))
                        seq_text = []
                        for i, b in enumerate(bends_logical, 1):
                            seq_text.append(f"{i}. {b['type'].upper()} {b['angle']:.1f}° (R={b['radius']:.1f}mm)")
                        elements.append(Paragraph(", ".join(seq_text), small_style))
                        elements.append(Spacer(1, 3*mm))

                    # Fold lines table
                    fold_details = unfold_result.get('fold_details', [])
                    if fold_details:
                        elements.append(Paragraph("Buiglijnen (Locatie op uitslag)", subheading_style))
                        fd_data = [["#", "Lengte", "Center (X, Y, Z)"]]
                        for fold in fold_details:
                            c = fold['center']
                            fd_data.append([
                                str(fold['id']),
                                f"{fold['length']:.1f}mm",
                                f"({c[0]:.1f}, {c[1]:.1f}, {c[2]:.1f})"
                            ])
                        
                        fd_table = Table(fd_data, colWidths=[15*mm, 30*mm, 80*mm])
                        fd_table.setStyle(TableStyle([
                            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#34495e')),
                            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#bdc3c7')),
                            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                            ('FONTSIZE', (0, 0), (-1, -1), 8),
                        ]))
                        elements.append(fd_table)

            else:
                elements.append(Paragraph(f"⚠ Unfold mogelijk maar niet uitgevoerd", warning_style))
                elements.append(Paragraph(f"  Reden: {analysis.unfold_reason}", normal_style))
        else:
            elements.append(Paragraph(f"✗ Unfold niet mogelijk", error_style))
            elements.append(Paragraph(f"  Reden: {analysis.unfold_reason}", normal_style))

    # ==================== PAGE 2: DETAILED ANALYSIS ====================
    elements.append(PageBreak())
    elements.append(Paragraph("Gedetailleerde Analyse", title_style))
    elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#3498db')))
    elements.append(Spacer(1, 5*mm))

    # Analysis steps
    elements.append(Paragraph("Analyse Stappen", heading_style))
    elements.append(Paragraph("Hieronder wordt stap voor stap uitgelegd hoe het onderdeel is geanalyseerd:", small_style))
    elements.append(Spacer(1, 3*mm))

    for r in analysis.reasoning:
        step_color = colors.HexColor('#2980b9')
        elements.append(Paragraph(f"<font color='#2980b9'><b>{r.step}</b></font>", normal_style))
        elements.append(Paragraph(f"  Observatie: {r.observation}", small_style))
        elements.append(Paragraph(f"  <b>Conclusie:</b> {r.conclusion}", normal_style))
        elements.append(Spacer(1, 3*mm))

    # Bends detail
    if analysis.bends:
        elements.append(Paragraph("Zettingen Detail", heading_style))
        bend_data = [["#", "Radius", "Hoek", "Lengte", "Telt voor ERP"]]
        for i, b in enumerate(analysis.bends[:15], 1):  # Max 15
            bend_data.append([
                str(i),
                f"R{b.radius:.1f}mm",
                f"{b.angle:.0f}°",
                f"{b.length:.0f}mm",
                "Ja" if b.is_counted else "Nee"
            ])

        bend_table = Table(bend_data, colWidths=[15*mm, 30*mm, 25*mm, 30*mm, 35*mm])
        bend_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#34495e')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#bdc3c7')),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
        ]))
        elements.append(bend_table)

        if len(analysis.bends) > 15:
            elements.append(Paragraph(f"  ... en {len(analysis.bends) - 15} meer zettingen", small_style))

    elements.append(Spacer(1, 5*mm))

    # Holes detail
    if analysis.holes:
        elements.append(Paragraph("Gaten Detail", heading_style))

        # Group by type
        cyl_holes = [h for h in analysis.holes if h.hole_type == 'cylindrical']
        shaped_holes = [h for h in analysis.holes if h.hole_type != 'cylindrical']

        if cyl_holes:
            elements.append(Paragraph(f"Cilindrische gaten: {len(cyl_holes)}", subheading_style))
            # Show diameter distribution
            diameters = {}
            for h in cyl_holes:
                d = round(h.diameter, 1)
                diameters[d] = diameters.get(d, 0) + 1
            for d, count in sorted(diameters.items()):
                elements.append(Paragraph(f"  • Ø{d:.1f}mm: {count}x", normal_style))

        if shaped_holes:
            elements.append(Paragraph(f"Shaped holes (slots, rechthoeken): {len(shaped_holes)}", subheading_style))
            elements.append(Paragraph("  Deze gaten zijn gedetecteerd via inner wires op vlakke oppervlakken.", small_style))

    # ==================== RECOMMENDATIONS ====================
    elements.append(Spacer(1, 10*mm))
    elements.append(Paragraph("Aanbevelingen", heading_style))

    recommendations = []

    if analysis.is_profile:
        recommendations.append("• Dit is een ingekocht profiel - zettingen worden niet meegerekend voor productie.")

    if analysis.is_turned:
        recommendations.append("• Dit is een draaistuk - cilindrische gaten zijn boren, geen lasersnijwerk.")

    if analysis.bend_count_erp > 10:
        recommendations.append(f"• Veel zettingen ({analysis.bend_count_erp}) - controleer of dit klopt met verwachting.")

    if not analysis.can_unfold and analysis.is_sheet_metal:
        recommendations.append("• Unfold niet mogelijk - mogelijk samengesteld onderdeel of variërende plaatdikte.")
        recommendations.append("  Overweeg handmatige unfold in CAD software (SolidWorks, Inventor, FreeCAD GUI).")

    if analysis.thickness > 10:
        recommendations.append(f"• Dikke plaat ({analysis.thickness:.1f}mm) - controleer of dit correct is gedetecteerd.")

    if not recommendations:
        recommendations.append("• Geen bijzondere aandachtspunten.")

    for rec in recommendations:
        elements.append(Paragraph(rec, normal_style))
        elements.append(Spacer(1, 2*mm))

    # Footer
    elements.append(Spacer(1, 10*mm))
    elements.append(HRFlowable(width="100%", thickness=0.5, color=colors.grey))
    elements.append(Paragraph("Gegenereerd door Manufacturing Pipeline - FreeCAD + CadQuery analyse", small_style))

    # Build PDF
    doc.build(elements)
    print(f"  PDF: {pdf_path}")

    return pdf_path
