"""Central decision-variable source for the manufacturing pipeline.

This module is the canonical code source for decision-driving variables used by:
- classification
- sheet feature semantics
- profile feature semantics
- unfold/runtime decision logic
- XML export policy helpers
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict


CLASSIFICATION_VARIABLES: Dict[str, Any] = {
    "plate": {
        "face_top2_threshold_pct": 50.0,
        "feature_heavy_top2_min_pct": 30.0,
        "feature_heavy_face_count_min": 40,
        "feature_heavy_edge_face_ratio_min": 3.0,
        "feature_heavy_volume_ratio_max": 0.25,
        "feature_heavy_aspect_ratio_min": 2.0,
        "thick_max_mm": 25.0,
        "thickness_ratio_max": 0.15,
        "aspect_ratio_min": 5.0,
    },
    "profile": {
        "smallest_min_mm": 5.0,
        "length_ratio_min": 3.0,
        "cross_ratio_min": 0.5,
        "cross_ratio_max": 3.5,
        "volume_ratio_strong_min": 0.5,
        "volume_ratio_weak_min": 0.15,
        "sa_v_ratio_max": 1.2,
    },
    "score_model": {
        "plate_top2_high_pct": 70.0,
        "plate_top2_min_pct": 50.0,
        "plate_support_top2_pct": 45.0,
        "plate_support_thickness_ratio_max": 0.35,
        "plate_support_aspect_min": 2.0,
        "profile_primary_points": 2.0,
        "plate_primary_points": 2.0,
        "ambiguous_margin_min": 1.0,
    },
    "standard_profile": {
        "tube_cylindrical_min_pct": 60.0,
        "tube_volume_ratio_max": 0.7,
        "tube_aspect_min": 0.5,
        "variable_thickness_enabled": True,
        "elongated_length_ratio_min": 5.0,
        "face_area_tolerance": 0.20,
    },
    "bent_sheet": {
        "thickness_max_mm": 100.0,
        "large_radius_min_mm": 1.0,
        "min_edge_count": 8,
        "volume_ratio_min": 0.10,
        "volume_ratio_max": 0.50,
        "top2_faces_max_pct": 60.0,
        "aspect_ratio_min": 2.0,
    },
    "cross_section": {
        "sample_fractions": (0.2, 0.4, 0.6, 0.8),
        "min_valid_samples": 3,
        "closed_ratio_min": 0.75,
        "perimeter_cv_max": 0.08,
        "edge_count_span_max": 2,
    },
    "hollow_detection": {
        "wire_overlap_ratio_min": 0.90,
        "rect_bbox_fill_min": 0.85,
        "rect_convexity_min": 0.95,
        "rect_tolerance_rel": 0.05,
    },
    "step0": {
        "cluster_ratio_min": 0.30,
        "round_shaft_core_compactness_min": 0.90,
        "round_shaft_core_bbox_ratio_min": 0.95,
        "round_shaft_min_length_ratio": 3.0,
        "round_shaft_axial_area_ratio_min": 0.99,
    },
}


CLASSIFICATION_REVIEW_THRESHOLDS: Dict[str, Dict[str, float]] = {
    "bent_sheet": {
        "aspect_ratio_min": 1.5,
        "min_edge_count": 8,
        "thickness_max_mm": 25,
        "top2_faces_max_pct": 50,
        "volume_ratio_min": 0.01,
        "volume_ratio_max": 0.5,
    },
    "plate": {
        "aspect_ratio_min": 1.2,
        "face_top2_threshold_pct": 65,
        "thick_max_mm": 20,
        "thickness_ratio_max": 0.25,
    },
    "profile": {
        "smallest_min_mm": 3.0,
        "length_ratio_min": 2.5,
        "cross_ratio_min": 0.7,
        "cross_ratio_max": 5.0,
        "sa_v_ratio_max": 2.0,
        "volume_ratio_strong_min": 0.3,
        "volume_ratio_weak_min": 0.1,
    },
}


PROFILE_FEATURE_DECISION_VARIABLES: Dict[str, Any] = {
    "tube_type": {
        "circular_cylindrical_min_pct": 60.0,
        "rectangular_planar_min_pct": 80.0,
        "hollow_volume_ratio_max": 0.7,
    },
    "radius_detection": {
        "noise_min_radius_mm": 0.1,
        "dedupe_tolerance_mm": 0.1,
        "torus_minor_radius_min_mm": 0.5,
        "torus_minor_radius_max_mm": 50.0,
        "torus_minor_major_ratio_max": 0.5,
    },
    "end_opening_filter": {
        "end_band_min_mm": 2.0,
        "end_band_ratio": 0.05,
        "axis_alignment_min": 0.95,
        "large_opening_max_dim_ratio": 0.60,
        "large_opening_min_dim_ratio": 0.50,
    },
    "countersink_pairing": {
        "diameter_ratio_min": 1.6,
        "diameter_ratio_max": 2.6,
        "axis_alignment_min": 0.98,
        "perp_dist_max_mm": 4.0,
        "axial_dist_min_mm": 5.0,
        "axial_dist_max_mm": 30.0,
        "depth_delta_max_mm": 2.0,
        "axial_target_mm": 15.0,
        "axial_weight": 0.05,
    },
}


SHEET_FEATURE_DECISION_VARIABLES: Dict[str, Any] = {
    "countersink_pairing": {
        "axis_alignment_min": 0.995,
        "coaxial_radial_dist_max_mm": 3.5,
        "coaxial_axial_dist_max_mm": 40.0,
        "diameter_ratio_min": 1.65,
        "diameter_ratio_max": 2.35,
        "depth_large_abs_max_mm": 8.0,
        "depth_large_rel_max_factor": 0.7,
    },
    "conical_matching": {
        "axis_alignment_min": 0.97,
        "radial_dist_base_max_mm": 1.0,
        "radial_dist_radius_factor": 1.25,
        "axial_dist_base_max_mm": 25.0,
        "axial_dist_radius_factor": 6.0,
        "included_angle_min_deg": 55.0,
        "included_angle_max_deg": 150.0,
    },
    "standalone_conical_matching": {
        "radial_limit_base_mm": 1.0,
        "radial_limit_inner_factor": 0.8,
        "axial_limit_base_mm": 40.0,
        "axial_limit_radius_factor": 8.0,
        "included_angle_min_deg": 55.0,
        "included_angle_max_deg": 150.0,
    },
}


HOLE_DETECTION_DECISION_VARIABLES: Dict[str, Any] = {
    "flat_artifact_filter": {
        "diameter_min_mm": 100.0,
        "depth_abs_min_mm": 20.0,
        "depth_thickness_factor": 3.0,
    },
}


UNFOLD_DEFAULT_THRESHOLDS: Dict[str, Any] = {
    "runtime": {
        "timeout_sec": 180,
        "extra_timeout_per_mb_sec": 45,
        "max_timeout_sec": 600,
    },
    "candidate_limits": {
        "max_solids": 3,
        "max_base_faces_per_solid": 10,
    },
    "thickness": {
        "opposite_face_dot_max": -0.9,
        "max_override_mm": 25.0,
        "min_override_delta_mm": 0.1,
    },
    "fold_merge": {
        "offset_tol_mm": 2.0,
        "angle_tol_deg": 1.0,
        "radius_tol_mm": 0.5,
        "overlap_tol_mm": 5.0,
        "gap_tol_mm": 10.0,
    },
    "simplification": {
        "fillet_radius_thickness_factor": 0.40,
        "min_fillet_faces_to_defeature": 30,
        "min_cyl_faces_to_trigger": 100,
        "skip_sheet_tree_cyl_threshold": 120,
    },
    "k_factor": {
        "default": 0.44,
        "thickness_buckets_mm": {
            "0.5": 0.44,
            "0.75": 0.44,
            "1.0": 0.44,
            "1.5": 0.44,
            "2.0": 0.44,
            "2.5": 0.44,
            "3.0": 0.44,
            "4.0": 0.44,
            "5.0": 0.44,
            "6.0": 0.44,
            "8.0": 0.44,
            "10.0": 0.44,
            "12.0": 0.44,
            "15.0": 0.44,
            "20.0": 0.44,
        },
    },
}


def get_classification_review_thresholds() -> Dict[str, Any]:
    return deepcopy(CLASSIFICATION_REVIEW_THRESHOLDS)


def get_unfold_default_thresholds() -> Dict[str, Any]:
    return deepcopy(UNFOLD_DEFAULT_THRESHOLDS)
