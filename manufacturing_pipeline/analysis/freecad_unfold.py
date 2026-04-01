#!/opt/homebrew/Caskroom/freecad/1.0.2/FreeCAD.app/Contents/Resources/bin/python
"""
FreeCAD Sheet Metal Unfolder

Gebruikt FreeCAD's SheetMetal workbench om gebogen plaatwerk te ontbuigen
en een vlakke uitslag (flat pattern) te genereren.

Kan STEP files inladen, analyseren en ontvouwen naar DXF.
"""
import sys
import os
from typing import Optional, Any

import math
import json
import tempfile
from manufacturing_pipeline.analysis.sheetmetal import freecad_environment as _freecad_environment
from manufacturing_pipeline.analysis.sheetmetal import freecad_geometry as _freecad_geometry
from manufacturing_pipeline.analysis.sheetmetal import freecad_process as _freecad_process

FreeCAD = None
Part = None
_FREECAD_IMPORT_ERROR = None


def _candidate_freecad_paths():
    return _freecad_environment._candidate_freecad_paths()


def _should_prefer_freecadcmd() -> bool:
    return _freecad_environment._should_prefer_freecadcmd()


def _ensure_freecad_imported() -> bool:
    imported = _freecad_environment._ensure_freecad_imported()
    _sync_freecad_bindings()
    return imported


def _find_freecadcmd_executable() -> str:
    return _freecad_environment._find_freecadcmd_executable()


def _vector_components(value):
    return _freecad_geometry._vector_components(value)


def _normalize_components(x_value, y_value, z_value):
    return _freecad_geometry._normalize_components(x_value, y_value, z_value)


def _find_largest_planar_face(shape):
    return _freecad_geometry._find_largest_planar_face(shape)


def _choose_plane_basis(normal):
    return _freecad_geometry._choose_plane_basis(normal)


def _sample_edge_points(shape, samples_per_edge=33):
    return _freecad_geometry._sample_edge_points(shape, samples_per_edge=samples_per_edge)


def _measure_flat_pattern_dimensions(flat_shape):
    return _freecad_geometry._measure_flat_pattern_dimensions(flat_shape)


def _build_sheet_tree(sheetmetal_unfolder, shape, face_idx, k_factor_lookup, obj=None):
    try:
        return sheetmetal_unfolder.SheetTree(shape, face_idx, k_factor_lookup, obj)
    except TypeError as exc:
        if "takes 4 positional arguments but 5 were given" not in str(exc):
            raise
        return sheetmetal_unfolder.SheetTree(shape, face_idx, k_factor_lookup)


