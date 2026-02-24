"""Test script for XML export functionality.

Tests the complete workflow: STEP analysis → XML export
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from manufacturing_pipeline.scripts.aag_analyzer import analyze_with_aag
from manufacturing_pipeline.analysis.part_analyzer import PartAnalyzer
from manufacturing_pipeline.reporting.xml_exporter import export_to_xml


def test_xml_export(step_file: str):
    """Test XML export with a sample STEP file.

    Args:
        step_file: Path to STEP file
    """
    print(f"\n{'='*60}")
    print(f"Testing XML export with: {step_file}")
    print(f"{'='*60}\n")

    # Step 1: Analyze STEP file
    print("[1/3] Running AAG analysis...")
    result = analyze_with_aag(step_file, enable_unfold=True, verbose=False)

    # Step 2: Add part classification
    print("[2/3] Classifying part...")
    analyzer = PartAnalyzer()
    category, part_type, reasoning = analyzer.classify_part(result)

    result['category'] = category
    result['part_type'] = part_type
    result['file'] = Path(step_file).name
    result['success'] = True

    # Print summary
    print(f"\nAnalysis results:")
    print(f"  Category: {category}")
    print(f"  Part type: {part_type}")
    print(f"  Thickness: {result.get('thickness', 'N/A')} mm")
    print(f"  Dimensions: {result.get('dimensions', {})}")
    print(f"  Holes: {result.get('production', {}).get('holes_total', 0)}")
    print(f"  Bends: {result.get('production', {}).get('bends_total', 0)}")

    # Step 3: Export to XML
    print(f"\n[3/3] Exporting to XML...")
    output_path = Path("data/output") / f"{Path(step_file).stem}.xml"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    export_to_xml(result, output_path)

    print(f"✓ XML exported to: {output_path}")

    # Read and display XML
    print(f"\nGenerated XML content:")
    print("-" * 60)
    xml_content = output_path.read_text(encoding='utf-8')
    print(xml_content)
    print("-" * 60)

    print(f"\n✓ Test completed successfully!")
    print(f"  XML file: {output_path}")


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description="Test XML export functionality")
    parser.add_argument('step_file', nargs='?',
                       default='data/input/10015088_3.stp',
                       help="Path to STEP file (default: data/input/10015088_3.stp)")

    args = parser.parse_args()

    test_xml_export(args.step_file)
