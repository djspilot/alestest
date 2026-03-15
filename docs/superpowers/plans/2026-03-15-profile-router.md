# Profile Router Integration Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate `step_profile_classifier.py` into the manufacturing pipeline as a pre-router that classifies solids into PLAAT/PROFIEL/ROND/OVERIG before analysis begins.

**Architecture:** Copy `step_profile_classifier.py` into `manufacturing_pipeline/analysis/`. Add a thin `router.py` that calls the classifier and maps its labels to four routing categories. Wire the router into `cli.py` as the first step after STEP loading, passing the `RouteResult` downstream.

**Tech Stack:** Python, OCP/pythonocc, Shapely, NumPy, SciPy (all already in requirements.txt)

---

## File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `manufacturing_pipeline/analysis/profile_classifier.py` | Cross-section profile classification (copied from `step_profile_classifier.py`) |
| Create | `manufacturing_pipeline/analysis/router.py` | Route enum + mapping logic + `route_solid()` / `route_step_file()` |
| Create | `tests/test_router.py` | Tests for router mapping and integration |
| Modify | `manufacturing_pipeline/core/models.py` | Add `RouteCategory` enum |
| Modify | `manufacturing_pipeline/core/utils.py` | Call router in `run_analysis()`, pass result downstream |
| Modify | `manufacturing_pipeline/cli.py` | Call router in full pipeline, display route result |
| Modify | `profile_pipeline/pipeline.py` | Update imports to use `manufacturing_pipeline.analysis.profile_classifier` |

---

## Chunk 1: Core — profile_classifier + router + models

### Task 1: Copy profile_classifier into manufacturing_pipeline

**Files:**
- Create: `manufacturing_pipeline/analysis/profile_classifier.py`
- Source: `/Users/ds/AIdoel/spaceclaim test/step_profile_classifier.py`

- [ ] **Step 1: Copy the file**

```bash
cp "/Users/ds/AIdoel/spaceclaim test/step_profile_classifier.py" \
   manufacturing_pipeline/analysis/profile_classifier.py
```

- [ ] **Step 2: Verify the copy**

```bash
wc -l manufacturing_pipeline/analysis/profile_classifier.py
```

Expected: 1321 lines

- [ ] **Step 3: Verify syntax**

```bash
python -c "import ast; ast.parse(open('manufacturing_pipeline/analysis/profile_classifier.py').read()); print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add manufacturing_pipeline/analysis/profile_classifier.py
git commit -m "feat(router): copy step_profile_classifier into manufacturing_pipeline"
```

---

### Task 2: Add RouteCategory to core/models.py

**Files:**
- Modify: `manufacturing_pipeline/core/models.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_router.py`:

```python
"""Tests for profile routing."""
import pytest
from manufacturing_pipeline.core.models import RouteCategory


def test_route_category_values():
    assert RouteCategory.PLAAT.value == "plaat"
    assert RouteCategory.PROFIEL.value == "profiel"
    assert RouteCategory.ROND.value == "rond"
    assert RouteCategory.OVERIG.value == "overig"


def test_route_category_has_four_members():
    assert len(RouteCategory) == 4
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_router.py::test_route_category_values -v
```

Expected: FAIL — `ImportError: cannot import name 'RouteCategory'`

- [ ] **Step 3: Add RouteCategory to models.py**

Add to `manufacturing_pipeline/core/models.py`:

```python
class RouteCategory(Enum):
    """Pre-routing classificatie: bepaalt welk pad de pipeline volgt."""
    PLAAT = "plaat"        # Vlakke plaat / plaatwerk (incl. gebogen plaat)
    PROFIEL = "profiel"    # Stalen profiel (I/U/L/T/koker)
    ROND = "rond"          # Rond staal / buis / draaistuk
    OVERIG = "overig"      # Niet geclassificeerd
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest tests/test_router.py::test_route_category_values tests/test_router.py::test_route_category_has_four_members -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add manufacturing_pipeline/core/models.py tests/test_router.py
git commit -m "feat(router): add RouteCategory enum to core models"
```

---

### Task 3: Create router.py with mapping logic

**Files:**
- Create: `manufacturing_pipeline/analysis/router.py`
- Modify: `tests/test_router.py`