def _unfold_via_freecadcmd(step_path, output_dxf=None, k_factor=0.44, max_attempts=5, max_bends=None):
    """Run unfold in external FreeCAD runtime to avoid Python ABI conflicts."""
    freecadcmd = _find_freecadcmd_executable()
    if not freecadcmd:
        return {
            'success': False,
            'error': 'FreeCADCmd niet gevonden',
            'attempts': 0,
            'error_details': []
        }

    payload = {
        'step_path': str(step_path),
        'output_dxf': str(output_dxf) if output_dxf else '',
        'k_factor': float(k_factor),
        'max_attempts': int(max_attempts),
        'max_bends': int(max_bends) if max_bends and max_bends > 0 else 0,
    }

    script = f'''import importlib.util\nimport json\nimport Part\nimport FreeCAD\nimport math\n\nHELPER_MODULE_PATH = {json.dumps(os.path.abspath(__file__))}\nUNFOLD_ERROR_MESSAGES = {json.dumps(UNFOLD_ERROR_MESSAGES, ensure_ascii=False)}\n\nspec = importlib.util.spec_from_file_location("freecad_unfold_host", HELPER_MODULE_PATH)\nfreecad_unfold_host = importlib.util.module_from_spec(spec)\nspec.loader.exec_module(freecad_unfold_host)\n\ndef _result():\n    return {{\n        "success": False,\n        "flat_shape": None,\n        "flat_length": 0,\n        "flat_width": 0,\n        \n        "bend_angles": [],\n        "bend_radii": [],\n        "bend_lengths": [],\n        "bend_count": 0,\n        "bend_line_segments": [],\n        "bend_line_groups": [],\n        "error": None,\n        "attempts": 0,\n        "error_details": [],\n        "used_face_idx": None\n    }}\n\ndef _collect_bend_nodes(node, bend_list):\n    """Recursively collect Bend nodes from tree"""\n    if node is None:\n        return\n    try:\n        if hasattr(node, 'node_type'):\n            print(f"[DEBUG] Node type: {{node.node_type}}")\n            if node.node_type == 'Bend':\n                print(f"[DEBUG] Found Bend node!")\n                bend_list.append(node)\n        if hasattr(node, 'bend_angle') and node.bend_angle is not None:\n            print(f"[DEBUG] Node has bend_angle: {{node.bend_angle}}")\n        if hasattr(node, 'bend_dir') and node.bend_dir is not None:\n            print(f"[DEBUG] Node has bend_dir: {{node.bend_dir}}")\n        if hasattr(node, 'innerRadius') and node.innerRadius is not None:\n            print(f"[DEBUG] Node has innerRadius: {{node.innerRadius}}")\n\n        if hasattr(node, 'child_list'):\n            print(f"[DEBUG] Node has child_list attribute: {{node.child_list is not None}}, length: {{len(node.child_list) if node.child_list else 0}}")\n            if node.child_list:\n                print(f"[DEBUG] Node has {{len(node.child_list)}} children")\n                for child in node.child_list:\n                    _collect_bend_nodes(child, bend_list)\n        else:\n            print(f"[DEBUG] Node does NOT have child_list attribute")\n    except Exception as e:\n        print(f"[DEBUG] Error in _collect_bend_nodes: {{e}}")\n\ndef _signed_angle_deg(node):\n    raw_angle = getattr(node, 'bend_angle', None)\n    if raw_angle is None:\n        return None\n\n    try:\n        angle_deg = abs(float(raw_angle) * 180.0 / 3.14159265)\n    except Exception:\n        return None\n\n    direction = getattr(node, 'bend_dir', None)\n    sign = 1.0\n\n    if isinstance(direction, str):\n        token = direction.strip().lower()\n        if token in ('down', 'negative', '-', 'minus', '-1'):\n            sign = -1.0\n        elif token in ('up', 'positive', '+', 'plus', '1'):\n            sign = 1.0\n    elif isinstance(direction, (int, float)):\n        if float(direction) < 0:\n            sign = -1.0\n        elif float(direction) > 0:\n            sign = 1.0\n\n    return angle_deg * sign\n\ndef _extract_bends_from_tree(tree_root):\n    """Extract bend parameters from SheetTree node structure"""\n    result = {{\n        "bend_angles": [],\n        "bend_radii": [],\n        "bend_lengths": [],\n        "bend_count": 0\n    }}\n\n    try:\n        print(f"[DEBUG] Starting tree extraction...")\n        print(f"[DEBUG] Tree root type: {{type(tree_root).__name__}}")\n        print(f"[DEBUG] Tree root attributes: {{[attr for attr in dir(tree_root) if not attr.startswith('_')][:20]}}")\n        bend_nodes = []\n        _collect_bend_nodes(tree_root, bend_nodes)\n        print(f"[DEBUG] Found {{len(bend_nodes)}} bend nodes")\n\n        for node in bend_nodes:\n            try:\n                signed_angle = _signed_angle_deg(node)\n                if signed_angle is not None:\n                    result["bend_angles"].append(round(signed_angle, 2))\n                    print(f"[DEBUG] Bend angle: {{signed_angle}}°")\n\n                if hasattr(node, 'innerRadius') and node.innerRadius is not None:\n                    result["bend_radii"].append(round(node.innerRadius, 2))\n                    print(f"[DEBUG] Inner radius: {{node.innerRadius}} mm")\n\n                if hasattr(node, '_trans_length') and node._trans_length is not None:\n                    result["bend_lengths"].append(round(node._trans_length, 2))\n                    print(f"[DEBUG] Trans length: {{node._trans_length}} mm")\n                elif hasattr(node, 'p_wire') and node.p_wire is not None:\n                    try:\n                        result["bend_lengths"].append(round(node.p_wire.Length, 2))\n                        print(f"[DEBUG] Wire length: {{node.p_wire.Length}} mm")\n                    except:\n                        pass\n            except Exception as e:\n                print(f"[DEBUG] Error extracting from node: {{e}}")\n\n        result["bend_count"] = len(result["bend_angles"])\n        print(f"[DEBUG] Final bend_count: {{result['bend_count']}}")\n    except Exception as e:\n        print(f"[DEBUG] Error in _extract_bends_from_tree: {{e}}")\n\n    return result\n\ndef _analyze_bends(solid, max_bends=0):\n    """FALLBACK: Analyze cylindrical faces to extract bend parameters"""\n    bends = {{\n        "bend_angles": [],\n        "bend_radii": [],\n        "bend_lengths": [],\n        "bend_count": 0\n    }}\n\n    try:\n        cylinders = []\n        for face in solid.Faces:\n            try:\n                surf_type = face.Surface.TypeId\n                if "Cylinder" in surf_type:\n                    cyl = face.Surface\n                    radius = cyl.Radius\n                    u_min, u_max, v_min, v_max = face.ParameterRange\n                    angle_rad = abs(u_max - u_min)\n                    angle_deg = angle_rad * 180.0 / 3.14159265\n                    length = abs(v_max - v_min)\n\n                    if angle_rad > 0.3 and length > 5:\n                        cylinders.append({{\n                            "radius": radius,\n                            "angle_deg": angle_deg,\n                            "length": length,\n                            "area": face.Area\n                        }})\n            except:\n                pass\n\n        unique = {{}}\n        for cyl in cylinders:\n            key = (round(cyl["angle_deg"], 1), round(cyl["length"], 1))\n            if key not in unique:\n                unique[key] = cyl\n            elif cyl["radius"] < unique[key]["radius"]:\n                unique[key] = cyl\n\n        sorted_bends = sorted(unique.values(), key=lambda x: x["area"], reverse=True)\n        if max_bends > 0:\n            sorted_bends = sorted_bends[:max_bends]\n\n        for bend in sorted_bends:\n            bends["bend_radii"].append(round(bend["radius"], 2))\n            bends["bend_angles"].append(round(bend["angle_deg"], 2))\n            bends["bend_lengths"].append(round(bend["length"], 2))\n\n        bends["bend_count"] = len(sorted_bends)\n    except:\n        pass\n\n    return bends\n\ndef _candidates(shape):\n    planar = []\n    for i, face in enumerate(shape.Faces):\n        try:\n            t = face.Surface.TypeId\n            if "Plane" in t:\n                planar.append((i, face.Area))\n        except Exception:\n            pass\n    planar.sort(key=lambda x: x[1], reverse=True)\n    return planar\n\ndef run(data):\n    res = _result()\n    try:\n        shape = Part.read(data["step_path"])\n        if not shape.Solids:\n            res["error"] = "Geen solids gevonden in STEP file"\n            print(json.dumps(res))\n            return\n\n        solid = shape.Solids[0] if len(shape.Solids) > 1 else shape\n\n        cand = _candidates(solid)\n        if not cand:\n            res["error"] = "Geen vlakke oppervlakken gevonden"\n            print(json.dumps(res))\n            return\n\n        import SheetMetalUnfolder\n\n        k_lookup = {{}}\n        for t in [0.5, 0.75, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0, 12.0, 15.0, 20.0]:\n            k_lookup[t] = float(data["k_factor"])\n\n        attempts_to_try = min(int(data["max_attempts"]), len(cand))\n\n        for attempt, (face_idx, area) in enumerate(cand[:attempts_to_try]):\n            res["attempts"] = attempt + 1\n            doc = FreeCAD.newDocument("UnfoldDoc")\n            try:\n                obj = doc.addObject("Part::Feature", "SheetPart")\n                obj.Shape = solid\n                doc.recompute()\n\n                try:\n                    tree = SheetMetalUnfolder.SheetTree(solid, face_idx, k_lookup, obj)\n                except TypeError:\n                    tree = SheetMetalUnfolder.SheetTree(solid, face_idx, k_lookup)\n                if tree.error_code:\n                    msg = UNFOLD_ERROR_MESSAGES.get(tree.error_code, f"Onbekende fout ({{tree.error_code}})")\n                    res["error_details"].append({{"face_idx": face_idx, "stage": "init", "error_code": tree.error_code, "message": msg}})\n                    continue\n\n                tree.Bend_analysis(face_idx, None)\n                if tree.error_code:\n                    msg = UNFOLD_ERROR_MESSAGES.get(tree.error_code, f"Onbekende fout ({{tree.error_code}})")\n                    res["error_details"].append({{"face_idx": face_idx, "stage": "analysis", "error_code": tree.error_code, "message": msg}})\n                    continue\n\n                if hasattr(tree, "root") and tree.root:\n                    face_list, fold_lines = tree.unfold_tree2(tree.root)\n                    if tree.error_code:\n                        msg = UNFOLD_ERROR_MESSAGES.get(tree.error_code, f"Onbekende fout ({{tree.error_code}})")\n                        res["error_details"].append({{"face_idx": face_idx, "stage": "unfold", "error_code": tree.error_code, "message": msg}})\n                        continue\n\n                    print(f"[DEBUG] fold_lines: {{type(fold_lines).__name__}}, length: {{len(fold_lines) if fold_lines else 0}}")\n                    if fold_lines:\n                        for i, line in enumerate(fold_lines[:3]):\n                            print(f"[DEBUG] fold_line[{{i}}]: {{type(line).__name__}}")\n                            if hasattr(line, '__dict__'):\n                                print(f"[DEBUG] fold_line[{{i}}] dict: {{line.__dict__}}")\n\n                    bend_params = _extract_bends_from_tree(tree.root)\n                    res["bend_angles"] = bend_params["bend_angles"]\n                    res["bend_radii"] = bend_params["bend_radii"]\n                    res["bend_lengths"] = bend_params["bend_lengths"]\n                    res["bend_count"] = bend_params["bend_count"]\n\n                    if res["bend_count"] == 0:\n                        bend_params_fallback = _analyze_bends(solid, max_bends=int(data.get("max_bends", 0)))\n                        res["bend_angles"] = bend_params_fallback["bend_angles"]\n                        res["bend_radii"] = bend_params_fallback["bend_radii"]\n                        res["bend_lengths"] = bend_params_fallback["bend_lengths"]\n                        res["bend_count"] = bend_params_fallback["bend_count"]\n                    if tree.error_code:\n                        msg = UNFOLD_ERROR_MESSAGES.get(tree.error_code, f"Onbekende fout ({{tree.error_code}})")\n                        res["error_details"].append({{"face_idx": face_idx, "stage": "unfold", "error_code": tree.error_code, "message": msg}})\n                        continue\n\n                    if face_list:\n                        try:\n                            flat_shape = Part.Shell(face_list)\n                        except Exception:\n                            flat_shape = Part.Compound(face_list)\n\n                        dims_info = freecad_unfold_host._measure_flat_pattern_dimensions(flat_shape)\n                        res["flat_length"] = dims_info["flat_length"]\n                        res["flat_width"] = dims_info["flat_width"]\n                        res["bend_line_segments"] = freecad_unfold_host._extract_fold_line_segments_from_edges(fold_lines, flat_shape)\n\n                        res["success"] = True\n                        res["used_face_idx"] = int(face_idx)\n\n                        if data.get("output_dxf"):\n                            try:\n                                import importDXF\n                                export_doc = FreeCAD.newDocument("ExportDoc")\n                                exp_obj = export_doc.addObject("Part::Feature", "FlatPattern")\n                                exp_obj.Shape = flat_shape\n                                importDXF.export([exp_obj], data["output_dxf"])\n                                FreeCAD.closeDocument("ExportDoc")\n                            except Exception:\n                                pass\n\n                        print(json.dumps(res))\n                        return\n\n            except Exception as e:\n                res["error_details"].append({{"face_idx": int(face_idx), "stage": "exception", "error_code": -1, "message": str(e)}})\n            finally:\n                try:\n                    FreeCAD.closeDocument("UnfoldDoc")\n                except Exception:\n                    pass\n\n        if res["error_details"]:\n            code = res["error_details"][-1].get("error_code", -1)\n            res["error"] = UNFOLD_ERROR_MESSAGES.get(code, f"Unfold gefaald na {{res['attempts']}} pogingen")\n        else:\n            res["error"] = f"Unfold gefaald na {{res['attempts']}} pogingen"\n\n    except Exception as e:\n        res["error"] = str(e)\n\n    print(json.dumps(res))\n\nrun({json.dumps(payload)})\n'''

    return _freecad_process.run_freecadcmd_script(
        freecadcmd,
        script,
        timeout_seconds=300,
    )

