#!/usr/bin/env python3
"""
ERP/Spaceclaim Vergelijking Tool

Vergelijkt de pipeline analyse met:
1. ERP data uit Excel (.xlsx)
2. Spaceclaim/AutoPOL data uit XML

Nu met AAG (Attributed Adjacency Graph) feature recognition:
- Topologie-gebaseerde feature detectie
- Isoperimetrisch Quotiënt voor hole/slot classificatie
- K-factor gebaseerde Bend Allowance/Deduction
- Laser snijkosten schatting

Output: Vergelijkingsrapport per onderdeel
"""

import os
import sys
import glob
import argparse
import xml.etree.ElementTree as ET
from pathlib import Path

# Add pipeline to path
SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPTS_DIR)
PIPELINE_DIR = os.path.join(PROJECT_ROOT, "manufacturing_pipeline")
sys.path.insert(0, PIPELINE_DIR)
sys.path.insert(0, SCRIPTS_DIR)

# FreeCAD Python path
FREECAD_PYTHON = "/opt/homebrew/Caskroom/freecad/1.0.2/FreeCAD.app/Contents/Resources/bin/python"

# Import AAG analyzer (optional - used when running with --aag flag)
try:
    from aag_analyzer import analyze_with_aag, AAGAnalyzer
    AAG_AVAILABLE = True
except ImportError:
    AAG_AVAILABLE = False


def parse_excel(excel_path):
    """Parse ERP Excel file."""
    import pandas as pd

    try:
        df = pd.read_excel(excel_path)

        # Check if this is an ERP file (has ArtikelNr column)
        if 'ArtikelNr' not in df.columns:
            print(f"    (no ArtikelNr column - skipping)")
            return {}

        results = {}
        for _, row in df.iterrows():
            part_name = str(row.get('ArtikelNr', '')).strip()
            if not part_name or part_name == 'nan' or part_name == 'ArtikelNr':
                continue

            try:
                holes = int(row.get('Snijgaten', 0) or 0)
            except (ValueError, TypeError):
                holes = 0

            try:
                bends = int(row.get('ZetAantal', 0) or 0)
            except (ValueError, TypeError):
                bends = 0

            try:
                length = float(row.get('Lengte', 0) or 0)
            except (ValueError, TypeError):
                length = 0

            try:
                width = float(row.get('Breedte', 0) or 0)
            except (ValueError, TypeError):
                width = 0

            try:
                thickness = float(row.get('Dikte', 0) or 0)
            except (ValueError, TypeError):
                thickness = 0

            try:
                max_hole_dia = float(row.get('DiaSnijgat', 0) or 0)
            except (ValueError, TypeError):
                max_hole_dia = 0

            results[part_name] = {
                'source': 'ERP',
                'holes': holes,
                'bends': bends,
                'length': length,
                'width': width,
                'thickness': thickness,
                'type': str(row.get('Vorm', '') or ''),
                'max_hole_dia': max_hole_dia,
            }

        return results
    except Exception as e:
        print(f"  ⚠ Excel parse error: {e}")
        return {}


def parse_xml(xml_path):
    """Parse Spaceclaim/AutoPOL XML file.

    Note: XML can contain multiple entries per part (from assembly or multiple analyses).
    We collect ALL entries and let the caller choose the best match.
    """
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()

        # Collect ALL entries per part name
        all_entries = {}
        for calc in root.findall('.//CalculationResult'):
            part_name = calc.findtext('Sheet_PartName')
            if not part_name:
                continue

            # Parse hole contours (format: "324.2_324.2")
            hole_contours_str = calc.findtext('Sheet_HoleContours', '')
            hole_contours = [float(x) for x in hole_contours_str.split('_') if x] if hole_contours_str else []

            # Parse bend angles (format: "90_90_90")
            bend_angles_str = calc.findtext('Sheet_BendAngles', '')
            bend_angles = [float(x) for x in bend_angles_str.split('_') if x] if bend_angles_str else []

            # Parse bend radii
            bend_radii_str = calc.findtext('Sheet_BendInnerRadii', '')
            bend_radii = [float(x) for x in bend_radii_str.split('_') if x] if bend_radii_str else []

            entry = {
                'source': 'Spaceclaim',
                'holes': int(calc.findtext('Sheet_NrHoles', '0') or 0),
                'bends': int(calc.findtext('Sheet_NrBends', '0') or 0),
                'length': float(calc.findtext('Sheet_BoxX', '0') or 0),
                'width': float(calc.findtext('Sheet_BoxY', '0') or 0),
                'thickness': float(calc.findtext('Sheet_Thickness', '0') or 0),
                'type': calc.findtext('Sheet_Type', ''),
                'unfold_success': calc.findtext('Sheet_UnfoldSuccess', 'False') == 'True',
                'material': calc.findtext('Sheet_Material', ''),
                'weight': float(calc.findtext('Sheet_Weight', '0') or 0),
                'volume': float(calc.findtext('Sheet_Volume', '0') or 0),
                'top_area': float(calc.findtext('Sheet_TopArea', '0') or 0),
                'total_area': float(calc.findtext('Sheet_TotalArea', '0') or 0),
                'box_area': float(calc.findtext('Sheet_BoxArea', '0') or 0),
                'outer_contour': float(calc.findtext('Sheet_OuterContour', '0') or 0),
                'total_contour': float(calc.findtext('Sheet_TotalContour', '0') or 0),
                'hole_contours': hole_contours,
                'bend_angles': bend_angles,
                'bend_radii': bend_radii,
            }

            if part_name not in all_entries:
                all_entries[part_name] = []
            all_entries[part_name].append(entry)

        # For each part, select the BEST entry:
        # Priority: entry with highest (holes + bends) count (most complete analysis)
        results = {}
        for part_name, entries in all_entries.items():
            if len(entries) == 1:
                results[part_name] = entries[0]
            else:
                # Choose entry with most features detected
                best = max(entries, key=lambda e: e['holes'] + e['bends'] * 10)
                results[part_name] = best

        return results
    except Exception as e:
        print(f"  ⚠ XML parse error: {e}")
        return {}


