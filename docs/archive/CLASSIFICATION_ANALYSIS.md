# Classificatie Criteria - Gestructureerd Overzicht

## Priority Order (Klassificatie Volgorde)

```
INPUT: Solid (OCP TopoDS shape)
     ↓
[STEP 1] STANDARD PROFILE CHECK
     ├─ 1a. Hollow Tube Detection → "anders"
     ├─ 1b. Variable Thickness Detection → "anders"
     └─ 1c. Closed Constant Section → "profiel"
     ↓ (if not matched)
[STEP 1.5] BENT SHEET DETECTION
     └─ Bent/Folded Sheet Metal → "plaat" or "profiel" (if closed loop)
     ↓ (if not matched)
[STEP 2] PLATE DETECTION
     ├─ 2a. Face Analysis (top 2 faces > 50%) → "plaat"
     └─ 2b. Traditional Thin Plate Check → "plaat"
     ↓ (if not matched)
[STEP 3] PROFILE DETECTION
     └─ Solid Rectangular Beam → "profiel"
     ↓ (if not matched)
[STEP 4] DEFAULT
     └─ → "anders"
```

---

## Detailed Criteria

### STEP 1A: Hollow Tube Detection
**Returns**: "anders" (purchased standard pipe/tube)
**Criteria**:
- Cylindrical faces ≥ 60% of surface area
- volume_ratio < 0.7 (not solid)
- Example: EN 10210-2 tube Ø88.9×4 mm

**Our case**: 
- ✅ 10000503252_Rev_00 (88.9×88.9×1162mm tube) - 24 edges, 6 faces
  - BUT: Gets "anders" with `default_anders` rule instead of `standard_hollow_tube`

---

### STEP 1B: Variable Thickness Profile Detection  
**Returns**: "anders" (purchased standard profile)
**Criteria**:
- Face area variation > 20%
- Elongated (length_ratio ≥ 5.0)
- Example: DIN 1026 UNP (I-beam profile)

**Our case**:
- No matches

---

### STEP 1C: Closed Constant Cross-Section
**Returns**: "profiel" (extruded profile)
**Criteria**:
- Multi-slice section check along dominant axis
- Closed contour ratio high
- Low perimeter variation
- Example: Square tube, circular pipe, complex extrusion

**Our case**:
- ✅ 10000503253_Rev_00 (35×100×191mm part) 
  - Rule: `closed_constant_section` → "profiel" ✓

---

### STEP 1.5: Bent Sheet Detection
**Returns**: "plaat" or "profiel" (if closed loop ≥360°)
**Criteria**:
- Edge count ≥ 8 (flat plate ~4, bent sheet ~12+)
- Small/medium volume_ratio
- Thin material (thickness < 100mm flexible)

**Our case**:
- ✅ 10000255318_Rev_00 (plaat with bends)
  - Rule: `bent_sheet_metal` → "plaat" ✓

---

### STEP 2A: Face Analysis (PRIMARY)
**Returns**: "plaat" (sheet metal)
**Criteria**:
- Top 2 planar faces > 50% of total surface area
- Indicates dominant opposing flat surfaces
- Works even with holes, cutouts, weld preps

**Our case**:
- ✅ 10000418502_Rev_00, 10000520810_Rev_00, 10000940837_Rev_00
  - Rule: `plate_face` → "plaat" ✓
- ❌ 10000520371_Rev_00 (82.451% top2 faces, but classified "anders")
  - Should match this rule but doesn't

---

### STEP 2B: Traditional Thin Plate Check (FALLBACK)
**Returns**: "plaat" (sheet metal)
**Criteria**:
- smallest_dimension < 25 mm (thin)
- thickness_ratio < 0.15 (smallest < 15% of width)
- aspect_ratio > 5 (elongated)

**Our case**:
- No matches (smallest dimensions all ≥ 35mm)

---

### STEP 3: Profile Detection
**Returns**: "profiel" (solid beam/extrusion)
**Criteria**:
1. **Primary criteria**:
   - smallest ≥ 5 mm
   - length_ratio ≥ 5.0 (longest ≥ 5× smallest)
   - cross_ratio 0.5-2.0 (middle/smallest between 0.5–2.0)

2. **Secondary volume check** (if primary matches):
   - Strong: volume_ratio > 0.5 → "profiel" ✓
   - Weak: volume_ratio 0.15-0.5 → use SA/V tiebreaker
     - If SA/V < 1.2 cm⁻¹ → "profiel" ✓
     - Else → default "anders"

