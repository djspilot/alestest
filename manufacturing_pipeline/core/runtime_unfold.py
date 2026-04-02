"""Extracted runtime functions from runtime_functions.py."""

import os
import sys
import math
import json
import subprocess
from types import SimpleNamespace

from manufacturing_pipeline.core.config import SystemConfig
from manufacturing_pipeline.core.thresholds import get_unfold_thresholds

from manufacturing_pipeline.core.paths import PIPELINE_DIR, SCRIPTS_DIR

UNFOLD_ERROR_MESSAGES = {
    1: "Volume onbruikbaar - geen echt 3D sheet metal met uniforme dikte",
    2: "Ongeldige punt voor dikte meting",
    3: "Ongeldige dikte - plaatdikte niet consistent of te complex",
    4: "Ongeldige shape",
    5: "Shape heeft onnodige edges - gebruik 'Refine Shape' eerst",
    10: "Geen wires in sheet edge analyse",
    11: "Dubbele buigingen niet ondersteund",
    12: "Meer dan een bend-child niet ondersteund",
    13: "Plaatdikte ongeldig voor dit vlak",
    14: "Edges zonder buur-vlakken",
    15: "Alle sheet edges moeten een vlak hebben",
    16: "Starthoek van buiging niet gevonden",
    17: "Type oppervlak niet ondersteund voor sheet metal",
    20: "Section wire met minder dan 4 edges",
    21: "Section wire niet gesloten",
    22: "Section gefaald",
    23: "CutToolWire niet gesloten",
    24: "Bend-face zonder child niet geimplementeerd",
    26: "Niet-ondersteund curve type in unbendFace",
}

FREECAD_PYTHON = SystemConfig.from_env().freecad_python
HOST_PYTHON = sys.executable

if PIPELINE_DIR not in sys.path:
    sys.path.insert(0, PIPELINE_DIR)
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)


def _get_unfold_runtime_settings(config_path=None):
    """Return unfold thresholds normalized for runtime use."""
    unfold_thresholds = get_unfold_thresholds(config_path)
    return {
        "runtime_timeout_sec": int(unfold_thresholds["runtime"]["timeout_sec"]),
        "candidate_limits": {
            "max_solids": int(unfold_thresholds["candidate_limits"]["max_solids"]),
            "max_base_faces_per_solid": int(
                unfold_thresholds["candidate_limits"]["max_base_faces_per_solid"]
            ),
        },
        "thickness": {
            "opposite_face_dot_max": float(unfold_thresholds["thickness"]["opposite_face_dot_max"]),
            "max_override_mm": float(unfold_thresholds["thickness"]["max_override_mm"]),
            "min_override_delta_mm": float(unfold_thresholds["thickness"]["min_override_delta_mm"]),
        },
        "fold_merge": {
            "offset_tol_mm": float(unfold_thresholds["fold_merge"]["offset_tol_mm"]),
            "angle_tol_deg": float(unfold_thresholds["fold_merge"]["angle_tol_deg"]),
            "radius_tol_mm": float(unfold_thresholds["fold_merge"]["radius_tol_mm"]),
            "overlap_tol_mm": float(unfold_thresholds["fold_merge"]["overlap_tol_mm"]),
            "gap_tol_mm": float(unfold_thresholds["fold_merge"]["gap_tol_mm"]),
        },
        "k_factor_default": float(unfold_thresholds["k_factor"]["default"]),
        "k_factor_lookup": {
            float(bucket): float(value)
            for bucket, value in unfold_thresholds["k_factor"]["thickness_buckets_mm"].items()
        },
    }
def _summarize_unfold_failure(result):
    """Build a readable error from structured unfold failure details."""
    if not result:
        return "Unfold gefaald zonder resultaat"

    explicit_error = (result.get("error") or "").strip()
    if explicit_error:
        return explicit_error

    details = result.get("error_details") or []
    attempts = result.get("attempts") or 0
    if not details:
        return f"Unfold gefaald na {attempts} pogingen zonder diagnose"

    exception_messages = []
    regular_messages = []
    seen = set()
    for detail in details:
        message = (detail.get("message") or "").strip()
        if not message or message in seen:
            continue
        seen.add(message)
        if detail.get("stage") == "exception":
            exception_messages.append(message)
        else:
            regular_messages.append(message)

    if exception_messages:
        summary = f"Interne SheetMetal fout tijdens unfold: {exception_messages[0]}"
        if regular_messages:
            summary += f". Eerder ook gezien: {'; '.join(regular_messages[:2])}"
        return summary

    joined = "; ".join(regular_messages[:3])
    if joined:
        return f"Geen geldige unfold-route gevonden na {attempts} pogingen: {joined}"

    return f"Unfold gefaald na {attempts} pogingen zonder bruikbare foutmelding"

