# Overhaul Phases — Removal Plan

> Branch: `overhaul-of-shit-code`  
> Rule: One commit per phase. Test after each. Never combine phases.  
> Keep: Viewer (`viewer/`), Quick mode, Classification, Sheet metal, Profile, Assembly/BOM, FreeCAD unfold, XML export

## Test Protocol (Required After Every Phase Commit)

1. Run:

```bash
export PYTHONPATH=/Users/ds/AIdoel/alestest
python /Users/ds/AIdoel/alestest/manufacturing_pipeline/cli.py -f /Users/ds/AIdoel/alestest/nieuwmodel.step
```

2. Record the outcome in `manufacturing_pipeline/overhaul_test_results.md`.
3. Include:
- phase number
- commit hash
- exit code
- key output/error lines
- manual test verdict and notes

---

## Phase 1 — Dead Code & Stubs
**Risk: zero. Nothing calls these.**

Delete:
- [ ] `manufacturing_pipeline/reporting/pdf_processing.py` (14 lines — hardcoded mock stub)
- [ ] `manufacturing_pipeline/analysis/correlation.py` (20 lines — only consumer of above stub)
- [ ] `manufacturing_pipeline/tests/legacy/` (3 old test files, not run by pytest)
- [ ] `test_refactoring_phase7.py` (root, 61 lines — one-off validation script)
- [ ] `manufacturing_pipeline/core/runtime_functions.py` (135 lines — pure trampoline)

Fix after delete:
- [ ] `core/utils.py`: Change `from .runtime_functions import *` → direct imports from `runtime_analysis`, `runtime_reporting`, `runtime_unfold`, `cache`, `file_utils`, `analysis_pipeline`, `hole_detection_fallback`, `unfold_integration`, `report_generation`
- [ ] `cli.py:_import_full_pipeline()`: Remove `pdf_processing` and `correlation` imports

Verify: `python -m pytest && python run.py --list`

```
git add -p && git commit -m "phase 1: remove dead stubs, trampoline, legacy tests"
```

---

## Phase 2 — Docs & Planning Junk
**Risk: zero. No code depends on docs.**

Delete:
- [ ] `docs/archive/` (entire folder — 22 old changelogs + archived profile_pipeline with .pyc)
- [ ] `docs/scripts/` (entire folder — 25 one-off test/validation scripts, 4808 lines)
- [ ] `docs/plans/` (3 stale plan files)
- [ ] `docs/superpowers/` (empty folder)
- [ ] `docs/index.html` (standalone, not served)
- [ ] `.planning/` (entire folder — agent-generated, regeneratable)

Keep in `docs/`: The .md files at root level (classification docs, handovers, etc.) — useful reference.

Verify: `python -m pytest`

```
git add -p && git commit -m "phase 2: remove stale docs, archived scripts, planning files"
```

---

## Phase 3 — Standalone Scripts
**Risk: zero. Not imported by pipeline.**

Delete:
- [ ] `manufacturing_pipeline/scripts/compare_erp.py` (1251 lines — standalone ERP comparison tool)

Keep: `scripts/aag_analyzer.py` stays until Phase 7.

Verify: `python -m pytest`

```
git add -p && git commit -m "phase 3: remove standalone compare_erp script"
```

---

## Phase 4 — Deploy Scripts (keep Docker)
**Risk: zero for pipeline. Only affects ops tooling.**

Delete:
- [ ] `deploy/file_watcher_service.py` (238 lines — Windows-only ERP folder watcher)
- [ ] `deploy/install_windows_service.bat` (226 lines — installer for above)
- [ ] `deploy/requirements-watcher.txt` (watcher deps)
- [ ] `deploy/install.sh` (204 lines — VPS setup)
- [ ] `deploy/deploy.sh` (172 lines — VPS deploy)
- [ ] `deploy/nginx.conf` (27 lines — reverse proxy config)
- [ ] `deploy/.env.example` (env template)