# Mock FreeCADGui voor headless mode
class MockSelection:
    """Mock Selection class voor headless gebruik"""
    _selection = []

    @classmethod
    def getSelection(cls):
        return cls._selection

    @classmethod
    def clearSelection(cls):
        cls._selection = []

    @classmethod
    def addSelection(cls, obj):
        cls._selection.append(obj)


class MockFreeCADGui:
    """Mock FreeCADGui module voor headless gebruik"""
    Selection = MockSelection()


# Probeer echte FreeCADGui, anders gebruik mock
try:
    import FreeCADGui
    # Test of Selection werkt
    FreeCADGui.Selection.getSelection()
except (ImportError, AttributeError):
    # Gebruik mock in headless mode
    import sys
    sys.modules['FreeCADGui'] = MockFreeCADGui()
    FreeCADGui = MockFreeCADGui()


def find_largest_planar_face(shape):
    """
    Vind het grootste vlakke oppervlak in een shape.
    Dit is typisch de 'base' face voor het ontbuigen.
    """
    largest_face = None
    largest_area = 0

    for i, face in enumerate(shape.Faces):
        # Check of het een vlak (plane) is
        surface = face.Surface
        if hasattr(surface, 'isPlanar') and surface.isPlanar():
            area = face.Area
            if area > largest_area:
                largest_area = area
                largest_face = (i, face)

    return largest_face


def find_base_face_for_unfold(shape):
    """
    Automatisch de beste base face vinden voor het ontbuigen.
    Zoekt naar het grootste vlakke oppervlak.
    """
    planar_faces = []

    for i, face in enumerate(shape.Faces):
        try:
            # Probeer te bepalen of het vlak is
            surf_type = face.Surface.TypeId
            if 'Plane' in surf_type:
                planar_faces.append({
                    'index': i,
                    'face': face,
                    'area': face.Area,
                    'normal': face.normalAt(0, 0)
                })
        except Exception:
            continue

    if not planar_faces:
        return None

    # Sorteer op oppervlakte (grootste eerst)
    planar_faces.sort(key=lambda x: x['area'], reverse=True)

    return planar_faces[0]


def find_all_base_face_candidates(shape):
    """
    Vind alle mogelijke base faces, gesorteerd op geschiktheid.
    Returns lijst van candidates voor als de eerste niet werkt.
    """
    planar_faces = []

    for i, face in enumerate(shape.Faces):
        try:
            surf_type = face.Surface.TypeId
            if 'Plane' in surf_type:
                planar_faces.append({
                    'index': i,
                    'face': face,
                    'area': face.Area,
                    'normal': face.normalAt(0, 0)
                })
        except Exception:
            continue

    if not planar_faces:
        return []

    # Sorteer op oppervlakte (grootste eerst)
    planar_faces.sort(key=lambda x: x['area'], reverse=True)

    return planar_faces


def extract_bend_info_from_tree(unfold_tree):
    """
    Extraheer bend-parameters (hoeken, radii, lengtes) uit SheetTree object.
    Loopt door de tree structure en haalt alleen echte Bend nodes op.
    
    Returns:
        dict met:
            - bend_angles: komma-gescheiden hoeken [in graden]
            - bend_radii: komma-gescheiden binnenstralen [in mm]
            - bend_lengths: komma-gescheiden lengtes [in mm]
            - bend_count: aantal bends
    """
    result = {
        'bend_angles': [],
        'bend_radii': [],
        'bend_lengths': [],
        'bend_count': 0
    }
    
    try:
        # Start from root node and traverse tree to find all Bend nodes
        if not hasattr(unfold_tree, 'root') or not unfold_tree.root:
            print(f"[DEBUG] extract_bend_info_from_tree: No root node found in SheetTree")
            return result
        
        print(f"[DEBUG] extract_bend_info_from_tree: Starting traversal from root")
        bend_nodes = []
        _collect_bend_nodes(unfold_tree.root, bend_nodes)
        
        print(f"[DEBUG] extract_bend_info_from_tree: Found {len(bend_nodes)} bend nodes")
        if not bend_nodes:
            return result
        
        # Extract parameters from each bend node
        for node in bend_nodes:
            try:
                # These attributes are set by SheetMetal's Bend_analysis()
                if hasattr(node, 'bend_angle') and node.bend_angle is not None:
                    # Convert from radians to degrees and preserve bend direction.
                    angle_deg = abs(math.degrees(node.bend_angle))
                    bend_dir = getattr(node, 'bend_dir', None)
                    if isinstance(bend_dir, str) and bend_dir.strip().lower() in {'down', 'negative', '-', 'minus', '-1'}:
                        angle_deg = -angle_deg
                    elif isinstance(bend_dir, (int, float)) and float(bend_dir) < 0:
                        angle_deg = -angle_deg
                    result['bend_angles'].append(round(float(angle_deg), 2))
                
                if hasattr(node, 'innerRadius') and node.innerRadius is not None:
                    result['bend_radii'].append(round(float(node.innerRadius), 2))
                
                # Calculate bend length from the edge length or face parameters
                if hasattr(node, '_trans_length') and node._trans_length is not None:
                    # This is the actual bend arc length along neutral axis
                    result['bend_lengths'].append(round(float(node._trans_length), 2))
                elif hasattr(node, 'p_wire') and node.p_wire is not None:
                    # Fallback: use parent wire length
                    try:
                        length = node.p_wire.Length
                        result['bend_lengths'].append(round(float(length), 2))
                    except:
                        pass
                        
            except (AttributeError, TypeError, ValueError) as e:
                print(f"[DEBUG] Error processing bend node: {e}")
                continue
        
        result['bend_count'] = len(result['bend_angles'])
        
        if result['bend_count'] > 0:
            print(f"[INFO] Extracted {result['bend_count']} bends from SheetTree")
            for i in range(result['bend_count']):
                angle = result['bend_angles'][i] if i < len(result['bend_angles']) else 'N/A'
                radius = result['bend_radii'][i] if i < len(result['bend_radii']) else 'N/A'
                length = result['bend_lengths'][i] if i < len(result['bend_lengths']) else 'N/A'
                print(f"  Bend {i+1}: angle={angle}°, radius={radius}mm, length={length}mm")
        
    except Exception as e:
        print(f"[DEBUG] Error in extract_bend_info_from_tree: {e}")
        import traceback
        traceback.print_exc()
    
    return result


