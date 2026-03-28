# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Current Repository Status (Post-Overhaul)

The repository is now quick-mode focused.

- Available: quick analysis and batch processing through `python run.py`
- Removed: `--full` mode, API package, Docker/deploy setup, AAG analyzer, ISO standards module, database/cache pipeline layers
- Viewer launcher: use `python run_viewer.py`

Note: parts of this document are historical and may still mention removed components.

## Project Overview

This is a **manufacturing analysis pipeline** that processes STEP CAD files to extract geometric data, analyze components, detect holes/features, and generate reports. The pipeline includes comprehensive **Dutch/ISO manufacturing standards** analysis for tolerances, fits, threads, surface finish, and material calculations.

The project provides three usage modes:

| Mode | Command | Description |
|------|---------|-------------|
| **Quick** (default) | `python run.py` | Fast AAG-based analysis with PDF reports |
| **Full** | `python run.py --full` | Complete ISO pipeline with database storage |
| **API** (Docker) | `docker compose -f deploy/docker-compose.yml up -d` | REST API for VPS deployment |

## Key Commands

### Installation
```bash
pip install -r requirements.txt
```

### Quick Mode (Default)
```bash
python run.py                              # Interactive file selection
python run.py -f mypart.step               # Analyze specific file
python run.py -f mypart.step --aag         # AAG topology-based feature recognition
python run.py -f mypart.step --aag -v      # AAG with verbose hole/bend details
python run.py --analyze                    # Show detailed analysis reasoning
python run.py --debug                      # Debug hole detection
python run.py --no-unfold                  # Skip automatic unfolding
python run.py --list                       # List available STEP files
```

### Batch Processing
```bash
python run.py --batch                      # Process all files in data/input/
python run.py -f ./folder --batch -p 4     # Parallel batch (4 workers)
python run.py -f ./folder --batch --json   # JSON output for ERP integration
python run.py --batch --no-cache           # Skip cache, force re-analysis
```

### Excel Export (SpaceClaim Comparison)
```bash
python run.py -f mypart.step --excel                        # Excel in SpaceClaim format
python run.py -f mypart.step --aag --excel                  # With AAG cut length data
python run.py -f mypart.step --excel --reference ref.xlsx   # Side-by-side with SpaceClaim
python run.py --batch --excel                               # Excel for batch results
python run.py --batch --excel --reference spaceclaim.xml    # Batch + comparison
```

### Full Mode (Complete ISO Pipeline)
```bash
python run.py -f mypart.step --full                    # Full ISO pipeline
python run.py -f mypart.step --full --production-info  # With production table
python run.py --full --status                          # Show cache status
python run.py --full --clear-cache                     # Clear cached data
python run.py --full --from threads                    # Resume from specific stage
python run.py --full --list-stages                     # List pipeline stages
python run.py --full --list-modules                    # List available modules
python run.py --full --disable cost_estimation         # Disable specific module
```

You can also use `python -m manufacturing_pipeline` instead of `python run.py`.

### ERP Comparison Tool
```bash
python manufacturing_pipeline/scripts/compare_erp.py data/parts/AI-voorbeelden/
python manufacturing_pipeline/scripts/compare_erp.py data/parts/AI-voorbeelden/ --aag
python manufacturing_pipeline/scripts/compare_erp.py data/parts/AI-voorbeelden/ -v
```

### Docker / API Deployment
```bash
# Start API server
docker compose -f deploy/docker-compose.yml up -d

# Or local dev mode
API_KEYS=your-key uvicorn manufacturing_pipeline.api.app:app --reload --port 8000

# Use the API
curl -X POST http://localhost:8000/api/v1/analyze \
  -H "X-API-Key: your-key" -F "file=@mypart.step"
curl http://localhost:8000/api/v1/jobs/{job_id} -H "X-API-Key: your-key"
curl http://localhost:8000/api/v1/health
```

### Windows File Watcher (ERP Integration)
```bash
# Run from project root
python deploy/file_watcher_service.py
python deploy/file_watcher_service.py --test --file path/to/file.step
```

### Testing
```bash
python -m pytest
```

## Project Structure

