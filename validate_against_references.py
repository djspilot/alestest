#!/usr/bin/env python3
"""
Validate pipeline output against reference XMLs for all STEP files in data/output
"""

import sys
sys.path.insert(0, '.')

from pathlib import Path
import cadquery as cq
from manufacturing_pipeline.analysis.assembly_analysis import analyze_assembly_complete
import xml.etree.ElementTree as ET
from collections import defaultdict

def parse_reference_xml(xml_path):
    """Parse reference XML and extract key metrics"""
    tree = ET.parse(xml_path)
    root = tree.getroot()
    
    parts = {}
    control = {}
    
    # Parse DocumentControl if present
    doc_control = root.find('.//DocumentControl')
    if doc_control is not None:
        for elem in doc_control:
            if elem.text:
                control[elem.tag] = elem.text
    
    # Parse all parts
    for result in root.findall('.//CalculationResult'):
        # Try different name fields
        name = None
        part_type = None
        count = 0
        
        # Check for specific type-prefixed fields first
        for field in ['Sheet_Name', 'Tube_Name', 'Others_Name']:
            val = result.findtext(field)
            if val and val.strip():
                name = val.strip()
                if 'Sheet' in field:
                    # Check if this is actually a profile based on Sheet_Type
                    sheet_type = result.findtext('Sheet_Type', '').strip()
                    if sheet_type == 'Profile':
                        part_type = 'profiel'
                    else:
                        part_type = 'plaat'
                elif 'Tube' in field:
                    part_type = 'profiel'
                elif 'Others' in field:
                    part_type = 'anders'
                break
        
        # Get count
        for field in ['Sheet_Count', 'Tube_Count', 'Others_Count']:
            val = result.findtext(field)
            if val and val.strip():
                try:
                    count = int(val)
                    break
                except ValueError:
                    pass
        
        if name and part_type:  # Only add if we have both name and type
            parts[name] = {'type': part_type, 'count': count}
    
    return control, parts

def compare_results(actual_bom, reference_parts, reference_control):
    """Compare actual BOM with reference"""
    
    # Count by type
    actual_counts = {'plaat': 0, 'profiel': 0, 'anders': 0}
    actual_parts = {}
    
    for item in actual_bom:
        part_class = item.get('part_class', 'anders')
        # Handle empty string part_class
        if not part_class or part_class not in ['plaat', 'profiel', 'anders']:
            part_class = 'anders'
        qty = item.get('quantity', 1)
        name = item.get('part_name', '')
        
        actual_counts[part_class] += qty
        actual_parts[name] = {'type': part_class, 'count': qty}
    
    ref_counts = {'plaat': 0, 'profiel': 0, 'anders': 0}
    for name, info in reference_parts.items():
        ref_counts[info['type']] += info['count']
    
    # Compare
    results = {
        'counts_match': actual_counts == ref_counts,
        'actual_counts': actual_counts,
        'reference_counts': ref_counts,
        'actual_parts': actual_parts,
        'reference_parts': reference_parts,
        'parts_match': {},
    }
    
    # Check each part
    for name, ref_info in reference_parts.items():
        if name in actual_parts:
            actual_info = actual_parts[name]
            match = (actual_info['type'] == ref_info['type'] and 
                    actual_info['count'] == ref_info['count'])
            results['parts_match'][name] = {
                'match': match,
                'actual': actual_info,
                'reference': ref_info
            }
        else:
            results['parts_match'][name] = {
                'match': False,
                'actual': None,
                'reference': ref_info
            }
    
    return results

