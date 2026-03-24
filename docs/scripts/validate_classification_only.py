#!/usr/bin/env python3
"""
Validate classification counts for test files.

Only checks part_class counts (plaat/profiel/anders), not unfold or dimensions.
"""

import sys
from pathlib import Path
from typing import Dict, List

# Setup paths
ROOT_DIR = Path(__file__).parent
sys.path.insert(0, str(ROOT_DIR))

import cadquery as cq
from manufacturing_pipeline.analysis.assembly_analysis import analyze_assembly_complete


def validate_classification(step_file: Path, expected: Dict[str, int]) -> Dict:
    """
    Validate classification counts for a STEP file.
    
    Args:
        step_file: Path to STEP file
        expected: Dict with expected counts {'plaat': 2, 'profiel': 2, 'anders': 1}
    
    Returns:
        Dict with validation results
    """
    print(f"\n{'='*80}")
    print(f"VALIDATING: {step_file.name}")
    print(f"{'='*80}")
    
    # Load and analyze
    try:
        doc = cq.importers.importStep(str(step_file))
        bom_result = analyze_assembly_complete(
            doc,
            assembly_name=step_file.stem,
            material="steel_304",
            step_file_path=str(step_file)
        )
        bom_list = bom_result.get('flat_bom', [])
    except Exception as e:
        print(f"ERROR: Failed to analyze file: {e}")
        return {
            'file': step_file.name,
            'status': 'ERROR',
            'error': str(e)
        }
    
    # Count classifications
    counts = {
        'plaat': 0,
        'profiel': 0,
        'anders': 0
    }
    
    items_by_class = {
        'plaat': [],
        'profiel': [],
        'anders': []
    }
    
    for item in bom_list:
        part_class = item.get('part_class', 'anders').lower()
        part_name = item.get('part_name', 'Unknown')
        qty = item.get('quantity', 1)
        
        if part_class in counts:
            counts[part_class] += 1
            items_by_class[part_class].append(f"{part_name} (qty={qty})")
    
    # Compare with expected
    print(f"\nExpected: {expected['plaat']} plaat, {expected['profiel']} profiel, {expected['anders']} anders")
    print(f"Got:      {counts['plaat']} plaat, {counts['profiel']} profiel, {counts['anders']} anders")
    
    # Check if matches
    plaat_ok = counts['plaat'] == expected['plaat']
    profiel_ok = counts['profiel'] == expected['profiel']
    anders_ok = counts['anders'] == expected['anders']
    all_ok = plaat_ok and profiel_ok and anders_ok
    
    # Detailed breakdown
    print(f"\nDetailed Breakdown:")
    print(f"  PLAAT ({counts['plaat']}): {'✓ PASS' if plaat_ok else '✗ FAIL'}")
    for item in items_by_class['plaat']:
        print(f"    - {item}")
    
    print(f"  PROFIEL ({counts['profiel']}): {'✓ PASS' if profiel_ok else '✗ FAIL'}")
    for item in items_by_class['profiel']:
        print(f"    - {item}")
    
    print(f"  ANDERS ({counts['anders']}): {'✓ PASS' if anders_ok else '✗ FAIL'}")
    for item in items_by_class['anders']:
        print(f"    - {item}")
    
    # Overall status
    status = "✓ PASS" if all_ok else "✗ FAIL"
    print(f"\n{'='*80}")
    print(f"RESULT: {status}")
    print(f"{'='*80}")
    
    return {
        'file': step_file.name,
        'status': 'PASS' if all_ok else 'FAIL',
        'expected': expected,
        'actual': counts,
        'plaat_ok': plaat_ok,
        'profiel_ok': profiel_ok,
        'anders_ok': anders_ok,
        'items': items_by_class
    }


def main():
    """Run classification validation for all test files."""
    
    # Test files with expected classification counts
    test_files = [
        {
            'file': '../stepfiles/10040852_1.stp',
            'expected': {'plaat': 2, 'profiel': 2, 'anders': 1}
        },
        {
            'file': '../stepfiles/10040878_1.stp',
            'expected': {'plaat': 2, 'profiel': 2, 'anders': 1}
        },
        {
            'file': '../stepfiles/2006020_A-00.STEP',
            'expected': {'plaat': 0, 'profiel': 0, 'anders': 2}
        },
        {
            'file': '../stepfiles/MD-16-03698_R2.stp',
            'expected': {'plaat': 2, 'profiel': 1, 'anders': 2}
        },
        {
            'file': '../stepfiles/31686-080.stp',
            'expected': {'plaat': 8, 'profiel': 0, 'anders': 10}
        }
    ]
    
    # Run validation
    results = []
    for test in test_files:
        step_file = Path(test['file'])
        if not step_file.exists():
            print(f"\n✗ File not found: {step_file}")
            results.append({
                'file': step_file.name,
                'status': 'ERROR',
                'error': 'File not found'
            })
            continue
        
        result = validate_classification(step_file, test['expected'])
        results.append(result)
    
    # Summary
    print(f"\n\n{'='*80}")
    print(f"VALIDATION SUMMARY")
    print(f"{'='*80}\n")
    
    passed = sum(1 for r in results if r.get('status') == 'PASS')
    failed = sum(1 for r in results if r.get('status') == 'FAIL')
    errors = sum(1 for r in results if r.get('status') == 'ERROR')
    
    print(f"Total Files:  {len(results)}")
    print(f"Passed:       {passed} ✓")
    print(f"Failed:       {failed} ✗")
    print(f"Errors:       {errors}")
    print()
    
    # Detailed results table
    print(f"{'File':<25} {'Plaat':>8} {'Profiel':>8} {'Anders':>8} {'Status':>10}")
    print(f"{'-'*80}")
    
    for r in results:
        if r.get('status') == 'ERROR':
            print(f"{r['file']:<25} {'ERROR':>40}")
            continue
        
        exp = r['expected']
        act = r['actual']
        
        plaat_str = f"{act['plaat']}/{exp['plaat']}"
        profiel_str = f"{act['profiel']}/{exp['profiel']}"
        anders_str = f"{act['anders']}/{exp['anders']}"
        
        status_icon = "✓" if r['status'] == 'PASS' else "✗"
        
        print(f"{r['file']:<25} {plaat_str:>8} {profiel_str:>8} {anders_str:>8} {status_icon:>10}")
    
    print(f"\n{'='*80}")
    
    # Exit code
    if failed > 0 or errors > 0:
        print(f"\n⚠️  VALIDATION FAILED - {failed + errors} file(s) with issues")
        sys.exit(1)
    else:
        print(f"\n✓ ALL VALIDATIONS PASSED")
        sys.exit(0)


if __name__ == "__main__":
    main()