- [ ] **Step 1: Write failing tests for the mapping**

Add to `tests/test_router.py`:

```python
from manufacturing_pipeline.analysis.router import RouteResult, map_profile_label


def test_map_plat_staal_to_plaat():
    result = map_profile_label("PLAT_STAAL", 0.98)
    assert result.category == RouteCategory.PLAAT


def test_map_i_family_to_profiel():
    result = map_profile_label("I_FAMILY", 0.90)
    assert result.category == RouteCategory.PROFIEL


def test_map_u_family_to_profiel():
    result = map_profile_label("U_FAMILY", 0.85)
    assert result.category == RouteCategory.PROFIEL


def test_map_l_family_to_profiel():
    result = map_profile_label("L_FAMILY", 0.85)
    assert result.category == RouteCategory.PROFIEL


def test_map_t_family_to_profiel():
    result = map_profile_label("T_FAMILY", 0.80)
    assert result.category == RouteCategory.PROFIEL


def test_map_rechthoekige_koker_to_profiel():
    result = map_profile_label("RECHTHOEKIGE_KOKER", 0.98)
    assert result.category == RouteCategory.PROFIEL


def test_map_rond_staal_to_rond():
    result = map_profile_label("ROND_STAAL", 0.99)
    assert result.category == RouteCategory.ROND


def test_map_ronde_buis_to_rond():
    result = map_profile_label("RONDE_BUIS", 0.99)
    assert result.category == RouteCategory.ROND


def test_map_anders_to_overig():
    result = map_profile_label("ANDERS", 0.60)
    assert result.category == RouteCategory.OVERIG


def test_map_unknown_label_to_overig():
    result = map_profile_label("SOMETHING_NEW", 0.50)
    assert result.category == RouteCategory.OVERIG


def test_route_result_has_profile_label():
    result = map_profile_label("ROND_STAAL", 0.99)
    assert result.profile_label == "ROND_STAAL"
    assert result.confidence == 0.99


def test_route_result_has_reasoning():
    result = map_profile_label("I_FAMILY", 0.90)
    assert len(result.reasoning) > 0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_router.py -v -k "map_"
```

Expected: FAIL — `ImportError: cannot import name 'RouteResult'`

- [ ] **Step 3: Create router.py**

Create `manufacturing_pipeline/analysis/router.py`:

