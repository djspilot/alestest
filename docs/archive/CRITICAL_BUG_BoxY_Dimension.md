# CRITICAL BUG FOUND: BoxY Dimension Calculation in freecad_unfold.py

## Status
📍 **ANALYZED - ROOT CAUSE IDENTIFIED**  
🔴 **BLOCKER**: Feature validation fails for bent sheet metal parts due to incorrect unfold dimensions  
✅ **USER CONFIRMED**: Reference data is correct (272mm = valid unfold dimension)

## The Problem

### Symptom
For bent sheet metal part `10001081080_Rev_00` (part of assembly `10001091875_Rev_00`):
- **Expected**: Sheet_BoxY = 272mm
- **Actual**: Sheet_BoxY = 238mm (reported from freecad_unfold.py)
- **Error**: 12.5% mismatch

### Root Cause (USER INSIGHT - March 10)

238mm is **NOT** the total flat pattern dimension.  
It represents only the **folded height of the first arm** of the L-shaped part.

**Correct Calculation**:
```
Arm 1 (main vertical):    238mm - 8mm (thickness) = 230mm (unfolded)
Arm 2 (horizontal flange):  50mm - 8mm (thickness) =  42mm (unfolded)
                           ―――――――――――――――――――――――――――――――――――
TOTAL UNFOLD (BoxY):                           272mm ✅ CORRECT
```

### Why freecad_unfold Reports 238mm

When FreeCAD Sheet Metal `unfold_tree2()` returns unfolded faces:
1. Creates a Part.Shell() from all flattened faces
2. Calculates BoundBox.YLength of the shell
3. **BUG**: Apparently returns only one arm's YLength, not the sum of unfolded arms

**Hypothesis**: 
- The unfolded shell may have geometry that's not fully aligned in Y-axis
- Or FreeCAD reports intermediate folded segment length instead of total span
- Or coordinate transformation is incomplete

## Files Affected
- **`manufacturing_pipeline/analysis/freecad_unfold.py`** (Lines ~850-855):
  ```python
  bbox = flat_shell.BoundBox
  result['flat_length'] = bbox.XLength  # Works correctly ✓
  result['flat_width'] = bbox.YLength   # BUG: Returns 238 instead of 272
  ```

- **`manufacturing_pipeline/reporting/xml_exporter.py`** (Lines ~1632-1633):
  ```python
  flat_width = float(unfold_result.get('flat_width', 0) or 0)  # Uses wrong value
  calc_result.find('Sheet_BoxY').text = flat_width  # Writes 238 to XML
  ```

## Verification

✅ **DXF Visual Inspection** (LibreCAD screenshot):
- L-shaped profile with 1 bend (90°)
- Y-dimension visually measures ~270-280mm (matches expected 272mm)
- 11 holes arranged horizontally (confirmed)
- Current code produces 238mm → Visual inspection invalidates current output

✅ **Reference Data Validation**:
- User confirmed: "Gaten zitten er echt in" (11 holes confirmed)
- User confirmed: "BoxY = 272mm klopt" (272mm is correct)
- Reference voorbeeldxml.xml is authoritative

## Resolution Path

### Option A: Fix freecad_unfold.py Logic (PREFERRED)
Debug why BoundBox.YLength returns intermediate value:
1. Add debug logging to print all unfolded faces' dimensions
2. Check if face list is complete (all arms included?)
3. Verify coordinate system after unfold (rotation/translation issues?)
4. Possibly need to sum individual face extents instead of shell bounding box

### Option B: Post-Process the Result (WORKAROUND)
Calculate total unfold from geometry analysis:
- Sum all unfolded arm segment lengths
- Need access to bend parameters + original dimensions
- More fragile than fixing root cause

### Option C: Use DXF EXTMIN/EXTMAX Header (ALTERNATIVE)
Export DXF and read bounds from DXF header instead:
- freecad_unfold already exports DXF for visualization
- DXF header should contain correct EXTMIN/EXTMAX
- Current code doesn't extract DXF header bounds

## Next Steps for Developer

### Immediate (Debug Phase)
1. Add extensive logging to freecad_unfold.py unfold process:
   ```python
   for idx, face in enumerate(theFaceList):
       face_bbox = face.BoundBox
       print(f"Face {idx}: {face_bbox.XLength} x {face_bbox.YLength}")
   print(f"Shell total: {flat_shell.BoundBox.XLength} x {flat_shell.BoundBox.YLength}")
   ```

2. Test with known bent sheet (10001091875_Rev_00, part 10001081080_Rev_00)
3. Compare actual vs expected dimensions

### Secondary (Fix Implementation)
Once root cause confirmed:
- Fix BoundBox calculation in freecad_unfold.py
- Add validation (flat_width should be > original part width after expansion)
- Add test case to prevent regression

### Testing
- Verify fix produces 272mm for current test case
- Re-run full validation suite
- Check other bent sheet parts don't break

## Related Issues
- **NrHoles**: Separately identified - 11 vs 6 mismatch (different root cause)
- **DXF Format**: FreeCAD exports ARC/LINE primitives instead of LWPOLYLINE with hole layers

## References
- Test assemblies: `/data/input/10001091875_Rev_00.step`
- Reference XML: `/alestest/data/output/results10001091875.xml`
- Unfold script: `/manufacturing_pipeline/analysis/freecad_unfold.py`
- XML writer: `/manufacturing_pipeline/reporting/xml_exporter.py`
- Priority features: `/voorbeeldxml.xml` (reference data)

---

**Created**: March 10, 2026  
**Status**: 🔴 BLOCKER - Awaiting fix implementation  
**Owner**: Development team  
**Priority**: HIGH - Blocks GEZETTE_PLAAT (bent sheet) feature validation
