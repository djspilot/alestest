"""Unit tests for geometry/profile_sections.py — pure 2D geometry functions.

Tests all functions that depend only on numpy + shapely (no OCP):
  - normalize, unique_rows_rounded
  - orthonormal_basis_from_normal, project_points_to_plane
  - polygon_signed_area, simplify_relative
  - normalize_section_polygon, section_distance
  - count_reentrant_corners, reflect_polygon_about_axis
  - symmetry_score, detect_symmetry_axes
  - extract_section_features
  - Template factories (make_round_bar, make_pipe, etc.)
  - ProfileRegistry, match_templates
"""
import math

import numpy as np
import pytest
from shapely.geometry import MultiPolygon, Point, Polygon

from manufacturing_pipeline.analysis.geometry.profile_sections import (
    AxisCandidate,
    ProfileRegistry,
    ProfileTemplate,
    Section2D,
    SectionFeatures,
    TemplateMatch,
    count_reentrant_corners,
    detect_symmetry_axes,
    extract_section_features,
    make_flat_bar,
    make_i_section,
    make_l_section,
    make_pipe,
    make_rectangular_tube,
    make_round_bar,
    make_t_section,
    make_u_section,
    match_templates,
    normalize,
    normalize_section_polygon,
    orthonormal_basis_from_normal,
    polygon_signed_area,
    project_points_to_plane,
    reflect_polygon_about_axis,
    section_distance,
    simplify_relative,
    symmetry_score,
    unique_rows_rounded,
)


# ===================================================================
# normalize
# ===================================================================


class TestNormalize:
    def test_unit_vector_unchanged(self):
        result = normalize([1.0, 0.0, 0.0])
        np.testing.assert_allclose(result, [1, 0, 0], atol=1e-12)

    def test_scales_to_unit(self):
        result = normalize([3.0, 4.0, 0.0])
        np.testing.assert_allclose(result, [0.6, 0.8, 0.0], atol=1e-12)

    def test_zero_raises(self):
        with pytest.raises(ValueError, match="near-zero"):
            normalize([0.0, 0.0, 0.0])

    def test_preserves_direction(self):
        v = [2.0, -3.0, 5.0]
        result = normalize(v)
        assert float(np.dot(result, normalize(v))) == pytest.approx(1.0, abs=1e-10)

    def test_unit_length(self):
        result = normalize([1.0, 2.0, 3.0])
        assert float(np.linalg.norm(result)) == pytest.approx(1.0, abs=1e-12)


# ===================================================================
# unique_rows_rounded
# ===================================================================


class TestUniqueRowsRounded:
    def test_empty(self):
        arr = np.array([]).reshape(0, 2)
        result = unique_rows_rounded(arr)
        assert len(result) == 0

    def test_removes_duplicates(self):
        arr = np.array([[1.0, 2.0], [1.0, 2.0], [3.0, 4.0]])
        result = unique_rows_rounded(arr)
        assert len(result) == 2

    def test_preserves_order(self):
        arr = np.array([[3.0, 4.0], [1.0, 2.0], [3.0, 4.0]])
        result = unique_rows_rounded(arr)
        assert result[0, 0] == pytest.approx(3.0)
        assert result[1, 0] == pytest.approx(1.0)

    def test_near_duplicates_kept(self):
        """Points within tolerance should be deduplicated."""
        arr = np.array([[1.0, 2.0], [1.0 + 1e-9, 2.0]])
        result = unique_rows_rounded(arr, tol=1e-8)
        assert len(result) == 1


# ===================================================================
# orthonormal_basis_from_normal
# ===================================================================


