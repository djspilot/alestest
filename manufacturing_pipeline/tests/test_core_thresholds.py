import json

import pytest

from manufacturing_pipeline.core.runtime_unfold import _get_unfold_runtime_settings
from manufacturing_pipeline.core.thresholds import (
    DEFAULT_THRESHOLDS,
    clear_threshold_cache,
    get_thresholds,
    get_unfold_thresholds,
)


def setup_function() -> None:
    clear_threshold_cache()


def teardown_function() -> None:
    clear_threshold_cache()


def test_get_thresholds_uses_defaults_when_file_is_missing(tmp_path):
    missing_path = tmp_path / "missing-thresholds.json"

    thresholds = get_thresholds(str(missing_path))

    assert thresholds["unfold"]["runtime"]["timeout_sec"] == DEFAULT_THRESHOLDS["unfold"]["runtime"]["timeout_sec"]
    assert thresholds["unfold"]["fold_merge"]["gap_tol_mm"] == DEFAULT_THRESHOLDS["unfold"]["fold_merge"]["gap_tol_mm"]


def test_get_thresholds_applies_json_overrides(tmp_path):
    config_path = tmp_path / "thresholds.json"
    config_path.write_text(
        json.dumps(
            {
                "unfold": {
                    "runtime": {"timeout_sec": 240},
                    "fold_merge": {"gap_tol_mm": 80.0},
                }
            }
        ),
        encoding="utf-8",
    )

    thresholds = get_unfold_thresholds(str(config_path))

    assert thresholds["runtime"]["timeout_sec"] == 240
    assert thresholds["fold_merge"]["gap_tol_mm"] == 80.0
    assert thresholds["fold_merge"]["offset_tol_mm"] == DEFAULT_THRESHOLDS["unfold"]["fold_merge"]["offset_tol_mm"]


def test_get_thresholds_rejects_invalid_values(tmp_path):
    config_path = tmp_path / "thresholds.json"
    config_path.write_text(
        json.dumps(
            {
                "unfold": {
                    "candidate_limits": {"max_solids": 0},
                }
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="max_solids"):
        get_thresholds(str(config_path))


def test_runtime_unfold_settings_normalize_defaults():
    settings = _get_unfold_runtime_settings()

    assert settings["runtime_timeout_sec"] == 180
    assert settings["candidate_limits"]["max_solids"] == 3
    assert settings["candidate_limits"]["max_base_faces_per_solid"] == 10
    assert settings["fold_merge"]["offset_tol_mm"] == 2.0
    assert settings["thickness"]["max_override_mm"] == 25.0
    assert settings["thickness"]["min_override_delta_mm"] == 0.1
    assert settings["k_factor_lookup"][0.5] == 0.44
    assert settings["k_factor_lookup"][20.0] == 0.44