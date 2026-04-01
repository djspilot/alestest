from manufacturing_pipeline.analysis.geometry import profile_sections as shared
from manufacturing_pipeline.analysis.io import step_file_io
from manufacturing_pipeline.analysis.features import hole_detection
from manufacturing_pipeline.analysis.features import cut_features_geometry_helpers
from manufacturing_pipeline.analysis.features import cut_features_extractors
from manufacturing_pipeline.analysis.features import component_reporting
from manufacturing_pipeline.analysis.features import cut_features_profile_helpers
from manufacturing_pipeline.analysis.features import manufacturing_orchestration
from manufacturing_pipeline.analysis.features import manufacturing_features
from manufacturing_pipeline.analysis.features import runtime_support
from manufacturing_pipeline.analysis.bom import assembly_analysis as bom_assembly_analysis
from manufacturing_pipeline.analysis.sheetmetal import orchestration as sheetmetal_orchestration
from manufacturing_pipeline.analysis.sheetmetal import freecad_environment
from manufacturing_pipeline.analysis.sheetmetal import freecad_geometry
from manufacturing_pipeline.analysis.sheetmetal import complete_analysis as sheetmetal_complete_analysis
from manufacturing_pipeline.analysis.sheetmetal import geometry_analysis as sheetmetal_geometry_analysis
from manufacturing_pipeline.analysis.sheetmetal import freecad_process
from manufacturing_pipeline.analysis.sheetmetal import standards as sheetmetal_standards
from manufacturing_pipeline.analysis.classification_core import step0 as classification_core_step0
from manufacturing_pipeline.analysis.classification_core import geometry_metrics as classification_geometry_metrics
from manufacturing_pipeline.analysis.classification_core import hollow_closed as classification_hollow_closed
from manufacturing_pipeline.analysis.classification_core import open_profile as classification_open_profile
from manufacturing_pipeline.analysis.classification_core import plate_rules as classification_plate_rules
from manufacturing_pipeline.analysis.classification_core import result_types as classification_result_types
from manufacturing_pipeline.analysis.classification_core import solid_profile_fallback as classification_solid_profile_fallback
from manufacturing_pipeline.analysis.classification_core import validation as classification_validation
from manufacturing_pipeline.analysis import assembly_analysis
from manufacturing_pipeline.analysis import classification
from manufacturing_pipeline.analysis import cut_features
from manufacturing_pipeline.analysis import freecad_unfold
from manufacturing_pipeline.analysis import profile_classifier
from manufacturing_pipeline.analysis import sheetmetal_analysis
from manufacturing_pipeline.analysis import step_processing
from manufacturing_pipeline.analysis import step0_section_tools


def test_step0_section_tools_reexports_shared_profile_geometry():
    assert step0_section_tools.AxisCandidate is shared.AxisCandidate
    assert step0_section_tools.Section2D is shared.Section2D
    assert step0_section_tools.ProfileRegistry is shared.ProfileRegistry
    assert step0_section_tools.normalize is shared.normalize
    assert step0_section_tools.normalize_section_polygon is shared.normalize_section_polygon
    assert step0_section_tools.match_templates is shared.match_templates
    assert step0_section_tools.make_round_bar is shared.make_round_bar
    assert step0_section_tools.make_pipe is shared.make_pipe
    assert step0_section_tools.make_flat_bar is shared.make_flat_bar
    assert step0_section_tools.make_rectangular_tube is shared.make_rectangular_tube
    assert step0_section_tools.make_i_section is shared.make_i_section
    assert step0_section_tools.make_u_section is shared.make_u_section
    assert step0_section_tools.make_l_section is shared.make_l_section
    assert step0_section_tools.make_t_section is shared.make_t_section


