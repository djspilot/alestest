"""
Pipeline utilities for manufacturing analysis.
"""

import os
import sys
import glob
import subprocess
import json
import hashlib
from datetime import datetime

# Project paths
# This file is now in PROJECT_ROOT/manufacturing_pipeline/core/
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
CONFIG_DIR = os.path.join(DATA_DIR, "config")
DB_DIR = os.path.join(DATA_DIR, "db")

PARTS_DIR = os.path.join(DATA_DIR, "input")
OUTPUT_DIR = os.path.join(DATA_DIR, "output")
PIPELINE_DIR = os.path.join(PROJECT_ROOT, "manufacturing_pipeline")
SCRIPTS_DIR = os.path.join(PIPELINE_DIR, "scripts")

# FreeCAD Python path
# FreeCAD Python path
from manufacturing_pipeline.core.config import SystemConfig
FREECAD_PYTHON = SystemConfig.from_env().freecad_python


# Add pipeline and scripts to path
if PIPELINE_DIR not in sys.path:
    sys.path.insert(0, PIPELINE_DIR)
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

# Cache file location
CACHE_FILE = os.path.join(DB_DIR, "pipeline_cache.json")


# =============================================================================
# Cache Functions
# =============================================================================

def get_file_hash(filepath):
    """Calculate MD5 hash of a file."""
    hasher = hashlib.md5()
    with open(filepath, 'rb') as f:
        for chunk in iter(lambda: f.read(65536), b''):
            hasher.update(chunk)
    return hasher.hexdigest()


def load_cache():
    """Load cache from disk."""
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}
    return {}


def save_cache(cache):
    """Save cache to disk."""
    with open(CACHE_FILE, 'w') as f:
        json.dump(cache, f, indent=2)


def get_cached_result(filepath, cache):
    """Get cached result if file hasn't changed."""
    file_hash = get_file_hash(filepath)
    cache_key = os.path.abspath(filepath)
    
    if cache_key in cache:
        cached = cache[cache_key]
        if cached.get('hash') == file_hash:
            return cached.get('result')
    return None


def cache_result(filepath, result, cache):
    """Cache a result for a file."""
    file_hash = get_file_hash(filepath)
    cache_key = os.path.abspath(filepath)
    
    cache[cache_key] = {
        'hash': file_hash,
        'result': result,
        'cached_at': datetime.now().isoformat()
    }
    return cache


def process_single_file(step_file, args_dict, cache_data=None):
    """Worker function to process a single STEP file (for parallel processing)."""
    # Convert args dict back to namespace
    class Args:
        def __init__(self, d):
            for k, v in d.items():
                setattr(self, k, v)
    
    args = Args(args_dict)
    part_name = os.path.basename(step_file)
    
    # Check cache if provided and not disabled
    if cache_data is not None and not args_dict.get('no_cache', False):
        file_key = os.path.abspath(step_file)
        if file_key in cache_data:
            current_hash = get_file_hash(step_file)
            cached = cache_data[file_key]
            if cached.get('hash') == current_hash:
                result = cached.get('result', {}).copy()
                result['cached'] = True
                return result
    
    try:
        output_dir, part_name_clean = get_output_dir(step_file)
        analysis, total_holes = run_analysis(step_file, output_dir, args)
        
        if not args.no_pdf:
            generate_simple_pdf(step_file, output_dir, part_name_clean, analysis, total_holes)
        
        result = {
            'file': part_name,
            'filepath': step_file,
            'success': True,
            'cached': False,
            'category': getattr(analysis, 'part_category', 'UNKNOWN'),
            'part_type': getattr(analysis, 'part_type', None),
            'holes': total_holes,
            'thickness': getattr(analysis, 'thickness', 0),
            'bends': getattr(analysis, 'bend_count_erp', 0),
            'dimensions': {
                'length': getattr(analysis, 'length', 0),
                'width': getattr(analysis, 'width', 0),
                'height': getattr(analysis, 'height', 0)
            }
        }
        # Convert part_type enum to string for JSON serialization
        if result['part_type'] is not None:
            result['part_type'] = str(result['part_type'].value) if hasattr(result['part_type'], 'value') else str(result['part_type'])
        
        return result
    except Exception as e:
        return {
            'file': part_name,
            'filepath': step_file,
            'success': False,
            'cached': False,
            'error': str(e)
        }


