# Installation Guide

## Option 1: Pip (Recommended for quick start)

The project has been updated to use `cadquery` instead of `pythonocc-core`, which is easier to install via pip.

1.  Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```

2.  Run the pipeline:
    ```bash
    python run.py
    ```

3.  Verify or install host Python dependencies such as `cadquery`:
    ```bash
    python -m manufacturing_pipeline.tools.ensure_python_deps --doctor
    python -m manufacturing_pipeline.tools.ensure_python_deps
    ```

The host dependency preflight also verifies `shapely`, because STEP classification and profile section analysis import it directly.

## Windows bootstrap (recommended on a fresh PC)

On a new Windows machine, use the repo bootstrapper instead of installing Python, Node, Git, viewer dependencies, and the FreeCAD unfold runtime manually:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\bootstrap-windows.ps1
```

Or:

```bat
bootstrap-windows.bat
```

It will:
- install `Python`, `Node.js`, and `Git` with `winget`, or `Chocolatey` as fallback
- create a local `.venv`
- install `requirements.txt`
- run `ensure_python_deps`
- run `ensure_unfold_runtime`
- run `npm install` in `viewer/`
- finish with doctor output

Useful flags:

```powershell
.\scripts\bootstrap-windows.ps1 -DoctorOnly
.\scripts\bootstrap-windows.ps1 -SkipViewer
.\scripts\bootstrap-windows.ps1 -SkipFreeCAD
```

## Headless FreeCAD unfold runtime

If you need sheet-metal unfolding, do not rely on the desktop FreeCAD app path. Use the managed headless runtime instead:

```bash
python -m manufacturing_pipeline.tools.ensure_unfold_runtime
```

This command:
- installs a local FreeCAD runtime under `.runtime/freecad`
- clones the `SheetMetal` source workbench into that runtime
- verifies `FreeCADCmd`, `Part`, and `SheetMetalUnfolder`
- persists the runtime metadata for normal pipeline runs

Useful variants:

```bash
python -m manufacturing_pipeline.tools.ensure_unfold_runtime --no-install
python -m manufacturing_pipeline.tools.ensure_unfold_runtime --update-sheetmetal
python -m manufacturing_pipeline.tools.ensure_unfold_runtime --json
```

On both macOS and Windows the pipeline prefers the headless `FreeCADCmd` subprocess route by default.

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
    pip install -r requirements.txt
    ```
