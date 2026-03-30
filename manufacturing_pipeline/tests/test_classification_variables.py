"""Unit tests for classification threshold constants.

Validates domain constraints on every exported constant so that accidental
threshold edits are caught before they reach production.

Sections tested:
  - Plate detection thresholds
  - Profile detection thresholds
  - Score-model thresholds
  - Standard profile / tube detection thresholds
  - Bent-sheet detection thresholds
  - Hard profile override (cross-section sampling)
  - Hollow/koker wire-loop fallback thresholds
  - Step 0.1 slice-validation thresholds
  - Round-shaft thresholds
"""
import pytest

from manufacturing_pipeline.analysis.classification_variables import (
    # Plate detection
    PLATE_FACE_TOP2_THRESHOLD_PCT,
    PLATE_FEATURE_HEAVY_TOP2_MIN_PCT,
    PLATE_FEATURE_HEAVY_FACE_COUNT_MIN,
    PLATE_FEATURE_HEAVY_EDGE_FACE_RATIO_MIN,
    PLATE_FEATURE_HEAVY_VOLUME_RATIO_MAX,
    PLATE_FEATURE_HEAVY_ASPECT_RATIO_MIN,
    PLATE_THICK_MAX_MM,
    PLATE_THICKNESS_RATIO_MAX,
    PLATE_ASPECT_RATIO_MIN,
    # Profile detection
    PROFILE_SMALLEST_MIN_MM,
    PROFILE_LENGTH_RATIO_MIN,
    PROFILE_CROSS_RATIO_MIN,
    PROFILE_CROSS_RATIO_MAX,
    PROFILE_VOLUME_RATIO_STRONG_MIN,
    PROFILE_VOLUME_RATIO_WEAK_MIN,
    PROFILE_SA_V_RATIO_MAX,
    # Score model
    SCORE_PLATE_TOP2_HIGH_PCT,
    SCORE_PLATE_TOP2_MIN_PCT,
    SCORE_PLATE_SUPPORT_TOP2_PCT,
    SCORE_PLATE_SUPPORT_THICKNESS_RATIO_MAX,
    SCORE_PLATE_SUPPORT_ASPECT_MIN,
    SCORE_PROFILE_PRIMARY_POINTS,
    SCORE_PLATE_PRIMARY_POINTS,
    SCORE_AMBIGUOUS_MARGIN_MIN,
    # Standard profile / tube
    STANDARD_TUBE_CYLINDRICAL_MIN_PCT,
    STANDARD_TUBE_VOLUME_RATIO_MAX,
    STANDARD_TUBE_ASPECT_MIN,
    STANDARD_PROFILE_VARIABLE_THICKNESS,
    STANDARD_PROFILE_ELONGATED_LENGTH_RATIO_MIN,
    STANDARD_PROFILE_FACE_AREA_TOLERANCE,
    # Bent sheet
    BENT_SHEET_THICKNESS_MAX_MM,
    BENT_SHEET_LARGE_RADIUS_MIN_MM,
    BENT_SHEET_MIN_EDGE_COUNT,
    BENT_SHEET_VOLUME_RATIO_MIN,
    BENT_SHEET_VOLUME_RATIO_MAX,
    BENT_SHEET_TOP2_FACES_MAX_PCT,
    BENT_SHEET_ASPECT_RATIO_MIN,
    # Hard profile override
    CROSS_SECTION_SAMPLE_FRACTIONS,
    CROSS_SECTION_MIN_VALID_SAMPLES,
    CROSS_SECTION_CLOSED_RATIO_MIN,
    CROSS_SECTION_PERIMETER_CV_MAX,
    CROSS_SECTION_EDGE_COUNT_SPAN_MAX,
    # Hollow/koker
    HOLLOW_WIRE_OVERLAP_RATIO_MIN,
    HOLLOW_RECT_BBOX_FILL_MIN,
    HOLLOW_RECT_CONVEXITY_MIN,
    HOLLOW_RECT_TOLERANCE_REL,
    # Slice validation
    STEP0_CLUSTER_RATIO_MIN,
    # Round shaft
    ROUND_SHAFT_CORE_COMPACTNESS_MIN,
    ROUND_SHAFT_CORE_BBOX_RATIO_MIN,
    ROUND_SHAFT_MIN_LENGTH_RATIO,
    ROUND_SHAFT_AXIAL_AREA_RATIO_MIN,
)