class TestOrthonormalBasis:
    def test_z_normal(self):
        n, u, v = orthonormal_basis_from_normal([0, 0, 1])
        np.testing.assert_allclose(n, [0, 0, 1], atol=1e-10)
        assert float(np.dot(u, v)) == pytest.approx(0.0, abs=1e-10)
        assert float(np.dot(n, u)) == pytest.approx(0.0, abs=1e-10)

    def test_x_normal(self):
        n, u, v = orthonormal_basis_from_normal([1, 0, 0])
        np.testing.assert_allclose(n, [1, 0, 0], atol=1e-10)
        assert float(np.dot(u, v)) == pytest.approx(0.0, abs=1e-10)

    def test_arbitrary_direction(self):
        n, u, v = orthonormal_basis_from_normal([1, 2, 3])
        assert float(np.linalg.norm(n)) == pytest.approx(1.0, abs=1e-10)
        assert float(np.linalg.norm(u)) == pytest.approx(1.0, abs=1e-10)
        assert float(np.linalg.norm(v)) == pytest.approx(1.0, abs=1e-10)

    def test_right_handed(self):
        n, u, v = orthonormal_basis_from_normal([0.5, -0.3, 0.8])
        cross = np.cross(u, v)
        # u×v should be parallel to n
        assert float(np.dot(cross, n)) == pytest.approx(1.0, abs=1e-8)


# ===================================================================
# project_points_to_plane
# ===================================================================


class TestProjectPointsToPlane:
    def test_xy_plane(self):
        pts = np.array([[1, 2, 0], [3, 4, 0]], dtype=float)
        origin = np.zeros(3)
        u = np.array([1.0, 0.0, 0.0])
        v = np.array([0.0, 1.0, 0.0])
        result = project_points_to_plane(pts, origin, u, v)
        np.testing.assert_allclose(result, [[1, 2], [3, 4]], atol=1e-10)

    def test_offset_origin(self):
        pts = np.array([[2, 3, 0]], dtype=float)
        origin = np.array([1, 1, 0], dtype=float)
        u = np.array([1.0, 0.0, 0.0])
        v = np.array([0.0, 1.0, 0.0])
        result = project_points_to_plane(pts, origin, u, v)
        np.testing.assert_allclose(result, [[1, 2]], atol=1e-10)

    def test_output_shape(self):
        pts = np.random.randn(10, 3)
        origin = np.zeros(3)
        n, u, v = orthonormal_basis_from_normal([1, 2, 3])
        result = project_points_to_plane(pts, origin, u, v)
        assert result.shape == (10, 2)


# ===================================================================
# polygon_signed_area
# ===================================================================


class TestPolygonSignedArea:
    def test_unit_square_ccw(self):
        coords = np.array([[0, 0], [1, 0], [1, 1], [0, 1]])
        assert polygon_signed_area(coords) == pytest.approx(1.0)

    def test_unit_square_cw(self):
        coords = np.array([[0, 0], [0, 1], [1, 1], [1, 0]])
        assert polygon_signed_area(coords) == pytest.approx(-1.0)

    def test_triangle(self):
        coords = np.array([[0, 0], [2, 0], [0, 2]])
        assert polygon_signed_area(coords) == pytest.approx(2.0)

    def test_degenerate_line(self):
        coords = np.array([[0, 0], [1, 0], [2, 0]])
        assert polygon_signed_area(coords) == pytest.approx(0.0)


# ===================================================================
# simplify_relative
# ===================================================================


class TestSimplifyRelative:
    def test_empty_polygon(self):
        result = simplify_relative(Polygon())
        assert result.is_empty

    def test_simple_polygon_unchanged(self):
        poly = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
        result = simplify_relative(poly)
        assert result.area == pytest.approx(1.0, abs=0.01)

    def test_reduces_vertices(self):
        # Circle approximation has many vertices
        circle = Point(0, 0).buffer(1.0, resolution=64)
        simplified = simplify_relative(circle)
        assert len(simplified.exterior.coords) < len(circle.exterior.coords)


# ===================================================================
# normalize_section_polygon
# ===================================================================