def analyze_step_file(step_path, analyze_all_solids=False):
    """Run pipeline analysis on STEP file via FreeCAD subprocess.

    Strategy:
    1. Try to unfold the part first
    2. If unfold succeeds: count holes on the flat pattern (most accurate)
    3. If unfold fails: count holes on the 3D shape using inner wire method

    Args:
        step_path: Path to STEP file
        analyze_all_solids: If True, analyze each solid separately and return list of results

    Returns:
        If analyze_all_solids=False: single result dict
        If analyze_all_solids=True: list of result dicts (one per solid)
    """
    import subprocess
    import json

    # FreeCAD paths
    freecad_app = "/opt/homebrew/Caskroom/freecad/1.0.2/FreeCAD.app"
    freecad_lib = f"{freecad_app}/Contents/Resources/lib"
    freecad_mod = f"{freecad_app}/Contents/Resources/Mod"
    freecad_user_mod = os.path.expanduser("~/Library/Application Support/FreeCAD/Mod")

    # Create analysis script using FreeCAD directly
    analysis_script = f'''
import sys
import os
import json
import math
from collections import defaultdict

# FreeCAD paths
sys.path.insert(0, "{freecad_lib}")
sys.path.insert(0, "{freecad_mod}")
sys.path.insert(0, "{freecad_user_mod}")
sys.path.insert(0, os.path.join("{freecad_user_mod}", "sheetmetal"))
sys.path.insert(0, "{PIPELINE_DIR}")

import FreeCAD
import Part

# Mock FreeCADGui for headless mode
class MockSelection:
    _selection = []
    @classmethod
    def getSelection(cls): return cls._selection
    @classmethod
    def clearSelection(cls): cls._selection = []
    @classmethod
    def addSelection(cls, obj): cls._selection.append(obj)

class MockFreeCADGui:
    Selection = MockSelection()

try:
    import FreeCADGui
    FreeCADGui.Selection.getSelection()
except (ImportError, AttributeError):
    sys.modules['FreeCADGui'] = MockFreeCADGui()
    FreeCADGui = MockFreeCADGui()

step_path = "{step_path}"

def count_holes_on_shape(shape, method='largest_face'):
    """Count holes (inner wires) on a shape.

    For sheet metal, holes appear on BOTH top and bottom planar faces.
    So we count holes on the LARGEST planar face only (avoids double counting).

    Args:
        shape: Part.Shape (3D or flat)
        method: 'largest_face' or 'all_faces_div2'
    """
    faces = shape.Faces if hasattr(shape, 'Faces') else [shape]

    # Collect planar faces with their areas and hole counts
    planar_faces = []
    for face in faces:
        try:
            if 'Plane' in face.Surface.TypeId:
                inner_wires = len(face.Wires) - 1
                planar_faces.append({{'area': face.Area, 'holes': inner_wires}})
        except:
            pass

    if not planar_faces:
        return 0

    if method == 'largest_face':
        # Count holes on the largest planar face only
        planar_faces.sort(key=lambda x: x['area'], reverse=True)
        return planar_faces[0]['holes']
    else:
        # Count all inner wires and divide by 2
        total = sum(pf['holes'] for pf in planar_faces)
        return total // 2

def detect_thickness(shape):
    """Detect sheet metal thickness from geometry.

    Strategy:
    1. Find parallel planar face pairs (top/bottom)
    2. Calculate distances between them
    3. Most common small distance is likely the thickness
    """
    planar_faces = []
    for face in shape.Faces:
        try:
            if 'Plane' in face.Surface.TypeId:
                normal = face.Surface.Axis
                center = face.CenterOfMass
                planar_faces.append({{'normal': normal, 'center': center, 'area': face.Area}})
        except:
            pass

    if len(planar_faces) < 2:
        return None

    # Find parallel face pairs and their distances
    distances = []
    for i, f1 in enumerate(planar_faces):
        for f2 in planar_faces[i+1:]:
            # Check if faces are parallel (normals are parallel or anti-parallel)
            dot = abs(f1['normal'].dot(f2['normal']))
            if dot > 0.99:  # Nearly parallel
                # Calculate distance between face centers along normal
                diff = f2['center'] - f1['center']
                dist = abs(diff.dot(f1['normal']))
                if 0.3 <= dist <= 20:  # Typical sheet metal thickness range
                    distances.append(dist)

    if not distances:
        return None

    # Most common distance (rounded to 0.1mm)
    rounded = [round(d, 1) for d in distances]
    from collections import Counter
    counts = Counter(rounded)
    thickness = counts.most_common(1)[0][0]
    return thickness

def analyze_3d_shape(shape):
    """Fallback analysis on 3D shape when unfold fails."""
    inner_wire_holes = []
    planar_faces = []
    cylindrical_faces = []

    for i, face in enumerate(shape.Faces):
        try:
            surf_type = face.Surface.TypeId
            if 'Plane' in surf_type:
                planar_faces.append({{'index': i, 'area': face.Area}})
                for wire in face.Wires[1:]:
                    wire_bbox = wire.BoundBox
                    inner_wire_holes.append(max(wire_bbox.XLength, wire_bbox.YLength))
            elif 'Cylinder' in surf_type:
                cyl = face.Surface
                cyl_bbox = face.BoundBox
                axis = cyl.Axis
                if abs(axis.z) > 0.9:
                    h = cyl_bbox.ZLength
                elif abs(axis.x) > 0.9:
                    h = cyl_bbox.XLength
                else:
                    h = cyl_bbox.YLength
                cylindrical_faces.append({{'radius': cyl.Radius, 'height': h, 'area': face.Area}})
        except:
            pass

    return inner_wire_holes, planar_faces, cylindrical_faces

def count_bends_from_cylindrical_faces(shape):
    """Fallback bend detection using cylindrical faces.

    Sheet metal bends create cylindrical surfaces at the bend location.
    Each bend has TWO cylindrical faces (inner and outer radius).
    So we count cylindrical faces and divide by 2.

    Criteria for bend cylindrical faces:
    - Radius between 0.3 and 15mm (typical sheet metal bend radii)
    - Height > 15mm (bend extends along sheet width)
    - Not through-holes (those have small height relative to radius)
    """
    cylindrical_faces = []

    for face in shape.Faces:
        try:
            if 'Cylinder' in face.Surface.TypeId:
                cyl = face.Surface
                radius = cyl.Radius
                axis = cyl.Axis

                # Calculate height along cylinder axis
                bbox = face.BoundBox
                if abs(axis.z) > 0.9:
                    height = bbox.ZLength
                elif abs(axis.x) > 0.9:
                    height = bbox.XLength
                else:
                    height = bbox.YLength

                # Bend criteria:
                # 1. Radius in typical sheet metal range (0.3-15mm)
                # 2. Height > 15mm (typical min bend length)
                # 3. Height > 2*radius (distinguish from holes)
                if 0.3 <= radius <= 15 and height > 15 and height > 2 * radius:
                    cylindrical_faces.append({{'radius': radius, 'height': height}})
        except:
            pass

    # Each bend has inner + outer cylindrical face
    return len(cylindrical_faces) // 2

def try_unfold_solid(solid, kFactorLookup, detected_thickness=None):
    """Try to unfold a single solid.

    Returns: (success, flat_shape, flat_length, flat_width, bend_count, fold_lines)
    """
    import FreeCAD
    import SheetMetalUnfolder

    # Find base face candidates
    base_candidates = []
    for i, face in enumerate(solid.Faces):
        try:
            if 'Plane' in face.Surface.TypeId:
                base_candidates.append({{'index': i, 'area': face.Area}})
        except:
            pass
    base_candidates.sort(key=lambda x: x['area'], reverse=True)

    if not base_candidates:
        return False, None, 0, 0, 0, []

    # Try up to 3 base faces
    for base_info in base_candidates[:3]:
        base_face_idx = base_info['index']

        try:
            doc = FreeCAD.newDocument("UnfoldDoc")
            obj = doc.addObject("Part::Feature", "SheetPart")
            obj.Shape = solid
            doc.recompute()

            class ObjWrapper:
                def __init__(self, real_obj):
                    self._obj = real_obj
                    self.Refine = False
                def __getattr__(self, name):
                    return getattr(self._obj, name)

            MockSelection._selection = [ObjWrapper(obj)]

            unfold_tree = SheetMetalUnfolder.SheetTree(solid, base_face_idx, kFactorLookup)

            if unfold_tree.error_code:
                FreeCAD.closeDocument("UnfoldDoc")
                continue

            unfold_tree.Bend_analysis(base_face_idx, None)

            if unfold_tree.error_code:
                FreeCAD.closeDocument("UnfoldDoc")
                continue

            if hasattr(unfold_tree, 'root') and unfold_tree.root:
                theFaceList, foldLines = unfold_tree.unfold_tree2(unfold_tree.root)

                if not unfold_tree.error_code and theFaceList:
                    try:
                        flat_shape = Part.Shell(theFaceList)
                    except:
                        flat_shape = Part.Compound(theFaceList)

                    flat_bbox = flat_shape.BoundBox
                    flat_length = flat_bbox.XLength
                    flat_width = flat_bbox.YLength
                    bend_count = len(foldLines)

                    FreeCAD.closeDocument("UnfoldDoc")
                    return True, flat_shape, flat_length, flat_width, bend_count, foldLines

            FreeCAD.closeDocument("UnfoldDoc")
        except Exception as ue:
            try:
                FreeCAD.closeDocument("UnfoldDoc")
            except:
                pass
            continue

    return False, None, 0, 0, 0, []

try:
    # Load STEP file
    shape = Part.Shape()
    shape.read(step_path)

    # Detect material thickness from geometry
    detected_thickness = detect_thickness(shape)

    # Bounding box of 3D shape
    bbox = shape.BoundBox
    dims = sorted([bbox.XLength, bbox.YLength, bbox.ZLength], reverse=True)
    length_3d = dims[0]
    width_3d = dims[1]
    thickness_bbox = dims[2]

    # Use detected thickness if available, otherwise use bounding box
    thickness = detected_thickness if detected_thickness else thickness_bbox

    # K-factor lookup (can be optimized based on material/thickness)
    kFactorLookup = {{t: 0.44 for t in [0.5, 0.75, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0, 12.0, 15.0, 20.0]}}

    # ============================================
    # STRATEGY: TRY UNFOLD - PER SOLID IF NEEDED
    # ============================================
    unfold_success = False
    flat_shape = None
    flat_length = 0
    flat_width = 0
    bend_count_from_unfold = 0
    holes_from_flat = 0
    fold_lines_data = []
    solids_unfolded = 0
    total_solids = len(shape.Solids)

    # Collect all flat shapes and fold lines
    all_flat_shapes = []
    all_fold_lines = []

    try:
        import SheetMetalUnfolder

        # STRATEGY: Always try largest solid first
        # For multi-solid: if largest fails, try per-solid as fallback
        sorted_solids = sorted(shape.Solids, key=lambda s: s.Volume, reverse=True) if shape.Solids else [shape]
        largest_solid = sorted_solids[0]

        # For multi-solid assemblies: analyze ALL solids, not just the largest
        # This is important because assemblies may have multiple sheet metal parts
        # each with their own bends

        if total_solids == 1:
            # Single solid: just try to unfold it
            success, flat_s, flat_l, flat_w, bends, folds = try_unfold_solid(largest_solid, kFactorLookup, detected_thickness)
            if success:
                unfold_success = True
                flat_shape = flat_s
                flat_length = flat_l
                flat_width = flat_w
                bend_count_from_unfold = bends
                all_fold_lines = folds
                holes_from_flat = count_holes_on_shape(flat_shape, 'all_faces_div2')
                solids_unfolded = 1
                all_flat_shapes = [flat_s]
        else:
            # Multi-solid: analyze ALL solids
            # Track bends from cylindrical faces for solids where unfold fails
            total_bends_from_cyl = 0
            for solid_idx, solid in enumerate(sorted_solids):
                success, flat_s, flat_l, flat_w, bends, folds = try_unfold_solid(solid, kFactorLookup, detected_thickness)
                if success:
                    all_flat_shapes.append(flat_s)
                    all_fold_lines.extend(folds)
                    solids_unfolded += 1
                    # Use largest successful solid's dimensions as primary
                    if flat_length == 0:
                        flat_length = flat_l
                        flat_width = flat_w
                else:
                    # Fallback: count bends from cylindrical faces for this solid
                    solid_bends = count_bends_from_cylindrical_faces(solid)
                    total_bends_from_cyl += solid_bends

            if solids_unfolded > 0 or total_bends_from_cyl > 0:
                unfold_success = solids_unfolded > 0
                # Combine bends from unfold and cylindrical fallback
                bend_count_from_unfold = len(all_fold_lines) + total_bends_from_cyl
                # Count holes on all flat shapes combined
                total_holes_flat = 0
                for flat_s in all_flat_shapes:
                    total_holes_flat += count_holes_on_shape(flat_s, 'all_faces_div2')
                holes_from_flat = total_holes_flat
                # Combine flat shapes for geometry calculations
                if len(all_flat_shapes) == 1:
                    flat_shape = all_flat_shapes[0]
                elif len(all_flat_shapes) > 1:
                    flat_shape = Part.Compound(all_flat_shapes)

    except ImportError:
        pass  # SheetMetal not available

    # ============================================
    # ANALYZE 3D SHAPE (for bends and fallback)
    # ============================================
    inner_wire_holes, planar_faces, cylindrical_faces = analyze_3d_shape(shape)

    # Bend detection from cylindrical faces
    # Improved: add height > 2*radius check to distinguish bends from holes
    bend_candidates = []
    for cyl in cylindrical_faces:
        radius = cyl['radius']
        height = cyl['height']
        # Bend criteria: radius 0.3-15mm, height > 15mm, height > 2*radius (not a hole)
        if 0.3 <= radius <= 15 and height > 15 and height > 2 * radius:
            bend_candidates.append(cyl)

    bend_count_3d = len(bend_candidates) // 2

    # Hole count from 3D shape (all faces / 2 method)
    holes_from_3d = count_holes_on_shape(shape, 'all_faces_div2')

    # ============================================
    # FINAL COUNTS
    # ============================================
    if unfold_success:
        # Use unfold results (most accurate)
        total_holes = holes_from_flat
        bend_count = bend_count_from_unfold
        length = flat_length
        width = flat_width
        method = 'unfold'
    else:
        # Fallback to 3D analysis using largest face
        total_holes = holes_from_3d
        bend_count = bend_count_3d
        length = length_3d
        width = width_3d
        method = '3d_fallback'

    # ============================================
    # GEOMETRY - from flat pattern if available
    # ============================================
    volume_3d = shape.Volume

    # Calculate geometry from flat pattern if unfold succeeded
    if unfold_success and flat_shape:
        # Top area from flat pattern (should match Spaceclaim better)
        flat_faces = flat_shape.Faces if hasattr(flat_shape, 'Faces') else []
        flat_planar = []
        for f in flat_faces:
            try:
                if 'Plane' in f.Surface.TypeId:
                    flat_planar.append(f.Area)
            except:
                pass
        top_area = max(flat_planar) if flat_planar else 0

        # Total area from flat pattern
        total_area = sum(f.Area for f in flat_faces) if flat_faces else 0

        # Box area from flat dimensions
        box_area = flat_length * flat_width

        # Contour from flat pattern
        outer_contour = 0
        total_contour = 0
        if flat_planar:
            # Find largest planar face for contour
            for f in flat_faces:
                try:
                    if 'Plane' in f.Surface.TypeId and abs(f.Area - max(flat_planar)) < 0.1:
                        if f.Wires:
                            outer_contour = f.Wires[0].Length
                        for wire in f.Wires:
                            total_contour += wire.Length
                        break
                except:
                    pass

        # Volume: use 3D volume (material volume is constant)
        volume = volume_3d
    else:
        # Fallback to 3D geometry
        sorted_planar = sorted(planar_faces, key=lambda x: x['area'], reverse=True)
        top_area = sorted_planar[0]['area'] if sorted_planar else 0
        total_area = sum(f.Area for f in shape.Faces)
        box_area = length * width

        outer_contour = 0
        total_contour = 0
        if sorted_planar:
            largest_face = shape.Faces[sorted_planar[0]['index']]
            if largest_face.Wires:
                outer_contour = largest_face.Wires[0].Length
            for wire in largest_face.Wires:
                total_contour += wire.Length

        volume = volume_3d

    weight_alu = volume * 2.7 / 1000

    # Part type
    if bend_count == 0 and thickness < 10:
        part_type = 'PLAAT'
    elif bend_count > 0:
        part_type = 'COMPLEX'
    else:
        part_type = 'OVERIG'

    # Fold line info (for bend analysis)
    fold_line_lengths = []
    for fl in all_fold_lines:
        try:
            if hasattr(fl, 'Length'):
                fold_line_lengths.append(fl.Length)
        except:
            pass

    # ============================================
    # PER-SOLID ANALYSIS (for assemblies)
    # ============================================
    per_solid_results = []
    if total_solids > 1:
        for solid_idx, solid in enumerate(sorted_solids):
            solid_bbox = solid.BoundBox
            solid_dims = sorted([solid_bbox.XLength, solid_bbox.YLength, solid_bbox.ZLength], reverse=True)

            # Try to unfold this solid
            s_success, s_flat, s_flat_l, s_flat_w, s_bends, s_folds = try_unfold_solid(solid, kFactorLookup, detected_thickness)

            if s_success:
                s_holes = count_holes_on_shape(s_flat, 'all_faces_div2')
                s_method = 'unfold'
                s_length = s_flat_l
                s_width = s_flat_w
            else:
                s_holes = count_holes_on_shape(solid, 'all_faces_div2')
                s_method = '3d_fallback'
                s_length = solid_dims[0]
                s_width = solid_dims[1]
                # FALLBACK: Detect bends from cylindrical faces when unfold fails
                s_bends = count_bends_from_cylindrical_faces(solid)

            per_solid_results.append({{
                'solid_index': solid_idx,
                'volume': round(solid.Volume, 1),
                'length': round(s_length, 1),
                'width': round(s_width, 1),
                'thickness': round(solid_dims[2], 2),
                'holes': s_holes,
                'bends': s_bends,
                'unfold_success': s_success,
                'method': s_method,
            }})

    result = {{
        'source': 'Pipeline',
        'holes': total_holes,
        'holes_from_flat': holes_from_flat if unfold_success else None,
        'holes_from_3d': holes_from_3d,
        'bends': bend_count,
        'bends_from_unfold': bend_count_from_unfold if unfold_success else None,
        'bends_from_3d': bend_count_3d,
        'unfold_success': unfold_success,
        'solids_unfolded': solids_unfolded,
        'total_solids': total_solids,
        'analysis_method': method,
        'length': round(length, 1),
        'width': round(width, 1),
        'flat_length': round(flat_length, 1) if unfold_success else 0,
        'flat_width': round(flat_width, 1) if unfold_success else 0,
        'thickness': round(thickness, 2),
        'thickness_detected': round(detected_thickness, 2) if detected_thickness else None,
        'thickness_bbox': round(thickness_bbox, 2),
        'type': part_type,
        'planar_faces': len(planar_faces),
        'cylindrical_faces': len(cylindrical_faces),
        'volume': round(volume, 1),
        'top_area': round(top_area, 1),
        'total_area': round(total_area, 1),
        'box_area': round(box_area, 1),
        'outer_contour': round(outer_contour, 1),
        'total_contour': round(total_contour, 1),
        'weight_alu': round(weight_alu, 0),
        'fold_line_count': len(fold_line_lengths),
        'fold_line_lengths': [round(l, 1) for l in fold_line_lengths],
        'per_solid': per_solid_results,
    }}
    print("RESULT_JSON:" + json.dumps(result))
except Exception as e:
    import traceback
    print(f"ERROR:{{e}}")
    traceback.print_exc()
'''

    try:
        result = subprocess.run(
            [FREECAD_PYTHON, "-c", analysis_script],
            capture_output=True,
            text=True,
            timeout=60
        )

        output = result.stdout + result.stderr

        # Parse result
        for line in output.split('\n'):
            if line.startswith('RESULT_JSON:'):
                json_str = line[len('RESULT_JSON:'):]
                return json.loads(json_str)
            if line.startswith('ERROR:'):
                print(f"    ⚠ Pipeline error: {line[6:]}")
                return None

        # Check for errors in output
        if result.returncode != 0:
            # Show some error details
            for line in output.split('\n')[-5:]:
                if line.strip():
                    print(f"    {line}")
            return None

        return None
    except subprocess.TimeoutExpired:
        print(f"    ⚠ Pipeline timeout")
        return None
    except Exception as e:
        print(f"    ⚠ Pipeline error: {e}")
        return None


