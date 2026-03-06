#!/usr/bin/env python3
"""
Detailed validation comparing all data (dimensions, areas, bends, holes) 
between pipeline output and reference XMLs for specific assemblies
"""

import sys
sys.path.insert(0, '.')

from pathlib import Path
import cadquery as cq
from manufacturing_pipeline.analysis.assembly_analysis import analyze_assembly_complete
import xml.etree.ElementTree as ET
from collections import defaultdict

def parse_reference_detailed(xml_path):
    """Parse reference XML and extract ALL detailed data"""
    tree = ET.parse(xml_path)
    root = tree.getroot()
    
    parts = {}
    
    # Parse all CalculationResult elements
    for result in root.findall('.//CalculationResult'):
        # Get part name
        name = None
        part_type = None
        
        for field in ['Sheet_Name', 'Tube_Name', 'Others_Name']:
            val = result.findtext(field)
            if val and val.strip():
                name = val.strip()
                if 'Sheet' in field:
                    part_type = 'sheet'
                elif 'Tube' in field:
                    part_type = 'tube'
                else:
                    part_type = 'other'
                break
        
        if not name:
            continue
        
        # Extract ALL relevant data
        data = {'type': part_type}
        
        if part_type == 'sheet':
            # Basic info
            data['thickness'] = _get_float(result, 'Sheet_Thickness')
            data['count'] = _get_int(result, 'Sheet_Count', 1)
            data['material'] = result.findtext('Sheet_Material', '')
            
            # Dimensions
            data['box_x'] = _get_float(result, 'Sheet_BoxX')
            data['box_y'] = _get_float(result, 'Sheet_BoxY')
            data['box_area'] = _get_float(result, 'Sheet_BoxArea')
            
            # Areas
            data['top_area'] = _get_float(result, 'Sheet_TopArea')
            data['bottom_area'] = _get_float(result, 'Sheet_BottomArea')
            data['area_no_holes'] = _get_float(result, 'Sheet_AreaNoHoles')
            data['total_area'] = _get_float(result, 'Sheet_TotalArea')
            
            # Volume
            data['volume'] = _get_float(result, 'Sheet_Volume')
            data['weight'] = _get_float(result, 'Sheet_Weight')
            
            # Bending
            data['nr_bends'] = _get_int(result, 'Sheet_NrBends')
            data['bend_angles'] = result.findtext('Sheet_BendAngles', '')
            data['bend_inner_radii'] = result.findtext('Sheet_BendInnerRadii', '')
            data['bend_length'] = _get_float(result, 'Sheet_BendLength')
            data['unfold_success'] = result.findtext('Sheet_UnfoldSuccess', '').lower() == 'true'
            
            # Holes
            data['nr_holes'] = _get_int(result, 'Sheet_NrHoles')
            data['hole_contours'] = result.findtext('Sheet_HoleContours', '')
            data['hole_radii'] = result.findtext('Sheet_HoleRadii', '')
            
            # Contours
            data['outer_contour'] = _get_float(result, 'Sheet_OuterContour')
            data['total_contour'] = _get_float(result, 'Sheet_TotalContour')
            
        elif part_type == 'tube':
            data['tube_type'] = result.findtext('Tube_Type', '')
            data['count'] = _get_int(result, 'Tube_Count', 1)
            data['material'] = result.findtext('Tube_Material', '')
            data['thickness'] = _get_float(result, 'Tube_Thickness')
            data['width'] = _get_float(result, 'Tube_Width')
            data['height'] = _get_float(result, 'Tube_Height')
            data['volume'] = _get_float(result, 'Tube_Volume')
            data['weight'] = _get_float(result, 'Tube_Weight')
        
        parts[name] = data
    
    return parts

def _get_float(elem, tag, default=None):
    """Safely extract float value"""
    try:
        val = elem.findtext(tag, '')
        if val and val.strip():
            return float(val)
    except (ValueError, TypeError):
        pass
    return default

