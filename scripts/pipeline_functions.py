"""
Pipeline functions moved from run.py
"""

import os
import sys
import glob
import subprocess
import json

# Project paths
# Assuming this file is in PROJECT_ROOT/scripts/
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARTS_DIR = os.path.join(PROJECT_ROOT, "parts")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output")
PIPELINE_DIR = os.path.join(PROJECT_ROOT, "manufacturing_pipeline")
SCRIPTS_DIR = os.path.join(PROJECT_ROOT, "scripts")

# FreeCAD Python path
FREECAD_PYTHON = "/opt/homebrew/Caskroom/freecad/1.0.2/FreeCAD.app/Contents/Resources/bin/python"

# Add pipeline and scripts to path
if PIPELINE_DIR not in sys.path:
    sys.path.insert(0, PIPELINE_DIR)
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)


def find_step_files(directory=None):
    """Find all STEP files in the given directory."""
    search_dir = directory or PARTS_DIR
    if not os.path.exists(search_dir):
        os.makedirs(search_dir)
        return []

    step_files = []
    for pattern in ["*.step", "*.STEP", "*.stp", "*.STP"]:
        step_files.extend(glob.glob(os.path.join(search_dir, pattern)))
        # Also search subdirectories
        step_files.extend(glob.glob(os.path.join(search_dir, "**", pattern), recursive=True))
    return sorted(set(step_files))


def select_step_file(step_files):
    """Interactive file selector."""
    if not step_files:
        return None

    if len(step_files) == 1:
        print(f"Found: {os.path.basename(step_files[0])}")
        return step_files[0]

    print("\nSTEP files found:")
    print("-" * 60)
    for i, f in enumerate(step_files, 1):
        rel_path = os.path.relpath(f, PROJECT_ROOT)
        size_kb = os.path.getsize(f) / 1024
        print(f"  [{i:2d}] {rel_path:<45} ({size_kb:.0f} KB)")
    print("-" * 60)

    while True:
        try:
            choice = input(f"Select file [1-{len(step_files)}] or 'q' to quit: ").strip()
            if choice.lower() == 'q':
                return None
            idx = int(choice) - 1
            if 0 <= idx < len(step_files):
                return step_files[idx]
            print(f"Invalid choice. Enter 1-{len(step_files)}")
        except ValueError:
            print("Enter a valid number.")


def get_output_dir(step_file):
    """Get output directory for a STEP file."""
    part_name = os.path.splitext(os.path.basename(step_file))[0]
    part_output = os.path.join(OUTPUT_DIR, part_name)

    os.makedirs(part_output, exist_ok=True)
    os.makedirs(os.path.join(part_output, "images"), exist_ok=True)

    return part_output, part_name


