# Codebase Concerns

**Analysis Date:** 2026-03-25

## Tech Debt

**Bare `except:` clauses (silent error swallowing):**
- Issue: Over 40 bare `except: pass` blocks across the codebase silently swallow all exceptions including `KeyboardInterrupt` and `SystemExit`. This masks bugs and makes debugging extremely difficult.
- Files: `manufacturing_pipeline/scripts/aag_analyzer.py` (16 instances), `manufacturing_pipeline/analysis/assembly_analysis.py` (10 instances), `manufacturing_pipeline/core/utils.py` (4 instances), `manufacturing_pipeline/reporting/dxf_metrics_extractor.py` (8 instances), `manufacturing_pipeline/analysis/freecad_unfold.py` (2 instances), `manufacturing_pipeline/analysis/profile_features.py` (2 instances), `manufacturing_pipeline/analysis/step_processing.py` (1 instance)
- Impact: Failures go undetected; wrong results returned silently instead of raising errors. Debugging production issues requires adding logging retroactively.
- Fix approach: Replace bare `except:` with `except Exception:` at minimum. For each site, determine the expected exception types and catch only those. Add logging before `pass`.

**Excessive `except Exception` with silent pass in xml_exporter:**
- Issue: `xml_exporter.py` has 40+ try/except blocks, many catching broad `Exception` and either passing silently or printing a truncated warning. The file acts as a "catch-all" that never fails but may produce incomplete or incorrect output.
- Files: `manufacturing_pipeline/reporting/xml_exporter.py` (2745 lines, 37 functions, 40+ exception handlers)
- Impact: Corrupt or partial XML output may be generated without any indication of failure. Downstream ERP systems receive bad data silently.
- Fix approach: Introduce a structured error collector that accumulates warnings during export. Return the warning list alongside the XML so callers can decide severity. Replace `pass` with logging.

**`sys.path` manipulation throughout codebase:**
- Issue: At least 20 `sys.path.insert(0, ...)` calls scattered across modules, including in generated subprocess scripts. This creates import fragility and makes the project structure hard to reason about.
- Files: `manufacturing_pipeline/core/utils.py` (lines 34-36, 949-952, 1238, 1304-1307), `manufacturing_pipeline/reporting/xml_exporter.py` (line 16), `manufacturing_pipeline/reporting/dxf_metrics_extractor.py` (line 15), `manufacturing_pipeline/analysis/freecad_unfold.py` (line 86), `manufacturing_pipeline/analysis/step_processing.py` (line 64), multiple test files
- Impact: Import order matters in unexpected ways. Running scripts from different working directories can produce different behavior. Path pollution can cause wrong module versions to load.
- Fix approach: Use proper package installation (`pip install -e .`) and rely on Python's package resolution. For subprocess scripts that need FreeCAD, pass paths as arguments rather than embedding them in generated code.

**Print-based logging (627 `print()` calls):**
- Issue: The vast majority of the codebase uses raw `print()` for output. Only 4 modules use Python's `logging` module: `manufacturing_pipeline/analysis/router.py`, `manufacturing_pipeline/analysis/cut_features.py`, `manufacturing_pipeline/analysis/classification.py`, `manufacturing_pipeline/core/xcaf_reader.py`.
- Files: All major modules, especially `manufacturing_pipeline/reporting/cli_output.py` (101 prints), `manufacturing_pipeline/core/utils.py` (100 prints), `manufacturing_pipeline/reporting/xml_exporter.py` (93 prints)
- Impact: No log levels, no structured logging, no ability to filter output by severity. API deployment mixes print output with uvicorn logs. Cannot distinguish warnings from informational messages.
- Fix approach: Adopt `logging` module consistently. Define a project-wide logger configuration. Replace `print()` with appropriate log levels (`logger.debug`, `logger.info`, `logger.warning`, `logger.error`).

**Duplicate FreeCAD path comment:**
- Issue: Line 27 of `manufacturing_pipeline/core/utils.py` has a duplicate comment `# FreeCAD Python path` (lines 26-27).
- Files: `manufacturing_pipeline/core/utils.py` (lines 26-27)
- Impact: Minor, cosmetic only.
- Fix approach: Remove the duplicate comment.

## Complexity Hotspots