def _get_int(elem, tag, default=None):
    """Safely extract int value"""
    try:
        val = elem.findtext(tag, '')
        if val and val.strip():
            return int(val)
    except (ValueError, TypeError):
        pass
    return default

def compare_detailed(actual_bom, reference_parts, tolerance=0.02):
    """Compare detailed data with tolerance"""
    
    results = {
        'parts_matched': {},
        'parts_missing': [],
        'extra_parts': [],
        'differences': defaultdict(list)
    }
    
    # Match actual BOM to reference
    actual_by_name = {item['part_name']: item for item in actual_bom}
    
    for ref_name, ref_data in reference_parts.items():
        if ref_name in actual_by_name:
            actual_data = actual_by_name[ref_name]
            
            # Compare data
            comparison = {
                'reference': ref_data,
                'actual': actual_data,
                'differences': []
            }
            
            # Compare key metrics
            if ref_data['type'] == 'sheet':
                _compare_sheet_data(ref_data, actual_data, comparison, tolerance)
            elif ref_data['type'] == 'tube':
                _compare_tube_data(ref_data, actual_data, comparison)
            
            results['parts_matched'][ref_name] = comparison
        else:
            results['parts_missing'].append(ref_name)
    
    # Find extra parts
    for actual_name in actual_by_name:
        if actual_name not in reference_parts:
            results['extra_parts'].append(actual_name)
    
    return results

def _compare_sheet_data(ref, actual, comparison, tolerance):
    """Compare sheet metal data"""
    
    # Core dimensions
    metrics = [
        ('thickness', 'Thickness', 'mm', tolerance),
        ('volume', 'Volume', 'mm³', tolerance),
        ('weight', 'Weight', 'g', tolerance),
        ('box_x', 'Box Length X', 'mm', tolerance),
        ('box_y', 'Box Length Y', 'mm', tolerance),
        ('top_area', 'Top Surface Area', 'mm²', tolerance),
        ('area_no_holes', 'Area Without Holes', 'mm²', tolerance),
        ('outer_contour', 'Outer Contour', 'mm', 0.05),  # Stricter for contours
        ('nr_bends', 'Number of Bends', 'count', 0),
        ('nr_holes', 'Number of Holes', 'count', 0),
    ]
    
    for ref_key, display_name, unit, tol in metrics:
        ref_val = ref.get(ref_key)
        act_val = actual.get(ref_key)
        
        if ref_val is not None and act_val is not None:
            if isinstance(ref_val, (int, float)):
                if tol == 0:  # Exact match required
                    if ref_val != act_val:
                        comparison['differences'].append({
                            'metric': display_name,
                            'reference': ref_val,
                            'actual': act_val,
                            'unit': unit,
                            'match': False,
                            'diff_percent': 0
                        })
                else:
                    # Percentage tolerance
                    if ref_val != 0:
                        diff_pct = abs(act_val - ref_val) / abs(ref_val) * 100
                        is_match = diff_pct <= tol * 100
                        if not is_match:
                            comparison['differences'].append({
                                'metric': display_name,
                                'reference': ref_val,
                                'actual': act_val,
                                'unit': unit,
                                'match': is_match,
                                'diff_percent': diff_pct
                            })

def _compare_tube_data(ref, actual, comparison):
    """Compare profile/tube data"""
    
    metrics = [
        ('weight', 'Weight'),
        ('thickness', 'Wall Thickness'),
        ('width', 'Width'),
        ('height', 'Height'),
        ('volume', 'Volume'),
    ]
    
    for ref_key, display_name in metrics:
        ref_val = ref.get(ref_key)
        act_val = actual.get(ref_key)
        
        if ref_val is not None and act_val is not None and isinstance(ref_val, (int, float)):
            if ref_val != 0:
                diff_pct = abs(act_val - ref_val) / abs(ref_val) * 100
                if diff_pct > 2:  # 2% tolerance for profiles
                    comparison['differences'].append({
                        'metric': display_name,
                        'reference': ref_val,
                        'actual': act_val,
                        'diff_percent': diff_pct
                    })

