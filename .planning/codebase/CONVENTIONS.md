# Coding Conventions

**Analysis Date:** 2026-03-25

## Naming Patterns

**Files:**
- Use `snake_case.py` for all Python modules: `step_processing.py`, `cache_manager.py`, `xml_exporter.py`
- Test files: `test_<subject>.py` (e.g., `test_router.py`, `test_feature_layer1.py`)
- No `__init__.py` in test directories

**Functions:**
- `snake_case` for all functions: `detect_holes()`, `load_step_file()`, `get_output_dir()`
- Private functions prefixed with underscore: `_normalize_step_file()`, `_load_step_via_xcaf()`, `_build_timeline()`
- Helper factory functions prefixed with underscore in tests: `_sample_result()`, `_hole()`, `_stub_cq()`

**Classes:**
- `PascalCase` for classes: `AnalysisProfiler`, `PDFReportGenerator`, `SystemConfig`
- Dataclasses used heavily for data containers: `HoleFeature`, `BendInfo`, `PartAnalysis`
- Enums in `PascalCase` with `UPPER_SNAKE` values: `PartType.PLAAT`, `RouteCategory.PROFIEL`

**Variables:**
- `snake_case` for locals and parameters
- `UPPER_SNAKE_CASE` for module-level constants: `PROJECT_ROOT`, `STANDARD_THICKNESSES`, `STEP_HEADER`
- Boolean capability flags: `HAS_OCP`, `HAS_CADQUERY`, `HAS_PART_ANALYZER`

## Code Style

**Formatting:**
- No enforced formatter (no `.prettierrc`, `black.toml`, or `pyproject.toml` with formatting config)
- 4-space indentation throughout
- No consistent line length limit; some lines exceed 120 characters
- Single blank line between functions, double blank line between top-level definitions (inconsistent)

**Linting:**
- No linter configured (no `.flake8`, `.pylintrc`, `ruff.toml`)
- Minimal `pytest.ini` for test configuration only

**String Formatting:**
- f-strings predominate: `f"STEP file not found: {filepath}"`
- Older code uses `%` formatting in some logging calls: `logger.warning("Could not load %s", path)`

## Import Organization

**Order (observed pattern):**
1. Standard library imports (`os`, `sys`, `math`, `json`, `hashlib`)
2. Third-party imports (`cadquery`, `OCP.*`, `reportlab`, `fastapi`, `pydantic`)
3. Internal imports (`manufacturing_pipeline.core.*`, `manufacturing_pipeline.analysis.*`)

**No enforced import ordering.** Order is generally followed but not tooled.

**Path Aliases:**
- No path aliases configured. All imports use full package paths: `from manufacturing_pipeline.core.config import SystemConfig`
- Some files manually insert `sys.path` entries: `sys.path.insert(0, str(Path(__file__).parent.parent.parent))`

**Conditional Imports:**
- Extensively used for optional dependencies with boolean flags:
```python
try:
    import cadquery as cq
    HAS_CADQUERY = True
except ImportError:
    HAS_CADQUERY = False
```
- Pattern used in: `manufacturing_pipeline/reporting/xml_exporter.py`, `manufacturing_pipeline/analysis/sheetmetal_analysis.py`

**Lazy Imports:**
- `cli.py` uses lazy imports to keep quick mode fast:
```python
def _import_full_pipeline():
    """Lazy import of full pipeline modules (only needed for --full mode)."""
    from manufacturing_pipeline.analysis.step_processing import load_step_file
    # ...
    return {k: v for k, v in locals().items()}
```

## Error Handling

**Primary Pattern: try/except with fallback:**
- Functions wrap risky operations in try/except and return `None` or a safe default
- Multiple fallback strategies (e.g., XCAF reader falls back to CadQuery importer)
- `step_processing.py` has 23 try/except blocks - defensive against corrupt CAD data

```python
# Typical pattern in analysis code
try:
    result = risky_operation()
except Exception:
    return None
```

**Validation at boundaries:**
- Entry points use explicit checks: `if not filepath: raise ValueError(...)`
- File existence checked before processing: `if not os.path.exists(filepath): raise FileNotFoundError(...)`

**Graceful degradation is a core principle:**
- If unfold fails, fall back to 3D analysis
- If XCAF crashes (subprocess segfault), use CadQuery fallback
- If optional modules are unavailable, skip those features

## Logging

