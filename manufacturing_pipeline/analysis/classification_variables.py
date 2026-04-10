"""Compatibility shim for classification variables.

Canonical source: ``manufacturing_pipeline.core.decision_variables``.
"""

from manufacturing_pipeline.core.decision_variables import CLASSIFICATION_VARIABLES

# =============================================================================
# PLATE DETECTION
# =============================================================================
# Top2 faces analysis (primary plate detection method)
PLATE_FACE_TOP2_THRESHOLD_PCT = CLASSIFICATION_VARIABLES["plate"]["face_top2_threshold_pct"]

# Feature-heavy plate fallback for industrial parts with many holes/cutouts.
# Keeps the global 50% threshold strict, but allows complex plates where
# top2-planar drops into the 30-50% band due to hundreds of small faces.
PLATE_FEATURE_HEAVY_TOP2_MIN_PCT = CLASSIFICATION_VARIABLES["plate"]["feature_heavy_top2_min_pct"]
PLATE_FEATURE_HEAVY_FACE_COUNT_MIN = CLASSIFICATION_VARIABLES["plate"]["feature_heavy_face_count_min"]
PLATE_FEATURE_HEAVY_EDGE_FACE_RATIO_MIN = CLASSIFICATION_VARIABLES["plate"]["feature_heavy_edge_face_ratio_min"]
PLATE_FEATURE_HEAVY_VOLUME_RATIO_MAX = CLASSIFICATION_VARIABLES["plate"]["feature_heavy_volume_ratio_max"]
PLATE_FEATURE_HEAVY_ASPECT_RATIO_MIN = CLASSIFICATION_VARIABLES["plate"]["feature_heavy_aspect_ratio_min"]

# Thin plate bbox fallback (when face analysis inconclusive)
PLATE_THICK_MAX_MM = CLASSIFICATION_VARIABLES["plate"]["thick_max_mm"]
PLATE_THICKNESS_RATIO_MAX = CLASSIFICATION_VARIABLES["plate"]["thickness_ratio_max"]
PLATE_ASPECT_RATIO_MIN = CLASSIFICATION_VARIABLES["plate"]["aspect_ratio_min"]

# =============================================================================
# PROFILE DETECTION (Solid beams, bars)
# =============================================================================
PROFILE_SMALLEST_MIN_MM = CLASSIFICATION_VARIABLES["profile"]["smallest_min_mm"]
PROFILE_LENGTH_RATIO_MIN = CLASSIFICATION_VARIABLES["profile"]["length_ratio_min"]
PROFILE_CROSS_RATIO_MIN = CLASSIFICATION_VARIABLES["profile"]["cross_ratio_min"]
PROFILE_CROSS_RATIO_MAX = CLASSIFICATION_VARIABLES["profile"]["cross_ratio_max"]
PROFILE_VOLUME_RATIO_STRONG_MIN = CLASSIFICATION_VARIABLES["profile"]["volume_ratio_strong_min"]
PROFILE_VOLUME_RATIO_WEAK_MIN = CLASSIFICATION_VARIABLES["profile"]["volume_ratio_weak_min"]
PROFILE_SA_V_RATIO_MAX = CLASSIFICATION_VARIABLES["profile"]["sa_v_ratio_max"]

# =============================================================================
# SCORE MODEL (Feature-flagged via ALES_CLASSIFICATION_MODE=score)
# =============================================================================
SCORE_PLATE_TOP2_HIGH_PCT = CLASSIFICATION_VARIABLES["score_model"]["plate_top2_high_pct"]
SCORE_PLATE_TOP2_MIN_PCT = CLASSIFICATION_VARIABLES["score_model"]["plate_top2_min_pct"]
SCORE_PLATE_SUPPORT_TOP2_PCT = CLASSIFICATION_VARIABLES["score_model"]["plate_support_top2_pct"]
SCORE_PLATE_SUPPORT_THICKNESS_RATIO_MAX = CLASSIFICATION_VARIABLES["score_model"]["plate_support_thickness_ratio_max"]
SCORE_PLATE_SUPPORT_ASPECT_MIN = CLASSIFICATION_VARIABLES["score_model"]["plate_support_aspect_min"]

