# Architecture

**Analysis Date:** 2026-03-25

## Pattern Overview

**Overall:** Multi-mode pipeline architecture with shared analysis engine

**Key Characteristics:**
- Three execution modes (Quick CLI, Full ISO pipeline, REST API) sharing the same analysis core
- Lazy-import strategy to keep quick mode startup fast
- Stage-based pipeline with checkpoint/resume caching in full mode
- Pre-routing classification determines which analysis path a STEP solid follows

## Layers

**Entry / CLI Layer:**
- Purpose: Parse arguments, select mode, orchestrate top-level flow
- Location: `run.py`, `manufacturing_pipeline/cli.py`, `manufacturing_pipeline/__main__.py`
- Contains: Argument parsing, mode dispatch (quick vs full vs batch vs step0), JSON/Excel output wiring
- Depends on: `core/utils.py` (quick mode), lazy-imports to `analysis/`, `data/`, `reporting/` (full mode)
- Used by: End users via command line

**Core Infrastructure Layer:**
- Purpose: Shared utilities, configuration, data models, profiling
- Location: `manufacturing_pipeline/core/`
- Contains:
  - `utils.py` - Project paths (`PROJECT_ROOT`, `DATA_DIR`, `OUTPUT_DIR`, etc.), file discovery, cache helpers, `run_analysis()` orchestrator for quick mode
  - `config.py` - `SystemConfig` (FreeCAD paths), `PipelineConfig` (module toggles)
  - `models.py` - `RouteCategory` enum, `HoleFeature`, `MatchedFeature` dataclasses, `ValidationStatus` enum
  - `profiler.py` - `AnalysisProfiler` with `step()`/`sub_step()` context managers, outputs timing JSON
  - `pipeline_init.py` - Argument normalization, path resolution, config loading for full mode
  - `xcaf_reader.py` - XCAF tree traversal for assembly-aware solid/name extraction
- Depends on: Nothing (leaf layer)
- Used by: All other layers

**Analysis Layer:**
- Purpose: All manufacturing analysis business logic
- Location: `manufacturing_pipeline/analysis/`
- Contains:
  - `step_processing.py` - STEP file loading (CadQuery/OCP), hole detection (cylindrical + shaped), face analysis, geometry extraction, `precompute_face_properties()` optimization
  - `classification.py` - Step 0 decision tree classifier (RONDE_BUIS, RECHTHOEKIGE_KOKER, PROFIEL, PLAAT, GEZETTE_PLAAT, ANDERS)
  - `classification_variables.py` - Thresholds and constants for classification
  - `router.py` - Pre-routing classifier mapping profile labels to `RouteCategory` (PLAAT/PROFIEL/ROND/OVERIG)
  - `profile_classifier.py` - Cross-section profile analysis
  - `profile_features.py` - Geometric feature extraction for profiles
  - `sheetmetal_analysis.py` - Thickness detection, bend counting, profile classification
  - `part_analyzer.py` - High-level part classification, reasoning system, unfold feasibility
  - `iso_standards.py` - ISO 2768/286/1302/68-1/13715, EN 10025/573 standards
  - `freecad_unfold.py` - FreeCAD SheetMetal workbench integration (subprocess call to FreeCAD Python)
  - `assembly_analysis.py` - Assembly/BOM analysis for multi-solid files
  - `pipeline_stages.py` - Stage runner functions grouping stages 1-17 for full pipeline
  - `correlation.py` - Dimension correlation between STEP and PDF
  - `werkvoorbereiding.py` - Work preparation analysis, cost table generation
  - `cut_features.py` - Cut feature detection
  - `step0_section_tools.py` - Section analysis tools for Step 0 classification
- Depends on: `core/` for models and config, OCP/CadQuery for geometry
- Used by: `cli.py`, `api/analysis_service.py`

**Data Layer:**
- Purpose: Persistence and caching
- Location: `manufacturing_pipeline/data/`
- Contains:
  - `cache_manager.py` - `CacheManager` (pickle-based stage caching to `.pipeline_cache/`), `PipelineRunner` (orchestrates get-or-run logic), `PipelineStage` enum with dependency DAG
  - `database.py` - `DatabaseManager` wrapping SQLite for storing analysis results
  - `sql/schema.sql` - Database schema (Parts, Holes, PostProcessing, api_jobs tables)
- Depends on: `core/` for paths
- Used by: `cli.py` (full mode), `api/`

**Reporting Layer:**
- Purpose: Output generation in multiple formats
- Location: `manufacturing_pipeline/reporting/`
- Contains:
  - `report_generator.py` - PDF report generation with ISO standard sections (reportlab)
  - `cli_output.py` - Terminal output formatting with section headers and summary tables
  - `xml_exporter.py` - XML export for ERP/SpaceClaim integration
  - `excel_exporter.py` - Excel export in SpaceClaim format (openpyxl)
  - `pdf_processing.py` - PDF parsing to extract dimensions (pymupdf)
  - `dxf_metrics_extractor.py` - DXF file metrics extraction