def find_best_matching_solid(pipeline_data, spaceclaim_data):
    """For multi-solid assemblies, find the solid that best matches Spaceclaim data.

    Uses a combination of:
    1. Volume match (most reliable - material volume is constant)
    2. Hole count match (helpful for distinguishing similar parts)
    3. Bend count match (when available)

    Note: Dimension matching is de-prioritized because flat pattern dimensions
    from unfold may not match Spaceclaim's unfolded dimensions.

    Returns the matching solid's data, or None if no good match found.
    """
    if not spaceclaim_data or not pipeline_data:
        return None

    per_solid = pipeline_data.get('per_solid', [])
    if not per_solid:
        return None

    sc_volume = spaceclaim_data.get('volume', 0)
    sc_holes = spaceclaim_data.get('holes', 0)
    sc_bends = spaceclaim_data.get('bends', 0)

    if sc_volume == 0:
        return None

    best_match = None
    best_score = float('inf')

    for solid in per_solid:
        # Volume match is primary (most reliable)
        s_volume = solid.get('volume', 0)
        if sc_volume > 0 and s_volume > 0:
            vol_diff_pct = abs(s_volume - sc_volume) / sc_volume * 100
        else:
            vol_diff_pct = 100  # Penalize if volume not available

        # Hole count match
        s_holes = solid.get('holes', 0)
        hole_diff = abs(s_holes - sc_holes)

        # Bend count match
        s_bends = solid.get('bends', 0)
        bend_diff = abs(s_bends - sc_bends)

        # Combined score (lower is better):
        # - Volume within 5% is considered a good match
        # - Exact hole/bend match helps distinguish similar volumes
        score = vol_diff_pct + hole_diff * 5 + bend_diff * 10

        if score < best_score:
            best_score = score
            best_match = solid

    # Accept if volume is within 10% and hole/bend counts are reasonable
    if best_match and best_score < 50:
        return best_match

    return None