def run_analysis(step_file, output_dir, args):
    """Run the complete analysis pipeline.

    NEW FLOW:
    1. Load & classify part type (plaat/hoekprofiel/gebogen)
    2. Unfold if needed (gebogen plaatwerk)
    3. Analyze holes on FLAT pattern (not 3D)
    4. Generate report with both views
    """
    from src.step_processing import load_step_file, detect_holes, detect_shaped_holes
    from src.part_analyzer import analyze_part_geometry, format_analysis_report, PartType

    part_name = os.path.splitext(os.path.basename(step_file))[0]

    # ================================================================
    # STEP 1: Load and classify
    # ================================================================
    print("\n[1/5] Loading STEP file...")
    shape = load_step_file(step_file)

    print("[2/5] Classifying part type...")
    analysis = analyze_part_geometry(shape, part_name)

    # Determine part category
    part_category = "ONBEKEND"
    if analysis.is_profile:
        part_category = "PROFIEL (ingekocht)"
    elif analysis.bend_count_erp == 0:
        part_category = "PLAAT (vlak)"
    elif analysis.bend_count_erp > 0:
        part_category = "GEBOGEN PLAATWERK"

    print(f"\n--- Classificatie ---")
    print(f"Categorie:   {part_category}")
    print(f"Type:        {analysis.part_type.value.upper()}")
    print(f"Afmetingen:  {analysis.length:.0f} x {analysis.width:.0f} x {analysis.height:.0f} mm")
    print(f"Dikte:       {analysis.thickness:.1f} mm")
    print(f"Zettingen:   {analysis.bend_count_erp}")

    # ================================================================
    # STEP 2: Unfold if gebogen plaatwerk
    # ================================================================
    unfold_result = None
    flat_shape = None
    flat_step_path = None

    if analysis.can_unfold and not args.no_unfold and analysis.bend_count_erp > 0:
        print("\n[3/5] Unfolding sheet metal...")
        unfold_result = run_unfold_to_step(step_file, output_dir, part_name, analysis)

        if unfold_result and unfold_result.get('success'):
            flat_step_path = unfold_result.get('flat_step_path')
            print(f"  ✓ Unfold geslaagd: {unfold_result.get('flat_length', 0):.0f} x {unfold_result.get('flat_width', 0):.0f} mm")
            print(f"  ✓ Fold lines: {unfold_result.get('fold_lines', 0)}")
            
            # Check thickness from unfold result
            unfold_thickness = unfold_result.get('thickness', 0)
            if unfold_thickness > 0:
                print(f"  ✓ Detected thickness (unfold): {unfold_thickness:.2f} mm")
                # Update analysis thickness if it was 0 or significantly different?
                # Usually we trust the initial analysis, but this is a good cross-check.
                if analysis.thickness == 0:
                    analysis.thickness = unfold_thickness

            # Load the flat shape for hole analysis
            if flat_step_path and os.path.exists(flat_step_path):
                flat_shape = load_step_file(flat_step_path)
                print(f"  ✓ Flat STEP: {flat_step_path}")
        else:
            print(f"  ⚠ Unfold niet gelukt: {unfold_result.get('error', 'onbekend') if unfold_result else 'geen resultaat'}")
    elif analysis.bend_count_erp == 0:
        print("\n[3/5] Unfold: Niet nodig (vlakke plaat)")
    elif analysis.is_profile:
        print("\n[3/5] Unfold: Niet nodig (ingekocht profiel)")
    else:
        print(f"\n[3/5] Unfold: {analysis.unfold_reason}")

    # ================================================================
    # STEP 3: Detect holes - on FLAT pattern if available
    # ================================================================
    print("\n[4/5] Detecting holes...")

    # For gebogen plaatwerk: analyze on flat pattern (this is what gets laser cut)
    # For plaat/profiel: analyze on 3D model
    if flat_shape is not None:
        print(f"  Analyseren op: UITSLAG (flat pattern)")
        analysis_shape = flat_shape
        is_flat = True
    else:
        print(f"  Analyseren op: 3D model")
        analysis_shape = shape
        is_flat = False

    circular_holes = detect_holes(analysis_shape, is_flat_pattern=is_flat)
    shaped_holes = detect_shaped_holes(analysis_shape)
    total_holes = len(circular_holes) + len(shaped_holes)

    print(f"  Cilindrische gaten: {len(circular_holes)}")
    print(f"  Shaped holes (slots/rect): {len(shaped_holes)}")
    print(f"  Totaal: {total_holes}")

    # ================================================================
    # STEP 4: Save results
    # ================================================================
    print("\n[5/5] Saving results...")

    # Update analysis with flat dimensions if available
    if unfold_result and unfold_result.get('success'):
        analysis.flat_length = unfold_result.get('flat_length', 0)
        analysis.flat_width = unfold_result.get('flat_width', 0)

    # Save analysis report
    report_path = os.path.join(output_dir, f"{part_name}_analysis.txt")
    with open(report_path, 'w') as f:
        f.write(format_analysis_report(analysis))
        f.write(f"\n\nCategorie: {part_category}\n")
        f.write(f"Gaten (flat): {total_holes}\n")
        if unfold_result and unfold_result.get('success'):
            f.write(f"Flat dimensions: {analysis.flat_length:.0f} x {analysis.flat_width:.0f} mm\n")
    print(f"  Rapport: {report_path}")

    # Store extra info for PDF generation
    analysis.part_category = part_category
    analysis.unfold_result = unfold_result
    analysis.flat_step_path = flat_step_path

    return analysis, total_holes


