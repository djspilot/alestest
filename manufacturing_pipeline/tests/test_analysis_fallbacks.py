"""Tests voor graceful degradation in de analysis service.

Verifieert dat de pipeline correct terugvalt als:
- FreeCAD niet beschikbaar is (VPS lite mode)
- Unfold mislukt
- Een STEP file corrupt is
- Analysemodules ontbreken of crashen
"""

import os
import pytest
from types import SimpleNamespace
from unittest.mock import patch, MagicMock
from pathlib import Path


# ---------------------------------------------------------------------------
# Analysis service: unfold uitgeschakeld
# ---------------------------------------------------------------------------

class TestAnalysisServiceUnfoldDisabled:
    def test_run_step_analysis_with_unfold_disabled_does_not_call_freecad(self):
        """Als unfold in disable_stages zit, mag FreeCAD nooit aangeroepen worden."""
        from manufacturing_pipeline.api.analysis_service import run_step_analysis

        with patch("manufacturing_pipeline.core.runtime_unfold.run_unfold_to_step") as mock_unfold:
            result = run_step_analysis(
                "/nonexistent/path.step",
                use_aag=False,
                disable_stages={"unfold"},
            )
            mock_unfold.assert_not_called()

    def test_run_step_analysis_returns_dict_on_failure(self):
        """Bij een niet-bestaand bestand moet een dict teruggegeven worden, geen exception."""
        from manufacturing_pipeline.api.analysis_service import run_step_analysis

        result = run_step_analysis("/nonexistent/does_not_exist.step")
        assert isinstance(result, dict)
        assert "file" in result
        assert "success" in result

    def test_run_step_analysis_failure_has_error_key(self):
        """Een mislukte analyse moet 'success': False en 'error' bevatten."""
        from manufacturing_pipeline.api.analysis_service import run_step_analysis

        result = run_step_analysis("/nonexistent/does_not_exist.step")
        assert result["success"] is False
        assert "error" in result
        assert result["error"]  # error mag niet leeg zijn

    def test_run_step_analysis_file_key_is_basename(self):
        """'file' in het resultaat moet de bestandsnaam zijn, niet het volledige pad."""
        from manufacturing_pipeline.api.analysis_service import run_step_analysis

        result = run_step_analysis("/some/deep/path/mypart.step")
        assert result["file"] == "mypart.step"


# ---------------------------------------------------------------------------
# FreeCAD auto-install: uitgeschakeld in lite mode
# ---------------------------------------------------------------------------

class TestFreeCADAutoInstall:
    def test_auto_install_disabled_when_env_set(self):
        from manufacturing_pipeline.core import freecad_runtime
        with patch.dict(os.environ, {"FREECAD_AUTO_INSTALL": "0"}):
            assert freecad_runtime.auto_install_enabled() is False

    def test_auto_install_enabled_by_default(self):
        from manufacturing_pipeline.core import freecad_runtime
        env = os.environ.copy()
        env.pop("FREECAD_AUTO_INSTALL", None)
        with patch.dict(os.environ, env, clear=True):
            assert freecad_runtime.auto_install_enabled() is True

    def test_auto_install_disabled_with_false_string(self):
        from manufacturing_pipeline.core import freecad_runtime
        with patch.dict(os.environ, {"FREECAD_AUTO_INSTALL": "false"}):
            assert freecad_runtime.auto_install_enabled() is False

    def test_auto_install_disabled_with_zero(self):
        from manufacturing_pipeline.core import freecad_runtime
        with patch.dict(os.environ, {"FREECAD_AUTO_INSTALL": "0"}):
            assert freecad_runtime.auto_install_enabled() is False


# ---------------------------------------------------------------------------
# Unfold integration: fallback gedrag
# ---------------------------------------------------------------------------