def _collect_bend_nodes(node, bend_list):
    """Recursively collect all Bend type nodes from the tree."""
    if node is None:
        print(f"[DEBUG] _collect_bend_nodes: node is None")
        return
    
    try:
        # Check if this is a Bend node
        if hasattr(node, 'node_type'):
            print(f"[DEBUG] _collect_bend_nodes: node_type = {node.node_type}")
            if node.node_type == 'Bend':
                print(f"[DEBUG] _collect_bend_nodes: Found Bend node!")
                bend_list.append(node)
        else:
            print(f"[DEBUG] _collect_bend_nodes: node has no node_type attribute")
        
        # Traverse children
        if hasattr(node, 'child_list') and node.child_list:
            print(f"[DEBUG] _collect_bend_nodes: node has {len(node.child_list)} children")
            for child in node.child_list:
                _collect_bend_nodes(child, bend_list)
        else:
            print(f"[DEBUG] _collect_bend_nodes: node has no child_list or it's empty")
                
    except Exception as e:
        print(f"[DEBUG] Error traversing node: {e}")


def analyze_sheet_bends(solid, max_bends=None):
    """
    Analyseer alle cylindrische faces in een solid om bend-parameters op te halen.
    Dit is de meest betrouwbare manier om bend-info te achterhalen.
    
    Args:
        solid: FreeCAD solid to analyze
        max_bends: Optional limit to return only top N bends by area
    
    Returns:
        dict met bend_angles, bend_radii, bend_lengths (deduplicated per unique bend)
    """
    result = {
        'bend_angles': [],
        'bend_radii': [],
        'bend_lengths': [],
        'bend_count': 0
    }
    
    try:
        # Find all cylindrical faces (these represent bends)
        cylinders = []
        
        for face in solid.Faces:
            try:
                surf_type = face.Surface.TypeId
                if 'Cylinder' in surf_type:
                    cyl = face.Surface
                    radius = cyl.Radius
                    
                    # Get the parameterization of the face
                    # U is angular (around the cylinder), V is axial
                    u_min, u_max, v_min, v_max = face.ParameterRange
                    
                    # Angle in radians
                    angle_rad = abs(u_max - u_min)
                    angle_deg = math.degrees(angle_rad)
                    
                    # Length along the cylinder axis
                    length = abs(v_max - v_min)
                    
                    # Only consider prominent bends (not just edge curves)
                    if angle_rad > 0.3 and length > 5:  # At least 0.3 rad ~= 17 degrees
                        cylinders.append({
                            'radius': radius,
                            'angle_rad': angle_rad,
                            'angle_deg': angle_deg,
                            'length': length,
                            'area': face.Area
                        })
            except Exception:
                continue
        
        # Group cylinders by bend (same angle & length, different radii are inner/outer faces)
        # This deduplicates: a bend typically has 2 faces (inner and outer radius)
        unique_bends = {}
        for cyl in cylinders:
            # Key by angle and length to group related faces
            key = (round(cyl['angle_deg'], 1), round(cyl['length'], 1))
            if key not in unique_bends:
                # Take the smaller radius (inner radius) as the canonical one
                unique_bends[key] = cyl
            else:
                # If this radius is smaller, use it (inner radius)
                if cyl['radius'] < unique_bends[key]['radius']:
                    unique_bends[key] = cyl
        
        # Sort by area of first occurrence (roughly by prominence)
        sorted_bends = sorted(unique_bends.values(), key=lambda c: c['area'], reverse=True)
        
        # Limit to top N if specified (e.g., from part_analyzer)
        if max_bends and max_bends > 0:
            sorted_bends = sorted_bends[:max_bends]
        
        # Extract parameters
        for bend in sorted_bends:
            result['bend_radii'].append(round(float(bend['radius']), 2))
            result['bend_angles'].append(round(float(bend['angle_deg']), 2))
            result['bend_lengths'].append(round(float(bend['length']), 2))
        
        result['bend_count'] = len(sorted_bends)
        
        if sorted_bends:
            print(f"[INFO] Found {len(sorted_bends)} unique cylindrical bends")
            for i, b in enumerate(sorted_bends):
                print(f"  Bend {i+1}: radius={b['radius']:.1f}mm, angle={b['angle_deg']:.1f}°, length={b['length']:.1f}mm")
        
    except Exception as e:
        print(f"[DEBUG] Error in analyze_sheet_bends: {e}")
    
    return result


# Error code vertaling
UNFOLD_ERROR_MESSAGES = {
    1: "Volume onbruikbaar - geen echt 3D sheet metal met uniforme dikte",
    2: "Ongeldige punt voor dikte meting",
    3: "Ongeldige dikte - plaatdikte niet consistent of te complex",
    4: "Ongeldige shape",
    5: "Shape heeft onnodige edges - gebruik 'Refine Shape' eerst",
    10: "Geen wires in sheet edge analyse",
    11: "Dubbele buigingen niet ondersteund",
    12: "Meer dan één bend-child niet ondersteund",
    13: "Plaatdikte ongeldig voor dit vlak",
    14: "Edges zonder buur-vlakken",
    15: "Alle sheet edges moeten een vlak hebben",
    16: "Starthoek van buiging niet gevonden",
    17: "Type oppervlak niet ondersteund voor sheet metal",
    20: "Section wire met minder dan 4 edges",
    21: "Section wire niet gesloten",
    22: "Section gefaald",
    23: "CutToolWire niet gesloten",
    24: "Bend-face zonder child niet geïmplementeerd",
    26: "Niet-ondersteund curve type in unbendFace",
}


def _merge_adjacent_bends(bend_angles, bend_radii, bend_lengths):
    """
    Merge bends that are likely part of the same bend line but interrupted by holes.
    
    Criteria for merging:
    - Same angle (e.g., all 90°)
    - Same radius (inner radius)
    - Adjacent in sequence (FreeCAD likely detected them in order)
    
    This removes artificial "bend splits" caused by holes that interrupt a bend line.
    Example: A single 90° bend interrupted by 2 holes appears as 3 separate bends,
    but should be counted as 1 bend if the gaps are small.
    
    Args:
        bend_angles: List of bend angles in degrees
        bend_radii: List of inner bend radii in mm
        bend_lengths: List of bend lengths in mm
    
    Returns:
        Tuple of (merged_angles, merged_radii, merged_lengths)
    """
    if not bend_angles:
        return bend_angles, bend_radii, bend_lengths
    
    # Build list of bends with metadata
    bends = []
    for i in range(len(bend_angles)):
        bends.append({
            'angle': bend_angles[i],
            'radius': bend_radii[i] if i < len(bend_radii) else None,
            'length': bend_lengths[i] if i < len(bend_lengths) else None,
            'index': i
        })
    
    # Merge adjacent bends with identical angle and radius
    merged = []
    i = 0
    while i < len(bends):
        current = bends[i].copy()
        merged_count = 0
        
        # Look ahead for similar bends
        j = i + 1
        while j < len(bends):
            next_bend = bends[j]
            # Merge if: same angle AND same radius
            if (current['angle'] == next_bend['angle'] and 
                current['radius'] == next_bend['radius']):
                merged_count += 1
                j += 1
            else:
                break
        
        # Report merging
        if merged_count > 0:
            print(f"[INFO] Merged {merged_count} adjacent bends into 1 "
                  f"(angle={current['angle']}°, radius={current['radius']}mm) "
                  f"- likely interrupted by holes")
        
        merged.append(current)
        i = j
    
    # Extract back into lists
    merged_angles = [b['angle'] for b in merged]
    merged_radii = [b['radius'] for b in merged if b['radius'] is not None]
    merged_lengths = [b['length'] for b in merged if b['length'] is not None]
    
    original_count = len(bend_angles)
    merged_count = len(merged_angles)
    if original_count != merged_count:
        print(f"[INFO] Bend count: {original_count} -> {merged_count} after merging")
    
    return merged_angles, merged_radii, merged_lengths