def run_unfold_to_step(step_file, output_dir, part_name, analysis):
    """Run FreeCAD unfold and export both DXF and STEP of flat pattern.

    Returns dict with:
    - success: bool
    - flat_step_path: path to flat STEP file
    - flat_length, flat_width: dimensions
    - fold_lines: number of bends
    """
    # Build unfold script that exports STEP
    unfold_script = f'''
import sys
import os
import json

# FreeCAD paths
freecad_app = "/opt/homebrew/Caskroom/freecad/1.0.2/FreeCAD.app"
freecad_lib = f"{{freecad_app}}/Contents/Resources/lib"
freecad_mod = f"{{freecad_app}}/Contents/Resources/Mod"
freecad_user_mod = os.path.expanduser("~/Library/Application Support/FreeCAD/Mod")

sys.path.insert(0, freecad_lib)
sys.path.insert(0, freecad_mod)
sys.path.insert(0, freecad_user_mod)
sys.path.insert(0, os.path.join(freecad_user_mod, "sheetmetal"))

# Mock GUI with proper Selection that returns an object with Refine attribute
class MockObject:
    Refine = True

class MockSelection:
    _selection = [MockObject()]

    @staticmethod
    def getSelection():
        return MockSelection._selection

    @staticmethod
    def addSelection(*args):
        pass

class MockGui:
    Selection = MockSelection()

sys.modules["FreeCADGui"] = MockGui()

import FreeCAD
import Part
import SheetMetalUnfolder

# Load STEP
step_path = "{step_file}"
shape = Part.Shape()
shape.read(step_path)

# K-factor lookup
kFactorLookup = {{t: 0.44 for t in [0.5, 0.75, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0, 12.0, 15.0, 20.0]}}

def get_thickness_from_solid(solid):
    try:
        # Strategy: Find largest planar face, then find opposite face
        faces = [f for f in solid.Faces if "Plane" in f.Surface.TypeId]
        if not faces:
            return 0.0
            
        # Sort by area
        faces.sort(key=lambda f: f.Area, reverse=True)
        main_face = faces[0]
        main_normal = main_face.Surface.Axis
        
        # Find opposite face (parallel, normal dot product approx -1)
        # We check the top 5 largest faces to find the matching back face
        for f in faces[1:10]:
            # Check if normals are opposite
            if f.Surface.Axis.dot(main_normal) < -0.9:
                # Measure distance
                dist = main_face.distToShape(f)[0]
                if dist > 0:
                    return dist
        return 0.0
    except:
        return 0.0

result = {{"success": False}}

# Get solids
solids = shape.Solids if shape.Solids else [shape]
sorted_solids = sorted(solids, key=lambda s: s.Volume, reverse=True)

for solid in sorted_solids[:3]:  # Try top 3 by volume
    # Calculate thickness first
    detected_thickness = get_thickness_from_solid(solid)

    # Find planar faces for base
    planar_faces = []
    for i, face in enumerate(solid.Faces):
        try:
            if "Plane" in face.Surface.TypeId:
                planar_faces.append({{"index": i, "area": face.Area}})
        except:
            pass
    planar_faces.sort(key=lambda x: x["area"], reverse=True)

    for base_info in planar_faces[:3]:  # Try top 3 largest faces
        base_idx = base_info["index"]
        try:
            doc = FreeCAD.newDocument("UnfoldDoc")
            obj = doc.addObject("Part::Feature", "SheetPart")
            obj.Shape = solid
            doc.recompute()

            unfold_tree = SheetMetalUnfolder.SheetTree(solid, base_idx, kFactorLookup)
            if unfold_tree.error_code:
                FreeCAD.closeDocument("UnfoldDoc")
                continue

            unfold_tree.Bend_analysis(base_idx, None)
            if unfold_tree.error_code:
                FreeCAD.closeDocument("UnfoldDoc")
                continue

            if hasattr(unfold_tree, "root") and unfold_tree.root:
                theFaceList, foldLines = unfold_tree.unfold_tree2(unfold_tree.root)

                if not unfold_tree.error_code and theFaceList:
                    # Create flat shape - use FULL faces to preserve inner wires (holes)
                    # Don't use OuterWire only, that loses the hole geometry!
                    flat_faces = [f for f in theFaceList if f.isValid()]
                    if flat_faces:
                        # Use Compound instead of Shell to preserve all geometry
                        flat_compound = Part.Compound(flat_faces)

                        # Get dimensions
                        bbox = flat_compound.BoundBox
                        dims = sorted([bbox.XLength, bbox.YLength, bbox.ZLength], reverse=True)

                        # Export STEP - compound preserves holes
                        flat_step_path = "{output_dir}/{part_name}_flat.step"
                        flat_compound.exportStep(flat_step_path)

                        # Export DXF
                        dxf_path = "{output_dir}/{part_name}_flat.dxf"
                        import importDXF
                        importDXF.export([flat_compound], dxf_path)

                        result = {{
                            "success": True,
                            "flat_step_path": flat_step_path,
                            "flat_length": dims[0],
                            "flat_width": dims[1],
                            "fold_lines": len(foldLines),
                            "thickness": detected_thickness
                        }}
                        FreeCAD.closeDocument("UnfoldDoc")
                        break

            FreeCAD.closeDocument("UnfoldDoc")
        except Exception as e:
            try:
                FreeCAD.closeDocument("UnfoldDoc")
            except:
                pass
            continue

    if result["success"]:
        break

print("UNFOLD_RESULT:" + json.dumps(result))
'''

    try:
        proc = subprocess.run(
            [FREECAD_PYTHON, "-c", unfold_script],
            capture_output=True,
            text=True,
            timeout=180
        )

        # Parse result
        for line in proc.stdout.split('\n'):
            if line.startswith('UNFOLD_RESULT:'):
                return json.loads(line[len('UNFOLD_RESULT:'):])

        return {"success": False, "error": "No result returned"}

    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Timeout (>180s)"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def run_unfold(step_file, output_dir, part_name, analysis):
    """Run FreeCAD unfold via subprocess, with theoretical fallback (legacy)."""
    unfold_script = os.path.join(PIPELINE_DIR, "src", "freecad_unfold.py")
    dxf_output = os.path.join(output_dir, f"{part_name}_flat.dxf")
    unfold_result = {'success': False, 'error_details': []}

    if not os.path.exists(FREECAD_PYTHON):
        print(f"  ⚠ FreeCAD Python not found at {FREECAD_PYTHON}")
        print("  Skipping unfold...")
        return unfold_result

    if not os.path.exists(unfold_script):
        print(f"  ⚠ Unfold script not found: {unfold_script}")
        return unfold_result

    try:
        result = subprocess.run(
            [FREECAD_PYTHON, unfold_script, step_file, "-o", dxf_output],
            capture_output=True,
            text=True,
            timeout=180  # Increased timeout for multiple attempts
        )

        if result.returncode == 0:
            unfold_result['success'] = True
            # Parse output for dimensions
            for line in result.stdout.split('\n'):
                if 'Unfold geslaagd' in line or 'Unfold successful' in line:
                    print(f"  ✓ {line.strip()}")
                elif 'Fold lines' in line:
                    print(f"  ✓ {line.strip()}")

            if os.path.exists(dxf_output):
                size_kb = os.path.getsize(dxf_output) / 1024
                print(f"  ✓ DXF: {dxf_output} ({size_kb:.0f} KB)")

                # Update analysis with flat dimensions
                for line in result.stdout.split('\n'):
                    if 'Unfold geslaagd' in line or 'Unfold successful' in line:
                        try:
                            parts = line.split(':')
                            if len(parts) >= 2:
                                dims = parts[1].strip().replace(' mm', '').split(' x ')
                                analysis.flat_length = float(dims[0])
                                analysis.flat_width = float(dims[1])
                        except (IndexError, ValueError):
                            pass
        else:
            # Parse error details from output
            for line in result.stdout.split('\n'):
                if '✗' in line and 'fout:' in line:
                    msg = line.split('fout:')[-1].strip() if 'fout:' in line else line
                    unfold_result['error_details'].append({
                        'face_idx': -1,
                        'stage': 'unfold',
                        'error_code': -1,
                        'message': msg
                    })

            print(f"  ✗ Automatische unfold gefaald")

            # Try theoretical unfold as fallback
            print(f"  → Berekenen theoretische uitslag...")
            theoretical = run_theoretical_unfold(step_file, analysis)
            if theoretical:
                unfold_result['theoretical'] = theoretical

    except subprocess.TimeoutExpired:
        print("  ✗ Unfold timeout (>180s)")
    except Exception as e:
        print(f"  ✗ Unfold error: {e}")

    return unfold_result


