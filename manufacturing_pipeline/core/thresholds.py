"""Central threshold loading with JSON overrides and validation."""

from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
import json
import os
from typing import Any, Dict

from manufacturing_pipeline.core.paths import CONFIG_DIR
from manufacturing_pipeline.core.decision_variables import get_unfold_default_thresholds


DEFAULT_THRESHOLDS: Dict[str, Any] = {"unfold": get_unfold_default_thresholds()}


def _default_thresholds_path() -> str:
    return os.path.join(CONFIG_DIR, "thresholds.json")


def _filter_comment_keys(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _filter_comment_keys(item)
            for key, item in value.items()
            if not str(key).startswith("_")
        }
    if isinstance(value, list):
        return [_filter_comment_keys(item) for item in value]
    return value


def _deep_merge(base: Dict[str, Any], overrides: Dict[str, Any]) -> Dict[str, Any]:
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
    return base


def _require_number(name: str, value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"Threshold '{name}' must be numeric, got {type(value).__name__}")
    return float(value)


def validate_thresholds(thresholds: Dict[str, Any]) -> None:
    unfold = thresholds["unfold"]
    runtime = unfold["runtime"]
    limits = unfold["candidate_limits"]
    thickness = unfold["thickness"]
    fold_merge = unfold["fold_merge"]
    k_factor = unfold["k_factor"]

    timeout_sec = _require_number("unfold.runtime.timeout_sec", runtime["timeout_sec"])
    if timeout_sec < 1:
        raise ValueError("Threshold 'unfold.runtime.timeout_sec' must be >= 1")

    extra_timeout_per_mb_sec = _require_number(
        "unfold.runtime.extra_timeout_per_mb_sec",
        runtime["extra_timeout_per_mb_sec"],
    )
    if extra_timeout_per_mb_sec < 0:
        raise ValueError("Threshold 'unfold.runtime.extra_timeout_per_mb_sec' must be >= 0")

    max_timeout_sec = _require_number("unfold.runtime.max_timeout_sec", runtime["max_timeout_sec"])
    if max_timeout_sec < timeout_sec:
        raise ValueError("Threshold 'unfold.runtime.max_timeout_sec' must be >= timeout_sec")

    for key in ("max_solids", "max_base_faces_per_solid"):
        value = limits[key]
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"Threshold 'unfold.candidate_limits.{key}' must be an integer")
        if value < 1:
            raise ValueError(f"Threshold 'unfold.candidate_limits.{key}' must be >= 1")

    opposite_face_dot_max = _require_number(
        "unfold.thickness.opposite_face_dot_max",
        thickness["opposite_face_dot_max"],
    )
    if opposite_face_dot_max >= 0:
        raise ValueError("Threshold 'unfold.thickness.opposite_face_dot_max' must be < 0")

    max_override_mm = _require_number("unfold.thickness.max_override_mm", thickness["max_override_mm"])
    min_override_delta_mm = _require_number(
        "unfold.thickness.min_override_delta_mm",
        thickness["min_override_delta_mm"],
    )
    if max_override_mm <= 0:
        raise ValueError("Threshold 'unfold.thickness.max_override_mm' must be > 0")
    if min_override_delta_mm < 0:
        raise ValueError("Threshold 'unfold.thickness.min_override_delta_mm' must be >= 0")

    for key in ("offset_tol_mm", "angle_tol_deg", "radius_tol_mm", "overlap_tol_mm", "gap_tol_mm"):
        value = _require_number(f"unfold.fold_merge.{key}", fold_merge[key])
        if value < 0:
            raise ValueError(f"Threshold 'unfold.fold_merge.{key}' must be >= 0")
    if _require_number("unfold.fold_merge.angle_tol_deg", fold_merge["angle_tol_deg"]) > 180:
        raise ValueError("Threshold 'unfold.fold_merge.angle_tol_deg' must be <= 180")

    simplification = unfold.get("simplification", {})
    if simplification:
        frf = _require_number(
            "unfold.simplification.fillet_radius_thickness_factor",
            simplification["fillet_radius_thickness_factor"],
        )
        if not 0 < frf <= 1:
            raise ValueError("Threshold 'unfold.simplification.fillet_radius_thickness_factor' must be in (0, 1]")
        for int_key in ("min_fillet_faces_to_defeature", "min_cyl_faces_to_trigger", "skip_sheet_tree_cyl_threshold"):
            int_val = simplification[int_key]
            if isinstance(int_val, bool) or not isinstance(int_val, int):
                raise ValueError(f"Threshold 'unfold.simplification.{int_key}' must be an integer")
            if int_val < 1:
                raise ValueError(f"Threshold 'unfold.simplification.{int_key}' must be >= 1")

    default_k = _require_number("unfold.k_factor.default", k_factor["default"])
    if not 0 < default_k <= 1:
        raise ValueError("Threshold 'unfold.k_factor.default' must be in the range (0, 1]")

    buckets = k_factor["thickness_buckets_mm"]
    if not isinstance(buckets, dict) or not buckets:
        raise ValueError("Threshold 'unfold.k_factor.thickness_buckets_mm' must be a non-empty object")
    for key, value in buckets.items():
        try:
            numeric_key = float(key)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"Threshold 'unfold.k_factor.thickness_buckets_mm' key '{key}' must be numeric"
            ) from exc
        if numeric_key <= 0:
            raise ValueError("K-factor thickness bucket keys must be > 0")
        numeric_value = _require_number(
            f"unfold.k_factor.thickness_buckets_mm.{key}",
            value,
        )
        if not 0 < numeric_value <= 1:
            raise ValueError(
                f"Threshold 'unfold.k_factor.thickness_buckets_mm.{key}' must be in the range (0, 1]"
            )


@lru_cache(maxsize=None)
def _load_thresholds_cached(config_path: str) -> Dict[str, Any]:
    thresholds = deepcopy(DEFAULT_THRESHOLDS)
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as handle:
            overrides = _filter_comment_keys(json.load(handle))
        if overrides:
            _deep_merge(thresholds, overrides)
    validate_thresholds(thresholds)
    return thresholds


def clear_threshold_cache() -> None:
    _load_thresholds_cached.cache_clear()


def get_thresholds(config_path: str | None = None) -> Dict[str, Any]:
    resolved_path = os.path.abspath(config_path or _default_thresholds_path())
    return deepcopy(_load_thresholds_cached(resolved_path))


def get_unfold_thresholds(config_path: str | None = None) -> Dict[str, Any]:
    return get_thresholds(config_path)["unfold"]