def _build_freecad_subprocess_env(sys_config):
    """Build an isolated environment for headless FreeCAD subprocesses.

    The managed runtime ships its own SheetMetal workbench under the runtime
    `Mod` folder. Without isolating the user profile, FreeCAD may still pick up
    `%APPDATA%\\FreeCAD\\Mod\\SheetMetal`, which makes unfold behavior depend on
    workstation-local add-ons. We force a local profile root under the managed
    runtime and prepend the runtime DLL paths so imports stay deterministic.
    """
    runtime_root = ""
    try:
        runtime_root = str(sys_config._managed_runtime_value("runtime_root") or "")
    except Exception:
        runtime_root = ""
    if not runtime_root:
        runtime_root = str(sys_config.freecad_path or "")
    if not runtime_root or runtime_root.endswith(".app"):
        runtime_root = os.path.join("/tmp", "alestest-freecad-runtime")
    env = os.environ.copy()

    extra_path_parts = []
    for candidate in (
        os.path.join(runtime_root, "Library", "bin"),
        os.path.join(runtime_root, "Library", "mingw-w64", "bin"),
        os.path.join(runtime_root, "bin"),
        str(sys_config.freecad_lib or ""),
    ):
        if candidate and os.path.isdir(candidate) and candidate not in extra_path_parts:
            extra_path_parts.append(candidate)

    if extra_path_parts:
        path_sep = ";" if sys.platform.startswith("win") else ":"
        existing = env.get("PATH", "")
        env["PATH"] = path_sep.join(extra_path_parts) + path_sep + existing

    isolated_profile_root = os.path.join(runtime_root, "_freecad_profile")
    isolated_appdata = os.path.join(isolated_profile_root, "AppData", "Roaming")
    isolated_localappdata = os.path.join(isolated_profile_root, "AppData", "Local")
    isolated_freecad_home = os.path.join(isolated_appdata, "FreeCAD")
    isolated_mod = os.path.join(isolated_freecad_home, "Mod")

    os.makedirs(isolated_mod, exist_ok=True)
    os.makedirs(isolated_localappdata, exist_ok=True)

    env["FREECAD_USER_HOME"] = isolated_freecad_home
    env["APPDATA"] = isolated_appdata
    env["LOCALAPPDATA"] = isolated_localappdata
    env["HOME"] = isolated_profile_root
    env["USERPROFILE"] = isolated_profile_root
    env["FREECAD_RUNTIME_ROOT"] = runtime_root
    env["FREECAD_PATH"] = str(sys_config.freecad_path or "")
    env["FREECAD_PYTHON"] = str(sys_config.freecad_python or "")
    env["FREECAD_CMD"] = str(sys_config.freecad_cmd or "")
    env["FREECAD_LIB"] = str(sys_config.freecad_lib or "")
    env["FREECAD_MOD"] = str(sys_config.freecad_mod or "")

    return env


def _runtime_debug_snapshot(sys_config: SystemConfig, env: dict) -> dict:
    """Collect a compact runtime snapshot for diagnostics."""
    path_sep = ";" if sys.platform.startswith("win") else ":"
    path_value = env.get("PATH", "")
    path_entries = [entry for entry in path_value.split(path_sep) if entry]
    return {
        "platform": sys.platform,
        "freecad_path": sys_config.freecad_path,
        "freecad_python": sys_config.freecad_python,
        "freecad_cmd": sys_config.freecad_cmd,
        "freecad_lib": sys_config.freecad_lib,
        "freecad_mod": sys_config.freecad_mod,
        "freecad_runtime_root": env.get("FREECAD_RUNTIME_ROOT", ""),
        "path_entries": path_entries[:12],
    }


def _print_runtime_debug_snapshot(prefix: str, snapshot: dict) -> None:
    print(f"{prefix} platform: {snapshot.get('platform') or '(empty)'}")
    print(f"{prefix} FREECAD_PATH: {snapshot.get('freecad_path') or '(empty)'}")
    print(f"{prefix} FREECAD_PYTHON: {snapshot.get('freecad_python') or '(empty)'}")
    print(f"{prefix} FREECAD_CMD: {snapshot.get('freecad_cmd') or '(empty)'}")
    print(f"{prefix} FREECAD_LIB: {snapshot.get('freecad_lib') or '(empty)'}")
    print(f"{prefix} FREECAD_MOD: {snapshot.get('freecad_mod') or '(empty)'}")
    print(f"{prefix} FREECAD_RUNTIME_ROOT: {snapshot.get('freecad_runtime_root') or '(empty)'}")
    for entry in snapshot.get("path_entries", []):
        print(f"{prefix} PATH+: {entry}")