def _extract_fold_line_segments_from_edges(fold_lines, flat_shape=None):
    """Extract serializable fold line segment metadata from Part.Edge objects."""
    segments = []
    if not fold_lines:
        return segments

    long_axis = 'X'
    long_min = 0.0
    flat_length = 0.0
    if flat_shape is not None:
        try:
            fbbox = flat_shape.BoundBox
            if fbbox.YLength > fbbox.XLength:
                long_axis = 'Y'
                long_min = float(fbbox.YMin)
                flat_length = float(fbbox.YLength)
            else:
                long_axis = 'X'
                long_min = float(fbbox.XMin)
                flat_length = float(fbbox.XLength)
        except Exception:
            pass

    for idx, line in enumerate(fold_lines):
        try:
            bb = line.BoundBox
            cx = float((bb.XMin + bb.XMax) / 2.0)
            cy = float((bb.YMin + bb.YMax) / 2.0)
            cz = float((bb.ZMin + bb.ZMax) / 2.0)
            x_len = float(bb.XLength)
            y_len = float(bb.YLength)

            # Segment axis follows the long dimension of the segment in the flat pattern plane.
            seg_axis = 'X' if x_len >= y_len else 'Y'
            line_offset_axis = 'Y' if seg_axis == 'X' else 'X'
            line_offset = cy if line_offset_axis == 'Y' else cx
            axis_span = [
                float(bb.XMin if seg_axis == 'X' else bb.YMin),
                float(bb.XMax if seg_axis == 'X' else bb.YMax),
            ]

            pos_along_length = None
            if flat_length > 0:
                long_center = cx if long_axis == 'X' else cy
                pos_along_length = round(long_center - long_min - flat_length / 2.0, 3)

            segments.append({
                'index': idx,
                'axis': seg_axis,
                'line_offset_axis': line_offset_axis,
                'line_offset': round(line_offset, 3),
                'axis_span': [round(axis_span[0], 3), round(axis_span[1], 3)],
                'center': [round(cx, 3), round(cy, 3), round(cz, 3)],
                'length': round(float(getattr(line, 'Length', 0.0)), 3),
                'pos_along_length': pos_along_length,
            })
        except Exception:
            continue

    return segments


def _merge_bends_by_collinear_segments(
    bend_angles,
    bend_radii,
    bend_lengths,
    segments,
    offset_tol=2.0,
    gap_tol=120.0,
    overlap_tol=5.0,
    angle_tol=1.0,
    radius_tol=0.5,
):
    """Merge bend segments by geometric collinearity (same line offset), not by sequence.

    A physical bend line can be split into multiple segments by holes/cut-outs.
    Segments belong to the same bend line when they have:
    - same segment axis (X or Y)
    - line_offset within tolerance on the perpendicular axis
    - comparable bend angle/radius
    - spans that are in each other's extension (small gap), not heavily overlapping
    """
    if not bend_angles:
        return bend_angles, bend_radii, bend_lengths, []

    if not segments:
        # No geometric segment data available: keep original bends to avoid false merges.
        return bend_angles, bend_radii, bend_lengths, []

    usable = []
    for s in segments:
        try:
            axis = s.get('axis')
            offset = float(s.get('line_offset'))
            idx = int(s.get('index'))
            axis_span = s.get('axis_span')
            if not isinstance(axis_span, list) or len(axis_span) != 2:
                continue
            span_min = float(min(axis_span[0], axis_span[1]))
            span_max = float(max(axis_span[0], axis_span[1]))
            if not math.isfinite(span_min) or not math.isfinite(span_max):
                continue
            angle = float(bend_angles[idx]) if idx < len(bend_angles) else None
            radius = float(bend_radii[idx]) if idx < len(bend_radii) else None
            if axis not in ('X', 'Y'):
                continue
            if not math.isfinite(offset):
                continue
            if idx < 0:
                continue
            usable.append((axis, offset, idx, span_min, span_max, angle, radius, s))
        except Exception:
            continue

    if not usable:
        return bend_angles, bend_radii, bend_lengths, []

    usable.sort(key=lambda item: (item[0], item[1], item[3]))

    def _effective_gap_tol(prev_span, next_span):
        prev_len = max(0.0, float(prev_span[1]) - float(prev_span[0]))
        next_len = max(0.0, float(next_span[1]) - float(next_span[0]))
        dynamic_tol = max(
            float(gap_tol),
            2.0 * max(prev_len, next_len),
            5.0 * min(prev_len, next_len),
        )
        return min(dynamic_tol, 500.0)

    clusters = []
    current = None
    for axis, offset, idx, span_min, span_max, angle, radius, seg in usable:
        if current is None:
            current = {
                'axis': axis,
                'offset_ref': offset,
                'members': [idx],
                'segments': [seg],
                'spans': [(span_min, span_max)],
                'angle_ref': angle,
                'radius_ref': radius,
            }
            continue

        same_line = current['axis'] == axis and abs(offset - current['offset_ref']) <= float(offset_tol)
        if not same_line:
            clusters.append(current)
            current = {
                'axis': axis,
                'offset_ref': offset,
                'members': [idx],
                'segments': [seg],
                'spans': [(span_min, span_max)],
                'angle_ref': angle,
                'radius_ref': radius,
            }
            continue

        angle_ok = True
        if current['angle_ref'] is not None and angle is not None:
            angle_ok = abs(float(angle) - float(current['angle_ref'])) <= float(angle_tol)

        radius_ok = True
        if current['radius_ref'] is not None and radius is not None:
            radius_ok = abs(float(radius) - float(current['radius_ref'])) <= float(radius_tol)

        last_span_min, last_span_max = current['spans'][-1]
        overlap = max(0.0, min(last_span_max, span_max) - max(last_span_min, span_min))
        gap = max(0.0, span_min - last_span_max)

        # Treat hole interruptions as one physical bend when the gap is still
        # reasonable relative to the neighboring segment lengths.
        gap_limit = _effective_gap_tol((last_span_min, last_span_max), (span_min, span_max))
        extension_ok = overlap <= float(overlap_tol) and gap <= gap_limit

        if angle_ok and radius_ok and extension_ok:
            current['members'].append(idx)
            current['segments'].append(seg)
            current['spans'].append((span_min, span_max))
        else:
            clusters.append(current)
            current = {
                'axis': axis,
                'offset_ref': offset,
                'members': [idx],
                'segments': [seg],
                'spans': [(span_min, span_max)],
                'angle_ref': angle,
                'radius_ref': radius,
            }

    if current is not None:
        clusters.append(current)

    merged_angles = []
    merged_radii = []
    merged_lengths = []
    groups = []

    for group_id, cluster in enumerate(clusters, start=1):
        members = sorted(set(cluster['members']))
        if not members:
            continue

        first_idx = members[0]
        angle = bend_angles[first_idx] if first_idx < len(bend_angles) else None
        radius = bend_radii[first_idx] if first_idx < len(bend_radii) else None

        lengths = []
        for m in members:
            if m < len(bend_lengths) and bend_lengths[m] is not None:
                lengths.append(float(bend_lengths[m]))
        merged_len = round(sum(lengths), 3) if lengths else None

        if angle is not None:
            merged_angles.append(angle)
        if radius is not None:
            merged_radii.append(radius)
        if merged_len is not None:
            merged_lengths.append(merged_len)

        pos_vals = [s.get('pos_along_length') for s in cluster['segments'] if s.get('pos_along_length') is not None]
        pos_mean = round(sum(pos_vals) / len(pos_vals), 3) if pos_vals else None

        groups.append({
            'id': group_id,
            'axis': cluster['axis'],
            'line_offset': round(cluster['offset_ref'], 3),
            'segment_count': len(cluster['segments']),
            'segment_indices': members,
            'pos_along_length': pos_mean,
        })

    if len(merged_angles) != len(bend_angles):
        print(f"[INFO] Bend count: {len(bend_angles)} -> {len(merged_angles)} after collinear merge")

    return merged_angles, merged_radii, merged_lengths, groups


