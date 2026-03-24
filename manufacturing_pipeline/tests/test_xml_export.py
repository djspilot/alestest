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
