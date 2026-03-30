# Analysis Refactor Continuation TODO

## Rules
- Keep all existing imports from `manufacturing_pipeline.analysis.*` working.
- Preserve callable signatures and return shapes unless a wrapper restores legacy behavior.
- Move logic into internal modules first, then leave thin compatibility wrappers behind.
- Treat underscore-prefixed names as public if other modules or tests import them.
- Run targeted tests first, then serial full-suite validation.

## Current Extracted State
- [x] Shared profile/section helpers moved to `geometry/profile_sections.py`
- [x] STEP 0 entrypoints wrapped through `classification_core/step0.py`
- [x] STEP file loading and tessellation moved to `io/step_file_io.py`
- [x] Hole and shaped-hole helpers moved to `features/hole_detection.py`
- [x] Assembly/BOM implementation moved to `bom/assembly_analysis.py`
- [x] STEP 0 helper layers extracted:
  - [x] `classification_core/geometry_metrics.py`
  - [x] `classification_core/result_types.py`
  - [x] `classification_core/validation.py`
  - [x] `classification_core/hollow_closed.py`
- [x] FreeCAD environment probing moved to `sheetmetal/freecad_environment.py`
- [x] FreeCAD subprocess execution moved to `sheetmetal/freecad_process.py`
- [x] FreeCAD flat-pattern geometry helpers moved to `sheetmetal/freecad_geometry.py`
- [x] Sheet-metal standards and flat-pattern calculators moved to `sheetmetal/standards.py`
- [x] Sheet-metal OCP bend detection moved to `sheetmetal/geometry_analysis.py`
- [x] Sheet-metal complete analysis/reporting moved to `sheetmetal/complete_analysis.py`
- [x] Cut-feature geometry/labeling helpers moved to `features/cut_features_geometry_helpers.py`
- [x] Cut-feature sheet/profile extractor flows moved to `features/cut_features_extractors.py`
- [x] Step-processing manufacturing orchestration moved to `features/manufacturing_orchestration.py`
- [x] Step-processing component reporting moved to `features/component_reporting.py`
- [x] Step-processing runtime support shims moved to `features/runtime_support.py`
- [x] Step-processing STEP IO and mesh/display-edge functions reduced to wrapper-only delegation
- [x] Step-processing hole/shaped-hole legacy bodies reduced to compatibility delegates
- [x] Local STEP regression harness added in `tests/test_step_regression_manifest.py`

## Next Refactor Steps
- [ ] Extract `_step_0_3_open_profile` ownership fully into `classification_core/open_profile.py` and keep `step0.py` thin
- [ ] Extract plate-rule ownership fully into smaller internal modules if `classification_core/plate_rules.py` is still carrying mixed concerns
- [ ] Continue thinning `step_processing.py` by moving more orchestration into `analysis/io/` and `analysis/features/`
- [x] Reduce `sheetmetal_analysis.py` to a thin compatibility wrapper and remove duplicate legacy bodies once no direct ownership remains
- [ ] Reduce `cut_features.py` to a thinner compatibility wrapper and remove any leftover duplicate helper ownership
- [ ] Refactor `cut_features.py` remaining ownership behind `analysis/features/` wrappers
- [ ] Expand the STEP regression manifest with one assembly sample and one unfold-capable sample

## Validation Checklist Per Slice
- [ ] `python3 -m compileall` for touched modules
- [ ] Targeted pytest for touched modules
- [ ] `pytest -q`
- [ ] `PYTHONPATH=/Users/ds/AIdoel/alestest pytest -q`

## Do Not Do
- [ ] Do not change public import paths during extraction
- [ ] Do not remove underscore helpers until all downstream imports are gone
- [ ] Do not run full suites in parallel because `test_get_output_dir` can race on cleanup
