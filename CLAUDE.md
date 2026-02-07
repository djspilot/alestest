# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a **manufacturing analysis pipeline** that processes STEP CAD files to extract geometric data, analyze components, detect holes/features, and generate reports. The pipeline includes comprehensive **Dutch/ISO manufacturing standards** analysis for tolerances, fits, threads, surface finish, and material calculations.

The project provides three analysis modes:
1. **Quick mode** (default via `run.py`) - Fast AAG-based analysis with simple reports
2. **Full mode** (`run.py --full` or `manufacturing_pipeline/cli.py`) - Complete ISO pipeline with database storage
3. **API mode** (`api/app.py`) - REST API for VPS deployment, accepts STEP uploads, returns JSON/CSV

## Key Commands

### Installation
```bash
# Install dependencies (pip - quick start)
pip install -r requirements.txt

# Install dependencies (conda - recommended for stability)
conda create -n manufacturing python=3.10
conda activate manufacturing
conda install -c conda-forge cadquery
pip install -r requirements.txt
```

### Quick Mode (Default - Fast Analysis)
```bash
# Interactive file selection
python run.py

# Analyze specific file
python run.py -f mypart.step

# Run AAG topology-based feature recognition
python run.py -f mypart.step --aag

# AAG with verbose output (hole/bend details)
python run.py -f mypart.step --aag -v

# Show detailed analysis reasoning
python run.py --analyze

# Debug hole detection
python run.py --debug

# Skip automatic unfolding
python run.py --no-unfold

# List available STEP files
python run.py --list
```

### Batch Processing
```bash
# Process all files in default parts folder
python run.py --batch

# Process folder with parallel workers
python run.py -f ./folder --batch -p 4

# JSON output for ERP integration
python run.py -f ./folder --batch --json

# Skip cache, force re-analysis
python run.py --batch --no-cache
```

### Full Mode (Complete ISO Pipeline)
```bash
# Full ISO pipeline with database storage
python run.py -f mypart.step --full

# Or use the CLI directly
python -m manufacturing_pipeline.cli -f mypart.step

# Show production information table
python run.py -f mypart.step --full --production-info

# Legacy entry point (backward compatible)
python manufacturing_pipeline/main.py -f mypart.step
```

### Full Mode - Cache Management
```bash
# Show cache status
python -m manufacturing_pipeline.cli --status

# Clear cache
python -m manufacturing_pipeline.cli --clear-cache

# Resume from specific stage
python -m manufacturing_pipeline.cli --from threads

# Run without caching
python -m manufacturing_pipeline.cli --no-cache

# List available stages
python -m manufacturing_pipeline.cli --list-stages
```

### Full Mode - Module Control
```bash
# List available modules
python -m manufacturing_pipeline.cli --list-modules

# Disable specific module
python -m manufacturing_pipeline.cli --disable cost_estimation

# Enable/disable combinations
python -m manufacturing_pipeline.cli --enable iso --disable cost_estimation

# Show current configuration
python -m manufacturing_pipeline.cli --show-config
```

### ERP Comparison Tool
```bash
# Compare pipeline results with ERP/Spaceclaim data
python manufacturing_pipeline/scripts/compare_erp.py AI-voorbeelden/

# Use AAG feature recognition
python manufacturing_pipeline/scripts/compare_erp.py AI-voorbeelden/ --aag

# Process specific subfolder
python manufacturing_pipeline/scripts/compare_erp.py AI-voorbeelden/ --subfolder "Subfolder Name"

# Verbose output
python manufacturing_pipeline/scripts/compare_erp.py AI-voorbeelden/ -v
```

### API Mode (VPS Deployment)
```bash
# Install API dependencies
pip install -r requirements-api.txt

# Start API server (development)
API_KEYS=your-key uvicorn api.app:app --reload --port 8000

# Docker deployment
docker compose up -d

# Upload a STEP file for analysis
curl -X POST http://localhost:8000/api/v1/analyze \
  -H "X-API-Key: your-key" \
  -F "file=@mypart.step"

# Poll job result (JSON)
curl http://localhost:8000/api/v1/jobs/{job_id} \
  -H "X-API-Key: your-key"

# Get result as CSV
curl http://localhost:8000/api/v1/jobs/{job_id}?format=csv \
  -H "X-API-Key: your-key"

# Health check
curl http://localhost:8000/api/v1/health
```