def _first_existing(candidates):
    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            return candidate
    return ""


def _resolve_windows_desktop_freecad_config():
    if not sys.platform.startswith("win"):
        return None

    program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
    program_files_x86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    install_roots = []
    for base in (program_files, program_files_x86):
        if not base:
            continue
        install_roots.extend([
            os.path.join(base, "FreeCAD 1.0"),
            os.path.join(base, "FreeCAD"),
            os.path.join(base, "FreeCAD 0.21"),
        ])

    for root in install_roots:
        cmd_path = _first_existing([
            os.path.join(root, "bin", "FreeCADCmd.exe"),
            os.path.join(root, "bin", "freecadcmd.exe"),
            os.path.join(root, "Library", "bin", "FreeCADCmd.exe"),
            os.path.join(root, "Library", "bin", "freecadcmd.exe"),
        ])
        if not cmd_path:
            continue

        python_path = _first_existing([
            os.path.join(root, "python.exe"),
            os.path.join(root, "Library", "bin", "python.exe"),
            os.path.join(root, "bin", "python.exe"),
            cmd_path,
        ])
        lib_path = _first_existing([
            os.path.join(root, "Library", "bin"),
            os.path.join(root, "Library", "lib"),
            os.path.join(root, "Lib", "site-packages"),
            os.path.join(root, "bin"),
        ])
        mod_path = _first_existing([
            os.path.join(root, "Mod"),
            os.path.join(root, "Library", "Mod"),
        ])

        return SimpleNamespace(
            freecad_path=root,
            freecad_python=python_path,
            freecad_cmd=cmd_path,
            freecad_lib=lib_path,
            freecad_mod=mod_path,
            _managed_runtime_value=lambda key: "",
        )

    return None


