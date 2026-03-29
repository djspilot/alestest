# Manufacturing Pipeline — Full Refactoring Overhaul

> Generated: 2026-03-28  
> Scope: All packages under `manufacturing_pipeline/`  
> See also: `analysis/REFACTORING_PRIORITY.md` for analysis-only deep dive

---

## Phase -1 — Modules to Remove (do before any refactoring)

**Goal**: Strip dead weight before restructuring. These modules are either unused, stubs, fully replaceable, or only serve a mode nobody uses.

### ✅ Safe to Delete (no downstream impact on core pipeline)

| File | Lines | Why Remove | Impact |
|------|------:|------------|--------|
| `reporting/report_generator.py` | 772 | Full-mode PDF report (reportlab). Only used in `--full` mode via `cli.py` lazy import. Core quick-mode pipeline doesn't need it. | Remove import from `cli.py:_import_full_pipeline()` |
| `reporting/pdf_processing.py` | 14 | **Stub** — returns hardcoded mock data. Never does real work. | Remove import from `cli.py:_import_full_pipeline()` |
| `analysis/correlation.py` | 20 | Only consumer of `pdf_processing.py` stub output. Returns `None` for most calls. | Remove import from `cli.py:_import_full_pipeline()` |
| `reporting/excel_exporter.py` | 474 | Excel/SpaceClaim comparison export. Used behind `--excel` flag in CLI and one API route. Not part of core analysis. | Remove `--excel` flag from CLI, remove API route |
| `reporting/dxf_metrics_extractor.py` | 1046 | Only used by `xml_exporter.py` (behind try/except). Requires `ezdxf` + `shapely` extra deps. | Remove import from `xml_exporter.py` |
| `core/report_generation.py` | 179 | Summary builders only consumed by `runtime_analysis.py` / `runtime_functions.py`. Can be inlined or deleted with the PDF path. | Inline the 2-3 used helpers, delete file |
| `scripts/compare_erp.py` | 1251 | Standalone validation script. Not imported by any pipeline module. Has hardcoded FreeCAD path. | Just delete — standalone tool |

**Total removable: ~3,756 lines (10.5% of codebase)**

### ⚠️ Conditional Removal (need decision)

| File | Lines | Why Consider | What Blocks Removal |
|------|------:|--------------|---------------------|
| `scripts/aag_analyzer.py` | 1569 | AAG analysis via FreeCAD subprocess. Used in quick-mode via `--aag` flag AND as fallback in `run_analysis()` for bend/thickness detection. | `runtime_analysis.py` uses `AAGAnalyzer` directly (in-process, lines 125-128) AND `run_aag_analysis()` via subprocess. **If you remove AAG, you lose topology-based bend/thickness detection.** Keep data classes, remove FreeCAD-dependent code? |
| `core/runtime_reporting.py` | 947 | Contains `generate_compact_pdf()`, `generate_simple_pdf()`, `run_aag_analysis()`, `run_debug()`. | `run_aag_analysis()` is the subprocess wrapper called by quick mode. `generate_compact_pdf()` is called by CLI quick mode to produce the output PDF. **If you remove PDF output entirely**, this file loses 740 lines and only `run_debug()` remains. |
| `reporting/cli_output.py` | 316 | Terminal formatting for `--full` mode. Used by `pipeline_stages.py` (6 print functions). | Only needed for `--full` mode verbose output. If you remove `--full`, this goes too. |
| `analysis/pipeline_stages.py` | 431 | Full-mode stage orchestration. Only imported by `cli.py:_import_full_pipeline()`. | Only needed for `--full` mode. |
| `analysis/werkvoorbereiding.py` | 1375 | Work preparation / cost estimation. Only used by `pipeline_stages.py` and `step_processing.py`. | Only needed for `--full` mode. |
| `analysis/iso_standards.py` | 696 | ISO tolerance/thread/fit tables. Used by `pipeline_stages.py`, `step_processing.py`, `cut_features.py`. | `cut_features.py` uses thread data for countersink detection. Partial removal possible. |
| `data/database.py` + `data/sql/` | 101 | SQLite storage. Only used in `--full` mode. | Only needed for `--full` mode. |
| `data/cache_manager.py` | 314 | Pipeline stage caching. Only used in `--full` mode. | Only needed for `--full` mode. |
| `core/pipeline_init.py` | 144 | Full-mode initialization helpers. Only imported by `cli.py:_import_full_pipeline()`. | Only needed for `--full` mode. |

