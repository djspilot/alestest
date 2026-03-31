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
from manufacturing_pipeline.core.paths import (
    PROJECT_ROOT, DATA_DIR, CONFIG_DIR, DB_DIR,
    PARTS_DIR, OUTPUT_DIR, PIPELINE_DIR, SCRIPTS_DIR,
)

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
    promote_rejected_contour_candidates,
)
from manufacturing_pipeline.core.unfold_integration import (
    calculate_unfold_statistics,
    merge_unfold_thickness_with_analysis,
    should_attempt_unfold,
    validate_unfold_dimensions,
    build_unfold_event_payload,
)
# =============================================================================
# Main Analysis Pipeline
# =============================================================================


# Runtime cross-module calls used by run_analysis
from manufacturing_pipeline.core.runtime_unfold import run_unfold_to_step

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
    from manufacturing_pipeline.analysis.cut_features import _detect_closed_inner_contours
    from manufacturing_pipeline.analysis.part_analyzer import analyze_part_geometry, format_analysis_report, PartType
    from manufacturing_pipeline.core.profiler import AnalysisProfiler

    part_name = os.path.splitext(os.path.basename(step_file))[0]

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
                comparison_criterion("STEP 0B", "Router confidence", step0_confidence, 0.7, ">=", "ML-router profiel confidence"),
                boolean_criterion("STEP 0B", "Router fallthrough", step0_fallthrough, False, "False betekent early exit in STEP 0"),
            ])

        criteria.extend([
            comparison_criterion("STEP 1A", "Top2 planar %", top2_planar, PLATE_FACE_TOP2_THRESHOLD_PCT, ">", "Plaatdetectie via parallelle grote vlakke faces"),
            comparison_criterion("STEP 1B", "Thickness / smallest", smallest, BENT_SHEET_THICKNESS_MAX_MM, "<=", "Gebogen plaat moet relatief dun blijven"),
            comparison_criterion("STEP 1B", "Edge count", edge_count, BENT_SHEET_MIN_EDGE_COUNT, ">=", "Gebogen plaat heeft veel randen/vouwen"),
            range_criterion("STEP 1B", "Volume ratio", volume_ratio, BENT_SHEET_VOLUME_RATIO_MIN, BENT_SHEET_VOLUME_RATIO_MAX, "Luchtig maar niet volledig hol"),
            comparison_criterion("STEP 1B", "Top2 faces %", top2_percent, BENT_SHEET_TOP2_FACES_MAX_PCT, "<=", "Niet te vlak verdeeld"),
            comparison_criterion("STEP 1B", "Aspect ratio", aspect_ratio, BENT_SHEET_ASPECT_RATIO_MIN, ">=", "Moet uitgestrekt genoeg zijn"),
            boolean_criterion("STEP 1B", "Rectangular profile exclusion", rectangular_profile_exclusion, False, "False vereist voor bent-sheet"),
            boolean_criterion("STEP 1B", "Perfect round/square exclusion", perfect_round_or_square, False, "False vereist voor bent-sheet"),
            comparison_criterion("STEP 1B", "Bend angle sum", bend_angle_sum, 360.0, ">=", ">=360 betekent gesloten bent profiel"),
            comparison_criterion("STEP 1C", "Smallest dim", smallest, PLATE_THICK_MAX_MM, "<", "Dunne plaat fallback"),
            comparison_criterion("STEP 1C", "Thickness ratio", thickness_ratio, PLATE_THICKNESS_RATIO_MAX, "<", "Kleinste/middelste verhouding"),
            comparison_criterion("STEP 1C", "Aspect ratio", aspect_ratio, PLATE_ASPECT_RATIO_MIN, ">", "Plaat moet slank genoeg zijn"),
            range_criterion("STEP 1D", "Top2 planar band", top2_planar, PLATE_FEATURE_HEAVY_TOP2_MIN_PCT, PLATE_FACE_TOP2_THRESHOLD_PCT, "Perforated plate window"),
            comparison_criterion("STEP 1D", "Face count", face_count, PLATE_FEATURE_HEAVY_FACE_COUNT_MIN, ">=", "Veel faces door perforaties"),
            comparison_criterion("STEP 1D", "Edge / face ratio", edge_face_ratio, PLATE_FEATURE_HEAVY_EDGE_FACE_RATIO_MIN, ">=", "Veel randen per face"),
            comparison_criterion("STEP 1D", "Volume ratio", volume_ratio, PLATE_FEATURE_HEAVY_VOLUME_RATIO_MAX, "<", "Perforated plates zijn relatief luchtig"),
            comparison_criterion("STEP 1D", "Aspect ratio", aspect_ratio, PLATE_FEATURE_HEAVY_ASPECT_RATIO_MIN, ">=", "Nog steeds uitgestrekt"),
            comparison_criterion("STEP 2B", "Smallest dim", smallest, PROFILE_SMALLEST_MIN_MM, ">=", "Minimale profiel-dikte"),
            comparison_criterion("STEP 2B", "Length ratio", length_ratio, PROFILE_LENGTH_RATIO_MIN, ">=", "Profiel moet lang genoeg zijn"),
            range_criterion("STEP 2B", "Cross ratio", cross_ratio, PROFILE_CROSS_RATIO_MIN, PROFILE_CROSS_RATIO_MAX, "Rechthoekig profielvenster"),
            comparison_criterion("STEP 2B", "Volume ratio strong", volume_ratio, PROFILE_VOLUME_RATIO_STRONG_MIN, ">", "Sterke profiel-indicatie"),
            comparison_criterion("STEP 2B", "Volume ratio weak", volume_ratio, PROFILE_VOLUME_RATIO_WEAK_MIN, ">=", "Zwakkere profiel-indicatie"),
            comparison_criterion("STEP 2B", "Surface / volume ratio", sa_v_ratio, PROFILE_SA_V_RATIO_MAX, "<", "Tie-breaker voor massief profiel"),
            comparison_criterion("STEP 3A", "Cylindrical %", cylindrical_pct, STANDARD_TUBE_CYLINDRICAL_MIN_PCT, ">=", "Holle buis detectie"),
            comparison_criterion("STEP 3A", "Volume ratio", volume_ratio, STANDARD_TUBE_VOLUME_RATIO_MAX, "<", "Holle buis is niet te massief"),
            comparison_criterion("STEP 3A", "Tube aspect", tube_aspect, STANDARD_TUBE_ASPECT_MIN, ">=", "Niet te plat"),
            comparison_criterion("STEP 3B", "Elongated length ratio", aspect_ratio, STANDARD_PROFILE_ELONGATED_LENGTH_RATIO_MIN, ">=", "UNP/I-beam lengteverhouding"),
            comparison_criterion("STEP 3B", "Top2 face area diff", variable_face_diff, STANDARD_PROFILE_FACE_AREA_TOLERANCE, ">", "Verschil tussen grootste 2 faces"),
            boolean_criterion("STEP 3B", "Bent-sheet exclusion", rectangular_profile_exclusion or perfect_round_or_square, False, "Variable-thickness pad mag geen bent-sheet/profiel-exclusion raken"),
        ])

        return criteria

    # Stage disable set (backward compatible with CLI)
    disabled_stages = getattr(args, 'disable_stages', set())

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
    if "classify_geometry" not in disabled_stages:
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
    else:
        print("[2/7] Profile Router: Overgeslagen (uitgeschakeld)")
        route_result = None
        with profiler.step("Profile Router", 2, 7) as s:
            s["status"] = "SKIP"
        profiler.emit(
            "classification_decision",
            "Profile Router",
            {"skipped": True, "reason": "Stage uitgeschakeld via disable_stages"},
            status="SKIP",
        )

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

    # Phase 7: AAG fallback removed
    aag_result = AAGResult({"success": False})
    print("[3b/7] AAG: Uitgeschakeld (fase 7)")
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

        solid_for_classification = primary_solid_for_classification(shape)
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
    classification_visuals = build_classification_visuals(
        analysis=analysis,
        legacy_class=legacy_class,
        legacy_trace=legacy_trace,
        classification_criteria=classification_criteria,
        source=source,
        solid_for_classification=solid_for_classification,
        part_category=part_category,
    )
    analysis.classification_visuals = classification_visuals

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
            **classification_visuals,
            "category": part_category,
            "part_type": analysis.part_type.value if hasattr(analysis.part_type, "value") else str(analysis.part_type),
            "length": round(float(analysis.length or 0), 3),
            "width": round(float(analysis.width or 0), 3),
            "height": round(float(analysis.height or 0), 3),
            "bends_total": int(analysis.bend_count_erp or 0),
        },
    )

    def _normalize_overlap_reference(ref):
        if not isinstance(ref, dict):
            return None
        position = ref.get("position")
        if isinstance(position, (list, tuple)) and len(position) >= 3:
            normalized_position = [float(position[0]), float(position[1]), float(position[2])]
        else:
            normalized_position = None
        distance = ref.get("distance")
        return {
            "id": str(ref.get("id") or ""),
            "method": str(ref.get("method") or "unknown"),
            "type": str(ref.get("type") or ""),
            "label": str(ref.get("label") or ref.get("type") or "Unknown"),
            "position": normalized_position,
            "distance": float(distance) if distance is not None else None,
        }

    def _build_overlap_summary(items):
        summary = {}
        for item in items:
            overlap_with = item.get("overlap_with")
            if not overlap_with:
                continue
            from_method = str(item.get("method") or "unknown")
            to_method = str(overlap_with.get("method") or "unknown")
            key = (from_method, to_method)
            bucket = summary.setdefault(
                key,
                {
                    "from_method": from_method,
                    "to_method": to_method,
                    "count": 0,
                    "sample_ids": [],
                },
            )
            bucket["count"] += 1
            item_id = str(item.get("id") or "")
            if item_id and len(bucket["sample_ids"]) < 5:
                bucket["sample_ids"].append(item_id)
        return sorted(summary.values(), key=lambda entry: (-entry["count"], entry["from_method"], entry["to_method"]))

    def _build_hole_visual_items(items, source_label):
        return [
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
                "perimeter": float(item.get("perimeter", 0.0) or 0.0),
                "source": str(item.get("source") or source_label),
                "method": str(item.get("method") or ("cylindrical_detector" if str(item.get("type", "hole")).lower() == "cylindrical" else "unknown")),
                "criteria": item.get("criteria") or [],
                "overlap_with": _normalize_overlap_reference(item.get("overlap_with")),
                "recovered_from": _normalize_overlap_reference(item.get("recovered_from")),
                "contour_points": [
                    [float(pt[0]), float(pt[1]), float(pt[2])]
                    for pt in (item.get("contour_points") or [])
                    if isinstance(pt, (list, tuple)) and len(pt) >= 3
                ],
            }
            for item in items
        ]

    def _build_boundary_suppressed_items(items):
        normalized = []
        for item in items:
            position = item.get("position")
            normalized.append(
                {
                    "id": str(item.get("id") or ""),
                    "label": str(item.get("label") or item.get("size") or "Boundary contour"),
                    "method": str(item.get("method") or "face_boundary_missing_round"),
                    "reason": str(item.get("reason") or "Boundary kandidaat onderdrukt"),
                    "position": [
                        float((position or (0.0, 0.0, 0.0))[0]),
                        float((position or (0.0, 0.0, 0.0))[1]),
                        float((position or (0.0, 0.0, 0.0))[2]),
                    ],
                    "size": str(item.get("size") or ""),
                    "suppressed_by": _normalize_overlap_reference(item.get("suppressed_by")),
                }
            )
        return normalized

    enable_face_boundary_hole_methods = True
    enable_pre_unfold_face_boundary_bridge = False

    def _parse_contour_dims(dim_text):
        text = str(dim_text or "").strip().lower()
        if not text:
            return []
        if "x" not in text:
            try:
                return [abs(float(text))]
            except Exception:
                return []
        parts = []
        for raw in text.split("x"):
            try:
                parts.append(abs(float(raw.strip())))
            except Exception:
                continue
        return parts

    def _matches_existing_cylindrical(contour, circular_items):
        center = contour.get("center")
        normal = contour.get("normal") or (0.0, 0.0, 1.0)
        dims = _parse_contour_dims(contour.get("dim"))
        contour_major = max(dims) if dims else None
        contour_minor = min(dims) if dims else contour_major
        for circular in circular_items:
            c_pos = tuple(getattr(circular, "position", (0.0, 0.0, 0.0)))
            c_axis = tuple(getattr(circular, "axis", (0.0, 0.0, 1.0)))
            c_diam = float(getattr(circular, "diameter", 0.0) or 0.0)
            dot = abs(
                float(normal[0]) * float(c_axis[0]) +
                float(normal[1]) * float(c_axis[1]) +
                float(normal[2]) * float(c_axis[2])
            )
            if dot < 0.65:
                continue

            dx = float(center[0]) - float(c_pos[0])
            dy = float(center[1]) - float(c_pos[1])
            dz = float(center[2]) - float(c_pos[2])
            axis_len = math.sqrt(float(c_axis[0]) ** 2 + float(c_axis[1]) ** 2 + float(c_axis[2]) ** 2) or 1.0
            axis_unit = (float(c_axis[0]) / axis_len, float(c_axis[1]) / axis_len, float(c_axis[2]) / axis_len)
            axial = abs(dx * axis_unit[0] + dy * axis_unit[1] + dz * axis_unit[2])
            radial_sq = max(0.0, dx * dx + dy * dy + dz * dz - axial * axial)
            radial = math.sqrt(radial_sq)

            if contour_major is not None and c_diam > 0:
                size_delta = abs(contour_major - c_diam)
                if size_delta > max(1.25, max(contour_major, c_diam) * 0.35):
                    continue

            radial_limit = max(3.0, c_diam * 0.55, (contour_minor or 0.0) * 0.55)
            axial_limit = max(4.0, float(getattr(circular, "depth", 0.0) or 0.0) * 0.75, (contour_major or 0.0) * 0.4)
            if radial <= radial_limit and axial <= axial_limit:
                return {
                    "id": str(getattr(circular, "id", "") or ""),
                    "method": "detect_holes_cylindrical",
                    "type": "cylindrical",
                    "label": f"Ø{c_diam:.1f} mm" if c_diam > 0 else "Cylindrical hole",
                    "position": list(c_pos),
                    "distance": round(radial, 3),
                }
        return None

    def _matches_rejected_cylindrical(contour, rejected_items):
        center = contour.get("center")
        normal = contour.get("normal") or (0.0, 0.0, 1.0)
        dims = _parse_contour_dims(contour.get("dim"))
        contour_major = max(dims) if dims else None
        contour_minor = min(dims) if dims else contour_major
        for item in rejected_items:
            position = item.get("position")
            axis = item.get("axis") or (0.0, 0.0, 1.0)
            diameter = float(item.get("diameter", 0.0) or 0.0)
            if not position:
                continue
            dot = abs(
                float(normal[0]) * float(axis[0]) +
                float(normal[1]) * float(axis[1]) +
                float(normal[2]) * float(axis[2])
            )
            if dot < 0.55:
                continue

            dx = float(center[0]) - float(position[0])
            dy = float(center[1]) - float(position[1])
            dz = float(center[2]) - float(position[2])
            axis_len = math.sqrt(float(axis[0]) ** 2 + float(axis[1]) ** 2 + float(axis[2]) ** 2) or 1.0
            axis_unit = (float(axis[0]) / axis_len, float(axis[1]) / axis_len, float(axis[2]) / axis_len)
            axial = abs(dx * axis_unit[0] + dy * axis_unit[1] + dz * axis_unit[2])
            radial_sq = max(0.0, dx * dx + dy * dy + dz * dz - axial * axial)
            radial = math.sqrt(radial_sq)

            if contour_major is not None and diameter > 0:
                size_delta = abs(contour_major - diameter)
                if size_delta > max(1.5, max(contour_major, diameter) * 0.4):
                    continue

            radial_limit = max(4.0, diameter * 0.7, (contour_minor or 0.0) * 0.7)
            axial_limit = max(5.0, float(item.get("depth", 0.0) or 0.0), (contour_major or 0.0) * 0.5)
            if radial <= radial_limit and axial <= axial_limit:
                return {
                    "id": str(item.get("id") or ""),
                    "method": "cylindrical_detector_rejected",
                    "type": "cylindrical",
                    "label": f"Ø{diameter:.1f} mm" if diameter > 0 else "Rejected cylindrical candidate",
                    "position": [float(position[0]), float(position[1]), float(position[2])],
                    "distance": round(radial, 3),
                    "reason": str(item.get("reason") or "Rejected cylindrical candidate"),
                }
        return None

    # Pre-unfold snapshot for viewer: detect holes on original 3D geometry
    # before any flattening, so pre/post unfold can be compared in timeline.
    if (
        enable_face_boundary_hole_methods
        and part_category == "GEBOGEN PLAATWERK"
        and not args.no_unfold
        and "detect_holes_pre_unfold" not in disabled_stages
    ):
        try:
            pre_circular_holes, pre_circular_debug = detect_holes(
                shape,
                is_flat_pattern=False,
                is_turned=analysis.is_turned,
                face_data=face_data,
                return_debug=True,
            )
            pre_shaped_holes, pre_shaped_debug = detect_shaped_holes(
                shape,
                face_data=face_data,
                is_flat_pattern=False,
                return_debug=True,
            )
            pre_shaped_holes, pre_shaped_debug, pre_promoted_count = promote_rejected_contour_candidates(
                pre_shaped_holes,
                pre_shaped_debug,
                pre_circular_holes,
                is_flat_pattern=False,
            )
            pre_circular_holes, pre_dedup_rejections = deduplicate_holes(
                pre_circular_holes,
                pre_shaped_holes,
                return_debug=True,
            )

            pre_total_holes = len(pre_circular_holes) + len(pre_shaped_holes)
            pre_debug_items = []
            for item in pre_circular_debug + pre_shaped_debug:
                normalized_item = dict(item)
                normalized_item["source"] = "3d-preunfold"
                pre_debug_items.append(normalized_item)

            for rejection in pre_dedup_rejections:
                for item in pre_debug_items:
                    if item.get("id") == rejection.get("id"):
                        item["status"] = "rejected"
                        item["reason"] = rejection.get("reason")
                        item["overlap_with"] = rejection.get("overlap_with")
                        item["criteria"] = [
                            *(item.get("criteria") or []),
                            *(rejection.get("criteria") or []),
                        ]
                        break

            pre_accepted = sum(1 for item in pre_debug_items if item.get("status") == "accepted")
            pre_rejected = sum(1 for item in pre_debug_items if item.get("status") == "rejected")

            analysis.detected_hole_visuals_pre_unfold = {
                "source": "3d-preunfold",
                "method_order": [
                    "detect_holes_cylindrical",
                    "face_boundary_primary_for_irregular",
                    "recovery_bucket_fallback_for_unclassified",
                    "face_boundary_rejected_promoted",
                ],
                "criteria_note": "Pre-unfold snapshot op originele 3D geometrie (voor vergelijking met flat detectie).",
                "total_candidates": len(pre_debug_items),
                "accepted_total": pre_accepted,
                "rejected_total": pre_rejected,
                "items": _build_hole_visual_items(pre_debug_items, "3d-preunfold"),
                "overlap_summary": _build_overlap_summary(pre_debug_items),
            }

            profiler.emit(
                "holes_detected_pre_unfold",
                "Detect holes (pre-unfold)",
                {
                    "total": pre_total_holes,
                    "cylindrical": len(pre_circular_holes),
                    "shaped": len(pre_shaped_holes),
                    "promoted_from_rejected": int(pre_promoted_count),
                    "accepted": pre_accepted,
                    "rejected": pre_rejected,
                    **analysis.detected_hole_visuals_pre_unfold,
                },
                status="OK",
            )
        except Exception:
            pass

    # ================================================================
    # STEP 5: Unfold if gebogen plaatwerk
    # ================================================================
    unfold_result = None
    flat_shape = None
    flat_step_path = None
    
    # Logic: If it's bent sheet metal, try to unfold
    should_unfold = (part_category == "GEBOGEN PLAATWERK") and not args.no_unfold and "unfold" not in disabled_stages

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
                print(f"  [!] Unfold niet gelukt: {unfold_result.get('error', 'onbekend') if unfold_result else 'geen resultaat'}")

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
    if "detect_holes" not in disabled_stages:
        print("\n[6/7] Detecting holes...")
        with profiler.step("Detect holes", 6, 7):
            pre_unfold_shaped_holes = []
            pre_unfold_shaped_debug = []

            if flat_shape is not None:
                print(f"  Analyseren op: UITSLAG (flat pattern)")
                analysis_shape = flat_shape
                is_flat = True
                # Precompute face data for flat pattern (different shape)
                hole_face_data = precompute_face_properties(flat_shape)

                # Also detect shaped contours on original 3D model before unfold.
                # Some irregular inner wires can be altered/lost by unfold conversion.
                pre_unfold_shaped_holes, pre_unfold_shaped_debug = [], []
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
            rejected_cylindrical_debug = [
                item
                for item in (circular_debug or [])
                if item.get("status") == "rejected"
                and "onvoldoende cilindrische dekking" in str(item.get("reason") or "").lower()
            ]

            shaped_holes, shaped_debug = [], []

            # If unfold is active, bridge missing irregular shaped holes from pre-unfold 3D.
            if enable_pre_unfold_face_boundary_bridge and is_flat and pre_unfold_shaped_holes:
                def _norm(v):
                    return str(v or "").strip().lower()

                def _is_irregular_candidate(hole):
                    return "irregular" in _norm(hole.get("type"))

                def _same_xy(a, b, tol=1.0):
                    dx = float(a[0]) - float(b[0])
                    dy = float(a[1]) - float(b[1])
                    return math.sqrt(dx * dx + dy * dy) <= tol

                existing_flat_points = [tuple(h.get("center", (0.0, 0.0, 0.0))) for h in shaped_holes]
                bridge_count = 0

                for idx, hole in enumerate(pre_unfold_shaped_holes):
                    if not _is_irregular_candidate(hole):
                        continue

                    center = hole.get("center")
                    if center is None:
                        continue

                    if any(_same_xy(center, p) for p in existing_flat_points):
                        continue

                    item_id = f"hole-preunfold-{len(shaped_holes) + bridge_count}"
                    bridge_count += 1

                    shaped_holes.append({
                        "id": item_id,
                        "type": hole.get("type") or "Irregular contour",
                        "dim": hole.get("dim") or "",
                        "center": center,
                        "normal": hole.get("normal") or (1.0, 0.0, 0.0),
                        "perimeter": float(hole.get("perimeter") or 0.0),
                        "contour_points": hole.get("contour_points") or [],
                        "method": "pre_unfold_face_boundary_bridge",
                    })
                    shaped_debug.append({
                        "id": item_id,
                        "status": "accepted",
                        "type": "irregular_contour",
                        "label": hole.get("dim") or "Irregular contour",
                        "reason": "Toegevoegd vanuit pre-unfold 3D face boundaries (bridge)",
                        "method": "pre_unfold_face_boundary_bridge",
                        "criteria": [
                            {
                                "name": "pre_unfold_bridge",
                                "value": True,
                                "threshold": True,
                                "passed": True,
                                "note": "Irregulaire contour bestond pre-unfold maar ontbrak op flat detectie",
                            }
                        ],
                        "position": center,
                        "normal": hole.get("normal") or (1.0, 0.0, 0.0),
                        "size": hole.get("dim") or "",
                        "perimeter": float(hole.get("perimeter") or 0.0),
                        "contour_points": hole.get("contour_points") or [],
                        "source": "3d-preunfold",
                    })
                    existing_flat_points.append(tuple(center))

            # Face Boundary is leading for irregular contours. If any closed inner contour
            # is still unmatched after cylindrical+shaped detection, add it explicitly.
            try:
                if not enable_face_boundary_hole_methods:
                    raise RuntimeError("face-boundary hole methods disabled")
                from OCP.TopExp import TopExp_Explorer
                from OCP.TopAbs import TopAbs_FACE, TopAbs_WIRE, TopAbs_EDGE
                from OCP.TopoDS import TopoDS
                from OCP.BRepTools import BRepTools
                from OCP.BRepAdaptor import BRepAdaptor_Surface, BRepAdaptor_Curve
                from OCP.GeomAbs import GeomAbs_Plane, GeomAbs_Circle
                from OCP.GProp import GProp_GProps
                from OCP.BRepGProp import BRepGProp
                from OCP.Bnd import Bnd_Box
                from OCP.BRepBndLib import BRepBndLib

                shape_for_contours = None
                if hasattr(analysis_shape, "val"):
                    val = analysis_shape.val()
                    shape_for_contours = val.wrapped if hasattr(val, "wrapped") else val
                elif hasattr(analysis_shape, "wrapped"):
                    shape_for_contours = analysis_shape.wrapped
                else:
                    shape_for_contours = analysis_shape

                closed_inner_contours = _detect_closed_inner_contours(shape_for_contours) if shape_for_contours is not None else []

                existing_points = []
                existing_points.extend([tuple(getattr(h, "position", (0.0, 0.0, 0.0))) for h in circular_holes])
                existing_points.extend([tuple(h.get("center", (0.0, 0.0, 0.0))) for h in shaped_holes])
                circular_points = [tuple(getattr(h, "position", (0.0, 0.0, 0.0))) for h in circular_holes]

                def _distance(a, b):
                    dx = float(a[0]) - float(b[0])
                    dy = float(a[1]) - float(b[1])
                    dz = float(a[2]) - float(b[2])
                    return math.sqrt(dx * dx + dy * dy + dz * dz)

                def _is_same_detection(a, b):
                    dx = float(a[0]) - float(b[0])
                    dy = float(a[1]) - float(b[1])
                    dz = float(a[2]) - float(b[2])
                    planar = math.sqrt(dx * dx + dy * dy)
                    if is_flat:
                        # Flat holes are represented on top/bottom surfaces with Z offset.
                        # Match by XY first so we don't duplicate circular contours.
                        return planar <= 1.0
                    return math.sqrt(dx * dx + dy * dy + dz * dz) <= 2.0

                injected_count = 0
                boundary_suppressed = []
                for contour in closed_inner_contours:
                    center = contour.get("center")
                    if center is None:
                        continue

                    dim_text = str(contour.get("dim") or "")
                    dim_parts = dim_text.lower().split("x") if "x" in dim_text.lower() else []
                    is_round_contour = False
                    if len(dim_parts) == 2:
                        try:
                            dim_a = abs(float(dim_parts[0].strip()))
                            dim_b = abs(float(dim_parts[1].strip()))
                            if dim_a > 0 and dim_b > 0:
                                ratio = max(dim_a, dim_b) / max(min(dim_a, dim_b), 1e-6)
                                is_round_contour = ratio <= 1.15
                        except Exception:
                            pass

                    matched_cylindrical = _matches_existing_cylindrical(contour, circular_holes)
                    rejected_cylindrical_match = _matches_rejected_cylindrical(contour, rejected_cylindrical_debug)
                    if is_round_contour:
                        # Only supplement cylindrical detection when no matching
                        # cylindrical hole already exists on this side/feature.
                        if matched_cylindrical is not None:
                            boundary_suppressed.append(
                                {
                                    "id": f"boundary-suppressed-{len(boundary_suppressed)}",
                                    "label": str(contour.get("dim") or "Closed contour"),
                                    "method": "face_boundary_missing_round",
                                    "reason": "Cilindrisch gevonden, daarom boundary onderdrukt",
                                    "position": center,
                                    "size": str(contour.get("dim") or ""),
                                    "suppressed_by": matched_cylindrical,
                                }
                            )
                            continue

                    if any(_is_same_detection(center, point) for point in existing_points):
                        continue

                    item_id = f"hole-face-boundary-{len(shaped_holes) + injected_count}"
                    injected_count += 1
                    contour_method = "face_boundary_missing_round" if is_round_contour else "face_boundary_missing_contour"
                    contour_reason = (
                        "Toegevoegd vanuit Face Boundary op plek zonder bestaand cilindrisch gat"
                        if is_round_contour
                        else "Toegevoegd vanuit Face Boundary als ontbrekende gesloten contour"
                    )
                    if is_round_contour and rejected_cylindrical_match is not None:
                        contour_reason = "Toegevoegd vanuit Face Boundary nadat cilindrische detectie op dekking afviel"

                    shaped_holes.append({
                        "id": item_id,
                        "type": "Closed contour" if is_round_contour else "Irregular contour",
                        "dim": str(contour.get("dim") or ""),
                        "center": center,
                        "normal": contour.get("normal") or (1.0, 0.0, 0.0),
                        "perimeter": float(contour.get("perimeter") or 0.0),
                        "method": contour_method,
                    })
                    shaped_debug.append({
                        "id": item_id,
                        "status": "accepted",
                        "type": "closed_contour" if is_round_contour else "irregular_contour",
                        "label": str(contour.get("dim") or ("Closed contour" if is_round_contour else "Irregular contour")),
                        "reason": contour_reason,
                        "method": contour_method,
                        "criteria": [
                            {
                                "name": "boundary_missing_only",
                                "value": True,
                                "threshold": True,
                                "passed": True,
                                "note": "Face Boundary is alleen gebruikt waar nog geen passende hole-detectie bestond",
                            },
                            *(
                                [
                                    {
                                        "name": "boundary_recovered_after_cylindrical_reject",
                                        "value": rejected_cylindrical_match.get("label"),
                                        "threshold": "accepted_cylindrical_match",
                                        "passed": True,
                                        "note": rejected_cylindrical_match.get("reason"),
                                    }
                                ]
                                if rejected_cylindrical_match is not None
                                else []
                            ),
                        ],
                        "position": center,
                        "normal": contour.get("normal") or (1.0, 0.0, 0.0),
                        "size": str(contour.get("dim") or ""),
                        "perimeter": float(contour.get("perimeter") or 0.0),
                        "source": "flat" if is_flat else "3d",
                        "overlap_with": matched_cylindrical,
                        "recovered_from": rejected_cylindrical_match,
                    })
                    existing_points.append(tuple(center))

                # Extra fallback: circular inner wires directly from planar faces.
                # Some circular contours are not recovered through cylindrical faces
                # and can be missed after unfold/topology conversion.
                if shape_for_contours is not None:
                    circular_wire_seen = []
                    circular_wire_added = 0
                    face_exp = TopExp_Explorer(shape_for_contours, TopAbs_FACE)
                    while face_exp.More():
                        face = TopoDS.Face_s(face_exp.Current())
                        face_exp.Next()

                        surf = BRepAdaptor_Surface(face, True)
                        if surf.GetType() != GeomAbs_Plane:
                            continue

                        outer = BRepTools.OuterWire_s(face)
                        wire_exp = TopExp_Explorer(face, TopAbs_WIRE)
                        while wire_exp.More():
                            wire = TopoDS.Wire_s(wire_exp.Current())
                            wire_exp.Next()
                            if wire.IsSame(outer):
                                continue

                            edge_exp = TopExp_Explorer(wire, TopAbs_EDGE)
                            edge_count = 0
                            circle_count = 0
                            while edge_exp.More():
                                edge = TopoDS.Edge_s(edge_exp.Current())
                                edge_exp.Next()
                                curve = BRepAdaptor_Curve(edge)
                                edge_count += 1
                                if curve.GetType() == GeomAbs_Circle:
                                    circle_count += 1

                            is_circular_wire = (edge_count == 1 and circle_count == 1) or (edge_count == 2 and circle_count == 2)
                            if not is_circular_wire:
                                continue

                            props = GProp_GProps()
                            BRepGProp.LinearProperties_s(wire, props)
                            c = props.CentreOfMass()
                            center = (float(c.X()), float(c.Y()), float(c.Z()))

                            if any(math.hypot(center[0] - seen[0], center[1] - seen[1]) <= 1.0 for seen in circular_wire_seen):
                                continue
                            circular_wire_seen.append(center)

                            if any(_distance(center, point) <= 1.0 for point in existing_points):
                                continue

                            bbox = Bnd_Box()
                            BRepBndLib.Add_s(wire, bbox)
                            xmin, ymin, zmin, xmax, ymax, zmax = bbox.Get()
                            dx = max(0.0, float(xmax - xmin))
                            dy = max(0.0, float(ymax - ymin))
                            dim_a = round(max(dx, dy), 1)
                            dim_b = round(min(dx, dy), 1)
                            dim_text = f"{dim_a}x{dim_b}"

                            matched_cylindrical = _matches_existing_cylindrical(
                                {
                                    "center": center,
                                    "normal": (1.0, 0.0, 0.0),
                                    "dim": dim_text,
                                },
                                circular_holes,
                            )
                            rejected_cylindrical_match = _matches_rejected_cylindrical(
                                {
                                    "center": center,
                                    "normal": (1.0, 0.0, 0.0),
                                    "dim": dim_text,
                                },
                                rejected_cylindrical_debug,
                            )
                            if matched_cylindrical is not None:
                                boundary_suppressed.append(
                                    {
                                        "id": f"boundary-suppressed-{len(boundary_suppressed)}",
                                        "label": dim_text,
                                        "method": "face_boundary_missing_round",
                                        "reason": "Cilindrisch gevonden, daarom boundary onderdrukt",
                                        "position": center,
                                        "size": dim_text,
                                        "suppressed_by": matched_cylindrical,
                                    }
                                )
                                continue

                            if circular_wire_added >= 3:
                                continue

                            item_id = f"hole-face-circular-wire-{len(shaped_holes)}"
                            shaped_holes.append({
                                "id": item_id,
                                "type": "Closed contour",
                                "dim": dim_text,
                                "center": center,
                                "normal": (1.0, 0.0, 0.0),
                                "perimeter": float(props.Mass() or 0.0),
                                "method": "face_boundary_missing_round",
                            })
                            shaped_debug.append({
                                "id": item_id,
                                "status": "accepted",
                                "type": "closed_contour",
                                "label": dim_text,
                                "reason": "Toegevoegd vanuit Face Boundary op plek zonder bestaand cilindrisch gat",
                                "method": "face_boundary_missing_round",
                                "criteria": [
                                    {
                                        "name": "boundary_missing_only",
                                        "value": True,
                                        "threshold": True,
                                        "passed": True,
                                        "note": "Circular inner wire alleen toegevoegd zonder bestaande cilindrische match",
                                    },
                                    *(
                                        [
                                            {
                                                "name": "boundary_recovered_after_cylindrical_reject",
                                                "value": rejected_cylindrical_match.get("label"),
                                                "threshold": "accepted_cylindrical_match",
                                                "passed": True,
                                                "note": rejected_cylindrical_match.get("reason"),
                                            }
                                        ]
                                        if rejected_cylindrical_match is not None
                                        else []
                                    ),
                                ],
                                "position": center,
                                "normal": (1.0, 0.0, 0.0),
                                "size": dim_text,
                                "perimeter": float(props.Mass() or 0.0),
                                "source": "flat" if is_flat else "3d",
                                "overlap_with": matched_cylindrical,
                                "recovered_from": rejected_cylindrical_match,
                            })
                            existing_points.append(tuple(center))
                            circular_wire_added += 1
            except Exception:
                boundary_suppressed = []
                pass

            profiler.set_sub_count("Shaped", len(shaped_holes))

            promoted_count = 0

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
                    item["overlap_with"] = rejection.get("overlap_with")
                    item["criteria"] = [
                        *(item.get("criteria") or []),
                        *(rejection.get("criteria") or []),
                    ]
                    break

        accepted_hole_count = sum(1 for item in hole_debug_items if item.get("status") == "accepted")
        rejected_hole_count = sum(1 for item in hole_debug_items if item.get("status") == "rejected")

        analysis.detected_hole_visuals = {
            "source": "flat" if is_flat else "3d",
            "method_order": [
                "detect_holes_cylindrical",
                "face_boundary_missing_round",
                "face_boundary_missing_contour",
            ],
            "criteria_note": "Cilindrische detectie is leidend; Face Boundary vult alleen ontbrekende gaten of contouren aan.",
            "total_candidates": len(hole_debug_items),
            "accepted_total": accepted_hole_count,
            "rejected_total": rejected_hole_count,
            "items": _build_hole_visual_items(hole_debug_items, "flat" if is_flat else "3d"),
            "overlap_summary": _build_overlap_summary(hole_debug_items),
            "boundary_suppressed": _build_boundary_suppressed_items(boundary_suppressed),
        }
        profiler.emit(
            "holes_detected",
            "Detect holes",
            {
                "total": total_holes,
                "cylindrical": len(circular_holes),
                "shaped": len(shaped_holes),
                "promoted_from_rejected": int(promoted_count),
                "accepted": accepted_hole_count,
                "rejected": rejected_hole_count,
                **analysis.detected_hole_visuals,
            },
        )

    else:
        print("\n[6/7] Detect holes: Overgeslagen (uitgeschakeld)")
        circular_holes, shaped_holes = [], []
        circular_debug, shaped_debug = [], []
        dedup_rejections = []
        is_flat = False
        total_holes = 0
        analysis.detected_hole_visuals = {"source": "skipped", "items": [], "total_candidates": 0, "accepted_total": 0, "rejected_total": 0, "method_order": []}
        with profiler.step("Detect holes", 6, 7) as s:
            s["status"] = "SKIP"
        profiler.emit("holes_detected", "Detect holes", {"skipped": True, "total": 0, "reason": "Stage uitgeschakeld via disable_stages"}, status="SKIP")

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

# =============================================================================
# Delegated Runtime Functions (extracted modules)
# =============================================================================