# ===================================================================
# Helpers
# ===================================================================

def _pct(v: float) -> bool:
    """True if v is a valid percentage (0..100)."""
    return 0.0 <= v <= 100.0


# ===================================================================
# Plate detection
# ===================================================================


class TestPlateDetectionThresholds:
    def test_top2_threshold_is_percentage(self):
        assert _pct(PLATE_FACE_TOP2_THRESHOLD_PCT)

    def test_top2_threshold_reasonable(self):
        """Primary plate threshold should be >= 50%."""
        assert PLATE_FACE_TOP2_THRESHOLD_PCT >= 50.0

    def test_feature_heavy_top2_lower_than_primary(self):
        """Feature-heavy fallback is a relaxation."""
        assert PLATE_FEATURE_HEAVY_TOP2_MIN_PCT < PLATE_FACE_TOP2_THRESHOLD_PCT

    def test_feature_heavy_top2_is_percentage(self):
        assert _pct(PLATE_FEATURE_HEAVY_TOP2_MIN_PCT)

    def test_feature_heavy_face_count_positive(self):
        assert PLATE_FEATURE_HEAVY_FACE_COUNT_MIN > 0

    def test_feature_heavy_edge_face_ratio_positive(self):
        assert PLATE_FEATURE_HEAVY_EDGE_FACE_RATIO_MIN > 0

    def test_feature_heavy_volume_ratio_fraction(self):
        assert 0.0 < PLATE_FEATURE_HEAVY_VOLUME_RATIO_MAX < 1.0

    def test_feature_heavy_aspect_greater_than_one(self):
        assert PLATE_FEATURE_HEAVY_ASPECT_RATIO_MIN >= 1.0

    def test_thick_max_positive(self):
        assert PLATE_THICK_MAX_MM > 0

    def test_thickness_ratio_fraction(self):
        assert 0.0 < PLATE_THICKNESS_RATIO_MAX < 1.0

    def test_aspect_ratio_greater_than_one(self):
        assert PLATE_ASPECT_RATIO_MIN > 1.0


# ===================================================================
# Profile detection
# ===================================================================


class TestProfileDetectionThresholds:
    def test_smallest_min_positive(self):
        assert PROFILE_SMALLEST_MIN_MM > 0

    def test_length_ratio_greater_than_one(self):
        assert PROFILE_LENGTH_RATIO_MIN > 1.0

    def test_cross_ratio_bounds(self):
        assert 0 < PROFILE_CROSS_RATIO_MIN <= PROFILE_CROSS_RATIO_MAX

    def test_volume_strong_greater_than_weak(self):
        assert PROFILE_VOLUME_RATIO_STRONG_MIN > PROFILE_VOLUME_RATIO_WEAK_MIN

    def test_volume_weak_positive(self):
        assert PROFILE_VOLUME_RATIO_WEAK_MIN > 0

    def test_volume_strong_fraction(self):
        assert 0 < PROFILE_VOLUME_RATIO_STRONG_MIN < 1.0

    def test_sa_v_ratio_positive(self):
        assert PROFILE_SA_V_RATIO_MAX > 0


# ===================================================================
# Score model
# ===================================================================


