#!/usr/bin/env python3
"""
Manufacturing Pipeline - Backward Compatibility Shim

NOTE: This is the legacy entry point maintained for backward compatibility.
Please use the unified entry point instead:
    python run.py -f mypart.step --full

Or call the CLI module directly:
    python -m manufacturing_pipeline.cli
"""
from .cli import main

if __name__ == "__main__":
    main()
