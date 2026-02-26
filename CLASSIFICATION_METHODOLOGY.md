# Classification Methodology - ALES Manufacturing Pipeline

**Version:** 2.0  
**Date:** February 26, 2026  
**Status:** Production Ready

---

## Overview

The manufacturing pipeline classifies parts into three categories to optimize production routing:

| Classification | Description | Manufacturing Process |
|---------------|-------------|----------------------|
| **PLAAT** | Flat sheet metal parts | Laser cutting, folding, welding |
| **PROFIEL** | Structural profiles/beams | Sawing, drilling, assembly |
| **ANDERS** | Everything else | Machining, purchased items, complex parts |

---

## PLAAT (Plate Part) Detection

### Primary Method: Face-Based Analysis (NEW in v2.0)

**Algorithm:**
1. Extract all faces from solid geometry
2. Calculate surface area of each face
3. Sort faces by area (descending)
4. Check: Do top-2 faces comprise >50% of total surface area?
5. If YES → classify as PLAAT

**Code:**
```python
def _is_plate_by_face_analysis(solid, threshold=50.0):
    """Check if solid is a plate by analyzing face areas."""
    face_areas = [get_face_area(face) for face in get_faces(solid)]
    face_areas.sort(reverse=True)
    total_area = sum(face_areas)
    top2_percent = ((face_areas[0] + face_areas[1]) / total_area) * 100
    return top2_percent > threshold
```

**Why this works:**
- Plates have two dominant parallel faces (top and bottom)
- Features (holes, cutouts, weld preps) add small faces but don't change dominance
- Works for thick plates (20-50mm) that fail bounding box checks

**Threshold rationale:**
- **50%** chosen for industrial parts with features
- Higher (60-70%): Misses plates with many holes
- Lower (30-40%): Risk of false positives on machined blocks

### Fallback Method: Thin Plate Check (Legacy)

For very thin plates (<10mm) where face analysis might struggle:

**Criteria:**
- `smallest_dimension < 25mm` AND
- `thickness_ratio < 0.15` (thickness < 15% of width) AND
- `aspect_ratio > 5` (length > 5× thickness)

**Examples:**
- ✓ 5×210×300mm → PLAAT
- ✓ 3×54×1100mm → PLAAT
- ✗ 50×850×2270mm → Would fail thickness_ratio, but passes face analysis ✓

---

## PROFIEL (Profile) Detection

**Criteria:**
- `smallest_dimension ≥ 5mm` (not a thin sheet)
- `length_ratio ≥ 5.0` (elongated)
- `cross_ratio 0.5-2.0` (roughly rectangular cross-section)
- `volume_ratio > 0.5` (solid, not hollow)

**Examples:**
- ✓ 8.5×16.7×1400mm beam → PROFIEL
- ✓ Rectangular bar stock
- ✗ Thin-walled tube (low volume_ratio)

### Standard Profile Override

**DIN/EN/ISO catalog profiles** are classified as **ANDERS** (purchased, not manufactured):

**Detection:**
- Part name contains: `DIN `, `DIN-`, `EN `, `EN-`, `ISO `, `ISO-`
- Applied during Excel export stage

**Examples:**
- "DIN 1026 - U 160 - 600" → ANDERS (U-profile from catalog)
- "EN 10210-2 - 88,9 x 4 - 65" → ANDERS (RHS tube from standard)

**Rationale:**
- These are purchased items, not manufactured from plate/sheet
- Different cost calculation (catalog price vs. manufacturing cost)
- Different lead time (stock vs. production)

---

## ANDERS (Other) Classification

Catch-all for parts that don't fit PLAAT or PROFIEL:

**Includes:**
- Machined parts (milled blocks, turned shafts)
- Standard catalog items (DIN/EN/ISO)
- Fasteners (bolts, nuts, washers - auto-detected)
- Complex geometry (castings, formed parts with extensive features)
- Parts with face-ratio <50% but >25mm thick

**Fastener Auto-Detection:**

Checked BEFORE classification to prevent false matches:

```python
def identify_fastener(solid, volume, dims):
    # Reject plates first (face analysis)
    if _is_plate_by_face_analysis(solid, threshold=50.0):
        return None  # Not a fastener
    
    # Then check fastener patterns
    if matches_bolt_dimensions(dims):
        return {"type": "bout", "size": "M20", ...}
    if matches_nut_dimensions(dims):
        return {"type": "moer", "size": "M10", ...}
    # etc.
```

**Why rejection order matters:**
- A 20×100×800mm plate could match M20 bolt diameter
- Face analysis catches this before fastener check
- Prevents misclassification

---

## Decision Flow

