"""
Pipeline utilities for manufacturing analysis.

This module now delegates to specialized submodules:
- cache.py: Cache management
- file_utils.py: File discovery and batch processing
- analysis_pipeline.py: Main analysis orchestration (future)
- unfold_integration.py: FreeCAD integration (future)
- report_generation.py: PDF/report generation (future)
"""

import os
import sys
import math
from types import SimpleNamespace

# Project paths
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
CONFIG_DIR = os.path.join(DATA_DIR, "config")
DB_DIR = os.path.join(DATA_DIR, "db")

PARTS_DIR = os.path.join(DATA_DIR, "input")
OUTPUT_DIR = os.path.join(DATA_DIR, "output")
PIPELINE_DIR = os.path.join(PROJECT_ROOT, "manufacturing_pipeline")
SCRIPTS_DIR = os.path.join(PIPELINE_DIR, "scripts")

# FreeCAD Python path
from manufacturing_pipeline.core.config import SystemConfig
FREECAD_PYTHON = SystemConfig.from_env().freecad_python
HOST_PYTHON = sys.executable

# Add pipeline and scripts to path
if PIPELINE_DIR not in sys.path:
    sys.path.insert(0, PIPELINE_DIR)
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

# Import submodules (cache, file utils, analysis pipeline)
from manufacturing_pipeline.core.cache import (
    get_file_hash,
    load_cache,
    save_cache,
    get_cached_result,
    cache_result,
    CACHE_FILE,
)
from manufacturing_pipeline.core.file_utils import (
    find_step_files,
    select_step_file,
    get_output_dir,
    process_single_file,
    process_batch,
)
from manufacturing_pipeline.core.analysis_pipeline import (
    comparison_criterion,
    range_criterion,
    boolean_criterion,
    json_safe,
    primary_solid_for_classification,
    normalize_step0_review,
    build_legacy_gate_flow,
    build_classification_visuals,
)
from manufacturing_pipeline.core.hole_detection_fallback import (
    normalize_string,
    is_irregular_hole,
    xy_distance,
    euclidean_distance,
    is_same_detection,
    classify_contour_roundness,
    bridge_pre_unfold_irregular_holes,
    inject_closed_contours,
    detect_circular_wire_fallback,
)
from manufacturing_pipeline.core.unfold_integration import (
    calculate_unfold_statistics,
    merge_unfold_thickness_with_analysis,
    should_attempt_unfold,
    validate_unfold_dimensions,
    build_unfold_event_payload,
)
from manufacturing_pipeline.core.report_generation import (
    REPORT_FORMAT_SIMPLE,
    REPORT_FORMAT_COMPACT,
    build_part_summary,
    calculate_unfold_summary,
    build_hole_report,
    build_classification_report,
    build_csv_export,
    build_json_export,
    calculate_report_completeness,
)


# =============================================================================
# Main Analysis Pipeline
# =============================================================================

def run_analysis(step_file, output_dir, args, progress_callback=None):
    from manufacturing_pipeline.core.runtime_analysis import run_analysis as _impl
    return _impl(step_file, output_dir, args, progress_callback=progress_callback)
def run_unfold_to_step(step_file, output_dir, part_name, analysis):
    from manufacturing_pipeline.core.runtime_unfold import run_unfold_to_step as _impl
    return _impl(step_file, output_dir, part_name, analysis)


def run_unfold(step_file, output_dir, part_name, analysis):
    from manufacturing_pipeline.core.runtime_unfold import run_unfold as _impl
    return _impl(step_file, output_dir, part_name, analysis)


def run_theoretical_unfold(step_file, analysis):
    from manufacturing_pipeline.core.runtime_unfold import run_theoretical_unfold as _impl
    return _impl(step_file, analysis)


def run_aag_analysis(step_file):
    from manufacturing_pipeline.core.runtime_reporting import run_aag_analysis as _impl
    return _impl(step_file)


def run_debug(step_file):
    from manufacturing_pipeline.core.runtime_reporting import run_debug as _impl
    return _impl(step_file)


def generate_compact_pdf(step_file, output_dir, part_name, analysis, total_holes, unfold_result=None):
    from manufacturing_pipeline.core.runtime_reporting import generate_compact_pdf as _impl
    return _impl(step_file, output_dir, part_name, analysis, total_holes, unfold_result=unfold_result)


def generate_simple_pdf(step_file, output_dir, part_name, analysis, total_holes, unfold_result=None):
    from manufacturing_pipeline.core.runtime_reporting import generate_simple_pdf as _impl
    return _impl(step_file, output_dir, part_name, analysis, total_holes, unfold_result=unfold_result)
