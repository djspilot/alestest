# Core Module Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deduplicate, restructure, and add full pytest coverage to `manufacturing_pipeline/core/`, making it maintainable and testable without breaking existing consumers.

**Architecture:** Centralize path constants in one module (`paths.py`). Remove duplicated helper functions from `runtime_analysis.py` so it calls the already-extracted versions in `analysis_pipeline.py`. Replace the wildcard re-export shim (`utils.py`) with explicit imports that consumers already use. Add pytest tests for every pure-logic module (cache, config, profiler, analysis_pipeline, unfold_integration, file_utils, hole_detection_fallback helpers).

**Tech Stack:** Python 3.11+, pytest, dataclasses, OCP/CadQuery (mocked in tests where needed)

---

## File Structure

### New files
- `manufacturing_pipeline/core/paths.py` -- Single source of truth for all path constants
- `manufacturing_pipeline/tests/test_core_paths.py` -- Tests for paths module
- `manufacturing_pipeline/tests/test_core_cache.py` -- Tests for cache module
- `manufacturing_pipeline/tests/test_core_config.py` -- Tests for config dataclasses
- `manufacturing_pipeline/tests/test_core_profiler.py` -- Tests for AnalysisProfiler
- `manufacturing_pipeline/tests/test_core_analysis_pipeline.py` -- Tests for criterion builders, json_safe, classification helpers
- `manufacturing_pipeline/tests/test_core_unfold_integration.py` -- Tests for unfold helpers
- `manufacturing_pipeline/tests/test_core_file_utils.py` -- Tests for file discovery helpers
- `manufacturing_pipeline/tests/test_core_runtime_reporting.py` -- Tests for debug output

### Modified files
- `manufacturing_pipeline/core/utils.py` -- Replace wildcard re-exports with explicit forwarding of `run_analysis` + path constants only
- `manufacturing_pipeline/core/runtime_analysis.py` -- Remove duplicated inner functions, import from `analysis_pipeline.py` and `paths.py`
- `manufacturing_pipeline/core/runtime_unfold.py` -- Import path constants from `paths.py`
- `manufacturing_pipeline/core/file_utils.py` -- Import path constants from `paths.py`
- `manufacturing_pipeline/core/cache.py` -- Import CACHE_FILE path from `paths.py`
- `manufacturing_pipeline/cli.py` -- Update imports to use specific submodules instead of `utils`
- `manufacturing_pipeline/api/analysis_service.py` -- Update imports
- `manufacturing_pipeline/tests/test_basic.py` -- Update imports

---

## Task 1: Create `paths.py` -- centralize path constants

**Files:**
- Create: `manufacturing_pipeline/core/paths.py`
- Create: `manufacturing_pipeline/tests/test_core_paths.py`

- [ ] **Step 1: Write the failing test**

```python
# manufacturing_pipeline/tests/test_core_paths.py
import os
import pytest

from manufacturing_pipeline.core.paths import (
    PROJECT_ROOT,
    DATA_DIR,
    CONFIG_DIR,
    DB_DIR,
    PARTS_DIR,
    OUTPUT_DIR,
    PIPELINE_DIR,
    SCRIPTS_DIR,
    CACHE_FILE,
)


def test_project_root_exists():
    assert os.path.isdir(PROJECT_ROOT)
    assert os.path.exists(os.path.join(PROJECT_ROOT, "manufacturing_pipeline"))


def test_data_dir_under_root():
    assert DATA_DIR == os.path.join(PROJECT_ROOT, "data")


def test_parts_dir():
    assert PARTS_DIR == os.path.join(DATA_DIR, "input")


def test_output_dir():
    assert OUTPUT_DIR == os.path.join(DATA_DIR, "output")


def test_pipeline_dir():
    assert PIPELINE_DIR == os.path.join(PROJECT_ROOT, "manufacturing_pipeline")
    assert os.path.isdir(PIPELINE_DIR)


def test_cache_file_path():
    assert CACHE_FILE.endswith("pipeline_cache.json")
    assert DB_DIR in CACHE_FILE
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest manufacturing_pipeline/tests/test_core_paths.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'manufacturing_pipeline.core.paths'`

- [ ] **Step 3: Write minimal implementation**

```python
# manufacturing_pipeline/core/paths.py
"""Single source of truth for project path constants."""

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DATA_DIR = os.path.join(PROJECT_ROOT, "data")
CONFIG_DIR = os.path.join(DATA_DIR, "config")
DB_DIR = os.path.join(DATA_DIR, "db")
PARTS_DIR = os.path.join(DATA_DIR, "input")
OUTPUT_DIR = os.path.join(DATA_DIR, "output")

PIPELINE_DIR = os.path.join(PROJECT_ROOT, "manufacturing_pipeline")
SCRIPTS_DIR = os.path.join(PIPELINE_DIR, "scripts")

CACHE_FILE = os.path.join(DB_DIR, "pipeline_cache.json")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest manufacturing_pipeline/tests/test_core_paths.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add manufacturing_pipeline/core/paths.py manufacturing_pipeline/tests/test_core_paths.py
git commit -m "refactor(core): extract path constants into paths.py with tests"
```