### 🔴 Decision Point: Remove `--full` mode entirely?

If `--full` mode is not actively used, you can remove **all conditional modules above** in one sweep:

**Additional removable if `--full` is dropped: ~3,383 lines**  
**Grand total removable: ~7,139 lines (20% of codebase)**

The `--full` mode removal would affect:
- `cli.py`: Remove `_import_full_pipeline()`, `run_full_pipeline()`, `save_to_json()`, related arg parsing (~250 lines)
- `analysis/pipeline_stages.py`: Delete entirely
- `analysis/werkvoorbereiding.py`: Delete entirely  
- `reporting/cli_output.py`: Delete entirely
- `data/database.py` + `data/sql/`: Delete entirely
- `data/cache_manager.py`: Delete entirely
- `core/pipeline_init.py`: Delete entirely

### ✅ Outside `manufacturing_pipeline/` — Also Safe to Delete

| Path | Size | Why Remove |
|------|------|------------|
| `docs/archive/` | ~5,849 lines | Old changelogs, handoffs, validation reports, archived `profile_pipeline/` package (incl. `.pyc` files). Pure historical. |
| `docs/scripts/` (25 files) | ~4,808 lines | One-off test/validation scripts (`test_step0_*.py`, `validate_*.py`, `analyze_*.py`, `generate_xml_*.py`). Not imported anywhere. Not run by pytest. |
| `docs/plans/` | 3 files | Old static-site and naming-strategy plans from Feb/Mar 2026. |
| `docs/superpowers/` | empty dir | Contains only an empty `plans/` subfolder. |
| `docs/index.html` | 1 file | Standalone HTML, not served by anything. |
| `.planning/` | ~1,484 lines | Cached architecture/convention/testing docs + old quick plans. Agent-generated, regeneratable. |
| `test_refactoring_phase7.py` (root) | 61 lines | One-off validation script for Phase 7 refactoring. Not in test suite, not run by pytest. |
| `viewer/node_modules/` | 242 MB | Should be in `.gitignore`, not committed. Regeneratable via `npm install`. |
| `viewer/dist/` | 8.4 MB | Build output. Regeneratable via `npm run build`. |
| `viewer/*.timestamp-*.mjs` | 1 file | Vite temp file (`vite.config.js.timestamp-1774608830788-96b0ab71a2e87.mjs`). |
| `deploy/file_watcher_service.py` | 238 lines | Windows-only ERP file watcher. Not imported by pipeline. Hardcoded paths. |
| `deploy/install_windows_service.bat` | 226 lines | Windows service installer for above watcher. |
| `deploy/install.sh` | 204 lines | VPS setup script — only relevant if deploying the API. |
| `deploy/deploy.sh` | 172 lines | VPS deploy script — same. |
| `deploy/nginx.conf` | 27 lines | Nginx config for API proxy — same. |
| `deploy/requirements-watcher.txt` | small | Deps for the file watcher only. |

**Total outside pipeline: ~12,800+ lines + 250 MB of node_modules/dist**

### ⚠️ Partially Dead Inside Kept Modules

| File | Dead Code | Why |
|------|-----------|-----|
| `core/models.py` (34 lines) | `MatchedFeature`, `HoleFeature`, `ValidationStatus` | Only used by `correlation.py` (being deleted), `database.py` (being deleted), and `step_processing.py`. After removing those consumers, only `RouteCategory` survives — inline it into `router.py`. Delete file. |
| `core/runtime_functions.py` (135 lines) | Entire file | Pure trampoline: re-imports from 6 submodules + lazy forwards to `runtime_analysis.py`, `runtime_reporting.py`, `runtime_unfold.py`. Delete and point `core/utils.py` directly. |
| `core/runtime_reporting.py` | `generate_compact_pdf()` (270 lines), `generate_simple_pdf()` (470 lines) | If PDF output is removed, only `run_aag_analysis()` + `run_debug()` remain (~180 lines). |
| `analysis/freecad_unfold.py` | Duplicated helpers | `_find_largest_planar_face`, `get_thickness_from_solid`, MockGui — all also exist in `core/runtime_unfold.py`. One copy should go. |
| `tests/legacy/` (3 files) | All | `test_bom_to_xml.py`, `test_final_verification.py`, `test_xml_exporter_dxf.py` — old tests not run by pytest, reference deleted/changed APIs. |
| `run_viewer.py` + `run_viewer.sh` | Both | Viewer launch scripts. `run_viewer.py` (160 lines) starts uvicorn + opens browser. `run_viewer.sh` (118 lines) does the same in bash. Keep one or neither if viewer stays. |

