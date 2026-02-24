#!/usr/bin/env python3
"""
Manufacturing Pipeline - convenience wrapper.

Usage:
    python run.py [args]          # Same as: python -m manufacturing_pipeline [args]

Quick mode (default):
    python run.py -f mypart.step          Analyze a single file
    python run.py --batch                 Batch process all files
    python run.py --aag -v                AAG analysis with verbose output

Full ISO pipeline:
    python run.py -f mypart.step --full   Complete ISO analysis with database
"""
from manufacturing_pipeline.cli import main

if __name__ == "__main__":
    main()
