# ALES Manufacturing Pipeline

Automated analysis of STEP CAD files for manufacturing. Extracts geometry, detects features (holes, bends, threads), classifies parts, and generates production-ready reports with Dutch/ISO manufacturing standards.

Built for sheet metal fabrication shops that need fast, accurate work preparation data from 3D models.

## What It Does

```
┌─────────────┐     ┌──────────────────────────────────────────────────────┐     ┌──────────────┐
│             │     │            Manufacturing Pipeline                    │     │              │
│  STEP File  │────▶│                                                      │────▶│   Reports    │
│  (.step)    │     │  1. Load & parse 3D geometry (CadQuery/OCP)          │     │              │
│             │     │  2. Classify part type (sheet metal / profile / etc) │     │  - PDF       │
└─────────────┘     │  3. Detect features:                                 │     │  - Excel     │
                    │     - Holes (cylindrical + shaped)                   │     │  - XML       │
                    │     - Bends (radius, angle, K-factor)               │     │  - JSON      │
                    │     - Threads (M3–M68, ISO 68-1)                    │     │  - Database   │
                    │  4. Unfold sheet metal (FreeCAD)                     │     │              │
                    │  5. Apply ISO standards                              │     └──────────────┘
                    │  6. Generate reports                                 │
                    └──────────────────────────────────────────────────────┘
```

### Key Features

- **Part Classification** — Automatically identifies sheet metal, turned parts, profiles, assemblies
- **Hole Detection** — Cylindrical face detection + inner wire method for slots and shaped cutouts
- **Bend Analysis** — Counts production-relevant bends, excludes profiles and fillets
- **Sheet Metal Unfold** — FreeCAD SheetMetal workbench integration with multi-attempt strategy
- **AAG Feature Recognition** — Attributed Adjacency Graph for topology-based feature detection
- **ISO Standards** — ISO 2768, ISO 286, ISO 1302, ISO 68-1, ISO 13715, EN 10025/573
- **ERP Integration** — XML/Excel export in SpaceClaim format, Windows file watcher service
- **Batch Processing** — Parallel analysis of entire folders with caching

## Quick Start

### Prerequisites