### Testing
```bash
# Run basic tests
python -m pytest tests/

# Test specific file
python tests/test_basic.py
```

## Project Structure

```
/
├── run.py                            # Unified entry point (Quick + Full modes)
├── requirements.txt                  # Python dependencies
├── requirements-api.txt              # API-specific dependencies (FastAPI, uvicorn)
├── CLAUDE.md                         # Project documentation (this file)
├── Dockerfile                        # Docker container image definition
├── docker-compose.yml                # Docker orchestration for VPS deployment
│
├── api/                              # REST API Service (VPS deployment)
│   ├── __init__.py
│   ├── app.py                        # FastAPI application, middleware, CORS
│   ├── config.py                     # API configuration (env vars)
│   ├── schemas.py                    # Pydantic request/response models
│   ├── routes.py                     # API endpoints (analyze, jobs, health)
│   ├── analysis_service.py           # Bridge to manufacturing pipeline
│   └── job_manager.py                # In-memory job state management
│
├── deployment/                       # VPS Deployment Configuration
│   └── nginx.conf                    # Example nginx reverse proxy config
│
├── manufacturing_pipeline/           # Core Application Package
│   ├── __init__.py
│   ├── main.py                       # Legacy entry point (backward compat shim)
│   ├── cli.py                        # Full pipeline CLI with caching
│   ├── README.md                     # Package documentation
│   │
│   ├── core/                         # Core infrastructure
│   │   ├── config.py                 # Pipeline configuration, module settings
│   │   ├── models.py                 # Data models and types
│   │   ├── pipeline_init.py          # Pipeline initialization helpers
│   │   └── utils.py                  # Shared utilities, constants, helpers
│   │
│   ├── analysis/                     # Analysis modules (Business Logic)
│   │   ├── step_processing.py        # STEP parsing, hole/bend detection, geometry
│   │   ├── sheetmetal_analysis.py    # Sheet metal: thickness, bends, profiles
│   │   ├── part_analyzer.py          # Part classification, reasoning system
│   │   ├── iso_standards.py          # ISO/NEN standards (tolerances, fits, threads)
│   │   ├── freecad_unfold.py         # FreeCAD SheetMetal workbench integration
│   │   ├── assembly_analysis.py      # Assembly/BOM analysis
│   │   ├── pipeline_stages.py        # Pipeline stage definitions
│   │   ├── correlation.py            # Dimension correlation
│   │   └── werkvoorbereiding.py      # Work preparation analysis
│   │
│   ├── data/                         # Data layer
│   │   ├── cache_manager.py          # Pipeline caching system
│   │   ├── database.py               # SQLite database manager
│   │   └── sql/                      # SQL schema files
│   │       └── schema.sql
│   │
│   ├── reporting/                    # Output generation
│   │   ├── report_generator.py       # PDF report generation
│   │   ├── cli_output.py             # CLI output formatting
│   │   └── pdf_processing.py         # PDF parsing utilities
│   │
│   ├── scripts/                      # Utility scripts
│   │   ├── __init__.py
│   │   ├── README.md
│   │   ├── aag_analyzer.py           # AAG feature recognition
│   │   ├── compare_erp.py            # ERP validation tool
│   │   └── batch_process.py          # Batch processing runner
│   │
│   ├── resources/                    # Package-specific resources
│   └── .pipeline_cache/              # Cache directory (auto-created)
│
├── resources/                        # Project Resources & Data
│   ├── parts/                        # Default input folder for STEP files
│   ├── input/                        # Additional input files
│   ├── output/                       # Analysis results (Reports, Images, JSON)
│   ├── data/                         # Database and reference files
│   ├── config/                       # Configuration files
│   └── docs/                         # Additional documentation
│
├── tests/                            # Test suite
│   └── test_basic.py                 # Basic functionality tests
│
├── docs/                             # Project documentation
│   └── dev/                          # Developer documentation
│
└── archive/                          # Archived/deprecated code
    ├── README.md
    ├── scripts/                      # Old utility scripts
    └── modules/                      # Old modules
```

## Architecture

### Package Structure