# =============================================================================
# File Discovery Functions
# =============================================================================


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

    IMPROVED FLOW:
    1. Load STEP file
    2. Run AAG Analysis (Topology-based feature recognition)
       -> Detects bends, thickness, holes purely from geometry
    3. Run Standard Analysis (Dimensions, bounding box)
    4. Classify based on AAG results (Bends > 0 -> Bent, etc.)
    5. Unfold if classified as Bent Sheet Metal
    6. Analyze holes (on flat pattern if available)
    7. Generate report
    """
    from manufacturing_pipeline.analysis.step_processing import load_step_file, detect_holes, detect_shaped_holes, deduplicate_holes
    from manufacturing_pipeline.analysis.part_analyzer import analyze_part_geometry, format_analysis_report, PartType
    
    # Import AAG Analyzer
    try:
        from manufacturing_pipeline.scripts.aag_analyzer import AAGAnalyzer
    except ImportError as e:
        print(f"Warning: Could not import AAGAnalyzer: {e}")
        # Fallback dummy class if needed or just let it fail later
        AAGAnalyzer = None

    part_name = os.path.splitext(os.path.basename(step_file))[0]

    print("\n[1/6] Loading STEP file...")
    shape = load_step_file(step_file)

    # ================================================================
    # STEP 2: AAG Feature Recognition (The "Brain")
    # ================================================================
    print("[2/6] Running AAG Feature Recognition...")
    
    # Run via subprocess to use FreeCAD's robust geometry engine
    aag_data = run_aag_analysis(step_file)
    
    # Create a simple object to hold results for easier access
    class AAGResult:
        def __init__(self, data):
            self.success = data.get('success', False)
            self.thickness = data.get('thickness', 0.0)
            self.bend_count = data.get('bend_count', 0)
            self.hole_count = data.get('hole_count', 0)
            self.slot_count = data.get('slot_count', 0)
            self.data = data

    aag_result = AAGResult(aag_data)
    
    if not aag_result.success:
        print(f"  ⚠ AAG Analysis failed, falling back to standard analysis")
    else:
        print(f"  ✓ AAG Success: {aag_result.bend_count} bends, t={aag_result.thickness:.2f}mm")

    # ================================================================
    # STEP 3: Standard Geometry Analysis
    # ================================================================
    print("[3/6] Analyzing dimensions & geometry...")
    analysis = analyze_part_geometry(shape, part_name)

    # ================================================================
    # STEP 4: Classification (Logic Update)
    # ================================================================
    # Use AAG results to override/refine classification
    # This makes it robust for files WITHOUT ERP data
    
    if aag_result.success:
        # Update analysis with AAG data
        if aag_result.thickness > 0:
            # Only overwrite if current thickness is 0 or if AAG thickness is plausible
            if analysis.thickness == 0:
                analysis.thickness = aag_result.thickness
            elif abs(analysis.thickness - aag_result.thickness) > 0.1:
                print(f"  ⚠ Thickness mismatch: AAG={aag_result.thickness:.2f}mm, Standard={analysis.thickness:.2f}mm")
                # Heuristic: If AAG is very thin (<1mm) and Standard is thicker (>2mm), trust Standard
                if aag_result.thickness < 1.0 and analysis.thickness > 2.0:
                    print("  -> Keeping Standard thickness (AAG result seems too thin)")
                else:
                    analysis.thickness = aag_result.thickness
        
        # Determine category based on GEOMETRY (AAG), not ERP
        part_category = "ONBEKEND"
        
        # Profile detection (AAG can detect closed loops of bends, but for now we use simple heuristics)
        # If it has bends but looks like a standard profile (e.g. 4 bends 90 deg in a loop)
        # For now, we trust the standard analyzer for profile detection (it checks cross sections)
        
        if analysis.is_profile:
            part_category = "PROFIEL (ingekocht)"
            # Keep existing profile type (e.g. BUIS, KOKER) if set, otherwise default to KOKER_PROFIEL
            # PartType is already imported at function start

            if analysis.part_type not in [PartType.BUIS, PartType.KOKER, PartType.KOKER_PROFIEL]:
                analysis.part_type = PartType.KOKER_PROFIEL 
        elif aag_result.bend_count > 0:
            part_category = "GEBOGEN PLAATWERK"
            analysis.part_type = PartType.COMPLEX # Default to complex/bent
            analysis.is_sheet_metal = True
            # Update ERP count to match geometric count if ERP is missing
            if analysis.bend_count_erp == 0:
                analysis.bend_count_erp = aag_result.bend_count
        elif aag_result.thickness > 0 and aag_result.bend_count == 0:
            part_category = "PLAAT (vlak)"
            analysis.part_type = PartType.PLAAT
            analysis.is_sheet_metal = True
        elif analysis.is_turned:
            part_category = "DRAAISTUK"
            
        print(f"\n--- Classificatie (AAG Powered) ---")
        print(f"Categorie:   {part_category}")
        print(f"Type:        {analysis.part_type.value.upper()}")
        print(f"Afmetingen:  {analysis.length:.0f} x {analysis.width:.0f} x {analysis.height:.0f} mm")
        print(f"Dikte:       {analysis.thickness:.2f} mm (AAG detected)")
        print(f"Zettingen:   {aag_result.bend_count} (AAG detected)")
    else:
        # Fallback to original logic if AAG failed
        part_category = "ONBEKEND"
        if analysis.is_profile:
            part_category = "PROFIEL (ingekocht)"
        elif analysis.bend_count_erp == 0:
            part_category = "PLAAT (vlak)"
        elif analysis.bend_count_erp > 0:
            part_category = "GEBOGEN PLAATWERK"
            
        print(f"\n--- Classificatie (Standard) ---")
        print(f"Categorie:   {part_category}")
        print(f"Type:        {analysis.part_type.value.upper()}")
        print(f"Afmetingen:  {analysis.length:.0f} x {analysis.width:.0f} x {analysis.height:.0f} mm")
        print(f"Dikte:       {analysis.thickness:.1f} mm")
        print(f"Zettingen:   {analysis.bend_count_erp}")

    # ================================================================
    # STEP 5: Unfold if gebogen plaatwerk
    # ================================================================
    unfold_result = None
    flat_shape = None
    flat_step_path = None
    
    # Logic: If it's bent sheet metal, try to unfold
    should_unfold = (part_category == "GEBOGEN PLAATWERK") and not args.no_unfold

    if should_unfold:
        print("\n[4/6] Unfolding sheet metal...")
        unfold_result = run_unfold_to_step(step_file, output_dir, part_name, analysis)

        if unfold_result and unfold_result.get('success'):
            flat_step_path = unfold_result.get('flat_step_path')
            print(f"  ✓ Unfold geslaagd: {unfold_result.get('flat_length', 0):.0f} x {unfold_result.get('flat_width', 0):.0f} mm")
            print(f"  ✓ Fold lines: {unfold_result.get('fold_lines', 0)}")
            
            # Check thickness from unfold result
            unfold_thickness = unfold_result.get('thickness', 0)
            if unfold_thickness > 0:
                print(f"  ✓ Detected thickness (unfold): {unfold_thickness:.2f} mm")
                
                # Sanity check: Sheet metal thickness is usually < 25mm
                if unfold_thickness < 25.0:
                    if analysis.thickness == 0 or abs(analysis.thickness - unfold_thickness) > 0.1:
                        print(f"  -> Updating thickness to {unfold_thickness:.2f} mm (Unfold is authoritative)")
                        analysis.thickness = unfold_thickness
                else:
                    print(f"  -> Ignoring unfold thickness (seems too large: {unfold_thickness:.2f} mm)")

            # Load the flat shape for hole analysis
            if flat_step_path and os.path.exists(flat_step_path):
                flat_shape = load_step_file(flat_step_path)
                print(f"  ✓ Flat STEP: {flat_step_path}")
        else:
            print(f"  ⚠ Unfold niet gelukt: {unfold_result.get('error', 'onbekend') if unfold_result else 'geen resultaat'}")
    else:
        print(f"\n[4/6] Unfold: Niet nodig ({part_category})")

    # ================================================================
    # STEP 6: Detect holes - on FLAT pattern if available
    # ================================================================
    print("\n[5/6] Detecting holes...")

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
    
    # Deduplicate holes (remove circular holes that are part of shaped holes)
    circular_holes = deduplicate_holes(circular_holes, shaped_holes)
    
    total_holes = len(circular_holes) + len(shaped_holes)

    print(f"  Cilindrische gaten: {len(circular_holes)}")
    for i, h in enumerate(circular_holes):
        print(f"    {i+1}. Ø{h.diameter:.2f}mm at {h.position}")
        
    print(f"  Shaped holes (slots/rect): {len(shaped_holes)}")
    for i, h in enumerate(shaped_holes):
        print(f"    {i+1}. {h['type']} {h['dim']} at {h['center']}")
        
    print(f"  Totaal: {total_holes}")

    # ================================================================
    # STEP 7: Save results
    # ================================================================
    print("\n[6/6] Saving results...")

    # Update analysis with flat dimensions if available
    if unfold_result and unfold_result.get('success'):
        analysis.unfold_result = unfold_result  # Attach for PDF generation
        analysis.flat_length = unfold_result.get('flat_length', 0)
        analysis.flat_width = unfold_result.get('flat_width', 0)
        
        # Update main dimensions to reflect the flat pattern (as requested)
        # We keep the thickness as the 3rd dimension
        analysis.length = analysis.flat_length
        analysis.width = analysis.flat_width
        analysis.height = analysis.thickness # Height becomes thickness in flat view
        
        # Update bend count to match the verified unfold count
        # AAG can sometimes overcount (e.g. segmented bends), Unfold is authoritative
        if unfold_result.get('fold_lines', 0) > 0:
            analysis.bend_count_erp = unfold_result.get('fold_lines')

    # Save analysis report
    report_path = os.path.join(output_dir, f"{part_name}_analysis.txt")
    with open(report_path, 'w') as f:
        f.write(format_analysis_report(analysis))
        f.write(f"\n\nCategorie: {part_category}\n")
        f.write(f"Gaten (flat): {total_holes}\n")
        if aag_result.success:
            f.write(f"AAG Analysis (Raw): {aag_result.bend_count} bends detected\n")
        if unfold_result and unfold_result.get('success'):
            f.write(f"Unfold Analysis: {unfold_result.get('fold_lines')} fold lines (Verified)\n")
            
            # Report Zettingen vs Tegenzettingen
            bends = unfold_result.get('bends_logical', [])
            if bends:
                up_count = sum(1 for b in bends if b['type'] == 'up')
                down_count = sum(1 for b in bends if b['type'] == 'down')
                f.write(f"  Zettingen (Up): {up_count}\n")
                f.write(f"  Tegenzettingen (Down): {down_count}\n")
                f.write("  Bend Sequence:\n")
                for i, b in enumerate(bends):
                    f.write(f"    {i+1}. {b['type'].upper()} {b['angle']:.1f}° (R={b['radius']:.1f}mm)\n")

            if unfold_result.get('fold_details'):
                f.write("  Fold Lines (Center X, Y, Z | Length):\n")
                for fold in unfold_result.get('fold_details'):
                    c = fold['center']
                    f.write(f"  - Fold {fold['id']}: ({c[0]:.1f}, {c[1]:.1f}, {c[2]:.1f}) L={fold['length']:.1f}mm\n")
            f.write(f"Flat dimensions: {analysis.flat_length:.0f} x {analysis.flat_width:.0f} mm\n")
    print(f"  Rapport: {report_path}")

    # Store extra info for PDF generation
    analysis.part_category = part_category
    analysis.unfold_result = unfold_result
    analysis.flat_step_path = flat_step_path
    if aag_result.success:
        analysis.aag_result = aag_result.data # Store AAG result for PDF

    return analysis, total_holes


def run_unfold_to_step(step_file, output_dir, part_name, analysis):
    """Run FreeCAD unfold and export both DXF and STEP of flat pattern.

    Returns dict with:
    - success: bool
    - flat_step_path: path to flat STEP file
    - flat_length, flat_width: dimensions
    - fold_lines: number of bends
    """
    # Get system config for paths
    sys_config = SystemConfig.from_env()
    fc_lib = sys_config.freecad_lib
    fc_mod = sys_config.freecad_mod

    # Build unfold script that exports STEP
    unfold_script = f'''
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
best_score = -1

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

    # Try top 10 largest faces to find the best base for unfolding
    for base_info in planar_faces[:10]:
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
                    flat_faces = [f for f in theFaceList if f.isValid()]
                    if flat_faces:
                        flat_compound = Part.Compound(flat_faces)

                        # Calculate score: number of fold lines (primary) + area (secondary)
                        num_folds = len(foldLines)
                        area = flat_compound.Area
                        # Weight folds heavily to prefer complete unfolds
                        score = (num_folds * 1000000) + area
                        
                        if score > best_score:
                            best_score = score
                            
                            # Get dimensions
                            bbox = flat_compound.BoundBox
                            dims = sorted([bbox.XLength, bbox.YLength, bbox.ZLength], reverse=True)

                            # Export STEP
                            flat_step_path = "{output_dir}/{part_name}_flat.step"
                            flat_compound.exportStep(flat_step_path)

                            # Export DXF
                            dxf_path = "{output_dir}/{part_name}_flat.dxf"
                            import importDXF
                            importDXF.export([flat_compound], dxf_path)

                            # Extract fold details from geometry
                            fold_details = []
                            for i, line in enumerate(foldLines):
                                try:
                                    center = line.BoundBox.Center
                                    length = line.Length
                                    fold_details.append({{
                                        "id": i+1,
                                        "length": length,
                                        "center": (center.x, center.y, center.z)
                                    }})
                                except:
                                    pass

                            # Extract logical bend info from tree (Up/Down)
                            bends_logical = []
                            def traverse_bends(node):
                                if hasattr(node, "node_type") and node.node_type == "Bend":
                                    import math
                                    angle_deg = math.degrees(node.bend_angle) if node.bend_angle else 0
                                    bends_logical.append({{
                                        "type": node.bend_dir, # 'up' or 'down'
                                        "angle": angle_deg,
                                        "radius": node.innerRadius
                                    }})
                                
                                if hasattr(node, "child_list"):
                                    for child in node.child_list:
                                        traverse_bends(child)
                            
                            traverse_bends(unfold_tree.root)

                            result = {{
                                "success": True,
                                "flat_step_path": flat_step_path,
                                "flat_length": dims[0],
                                "flat_width": dims[1],
                                "fold_lines": num_folds,
                                "thickness": detected_thickness,
                                "fold_details": fold_details,
                                "bends_logical": bends_logical
                            }}
                            
            FreeCAD.closeDocument("UnfoldDoc")
        except Exception as e:
            try:
                FreeCAD.closeDocument("UnfoldDoc")
            except:
                pass
            continue

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
    unfold_script = os.path.join(PIPELINE_DIR, "freecad_unfold.py")
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
sys.path.insert(0, "{PIPELINE_DIR}")
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
                elements.append(Paragraph(f"✓ Unfold geslaagd: {analysis.flat_length:.1f} × {analysis.flat_width:.1f} mm", success_style))
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