SCORE_PROFILE_PRIMARY_POINTS = CLASSIFICATION_VARIABLES["score_model"]["profile_primary_points"]
SCORE_PLATE_PRIMARY_POINTS = CLASSIFICATION_VARIABLES["score_model"]["plate_primary_points"]
SCORE_AMBIGUOUS_MARGIN_MIN = CLASSIFICATION_VARIABLES["score_model"]["ambiguous_margin_min"]

# =============================================================================
# STANDARD PROFILE DETECTION (v2.1 - Geometry-based fallback)
# =============================================================================
# These thresholds detect standard catalog items (DIN/EN/ISO) when STEP name
# parsing fails, using geometry signatures instead of metadata.

# Hollow tube detection (round/rectangular pipes, fittings)
STANDARD_TUBE_CYLINDRICAL_MIN_PCT = CLASSIFICATION_VARIABLES["standard_profile"]["tube_cylindrical_min_pct"]
STANDARD_TUBE_VOLUME_RATIO_MAX = CLASSIFICATION_VARIABLES["standard_profile"]["tube_volume_ratio_max"]
STANDARD_TUBE_ASPECT_MIN = CLASSIFICATION_VARIABLES["standard_profile"]["tube_aspect_min"]

# Variable thickness detection (UNP, I-beams, L-profiles)
STANDARD_PROFILE_VARIABLE_THICKNESS = CLASSIFICATION_VARIABLES["standard_profile"]["variable_thickness_enabled"]
STANDARD_PROFILE_ELONGATED_LENGTH_RATIO_MIN = CLASSIFICATION_VARIABLES["standard_profile"]["elongated_length_ratio_min"]
STANDARD_PROFILE_FACE_AREA_TOLERANCE = CLASSIFICATION_VARIABLES["standard_profile"]["face_area_tolerance"]

# =============================================================================
# BENT SHEET DETECTION (v2.1 - Formed/Folded Sheet Metal)
# =============================================================================
# Detect sheet metal that has been bent/formed (U-profiles, channels, trays)
# These should be classified as PLAAT even though they don't have high top2%

# Thickness constraint - bent sheets must be thin (like normal sheets)
# Note: For U-profiles, "smallest" dimension includes the hollow opening,
# so this is more generous (allows profiles with larger cross-sections)
BENT_SHEET_THICKNESS_MAX_MM = CLASSIFICATION_VARIABLES["bent_sheet"]["thickness_max_mm"]

# Edge count - bent sheets have many edges due to bends/folds  
BENT_SHEET_LARGE_RADIUS_MIN_MM = CLASSIFICATION_VARIABLES["bent_sheet"]["large_radius_min_mm"]
BENT_SHEET_MIN_EDGE_COUNT = CLASSIFICATION_VARIABLES["bent_sheet"]["min_edge_count"]
                                          # Flat plate: ~4 edges
                                          # U-profile: ~12-16 edges
                                          # Channel: ~8-12 edges

# Volume ratio - bent sheets should be mostly air (not solid mass)
BENT_SHEET_VOLUME_RATIO_MIN = CLASSIFICATION_VARIABLES["bent_sheet"]["volume_ratio_min"]
BENT_SHEET_VOLUME_RATIO_MAX = CLASSIFICATION_VARIABLES["bent_sheet"]["volume_ratio_max"]

# Top2 faces should NOT be too high (to distinguish from completely flat plates)
BENT_SHEET_TOP2_FACES_MAX_PCT = CLASSIFICATION_VARIABLES["bent_sheet"]["top2_faces_max_pct"]

# Aspect ratio - bent sheets are typically elongated
BENT_SHEET_ASPECT_RATIO_MIN = CLASSIFICATION_VARIABLES["bent_sheet"]["aspect_ratio_min"]