def compare_results(erp_data, spaceclaim_data, pipeline_data):
    """Compare results from all three sources."""
    comparison = {
        'holes': {},
        'bends': {},
        'dimensions': {},
        'geometry': {},  # New: volume, area, contour
        'matches': [],
        'mismatches': [],
        'matched_solid': None,
    }

    # For multi-solid assemblies, try to find matching solid
    matched_solid = None
    if pipeline_data and pipeline_data.get('total_solids', 1) > 1 and spaceclaim_data:
        matched_solid = find_best_matching_solid(pipeline_data, spaceclaim_data)
        if matched_solid:
            comparison['matched_solid'] = matched_solid.get('solid_index')

    # Holes comparison
    if erp_data:
        comparison['holes']['ERP'] = erp_data.get('holes', 0)
    if spaceclaim_data:
        comparison['holes']['Spaceclaim'] = spaceclaim_data.get('holes', 0)
    if pipeline_data:
        # For multi-solid assemblies with a match, use the matched solid's values
        if matched_solid:
            comparison['holes']['Pipeline'] = matched_solid.get('holes', 0)
            comparison['holes']['Pipeline_total'] = pipeline_data.get('holes', 0)
        else:
            comparison['holes']['Pipeline'] = pipeline_data.get('holes', 0)
        comparison['holes']['Pipeline_combined'] = pipeline_data.get('holes_combined', 0)

    # Bends comparison
    if erp_data:
        comparison['bends']['ERP'] = erp_data.get('bends', 0)
    if spaceclaim_data:
        comparison['bends']['Spaceclaim'] = spaceclaim_data.get('bends', 0)
    if pipeline_data:
        # For multi-solid assemblies with a match, use the matched solid's values
        if matched_solid:
            comparison['bends']['Pipeline'] = matched_solid.get('bends', 0)
            comparison['bends']['Pipeline_total'] = pipeline_data.get('bends', 0)
        else:
            comparison['bends']['Pipeline'] = pipeline_data.get('bends', 0)

    # Dimensions comparison
    if erp_data:
        comparison['dimensions']['ERP'] = f"{erp_data.get('length', 0):.0f} x {erp_data.get('width', 0):.0f}"
    if spaceclaim_data:
        comparison['dimensions']['Spaceclaim'] = f"{spaceclaim_data.get('length', 0):.0f} x {spaceclaim_data.get('width', 0):.0f}"
    if pipeline_data:
        if matched_solid:
            comparison['dimensions']['Pipeline_matched'] = f"{matched_solid.get('length', 0):.0f} x {matched_solid.get('width', 0):.0f}"
        comparison['dimensions']['Pipeline_bbox'] = f"{pipeline_data.get('length', 0):.0f} x {pipeline_data.get('width', 0):.0f}"
        if pipeline_data.get('flat_length', 0) > 0:
            comparison['dimensions']['Pipeline_flat'] = f"{pipeline_data.get('flat_length', 0):.0f} x {pipeline_data.get('flat_width', 0):.0f}"

    # Geometry comparison (new Spaceclaim-matching fields)
    if spaceclaim_data and pipeline_data:
        sc_vol = spaceclaim_data.get('volume', 0)
        pipe_vol = pipeline_data.get('volume', 0)
        if sc_vol > 0 and pipe_vol > 0:
            vol_diff = abs(sc_vol - pipe_vol) / sc_vol * 100
            comparison['geometry']['volume'] = {
                'Spaceclaim': f"{sc_vol:.0f} mm³",
                'Pipeline': f"{pipe_vol:.0f} mm³",
                'diff': f"{vol_diff:.1f}%"
            }

        sc_area = spaceclaim_data.get('top_area', 0)
        pipe_area = pipeline_data.get('top_area', 0)
        if sc_area > 0 and pipe_area > 0:
            area_diff = abs(sc_area - pipe_area) / sc_area * 100
            comparison['geometry']['top_area'] = {
                'Spaceclaim': f"{sc_area:.0f} mm²",
                'Pipeline': f"{pipe_area:.0f} mm²",
                'diff': f"{area_diff:.1f}%"
            }

        sc_contour = spaceclaim_data.get('total_contour', 0)
        pipe_contour = pipeline_data.get('total_contour', 0)
        if sc_contour > 0 and pipe_contour > 0:
            contour_diff = abs(sc_contour - pipe_contour) / sc_contour * 100
            comparison['geometry']['total_contour'] = {
                'Spaceclaim': f"{sc_contour:.0f} mm",
                'Pipeline': f"{pipe_contour:.0f} mm",
                'diff': f"{contour_diff:.1f}%"
            }

        sc_weight = spaceclaim_data.get('weight', 0)
        pipe_weight = pipeline_data.get('weight_alu', 0)
        if sc_weight > 0 and pipe_weight > 0:
            weight_diff = abs(sc_weight - pipe_weight) / sc_weight * 100
            comparison['geometry']['weight'] = {
                'Spaceclaim': f"{sc_weight:.0f} g",
                'Pipeline': f"{pipe_weight:.0f} g",
                'diff': f"{weight_diff:.1f}%"
            }

    # Check matches
    erp_holes = erp_data.get('holes', -1) if erp_data else -1
    sc_holes = spaceclaim_data.get('holes', -1) if spaceclaim_data else -1
    pipe_holes = pipeline_data.get('holes', -1) if pipeline_data else -1

    if erp_holes == pipe_holes and erp_holes >= 0:
        comparison['matches'].append(f"Holes: ERP={erp_holes} == Pipeline={pipe_holes}")
    elif erp_holes != pipe_holes and erp_holes >= 0 and pipe_holes >= 0:
        comparison['mismatches'].append(f"Holes: ERP={erp_holes} != Pipeline={pipe_holes}")

    erp_bends = erp_data.get('bends', -1) if erp_data else -1
    sc_bends = spaceclaim_data.get('bends', -1) if spaceclaim_data else -1
    pipe_bends = pipeline_data.get('bends', -1) if pipeline_data else -1

    if erp_bends == pipe_bends and erp_bends >= 0:
        comparison['matches'].append(f"Bends: ERP={erp_bends} == Pipeline={pipe_bends}")
    elif erp_bends != pipe_bends and erp_bends >= 0 and pipe_bends >= 0:
        comparison['mismatches'].append(f"Bends: ERP={erp_bends} != Pipeline={pipe_bends}")

    return comparison


