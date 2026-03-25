# Codebase Structure

**Analysis Date:** 2026-03-25

## Directory Layout

```
/Users/ds/AIdoel/alestest/
├── manufacturing_pipeline/     # ALL Python source code
│   ├── __init__.py
│   ├── __main__.py             # python -m manufacturing_pipeline entry
│   ├── cli.py                  # Unified CLI (quick + full + batch)
│   ├── core/                   # Infrastructure: config, models, utils
│   ├── analysis/               # Business logic: STEP processing, classification, ISO standards
│   ├── data/                   # Persistence: cache, database, SQL schema
│   ├── reporting/              # Output: PDF, Excel, XML, CLI formatting
│   ├── scripts/                # Standalone tools: AAG analyzer, ERP comparator
│   ├── api/                    # REST API: FastAPI app, routes, schemas
│   │   └── static/             # Web frontend + vendored JS libs
│   └── tests/                  # Test suite
│       └── legacy/             # Archived tests
├── viewer/                     # 3D STEP viewer (React + Three.js, Vite)
│   ├── src/                    # JSX components and JS modules
│   ├── dist/                   # Built viewer assets
│   └── public/                 # Static assets
├── deploy/                     # Docker, nginx, deployment scripts
├── docs/                       # Documentation, handovers, plans
│   ├── archive/                # Archived code (profile_pipeline, etc.)
│   ├── plans/                  # Implementation plans
│   ├── scripts/                # Standalone validation scripts
│   └── superpowers/            # Superpowers docs and plans
├── data/                       # Runtime data (gitignored except snapshots)
│   ├── input/                  # STEP files for analysis
│   ├── output/                 # Per-part analysis results
│   ├── parts/                  # Quick-access sample parts
│   ├── config/                 # pipeline_config.json
│   ├── db/                     # SQLite DB + pipeline_cache.json
│   └── snapshots/              # XML status snapshots (git-tracked)
├── run.py                      # Primary entry point (thin wrapper)
├── run_viewer.py               # Launches API + Vite dev server for viewer
├── run_viewer.sh               # Shell script variant of run_viewer
├── requirements.txt            # Python dependencies
├── pytest.ini                  # Pytest configuration
├── CLAUDE.md                   # AI assistant instructions
├── README.md                   # Project documentation
└── holedetection_review.md     # Hole detection analysis document
```

## Directory Purposes

**`manufacturing_pipeline/core/`:**
- Purpose: Shared infrastructure used by all other modules
- Contains: Path constants, config dataclasses, data models, profiler, XCAF reader
- Key files:
  - `utils.py`: Project paths (`PROJECT_ROOT`, `DATA_DIR`, `OUTPUT_DIR`, etc.), `run_analysis()` quick-mode orchestrator, file discovery, cache helpers
  - `config.py`: `SystemConfig` (FreeCAD paths by platform), `PipelineConfig` (module enable/disable)
  - `models.py`: `RouteCategory` enum, `HoleFeature`/`MatchedFeature` dataclasses
  - `profiler.py`: `AnalysisProfiler` with context manager API
  - `pipeline_init.py`: Full-mode initialization helpers (arg normalization, path resolution)
  - `xcaf_reader.py`: XCAF tree traversal for assembly-aware solid extraction

