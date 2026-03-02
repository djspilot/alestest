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
import subprocess

FreeCAD = None
Part = None
_FREECAD_IMPORT_ERROR = None


def _candidate_freecad_paths():
    """Build candidate FreeCAD python/module paths for multiple platforms."""
    candidates = []

    # Explicit override via env var (recommended for deployments)
    freecad_path = os.getenv('FREECAD_PATH')
    if freecad_path:
        candidates.append(freecad_path)
        candidates.append(os.path.join(freecad_path, 'lib'))
        candidates.append(os.path.join(freecad_path, 'Mod'))

    # Windows common installs
    program_files = os.environ.get('ProgramFiles', r'C:\Program Files')
    program_files_x86 = os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)')
    for base in [program_files, program_files_x86]:
        if base:
            candidates.extend([
                os.path.join(base, 'FreeCAD 1.0', 'bin'),
                os.path.join(base, 'FreeCAD 1.0', 'Mod'),
                os.path.join(base, 'FreeCAD', 'bin'),
                os.path.join(base, 'FreeCAD', 'Mod'),
                os.path.join(base, 'FreeCAD 0.21', 'bin'),
                os.path.join(base, 'FreeCAD 0.21', 'Mod'),
            ])

    appdata = os.environ.get('APPDATA')
    if appdata:
        candidates.append(os.path.join(appdata, 'FreeCAD', 'Mod'))

    # macOS/Homebrew + app bundle
    mac_app = '/Applications/FreeCAD.app/Contents/Resources'
    brew_app = '/opt/homebrew/Caskroom/freecad/1.0.2/FreeCAD.app/Contents/Resources'
    for path in [mac_app, brew_app]:
        candidates.extend([
            os.path.join(path, 'lib'),
            os.path.join(path, 'Mod'),
        ])
    candidates.append(os.path.expanduser('~/Library/Application Support/FreeCAD/Mod'))

    # Linux common paths
    candidates.extend([
        '/usr/lib/freecad/lib',
        '/usr/share/freecad/Mod',
        '/usr/lib/freecad/Mod',
        '/snap/freecad/current/usr/lib/freecad/lib',
        '/snap/freecad/current/usr/share/freecad/Mod',
        os.path.expanduser('~/.local/share/FreeCAD/Mod'),
    ])

    return candidates


def _ensure_freecad_imported() -> bool:
    """Import FreeCAD/Part lazily with platform-aware path setup."""
    global FreeCAD, Part, _FREECAD_IMPORT_ERROR

    if FreeCAD is not None and Part is not None:
        return True

    # Add candidate paths once at runtime
    for path in _candidate_freecad_paths():
        if path and os.path.isdir(path) and path not in sys.path:
            sys.path.insert(0, path)

    try:
        import FreeCAD as _FreeCAD
        import Part as _Part
        FreeCAD = _FreeCAD
        Part = _Part

        try:
            import FreeCADGui as _FreeCADGui
            _FreeCADGui.Selection.getSelection()
        except (ImportError, AttributeError):
            sys.modules['FreeCADGui'] = MockFreeCADGui()

        return True
    except Exception as e:
        _FREECAD_IMPORT_ERROR = str(e)
        return False