def process_folder(folder_path, verbose=False):
    """Process a single folder with STEP files, Excel and XML."""
    folder_name = os.path.basename(folder_path)
    print(f"\n{'='*70}")
    print(f"FOLDER: {folder_name}")
    print(f"{'='*70}")

    # Find files
    step_files = glob.glob(os.path.join(folder_path, "*.step")) + \
                 glob.glob(os.path.join(folder_path, "*.STEP")) + \
                 glob.glob(os.path.join(folder_path, "*.stp"))

    excel_files = glob.glob(os.path.join(folder_path, "*.xlsx")) + \
                  glob.glob(os.path.join(folder_path, "*.xls"))

    xml_files = glob.glob(os.path.join(folder_path, "*.xml"))

    print(f"  STEP files: {len(step_files)}")
    print(f"  Excel files: {len(excel_files)}")
    print(f"  XML files: {len(xml_files)}")

    # Parse reference data
    erp_data = {}
    spaceclaim_data = {}

    for excel_file in excel_files:
        print(f"\n  Parsing Excel: {os.path.basename(excel_file)}")
        erp_data.update(parse_excel(excel_file))

    for xml_file in xml_files:
        print(f"  Parsing XML: {os.path.basename(xml_file)}")
        spaceclaim_data.update(parse_xml(xml_file))

    if verbose:
        print(f"\n  ERP parts: {list(erp_data.keys())}")
        print(f"  Spaceclaim parts: {list(spaceclaim_data.keys())}")

    # Process each STEP file
    results = []

    for step_file in step_files:
        part_name = Path(step_file).stem
        # Try to match with various naming conventions
        part_key = part_name

        # Check different variations
        for key in list(erp_data.keys()) + list(spaceclaim_data.keys()):
            if key.lower() in part_name.lower() or part_name.lower() in key.lower():
                part_key = key
                break

        print(f"\n  --- {part_name} ---")

        # Get reference data
        erp = erp_data.get(part_key) or erp_data.get(part_name)
        sc = spaceclaim_data.get(part_key) or spaceclaim_data.get(part_name)

        # Run pipeline analysis
        print(f"    Analyzing with pipeline...")
        pipeline = analyze_step_file(step_file)

        if pipeline is None:
            print(f"    ⚠ Pipeline analysis failed")
            continue

        # Compare
        comparison = compare_results(erp, sc, pipeline)

        # Print comparison
        print(f"\n    GATEN:")
        for source, count in comparison['holes'].items():
            print(f"      {source:20s}: {count}")

        print(f"\n    ZETTINGEN:")
        for source, count in comparison['bends'].items():
            print(f"      {source:20s}: {count}")

        print(f"\n    AFMETINGEN:")
        for source, dims in comparison['dimensions'].items():
            print(f"      {source:20s}: {dims} mm")

        # Show geometry comparison if available
        if comparison.get('geometry'):
            print(f"\n    GEOMETRY (Spaceclaim vs Pipeline):")
            for field, values in comparison['geometry'].items():
                print(f"      {field:15s}: SC={values['Spaceclaim']:>12s}  Pipe={values['Pipeline']:>12s}  diff={values['diff']:>6s}")

        if comparison['matches']:
            print(f"\n    ✓ MATCHES:")
            for m in comparison['matches']:
                print(f"      {m}")

        if comparison['mismatches']:
            print(f"\n    ✗ MISMATCHES:")
            for m in comparison['mismatches']:
                print(f"      {m}")

        results.append({
            'part_name': part_name,
            'erp': erp,
            'spaceclaim': sc,
            'pipeline': pipeline,
            'comparison': comparison,
        })

    return results


