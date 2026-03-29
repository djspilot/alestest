from manufacturing_pipeline.analysis.geometry import profile_sections as shared
from manufacturing_pipeline.analysis.io import step_file_io
from manufacturing_pipeline.analysis.features import hole_detection
from manufacturing_pipeline.analysis.bom import assembly_analysis as bom_assembly_analysis
from manufacturing_pipeline.analysis.classification_core import step0 as classification_core_step0
from manufacturing_pipeline.analysis.classification_core import geometry_metrics as classification_geometry_metrics
from manufacturing_pipeline.analysis.classification_core import hollow_closed as classification_hollow_closed
from manufacturing_pipeline.analysis.classification_core import result_types as classification_result_types
from manufacturing_pipeline.analysis.classification_core import validation as classification_validation
from manufacturing_pipeline.analysis import assembly_analysis
from manufacturing_pipeline.analysis import classification
from manufacturing_pipeline.analysis import profile_classifier
from manufacturing_pipeline.analysis import step_processing
from manufacturing_pipeline.analysis import step0_section_tools


def test_step0_section_tools_reexports_shared_profile_geometry():
    assert step0_section_tools.AxisCandidate is shared.AxisCandidate
    assert step0_section_tools.Section2D is shared.Section2D
    assert step0_section_tools.ProfileRegistry is shared.ProfileRegistry
    assert step0_section_tools.normalize is shared.normalize
    assert step0_section_tools.normalize_section_polygon is shared.normalize_section_polygon
    assert step0_section_tools.match_templates is shared.match_templates


def test_profile_classifier_reexports_shared_profile_geometry():
    assert profile_classifier.AxisCandidate is shared.AxisCandidate
    assert profile_classifier.SectionFeatures is shared.SectionFeatures
    assert profile_classifier.ProfileRegistry is shared.ProfileRegistry
    assert profile_classifier.normalize is shared.normalize
    assert profile_classifier.extract_section_features is shared.extract_section_features
    assert profile_classifier.make_i_section is shared.make_i_section


def test_classification_reexports_internal_step0_module():
    assert classification.classify_step0 is classification_core_step0.classify_step0
    assert classification.classify_step0_detailed_trace is classification_core_step0.classify_step0_detailed_trace


def test_step_processing_reexports_internal_step_file_io():
    assert step_processing.STEP_HEADER is step_file_io.STEP_HEADER
    assert step_processing._normalize_step_file is step_file_io._normalize_step_file
    assert step_processing._load_step_via_xcaf is step_file_io._load_step_via_xcaf
    assert step_processing.load_step_file is step_file_io.load_step_file
    assert step_processing.tessellate_shape is step_file_io.tessellate_shape
    assert step_processing.extract_display_edges is step_file_io.extract_display_edges


def test_step_processing_reexports_internal_hole_helpers():
    assert step_processing.HoleFeature is hole_detection.HoleFeature
    assert step_processing.precompute_face_properties is hole_detection.precompute_face_properties
    assert step_processing._classify_shaped_inner_wire is hole_detection._classify_shaped_inner_wire
    assert step_processing._sample_edge_points is hole_detection._sample_edge_points
    assert step_processing._edge_end_keys is hole_detection._edge_end_keys
    assert step_processing._recover_contours_from_bucket is hole_detection._recover_contours_from_bucket


def test_assembly_analysis_reexports_internal_bom_module():
    assert assembly_analysis.BOMItem is bom_assembly_analysis.BOMItem
    assert assembly_analysis.AssemblyAnalysis is bom_assembly_analysis.AssemblyAnalysis
    assert assembly_analysis.classify_solid is bom_assembly_analysis.classify_solid
    assert assembly_analysis.get_solid_topology_counts is bom_assembly_analysis.get_solid_topology_counts
    assert assembly_analysis._get_solid_surface_area is bom_assembly_analysis._get_solid_surface_area
    assert assembly_analysis._is_plate_by_face_analysis is bom_assembly_analysis._is_plate_by_face_analysis


def test_classification_step0_reuses_internal_metric_and_result_helpers():
    assert classification_core_step0._get_volume is classification_geometry_metrics._get_volume
    assert classification_core_step0._get_bbox_sorted is classification_geometry_metrics._get_bbox_sorted
    assert classification_core_step0._get_face_areas is classification_geometry_metrics._get_face_areas
    assert classification_core_step0._get_top2_face_percent is classification_geometry_metrics._get_top2_face_percent
    assert classification_core_step0._count_edges_and_large_radius is classification_geometry_metrics._count_edges_and_large_radius
    assert classification_core_step0._count_edges is classification_geometry_metrics._count_edges
    assert classification_core_step0._result is classification_result_types._result
    assert classification_core_step0._evaluate_round_shaft_axial_slice is classification_validation._evaluate_round_shaft_axial_slice
    assert classification_core_step0._step_0_1_slice_validation is classification_validation._step_0_1_slice_validation
    assert classification_core_step0._check_hollow_tube_consistency is classification_hollow_closed._check_hollow_tube_consistency
    assert classification_core_step0._step_0_2_hollow_closed is classification_hollow_closed._step_0_2_hollow_closed