class TestUnfoldFallbacks:
    def test_unfold_failure_result_is_dict(self):
        """run_unfold_to_step mag nooit een exception gooien, altijd een dict teruggeven."""
        from manufacturing_pipeline.core import runtime_unfold

        with patch.object(runtime_unfold, "_run_direct_unfold_attempt",
                          return_value={"success": False, "error": "FreeCAD niet beschikbaar"}), \
             patch.object(runtime_unfold, "_run_direct_python_worker_attempt",
                          return_value={"success": False, "error": "Geen python runtime"}), \
             patch.object(runtime_unfold, "_run_unfold_subprocess_attempt",
                          return_value={"success": False, "error": "Subprocess gefaald"}):

            result = runtime_unfold.run_unfold_to_step(
                "/nonexistent.step", "/tmp", "test", analysis=None
            )
            assert isinstance(result, dict)

    def test_unfold_failure_has_success_false(self):
        from manufacturing_pipeline.core import runtime_unfold

        with patch.object(runtime_unfold, "_run_direct_unfold_attempt",
                          return_value={"success": False, "error": "FreeCAD niet beschikbaar"}), \
             patch.object(runtime_unfold, "_run_direct_python_worker_attempt",
                          return_value={"success": False, "error": "geen runtime"}), \
             patch.object(runtime_unfold, "_run_unfold_subprocess_attempt",
                          return_value={"success": False, "error": "gefaald"}):

            result = runtime_unfold.run_unfold_to_step(
                "/nonexistent.step", "/tmp", "test", analysis=None
            )
            assert result.get("success") is False

    def test_summarize_unfold_failure_with_none(self):
        from manufacturing_pipeline.core.runtime_unfold import _summarize_unfold_failure
        result = _summarize_unfold_failure(None)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_summarize_unfold_failure_with_error(self):
        from manufacturing_pipeline.core.runtime_unfold import _summarize_unfold_failure
        result = _summarize_unfold_failure({"error": "FreeCAD niet gevonden", "attempts": 1})
        assert "FreeCAD" in result

    def test_summarize_unfold_failure_with_error_details(self):
        from manufacturing_pipeline.core.runtime_unfold import _summarize_unfold_failure
        result = _summarize_unfold_failure({
            "error": None,
            "attempts": 3,
            "error_details": [
                {"stage": "init", "error_code": 1, "message": "Volume onbruikbaar"},
                {"stage": "analysis", "error_code": 3, "message": "Dikte inconsistent"},
            ]
        })
        assert isinstance(result, str)
        assert len(result) > 0


# ---------------------------------------------------------------------------
# Analysis service: mesh en tessellatie zijn optioneel
# ---------------------------------------------------------------------------

