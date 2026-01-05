# Installation Guide

## Option 1: Pip (Recommended for quick start)

The project has been updated to use `cadquery` instead of `pythonocc-core`, which is easier to install via pip.

1.  Install dependencies:
    ```bash
    pip install -r manufacturing_pipeline/requirements.txt
    ```

2.  Run the pipeline:
    ```bash
    python manufacturing_pipeline/main.py
    ```

## Option 2: Conda (Recommended for stability)

If you encounter issues with pip, installing via Conda is more robust for engineering libraries.

1.  Install [Miniconda](https://docs.conda.io/en/latest/miniconda.html).
2.  Create an environment:
    ```bash
    conda create -n manufacturing python=3.10
    conda activate manufacturing
    ```
3.  Install dependencies:
    ```bash
    conda install -c conda-forge cadquery
    pip install -r manufacturing_pipeline/requirements.txt
    ```