def _run_unfold_subprocess_attempt(step_file, output_dir, part_name, sys_config, runtime_label="managed"):
    fc_lib = sys_config.freecad_lib
    fc_mod = sys_config.freecad_mod
    unfold_settings = _get_unfold_runtime_settings()
    freecad_python = sys_config.freecad_python
    freecad_env = _build_freecad_subprocess_env(sys_config)
    debug_snapshot = _runtime_debug_snapshot(sys_config, freecad_env)

    unfold_script = f'''
import sys
import os
import platform
import json
import math
import traceback

# FreeCAD paths
freecad_lib = {repr(fc_lib)}
freecad_mod = {repr(fc_mod)}
freecad_sheetmetal_mod = os.path.join(freecad_mod, "SheetMetal")
UNFOLD_ERROR_MESSAGES = {repr(UNFOLD_ERROR_MESSAGES)}

if platform.system() == "Darwin":
    freecad_user_mod = os.path.expanduser("~/Library/Application Support/FreeCAD/Mod")
else:
    freecad_user_mod = os.path.expanduser("~/.local/share/FreeCAD/Mod")

sys.path.insert(0, freecad_lib)
sys.path.insert(0, freecad_mod)
if os.path.isdir(freecad_sheetmetal_mod):
    sys.path.insert(0, freecad_sheetmetal_mod)

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
step_path = {repr(step_file)}
shape = Part.Shape()
shape.read(step_path)

# K-factor lookup
kFactorLookup = {repr(unfold_settings["k_factor_lookup"])}

def build_sheet_tree(shape, face_idx, k_factor_lookup, obj):
    try:
        return SheetMetalUnfolder.SheetTree(shape, face_idx, k_factor_lookup, obj)
    except TypeError as exc:
        if "takes 4 positional arguments but 5 were given" not in str(exc):
            raise
        return SheetMetalUnfolder.SheetTree(shape, face_idx, k_factor_lookup)

def get_thickness_from_solid(solid):
    try:
        # Strategy 1: Find largest planar face, then find opposite face
        faces = [f for f in solid.Faces if "Plane" in f.Surface.TypeId]
        if faces:
            # Sort by area
            faces.sort(key=lambda f: f.Area, reverse=True)
            main_face = faces[0]
            main_normal = main_face.Surface.Axis

            # Find opposite face (parallel, normal dot product approx -1)
            # We check the top 10 largest faces to find the matching back face
            for f in faces[1:10]:
                if f.Surface.Axis.dot(main_normal) < {unfold_settings["thickness"]["opposite_face_dot_max"]}:
                    dist = main_face.distToShape(f)[0]
                    if dist > 0:
                        return dist

        # Strategy 2: volume / top_area fallback for curved sheet metal.
        # Prefer the largest planar face area when available.
        # For bent plates the largest cylindrical face can be much larger than
        # the projected plate area and underestimates thickness.
        if solid.Volume > 0:
            planar_areas = [f.Area for f in solid.Faces if "Plane" in f.Surface.TypeId and f.Area > 0]
            if planar_areas:
                top_area = max(planar_areas)
            else:
                all_areas = [f.Area for f in solid.Faces if f.Area > 0]
                top_area = max(all_areas) if all_areas else 0.0

            if top_area > 0:
                estimated = solid.Volume / top_area
                if 0.3 < estimated < 20.0:
                    return round(estimated * 2) / 2  # round to nearest 0.5 mm
        return 0.0
    except:
        return 0.0

def _merge_fold_segments(bend_line_segments, bends_logical):
    usable = []
    for segment in bend_line_segments:
        try:
            axis = str(segment.get("axis") or "").upper()
            idx = int(segment.get("index", -1))
            center = segment.get("center") or [0.0, 0.0, 0.0]
            axis_span = segment.get("axis_span") or [0.0, 0.0]
            if axis not in ("X", "Y") or idx < 0 or len(axis_span) < 2:
                continue

            span_min = float(min(axis_span[0], axis_span[1]))
            span_max = float(max(axis_span[0], axis_span[1]))
            line_offset = float(center[1] if axis == "X" else center[0])
            logical = bends_logical[idx] if idx < len(bends_logical) else {{}}
            angle = logical.get("angle")
            radius = logical.get("radius")

            usable.append({{
                "axis": axis,
                "index": idx,
                "line_offset": line_offset,
                "span_min": span_min,
                "span_max": span_max,
                "angle": float(angle) if angle is not None else None,
                "radius": float(radius) if radius is not None else None,
                "segment": segment,
            }})
        except:
            continue

    if not usable:
        return [], [], []

    usable.sort(key=lambda item: (item["axis"], round(item["line_offset"], 3), item["span_min"]))

    clusters = []
    current = None
    for item in usable:
        if current is None:
            current = {{
                "axis": item["axis"],
                "line_offset": item["line_offset"],
                "items": [item],
                "angle": item["angle"],
                "radius": item["radius"],
            }}
            continue

        same_line = current["axis"] == item["axis"] and abs(item["line_offset"] - current["line_offset"]) <= {unfold_settings["fold_merge"]["offset_tol_mm"]}
        angle_ok = current["angle"] is None or item["angle"] is None or abs(item["angle"] - current["angle"]) <= {unfold_settings["fold_merge"]["angle_tol_deg"]}
        radius_ok = current["radius"] is None or item["radius"] is None or abs(item["radius"] - current["radius"]) <= {unfold_settings["fold_merge"]["radius_tol_mm"]}

        last_item = current["items"][-1]
        overlap = max(0.0, min(last_item["span_max"], item["span_max"]) - max(last_item["span_min"], item["span_min"]))
        gap = max(0.0, item["span_min"] - last_item["span_max"])
        extension_ok = overlap <= {unfold_settings["fold_merge"]["overlap_tol_mm"]} and gap <= {unfold_settings["fold_merge"]["gap_tol_mm"]}

        if same_line and angle_ok and radius_ok and extension_ok:
            current["items"].append(item)
        else:
            clusters.append(current)
            current = {{
                "axis": item["axis"],
                "line_offset": item["line_offset"],
                "items": [item],
                "angle": item["angle"],
                "radius": item["radius"],
            }}

    if current is not None:
        clusters.append(current)

    merged_details = []
    merged_bends = []
    merged_groups = []

    for group_id, cluster in enumerate(clusters, start=1):
        members = sorted({{item["index"] for item in cluster["items"]}})
        if not members:
            continue

        points = []
        centers = []
        span_min = min(item["span_min"] for item in cluster["items"])
        span_max = max(item["span_max"] for item in cluster["items"])

        for item in cluster["items"]:
            segment = item["segment"]
            center = segment.get("center") or [0.0, 0.0, 0.0]
            centers.append(center)
            start_pt = segment.get("start")
            end_pt = segment.get("end")
            if isinstance(start_pt, (list, tuple)) and len(start_pt) >= 3:
                points.append(start_pt)
            if isinstance(end_pt, (list, tuple)) and len(end_pt) >= 3:
                points.append(end_pt)

        avg_x = sum(float(c[0]) for c in centers) / len(centers)
        avg_y = sum(float(c[1]) for c in centers) / len(centers)
        avg_z = sum(float(c[2]) for c in centers) / len(centers)
        axis = cluster["axis"]

        if axis == "X":
            coords = [float(p[0]) for p in points] if points else [span_min, span_max]
            start = (min(coords), avg_y, avg_z)
            end = (max(coords), avg_y, avg_z)
            center = ((start[0] + end[0]) / 2.0, avg_y, avg_z)
        else:
            coords = [float(p[1]) for p in points] if points else [span_min, span_max]
            start = (avg_x, min(coords), avg_z)
            end = (avg_x, max(coords), avg_z)
            center = (avg_x, (start[1] + end[1]) / 2.0, avg_z)

        line_length = math.dist(start, end)
        source_idx = members[0]
        logical = bends_logical[source_idx] if source_idx < len(bends_logical) else {{}}

        merged_details.append({{
            "id": group_id,
            "length": line_length,
            "center": center,
            "axis": axis.lower(),
            "axis_span": (span_min, span_max),
            "start": start,
            "end": end,
            "segment_indices": [idx + 1 for idx in members],
        }})
        merged_bends.append({{
            "id": group_id,
            "type": logical.get("type"),
            "angle": logical.get("angle"),
            "radius": logical.get("radius"),
        }})
        merged_groups.append({{
            "id": group_id,
            "axis": axis,
            "line_offset": round(cluster["line_offset"], 3),
            "segment_count": len(cluster["items"]),
            "segment_indices": members,
            "start": start,
            "end": end,
            "center": center,
            "length": line_length,
        }})

    return merged_details, merged_bends, merged_groups

def _record_error(target, face_idx, stage, error_code, message, tb=None):
    detail = {{
        "face_idx": int(face_idx),
        "stage": stage,
        "error_code": int(error_code),
        "message": str(message),
    }}
    if tb:
        detail["traceback"] = tb
    target["error_details"].append(detail)

result = {{
    "success": False,
    "error": None,
    "attempts": 0,
    "error_details": [],
    "first_traceback": None,
}}
best_score = -1

try:
    pass  # placeholder for indent
except Exception as e:
    print(f"FATAL: {{e}}")
    import traceback
    traceback.print_exc()

print(f"DEBUG: shape has {{len(shape.Solids)}} solids, {{len(shape.Faces)}} faces")

# Get solids
solids = shape.Solids if shape.Solids else [shape]
sorted_solids = sorted(solids, key=lambda s: s.Volume, reverse=True)

for solid_idx, solid in enumerate(sorted_solids[:{unfold_settings["candidate_limits"]["max_solids"]}]):
    print(f"DEBUG: trying solid {{solid_idx}}, volume={{solid.Volume:.1f}}")
    # Calculate thickness first
    detected_thickness = get_thickness_from_solid(solid)
    print(f"DEBUG: detected thickness={{detected_thickness}}")

    # Find planar faces for base
    planar_faces = []
    for i, face in enumerate(solid.Faces):
        try:
            if "Plane" in face.Surface.TypeId:
                planar_faces.append({{"index": i, "area": face.Area}})
        except:
            pass
    planar_faces.sort(key=lambda x: x["area"], reverse=True)
    print(f"DEBUG: {{len(planar_faces)}} planar faces")

    # Try the configured number of largest faces to find the best base for unfolding
    for base_info in planar_faces[:{unfold_settings["candidate_limits"]["max_base_faces_per_solid"]}]:
        base_idx = base_info["index"]
        result["attempts"] += 1
        print(f"DEBUG: trying base face {{base_idx}}, area={{base_info['area']:.1f}}")
        try:
            doc = FreeCAD.newDocument("UnfoldDoc")
            obj = doc.addObject("Part::Feature", "SheetPart")
            obj.Shape = solid
            doc.recompute()

            unfold_tree = build_sheet_tree(solid, base_idx, kFactorLookup, obj)
            if unfold_tree.error_code:
                print(f"DEBUG: SheetTree error={{unfold_tree.error_code}} on face {{base_idx}}")
                _record_error(
                    result,
                    base_idx,
                    "init",
                    unfold_tree.error_code,
                    UNFOLD_ERROR_MESSAGES.get(unfold_tree.error_code, f"Onbekende fout ({{unfold_tree.error_code}})"),
                )
                FreeCAD.closeDocument("UnfoldDoc")
                continue

            unfold_tree.Bend_analysis(base_idx, None)
            if unfold_tree.error_code:
                print(f"DEBUG: Bend_analysis error={{unfold_tree.error_code}} on face {{base_idx}}")
                _record_error(
                    result,
                    base_idx,
                    "analysis",
                    unfold_tree.error_code,
                    UNFOLD_ERROR_MESSAGES.get(unfold_tree.error_code, f"Onbekende fout ({{unfold_tree.error_code}})"),
                )
                FreeCAD.closeDocument("UnfoldDoc")
                continue

            if hasattr(unfold_tree, "root") and unfold_tree.root:
                theFaceList, foldLines = unfold_tree.unfold_tree2(unfold_tree.root)

                print(f"DEBUG: face {{base_idx}} -> error={{unfold_tree.error_code}}, faces={{len(theFaceList) if theFaceList else 0}}, folds={{len(foldLines) if foldLines else 0}}")

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
                            flat_step_path = os.path.join({repr(output_dir)}, {repr(part_name)} + "_flat.step")
                            flat_compound.exportStep(flat_step_path)

                            # Export DXF
                            dxf_path = os.path.join({repr(output_dir)}, {repr(part_name)} + "_flat.dxf")
                            import importDXF
                            importDXF.export([flat_compound], dxf_path)

                            # Extract fold details from geometry
                            fold_details = []
                            bend_line_segments = []
                            for i, line in enumerate(foldLines):
                                try:
                                    bb = line.BoundBox
                                    center = bb.Center
                                    length = line.Length
                                    start_pt = None
                                    end_pt = None
                                    try:
                                        vertices = getattr(line, "Vertexes", None) or []
                                        if len(vertices) >= 2:
                                            start_pt = vertices[0].Point
                                            end_pt = vertices[-1].Point
                                    except:
                                        start_pt = None
                                        end_pt = None
                                    x_len = bb.XLength
                                    y_len = bb.YLength
                                    seg_axis = "x" if x_len >= y_len else "y"
                                    if start_pt is not None and end_pt is not None:
                                        dx = abs(float(end_pt.x) - float(start_pt.x))
                                        dy = abs(float(end_pt.y) - float(start_pt.y))
                                        if dy > dx:
                                            seg_axis = "y"
                                        else:
                                            seg_axis = "x"
                                    axis_span = (
                                        (bb.XMin, bb.XMax)
                                        if seg_axis == "x"
                                        else (bb.YMin, bb.YMax)
                                    )
                                    fold_details.append({{
                                        "id": i+1,
                                        "length": length,
                                        "center": (center.x, center.y, center.z),
                                        "axis": seg_axis,
                                        "axis_span": axis_span,
                                        "start": (start_pt.x, start_pt.y, start_pt.z) if start_pt is not None else None,
                                        "end": (end_pt.x, end_pt.y, end_pt.z) if end_pt is not None else None
                                    }})
                                    bend_line_segments.append({{
                                        "index": i,
                                        "axis": seg_axis.upper(),
                                        "center": (center.x, center.y, center.z),
                                        "length": length,
                                        "axis_span": axis_span,
                                        "start": (start_pt.x, start_pt.y, start_pt.z) if start_pt is not None else None,
                                        "end": (end_pt.x, end_pt.y, end_pt.z) if end_pt is not None else None
                                    }})
                                except:
                                    pass

                            # Extract logical bend info from tree (Up/Down)
                            bends_logical = []
                            def traverse_bends(node):
                                if hasattr(node, "node_type") and node.node_type == "Bend":
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

                            merged_fold_details, merged_bends_logical, bend_line_groups = _merge_fold_segments(
                                bend_line_segments,
                                bends_logical,
                            )
                            if merged_fold_details:
                                display_fold_lines = len(merged_fold_details)
                                display_fold_details = merged_fold_details
                                display_bends_logical = merged_bends_logical
                            else:
                                display_fold_lines = num_folds
                                display_fold_details = fold_details
                                display_bends_logical = bends_logical

                            result = {{
                                "success": True,
                                "flat_step_path": flat_step_path,
                                "flat_length": dims[0],
                                "flat_width": dims[1],
                                "fold_lines": display_fold_lines,
                                "raw_fold_lines": num_folds,
                                "thickness": detected_thickness,
                                "fold_details": display_fold_details,
                                "bend_line_segments": bend_line_segments,
                                "bend_line_groups": bend_line_groups,
                                "bends_logical": display_bends_logical,
                                "attempts": result.get("attempts", 0),
                                "error_details": result.get("error_details", []),
                                "first_traceback": result.get("first_traceback"),
                            }}
                elif unfold_tree.error_code:
                    _record_error(
                        result,
                        base_idx,
                        "unfold",
                        unfold_tree.error_code,
                        UNFOLD_ERROR_MESSAGES.get(unfold_tree.error_code, f"Onbekende fout ({{unfold_tree.error_code}})"),
                    )
                else:
                    _record_error(
                        result,
                        base_idx,
                        "unfold",
                        -2,
                        "Unfold leverde geen vlak patroon op voor dit basisvlak",
                    )
                            
            FreeCAD.closeDocument("UnfoldDoc")
        except Exception as e:
            print(f"DEBUG EXCEPTION on face {{base_idx}}: {{type(e).__name__}}: {{e}}")
            tb = traceback.format_exc()
            if not result.get("first_traceback"):
                result["first_traceback"] = tb
            _record_error(result, base_idx, "exception", -1, f"{{type(e).__name__}}: {{e}}", tb=tb)
            try:
                FreeCAD.closeDocument("UnfoldDoc")
            except:
                pass
            continue

if not result.get("success"):
    exception_details = [d for d in result["error_details"] if d.get("stage") == "exception"]
    regular_messages = []
    for detail in result["error_details"]:
        if detail.get("stage") == "exception":
            continue
        message = detail.get("message")
        if message and message not in regular_messages:
            regular_messages.append(message)
    if exception_details:
        result["error"] = f"Interne SheetMetal fout tijdens unfold: {{exception_details[0]['message']}}"
        if regular_messages:
            result["error"] += f". Eerder ook gezien: {{'; '.join(regular_messages[:2])}}"
    elif regular_messages:
        result["error"] = f"Geen geldige unfold-route gevonden na {{result['attempts']}} pogingen: {{'; '.join(regular_messages[:3])}}"
    else:
        result["error"] = f"Unfold gefaald na {{result['attempts']}} pogingen zonder diagnose"

print("UNFOLD_RESULT:" + json.dumps(result))
'''
    print(f"    FreeCAD runtime source: {runtime_label}")
    print(f"    FreeCAD Python: {freecad_python or '(empty)'}")
    print(f"    FreeCAD root:   {sys_config.freecad_path or '(empty)'}")
    print(f"    FreeCAD cmd:    {sys_config.freecad_cmd or '(empty)'}")
    _print_runtime_debug_snapshot("    [runtime]", debug_snapshot)

    if not freecad_python or not os.path.exists(freecad_python):
        msg = (
            f"FreeCAD Python not found at \"{freecad_python or '(empty)'}\".\n"
            f"    Install FreeCAD or set FREECAD_PYTHON=C:\\path\\to\\python.exe"
        )
        print(f"    [!] {msg}")
        return {"success": False, "error": msg}

    try:
        proc = subprocess.run(
            [freecad_python, "-c", unfold_script],
            capture_output=True,
            text=True,
            timeout=unfold_settings["runtime_timeout_sec"],
            env=freecad_env,
        )

        if proc.returncode != 0:
            stderr = (proc.stderr or "").strip()
            if stderr:
                for line in stderr.split('\n')[:10]:
                    print(f"    [FreeCAD stderr] {line}")
            _print_runtime_debug_snapshot("    [runtime-failure]", debug_snapshot)
            return {"success": False, "error": f"FreeCAD exited {proc.returncode}: {stderr[:300]}"}

        # Parse result
        stdout_lines = (proc.stdout or "").strip().split('\n')
        for line in stdout_lines:
            if line.startswith('UNFOLD_RESULT:'):
                result = json.loads(line[len('UNFOLD_RESULT:'):])
                if not result.get("success"):
                    result["error"] = _summarize_unfold_failure(result)
                    # Show intermediate debug lines from FreeCAD
                    debug_lines = [l for l in stdout_lines if not l.startswith('UNFOLD_RESULT:')]
                    if debug_lines:
                        print(f"    [FreeCAD debug (last 10 lines)]:")
                        for dl in debug_lines[-10:]:
                            print(f"      {dl}")
                    first_traceback = (result.get("first_traceback") or "").strip()
                    if first_traceback:
                        print("    [FreeCAD traceback (first failure)]:")
                        for line in first_traceback.splitlines()[:12]:
                            print(f"      {line}")
                return result

        # Debug: show what FreeCAD actually output
        if stdout_lines:
            print(f"    [FreeCAD stdout (last 5 lines)]:")
            for line in stdout_lines[-5:]:
                print(f"      {line}")
        stderr = (proc.stderr or "").strip()
        if stderr:
            print(f"    [FreeCAD stderr (last 5 lines)]:")
            for line in stderr.split('\n')[-5:]:
                print(f"      {line}")
        _print_runtime_debug_snapshot("    [runtime-no-result]", debug_snapshot)

        return {"success": False, "error": "No result returned"}

    except subprocess.TimeoutExpired:
        _print_runtime_debug_snapshot("    [runtime-timeout]", debug_snapshot)
        return {"success": False, "error": f"Timeout (>{unfold_settings['runtime_timeout_sec']}s)"}
    except FileNotFoundError:
        msg = (
            f"FreeCAD executable not found: \"{freecad_python}\".\n"
            f"    Install FreeCAD or set FREECAD_PYTHON=C:\\path\\to\\python.exe"
        )
        print(f"    [!] {msg}")
        _print_runtime_debug_snapshot("    [runtime-missing]", debug_snapshot)
        return {"success": False, "error": msg}
    except Exception as e:
        _print_runtime_debug_snapshot("    [runtime-exception]", debug_snapshot)
        return {"success": False, "error": str(e)}


