#!/usr/bin/env python3
"""Generate XML for STEP file with DXF metrics extraction.

Simple wrapper to generate XML output for comparison purposes.
"""

import argparse
import sys
from pathlib import Path
import xml.etree.ElementTree as ET

# Setup paths
sys.path.insert(0, str(Path.cwd()))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Generate BOM XML and compare against reference XML (sheet-focused comparator).'
    )
    parser.add_argument(
        '--step',
        type=str,
        default='',
        help='Path to STEP file (default: stepfiles/10040878_1.stp)'
    )
    parser.add_argument(
        '--reference',
        type=str,
        default='',
        help='Path to reference XML (default: stepfiles/Results<step_name>.xml when available)'
    )
    parser.add_argument(
        '--output',
        type=str,
        default='',
        help='Path to generated XML output (default: data/output/<step_name>_generated.xml)'
    )
    parser.add_argument(
        '--material',
        type=str,
        default='steel_s235',
        help='Material code used by export_bom_to_xml (default: steel_s235)'
    )
    parser.add_argument(
        '--no-compare',
        action='store_true',
        help='Skip comparison step and only generate XML'
    )
    return parser.parse_args()


def _resolve_paths(args: argparse.Namespace) -> tuple[Path, Path, Path]:
    script_dir = Path(__file__).parent
    parent_dir = script_dir.parent

    default_step = parent_dir / 'stepfiles' / '10040878_1.stp'
    step_file = Path(args.step).resolve() if args.step else default_step

    if args.output:
        output_xml = Path(args.output).resolve()
    else:
        output_xml = (script_dir / 'data' / 'output' / f'{step_file.stem}_generated.xml').resolve()

    if args.reference:
        reference_xml = Path(args.reference).resolve()
    else:
        candidate = parent_dir / 'stepfiles' / f'Results{step_file.stem}.xml'
        reference_xml = candidate.resolve() if candidate.exists() else Path('')

    # Also try cwd-relative fallback for step/ref when needed
    if not step_file.exists():
        alt_step = Path.cwd() / 'stepfiles' / step_file.name
        if alt_step.exists():
            step_file = alt_step.resolve()

    if reference_xml and not reference_xml.exists():
        alt_ref = Path.cwd() / 'stepfiles' / reference_xml.name
        if alt_ref.exists():
            reference_xml = alt_ref.resolve()

    return step_file, output_xml, reference_xml


def main():
    args = _parse_args()
    step_file, output_xml, reference_xml = _resolve_paths(args)
    
    # Make sure output dir exists
    output_xml.parent.mkdir(parents=True, exist_ok=True)
    
    if not step_file.exists():
        print(f"[ERROR] STEP file not found: {step_file}")
        return 1
    
    print(f"\n=== Generating XML with DXF Metrics ===\n")
    print(f"Input:      {step_file}")
    print(f"Output:     {output_xml}")
    print(f"Reference:  {reference_xml if reference_xml else 'None'}")
    
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
            material=args.material,
            output_xml_path=str(output_xml),
            work_dir=str(output_xml.parent),
            reference_xml_path=str(reference_xml) if reference_xml and reference_xml.exists() else None
        )
        
        print(f"\n[OK] XML generated: {output_path}")
        
        # Compare with reference if available
        if not args.no_compare and reference_xml and reference_xml.exists():
            print(f"\n[INFO] Comparing with reference XML...")
            compare_xmls(Path(output_path), reference_xml)
        elif not args.no_compare:
            print("\n[INFO] No reference XML found - skipped comparison")
        
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
        
        def _norm(value: str) -> str:
            txt = (value or '').strip()
            if txt.endswith('.xml'):
                txt = txt[:-4]
            return txt.lower()

        def _item_key(item: ET.Element) -> str:
            sheet_name = _norm(item.findtext('Sheet_Name', ''))
            part_name = _norm(item.findtext('Sheet_PartName', ''))
            item_type = _norm(item.findtext('Sheet_Type', ''))
            thickness = (item.findtext('Sheet_Thickness', '') or '').strip()
            if sheet_name:
                return f"sheet:{sheet_name}"
            if part_name:
                return f"part:{part_name}|type:{item_type}|t:{thickness}"
            return ''

        gen_by_key = {}
        for item in gen_results:
            key = _item_key(item)
            if key:
                gen_by_key[key] = item

        ref_by_key = {}
        for item in ref_results:
            key = _item_key(item)
            if key:
                ref_by_key[key] = item

        common_keys = sorted(set(gen_by_key.keys()) & set(ref_by_key.keys()))
        missing_in_generated = sorted(set(ref_by_key.keys()) - set(gen_by_key.keys()))
        extra_in_generated = sorted(set(gen_by_key.keys()) - set(ref_by_key.keys()))

        print(f"Matched items: {len(common_keys)}")
        print(f"Missing in generated: {len(missing_in_generated)}")
        print(f"Extra in generated: {len(extra_in_generated)}")

        if missing_in_generated:
            print("\n[WARN] Missing keys in generated XML:")
            for key in missing_in_generated:
                ref_item = ref_by_key[key]
                ref_sheet = (ref_item.findtext('Sheet_Name', '') or '').strip()
                ref_part = (ref_item.findtext('Sheet_PartName', '') or '').strip()
                print(f"  - {key} (Sheet_Name='{ref_sheet}', Sheet_PartName='{ref_part}')")

        if extra_in_generated:
            print("\n[INFO] Extra keys in generated XML:")
            for key in extra_in_generated:
                gen_item = gen_by_key[key]
                gen_sheet = (gen_item.findtext('Sheet_Name', '') or '').strip()
                gen_part = (gen_item.findtext('Sheet_PartName', '') or '').strip()
                print(f"  - {key} (Sheet_Name='{gen_sheet}', Sheet_PartName='{gen_part}')")

        # Compare matched items by key
        for idx, key in enumerate(common_keys):
            gen_item = gen_by_key[key]
            ref_item = ref_by_key[key]

            gen_name = (gen_item.findtext('Sheet_PartName', 'Unknown') or 'Unknown').strip()
            ref_name = (ref_item.findtext('Sheet_PartName', 'Unknown') or 'Unknown').strip()

            print(f"\n--- Item {idx}: {gen_name} vs {ref_name} [{key}] ---\n")
            
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
                
                gen_val = (gen_elem.text if gen_elem is not None and gen_elem.text is not None else '').strip()
                ref_val = (ref_elem.text if ref_elem is not None and ref_elem.text is not None else '').strip()
                
                if gen_val == ref_val:
                    if gen_val:
                        matches += 1
                else:
                    # Try numeric comparison with tolerance
                    try:
                        gen_f = float(gen_val) if gen_val else 0.0
                        ref_f = float(ref_val) if ref_val else 0.0
                        if abs(gen_f - ref_f) < 0.1:  # Small tolerance
                            print(f"≈ {field:25} {gen_val:12} ≈ {ref_val:12} (diff: {abs(gen_f-ref_f):.4f})")
                            matches += 1
                            continue
                    except (ValueError, TypeError):
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
