#!/usr/bin/env python3
import os
import sys
import glob
import pandas as pd
import argparse
from pathlib import Path

# Add project root to path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
sys.path.append(project_root)

from scripts.pipeline_functions import (
    run_analysis, 
    run_aag_analysis, 
    generate_compact_pdf
)

def normalize_key(key):
    """Normalize part name for matching (e.g. handle _R1 vs _1)."""
    return key.replace('_R', '_')

def load_ground_truth(input_dir):
    """Load ground truth data from Excel file in the directory."""
    excel_files = glob.glob(os.path.join(input_dir, '*.xlsx')) + glob.glob(os.path.join(input_dir, '*.xls'))
    if not excel_files:
        print("No Excel file found for ground truth comparison.")
        return {}
    
    excel_path = excel_files[0]
    print(f"Loading ground truth from: {excel_path}")
    
    try:
        # Read all data
        df = pd.read_excel(excel_path)
        
        # Clean up: remove rows where ArtikelNr is NaN or header repetition
        if 'ArtikelNr' in df.columns:
            df = df[df['ArtikelNr'].notna()]
            df = df[df['ArtikelNr'] != 'ArtikelNr']
            
            ground_truth = {}
            for _, row in df.iterrows():
                part_name = str(row['ArtikelNr']).strip()
                # Store both original and normalized keys
                ground_truth[part_name] = {
                    'Lengte': float(row['Lengte']) if pd.notnull(row.get('Lengte')) else 0,
                    'Breedte': float(row['Breedte']) if pd.notnull(row.get('Breedte')) else 0,
                    'Dikte': float(row['Dikte']) if pd.notnull(row.get('Dikte')) else 0,
                    'Snijgaten': int(row['Snijgaten']) if pd.notnull(row.get('Snijgaten')) else 0,
                    'ZetAantal': int(row['ZetAantal']) if pd.notnull(row.get('ZetAantal')) else 0,
                    'Aantaltegenzet': int(row['Aantaltegenzet']) if pd.notnull(row.get('Aantaltegenzet')) else 0
                }
                # Also add normalized version if different
                norm_name = normalize_key(part_name)
                if norm_name != part_name:
                     ground_truth[norm_name] = ground_truth[part_name]
                     
            return ground_truth
        else:
            print("Excel file does not contain 'ArtikelNr' column.")
            return {}
            
    except Exception as e:
        print(f"Error reading Excel: {e}")
        return {}