def run_unfold_to_step(step_file, output_dir, part_name, analysis):
    """Run FreeCAD unfold and export both DXF and STEP of flat pattern.

    Returns dict with:
    - success: bool
    - flat_step_path: path to flat STEP file
    - flat_length, flat_width: dimensions
    - fold_lines: number of bends
    """
    sys_config = SystemConfig.from_env()
    result = _run_unfold_subprocess_attempt(
        step_file,
        output_dir,
        part_name,
        sys_config,
        runtime_label="managed/runtime-configured",
    )
    if result.get("success") or not sys.platform.startswith("win"):
        return result

    desktop_config = _resolve_windows_desktop_freecad_config()
    if not desktop_config:
        return result
    if os.path.abspath(str(desktop_config.freecad_cmd or "")) == os.path.abspath(str(sys_config.freecad_cmd or "")):
        return result

    print("    [runtime-fallback] Managed runtime failed; retrying with desktop FreeCAD installation.")
    fallback_result = _run_unfold_subprocess_attempt(
        step_file,
        output_dir,
        part_name,
        desktop_config,
        runtime_label="desktop-freecad",
    )
    if fallback_result.get("success"):
        fallback_result["runtime_source"] = "desktop-freecad"
        return fallback_result

    fallback_result.setdefault("runtime_source", "desktop-freecad")
    fallback_result.setdefault("managed_runtime_error", result.get("error"))
    return fallback_result