def unfold_sheet_metal(
    step_path: Optional[str] = None,
    solid_object: Optional[Any] = None,
    output_dxf: Optional[str] = None,
    k_factor: float = 0.44,
    max_attempts: int = 5,
    max_bends: Optional[int] = None
):
    """
    Ontbuig een sheet metal STEP file naar een vlakke uitslag.

    Args:
        step_path: Pad naar STEP bestand (optioneel als solid_object gegeven)
        solid_object: Direct solid object om te unfolden (alternatief voor step_path)
        output_dxf: Pad voor DXF output (optioneel)
        k_factor: K-factor voor buigberekening (default 0.44)
        max_attempts: Max aantal base faces om te proberen
        max_bends: Limiteer aantal geretourneerde bends (voor ERP)

    Returns:
        dict met resultaten:
            - success: bool
            - flat_shape: Part.Shape van de vlakke uitslag
            - flat_length: lengte van uitslag
            - flat_width: breedte van uitslag
            - bend_lines: lijst met buiglijnen
            - bend_angles: lijst met hoeken (degrees)
            - bend_radii: lijst met binnenstralen (mm)
            - bend_lengths: lijst met lengtes (mm)  
            - bend_count: aantal bends
            - error: foutmelding indien mislukt
            - attempts: aantal pogingen
            - error_details: gedetailleerde foutinfo
    """
    result = {
        'success': False,
        'flat_shape': None,
        'flat_length': 0,
        'flat_width': 0,
        'bend_lines': [],
        'bend_angles': [],
        'bend_radii': [],
        'bend_lengths': [],
        'bend_count': 0,
        'bend_line_segments': [],
        'bend_line_groups': [],
        'error': None,
        'attempts': 0,
        'error_details': [],
        'used_face_idx': None
    }

    prefer_subprocess = _should_prefer_freecadcmd()
    freecadcmd = _find_freecadcmd_executable()

    def _run_subprocess_fallback():
        print("[INFO] Using subprocess fallback (FreeCADCmd)")

        temp_step = None
        fallback_step_path = step_path

        if solid_object is not None:
            try:
                temp_step = tempfile.NamedTemporaryFile(suffix='.step', delete=False).name
                print(f"[INFO] Writing solid to temp STEP: {temp_step}")

                try:
                    from OCP.STEPControl import STEPControl_Writer, STEPControl_AsIs
                    from OCP.IFSelect import IFSelect_RetDone

                    writer = STEPControl_Writer()
                    writer.Transfer(solid_object, STEPControl_AsIs)
                    status = writer.Write(temp_step)

                    if status != IFSelect_RetDone:
                        raise Exception(f"STEP write failed with status: {status}")

                    fallback_step_path = temp_step
                    print("[INFO] Solid exported to temp STEP successfully")
                except Exception as e:
                    print(f"[WARN] Could not write solid to temp STEP: {e}")
                    result['error'] = f"Cannot use solid object with subprocess fallback: {e}"
                    return result
            except Exception as e:
                result['error'] = f"Failed to create temp STEP for solid: {e}"
                return result

        try:
            fallback_result = _unfold_via_freecadcmd(fallback_step_path, output_dxf, k_factor, max_attempts, max_bends)
            if fallback_result.get('success'):
                merged_angles, merged_radii, merged_lengths, merged_groups = _merge_bends_by_collinear_segments(
                    fallback_result.get('bend_angles', []),
                    fallback_result.get('bend_radii', []),
                    fallback_result.get('bend_lengths', []),
                    fallback_result.get('bend_line_segments', []),
                )
                fallback_result['bend_angles'] = merged_angles
                fallback_result['bend_radii'] = merged_radii
                fallback_result['bend_lengths'] = merged_lengths
                fallback_result['bend_count'] = len(merged_angles)
                fallback_result['bend_line_groups'] = merged_groups
                return fallback_result
            result['error'] = fallback_result.get('error') or f"FreeCAD niet beschikbaar: {_FREECAD_IMPORT_ERROR or 'onbekende importfout'}"
            result['attempts'] = fallback_result.get('attempts', 0)
            result['error_details'] = fallback_result.get('error_details', [])
            return result
        finally:
            if temp_step and os.path.exists(temp_step):
                try:
                    os.remove(temp_step)
                except Exception:
                    pass

    if prefer_subprocess and freecadcmd:
        return _run_subprocess_fallback()

    if not _ensure_freecad_imported():
        if freecadcmd:
            return _run_subprocess_fallback()
        print("[INFO] Using subprocess fallback (FreeCAD not directly importable)")
        result['error'] = f"FreeCAD niet beschikbaar: {_FREECAD_IMPORT_ERROR or 'onbekende importfout'}"
        return result

    try:
        # Import STEP or use provided solid
        print(f"[INFO] Using direct FreeCAD import")
        if solid_object is not None:
            print(f"Using provided solid object")
            shape = solid_object
        elif step_path is not None:
            print(f"Loading STEP: {step_path}")
            shape = Part.read(step_path)
        else:
            result['error'] = "Either step_path or solid_object must be provided"
            return result

        if not shape.Solids:
            result['error'] = "Geen solids gevonden in STEP file"
            return result

        solid = shape.Solids[0] if len(shape.Solids) > 1 else shape
        
        # Analyze bends in solid first (for bend parameters)
        bend_params = analyze_sheet_bends(solid, max_bends=max_bends)
        result['bend_angles'] = bend_params['bend_angles']
        result['bend_radii'] = bend_params['bend_radii']
        result['bend_lengths'] = bend_params['bend_lengths']
        result['bend_count'] = bend_params['bend_count']

        # Vind ALLE mogelijke base faces
        base_candidates = find_all_base_face_candidates(solid)
        if not base_candidates:
            result['error'] = "Geen vlakke oppervlakken gevonden - niet geschikt voor ontbuigen"
            return result

        print(f"Gevonden {len(base_candidates)} kandidaat base faces")

        # Import SheetMetal Unfolder
        import SheetMetalUnfolder

        # K-factor lookup (standaard waarden per dikte)
        kFactorLookup = {}
        for t in [0.5, 0.75, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0, 12.0, 15.0, 20.0]:
            kFactorLookup[t] = k_factor

        # Probeer meerdere base faces
        attempts_to_try = min(max_attempts, len(base_candidates))

        for attempt, base_info in enumerate(base_candidates[:attempts_to_try]):
            result['attempts'] = attempt + 1
            base_face_idx = base_info['index']

            print(f"\nPoging {attempt + 1}/{attempts_to_try}: face {base_face_idx} (area {base_info['area']:.1f} mm²)")

            # Maak een FreeCAD document voor de operatie
            doc = FreeCAD.newDocument("UnfoldDoc")

            try:
                # Voeg shape toe aan document
                obj = doc.addObject("Part::Feature", "SheetPart")
                obj.Shape = solid
                doc.recompute()

                # Mock object wrapper die Refine attribuut heeft
                class ObjWrapper:
                    def __init__(self, real_obj):
                        self._obj = real_obj
                        self.Refine = False

                    def __getattr__(self, name):
                        return getattr(self._obj, name)

                wrapped_obj = ObjWrapper(obj)
                MockSelection._selection = [wrapped_obj]

                unfold_tree = _build_sheet_tree(
                    SheetMetalUnfolder,
                    solid,
                    base_face_idx,
                    kFactorLookup,
                    wrapped_obj,
                )

                # Check for init errors
                if unfold_tree.error_code:
                    err_msg = UNFOLD_ERROR_MESSAGES.get(unfold_tree.error_code, f"Onbekende fout ({unfold_tree.error_code})")
                    result['error_details'].append({
                        'face_idx': base_face_idx,
                        'stage': 'init',
                        'error_code': unfold_tree.error_code,
                        'message': err_msg
                    })
                    print(f"  ✗ Init fout: {err_msg}")
                    continue

                # Bend analysis
                unfold_tree.Bend_analysis(base_face_idx, None)

                if unfold_tree.error_code:
                    err_msg = UNFOLD_ERROR_MESSAGES.get(unfold_tree.error_code, f"Onbekende fout ({unfold_tree.error_code})")
                    result['error_details'].append({
                        'face_idx': base_face_idx,
                        'stage': 'analysis',
                        'error_code': unfold_tree.error_code,
                        'message': err_msg
                    })
                    print(f"  ✗ Analysis fout: {err_msg}")
                    continue

                # Genereer de unfolded shape
                if hasattr(unfold_tree, 'root') and unfold_tree.root:
                    theFaceList, foldLines = unfold_tree.unfold_tree2(unfold_tree.root)

                    if unfold_tree.error_code:
                        err_msg = UNFOLD_ERROR_MESSAGES.get(unfold_tree.error_code, f"Onbekende fout ({unfold_tree.error_code})")
                        result['error_details'].append({
                            'face_idx': base_face_idx,
                            'stage': 'unfold',
                            'error_code': unfold_tree.error_code,
                            'message': err_msg
                        })
                        print(f"  ✗ Unfold fout: {err_msg}")
                        continue

                    if theFaceList:
                        # Maak shell van de faces
                        try:
                            flat_shell = Part.Shell(theFaceList)
                        except Exception:
                            flat_shell = Part.Compound(theFaceList)

                        dims_info = _measure_flat_pattern_dimensions(flat_shell)
                        flat_length = dims_info['flat_length']
                        flat_width = dims_info['flat_width']
                        raw_bbox = dims_info['raw_bbox']
                        flat_thickness = min(raw_bbox)
                        
                        result['flat_length'] = flat_length
                        result['flat_width'] = flat_width
                        result['flat_shape'] = flat_shell
                        result['bend_lines'] = foldLines
                        result['bend_line_segments'] = _extract_fold_line_segments_from_edges(foldLines, flat_shell)
                        result['success'] = True
                        result['used_face_idx'] = base_face_idx
                        
                        # Extraheer bend parameters uit unfold tree
                        bend_info = extract_bend_info_from_tree(unfold_tree)
                        
                        # Merge bend segments by geometric collinearity (same line offset).
                        merged_angles, merged_radii, merged_lengths, merged_groups = _merge_bends_by_collinear_segments(
                            bend_info['bend_angles'],
                            bend_info['bend_radii'],
                            bend_info['bend_lengths'],
                            result.get('bend_line_segments', []),
                        )
                        
                        result['bend_angles'] = merged_angles
                        result['bend_radii'] = merged_radii
                        result['bend_lengths'] = merged_lengths
                        result['bend_count'] = len(merged_angles)
                        result['bend_line_groups'] = merged_groups

                        print(
                            f"  ✓ Unfold geslaagd: {flat_length:.1f} x {flat_width:.1f} mm "
                            f"(raw XYZ: {raw_bbox[0]:.1f}, {raw_bbox[1]:.1f}, {raw_bbox[2]:.1f}; "
                            f"thickness axis ~ {flat_thickness:.1f} mm)"
                        )
                        if result['bend_count'] > 0:
                            print(f"  ✓ Bends: {result['bend_count']} gevonden")
                            if result['bend_angles']:
                                print(f"    - Angles: {result['bend_angles']}")
                            if result['bend_radii']:
                                print(f"    - Radii: {result['bend_radii']}")
                            if result['bend_lengths']:
                                print(f"    - Lengths: {result['bend_lengths']}")
                        print(f"  ✓ Fold lines: {len(foldLines)}")

                        # Export naar DXF indien gewenst
                        if output_dxf:
                            export_to_dxf(flat_shell, output_dxf, foldLines)
                            print(f"  ✓ DXF: {output_dxf}")

                        return result  # Success!
                    else:
                        result['error_details'].append({
                            'face_idx': base_face_idx,
                            'stage': 'unfold',
                            'error_code': -1,
                            'message': 'Lege face list'
                        })
                        print(f"  ✗ Lege face list")
                else:
                    result['error_details'].append({
                        'face_idx': base_face_idx,
                        'stage': 'analysis',
                        'error_code': -1,
                        'message': 'Geen root node'
                    })
                    print(f"  ✗ Geen root node")

            except Exception as e:
                result['error_details'].append({
                    'face_idx': base_face_idx,
                    'stage': 'exception',
                    'error_code': -1,
                    'message': str(e)
                })
                print(f"  ✗ Exception: {str(e)}")

            finally:
                try:
                    FreeCAD.closeDocument("UnfoldDoc")
                except Exception:
                    pass

        # Geen van de pogingen werkte
        if result['error_details']:
            # Vind meest voorkomende fout
            error_codes = [e['error_code'] for e in result['error_details']]
            most_common_code = max(set(error_codes), key=error_codes.count)
            result['error'] = UNFOLD_ERROR_MESSAGES.get(most_common_code, f"Unfold gefaald na {result['attempts']} pogingen")
        else:
            result['error'] = f"Unfold gefaald na {result['attempts']} pogingen"

    except Exception as e:
        result['error'] = f"Error: {str(e)}"
        import traceback
        traceback.print_exc()

    return result


