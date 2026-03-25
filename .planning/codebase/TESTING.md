# Testing Patterns

**Analysis Date:** 2026-03-25

## Test Framework

**Runner:**
- pytest (version managed via `requirements.txt`)
- Config: `pytest.ini`

**Assertion Library:**
- pytest native `assert` statements (newer tests)
- `unittest.TestCase` assertions in older tests (`self.assertEqual`, `self.assertIn`)

**Run Commands:**
```bash
python -m pytest                    # Run all tests
python -m pytest -v                 # Verbose output
python -m pytest -k test_router     # Run specific test file/pattern
```

## Test Configuration

**`pytest.ini`:**
```ini
[pytest]
testpaths = manufacturing_pipeline/tests
python_files = test_*.py
addopts = --ignore=manufacturing_pipeline/tests/legacy
filterwarnings =
    ignore:.*addParseAction.*deprecated.*:DeprecationWarning:ezdxf.queryparser
    ignore:.*oneOf.*deprecated.*:DeprecationWarning:ezdxf.queryparser
    ignore:.*setResultsName.*deprecated.*:DeprecationWarning:ezdxf.queryparser
    ignore:.*infixNotation.*deprecated.*:DeprecationWarning:ezdxf.queryparser
```

- Legacy tests in `manufacturing_pipeline/tests/legacy/` are excluded from default runs
- ezdxf deprecation warnings are suppressed

## Test File Organization

**Location:** `manufacturing_pipeline/tests/`

**No `conftest.py` or `__init__.py`** in test directory.

**Naming:** `test_<subject>.py`

**Active test files (7 files, 725 lines total):**

| File | Lines | Tests | Style | Subject |
|------|-------|-------|-------|---------|
| `test_basic.py` | 41 | 4 | unittest | Config defaults, utils |
| `test_router.py` | 78 | 14 | pytest functions | Profile routing/classification |
| `test_xml_export.py` | 59 | 2 | pytest functions | XML export output |
| `test_display_edges.py` | 29 | 1 | pytest function | Edge extraction geometry |
| `test_feature_layer1.py` | 233 | 6 | pytest functions | Cut feature detection logic |
| `test_timeline_api.py` | 171 | 3 | unittest | Timeline API endpoints |
| `test_step_naming_fallback_regression.py` | 114 | 2 | unittest | STEP naming regression |

**Legacy tests (excluded from runs):**
- `legacy/test_final_verification.py` - Plate detection verification script
- `legacy/test_bom_to_xml.py`
- `legacy/test_xml_exporter_dxf.py`

## Test Styles

**Two coexisting styles:**

**Style 1 - pytest functions (preferred for new tests):**
```python
def test_xml_export_writes_file(tmp_path: Path) -> None:
    """XML export should generate a non-empty file for a minimal result payload."""
    output_path = tmp_path / "sample_part.xml"
    export_to_xml(_sample_result(), output_path)
    assert output_path.exists()
    assert output_path.stat().st_size > 0
```

**Style 2 - unittest.TestCase (older tests):**
```python
class TestConfig(unittest.TestCase):
    def test_system_config_defaults(self):
        config = SystemConfig()
        self.assertIn("FreeCAD.app", config.freecad_path)
```

**Guideline:** Use pytest-style functions for new tests. Only use unittest when testing async code with `asyncio.run()` workaround.

## Test Patterns

**Helper factories with underscore prefix:**
```python
def _sample_result() -> dict:
    """Minimal export payload compatible with export_to_xml()."""
    return {"file": "sample_part.stp", "category": "plaat", ...}

def _hole(diameter: float, depth: float) -> SimpleNamespace:
    """Create a minimal hole object compatible with cut_features logic."""
    return SimpleNamespace(diameter=diameter, depth=depth, ...)
```

**Dummy/stub classes for complex dependencies:**
```python
class DummyRouteCategory:
    value = "plaat"

class DummyAnalysis:
    route_result = DummyRouteResult()
    unfold_result = {"success": False, "error": "Unfold failed", ...}
```

**SimpleNamespace for lightweight test objects:**
```python
from types import SimpleNamespace
job = SimpleNamespace(job_id="job-1", status="completed", result={...})
```

## Mocking

**Framework:** `pytest.MonkeyPatch` (primary), `unittest.mock.patch` (for API tests)

**MonkeyPatch pattern (used in `test_feature_layer1.py`):**
```python
def _stub_cq(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch CadQuery constructors so we can unit-test feature flow deterministically."""
    monkeypatch.setattr(cut_features.cq, "Solid", lambda shape: shape)
    monkeypatch.setattr(cut_features.cq, "Workplane", _DummyWorkplane)

def test_layer1_countersunk_priority_over_thread(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_cq(monkeypatch)
    _stub_sheet_geometry(monkeypatch)
    monkeypatch.setattr(cut_features, "detect_holes", lambda *_a, **_k: holes)
    # ...
```

