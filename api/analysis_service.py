"""Bridge between the API and the existing manufacturing pipeline.

Wraps process_single_file() and enriches the result with AAG details.
"""

import os
import shutil

from manufacturing_pipeline.core.utils import (
    run_analysis,
    get_output_dir,
)


def run_step_analysis(step_file: str, use_aag: bool = True) -> dict:
    """Run the manufacturing analysis pipeline on a STEP file.

    Args:
        step_file: Absolute path to the STEP file.
        use_aag: Whether to run AAG topology-based feature recognition.

    Returns:
        Enriched result dict with analysis data, AAG details, and production info.
    """

    class Args:
        def __init__(self):
            self.analyze = False
            self.aag = use_aag
            self.verbose = False
            self.debug = False
            self.no_unfold = False
            self.no_pdf = True  # No PDF generation for API
            self.no_cache = True

    args = Args()
    part_name = os.path.basename(step_file)

    try:
        output_dir, _ = get_output_dir(step_file)
        analysis, total_holes = run_analysis(step_file, output_dir, args)

        # Build base result
        result = {
            "file": part_name,
            "success": True,
            "category": getattr(analysis, "part_category", "UNKNOWN"),
            "part_type": None,
            "thickness": getattr(analysis, "thickness", 0),
            "dimensions": {
                "length": getattr(analysis, "length", 0),
                "width": getattr(analysis, "width", 0),
                "height": getattr(analysis, "height", 0),
            },
            "flat_dimensions": None,
            "production": {
                "holes_total": total_holes,
                "bends_total": getattr(analysis, "bend_count_erp", 0),
                "bends_up": 0,
                "bends_down": 0,
            },
            "aag_details": None,
        }

        # Convert part_type enum to string
        pt = getattr(analysis, "part_type", None)
        if pt is not None:
            result["part_type"] = pt.value if hasattr(pt, "value") else str(pt)

        # Add flat dimensions if unfold was successful
        flat_length = getattr(analysis, "flat_length", 0)
        flat_width = getattr(analysis, "flat_width", 0)
        if flat_length > 0 and flat_width > 0:
            result["flat_dimensions"] = {
                "length": flat_length,
                "width": flat_width,
            }

        # Extract up/down bend counts from unfold result
        unfold_result = getattr(analysis, "unfold_result", None)
        if unfold_result and unfold_result.get("success"):
            bends_logical = unfold_result.get("bends_logical", [])
            result["production"]["bends_up"] = sum(
                1 for b in bends_logical if b.get("type") == "up"
            )
            result["production"]["bends_down"] = sum(
                1 for b in bends_logical if b.get("type") == "down"
            )

        # Add AAG details if available
        aag_data = getattr(analysis, "aag_result", None)
        if aag_data and aag_data.get("success"):
            result["aag_details"] = {
                "cut_length": aag_data.get("cut_length"),
                "total_cut_length": aag_data.get("total_cut_length"),
                "pierce_count": aag_data.get("pierce_count"),
                "estimated_cut_time_seconds": aag_data.get("estimated_cut_time"),
                "face_count": aag_data.get("face_count"),
                "edge_count": aag_data.get("edge_count"),
                "hole_details": aag_data.get("holes_detail", []),
                "bend_details": aag_data.get("bends_detail", []),
            }

        # Cleanup output dir (we don't need generated files for API mode)
        try:
            shutil.rmtree(output_dir, ignore_errors=True)
        except Exception:
            pass

        return result

    except Exception as e:
        return {
            "file": part_name,
            "success": False,
            "error": str(e),
        }