```
/
├── run.py                          # Entry point (thin wrapper → cli.py)
├── requirements.txt                # All Python dependencies
├── CLAUDE.md                       # This file
│
├── manufacturing_pipeline/         # ALL code
│   ├── __init__.py
│   ├── __main__.py                 # Enables: python -m manufacturing_pipeline
│   ├── cli.py                      # Unified CLI (quick + full + batch modes)
│   │
│   ├── core/                       # Infrastructure
│   │   ├── config.py               # Pipeline configuration, module settings
│   │   ├── models.py               # Data models and types
│   │   ├── pipeline_init.py        # Pipeline initialization helpers
│   │   ├── profiler.py             # Performance profiling & timing (AnalysisProfiler)
│   │   └── utils.py                # Shared utilities, constants, path definitions
│   │
│   ├── analysis/                   # Analysis modules (business logic)
│   │   ├── step_processing.py      # STEP parsing, hole/bend detection, geometry
│   │   ├── sheetmetal_analysis.py  # Sheet metal: thickness, bends, profiles
│   │   ├── part_analyzer.py        # Part classification, reasoning system
│   │   ├── iso_standards.py        # ISO/NEN standards (tolerances, fits, threads)
│   │   ├── freecad_unfold.py       # FreeCAD SheetMetal workbench integration
│   │   ├── assembly_analysis.py    # Assembly/BOM analysis
│   │   ├── pipeline_stages.py      # Pipeline stage definitions
│   │   ├── correlation.py          # Dimension correlation
│   │   └── werkvoorbereiding.py    # Work preparation analysis
│   │
│   ├── data/                       # Data layer
│   │   ├── cache_manager.py        # Pipeline caching system
│   │   ├── database.py             # SQLite database manager
│   │   └── sql/schema.sql          # Database schema
│   │
│   ├── reporting/                  # Output generation
│   │   ├── report_generator.py     # PDF report generation
│   │   ├── cli_output.py           # CLI output formatting
│   │   ├── xml_exporter.py         # XML export for ERP integration
│   │   ├── excel_exporter.py       # Excel export in SpaceClaim format
│   │   └── pdf_processing.py       # PDF parsing utilities
│   │
│   ├── scripts/                    # Standalone analysis scripts
│   │   ├── aag_analyzer.py         # AAG feature recognition
│   │   └── compare_erp.py          # ERP validation tool
│   │
│   ├── api/                        # REST API (Docker/VPS deployment)
│   │   ├── app.py                  # FastAPI application, middleware, CORS
│   │   ├── routes.py               # API endpoints (analyze, jobs, health)
│   │   ├── analysis_service.py     # Bridge to manufacturing pipeline
│   │   ├── job_manager.py          # Job state management with SQLite
│   │   ├── schemas.py              # Pydantic request/response models
│   │   ├── config.py               # API configuration (env vars)
│   │   └── static/index.html       # Web frontend
│   │
│   └── tests/                      # Test suite
│       ├── test_basic.py
│       └── test_xml_export.py
│
├── deploy/                         # Deployment & Docker
│   ├── Dockerfile                  # Docker image definition
│   ├── docker-compose.yml          # Docker orchestration
│   ├── .env.example                # Environment config template
│   ├── deploy.sh                   # VPS deploy script
│   ├── install.sh                  # VPS setup script
│   ├── nginx.conf                  # Nginx reverse proxy config
│   ├── file_watcher_service.py     # Windows ERP file watcher service
│   └── requirements-watcher.txt    # File watcher dependencies
│
├── docs/                           # Documentation, scripts & archive
│   ├── *.md                        # Handovers, classificatie, workflows
│   ├── scripts/                    # Standalone validation/analysis scripts
│   ├── archive/                    # Archived code (profile_pipeline, etc.)
│   └── plans/                      # Implementation plans
│
└── data/                           # Runtime data (gitignored)
    ├── input/                      # STEP files for analysis
    ├── output/                     # Analysis results (per-part subdirs)
    ├── parts/                      # Quick-access sample parts
    ├── snapshots/                  # XML status snapshots (git-tracked)
    ├── config/                     # pipeline_config.json
    └── db/                         # manufacturing_data.db, pipeline_cache.json
```

## Architecture

### How It Works

