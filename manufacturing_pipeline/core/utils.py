"""
Pipeline utilities for manufacturing analysis.
"""

import os
import sys
import glob
import subprocess
import json
import hashlib
import math
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


def run_analysis(step_file, output_dir, args, progress_callback=None):
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
    from manufacturing_pipeline.analysis.step_processing import load_step_file, detect_holes, detect_shaped_holes, deduplicate_holes, precompute_face_properties
    from manufacturing_pipeline.analysis.part_analyzer import analyze_part_geometry, format_analysis_report, PartType
    from manufacturing_pipeline.core.profiler import AnalysisProfiler

    # Import AAG Analyzer
    try:
        from manufacturing_pipeline.scripts.aag_analyzer import AAGAnalyzer
    except ImportError as e:
        print(f"Warning: Could not import AAGAnalyzer: {e}")
        AAGAnalyzer = None

    part_name = os.path.splitext(os.path.basename(step_file))[0]

    def _primary_solid_for_classification(cq_shape):
        try:
            if hasattr(cq_shape, "solids"):
                solids_obj = cq_shape.solids()
                solids = solids_obj.vals() if hasattr(solids_obj, "vals") else list(solids_obj)
                if solids:
                    first = solids[0]
                    return first.wrapped if hasattr(first, "wrapped") else first
        except Exception:
            pass

        try:
            if hasattr(cq_shape, "val"):
                val = cq_shape.val()
                return val.wrapped if hasattr(val, "wrapped") else val
        except Exception:
            pass

        return cq_shape.wrapped if hasattr(cq_shape, "wrapped") else cq_shape

    def _comparison_criterion(step, name, actual, threshold, operator, note=None):
        actual_value = None if actual is None else float(actual)
        threshold_value = None if threshold is None else float(threshold)
        passed = None
        deviation = None

        if actual_value is not None and threshold_value is not None:
            if operator == ">=":
                deviation = round(actual_value - threshold_value, 3)
                passed = actual_value >= threshold_value
            elif operator == ">":
                deviation = round(actual_value - threshold_value, 3)
                passed = actual_value > threshold_value
            elif operator == "<=":
                deviation = round(threshold_value - actual_value, 3)
                passed = actual_value <= threshold_value
            elif operator == "<":
                deviation = round(threshold_value - actual_value, 3)
                passed = actual_value < threshold_value

        return {
            "step": step,
            "name": name,
            "actual": round(actual_value, 3) if actual_value is not None else None,
            "threshold": f"{operator} {threshold_value:.3f}" if threshold_value is not None else None,
            "deviation": deviation,
            "passed": passed,
            "note": note,
        }

    def _range_criterion(step, name, actual, minimum, maximum, note=None):
        actual_value = None if actual is None else float(actual)
        min_value = None if minimum is None else float(minimum)
        max_value = None if maximum is None else float(maximum)
        passed = None
        deviation = None

        if actual_value is not None and min_value is not None and max_value is not None:
            if min_value <= actual_value <= max_value:
                deviation = round(min(actual_value - min_value, max_value - actual_value), 3)
                passed = True
            elif actual_value < min_value:
                deviation = round(actual_value - min_value, 3)
                passed = False
            else:
                deviation = round(max_value - actual_value, 3)
                passed = False

        return {
            "step": step,
            "name": name,
            "actual": round(actual_value, 3) if actual_value is not None else None,
            "threshold": f"{min_value:.3f} .. {max_value:.3f}" if min_value is not None and max_value is not None else None,
            "deviation": deviation,
            "passed": passed,
            "note": note,
        }

    def _boolean_criterion(step, name, actual, should_be, note=None):
        actual_value = bool(actual)
        return {
            "step": step,
            "name": name,
            "actual": actual_value,
            "threshold": str(bool(should_be)).lower(),
            "deviation": None,
            "passed": actual_value is bool(should_be),
            "note": note,
        }

    def _compute_classification_thresholds(solid, trace):
        if solid is None:
            return []

        from manufacturing_pipeline.analysis.assembly_analysis import get_solid_topology_counts, _get_solid_surface_area
        from manufacturing_pipeline.analysis.classification_variables import (
            BENT_SHEET_ASPECT_RATIO_MIN,
            BENT_SHEET_MIN_EDGE_COUNT,
            BENT_SHEET_THICKNESS_MAX_MM,
            BENT_SHEET_TOP2_FACES_MAX_PCT,
            BENT_SHEET_VOLUME_RATIO_MAX,
            BENT_SHEET_VOLUME_RATIO_MIN,
            PLATE_ASPECT_RATIO_MIN,
            PLATE_FACE_TOP2_THRESHOLD_PCT,
            PLATE_FEATURE_HEAVY_ASPECT_RATIO_MIN,
            PLATE_FEATURE_HEAVY_EDGE_FACE_RATIO_MIN,
            PLATE_FEATURE_HEAVY_FACE_COUNT_MIN,
            PLATE_FEATURE_HEAVY_TOP2_MIN_PCT,
            PLATE_FEATURE_HEAVY_VOLUME_RATIO_MAX,
            PLATE_THICK_MAX_MM,
            PLATE_THICKNESS_RATIO_MAX,
            PROFILE_CROSS_RATIO_MAX,
            PROFILE_CROSS_RATIO_MIN,
            PROFILE_LENGTH_RATIO_MIN,
            PROFILE_SA_V_RATIO_MAX,
            PROFILE_SMALLEST_MIN_MM,
            PROFILE_VOLUME_RATIO_STRONG_MIN,
            PROFILE_VOLUME_RATIO_WEAK_MIN,
            STANDARD_PROFILE_FACE_AREA_TOLERANCE,
            STANDARD_PROFILE_ELONGATED_LENGTH_RATIO_MIN,
            STANDARD_TUBE_ASPECT_MIN,
            STANDARD_TUBE_CYLINDRICAL_MIN_PCT,
            STANDARD_TUBE_VOLUME_RATIO_MAX,
        )

        features = dict((trace or {}).get("features") or {})
        smallest = float(features.get("smallest") or 0.0)
        middle = float(features.get("middle") or 0.0)
        longest = float(features.get("longest") or 0.0)
        top2_planar = float(features.get("top2_planar_percent") or 0.0)
        top2_percent = float(features.get("top2_percent") or 0.0)
        aspect_ratio = float(features.get("aspect_ratio") or 0.0)
        thickness_ratio = float(features.get("thickness_ratio") or 0.0)
        length_ratio = float(features.get("length_ratio") or 0.0)
        cross_ratio = float(features.get("cross_ratio") or 0.0)
        volume_ratio = float(features.get("volume_ratio") or 0.0)
        bend_angle_sum = float(features.get("bend_angle_sum") or 0.0)
        step0_confidence = float(features.get("step0_confidence") or 0.0)
        step0_fallthrough = bool(features.get("step0_fallthrough")) if "step0_fallthrough" in features else None

        face_count, edge_count = get_solid_topology_counts(solid)
        edge_face_ratio = (edge_count / face_count) if face_count else 0.0
        volume = volume_ratio * smallest * middle * longest if smallest and middle and longest else 0.0
        surface_area = _get_solid_surface_area(solid)
        sa_v_ratio = (surface_area / volume) if volume > 0 else 0.0

        try:
            from OCP.BRepAdaptor import BRepAdaptor_Surface
            from OCP.GeomAbs import GeomAbs_Cylinder
            from OCP.GProp import GProp_GProps
            from OCP.BRepGProp import BRepGProp
            from OCP.TopExp import TopExp_Explorer
            from OCP.TopAbs import TopAbs_FACE
            from OCP.TopoDS import TopoDS

            cylindrical_area = 0.0
            total_area = 0.0
            face_areas = []
            exp = TopExp_Explorer(solid, TopAbs_FACE)
            while exp.More():
                face = TopoDS.Face_s(exp.Current())
                props = GProp_GProps()
                BRepGProp.SurfaceProperties_s(face, props)
                area = props.Mass()
                total_area += area
                face_areas.append(area)
                surf = BRepAdaptor_Surface(face, True)
                if surf.GetType() == GeomAbs_Cylinder:
                    cylindrical_area += area
                exp.Next()
            cylindrical_pct = (cylindrical_area / total_area) * 100 if total_area > 0 else 0.0
            face_areas.sort(reverse=True)
            variable_face_diff = (
                abs(face_areas[0] - face_areas[1]) / face_areas[0]
                if len(face_areas) >= 2 and face_areas[0] > 0
                else 0.0
            )
        except Exception:
            cylindrical_pct = 0.0
            variable_face_diff = 0.0

        profile_length_ratio = (longest / middle) if middle > 0 else 0.0
        profile_cross_ratio = (middle / smallest) if smallest > 0 else 0.0
        tube_aspect = (middle / longest) if longest > 0 else 0.0
        bent_cross_ratio = (smallest / middle) if middle > 0 else 0.0
        rectangular_profile_exclusion = (
            smallest >= PLATE_THICK_MAX_MM and
            profile_length_ratio >= PROFILE_LENGTH_RATIO_MIN and
            PROFILE_CROSS_RATIO_MIN <= profile_cross_ratio <= PROFILE_CROSS_RATIO_MAX and
            volume_ratio <= STANDARD_TUBE_VOLUME_RATIO_MAX
        )
        perfect_round_or_square = abs(bent_cross_ratio - 1.0) < 0.05 if middle > 0 else False

        criteria = []
        if step0_fallthrough is not None:
            criteria.extend([
                _comparison_criterion("STEP 0B", "Router confidence", step0_confidence, 0.7, ">=", "ML-router profiel confidence"),
                _boolean_criterion("STEP 0B", "Router fallthrough", step0_fallthrough, False, "False betekent early exit in STEP 0"),
            ])

        criteria.extend([
            _comparison_criterion("STEP 1A", "Top2 planar %", top2_planar, PLATE_FACE_TOP2_THRESHOLD_PCT, ">", "Plaatdetectie via parallelle grote vlakke faces"),
            _comparison_criterion("STEP 1B", "Thickness / smallest", smallest, BENT_SHEET_THICKNESS_MAX_MM, "<=", "Gebogen plaat moet relatief dun blijven"),
            _comparison_criterion("STEP 1B", "Edge count", edge_count, BENT_SHEET_MIN_EDGE_COUNT, ">=", "Gebogen plaat heeft veel randen/vouwen"),
            _range_criterion("STEP 1B", "Volume ratio", volume_ratio, BENT_SHEET_VOLUME_RATIO_MIN, BENT_SHEET_VOLUME_RATIO_MAX, "Luchtig maar niet volledig hol"),
            _comparison_criterion("STEP 1B", "Top2 faces %", top2_percent, BENT_SHEET_TOP2_FACES_MAX_PCT, "<=", "Niet te vlak verdeeld"),
            _comparison_criterion("STEP 1B", "Aspect ratio", aspect_ratio, BENT_SHEET_ASPECT_RATIO_MIN, ">=", "Moet uitgestrekt genoeg zijn"),
            _boolean_criterion("STEP 1B", "Rectangular profile exclusion", rectangular_profile_exclusion, False, "False vereist voor bent-sheet"),
            _boolean_criterion("STEP 1B", "Perfect round/square exclusion", perfect_round_or_square, False, "False vereist voor bent-sheet"),
            _comparison_criterion("STEP 1B", "Bend angle sum", bend_angle_sum, 360.0, ">=", ">=360 betekent gesloten bent profiel"),
            _comparison_criterion("STEP 1C", "Smallest dim", smallest, PLATE_THICK_MAX_MM, "<", "Dunne plaat fallback"),
            _comparison_criterion("STEP 1C", "Thickness ratio", thickness_ratio, PLATE_THICKNESS_RATIO_MAX, "<", "Kleinste/middelste verhouding"),
            _comparison_criterion("STEP 1C", "Aspect ratio", aspect_ratio, PLATE_ASPECT_RATIO_MIN, ">", "Plaat moet slank genoeg zijn"),
            _range_criterion("STEP 1D", "Top2 planar band", top2_planar, PLATE_FEATURE_HEAVY_TOP2_MIN_PCT, PLATE_FACE_TOP2_THRESHOLD_PCT, "Perforated plate window"),
            _comparison_criterion("STEP 1D", "Face count", face_count, PLATE_FEATURE_HEAVY_FACE_COUNT_MIN, ">=", "Veel faces door perforaties"),
            _comparison_criterion("STEP 1D", "Edge / face ratio", edge_face_ratio, PLATE_FEATURE_HEAVY_EDGE_FACE_RATIO_MIN, ">=", "Veel randen per face"),
            _comparison_criterion("STEP 1D", "Volume ratio", volume_ratio, PLATE_FEATURE_HEAVY_VOLUME_RATIO_MAX, "<", "Perforated plates zijn relatief luchtig"),
            _comparison_criterion("STEP 1D", "Aspect ratio", aspect_ratio, PLATE_FEATURE_HEAVY_ASPECT_RATIO_MIN, ">=", "Nog steeds uitgestrekt"),
            _comparison_criterion("STEP 2B", "Smallest dim", smallest, PROFILE_SMALLEST_MIN_MM, ">=", "Minimale profiel-dikte"),
            _comparison_criterion("STEP 2B", "Length ratio", length_ratio, PROFILE_LENGTH_RATIO_MIN, ">=", "Profiel moet lang genoeg zijn"),
            _range_criterion("STEP 2B", "Cross ratio", cross_ratio, PROFILE_CROSS_RATIO_MIN, PROFILE_CROSS_RATIO_MAX, "Rechthoekig profielvenster"),
            _comparison_criterion("STEP 2B", "Volume ratio strong", volume_ratio, PROFILE_VOLUME_RATIO_STRONG_MIN, ">", "Sterke profiel-indicatie"),
            _comparison_criterion("STEP 2B", "Volume ratio weak", volume_ratio, PROFILE_VOLUME_RATIO_WEAK_MIN, ">=", "Zwakkere profiel-indicatie"),
            _comparison_criterion("STEP 2B", "Surface / volume ratio", sa_v_ratio, PROFILE_SA_V_RATIO_MAX, "<", "Tie-breaker voor massief profiel"),
            _comparison_criterion("STEP 3A", "Cylindrical %", cylindrical_pct, STANDARD_TUBE_CYLINDRICAL_MIN_PCT, ">=", "Holle buis detectie"),
            _comparison_criterion("STEP 3A", "Volume ratio", volume_ratio, STANDARD_TUBE_VOLUME_RATIO_MAX, "<", "Holle buis is niet te massief"),
            _comparison_criterion("STEP 3A", "Tube aspect", tube_aspect, STANDARD_TUBE_ASPECT_MIN, ">=", "Niet te plat"),
            _comparison_criterion("STEP 3B", "Elongated length ratio", aspect_ratio, STANDARD_PROFILE_ELONGATED_LENGTH_RATIO_MIN, ">=", "UNP/I-beam lengteverhouding"),
            _comparison_criterion("STEP 3B", "Top2 face area diff", variable_face_diff, STANDARD_PROFILE_FACE_AREA_TOLERANCE, ">", "Verschil tussen grootste 2 faces"),
            _boolean_criterion("STEP 3B", "Bent-sheet exclusion", rectangular_profile_exclusion or perfect_round_or_square, False, "Variable-thickness pad mag geen bent-sheet/profiel-exclusion raken"),
        ])

        return criteria

    # Initialize profiler
    file_size_mb = os.path.getsize(step_file) / (1024 * 1024)
    profiler = AnalysisProfiler(
        os.path.basename(step_file),
        file_size_mb,
        event_callback=progress_callback,
    )

    print("\n[1/7] Loading STEP file...")
    with profiler.step("Load STEP", 1, 7):
        shape = load_step_file(step_file)

    # ================================================================
    # STEP 1.5: Profile Router (Pre-classification)
    # ================================================================
    print("[2/7] Running profile router...")
    with profiler.step("Profile Router", 2, 7):
        try:
            from manufacturing_pipeline.analysis.router import route_step_file as _route_step_file
            route_result = _route_step_file(step_file)
            print(f"  Route: {route_result.category.value.upper()} "
                  f"(profiel: {route_result.profile_label}, "
                  f"confidence: {route_result.confidence:.0%})")
            print(f"  {route_result.reasoning}")
            profiler.emit(
                "classification_decision",
                "Profile Router",
                {
                    "category": getattr(route_result.category, "value", None),
                    "profile_label": route_result.profile_label,
                    "confidence": route_result.confidence,
                    "method": route_result.method,
                    "variant": route_result.variant,
                    "reasoning": route_result.reasoning,
                    **(getattr(route_result, "debug", None) or {}),
                },
            )
        except Exception as e:
            print(f"  Warning: Router failed ({e}), continuing without routing")
            route_result = None

    # ================================================================
    # STEP 3: Standard Geometry Analysis (primary — always runs)
    # ================================================================
    print("[3/7] Analyzing dimensions & geometry...")
    with profiler.step("Classify geometry", 3, 7):
        analysis = analyze_part_geometry(shape, part_name)

    # Precompute face properties once for hole detection (avoids redundant OCP calls)
    face_data = precompute_face_properties(shape)
    profiler.count("faces", len(face_data))

    # ================================================================
    # STEP 3b: Classification from standard analysis
    # ================================================================
    class AAGResult:
        def __init__(self, data):
            self.success = data.get('success', False)
            self.thickness = data.get('thickness', 0.0)
            self.bend_count = data.get('bend_count', 0)
            self.hole_count = data.get('hole_count', 0)
            self.slot_count = data.get('slot_count', 0)
            self.data = data

    # Determine if standard analysis has enough data
    standard_has_thickness = analysis.thickness > 0
    standard_has_classification = (
        analysis.is_profile or analysis.is_turned or
        analysis.bend_count_erp > 0 or analysis.is_sheet_metal
    )

    # AAG as fallback: only run if standard analysis lacks thickness or classification
    use_aag = args.aag  # Force AAG if --aag flag
    if not standard_has_thickness and not standard_has_classification:
        use_aag = True  # Auto-fallback

    aag_result = AAGResult({"success": False})  # Default: no AAG

    if use_aag:
        print("[3b/7] AAG Fallback: standard analysis incomplete, running AAG...")
        with profiler.step("AAG Fallback", None, None):
            aag_data = run_aag_analysis(step_file)
        aag_result = AAGResult(aag_data)

        if not aag_result.success:
            print(f"  AAG also failed, using standard analysis only")
        else:
            print(f"  [OK] AAG: {aag_result.bend_count} bends, t={aag_result.thickness:.2f}mm")
    else:
        print("[3b/7] AAG: Overgeslagen (standard analyse voldoende)")
        with profiler.step("AAG Fallback", None, None) as s:
            s["status"] = "SKIP"

    # ================================================================
    # STEP 4: Merge classification
    # ================================================================
    if aag_result.success:
        # AAG ran and succeeded — use it to fill gaps
        if aag_result.thickness > 0 and analysis.thickness == 0:
            analysis.thickness = aag_result.thickness
        if aag_result.bend_count > 0 and analysis.bend_count_erp == 0:
            analysis.bend_count_erp = aag_result.bend_count
            analysis.is_sheet_metal = True

    # Classify based on (possibly AAG-augmented) standard analysis
    part_category = "ONBEKEND"
    if analysis.is_profile:
        part_category = "PROFIEL (ingekocht)"
        if analysis.part_type not in [PartType.BUIS, PartType.KOKER, PartType.KOKER_PROFIEL]:
            analysis.part_type = PartType.KOKER_PROFIEL
    elif analysis.bend_count_erp > 0:
        part_category = "GEBOGEN PLAATWERK"
        analysis.part_type = PartType.COMPLEX
        analysis.is_sheet_metal = True
    elif analysis.thickness > 0 and analysis.bend_count_erp == 0:
        part_category = "PLAAT (vlak)"
        analysis.part_type = PartType.PLAAT
        analysis.is_sheet_metal = True
    elif analysis.is_turned:
        part_category = "DRAAISTUK"

    source = "AAG+Standard" if aag_result.success else "Standard"

    legacy_class = None
    legacy_trace = None
    solid_for_classification = None
    classification_criteria = []

    try:
        from manufacturing_pipeline.analysis.assembly_analysis import classify_solid

        solid_for_classification = _primary_solid_for_classification(shape)
        legacy_class, legacy_trace = classify_solid(solid_for_classification, return_trace=True)
        analysis.classification_trace = legacy_trace
        classification_criteria = _compute_classification_thresholds(solid_for_classification, legacy_trace)
    except Exception as e:
        if args.verbose:
            print(f"  Warning: classify_solid trace build failed ({e})")

    # Bugfix: quick-mode kon ONBEKEND/OVERIG tonen terwijl classify_solid al
    # een valide eindklasse had (plaat/profiel/anders).
    if part_category == "ONBEKEND" and legacy_class is not None and legacy_trace is not None:
        if legacy_class == "plaat":
            step0_label = str(legacy_trace.get("features", {}).get("step0_label", "")).upper()
            if step0_label == "GEZETTE_PLAAT" or analysis.bend_count_erp > 0:
                part_category = "GEBOGEN PLAATWERK"
                analysis.part_type = PartType.COMPLEX
            else:
                part_category = "PLAAT (vlak)"
                analysis.part_type = PartType.PLAAT
            analysis.is_sheet_metal = True
        elif legacy_class == "profiel":
            part_category = "PROFIEL (ingekocht)"
            if analysis.part_type not in [PartType.BUIS, PartType.KOKER, PartType.KOKER_PROFIEL]:
                analysis.part_type = PartType.KOKER_PROFIEL
        elif legacy_class == "anders":
            part_category = "ANDERS"
            analysis.part_type = PartType.OVERIG

        source = f"{source}+classify_solid"

    analysis.classification_criteria = classification_criteria

    print(f"\n--- Classificatie ({source}) ---")
    print(f"Categorie:   {part_category}")
    print(f"Type:        {analysis.part_type.value.upper()}")
    print(f"Afmetingen:  {analysis.length:.0f} x {analysis.width:.0f} x {analysis.height:.0f} mm")
    print(f"Dikte:       {analysis.thickness:.1f} mm")
    print(f"Zettingen:   {analysis.bend_count_erp}")
    profiler.emit(
        "geometry_classified",
        "Classify geometry",
        {
            "part_category": part_category,
            "category": part_category,
            "part_type": analysis.part_type.value if hasattr(analysis.part_type, "value") else str(analysis.part_type),
            "dimensions": {
                "length": round(float(analysis.length or 0), 3),
                "width": round(float(analysis.width or 0), 3),
                "height": round(float(analysis.height or 0), 3),
            },
            "length": round(float(analysis.length or 0), 3),
            "width": round(float(analysis.width or 0), 3),
            "height": round(float(analysis.height or 0), 3),
            "thickness": round(float(analysis.thickness or 0), 3),
            "bends_total": int(analysis.bend_count_erp or 0),
            "source": source,
            "trace": legacy_trace or {},
            "rules": list((legacy_trace or {}).get("rules") or []),
            "criteria": classification_criteria,
            "matrix_doc": "docs/CLASSIFICATION_THRESHOLDS_MATRIX.md",
            "reasoning": [
                {
                    "step": getattr(item, "step", ""),
                    "observation": getattr(item, "observation", ""),
                    "conclusion": getattr(item, "conclusion", ""),
                    "details": getattr(item, "details", {}) or {},
                }
                for item in (getattr(analysis, "reasoning", []) or [])
            ],
        },
    )

    # ================================================================
    # STEP 5: Unfold if gebogen plaatwerk
    # ================================================================
    unfold_result = None
    flat_shape = None
    flat_step_path = None
    
    # Logic: If it's bent sheet metal, try to unfold
    should_unfold = (part_category == "GEBOGEN PLAATWERK") and not args.no_unfold

    if should_unfold:
        print("\n[5/7] Unfolding sheet metal...")
        with profiler.step("Unfold", 5, 7):
            unfold_result = run_unfold_to_step(step_file, output_dir, part_name, analysis)

            if unfold_result and unfold_result.get('success'):
                flat_step_path = unfold_result.get('flat_step_path')
                print(f"  [OK] Unfold geslaagd: {unfold_result.get('flat_length', 0):.0f} x {unfold_result.get('flat_width', 0):.0f} mm")
                print(f"  [OK] Fold lines: {unfold_result.get('fold_lines', 0)}")

                unfold_thickness = unfold_result.get('thickness', 0)
                if unfold_thickness > 0:
                    print(f"  [OK] Detected thickness (unfold): {unfold_thickness:.2f} mm")

                    if unfold_thickness < 25.0:
                        if analysis.thickness == 0 or abs(analysis.thickness - unfold_thickness) > 0.1:
                            print(f"  -> Updating thickness to {unfold_thickness:.2f} mm (Unfold is authoritative)")
                            analysis.thickness = unfold_thickness
                    else:
                        print(f"  -> Ignoring unfold thickness (seems too large: {unfold_thickness:.2f} mm)")

                if flat_step_path and os.path.exists(flat_step_path):
                    flat_shape = load_step_file(flat_step_path)
                    print(f"  [OK] Flat STEP: {flat_step_path}")
            else:
                print(f"  ⚠ Unfold niet gelukt: {unfold_result.get('error', 'onbekend') if unfold_result else 'geen resultaat'}")

        profiler.emit(
            "unfold_result",
            "Unfold",
            {
                "success": bool(unfold_result and unfold_result.get("success")),
                "flat_length": unfold_result.get("flat_length") if unfold_result else None,
                "flat_width": unfold_result.get("flat_width") if unfold_result else None,
                "fold_lines": unfold_result.get("fold_lines") if unfold_result else 0,
                "fold_details": unfold_result.get("fold_details", []) if unfold_result else [],
                "bends_logical": unfold_result.get("bends_logical", []) if unfold_result else [],
                "error": unfold_result.get("error") if unfold_result else None,
            },
            status="OK" if unfold_result and unfold_result.get("success") else "FAIL",
        )
    else:
        print(f"\n[5/7] Unfold: Niet nodig ({part_category})")
        with profiler.step("Unfold", 5, 7) as s:
            s["status"] = "SKIP"
        profiler.emit(
            "unfold_result",
            "Unfold",
            {
                "success": False,
                "skipped": True,
                "reason": f"Niet nodig ({part_category})",
            },
            status="SKIP",
        )

    # ================================================================
    # STEP 6: Detect holes - on FLAT pattern if available
    # ================================================================
    print("\n[6/7] Detecting holes...")
    with profiler.step("Detect holes", 6, 7):
        if flat_shape is not None:
            print(f"  Analyseren op: UITSLAG (flat pattern)")
            analysis_shape = flat_shape
            is_flat = True
            # Precompute face data for flat pattern (different shape)
            hole_face_data = precompute_face_properties(flat_shape)
        else:
            print(f"  Analyseren op: 3D model")
            analysis_shape = shape
            is_flat = False
            hole_face_data = face_data  # Reuse already-computed data

        with profiler.sub_step("Cylindrical"):
            circular_holes, circular_debug = detect_holes(
                analysis_shape, is_flat_pattern=is_flat,
                is_turned=analysis.is_turned, face_data=hole_face_data, return_debug=True
            )
        profiler.set_sub_count("Cylindrical", len(circular_holes))

        with profiler.sub_step("Shaped"):
            shaped_holes, shaped_debug = detect_shaped_holes(
                analysis_shape,
                face_data=hole_face_data,
                is_flat_pattern=is_flat,
                return_debug=True,
            )
        profiler.set_sub_count("Shaped", len(shaped_holes))

        with profiler.sub_step("Dedup"):
            circular_holes, dedup_rejections = deduplicate_holes(circular_holes, shaped_holes, return_debug=True)

        total_holes = len(circular_holes) + len(shaped_holes)
        profiler.count("holes", total_holes)

    print(f"  Cilindrische gaten: {len(circular_holes)}")
    for i, h in enumerate(circular_holes):
        print(f"    {i+1}. Ø{h.diameter:.2f}mm at {h.position}")

    print(f"  Shaped holes (slots/rect): {len(shaped_holes)}")
    for i, h in enumerate(shaped_holes):
        print(f"    {i+1}. {h['type']} {h['dim']} at {h['center']}")

    print(f"  Totaal: {total_holes}")
    hole_debug_items = []
    for item in circular_debug + shaped_debug:
        normalized_item = dict(item)
        normalized_item["source"] = "flat" if is_flat else "3d"
        hole_debug_items.append(normalized_item)

    for rejection in dedup_rejections:
        for item in hole_debug_items:
            if item.get("id") == rejection.get("id"):
                item["status"] = "rejected"
                item["reason"] = rejection.get("reason")
                item["criteria"] = [
                    *(item.get("criteria") or []),
                    *(rejection.get("criteria") or []),
                ]
                break

    accepted_hole_count = sum(1 for item in hole_debug_items if item.get("status") == "accepted")
    rejected_hole_count = sum(1 for item in hole_debug_items if item.get("status") == "rejected")

    analysis.detected_hole_visuals = {
        "source": "flat" if is_flat else "3d",
        "total_candidates": len(hole_debug_items),
        "accepted_total": accepted_hole_count,
        "rejected_total": rejected_hole_count,
        "items": [
            {
                "id": str(item.get("id") or ""),
                "status": str(item.get("status") or "accepted"),
                "type": str(item.get("type", "hole")).lower(),
                "diameter": float(item.get("diameter", 0.0) or 0.0) if item.get("diameter") is not None else None,
                "depth": float(item.get("depth", 0.0) or 0.0) if item.get("depth") is not None else None,
                "position": [
                    float((item.get("position") or (0.0, 0.0, 0.0))[0]),
                    float((item.get("position") or (0.0, 0.0, 0.0))[1]),
                    float((item.get("position") or (0.0, 0.0, 0.0))[2]),
                ],
                "label": str(item.get("label") or item.get("type") or "Hole"),
                "reason": str(item.get("reason") or "Geen toelichting"),
                "axis": list(item.get("axis") or (1.0, 0.0, 0.0)),
                "normal": list(item.get("normal") or (1.0, 0.0, 0.0)),
                "size": str(item.get("size", "")),
                "source": str(item.get("source") or ("flat" if is_flat else "3d")),
                "criteria": item.get("criteria") or [],
            }
            for item in hole_debug_items
        ],
    }
    profiler.emit(
        "holes_detected",
        "Detect holes",
        {
            "total": total_holes,
            "cylindrical": len(circular_holes),
            "shaped": len(shaped_holes),
            "accepted": accepted_hole_count,
            "rejected": rejected_hole_count,
            **analysis.detected_hole_visuals,
        },
    )

    # ================================================================
    # STEP 7: Save results
    # ================================================================
    print("\n[7/7] Saving results...")
    with profiler.step("Save results", 7, 7):
        # Update analysis with flat dimensions if available
        if unfold_result and unfold_result.get('success'):
            analysis.unfold_result = unfold_result  # Attach for PDF generation
            analysis.flat_length = unfold_result.get('flat_length', 0)
            analysis.flat_width = unfold_result.get('flat_width', 0)

            analysis.length = analysis.flat_length
            analysis.width = analysis.flat_width
            analysis.height = analysis.thickness

            if unfold_result.get('fold_lines', 0) > 0:
                analysis.bend_count_erp = unfold_result.get('fold_lines')

        # Save analysis report
        report_path = os.path.join(output_dir, f"{part_name}_analysis.txt")
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(format_analysis_report(analysis))
            f.write(f"\n\nCategorie: {part_category}\n")
            f.write(f"Gaten (flat): {total_holes}\n")
            if aag_result.success:
                f.write(f"AAG Analysis (Raw): {aag_result.bend_count} bends detected\n")
            if unfold_result and unfold_result.get('success'):
                f.write(f"Unfold Analysis: {unfold_result.get('fold_lines')} fold lines (Verified)\n")

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
        analysis.route_result = route_result  # Profile router result
        if aag_result.success:
            analysis.aag_result = aag_result.data

    # Print profiling summary and save timing data
    profiler.count("solids", len(shape.solids().vals()) if hasattr(shape, 'solids') else 1)
    profiler.print_summary()
    profiler.save_json(output_dir)

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
                    print(f"  [OK] Theoretische uitslag: ~{data['estimated_length']:.0f} x {data['estimated_width']:.0f} mm (indicatief)")
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
                elements.append(Paragraph(f"[OK] Unfold geslaagd: {analysis.flat_length:.1f} x {analysis.flat_width:.1f} mm", success_style))
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