- Depends on: `core/` for models
- Used by: `cli.py`, `api/routes.py`

**API Layer:**
- Purpose: REST API for Docker/VPS deployment
- Location: `manufacturing_pipeline/api/`
- Contains:
  - `app.py` - FastAPI application, CORS middleware, API key auth middleware, job cleanup loop
  - `routes.py` - API endpoints under `/api/v1/` (analyze, jobs, health, timeline)
  - `analysis_service.py` - Bridge: wraps `run_analysis()` from `core/utils.py`, builds timeline events from profiler timing data
  - `job_manager.py` - In-memory + SQLite job state management with TTL cleanup
  - `schemas.py` - Pydantic request/response models
  - `config.py` - API env var configuration (API_KEYS, UPLOAD_DIR, MAX_FILE_SIZE_MB)
  - `static/index.html` - Web frontend for API
  - `static/vendor/` - Three.js vendored assets
- Depends on: `core/utils.py`, `reporting/xml_exporter.py`
- Used by: External HTTP clients, Docker deployment

**Scripts Layer:**
- Purpose: Standalone analysis tools
- Location: `manufacturing_pipeline/scripts/`
- Contains:
  - `aag_analyzer.py` - AAG (Attributed Adjacency Graph) feature recognition: builds face-edge graph, detects features via topology, K-factor bend calculations, laser cutting time estimation
  - `compare_erp.py` - ERP validation tool comparing pipeline output against reference data
- Depends on: `core/`, `analysis/`
- Used by: `core/utils.py` imports `AAGAnalyzer` for quick mode

**Viewer Layer:**
- Purpose: Browser-based 3D STEP file viewer with live analysis pipeline visualization
- Location: `viewer/`
- Contains: React + Three.js application (Vite build)
  - `src/App.jsx` - Main application
  - `src/StepModel.jsx` - 3D model rendering
  - `src/stepLoader.js` - STEP file loading
  - `src/pipelineClient.js` - API client for pipeline status
  - `src/pipelineUi.js` - Pipeline progress UI
  - `src/Sidebar.jsx`, `src/StageDetailsPanel.jsx` - UI components
  - `src/ViewerCanvas.jsx`, `src/Dropzone.jsx` - 3D canvas and file drop
- Depends on: API layer (consumes `/api/v1/` endpoints)
- Used by: `run_viewer.py` (launches both API server and Vite dev server)

## Data Flow

**Quick Mode (default):**

1. `run.py` dispatches to `cli.py:main()` which parses args
2. `cli.py` calls `core/utils.py:run_analysis()` with the STEP file path
3. `run_analysis()` loads STEP via `step_processing.load_step_file()`
4. AAG analysis runs via `scripts/aag_analyzer.AAGAnalyzer` (topology-based feature recognition)
5. Pre-routing classification via `analysis/router.py` determines part category
6. Standard analysis: `part_analyzer.analyze_part_geometry()` classifies and extracts features
7. If sheet metal with bends: `freecad_unfold.py` attempts unfold via FreeCAD subprocess
8. Hole detection on flat pattern (if available) or 3D geometry
9. PDF report generated via `reporting/report_generator.py`
10. Results written to `data/output/{part_name}/`

**Full Mode (`--full`):**

1. `cli.py` lazy-imports full pipeline modules via `_import_full_pipeline()`
2. `PipelineRunner` initialized with `CacheManager` for checkpoint/resume
3. Pre-routing: `router.route_step_file()` classifies the solid
4. Stages 1-7: Geometry and topology via `pipeline_stages.run_geometry_and_topology_stages()`
5. Stages 8-12: ISO standards via `pipeline_stages.run_iso_standards_stages()`
6. Stage 13: Werkvoorbereiding (work preparation)
7. Stage 14: Sheet metal analysis
8. Stage 15: Assembly/BOM analysis
9. Stage 16: Cost table generation
10. Stage 17: PDF correlation (match STEP dimensions to PDF drawing dimensions)
11. Results compiled, saved to JSON, SQLite database, and PDF report

**API Mode:**

1. Client POSTs STEP file to `/api/v1/analyze`
2. `routes.py` creates job, saves file to `UPLOAD_DIR`, starts background task
3. `analysis_service.run_step_analysis()` calls `core/utils.py:run_analysis()`
4. Job status polled via GET `/api/v1/jobs/{job_id}`
5. Results available as JSON, CSV, XML, or Excel
6. Timeline events built from profiler timing data for live progress display

**Step 0 Classification (`--step0`):**

1. `run.py` intercepts `--step0` flag before delegating to `cli.py`
2. Loads solids via `core/xcaf_reader.xcaf_match_solids_to_names()` (XCAF tree) or CadQuery fallback
3. Each solid classified by `analysis/classification.classify_step0_detailed_trace()`
4. Decision tree: slice validation -> hollow detection -> open profile -> flat plate -> fallback

**State Management:**

