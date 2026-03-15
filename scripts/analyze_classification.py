#!/usr/bin/env python
"""Debug: Show classification details for specific parts."""

import sys
sys.path.insert(0, '.')

from manufacturing_pipeline.analysis.assembly_analysis import (
    analyze_assembly_complete,
    classify_solid,
    get_solid_bounding_box,
    get_solid_volume,
    get_solid_topology_counts
)
from pathlib import Path
import cadquery as cq

# Load STEP
step_file = Path('data/output/10000982426_Rev_00.step')
doc = cq.importers.importStep(str(step_file))

# Analyze assembly to get solids with names
analysis = analyze_assembly_complete(
    doc,
    assembly_name="10000982426_Rev_00",
    material="steel_s235",
    step_file_path=str(step_file)
)

flat_bom = analysis.get('flat_bom', [])

# Target items to analyze
targets = ['10000503252_Rev_00', '10000503253_Rev_00', '10000520371_Rev_00', '10000596440_Rev_00']

print("=== CLASSIFICATION DETAIL ANALYSIS ===\n")

# Get the part_name_to_solid mapping from analysis
# We need to access the solids directly
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_SOLID
from OCP.TopoDS import TopoDS

shape = doc.val().wrapped if hasattr(doc, 'val') else doc.wrapped if hasattr(doc, 'wrapped') else doc

solids = []
exp = TopExp_Explorer(shape, TopAbs_SOLID)
while exp.More():
    solids.append(TopoDS.Solid_s(exp.Current()))
    exp.Next()

# Map names to solids using the grouped_solids from assembly analysis
# We need to recreate the grouping logic to get the representative solids

from manufacturing_pipeline.analysis.assembly_analysis import parse_step_shape_rep_name_counts

shape_rep_counts = parse_step_shape_rep_name_counts(str(step_file))

# Assign names sequentially
solid_names = []
solid_idx = 0

if shape_rep_counts:
    for step_name, instance_count in shape_rep_counts.items():
        for i in range(instance_count):
            if solid_idx < len(solids):
                solid_names.append(step_name)
                solid_idx += 1

while solid_idx < len(solids):
    solid_names.append(f"Part_{solid_idx + 1}")
    solid_idx += 1

# Group by name
name_groups = {}
for idx, solid in enumerate(solids):
    name = solid_names[idx] if idx < len(solid_names) else f"Part_{idx+1}"
    if name not in name_groups:
        name_groups[name] = []
    name_groups[name].append(idx)

# Create mapping: name -> representative solid
name_to_solid = {}
for name, indices in name_groups.items():
    rep_idx = indices[0]
    name_to_solid[name] = solids[rep_idx]

# Now analyze each BOM item
for bom_item in flat_bom:
    part_name = bom_item.get('part_name', '')
    part_class = bom_item.get('part_class', '')
    
    if part_name not in targets:
        continue
    
    print(f"\n{'='*70}")
    print(f"Part: {part_name}")
    print(f"Current BOM Classification: {part_class}")
    print(f"{'='*70}")
    
    # Get the representative solid for this part
    if part_name in name_to_solid:
        solid = name_to_solid[part_name]
        
        # Get dimensions
        dims = get_solid_bounding_box(solid)
        volume = get_solid_volume(solid)
        faces, edges = get_solid_topology_counts(solid)
        
        sorted_dims = sorted(dims)
        smallest, middle, longest = sorted_dims
        
        # Calculate ratios
        thickness_ratio = smallest / longest if longest > 0 else 0
        aspect_ratio = longest / middle if middle > 0 else 0
        cross_ratio = middle / smallest if smallest > 0 else 0
        length_ratio = longest / smallest if smallest > 0 else 0
        
        bbox_volume = smallest * middle * longest
        volume_ratio = volume / bbox_volume if bbox_volume > 0 else 0
        
        print(f"\nDimensions (sorted): {smallest:.1f} x {middle:.1f} x {longest:.1f} mm")
        print(f"Volume: {volume:.1f} mm³")
        print(f"Topology: {faces} faces, {edges} edges")
        
        print(f"\nRatios:")
        print(f"  thickness_ratio = {thickness_ratio:.3f} (smallest/longest)")
        print(f"  aspect_ratio = {aspect_ratio:.3f} (longest/middle)")
        print(f"  cross_ratio = {cross_ratio:.3f} (middle/smallest)")
        print(f"  length_ratio = {length_ratio:.3f} (longest/smallest)")
        print(f"  volume_ratio = {volume_ratio:.3f} (volume/bbox)")
        
        # Run classification with trace
        classified, trace = classify_solid(solid, return_trace=True)
        
        print(f"\nClassification Result: {classified}")
        print(f"\nClassification Trace:")
        print(f"  Features: {trace.get('features', {})}")
        print(f"  Rules applied: {trace.get('rules', [])}")
        print(f"  Final: {trace.get('final', '')}")
        
        # Check specific criteria
        print(f"\nCriteria Check:")
        print(f"  PLAAT: thickness_ratio < 0.15? {thickness_ratio < 0.15} (is {thickness_ratio:.3f})")
        print(f"  PLAAT: smallest < 25mm? {smallest < 25} (is {smallest:.1f}mm)")
        print(f"  PLAAT: aspect_ratio > 5? {aspect_ratio > 5} (is {aspect_ratio:.1f})")
        print(f"  PROFIEL: smallest >= 5mm? {smallest >= 5} (is {smallest:.1f}mm)")
        print(f"  PROFIEL: length_ratio >= 5? {length_ratio >= 5} (is {length_ratio:.1f})")
        print(f"  PROFIEL: cross_ratio 0.5-2.0? {0.5 <= cross_ratio <= 2.0} (is {cross_ratio:.3f})")
        print(f"  PROFIEL: volume_ratio > 0.5? {volume_ratio > 0.5} (is {volume_ratio:.3f})")
    else:
        print(f"  [WARNING] No solid found at index {bom_index}")

print(f"\n{'='*70}\n")
