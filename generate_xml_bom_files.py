#!/usr/bin/env python3
"""
Generate XML BOM files for STEP files and save them alongside the STEP files
"""

import sys
sys.path.insert(0, '.')

from pathlib import Path
import cadquery as cq
from manufacturing_pipeline.analysis.assembly_analysis import analyze_assembly_complete
import xml.etree.ElementTree as ET
from datetime import datetime

def generate_xml_bom(analysis, assembly_name, step_file_path):
    """Generate XML BOM file from analysis results"""
    
    root = ET.Element('DocumentElement')
    
    # Add document control info
    control = ET.SubElement(root, 'DocumentControl')
    ET.SubElement(control, 'GeneratedDate').text = datetime.now().isoformat()
    ET.SubElement(control, 'Assembly').text = assembly_name
    ET.SubElement(control, 'StepFile').text = str(step_file_path)
    ET.SubElement(control, 'Source').text = 'Manufacturing Pipeline v3.0'
    
    # Calculate classification summary from BOM items
    flat_bom = analysis.get('flat_bom', [])
    counts = {'plaat': 0, 'profiel': 0, 'anders': 0}
    for item in flat_bom:
        part_class = item.get('part_class', 'anders')
        qty = item.get('quantity', 1)
        if part_class in counts:
            counts[part_class] += qty
    
    ET.SubElement(control, 'Aantal_Plaat').text = str(counts.get('plaat', 0))
    ET.SubElement(control, 'Aantal_Profiel').text = str(counts.get('profiel', 0))
    ET.SubElement(control, 'Aantal_Anders').text = str(counts.get('anders', 0))
    ET.SubElement(control, 'Total_Parts').text = str(len(flat_bom))
    
    # Add each BOM item
    for item in flat_bom:
        result = ET.SubElement(root, 'CalculationResult')
        
        # Basic info
        ET.SubElement(result, 'Part_Name').text = item.get('part_name', '')
        ET.SubElement(result, 'Part_Class').text = item.get('part_class', 'anders')
        ET.SubElement(result, 'Quantity').text = str(item.get('quantity', 1))
        ET.SubElement(result, 'Classification_Source').text = item.get('classification_source', 'unknown')
        
        # Geometry data
        ET.SubElement(result, 'Volume_mm3').text = str(item.get('volume', 0))
        
        bbox = item.get('bbox', {})
        if bbox:
            ET.SubElement(result, 'BBox_X').text = str(bbox.get('x', 0))
            ET.SubElement(result, 'BBox_Y').text = str(bbox.get('y', 0))
            ET.SubElement(result, 'BBox_Z').text = str(bbox.get('z', 0))
        
        # Face data for plates
        face_data = item.get('face_data', {})
        if face_data:
            ET.SubElement(result, 'Planar_Faces').text = str(face_data.get('planar_faces', 0))
            ET.SubElement(result, 'Top2_Planar_Percent').text = str(face_data.get('top2_planar_percent', 0))
            ET.SubElement(result, 'Max_Face_Area').text = str(face_data.get('max_face_area', 0))
            ET.SubElement(result, 'Min_Face_Area').text = str(face_data.get('min_face_area', 0))
        
        # Metadata
        ET.SubElement(result, 'Reference_Used').text = str(item.get('reference_used', False))
        ET.SubElement(result, 'Solid_Index').text = str(item.get('solid_idx', -1))
    
    return root

def save_xml_bom(root, output_path):
    """Save XML to file with pretty formatting"""
    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    tree.write(output_path, encoding='utf-8', xml_declaration=True)

def process_step_file(step_path, output_dir):
    """Process single STEP file and generate XML"""
    
    print(f"\n{'─'*100}")
    print(f"Processing: {step_path.name}")
    print(f"{'─'*100}")
    
    if not step_path.exists():
        print(f"❌ File not found: {step_path}")
        return False
    
    try:
        # Load STEP
        print(f"📄 Loading STEP file...")
        doc = cq.importers.importStep(str(step_path))
        
        # Run pipeline
        assembly_name = step_path.stem
        print(f"🔍 Running pipeline analysis...")
        analysis = analyze_assembly_complete(
            doc,
            assembly_name=assembly_name,
            material='steel_s235',
            step_file_path=str(step_path)
        )
        
        # Generate XML
        print(f"📝 Generating XML...")
        root = generate_xml_bom(analysis, assembly_name, step_path)
        
        # Save XML alongside STEP file
        xml_filename = f"{step_path.stem}_generated.xml"
        xml_path = output_dir / xml_filename
        
        save_xml_bom(root, xml_path)
        print(f"✅ XML saved: {xml_path}")
        
        # Print summary
        flat_bom = analysis.get('flat_bom', [])
        counts = analysis.get('classification_counts', {})
        print(f"\n📊 BOM Summary:")
        print(f"   Total parts: {len(flat_bom)}")
        print(f"   Plaat (sheets): {counts.get('plaat', 0)}")
        print(f"   Profiel (profiles): {counts.get('profiel', 0)}")
        print(f"   Anders (other): {counts.get('anders', 0)}")
        
        print(f"\n📋 Parts in BOM:")
        for item in flat_bom:
            print(f"   • {item['part_name']:30s} {item['part_class']:10s} × {item['quantity']}")
        
        return True
        
    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    print("="*100)
    print("GENERATE XML BOM FILES FOR STEP FILES")
    print("="*100)
    
    output_dir = Path('data/output')
    
    # STEP files to process
    step_files = [
        output_dir / '10001091875_Rev_00.step',
        output_dir / '10040878_1.stp',
    ]
    
    results = []
    
    for step_file in step_files:
        success = process_step_file(step_file, output_dir)
        results.append((step_file.name, success))
    
    # Summary
    print(f"\n{'='*100}")
    print("SUMMARY")
    print(f"{'='*100}")
    
    for filename, success in results:
        status = "✅ SUCCESS" if success else "❌ FAILED"
        print(f"{status}  {filename}")
    
    all_success = all(r[1] for r in results)
    
    print(f"\n{'='*100}")
    if all_success:
        print("✅ All XML files generated successfully!")
    else:
        print("⚠️  Some files failed to process")
    print(f"{'='*100}\n")
    
    return 0 if all_success else 1

if __name__ == '__main__':
    sys.exit(main())
