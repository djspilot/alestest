"""
File utilities for manufacturing pipeline.
Handles file discovery, selection, batch processing, and output directories.
"""

import os
import sys
import glob
from types import SimpleNamespace
from multiprocessing import Pool

from manufacturing_pipeline.core.paths import PARTS_DIR, OUTPUT_DIR


def find_step_files(directory=None):
    """Find all STEP files in a directory or default PARTS_DIR."""
    if directory is None:
        directory = PARTS_DIR
    
    directory = os.path.abspath(directory)
    
    if not os.path.isdir(directory):
        return []
    
    step_files = []
    for ext in ['*.step', '*.stp', '*.STEP', '*.STP']:
        step_files.extend(glob.glob(os.path.join(directory, ext)))
    
    # Recursively search subdirectories
    for root, dirs, files in os.walk(directory):
        for ext in ['*.step', '*.stp', '*.STEP', '*.STP']:
            step_files.extend(glob.glob(os.path.join(root, ext)))
    
    return sorted(set(step_files))


def select_step_file(step_files):
    """Interactively select a STEP file from a list."""
    if not step_files:
        print("❌ Geen STEP bestanden gevonden.")
        return None
    
    if len(step_files) == 1:
        print(f"📁 Geselecteerd: {os.path.basename(step_files[0])}")
        return step_files[0]
    
    print("\n🔧 Beschikbare STEP bestanden:\n")
    for i, f in enumerate(step_files, 1):
        basename = os.path.basename(f)
        size_mb = os.path.getsize(f) / (1024 * 1024)
        print(f"  {i}. {basename} ({size_mb:.1f} MB)")
    
    while True:
        try:
            choice = input("\n📌 Selecteer bestandsnummer (of 'q' voor annuleren): ").strip()
            if choice.lower() == 'q':
                return None
            index = int(choice) - 1
            if 0 <= index < len(step_files):
                return step_files[index]
            print("❌ Ongeldig nummer.")
        except ValueError:
            print("❌ Voer een geldig getal in.")


def get_output_dir(step_file):
    """Determine output directory for a STEP file."""
    basename = os.path.basename(step_file)
    name_without_ext = os.path.splitext(basename)[0]
    output_subdir = os.path.join(OUTPUT_DIR, name_without_ext)
    os.makedirs(output_subdir, exist_ok=True)
    return output_subdir, name_without_ext


def process_single_file(step_file, args_dict, cache_data=None):
    """Worker function to process a single STEP file (for parallel processing)."""
    from manufacturing_pipeline.core.utils import run_analysis
    
    # Convert args dict back to namespace
    args = SimpleNamespace(**args_dict)
    
    output_dir, _ = get_output_dir(step_file)
    
    try:
        analysis, profiler = run_analysis(step_file, output_dir, args)
        return {
            'file': step_file,
            'success': True,
            'analysis': analysis,
            'profiler': profiler,
            'error': None
        }
    except Exception as e:
        return {
            'file': step_file,
            'success': False,
            'analysis': None,
            'profiler': None,
            'error': str(e)
        }


def process_batch(files, args, num_workers=4, progress_callback=None):
    """
    Process multiple STEP files in parallel.
    
    Args:
        files: List of STEP file paths
        args: Arguments namespace
        num_workers: Number of parallel workers
        progress_callback: Optional callback(completed, total) for progress updates
    
    Returns:
        List of result dicts with 'success', 'file', 'analysis', 'error' keys
    """
    if num_workers == 1:
        # Sequential processing (for debugging)
        results = []
        for i, f in enumerate(files):
            result = process_single_file(f, vars(args))
            results.append(result)
            if progress_callback:
                progress_callback(i + 1, len(files))
        return results
    
    # Parallel processing
    args_dict = vars(args)
    with Pool(num_workers) as pool:
        results = []
        for i, result in enumerate(pool.imap_unordered(
            process_single_file,
            [(f, args_dict) for f in files]
        )):
            results.append(result)
            if progress_callback:
                progress_callback(i + 1, len(files))
    
    return results