### Revised Deletion Summary

| Category | Lines | Disk |
|----------|------:|------|
| Safe to delete inside pipeline | ~3,756 | — |
| Conditional (if `--full` dropped) | ~3,383 | — |
| Outside pipeline (docs, scripts, etc.) | ~12,800 | — |
| node_modules + dist | — | ~250 MB |
| Partial dead code in kept files | ~1,100 | — |
| **Grand total removable** | **~21,000+ lines** | **~250 MB** |

That's roughly **58% of all code** and virtually all disk bloat.

### Removal Order

```
Step 1: Delete stubs & dead code (correlation.py, pdf_processing.py, test_refactoring_phase7.py)
Step 2: Delete standalone scripts (compare_erp.py, all docs/scripts/, docs/archive/, docs/plans/)
Step 3: Delete export modules (excel_exporter.py, dxf_metrics_extractor.py)
Step 4: Delete PDF reporting (report_generator.py, report_generation.py)
Step 5: Delete legacy tests (tests/legacy/), .planning/, docs/superpowers/
Step 6: Strip PDF generation from runtime_reporting.py (keep run_debug only)
Step 7: Delete trampoline (runtime_functions.py), inline RouteCategory, delete core/models.py
Step 8: Clean viewer/ (delete node_modules, dist, timestamp file)
Step 9: Clean deploy/ (delete file_watcher, windows bat, install/deploy scripts if not deploying)
Step 10: (If decided) Remove --full mode and all its dependencies
Step 11: Clean up cli.py imports, dead flags, and run_viewer scripts
Step 12: Run tests, verify quick mode still works
```

---

## Current State Summary

### Line Counts by Package

| Package | Files | Total Lines | Largest File |
|---------|------:|------------:|--------------|
| `analysis/` | 16 | ~19,400 | `step_processing.py` (2659) |
| `core/` | 16 | ~4,800 | `runtime_analysis.py` (1447) |
| `reporting/` | 6 | ~5,430 | `xml_exporter.py` (2806) |
| `scripts/` | 2 | ~2,820 | `aag_analyzer.py` (1569) |
| `api/` | 6 | ~1,340 | `analysis_service.py` (434) |
| `data/` | 2 | ~415 | `cache_manager.py` (314) |
| `tests/` | 9 | ~889 | `test_feature_layer1.py` (296) |
| Root | 2 | ~788 | `cli.py` (783) |
| **Total** | **~59** | **~35,900** | |

### Top Problem Areas (cross-package)

```
                    ┌──────────────────┐
         ┌────────►│ xml_exporter.py  │ 2806 lines, imports from 8 analysis modules
         │         │  (reporting/)     │
         │         └──────────────────┘
         │
┌────────┴──────────┐     ┌──────────────────────┐
│ runtime_analysis  │────►│ step_processing.py   │ 2659 lines (god module #1)
│   (core/) 1447    │     │  (analysis/)          │
└────────┬──────────┘     └──────────────────────┘
         │
         │  ┌──────────────────────┐
         ├─►│ assembly_analysis.py │ 2630 lines (god module #2)
         │  │  (analysis/)          │
         │  └──────────────────────┘
         │
         │  ┌──────────────────────┐
         └─►│ classification.py    │ 2250 lines (god module #3)
            │  (analysis/)          │
            └──────────────────────┘
```

---

## Systemic Issues

### 1. The "Trampoline" Anti-Pattern in `core/`

The call chain is:

```
cli.py → core/utils.py (8 lines, re-exports *)
       → core/runtime_functions.py (135 lines, lazy-import trampolines)
       → core/runtime_analysis.py (1447 lines, actual run_analysis)
       → core/runtime_reporting.py (947 lines, generate_pdf, run_aag, run_debug)
       → core/runtime_unfold.py (583 lines, run_unfold_to_step)
```

**Problem**: `utils.py` → `runtime_functions.py` → `runtime_*.py` is a 3-hop trampoline. The `runtime_functions.py` file re-imports everything from 6 submodules AND defines lazy forwarders. `runtime_analysis.py` is nearly identical in its import header. Both files redefine `PROJECT_ROOT`, `FREECAD_PYTHON`, etc.

### 2. Path Constants Defined in 6+ Places

