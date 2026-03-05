#!/usr/bin/env python3
"""
Test BOM-to-XML export with STAP 1: PLAAT Processing.

Usage:
    python test_bom_to_xml.py [STEP_FILE] [MATERIAL] [REFERENCE_XML]

Example:
    python test_bom_to_xml.py stepfiles/10040878_1.stp steel_304
    python test_bom_to_xml.py stepfiles/3001-28608.stp steel_s235
    python test_bom_to_xml.py stepfiles/10040878_1.stp steel_304 stepfiles/result10040787_1
"""

import sys
import os
from pathlib import Path

# Setup paths
ROOT_DIR = Path(__file__).parent
sys.path.insert(0, str(ROOT_DIR))

def main():
    import cadquery as cq
    from manufacturing_pipeline.analysis.assembly_analysis import analyze_assembly_complete
    from manufacturing_pipeline.reporting.xml_exporter import export_bom_to_xml

    # Get arguments
    if len(sys.argv) < 2:
        print("Usage: python test_bom_to_xml.py <STEP_FILE> [MATERIAL] [REFERENCE_XML]")
        print("\nAvailable test STEP files:")
        stepfiles_dir = ROOT_DIR / "stepfiles"
        if stepfiles_dir.exists():
            for f in sorted(stepfiles_dir.glob("*.stp")) + sorted(stepfiles_dir.glob("*.STEP")):
                print(f"  - {f.name}")
        sys.exit(1)

    step_file = Path(sys.argv[1])
    material = sys.argv[2] if len(sys.argv) > 2 else "steel_s235"
    reference_xml = Path(sys.argv[3]) if len(sys.argv) > 3 else None

    if not step_file.exists():
        print(f"✗ File not found: {step_file}")
        sys.exit(1)

    print("\n" + "="*70)
    print(f"BOM-to-XML Export Test (STAP 1: PLAAT Processing)")
    print("="*70)

    print(f"\n[FILE] Input STEP:  {step_file.name}")
    print(f"[MAT]  Material:   {material}")
    if reference_xml:
        print(f"[REF]  XML Source: {reference_xml.name}")

    # STEP 1: Load and analyze BOM
    print(f"\n[STEP 1] Loading STEP and analyzing assembly...")
    try:
        doc = cq.importers.importStep(str(step_file))
        bom_result = analyze_assembly_complete(
            doc,
            assembly_name=step_file.stem,
            material=material,
            step_file_path=str(step_file)
        )
        bom_list = bom_result.get('flat_bom', [])
        print(f"  [OK] BOM loaded: {len(bom_list)} items")

        # Show BOM summary
        print(f"\n  BOM Summary:")
        for idx, item in enumerate(bom_list[:5], 1):  # Show first 5
            print(f"    {idx}. {item.get('part_name', 'Unknown'):30} | Qty: {item.get('quantity', 1):3} | Class: {item.get('part_class', 'unknown')}")

        if len(bom_list) > 5:
            print(f"    ... and {len(bom_list) - 5} more")

    except Exception as e:
        print(f"  ✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    # STEP 2: Export to XML with full feature extraction
    print(f"\n[STEP 2] Exporting BOM to XML with feature extraction...")
    try:
        output_xml = step_file.parent / f"{step_file.stem}_bom_features.xml"

        xml_path = export_bom_to_xml(
            step_file_path=str(step_file),
            bom_list=bom_list,
            material=material,
            output_xml_path=str(output_xml),
            reference_xml_path=str(reference_xml) if reference_xml else None
        )

        print(f"\n  [OK] XML created: {Path(xml_path).name}")

    except Exception as e:
        print(f"  [ERR] Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    # STEP 3: Display XML excerpt
    print(f"\n[STEP 3] XML Preview (first 50 lines):")
    print("-" * 70)

    xml_content = Path(xml_path).read_text(encoding='utf-8')
    lines = xml_content.split('\n')

    for line in lines[:50]:
        print(line)

    if len(lines) > 50:
        print(f"... ({len(lines) - 50} more lines)")

    print("-" * 70)
    print(f"\n[OK] Full XML saved to: {xml_path}")
    print("\n[INFO] Next: Review XML in Excel or open with text editor")
    print("   You can now control:")
    print("   - Sheet_BoxX/Y (flat dimensions after unfold)")
    print("   - Sheet_NrBends, Sheet_BendAngles, Sheet_BendInnerRadii")
    print("   - Sheet_NrHoles, Sheet_HoleContours, Sheet_HoleRadii")
    print("   - Sheet_Material (from K-factor)")

if __name__ == "__main__":
    main()