def run_unfold(step_file, output_dir, part_name, analysis):
    """Run FreeCAD unfold via subprocess, with theoretical fallback (legacy)."""
    unfold_script = os.path.join(PIPELINE_DIR, "analysis", "freecad_unfold.py")
    dxf_output = os.path.join(output_dir, f"{part_name}_flat.dxf")
    unfold_result = {'success': False, 'error_details': []}
    unfold_settings = _get_unfold_runtime_settings()

    if not os.path.exists(unfold_script):
        print(f"  [!] Unfold script not found: {unfold_script}")
        return unfold_result

    sys_config = SystemConfig.from_env()
    freecad_env = _build_freecad_subprocess_env(sys_config)

    try:
        result = subprocess.run(
            [HOST_PYTHON, unfold_script, step_file, "-o", dxf_output],
            capture_output=True,
            text=True,
            env=freecad_env,
            timeout=unfold_settings["runtime_timeout_sec"],
        )

        if result.returncode == 0:
            unfold_result['success'] = True
            # Parse output for dimensions
            for line in result.stdout.split('\n'):
                if 'Unfold geslaagd' in line or 'Unfold successful' in line:
                    print(f"  [OK] {line.strip()}")
                elif 'Fold lines' in line:
                    print(f"  [OK] {line.strip()}")

            if os.path.exists(dxf_output):
                size_kb = os.path.getsize(dxf_output) / 1024
                print(f"  [OK] DXF: {dxf_output} ({size_kb:.0f} KB)")

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
        print(f"  ✗ Unfold timeout (>{unfold_settings['runtime_timeout_sec']}s)")
    except Exception as e:
        print(f"  ✗ Unfold error: {e}")

    return unfold_result