**unittest.mock.patch pattern (used in `test_timeline_api.py`):**
```python
with patch("manufacturing_pipeline.api.routes.jobs.get", return_value=job):
    response = asyncio.run(get_job_timeline("job-1"))
```

**What to mock:**
- CadQuery/OCP geometry operations (heavy C++ bindings)
- External service calls (job manager, file I/O)
- ISO standards lookup functions when testing classification logic

**What NOT to mock:**
- The function under test itself
- Simple data transformations
- Enum/dataclass construction

## Fixtures and Test Data

**No shared conftest.py fixtures.** Each test file defines its own helpers.

**Built-in pytest fixtures used:**
- `tmp_path` for file I/O tests (`test_xml_export.py`)
- `monkeypatch` for attribute patching (`test_feature_layer1.py`)

**Inline test data:**
```python
def _sample_result() -> dict:
    return {
        "file": "sample_part.stp",
        "category": "plaat",
        "thickness": 3.0,
        "dimensions": {"length": 120.0, "width": 80.0, "height": 3.0},
        "production": {"bends_total": 2, "holes_total": 4},
        ...
    }
```

**Conditional test skipping for environment-dependent tests:**
```python
@unittest.skipIf(cq is None, "cadquery is not installed")
class TestStepNamingFallbackRegression(unittest.TestCase):
    def _skip_if_missing(self, file_path: Path) -> None:
        if not file_path.exists():
            self.skipTest(f"STEP file not found: {file_path}")
```

## Coverage

**Requirements:** None enforced. No coverage configuration or thresholds.

**No coverage tool configured.** To add:
```bash
pip install pytest-cov
python -m pytest --cov=manufacturing_pipeline --cov-report=html
```

## Test Types Present

**Unit Tests:**
- `test_router.py`: Pure function tests for `map_profile_label()` routing logic
- `test_feature_layer1.py`: Feature extraction logic with mocked geometry
- `test_display_edges.py`: Edge extraction algorithm with synthetic mesh data
- `test_xml_export.py`: XML output generation with mock data

**Integration Tests (light):**
- `test_basic.py`: Tests config loading and path resolution (touches filesystem)
- `test_timeline_api.py`: Tests API route handlers with mocked job manager

**Regression Tests:**
- `test_step_naming_fallback_regression.py`: Tests STEP naming with real STEP files (skipped if files missing)

**No E2E tests.** No tests that run the full pipeline end-to-end.

## Async Testing

**Pattern used in `test_timeline_api.py`:**
```python
class TestTimelineRoute(unittest.TestCase):
    def test_get_job_timeline_completed_job(self):
        job = SimpleNamespace(...)
        with patch("manufacturing_pipeline.api.routes.jobs.get", return_value=job):
            response = asyncio.run(get_job_timeline("job-1"))
        self.assertEqual(response.job_id, "job-1")
```

Uses `asyncio.run()` to test async FastAPI route handlers synchronously. No `pytest-asyncio` configured.

## Test Coverage Gaps

**Well-tested areas:**
- Profile routing logic (`test_router.py` - 14 tests)
- Cut feature extraction with various hole/thread scenarios (`test_feature_layer1.py` - 6 tests)

**Undertested areas:**
- `manufacturing_pipeline/core/utils.py` (1717+ lines, only 4 basic tests)
- `manufacturing_pipeline/analysis/step_processing.py` (large file, only edge extraction tested)
- `manufacturing_pipeline/analysis/sheetmetal_analysis.py` (no dedicated tests)
- `manufacturing_pipeline/analysis/iso_standards.py` (no dedicated tests)
- `manufacturing_pipeline/reporting/report_generator.py` (no tests)
- `manufacturing_pipeline/reporting/excel_exporter.py` (no tests)
- `manufacturing_pipeline/data/cache_manager.py` (no tests)
- `manufacturing_pipeline/cli.py` (no tests)
- Full pipeline flow (no integration test running `run_analysis()`)

## Adding New Tests

**Where to put new tests:** `manufacturing_pipeline/tests/test_<subject>.py`

**Pattern to follow:**
```python
"""Tests for <module description>."""

import pytest
from manufacturing_pipeline.analysis.<module> import <function_under_test>


def _make_<fixture>() -> <Type>:
    """Create minimal test fixture."""
    return <Type>(...)


def test_<function>_<scenario>() -> None:
    """<What should happen in this scenario>."""
    result = <function_under_test>(...)
    assert result.<field> == expected_value
```

**For tests requiring CadQuery mocking:** Follow `test_feature_layer1.py` pattern with `monkeypatch.setattr`.

**For tests requiring file I/O:** Use `tmp_path` fixture.

**For tests requiring real STEP files:** Use `@unittest.skipIf` with file existence check.

---

*Testing analysis: 2026-03-25*