Keep: `deploy/Dockerfile` and `deploy/docker-compose.yml` (needed for API, removed in Phase 8).

Verify: `python -m pytest`

```
git add -p && git commit -m "phase 4: remove deploy scripts, watcher, VPS tooling"
```

---

## Phase 5 — PDF Reports & Excel Export
**Risk: low. Output formats only, no analysis logic lost.**

Delete:
- [ ] `manufacturing_pipeline/reporting/report_generator.py` (772 lines — reportlab PDF)
- [ ] `manufacturing_pipeline/reporting/excel_exporter.py` (474 lines — SpaceClaim Excel)
- [ ] `manufacturing_pipeline/core/report_generation.py` (179 lines — summary builders for PDF)

Strip from existing files:
- [ ] `core/runtime_reporting.py`: Delete `generate_compact_pdf()` (~270 lines) and `generate_simple_pdf()` (~470 lines). Keep only `run_aag_analysis()` and `run_debug()`.
- [ ] `cli.py`: Remove `--excel` flag, `generate_compact_pdf` / `generate_simple_pdf` imports, and the PDF generation call in quick mode (~15 lines)
- [ ] `core/utils.py`: Remove re-exports of `generate_compact_pdf`, `generate_simple_pdf`
- [ ] `api/routes.py`: Remove the `?format=excel` route branch

Verify: `python -m pytest && python run.py -f <any_step_file>`  
(Output should still produce XML, just no PDF/Excel)

```
git add -p && git commit -m "phase 5: remove PDF reports, Excel export, report_generation"
```

---

## Phase 6 — DXF Metrics
**Risk: low. Only used by xml_exporter behind try/except.**

Delete:
- [ ] `manufacturing_pipeline/reporting/dxf_metrics_extractor.py` (1046 lines)

Strip from existing files:
- [ ] `reporting/xml_exporter.py`: Remove the `try: from ... dxf_metrics_extractor` import block and all `generate_dxf_from_solid` / `extract_metrics_from_dxf` calls (replace with `None` or skip the DXF branch)

Verify: `python -m pytest && python run.py -f <any_step_file>`

```
git add -p && git commit -m "phase 6: remove DXF metrics extractor"
```

---

## Phase 7 — AAG Analyzer & ISO Standards
**Risk: medium. AAG provides bend/thickness fallback. ISO provides thread detection.**

### 7a — AAG Analyzer
Delete:
- [ ] `manufacturing_pipeline/scripts/aag_analyzer.py` (1569 lines)

Strip from existing files:
- [ ] `core/runtime_analysis.py`: Remove `AAGAnalyzer` import (lines 124-128), remove `run_aag_analysis()` call and `aag_result` usage (~30 lines). The classification still works via `part_analyzer.py` and `sheetmetal_analysis.py` without AAG.
- [ ] `core/runtime_reporting.py`: Delete `run_aag_analysis()` function entirely (~120 lines). Only `run_debug()` remains.
- [ ] `cli.py`: Remove `--aag` flag and related conditional blocks
- [ ] `core/utils.py`: Remove `run_aag_analysis` re-export

### 7b — ISO Standards
Delete:
- [ ] `manufacturing_pipeline/analysis/iso_standards.py` (696 lines)

Strip from existing files:
- [ ] `analysis/step_processing.py`: Remove `from manufacturing_pipeline.analysis import iso_standards` and any thread detection calls using it
- [ ] `analysis/cut_features.py`: Remove `from . import iso_standards` and thread-related lookups (replace with simple heuristic or remove thread column from output)
- [ ] `analysis/pipeline_stages.py`: Remove ISO stages (will be fully deleted in Phase 9 anyway, but clean the import now)

Verify: `python -m pytest && python run.py -f <any_step_file>`  
(Bend detection now relies solely on `sheetmetal_analysis.py` geometry. No thread info in output.)

```
git add -p && git commit -m "phase 7: remove AAG analyzer and ISO standards"
```

---

