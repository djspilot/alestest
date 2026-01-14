# Project Structure Refactoring Plan

This document outlines a plan to simplify the folder structure while keeping all functionality intact.

## Current Structure (Problems)

```
/
├── manufacturing_pipeline/           # Main pipeline
│   ├── main.py                       # ❌ Legacy entry point (redundant)
│   ├── src/                          # ❌ Unnecessary nesting
│   │   ├── 18 Python modules...
│   │   └── archive/
│   └── sql/
├── scripts/                          # ❌ Separate from main package
│   ├── pipeline_functions.py         # ❌ Core logic outside package
│   ├── aag_analyzer.py
│   ├── compare_erp.py
│   └── archive/                      # ❌ Multiple archive locations
├── resources/
│   ├── parts/                        # ❌ Duplicate input location
│   ├── output/
│   ├── data/
│   └── docs/
├── input/                            # ❌ Another input folder
├── run.py                            # Main entry point
└── CLAUDE.md
```

### Issues Identified

1. **Two entry points** - `run.py` and `manufacturing_pipeline/main.py`
2. **Unnecessary nesting** - `manufacturing_pipeline/src/` adds complexity
3. **Scattered code** - `scripts/pipeline_functions.py` contains core logic but lives outside the package
4. **Duplicate inputs** - Both `input/` and `resources/parts/` for STEP files
5. **Multiple archives** - `scripts/archive/` and `manufacturing_pipeline/src/archive/`

---

## Proposed Structure

```
/
├── manufacturing_pipeline/           # Flat Python package
│   ├── __init__.py
│   ├── cli.py                        # CLI entry point (from main.py)
│   ├── utils.py                      # Shared utilities (from scripts/pipeline_functions.py)
│   ├── step_processing.py            # All modules directly here (no src/)
│   ├── iso_standards.py
│   ├── cache_manager.py
│   ├── config.py
│   ├── models.py
│   ├── database.py
│   ├── correlation.py
│   ├── report_generator.py
│   ├── pdf_processing.py
│   ├── werkvoorbereiding.py
│   ├── sheetmetal_analysis.py
│   ├── assembly_analysis.py
│   ├── part_analyzer.py
│   ├── freecad_unfold.py
│   ├── pipeline_init.py
│   ├── pipeline_stages.py
│   ├── cli_output.py
│   └── sql/
│       └── schema.sql
│
├── scripts/                          # Thin dev/utility wrappers only
│   ├── aag_analyzer.py
│   ├── compare_erp.py
│   └── README.md
│
├── resources/
│   ├── input/                        # All STEP files (consolidated)
│   ├── output/                       # Generated reports
│   ├── data/                         # Database, Excel references
│   └── docs/                         # Documentation
│
├── archive/                          # Single archive location
│   ├── scripts/                      # Unused scripts
│   └── modules/                      # Unused modules
│
├── run.py                            # Single entry point
├── CLAUDE.md
└── pyproject.toml                    # (optional) For proper packaging
```

---

## Migration Steps

### Phase 1: Flatten the Package Structure

**Goal:** Remove the `src/` nesting layer.

1. Move all files from `manufacturing_pipeline/src/*.py` up to `manufacturing_pipeline/`
2. Update all imports:
   - `from src.step_processing import ...` → `from .step_processing import ...`
   - `from manufacturing_pipeline.src.X` → `from manufacturing_pipeline.X`
3. Move `manufacturing_pipeline/src/archive/` to top-level `archive/modules/`
4. Delete empty `manufacturing_pipeline/src/` directory

**Files to move (18 modules):**
- `step_processing.py`, `iso_standards.py`, `cache_manager.py`, `config.py`
- `models.py`, `database.py`, `correlation.py`, `report_generator.py`
- `pdf_processing.py`, `werkvoorbereiding.py`, `sheetmetal_analysis.py`
- `assembly_analysis.py`, `part_analyzer.py`, `freecad_unfold.py`
- `pipeline_init.py`, `pipeline_stages.py`, `cli_output.py`, `__init__.py`

