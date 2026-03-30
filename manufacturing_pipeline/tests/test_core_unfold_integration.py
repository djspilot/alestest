import pytest

from manufacturing_pipeline.core.unfold_integration import (
    calculate_unfold_statistics,
    merge_unfold_thickness_with_analysis,
    should_attempt_unfold,
    validate_unfold_dimensions,
    build_unfold_event_payload,
)


# ---- calculate_unfold_statistics ----

def test_unfold_stats_success():
    result = calculate_unfold_statistics({
        "success": True,
        "flat_length": 200.0,
        "flat_width": 100.0,
        "fold_lines": 3,
        "thickness": 2.0,
        "flat_step_path": "/tmp/flat.step",
    })
    assert result["success"] is True
    assert result["flat_length"] == 200.0
    assert result["fold_lines"] == 3
    assert result["thickness"] == 2.0


def test_unfold_stats_failure():
    result = calculate_unfold_statistics(None)
    assert result["success"] is False
    assert result["flat_length"] is None


def test_unfold_stats_failed_result():
    result = calculate_unfold_statistics({"success": False})
    assert result["success"] is False


# ---- merge_unfold_thickness_with_analysis ----

def test_merge_thickness_replaces_zero():
    assert merge_unfold_thickness_with_analysis(2.0, 0.0) == 2.0


def test_merge_thickness_replaces_different():
    assert merge_unfold_thickness_with_analysis(2.0, 5.0) == 2.0


def test_merge_thickness_skips_close():
    assert merge_unfold_thickness_with_analysis(2.0, 2.05) is None


def test_merge_thickness_skips_too_large():
    assert merge_unfold_thickness_with_analysis(30.0, 0.0) is None


def test_merge_thickness_skips_none():
    assert merge_unfold_thickness_with_analysis(None, 2.0) is None


def test_merge_thickness_skips_zero():
    assert merge_unfold_thickness_with_analysis(0.0, 2.0) is None


def test_merge_thickness_skips_negative():
    assert merge_unfold_thickness_with_analysis(-1.0, 2.0) is None


# ---- should_attempt_unfold ----

def test_should_unfold_bent_sheet():
    assert should_attempt_unfold("GEBOGEN PLAATWERK", False, set()) is True


def test_should_not_unfold_flat_plate():
    assert should_attempt_unfold("PLAAT (vlak)", False, set()) is False


def test_should_not_unfold_flag_set():
    assert should_attempt_unfold("GEBOGEN PLAATWERK", True, set()) is False


def test_should_not_unfold_disabled():
    assert should_attempt_unfold("GEBOGEN PLAATWERK", False, {"unfold"}) is False


# ---- validate_unfold_dimensions ----

def test_valid_dimensions():
    assert validate_unfold_dimensions(200.0, 100.0) is True


def test_invalid_zero():
    assert validate_unfold_dimensions(0.0, 100.0) is False


def test_invalid_none():
    assert validate_unfold_dimensions(None, 100.0) is False


def test_invalid_too_large():
    assert validate_unfold_dimensions(20000.0, 100.0) is False


def test_invalid_negative():
    assert validate_unfold_dimensions(-5.0, 100.0) is False


# ---- build_unfold_event_payload ----

def test_event_payload_success():
    payload = build_unfold_event_payload({
        "success": True,
        "flat_length": 200.0,
        "flat_width": 100.0,
        "fold_lines": 3,
        "fold_details": [{"id": 1}],
        "bends_logical": [{"type": "up"}],
    })
    assert payload["success"] is True
    assert payload["flat_length"] == 200.0
    assert len(payload["fold_details"]) == 1


def test_event_payload_none():
    payload = build_unfold_event_payload(None)
    assert payload["success"] is False
    assert payload["flat_length"] is None
    assert payload["fold_lines"] == 0