```python
"""
Profile Router — pre-classifies STEP solids into manufacturing categories.

Runs the cross-section profile classifier and maps its labels to four
routing categories: PLAAT, PROFIEL, ROND, OVERIG. The manufacturing
pipeline uses this to decide which analysis path to follow.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from manufacturing_pipeline.core.models import RouteCategory

logger = logging.getLogger("profile_router")

# Label → RouteCategory mapping
_LABEL_MAP: dict[str, RouteCategory] = {
    "PLAT_STAAL": RouteCategory.PLAAT,
    "I_FAMILY": RouteCategory.PROFIEL,
    "U_FAMILY": RouteCategory.PROFIEL,
    "L_FAMILY": RouteCategory.PROFIEL,
    "T_FAMILY": RouteCategory.PROFIEL,
    "RECHTHOEKIGE_KOKER": RouteCategory.PROFIEL,
    "ROND_STAAL": RouteCategory.ROND,
    "RONDE_BUIS": RouteCategory.ROND,
    "ANDERS": RouteCategory.OVERIG,
}


@dataclass
class RouteResult:
    """Result of the pre-routing classification."""
    category: RouteCategory
    profile_label: str       # Original label from profile classifier
    confidence: float        # 0..1
    reasoning: str           # Why this route was chosen
    variant: str | None = None  # Template variant (e.g. "i-b0.55-tw0.08-tf0.14")
    method: str = ""         # "rule", "template", "template-fallback"


def map_profile_label(label: str, confidence: float, variant: str | None = None, method: str = "") -> RouteResult:
    """Map a profile classifier label to a RouteResult."""
    category = _LABEL_MAP.get(label, RouteCategory.OVERIG)

    reasoning_map = {
        RouteCategory.PLAAT: f"Profiel '{label}' is plat staal → PLAAT route",
        RouteCategory.PROFIEL: f"Profiel '{label}' is een stalen profiel → PROFIEL route",
        RouteCategory.ROND: f"Profiel '{label}' is rond/buisvormig → ROND route",
        RouteCategory.OVERIG: f"Profiel '{label}' niet herkend als standaard → OVERIG route",
    }

    return RouteResult(
        category=category,
        profile_label=label,
        confidence=confidence,
        reasoning=reasoning_map[category],
        variant=variant,
        method=method,
    )


def route_solid(solid_shape: Any) -> RouteResult:
    """Classify a single OCC solid and return a RouteResult.

    Uses the profile classifier's cross-section analysis to determine
    the solid's profile type, then maps to a routing category.
    """
    from manufacturing_pipeline.analysis.profile_classifier import (
        classify_solid_profile,
        ProfileRegistry,
    )

    registry = ProfileRegistry().extend_generic_defaults()
    result = classify_solid_profile(solid_shape, registry=registry)

    return map_profile_label(
        label=result.get("label", "ANDERS"),
        confidence=result.get("confidence", 0.0),
        variant=result.get("variant"),
        method=result.get("method", ""),
    )


def route_step_file(step_path: str | Path) -> RouteResult:
    """Classify a STEP file and return a RouteResult.

    For multi-solid files, classifies the largest solid (by bounding box volume).
    """
    from manufacturing_pipeline.analysis.profile_classifier import (
        read_step_solids,
        read_step_solids_flat,
        classify_solid_profile,
        ProfileRegistry,
        solid_vertices_np,
    )
    import numpy as np

    step_path = str(step_path)

    # Try flat reader first (consistent with manufacturing pipeline)
    solids = []
    for reader in [read_step_solids_flat, read_step_solids]:
        try:
            solids = reader(step_path)
            if solids:
                break
        except Exception as e:
            logger.debug("Reader failed: %s", e)

    if not solids:
        logger.warning("No solids found in %s, routing as OVERIG", step_path)
        return RouteResult(
            category=RouteCategory.OVERIG,
            profile_label="ANDERS",
            confidence=0.0,
            reasoning="Geen solids gevonden in STEP bestand",
        )

    # Pick largest solid by bounding box volume
    best_solid = solids[0]
    best_vol = 0.0
    for s in solids:
        try:
            verts = solid_vertices_np(s.shape)
            dims = verts.max(axis=0) - verts.min(axis=0)
            vol = float(np.prod(dims))
            if vol > best_vol:
                best_vol = vol
                best_solid = s
        except Exception:
            pass

    registry = ProfileRegistry().extend_generic_defaults()
    result = classify_solid_profile(best_solid.shape, registry=registry)

    route = map_profile_label(
        label=result.get("label", "ANDERS"),
        confidence=result.get("confidence", 0.0),
        variant=result.get("variant"),
        method=result.get("method", ""),
    )

    logger.info(
        "Routed %s → %s (%s, confidence=%.2f)",
        Path(step_path).name,
        route.category.value,
        route.profile_label,
        route.confidence,
    )
    return route
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_router.py -v -k "map_"
```

Expected: all `map_*` tests PASS

- [ ] **Step 5: Commit**

```bash
git add manufacturing_pipeline/analysis/router.py tests/test_router.py
git commit -m "feat(router): add router module with label mapping and route_solid/route_step_file"
```

---

## Chunk 2: Wire router into manufacturing pipeline

### Task 4: Integrate router into quick mode (run_analysis in utils.py)

**Files:**
- Modify: `manufacturing_pipeline/core/utils.py` (around line 217, inside `run_analysis()`)

The router should run immediately after the STEP file is loaded (after step [1/6], before step [2/6]).

- [ ] **Step 1: Add router import and call**

In `run_analysis()` at `manufacturing_pipeline/core/utils.py:243`, after `shape = load_step_file(step_file)`, add:

```python
    # === ROUTING: Pre-classify via cross-section profile analysis ===
    print("[1.5/6] Running profile router...")
    try:
        from manufacturing_pipeline.analysis.router import route_step_file
        route_result = route_step_file(step_file)
        print(f"  Route: {route_result.category.value.upper()} "
              f"(profiel: {route_result.profile_label}, "
              f"confidence: {route_result.confidence:.0%})")
        print(f"  {route_result.reasoning}")
    except Exception as e:
        print(f"  Warning: Router failed ({e}), continuing without routing")
        route_result = None
```

- [ ] **Step 2: Pass route_result to the result dict**

Find where `run_analysis()` builds its final result dict or calls reporting. Add `route_result` to the data being passed along so downstream code can access it. The exact location depends on reading more of `run_analysis()` — look for where results are collected/returned.

- [ ] **Step 3: Test manually**

```bash
python run.py -f data/input/some_test_file.step
```

Expected: Output shows `[1.5/6] Running profile router...` with a route category.

- [ ] **Step 4: Commit**

```bash
git add manufacturing_pipeline/core/utils.py
git commit -m "feat(router): wire router into quick mode run_analysis"
```

---

### Task 5: Integrate router into full mode (cli.py)

**Files:**
- Modify: `manufacturing_pipeline/cli.py` (around line 145, inside `run_full_pipeline()`)

- [ ] **Step 1: Add router call after pipeline initialization**

In `run_full_pipeline()` at `manufacturing_pipeline/cli.py:145`, after the `PipelineRunner` is created but before stage 1, add:

```python
    # === Pre-routing ===
    if not production_only:
        print("Running profile router...")
    try:
        from manufacturing_pipeline.analysis.router import route_step_file
        route_result = route_step_file(step_file)
        if not production_only:
            print(f"  Route: {route_result.category.value.upper()} "
                  f"(profiel: {route_result.profile_label}, "
                  f"confidence: {route_result.confidence:.0%})")
            print(f"  {route_result.reasoning}\n")
    except Exception as e:
        if not production_only:
            print(f"  Warning: Router failed ({e}), continuing without routing\n")
        route_result = None
```

- [ ] **Step 2: Include route_result in JSON output**

In `save_to_json()`, add `route_result` to the `data` dict:

```python
    if route_result is not None:
        data["route"] = {
            "category": route_result.category.value,
            "profile_label": route_result.profile_label,
            "confidence": route_result.confidence,
            "reasoning": route_result.reasoning,
            "variant": route_result.variant,
            "method": route_result.method,
        }
```

- [ ] **Step 3: Test manually**

```bash
python run.py -f data/input/some_test_file.step --full
```

Expected: Route output appears before stage 1.

- [ ] **Step 4: Commit**

```bash
git add manufacturing_pipeline/cli.py
git commit -m "feat(router): wire router into full pipeline mode"
```

---

### Task 6: Update profile_pipeline imports

**Files:**
- Modify: `profile_pipeline/pipeline.py`

- [ ] **Step 1: Replace sys.path hack with proper import**

In `profile_pipeline/pipeline.py`, replace lines 16-32:

```python
# OLD:
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from step_profile_classifier import (
    Section2D,
    SolidInstance,
    ...
)

# NEW:
from manufacturing_pipeline.analysis.profile_classifier import (
    Section2D,
    SolidInstance,
    ProfileRegistry,
    read_step_solids,
    read_step_solids_flat,
    solid_vertices_np,
    find_extrusion_axis,
    section_plane_positions_from_vertices,
    slice_solid_to_section,
    dominant_section_cluster,
    normalize_section_polygon,
    section_distance,
    extract_section_features,
    classify_section,
)
```

Also remove the `import sys` if no longer needed, and remove the `sys.path.insert` line.

- [ ] **Step 2: Test profile_pipeline still works**

```bash
python -m profile_pipeline --help
```

Expected: Help text appears without import errors.

- [ ] **Step 3: Commit**

```bash
git add profile_pipeline/pipeline.py
git commit -m "refactor(profile_pipeline): import from manufacturing_pipeline instead of sys.path hack"
```

---

### Task 7: Run full test suite

- [ ] **Step 1: Run all tests**

```bash
python -m pytest tests/ -v
```

Expected: All tests pass (existing + new router tests).

- [ ] **Step 2: Final commit if any cleanup needed**

```bash
git add -u
git commit -m "chore: cleanup after router integration"
```
