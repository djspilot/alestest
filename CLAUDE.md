# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a **manufacturing analysis pipeline** that processes STEP CAD files to extract geometric data, analyze components, detect holes/features, and generate reports. The pipeline includes comprehensive **Dutch/ISO manufacturing standards** analysis for tolerances, fits, threads, surface finish, and material calculations.

The project includes four main analysis approaches:
1. **Main pipeline** ([manufacturing_pipeline/](manufacturing_pipeline/)) - Full ISO standards analysis with database storage, modular architecture, and caching
2. **Simple runner** ([run.py](run.py)) - Streamlined analysis with detailed reasoning and PDF reports
3. **ERP comparison** ([scripts/compare_erp.py](scripts/compare_erp.py)) - Validates pipeline results against ERP/Spaceclaim data
4. **AAG analyzer** ([scripts/aag_analyzer.py](scripts/aag_analyzer.py)) - Advanced Attributed Adjacency Graph-based feature recognition

## Key Commands

### Installation
```bash
# Install dependencies (pip - quick start)
pip install -r manufacturing_pipeline/requirements.txt

# Install dependencies (conda - recommended for stability)
conda create -n manufacturing python=3.10
conda activate manufacturing
conda install -c conda-forge cadquery
pip install -r manufacturing_pipeline/requirements.txt
```

### Main Pipeline (Full Analysis with ISO Standards)
```bash
# Run the main analysis pipeline (default: core_one_assembly.step)
python manufacturing_pipeline/main.py

# Run with specific STEP file
python manufacturing_pipeline/main.py -f mypart.step

# Run without caching (fresh analysis)
python manufacturing_pipeline/main.py --no-cache

# Resume from specific stage
python manufacturing_pipeline/main.py --from threads

# Show cache status
python manufacturing_pipeline/main.py --status

# Clear cache
python manufacturing_pipeline/main.py --clear-cache

# List available stages
python manufacturing_pipeline/main.py --list-stages

# Show detailed production information table
python manufacturing_pipeline/main.py --production-info

# Show ONLY production info (skip full report)
python manufacturing_pipeline/main.py --production-only

# Skip PDF report generation
python manufacturing_pipeline/main.py --no-report

# Module control
python manufacturing_pipeline/main.py --disable cost_estimation
python manufacturing_pipeline/main.py --disable werkvoorbereiding
python manufacturing_pipeline/main.py --list-modules
python manufacturing_pipeline/main.py --show-config

# Material and quantity for cost estimation
python manufacturing_pipeline/main.py --material steel_s355 --quantity 10
```

### Simple Runner (Quick Analysis with Reasoning)
```bash
# Interactive file selection
python run.py

# Analyze specific file (looks in ./resources/parts/)
python run.py -f mypart.step

# Show detailed analysis reasoning
python run.py --analyze

# Run AAG topology-based feature recognition
python run.py -f mypart.step --aag

# AAG with verbose output (hole/bend details)
python run.py -f mypart.step --aag -v

# Debug hole detection
python run.py --debug

# Skip automatic unfolding
python run.py --no-unfold

# Skip PDF generation
python run.py --no-pdf

# Process all files in ./resources/parts/
python run.py --batch

# List available STEP files
python run.py --list
```

### ERP Comparison Tool
```bash
# Compare pipeline results with ERP/Spaceclaim data
# Processes folders with STEP, Excel (.xlsx), and XML files
python scripts/compare_erp.py resources/parts/AI-voorbeelden/

# Use AAG feature recognition
python scripts/compare_erp.py resources/parts/AI-voorbeelden/ --aag

# Process specific subfolder
python scripts/compare_erp.py resources/parts/AI-voorbeelden/ --subfolder "20253511"

# Verbose output
python scripts/compare_erp.py resources/parts/AI-voorbeelden/ -v
```

### Testing and Validation
```bash
# Test detection accuracy against Excel data
python scripts/test_accuracy.py

# Test FreeCAD unfold functionality
python scripts/test_freecad.py

# Test unfold with hole detection
python scripts/test_unfold_holes.py

# Debug sheet metal bend detection
python scripts/debug_bends.py

# Inspect assembly structure
python scripts/inspect_assembly.py

# Inspect individual solids in a STEP file
python scripts/inspect_solids.py

# Debug Excel parsing
python scripts/debug_excel.py

# Probe STEP PMI (Product Manufacturing Information)
python scripts/probe_step_pmi.py

# Batch process multiple files
python scripts/batch_process.py
```

