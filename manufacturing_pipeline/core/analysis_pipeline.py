"""
Analysis pipeline helper functions and orchestration.

This module contains:
- Criterion builders (_comparison_criterion, _range_criterion, etc.)
- Classification logic helpers
- Pipeline orchestration
"""

import math
from typing import Any, Dict, List, Optional, Tuple

from manufacturing_pipeline.core.decision_variables import get_classification_review_thresholds


# =============================================================================
# Criterion Builders
# =============================================================================

def comparison_criterion(step: str, name: str, actual: Optional[float], 
                         threshold: Optional[float], operator: str, note: Optional[str] = None) -> Dict[str, Any]:
    """Build a comparison criterion result."""
    actual_value = None if actual is None else float(actual)
    threshold_value = None if threshold is None else float(threshold)
    passed = None
    deviation = None

    if actual_value is not None and threshold_value is not None:
        if operator == ">=":
            deviation = round(actual_value - threshold_value, 3)
            passed = actual_value >= threshold_value
        elif operator == ">":
            deviation = round(actual_value - threshold_value, 3)
            passed = actual_value > threshold_value
        elif operator == "<=":
            deviation = round(threshold_value - actual_value, 3)
            passed = actual_value <= threshold_value
        elif operator == "<":
            deviation = round(threshold_value - actual_value, 3)
            passed = actual_value < threshold_value

    return {
        "step": step,
        "name": name,
        "actual": round(actual_value, 3) if actual_value is not None else None,
        "threshold": f"{operator} {threshold_value:.3f}" if threshold_value is not None else None,
        "deviation": deviation,
        "passed": passed,
        "note": note,
    }


def range_criterion(step: str, name: str, actual: Optional[float],
                   minimum: Optional[float], maximum: Optional[float], 
                   note: Optional[str] = None) -> Dict[str, Any]:
    """Build a range criterion result."""
    actual_value = None if actual is None else float(actual)
    min_value = None if minimum is None else float(minimum)
    max_value = None if maximum is None else float(maximum)
    passed = None
    deviation = None

    if actual_value is not None and min_value is not None and max_value is not None:
        if min_value <= actual_value <= max_value:
            deviation = round(min(actual_value - min_value, max_value - actual_value), 3)
            passed = True
        elif actual_value < min_value:
            deviation = round(actual_value - min_value, 3)
            passed = False
        else:
            deviation = round(max_value - actual_value, 3)
            passed = False

    return {
        "step": step,
        "name": name,
        "actual": round(actual_value, 3) if actual_value is not None else None,
        "threshold": f"{min_value:.3f} .. {max_value:.3f}" if min_value is not None and max_value is not None else None,
        "deviation": deviation,
        "passed": passed,
        "note": note,
    }


def boolean_criterion(step: str, name: str, actual: bool, should_be: bool, 
                     note: Optional[str] = None) -> Dict[str, Any]:
    """Build a boolean criterion result."""
    actual_value = bool(actual)
    return {
        "step": step,
        "name": name,
        "actual": actual_value,
        "threshold": str(bool(should_be)).lower(),
        "deviation": None,
        "passed": actual_value is bool(should_be),
        "note": note,
    }


