# External Integrations

**Analysis Date:** 2026-03-25

## APIs & External Services

**No external cloud APIs are called.** The pipeline is fully self-contained and runs offline. All analysis is performed locally using OpenCASCADE/CadQuery.

**Self-hosted REST API:**
- FastAPI at `/api/v1/*` (`manufacturing_pipeline/api/app.py`, `manufacturing_pipeline/api/routes.py`)
- Auth: `X-API-Key` header, keys from `API_KEYS` env var (comma-separated)
- Endpoints:
  - `POST /api/v1/analyze` - Upload STEP file, returns job_id
  - `GET /api/v1/jobs/{job_id}` - Poll status, get results (supports `?format=csv|xml|excel`)
  - `GET /api/v1/health` - Health check

## File Format I/O

**Input Formats:**
- STEP / STP (ISO 10303-21) - Primary CAD input format
  - Loaded via CadQuery `importStep()` or XCAF reader (`manufacturing_pipeline/core/xcaf_reader.py`)
  - File normalization strips junk bytes before STEP header (`manufacturing_pipeline/analysis/step_processing.py`)
- PDF - Technical drawings for dimension extraction (`manufacturing_pipeline/reporting/pdf_processing.py`) - currently a mock/placeholder
- Excel (.xlsx) - SpaceClaim reference data for comparison (`manufacturing_pipeline/reporting/excel_exporter.py`)
- XML - SpaceClaim reference data for comparison (`manufacturing_pipeline/reporting/excel_exporter.py`)
- JSON - Pipeline config (`data/config/pipeline_config.json`), cached stage results (`.pipeline_cache/`)

**Output Formats:**
- PDF - Analysis reports with charts, images, tables (`manufacturing_pipeline/reporting/report_generator.py`, uses reportlab + svglib)
- Excel (.xlsx) - SpaceClaim-compatible 26-column format (`manufacturing_pipeline/reporting/excel_exporter.py`, uses openpyxl)
- XML - ALES ERP / AutoPOL / SpaceClaim compatible format (`manufacturing_pipeline/reporting/xml_exporter.py`)
- JSON - Analysis results, timing profiles (`data/output/` subdirectories)
- SVG - Part images generated from 3D geometry (`manufacturing_pipeline/analysis/step_processing.py`)
- DXF - Flat pattern export from FreeCAD unfold (`manufacturing_pipeline/analysis/freecad_unfold.py`)
- CSV - API job results (via `?format=csv` query param)

## Data Storage

**Databases:**
- SQLite (stdlib `sqlite3`) - Two usage patterns:
  1. **Pipeline database** (`data/db/manufacturing_data.db`): Parts, Holes, PostProcessing tables
     - Client: `manufacturing_pipeline/data/database.py` (`DatabaseManager` class)
     - Schema: `manufacturing_pipeline/data/sql/schema.sql`
  2. **API job persistence** (`api_jobs` table in same DB): Job tracking for REST API
     - Client: `manufacturing_pipeline/api/job_manager.py` (`JobManager` class)
     - In-memory cache + SQLite persistence with thread locking

**File-based Cache:**
- Pipeline stage cache in `.pipeline_cache/` directory
  - JSON files per stage, keyed by STEP file MD5 hash
  - Managed by `manufacturing_pipeline/data/cache_manager.py`

**File Storage:**
- Local filesystem only
- STEP input: `data/input/`, `data/parts/`
- Analysis output: `data/output/{part_name}/`
- API uploads: `UPLOAD_DIR` env var (default `/tmp/manufacturing-uploads`)
- Snapshots: `data/snapshots/` (XML, git-tracked)

**Caching:**
- Stage-based pipeline cache (file MD5 invalidation) via `CacheManager`
- In-memory job cache in API (`JobManager._cache` dict)
- No Redis/Memcached

## Authentication & Identity

**Auth Provider:** Custom API key middleware
- Implementation: HTTP middleware in `manufacturing_pipeline/api/app.py`
- Keys read from `API_KEYS` environment variable (comma-separated)
- Header: `X-API-Key`
- Empty `API_KEYS` = no authentication (development mode)
- No user management, sessions, or OAuth

## Third-Party Tools (External CLI/Runtime)

**FreeCAD (critical):**
- Purpose: Sheet metal unfold / flat pattern generation
- Invoked as: subprocess with FreeCAD's bundled Python interpreter
- macOS path: `/opt/homebrew/Caskroom/freecad/1.0.2/FreeCAD.app/Contents/Resources/bin/python`
- Linux/Docker path: `/usr/lib/freecad/bin/python`
- Workbench: FreeCAD SheetMetal (cloned from `github.com/shaise/FreeCAD_SheetMetal`)
- Config: `FREECAD_PATH` env var, platform detection in `manufacturing_pipeline/core/config.py`
- Integration: `manufacturing_pipeline/analysis/freecad_unfold.py`
- Outputs: DXF flat patterns, unfold dimensions

**OpenCASCADE (OCP - linked library):**
- Purpose: CAD kernel for all geometry operations
- Access: Python bindings via `cadquery-ocp` package
- Key modules used: `STEPCAFControl_Reader` (XCAF tree), `BRepGProp` (mass properties), `BRepAdaptor_Surface` (face geometry), `TopExp_Explorer` (topology traversal)
- Not a CLI tool but a compiled C++ library loaded at runtime

## Monitoring & Observability

**Error Tracking:** None (no Sentry, Datadog, etc.)

**Logs:**
- Python `logging` module (standard library)
- Console output via `print()` for CLI mode
- `AnalysisProfiler` in `manufacturing_pipeline/core/profiler.py` generates timing data:
  - Box-drawing table in terminal
  - `{part_name}_timing.json` per analysis run

## CI/CD & Deployment

**Hosting:**
- Docker container on VPS (Ubuntu)
- Nginx reverse proxy with SSL (Certbot/Let's Encrypt)

**CI Pipeline:** None detected (no GitHub Actions, GitLab CI, etc.)

**Deployment Scripts:**
- `deploy/deploy.sh` - VPS deployment script
- `deploy/install.sh` - VPS setup script
- `deploy/Dockerfile` - Debian Bookworm based image
- `deploy/docker-compose.yml` - Single-service compose with persistent upload volume

## ERP Integration

**ALES ERP System:**
- XML export format compatible with SpaceClaim/AutoPOL (`manufacturing_pipeline/reporting/xml_exporter.py`)
- Excel export in SpaceClaim 26-column format (`manufacturing_pipeline/reporting/excel_exporter.py`)
- Windows file watcher service monitors shared folder for new STEP files (`deploy/file_watcher_service.py`)
  - Uses `watchdog` for filesystem events
  - Auto-analyzes and exports XML results
  - Designed for network folder integration (e.g., `G:\ALES\Offerte-ALES`)

**ERP Comparison Tool:**
- `manufacturing_pipeline/scripts/compare_erp.py` - Validates pipeline output against ERP reference data

## Webhooks & Callbacks

**Incoming:** None
**Outgoing:** None

---

*Integration audit: 2026-03-25*