**`manufacturing_pipeline/analysis/`:**
- Purpose: All manufacturing analysis business logic
- Contains: STEP processing, classification, ISO standards, unfold, assembly analysis
- Key files:
  - `step_processing.py`: Core STEP file operations -- load, detect holes (cylindrical + shaped), face analysis, geometry extraction, `precompute_face_properties()`
  - `classification.py`: Step 0 decision tree classifier (primary classification entry point)
  - `classification_variables.py`: Threshold constants for classification decisions
  - `router.py`: Pre-routing classifier mapping profile labels to `RouteCategory`
  - `profile_classifier.py`: Cross-section profile analysis
  - `profile_features.py`: Geometric feature extraction for profile classification
  - `part_analyzer.py`: High-level part classification and reasoning system
  - `sheetmetal_analysis.py`: Thickness, bends, profile classification
  - `iso_standards.py`: ISO 2768/286/1302/68-1/13715 and EN 10025/573 implementations
  - `freecad_unfold.py`: FreeCAD subprocess integration for sheet metal unfolding
  - `pipeline_stages.py`: Stage runner functions for full pipeline (stages 1-17)
  - `assembly_analysis.py`: Multi-solid assembly/BOM analysis
  - `correlation.py`: STEP-to-PDF dimension correlation
  - `werkvoorbereiding.py`: Work preparation and cost table generation
  - `cut_features.py`: Cut feature detection
  - `step0_section_tools.py`: Cross-section tools for Step 0

**`manufacturing_pipeline/data/`:**
- Purpose: Caching and database persistence
- Contains: Cache manager, SQLite wrapper, schema
- Key files:
  - `cache_manager.py`: `CacheManager` (pickle-based), `PipelineRunner`, `PipelineStage` enum with dependency DAG (`STAGE_DEPENDENCIES` dict)
  - `database.py`: `DatabaseManager` for SQLite operations
  - `sql/schema.sql`: Schema with Parts, Holes, PostProcessing, api_jobs tables

**`manufacturing_pipeline/reporting/`:**
- Purpose: All output generation
- Contains: PDF, Excel, XML, DXF, CLI formatters
- Key files:
  - `report_generator.py`: `PDFReportGenerator` using reportlab
  - `cli_output.py`: Terminal formatting functions (`print_section_header`, `print_holes_summary`, etc.)
  - `xml_exporter.py`: `export_to_xml()` for ERP/SpaceClaim
  - `excel_exporter.py`: Excel export in SpaceClaim format (openpyxl)
  - `pdf_processing.py`: PDF dimension extraction (pymupdf)
  - `dxf_metrics_extractor.py`: DXF file metrics

**`manufacturing_pipeline/api/`:**
- Purpose: REST API for remote/Docker deployment
- Contains: FastAPI app, routes, schemas, job management
- Key files:
  - `app.py`: FastAPI application with CORS + API key auth middleware
  - `routes.py`: `/api/v1/` endpoints (POST analyze, GET jobs/{id}, GET health)
  - `analysis_service.py`: Wraps `run_analysis()`, builds timeline events
  - `job_manager.py`: Job state tracking (in-memory + SQLite)
  - `schemas.py`: Pydantic models for API request/response
  - `config.py`: Env var configuration (API_KEYS, UPLOAD_DIR, MAX_FILE_SIZE_MB, JOB_TTL_SECONDS)
  - `static/index.html`: Web frontend for API
  - `static/vendor/`: Vendored Three.js and addons

**`manufacturing_pipeline/scripts/`:**
- Purpose: Standalone analysis tools (also imported by quick mode)
- Key files:
  - `aag_analyzer.py`: `AAGAnalyzer` class -- AAG graph construction, topology-based feature detection, K-factor calculations, laser time estimation
  - `compare_erp.py`: ERP validation comparing pipeline output against reference

**`manufacturing_pipeline/tests/`:**
- Purpose: Test suite
- Key files:
  - `test_basic.py`: Basic pipeline tests
  - `test_xml_export.py`: XML exporter tests
  - `test_router.py`: Router classification tests
  - `test_feature_layer1.py`: Feature detection tests
  - `test_step_naming_fallback_regression.py`: STEP naming regression test
  - `test_timeline_api.py`: API timeline endpoint tests
  - `test_display_edges.py`: Edge display tests
  - `legacy/`: Archived test files