def export_to_dxf(shape, filepath, bend_lines=None):
    """
    Exporteer een vlakke shape naar DXF formaat.
    """
    if not _ensure_freecad_imported():
        return False

    try:
        import importDXF

        # Maak tijdelijk document
        doc = FreeCAD.newDocument("ExportDoc")
        obj = doc.addObject("Part::Feature", "FlatPattern")
        obj.Shape = shape

        # Export
        importDXF.export([obj], filepath)

        # Cleanup
        FreeCAD.closeDocument("ExportDoc")

        return True
    except Exception as e:
        print(f"DXF export error: {e}")
        return False


def analyze_for_unfold(step_path):
    """
    Analyseer een STEP file om te bepalen of het geschikt is voor ontbuigen.

    Returns:
        dict met analyse resultaten
    """
    result = {
        'suitable': False,
        'reason': '',
        'thickness': 0,
        'bend_count': 0,
        'planar_faces': 0,
        'cylindrical_faces': 0,
        'base_face_area': 0
    }

    if not _ensure_freecad_imported():
        result['reason'] = f"FreeCAD niet beschikbaar: {_FREECAD_IMPORT_ERROR or 'onbekende importfout'}"
        return result

    try:
        shape = Part.read(step_path)

        if not shape.Solids:
            result['reason'] = "Geen solids in STEP"
            return result

        solid = shape.Solids[0] if len(shape.Solids) > 1 else shape

        # Tel face types
        planar_count = 0
        cylindrical_count = 0
        cylindrical_radii = []

        for face in solid.Faces:
            try:
                surf_type = face.Surface.TypeId
                if 'Plane' in surf_type:
                    planar_count += 1
                elif 'Cylinder' in surf_type:
                    cylindrical_count += 1
                    cylindrical_radii.append(face.Surface.Radius)
            except Exception:
                continue

        result['planar_faces'] = planar_count
        result['cylindrical_faces'] = cylindrical_count

        # Vind base face
        base_info = find_base_face_for_unfold(solid)
        if base_info:
            result['base_face_area'] = base_info['area']

        # Schat dikte uit kleinste buigradius
        if cylindrical_radii:
            min_radius = min(cylindrical_radii)
            # Typisch: binnenradius ≈ dikte, dus dikte ≈ radius
            result['thickness'] = min_radius
            result['bend_count'] = cylindrical_count // 2  # Binnen + buiten radius

        # Bepaal geschiktheid
        if planar_count >= 2 and cylindrical_count >= 2:
            result['suitable'] = True
            result['reason'] = "Sheet metal part met buigingen gedetecteerd"
        elif planar_count >= 2 and cylindrical_count == 0:
            result['suitable'] = True
            result['reason'] = "Vlakke plaat (geen buigingen)"
        else:
            result['suitable'] = False
            result['reason'] = "Niet herkend als sheet metal"

    except Exception as e:
        result['reason'] = f"Analyse error: {str(e)}"

    return result