```
┌─────────────┐
│  Load Solid │
└──────┬──────┘
       │
       ▼
┌─────────────────────────────┐
│ Part name has DIN/EN/ISO?   │──YES──▶ ANDERS (purchased)
└──────┬──────────────────────┘
       │ NO
       ▼
┌─────────────────────────────┐
│ Fastener pattern detected?  │──YES──▶ ANDERS (fastener)
│ (after plate rejection)     │
└──────┬──────────────────────┘
       │ NO
       ▼
┌─────────────────────────────┐
│ Face analysis: top-2 >50%?  │──YES──▶ PLAAT
└──────┬──────────────────────┘
       │ NO
       ▼
┌─────────────────────────────┐
│ Thin plate: thick<25mm,     │──YES──▶ PLAAT
│ ratio<0.15, aspect>5?       │
└──────┬──────────────────────┘
       │ NO
       ▼
┌─────────────────────────────┐
│ Profile: length>5×width,    │──YES──▶ PROFIEL
│ cross 0.5-2.0, vol>0.5?     │
└──────┬──────────────────────┘
       │ NO
       ▼
    ANDERS
```

---

## Accuracy & Limitations

### Test Results (5 STEP files)

| File | Plaat | Profiel | Anders | Accuracy |
|------|-------|---------|--------|----------|
| 10040852_1.stp | 2 | 2 | 1 | ✓ 100% |
| 10040878_1.stp | 2 | 2 | 1 | ✓ 100% |
| 2006020_A-00.STEP | 0 | 0 | 2 | ✓ 100% |
| MD-16-03698_R2.stp | 2 | 1 | 2 | ✓ 100% |
| 31686-080.stp | 8 | 0 | 10 | ≈ 80% |

**Overall:** 80-85% classification accuracy

### Known Limitations

**Parts misclassified as ANDERS (should be PLAAT):**
- Very complex features (>50% surface from holes/pockets)
- Example: 50mm plate with extensive cutouts → face ratio 30%

**Root cause:**
- Feature geometry dominates surface area
- Top-2 faces no longer >50% of total

**Workarounds:**
1. Lower threshold to 35-40% (may cause false positives)
2. Implement feature detection preprocessing (recommended for v3.0)

**Example from 31686-080.stp:**

| Part | Thickness | Face Ratio | Classification | Should Be |
|------|-----------|------------|----------------|-----------|
| 31686-363 | 50mm | 30.1% | Anders | Plaat |
| 31686-365 | 54mm | 17.5% | Anders | Plaat |
| 31686-370 | 54mm | 48.2% | Anders | Plaat |

These have extensive internal pockets/cutouts that add many small faces.

---

## Implementation Details

### Key Functions

**Location:** `manufacturing_pipeline/analysis/assembly_analysis.py`

```python
_is_plate_by_face_analysis(solid, threshold=50.0) -> bool
    """Face-based plate detection (new in v2.0)"""
    
classify_solid(solid) -> str
    """Main classification function. Returns: 'plaat', 'profiel', 'anders'"""
    
identify_fastener(solid, volume, dims) -> Optional[Dict]
    """Fastener detection with plate rejection"""
```

**Location:** `export_classification_excel.py`

```python
# DIN/EN/ISO override during export
if part_name:
    name_upper = part_name.upper()
    is_standard = any(std in name_upper for std in ['DIN ', 'EN ', 'ISO '])
    if is_standard:
        part_class = 'anders'
```

### Dependencies

- **OCP (OpenCascade Python)**: Face extraction, surface area calculation
- **CadQuery**: STEP file loading, geometry manipulation
- **TopExp_Explorer**: Topology traversal (faces, edges)
- **BRepGProp**: Surface area calculation

---

## Future Improvements (v3.0 Roadmap)

### Feature-Based Classification

**Concept:**
1. **Preprocess**: Identify base geometry (largest faces)
2. **Feature Detection**: Recognize holes, pockets, chamfers
3. **Feature Suppression**: Conceptually "remove" features
4. **Classify**: On clean base geometry
5. **Feature Re-application**: Link features to classified part

**Benefits:**
- 90-95%+ accuracy (vs 80-85% now)
- Manufacturing intent clear (M8 holes → assembly features)
- Better cost estimation (feature machining time)

**Complexity:**
- Requires robust feature recognition (AAG, B-rep analysis)
- Computationally expensive
- Risk of false feature detections

**Timeline:** Q2 2026 (after feature detection engine complete)

---

## References

- **Changelog**: [CHANGELOG_PLATE_DETECTION.md](CHANGELOG_PLATE_DETECTION.md)
- **Test Suite**: `test_final_verification.py`
- **Debug Tools**: 
  - `debug_face_classification.py` — Analyze face ratios
  - `analyze_problem_groups.py` — Investigate misclassifications
  - `test_plate_detection.py` — Face-based detection testing

---

*For questions or contributions, see main [README.md](README.md)*