def test_profile_classifier_reexports_shared_profile_geometry():
    assert profile_classifier.AxisCandidate is shared.AxisCandidate
    assert profile_classifier.SectionFeatures is shared.SectionFeatures
    assert profile_classifier.ProfileRegistry is shared.ProfileRegistry
    assert profile_classifier.normalize is shared.normalize
    assert profile_classifier.extract_section_features is shared.extract_section_features
    assert profile_classifier.make_i_section is shared.make_i_section
    assert profile_classifier.make_round_bar is shared.make_round_bar
    assert profile_classifier.make_pipe is shared.make_pipe
    assert profile_classifier.make_flat_bar is shared.make_flat_bar
    assert profile_classifier.make_rectangular_tube is shared.make_rectangular_tube
    assert profile_classifier.make_u_section is shared.make_u_section
    assert profile_classifier.make_l_section is shared.make_l_section
    assert profile_classifier.make_t_section is shared.make_t_section
    assert profile_classifier.match_templates is shared.match_templates
    assert profile_classifier.TEMPLATE_BUILDERS["round_bar"] is shared.make_round_bar
    assert profile_classifier.TEMPLATE_BUILDERS["pipe"] is shared.make_pipe
    assert profile_classifier.TEMPLATE_BUILDERS["flat_bar"] is shared.make_flat_bar
    assert profile_classifier.TEMPLATE_BUILDERS["rect_tube"] is shared.make_rectangular_tube
    assert profile_classifier.TEMPLATE_BUILDERS["i_section"] is shared.make_i_section
    assert profile_classifier.TEMPLATE_BUILDERS["u_section"] is shared.make_u_section
    assert profile_classifier.TEMPLATE_BUILDERS["l_section"] is shared.make_l_section
    assert profile_classifier.TEMPLATE_BUILDERS["t_section"] is shared.make_t_section


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


def test_step_processing_reexports_internal_sheetmetal_and_manufacturing_helpers():
    assert callable(step_processing.analyze_sheet_metal)
    assert step_processing.detect_threads is not None
    assert step_processing.detect_shafts is not None
    assert step_processing.analyze_chamfers_and_fillets is not None


def test_step_processing_wrappers_pass_legacy_callbacks(monkeypatch):
    captured = {}

    def fake_sheetmetal(solid):
        captured["sheet_solid"] = solid
        return {"is_sheet_metal": False}

    def fake_detect_threads(cq_object, detect_holes_fn, iso_provider, tolerance=0.15):
        captured["thread_obj"] = cq_object
        captured["detect_holes_fn"] = detect_holes_fn
        captured["iso_provider"] = iso_provider
        captured["thread_tolerance"] = tolerance
        return ["ok"]

    def fake_detect_holes(_cq_object):
        return []

    monkeypatch.setattr(sheetmetal_orchestration, "analyze_sheet_metal", fake_sheetmetal)
    monkeypatch.setattr(manufacturing_features, "detect_threads", fake_detect_threads)
    monkeypatch.setattr(step_processing, "detect_holes", fake_detect_holes)

    assert step_processing.analyze_sheet_metal("solid") == {"is_sheet_metal": False}
    assert captured["sheet_solid"] == "solid"

    assert step_processing.detect_threads("shape", tolerance=0.2) == ["ok"]
    assert captured["thread_obj"] == "shape"
    assert captured["detect_holes_fn"] is fake_detect_holes
    assert captured["iso_provider"] is step_processing.iso_standards
    assert captured["thread_tolerance"] == 0.2


def test_step_processing_reexports_internal_manufacturing_orchestration():
    assert manufacturing_orchestration.analyze_manufacturing_requirements is not None
    assert manufacturing_orchestration.calculate_mass_properties is not None
    assert manufacturing_orchestration.analyze_holes_with_fits is not None
    assert manufacturing_orchestration.generate_manufacturing_summary is not None
    assert manufacturing_orchestration.generate_werkvoorbereiding is not None
    assert manufacturing_orchestration.analyze_sheetmetal is not None
    assert manufacturing_orchestration.analyze_assembly_bom is not None


def test_step_processing_reexports_runtime_support_shims():
    assert step_processing._IsoThreadMatch is runtime_support._IsoThreadMatch
    assert step_processing._IsoStandardsFallback is runtime_support._IsoStandardsFallback
    assert step_processing._WerkvoorbereidingFallback is runtime_support._WerkvoorbereidingFallback


def test_step_processing_reexports_internal_component_reporting():
    assert component_reporting._analyze_part_manufacturing is not None
    assert component_reporting.analyze_components_detailed is not None
    assert component_reporting.get_topology_stats is not None
    assert component_reporting.classify_components is not None
    assert component_reporting.get_geometric_properties is not None
    assert component_reporting.analyze_faces is not None
    assert component_reporting.debug_hole_detection is not None