def _find_freecadcmd_executable() -> str:
    """Find FreeCADCmd executable for subprocess fallback."""
    env_path = os.getenv('FREECAD_CMD')
    if env_path and os.path.exists(env_path):
        return env_path

    candidates = [
        r"C:\Program Files\FreeCAD 1.0\bin\freecadcmd.exe",
        r"C:\Program Files\FreeCAD\bin\freecadcmd.exe",
        r"C:\Program Files\FreeCAD 0.21\bin\freecadcmd.exe",
        r"C:\Program Files (x86)\FreeCAD\bin\freecadcmd.exe",
        "/usr/bin/freecadcmd",
        "/usr/local/bin/freecadcmd",
        "/Applications/FreeCAD.app/Contents/MacOS/FreeCADCmd",
    ]

    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate

    return ''


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

    script = f'''import json\nimport Part\nimport FreeCAD\nimport math\n\nUNFOLD_ERROR_MESSAGES = {json.dumps(UNFOLD_ERROR_MESSAGES, ensure_ascii=False)}\n\ndef _result():\n    return {{\n        "success": False,\n        "flat_shape": None,\n        "flat_length": 0,\n        "flat_width": 0,\n        \n        "bend_angles": [],\n        "bend_radii": [],\n        "bend_lengths": [],\n        "bend_count": 0,\n        "error": None,\n        "attempts": 0,\n        "error_details": [],\n        "used_face_idx": None\n    }}\n\ndef _collect_bend_nodes(node, bend_list):\n    """Recursively collect Bend nodes from tree"""\n    if node is None:\n        return\n    try:\n        if hasattr(node, 'node_type'):\n            print(f"[DEBUG] Node type: {{node.node_type}}")\n            if node.node_type == 'Bend':\n                print(f"[DEBUG] Found Bend node!")\n                bend_list.append(node)\n        # Debug: print bend info even for non-Bend nodes\n        if hasattr(node, 'bend_angle') and node.bend_angle is not None:\n            print(f"[DEBUG] Node has bend_angle: {{node.bend_angle}}")\n        if hasattr(node, 'innerRadius') and node.innerRadius is not None:\n            print(f"[DEBUG] Node has innerRadius: {{node.innerRadius}}")\n            \n        if hasattr(node, 'child_list'):\n            print(f"[DEBUG] Node has child_list attribute: {{node.child_list is not None}}, length: {{len(node.child_list) if node.child_list else 0}}")\n            if node.child_list:\n                print(f"[DEBUG] Node has {{len(node.child_list)}} children")\n                for child in node.child_list:\n                    _collect_bend_nodes(child, bend_list)\n        else:\n            print(f"[DEBUG] Node does NOT have child_list attribute")\n    except Exception as e:\n        print(f"[DEBUG] Error in _collect_bend_nodes: {{e}}")\n\ndef _extract_bends_from_tree(tree_root):\n    """Extract bend parameters from SheetTree node structure"""\n    result = {{\n        "bend_angles": [],\n        "bend_radii": [],\n        "bend_lengths": [],\n        "bend_count": 0\n    }}\n    \n    try:\n        print(f"[DEBUG] Starting tree extraction...")\n        print(f"[DEBUG] Tree root type: {{type(tree_root).__name__}}")\n        print(f"[DEBUG] Tree root attributes: {{[attr for attr in dir(tree_root) if not attr.startswith('_')][:20]}}")\n        bend_nodes = []\n        _collect_bend_nodes(tree_root, bend_nodes)\n        print(f"[DEBUG] Found {{len(bend_nodes)}} bend nodes")\n        \n        for node in bend_nodes:\n            try:\n                if hasattr(node, 'bend_angle') and node.bend_angle is not None:\n                    angle_deg = node.bend_angle * 180.0 / 3.14159265\n                    result["bend_angles"].append(round(angle_deg, 2))\n                    print(f"[DEBUG] Bend angle: {{angle_deg}}°")\n                \n                if hasattr(node, 'innerRadius') and node.innerRadius is not None:\n                    result["bend_radii"].append(round(node.innerRadius, 2))\n                    print(f"[DEBUG] Inner radius: {{node.innerRadius}} mm")\n                \n                if hasattr(node, '_trans_length') and node._trans_length is not None:\n                    result["bend_lengths"].append(round(node._trans_length, 2))\n                    print(f"[DEBUG] Trans length: {{node._trans_length}} mm")\n                elif hasattr(node, 'p_wire') and node.p_wire is not None:\n                    try:\n                        result["bend_lengths"].append(round(node.p_wire.Length, 2))\n                        print(f"[DEBUG] Wire length: {{node.p_wire.Length}} mm")\n                    except:\n                        pass\n            except Exception as e:\n                print(f"[DEBUG] Error extracting from node: {{e}}")\n        \n        result["bend_count"] = len(result["bend_angles"])\n        print(f"[DEBUG] Final bend_count: {{result['bend_count']}}")\n    except Exception as e:\n        print(f"[DEBUG] Error in _extract_bends_from_tree: {{e}}")\n    \n    return result\n\ndef _analyze_bends(solid, max_bends=0):\n    """FALLBACK: Analyze cylindrical faces to extract bend parameters"""\n    bends = {{\n        "bend_angles": [],\n        "bend_radii": [],\n        "bend_lengths": [],\n        "bend_count": 0\n    }}\n    \n    try:\n        cylinders = []\n        for face in solid.Faces:\n            try:\n                surf_type = face.Surface.TypeId\n                if "Cylinder" in surf_type:\n                    cyl = face.Surface\n                    radius = cyl.Radius\n                    u_min, u_max, v_min, v_max = face.ParameterRange\n                    angle_rad = abs(u_max - u_min)\n                    angle_deg = angle_rad * 180.0 / 3.14159265\n                    length = abs(v_max - v_min)\n                    \n                    if angle_rad > 0.3 and length > 5:\n                        cylinders.append({{\n                            "radius": radius,\n                            "angle_deg": angle_deg,\n                            "length": length,\n                            "area": face.Area\n                        }})\n            except:\n                pass\n        \n        # Deduplicate: group by angle+length to combine inner/outer faces\n        unique = {{}}\n        for cyl in cylinders:\n            key = (round(cyl["angle_deg"], 1), round(cyl["length"], 1))\n            if key not in unique:\n                unique[key] = cyl\n            elif cyl["radius"] < unique[key]["radius"]:\n                unique[key] = cyl\n        \n        # Sort by area\n        sorted_bends = sorted(unique.values(), key=lambda x: x["area"], reverse=True)\n        \n        # Limit to max_bends if specified\n        if max_bends > 0:\n            sorted_bends = sorted_bends[:max_bends]\n        \n        for bend in sorted_bends:\n            bends["bend_radii"].append(round(bend["radius"], 2))\n            bends["bend_angles"].append(round(bend["angle_deg"], 2))\n            bends["bend_lengths"].append(round(bend["length"], 2))\n        \n        bends["bend_count"] = len(sorted_bends)\n    except:\n        pass\n    \n    return bends\n\ndef _candidates(shape):\n    planar = []\n    for i, face in enumerate(shape.Faces):\n        try:\n            t = face.Surface.TypeId\n            if "Plane" in t:\n                planar.append((i, face.Area))\n        except Exception:\n            pass\n    planar.sort(key=lambda x: x[1], reverse=True)\n    return planar\n\ndef run(data):\n    res = _result()\n    try:\n        shape = Part.read(data["step_path"])\n        if not shape.Solids:\n            res["error"] = "Geen solids gevonden in STEP file"\n            print(json.dumps(res))\n            return\n\n        solid = shape.Solids[0] if len(shape.Solids) > 1 else shape\n        \n        cand = _candidates(solid)\n        if not cand:\n            res["error"] = "Geen vlakke oppervlakken gevonden"\n            print(json.dumps(res))\n            return\n\n        import SheetMetalUnfolder\n\n        k_lookup = {{}}\n        for t in [0.5, 0.75, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0, 12.0, 15.0, 20.0]:\n            k_lookup[t] = float(data["k_factor"])\n\n        attempts_to_try = min(int(data["max_attempts"]), len(cand))\n\n        for attempt, (face_idx, area) in enumerate(cand[:attempts_to_try]):\n            res["attempts"] = attempt + 1\n            doc = FreeCAD.newDocument("UnfoldDoc")\n            try:\n                obj = doc.addObject("Part::Feature", "SheetPart")\n                obj.Shape = solid\n                doc.recompute()\n\n                try:\n                    tree = SheetMetalUnfolder.SheetTree(solid, face_idx, k_lookup, obj)\n                except TypeError:\n                    tree = SheetMetalUnfolder.SheetTree(solid, face_idx, k_lookup)\n                if tree.error_code:\n                    msg = UNFOLD_ERROR_MESSAGES.get(tree.error_code, f"Onbekende fout ({{tree.error_code}})")\n                    res["error_details"].append({{"face_idx": face_idx, "stage": "init", "error_code": tree.error_code, "message": msg}})\n                    continue\n\n                tree.Bend_analysis(face_idx, None)\n                if tree.error_code:\n                    msg = UNFOLD_ERROR_MESSAGES.get(tree.error_code, f"Onbekende fout ({{tree.error_code}})")\n                    res["error_details"].append({{"face_idx": face_idx, "stage": "analysis", "error_code": tree.error_code, "message": msg}})\n                    continue\n\n                if hasattr(tree, "root") and tree.root:\n                    face_list, fold_lines = tree.unfold_tree2(tree.root)\n                    if tree.error_code:\n                        msg = UNFOLD_ERROR_MESSAGES.get(tree.error_code, f"Onbekende fout ({{tree.error_code}})")\n                        res["error_details"].append({{"face_idx": face_idx, "stage": "unfold", "error_code": tree.error_code, "message": msg}})\n                        continue\n                    \n                    print(f"[DEBUG] fold_lines: {{type(fold_lines).__name__}}, length: {{len(fold_lines) if fold_lines else 0}}")\n                    if fold_lines:\n                        for i, line in enumerate(fold_lines[:3]):\n                            print(f"[DEBUG] fold_line[{{i}}]: {{type(line).__name__}}")\n                            if hasattr(line, '__dict__'):\n                                print(f"[DEBUG] fold_line[{{i}}] dict: {{line.__dict__}}")\n                    \n                    # Extract bend info from tree AFTER unfold_tree2()\n                    bend_params = _extract_bends_from_tree(tree.root)\n                    res["bend_angles"] = bend_params["bend_angles"]\n                    res["bend_radii"] = bend_params["bend_radii"]\n                    res["bend_lengths"] = bend_params["bend_lengths"]\n                    res["bend_count"] = bend_params["bend_count"]\n                    \n                    # Fallback to face analysis if tree extraction failed\n                    if res["bend_count"] == 0:\n                        bend_params_fallback = _analyze_bends(solid, max_bends=int(data.get("max_bends", 0)))\n                        res["bend_angles"] = bend_params_fallback["bend_angles"]\n                        res["bend_radii"] = bend_params_fallback["bend_radii"]\n                        res["bend_lengths"] = bend_params_fallback["bend_lengths"]\n                        res["bend_count"] = bend_params_fallback["bend_count"]\n                    if tree.error_code:\n                        msg = UNFOLD_ERROR_MESSAGES.get(tree.error_code, f"Onbekende fout ({{tree.error_code}})")\n                        res["error_details"].append({{"face_idx": face_idx, "stage": "unfold", "error_code": tree.error_code, "message": msg}})\n                        continue\n\n                    if face_list:\n                        try:\n                            flat_shape = Part.Shell(face_list)\n                        except Exception:\n                            flat_shape = Part.Compound(face_list)\n\n                        bbox = flat_shape.BoundBox\n                        res["flat_length"] = float(bbox.XLength)\n                        res["flat_width"] = float(bbox.YLength)\n                        \n                        res["success"] = True\n                        res["used_face_idx"] = int(face_idx)\n\n                        if data.get("output_dxf"):\n                            try:\n                                import importDXF\n                                export_doc = FreeCAD.newDocument("ExportDoc")\n                                exp_obj = export_doc.addObject("Part::Feature", "FlatPattern")\n                                exp_obj.Shape = flat_shape\n                                importDXF.export([exp_obj], data["output_dxf"])\n                                FreeCAD.closeDocument("ExportDoc")\n                            except Exception:\n                                pass\n\n                        print(json.dumps(res))\n                        return\n\n            except Exception as e:\n                res["error_details"].append({{"face_idx": int(face_idx), "stage": "exception", "error_code": -1, "message": str(e)}})\n            finally:\n                try:\n                    FreeCAD.closeDocument("UnfoldDoc")\n                except Exception:\n                    pass\n\n        if res["error_details"]:\n            code = res["error_details"][-1].get("error_code", -1)\n            res["error"] = UNFOLD_ERROR_MESSAGES.get(code, f"Unfold gefaald na {{res['attempts']}} pogingen")\n        else:\n            res["error"] = f"Unfold gefaald na {{res['attempts']}} pogingen"\n\n    except Exception as e:\n        res["error"] = str(e)\n\n    print(json.dumps(res))\n\nrun({json.dumps(payload)})\n'''

    tmp_file = None
    try:
        with tempfile.NamedTemporaryFile('w', suffix='_freecad_unfold.py', delete=False, encoding='utf-8') as handle:
            handle.write(script)
            tmp_file = handle.name

        proc = subprocess.run(
            [freecadcmd, tmp_file],
            capture_output=True,
            text=True,
            timeout=300,
            check=False
        )

        output_lines = [line.strip() for line in (proc.stdout or '').splitlines() if line.strip()]
        
        # Print debug output
        for line in output_lines:
            if not (line.startswith('{') and line.endswith('}')):
                if '[DEBUG]' in line:
                    print(line)
        
        for line in reversed(output_lines):
            if line.startswith('{') and line.endswith('}'):
                try:
                    data = json.loads(line)
                    data.setdefault('error_details', [])
                    data.setdefault('attempts', 0)
                    return data
                except Exception:
                    continue

        stderr = (proc.stderr or '').strip()
        return {
            'success': False,
            'error': f'FreeCADCmd uitvoer niet parsebaar (code {proc.returncode}): {stderr[:300]}',
            'attempts': 0,
            'error_details': []
        }
    except Exception as e:
        return {
            'success': False,
            'error': f'FreeCADCmd fallback error: {e}',
            'attempts': 0,
            'error_details': []
        }
    finally:
        if tmp_file and os.path.exists(tmp_file):
            try:
                os.remove(tmp_file)
            except Exception:
                pass

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
                    # Convert from radians to degrees
                    angle_deg = math.degrees(node.bend_angle)
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
        'error': None,
        'attempts': 0,
        'error_details': [],
        'used_face_idx': None
    }

    if not _ensure_freecad_imported():
        print(f"[INFO] Using subprocess fallback (FreeCAD not directly importable)")
        
        # If solid_object provided, write to temp STEP file first
        temp_step = None
        if solid_object is not None:
            try:
                import tempfile
                temp_step = tempfile.NamedTemporaryFile(suffix='.step', delete=False).name
                print(f"[INFO] Writing solid to temp STEP: {temp_step}")
                
                # Write solid to STEP file using OCP directly
                try:
                    from OCP.STEPControl import STEPControl_Writer, STEPControl_AsIs
                    from OCP.IFSelect import IFSelect_RetDone
                    
                    writer = STEPControl_Writer()
                    writer.Transfer(solid_object, STEPControl_AsIs)
                    status = writer.Write(temp_step)
                    
                    if status != IFSelect_RetDone:
                        raise Exception(f"STEP write failed with status: {status}")
                    
                    step_path = temp_step
                    print(f"[INFO] Solid exported to temp STEP successfully")
                except Exception as e:
                    print(f"[WARN] Could not write solid to temp STEP: {e}")
                    result['error'] = f"Cannot use solid object with subprocess fallback: {e}"
                    return result
            except Exception as e:
                result['error'] = f"Failed to create temp STEP for solid: {e}"
                return result
        
        try:
            fallback_result = _unfold_via_freecadcmd(step_path, output_dxf, k_factor, max_attempts, max_bends)
            if fallback_result.get('success'):
                return fallback_result
            result['error'] = fallback_result.get('error') or f"FreeCAD niet beschikbaar: {_FREECAD_IMPORT_ERROR or 'onbekende importfout'}"
            result['attempts'] = fallback_result.get('attempts', 0)
            result['error_details'] = fallback_result.get('error_details', [])
            return result
        finally:
            # Clean up temp file
            if temp_step and os.path.exists(temp_step):
                try:
                    os.remove(temp_step)
                except:
                    pass

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

                # SheetTree signature verschilt per SheetMetal versie
                try:
                    # Nieuwere versies: (shape, face_idx, k_lookup, obj)
                    unfold_tree = SheetMetalUnfolder.SheetTree(
                        solid,
                        base_face_idx,
                        kFactorLookup,
                        wrapped_obj
                    )
                except TypeError:
                    # Oudere versies: (shape, face_idx, k_lookup)
                    unfold_tree = SheetMetalUnfolder.SheetTree(
                        solid,
                        base_face_idx,
                        kFactorLookup
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

                        # Bereken bounding box
                        bbox = flat_shell.BoundBox
                        result['flat_length'] = bbox.XLength
                        result['flat_width'] = bbox.YLength
                        result['flat_shape'] = flat_shell
                        result['bend_lines'] = foldLines
                        result['success'] = True
                        result['used_face_idx'] = base_face_idx
                        
                        # Extraheer bend parameters uit unfold tree
                        bend_info = extract_bend_info_from_tree(unfold_tree)
                        result['bend_angles'] = bend_info['bend_angles']
                        result['bend_radii'] = bend_info['bend_radii']
                        result['bend_lengths'] = bend_info['bend_lengths']
                        result['bend_count'] = bend_info['bend_count']

                        print(f"  ✓ Unfold geslaagd: {bbox.XLength:.1f} x {bbox.YLength:.1f} mm")
                        if bend_info['bend_count'] > 0:
                            print(f"  ✓ Bends: {bend_info['bend_count']} gevonden")
                            if bend_info['bend_angles']:
                                print(f"    - Angles: {bend_info['bend_angles']}")
                            if bend_info['bend_radii']:
                                print(f"    - Radii: {bend_info['bend_radii']}")
                            if bend_info['bend_lengths']:
                                print(f"    - Lengths: {bend_info['bend_lengths']}")
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
