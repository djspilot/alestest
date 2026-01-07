# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a **manufacturing analysis pipeline** that processes STEP CAD files to extract geometric data, analyze components, detect holes/features, and generate reports. The pipeline includes comprehensive **Dutch/ISO manufacturing standards** analysis for tolerances, fits, threads, surface finish, and material calculations.

The project includes four main analysis approaches:
1. **Main pipeline** ([manufacturing_pipeline/](manufacturing_pipeline/)) - Full ISO standards analysis with database storage
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
# Run the main analysis pipeline
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
```

### Simple Runner (Quick Analysis with Reasoning)
```bash
# Interactive file selection
python run.py

# Analyze specific file
python run.py -f parts/mypart.step

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

# Process all files in ./parts/
python run.py --batch

# List available STEP files
python run.py --list
```

### ERP Comparison Tool
```bash
# Compare pipeline results with ERP/Spaceclaim data
# Processes folders with STEP, Excel (.xlsx), and XML files
python scripts/compare_erp.py AI-voorbeelden/

# Use AAG feature recognition
python scripts/compare_erp.py AI-voorbeelden/ --aag

# Process specific subfolder
python scripts/compare_erp.py AI-voorbeelden/ --subfolder "Subfolder Name"

# Verbose output
python scripts/compare_erp.py AI-voorbeelden/ -v
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
```

## Project Structure

```
/
├── manufacturing_pipeline/           # Main pipeline (Core Application Logic)
│   ├── main.py                       # Entry point - orchestrates full pipeline with caching
│   ├── requirements.txt              # Python dependencies
│   └── src/                          # Core analysis modules (Business Logic)
│       ├── step_processing.py        # STEP parsing, hole/bend detection, geometry analysis
│       ├── iso_standards.py          # ISO/NEN standards (tolerances, fits, threads, surface finish)
│       ├── sheetmetal_analysis.py    # Sheet metal specific analysis (thickness, bends, profiles)
│       └── ... (other core modules)
│
├── scripts/                          # Utility & Testing Scripts (Development Tools)
│   ├── pipeline_functions.py         # Shared logic for scripts
│   ├── compare_erp.py                # Validation tool for ERP comparison
│   ├── batch_process.py              # Batch processing runner
│   ├── test_*.py                     # Various test scripts
│   └── debug_*.py                    # Debugging helpers
│
├── run.py                            # Simple runner - quick analysis entry point
│
├── resources/                        # Project Resources & Data
│   ├── parts/                        # Input STEP files
│   ├── output/                       # Analysis results (Reports, Images, JSON)
│   ├── data/                         # Database and reference files (Excel, DB)
│   ├── docs/                         # Additional documentation
│   └── examples/                     # Sample files
│
├── CLAUDE.md                         # Project documentation
└── RESEARCH_QUESTIONS.md             # Research notes
```

## Manufacturing Pipeline vs Scripts

It is important to understand the distinction between the two code directories:

### 1. `manufacturing_pipeline/` (The Application)
This folder contains the **production-ready core code**. It is structured as a proper Python package.
- **`src/`**: Contains the actual business logic, classes, and algorithms.
- **`main.py`**: The official entry point for running the full analysis.
- **Purpose**: This is the "product". It handles the heavy lifting of geometry analysis, ISO standards, database storage, and caching.

### 2. `scripts/` (The Toolbelt)
This folder contains **utilities, tests, and wrappers** that use the pipeline.
- **Purpose**: These are tools for developers and analysts to validate the pipeline, run batches, or debug specific issues.
- **Dependency**: These scripts Import modules from `manufacturing_pipeline/src` to do their work.
- **Key Scripts**:
    - `compare_erp.py`: Critical for validating the code against "Ground Truth" data (Excel/Spaceclaim).
    - `batch_process.py`: Runs the pipeline on many files at once.
    - `debug_*.py`: Helps isolate specific problems (like bend detection).

### Note on `src` folders
- **Root `src/`**: This folder was empty (only containing `__pycache__`) and has been removed to avoid confusion.
- **`manufacturing_pipeline/src/`**: **DO NOT DELETE**. This is where the actual code lives. It contains all the intelligence for STEP processing and analysis.

## Architecture

### Core Analysis Flow

The project has multiple entry points for different use cases:

1. **Main Pipeline Flow** (`manufacturing_pipeline/main.py`):
   - Load STEP → Detect holes/bends → Classify part type → Apply ISO standards → Generate report → Store in database
   - **Caching system**: Each stage is cached to `.pipeline_cache/` for fast re-runs
   - **Multi-solid support**: Analyzes assemblies by processing each solid separately

2. **Simple Runner Flow** (`run.py`):
   - Load STEP → Classify part (sheet metal/profile/turned) → Detect features → Unfold if applicable → Generate reasoning-based PDF
   - **FreeCAD integration**: Uses FreeCAD Python for sheet metal unfolding
   - **Detailed reasoning**: Explains every decision (why a part is classified as sheet metal, why unfold failed, etc.)

3. **ERP Comparison Flow** ([scripts/compare_erp.py](scripts/compare_erp.py)):
   - Parse ERP Excel + Spaceclaim XML → Analyze STEP with pipeline → Compare results → Report matches/mismatches
   - **Smart matching**: For assemblies, matches individual solids to Spaceclaim data using volume/hole/bend counts
   - **AAG mode**: Optional topology-based feature recognition for higher accuracy

### Key Module Responsibilities

**STEP Processing** ([step_processing.py](manufacturing_pipeline/src/step_processing.py)):
- Load STEP files using CadQuery/OCP
- Detect holes: cylindrical (via cylindrical faces) and shaped (via inner wires on planar faces)
- Detect bends: identify cylindrical bend faces with radius/angle
- Classify face types (planar, cylindrical, conical, etc.)
- Generate part images as SVG

**Sheet Metal Analysis** ([sheetmetal_analysis.py](manufacturing_pipeline/src/sheetmetal_analysis.py)):
- Detect thickness from parallel planar faces
- Classify profiles (closed/open, koker/U-profiel/hoekprofiel)
- Count bends for ERP (excludes certain bend types per business rules)
- Determine if part is purchased profile vs fabricated sheet metal

**Part Analyzer** ([part_analyzer.py](manufacturing_pipeline/src/part_analyzer.py)):
- High-level classification: sheet metal, turned part, profile, or other
- Business logic for bend counting (e.g., profile bends don't count for production)
- Reasoning system: tracks why decisions were made
- Determines unfold feasibility

**FreeCAD Unfold** ([freecad_unfold.py](manufacturing_pipeline/src/freecad_unfold.py)):
- Integrates with FreeCAD's SheetMetal workbench
- Tries multiple base faces if initial unfold fails
- Exports flat pattern as DXF
- Calculates theoretical unfold if automatic unfold fails

**AAG Analyzer** ([scripts/aag_analyzer.py](scripts/aag_analyzer.py)):
- Builds Attributed Adjacency Graph (nodes=faces, arcs=edges with convexity)
- Topology-based feature recognition (more robust than geometry-only)
- Isoperimetric Quotient for hole/slot classification (Q=4πA/P², Q≈1 for circles)
- K-factor based bend allowance/deduction calculations
- Laser cutting time estimation

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

1. **Cylindrical face method** (`detect_holes`):
   - Finds cylindrical faces on the part
   - Filters for internal cylinders (holes) vs external (shafts)
   - Works well for through-holes and deep holes
   - Returns diameter, depth, orientation

2. **Inner wire method** (`detect_shaped_holes`):
   - Finds inner wires on planar faces (wires inside the outer boundary)
   - Detects slots, rectangles, complex shapes that aren't pure cylinders
   - Essential for laser-cut parts with non-circular holes
   - Works on flat pattern after unfold

**Best practice**: Use both methods and combine results. For sheet metal, run inner wire detection on the unfolded flat pattern for maximum accuracy.

### Sheet Metal Unfold Strategy

The FreeCAD unfold uses a **multi-attempt strategy**:

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

- ✅ **Count**: Bends on fabricated sheet metal parts (angle 45-135°, radius 0.3-15mm)
- ❌ **Don't count**: Bends on purchased profiles (koker, U-profiel, hoekprofiel)
- ❌ **Don't count**: Very small radii (<0.3mm) - likely fillets/chamfers
- ❌ **Don't count**: Very large radii (>15mm) - likely formed features

This logic is in `part_analyzer.py` and `sheetmetal_analysis.py`.

### Assembly Handling

For multi-solid STEP files (assemblies):

1. **Main pipeline**: Analyzes each solid separately, stores per-solid results
2. **ERP comparison**: Matches individual solids to Spaceclaim data using volume as primary key
3. **Volume matching**: Most reliable identifier (material volume is constant even when unfolded)

### FreeCAD Python Path

The project uses **FreeCAD's bundled Python** for unfold operations:
```bash
/opt/homebrew/Caskroom/freecad/1.0.2/FreeCAD.app/Contents/Resources/bin/python
```

This is required because the SheetMetal workbench only works with FreeCAD's Python environment.

## Key Dependencies

- **cadquery** / **cadquery-ocp**: CAD kernel for STEP file processing and geometry analysis
- **reportlab**: PDF report generation
- **svglib**: SVG to PDF conversion for part images
- **pymupdf**: PDF parsing and extraction
- **numpy**: Numerical operations

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

### Example Workflow

```bash
# First run - computes all stages
python main.py -f part.step

