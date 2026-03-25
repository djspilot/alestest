# Technology Stack

**Analysis Date:** 2026-03-25

## Languages

**Primary:**
- Python 3.12+ - All backend analysis, API, CLI, and pipeline code (`manufacturing_pipeline/`)
- JavaScript (ES2020, JSX) - STEP 3D viewer frontend (`viewer/`)

**Secondary:**
- SQL - Database schema (`manufacturing_pipeline/data/sql/schema.sql`)
- HTML - API web frontend (`manufacturing_pipeline/api/static/index.html`)

## Runtime

**Environment:**
- Python 3.12.8 (system)
- Node.js (for viewer frontend, version not pinned)
- FreeCAD bundled Python (separate runtime for unfold operations)

**Package Manager:**
- pip - Python dependencies via `requirements.txt`
- npm - Viewer frontend via `viewer/package.json`
- No lockfile for pip (no `requirements.lock` or `poetry.lock`)
- npm lockfile: `viewer/package-lock.json` (present via node_modules)

## Frameworks

**Core:**
- CadQuery >= 2.4.0 - CAD kernel wrapping OpenCASCADE (OCP) for STEP file processing (`manufacturing_pipeline/analysis/step_processing.py`)
- FastAPI >= 0.104.0 - REST API framework (`manufacturing_pipeline/api/app.py`)
- React 18.2.0 - 3D viewer UI (`viewer/`)
- Three.js 0.160.0 + React Three Fiber 8.x - WebGL 3D rendering (`viewer/`)

**Testing:**
- pytest - Test runner (invoked via `python -m pytest`)

**Build/Dev:**
- Vite 5.4.0 - Viewer frontend bundler (`viewer/vite.config.js`)
- @vitejs/plugin-react 4.2.0 - JSX/React support for Vite

## Key Dependencies

**Critical (CAD/Analysis):**
- `cadquery` >= 2.4.0 - STEP file import, solid geometry operations
- `cadquery-ocp` - OpenCASCADE Python bindings (OCP.* modules: BRepGProp, TopExp, STEPCAFControl, XCAFDoc, etc.)
- `numpy` - Numerical computations in geometry analysis
- `opencv-python` - Image processing (imported as `cv2`)

**Reporting:**
- `reportlab` - PDF report generation with charts (`manufacturing_pipeline/reporting/report_generator.py`)
- `svglib` - SVG to ReportLab graphics conversion (`manufacturing_pipeline/reporting/report_generator.py`)
- `openpyxl` >= 3.1.0 - Excel (.xlsx) export in SpaceClaim format (`manufacturing_pipeline/reporting/excel_exporter.py`)
- `pymupdf` - PDF parsing for dimension extraction (`manufacturing_pipeline/reporting/pdf_processing.py`)

**API/Web:**
- `fastapi` >= 0.104.0 - REST API (`manufacturing_pipeline/api/app.py`)
- `uvicorn[standard]` >= 0.24.0 - ASGI server
- `python-multipart` >= 0.0.6 - File upload handling
- `pydantic` >= 2.0.0 - Request/response validation (`manufacturing_pipeline/api/schemas.py`)

**3D Viewer:**
- `@react-three/fiber` ^8.15.14 - React renderer for Three.js
- `@react-three/drei` ^9.92.3 - Useful helpers/controls for R3F
- `three` ^0.160.0 - WebGL 3D library
- `react` ^18.2.0 / `react-dom` ^18.2.0

**File Watcher (separate deps in `deploy/requirements-watcher.txt`):**
- `watchdog` 3.0.0 - Filesystem monitoring
- `python-dotenv` 1.0.0 - Environment variable loading from `.env`

## Configuration

**Environment:**
- `FREECAD_PATH` - Path to FreeCAD installation (default: `/opt/homebrew/Caskroom/freecad/1.0.2/FreeCAD.app` on macOS)
- `API_KEYS` - Comma-separated API keys for REST API auth (empty = dev mode, no auth)
- `UPLOAD_DIR` - Temp directory for uploaded STEP files (default: `/tmp/manufacturing-uploads`)
- `MAX_FILE_SIZE_MB` - Max upload size (default: 100)
- `JOB_TTL_SECONDS` - Job cleanup interval (default: 3600)
- `DB_PATH` - SQLite database path (default: `data/db/manufacturing_data.db`)

**Pipeline Config:**
- JSON config file at `data/config/pipeline_config.json` - module toggles, pricing, material prices
- `PipelineConfig` dataclass in `manufacturing_pipeline/core/config.py` - all settings with defaults
- Module groups: basic, iso, manufacturing, werkvoorbereiding, plaatwerk

**Build:**
- `viewer/vite.config.js` - Vite config with manual chunk splitting (react-vendor, viewer-3d, viewer-runtime)
- No Python build config (no pyproject.toml, setup.py, or setup.cfg) - run directly from source

## Platform Requirements

**Development (macOS):**
- Python 3.12+
- FreeCAD 1.0.2 (Homebrew cask) for sheet metal unfold
- Node.js + npm (for viewer frontend)
- No linter/formatter config files detected

**Production (Docker/VPS):**
- Debian Bookworm base image (`deploy/Dockerfile`)
- FreeCAD installed via apt (Debian package)
- FreeCAD SheetMetal workbench cloned from GitHub at build time
- Nginx reverse proxy (`deploy/nginx.conf`)
- SSL via Certbot/Let's Encrypt
- uvicorn with 2 workers

**Windows (ERP integration):**
- File watcher service (`deploy/file_watcher_service.py`)
- Monitors network folder for STEP files
- Requires FreeCAD installed locally

---

*Stack analysis: 2026-03-25*