**`manufacturing_pipeline/reporting/xml_exporter.py` (2745 lines, 37 functions):**
- This is the largest file in the codebase and handles XML export, unfold orchestration, solid matching, profile classification, feature extraction, and ERP format generation -- all in one module.
- Contains 9 conditional import blocks at the top with `HAS_*` feature flags, creating a combinatorial explosion of code paths.
- Fix approach: Split into focused modules: `xml_builder.py` (XML structure), `solid_matcher.py` (solid-to-name matching), `unfold_coordinator.py` (unfold orchestration). Keep `xml_exporter.py` as a thin facade.

**`manufacturing_pipeline/analysis/assembly_analysis.py` (2630 lines, 49 functions):**
- Second largest file. Handles assembly parsing, BOM generation, solid matching, volume calculation, and naming -- multiple distinct responsibilities.
- Fix approach: Extract solid-matching logic and BOM generation into separate modules.

**`manufacturing_pipeline/analysis/step_processing.py` (2325 lines, 35 functions):**
- Core STEP parsing, hole detection, bend detection, face analysis, and image generation in a single file.
- Contains subprocess calls that generate and execute Python scripts as strings (lines 61-74, 949-952), making the code very hard to test and debug.
- Fix approach: Extract hole detection, bend detection, and image generation into separate modules.

**`manufacturing_pipeline/core/utils.py` (2190 lines, 29 functions):**
- A grab-bag utility module with path constants, cache functions, FreeCAD subprocess orchestration, unfold logic, and image processing. The name "utils" invites unbounded growth.
- Contains multi-hundred-line string templates for FreeCAD subprocess scripts (lines ~940-1133, ~1230-1400).
- Fix approach: Split into `paths.py` (constants), `cache.py` (caching), `freecad_subprocess.py` (subprocess orchestration), `image_utils.py` (SVG/image).

**`manufacturing_pipeline/analysis/classification.py` (2250 lines):**
- Large classification module that could benefit from being split by classification category.

## Security Considerations

**CORS wildcard in API:**
- Risk: `allow_origins=["*"]` in `manufacturing_pipeline/api/app.py` (line 25) allows any origin to call the API. Combined with the API key auth bypass in dev mode (`if API_KEYS:` check at line 36), this means an unauthenticated, open API in development.
- Files: `manufacturing_pipeline/api/app.py` (lines 23-28, 32-43)
- Current mitigation: API key middleware exists but is optional (empty `API_KEYS` env var disables it).
- Recommendations: Default to requiring at least one API key. Restrict CORS origins in production. Add rate limiting.

**Uploaded file handling:**
- Risk: Uploaded STEP files are saved to disk at `manufacturing_pipeline/api/routes.py` (line 109) using the original filename (`file.filename`). While the extension is validated, the filename is not sanitized for path traversal (e.g., `../../etc/passwd.step`).
- Files: `manufacturing_pipeline/api/routes.py` (lines 90-111)
- Current mitigation: Files are saved inside a UUID-named subdirectory, which limits traversal impact.
- Recommendations: Use `os.path.basename()` or generate a safe filename. Validate that the resolved path stays within `UPLOAD_DIR`.

**Subprocess code injection surface:**
- Risk: Multiple modules build Python scripts as f-strings and execute them via `subprocess.run`. File paths are interpolated directly into script strings without escaping.
- Files: `manufacturing_pipeline/core/utils.py` (lines ~940-1133), `manufacturing_pipeline/analysis/step_processing.py` (lines 61-74), `manufacturing_pipeline/analysis/freecad_unfold.py` (unfold script generation)
- Current mitigation: Only internal file paths are used (not user input in CLI mode). In API mode, uploaded filenames could theoretically be part of paths.
- Recommendations: Use `shlex.quote()` for all path interpolation in subprocess scripts. Better yet, pass data via JSON files or command-line arguments instead of embedded strings.

**MD5 for file hashing:**
- Risk: `hashlib.md5()` is used for file change detection in `manufacturing_pipeline/core/utils.py` (line 48) and `manufacturing_pipeline/api/routes.py` (line 114). MD5 is cryptographically broken.
- Impact: Low risk since MD5 is only used for cache invalidation, not security. But it sets a bad precedent.
- Recommendations: Use `hashlib.sha256()` for consistency with modern practices.