- **Quick mode cache**: Simple JSON file at `data/db/pipeline_cache.json` keyed by absolute file path with MD5 hash invalidation
- **Full mode cache**: Pickle-based stage cache in `.pipeline_cache/` directory with `PipelineStage` dependency DAG. Clearing a stage cascades to dependents.
- **API jobs**: In-memory dict + SQLite `api_jobs` table. Jobs have TTL-based expiry (default 3600s).
- **Database**: SQLite at `data/db/manufacturing_data.db` stores Parts, Holes, PostProcessing records (full mode only)
- **File outputs**: Per-part directories under `data/output/{part_name}/` with images, JSON, PDF, timing JSON

## Key Abstractions

**PipelineRunner / PipelineStage:**
- Purpose: Checkpoint/resume orchestration for full pipeline
- Examples: `manufacturing_pipeline/data/cache_manager.py`
- Pattern: `runner.get_or_run(PipelineStage.X, callable, *args)` -- returns cached result or executes and caches

**RouteCategory / RouteResult:**
- Purpose: Pre-routing classification that determines analysis path
- Examples: `manufacturing_pipeline/core/models.py`, `manufacturing_pipeline/analysis/router.py`
- Pattern: STEP solid -> profile classifier -> RouteCategory enum (PLAAT/PROFIEL/ROND/OVERIG) -> pipeline adapts behavior

**AAGAnalyzer:**
- Purpose: Topology-based feature recognition via Attributed Adjacency Graph
- Examples: `manufacturing_pipeline/scripts/aag_analyzer.py`
- Pattern: Build graph (nodes=faces, arcs=edges with convexity), detect features (bends, holes, slots), compute manufacturing parameters

**AnalysisProfiler:**
- Purpose: Timing measurement for pipeline stages and sub-steps
- Examples: `manufacturing_pipeline/core/profiler.py`
- Pattern: Context manager `with profiler.step("name"):` / `with profiler.sub_step("name"):`, outputs box-drawing table and JSON

**Classification Decision Tree (Step 0):**
- Purpose: Geometry-only solid classification without full pipeline overhead
- Examples: `manufacturing_pipeline/analysis/classification.py`
- Pattern: Sequential steps (0.1-0.5) with early exit on match, fallthrough flag for ambiguous cases

## Entry Points

**`run.py` (primary CLI):**
- Location: `run.py`
- Triggers: `python run.py [args]` or `python -m manufacturing_pipeline`
- Responsibilities: Dispatches `--step0` to local classification logic, everything else to `manufacturing_pipeline.cli.main()`

**`manufacturing_pipeline/cli.py:main()`:**
- Location: `manufacturing_pipeline/cli.py`
- Triggers: Called from `run.py` or `__main__.py`
- Responsibilities: Argument parsing, mode selection (quick/full/batch), file discovery, output formatting

**`manufacturing_pipeline/api/app.py`:**
- Location: `manufacturing_pipeline/api/app.py`
- Triggers: `uvicorn manufacturing_pipeline.api.app:app` or Docker
- Responsibilities: FastAPI app, auth middleware, routes mount, job cleanup

**`deploy/file_watcher_service.py`:**
- Location: `deploy/file_watcher_service.py`
- Triggers: Windows service watching a configured folder
- Responsibilities: Monitors folder for new STEP files, auto-analyzes, exports XML for ERP

**`run_viewer.py`:**
- Location: `run_viewer.py`
- Triggers: `python run_viewer.py`
- Responsibilities: Launches both API server (uvicorn) and Vite dev server for the 3D viewer

## Error Handling

**Strategy:** Graceful degradation with fallback chains

**Patterns:**
- XCAF reader fails -> CadQuery fallback for solid loading (`run.py:_load_step_bom_solids()`)
- FreeCAD unfold fails on first face -> tries 2nd and 3rd largest faces -> theoretical unfold calculation
- Router fails -> pipeline continues without routing (`cli.py` catches exception, sets `route_result = None`)
- Individual pipeline stages wrapped in try/except with tip to use `--status` / `--from <stage>` to debug and resume
- Import errors caught for optional dependencies (AAGAnalyzer, FreeCAD)

## Cross-Cutting Concerns

**Logging:** Mix of `print()` statements (CLI output) and Python `logging` module (analysis modules use `logging.getLogger()`)

**Validation:** Pydantic models in API layer (`api/schemas.py`), dataclass models in core (`core/models.py`). No formal validation layer for STEP geometry input beyond file existence checks.

**Authentication:** API key middleware in `api/app.py` -- checks `X-API-Key` header against comma-separated `API_KEYS` env var. Empty = dev mode (no auth).

**Profiling:** `AnalysisProfiler` in `core/profiler.py` wraps every stage. Outputs timing table to terminal and `{part_name}_timing.json` to output dir. API layer converts timing data into timeline events.

**Caching:** Two independent systems -- simple JSON hash cache for quick mode (`core/utils.py`), pickle-based stage cache with dependency DAG for full mode (`data/cache_manager.py`).

---

*Architecture analysis: 2026-03-25*