**Our case**:
- ⚠️ 10000503252_Rev_00 (88.9×88.9×1162mm)
  - ✓ smallest=88.9 ≥ 5
  - ✓ length_ratio=13.1 ≥ 5.0
  - ✓ cross_ratio=1.0 in [0.5-2.0]
  - ❌ volume_ratio=0.246 < 0.5 (not strong)
  - Should check SA/V but doesn't reach this step (caught by STEP 1a?)

---

### STEP 4: Default (Catch-All)
**Returns**: "anders" (machined part, complex geometry)
**Criteria**:
- Anything not matching above rules

**Our case**:
- 10000503252_Rev_00 → "anders" with `default_anders`
- 10000520371_Rev_00 → "anders" with `standard_hollow_tube`
- 10000596440_Rev_00 → "anders" with `standard_hollow_tube`

---

## Current Classification Results

| Part | Actual | Expected | Rule | Issue |
|------|--------|----------|------|-------|
| 10000255318_Rev_00 | plaat | plaat | bent_sheet_metal | ✓ Correct |
| 10000520810_Rev_00 | plaat | plaat | plate_face | ✓ Correct |
| 10000418502_Rev_00 | plaat | plaat | plate_face | ✓ Correct |
| **10000503252_Rev_00** | **anders** | **profiel** | **default_anders** | ❌ Missed tube check |
| 10000503253_Rev_00 | profiel | profiel | closed_constant_section | ✓ Correct |
| **10000520371_Rev_00** | **anders** | **plaat?** | **standard_hollow_tube** | ⚠️ Over-conservative |
| **10000596440_Rev_00** | **anders** | **plaat?** | **standard_hollow_tube** | ⚠️ Over-conservative |
| 10000940837_Rev_00 | plaat | plaat | plate_face | ✓ Correct |

---

## Problems Identified

### Problem 1: 10000503252_Rev_00 (88.9mm Square Tube)
**Actual**: anders (via `default_anders`)
**Expected**: profiel (closed tube)  
**Root cause**: Should hit STEP 1a (hollow tube detection) but gets `default_anders` instead
- Possible: `_detect_hollow_tube()` returns False for this geometry
- Cross-check: Geometry looks correct (88.9×88.9×1162mm, 24 edges, 6 faces)

### Problem 2: 10000520371_Rev_00 & 10000596440_Rev_00 (35×100×191mm parts)
**Actual**: anders (via `standard_hollow_tube`)
**Expected**: plaat (bent sheet with multiple faces)
**Root cause**: `_detect_hollow_tube()` classifies these as "anders" but they have 53 faces (bent sheet metal!)
- These are NOT hollow tubes (solid bent sheet metal)
- False positives in `_detect_hollow_tube()` function

---

## Key Insights

1. **STEP 1A (Hollow Tube)** is too aggressive/loose
   - Catching bent sheet metal with complex faces
   - Need to distinguish: hollow tube (6 faces, round) vs bent plate (50+ faces, angular)

2. **10000503252 missing the tube classification**
   - Not being caught by STEP 1a despite looking like perfect tube
   - Either `_detect_hollow_tube()` fails OR reaches default before it's called

3. **Order matters critically**
   - Hollow tube check must come BEFORE bent sheet check
   - But it's also catching bent sheet parts

---

## Threshold Tuning Needed

| Function | Current | Issue | Suggested Fix |
|----------|---------|-------|----------------|
| `_detect_hollow_tube()` | cyl% ≥ 60% | Too aggressive | Add face count check (hollow=6 faces) AND verify circular faces |
| `_detect_hollow_tube()` | vol_ratio < 0.7 | Too loose | Stricter: volume_ratio < 0.4 (truly hollow) |
| `_detect_variable_thickness()` | area_diff > 20% | ??? | Check what this catches |
| Top2 Face Threshold | 50% | Might miss some | Consider 45% or dynamic based on face count |

---

## Next Steps

1. **Debug `_detect_hollow_tube()`**: Why doesn't 10000503252 trigger it?
2. **Verify face counts**: Hollow tubes should have 6-8 faces, bent sheets 40+
3. **Improve hollow tube check**: Add face topology validation
4. **Reduce false positives**: Don't classify bent sheet metal (50+ faces) as "hollow tube"