The `manufacturing_pipeline` package is organized into logical subpackages:

| Subpackage | Purpose |
|------------|---------|
| `core/` | Configuration, models, utilities, constants |
| `analysis/` | All analysis algorithms (STEP processing, ISO standards, sheet metal) |
| `data/` | Data persistence (caching, database) |
| `reporting/` | Output generation (PDF reports, CLI output) |
| `scripts/` | Standalone utility scripts (AAG, ERP comparison) |

### Entry Points

1. **`run.py`** - Unified entry point (recommended)
   - Quick mode (default): Fast AAG-based analysis
   - Full mode (`--full`): Complete ISO pipeline
   - Batch mode (`--batch`): Process multiple files

2. **`manufacturing_pipeline/cli.py`** - Full pipeline CLI
   - Direct access to full pipeline with all options
   - Module enable/disable control
   - Cache management commands

3. **`manufacturing_pipeline/main.py`** - Legacy shim
   - Maintained for backward compatibility
   - Redirects to `cli.py`

4. **`api/app.py`** - REST API (VPS deployment)
   - Accepts STEP file uploads via HTTP POST
   - Async job processing via FastAPI BackgroundTasks
   - Returns JSON or CSV results
   - API key authentication via `X-API-Key` header

### Analysis Flow

**Quick Mode** (`run.py`):
```
Load STEP → Classify part → Detect features → Unfold (if applicable) → Generate PDF
```

**Full Mode** (`run.py --full` or `cli.py`):
```
Load STEP → Detect holes/bends → Classify part type → Apply ISO standards →
Generate report → Store in database
```

### Key Module Responsibilities

**STEP Processing** (`analysis/step_processing.py`):
- Load STEP files using CadQuery/OCP
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
- Isoperimetric Quotient for hole/slot classification (Q=4πA/P², Q≈1 for circles)
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

- ✅ **Count**: Bends on fabricated sheet metal (angle 45-135°, radius 0.3-15mm)
- ❌ **Don't count**: Bends on purchased profiles (koker, U-profiel, hoekprofiel)
- ❌ **Don't count**: Very small radii (<0.3mm) - likely fillets/chamfers
- ❌ **Don't count**: Very large radii (>15mm) - likely formed features

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

- **cadquery** / **cadquery-ocp**: CAD kernel for STEP file processing
- **reportlab**: PDF report generation
- **svglib**: SVG to PDF conversion
- **pymupdf**: PDF parsing
- **numpy**: Numerical operations

### API Dependencies (requirements-api.txt)

- **fastapi**: Web framework for REST API
- **uvicorn**: ASGI server
- **python-multipart**: File upload handling
- **pydantic**: Request/response validation

## Docker / VPS Deployment

### Quick Start
```bash
# Set API key and start
export API_KEYS=your-secret-key
docker compose up -d

# Verify
curl http://localhost:8000/api/v1/health
```

### API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/analyze` | Upload STEP file, returns job_id |
| GET | `/api/v1/jobs/{job_id}` | Poll job status, get results |
| GET | `/api/v1/health` | Health check |

### VPS Setup (Ubuntu)
```bash
# On VPS
apt update && apt install docker.io docker-compose-v2 nginx certbot python3-certbot-nginx
git clone <repo> /opt/manufacturing-api
cd /opt/manufacturing-api
echo "API_KEYS=your-key" > .env
docker compose up -d

# Configure nginx (copy deployment/nginx.conf to /etc/nginx/sites-available/)
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
4. Add tests in `tests/`
5. Update this CLAUDE.md

### Testing Changes

```bash
# Run tests
python -m pytest tests/

# Test specific part
python run.py -f parts/mypart.step --analyze

# Compare with Spaceclaim
python manufacturing_pipeline/scripts/compare_erp.py AI-voorbeelden/ -v
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

- **STEP files**: Place in `resources/parts/` for `run.py`
- **ERP data**: Organize as `resources/parts/AI-voorbeelden/subfolder/` with STEP + Excel + XML files
- **Generated outputs**: Go to `resources/output/`
- **Database**: `resources/data/manufacturing_data.db`
- **Cache**: `.pipeline_cache/` (safe to delete for fresh analysis)
- **FreeCAD path**: Hardcoded for macOS; update for other platforms
