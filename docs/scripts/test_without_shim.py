#!/usr/bin/env python3
"""Test: werkt classify_step0 zonder shim?"""

from manufacturing_pipeline.analysis.assembly_analysis import load_solids_from_step
from manufacturing_pipeline.analysis.classification import classify_step0

# Laad STEP-file
stepfile = r'data\stepfile\Zetwerk\10000362951_Rev_01.step'
solids = load_solids_from_step(stepfile)
print(f'✓ {len(solids)} solid(s) geladen')

# Test classify_step0
if solids:
    result = classify_step0(solids[0].shape)
    print(f'✓ classify_step0 werkt!')
    print(f'  Label: {result.get("label")}')
    print(f'  Step:  {result.get("step")}')
    print(f'  Reason: {result.get("reason")[:100]}')
    print('\n✅ ANTWOORD: ja, code werkt zonder shim!')
else:
    print('❌ Geen solids geladen')
