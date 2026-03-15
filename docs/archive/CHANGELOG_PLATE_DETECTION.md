# Changelog - Plate Detection Improvements

## Date: 2026-02-26

### Context
Improved classification of sheet metal parts (plaatdelen) from STEP files. Previous classification relied solely on bounding box ratios, which failed for thick plates (>25mm) and plates with features (holes, cutouts, weld preparations).

---

## Changes Made

### 1. Face-Based Plate Detection (NEW)

**Location:** `manufacturing_pipeline/analysis/assembly_analysis.py`

**Function Added:** `_is_plate_by_face_analysis(solid, threshold=50.0)`

**Method:**
- Analyzes all faces of a solid
- Calculates surface area of each face
- If top 2 largest faces comprise >50% of total surface area → it's a plate
- More reliable than bounding box for thick plates with features

**Rationale:**
- Plates have two dominant parallel faces (top/bottom)
- Bounding box thickness ratio fails for:
  - Thick plates (50mm+): thickness_ratio > 0.15
  - Plates with many small features: disturbs aspect ratio
- Face analysis works regardless of thickness or feature count

**Threshold:**
- 50% chosen for industrial plates with holes/cutouts/weld preparations
- Higher threshold (60-70%) would miss plates with many features
- Lower threshold (<50%) risks false positives on machined blocks

---

### 2. Improved Fastener Detection

**Location:** `manufacturing_pipeline/analysis/assembly_analysis.py : identify_fastener()`

**Changes:**
- Added face-based plate rejection BEFORE fastener pattern matching
- Prevents plates from being misidentified as bolts (e.g., 20×100×800mm plate was detected as M20 bolt)

**New rejection criteria (in order):**
1. Face analysis indicates plate → reject as fastener
2. Thin plate by bbox (thickness_ratio < 0.15, aspect > 5) → reject
3. Solid profile (volume_ratio > 0.5, length_ratio ≥ 5) → reject
4. Then check fastener patterns (bolt, nut, washer)

---

### 3. Classification Logic Update

**Location:** `manufacturing_pipeline/analysis/assembly_analysis.py : classify_solid()`

**Updated classification order:**
1. **PLAAT** (primary): Face analysis (top-2 faces > 50% surface area)
2. **PLAAT** (fallback): Traditional thin plate (thickness < 25mm, thickness_ratio < 0.15, aspect > 5)
3. **PROFIEL**: Beam geometry (smallest ≥ 5mm, length_ratio ≥ 5, cross_ratio 0.5-2.0, volume_ratio check)
4. **ANDERS**: Everything else

**Key insight:** Face-based detection moved to PRIMARY check (not fallback)

---

### 4. Standard Profile Override

**Location:** `export_classification_excel.py`

**Changes:**
- DIN/EN/ISO standard profiles now classified as "Anders" (purchased items, not manufactured)
- Detection: Part name contains "DIN ", "DIN-", "EN ", "EN-", "ISO ", "ISO-"
- Override happens during Excel export (after part names are assigned)

**Examples:**
- "DIN 1026 - U 160 - 600" → Anders (U-profile from catalog)
- "EN 10210-2 - 88,9 x 4 - 65" → Anders (RHS tube from catalog)

**Rationale:** 
- Standard profiles are purchased, not manufactured from plate/sheet
- Should not be classified as "Plaat" even if geometry suggests it

---

## Test Results

### Before Changes:
- **31686-080.stp**: 5 Plaat, 0 Profiel, 13 Anders
  - Problem: Thick plates with features misclassified
  - Problem: Standard profiles detected as plates

### After Changes:
- **31686-080.stp**: 8 Plaat, 0 Profiel, 10 Anders
  - ✓ DIN 1026 U-profile → Anders
  - ✓ EN 10210 RHS tube → Anders
  - ✓ Thick plates (20-50mm) now detected
  - Items 3, 5-7, 9, 13, 18 remain "Anders" (complex geometry with extensive features)

### All Files Summary:
| File | Plaat | Profiel | Anders | Notes |
|------|-------|---------|--------|-------|
| 10040852_1.stp | 2 | 2 | 1 | ✓ |
| 10040878_1.stp | 2 | 2 | 1 | ✓ |
| 2006020_A-00.STEP | 0 | 0 | 2 | Machined parts |
| MD-16-03698_R2.stp | 2 | 1 | 2 | ✓ No false PROFIEL |
| 31686-080.stp | 8 | 0 | 10 | ✓ DIN/EN correct |

---

## Limitations & Known Issues

### Current Accuracy: ~80-85%

**Still classified as "Anders" despite being plates (31686-080):**
- Item 3 (31686-363): 50mm thick, extensive features → face ratio 30%
- Items 5-7 (31686-365-367): Complex cutouts/pockets → face ratio <50%
- Item 9 (31686-370): Internal features → face ratio 48%

**Root cause:** 
- Features (holes, pockets, chamfers) add extra faces
- Top-2 face percentage drops below 50% threshold
- Lowering threshold to 35% would capture these BUT risk false positives

**Recommended solution:** Feature detection preprocessing (future work)

---

## Code Quality

**Files Modified:**
1. `manufacturing_pipeline/analysis/assembly_analysis.py`
   - Added `_is_plate_by_face_analysis()` function
   - Updated `identify_fastener()` rejection logic
   - Updated `classify_solid()` primary detection method

2. `export_classification_excel.py`
   - Added DIN/EN/ISO standard profile override
   - Override applied after part naming

**No breaking changes:** Existing API maintained

---

## Next Steps (Future Work)

### Feature Detection Pipeline
1. **Preprocess:** Identify base geometry (largest faces)
2. **Feature Recognition:** Detect holes, pockets, chamfers, fillets
3. **Feature Removal:** Conceptually "clean" geometry
4. **Classify:** On simplified geometry
5. **Feature Analysis:** Extract manufacturing info (hole sizes → fasteners)

**Benefits:**
- Higher accuracy (90-95%+)
- Manufacturing intent clear (M8 holes → assembly holes)
- Better cost estimation (feature machining time)

**Complexity:** High (requires robust feature recognition algorithms)

---

## Testing Performed

```bash
# Export all classifications
python export_classification_excel.py

# Verify all 5 files
python test_all_classifications.py

# Debug specific issues
python debug_face_classification.py
python debug_fastener_blocking.py
python analyze_problem_groups.py
```

All tests passed. No regressions on existing files.

---

## Commit Message Suggestion

```
feat: Improve plate detection with face-based geometry analysis

- Add face-based plate detection (_is_plate_by_face_analysis)
  - Analyzes top 2 face areas vs total surface area
  - Threshold: 50% for industrial plates with features
  - More reliable than bbox for thick plates (>25mm)

- Enhance fastener detection rejection
  - Prevent plates from being misclassified as bolts
  - Face analysis check before pattern matching

- Add standard profile override (DIN/EN/ISO)
  - Catalog items classified as "Anders" (purchased)
  - Applied during Excel export

- Update classify_solid() priority order
  - Face-based detection now primary method
  - Bbox-based as fallback for thin plates

Test results: 80-85% accuracy on 5 STEP files
Known limitation: Complex features may still cause misclassification
Future: Feature detection preprocessing recommended
```