## Scalability Concerns

**Full file read into memory for uploads:**
- Problem: `manufacturing_pipeline/api/routes.py` (line 98) reads the entire uploaded file into memory with `content = await file.read()` before checking size. A 100MB file (the configured max) is fully buffered.
- Files: `manufacturing_pipeline/api/routes.py` (line 98)
- Impact: Concurrent uploads of large files can exhaust server memory.
- Improvement path: Stream the file to disk with a size-checking wrapper that aborts early if the limit is exceeded.

**Synchronous analysis in background task:**
- Problem: The analysis pipeline is CPU-bound (CAD geometry processing) and runs in a FastAPI `BackgroundTask`, which uses the same thread pool as request handling.
- Files: `manufacturing_pipeline/api/routes.py` (line 119)
- Impact: Long-running analyses (some STEP files take >60s) block the server's thread pool, potentially causing request timeouts for other clients.
- Improvement path: Use a proper task queue (Celery, Redis Queue) or at minimum run analysis in a separate process pool.

**FreeCAD subprocess overhead:**
- Problem: Every unfold operation spawns a new Python subprocess that imports the entire FreeCAD library from scratch. FreeCAD import alone can take several seconds.
- Files: `manufacturing_pipeline/analysis/freecad_unfold.py` (line 340), `manufacturing_pipeline/core/utils.py` (lines 1137, 1173, 1245, 1370)
- Cause: FreeCAD is imported in subprocesses because its C++ bindings can crash the main process (segfault).
- Improvement path: Consider a long-running FreeCAD worker process that receives jobs via IPC, avoiding repeated startup costs.

**No connection pooling for SQLite:**
- Problem: `DatabaseManager` in `manufacturing_pipeline/data/database.py` creates a new SQLite connection for every operation (`connect()` / `close()` pattern).
- Files: `manufacturing_pipeline/data/database.py` (lines 11-17)
- Impact: Fine for CLI usage but inefficient for API mode with concurrent requests.
- Improvement path: Use a connection pool or keep a single connection with proper thread-safety (SQLite WAL mode).

## Maintenance Risks

**Conditional import feature flags in xml_exporter:**
- Risk: `manufacturing_pipeline/reporting/xml_exporter.py` has 9 `try/except ImportError` blocks at module level (lines 19-94), each setting a `HAS_*` boolean. Every function must check these flags before using functionality.
- Files: `manufacturing_pipeline/reporting/xml_exporter.py` (lines 19-94)
- Why fragile: Adding a new dependency requires adding another flag and checking it everywhere. Missing a check causes `NameError` at runtime. The module behaves differently depending on which packages happen to be installed.
- Fix approach: Make all analysis dependencies mandatory (they already are in `requirements.txt`). Remove the conditional import pattern.

**Hardcoded FreeCAD path (macOS-specific):**
- Risk: Default FreeCAD path is hardcoded to `/opt/homebrew/Caskroom/freecad/1.0.2/FreeCAD.app` in `manufacturing_pipeline/core/config.py` (line 17) and `manufacturing_pipeline/analysis/freecad_unfold.py` (shebang line 1, line 55). Version `1.0.2` is baked in.
- Files: `manufacturing_pipeline/core/config.py` (lines 17, 58), `manufacturing_pipeline/analysis/freecad_unfold.py` (lines 1, 55)
- Impact: FreeCAD upgrades break the pipeline. Linux/Windows require `FREECAD_PATH` env var. New developer setup requires knowing this.
- Fix approach: Auto-detect FreeCAD installation using `which freecad` or checking common paths at runtime. Make the version part of the path a glob pattern.

**Legacy test directory:**
- Risk: `manufacturing_pipeline/tests/legacy/` contains old tests (`test_bom_to_xml.py`, `test_final_verification.py`, `test_xml_exporter_dxf.py`) with bare `except:` clauses and `sys.path` manipulation. Unclear if they still pass or are maintained.
- Files: `manufacturing_pipeline/tests/legacy/test_bom_to_xml.py`, `manufacturing_pipeline/tests/legacy/test_final_verification.py`, `manufacturing_pipeline/tests/legacy/test_xml_exporter_dxf.py`
- Impact: Dead tests create false confidence. If run in CI, failures may be ignored because they are "legacy."
- Fix approach: Either update and integrate into main test suite, or delete.