## Project Structure

```
/
├── manufacturing_pipeline/           # Main pipeline (Core Application Logic)
│   ├── main.py                       # Entry point - orchestrates full pipeline with caching
│   ├── requirements.txt              # Python dependencies
│   ├── README.md                     # Installation guide
│   ├── pipeline_config.json          # Module configuration (enabled/disabled modules)
│   ├── manufacturing_data.db         # SQLite database (analysis results)
│   ├── .pipeline_cache/              # Cache directory for stage results
│   ├── sql/                          # SQL schemas and migrations
│   ├── part_images/                  # Generated part images (legacy location)
│   └── src/                          # Core analysis modules (Business Logic)
│       ├── __init__.py               # Package initialization
│       ├── step_processing.py        # STEP parsing, hole/bend detection, geometry analysis
│       ├── iso_standards.py          # ISO/NEN standards (tolerances, fits, threads, surface finish)
│       ├── sheetmetal_analysis.py    # Sheet metal specific analysis (thickness, bends, profiles)
│       ├── part_analyzer.py          # Part classification and reasoning
│       ├── freecad_unfold.py         # FreeCAD integration for sheet metal unfolding
│       ├── assembly_analysis.py      # Multi-solid assembly handling
│       ├── werkvoorbereiding.py      # Production planning and cost estimation
│       ├── report_generator.py       # PDF report generation
│       ├── cache_manager.py          # Pipeline caching system
│       ├── config.py                 # Configuration management
│       ├── database.py               # Database operations
│       ├── models.py                 # Data models
│       ├── correlation.py            # Dimension correlation
│       ├── pdf_processing.py         # PDF parsing for dimension extraction
│       └── pmi_processing.py         # PMI (Product Manufacturing Information) extraction
│
├── scripts/                          # Utility & Testing Scripts (Development Tools)
│   ├── __init__.py                   # Package initialization
│   ├── pipeline_functions.py         # Shared logic for run.py and scripts
│   ├── compare_erp.py                # Validation tool for ERP comparison
│   ├── aag_analyzer.py               # Attributed Adjacency Graph feature recognition
│   ├── batch_process.py              # Batch processing runner
│   ├── test_accuracy.py              # Test detection accuracy
│   ├── test_freecad.py               # Test FreeCAD unfold
│   ├── test_unfold_holes.py          # Test unfold + hole detection
│   ├── debug_bends.py                # Debug bend detection
│   ├── debug_excel.py                # Debug Excel parsing
│   ├── inspect_assembly.py           # Inspect assembly structure
│   ├── inspect_solids.py             # Inspect individual solids
│   ├── inspect_unfold_tree.py        # Inspect unfold object tree
│   └── probe_step_pmi.py             # Probe STEP PMI data
│
├── run.py                            # Simple runner - quick analysis entry point
│
├── resources/                        # Project Resources & Data
│   ├── parts/                        # Input STEP files
│   │   ├── *.step                    # Individual STEP files
│   │   ├── AI-voorbeelden/           # ERP test data with subfolders
│   │   │   ├── 20253511/             # Subfolder with STEP + Excel + XML
│   │   │   ├── 20253512/             # Another subfolder
│   │   │   └── ...
│   │   └── part_images/              # Legacy part images
│   ├── output/                       # Analysis results (Reports, Images, JSON)
│   │   ├── <part_name>/              # Per-part output folder
│   │   │   ├── images/               # Part images (SVG/PNG)
│   │   │   ├── *_report.pdf          # Analysis report
│   │   │   └── *_results.json        # JSON results
│   │   └── aivoorbeelden/            # Batch processing results
│   ├── data/                         # Database and reference files
│   │   ├── manufacturing_data.db     # Main database (also in manufacturing_pipeline/)
│   │   └── *.xlsx                    # Reference Excel files
│   └── docs/                         # Additional documentation
│
├── examples/                         # Sample files and test data (root level)
│   ├── core_one_assembly.step        # Large assembly example
│   ├── core_one_assembly_report.pdf  # Example report
│   └── core_one_assembly_results.json# Example results
│
├── CLAUDE.md                         # Project documentation (this file)
├── RESEARCH_QUESTIONS.md             # Research notes
├── todo.md                           # Task tracking
└── .gitignore                        # Git ignore rules
```