def main():
    output_dir = Path('data/output')
    
    # Test cases: (step_file, reference_xml)
    test_cases = [
        ('10000982426_Rev_00.step', 'Results10000982426.xml'),
        ('10001081088_Rev_00.step', 'result10001081088.xml'),
        ('10001091099_Rev_00.step', 'result10001091099.xml'),
        ('10001091137_Rev_00.step', 'result10001091137.xml'),
        ('10001091875_Rev_00.step', 'results10001091875.xml'),
        ('10040878_1.stp', 'Results10040878_1.xml'),
    ]
    
    print("=" * 80)
    print("VALIDATION: Pipeline Output vs Reference XMLs")
    print("=" * 80)
    
    all_passed = True
    results_summary = []
    
    for step_file, ref_xml in test_cases:
        step_path = output_dir / step_file
        ref_path = output_dir / ref_xml
        
        print(f"\n{'─' * 80}")
        print(f"Testing: {step_file}")
        print(f"Reference: {ref_xml}")
        print(f"{'─' * 80}")
        
        if not step_path.exists():
            print(f"❌ SKIP: STEP file not found")
            continue
        
        if not ref_path.exists():
            print(f"❌ SKIP: Reference XML not found")
            continue
        
        try:
            # Load STEP file
            doc = cq.importers.importStep(str(step_path))
            
            # Run pipeline
            assembly_name = step_path.stem
            analysis = analyze_assembly_complete(
                doc,
                assembly_name=assembly_name,
                material='steel_s235',
                step_file_path=str(step_path)
            )
            
            flat_bom = analysis.get('flat_bom', [])
            
            # Parse reference
            ref_control, ref_parts = parse_reference_xml(ref_path)
            
            # Compare
            comparison = compare_results(flat_bom, ref_parts, ref_control)
            
            # Print results
            print(f"\nTotal parts: {len(flat_bom)}")
            print(f"\nClassification counts:")
            print(f"  Actual:    plaat={comparison['actual_counts']['plaat']:2d}  profiel={comparison['actual_counts']['profiel']:2d}  anders={comparison['actual_counts']['anders']:2d}")
            print(f"  Reference: plaat={comparison['reference_counts']['plaat']:2d}  profiel={comparison['reference_counts']['profiel']:2d}  anders={comparison['reference_counts']['anders']:2d}")
            
            if comparison['counts_match']:
                print(f"  ✅ Counts MATCH")
            else:
                print(f"  ❌ Counts MISMATCH")
                all_passed = False
            
            # Check individual parts
            print(f"\nPer-part validation:")
            for name, match_info in comparison['parts_match'].items():
                if match_info['match']:
                    print(f"  ✅ {name:30s} {match_info['actual']['type']:8s} × {match_info['actual']['count']}")
                else:
                    if match_info['actual']:
                        print(f"  ❌ {name:30s} Expected: {match_info['reference']['type']:8s} × {match_info['reference']['count']}, Got: {match_info['actual']['type']:8s} × {match_info['actual']['count']}")
                    else:
                        print(f"  ❌ {name:30s} Expected: {match_info['reference']['type']:8s} × {match_info['reference']['count']}, Got: NOT FOUND")
                    all_passed = False
            
            # Check for extra parts
            extra_parts = set(comparison['actual_parts'].keys()) - set(comparison['reference_parts'].keys())
            if extra_parts:
                print(f"\n  ⚠️  Extra parts not in reference:")
                for name in extra_parts:
                    info = comparison['actual_parts'][name]
                    print(f"     {name:30s} {info['type']:8s} × {info['count']}")
            
            results_summary.append({
                'file': step_file,
                'passed': comparison['counts_match'],
                'actual': comparison['actual_counts'],
                'reference': comparison['reference_counts']
            })
            
        except Exception as e:
            print(f"❌ ERROR: {e}")
            import traceback
            traceback.print_exc()
            all_passed = False
    
    # Final summary
    print(f"\n{'=' * 80}")
    print("SUMMARY")
    print(f"{'=' * 80}")
    
    for result in results_summary:
        status = "✅ PASS" if result['passed'] else "❌ FAIL"
        print(f"{status}  {result['file']:30s}  Actual: {result['actual']}  Ref: {result['reference']}")
    
    print(f"\n{'=' * 80}")
    if all_passed:
        print("✅ ALL TESTS PASSED")
    else:
        print("❌ SOME TESTS FAILED")
    print(f"{'=' * 80}\n")
    
    return 0 if all_passed else 1

if __name__ == '__main__':
    sys.exit(main())