def run_theoretical_unfold(step_file, analysis):
    """Calculate theoretical unfold dimensions when automatic unfold fails."""
    try:
        # Run theoretical calculation via FreeCAD Python
        calc_code = f'''
import sys
sys.path.insert(0, "{PIPELINE_DIR}/src")
from freecad_unfold import calculate_theoretical_unfold
import json

result = calculate_theoretical_unfold("{step_file}")
print("THEORETICAL_RESULT:" + json.dumps(result))
'''
        result = subprocess.run(
            [FREECAD_PYTHON, "-c", calc_code],
            capture_output=True,
            text=True,
            timeout=60
        )

        # Parse result
        for line in result.stdout.split('\n'):
            if 'THEORETICAL_RESULT:' in line:
                import json
                data = json.loads(line.split('THEORETICAL_RESULT:')[1])
                if data.get('success'):
                    print(f"  ✓ Theoretische uitslag: ~{data['estimated_length']:.0f} x {data['estimated_width']:.0f} mm (indicatief)")
                    print(f"    Methode: oppervlakte + buiglengtes berekening")

                    # Update analysis with theoretical values
                    analysis.flat_length = data['estimated_length']
                    analysis.flat_width = data['estimated_width']

                    return data

        return None

    except Exception as e:
        print(f"  ⚠ Theoretische berekening gefaald: {e}")
        return None