**Import patterns to update:**
```python
# Before
from src.step_processing import load_step_file
from manufacturing_pipeline.src.config import PipelineConfig

# After
from .step_processing import load_step_file
from manufacturing_pipeline.config import PipelineConfig
```

---

### Phase 2: Consolidate Entry Points

**Goal:** Single entry point with backward compatibility.

1. Rename `manufacturing_pipeline/main.py` → `manufacturing_pipeline/cli.py`
2. Update `run.py` to import from cli:
   ```python
   from manufacturing_pipeline.cli import main
   if __name__ == "__main__":
       main()
   ```
3. Create minimal backward-compat shim at `manufacturing_pipeline/main.py`:
   ```python
   # Backward compatibility - use run.py instead
   from .cli import main
   if __name__ == "__main__":
       main()
   ```

---

### Phase 3: Move Shared Logic into Package

**Goal:** Core logic belongs in the package, not in scripts/.

1. Move `scripts/pipeline_functions.py` → `manufacturing_pipeline/utils.py`
2. Update all imports in `run.py` and `scripts/*.py`:
   ```python
   # Before
   from scripts.pipeline_functions import find_step_files, run_analysis
   
   # After
   from manufacturing_pipeline.utils import find_step_files, run_analysis
   ```
3. Keep `scripts/aag_analyzer.py` and `scripts/compare_erp.py` as thin wrappers

---

### Phase 4: Consolidate Input Folders

**Goal:** Single location for input files.

1. Move contents of `input/` → `resources/input/`
2. Move contents of `resources/parts/` → `resources/input/`
3. Delete empty `input/` and `resources/parts/` directories
4. Update path constants:
   ```python
   # Before
   PARTS_DIR = os.path.join(PROJECT_ROOT, "resources", "parts")
   
   # After
   INPUT_DIR = os.path.join(PROJECT_ROOT, "resources", "input")
   ```

---

### Phase 5: Consolidate Archives

**Goal:** Single archive location at project root.

1. Create `archive/` at project root
2. Move `scripts/archive/*` → `archive/scripts/`
3. Move `manufacturing_pipeline/src/archive/*` → `archive/modules/`
4. Add `archive/README.md` explaining contents

---

## Estimated Effort

| Phase | Description | Time |
|-------|-------------|------|
| 1 | Flatten package structure | 45 min |
| 2 | Consolidate entry points | 15 min |
| 3 | Move shared logic | 30 min |
| 4 | Consolidate inputs | 15 min |
| 5 | Consolidate archives | 10 min |
| - | Testing & fixes | 30 min |
| **Total** | | **~2.5 hours** |

---

## Testing Checklist

After each phase, verify:

- [ ] `python run.py --list` works
- [ ] `python run.py -f <test.step>` analyzes correctly
- [ ] `python run.py --batch` processes multiple files
- [ ] `python manufacturing_pipeline/main.py --list-stages` works (backward compat)
- [ ] `python scripts/compare_erp.py --help` works
- [ ] No import errors in any module

---

## Optional Future Improvements

### Add pyproject.toml for proper packaging

```toml
[project]
name = "manufacturing-pipeline"
version = "1.0.0"
description = "Manufacturing analysis pipeline for STEP CAD files"

[project.scripts]
mp-analyze = "manufacturing_pipeline.cli:main"

[tool.setuptools]
packages = ["manufacturing_pipeline"]
```

### Benefits of proper packaging
- Install with `pip install -e .` for development
- Use `mp-analyze` command from anywhere
- Cleaner imports without path manipulation

---

## Notes

- Keep `sql/` inside `manufacturing_pipeline/` since it's code-adjacent (schema for the pipeline)
- The `scripts/` folder remains for development utilities that shouldn't be part of the main package
- Consider adding `__all__` exports to `manufacturing_pipeline/__init__.py` for cleaner public API
