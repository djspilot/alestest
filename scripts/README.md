# Scripts Directory

This directory contains utility and testing scripts for the manufacturing analysis pipeline.

## Analysis Scripts

### compare_erp.py
**ERP/Spaceclaim comparison tool** - Validates pipeline results against reference data

```bash
python scripts/compare_erp.py AI-voorbeelden/
```

Features:
- Compares pipeline detection with ERP Excel data and Spaceclaim XML
- Smart volume-based matching for multi-solid assemblies
- Optional AAG (Attributed Adjacency Graph) mode for higher accuracy
- Detailed mismatch reporting

### aag_analyzer.py
**Attributed Adjacency Graph feature recognition** - Advanced topology-based analysis

Can be used standalone or integrated with compare_erp.py via `--aag` flag.

Features:
- Topology graph construction (nodes=faces, arcs=edges)
- Isoperimetric Quotient for hole/slot classification
- K-factor based bend calculations
- Laser cutting time estimation

## Testing Scripts

### test_accuracy.py
**Validation against ERP data** - Compares detected features with expected values from Excel

```bash
python scripts/test_accuracy.py
```

Tests holes, bends, and thickness detection against known-good ERP data.

### test_freecad.py
**FreeCAD unfold functionality test** - Validates sheet metal unfolding

```bash
python scripts/test_freecad.py
```

### test_unfold_holes.py
**Unfold with hole detection test** - Tests hole detection on unfolded flat patterns

```bash
python scripts/test_unfold_holes.py
```

### debug_bends.py
**Bend detection debugger** - Detailed analysis of bend detection logic

```bash
python scripts/debug_bends.py
```

Shows why bends are counted or excluded based on business rules.

## Utility Scripts

### inspect_assembly.py
**STEP assembly inspector** - Examines structure of multi-solid STEP files

Useful for understanding assembly composition before analysis.

### probe_step_pmi.py
**PMI data probe** - Extracts Product Manufacturing Information from STEP files

Checks for embedded tolerances, annotations, and manufacturing data.

## Note

All scripts automatically adjust their paths to work from the scripts directory. They reference the main pipeline at `../manufacturing_pipeline/` and data files at `../data/`.