---

## Task 2: Test and harden `cache.py`

**Files:**
- Modify: `manufacturing_pipeline/core/cache.py` -- use `paths.CACHE_FILE` instead of computing it locally
- Create: `manufacturing_pipeline/tests/test_core_cache.py`

- [ ] **Step 1: Write the failing tests**

```python
# manufacturing_pipeline/tests/test_core_cache.py
import json
import os
import tempfile
import pytest

from manufacturing_pipeline.core.cache import (
    get_file_hash,
    load_cache,
    save_cache,
    get_cached_result,
    cache_result,
)


def test_get_file_hash_deterministic(tmp_path):
    f = tmp_path / "test.txt"
    f.write_text("hello world")
    h1 = get_file_hash(str(f))
    h2 = get_file_hash(str(f))
    assert h1 == h2
    assert isinstance(h1, str)
    assert len(h1) == 32  # MD5 hex digest


def test_get_file_hash_changes_with_content(tmp_path):
    f = tmp_path / "test.txt"
    f.write_text("version 1")
    h1 = get_file_hash(str(f))
    f.write_text("version 2")
    h2 = get_file_hash(str(f))
    assert h1 != h2


def test_load_cache_missing_file(tmp_path, monkeypatch):
    monkeypatch.setattr("manufacturing_pipeline.core.cache.CACHE_FILE", str(tmp_path / "nope.json"))
    assert load_cache() == {}


def test_load_cache_corrupt_json(tmp_path, monkeypatch):
    bad = tmp_path / "bad.json"
    bad.write_text("{broken")
    monkeypatch.setattr("manufacturing_pipeline.core.cache.CACHE_FILE", str(bad))
    assert load_cache() == {}


def test_save_and_load_roundtrip(tmp_path, monkeypatch):
    cache_path = str(tmp_path / "sub" / "cache.json")
    monkeypatch.setattr("manufacturing_pipeline.core.cache.CACHE_FILE", cache_path)
    data = {"key": {"hash": "abc", "result": 42}}
    save_cache(data)
    loaded = load_cache()
    assert loaded == data


def test_cache_result_and_retrieve(tmp_path):
    f = tmp_path / "part.step"
    f.write_bytes(b"STEP DATA")
    cache = {}
    cache = cache_result(str(f), {"holes": 5}, cache)
    result = get_cached_result(str(f), cache)
    assert result == {"holes": 5}


def test_cached_result_invalidated_on_change(tmp_path):
    f = tmp_path / "part.step"
    f.write_bytes(b"v1")
    cache = {}
    cache = cache_result(str(f), {"v": 1}, cache)
    f.write_bytes(b"v2")
    result = get_cached_result(str(f), cache)
    assert result is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest manufacturing_pipeline/tests/test_core_cache.py -v`
Expected: PASS (cache.py already works correctly -- these tests document existing behavior)

- [ ] **Step 3: Update cache.py to use paths.py**

Replace the `CACHE_FILE` computation in `manufacturing_pipeline/core/cache.py`:

```python
# Replace lines 6-7 (the os.path.join computation) with:
from manufacturing_pipeline.core.paths import CACHE_FILE
```