class TestNormalizeSectionPolygon:
    def test_unit_area(self):
        poly = Polygon([(0, 0), (2, 0), (2, 1), (0, 1)])
        result = normalize_section_polygon(poly)
        assert result.area == pytest.approx(1.0, abs=0.01)

    def test_centered_at_origin(self):
        poly = Polygon([(5, 5), (6, 5), (6, 6), (5, 6)])
        result = normalize_section_polygon(poly)
        cx, cy = result.centroid.x, result.centroid.y
        assert abs(cx) < 0.01
        assert abs(cy) < 0.01

    def test_handles_multipolygon(self):
        mp = MultiPolygon([
            Polygon([(0, 0), (1, 0), (1, 1), (0, 1)]),
            Polygon([(2, 0), (3, 0), (3, 1), (2, 1)]),
        ])
        # Should pick the first/largest
        result = normalize_section_polygon(mp)
        assert isinstance(result, Polygon)
        assert result.area == pytest.approx(1.0, abs=0.01)

    def test_invalid_polygon_fixed(self):
        """Bowtie polygon should be fixed by buffer(0)."""
        coords = [(0, 0), (2, 2), (2, 0), (0, 2)]
        poly = Polygon(coords)
        result = normalize_section_polygon(poly)
        assert result.is_valid


# ===================================================================
# section_distance
# ===================================================================


class TestSectionDistance:
    def test_identical_polygons_zero(self):
        poly = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
        d = section_distance(poly, poly)
        assert d == pytest.approx(0.0, abs=0.01)

    def test_different_shapes_positive(self):
        """Two differently shaped polygons (square vs triangle) should have positive distance."""
        a = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
        b = Polygon([(0, 0), (1, 0), (0.5, 1)])
        d = section_distance(a, b)
        assert d > 0

    def test_same_shape_same_size_zero(self):
        """Two identical squares (different position) normalize to the same shape."""
        a = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
        b = Polygon([(5, 5), (6, 5), (6, 6), (5, 6)])
        d = section_distance(a, b)
        assert d == pytest.approx(0.0, abs=0.05)

    def test_symmetric(self):
        a = make_i_section()
        b = make_u_section()
        assert section_distance(a, b) == pytest.approx(section_distance(b, a), abs=1e-10)


# ===================================================================
# count_reentrant_corners
# ===================================================================


class TestCountReentrantCorners:
    def test_convex_square_zero(self):
        poly = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
        assert count_reentrant_corners(poly) == 0

    def test_l_shape_has_reentrant(self):
        """L-shape has exactly 1 reentrant corner."""
        poly = Polygon([(0, 0), (2, 0), (2, 0.5), (0.5, 0.5), (0.5, 2), (0, 2)])
        count = count_reentrant_corners(poly)
        assert count >= 1

    def test_triangle_zero(self):
        poly = Polygon([(0, 0), (1, 0), (0.5, 1)])
        assert count_reentrant_corners(poly) == 0


# ===================================================================
# reflect_polygon_about_axis / symmetry_score
# ===================================================================


class TestReflectPolygon:
    def test_circle_reflection_unchanged(self):
        circle = Point(0, 0).buffer(1.0, resolution=64)
        reflected = reflect_polygon_about_axis(circle, 0.0)
        assert reflected.area == pytest.approx(circle.area, rel=0.01)


class TestSymmetryScore:
    def test_circle_perfect_symmetry(self):
        circle = normalize_section_polygon(Point(0, 0).buffer(1.0, resolution=64))
        score = symmetry_score(circle, 0.0)
        assert score > 0.95

    def test_rectangle_symmetry_at_0_and_90(self):
        rect = normalize_section_polygon(Polygon([(0, 0), (2, 0), (2, 1), (0, 1)]))
        score_0 = symmetry_score(rect, 0.0)
        score_90 = symmetry_score(rect, 90.0)
        assert score_0 > 0.95
        assert score_90 > 0.95

    def test_asymmetric_shape_low_score(self):
        """A very asymmetric polygon should score low on most axes."""
        poly = normalize_section_polygon(Polygon([(0, 0), (3, 0), (3, 0.1), (0, 1)]))
        score = symmetry_score(poly, 45.0)
        assert score < 0.9


