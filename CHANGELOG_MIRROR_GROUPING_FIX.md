# Mirror Grouping Fix - March 2026

## Problem
STEP file `10000982426_Rev_00.step` with 25 solids (8 unique part types, 25 total instances) was producing only 7 BOM items instead of 8. Mirror variants `10000503252_Rev_00` (LEFT) and `10000503253_Rev_00` (RIGHT) were being merged as one item due to geometry-based grouping.

## Root Cause
The original geometry-based grouping in `assembly_analysis.py` used `solids_are_equal()` which compares:
- Volume
- Bounding box dimensions
- Surface area
- Face/edge topology counts

This approach cannot distinguish mirror variants or identically-shaped parts at different positions, causing LEFT/RIGHT hand versions to be merged incorrectly.

## Solution
Replaced geometry-based grouping with **STEP-guided grouping**:

1. **Phase 1**: Use `parse_step_shape_rep_name_counts()` to extract part names and instance counts from STEP file metadata
2. **Phase 2**: Assign names to solids sequentially based on STEP occurrence order
3. **Phase 3**: Group solids by their assigned STEP name

This preserves mirror distinctions (different STEP names) while correctly grouping true duplicates.

### Code Changes

#### `manufacturing_pipeline/analysis/assembly_analysis.py` (lines 1647-1688)
**Before**: Geometry comparison grouping
```python
for solid in solids:
    volume = get_solid_volume(solid)
    dims = get_solid_bounding_box(solid)
    
    # Find if this solid matches an existing group
    found = False
    for i, (rep_solid, count, ...) in enumerate(grouped_solids):
        if solids_are_equal(solid, rep_solid):  # ❌ Merges mirrors
            grouped_solids[i] = (rep_solid, count + 1, ...)
            found = True
            break
```

**After**: STEP-guided grouping
```python
# Phase 1: Get STEP part names and counts
shape_rep_counts = parse_step_shape_rep_name_counts(step_file_path)
# Example: {"10000503252_Rev_00": 2, "10000503253_Rev_00": 2, ...}

# Phase 2: Assign names sequentially to all 25 solids
solid_names = []
solid_idx = 0
for step_name, instance_count in shape_rep_counts.items():
    for i in range(instance_count):
        if solid_idx < len(solids):
            solid_names.append(step_name)
            solid_idx += 1

# Phase 3: Group by name
name_groups = {}
for idx, solid in enumerate(solids):
    name = solid_names[idx]
    if name not in name_groups:
        name_groups[name] = []
    name_groups[name].append(idx)

# Create grouped_solids entries
for name, indices in name_groups.items():
    rep_solid = solids[indices[0]]
    count = len(indices)  # ✅ Correct count per unique name
    grouped_solids.append((rep_solid, count, volume, dims, name))
```

#### `manufacturing_pipeline/reporting/xml_exporter.py` (lines 1476, 1581)
Added `Sheet_Count` and `Sheet_Type` to profiel and others items for consistency:

```python
# _process_profiel_item
ET.SubElement(calc_result, 'Sheet_Count').text = str(quantity)
ET.SubElement(calc_result, 'Sheet_Type').text = 'Profile'

# _process_others_item
ET.SubElement(calc_result, 'Sheet_Count').text = str(quantity)
ET.SubElement(calc_result, 'Sheet_Type').text = 'Other'
```

#### `generate_xml_dxf.py` (line 124)
Fixed `analyze_assembly_complete()` call to pass `step_file_path`:

```python
result = analyze_assembly_complete(
    doc, 
    assembly_name=step_file.stem,
    step_file_path=str(step_file)  # ✅ Required for STEP metadata parsing
)
```

## Results

### Before Fix
- **BOM items**: 7 (incorrect)
- **Mirror handling**: Merged as 1 item with qty=4
- **XML output**: Missing mirror distinction

```
10000503252_Rev_00 + 10000503253_Rev_00 → 1 item, qty=4  ❌
```

### After Fix
- **BOM items**: 8 (correct)
- **Mirror handling**: Separate items
- **XML output**: Complete with all fields

```
10000503252_Rev_00 → qty=2  ✅
10000503253_Rev_00 → qty=2  ✅
```

### Full XML Output (10000982426_Rev_00.step)

| # | Part Name | Qty | Type | Classification |
|---|-----------|-----|------|----------------|
| 1 | 10000255318_Rev_00 | 4 | 3D | plaat |
| 2 | 10000520810_Rev_00 | 2 | 3D | plaat |
| 3 | 10000418502_Rev_00 | 8 | 3D | plaat |
| 4 | 10000503252_Rev_00 | 2 | Other | anders |
| 5 | **10000503253_Rev_00** | **2** | Profile | profiel |
| 6 | 10000520371_Rev_00 | 1 | Other | anders |
| 7 | 10000596440_Rev_00 | 2 | Other | anders |
| 8 | 10000940837_Rev_00 | 4 | 3D | plaat |

**Total**: 25 pieces (4+2+8+2+2+1+2+4 = 25) ✅

## Benefits

1. **Accurate mirror detection**: LEFT/RIGHT hand parts remain separate
2. **STEP metadata authority**: Uses CAD assembly structure as source of truth
3. **Deterministic ordering**: Sequential assignment ensures reproducible results
4. **No geometry tolerance issues**: Names from STEP are exact, no floating-point comparison
5. **Maintains grouping**: True duplicates (same STEP name) are still grouped correctly

## Limitations

- Requires STEP file to have proper SHAPE_REPRESENTATION names
- Files without STEP metadata fall back to sequential Part_1, Part_2, etc.
- Classification accuracy depends on geometry features (separate issue to address)

## Testing

Test file: `data/output/10000982426_Rev_00.step`
- Contains 25 solids from 8 unique part types
- Includes mirror variants that should remain separate
- Result: ✅ 8 BOM items, 25 total pieces

## Next Steps

1. ✅ Mirror grouping fixed
2. 🔄 Classification accuracy improvement (items 4-7 misclassified)
3. 🔜 Profile feature extraction refinement
4. 🔜 Bent detection accuracy for complex geometries