Remove the old `CACHE_FILE = os.path.join(...)` block and the `import os` at top if no longer needed (it's still needed for `os.path.exists` and `os.makedirs`).

The updated file header becomes:
```python
"""
Cache management for manufacturing pipeline.
Handles file hashing, cache I/O, and result caching with invalidation.
"""

import os
import json
import hashlib
from datetime import datetime

from manufacturing_pipeline.core.paths import CACHE_FILE
```

- [ ] **Step 4: Run tests to verify everything passes**

Run: `python -m pytest manufacturing_pipeline/tests/test_core_cache.py manufacturing_pipeline/tests/test_core_paths.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add manufacturing_pipeline/core/cache.py manufacturing_pipeline/tests/test_core_cache.py
git commit -m "refactor(core): cache.py uses paths.py, add pytest coverage"
```

---

## Task 3: Test `config.py` dataclasses

**Files:**
- Create: `manufacturing_pipeline/tests/test_core_config.py`

- [ ] **Step 1: Write the tests**

```python
# manufacturing_pipeline/tests/test_core_config.py
import json
import os
import tempfile
import pytest

from manufacturing_pipeline.core.config import (
    SystemConfig,
    ModuleConfig,
    PricingConfig,
    MaterialPricesConfig,
    CostColumnsConfig,
    PipelineConfig,
    MODULE_GROUPS,
    MODULE_NAMES,
    create_default_config,
    create_minimal_config,
    apply_module_toggles,
    _freecad_root_candidates,
)


# ---- SystemConfig ----

def test_system_config_default_freecad_path():
    cfg = SystemConfig()
    assert isinstance(cfg.freecad_path, str)


def test_system_config_from_env(monkeypatch):
    monkeypatch.setenv("FREECAD_PATH", "/fake/freecad")
    cfg = SystemConfig.from_env()
    assert cfg.freecad_path == "/fake/freecad"


def test_system_config_from_env_missing(monkeypatch):
    monkeypatch.delenv("FREECAD_PATH", raising=False)
    cfg = SystemConfig.from_env()
    assert isinstance(cfg.freecad_path, str)


def test_freecad_root_candidates_linux():
    candidates = _freecad_root_candidates(platform="linux")
    assert any("/usr" in c for c in candidates)


def test_freecad_root_candidates_darwin():
    candidates = _freecad_root_candidates(platform="darwin")
    assert any("FreeCAD.app" in c for c in candidates)


def test_freecad_root_candidates_windows():
    candidates = _freecad_root_candidates(platform="win32")
    assert any("FreeCAD" in c for c in candidates)


def test_system_config_to_dict():
    cfg = SystemConfig(freecad_path="/test")
    d = cfg.to_dict()
    assert d["freecad_path"] == "/test"
    assert "freecad_cmd" in d


def test_system_config_from_dict():
    cfg = SystemConfig.from_dict({"freecad_path": "/custom"})
    assert cfg.freecad_path == "/custom"


# ---- ModuleConfig ----

def test_module_config_defaults_all_enabled():
    cfg = ModuleConfig()
    enabled = cfg.get_enabled_modules()
    assert "geometry" in enabled
    assert "holes" in enabled


def test_module_config_disabled_list():
    cfg = ModuleConfig()
    cfg.geometry = False
    disabled = cfg.get_disabled_modules()
    assert "geometry" in disabled


def test_module_config_roundtrip():
    cfg = ModuleConfig()
    cfg.holes = False
    d = cfg.to_dict()
    cfg2 = ModuleConfig.from_dict(d)
    assert cfg2.holes is False
    assert cfg2.geometry is True


def test_module_config_from_dict_ignores_unknown():
    cfg = ModuleConfig.from_dict({"geometry": True, "nonexistent_field": True})
    assert cfg.geometry is True


# ---- PricingConfig ----

def test_pricing_config_defaults():
    cfg = PricingConfig()
    assert cfg.cnc_draaien_klein == 55.0
    assert cfg.laser_snijden == 70.0


def test_pricing_config_roundtrip():
    cfg = PricingConfig(cnc_draaien_klein=100.0)
    d = cfg.to_dict()
    cfg2 = PricingConfig.from_dict(d)
    assert cfg2.cnc_draaien_klein == 100.0


# ---- MaterialPricesConfig ----

def test_material_prices_get_price():
    cfg = MaterialPricesConfig()
    assert cfg.get_price("steel_s235") == 1.20
    assert cfg.get_price("nonexistent") == 1.50  # fallback


def test_material_prices_roundtrip():
    cfg = MaterialPricesConfig(steel_s235=2.0)
    d = cfg.to_dict()
    cfg2 = MaterialPricesConfig.from_dict(d)
    assert cfg2.steel_s235 == 2.0


# ---- CostColumnsConfig ----

def test_cost_columns_enabled():
    cfg = CostColumnsConfig()
    enabled = cfg.get_enabled_columns()
    assert "snijden" in enabled


def test_cost_columns_disable():
    cfg = CostColumnsConfig(snijden=False)
    enabled = cfg.get_enabled_columns()
    assert "snijden" not in enabled


# ---- PipelineConfig ----

def test_pipeline_config_defaults():
    cfg = create_default_config("test.step")
    assert cfg.step_file == "test.step"
    assert cfg.modules.geometry is True


def test_pipeline_config_save_load(tmp_path):
    cfg = create_default_config("test.step")
    cfg.material = "steel_304"
    path = str(tmp_path / "config.json")
    cfg.save(path)
    loaded = PipelineConfig.load(path)
    assert loaded.material == "steel_304"
    assert loaded.modules.geometry is True


def test_minimal_config():
    cfg = create_minimal_config("test.step")
    assert cfg.modules.geometry is True
    assert cfg.modules.iso2768_tolerances is False
    assert cfg.modules.cost_estimation is False


# ---- apply_module_toggles ----

def test_toggle_disable_group():
    cfg = ModuleConfig()
    apply_module_toggles(cfg, disable=["iso"])
    assert cfg.iso2768_tolerances is False
    assert cfg.iso286_fits is False
    assert cfg.geometry is True  # untouched


def test_toggle_enable_group():
    cfg = ModuleConfig()
    cfg.iso2768_tolerances = False
    apply_module_toggles(cfg, enable=["iso"])
    assert cfg.iso2768_tolerances is True


def test_toggle_all_group():
    cfg = ModuleConfig()
    apply_module_toggles(cfg, disable=["all"])
    assert cfg.geometry is False
    assert cfg.holes is False


def test_toggle_individual_module():
    cfg = ModuleConfig()
    apply_module_toggles(cfg, disable=["geometry"])
    assert cfg.geometry is False
    assert cfg.holes is True


# ---- MODULE_GROUPS / MODULE_NAMES ----

def test_module_groups_all_is_none():
    assert MODULE_GROUPS["all"] is None


def test_module_names_cover_basic():
    for module in MODULE_GROUPS["basic"]:
        assert module in MODULE_NAMES
```

- [ ] **Step 2: Run tests**

Run: `python -m pytest manufacturing_pipeline/tests/test_core_config.py -v`
Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add manufacturing_pipeline/tests/test_core_config.py
git commit -m "test(core): add comprehensive pytest coverage for config dataclasses"
```

---

## Task 4: Test `profiler.py`

**Files:**
- Create: `manufacturing_pipeline/tests/test_core_profiler.py`

- [ ] **Step 1: Write the tests**

```python
# manufacturing_pipeline/tests/test_core_profiler.py
import json
import os
import pytest

from manufacturing_pipeline.core.profiler import AnalysisProfiler


def test_profiler_step_timing():
    p = AnalysisProfiler("test.step", 1.0)
    with p.step("Load", 1, 3):
        pass  # instant
    assert len(p.steps) == 1
    assert p.steps[0]["name"] == "Load"
    assert p.steps[0]["elapsed"] >= 0
    assert p.steps[0]["status"] == "OK"


def test_profiler_sub_step():
    p = AnalysisProfiler("test.step", 1.0)
    with p.step("Detect", 1, 1):
        with p.sub_step("Cylindrical"):
            pass
        p.set_sub_count("Cylindrical", 5)
    assert len(p.steps[0]["sub_steps"]) == 1
    assert p.steps[0]["sub_steps"][0]["name"] == "Cylindrical"
    assert p.steps[0]["sub_steps"][0]["count"] == 5


def test_profiler_count():
    p = AnalysisProfiler("test.step", 1.0)
    p.count("faces", 100)
    p.count("holes", 7)
    assert p.counts == {"faces": 100, "holes": 7}


def test_profiler_step_failure():
    p = AnalysisProfiler("test.step", 1.0)
    with pytest.raises(ValueError):
        with p.step("Bad step", 1, 1):
            raise ValueError("boom")
    assert p.steps[0]["status"] == "FAIL"
    assert p.steps[0]["error"] == "boom"


def test_profiler_save_json(tmp_path):
    p = AnalysisProfiler("part.step", 2.5)
    with p.step("Load", 1, 2):
        pass
    with p.step("Detect", 2, 2):
        with p.sub_step("Shaped", count=3):
            pass
    p.count("holes", 3)
    path = p.save_json(str(tmp_path))
    assert os.path.exists(path)
    with open(path) as f:
        data = json.load(f)
    assert data["part_name"] == "part.step"
    assert data["file_size_mb"] == 2.5
    assert len(data["steps"]) == 2
    assert data["counts"]["holes"] == 3


def test_profiler_print_summary(capsys):
    p = AnalysisProfiler("test.step", 1.0)
    with p.step("Load", 1, 1):
        pass
    p.print_summary()
    captured = capsys.readouterr()
    assert "test.step" in captured.out
    assert "Load" in captured.out


def test_profiler_emit_callback():
    events = []
    def callback(event, summary):
        events.append(event)

    p = AnalysisProfiler("test.step", 1.0, event_callback=callback)
    with p.step("Load", 1, 1):
        pass
    # stage_start + stage_end = 2 events
    assert len(events) >= 2
    assert events[0]["type"] == "stage_start"
    assert events[-1]["type"] == "stage_end"


def test_profiler_emit_custom_event():
    events = []
    def callback(event, summary):
        events.append(event)

    p = AnalysisProfiler("test.step", 1.0, event_callback=callback)
    with p.step("Load", 1, 1):
        p.emit("custom_event", "Load", {"key": "val"})
    custom = [e for e in events if e["type"] == "custom_event"]
    assert len(custom) == 1
    assert custom[0]["payload"] == {"key": "val"}


def test_profiler_fmt_time():
    assert AnalysisProfiler._fmt_time(0.5) == "0.50s"
    assert AnalysisProfiler._fmt_time(90.0) == "1m 30s"


def test_profiler_skip_status():
    p = AnalysisProfiler("test.step", 1.0)
    with p.step("Optional", 1, 1) as s:
        s["status"] = "SKIP"
    assert p.steps[0]["status"] == "SKIP"
```

- [ ] **Step 2: Run tests**

Run: `python -m pytest manufacturing_pipeline/tests/test_core_profiler.py -v`
Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add manufacturing_pipeline/tests/test_core_profiler.py
git commit -m "test(core): add pytest coverage for AnalysisProfiler"
```

---

## Task 5: Test `analysis_pipeline.py` (criterion builders + classification helpers)

**Files:**
- Create: `manufacturing_pipeline/tests/test_core_analysis_pipeline.py`

- [ ] **Step 1: Write the tests**

```python
# manufacturing_pipeline/tests/test_core_analysis_pipeline.py
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
    # All gates should be entered when winner is "4"
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
```

- [ ] **Step 2: Run tests**

Run: `python -m pytest manufacturing_pipeline/tests/test_core_analysis_pipeline.py -v`
Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add manufacturing_pipeline/tests/test_core_analysis_pipeline.py
git commit -m "test(core): add pytest coverage for analysis_pipeline criterion builders"
```

---

## Task 6: Test `unfold_integration.py`

**Files:**
- Create: `manufacturing_pipeline/tests/test_core_unfold_integration.py`

- [ ] **Step 1: Write the tests**

```python
# manufacturing_pipeline/tests/test_core_unfold_integration.py
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
```

- [ ] **Step 2: Run tests**

Run: `python -m pytest manufacturing_pipeline/tests/test_core_unfold_integration.py -v`
Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add manufacturing_pipeline/tests/test_core_unfold_integration.py
git commit -m "test(core): add pytest coverage for unfold_integration helpers"
```

---

## Task 7: Test `file_utils.py` and wire it to `paths.py`

**Files:**
- Modify: `manufacturing_pipeline/core/file_utils.py`
- Create: `manufacturing_pipeline/tests/test_core_file_utils.py`

- [ ] **Step 1: Write the tests**

```python
# manufacturing_pipeline/tests/test_core_file_utils.py
import os
import pytest

from manufacturing_pipeline.core.file_utils import (
    find_step_files,
    get_output_dir,
)


def test_find_step_files_empty_dir(tmp_path):
    assert find_step_files(str(tmp_path)) == []


def test_find_step_files_finds_step(tmp_path):
    (tmp_path / "part.step").write_text("STEP")
    (tmp_path / "other.txt").write_text("nope")
    files = find_step_files(str(tmp_path))
    assert len(files) == 1
    assert files[0].endswith("part.step")


def test_find_step_files_finds_stp(tmp_path):
    (tmp_path / "part.stp").write_text("STEP")
    files = find_step_files(str(tmp_path))
    assert len(files) == 1


def test_find_step_files_case_insensitive(tmp_path):
    (tmp_path / "part.STEP").write_text("STEP")
    files = find_step_files(str(tmp_path))
    assert len(files) == 1


def test_find_step_files_recursive(tmp_path):
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "nested.step").write_text("STEP")
    files = find_step_files(str(tmp_path))
    assert len(files) == 1
    assert "nested.step" in files[0]


def test_find_step_files_nonexistent_dir():
    assert find_step_files("/nonexistent/path/xyz") == []


def test_get_output_dir_creates_dir(tmp_path, monkeypatch):
    monkeypatch.setattr("manufacturing_pipeline.core.file_utils.OUTPUT_DIR", str(tmp_path))
    out_dir, name = get_output_dir("/fake/path/mypart.step")
    assert name == "mypart"
    assert out_dir.endswith("mypart")
    assert os.path.isdir(out_dir)


def test_get_output_dir_strips_extension(tmp_path, monkeypatch):
    monkeypatch.setattr("manufacturing_pipeline.core.file_utils.OUTPUT_DIR", str(tmp_path))
    _, name = get_output_dir("/path/to/complex.name.step")
    assert name == "complex.name"
```

- [ ] **Step 2: Run tests**

Run: `python -m pytest manufacturing_pipeline/tests/test_core_file_utils.py -v`
Expected: All tests PASS

- [ ] **Step 3: Update file_utils.py to import from paths.py**

In `manufacturing_pipeline/core/file_utils.py`, replace lines 13-15:

```python
# Old:
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PARTS_DIR = os.path.join(PROJECT_ROOT, "data", "input")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "data", "output")

# New:
from manufacturing_pipeline.core.paths import PARTS_DIR, OUTPUT_DIR
```

Also remove the now-unused `import subprocess` on line 9.

- [ ] **Step 4: Run tests again to verify nothing broke**

Run: `python -m pytest manufacturing_pipeline/tests/test_core_file_utils.py manufacturing_pipeline/tests/test_core_paths.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add manufacturing_pipeline/core/file_utils.py manufacturing_pipeline/tests/test_core_file_utils.py
git commit -m "refactor(core): file_utils uses paths.py, add pytest coverage"
```

---

## Task 8: Test `runtime_reporting.py`

**Files:**
- Create: `manufacturing_pipeline/tests/test_core_runtime_reporting.py`

- [ ] **Step 1: Write the test**

```python
# manufacturing_pipeline/tests/test_core_runtime_reporting.py
"""
runtime_reporting.run_debug requires OCP and a real STEP file.
We test that the module imports cleanly and the function signature exists.
Full integration testing requires STEP fixtures.
"""
import pytest

from manufacturing_pipeline.core.runtime_reporting import run_debug


def test_run_debug_callable():
    assert callable(run_debug)


def test_run_debug_rejects_missing_file():
    """run_debug should fail on a non-existent file (load_step_file raises)."""
    with pytest.raises(Exception):
        run_debug("/nonexistent/file.step")
```

- [ ] **Step 2: Run test**

Run: `python -m pytest manufacturing_pipeline/tests/test_core_runtime_reporting.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add manufacturing_pipeline/tests/test_core_runtime_reporting.py
git commit -m "test(core): add smoke test for runtime_reporting"
```

---

## Task 9: Remove duplicated helpers from `runtime_analysis.py`

This is the big dedup task. `runtime_analysis.py` contains inner functions that are exact copies of functions already extracted to `analysis_pipeline.py`.

**Files:**
- Modify: `manufacturing_pipeline/core/runtime_analysis.py`

**Duplicated functions to remove (inner defs inside `run_analysis`):**
| Inner function in `run_analysis()` | Already exists in `analysis_pipeline.py` as |
|---|---|
| `_primary_solid_for_classification()` (line 113) | `primary_solid_for_classification()` |
| `_comparison_criterion()` (line 132) | `comparison_criterion()` |
| `_range_criterion()` (line 162) | `range_criterion()` |
| `_boolean_criterion()` (line 190) | `boolean_criterion()` |
| `_json_safe()` (line 346) | `json_safe()` |
| `_normalize_step0_review()` (line 363) | `normalize_step0_review()` |
| `_build_legacy_gate_flow()` (line 401) | `build_legacy_gate_flow()` |
| `_build_classification_visuals()` (line 464) | `build_classification_visuals()` |

- [ ] **Step 1: Verify the module-level imports already exist**

At the top of `runtime_analysis.py` (lines 55-63), the module already imports these from `analysis_pipeline.py`:

```python
from manufacturing_pipeline.core.analysis_pipeline import (
    comparison_criterion,
    range_criterion,
    boolean_criterion,
    json_safe,
    primary_solid_for_classification,
    normalize_step0_review,
    build_legacy_gate_flow,
    build_classification_visuals,
)
```

These module-level imports are currently **shadowed** by the inner function definitions. The inner definitions must be removed.

- [ ] **Step 2: Delete the 8 duplicated inner functions**

Inside `run_analysis()`, delete these blocks entirely:
- `def _primary_solid_for_classification(cq_shape):` (lines ~113-130)
- `def _comparison_criterion(step, name, actual, threshold, operator, note=None):` (lines ~132-160)
- `def _range_criterion(step, name, actual, minimum, maximum, note=None):` (lines ~162-188)
- `def _boolean_criterion(step, name, actual, should_be, note=None):` (lines ~190-200)
- `def _json_safe(value):` (lines ~346-361)
- `def _normalize_step0_review(step0_trace):` (lines ~363-399)
- `def _build_legacy_gate_flow(legacy_trace, criteria):` (lines ~401-462)
- `def _build_classification_visuals(analysis, legacy_class, ...):` (lines ~464-527)

- [ ] **Step 3: Update call sites inside `run_analysis()` to use the module-level names**

Replace all calls from underscore-prefixed to non-prefixed:
- `_primary_solid_for_classification(` -> `primary_solid_for_classification(`
- `_comparison_criterion(` -> `comparison_criterion(`
- `_range_criterion(` -> `range_criterion(`
- `_boolean_criterion(` -> `boolean_criterion(`
- `_json_safe(` -> (no calls remain -- was only used inside the deleted inner functions)
- `_normalize_step0_review(` -> (no calls remain -- was only used inside `_build_classification_visuals`)
- `_build_legacy_gate_flow(` -> (no calls remain)
- `_build_classification_visuals(` -> `build_classification_visuals(`

The key call sites to update:
- `_compute_classification_thresholds()` inner function: update its calls from `_comparison_criterion` / `_range_criterion` / `_boolean_criterion` to `comparison_criterion` / `range_criterion` / `boolean_criterion`
- Line ~659: `_primary_solid_for_classification(shape)` -> `primary_solid_for_classification(shape)`
- Line ~690: `_build_classification_visuals(...)` -> `build_classification_visuals(...)`

- [ ] **Step 4: Also update path constants to use paths.py**

At the top of `runtime_analysis.py`, replace lines 18-26:

```python
# Old:
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
CONFIG_DIR = os.path.join(DATA_DIR, "config")
DB_DIR = os.path.join(DATA_DIR, "db")
PARTS_DIR = os.path.join(DATA_DIR, "input")
OUTPUT_DIR = os.path.join(DATA_DIR, "output")
PIPELINE_DIR = os.path.join(PROJECT_ROOT, "manufacturing_pipeline")
SCRIPTS_DIR = os.path.join(PIPELINE_DIR, "scripts")

# New:
from manufacturing_pipeline.core.paths import (
    PROJECT_ROOT, DATA_DIR, CONFIG_DIR, DB_DIR,
    PARTS_DIR, OUTPUT_DIR, PIPELINE_DIR, SCRIPTS_DIR,
)
```

- [ ] **Step 5: Run all tests**

Run: `python -m pytest -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add manufacturing_pipeline/core/runtime_analysis.py
git commit -m "refactor(core): remove 8 duplicated inner functions from runtime_analysis.py

run_analysis() now calls the already-extracted module-level functions from
analysis_pipeline.py instead of shadowing them with identical inner defs.
Path constants now come from paths.py."
```

---

## Task 10: Update path constants in `runtime_unfold.py`

**Files:**
- Modify: `manufacturing_pipeline/core/runtime_unfold.py`

- [ ] **Step 1: Replace duplicated path constants**

At the top of `runtime_unfold.py`, replace lines 11-18:

```python
# Old:
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
CONFIG_DIR = os.path.join(DATA_DIR, "config")
DB_DIR = os.path.join(DATA_DIR, "db")
PARTS_DIR = os.path.join(DATA_DIR, "input")
OUTPUT_DIR = os.path.join(DATA_DIR, "output")
PIPELINE_DIR = os.path.join(PROJECT_ROOT, "manufacturing_pipeline")
SCRIPTS_DIR = os.path.join(PIPELINE_DIR, "scripts")

# New:
from manufacturing_pipeline.core.paths import PIPELINE_DIR, SCRIPTS_DIR
```

Keep the `FREECAD_PYTHON`, `HOST_PYTHON`, and `sys.path` manipulation lines.

- [ ] **Step 2: Run all tests**

Run: `python -m pytest -v`
Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add manufacturing_pipeline/core/runtime_unfold.py
git commit -m "refactor(core): runtime_unfold uses paths.py for path constants"
```

---

## Task 11: Slim down `utils.py` re-export shim

**Files:**
- Modify: `manufacturing_pipeline/core/utils.py`
- Modify: `manufacturing_pipeline/cli.py`
- Modify: `manufacturing_pipeline/api/analysis_service.py`
- Modify: `manufacturing_pipeline/tests/test_basic.py`

The current `utils.py` is a wildcard `import *` shim. We'll reduce it to only re-export what external consumers actually need (based on the import analysis).

- [ ] **Step 1: Determine what consumers import from `utils`**

From the import analysis:
- `cli.py` imports: `PROJECT_ROOT, DATA_DIR, DB_DIR, PARTS_DIR, OUTPUT_DIR, find_step_files, select_step_file, get_output_dir, run_analysis, run_debug, process_single_file, get_file_hash, load_cache, save_cache, cache_result, CACHE_FILE`
- `analysis_service.py` imports: `run_analysis, get_output_dir`
- `file_utils.py` imports: `run_analysis` (circular -- for `process_single_file`)
- `test_basic.py` imports: `get_output_dir, PROJECT_ROOT`

- [ ] **Step 2: Update `cli.py` to import from specific submodules**

Replace the import block at line 17 of `cli.py`:

```python
# Old:
from manufacturing_pipeline.core.utils import (
    PROJECT_ROOT, DATA_DIR, DB_DIR, PARTS_DIR, OUTPUT_DIR,
    find_step_files, select_step_file, get_output_dir,
    run_analysis, run_debug, process_single_file,
    get_file_hash, load_cache, save_cache, cache_result,
)

# New:
from manufacturing_pipeline.core.paths import PROJECT_ROOT, DATA_DIR, DB_DIR, PARTS_DIR, OUTPUT_DIR
from manufacturing_pipeline.core.file_utils import find_step_files, select_step_file, get_output_dir, process_single_file
from manufacturing_pipeline.core.runtime_analysis import run_analysis
from manufacturing_pipeline.core.runtime_reporting import run_debug
from manufacturing_pipeline.core.cache import get_file_hash, load_cache, save_cache, cache_result, CACHE_FILE
```

Also update the `CACHE_FILE` import at line ~274 (remove the separate `from manufacturing_pipeline.core.utils import CACHE_FILE` -- it's now in the main import block).

- [ ] **Step 3: Update `analysis_service.py`**

Replace:
```python
# Old:
from manufacturing_pipeline.core.utils import (run_analysis, get_output_dir,)

# New:
from manufacturing_pipeline.core.runtime_analysis import run_analysis
from manufacturing_pipeline.core.file_utils import get_output_dir
```

- [ ] **Step 4: Update `test_basic.py`**

Replace:
```python
# Old:
from manufacturing_pipeline.core.utils import get_output_dir, PROJECT_ROOT

# New:
from manufacturing_pipeline.core.paths import PROJECT_ROOT
from manufacturing_pipeline.core.file_utils import get_output_dir
```

- [ ] **Step 5: Rewrite `utils.py` as a thin compatibility shim**

```python
"""Compatibility shim -- imports forwarded to specific submodules.

Prefer importing from the specific submodule directly:
  - paths: PROJECT_ROOT, DATA_DIR, etc.
  - cache: get_file_hash, load_cache, etc.
  - file_utils: find_step_files, get_output_dir, etc.
  - runtime_analysis: run_analysis
  - runtime_reporting: run_debug
"""

# Keep backward-compat for any external/script imports we may have missed.
from manufacturing_pipeline.core.paths import *  # noqa: F401,F403
from manufacturing_pipeline.core.runtime_analysis import run_analysis  # noqa: F401
from manufacturing_pipeline.core.runtime_reporting import run_debug  # noqa: F401
from manufacturing_pipeline.core.cache import (  # noqa: F401
    get_file_hash, load_cache, save_cache, get_cached_result, cache_result, CACHE_FILE,
)
from manufacturing_pipeline.core.file_utils import (  # noqa: F401
    find_step_files, select_step_file, get_output_dir, process_single_file, process_batch,
)
```

- [ ] **Step 6: Run all tests**

Run: `python -m pytest -v`
Expected: All tests PASS

- [ ] **Step 7: Commit**

```bash
git add manufacturing_pipeline/core/utils.py manufacturing_pipeline/cli.py manufacturing_pipeline/api/analysis_service.py manufacturing_pipeline/tests/test_basic.py
git commit -m "refactor(core): replace wildcard re-exports with explicit imports

Consumers now import from specific submodules. utils.py kept as thin
backward-compat shim with explicit named imports."
```

---

## Task 12: Final validation -- run full test suite

- [ ] **Step 1: Run full pytest suite**

Run: `python -m pytest -v`
Expected: All tests PASS, including the existing tests and all new tests.

- [ ] **Step 2: Verify line count reduction in runtime_analysis.py**

Run: `wc -l manufacturing_pipeline/core/runtime_analysis.py`
Expected: ~950-1000 lines (down from 1403), because ~400 lines of duplicated inner functions were removed.

- [ ] **Step 3: Verify no remaining path constant duplication**

Run: `grep -rn "PROJECT_ROOT = os.path" manufacturing_pipeline/core/`
Expected: Only `paths.py` should define `PROJECT_ROOT`.

- [ ] **Step 4: Commit any fixups**

If any minor fixups are needed, commit them:
```bash
git add -u
git commit -m "fix(core): post-refactor cleanup"
```

---

## Summary

| Task | What | Tests added |
|------|------|-------------|
| 1 | Create `paths.py` | 6 |
| 2 | Test + wire `cache.py` | 7 |
| 3 | Test `config.py` | 27 |
| 4 | Test `profiler.py` | 10 |
| 5 | Test `analysis_pipeline.py` | 35 |
| 6 | Test `unfold_integration.py` | 19 |
| 7 | Test + wire `file_utils.py` | 9 |
| 8 | Test `runtime_reporting.py` | 2 |
| 9 | Dedup `runtime_analysis.py` | 0 (covered by existing) |
| 10 | Wire `runtime_unfold.py` | 0 |
| 11 | Slim `utils.py` + update consumers | 0 |
| 12 | Final validation | 0 |
| **Total** | | **~115 tests** |