**Local usage (CLI):**
```
run.py → manufacturing_pipeline/cli.py → core/utils.py functions
                                       → analysis/ modules
                                       → reporting/ modules
```

**Docker deployment (API):**
```
deploy/Dockerfile → manufacturing_pipeline/api/app.py → api/routes.py → same engine
```

**Windows ERP integration:**
```
deploy/file_watcher_service.py → monitors folder → manufacturing_pipeline → XML export
```

### Entry Points

| Entry Point | Purpose |
|-------------|---------|
| `run.py` | Thin wrapper, delegates to `manufacturing_pipeline.cli.main()` |
| `python -m manufacturing_pipeline` | Same as `run.py` (via `__main__.py`) |
| `manufacturing_pipeline/api/app.py` | FastAPI REST API (Docker/VPS) |
| `deploy/file_watcher_service.py` | Windows folder watcher for ERP |

### Analysis Flow

**Quick Mode** (default):
```
Load STEP → Classify part → Detect features → Unfold (if applicable) → Generate PDF
```

**Full Mode** (`--full`):
```
Load STEP → Detect holes/bends → Classify part type → Apply ISO standards →
Generate report → Store in database
```

### Key Module Responsibilities

**Profiler** (`core/profiler.py`):
- `AnalysisProfiler` class with `step()` and `sub_step()` context managers
- Produces box-drawing timing table in terminal after each analysis run
- Saves `{part_name}_timing.json` to output dir for cross-file comparison
- Uses `time.perf_counter()` for accurate measurements

**STEP Processing** (`analysis/step_processing.py`):
- Load STEP files using CadQuery/OCP
- `precompute_face_properties()`: single-pass face property extraction (avoids redundant OCP calls)
- Detect holes: cylindrical (via cylindrical faces) and shaped (via inner wires)
- Detect bends: identify cylindrical bend faces with radius/angle
- Classify face types (planar, cylindrical, conical, etc.)
- Generate part images as SVG

**Sheet Metal Analysis** (`analysis/sheetmetal_analysis.py`):
- Detect thickness from parallel planar faces
- Classify profiles (closed/open, koker/U-profiel/hoekprofiel)
- Count bends for ERP (excludes certain bend types per business rules)
- Determine if part is purchased profile vs fabricated sheet metal

**Part Analyzer** (`analysis/part_analyzer.py`):
- High-level classification: sheet metal, turned part, profile, or other
- Business logic for bend counting
- Reasoning system: tracks why decisions were made
- Determines unfold feasibility

**FreeCAD Unfold** (`analysis/freecad_unfold.py`):
- Integrates with FreeCAD's SheetMetal workbench
- Tries multiple base faces if initial unfold fails
- Exports flat pattern as DXF
- Calculates theoretical unfold if automatic unfold fails

**AAG Analyzer** (`scripts/aag_analyzer.py`):
- Builds Attributed Adjacency Graph (nodes=faces, arcs=edges with convexity)
- Topology-based feature recognition (more robust than geometry-only)
- Isoperimetric Quotient for hole/slot classification (Q=4piA/P^2, Q~1 for circles)
- K-factor based bend allowance/deduction calculations
- Laser cutting time estimation

**ISO Standards** (`analysis/iso_standards.py`):
- ISO 2768: General tolerances (linear & geometric)
- ISO 286: Limits and fits (H7/h6, etc.)
- ISO 1302: Surface roughness (Ra/Rz)
- ISO 68-1/261: Metric screw threads
- ISO 13715: Edge conditions (chamfers/fillets)
- EN 10025/573: Material density tables

**Report Generator** (`reporting/report_generator.py`):
- Creates comprehensive PDF reports with ISO standard sections
- Includes part images, dimension tables, hole/bend details

**Cache Manager** (`data/cache_manager.py`):
- Stage-based caching system
- File change detection via MD5 hash
- Dependency tracking between stages

## ISO Standards Implemented

