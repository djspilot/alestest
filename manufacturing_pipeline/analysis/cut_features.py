"""Compatibility wrapper for extracted cut-feature helpers."""

from dataclasses import dataclass
import logging
from typing import Any, Dict, List, Optional

import cadquery as cq

from .features import cut_features_extractors as _cut_features_extractors
from .features import cut_features_geometry_helpers as _geometry_helpers
from .features import cut_features_profile_helpers as _profile_helpers
from .features import cut_features_sheet_helpers as _sheet_helpers
from .step_processing import deduplicate_holes, detect_holes, detect_shaped_holes
from .iso_standards import IsoStandards


class _IsoStandardsFallback:
    """Fallback only used when IsoStandards fails to initialize."""

    @staticmethod
    def identify_thread_from_diameter(_diameter, _tolerance=0.2):
        return []


try:
    iso_standards = IsoStandards()
except Exception:
    iso_standards = _IsoStandardsFallback()
logger = logging.getLogger(__name__)


@dataclass
class CutFeatures:
    nr_holes: int
    hole_contours: List[float]
    hole_radii: List[float]
    outer_contour: float
    total_contour: float
    box_x: float
    box_y: float
    source: str
    hole_types: List[str] = None
    threaded_holes: int = 0
    countersunk_holes: int = 0
    countersunk_angles: List[float] = None
    nr_cylindrical: int = 0
    nr_shaped: int = 0
    shaped_types: List[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "nr_holes": self.nr_holes,
            "hole_contours": self.hole_contours,
            "hole_radii": self.hole_radii,
            "outer_contour": self.outer_contour,
            "total_contour": self.total_contour,
            "box_x": self.box_x,
            "box_y": self.box_y,
            "source": self.source,
            "hole_types": self.hole_types or [],
            "threaded_holes": self.threaded_holes,
            "countersunk_holes": self.countersunk_holes,
            "countersunk_angles": self.countersunk_angles or [],
            "nr_cylindrical": self.nr_cylindrical,
            "nr_shaped": self.nr_shaped,
            "shaped_types": self.shaped_types or [],
        }


def extract_cut_features_for_sheet(
    solid,
    unfold_result: Optional[Dict[str, Any]] = None,
    part_classification: str = "plaat",
) -> Optional[CutFeatures]:
    return _cut_features_extractors.extract_cut_features_for_sheet(
        solid,
        CutFeaturesCls=CutFeatures,
        cq_module=cq,
        detect_holes_fn=detect_holes,
        detect_shaped_holes_fn=detect_shaped_holes,
        deduplicate_holes_fn=deduplicate_holes,
        iso_standards=iso_standards,
        logger=logger,
        detect_closed_inner_contours=_detect_closed_inner_contours,
        detect_countersunk_holes=_detect_countersunk_holes,
        detect_standalone_countersunk_holes=_detect_standalone_countersunk_holes,
        label_contours_from_holes=_label_contours_from_holes,
        get_outer_contour_length=_get_outer_contour_length,
        get_bounding_box=_get_bounding_box,
        parse_dimensions_from_string=_parse_dimensions_from_string,
        unfold_result=unfold_result,
        part_classification=part_classification,
    )


def extract_cut_features_for_profile(
    solid,
    part_classification: str = "profiel",
) -> Optional[CutFeatures]:
    return _cut_features_extractors.extract_cut_features_for_profile(
        solid,
        CutFeaturesCls=CutFeatures,
        cq_module=cq,
        detect_holes_fn=detect_holes,
        detect_shaped_holes_fn=detect_shaped_holes,
        deduplicate_holes_fn=deduplicate_holes,
        iso_standards=iso_standards,
        logger=logger,
        detect_closed_inner_contours=_detect_closed_inner_contours,
        filter_profile_end_opening_shaped_holes=_filter_profile_end_opening_shaped_holes,
        infer_profile_countersink_pairs=_infer_profile_countersink_pairs,
        detect_countersunk_holes=_detect_countersunk_holes,
        detect_standalone_countersunk_holes=_detect_standalone_countersunk_holes,
        label_contours_from_holes=_label_contours_from_holes,
        parse_dimensions_from_string=_parse_dimensions_from_string,
        part_classification=part_classification,
    )


