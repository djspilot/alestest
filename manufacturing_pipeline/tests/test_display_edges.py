"""Tests for clean display edge extraction used by the viewer."""

from manufacturing_pipeline.analysis.step_processing import extract_display_edges


def test_extract_display_edges_ignores_coplanar_diagonal():
    mesh = {
        "vertices": [
            0.0, 0.0, 0.0,
            10.0, 0.0, 0.0,
            10.0, 10.0, 0.0,
            0.0, 10.0, 0.0,
        ],
        "indices": [
            0, 1, 2,
            0, 2, 3,
        ],
    }

    edges = extract_display_edges(mesh, angle_threshold_deg=30.0, min_length_ratio=0.0)

    segments = {
        tuple(round(value, 3) for value in edges[index:index + 6])
        for index in range(0, len(edges), 6)
    }

    assert (0.0, 0.0, 0.0, 10.0, 10.0, 0.0) not in segments
    assert (10.0, 10.0, 0.0, 0.0, 0.0, 0.0) not in segments
    assert len(segments) == 4