`PROJECT_ROOT`, `DATA_DIR`, `PARTS_DIR`, `OUTPUT_DIR`, `FREECAD_PYTHON` are defined identically in:
- `core/runtime_analysis.py`
- `core/runtime_functions.py`
- `core/runtime_unfold.py`
- `core/runtime_reporting.py`
- `scripts/compare_erp.py`
- `reporting/xml_exporter.py` (via sys.path hack)

### 3. `reporting/xml_exporter.py` — Hidden God Module

At 2806 lines, this is the **largest file in the project** (bigger than `step_processing.py`). It imports from 8 different analysis modules using try/except guards and essentially re-implements parts of the analysis pipeline for XML output. It should consume structured results, not run analysis itself.

### 4. Inline FreeCAD Script Generation

Both `core/runtime_unfold.py` and `core/runtime_reporting.py` generate multi-hundred-line Python scripts as f-strings to run via `subprocess`. These embedded scripts duplicate helpers (`get_thickness_from_solid`, `MockGui`, K-factor tables) that also exist in `analysis/freecad_unfold.py` and `scripts/aag_analyzer.py`.

### 5. Test Coverage Gap

889 lines of tests for ~35,000 lines of code (~2.5% test-to-code ratio). Most tests are integration-level. No unit tests for classification rules, geometry utilities, or ISO standards.

---

## Phased Overhaul Plan

### Phase 0 — Foundation (do first, blocks everything)
**Goal**: Single source of truth for paths, eliminate trampoline pattern, add regression baseline.

