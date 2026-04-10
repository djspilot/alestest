"""Pytest smoke tests for XML export functionality."""

from pathlib import Path

from manufacturing_pipeline.reporting.xml_exporter import export_to_xml


def _sample_result() -> dict:
    """Minimal export payload compatible with export_to_xml()."""
    return {
        "file": "sample_part.stp",
        "category": "plaat",
        "part_type": "PLAAT",
        "thickness": 3.0,
        "dimensions": {
            "length": 120.0,
            "width": 80.0,
            "height": 3.0,
        },
        "production": {
            "bends_total": 2,
            "holes_total": 4,
        },
        "flat_dimensions": {
            "length": 125.0,
            "width": 82.0,
        },
        "aag_details": {
            "bend_details": [
                {"angle": 90.0, "radius": 2.0},
                {"angle": 45.0, "radius": 1.5},
            ],
            "hole_details": [
                {"type": "round", "diameter": 10.0, "perimeter": 31.4},
                {"type": "threaded", "diameter": 6.8, "perimeter": 21.4},
            ],
        },
    }


def test_xml_export_writes_file(tmp_path: Path) -> None:
    """XML export should generate a non-empty file for a minimal result payload."""
    output_path = tmp_path / "sample_part.xml"
    export_to_xml(_sample_result(), output_path)

    assert output_path.exists()
    assert output_path.stat().st_size > 0


def test_xml_export_contains_core_fields(tmp_path: Path) -> None:
    """Generated XML should include the core AutoPOL fields we rely on."""
    output_path = tmp_path / "sample_part.xml"
    export_to_xml(_sample_result(), output_path)
    xml = output_path.read_text(encoding="utf-8")

    assert "<Sheet_PartName>sample_part</Sheet_PartName>" in xml
    assert "<Sheet_Thickness>3</Sheet_Thickness>" in xml
    assert "<Sheet_NrBends>2</Sheet_NrBends>" in xml
    assert "<Sheet_NrHoles>4</Sheet_NrHoles>" in xml


def test_xml_export_prefers_semantic_sheet_hole_count_over_visual_fallback(tmp_path: Path) -> None:
    """Sheet XML must keep semantic hole totals authoritative when fallback visuals add extras."""
    output_path = tmp_path / "sample_part.xml"
    result = _sample_result()
    result["visuals"] = {
        "holes": {
            "items": [
                {"status": "accepted", "type": "cylindrical", "diameter": 10.0, "perimeter": 31.4},
                {"status": "accepted", "type": "cylindrical", "diameter": 6.8, "perimeter": 21.4},
                {"status": "accepted", "type": "closed_contour", "size": "12x8"},
                {"status": "accepted", "type": "irregular_contour", "label": "65"},
                {"status": "accepted", "type": "irregular_contour", "label": "65"},
            ]
        }
    }
    result["sheet_hole_semantics"] = {
        "nr_holes": 2,
        "threaded_holes": 1,
        "countersunk_holes": 0,
        "countersunk_angles": [],
    }

    export_to_xml(result, output_path)
    xml = output_path.read_text(encoding="utf-8")

    assert "<Sheet_NrHoles>2</Sheet_NrHoles>" in xml
    assert "<Sheet_ThreadedHoles>1</Sheet_ThreadedHoles>" in xml


def test_xml_export_assembly_preserves_quantity_for_unique_parts(tmp_path: Path) -> None:
    """Assembly export must keep occurrence count on unique analysed parts."""
    output_path = tmp_path / "assembly.xml"
    result = {
        "file": "assembly.stp",
        "is_assembly": True,
        "solid_count": 8,
        "unique_solid_count": 5,
        "parts": [
            {
                **_sample_result(),
                "file": "10040853_1_2.step",
                "solid_name": "10040853_1.2",
                "quantity": 2,
            },
            {
                **_sample_result(),
                "file": "10040876_1.step",
                "solid_name": "10040876_1",
                "quantity": 1,
            },
        ],
    }

    export_to_xml(result, output_path)
    xml = output_path.read_text(encoding="utf-8")

    assert xml.count("<CalculationResult>") == 2
    assert "<Sheet_Name>10040853_1.2</Sheet_Name>" in xml
    assert "<Sheet_Count>2</Sheet_Count>" in xml
    assert "<Sheet_Name>10040876_1</Sheet_Name>" in xml

