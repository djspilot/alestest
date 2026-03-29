# Analysis Module — Refactoring Priority

> Generated: 2026-03-28

## Summary

The `analysis/` folder contains ~19k lines across 16 files. The main issues are **god modules**, **cross-file duplication** of geometry/classification heuristics, and **poor separation of concerns** (CAD I/O mixed with business rules mixed with reporting).

---

## Priority Ranking

### 🔴 Critical (refactor first)

| # | File | Lines | Scope | Key Issues |
|---|------|------:|:-----:|------------|
| 1 | `step_processing.py` | 2659 | XL | God module: mixes STEP loading, tessellation, sheet metal analysis, image export, topology, and classification. Duplicates logic from `sheetmetal_analysis.py`, `cut_features.py`, `iso_standards.py`. |
| 2 | `assembly_analysis.py` | 2630 | XL | Second god module: BOM generation mixed with geometric heuristics, fastener catalogs, part classification rules. Duplicates classification from `classification.py`. Bare `except` blocks. |
| 3 | `classification.py` | 2250 | L–XL | Giant rule engine with implicit thresholds. Overlaps with `assembly_analysis.py` and `step0_section_tools.py`. Hard to unit test. |

### 🟠 High (refactor next)

| # | File | Lines | Scope | Key Issues |
|---|------|------:|:-----:|------------|
| 4 | `freecad_unfold.py` | 1654 | L | Fragile integration code: string-generated Python scripts, duplicated helpers (`_find_largest_planar_face` vs `find_largest_planar_face`), platform-path hunting mixed with runtime logic. |
| 5 | `profile_classifier.py` | 1462 | L | OCC/OCP compat shim mixed with business logic. Strong duplication with `step0_section_tools.py` (sectioning, clustering, template matching). |
| 6 | `cut_features.py` | 1358 | M | One giant orchestration function (`extract_cut_features_for_sheet`). Mixes flat-vs-3D selection, hole detection, contour labeling, countersink inference. |
| 7 | `part_analyzer.py` | 717 | M | One giant `analyze_part_geometry()` function. Reimplements logic that should call `classification.py`, `sheetmetal_analysis.py`. |

### 🟡 Medium (refactor after top tier stabilizes)

| # | File | Lines | Scope | Key Issues |
|---|------|------:|:-----:|------------|
| 8 | `werkvoorbereiding.py` | 1375 | M | Large but stable catalogs + calculators in one file. Could split into catalogs, costing, routing, purchasing. |
| 9 | `profile_features.py` | 1058 | M | Duplicates geometric extraction from `profile_classifier.py` and `step0_section_tools.py`. |
| 10 | `sheetmetal_analysis.py` | 894 | M | Fairly cohesive but main function is large. ERP policy mixed with geometry detection. |
| 11 | `step0_section_tools.py` | 853 | M | Good focus, but overlaps with `profile_classifier.py`. Should become the canonical geometry utility after refactoring. |

### 🟢 Low (leave for now)

| # | File | Lines | Scope | Key Issues |
|---|------|------:|:-----:|------------|
| 12 | `pipeline_stages.py` | 431 | S | Fine by itself. Pain comes from importing god modules. |
| 13 | `iso_standards.py` | 696 | S | Mostly stable, table-driven, pure functions. Could split later. |
| 14 | `router.py` | 211 | S | Small and understandable. |
| 15 | `classification_variables.py` | 166 | S | Simple constants — exactly the pattern we want. |
| 16 | `correlation.py` | 20 | S | Stub. Only touch if functionality expands. |

---

## Cross-Cutting Issues

### Duplicated Logic (highest risk)
These heuristics appear in **multiple files** and diverge over time:

| Concern | Duplicated across |
|---------|-------------------|
| Sheet metal bend detection | `step_processing.py`, `sheetmetal_analysis.py`, `part_analyzer.py` |
| Part classification rules | `classification.py`, `assembly_analysis.py`, `step0_section_tools.py` |
| Sectioning/PCA utilities | `profile_classifier.py`, `profile_features.py`, `step0_section_tools.py` |
| Hole/thread detection | `step_processing.py`, `cut_features.py`, `part_analyzer.py` |

### Recommended Canonical Owners

| Domain | Canonical file |
|--------|---------------|
| Sectioning & geometry utilities | `step0_section_tools.py` |
| Classification rules & thresholds | `classification.py` + `classification_variables.py` |
| Sheet metal bends | `sheetmetal_analysis.py` |
| Hole/thread/countersink | `cut_features.py` |
| BOM & assembly | `assembly_analysis.py` |

---

## Suggested End-State Package Structure

```
analysis/
├── step_io.py                 # STEP loading, normalization, XCAF fallback
├── geometry/                  # Topology, bbox, sectioning, OCC helpers
├── classification/            # Step 0 engine + thresholds + shared metrics
├── sheetmetal/                # Bend detection, unfold integration, flat pattern
├── features/                  # Holes, cut features, profile features
├── bom/                       # Assembly, BOM, fastener grouping
└── manufacturing/             # Costing, tooling, outsourcing, standards
```

---

## Before Refactoring: Guardrails

1. **Freeze a regression corpus** — representative STEP parts (flat plate, bent sheet, tube, profile, turned, machined, assembly)
2. **One owner per heuristic** — never edit the same threshold in 2 files
3. **Thin compatibility wrappers** — keep old function signatures while splitting modules to avoid breaking orchestrators
4. **Unit test extraction** — pull out pure functions first (easiest wins, highest confidence)