| Step | Action | Files Affected | Effort |
|------|--------|----------------|:------:|
| 0.1 | **Centralize path constants** — Define `PROJECT_ROOT`, `DATA_DIR`, `PARTS_DIR`, `OUTPUT_DIR`, `FREECAD_PYTHON` ONCE in `core/config.py` (already has `SystemConfig`). Delete all other definitions. | `core/runtime_analysis.py`, `core/runtime_functions.py`, `core/runtime_unfold.py`, `core/runtime_reporting.py`, `scripts/compare_erp.py` | S |
| 0.2 | **Flatten the trampoline** — `core/utils.py` should import directly from `core/runtime_analysis.py`, `core/runtime_reporting.py`, `core/runtime_unfold.py`. Delete `core/runtime_functions.py` (it's a pure passthrough). | `core/utils.py`, `core/runtime_functions.py` | S |
| 0.3 | **Build regression test corpus** — Create a set of representative STEP file hashes + expected classification results. Run before/after each phase. | `tests/` | M |
| 0.4 | **Add import-time tests** — Ensure every module can be imported without side effects or crashes. | `tests/test_imports.py` | S |

**Verification**: `python -m pytest` passes, `python run.py --list` works, no import errors.

---

### Phase 1 — Tame the `core/` Runtime Layer
**Goal**: Each runtime file has one responsibility, no duplication.

| Step | Action | Files Affected | Effort |
|------|--------|----------------|:------:|
| 1.1 | **Extract inline FreeCAD scripts** to standalone `.py` files in `scripts/freecad/`. Run them via subprocess pointing to the file, not via `-c` with a massive f-string. | `core/runtime_unfold.py`, `core/runtime_reporting.py` → `scripts/freecad/unfold_worker.py`, `scripts/freecad/aag_worker.py` | M |
| 1.2 | **Merge `core/unfold_integration.py`** (135 lines, thin helpers) into `core/runtime_unfold.py`. Two files for unfold in core/ is unnecessary. | `core/unfold_integration.py` → `core/runtime_unfold.py` | S |
| 1.3 | **Merge `core/report_generation.py`** (179 lines, summary builders) into `reporting/report_generator.py` or a new `reporting/summaries.py`. Report logic belongs in `reporting/`, not `core/`. | `core/report_generation.py` → `reporting/` | S |
| 1.4 | **Rename and clarify** remaining core files: `runtime_analysis.py` → `analysis_runner.py`, `runtime_reporting.py` → `debug_and_pdf.py` (or split). | `core/` | S |
| 1.5 | **Delete `core/models.py`** (34 lines) if only used by dead code, or merge into `core/config.py`. | `core/models.py` | S |

**Verification**: `python run.py -f sample.step` produces same PDF. All existing tests pass.

---

### Phase 2 — Break Up the `analysis/` God Modules
**Goal**: No file exceeds ~800 lines. Clear single-responsibility per module.

| Step | Action | Files Affected | Effort |
|------|--------|----------------|:------:|
| 2.1 | **Split `step_processing.py`** (2659 lines) into: | | XL |
|  | — `step_io.py`: `load_step_file()`, XCAF helpers, solid extraction | | |
|  | — `geometry.py`: `precompute_face_properties()`, bounding box, volume | | |
|  | — `hole_detection.py`: `detect_holes()`, `detect_shaped_holes()`, `deduplicate_holes()` | | |
|  | — `image_export.py`: SVG/image generation | | |
|  | Keep `step_processing.py` as a thin re-export shim temporarily. | | |
| 2.2 | **Split `assembly_analysis.py`** (2630 lines) into: | | XL |
|  | — `bom_builder.py`: BOM generation, part counting | | |
|  | — `fastener_catalog.py`: Fastener identification data/logic | | |
|  | — `assembly_geometry.py`: Solid comparison, bounding box matching | | |
| 2.3 | **Split `classification.py`** (2250 lines) into: | | L |
|  | — `classification_engine.py`: Core rule engine | | |
|  | — `classification_rules.py`: Threshold definitions, decision trees | | |
|  | — Keep `classification_variables.py` as-is (already good) | | |
| 2.4 | **Unify sectioning/PCA utilities** — Merge overlapping geometry code from `profile_classifier.py`, `profile_features.py`, and `step0_section_tools.py` into one canonical `section_tools.py`. | 3 files → 1+callers | L |
| 2.5 | **Clean up `part_analyzer.py`** — Remove duplicated classification/hole logic that now lives in dedicated modules. Make it a thin orchestrator. | `part_analyzer.py` | M |

**Verification**: Run regression corpus from Phase 0.3. `python run.py --batch` on test set gives identical results.

---

### Phase 3 — Tame `reporting/xml_exporter.py`
**Goal**: XML exporter consumes structured data, does NOT run analysis.

| Step | Action | Files Affected | Effort |
|------|--------|----------------|:------:|
| 3.1 | **Define a `PartAnalysisResult` dataclass** (or TypedDict) as the contract between analysis and reporting. All exporters consume this, not raw dicts. | `core/models.py` or new `core/result_types.py` | M |
| 3.2 | **Refactor `xml_exporter.py`** to receive pre-computed analysis results instead of importing from 8+ analysis modules and running analysis inline. | `reporting/xml_exporter.py` | L |
| 3.3 | **Split `xml_exporter.py`** into: | | L |
|  | — `xml_schema.py`: Feature schema definitions, field mappings | | |
|  | — `xml_writer.py`: XML tree building, formatting | | |
|  | — `xml_orchestrator.py`: Coordination (call analysis → write XML) | | |
| 3.4 | **Refactor `dxf_metrics_extractor.py`** (1046 lines) — Extract DXF generation from metric calculation. Remove `sys.path` hack. | `reporting/dxf_metrics_extractor.py` | M |

**Verification**: Generate XML for known parts, diff against baseline.

---

### Phase 4 — Consolidate `scripts/` into Pipeline
**Goal**: Scripts use the pipeline API, not parallel implementations.

| Step | Action | Files Affected | Effort |
|------|--------|----------------|:------:|
| 4.1 | **Make `aag_analyzer.py`** importable without FreeCAD — separate the data classes/enums (which are pure Python) from the FreeCAD-dependent analysis code. | `scripts/aag_analyzer.py` | M |
| 4.2 | **Clean up `compare_erp.py`** — Remove hardcoded `FREECAD_PYTHON` path, use `SystemConfig`. Remove duplicate `sys.path` hacking. | `scripts/compare_erp.py` | S |
| 4.3 | **Move shared AAG types** (`EdgeConvexity`, `FaceType`, `FeatureType`, dataclasses) to `core/` or `analysis/` so both scripts and pipeline can use them. | `scripts/` → `analysis/` | M |

**Verification**: `python manufacturing_pipeline/scripts/compare_erp.py data/parts/AI-voorbeelden/` still works.

---

### Phase 5 — Slim Down `cli.py` and `api/`
**Goal**: CLI is argument parsing + dispatch only. API is thin HTTP wrapper.

| Step | Action | Files Affected | Effort |
|------|--------|----------------|:------:|
| 5.1 | **Extract `run_full_pipeline()`** from `cli.py` (200+ lines) into `core/full_pipeline.py`. CLI only parses args and calls it. | `cli.py` → `core/full_pipeline.py` | M |
| 5.2 | **Extract `save_to_json()`** from `cli.py` into `reporting/json_exporter.py`. | `cli.py` → `reporting/` | S |
| 5.3 | **Clean `analysis_service.py`** — Currently does its own bend extraction. Should call analysis pipeline and extract from result. | `api/analysis_service.py` | S |

**Verification**: `python run.py -f sample.step` and `python run.py -f sample.step --full` produce identical results to before.

---

### Phase 6 — Testing & Documentation
**Goal**: Sufficient test coverage to refactor with confidence.

| Step | Action | Files Affected | Effort |
|------|--------|----------------|:------:|
| 6.1 | **Unit tests for classification rules** — Test threshold logic in isolation with mock geometry data. | `tests/test_classification.py` | M |
| 6.2 | **Unit tests for hole detection** — Test deduplication, bucketing, shaped hole identification. | `tests/test_hole_detection.py` | M |
| 6.3 | **Unit tests for ISO standards** — Test tolerance lookups, thread detection, fit calculations. | `tests/test_iso_standards.py` | S |
| 6.4 | **Integration test for XML export** — Compare generated XML against golden files. | `tests/test_xml_golden.py` | M |
| 6.5 | **Update `CLAUDE.md`** and `README.md` to reflect new module structure. | Root docs | S |

**Verification**: `python -m pytest --cov` shows >30% coverage on analysis modules.

---

## Dependency Graph (Current vs Target)

### Current: Spaghetti

```
cli.py ──→ core/utils.py ──→ core/runtime_functions.py ──→ core/runtime_analysis.py ──┐
                                    ↓                              ↓                    │
                          core/runtime_unfold.py      core/runtime_reporting.py         │
                                    ↓                              ↓                    │
                          analysis/freecad_unfold.py  scripts/aag_analyzer.py           │
                                                                                        ↓
   reporting/xml_exporter.py ──→ analysis/step_processing.py ←──────────────────────────┘
              ↓                  analysis/assembly_analysis.py
              ↓                  analysis/classification.py
              ↓                  analysis/part_analyzer.py
              ↓                  analysis/cut_features.py
              ↓                  analysis/sheetmetal_analysis.py
              ↓                  analysis/profile_features.py
              ↓                  analysis/profile_classifier.py
              └─────────────────(imports from ALL of the above)
```

### Target: Layered

```
cli.py ──→ core/analysis_runner.py ──→ analysis/step_io.py
       ──→ core/full_pipeline.py       analysis/geometry.py
                                        analysis/hole_detection.py
                                        analysis/classification_engine.py
                                        analysis/sheetmetal/
                                        analysis/bom/
                                              ↓
                                     core/result_types.py (PartAnalysisResult)
                                              ↓
                                     reporting/xml_writer.py
                                     reporting/json_exporter.py
                                     reporting/excel_exporter.py
                                     reporting/report_generator.py
```

---

## Execution Order & Dependencies

```
Phase 0  ──→  Phase 1  ──→  Phase 2  ──→  Phase 3
(Foundation)  (core/)       (analysis/)    (reporting/)
                                  │
                                  ├──→  Phase 4 (scripts/)
                                  │
                                  └──→  Phase 5 (cli + api)
                                              │
                                              └──→  Phase 6 (tests & docs)
```

- **Phases 0-1**: Must come first — clean foundation
- **Phases 2-3**: Can overlap if different people work on them
- **Phase 4**: Independent, can start after Phase 2
- **Phase 5**: After Phases 2-3 (depends on cleaned APIs)
- **Phase 6**: Ongoing throughout, formal push at end

---

## Estimated Total Effort

| Phase | Description | Effort | Risk |
|-------|-------------|:------:|:----:|
| 0 | Foundation | S-M | Low |
| 1 | Core cleanup | M | Low |
| 2 | Analysis god modules | XL | High |
| 3 | XML exporter | L | Medium |
| 4 | Scripts consolidation | M | Low |
| 5 | CLI + API slim | M | Low |
| 6 | Tests & docs | M | Low |

**Critical path**: Phase 0 → Phase 2 → Phase 3 (the analysis god modules are the bottleneck).

---

## Rules of Engagement

1. **One module at a time** — never refactor two god modules simultaneously
2. **Re-export shims** — keep old import paths working via thin re-export files during transition
3. **Run regression after every step** — not just every phase
4. **No behavior changes** — refactoring only, no new features mixed in
5. **Commit per step** — not per phase, so you can bisect if something breaks