def run_aag_analysis(step_file):
    """Run AAG (Attributed Adjacency Graph) analysis via FreeCAD subprocess.

    Returns dict with AAG analysis results including:
    - hole_count, bend_count, slot_count
    - thickness detection
    - cut length and laser cut time estimation
    - isoperimetric quotients for hole classification
    """
    # Build the analysis script
    aag_script = f'''
import sys
import os
import json

# FreeCAD paths
freecad_app = "/opt/homebrew/Caskroom/freecad/1.0.2/FreeCAD.app"
freecad_lib = f"{{freecad_app}}/Contents/Resources/lib"
freecad_mod = f"{{freecad_app}}/Contents/Resources/Mod"
freecad_user_mod = os.path.expanduser("~/Library/Application Support/FreeCAD/Mod")

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
    "hole_count": result.hole_count,
    "bend_count": result.bend_count,
    "slot_count": result.slot_count,
    "thickness": result.thickness,
    "cut_length": result.cut_length,
    "total_cut_length": result.total_cut_length,
    "pierce_count": result.pierce_count,
    "laser_cut_time": result.laser_cut_time,
    "face_count": result.face_count,
    "edge_count": result.edge_count,
    "skin_faces": result.skin_faces,
    "thickness_faces": result.thickness_faces,
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

# Add bend details
for b in result.bends[:20]:  # Limit to 20
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
            timeout=120
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
        return {"success": False, "error": "AAG analysis timeout (>120s)"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def run_debug(step_file):
    """Debug mode - detailed hole detection analysis."""
    from src.step_processing import load_step_file, debug_hole_detection

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


def generate_simple_pdf(step_file, output_dir, part_name, analysis, total_holes, unfold_result=None):
    """Generate comprehensive PDF report with detailed analysis and reasoning.

    Includes BOTH original 3D view AND flat pattern view when available.
    """
    from src.step_processing import load_step_file
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

    # Production data box
    prod_data = [
        ["PRODUCTIE DATA (ERP)", ""],
        ["Zettingen", str(analysis.bend_count_erp)],
        ["Snijgaten", str(total_holes)],
        ["Max gat diameter", f"{analysis.max_hole_diameter:.1f} mm" if analysis.max_hole_diameter > 0 else "-"],
        ["Plaatdikte", f"{analysis.thickness:.1f} mm" if analysis.thickness > 0 else "-"],
    ]

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
                elements.append(Paragraph(f"✓ Unfold geslaagd: {analysis.flat_length:.1f} × {analysis.flat_width:.1f} mm", success_style))
                elements.append(Paragraph(f"  Reden: {analysis.unfold_reason}", normal_style))
            else:
                elements.append(Paragraph(f"⚠ Unfold mogelijk maar niet uitgevoerd", warning_style))
                elements.append(Paragraph(f"  Reden: {analysis.unfold_reason}", normal_style))
        else:
            elements.append(Paragraph(f"✗ Unfold niet mogelijk", error_style))
            elements.append(Paragraph(f"  Reden: {analysis.unfold_reason}", normal_style))

        # If unfold failed with details, show them
        if unfold_result and not unfold_result.get('success') and unfold_result.get('error_details'):
            elements.append(Spacer(1, 3*mm))
            elements.append(Paragraph("Unfold pogingen:", subheading_style))
            for detail in unfold_result.get('error_details', [])[:3]:  # Show max 3
                elements.append(Paragraph(f"  • Face {detail['face_idx']}: {detail['message']}", small_style))

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