| Standard | Description | Features |
|----------|-------------|----------|
| ISO 2768 | General tolerances | Linear/angular tolerance classes (f/m/c/v), geometric tolerances (H/K/L) |
| ISO 286 | Limits and fits | Hole-basis fits (H7/h6, H7/g6, etc.), IT grades, tolerance calculation |
| ISO 1302 | Surface texture | Ra/Rz values, process-based finish estimation |
| ISO 68-1/261 | Metric threads | Thread detection (M3-M68), coarse/fine pitch, tap drill sizes |
| ISO 13715 | Edge conditions | Chamfer/fillet detection, standard sizes |
| EN 10025 | Steel grades | S235, S275, S355, C45, 42CrMo4, 304/316 stainless |
| EN 573 | Aluminum alloys | 1050, 5083, 6061, 6082, 7075 |

## Important Implementation Details

### Hole Detection Strategy

The pipeline uses **two complementary methods**:

1. **Cylindrical face method** (`detect_holes`):
   - Finds cylindrical faces on the part
   - Filters for internal cylinders (holes) vs external (shafts)
   - Works well for through-holes and deep holes

2. **Inner wire method** (`detect_shaped_holes`):
   - Finds inner wires on planar faces
   - Detects slots, rectangles, complex shapes
   - Essential for laser-cut parts with non-circular holes

**Best practice**: Use both methods and combine results. For sheet metal, run inner wire detection on the unfolded flat pattern.

### Performance Optimizations

The pipeline uses several strategies to handle large STEP files efficiently:

1. **`precompute_face_properties()`**: Single pass extracts all face types, areas, centers, and geometry-specific data (cylinder radius/axis, plane normal/d) as primitive Python values. Avoids redundant `BRepAdaptor_Surface` calls in detection loops.

2. **Diameter bucketing** in `detect_holes()`: Candidates are grouped by `round(diameter, 2)` into a `defaultdict`. Only candidates in the same bucket (±0.01) are compared, reducing O(n²) to O(n × bucket_size).

3. **Type/dim bucketing** in `detect_shaped_holes()` dedup: Shaped holes are grouped by `(type, dim)` tuple before distance comparison.

4. **Squared distance comparisons**: Inner loops use `dist_sq < threshold²` instead of `math.sqrt()`, only computing sqrt when needed for normalization.

5. **Profiling**: Each `run_analysis()` call produces a `_timing.json` file with per-step and sub-step timings. Use these to identify bottlenecks across different STEP files.

### Sheet Metal Unfold Strategy

Multi-attempt strategy:
1. Try largest planar face as base
2. If failed, try 2nd and 3rd largest planar faces
3. For assemblies, try each solid separately
4. If all fail, calculate theoretical unfold from bend geometry

**Why unfold fails**:
- Non-uniform thickness (variable gauge)
- Complex bends (lofted, conical)
- Assembled parts (welded/riveted)
- Incorrect geometry in STEP file

### Bend Counting for ERP

**Business rule**: Not all bends count for production cost estimation:

- **Count**: Bends on fabricated sheet metal (angle 45-135 deg, radius 0.3-15mm)
- **Don't count**: Bends on purchased profiles (koker, U-profiel, hoekprofiel)
- **Don't count**: Very small radii (<0.3mm) - likely fillets/chamfers
- **Don't count**: Very large radii (>15mm) - likely formed features

### Assembly Handling

For multi-solid STEP files (assemblies):
1. Analyzes each solid separately
2. Matches individual solids to Spaceclaim data using volume as primary key
3. Volume is the most reliable identifier (constant even when unfolded)

### FreeCAD Python Path

The project uses **FreeCAD's bundled Python** for unfold operations:
```bash
/opt/homebrew/Caskroom/freecad/1.0.2/FreeCAD.app/Contents/Resources/bin/python
```

This is required because the SheetMetal workbench only works with FreeCAD's Python environment.

## Pipeline Caching System

The full pipeline supports checkpoint/resume functionality.

### Pipeline Stages (in order)

| Stage | Description |
|-------|-------------|
| `load_step` | Load and parse STEP file |
| `detect_holes` | Detect cylindrical holes |
| `geometry_analysis` | Volume, surface area, bounding box |
| `face_analysis` | Classify face types |
| `topology` | Topology statistics |
| `component_classification` | Classify component types |
| `detailed_parts` | Detailed part analysis with images |
| `manufacturing_requirements` | ISO 2768 tolerances, surface finish |
| `holes_with_fits` | ISO 286 fit analysis |
| `threads` | ISO 68-1 thread detection |
| `chamfers_fillets` | ISO 13715 edge analysis |
| `mass_properties` | Material mass calculations |
| `pdf_correlation` | Correlate with PDF dimensions |
| `complete` | Pipeline finished |

