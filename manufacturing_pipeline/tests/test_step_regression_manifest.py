"""Manifest-driven smoke regression tests for local STEP samples."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from manufacturing_pipeline.analysis.assembly_analysis import classify_solid
from manufacturing_pipeline.analysis.part_analyzer import analyze_part_geometry
from manufacturing_pipeline.analysis.step_processing import load_step_file


ROOT_DIR = Path(__file__).resolve().parents[2]
MANIFEST_PATH = Path(__file__).with_name("step_regression_manifest.json")
MANIFEST = json.loads(MANIFEST_PATH.read_text())
pytestmark = [
    pytest.mark.filterwarnings("ignore:invalid value encountered in oriented_envelope:RuntimeWarning"),
    pytest.mark.filterwarnings("ignore:divide by zero encountered in oriented_envelope:RuntimeWarning"),
]


@pytest.mark.parametrize("case", MANIFEST, ids=[case["name"] for case in MANIFEST])
def test_step_regression_manifest(case: dict) -> None:
    step_path = ROOT_DIR / case["path"]
    if not step_path.exists():
        pytest.skip(f"STEP sample not available locally: {step_path}")

    shape = load_step_file(step_path)
    solid = shape.val().wrapped if hasattr(shape, "val") else shape.wrapped if hasattr(shape, "wrapped") else shape

    classify_result = classify_solid(solid, return_trace=True)
    classify_label = classify_result[0] if isinstance(classify_result, tuple) else classify_result
    part_analysis = analyze_part_geometry(shape, step_path.stem)

    expected = case["expected"]
    assert classify_label == expected["classify_solid"]
    assert part_analysis.part_type.value == expected["part_type"]
    assert part_analysis.total_hole_count == expected["hole_count"]
    assert part_analysis.bend_count_erp == expected["bend_count_erp"]
