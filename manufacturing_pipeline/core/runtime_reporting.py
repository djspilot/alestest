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
    """AAG disabled in phase 7."""
    return {"success": False, "error": "AAG disabled (phase 7)"}


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