def run_theoretical_unfold(step_file, analysis):
    """Calculate theoretical unfold dimensions when automatic unfold fails."""
    try:
        sys_config = SystemConfig.from_env()
        freecad_python = sys_config.freecad_python
        freecad_env = _build_freecad_subprocess_env(sys_config)

        # Run theoretical calculation via FreeCAD Python
        calc_code = f'''
import sys
sys.path.insert(0, {repr(PIPELINE_DIR)})
from freecad_unfold import calculate_theoretical_unfold
import json

result = calculate_theoretical_unfold({repr(step_file)})
print("THEORETICAL_RESULT:" + json.dumps(result))
'''
        result = subprocess.run(
            [freecad_python, "-c", calc_code],
            capture_output=True,
            text=True,
            timeout=60,
            env=freecad_env,
        )

        # Parse result
        for line in result.stdout.split('\n'):
            if 'THEORETICAL_RESULT:' in line:
                import json
                data = json.loads(line.split('THEORETICAL_RESULT:')[1])
                if data.get('success'):
                    print(f"  [OK] Theoretische uitslag: ~{data['estimated_length']:.0f} x {data['estimated_width']:.0f} mm (indicatief)")
                    print(f"    Methode: oppervlakte + buiglengtes berekening")

                    # Update analysis with theoretical values
                    analysis.flat_length = data['estimated_length']
                    analysis.flat_width = data['estimated_width']

                    return data

        return None

    except Exception as e:
        print(f"  [!] Theoretische berekening gefaald: {e}")
        return None