- Python 3.10+
- [FreeCAD](https://www.freecad.org/) (optional, for sheet metal unfolding)

### Installation

```bash
git clone https://github.com/your-org/ales-manufacturing-pipeline.git
cd ales-manufacturing-pipeline

pip install -r requirements.txt
```

### Analyze a Part

```bash
# Interactive file selection
python run.py

# Analyze a specific file
python run.py -f data/input/mypart.step

# AAG topology analysis with verbose output
python run.py -f mypart.step --aag -v
```

Output goes to `data/output/<partname>/` — includes PDF report, SVG images, and analysis data.

## Usage Modes

### 1. Quick Mode (Default)

Fast analysis with PDF report generation. Best for day-to-day work preparation.

```bash
python run.py -f mypart.step              # Basic analysis
python run.py -f mypart.step --aag        # With AAG feature recognition
python run.py -f mypart.step --excel      # Excel export (SpaceClaim format)
python run.py -f mypart.step --analyze    # Show detailed reasoning
python run.py -f mypart.step --debug      # Debug hole detection
```

### 2. Batch Processing

Process entire folders. Results cached for fast re-runs.

```bash
python run.py --batch                             # All files in data/input/
python run.py -f ./folder --batch -p 4            # Parallel (4 workers)
python run.py --batch --json                      # JSON output for ERP
python run.py --batch --excel --reference ref.xlsx # With SpaceClaim comparison
python run.py --batch --no-cache                  # Force re-analysis
```

### 3. Full ISO Pipeline

Complete analysis with database storage and all ISO standard checks.

```bash
python run.py -f mypart.step --full                    # Full pipeline
python run.py -f mypart.step --full --production-info  # With production table
python run.py --full --status                          # Show cache status
python run.py --full --from threads                    # Resume from stage
python run.py --full --list-stages                     # List all stages
```

### 4. REST API (Docker)

Deploy as a web service for remote analysis.

```bash
docker compose up -d
```

```bash
# Upload a file for analysis
curl -X POST http://localhost:8000/api/v1/analyze \
  -H "X-API-Key: your-key" \
  -F "file=@mypart.step"

# Poll for results
curl http://localhost:8000/api/v1/jobs/{job_id} \
  -H "X-API-Key: your-key"

# Get results in different formats
curl "http://localhost:8000/api/v1/jobs/{job_id}?format=excel"
curl "http://localhost:8000/api/v1/jobs/{job_id}?format=xml"
```

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                        Entry Points                              │
│                                                                  │
│  run.py ──────────────┐                                          │
│  python -m mfg_pipe ──┤                                          │
│                       ▼                                          │
│               manufacturing_pipeline/cli.py                      │
│                       │                                          │
│         ┌─────────────┼─────────────┐                            │
│         ▼             ▼             ▼                            │
│    ┌─────────┐  ┌──────────┐  ┌───────────┐                     │
│    │  core/  │  │ analysis/│  │ reporting/│                     │
│    │         │  │          │  │           │                     │
│    │ config  │  │ step_proc│  │ PDF       │                     │
│    │ models  │  │ sheetmtl │  │ Excel     │                     │
│    │ utils   │  │ analyzer │  │ XML       │                     │
│    │         │  │ iso_std  │  │ CLI output│                     │
│    └─────────┘  │ freecad  │  └───────────┘                     │
│                 │ aag      │                                     │
│                 └──────────┘                                     │
│                                                                  │
│  api/app.py ──▶ api/routes.py ──▶ manufacturing_pipeline (same) │
│  file_watcher ──▶ monitors folder ──▶ manufacturing_pipeline     │
└──────────────────────────────────────────────────────────────────┘
```

### Analysis Pipeline Flow

```
                    Quick Mode                              Full Mode
                    ──────────                              ─────────

              ┌──────────────┐                      ┌──────────────────┐
              │  Load STEP   │                      │    Load STEP     │
              └──────┬───────┘                      └────────┬─────────┘
                     │                                       │
              ┌──────▼───────┐                      ┌────────▼─────────┐
              │ Classify Part│                      │  Detect Holes    │
              │  (type, thk) │                      │  & Bends         │
              └──────┬───────┘                      └────────┬─────────┘
                     │                                       │
              ┌──────▼───────┐                      ┌────────▼─────────┐
              │   Detect     │                      │  Geometry &      │
              │   Features   │                      │  Face Analysis   │
              └──────┬───────┘                      └────────┬─────────┘
                     │                                       │
              ┌──────▼───────┐                      ┌────────▼─────────┐
              │  Unfold      │                      │  Part            │
              │ (if sheet)   │                      │  Classification  │
              └──────┬───────┘                      └────────┬─────────┘
                     │                                       │
              ┌──────▼───────┐                      ┌────────▼─────────┐
              │ Generate PDF │                      │  ISO Standards   │
              │              │                      │  (2768/286/etc)  │
              └──────────────┘                      └────────┬─────────┘
                                                             │
                                                    ┌────────▼─────────┐
                                                    │  Report + DB     │
                                                    └──────────────────┘
```

## ISO Standards

The pipeline implements the following manufacturing standards:

| Standard | What It Does |
|----------|-------------|
| **ISO 2768** | General tolerances — linear (f/m/c/v) and geometric (H/K/L) |
| **ISO 286** | Limits and fits — H7/h6, H7/g6, IT grades |
| **ISO 1302** | Surface texture — Ra/Rz values by manufacturing process |
| **ISO 68-1/261** | Metric threads — M3 to M68, coarse/fine pitch, tap drill sizes |
| **ISO 13715** | Edge conditions — chamfer/fillet detection |
| **EN 10025** | Steel grades — S235, S275, S355, C45, 42CrMo4, 304/316 SS |
| **EN 573** | Aluminum alloys — 1050, 5083, 6061, 6082, 7075 |

## API Reference

### Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/analyze` | Upload STEP file, returns `job_id` |
| `GET` | `/api/v1/jobs/{job_id}` | Get results (JSON by default) |
| `GET` | `/api/v1/jobs/{job_id}?format=csv` | Results as CSV |
| `GET` | `/api/v1/jobs/{job_id}?format=xml` | Results as SpaceClaim XML |
| `GET` | `/api/v1/jobs/{job_id}?format=excel` | Results as Excel (.xlsx) |
| `GET` | `/api/v1/health` | Health check |

### Authentication

Set the `API_KEYS` environment variable (comma-separated for multiple keys). Pass the key via the `X-API-Key` header. Leave `API_KEYS` empty for development mode (no auth).

## Deployment

### Docker (Recommended)

```bash
# Configure
cp .env.example .env
# Edit .env — set API_KEYS at minimum

# Run
docker compose up -d

# Verify
curl http://localhost:8000/api/v1/health
```

### VPS Setup (Ubuntu)

```bash
apt update && apt install docker.io docker-compose-v2 nginx certbot python3-certbot-nginx

git clone <repo> /opt/manufacturing-api
cd /opt/manufacturing-api
echo "API_KEYS=your-secret-key" > .env
docker compose up -d

# Nginx reverse proxy
cp deploy/nginx.conf /etc/nginx/sites-available/manufacturing-api
ln -s /etc/nginx/sites-available/manufacturing-api /etc/nginx/sites-enabled/
certbot --nginx -d api.yourdomain.com
```

### Windows ERP Integration (File Watcher)

Monitors a folder for new STEP files, processes them automatically, and exports XML for ERP import.

```bash
# Configure in .env
WATCHED_FOLDER=G:\ALES\Offerte-ALES

# Run
python deploy/file_watcher_service.py

# Test with a single file
python deploy/file_watcher_service.py --test --file path/to/file.step
```

Install as a Windows service with `deploy/install_windows_service.bat` (uses NSSM).

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `API_KEYS` | _(empty)_ | Comma-separated API keys |
| `FREECAD_PATH` | `/usr/lib/freecad` | FreeCAD installation path |
| `UPLOAD_DIR` | `/tmp/manufacturing-uploads` | Upload directory |
| `MAX_FILE_SIZE_MB` | `100` | Max upload size |
| `JOB_TTL_SECONDS` | `3600` | Job result TTL |
| `WATCHED_FOLDER` | — | Folder for file watcher |
| `ENABLE_UNFOLD` | `True` | Enable FreeCAD unfold |

## Project Structure

```
├── run.py                              # Entry point
├── Dockerfile                          # Docker image
├── docker-compose.yml                  # Docker orchestration
├── requirements.txt                    # Python dependencies
│
├── manufacturing_pipeline/             # Core package
│   ├── cli.py                          # CLI interface
│   ├── core/                           # Config, models, utilities
│   ├── analysis/                       # Business logic
│   │   ├── step_processing.py          #   STEP parsing, hole/bend detection
│   │   ├── sheetmetal_analysis.py      #   Sheet metal classification
│   │   ├── part_analyzer.py            #   Part type classification
│   │   ├── iso_standards.py            #   ISO/NEN standards
│   │   ├── freecad_unfold.py           #   FreeCAD unfold integration
│   │   └── ...
│   ├── data/                           # Caching, database
│   ├── reporting/                      # PDF, Excel, XML, CLI output
│   └── scripts/                        # AAG analyzer, ERP comparison
│
├── api/                                # REST API (FastAPI)
│   ├── app.py                          # Application setup
│   ├── routes.py                       # Endpoints
│   └── static/index.html              # Web frontend
│
├── deploy/                             # Deployment
│   ├── file_watcher_service.py         # Windows ERP file watcher
│   ├── nginx.conf                      # Reverse proxy config
│   └── install.sh                      # VPS setup script
│
├── tests/                              # Test suite
└── data/                               # Runtime data (gitignored)
    ├── input/                          # STEP files to analyze
    ├── output/                         # Analysis results
    └── db/                             # SQLite database
```

## Development

### Running Tests

```bash
python -m pytest tests/
```

### ERP Comparison Tool

Validate pipeline output against SpaceClaim reference data:

```bash
python manufacturing_pipeline/scripts/compare_erp.py data/parts/AI-voorbeelden/
python manufacturing_pipeline/scripts/compare_erp.py data/parts/AI-voorbeelden/ --aag -v
```

### Key Dependencies

| Package | Purpose |
|---------|---------|
| `cadquery` / `cadquery-ocp` | CAD kernel — STEP file parsing and geometry |
| `FreeCAD` + SheetMetal workbench | Sheet metal unfolding |
| `fastapi` + `uvicorn` | REST API |
| `openpyxl` | Excel export |
| `numpy` | Numerical operations |
| `reportlab` | PDF generation |

## License

Proprietary. Internal use only.
