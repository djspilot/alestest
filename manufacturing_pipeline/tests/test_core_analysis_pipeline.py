import math
import pytest

from manufacturing_pipeline.core.analysis_pipeline import (
    comparison_criterion,
    range_criterion,
    boolean_criterion,
    json_safe,
    normalize_step0_review,
    build_legacy_gate_flow,
    CLASSIFICATION_THRESHOLDS,
)


# ---- comparison_criterion ----

def test_comparison_gte_passes():
    c = comparison_criterion("STEP 1A", "Aspect ratio", 3.5, 1.5, ">=")
    assert c["passed"] is True
    assert c["deviation"] == 2.0
    assert c["step"] == "STEP 1A"


def test_comparison_gte_fails():
    c = comparison_criterion("STEP 1A", "Aspect ratio", 1.0, 1.5, ">=")
    assert c["passed"] is False
    assert c["deviation"] == -0.5


def test_comparison_lt():
    c = comparison_criterion("STEP 1C", "Thickness", 5.0, 20.0, "<")
    assert c["passed"] is True
    assert c["deviation"] == 15.0


def test_comparison_lte():
    c = comparison_criterion("STEP 1B", "Thickness", 25.0, 25.0, "<=")
    assert c["passed"] is True


def test_comparison_gt():
    c = comparison_criterion("S", "X", 10.0, 10.0, ">")
    assert c["passed"] is False


def test_comparison_none_actual():
    c = comparison_criterion("S", "X", None, 1.0, ">=")
    assert c["passed"] is None
    assert c["actual"] is None


def test_comparison_none_threshold():
    c = comparison_criterion("S", "X", 5.0, None, ">=")
    assert c["passed"] is None
    assert c["threshold"] is None


def test_comparison_note():
    c = comparison_criterion("S", "X", 1.0, 2.0, ">=", note="my note")
    assert c["note"] == "my note"


# ---- range_criterion ----

def test_range_in_range():
    c = range_criterion("S", "Vol ratio", 0.3, 0.01, 0.5)
    assert c["passed"] is True
    assert c["deviation"] > 0


def test_range_below():
    c = range_criterion("S", "Vol ratio", 0.005, 0.01, 0.5)
    assert c["passed"] is False
    assert c["deviation"] < 0


def test_range_above():
    c = range_criterion("S", "Vol ratio", 0.8, 0.01, 0.5)
    assert c["passed"] is False
    assert c["deviation"] < 0


def test_range_none_values():
    c = range_criterion("S", "X", None, 0.0, 1.0)
    assert c["passed"] is None


def test_range_threshold_format():
    c = range_criterion("S", "X", 0.5, 0.1, 0.9)
    assert ".." in c["threshold"]


# ---- boolean_criterion ----

def test_boolean_true_matches():
    c = boolean_criterion("S", "Flag", True, True)
    assert c["passed"] is True


def test_boolean_false_matches():
    c = boolean_criterion("S", "Flag", False, False)
    assert c["passed"] is True


def test_boolean_mismatch():
    c = boolean_criterion("S", "Flag", True, False)
    assert c["passed"] is False


# ---- json_safe ----

def test_json_safe_none():
    assert json_safe(None) is None


def test_json_safe_string():
    assert json_safe("hello") == "hello"


def test_json_safe_int():
    assert json_safe(42) == 42


def test_json_safe_float_normal():
    result = json_safe(3.14159265)
    assert isinstance(result, float)
    assert abs(result - 3.141593) < 1e-6


def test_json_safe_float_nan():
    assert json_safe(float("nan")) is None


def test_json_safe_float_inf():
    assert json_safe(float("inf")) is None


def test_json_safe_dict():
    result = json_safe({"a": 1, "b": float("nan")})
    assert result == {"a": 1, "b": None}


def test_json_safe_list():
    result = json_safe([1, "x", None])
    assert result == [1, "x", None]


def test_json_safe_set():
    result = json_safe({1, 2})
    assert isinstance(result, list)
    assert set(result) == {1, 2}


def test_json_safe_nested():
    result = json_safe({"a": [1, {"b": float("inf")}]})
    assert result == {"a": [1, {"b": None}]}


def test_json_safe_object_with_value():
    class FakeEnum:
        value = "hello"
    assert json_safe(FakeEnum()) == "hello"


def test_json_safe_object_with_dict():
    class Obj:
        def __init__(self):
            self.x = 1
    result = json_safe(Obj())
    assert result == {"x": 1}


def test_json_safe_fallback_str():
    import datetime
    result = json_safe(datetime.date(2026, 1, 1))
    assert isinstance(result, str)


# ---- normalize_step0_review ----

def test_normalize_step0_review_none():
    assert normalize_step0_review(None) is None


def test_normalize_step0_review_non_dict():
    assert normalize_step0_review("not a dict") is None


def test_normalize_step0_review_minimal():
    trace = {
        "steps": [
            {
                "step": "1A",
                "name": "Plate",
                "verdict": "pass",
                "result": "plaat",
                "next": None,
                "note": None,
                "criteria": [
                    {"name": "top2", "value": 70.0, "expected": ">= 65", "passed": True}
                ],
            }
        ],
        "final_result": {"step": "1A", "fallthrough": False},
    }
    result = normalize_step0_review(trace)
    assert result is not None
    assert result["fallthrough"] is False
    assert result["stopped_in"] == "STEP 1A"
    assert len(result["steps"]) == 1
    assert result["steps"][0]["status"] == "PASS"
    assert result["steps"][0]["criteria"][0]["passed"] is True


def test_normalize_step0_review_fallthrough():
    trace = {
        "steps": [],
        "final_result": {"step": None, "fallthrough": True},
    }
    result = normalize_step0_review(trace)
    assert result["fallthrough"] is True
    assert result["stopped_in"] is None


# ---- build_legacy_gate_flow ----

def test_build_legacy_gate_flow_plate():
    trace = {"rules": ["plate_face"]}
    criteria = [
        {"step": "STEP 1A", "name": "Top2", "passed": True},
    ]
    result = build_legacy_gate_flow(trace, criteria)
    assert result["winner_gate"] == "1A"
    assert result["winner_rule"] == "plate_face"
    gates = result["gates"]
    winner = [g for g in gates if g["won"]]
    assert len(winner) == 1
    assert winner[0]["step"] == "1A"


def test_build_legacy_gate_flow_default():
    trace = {"rules": ["default_anders"]}
    result = build_legacy_gate_flow(trace, [])
    assert result["winner_gate"] == "4"
    for gate in result["gates"]:
        assert gate["entered"] is True


def test_build_legacy_gate_flow_no_rules():
    trace = {"rules": []}
    result = build_legacy_gate_flow(trace, [])
    assert result["winner_gate"] is None
    assert result["winner_rule"] is None


def test_build_legacy_gate_flow_none_trace():
    result = build_legacy_gate_flow(None, [])
    assert result["winner_gate"] is None


# ---- CLASSIFICATION_THRESHOLDS ----

def test_thresholds_structure():
    assert "bent_sheet" in CLASSIFICATION_THRESHOLDS
    assert "plate" in CLASSIFICATION_THRESHOLDS
    assert "profile" in CLASSIFICATION_THRESHOLDS
    assert CLASSIFICATION_THRESHOLDS["plate"]["aspect_ratio_min"] == 1.2