## Manufacturing Pipeline vs Scripts

It is important to understand the distinction between the two code directories:

### 1. `manufacturing_pipeline/` (The Application)
This folder contains the **production-ready core code**. It is structured as a proper Python package.
- **`src/`**: Contains the actual business logic, classes, and algorithms.
- **`main.py`**: The official entry point for running the full analysis.
- **`pipeline_config.json`**: Modular configuration (enable/disable modules).
- **`.pipeline_cache/`**: Stage-by-stage caching for fast re-runs.
- **Purpose**: This is the "product". It handles the heavy lifting of geometry analysis, ISO standards, database storage, and caching.

### 2. `scripts/` (The Toolbelt)
This folder contains **utilities, tests, and wrappers** that use the pipeline.
- **Purpose**: These are tools for developers and analysts to validate the pipeline, run batches, or debug specific issues.
- **Dependency**: These scripts import modules from `manufacturing_pipeline/src` to do their work.
- **Key Scripts**:
    - `compare_erp.py`: Critical for validating the code against "Ground Truth" data (Excel/Spaceclaim).
    - `batch_process.py`: Runs the pipeline on many files at once.
    - `aag_analyzer.py`: Advanced topology-based feature recognition.
    - `debug_*.py`: Helps isolate specific problems (like bend detection).
    - `test_*.py`: Validation scripts for specific features.

### 3. `run.py` (Simple Entry Point)
- **Purpose**: Simplified runner that uses `scripts/pipeline_functions.py` for common operations.
- **Use case**: Quick analysis with reasoning, interactive file selection, debugging.
- **Difference from main.py**: No caching, simpler output, detailed reasoning explanations.

### Note on Directory Locations
- **`examples/`**: Located at **root level**, not under `resources/`. Contains large example files.
- **`resources/parts/`**: Primary location for STEP files to be analyzed.
- **`resources/output/`**: All analysis outputs (JSON, PDF, images).
- **`resources/data/`**: Database and reference files (Excel, DB).
- **Database locations**: The SQLite database exists in both `manufacturing_pipeline/manufacturing_data.db` and `resources/data/manufacturing_data.db` for historical reasons.

## Architecture

### Core Analysis Flow

The project has multiple entry points for different use cases:

1. **Main Pipeline Flow** (`manufacturing_pipeline/main.py`):
   - Load STEP → Detect holes/bends → Classify part type → Apply ISO standards → Generate report → Store in database
   - **Caching system**: Each stage is cached to `.pipeline_cache/` for fast re-runs
   - **Multi-solid support**: Analyzes assemblies by processing each solid separately
   - **Modular architecture**: Modules can be enabled/disabled via `pipeline_config.json`
   - **Production planning**: Optional werkvoorbereiding module for cost estimation

2. **Simple Runner Flow** (`run.py`):
   - Load STEP → Classify part (sheet metal/profile/turned) → Detect features → Unfold if applicable → Generate reasoning-based PDF
   - **FreeCAD integration**: Uses FreeCAD Python for sheet metal unfolding
   - **Detailed reasoning**: Explains every decision (why a part is classified as sheet metal, why unfold failed, etc.)
   - **No caching**: Always runs fresh analysis

3. **ERP Comparison Flow** ([scripts/compare_erp.py](scripts/compare_erp.py)):
   - Parse ERP Excel + Spaceclaim XML → Analyze STEP with pipeline → Compare results → Report matches/mismatches
   - **Smart matching**: For assemblies, matches individual solids to Spaceclaim data using volume/hole/bend counts
   - **AAG mode**: Optional topology-based feature recognition for higher accuracy

### Key Module Responsibilities