class TestScoreModelThresholds:
    def test_top2_high_pct_is_percentage(self):
        assert _pct(SCORE_PLATE_TOP2_HIGH_PCT)

    def test_top2_min_pct_is_percentage(self):
        assert _pct(SCORE_PLATE_TOP2_MIN_PCT)

    def test_support_top2_lower_than_min(self):
        """Support threshold is a weaker signal than the primary minimum."""
        assert SCORE_PLATE_SUPPORT_TOP2_PCT < SCORE_PLATE_TOP2_MIN_PCT

    def test_support_thickness_ratio_fraction(self):
        assert 0 < SCORE_PLATE_SUPPORT_THICKNESS_RATIO_MAX < 1.0

    def test_support_aspect_greater_than_one(self):
        assert SCORE_PLATE_SUPPORT_ASPECT_MIN > 1.0

    def test_primary_points_positive(self):
        assert SCORE_PROFILE_PRIMARY_POINTS > 0
        assert SCORE_PLATE_PRIMARY_POINTS > 0

    def test_ambiguous_margin_positive(self):
        assert SCORE_AMBIGUOUS_MARGIN_MIN > 0


# ===================================================================
# Standard profile / tube detection
# ===================================================================


class TestStandardProfileThresholds:
    def test_tube_cylindrical_pct_is_percentage(self):
        assert _pct(STANDARD_TUBE_CYLINDRICAL_MIN_PCT)

    def test_tube_cylindrical_reasonable(self):
        assert STANDARD_TUBE_CYLINDRICAL_MIN_PCT >= 50.0

    def test_tube_volume_ratio_fraction(self):
        assert 0 < STANDARD_TUBE_VOLUME_RATIO_MAX < 1.0

    def test_tube_aspect_positive(self):
        assert STANDARD_TUBE_ASPECT_MIN > 0

    def test_variable_thickness_is_bool(self):
        assert isinstance(STANDARD_PROFILE_VARIABLE_THICKNESS, bool)

    def test_elongated_length_ratio_greater_than_one(self):
        assert STANDARD_PROFILE_ELONGATED_LENGTH_RATIO_MIN > 1.0

    def test_face_area_tolerance_fraction(self):
        assert 0 < STANDARD_PROFILE_FACE_AREA_TOLERANCE < 1.0


# ===================================================================
# Bent sheet detection
# ===================================================================


class TestBentSheetThresholds:
    def test_thickness_max_positive(self):
        assert BENT_SHEET_THICKNESS_MAX_MM > 0

    def test_large_radius_min_positive(self):
        assert BENT_SHEET_LARGE_RADIUS_MIN_MM > 0

    def test_min_edge_count_positive(self):
        assert BENT_SHEET_MIN_EDGE_COUNT > 0

    def test_min_edge_count_at_least_8(self):
        """Flat plates have ~4 edges; bent sheets should need >= 8."""
        assert BENT_SHEET_MIN_EDGE_COUNT >= 8

    def test_volume_ratio_bounds(self):
        assert 0 < BENT_SHEET_VOLUME_RATIO_MIN < BENT_SHEET_VOLUME_RATIO_MAX

    def test_volume_ratio_max_below_half(self):
        assert BENT_SHEET_VOLUME_RATIO_MAX <= 0.50

    def test_top2_max_pct_is_percentage(self):
        assert _pct(BENT_SHEET_TOP2_FACES_MAX_PCT)

    def test_top2_max_above_plate_threshold(self):
        """Bent sheets can have up to 60% top2 — above the flat-plate 50%
        threshold — because formed/bent geometry still has concentrated faces."""
        assert BENT_SHEET_TOP2_FACES_MAX_PCT > PLATE_FACE_TOP2_THRESHOLD_PCT

    def test_aspect_ratio_greater_than_one(self):
        assert BENT_SHEET_ASPECT_RATIO_MIN >= 1.0


# ===================================================================
# Hard profile override (cross-section sampling)
# ===================================================================


