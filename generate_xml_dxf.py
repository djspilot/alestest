#!/usr/bin/env python3
"""Generate XML for STEP file with DXF metrics extraction.

Simple wrapper to generate XML output for comparison purposes.
"""

import sys
from pathlib import Path
import xml.etree.ElementTree as ET

# Setup paths
sys.path.insert(0, str(Path.cwd()))

def main():
    # Get paths relative to this script's location, or parent directory
    script_dir = Path(__file__).parent
    parent_dir = script_dir.parent
    
    step_file = parent_dir / 'stepfiles' / '10040878_1.stp'
    output_xml = script_dir / 'data' / 'output' / '10040878_1_generated.xml'
    reference_xml = parent_dir / 'stepfiles' / 'Results10040878_1.xml'
    
    # Also try cwd-relative paths
    if not step_file.exists():
        step_file = Path.cwd() / 'stepfiles' / '10040878_1.stp'
    if not reference_xml.exists():
        reference_xml = Path.cwd() / 'stepfiles' / 'Results10040878_1.xml'
    
    # Make sure output dir exists
    output_xml.parent.mkdir(parents=True, exist_ok=True)
    
    if not step_file.exists():
        print(f"[ERROR] STEP file not found: {step_file}")
        return 1
    
    print(f"\n=== Generating XML with DXF Metrics ===\n")
    print(f"Input:      {step_file}")
    print(f"Output:     {output_xml}")
    print(f"Reference:  {reference_xml}")
    
    # Try to generate using the manufacturing pipeline
    try:
        from manufacturing_pipeline.analysis.assembly_analysis import analyze_assembly_complete
        from manufacturing_pipeline.reporting.xml_exporter import export_bom_to_xml
        import cadquery as cq
        
        # Load STEP file
        print(f"\n[INFO] Loading STEP file...")
        try:
            doc = cq.importers.importStep(str(step_file))
            print(f"[OK] STEP loaded via CadQuery")
        except Exception as e:
            print(f"[WARN] CadQuery load failed: {e}")
            print(f"[INFO] Attempting alternative approach...")
            raise
        
        # Analyze assembly
        print(f"\n[INFO] Analyzing assembly...")
        result = analyze_assembly_complete(doc, str(step_file))
        print(f"[OK] Assembly analyzed")
        bom_list = result.get('flat_bom', [])
        print(f"    - Parts in BOM: {len(bom_list)}")
        for i, item in enumerate(bom_list):
            print(f"      {i}: {item.get('part_name')} ({item.get('part_class', 'unknown')})")
        
        # Generate XML using export_bom_to_xml
        print(f"\n[INFO] Generating XML with export_bom_to_xml...")
        output_path = export_bom_to_xml(
            str(step_file),
            bom_list,
            material='steel_s235',
            output_xml_path=str(output_xml),
            work_dir=str(output_xml.parent),
            reference_xml_path=str(reference_xml) if reference_xml.exists() else None
        )
        
        print(f"\n[OK] XML generated: {output_path}")
        
        # Compare with reference if available
        if reference_xml.exists():
            print(f"\n[INFO] Comparing with reference XML...")
            compare_xmls(Path(output_path), reference_xml)
        
        return 0
        
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
        return 1


def compare_xmls(generated_path: Path, reference_path: Path):
    """Compare generated and reference XML files."""
    try:
        gen_tree = ET.parse(generated_path)
        ref_tree = ET.parse(reference_path)
        
        gen_root = gen_tree.getroot()
        ref_root = ref_tree.getroot()
        
        print(f"\n=== XML Comparison ===\n")
        
        # Get all CalculationResult elements
        gen_results = gen_root.findall('.//CalculationResult')
        ref_results = ref_root.findall('.//CalculationResult')
        
        print(f"Generated results: {len(gen_results)}")
        print(f"Reference results: {len(ref_results)}")
        
        if len(gen_results) == 0:
            print("[WARN] No results in generated XML")
            return
        
        # Compare results pairwise
        for idx in range(min(len(gen_results), len(ref_results))):
            gen_item = gen_results[idx]
            ref_item = ref_results[idx]
            
            gen_name = gen_item.findtext('Sheet_PartName', 'Unknown')
            ref_name = ref_item.findtext('Sheet_PartName', 'Unknown')
            
            print(f"\n--- Item {idx}: {gen_name} vs {ref_name} ---\n")
            
            # Key fields to compare
            key_fields = [
                'Sheet_PartName',
                'Sheet_Name',
                'Sheet_Type',
                'Sheet_Count',
                'Sheet_Material',
                'Sheet_Thickness',
                'Sheet_BoxX',
                'Sheet_BoxY',
                'Sheet_NrBends',
                'Sheet_BendAngles',
                'Sheet_BendLength',
                'Sheet_NrHoles',
                'Sheet_HoleContours',
                'Sheet_OuterContour',
                'Sheet_TotalContour',
                'Sheet_TopArea',
                'Sheet_AreaNoHoles',
                'Sheet_UnfoldSuccess',
            ]
            
            matches = 0
            diffs = 0
            
            for field in key_fields:
                gen_elem = gen_item.find(field)
                ref_elem = ref_item.find(field)
                
                gen_val = gen_elem.text if gen_elem is not None else ''
                ref_val = ref_elem.text if ref_elem is not None else ''
                
                if gen_val == ref_val:
                    if gen_val:
                        matches += 1
                else:
                    # Try numeric comparison with tolerance
                    try:
                        gen_f = float(gen_val) if gen_val else 0
                        ref_f = float(ref_val) if ref_val else 0
                        if abs(gen_f - ref_f) < 0.1:  # Small tolerance
                            print(f"≈ {field:25} {gen_val:12} ≈ {ref_val:12} (diff: {abs(gen_f-ref_f):.4f})")
                            matches += 1
                            continue
                    except ValueError:
                        pass
                    
                    print(f"✗ {field:25}")
                    print(f"    Gen: {gen_val}")
                    print(f"    Ref: {ref_val}")
                    diffs += 1
            
            print(f"\nMatches: {matches}, Differences: {diffs}")
        
    except Exception as e:
        print(f"[WARN] Comparison failed: {e}")


if __name__ == '__main__':
    sys.exit(main())
