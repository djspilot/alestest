"""Runtime reporting helpers (AAG and debug only)."""

import json
import os
import subprocess
import sys

from manufacturing_pipeline.core.config import SystemConfig

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PIPELINE_DIR = os.path.join(PROJECT_ROOT, "manufacturing_pipeline")
SCRIPTS_DIR = os.path.join(PIPELINE_DIR, "scripts")

FREECAD_PYTHON = SystemConfig.from_env().freecad_python

if PIPELINE_DIR not in sys.path:
    sys.path.insert(0, PIPELINE_DIR)
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)


def run_aag_analysis(step_file):
    """Run AAG (Attributed Adjacency Graph) analysis via FreeCAD subprocess."""
    sys_config = SystemConfig.from_env()
    fc_lib = sys_config.freecad_lib
    fc_mod = sys_config.freecad_mod

    aag_script = f'''
import sys
import os
import platform
import json

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
from aag_analyzer import AAGAnalyzer

shape = Part.Shape()
shape.read("{step_file}")

analyzer = AAGAnalyzer()
result = analyzer.analyze(shape)

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

for h in result.holes[:20]:
    output["holes_detail"].append({{
        "type": h.hole_type.value if hasattr(h.hole_type, 'value') else str(h.hole_type),
        "diameter": h.diameter,
        "perimeter": h.perimeter,
        "isoperimetric_quotient": h.isoperimetric_quotient,
    }})

for b in result.production_bends[:20]:
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
            timeout=300,
        )

        for line in result.stdout.split("\n"):
            if line.startswith("AAG_RESULT:"):
                return json.loads(line[len("AAG_RESULT:"):])

        if result.returncode != 0:
            return {
                "success": False,
                "error": "AAG analysis failed",
                "details": result.stderr[-500:] if result.stderr else "",
            }

        return {"success": False, "error": "No result returned"}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "AAG analysis timeout (>300s)"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def run_debug(step_file):
    """Debug mode - detailed hole detection analysis."""
    from manufacturing_pipeline.analysis.step_processing import debug_hole_detection, load_step_file

    print(f"\n{'=' * 60}")
    print("DEBUG: HOLE DETECTION ANALYSIS")
    print(f"{'=' * 60}")
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

    if debug["cylindrical_faces"]:
        print(f"\n{'=' * 60}")
        print("ALL CYLINDRICAL FACES:")
        print(f"{'=' * 60}")
        for f in debug["cylindrical_faces"]:
            status = "HOLE CANDIDATE" if f["is_internal"] else "REJECTED (external)"
            print(
                f"  Face {f['face_index']:3d}: Ø{f['diameter']:8.2f}mm | {f['orientation']:8s} | "
                f"{f['angle_deg']:6.1f}° | {status}"
            )

    if debug["rejected_faces"]:
        print(f"\n{'=' * 60}")
        print("REJECTED FACES:")
        print(f"{'=' * 60}")
        for f in debug["rejected_faces"]:
            print(f"  Ø{f['diameter']:.2f}mm - {f['reason']}")

    if debug["final_holes"]:
        print(f"\n{'=' * 60}")
        print("DETECTED HOLES:")
        print(f"{'=' * 60}")
        for h in debug["final_holes"]:
            print(f"  Ø{h['diameter']:.2f}mm, depth={h['depth']:.2f}mm")
    else:
        print(f"\n{'=' * 60}")
        print("NO HOLES DETECTED!")
        print(f"{'=' * 60}")
        if not debug["cylindrical_faces"]:
            print("  -> No cylindrical faces in model")
        elif not debug["candidates"]:
            print("  -> All cylinders are external (FORWARD orientation)")
        else:
            print("  -> Candidates filtered out (angle < 270°)")