class TestMeshFallback:
    def test_missing_mesh_does_not_break_result(self):
        """Als tessellatie faalt, mag 'mesh' gewoon ontbreken — geen crash."""
        from manufacturing_pipeline.api import analysis_service

        mock_analysis = MagicMock()
        mock_analysis.part_category = "PLAAT"
        mock_analysis.part_type = None
        mock_analysis.thickness = 2.0
        mock_analysis.length = 100.0
        mock_analysis.width = 50.0
        mock_analysis.height = 2.0
        mock_analysis.flat_length = 0
        mock_analysis.flat_width = 0
        mock_analysis.bend_count_erp = 0
        mock_analysis.aag_result = None
        mock_analysis.route_result = None
        mock_analysis.unfold_result = None
        mock_analysis.reasoning = []
        mock_analysis.classification_visuals = None
        mock_analysis.classification_trace = {}
        mock_analysis.classification_criteria = []
        mock_analysis.detected_hole_visuals = None
        mock_analysis.detected_hole_visuals_pre_unfold = None

        import manufacturing_pipeline.analysis.step_processing as sp

        mock_shape = MagicMock()

        with patch("manufacturing_pipeline.api.analysis_service.run_analysis",
                   return_value=(mock_analysis, 0)), \
             patch("manufacturing_pipeline.api.analysis_service.get_output_dir",
                   return_value=("/tmp/test_out", "test")), \
             patch("manufacturing_pipeline.api.analysis_service._load_timing_json",
                   return_value=None), \
             patch.object(sp, "load_step_file", return_value=mock_shape), \
             patch.object(sp, "tessellate_shape",
                          side_effect=RuntimeError("tessellatie gefaald")):

            result = analysis_service.run_step_analysis(
                "/fake/test.step", use_aag=False, disable_stages={"unfold", "aag"}
            )

        # Analyse moet slagen ook zonder mesh
        assert result.get("success") is True
        # mesh is optioneel
        assert "mesh" not in result or result["mesh"] is None

    def test_run_step_analysis_groups_duplicate_solid_names_once(self):
        from manufacturing_pipeline.api import analysis_service

        assembly_step = "/fake/assembly.step"
        split_dir = "/fake/split"
        split_items = [
            {"name": "Part A", "path": f"{split_dir}/Part_A.step", "index": 0, "tmp_dir": split_dir},
            {"name": "Part B", "path": f"{split_dir}/Part_B.step", "index": 1, "tmp_dir": split_dir},
            {"name": "Part A", "path": f"{split_dir}/Part_A_002.step", "index": 2, "tmp_dir": split_dir},
            {"name": "Part B", "path": f"{split_dir}/Part_B_002.step", "index": 3, "tmp_dir": split_dir},
        ]

        def fake_extract(step_path):
            if step_path == assembly_step:
                return split_items
            return None

        def fake_get_output_dir(step_path):
            stem = Path(step_path).stem
            return (f"/tmp/{stem}", stem)

        mock_analysis = MagicMock()
        mock_analysis.part_category = "PLAAT"
        mock_analysis.part_type = None
        mock_analysis.thickness = 2.0
        mock_analysis.length = 100.0
        mock_analysis.width = 50.0
        mock_analysis.height = 2.0
        mock_analysis.flat_length = 0
        mock_analysis.flat_width = 0
        mock_analysis.bend_count_erp = 0
        mock_analysis.aag_result = None
        mock_analysis.route_result = None
        mock_analysis.unfold_result = None
        mock_analysis.reasoning = []
        mock_analysis.classification_visuals = None
        mock_analysis.classification_trace = {}
        mock_analysis.classification_criteria = []
        mock_analysis.detected_hole_visuals = None
        mock_analysis.detected_hole_visuals_pre_unfold = None

        with patch.object(analysis_service, "extract_solids_to_temp_files", side_effect=fake_extract), \
             patch.object(analysis_service, "get_output_dir", side_effect=fake_get_output_dir), \
             patch.object(analysis_service, "run_analysis", return_value=(mock_analysis, 0)), \
             patch.object(analysis_service, "_load_timing_json", return_value=None), \
             patch("shutil.rmtree"):
            result = analysis_service.run_step_analysis(assembly_step, use_aag=False, disable_stages={"unfold", "aag"})

        assert result["success"] is True
        assert result["is_assembly"] is True
        assert result["solid_count"] == 4
        assert result["unique_solid_count"] == 2
        assert len(result["parts"]) == 2
        assert [part["solid_name"] for part in result["parts"]] == ["Part A", "Part B"]
        assert [part["quantity"] for part in result["parts"]] == [2, 2]
        assert result["parts"][0]["occurrence_indices"] == [0, 2]
        assert result["parts"][1]["occurrence_indices"] == [1, 3]
        assert result["parts"][0]["solid_index"] == 0
        assert result["parts"][1]["solid_index"] == 1
        assert result["parts"][1]["representative_occurrence_index"] == 1

    def test_format_analysis_report_handles_missing_part_type(self):
        from manufacturing_pipeline.analysis.part_analyzer import format_analysis_report

        analysis = SimpleNamespace(
            name="test.step",
            part_type=None,
            is_sheet_metal=False,
            is_profile=False,
            is_turned=False,
            length=100.0,
            width=50.0,
            height=10.0,
            thickness=2.0,
            bend_count_erp=0,
            total_hole_count=0,
            max_hole_diameter=0.0,
            can_unfold=False,
            unfold_reason="n/a",
            flat_length=0.0,
            flat_width=0.0,
            reasoning=[],
            bends=[],
            holes=[],
        )

        report = format_analysis_report(analysis)

        assert "Type:           UNKNOWN" in report

    def test_format_bend_type_label_handles_none(self):
        from manufacturing_pipeline.core.runtime_analysis import _format_bend_type_label

        assert _format_bend_type_label(None) == "?"
        assert _format_bend_type_label("up") == "UP"


# ---------------------------------------------------------------------------
# Config: FREECAD_RUNTIME_ROOT env var
# ---------------------------------------------------------------------------

class TestFreeCADRuntimeConfig:
    def test_managed_runtime_root_uses_env_var(self):
        from manufacturing_pipeline.core import freecad_runtime
        with patch.dict(os.environ, {"FREECAD_RUNTIME_ROOT": "/custom/freecad"}):
            root = freecad_runtime.managed_runtime_root()
            assert root == "/custom/freecad"

    def test_managed_runtime_root_fallback_to_project(self):
        from manufacturing_pipeline.core import freecad_runtime
        env = os.environ.copy()
        env.pop("FREECAD_RUNTIME_ROOT", None)
        with patch.dict(os.environ, env, clear=True):
            root = freecad_runtime.managed_runtime_root()
            assert ".runtime" in root
            assert "freecad" in root