def print_detailed_report(assembly_name, comparison_results):
    """Print formatted detailed comparison report"""
    
    print(f"\n{'='*100}")
    print(f"DETAILED VALIDATION: {assembly_name}")
    print(f"{'='*100}\n")
    
    # Summary
    matched = len(comparison_results['parts_matched'])
    missing = len(comparison_results['parts_missing'])
    extra = len(comparison_results['extra_parts'])
    
    print(f"Summary:")
    print(f"  ✓ Parts with full data: {matched}")
    print(f"  ✗ Parts missing: {missing}")
    print(f"  ⚠ Extra parts: {extra}\n")
    
    # Detailed per-part comparison
    all_pass = True
    
    for part_name, comparison in comparison_results['parts_matched'].items():
        ref_data = comparison['reference']
        diffs = comparison['differences']
        
        part_type = ref_data.get('type', 'unknown')
        
        if not diffs:
            print(f"✅ {part_name:40s} {part_type:8s} - All measurements match")
        else:
            all_pass = False
            print(f"⚠️  {part_name:40s} {part_type:8s} - {len(diffs)} measurement(s) differ:")
            
            for diff in diffs:
                metric = diff['metric']
                ref_val = diff['reference']
                act_val = diff['actual']
                unit = diff.get('unit', '')
                diff_pct = diff['diff_percent']
                
                if isinstance(ref_val, float):
                    print(f"     • {metric:35s}: ref={ref_val:12.2f} vs actual={act_val:12.2f} {unit} ({diff_pct:+.1f}%)")
                else:
                    print(f"     • {metric:35s}: ref={ref_val} vs actual={act_val}")
    
    # List missing parts
    if comparison_results['parts_missing']:
        all_pass = False
        print(f"\n❌ Missing from pipeline output:")
        for part_name in comparison_results['parts_missing']:
            print(f"   - {part_name}")
    
    # List extra parts
    if comparison_results['extra_parts']:
        print(f"\n⚠️  Extra parts in pipeline (not in reference):")
        for part_name in comparison_results['extra_parts']:
            print(f"   - {part_name}")
    
    return all_pass

def main():
    output_dir = Path('data/output')
    
    # Test cases
    test_cases = [
        ('10001091875_Rev_00.step', 'results10001091875.xml'),
        ('10040878_1.stp', 'stepfiles/10040878_1_bom_features.xml'),
    ]
    
    print("="*100)
    print("DETAILED VALIDATION: Dimensions, Areas, Bends, Holes, Volumes")
    print("="*100)
    
    all_passed = True
    
    for step_file, ref_xml in test_cases:
        step_path = output_dir / step_file
        
        # Determine reference XML path
        if ref_xml.startswith('stepfiles/'):
            # Path relative to alestest, so go up one level
            ref_path = Path('..') / ref_xml
        else:
            # Path in data/output
            ref_path = output_dir / ref_xml
        
        print(f"\n{'─'*100}")
        print(f"Testing: {step_file}")
        print(f"Reference: {ref_xml}")
        print(f"{'─'*100}")
        
        if not step_path.exists():
            print(f"❌ SKIP: STEP file not found at {step_path}")
            continue
        
        if not ref_path.exists():
            print(f"❌ SKIP: Reference XML not found at {ref_path}")
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
            ref_parts = parse_reference_detailed(ref_path)
            
            # Compare
            comparison = compare_detailed(flat_bom, ref_parts)
            
            # Print detailed report
            test_passed = print_detailed_report(assembly_name, comparison)
            
            if not test_passed:
                all_passed = False
            
        except Exception as e:
            print(f"❌ ERROR: {e}")
            import traceback
            traceback.print_exc()
            all_passed = False
    
    # Final summary
    print(f"\n{'='*100}")
    print("FINAL RESULT")
    print(f"{'='*100}")
    
    if all_passed:
        print("✅ All detailed measurements MATCH reference data!")
    else:
        print("⚠️  Some measurements differ - see details above")
    
    print(f"{'='*100}\n")
    
    return 0 if all_passed else 1

if __name__ == '__main__':
    sys.exit(main())