def batch_process(input_dir, output_base_dir):
    print(f"Batch processing directory: {input_dir}")
    
    # Load Ground Truth
    ground_truth = load_ground_truth(input_dir)
    
    # Find STEP files
    step_files = []
    for ext in ['*.stp', '*.step', '*.STP', '*.STEP']:
        step_files.extend(glob.glob(os.path.join(input_dir, ext)))
    
    if not step_files:
        print("No STEP files found.")
        return

    print(f"Found {len(step_files)} STEP files.")
    
    # Create output directory
    os.makedirs(output_base_dir, exist_ok=True)
    
    results = []
    
    for i, step_file in enumerate(step_files):
        part_name = os.path.splitext(os.path.basename(step_file))[0]
        # Handle potential suffix variations (e.g. _1, _Rev_00) if needed, 
        # but for now assume exact match or simple prefix match
        
        print(f"\n[{i+1}/{len(step_files)}] Processing {part_name}...")
        
        # Create part specific output dir
        part_output_dir = os.path.join(output_base_dir, part_name)
        os.makedirs(part_output_dir, exist_ok=True)
        
        # Mock args object for run_analysis
        class Args:
            debug = False
            no_unfold = False
            aag = True # Always run AAG for batch to get best results
            
        args = Args()
        
        try:
            # Run Analysis
            analysis, total_holes = run_analysis(step_file, part_output_dir, args)
            
            aag_result = run_aag_analysis(step_file)
            
            # Update analysis with AAG data
            if aag_result.get('success'):
                if aag_result.get('thickness', 0) > 0:
                    if analysis.thickness == 0:
                        analysis.thickness = aag_result['thickness']
                    elif abs(analysis.thickness - aag_result['thickness']) > 0.1:
                        if aag_result['thickness'] < 1.0 and analysis.thickness > 2.0:
                            pass 
                        else:
                            analysis.thickness = aag_result['thickness']
                
                if analysis.bend_count_erp == 0:
                    analysis.bend_count_erp = aag_result.get('bend_count', 0)
            
            # Get Unfold Results (Up/Down counts)
            unfold_result = getattr(analysis, 'unfold_result', None)
            up_count = 0
            down_count = 0
            if unfold_result and unfold_result.get('bends_logical'):
                bends = unfold_result.get('bends_logical')
                up_count = sum(1 for b in bends if b['type'] == 'up')
                down_count = sum(1 for b in bends if b['type'] == 'down')

            # Generate PDF
            pdf_path = generate_compact_pdf(step_file, part_output_dir, part_name, analysis, total_holes, unfold_result)
            
            # Compare with Ground Truth
            gt = ground_truth.get(part_name)
            if not gt:
                gt = ground_truth.get(normalize_key(part_name), {})
            
            # Collect results
            row = {
                'Filename': os.path.basename(step_file),
                'Part Name': part_name,
                'Dimensions': f"{analysis.length:.1f}x{analysis.width:.1f}x{analysis.height:.1f}",
                'Thickness (Calc)': analysis.thickness,
                'Thickness (Ref)': gt.get('Dikte', ''),
                'Bends (Calc)': analysis.bend_count_erp,
                'Bends (Ref)': gt.get('ZetAantal', ''),
                'Down Bends (Calc)': down_count,
                'Down Bends (Ref)': gt.get('Aantaltegenzet', ''),
                'Holes (Calc)': total_holes,
                'Holes (Ref)': gt.get('Snijgaten', ''),
                'Class': getattr(analysis, 'part_category', 'Unknown'),
                'Status': 'Success',
                'PDF': pdf_path
            }
            
            # Add validation flags
            if gt:
                row['Valid Thickness'] = abs(row['Thickness (Calc)'] - gt['Dikte']) < 0.1 if gt.get('Dikte') is not None else None
                row['Valid Bends'] = row['Bends (Calc)'] == gt['ZetAantal'] if gt.get('ZetAantal') is not None else None
                row['Valid Holes'] = row['Holes (Calc)'] == gt['Snijgaten'] if gt.get('Snijgaten') is not None else None
            
            results.append(row)
            
        except Exception as e:
            print(f"Error processing {part_name}: {e}")
            results.append({
                'Filename': os.path.basename(step_file),
                'Part Name': part_name,
                'Status': f"Error: {str(e)}"
            })

    # Save summary
    df = pd.DataFrame(results)
    summary_path = os.path.join(output_base_dir, 'batch_summary_comparison.csv')
    df.to_csv(summary_path, index=False)
    print(f"\nBatch processing complete. Summary saved to {summary_path}")
    
    # Print comparison summary
    if 'Valid Bends' in df.columns:
        print("\n--- Validation Summary ---")
        print(f"Total Parts: {len(df)}")
        print(f"Correct Bends: {df['Valid Bends'].sum()}/{df['Valid Bends'].count()}")
        print(f"Correct Holes: {df['Valid Holes'].sum()}/{df['Valid Holes'].count()}")
        print(f"Correct Thickness: {df['Valid Thickness'].sum()}/{df['Valid Thickness'].count()}")

if __name__ == "__main__":
    input_dir = "/Users/ds/Projecten/alestest/parts/AI-voorbeelden/20253511"
    output_dir = "/Users/ds/Projecten/alestest/output/20253511"
    batch_process(input_dir, output_dir)
