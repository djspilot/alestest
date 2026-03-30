from unittest.mock import patch

from manufacturing_pipeline.analysis import step_processing


def test_detect_holes_wrapper_injects_turned_part_detector():
    sentinel = object()

    with patch("manufacturing_pipeline.analysis.features.hole_detection.detect_holes", return_value=sentinel) as detect_holes_mock:
        result = step_processing.detect_holes("shape")

    assert result is sentinel
    _, kwargs = detect_holes_mock.call_args
    assert kwargs["turned_part_detector"] is step_processing.is_turned_part