# ===================================================================
# detect_symmetry_axes
# ===================================================================


class TestDetectSymmetryAxes:
    def test_circle_returns_axes(self):
        circle = normalize_section_polygon(Point(0, 0).buffer(1.0, resolution=64))
        angles, scores = detect_symmetry_axes(circle)
        assert len(angles) > 0
        assert all(s > 0.9 for s in scores)

    def test_rectangle_returns_two_axes(self):
        rect = normalize_section_polygon(Polygon([(0, 0), (2, 0), (2, 1), (0, 1)]))
        angles, scores = detect_symmetry_axes(rect)
        assert len(angles) >= 2


# ===================================================================
# Template factories
# ===================================================================


class TestMakeRoundBar:
    def test_area_normalized(self):
        poly = make_round_bar()
        assert poly.area == pytest.approx(1.0, abs=0.02)

    def test_centered(self):
        poly = make_round_bar()
        assert abs(poly.centroid.x) < 0.01
        assert abs(poly.centroid.y) < 0.01


class TestMakePipe:
    def test_has_hole(self):
        poly = make_pipe()
        assert len(poly.interiors) >= 1

    def test_area_normalized(self):
        poly = make_pipe()
        assert poly.area == pytest.approx(1.0, abs=0.05)


class TestMakeFlatBar:
    def test_area_normalized(self):
        poly = make_flat_bar()
        assert poly.area == pytest.approx(1.0, abs=0.02)

    def test_no_holes(self):
        assert len(make_flat_bar().interiors) == 0


class TestMakeRectangularTube:
    def test_has_hole(self):
        poly = make_rectangular_tube()
        assert len(poly.interiors) >= 1

    def test_area_normalized(self):
        poly = make_rectangular_tube()
        assert poly.area == pytest.approx(1.0, abs=0.05)


class TestMakeISection:
    def test_valid_polygon(self):
        poly = make_i_section()
        assert poly.is_valid
        assert poly.area > 0

    def test_area_normalized(self):
        poly = make_i_section()
        assert poly.area == pytest.approx(1.0, abs=0.05)


class TestMakeUSection:
    def test_valid_polygon(self):
        poly = make_u_section()
        assert poly.is_valid
        assert poly.area > 0

    def test_has_reentrant_corners(self):
        poly = make_u_section()
        count = count_reentrant_corners(poly)
        assert count >= 1  # U-shape has reentrant corners


class TestMakeLSection:
    def test_valid_polygon(self):
        poly = make_l_section()
        assert poly.is_valid
        assert poly.area > 0

    def test_has_reentrant_corner(self):
        poly = make_l_section()
        assert count_reentrant_corners(poly) >= 1


class TestMakeTSection:
    def test_valid_polygon(self):
        poly = make_t_section()
        assert poly.is_valid
        assert poly.area > 0


# ===================================================================
# ProfileRegistry
# ===================================================================


class TestProfileRegistry:
    def test_empty_registry(self):
        reg = ProfileRegistry()
        assert len(reg.templates) == 0

    def test_add_template(self):
        reg = ProfileRegistry()
        reg.add("TEST", "test-v1", make_round_bar())
        assert len(reg.templates) == 1
        assert reg.templates[0].family == "TEST"

    def test_extend_generic_defaults_populates(self):
        reg = ProfileRegistry().extend_generic_defaults()
        families = {t.family for t in reg.templates}
        assert "ROUND_BAR" in families
        assert "I_FAMILY" in families
        assert "U_FAMILY" in families
        assert "L_FAMILY" in families
        assert "T_FAMILY" in families
        assert "PIPE" in families
        assert "FLAT_BAR" in families
        assert "RECT_TUBE" in families

    def test_all_templates_valid_polygons(self):
        reg = ProfileRegistry().extend_generic_defaults()
        for t in reg.templates:
            assert t.polygon.is_valid, f"{t.variant} is not valid"
            assert t.polygon.area > 0, f"{t.variant} has zero area"

    def test_all_templates_normalized(self):
        reg = ProfileRegistry().extend_generic_defaults()
        for t in reg.templates:
            assert t.polygon.area == pytest.approx(1.0, abs=0.1), f"{t.variant} not normalized"