**Mixed approach - not standardized:**
- Newer modules (`router.py`, `classification.py`, `cut_features.py`, `xcaf_reader.py`) use `logging.getLogger(__name__)` or named loggers
- Older/core modules (`core/utils.py`, `cli.py`) use `print()` statements extensively (~100 print calls in `utils.py`)
- API modules use neither - rely on FastAPI's built-in logging

**Logger naming:**
- `logging.getLogger(__name__)` in `xcaf_reader.py`
- Named loggers: `logging.getLogger("profile_router")` in `router.py`
- Named loggers: `logging.getLogger("ales.classification_step0")` in `classification.py`

**Guideline for new code:** Use `logging.getLogger(__name__)` for consistency with newer modules.

## Docstrings

**Module-level docstrings:**
- Present on most modules, often bilingual (Dutch + English)
- Format: triple-quoted block with description of purpose and features
- Example from `cut_features.py`: includes sections for WANNEER, WAT, strategie
- Example from `iso_standards.py`: lists which standards are implemented

**Function docstrings:**
- Short one-line docstrings on utility functions: `"""Calculate MD5 hash of a file."""`
- Longer docstrings on complex functions use Args/Returns format (inconsistent)
- Many functions lack docstrings entirely, especially in `utils.py` and `step_processing.py`

**Class docstrings:**
- Brief one-line docstrings on dataclasses: `"""Kantbank gereedschap (matrijs + stempel)"""`
- Dutch terminology common in class/field descriptions

## Comments

**Section Dividers:**
- Heavy use of `# ====...====` banner comments to divide modules into sections
- Used in 13 source files including `utils.py`, `step_processing.py`, `iso_standards.py`
```python
# =============================================================================
# STANDAARD PLAATDIKTES (ISO / DIN / NEN)
# =============================================================================
```

**Inline Comments:**
- Business rule explanations in Dutch: `# Vlakke plaat (kan gebogen zijn)`
- Technical notes in English: `# CadQuery importer fallback (existing behavior)`
- Mixed language is common and accepted

## Language Convention

**Code identifiers:** English (`detect_holes`, `load_step_file`, `BendTool`)

**Domain terminology:** Dutch in:
- Enum values: `PLAAT`, `KOKER`, `DRAAISTUK`, `FREESDEEL`
- Docstrings and comments: `"Pad naar de Python executable van FreeCAD"`
- User-facing output: `gaten`, `zettingen`, `plaatwerk`
- Configuration labels: `werkvoorbereiding`, `hoekprofiel`

**Guideline:** Use English for code identifiers, Dutch for domain-specific terminology and user-facing strings.

## Data Modeling

**Dataclasses for domain objects:**
- `@dataclass` used extensively: `HoleFeature`, `BendInfo`, `PartAnalysis`, `BendTool`, `SystemConfig`
- Location: `manufacturing_pipeline/core/models.py` for shared types, inline in analysis modules for module-specific types

**Enums for classifications:**
- `Enum` for categorical types: `PartType`, `RouteCategory`, `ISO2768Class`, `ValidationStatus`
- Values are lowercase strings matching Dutch manufacturing terms

**Pydantic for API boundaries:**
- `BaseModel` used in `manufacturing_pipeline/api/schemas.py` for request/response validation
- Strict separation: Pydantic only in API layer, dataclasses everywhere else

**Dicts for intermediate data:**
- Analysis results passed as plain dicts between pipeline stages
- No strict schema enforcement for internal pipeline data flow

## Configuration Pattern

**Dataclass-based config:**
- `SystemConfig` in `manufacturing_pipeline/core/config.py` - system paths
- `ModuleConfig` in same file - feature flags for analysis modules
- `PipelineConfig` wraps both

**Environment variables:**
- Read via `os.environ.get()` with defaults: `SystemConfig.from_env()`
- API config in `manufacturing_pipeline/api/config.py` reads env vars directly

**File-based config:**
- `data/config/pipeline_config.json` for persistent pipeline settings
- JSON format, loaded/saved via `PipelineConfig` methods

## Module Constants

**Constants defined at module top-level as plain Python values:**
```python
STANDARD_THICKNESSES = [0.5, 0.6, 0.7, ...]
STANDARD_BEND_ANGLES = [30, 45, 60, 90, ...]
ISO2768_LINEAR_TOLERANCES = {(0.5, 3): {"f": 0.05, ...}, ...}
```

**Path constants in `core/utils.py`:**
```python
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
OUTPUT_DIR = os.path.join(DATA_DIR, "output")
```

---

*Convention analysis: 2026-03-25*