_get_bounding_box = _profile_helpers._get_bounding_box
_parse_dimensions_from_string = _profile_helpers._parse_dimensions_from_string
_normalize_vector = _geometry_helpers._normalize_vector
_as_point_tuple = _geometry_helpers._as_point_tuple
_dot = _geometry_helpers._dot
_distance_point_to_axis = _geometry_helpers._distance_point_to_axis
_signed_axis_distance = _geometry_helpers._signed_axis_distance


def _get_outer_contour_length(shape):
    return _geometry_helpers._get_outer_contour_length(shape, logger=logger)


def _label_contours_from_holes(
    closed_contours,
    cylindrical_holes,
    countersink_matches,
    inferred_countersunk=None,
    is_profile: bool = False,
):
    return _geometry_helpers._label_contours_from_holes(
        closed_contours,
        cylindrical_holes,
        countersink_matches,
        iso_standards=iso_standards,
        as_point_tuple=_as_point_tuple,
        inferred_countersunk=inferred_countersunk,
        is_profile=is_profile,
    )


def _detect_closed_inner_contours(shape):
    return _geometry_helpers._detect_closed_inner_contours(
        shape,
        logger=logger,
        as_point_tuple=_as_point_tuple,
        normalize_vector=_normalize_vector,
        dot=_dot,
    )


def _filter_profile_end_opening_shaped_holes(
    shaped_holes,
    bbox_min,
    bbox_max,
):
    return _profile_helpers._filter_profile_end_opening_shaped_holes(
        shaped_holes,
        bbox_min,
        bbox_max,
        normalize_vector=_normalize_vector,
        as_point_tuple=_as_point_tuple,
        dot=_dot,
        parse_dimensions=_parse_dimensions_from_string,
    )


def _infer_profile_countersink_pairs(cylindrical_holes, countersink_matches):
    return _profile_helpers._infer_profile_countersink_pairs(
        cylindrical_holes,
        countersink_matches,
        normalize_vector=_normalize_vector,
        dot=_dot,
        as_point_tuple=_as_point_tuple,
        distance_point_to_axis=_distance_point_to_axis,
        signed_axis_distance=_signed_axis_distance,
    )


def _collect_conical_faces(cq_object):
    return _sheet_helpers._collect_conical_faces(
        cq_object,
        normalize_vector=_normalize_vector,
    )


def _group_conical_countersink_faces(conical_faces):
    return _sheet_helpers._group_conical_countersink_faces(
        conical_faces,
        dot=_dot,
        distance_point_to_axis=_distance_point_to_axis,
        signed_axis_distance=_signed_axis_distance,
    )


def _candidate_matches_cylindrical_hole(candidate, cylindrical_holes):
    return _sheet_helpers._candidate_matches_cylindrical_hole(
        candidate,
        cylindrical_holes,
        normalize_vector=_normalize_vector,
        as_point_tuple=_as_point_tuple,
        dot=_dot,
        distance_point_to_axis=_distance_point_to_axis,
        signed_axis_distance=_signed_axis_distance,
    )


def _detect_countersunk_holes(cq_object, cylindrical_holes):
    return _sheet_helpers._detect_countersunk_holes(
        cq_object,
        cylindrical_holes,
        collect_conical_faces=_collect_conical_faces,
        normalize_vector=_normalize_vector,
        as_point_tuple=_as_point_tuple,
        dot=_dot,
        distance_point_to_axis=_distance_point_to_axis,
        signed_axis_distance=_signed_axis_distance,
    )


def _detect_standalone_countersunk_holes(cq_object, cylindrical_holes):
    return _sheet_helpers._detect_standalone_countersunk_holes(
        cq_object,
        cylindrical_holes,
        collect_conical_faces=_collect_conical_faces,
        group_conical_countersink_faces=_group_conical_countersink_faces,
        candidate_matches_cylindrical_hole=_candidate_matches_cylindrical_hole,
    )