# ===================================================================
# match_templates
# ===================================================================


class TestMatchTemplates:
    @pytest.fixture()
    def registry(self):
        return ProfileRegistry().extend_generic_defaults()

    def test_round_bar_matches_round_bar(self, registry):
        query = make_round_bar()
        matches = match_templates(query, registry, top_k=3)
        assert matches[0].family == "ROUND_BAR"

    def test_returns_top_k(self, registry):
        matches = match_templates(make_round_bar(), registry, top_k=3)
        assert len(matches) == 3

    def test_scores_sorted_ascending(self, registry):
        matches = match_templates(make_i_section(), registry, top_k=5)
        scores = [m.score for m in matches]
        assert scores == sorted(scores)

    def test_i_section_matches_i_family(self, registry):
        matches = match_templates(make_i_section(), registry, top_k=3)
        top_families = {m.family for m in matches[:3]}
        assert "I_FAMILY" in top_families

    def test_flat_bar_matches_flat_bar(self, registry):
        matches = match_templates(make_flat_bar(), registry, top_k=3)
        assert matches[0].family in ("FLAT_BAR", "ROUND_BAR")


# ===================================================================
# extract_section_features
# ===================================================================


class TestExtractSectionFeatures:
    def _make_section(self, poly: Polygon) -> Section2D:
        return Section2D(
            polygon=poly,
            origin_3d=np.zeros(3),
            normal_3d=np.array([0, 0, 1.0]),
            basis_u=np.array([1, 0, 0], dtype=float),
            basis_v=np.array([0, 1, 0], dtype=float),
            source_position=0.5,
            line_length_fraction=1.0,
            curve_length_fraction=0.0,
        )

    def test_circle_compactness_near_one(self):
        circle = Point(0, 0).buffer(1.0, resolution=64)
        section = self._make_section(circle)
        features = extract_section_features(section)
        # Perfect circle: Q = 4πA/P² = 1
        assert features.compactness > 0.95

    def test_square_convexity_one(self):
        square = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
        section = self._make_section(square)
        features = extract_section_features(section)
        assert features.convexity == pytest.approx(1.0, abs=0.01)

    def test_area_positive(self):
        poly = Polygon([(0, 0), (2, 0), (2, 1), (0, 1)])
        features = extract_section_features(self._make_section(poly))
        assert features.area > 0

    def test_perimeter_positive(self):
        poly = Polygon([(0, 0), (2, 0), (2, 1), (0, 1)])
        features = extract_section_features(self._make_section(poly))
        assert features.perimeter > 0

    def test_bbox_ratio_between_0_and_1(self):
        poly = Polygon([(0, 0), (3, 0), (3, 1), (0, 1)])
        features = extract_section_features(self._make_section(poly))
        assert 0 < features.bbox_ratio <= 1.0

    def test_bbox_fill_between_0_and_1(self):
        poly = Polygon([(0, 0), (3, 0), (3, 1), (0, 1)])
        features = extract_section_features(self._make_section(poly))
        assert 0 < features.bbox_fill <= 1.0

    def test_pipe_has_holes(self):
        pipe = make_pipe(outer_radius=1.0, thickness=0.3)
        features = extract_section_features(self._make_section(pipe))
        assert features.holes >= 1

    def test_returns_tuple_types(self):
        poly = Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])
        features = extract_section_features(self._make_section(poly))
        assert isinstance(features.symmetry_angles_deg, tuple)
        assert isinstance(features.symmetry_scores, tuple)