def json_safe(value: Any) -> Any:
    """Convert value to JSON-safe representation."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return round(value, 6)
    if isinstance(value, dict):
        return {str(key): json_safe(val) for key, val in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(item) for item in value]
    if hasattr(value, "value"):
        return json_safe(value.value)
    if hasattr(value, "__dict__"):
        return json_safe(vars(value))
    return str(value)


# =============================================================================
# Geometry Helpers
# =============================================================================

def primary_solid_for_classification(cq_shape) -> Any:
    """Extract primary solid from CadQuery shape for classification."""
    try:
        if hasattr(cq_shape, "solids"):
            solids_obj = cq_shape.solids()
            solids = solids_obj.vals() if hasattr(solids_obj, "vals") else list(solids_obj)
            if solids:
                first = solids[0]
                return first.wrapped if hasattr(first, "wrapped") else first
    except Exception:
        pass

    try:
        if hasattr(cq_shape, "val"):
            val = cq_shape.val()
            return val.wrapped if hasattr(val, "wrapped") else val
    except Exception:
        pass

    return cq_shape.wrapped if hasattr(cq_shape, "wrapped") else cq_shape


# =============================================================================
# Classification Normalization
# =============================================================================

def normalize_step0_review(step0_trace: Optional[Dict]) -> Optional[Dict]:
    """Normalize STEP 0 classification review."""
    if not isinstance(step0_trace, dict):
        return None

    normalized_steps = []
    for step in step0_trace.get("steps") or []:
        criteria = []
        for criterion in step.get("criteria") or []:
            criterion_pass = criterion.get("pass") if "pass" in criterion else criterion.get("passed")
            criteria.append({
                "name": criterion.get("name"),
                "actual": json_safe(criterion.get("value")),
                "threshold": json_safe(criterion.get("expected")),
                "passed": json_safe(criterion_pass),
            })

        normalized_steps.append({
            "step": step.get("step"),
            "name": step.get("name"),
            "status": (step.get("verdict") or "UNKNOWN").upper(),
            "result": step.get("result"),
            "next": step.get("next"),
            "note": step.get("note"),
            "criteria": criteria,
        })

    final_result = json_safe(step0_trace.get("final_result") or {})
    final_step = final_result.get("step") if isinstance(final_result, dict) else None
    fallthrough = bool(final_result.get("fallthrough")) if isinstance(final_result, dict) else False

    return {
        "doc": "docs/classification_step_review.md",
        "final_result": final_result,
        "steps": normalized_steps,
        "fallthrough": fallthrough,
        "stopped_in": f"STEP {final_step}" if final_step and not fallthrough else None,
    }


def build_legacy_gate_flow(legacy_trace: Optional[Dict], criteria: List[Dict]) -> Dict:
    """Build legacy gate flow from trace and criteria."""
    rules = list((legacy_trace or {}).get("rules") or [])
    criteria_by_step = {}
    for criterion in criteria or []:
        step_name = str(criterion.get("step") or "").upper()
        criteria_by_step.setdefault(step_name, []).append(criterion)

    gate_definitions = [
        ("1A", "Plate detection — Face Analysis", ["plate_face"], 
         "Twee grote parallelle vlakke faces bepalen vlak plaatwerk."),
        ("1B", "Bent sheet", ["bent_sheet_metal", "bent_sheet_closed_profile"], 
         "Gebogen plaatwerk of gesloten gebogen profiel."),
        ("1C", "Thin plate fallback", ["plate_thin"], 
         "Dunne, slanke plaat als fallback."),
        ("1D", "Feature heavy plate", ["plate_feature_heavy"], 
         "Geperforeerde / feature-zware plaat."),
        ("2B", "Solid profile", ["profile_solid_strong", "profile_solid_weak_sav"], 
         "Massief profiel op volume- en SA/V-criteria."),
        ("3A", "Standard hollow tube", ["standard_hollow_tube"], 
         "Kataloog holle buis op cilindrisch oppervlak."),
        ("3B", "Variable thickness profile", ["standard_variable_thickness"], 
         "UNP/I/L-profielen via ongelijke face-oppervlakken."),
        ("4", "Default anders", ["default_anders"], 
         "Geen eerdere gate won; fallback naar anders."),
    ]
    rule_to_gate = {
        rule_name: gate_step
        for gate_step, _gate_name, gate_rules, _description in gate_definitions
        for rule_name in gate_rules
    }
    winner_rule = next((rule for rule in reversed(rules) if rule in rule_to_gate), None)
    winner_gate = rule_to_gate.get(winner_rule)
    winner_index = next((index for index, (step, *_rest) in enumerate(gate_definitions) 
                         if step == winner_gate), None)

    gates = []
    for index, (step, name, gate_rules, description) in enumerate(gate_definitions):
        step_key = f"STEP {step}"
        gate_criteria = criteria_by_step.get(step_key, [])
        entered = winner_index is not None and index <= winner_index
        if winner_gate == "4":
            entered = True

        known_passes = [item.get("passed") for item in gate_criteria if item.get("passed") is not None]
        if step == winner_gate:
            status = "WINNER"
        elif not entered:
            status = "SKIP"
        elif known_passes and all(known_passes):
            status = "PASS"
        else:
            status = "FAIL"

        gates.append({
            "step": step,
            "name": name,
            "status": status,
            "entered": entered,
            "won": step == winner_gate,
            "rule": winner_rule if step == winner_gate else None,
            "description": description,
            "criteria": gate_criteria,
        })

    return {
        "doc": "docs/CLASSIFICATION_THRESHOLDS_MATRIX.md",
        "rules": rules,
        "winner_gate": winner_gate,
        "winner_rule": winner_rule,
        "gates": gates,
    }


def build_classification_visuals(analysis: Any, legacy_class: str, legacy_trace: Optional[Dict],
                                 classification_criteria: List[Dict], source: str, 
                                 solid_for_classification: Any, part_category: str) -> Dict:
    """Build classification visuals combining STEP 0 and legacy flow."""
    step0_trace = None
    step0_review = None
    if solid_for_classification is not None:
        try:
            from manufacturing_pipeline.analysis.classification import classify_step0_detailed_trace
            step0_trace = classify_step0_detailed_trace(solid_for_classification)
            step0_review = normalize_step0_review(step0_trace)
        except Exception as e:
            step0_review = {
                "doc": "docs/classification_step_review.md",
                "error": str(e),
                "steps": [],
                "fallthrough": True,
                "stopped_in": None,
            }

    legacy_flow = build_legacy_gate_flow(legacy_trace, classification_criteria) if legacy_trace else None
    step0_fallthrough = bool((step0_review or {}).get("fallthrough"))
    final_step0 = (step0_review or {}).get("final_result") if isinstance((step0_review or {}).get("final_result"), dict) else {}

    stopped_in = None
    if step0_review and not step0_fallthrough and final_step0.get("step"):
        stopped_in = f"STEP {final_step0.get('step')}"
    elif legacy_flow and legacy_flow.get("winner_gate"):
        stopped_in = f"STEP {legacy_flow.get('winner_gate')}"

    final_decision = {
        "classification": legacy_class,
        "part_category": part_category,
        "part_type": getattr(getattr(analysis, "part_type", None), "value", 
                            getattr(analysis, "part_type", None)),
        "source": source,
        "stopped_in": stopped_in,
        "step0_only": bool(step0_review and not step0_fallthrough),
    }

    return {
        "part_category": part_category,
        "part_type": getattr(getattr(analysis, "part_type", None), "value", 
                            getattr(analysis, "part_type", None)),
        "thickness": round(float(getattr(analysis, "thickness", 0) or 0), 3),
        "dimensions": {
            "length": round(float(getattr(analysis, "length", 0) or 0), 3),
            "width": round(float(getattr(analysis, "width", 0) or 0), 3),
            "height": round(float(getattr(analysis, "height", 0) or 0), 3),
        },
        "source": source,
        "trace": legacy_trace or {},
        "rules": list((legacy_trace or {}).get("rules") or []),
        "criteria": classification_criteria,
        "matrix_doc": "docs/CLASSIFICATION_THRESHOLDS_MATRIX.md",
        "step0_doc": "docs/classification_step_review.md",
        "final_decision": final_decision,
        "step0_review": step0_review,
        "legacy_classification": legacy_flow if step0_fallthrough else None,
        "reasoning": [
            {
                "step": getattr(item, "step", ""),
                "observation": getattr(item, "observation", ""),
                "conclusion": getattr(item, "conclusion", ""),
                "details": getattr(item, "details", {}) or {},
            }
            for item in (getattr(analysis, "reasoning", []) or [])
        ],
    }


# =============================================================================
# Constants for Threshold Computation
# =============================================================================

CLASSIFICATION_THRESHOLDS = get_classification_review_thresholds()


__all__ = [
    "comparison_criterion",
    "range_criterion",
    "boolean_criterion",
    "json_safe",
    "primary_solid_for_classification",
    "normalize_step0_review",
    "build_legacy_gate_flow",
    "build_classification_visuals",
    "CLASSIFICATION_THRESHOLDS",
]