# Modify code in report_generator.py, re-run
# All cached stages are reused, only report is regenerated
python main.py -f part.step

# Force re-run from threads stage onwards
python main.py -f part.step --from threads

# Debug mode - run everything fresh
python main.py -f part.step --no-cache
```

## Development Workflow

### Adding New Features

When adding new analysis features:

1. **Add detection logic** to [step_processing.py](manufacturing_pipeline/src/step_processing.py) or [sheetmetal_analysis.py](manufacturing_pipeline/src/sheetmetal_analysis.py)
2. **Add caching** in [cache_manager.py](manufacturing_pipeline/src/cache_manager.py) if the operation is expensive
3. **Update report** in [report_generator.py](manufacturing_pipeline/src/report_generator.py) to display results
4. **Add tests** in `test_accuracy.py` or create new test file
5. **Update this CLAUDE.md** with usage examples

### Testing Changes

```bash
# Test against known ERP data
python scripts/test_accuracy.py

# Test specific part
python run.py -f parts/mypart.step --analyze

# Compare with Spaceclaim
python scripts/compare_erp.py AI-voorbeelden/ -v

# Run full pipeline
python manufacturing_pipeline/main.py -f mypart.step
```

### Common Debugging Tasks

**Hole detection issues**:
```bash
python run.py -f mypart.step --debug
```
Shows all cylindrical faces, why they were classified as holes/rejected, diameter distribution.

**Unfold failures**:
Check [freecad_unfold.py](manufacturing_pipeline/src/freecad_unfold.py) logs. Common issues:
- Base face selection (try different largest planar faces)
- SheetMetal workbench not installed
- Complex geometry (non-uniform thickness)

**Bend counting mismatches**:
Check [part_analyzer.py](manufacturing_pipeline/src/part_analyzer.py) business logic. Verify:
- Is part classified as profile? (profiles don't count bends)
- Are bend radii in range 0.3-15mm?
- Are bend angles in range 45-135°?

### Working with FreeCAD

The project requires FreeCAD for unfold operations. Key points:

- **Headless mode**: Mock FreeCADGui for subprocess execution
- **SheetMetal workbench**: Must be installed in FreeCAD
- **Python path**: Use FreeCAD's bundled Python, not system Python
- **Error handling**: FreeCAD can crash; always wrap in try/except with subprocess timeout

### Code Style

- **Explicit is better than implicit**: Add comments explaining "why", not "what"
- **Business rules**: Document in comments (e.g., "ERP doesn't count profile bends")
- **Dutch terminology**: Use in output (gaten, zettingen) but English in code
- **Graceful degradation**: If unfold fails, fall back to 3D analysis; never crash

## Notes

- **Folder structure**:
  - Place STEP files in [resources/parts/](resources/parts/) for [run.py](run.py).
  - Sample files are in [resources/examples/](resources/examples/)
  - ERP/test data goes in [resources/data/](resources/data/).
  - Utility scripts are in [scripts/](scripts/)
- **For ERP comparison**: Organize as `resources/parts/AI-voorbeelden/subfolder/` with STEP + Excel (.xlsx) + XML files
- **Generated outputs**:
  - Images: `resources/output/*/images/`
  - Results: JSON and PDF reports in [resources/output/](resources/output/)
  - Database: [resources/data/manufacturing_data.db](resources/data/manufacturing_data.db)
- **PDF reports** include dedicated sections for each ISO standard
- **Material mass** is calculated for multiple materials (steel/aluminum variants)
- **Cache files** are stored in `.pipeline_cache/` (can be safely deleted to force re-analysis)
- **FreeCAD path** is hardcoded for macOS; update in [scripts/compare_erp.py](scripts/compare_erp.py) and [run.py](run.py) for other platforms