def calculate_theoretical_unfold(step_path, k_factor=0.44):
    """
    Bereken een theoretische uitslag afmeting voor complexe onderdelen
    die niet automatisch ontbogen kunnen worden.

    Deze methode sommeert:
    - Alle vlakke oppervlakken in hun ontbogen oriëntatie
    - Plus de booglengte van alle buigingen (met K-factor correctie)

    Returns:
        dict met:
        - estimated_length: geschatte lengte uitslag
        - estimated_width: geschatte breedte uitslag
        - total_flat_area: totaal vlak oppervlak
        - total_bend_length: totale buiglengte
        - bend_count: aantal buigingen
        - method: 'theoretical' (niet exact, maar indicatief)
    """
    result = {
        'success': False,
        'estimated_length': 0,
        'estimated_width': 0,
        'total_flat_area': 0,
        'total_bend_length': 0,
        'bend_count': 0,
        'thickness': 0,
        'method': 'theoretical',
        'error': None
    }

    if not _ensure_freecad_imported():
        result['error'] = f"FreeCAD niet beschikbaar: {_FREECAD_IMPORT_ERROR or 'onbekende importfout'}"
        return result

    try:
        shape = Part.read(step_path)

        if not shape.Solids:
            result['error'] = "Geen solids in STEP"
            return result

        solid = shape.Solids[0] if len(shape.Solids) > 1 else shape

        # Analyseer alle faces
        planar_areas = []
        bend_data = []

        for face in solid.Faces:
            try:
                surf_type = face.Surface.TypeId

                if 'Plane' in surf_type:
                    planar_areas.append(face.Area)

                elif 'Cylinder' in surf_type:
                    cyl = face.Surface
                    radius = cyl.Radius

                    # Bereken hoek (U parameter)
                    u_range = face.ParameterRange[1] - face.ParameterRange[0]
                    angle_rad = abs(u_range)

                    # Bereken buiglengte (V parameter)
                    v_range = face.ParameterRange[3] - face.ParameterRange[2]
                    bend_length = abs(v_range)

                    if angle_rad > 0.5 and bend_length > 10:  # Filter kleine radii
                        # Booglengte = (radius + k*thickness) * hoek
                        # We kennen de dikte niet exact, gebruik radius als schatting
                        arc_length = (radius * (1 + k_factor)) * angle_rad

                        bend_data.append({
                            'radius': radius,
                            'angle_rad': angle_rad,
                            'bend_length': bend_length,
                            'arc_length': arc_length
                        })

            except Exception:
                continue

        # Bereken totalen
        result['total_flat_area'] = sum(planar_areas)
        result['bend_count'] = len(bend_data) // 2  # Binnen + buiten
        result['total_bend_length'] = sum(b['arc_length'] for b in bend_data)

        if bend_data:
            result['thickness'] = min(b['radius'] for b in bend_data)

        # Schat uitslag dimensies
        # Simpele benadering: sqrt(total_area) geeft indicatie van maat
        if result['total_flat_area'] > 0:
            # Gebruik bounding box voor aspect ratio
            bbox = solid.BoundBox
            dims = sorted([bbox.XLength, bbox.YLength, bbox.ZLength])

            # Langste dim blijft ongeveer gelijk bij ontbuigen
            result['estimated_length'] = dims[2]

            # Breedte wordt groter door ontbuigen
            # Schat: vlakke oppervlakte / lengte + buiglengtes
            result['estimated_width'] = (result['total_flat_area'] / dims[2]) + result['total_bend_length'] / 10

            result['success'] = True

    except Exception as e:
        result['error'] = str(e)

    return result


def _sync_freecad_bindings() -> None:
    global FreeCAD, Part, _FREECAD_IMPORT_ERROR
    FreeCAD = _freecad_environment.FreeCAD
    Part = _freecad_environment.Part
    _FREECAD_IMPORT_ERROR = _freecad_environment._FREECAD_IMPORT_ERROR


# Command line interface
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Ontbuig sheet metal STEP files")
    parser.add_argument("step_file", help="Pad naar STEP bestand")
    parser.add_argument("-o", "--output", help="Output DXF bestand")
    parser.add_argument("-k", "--kfactor", type=float, default=0.44, help="K-factor (default 0.44)")
    parser.add_argument("--analyze", action="store_true", help="Alleen analyseren, niet ontbuigen")

    args = parser.parse_args()

    if not os.path.exists(args.step_file):
        print(f"Error: Bestand niet gevonden: {args.step_file}")
        sys.exit(1)

    if args.analyze:
        print(f"\nAnalyzing: {args.step_file}")
        result = analyze_for_unfold(args.step_file)
        print(f"\nResultaat:")
        for key, value in result.items():
            print(f"  {key}: {value}")
    else:
        print(f"\nUnfolding: {args.step_file}")
        output = args.output or args.step_file.replace('.step', '_flat.dxf').replace('.STEP', '_flat.dxf')
        result = unfold_sheet_metal(args.step_file, output, args.kfactor)

        if result['success']:
            print(f"\n✓ Ontbuigen geslaagd!")
            print(f"  Uitslag: {result['flat_length']:.1f} x {result['flat_width']:.1f} mm")
            if args.output:
                print(f"  DXF: {output}")
        else:
            print(f"\n✗ Ontbuigen mislukt: {result['error']}")
            sys.exit(1)