**No type annotations on most functions:**
- Risk: Core modules like `manufacturing_pipeline/core/utils.py` and `manufacturing_pipeline/analysis/step_processing.py` have minimal or no type annotations on function signatures. Combined with the large function counts, this makes refactoring risky.
- Impact: IDE support is limited. Automated refactoring tools cannot verify correctness. New developers must read implementation to understand interfaces.
- Fix approach: Add type annotations incrementally, starting with public API functions in `core/` and `analysis/`.

## Test Coverage Gaps

**Minimal test suite for codebase size:**
- What's not tested: 725 lines of tests for ~35,000 lines of production code (~2% test-to-code ratio). The 7 test files cover basic config, XML export structure, routing, display edges, feature detection, step naming, and timeline API.
- Files with zero test coverage:
  - `manufacturing_pipeline/analysis/step_processing.py` (2325 lines) -- core STEP parsing
  - `manufacturing_pipeline/analysis/sheetmetal_analysis.py` (894 lines) -- sheet metal detection
  - `manufacturing_pipeline/analysis/freecad_unfold.py` (1390 lines) -- unfold logic
  - `manufacturing_pipeline/reporting/report_generator.py` (772 lines) -- PDF generation
  - `manufacturing_pipeline/analysis/assembly_analysis.py` (2630 lines) -- assembly handling
  - `manufacturing_pipeline/analysis/iso_standards.py` (696 lines) -- ISO calculations
  - `manufacturing_pipeline/data/cache_manager.py` (189+ lines) -- caching system
  - `manufacturing_pipeline/data/database.py` -- database operations
  - `manufacturing_pipeline/cli.py` (783 lines) -- CLI interface
  - `manufacturing_pipeline/analysis/werkvoorbereiding.py` (1375 lines) -- work preparation
  - `manufacturing_pipeline/analysis/classification.py` (2250 lines) -- part classification
- Risk: Regressions in hole detection, bend counting, unfold calculations, and ISO standard application go undetected. These are the core business logic modules.
- Priority: **High** -- the most critical modules (step_processing, sheetmetal_analysis, part_analyzer, iso_standards) have no tests at all.

**No integration tests:**
- What's not tested: End-to-end pipeline flow from STEP file to output (PDF, XML, Excel). No tests verify that `run.py` or `cli.py` produce correct outputs for known inputs.
- Files: No integration test directory or fixtures exist
- Risk: Changes to one module can break the pipeline in ways unit tests cannot detect.
- Priority: **High** -- even one golden-file integration test (run pipeline on a known STEP file, compare output) would catch most regressions.

**No API tests:**
- What's not tested: FastAPI endpoints (upload, job polling, health check) have no automated tests.
- Files: `manufacturing_pipeline/api/` (entire directory untested except `test_timeline_api.py` which tests a helper function, not the API itself)
- Risk: API deployment regressions (auth bypass, file handling, response format changes) go undetected.
- Priority: **Medium** -- API is a deployment convenience, CLI is the primary interface.

## Missing Capabilities

**No input validation for STEP file content:**
- Problem: The pipeline validates file extensions but not STEP file content validity before processing. Malformed STEP files can cause unpredictable crashes deep in the OCP/CadQuery stack.
- Files: `manufacturing_pipeline/analysis/step_processing.py` (line 29 has a `sanitize` function for STEP headers, but no structural validation)
- Blocks: Robust error reporting for bad input files.

**No retry/resume for API jobs:**
- Problem: If analysis fails partway through for an API job, the job is marked failed with no retry mechanism.
- Files: `manufacturing_pipeline/api/routes.py`, `manufacturing_pipeline/api/job_manager.py`
- Blocks: Reliable batch processing via API.

**Incomplete net surface area calculation:**
- Problem: `excel_exporter.py` line 174 has a TODO: `opperv_netto = oppervlakte  # TODO: subtract hole areas when available`. Net surface area (minus holes) is not calculated.
- Files: `manufacturing_pipeline/reporting/excel_exporter.py` (line 174)
- Blocks: Accurate surface treatment cost estimation.

---

*Concerns audit: 2026-03-25*
