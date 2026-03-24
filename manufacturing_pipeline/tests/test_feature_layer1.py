"""Layer 1 feature tests for shared hole/thread/countersink logic."""

from types import SimpleNamespace

import pytest
import cadquery as cq

from manufacturing_pipeline.analysis import cut_features


class _DummyWorkplane:
    """Minimal CadQuery Workplane stub used by cut_features wrappers."""

    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs

    def newObject(self, _items):
        return self


def _stub_cq(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch CadQuery constructors so we can unit-test feature flow deterministically."""

    monkeypatch.setattr(cut_features.cq, "Solid", lambda shape: shape)
    monkeypatch.setattr(cut_features.cq, "Workplane", _DummyWorkplane)


def _stub_sheet_geometry(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch geometry helpers unrelated to Layer 1 feature behavior."""

    monkeypatch.setattr(cut_features, "_get_outer_contour_length", lambda _shape: 100.0)
    monkeypatch.setattr(
        cut_features,
        "_get_bounding_box",
        lambda _shape: {"xlen": 10.0, "ylen": 20.0, "zlen": 2.0},
    )


def _hole(diameter: float, depth: float) -> SimpleNamespace:
    """Create a minimal hole object compatible with cut_features logic."""

    return SimpleNamespace(
        diameter=diameter,
        depth=depth,
        axis=(0.0, 0.0, 1.0),
        position=(0.0, 0.0, 0.0),
        axis_origin=(0.0, 0.0, 0.0),
    )


def test_layer1_countersunk_priority_over_thread(monkeypatch: pytest.MonkeyPatch) -> None:
    """Countersunk match should override thread classification for a cylindrical hole."""

    _stub_cq(monkeypatch)
    _stub_sheet_geometry(monkeypatch)

    holes = [_hole(10.0, 3.0), _hole(6.8, 8.0), _hole(12.0, 5.0)]

    monkeypatch.setattr(cut_features, "detect_holes", lambda *_a, **_k: holes)
    monkeypatch.setattr(cut_features, "detect_shaped_holes", lambda *_a, **_k: [])
    monkeypatch.setattr(cut_features, "deduplicate_holes", lambda c, _s: c)
    monkeypatch.setattr(cut_features, "_detect_countersunk_holes", lambda *_a, **_k: {0: 90.0})
    monkeypatch.setattr(cut_features, "_detect_standalone_countersunk_holes", lambda *_a, **_k: [])

    def _identify_thread(diameter: float, _tol: float):
        if abs(diameter - 6.8) < 1e-6:
            return [SimpleNamespace(designation="M8 tapped", major_diameter=8.0)]
        return []

    monkeypatch.setattr(cut_features.iso_standards, "identify_thread_from_diameter", _identify_thread)

    result = cut_features.extract_cut_features_for_sheet(solid=object(), unfold_result=None, part_classification="plaat")

    assert result is not None
    assert result.hole_types == ["countersunk", "thread", "round"]
    assert result.countersunk_holes == 1
    assert result.threaded_holes == 1
    assert result.nr_holes == 3
    assert result.countersunk_angles == [90.0]


def test_layer1_ambiguous_thread_match_stays_round(monkeypatch: pytest.MonkeyPatch) -> None:
    """If diameter matches both tapped and major, classify as round (clearance bias)."""

    _stub_cq(monkeypatch)
    _stub_sheet_geometry(monkeypatch)

    holes = [_hole(6.8, 8.0)]

    monkeypatch.setattr(cut_features, "detect_holes", lambda *_a, **_k: holes)
    monkeypatch.setattr(cut_features, "detect_shaped_holes", lambda *_a, **_k: [])
    monkeypatch.setattr(cut_features, "deduplicate_holes", lambda c, _s: c)
    monkeypatch.setattr(cut_features, "_detect_countersunk_holes", lambda *_a, **_k: {})
    monkeypatch.setattr(cut_features, "_detect_standalone_countersunk_holes", lambda *_a, **_k: [])

    monkeypatch.setattr(
        cut_features.iso_standards,
        "identify_thread_from_diameter",
        lambda _d, _t: [
            SimpleNamespace(designation="M8 tapped", major_diameter=8.0),
            SimpleNamespace(designation="M8", major_diameter=8.0),
        ],
    )

    result = cut_features.extract_cut_features_for_sheet(solid=object(), unfold_result=None, part_classification="plaat")

    assert result is not None
    assert result.hole_types == ["round"]
    assert result.threaded_holes == 0
    assert result.countersunk_holes == 0


def test_layer1_shaped_hole_types_and_contours(monkeypatch: pytest.MonkeyPatch) -> None:
    """Shaped holes should be counted/measured without separate output labels."""

    _stub_cq(monkeypatch)
    _stub_sheet_geometry(monkeypatch)

    monkeypatch.setattr(cut_features, "detect_holes", lambda *_a, **_k: [])
    monkeypatch.setattr(
        cut_features,
        "detect_shaped_holes",
        lambda *_a, **_k: [
            {"type": "Slot", "dim": "20x10"},
            {"type": "Rect", "dim": "4x5"},
        ],
    )
    monkeypatch.setattr(cut_features, "deduplicate_holes", lambda c, _s: c)
    monkeypatch.setattr(cut_features, "_detect_countersunk_holes", lambda *_a, **_k: {})
    monkeypatch.setattr(cut_features, "_detect_standalone_countersunk_holes", lambda *_a, **_k: [])
    monkeypatch.setattr(cut_features.iso_standards, "identify_thread_from_diameter", lambda *_a, **_k: [])

    result = cut_features.extract_cut_features_for_sheet(solid=object(), unfold_result=None, part_classification="plaat")

    assert result is not None
    assert result.nr_holes == 2
    assert result.hole_types == ["hole", "hole"]
    assert result.hole_contours[0] == pytest.approx(20.0 + 10.0 * 3.14159265359, rel=1e-6)
    assert result.hole_contours[1] == pytest.approx(18.0, rel=1e-6)


def test_profile_thread_disambiguation_prefers_tapped_for_small_ambiguous(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ambiguous small profile holes should map to thread when matching tap-drill pattern."""

    holes = [_hole(5.0, 3.0)]

    monkeypatch.setattr(cut_features, "detect_holes", lambda *_a, **_k: holes)
    monkeypatch.setattr(cut_features, "detect_shaped_holes", lambda *_a, **_k: [])
    monkeypatch.setattr(cut_features, "deduplicate_holes", lambda c, _s: c)
    monkeypatch.setattr(cut_features, "_detect_countersunk_holes", lambda *_a, **_k: {})
    monkeypatch.setattr(cut_features, "_detect_standalone_countersunk_holes", lambda *_a, **_k: [])
    monkeypatch.setattr(cut_features, "_infer_profile_countersink_pairs", lambda *_a, **_k: (set(), set()))

    monkeypatch.setattr(
        cut_features.iso_standards,
        "identify_thread_from_diameter",
        lambda _d, _t: [
            SimpleNamespace(designation="M5", major_diameter=5.0),
            SimpleNamespace(designation="M6 (tapped)", major_diameter=6.0),
        ],
    )

    test_solid = cq.Workplane("XY").box(10, 10, 10).val().wrapped
    result = cut_features.extract_cut_features_for_profile(solid=test_solid, part_classification="profiel")

    assert result is not None
    assert result.nr_holes == 1
    assert result.threaded_holes == 1
    assert result.countersunk_holes == 0
    assert result.hole_types == ["thread"]


def test_profile_infers_countersink_from_stepped_pair(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stepped cylindrical pair should count as one countersunk hole in profile flow."""

    large = SimpleNamespace(
        diameter=17.0,
        depth=3.0,
        axis=(1.0, 0.0, 0.0),
        position=(-8.5, 82.0, 0.0),
        axis_origin=(-8.5, 82.0, 0.0),
    )
    small = SimpleNamespace(
        diameter=8.5,
        depth=3.0,
        axis=(1.0, 0.0, 0.0),
        position=(8.5, 84.0, 0.0),
        axis_origin=(8.5, 84.0, 0.0),
    )

    monkeypatch.setattr(cut_features, "detect_holes", lambda *_a, **_k: [large, small])
    monkeypatch.setattr(cut_features, "detect_shaped_holes", lambda *_a, **_k: [])
    monkeypatch.setattr(cut_features, "deduplicate_holes", lambda c, _s: c)
    monkeypatch.setattr(cut_features, "_detect_countersunk_holes", lambda *_a, **_k: {})
    monkeypatch.setattr(cut_features, "_detect_standalone_countersunk_holes", lambda *_a, **_k: [])
    monkeypatch.setattr(cut_features.iso_standards, "identify_thread_from_diameter", lambda *_a, **_k: [])

    test_solid = cq.Workplane("XY").box(10, 10, 10).val().wrapped
    result = cut_features.extract_cut_features_for_profile(solid=test_solid, part_classification="profiel")

    assert result is not None
    assert result.nr_holes == 1
    assert result.countersunk_holes == 1
    assert result.threaded_holes == 0
    assert result.hole_types == ["countersunk"]


def test_profile_filters_end_face_hollow_opening_from_shaped_holes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Large shaped contour on profile end face should be suppressed as hollow-core opening."""

    monkeypatch.setattr(cut_features, "detect_holes", lambda *_a, **_k: [])
    monkeypatch.setattr(
        cut_features,
        "detect_shaped_holes",
        lambda *_a, **_k: [
            {"type": "Rect", "dim": "34x14", "center": (49.0, 0.0, 0.0), "normal": (1.0, 0.0, 0.0)},
            {"type": "Rect", "dim": "8x6", "center": (0.0, 19.0, 0.0), "normal": (0.0, 1.0, 0.0)},
        ],
    )
    monkeypatch.setattr(cut_features, "deduplicate_holes", lambda c, _s: c)
    monkeypatch.setattr(cut_features, "_detect_countersunk_holes", lambda *_a, **_k: {})
    monkeypatch.setattr(cut_features, "_detect_standalone_countersunk_holes", lambda *_a, **_k: [])
    monkeypatch.setattr(cut_features, "_infer_profile_countersink_pairs", lambda *_a, **_k: (set(), set()))
    monkeypatch.setattr(cut_features.iso_standards, "identify_thread_from_diameter", lambda *_a, **_k: [])

    test_solid = cq.Workplane("XY").box(100, 40, 20).val().wrapped
    result = cut_features.extract_cut_features_for_profile(solid=test_solid, part_classification="profiel")

    assert result is not None
    assert result.nr_holes == 1
    assert result.nr_shaped == 1
    assert result.hole_types == ["hole"]