**`viewer/`:**
- Purpose: Browser-based 3D STEP viewer with live pipeline progress
- Contains: React/Three.js app built with Vite
- Key files:
  - `src/App.jsx`: Main app component
  - `src/StepModel.jsx`: 3D STEP model rendering
  - `src/stepLoader.js`: STEP file loading logic
  - `src/pipelineClient.js`: API client for pipeline status polling
  - `src/pipelineUi.js`: Pipeline progress visualization
  - `src/ViewerCanvas.jsx`: Three.js canvas wrapper
  - `src/Sidebar.jsx`, `src/StageDetailsPanel.jsx`: UI panels
  - `src/Dropzone.jsx`: File drag-and-drop
  - `vite.config.js`: Vite build configuration

**`deploy/`:**
- Purpose: Deployment and infrastructure
- Key files:
  - `Dockerfile`: Docker image definition
  - `docker-compose.yml`: Docker orchestration
  - `nginx.conf`: Nginx reverse proxy config
  - `deploy.sh`: VPS deploy script
  - `install.sh`: VPS setup script
  - `file_watcher_service.py`: Windows folder watcher for ERP integration (uses watchdog)
  - `requirements-watcher.txt`: File watcher dependencies (watchdog, python-dotenv)
  - `install_windows_service.bat`: Windows service installer

**`docs/`:**
- Purpose: Documentation, handovers, implementation plans
- Contains: Markdown docs on classification, feature detection, pipeline flow, handover notes
- Key files: `CLASSIFICATION_DECISION_TREE.md`, `pipeline_flow.md`, `ENGINE.md`, `TIMELINE.md`
- Subdirectories: `archive/` (old code), `plans/` (implementation plans), `scripts/` (validation scripts), `superpowers/`

## Key File Locations

**Entry Points:**
- `run.py`: Primary CLI entry point, also handles `--step0` mode directly
- `manufacturing_pipeline/__main__.py`: Enables `python -m manufacturing_pipeline`
- `manufacturing_pipeline/cli.py`: Unified CLI implementation (all argument parsing lives here)
- `manufacturing_pipeline/api/app.py`: FastAPI application
- `deploy/file_watcher_service.py`: Windows ERP file watcher
- `run_viewer.py`: Launches API + viewer dev servers together

**Configuration:**
- `requirements.txt`: Python dependencies (cadquery, reportlab, fastapi, etc.)
- `pytest.ini`: Pytest configuration
- `manufacturing_pipeline/core/config.py`: `SystemConfig` and `PipelineConfig` dataclasses
- `manufacturing_pipeline/api/config.py`: API environment variable configuration
- `data/config/pipeline_config.json`: Runtime pipeline configuration (optional)
- `viewer/vite.config.js`: Vite build config for viewer
- `viewer/package.json`: Viewer npm dependencies

**Core Logic:**
- `manufacturing_pipeline/core/utils.py`: `run_analysis()` -- the quick-mode analysis orchestrator
- `manufacturing_pipeline/analysis/step_processing.py`: STEP file parsing and feature detection
- `manufacturing_pipeline/analysis/classification.py`: Step 0 solid classification
- `manufacturing_pipeline/analysis/router.py`: Pre-routing classifier
- `manufacturing_pipeline/scripts/aag_analyzer.py`: AAG topology-based feature recognition
- `manufacturing_pipeline/analysis/pipeline_stages.py`: Full pipeline stage runners

**Testing:**
- `manufacturing_pipeline/tests/test_basic.py`: Core pipeline tests
- `manufacturing_pipeline/tests/test_router.py`: Router tests
- `manufacturing_pipeline/tests/test_xml_export.py`: XML export tests
- `manufacturing_pipeline/tests/test_feature_layer1.py`: Feature detection tests

## Naming Conventions

**Files:**
- Python modules: `snake_case.py` (e.g., `step_processing.py`, `cache_manager.py`)
- React components: `PascalCase.jsx` (e.g., `StepModel.jsx`, `ViewerCanvas.jsx`)
- JS modules: `camelCase.js` (e.g., `stepLoader.js`, `pipelineClient.js`)
- Test files: `test_*.py` prefix (e.g., `test_basic.py`, `test_router.py`)