def test_assembly_analysis_reexports_internal_bom_module():
    assert assembly_analysis.BOMItem is bom_assembly_analysis.BOMItem
    assert assembly_analysis.AssemblyAnalysis is bom_assembly_analysis.AssemblyAnalysis
    assert assembly_analysis.classify_solid is bom_assembly_analysis.classify_solid
    assert assembly_analysis.get_solid_topology_counts is bom_assembly_analysis.get_solid_topology_counts
    assert assembly_analysis._get_solid_surface_area is bom_assembly_analysis._get_solid_surface_area
    assert assembly_analysis._is_plate_by_face_analysis is bom_assembly_analysis._is_plate_by_face_analysis


def test_cut_features_reexports_profile_helper_ownership():
    assert cut_features._get_bounding_box is cut_features_profile_helpers._get_bounding_box
    assert cut_features._parse_dimensions_from_string is cut_features_profile_helpers._parse_dimensions_from_string


def test_cut_features_reexports_geometry_helper_ownership():
    assert cut_features._normalize_vector is cut_features_geometry_helpers._normalize_vector
    assert cut_features._as_point_tuple is cut_features_geometry_helpers._as_point_tuple
    assert cut_features._dot is cut_features_geometry_helpers._dot
    assert cut_features._distance_point_to_axis is cut_features_geometry_helpers._distance_point_to_axis
    assert cut_features._signed_axis_distance is cut_features_geometry_helpers._signed_axis_distance


def test_cut_features_public_extractors_remain_available():
    assert callable(cut_features.extract_cut_features_for_sheet)
    assert callable(cut_features.extract_cut_features_for_profile)


def test_cut_features_public_extractors_delegate_to_internal_extractors():
    assert cut_features_extractors.extract_cut_features_for_sheet is not None
    assert cut_features_extractors.extract_cut_features_for_profile is not None


def test_freecad_unfold_delegates_environment_probing():
    assert freecad_unfold._candidate_freecad_paths() == freecad_environment._candidate_freecad_paths()
    assert freecad_unfold._should_prefer_freecadcmd() == freecad_environment._should_prefer_freecadcmd()


def test_freecad_unfold_delegates_process_execution(monkeypatch):
    captured = {}

    def fake_find_freecadcmd():
        return "/tmp/freecadcmd"

    def fake_run_freecadcmd_script(executable, script, timeout_seconds=300):
        captured["executable"] = executable
        captured["timeout_seconds"] = timeout_seconds
        captured["script_has_payload"] = "run(" in script
        return {"success": True, "attempts": 1, "error_details": []}

    monkeypatch.setattr(freecad_unfold, "_find_freecadcmd_executable", fake_find_freecadcmd)
    monkeypatch.setattr(freecad_process, "run_freecadcmd_script", fake_run_freecadcmd_script)

    result = freecad_unfold._unfold_via_freecadcmd("demo.step")
    assert result["success"] is True
    assert captured["executable"] == "/tmp/freecadcmd"
    assert captured["timeout_seconds"] == 300
    assert captured["script_has_payload"] is True


def test_freecad_unfold_delegates_geometry_helpers(monkeypatch):
    captured = {}

    def fake_vector_components(value):
        captured["vector"] = value
        return (1.0, 2.0, 3.0)

    def fake_measure_flat_pattern_dimensions(shape):
        captured["flat_shape"] = shape
        return {"flat_length": 100.0, "flat_width": 50.0}

    monkeypatch.setattr(freecad_geometry, "_vector_components", fake_vector_components)
    monkeypatch.setattr(
        freecad_geometry,
        "_measure_flat_pattern_dimensions",
        fake_measure_flat_pattern_dimensions,
    )

    assert freecad_unfold._vector_components("point") == (1.0, 2.0, 3.0)
    assert captured["vector"] == "point"

    dims = freecad_unfold._measure_flat_pattern_dimensions("flat-shape")
    assert dims == {"flat_length": 100.0, "flat_width": 50.0}
    assert captured["flat_shape"] == "flat-shape"


