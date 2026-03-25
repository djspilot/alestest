"""Unit tests for generic closed-contour hole classification."""

from manufacturing_pipeline.analysis.step_processing import _classify_shaped_inner_wire


def test_classify_unknown_inner_wire_as_closed_contour() -> None:
    """Non-standard inner wires should still classify as generic closed contours."""

    shape_type, dim_str, family = _classify_shaped_inner_wire(
        edge_count=5,
        lines=1,
        circles=1,
        radii=[3.2],
        lengths=[12.4],
        bbox_dims=(23.7, 14.7, 0.0),
    )

    assert shape_type == "Closed contour"
    assert dim_str == "23.7x14.7"
    assert family == "closed_contour"


def test_classify_standard_slot_still_wins_over_closed_contour() -> None:
    """Known slot signatures should keep their explicit classification."""

    shape_type, dim_str, family = _classify_shaped_inner_wire(
        edge_count=4,
        lines=2,
        circles=2,
        radii=[4.0, 4.0],
        lengths=[18.0, 18.0],
        bbox_dims=(26.0, 8.0, 0.0),
    )

    assert shape_type == "Slot"
    assert dim_str == "26.0x8.0"
    assert family == "slot_like"