**STEP Processing** ([step_processing.py](manufacturing_pipeline/src/step_processing.py)):
- Load STEP files using CadQuery/OCP
- Detect holes: cylindrical (via cylindrical faces) and shaped (via inner wires on planar faces)
- Detect bends: identify cylindrical bend faces with radius/angle
- Classify face types (planar, cylindrical, conical, spherical, etc.)
- Generate part images as SVG
- Calculate bounding boxes, volumes, surface areas

**Sheet Metal Analysis** ([sheetmetal_analysis.py](manufacturing_pipeline/src/sheetmetal_analysis.py)):
- Detect thickness from parallel planar faces
- Classify profiles (closed/open, koker/U-profiel/hoekprofiel)
- Count bends for ERP (excludes certain bend types per business rules)
- Determine if part is purchased profile vs fabricated sheet metal
- Analyze bend sequences and complexity

**Part Analyzer** ([part_analyzer.py](manufacturing_pipeline/src/part_analyzer.py)):
- High-level classification: sheet metal, turned part, profile, or other
- Business logic for bend counting (e.g., profile bends don't count for production)
- Reasoning system: tracks why decisions were made
- Determines unfold feasibility
- Classifies part complexity

**FreeCAD Unfold** ([freecad_unfold.py](manufacturing_pipeline/src/freecad_unfold.py)):
- Integrates with FreeCAD's SheetMetal workbench
- Tries multiple base faces if initial unfold fails
- Exports flat pattern as DXF
- Calculates theoretical unfold if automatic unfold fails
- Handles both simple parts and complex assemblies

**Assembly Analysis** ([assembly_analysis.py](manufacturing_pipeline/src/assembly_analysis.py)):
- Detects and processes multi-solid STEP files
- Analyzes each solid independently
- Tracks relationships between solids
- Generates per-solid and assembly-level reports

**Werkvoorbereiding** ([werkvoorbereiding.py](manufacturing_pipeline/src/werkvoorbereiding.py)):
- Production planning and cost estimation
- Material cost calculations
- Labor time estimation
- Process selection (laser, bending, welding, etc.)
- Batch quantity optimization

**AAG Analyzer** ([scripts/aag_analyzer.py](scripts/aag_analyzer.py)):
- Builds Attributed Adjacency Graph (nodes=faces, arcs=edges with convexity)
- Topology-based feature recognition (more robust than geometry-only)
- Isoperimetric Quotient for hole/slot classification (Q=4πA/P², Q≈1 for circles)
- K-factor based bend allowance/deduction calculations
- Laser cutting time estimation
- Advanced feature recognition (pockets, protrusions, slots)

**ISO Standards** ([iso_standards.py](manufacturing_pipeline/src/iso_standards.py)):
- ISO 2768: General tolerances (linear & geometric)
- ISO 286: Limits and fits (H7/h6, etc.)
- ISO 1302: Surface roughness (Ra/Rz)
- ISO 68-1/261: Metric screw threads
- ISO 13715: Edge conditions (chamfers/fillets)
- EN 10025/573: Material density tables

**Report Generator** ([report_generator.py](manufacturing_pipeline/src/report_generator.py)):
- Creates comprehensive PDF reports with ISO standard sections
- Includes part images, dimension tables, hole/bend details
- Dedicated sections for each ISO standard
- Production information tables
- Assembly hierarchy visualization

**Cache Manager** ([cache_manager.py](manufacturing_pipeline/src/cache_manager.py)):
- Stage-by-stage caching with MD5 hash validation
- Dependency tracking (clearing a stage clears dependents)
- Resume from failure support
- Cache status reporting
- Configurable cache directory

**Configuration** ([config.py](manufacturing_pipeline/src/config.py)):
- Module enable/disable system
- Configuration file management (JSON)
- Default settings and overrides
- Material and quantity parameters

**Database** ([database.py](manufacturing_pipeline/src/database.py)):
- SQLite database operations
- Schema management
- Analysis result storage
- Query helpers

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

The pipeline uses **two complementary methods** to detect holes:

1. **Cylindrical face method** (`detect_holes` in [step_processing.py](manufacturing_pipeline/src/step_processing.py)):
   - Finds cylindrical faces on the part
   - Filters for internal cylinders (holes) vs external (shafts)
   - Works well for through-holes and deep holes
   - Returns diameter, depth, orientation
   - Uses face adjacency and topology to classify

2. **Inner wire method** (`detect_shaped_holes`):
   - Finds inner wires on planar faces (wires inside the outer boundary)
   - Detects slots, rectangles, complex shapes that aren't pure cylinders
   - Essential for laser-cut parts with non-circular holes
   - Works on flat pattern after unfold
   - Calculates area and perimeter for each hole

**Best practice**: Use both methods and combine results. For sheet metal, run inner wire detection on the unfolded flat pattern for maximum accuracy.

### Sheet Metal Unfold Strategy

The FreeCAD unfold uses a **multi-attempt strategy** in [freecad_unfold.py](manufacturing_pipeline/src/freecad_unfold.py):

1. Try largest planar face as base
2. If failed, try 2nd and 3rd largest planar faces
3. For assemblies, try each solid separately
4. If all fail, calculate theoretical unfold from bend geometry

**Why unfold fails**:
- Non-uniform thickness (variable gauge)
- Complex bends (lofted, conical)
- Assembled parts (welded/riveted)
- Incorrect geometry in STEP file
- Missing base face (no clear flat surface)

**Fallback behavior**:
- Calculate theoretical unfold dimensions from bend geometry
- Use 3D dimensions with bend allowance adjustments
- Report unfold failure with diagnostic information

### Bend Counting for ERP

**Business rule**: Not all bends count for production cost estimation:

- ✅ **Count**: Bends on fabricated sheet metal parts (angle 45-135°, radius 0.3-15mm)
- ❌ **Don't count**: Bends on purchased profiles (koker, U-profiel, hoekprofiel)
- ❌ **Don't count**: Very small radii (<0.3mm) - likely fillets/chamfers
- ❌ **Don't count**: Very large radii (>15mm) - likely formed features
- ❌ **Don't count**: Bends with angles outside 45-135° range

This logic is in [part_analyzer.py](manufacturing_pipeline/src/part_analyzer.py) and [sheetmetal_analysis.py](manufacturing_pipeline/src/sheetmetal_analysis.py).

### Assembly Handling

For multi-solid STEP files (assemblies):

1. **Main pipeline**: Analyzes each solid separately, stores per-solid results in database
2. **ERP comparison**: Matches individual solids to Spaceclaim data using volume as primary key
3. **Volume matching**: Most reliable identifier (material volume is constant even when unfolded)
4. **Fallback matching**: Uses hole count, bend count, and bounding box dimensions
5. **Assembly-level reporting**: Generates summary reports for entire assembly

### FreeCAD Python Path

The project uses **FreeCAD's bundled Python** for unfold operations:
```bash
/opt/homebrew/Caskroom/freecad/1.0.2/FreeCAD.app/Contents/Resources/bin/python
```

This is required because the SheetMetal workbench only works with FreeCAD's Python environment.

**Platform-specific paths**:
- **macOS**: `/opt/homebrew/Caskroom/freecad/*/FreeCAD.app/Contents/Resources/bin/python`
- **Windows**: `C:\Program Files\FreeCAD X.X\bin\python.exe`
- **Linux**: `/usr/bin/freecad` (run as command, not Python script)

Update the path in [freecad_unfold.py](manufacturing_pipeline/src/freecad_unfold.py), [run.py](run.py), and [scripts/compare_erp.py](scripts/compare_erp.py) for your platform.

## Key Dependencies

- **cadquery** / **cadquery-ocp**: CAD kernel for STEP file processing and geometry analysis
- **reportlab**: PDF report generation (not in requirements.txt, imported dynamically)
- **svglib**: SVG to PDF conversion for part images (not in requirements.txt)
- **pymupdf**: PDF parsing and extraction
- **numpy**: Numerical operations
- **opencv-python**: Image processing (not actively used)
- **edocr**: OCR for PDF text extraction

**Note**: Some dependencies are imported dynamically and may need to be installed separately:
```bash
pip install reportlab svglib
```

## Pipeline Caching System

The pipeline supports checkpoint/resume functionality to avoid recomputing expensive operations:

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

- **Automatic caching**: Results are saved after each stage to `.pipeline_cache/`
- **File change detection**: Cache is invalidated if the STEP file changes (MD5 hash)
- **Dependency tracking**: Clearing a stage also clears dependent stages
- **Resume from failure**: If pipeline fails, use `--status` to see progress, then `--from <stage>` to resume
- **Per-file caching**: Each STEP file has its own cache subdirectory

### Cache Directory Structure

```
.pipeline_cache/
├── mypart_step/                # Cache for mypart.step
│   ├── file_hash.txt           # MD5 hash for file change detection
│   ├── load_step.pkl           # Cached stage results (pickle)
│   ├── detect_holes.pkl
│   ├── geometry_analysis.pkl
│   └── ...
└── otherpart_step/             # Cache for otherpart.step
    └── ...
```

### Example Workflow

```bash
# First run - computes all stages
python manufacturing_pipeline/main.py -f part.step

# Modify code in report_generator.py, re-run
# All cached stages are reused, only report is regenerated
python manufacturing_pipeline/main.py -f part.step

# Force re-run from threads stage onwards
python manufacturing_pipeline/main.py -f part.step --from threads

# Debug mode - run everything fresh
python manufacturing_pipeline/main.py -f part.step --no-cache

# Check what's cached
python manufacturing_pipeline/main.py -f part.step --status
```

## Modular Architecture

The main pipeline supports enabling/disabling modules via `pipeline_config.json`:

### Available Modules

- **cost_estimation**: Production cost calculations
- **werkvoorbereiding**: Full production planning (includes cost_estimation)
- **pmi_processing**: Extract PMI from STEP files
- **pdf_correlation**: Correlate dimensions with PDF drawings
- **assembly_analysis**: Multi-solid assembly handling

### Module Control

```bash
# Disable cost estimation
python manufacturing_pipeline/main.py --disable cost_estimation

# Disable all werkvoorbereiding modules
python manufacturing_pipeline/main.py --disable werkvoorbereiding

# Enable PMI processing
python manufacturing_pipeline/main.py --enable pmi_processing

# List all modules
python manufacturing_pipeline/main.py --list-modules

# Show current configuration
python manufacturing_pipeline/main.py --show-config

# Save configuration to file
python manufacturing_pipeline/main.py --save-config my_config.json

# Load configuration from file
python manufacturing_pipeline/main.py --config my_config.json
```

## Development Workflow

### Adding New Features

When adding new analysis features:

1. **Add detection logic** to [step_processing.py](manufacturing_pipeline/src/step_processing.py) or [sheetmetal_analysis.py](manufacturing_pipeline/src/sheetmetal_analysis.py)
2. **Add caching** in [cache_manager.py](manufacturing_pipeline/src/cache_manager.py) if the operation is expensive
3. **Update report** in [report_generator.py](manufacturing_pipeline/src/report_generator.py) to display results
4. **Add database fields** in [database.py](manufacturing_pipeline/src/database.py) if storing results
5. **Add tests** in `scripts/test_accuracy.py` or create new test file
6. **Update this CLAUDE.md** with usage examples

### Testing Changes

```bash
# Test against known ERP data
python scripts/test_accuracy.py

# Test specific part with simple runner
python run.py -f resources/parts/mypart.step --analyze

# Compare with Spaceclaim data
python scripts/compare_erp.py resources/parts/AI-voorbeelden/ -v

# Run full pipeline with caching
python manufacturing_pipeline/main.py -f resources/parts/mypart.step

# Run full pipeline without cache (fresh)
python manufacturing_pipeline/main.py -f resources/parts/mypart.step --no-cache

# Test AAG analyzer
python run.py -f resources/parts/mypart.step --aag -v
```

### Common Debugging Tasks

**Hole detection issues**:
```bash
python run.py -f resources/parts/mypart.step --debug
```
Shows all cylindrical faces, why they were classified as holes/rejected, diameter distribution.

**Unfold failures**:
Check [freecad_unfold.py](manufacturing_pipeline/src/freecad_unfold.py) logs. Common issues:
- Base face selection (try different largest planar faces)
- SheetMetal workbench not installed in FreeCAD
- Complex geometry (non-uniform thickness)
- Incorrect FreeCAD Python path

**Bend counting mismatches**:
Check [part_analyzer.py](manufacturing_pipeline/src/part_analyzer.py) business logic. Verify:
- Is part classified as profile? (profiles don't count bends)
- Are bend radii in range 0.3-15mm?
- Are bend angles in range 45-135°?
- Use `--debug` flag to see bend classification reasoning

**ERP comparison mismatches**:
```bash
python scripts/compare_erp.py resources/parts/AI-voorbeelden/ -v
```
Shows detailed matching process, volume comparisons, and mismatch reasons.

**Assembly handling issues**:
```bash
python scripts/inspect_assembly.py resources/parts/assembly.step
python scripts/inspect_solids.py resources/parts/assembly.step
```
Shows solid count, per-solid properties, and assembly structure.

### Working with FreeCAD

The project requires FreeCAD for unfold operations. Key points:

- **Headless mode**: Mock FreeCADGui for subprocess execution
- **SheetMetal workbench**: Must be installed in FreeCAD
- **Python path**: Use FreeCAD's bundled Python, not system Python
- **Error handling**: FreeCAD can crash; always wrap in try/except with subprocess timeout
- **Subprocess execution**: FreeCAD runs as a separate process to isolate crashes

**FreeCAD SheetMetal Installation**:
1. Open FreeCAD
2. Go to Tools → Addon Manager
3. Search for "SheetMetal"
4. Install and restart FreeCAD

### Code Style

- **Explicit is better than implicit**: Add comments explaining "why", not "what"
- **Business rules**: Document in comments (e.g., "ERP doesn't count profile bends")
- **Dutch terminology**: Use in output (gaten, zettingen, plaatstaal) but English in code
- **Graceful degradation**: If unfold fails, fall back to 3D analysis; never crash
- **Type hints**: Use type hints where practical (especially in new code)
- **Docstrings**: Add docstrings for public functions and classes
- **Error handling**: Always catch and log exceptions, provide meaningful error messages

## Notes

- **Folder structure**:
  - Place STEP files in [resources/parts/](resources/parts/) for [run.py](run.py)
  - Sample files are in [examples/](examples/) (root level, not under resources)
  - ERP/test data goes in [resources/data/](resources/data/)
  - Utility scripts are in [scripts/](scripts/)

- **For ERP comparison**: Organize as `resources/parts/AI-voorbeelden/subfolder/` with STEP + Excel (.xlsx) + XML files
  - Each subfolder should contain one or more STEP files
  - Excel file contains ERP data (holes, bends, dimensions)
  - XML file contains Spaceclaim export data for validation

- **Generated outputs**:
  - Images: `resources/output/<part_name>/images/`
  - Results: JSON and PDF reports in `resources/output/<part_name>/`
  - Database: `manufacturing_pipeline/manufacturing_data.db` and `resources/data/manufacturing_data.db`
  - Cache: `.pipeline_cache/<part_name>/` (gitignored)

- **PDF reports** include dedicated sections for each ISO standard with detailed tables and explanations

- **Material mass** is calculated for multiple materials (steel/aluminum variants) with density from EN standards

- **Cache files** are stored in `.pipeline_cache/` (can be safely deleted to force re-analysis)

- **FreeCAD path** is hardcoded for macOS; update in [freecad_unfold.py](manufacturing_pipeline/src/freecad_unfold.py), [scripts/compare_erp.py](scripts/compare_erp.py), and [run.py](run.py) for other platforms

- **Database duplication**: The SQLite database exists in both locations for historical reasons. The main pipeline writes to `manufacturing_pipeline/manufacturing_data.db`.

- **Module architecture**: The pipeline is designed to be modular. Modules can be enabled/disabled without breaking the core functionality.

- **Production mode**: Use `--production-only` flag to get a concise production information table without the full PDF report (useful for ERP integration).

- **Batch processing**: The `--batch` flag in `run.py` processes all STEP files in `resources/parts/` sequentially.

## Research and Future Improvements

See [RESEARCH_QUESTIONS.md](RESEARCH_QUESTIONS.md) for ongoing research topics and planned improvements.

Key areas of investigation:
- AAG (Attributed Adjacency Graph) feature recognition improvements
- Machine learning for bend sequence optimization
- PMI (Product Manufacturing Information) extraction from STEP files
- Improved unfold success rate for complex geometries
- Cost estimation accuracy improvements
- Integration with ERP systems