class TestCrossSectionOverride:
    def test_sample_fractions_in_unit_interval(self):
        for frac in CROSS_SECTION_SAMPLE_FRACTIONS:
            assert 0 < frac < 1, f"Fraction {frac} outside (0,1)"

    def test_sample_fractions_tuple(self):
        assert isinstance(CROSS_SECTION_SAMPLE_FRACTIONS, tuple)

    def test_min_valid_samples_positive(self):
        assert CROSS_SECTION_MIN_VALID_SAMPLES > 0

    def test_min_valid_samples_leq_total_fractions(self):
        assert CROSS_SECTION_MIN_VALID_SAMPLES <= len(CROSS_SECTION_SAMPLE_FRACTIONS)

    def test_closed_ratio_majority(self):
        assert CROSS_SECTION_CLOSED_RATIO_MIN > 0.5

    def test_closed_ratio_at_most_one(self):
        assert CROSS_SECTION_CLOSED_RATIO_MIN <= 1.0

    def test_perimeter_cv_positive(self):
        assert CROSS_SECTION_PERIMETER_CV_MAX > 0

    def test_perimeter_cv_small(self):
        """CV <= 0.08 means less than 8% variation."""
        assert CROSS_SECTION_PERIMETER_CV_MAX <= 0.10

    def test_edge_count_span_positive(self):
        assert CROSS_SECTION_EDGE_COUNT_SPAN_MAX > 0

    def test_edge_count_span_small(self):
        """Span of 2 means at most 2 edges difference across sections."""
        assert CROSS_SECTION_EDGE_COUNT_SPAN_MAX <= 4


# ===================================================================
# Hollow / koker wire-loop fallback
# ===================================================================


class TestHollowKokerThresholds:
    def test_overlap_ratio_high(self):
        assert HOLLOW_WIRE_OVERLAP_RATIO_MIN >= 0.80

    def test_overlap_ratio_at_most_one(self):
        assert HOLLOW_WIRE_OVERLAP_RATIO_MIN <= 1.0

    def test_bbox_fill_high(self):
        assert HOLLOW_RECT_BBOX_FILL_MIN >= 0.80

    def test_bbox_fill_at_most_one(self):
        assert HOLLOW_RECT_BBOX_FILL_MIN <= 1.0

    def test_convexity_high(self):
        assert HOLLOW_RECT_CONVEXITY_MIN >= 0.90

    def test_convexity_at_most_one(self):
        assert HOLLOW_RECT_CONVEXITY_MIN <= 1.0

    def test_tolerance_rel_positive(self):
        assert HOLLOW_RECT_TOLERANCE_REL > 0

    def test_tolerance_rel_small(self):
        assert HOLLOW_RECT_TOLERANCE_REL <= 0.10


# ===================================================================
# Slice validation
# ===================================================================


class TestSliceValidation:
    def test_cluster_ratio_positive(self):
        assert STEP0_CLUSTER_RATIO_MIN > 0

    def test_cluster_ratio_minority_allowed(self):
        """30% is deliberately low — lets ambiguous cases fall through."""
        assert STEP0_CLUSTER_RATIO_MIN <= 0.50


# ===================================================================
# Round shaft
# ===================================================================


class TestRoundShaftThresholds:
    def test_core_compactness_high(self):
        assert ROUND_SHAFT_CORE_COMPACTNESS_MIN >= 0.80

    def test_core_compactness_at_most_one(self):
        assert ROUND_SHAFT_CORE_COMPACTNESS_MIN <= 1.0

    def test_core_bbox_ratio_high(self):
        assert ROUND_SHAFT_CORE_BBOX_RATIO_MIN >= 0.80

    def test_core_bbox_ratio_at_most_one(self):
        assert ROUND_SHAFT_CORE_BBOX_RATIO_MIN <= 1.0

    def test_min_length_ratio_greater_than_one(self):
        assert ROUND_SHAFT_MIN_LENGTH_RATIO > 1.0

    def test_axial_area_ratio_high(self):
        assert ROUND_SHAFT_AXIAL_AREA_RATIO_MIN >= 0.90

    def test_axial_area_ratio_at_most_one(self):
        assert ROUND_SHAFT_AXIAL_AREA_RATIO_MIN <= 1.0