### Cache Behavior

- Results saved after each stage to `.pipeline_cache/`
- Cache invalidated if STEP file changes (MD5 hash)
- Clearing a stage also clears dependent stages
- Use `--status` to see progress, `--from <stage>` to resume

## Key Dependencies

All in `requirements.txt`:

- **cadquery** / **cadquery-ocp**: CAD kernel for STEP file processing
- **reportlab**: PDF report generation
- **svglib**: SVG to PDF conversion
- **pymupdf**: PDF parsing
- **numpy**: Numerical operations
- **openpyxl**: Excel export (SpaceClaim format comparison)
- **fastapi**: REST API framework
- **uvicorn**: ASGI server
- **pydantic**: Request/response validation

File watcher dependencies (separate, in `deploy/requirements-watcher.txt`):
- **watchdog**: Filesystem monitoring
- **python-dotenv**: Environment variable loading

## Docker / API Deployment

### Quick Start
```bash
export API_KEYS=your-secret-key
docker compose -f deploy/docker-compose.yml up -d
curl http://localhost:8000/api/v1/health
```

### API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/analyze` | Upload STEP file, returns job_id |
| GET | `/api/v1/jobs/{job_id}` | Poll job status, get results (JSON) |
| GET | `/api/v1/jobs/{job_id}?format=csv` | Results as CSV |
| GET | `/api/v1/jobs/{job_id}?format=xml` | Results as SpaceClaim XML |
| GET | `/api/v1/jobs/{job_id}?format=excel` | Results as Excel (.xlsx, SpaceClaim format) |
| GET | `/api/v1/health` | Health check |

### VPS Setup (Ubuntu)
```bash
apt update && apt install docker.io docker-compose-v2 nginx certbot python3-certbot-nginx
git clone <repo> /opt/manufacturing-api
cd /opt/manufacturing-api
echo "API_KEYS=your-key" > .env
docker compose -f deploy/docker-compose.yml up -d
# Configure nginx: copy deploy/nginx.conf to /etc/nginx/sites-available/
# Add SSL: certbot --nginx -d api.example.com
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `API_KEYS` | (none) | Comma-separated API keys. Empty = no auth (dev mode) |
| `FREECAD_PATH` | `/usr/lib/freecad` | FreeCAD installation path |
| `UPLOAD_DIR` | `/tmp/manufacturing-uploads` | Temp directory for uploaded files |
| `MAX_FILE_SIZE_MB` | `100` | Max upload size in MB |
| `JOB_TTL_SECONDS` | `3600` | Job cleanup after N seconds |

## Development Workflow

### Adding New Features

1. Add detection logic to `analysis/step_processing.py` or `analysis/sheetmetal_analysis.py`
2. Add caching in `data/cache_manager.py` if expensive
3. Update report in `reporting/report_generator.py`
4. Add tests in `manufacturing_pipeline/tests/`
5. Update this CLAUDE.md

### Testing Changes

```bash
python -m pytest
python run.py -f mypart.step --analyze
python manufacturing_pipeline/scripts/compare_erp.py data/parts/AI-voorbeelden/ -v
```

### Common Debugging

**Hole detection issues**:
```bash
python run.py -f mypart.step --debug
```

**Unfold failures**: Check `analysis/freecad_unfold.py` logs.

**Bend counting mismatches**: Check `analysis/part_analyzer.py` business logic.

### Code Style

- **Explicit is better than implicit**: Add comments explaining "why"
- **Business rules**: Document in comments
- **Dutch terminology**: Use in output (gaten, zettingen) but English in code
- **Graceful degradation**: Fall back to 3D analysis if unfold fails

## Notes

- **STEP files**: Place in `data/input/` or `data/parts/`
- **Generated outputs**: Go to `data/output/`
- **Database**: `data/db/manufacturing_data.db`
- **Cache**: `.pipeline_cache/` (safe to delete for fresh analysis)
- **FreeCAD path**: Hardcoded for macOS; update for other platforms