## Phase 8 — API & Docker
**Risk: low for local use. Removes REST API entirely.**

Delete:
- [ ] `manufacturing_pipeline/api/` (entire package — app.py, routes.py, analysis_service.py, job_manager.py, schemas.py, config.py, static/)
- [ ] `deploy/Dockerfile`
- [ ] `deploy/docker-compose.yml`
- [ ] `deploy/` (folder now empty, delete it)

Strip from existing files:
- [ ] `manufacturing_pipeline/tests/test_timeline_api.py`: Delete (tests API code that no longer exists)

Verify: `python -m pytest && python run.py -f <any_step_file>`

```
git add -p && git commit -m "phase 8: remove API, Docker, deploy"
```

---

## Phase 9 — `--full` Mode
**Risk: medium. Removes entire secondary pipeline mode.**

Delete:
- [ ] `manufacturing_pipeline/analysis/pipeline_stages.py` (431 lines)
- [ ] `manufacturing_pipeline/analysis/werkvoorbereiding.py` (1375 lines)
- [ ] `manufacturing_pipeline/reporting/cli_output.py` (316 lines)
- [ ] `manufacturing_pipeline/data/cache_manager.py` (314 lines)
- [ ] `manufacturing_pipeline/data/database.py` (101 lines)
- [ ] `manufacturing_pipeline/data/sql/` (schema files)
- [ ] `manufacturing_pipeline/core/pipeline_init.py` (144 lines)

Strip from existing files:
- [ ] `cli.py`: Delete `_import_full_pipeline()` (~25 lines), `run_full_pipeline()` (~200 lines), `save_to_json()` (~40 lines), `--full` flag and all related arg parsing. CLI becomes quick-mode only.
- [ ] `core/models.py`: Only `RouteCategory` survives → inline into `analysis/router.py`, delete `core/models.py`

Verify: `python -m pytest && python run.py -f <any_step_file>`  
(Only quick mode remains. `--full` flag gone.)

```
git add -p && git commit -m "phase 9: remove --full mode, database, cache, werkvoorbereiding"
```

---

## Phase 10 — Final Cleanup
**Risk: zero. Cosmetic.**

- [ ] `core/runtime_reporting.py`: If only `run_debug()` remains (~50 lines), rename to `core/debug.py` or inline into `runtime_analysis.py`
- [ ] `core/utils.py`: Review remaining re-exports, remove dead ones
- [ ] `requirements.txt`: Remove unused deps (`reportlab`, `svglib`, `pymupdf`, `openpyxl`, `pandas`, `ezdxf`, `shapely`, `fastapi`, `uvicorn`)
- [ ] `CLAUDE.md`: Update to reflect stripped-down pipeline
- [ ] `README.md`: Update commands, remove references to deleted modes/exports
- [ ] `run_viewer.py` / `run_viewer.sh`: Decide if both needed (keep one)
- [ ] Delete any leftover `__pycache__/` dirs

Verify: `python -m pytest && python run.py -f <any_step_file>`

```
git add -p && git commit -m "phase 10: final cleanup, update docs, trim requirements"
```

---

## Summary

| Phase | What Goes | Lines Removed | Risk |
|------:|-----------|-------------:|:----:|
| 1 | Dead stubs, trampoline, legacy tests | ~230 | None |
| 2 | Docs, scripts, planning | ~12,100 | None |
| 3 | compare_erp.py | ~1,250 | None |
| 4 | Deploy scripts | ~870 | None |
| 5 | PDF + Excel export | ~2,165 | Low |
| 6 | DXF metrics | ~1,050 | Low |
| 7 | AAG + ISO standards | ~2,265 | Medium |
| 8 | API + Docker | ~1,340 | Low |
| 9 | `--full` mode | ~2,680 | Medium |
| 10 | Cleanup + deps | ~200 | None |
| **Total** | | **~24,150** | |

After all phases: **~11,750 lines remain** — the lean core pipeline.