# =============================================================================
# HARD PROFILE OVERRIDE (v2.2 - Closed & Constant Cross-Section)
# =============================================================================
# Robust profile signature to separate closed extrusions (e.g. kokers) from
# bent/open sheet metal geometries.

# Sample planes along dominant length axis (fractions of bbox length)
CROSS_SECTION_SAMPLE_FRACTIONS = CLASSIFICATION_VARIABLES["cross_section"]["sample_fractions"]

# Minimum successful section slices required for decision
CROSS_SECTION_MIN_VALID_SAMPLES = CLASSIFICATION_VARIABLES["cross_section"]["min_valid_samples"]

# At least this share of successful slices must be closed contours
CROSS_SECTION_CLOSED_RATIO_MIN = CLASSIFICATION_VARIABLES["cross_section"]["closed_ratio_min"]

# Constant cross-section requirement: perimeter coefficient of variation
CROSS_SECTION_PERIMETER_CV_MAX = CLASSIFICATION_VARIABLES["cross_section"]["perimeter_cv_max"]

# Topological stability across slices: max spread in edge counts
CROSS_SECTION_EDGE_COUNT_SPAN_MAX = CLASSIFICATION_VARIABLES["cross_section"]["edge_count_span_max"]

# =============================================================================
# STEP 0.2 HOLLOW/KOKER DETECTION (Wire-Loop Fallback - March 19, 2026)
# =============================================================================
# When polygon hole assembly fails (e.g., self-intersecting rings from rounded
# corners), fallback to raw wire loop polygons and validate with strict overlap.

# Wire-loop fallback: minimum overlap ratio for inner hole vs outer shell
# overlap_area = outer.intersection(inner).area
# overlap_ratio = overlap_area / inner.area  (how much of inner is covered by outer)
# If >= 0.90 (90%), determines inner ring is genuine nested hole, not artifact
# Tolerance thresholds for rounded-corner rectangles in fallback path
HOLLOW_WIRE_OVERLAP_RATIO_MIN = CLASSIFICATION_VARIABLES["hollow_detection"]["wire_overlap_ratio_min"]
HOLLOW_RECT_BBOX_FILL_MIN = CLASSIFICATION_VARIABLES["hollow_detection"]["rect_bbox_fill_min"]
HOLLOW_RECT_CONVEXITY_MIN = CLASSIFICATION_VARIABLES["hollow_detection"]["rect_convexity_min"]
HOLLOW_RECT_TOLERANCE_REL = CLASSIFICATION_VARIABLES["hollow_detection"]["rect_tolerance_rel"]

# =============================================================================
# STEP 0.1 SLICE VALIDATION (Extrusion-axis stability gate)
# =============================================================================
# Cluster ratio threshold: minimum fraction of sections that must belong to
# the dominant cluster (same cross-sectional shape along the extrusion axis)
STEP0_CLUSTER_RATIO_MIN = CLASSIFICATION_VARIABLES["step0"]["cluster_ratio_min"]

# Round solid shaft longitudinal check (machining detection).
# For an unmachined round shaft, the central longitudinal slice area is close to
# diameter * length. A significantly lower ratio indicates turned/stepped ends
# or other machining operations, and should route to ANDERS in Step 0.1.
ROUND_SHAFT_CORE_COMPACTNESS_MIN = CLASSIFICATION_VARIABLES["step0"]["round_shaft_core_compactness_min"]
ROUND_SHAFT_CORE_BBOX_RATIO_MIN = CLASSIFICATION_VARIABLES["step0"]["round_shaft_core_bbox_ratio_min"]
ROUND_SHAFT_MIN_LENGTH_RATIO = CLASSIFICATION_VARIABLES["step0"]["round_shaft_min_length_ratio"]
ROUND_SHAFT_AXIAL_AREA_RATIO_MIN = CLASSIFICATION_VARIABLES["step0"]["round_shaft_axial_area_ratio_min"]