def main():
    parser = argparse.ArgumentParser(description="Compare ERP/Spaceclaim with Pipeline analysis")
    parser.add_argument("folder", nargs='?', default="/Users/ds/Projecten/alestest/data/parts/AI-voorbeelden",
                       help="Folder with subfolders containing STEP, Excel, and XML files")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    parser.add_argument("--subfolder", help="Process only specific subfolder")
    parser.add_argument("--aag", action="store_true",
                       help="Use AAG (Attributed Adjacency Graph) feature recognition")

    args = parser.parse_args()

    if args.aag and not AAG_AVAILABLE:
        print("Warning: AAG analyzer not available. Install aag_analyzer.py")
        print("Falling back to standard analysis.")

    base_folder = args.folder

    if not os.path.exists(base_folder):
        print(f"Error: Folder not found: {base_folder}")
        sys.exit(1)

    # Find subfolders
    if args.subfolder:
        subfolders = [os.path.join(base_folder, args.subfolder)]
    else:
        subfolders = [f.path for f in os.scandir(base_folder) if f.is_dir()]

    # Check if base folder itself contains STEP files
    base_step_files = glob.glob(os.path.join(base_folder, "*.step")) + \
                      glob.glob(os.path.join(base_folder, "*.STEP")) + \
                      glob.glob(os.path.join(base_folder, "*.stp"))

    process_base = len(base_step_files) > 0

    print(f"="*70)
    print(f"ERP/SPACECLAIM VERGELIJKING")
    print(f"Base folder: {base_folder}")
    print(f"Subfolders: {len(subfolders)}")
    if process_base:
        print(f"Base folder has {len(base_step_files)} STEP files - will process")
    if args.aag and AAG_AVAILABLE:
        print(f"Analysis mode: AAG (Attributed Adjacency Graph)")
    else:
        print(f"Analysis mode: Standard (FreeCAD unfold)")
    print(f"="*70)

    all_results = []

    # Process base folder if it has STEP files
    if process_base:
        results = process_folder(base_folder, args.verbose)
        all_results.extend(results)

    for subfolder in sorted(subfolders):
        results = process_folder(subfolder, args.verbose)
        all_results.extend(results)

    # Summary
    print(f"\n{'='*70}")
    print(f"SAMENVATTING")
    print(f"{'='*70}")

    total_parts = len(all_results)

    # Parts with ERP data
    parts_with_erp = [r for r in all_results if r.get('erp')]
    parts_with_spaceclaim = [r for r in all_results if r.get('spaceclaim')]

    erp_count = len(parts_with_erp)
    sc_count = len(parts_with_spaceclaim)

    # Match/mismatch counts for parts WITH ERP data
    holes_match = sum(1 for r in parts_with_erp
                      if any('Holes' in m for m in r['comparison'].get('matches', [])))
    bends_match = sum(1 for r in parts_with_erp
                      if any('Bends' in m for m in r['comparison'].get('matches', [])))

    holes_mismatch = sum(1 for r in parts_with_erp
                         if any('Holes' in m for m in r['comparison'].get('mismatches', [])))
    bends_mismatch = sum(1 for r in parts_with_erp
                         if any('Bends' in m for m in r['comparison'].get('mismatches', [])))

    print(f"\nTotaal onderdelen geanalyseerd: {total_parts}")
    print(f"  - Met ERP data: {erp_count}")
    print(f"  - Met Spaceclaim data: {sc_count}")
    print(f"  - Alleen pipeline: {total_parts - max(erp_count, sc_count)}")

    if erp_count > 0:
        print(f"\n--- Vergelijking met ERP (n={erp_count}) ---")
        print(f"\nGaten detectie:")
        print(f"  ✓ Match: {holes_match}/{erp_count} ({100*holes_match/erp_count:.0f}%)")
        print(f"  ✗ Mismatch: {holes_mismatch}/{erp_count} ({100*holes_mismatch/erp_count:.0f}%)")
        print(f"  ? Geen vergelijking: {erp_count - holes_match - holes_mismatch}/{erp_count}")

        print(f"\nZettingen detectie:")
        print(f"  ✓ Match: {bends_match}/{erp_count} ({100*bends_match/erp_count:.0f}%)")
        print(f"  ✗ Mismatch: {bends_mismatch}/{erp_count} ({100*bends_mismatch/erp_count:.0f}%)")
        print(f"  ? Geen vergelijking: {erp_count - bends_match - bends_mismatch}/{erp_count}")

    # Detailed mismatch analysis
    if holes_mismatch > 0 or bends_mismatch > 0:
        print(f"\n--- Mismatch details ---")
        for r in parts_with_erp:
            mismatches = r['comparison'].get('mismatches', [])
            if mismatches:
                erp = r.get('erp', {})
                pipe = r.get('pipeline', {})
                print(f"\n  {r['part_name']}:")
                for m in mismatches:
                    print(f"    {m}")
                if 'Holes' in str(mismatches):
                    print(f"    -> Pipeline detecteert {pipe.get('holes', 0)} gaten, ERP zegt {erp.get('holes', 0)}")
                if 'Bends' in str(mismatches):
                    print(f"    -> Pipeline detecteert {pipe.get('bends', 0)} bends, ERP zegt {erp.get('bends', 0)}")

    # Geometry comparison summary (Spaceclaim vs Pipeline)
    if sc_count > 0:
        print(f"\n--- Geometry vergelijking met Spaceclaim (n={sc_count}) ---")

        # Collect all geometry diffs
        vol_diffs = []
        area_diffs = []
        contour_diffs = []
        weight_diffs = []

        for r in parts_with_spaceclaim:
            geom = r['comparison'].get('geometry', {})
            if 'volume' in geom:
                diff_str = geom['volume']['diff'].replace('%', '')
                vol_diffs.append(float(diff_str))
            if 'top_area' in geom:
                diff_str = geom['top_area']['diff'].replace('%', '')
                area_diffs.append(float(diff_str))
            if 'total_contour' in geom:
                diff_str = geom['total_contour']['diff'].replace('%', '')
                contour_diffs.append(float(diff_str))
            if 'weight' in geom:
                diff_str = geom['weight']['diff'].replace('%', '')
                weight_diffs.append(float(diff_str))

        if vol_diffs:
            avg_vol = sum(vol_diffs) / len(vol_diffs)
            print(f"\n  Volume:        gem. afwijking {avg_vol:.1f}% (n={len(vol_diffs)})")
        if area_diffs:
            avg_area = sum(area_diffs) / len(area_diffs)
            print(f"  Top Area:      gem. afwijking {avg_area:.1f}% (n={len(area_diffs)})")
        if contour_diffs:
            avg_cont = sum(contour_diffs) / len(contour_diffs)
            print(f"  Total Contour: gem. afwijking {avg_cont:.1f}% (n={len(contour_diffs)})")
        if weight_diffs:
            avg_wt = sum(weight_diffs) / len(weight_diffs)
            print(f"  Weight (alu):  gem. afwijking {avg_wt:.1f}% (n={len(weight_diffs)})")


if __name__ == "__main__":
    main()