**Directories:**
- Python packages: `snake_case` (e.g., `manufacturing_pipeline`, `core`, `analysis`)
- Standard names: `tests/`, `scripts/`, `deploy/`, `docs/`, `data/`

**Classes:**
- PascalCase: `AAGAnalyzer`, `CacheManager`, `PipelineRunner`, `DatabaseManager`, `PDFReportGenerator`

**Functions:**
- snake_case: `run_analysis()`, `detect_holes()`, `precompute_face_properties()`
- Private with underscore prefix: `_import_full_pipeline()`, `_load_step_bom_solids()`

## Where to Add New Code

**New Analysis Feature:**
- Primary code: `manufacturing_pipeline/analysis/` -- add new module or extend `step_processing.py`
- Register as pipeline stage in `manufacturing_pipeline/data/cache_manager.py` (add to `PipelineStage` enum and `STAGE_DEPENDENCIES`)
- Add stage runner in `manufacturing_pipeline/analysis/pipeline_stages.py`
- Add CLI output formatting in `manufacturing_pipeline/reporting/cli_output.py`
- Tests: `manufacturing_pipeline/tests/test_*.py`

**New Classification Logic:**
- Step 0 (geometry-only): `manufacturing_pipeline/analysis/classification.py`
- Classification variables/thresholds: `manufacturing_pipeline/analysis/classification_variables.py`
- Profile-based routing: `manufacturing_pipeline/analysis/router.py` and `manufacturing_pipeline/analysis/profile_classifier.py`

**New Report Format:**
- Add exporter in `manufacturing_pipeline/reporting/` (follow pattern of `xml_exporter.py` or `excel_exporter.py`)
- Wire into CLI via `manufacturing_pipeline/cli.py`
- Wire into API via `manufacturing_pipeline/api/routes.py`

**New API Endpoint:**
- Route: `manufacturing_pipeline/api/routes.py`
- Schema: `manufacturing_pipeline/api/schemas.py`
- Service logic: `manufacturing_pipeline/api/analysis_service.py`

**New Viewer Feature:**
- Components: `viewer/src/` (React JSX)
- API integration: `viewer/src/pipelineClient.js`

**Utilities/Helpers:**
- Shared helpers: `manufacturing_pipeline/core/utils.py`
- Analysis-specific helpers: Within the relevant `manufacturing_pipeline/analysis/` module

**Deployment Changes:**
- Docker: `deploy/Dockerfile`, `deploy/docker-compose.yml`
- Nginx: `deploy/nginx.conf`
- File watcher: `deploy/file_watcher_service.py`

## Special Directories

**`data/`:**
- Purpose: All runtime data (STEP inputs, analysis outputs, database, cache)
- Generated: Yes (created at runtime)
- Committed: No (gitignored), except `data/snapshots/` (XML status snapshots are tracked)

**`.pipeline_cache/`:**
- Purpose: Pickle-based stage cache for full pipeline checkpoint/resume
- Generated: Yes (created by `CacheManager`)
- Committed: No (gitignored, safe to delete for fresh analysis)

**`data/output/`:**
- Purpose: Per-part output directories containing images/, JSON results, PDF reports, timing JSON
- Generated: Yes
- Committed: No

**`data/db/`:**
- Purpose: SQLite database (`manufacturing_data.db`) and quick-mode cache (`pipeline_cache.json`)
- Generated: Yes
- Committed: No

**`viewer/dist/`:**
- Purpose: Built viewer assets (Vite output)
- Generated: Yes
- Committed: Yes (checked in for deployment)

**`viewer/node_modules/`:**
- Purpose: npm dependencies for viewer
- Generated: Yes
- Committed: No

**`docs/archive/`:**
- Purpose: Archived/deprecated code and scripts
- Generated: No
- Committed: Yes

---

*Structure analysis: 2026-03-25*
