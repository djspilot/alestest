# Analysis Refactor Continue Guide

This file is the working checklist for continuing the `manufacturing_pipeline/analysis` refactor.

## Rules

- [ ] Keep all current public import paths working
- [ ] Treat underscore-prefixed imports used outside their module as compatibility surface
- [ ] Prefer extracting code into internal modules first, then turning the old top-level module into a wrapper
- [ ] Run tests serially, not in parallel
- [ ] Use `pytest -q` and `PYTHONPATH=/Users/ds/AIdoel/alestest pytest -q` as acceptance checks
- [ ] Keep the local STEP smoke manifest green while refactoring internals

## Current State

Already extracted:

- [x] Shared profile/section geometry in `geometry/profile_sections.py`
- [x] STEP 0 implementation behind `classification_core/step0.py`
- [x] STEP IO helpers in `io/step_file_io.py`
- [x] Hole and contour detection in `features/hole_detection.py`
- [x] Assembly/BOM implementation behind `bom/assembly_analysis.py`
- [x] STEP 0 geometry metrics in `classification_core/geometry_metrics.py`
- [x] STEP 0 result helpers in `classification_core/result_types.py`
- [x] STEP 0 slice validation helpers in `classification_core/validation.py`
- [x] STEP 0 hollow-closed helpers in `classification_core/hollow_closed.py`
- [x] Local STEP smoke manifest in `manufacturing_pipeline/tests/step_regression_manifest.json`

Still large / not properly split:

- [ ] `classification_core/step0.py`
- [ ] `step_processing.py`
- [ ] `cut_features.py`
- [ ] `freecad_unfold.py`
- [ ] `profile_classifier.py`
- [ ] `profile_features.py`
- [ ] `part_analyzer.py`
- [ ] `sheetmetal_analysis.py`

## Next Recommended Order

### 1. Finish `classification_core/step0.py`

- [x] Extract `_step_0_2_hollow_closed` into `classification_core/hollow_closed.py`
- [x] Extract `_step_0_3_open_profile` into `classification_core/open_profile.py`
- [x] Extract `_step_0_4a_flat_plate` and `_step_0_4b_constant_thickness_open` into `classification_core/plate_rules.py`
- [x] Extract `_step_0_5_solid_profile_fallback` into `classification_core/solid_profile_fallback.py`
- [ ] Keep `classify_step0` and `classify_step0_detailed_trace` in `classification_core/step0.py` as the orchestration layer
- [x] Add compatibility assertions when internal helper ownership changes

### 2. Keep thinning `step_processing.py`

- [x] Extract thread / shaft / chamfer / fillet helpers into `features/`
- [x] Extract sheet analysis orchestration helpers into `sheetmetal/`
- [ ] Leave only compatibility wrappers plus orchestration in `step_processing.py`
- [x] Make sure wrappers pass any required legacy callbacks explicitly

### 3. Split remaining duplicated profile logic

- [ ] Move remaining shared 2D/profile logic out of `profile_classifier.py`
- [x] Make `step0_section_tools.py` and `profile_classifier.py` delegate to the same canonical geometry helpers
- [ ] Remove duplicated template generation only after wrapper tests prove identity

### 4. Refactor `cut_features.py`

- [x] Move sheet cut-feature helpers into `features/`
- [x] Move profile cut-feature helpers into `features/`
- [x] Keep `extract_cut_features_for_sheet` and `extract_cut_features_for_profile` as top-level compatibility exports

### 5. Refactor `freecad_unfold.py`

- [x] Split FreeCAD path discovery / environment probing from unfold geometry logic
- [x] Move process execution helpers behind an internal module
- [x] Keep the public unfold functions unchanged

## STEP Smoke Coverage

Current tracked manifest cases:

- [x] `data/input/testcase/10040878_1.stp`
- [x] `data/input/10015088_3.stp`
- [x] `data/input/20253440/MD-22-08183_1.stp`
- [x] `data/input/fwofferte20253515bestanden/10000890096_Rev_00.step`

Expand next:

- [ ] Add one assembly-oriented local sample
- [ ] Add one unfold-capable local sample
- [ ] Add one stable round/tube sample if current router/profile path becomes reliable

## Validation Checklist

Run after each refactor slice:

- [ ] `python3 -m compileall manufacturing_pipeline/analysis`
- [ ] targeted pytest for touched modules
- [ ] `pytest -q`
- [ ] `PYTHONPATH=/Users/ds/AIdoel/alestest pytest -q`

If STEP-related code changed:

- [ ] `pytest -q manufacturing_pipeline/tests/test_step_regression_manifest.py`

## Do Not Do

- [ ] Do not delete compatibility wrappers yet
- [ ] Do not rename public functions yet
- [ ] Do not move large behavior and API changes in the same step
- [ ] Do not run full test suites in parallel because `test_get_output_dir` can race on cleanup