def test_merge_bends_by_collinear_segments_merges_hole_interrupted_lines():
    bend_angles = [90.0, 90.0, -90.0, -90.0]
    bend_radii = [1.0, 1.0, 1.0, 1.0]
    bend_lengths = [40.0, 35.0, 42.0, 38.0]
    segments = [
        {"index": 0, "axis": "X", "line_offset": 10.0, "axis_span": [0.0, 40.0], "pos_along_length": -50.0},
        {"index": 1, "axis": "X", "line_offset": 10.2, "axis_span": [190.0, 225.0], "pos_along_length": -48.0},
        {"index": 2, "axis": "X", "line_offset": 90.0, "axis_span": [5.0, 47.0], "pos_along_length": 48.0},
        {"index": 3, "axis": "X", "line_offset": 89.8, "axis_span": [205.0, 243.0], "pos_along_length": 50.0},
    ]

    merged_angles, merged_radii, merged_lengths, merged_groups = freecad_unfold._merge_bends_by_collinear_segments(
        bend_angles,
        bend_radii,
        bend_lengths,
        segments,
    )

    assert merged_angles == [90.0, -90.0]
    assert merged_radii == [1.0, 1.0]
    assert merged_lengths == [75.0, 80.0]
    assert len(merged_groups) == 2
    assert merged_groups[0]["segment_indices"] == [0, 1]
    assert merged_groups[1]["segment_indices"] == [2, 3]


def test_sheetmetal_analysis_reexports_internal_standards():
    assert sheetmetal_analysis.STANDARD_THICKNESSES is sheetmetal_standards.STANDARD_THICKNESSES
    assert sheetmetal_analysis.STANDARD_BEND_ANGLES is sheetmetal_standards.STANDARD_BEND_ANGLES
    assert sheetmetal_analysis.BendTool is sheetmetal_standards.BendTool
    assert sheetmetal_analysis.STANDARD_V_DIES is sheetmetal_standards.STANDARD_V_DIES
    assert sheetmetal_analysis.K_FACTORS is sheetmetal_standards.K_FACTORS
    assert sheetmetal_analysis.MATERIAL_BEND_PROPERTIES is sheetmetal_standards.MATERIAL_BEND_PROPERTIES
    assert sheetmetal_analysis.BendSequenceOptimizer is sheetmetal_standards.BendSequenceOptimizer
    assert sheetmetal_analysis.calculate_bend_allowance is sheetmetal_standards.calculate_bend_allowance
    assert sheetmetal_analysis.calculate_bend_deduction is sheetmetal_standards.calculate_bend_deduction
    assert sheetmetal_analysis.calculate_flat_length is sheetmetal_standards.calculate_flat_length
    assert sheetmetal_analysis.get_minimum_bend_radius is sheetmetal_standards.get_minimum_bend_radius
    assert sheetmetal_analysis.recommend_v_opening is sheetmetal_standards.recommend_v_opening
    assert sheetmetal_analysis.calculate_bend_force is sheetmetal_standards.calculate_bend_force
    assert sheetmetal_analysis.calculate_complete_flat_pattern is sheetmetal_standards.calculate_complete_flat_pattern


def test_sheetmetal_analysis_reexports_internal_geometry_analysis():
    assert sheetmetal_analysis.HAS_OCP is sheetmetal_geometry_analysis.HAS_OCP
    assert sheetmetal_analysis.DetectedBend is sheetmetal_geometry_analysis.DetectedBend
    assert sheetmetal_analysis.analyze_sheet_metal_geometry is sheetmetal_geometry_analysis.analyze_sheet_metal_geometry


def test_sheetmetal_analysis_reexports_internal_complete_analysis():
    assert sheetmetal_analysis.analyze_sheetmetal_complete is sheetmetal_complete_analysis.analyze_sheetmetal_complete
    assert sheetmetal_analysis._recommend_machine is sheetmetal_complete_analysis._recommend_machine


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
    assert classification_core_step0._step_0_3_open_profile is classification_open_profile._step_0_3_open_profile
    assert classification_core_step0._step_0_4a_flat_plate is classification_plate_rules._step_0_4a_flat_plate
    assert classification_core_step0._select_step_0_4b_features is classification_plate_rules._select_step_0_4b_features
    assert (
        classification_core_step0._step_0_4b_constant_thickness_open
        is classification_plate_rules._step_0_4b_constant_thickness_open
    )
    assert (
        classification_core_step0._step_0_5_solid_profile_fallback
        is classification_solid_profile_fallback._step_0_5_solid_profile_fallback
    )
